// 自动生成,请勿手改 —— tools/pack_csres.py
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
#define CS_RES_VERSION  1u

#define CS_LOGO_N       105
#define CS_LOGO48_EDGE  48
#define CS_LOGO20_EDGE  20
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
    { "3dmax", 0 },
    { "9pandas", 1 },
    { "9-pandas", 1 },
    { "9z", 2 },
    { "amkal", 3 },
    { "apeks", 4 },
    { "apeks-rebels", 5 },
    { "astralis", 6 },
    { "astralis-talent", 7 },
    { "atk", 8 },
    { "attax", 9 },
    { "alternate-attax", 9 },
    { "aurora", 10 },
    { "b8", 11 },
    { "betboom", 12 },
    { "big", 13 },
    { "big-clan", 13 },
    { "bleed", 14 },
    { "bne", 15 },
    { "bad-news-eagles", 15 },
    { "cloud9", 16 },
    { "complexity", 17 },
    { "cphflames", 18 },
    { "copenhagen-flames", 18 },
    { "dignitas", 19 },
    { "ecstatic", 20 },
    { "eg", 21 },
    { "evil-geniuses", 21 },
    { "ence", 22 },
    { "endpoint", 23 },
    { "entropiq", 24 },
    { "eternalfire", 25 },
    { "eternal-fire", 25 },
    { "ex-anonymo", 26 },
    { "anonymo", 26 },
    { "exfinest", 27 },
    { "finest", 27 },
    { "extremum", 28 },
    { "falcons", 29 },
    { "faze", 30 },
    { "faze-clan", 30 },
    { "fluxo", 31 },
    { "fnatic", 32 },
    { "fnatic-rising", 33 },
    { "forze", 34 },
    { "furia", 35 },
    { "g2", 36 },
    { "g2-esports", 36 },
    { "gaimin", 37 },
    { "gaimin-gladiators", 37 },
    { "gamerlegion", 38 },
    { "team-gamerlegion", 38 },
    { "godsent", 39 },
    { "grayhound", 40 },
    { "gtz", 41 },
    { "havu", 42 },
    { "hellraiser", 43 },
    { "hellraisers", 43 },
    { "heroic", 44 },
    { "illuminar", 45 },
    { "imperial", 46 },
    { "insilio", 47 },
    { "isurus", 48 },
    { "itb", 49 },
    { "into-the-breach", 49 },
    { "jano", 50 },
    { "k23", 51 },
    { "koi", 52 },
    { "legacy", 53 },
    { "legion", 54 },
    { "hard-legion", 54 },
    { "liquid", 55 },
    { "team-liquid", 55 },
    { "lynnvision", 56 },
    { "lynn-vision", 56 },
    { "m80", 57 },
    { "madlions", 58 },
    { "mad-lions", 58 },
    { "majestic", 59 },
    { "majestic-lions", 59 },
    { "metizport", 60 },
    { "mibr", 61 },
    { "mongolz", 62 },
    { "the-mongolz", 62 },
    { "monte", 63 },
    { "mouz", 64 },
    { "mouz-esports", 64 },
    { "mouz-nxt", 65 },
    { "movistar", 66 },
    { "movistar-riders", 66 },
    { "navi", 67 },
    { "natus-vincere", 67 },
    { "na-vi", 67 },
    { "navijunior", 68 },
    { "navi-junior", 68 },
    { "nemiga", 69 },
    { "nip", 70 },
    { "ninjas-in-pyjamas", 70 },
    { "nordavind", 71 },
    { "nouns", 72 },
    { "nrg", 73 },
    { "oddiK", 74 },
    { "oddik", 74 },
    { "og", 75 },
    { "order", 76 },
    { "pain", 77 },
    { "pain-gaming", 77 },
    { "parivision", 78 },
    { "partizan", 79 },
    { "passionua", 80 },
    { "passion-ua", 80 },
    { "rareatom", 81 },
    { "rare-atom", 81 },
    { "rebels", 82 },
    { "redcanids", 83 },
    { "red-canids", 83 },
    { "renegades", 84 },
    { "rooster", 85 },
    { "sangal", 86 },
    { "sashi", 87 },
    { "sharks", 88 },
    { "sinnerS", 89 },
    { "sinners", 89 },
    { "skade", 90 },
    { "spirit", 91 },
    { "team-spirit", 91 },
    { "spiritacad", 92 },
    { "spirit-academy", 92 },
    { "sprout", 93 },
    { "tyloo", 94 },
    { "unicorns", 95 },
    { "unicorns-of-love", 95 },
    { "vertex", 96 },
    { "virtuspro", 97 },
    { "virtus-pro", 97 },
    { "vp", 97 },
    { "virtuspro-acad", 98 },
    { "vp.prodigy", 98 },
    { "vitality", 99 },
    { "wildcard", 100 },
    { "wingsup", 101 },
    { "wings-up", 101 },
    { "winstrike", 102 },
    { "young-ninjas", 103 },
    { "youngsters", 104 },
    { "saw-youngsters", 104 },
};

// 运行时拼出来的图像描述符(BSS 约 9.0KB;像素本身留在 Flash,不进 RAM)
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
