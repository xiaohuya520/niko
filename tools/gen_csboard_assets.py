#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成 CS2 看板的静态资源(中文字体 + 真实战队队标)。

产物(直接覆盖仓库里的对应文件,都是"自动生成、勿手改"):
    main/cs_font_cn16.c   中文字体 16px,ASCII + GB2312 常用汉字(3755 一级汉字)
    main/cs_assets.c      9 支战队队标,48px(比分卡) / 20px(列表缩略) 两档 RGB565

依赖:
    pip install pillow fonttools brotli
    npm install lv_font_conv        # LVGL 官方字体生成器

用法:
    python tools/gen_csboard_assets.py \
        --ttf  <NotoSansSC.ttf> \
        --logo-dir <战队PNG目录> \
        --out-dir main

环境变量:
    NODE_BIN        node 可执行文件(默认取 WorkBuddy 托管 node)
    LV_FONT_CONV    lv_font_conv.js 路径(默认取托管 node_modules)

字体来源:Noto Sans SC(= 思源黑体,与 LVGL 内置 SourceHanSans 同源)。
  woff2 用 fontTools 转 TTF 时必须清掉 flavor,否则仍是 wOF2 封装。
"""
import argparse
import os
import subprocess
import sys

# ---------------------------------------------------------------- 字体

# 界面兜底字符:即使不在 GB2312 里也强制加入,避免界面出现空白方块
UI_EXTRA = ("：，。、！？（）《》「」％·—…‘’“”【】　"
            "赛事看板实时比分近期战绩预告网络设置已连接未扫描中失败离线在线"
            "进行结束开始第场地图暂无数据加载刷新更新时间来源胜负历史对阵选择"
            "重新找到保存加密开放信号密码输入目标删除切换提交字母大小写数字符"
            "号确定上下单击双击返回共页次双方战队比赛日程"
            "地图待定淘汰赛小组四分之一决赛半决决冠军联赛挑战者公开世界大师杯站")


def gb2312_chars(level1_only=True):
    """GB2312 符号区(A1-A9) + 一级汉字(B0-D7);level1_only=False 时含二级汉字。"""
    hi_end = 0xD8 if level1_only else 0xF8
    out = []
    for hi in range(0xA1, hi_end):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode('gb2312'))
            except Exception:
                continue
    return out


def gen_font(ttf, out_c, name, size, bpp, node, conv):
    from fontTools.ttLib import TTFont

    f = TTFont(ttf)
    cmap = set(f.getBestCmap().keys())
    f.close()

    chars = set(range(0x20, 0x7F))
    for ch in gb2312_chars():
        if ord(ch) in cmap:
            chars.add(ord(ch))
    for ch in UI_EXTRA:
        if ord(ch) not in cmap:
            print('[warn] 字体缺字: %r U+%04X' % (ch, ord(ch)))
        else:
            chars.add(ord(ch))

    symbols = ''.join(chr(c) for c in sorted(chars))
    print('[font] glyph 数 = %d' % len(symbols))

    cmd = [node, conv,
           '--font', ttf, '-r', '0x20-0x7F', '--symbols', symbols,
           '--size', str(size), '--bpp', str(bpp),
           '--format', 'lvgl', '--lv-include', 'lvgl.h',
           '--lv-font-name', name, '-o', out_c]
    r = subprocess.run(cmd, cwd=os.path.dirname(conv), capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit('lv_font_conv 失败 rc=%d' % r.returncode)
    print('[font] ok %s (%d 字节源码)' % (out_c, os.path.getsize(out_c)))


# ---------------------------------------------------------------- 队标

SIZES = (48, 20)              # 48=比分卡, 20=列表缩略
PLATE_LIGHT = (240, 243, 248)
PLATE_DARK = (23, 28, 38)


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def flatten(path, size):
    """等比缩放到 size 内并居中;按队标亮度自动选底板色,保证深浅主题下都清晰。"""
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    w, h = im.size
    sc = min(size / w, size / h)
    nw, nh = max(1, int(w * sc + 0.5)), max(1, int(h * sc + 0.5))
    im = im.resize((nw, nh), Image.LANCZOS)

    px = im.load()
    tot = wsum = 0.0
    for y in range(nh):
        for x in range(nw):
            r, g, b, a = px[x, y]
            if a < 16:
                continue
            tot += (0.299 * r + 0.587 * g + 0.114 * b) * a
            wsum += a
    lum = (tot / wsum) if wsum > 0 else 255.0
    plate = PLATE_DARK if lum > 140 else PLATE_LIGHT

    canvas = Image.new('RGBA', (size, size), plate + (255,))
    canvas.paste(im, ((size - nw) // 2, (size - nh) // 2), im)
    return canvas.convert('RGB'), plate, lum


def emit_bytes(f, name, data, per_line=12):
    f.write('static const uint8_t %s[] = {\n' % name)
    for i in range(0, len(data), per_line):
        f.write('    ' + ', '.join('0x%02X' % b for b in data[i:i + per_line]) + ',\n')
    f.write('};\n\n')


def gen_logos(logo_dir, out_c):
    ids = sorted(fn[:-4] for fn in os.listdir(logo_dir) if fn.lower().endswith('.png'))
    if not ids:
        raise SystemExit('目录里没有 PNG: %s' % logo_dir)

    with open(out_c, 'w', encoding='utf-8', newline='\n') as f:
        f.write('// 自动生成,请勿手改 —— 见 tools/gen_csboard_assets.py\n')
        f.write('// 真实战队队标 RGB565(已按亮度合成底板,无需 alpha 通道)\n')
        f.write('// 两档尺寸:%s\n' % ' / '.join('%dpx' % s for s in SIZES))
        f.write('#include "cs_assets.h"\n\n')

        per_size = {}
        for size in SIZES:
            entries = []
            for tid in ids:
                img, plate, lum = flatten(os.path.join(logo_dir, tid + '.png'), size)
                raw = bytearray()
                for y in range(size):
                    for x in range(size):
                        v = rgb565(*img.getpixel((x, y)))
                        raw.append(v & 0xFF); raw.append((v >> 8) & 0xFF)
                arr = 'logo%d_%s_map' % (size, tid)
                emit_bytes(f, arr, raw)
                entries.append((tid, arr))
                print('[logo] %2dpx %-10s plate=%-18s lum=%5.1f' % (size, tid, plate, lum))
            per_size[size] = entries

        for size in SIZES:
            for tid, arr in per_size[size]:
                f.write('const lv_image_dsc_t cs_logo%d_%s = {\n' % (size, tid))
                f.write('    .header.magic = LV_IMAGE_HEADER_MAGIC,\n')
                f.write('    .header.cf = LV_COLOR_FORMAT_RGB565,\n')
                f.write('    .header.w = %d,\n    .header.h = %d,\n' % (size, size))
                f.write('    .header.stride = %d,\n' % (size * 2))
                f.write('    .data_size = %d,\n' % (size * size * 2))
                f.write('    .data = %s,\n};\n\n' % arr)

        for size in SIZES:
            f.write('typedef struct { const char *id; const lv_image_dsc_t *dsc; } cs_logo%d_ent_t;\n' % size)
            f.write('static const cs_logo%d_ent_t CS_LOGOS%d[] = {\n' % (size, size))
            for tid, _ in per_size[size]:
                f.write('    { "%s", &cs_logo%d_%s },\n' % (tid, size, tid))
            f.write('};\n\n')

        f.write('static bool cs_id_eq(const char *a, const char *b)\n{\n'
                '    if (!a || !b) return false;\n'
                '    while (*a && *b) {\n'
                '        char ca = *a, cb = *b;\n'
                "        if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');\n"
                "        if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');\n"
                '        if (ca != cb) return false;\n'
                '        a++; b++;\n'
                '    }\n'
                '    return *a == 0 && *b == 0;\n}\n\n')

        for size, fn in ((48, 'cs_logo_get'), (20, 'cs_logo_get_small')):
            f.write('const lv_image_dsc_t *%s(const char *id)\n{\n' % fn)
            f.write('    if (!id || !id[0]) return NULL;\n')
            f.write('    for (unsigned i = 0; i < sizeof(CS_LOGOS%d) / sizeof(CS_LOGOS%d[0]); i++)\n'
                    % (size, size))
            f.write('        if (cs_id_eq(CS_LOGOS%d[i].id, id)) return CS_LOGOS%d[i].dsc;\n'
                    % (size, size))
            f.write('    return NULL;\n}\n\n')

    print('[logo] ok %s (%d 个队标 x %d 档)' % (out_c, len(ids), len(SIZES)))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ttf', help='中文字体 TTF/OTF(Noto Sans SC 等)')
    ap.add_argument('--logo-dir', help='战队 PNG 目录,文件名即 logo id(g2.png / navi.png)')
    ap.add_argument('--out-dir', default='main')
    ap.add_argument('--font-name', default='font_cn16')
    ap.add_argument('--font-size', type=int, default=16)
    ap.add_argument('--bpp', type=int, default=4)
    ap.add_argument('--node', default=os.environ.get(
        'NODE_BIN', 'node'))
    ap.add_argument('--lv-font-conv', default=os.environ.get(
        'LV_FONT_CONV', 'lv_font_conv'))
    a = ap.parse_args()

    if not a.ttf and not a.logo_dir:
        ap.error('至少要给 --ttf 或 --logo-dir')

    if a.ttf:
        gen_font(a.ttf, os.path.join(a.out_dir, 'cs_font_cn16.c'),
                 a.font_name, a.font_size, a.bpp, a.node, a.lv_font_conv)
    if a.logo_dir:
        gen_logos(a.logo_dir, os.path.join(a.out_dir, 'cs_assets.c'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
