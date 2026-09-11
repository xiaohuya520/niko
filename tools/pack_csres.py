#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把看板的静态资源从 app 镜像里搬到独立 Flash 分区(csres),给主固件瘦身。

背景
----
`tools/gen_csboard_assets.py` 生成的 `main/cs_assets.c` / `main/cs_font_cn16.c`
把全部像素(105 支战队 x 48px/20px RGB565 ≈ 555KB + 中文字体位图 ≈ 296KB)
编进了 app 镜像,而 app 分区被硬限制在 3MB。本脚本把这些字节原样搬出去:

    prebuilt/csres.bin          资源包 = 64 字节头(magic/version/CRC32/各段偏移) + 负载
    main/cs_assets.c            改写成"瘦"版:只留 id 索引,运行时从 mmap 出来的
                                分区里把像素拼成 lv_image_dsc_t
    main/cs_font_cn16.c         改写成"瘦"版:去掉 glyph_bitmap,留 1 字节占位,
                                开机由 cs_font_cn16_bind() 绑到映射区

**字节完全复用**:本脚本只做搬运,不重编码,所以画质与改造前逐字节一致。

用法
----
    # 1) 生成/改写(默认在仓库根读写,可重复执行)
    python3 tools/pack_csres.py

    # 2) 把资源包写进 merge-bin 出来的合并镜像(csres 分区偏移取自 partitions.csv)
    python3 tools/pack_csres.py --inject build/FoloToy-AI-Passport-full.bin

    # 3) 校验合并镜像里的资源包(CI 用)
    python3 tools/pack_csres.py --verify build/FoloToy-AI-Passport-full.bin

注意:重新跑 `gen_csboard_assets.py` 会再次产出"胖"源文件,之后必须再跑一次本脚本。
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAGIC = b"CSR2"
VERSION = 1
HDR_SIZE = 64
LOGO48_EDGE = 48
LOGO20_EDGE = 20
LOGO48_BYTES = LOGO48_EDGE * LOGO48_EDGE * 2
LOGO20_BYTES = LOGO20_EDGE * LOGO20_EDGE * 2

HEX_BYTE_RE = re.compile(r"0x([0-9A-Fa-f]{2})")


# ------------------------------------------------------------------ 解析

def parse_c_bytes(body: str) -> bytes:
    return bytes(int(t, 16) for t in HEX_BYTE_RE.findall(body))


def find_array(text: str, name: str, start: int = 0) -> tuple[int, int, bytes] | None:
    """返回 (声明起始下标, '};' 之后的下标, 数据)。"""
    m = re.search(r"^[^\n]*\b%s\[\]\s*=\s*\{" % re.escape(name), text[start:], re.M)
    if not m:
        return None
    begin = start + m.start()
    brace = start + m.end() - 1
    end = text.find("};", brace)
    if end < 0:
        raise ValueError("数组 %s 没有闭合" % name)
    return begin, end + 2, parse_c_bytes(text[brace:end])


def extract_logos(text: str) -> tuple[list[str], dict[str, bytes], dict[str, bytes]]:
    """抽出所有 logo48_<cid>_map / logo20_<cid>_map 的字节。"""
    big: dict[str, bytes] = {}
    small: dict[str, bytes] = {}
    order: list[str] = []
    for m in re.finditer(r"static\s+const\s+uint8_t\s+logo(48|20)_([A-Za-z0-9_]+)_map\[\]\s*=\s*\{", text):
        edge, cid = m.group(1), m.group(2)
        brace = text.index("{", m.end() - 1)
        end = text.find("};", brace)
        data = parse_c_bytes(text[brace:end])
        want = LOGO48_BYTES if edge == "48" else LOGO20_BYTES
        if len(data) != want:
            raise ValueError("logo%s_%s 长度 %d != %d" % (edge, cid, len(data), want))
        if edge == "48":
            if cid in big:
                raise ValueError("重复的 48px cid: %s" % cid)
            big[cid] = data
            order.append(cid)
        else:
            small[cid] = data
    if set(order) != set(small):
        missing = sorted(set(order) ^ set(small))
        raise ValueError("48px/20px 队标集合不一致: %s" % missing[:8])
    return order, big, small


ROW_RE = re.compile(r'\{\s*"([^"]+)"\s*,\s*&logo48_([A-Za-z0-9_]+)\s*,\s*&logo20_([A-Za-z0-9_]+)\s*\}')


def extract_rows(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for m in ROW_RE.finditer(text):
        ident, c48, c20 = m.group(1), m.group(2), m.group(3)
        if c48 != c20:
            raise ValueError("查表项 %s 的 48/20 名字不一致" % ident)
        rows.append((ident, c48))
    if not rows:
        raise ValueError("没找到 CS_LOGOS 查表")
    return rows


# ------------------------------------------------------------------ 打包

def build_blob(font: bytes, order: list[str], big: dict[str, bytes],
               small: dict[str, bytes]) -> bytes:
    font_off = HDR_SIZE
    l48_off = font_off + len(font)
    l20_off = l48_off + sum(len(big[c]) for c in order)
    total = l20_off + sum(len(small[c]) for c in order)

    hdr = bytearray(HDR_SIZE)
    hdr[0:4] = MAGIC
    struct.pack_into("<I", hdr, 4, VERSION)
    struct.pack_into("<I", hdr, 8, total)
    struct.pack_into("<I", hdr, 12, 0)                     # crc32 占位
    struct.pack_into("<I", hdr, 16, font_off)
    struct.pack_into("<I", hdr, 20, len(font))
    struct.pack_into("<I", hdr, 24, l48_off)
    struct.pack_into("<I", hdr, 28, len(order) * LOGO48_BYTES)
    struct.pack_into("<I", hdr, 32, l20_off)
    struct.pack_into("<I", hdr, 36, len(order) * LOGO20_BYTES)
    struct.pack_into("<I", hdr, 40, len(order))

    body = bytearray(hdr)
    body += font
    for c in order:
        body += big[c]
    for c in order:
        body += small[c]
    struct.pack_into("<I", body, 12, zlib.crc32(bytes(body[HDR_SIZE:])) & 0xFFFFFFFF)
    return bytes(body)


def read_csres_partition(csv_path: Path) -> tuple[int, int]:
    for raw in csv_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5 and parts[0] == "csres":
            return int(parts[3], 16), int(parts[4], 16)
    raise SystemExit("partitions.csv 里没有 csres 分区")


# ------------------------------------------------------------------ 产出瘦版源码

ASSETS_TEMPLATE = '''// 自动生成,请勿手改 —— tools/pack_csres.py
//
// 队标像素已外置到 Flash 资源分区 csres(prebuilt/csres.bin),本文件只保留
// id 查表 + 运行时把映射区里的像素拼成 lv_image_dsc_t,不再占用 app 分区。
//
// 重新生成资源的正确顺序:
//     python3 tools/gen_csboard_assets.py ...   # 产出"胖"源文件(位图在内)
//     python3 tools/pack_csres.py               # 把位图搬到 csres.bin
#include "cs_assets.h"

#include <stdbool.h>
#include <string.h>

#include "esp_log.h"
#include "esp_partition.h"

#define CS_ASSETS_TAG   "csassets"
#define CS_RES_LABEL    "csres"
#define CS_RES_MAGIC    "CSR2"
#define CS_RES_VERSION  __VERSION__u

#define CS_LOGO_N       __COUNT__
#define CS_LOGO48_EDGE  __EDGE48__
#define CS_LOGO20_EDGE  __EDGE20__
#define CS_LOGO48_BYTES (CS_LOGO48_EDGE * CS_LOGO48_EDGE * 2)
#define CS_LOGO20_BYTES (CS_LOGO20_EDGE * CS_LOGO20_EDGE * 2)

// csres 包头(64 字节,小端)。crc32 覆盖 [64, total_len),由 CI 侧校验;
// 设备上只核对 magic / version / 长度,不在启动路径上算 CRC。
typedef struct {
    uint8_t  magic[4];
    uint32_t version;
    uint32_t total_len;
    uint32_t crc32;
    uint32_t font_off;
    uint32_t font_len;
    uint32_t l48_off;
    uint32_t l48_len;
    uint32_t l20_off;
    uint32_t l20_len;
    uint32_t logo_count;
    uint32_t reserved[5];
} cs_res_hdr_t;

typedef struct {
    const char *id;
    uint16_t    idx;
} cs_logo_ent_t;

static const cs_logo_ent_t CS_LOGOS[] = {
__ROWS__};

// 运行时拼出来的图像描述符(BSS 约 __DSC_KB__KB;像素本身留在 Flash,不进 RAM)
static lv_image_dsc_t s_dsc48[CS_LOGO_N];
static lv_image_dsc_t s_dsc20[CS_LOGO_N];
static const uint8_t *s_l48;
static const uint8_t *s_l20;
static bool           s_loaded;

static bool cs_id_eq(const char *a, const char *b)
{
    if (!a || !b) return false;
    while (*a && *b) {
        char ca = *a, cb = *b;
        if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');
        if (ca != cb) return false;
        a++; b++;
    }
    return *a == 0 && *b == 0;
}

static const cs_logo_ent_t *cs_logo_find(const char *id)
{
    if (!id || !id[0]) return NULL;
    for (unsigned i = 0; i < sizeof(CS_LOGOS) / sizeof(CS_LOGOS[0]); i++)
        if (cs_id_eq(CS_LOGOS[i].id, id)) return &CS_LOGOS[i];
    return NULL;
}

static void config_dsc(lv_image_dsc_t *dsc, const uint8_t *data, uint16_t edge)
{
    memset(dsc, 0, sizeof(*dsc));
    dsc->header.magic  = LV_IMAGE_HEADER_MAGIC;
    dsc->header.cf     = LV_COLOR_FORMAT_RGB565;
    dsc->header.w      = edge;
    dsc->header.h      = edge;
    dsc->header.stride = (uint32_t)edge * 2u;
    dsc->data_size     = (uint32_t)edge * edge * 2u;
    dsc->data          = data;
}

// 把 csres 分区映射进地址空间并绑定字体位图。必须在第一次用 font_cn16 /
// cs_logo_* 之前调用(app_main 里)。映射常驻,不 munmap。
// 返回 false 时队标会退化为占位徽章,中文则不可用 —— 说明烧录的镜像不完整。
bool cs_assets_load(void)
{
    if (s_loaded) return true;

    const esp_partition_t *part = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_SPIFFS, CS_RES_LABEL);
    if (!part) {
        ESP_LOGE(CS_ASSETS_TAG, "没有 %s 分区 —— 请烧录完整的合并镜像", CS_RES_LABEL);
        return false;
    }

    const void *base = NULL;
    esp_partition_mmap_handle_t handle = 0;
    esp_err_t err = esp_partition_mmap(part, 0, part->size, ESP_PARTITION_MMAP_DATA,
                                      &base, &handle);
    if (err != ESP_OK || base == NULL) {
        ESP_LOGE(CS_ASSETS_TAG, "映射 %s 失败: %s", CS_RES_LABEL, esp_err_to_name(err));
        return false;
    }

    const cs_res_hdr_t *hdr = (const cs_res_hdr_t *)base;
    if (memcmp(hdr->magic, CS_RES_MAGIC, 4) != 0) {
        ESP_LOGE(CS_ASSETS_TAG, "资源包 magic 不符 —— 镜像里的 %s 段是空的",
                 CS_RES_LABEL);
        return false;
    }
    if (hdr->version != (uint32_t)CS_RES_VERSION) {
        ESP_LOGE(CS_ASSETS_TAG, "资源包版本 %u,固件要求 %u",
                 (unsigned)hdr->version, (unsigned)CS_RES_VERSION);
        return false;
    }
    if (hdr->logo_count != (uint32_t)CS_LOGO_N ||
        hdr->total_len > part->size ||
        hdr->font_len == 0u ||
        hdr->l48_len < (uint32_t)CS_LOGO_N * (uint32_t)CS_LOGO48_BYTES ||
        hdr->l20_len < (uint32_t)CS_LOGO_N * (uint32_t)CS_LOGO20_BYTES) {
        ESP_LOGE(CS_ASSETS_TAG, "资源包尺寸不符: count=%u/%u total=%u/%u",
                 (unsigned)hdr->logo_count, (unsigned)CS_LOGO_N,
                 (unsigned)hdr->total_len, (unsigned)part->size);
        return false;
    }

    const uint8_t *raw = (const uint8_t *)base;
    s_l48 = raw + hdr->l48_off;
    s_l20 = raw + hdr->l20_off;

    for (uint16_t i = 0; i < (uint16_t)CS_LOGO_N; i++) {
        config_dsc(&s_dsc48[i], s_l48 + (uint32_t)i * (uint32_t)CS_LOGO48_BYTES,
                   (uint16_t)CS_LOGO48_EDGE);
        config_dsc(&s_dsc20[i], s_l20 + (uint32_t)i * (uint32_t)CS_LOGO20_BYTES,
                   (uint16_t)CS_LOGO20_EDGE);
    }

    if (!cs_font_cn16_bind(raw + hdr->font_off, hdr->font_len)) {
        ESP_LOGE(CS_ASSETS_TAG, "中文字体位图绑定失败");
        return false;
    }

    s_loaded = true;
    ESP_LOGI(CS_ASSETS_TAG, "资源包就绪: %u 支战队,字体位图 %u 字节(Flash 映射)",
             (unsigned)CS_LOGO_N, (unsigned)hdr->font_len);
    return true;
}

const lv_image_dsc_t *cs_logo_get(const char *id)
{
    const cs_logo_ent_t *e = cs_logo_find(id);
    if (!e || !s_loaded) return NULL;
    return &s_dsc48[e->idx];
}

const lv_image_dsc_t *cs_logo_get_small(const char *id)
{
    const cs_logo_ent_t *e = cs_logo_find(id);
    if (!e || !s_loaded) return NULL;
    return &s_dsc20[e->idx];
}
'''

FONT_NOTE = """/* 位图已外置到 Flash 资源分区(csres),开机由 cs_assets_load() 经
 * cs_font_cn16_bind() 绑定到映射区;这里只留 1 字节占位数组。 */
static const uint8_t glyph_bitmap_stub[1] = { 0 };
"""

FONT_BINDER = """
/*--------------------
 *  位图绑定(位图外置在 csres 分区)
 *--------------------*/
/*由 cs_assets_load() 在开机时调用;失败则中文字形不可用。*/
bool cs_font_cn16_bind(const void *bitmap, uint32_t len)
{
    if (bitmap == NULL || len < 64u) return false;
    font_dsc.glyph_bitmap = (const uint8_t *)bitmap;
    return true;
}
"""


def slim_assets(rows: list[tuple[str, str]], cid_index: dict[str, int], count: int) -> str:
    body = []
    for ident, cid in rows:
        body.append('    { "%s", %d },\n' % (ident, cid_index[cid]))
    dsc = count * 2 * 44 / 1024.0
    return (ASSETS_TEMPLATE
            .replace("__VERSION__", str(VERSION))
            .replace("__COUNT__", str(count))
            .replace("__EDGE48__", str(LOGO48_EDGE))
            .replace("__EDGE20__", str(LOGO20_EDGE))
            .replace("__ROWS__", "".join(body))
            .replace("__DSC_KB__", "%.1f" % dsc))


def slim_font(text: str) -> tuple[str, int]:
    """去掉 glyph_bitmap,留占位 + 绑定函数;返回 (新文本, 原位图字节数)。"""
    found = find_array(text, "glyph_bitmap")
    if not found:
        raise SystemExit("cs_font_cn16.c 里找不到 glyph_bitmap(可能已经瘦过了)")
    begin, end, data = found
    text = text[:begin] + FONT_NOTE + text[end:]

    need = "static const lv_font_fmt_txt_dsc_t font_dsc = {"
    if need not in text:
        raise SystemExit("找不到 font_dsc 定义,无法去掉 const")
    text = text.replace(need, "static lv_font_fmt_txt_dsc_t font_dsc = {", 1)
    text = text.replace(".glyph_bitmap = glyph_bitmap,",
                        ".glyph_bitmap = glyph_bitmap_stub,", 1)

    marker = "#endif /*#if FONT_CN16*/"
    if marker not in text:
        raise SystemExit("找不到 FONT_CN16 的 #endif")
    text = text.replace(marker, FONT_BINDER + "\n" + marker, 1)
    return text, len(data)


# ------------------------------------------------------------------ 主流程

def generate(root: Path) -> int:
    assets_p = root / "main" / "cs_assets.c"
    font_p = root / "main" / "cs_font_cn16.c"
    out_p = root / "prebuilt" / "csres.bin"

    a_text = assets_p.read_text(encoding="utf-8", errors="replace")
    f_text = font_p.read_text(encoding="utf-8", errors="replace")

    order, big, small = extract_logos(a_text)
    rows = extract_rows(a_text)
    cid_index = {cid: i for i, cid in enumerate(order)}
    for _ident, cid in rows:
        if cid not in cid_index:
            raise SystemExit("查表项的队标 %s 没有像素数据" % cid)

    font_raw = find_array(f_text, "glyph_bitmap")
    if not font_raw:
        raise SystemExit("cs_font_cn16.c 里找不到 glyph_bitmap")
    font_bytes = font_raw[2]

    f_slim, font_len = slim_font(f_text)
    blob = build_blob(font=font_bytes, order=order, big=big, small=small)

    off, size = read_csres_partition(root / "partitions.csv")
    if len(blob) > size:
        raise SystemExit("资源包 %d 字节超过 csres 分区 %d 字节" % (len(blob), size))

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(blob)
    assets_p.write_text(slim_assets(rows, cid_index, len(order)), encoding="utf-8")
    font_p.write_text(f_slim, encoding="utf-8")

    print("[csres] %s : %d 字节 (%.1fKB)" % (out_p.relative_to(root), len(blob), len(blob) / 1024))
    print("        字体位图 %d 字节 / 队标 %d 支 x (48px %d + 20px %d)"
          % (font_len, len(order), LOGO48_BYTES, LOGO20_BYTES))
    print("        分区 csres @0x%X size=0x%X,剩余 %d 字节" % (off, size, size - len(blob)))
    print("        main/cs_assets.c -> %d 字节" % assets_p.stat().st_size)
    print("        main/cs_font_cn16.c -> %d 字节" % font_p.stat().st_size)
    return 0


def inject(merged: Path, blob: Path, csv: Path) -> int:
    off, size = read_csres_partition(csv)
    data = bytearray(merged.read_bytes())
    payload = blob.read_bytes()
    if len(payload) > size:
        raise SystemExit("资源包比 csres 分区大")
    if len(data) < off:
        data.extend(b"\xff" * (off - len(data)))
    end = off + len(payload)
    if len(data) < end:
        data.extend(b"\xff" * (end - len(data)))
    data[off:end] = payload
    merged.write_bytes(bytes(data))
    print("[csres] 已注入 %s: %d 字节 @0x%X,镜像现在 %d 字节"
          % (merged.name, len(payload), off, len(data)))
    return 0


def verify(merged: Path, csv: Path) -> int:
    off, size = read_csres_partition(csv)
    data = merged.read_bytes()
    if len(data) < off + HDR_SIZE:
        print("ERROR: 镜像没有到 csres 分区(镜像只有 %d 字节)" % len(data), file=sys.stderr)
        return 1
    hdr = data[off:off + HDR_SIZE]
    if hdr[0:4] != MAGIC:
        print("ERROR: csres 处不是资源包(magic=%r)" % hdr[0:4], file=sys.stderr)
        return 1
    version, total_len, crc = struct.unpack_from("<III", hdr, 4)
    font_off, font_len = struct.unpack_from("<II", hdr, 16)
    l48_off, l48_len = struct.unpack_from("<II", hdr, 24)
    l20_off, l20_len = struct.unpack_from("<II", hdr, 32)
    (count,) = struct.unpack_from("<I", hdr, 40)

    problems = []
    if version != VERSION:
        problems.append("version=%d" % version)
    if total_len > size:
        problems.append("total_len=%d > 分区 %d" % (total_len, size))
    if off + total_len > len(data):
        problems.append("镜像被截断: 需要 %d 实际 %d" % (off + total_len, len(data)))
    if count != (l48_len // LOGO48_BYTES if l48_len else 0) or l48_len % LOGO48_BYTES:
        problems.append("48px 段长度 %d 不是 %d 的整数倍" % (l48_len, LOGO48_BYTES))
    if l20_len != count * LOGO20_BYTES:
        problems.append("20px 段长度 %d != %d x %d" % (l20_len, count, LOGO20_BYTES))
    if font_len < 1024:
        problems.append("字体位图长度可疑: %d" % font_len)
    for name, o, n in (("font", font_off, font_len), ("logo48", l48_off, l48_len),
                       ("logo20", l20_off, l20_len)):
        if o < HDR_SIZE or o + n > total_len:
            problems.append("%s 段越界: off=%d len=%d total=%d" % (name, o, n, total_len))
    if not problems and off + total_len <= len(data):
        got = zlib.crc32(data[off + HDR_SIZE:off + total_len]) & 0xFFFFFFFF
        if got != crc:
            problems.append("CRC32 不符: 包内 %08X 实算 %08X" % (crc, got))
    if problems:
        for p in problems:
            print("ERROR: csres %s" % p, file=sys.stderr)
        return 1
    print("[csres] 校验通过: %d 支战队,字体位图 %d 字节,负载共 %d 字节 @0x%X"
          % (count, font_len, total_len, off))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="把静态资源搬到 csres 分区")
    ap.add_argument("--root", default=str(ROOT), help="仓库根(默认脚本上一级)")
    ap.add_argument("--inject", metavar="MERGED_BIN", help="把资源包写进合并镜像")
    ap.add_argument("--verify", metavar="MERGED_BIN", help="校验合并镜像里的资源包")
    ap.add_argument("--blob", default=None, help="资源包路径(默认 prebuilt/csres.bin)")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    csv = root / "partitions.csv"
    blob = Path(a.blob) if a.blob else root / "prebuilt" / "csres.bin"

    if a.verify:
        return verify(Path(a.verify), csv)
    if a.inject:
        if not blob.is_file():
            print("ERROR: 缺少 %s,先跑一次 pack_csres.py" % blob, file=sys.stderr)
            return 1
        return inject(Path(a.inject), blob, csv)
    return generate(root)


if __name__ == "__main__":
    raise SystemExit(main())
