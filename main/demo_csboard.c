// main/demo_csboard.c —— CS2 赛事看板(可视化中文版 / ESP32-C3 + LVGL 9)。
//
// 页面结构(设备右侧 UP/DOWN/OK 三键操作,OK 长按由 main.c 统一拦截返菜单):
//
//   主菜单 ──┬─ 实时比分   大比分 + 真实队标 + 逐图比分
//            ├─ 近期战绩   历史战绩列表(已结束)
//            ├─ 赛事预告   未来赛程列表(未开始)
//            └─ 网络设置   扫描 Wi-Fi / 选网 / 三键输密码
//
// 按键分工:
//   主菜单 : UP/DOWN 选条目 | OK 单击 进入 | OK 双击 刷新数据
//   列表页 : UP/DOWN 翻条目 | OK 单击 刷新   | OK 双击 返回主菜单
//   网络页 : UP/DOWN 选 AP   | OK 单击 连接   | OK 双击 返回主菜单
//   密码页 : UP/DOWN 选字符 | OK 单击 输入/执行 | OK 双击 返回网络页
//
// 注:OK 单击带 ~320ms 延时(等双击判定),避免"双击时先触发一次单击"。
//
// 资源:界面文字全部中文,用 cs_font_cn16(脚本生成的 GB2312 常用字集);
//      队标用真实官方图标(cs_assets.c),列表里贴 20px 缩略图,比分卡贴 48px。
#include "demo.h"
#include "cs_net.h"
#include "cs_assets.h"
#include "bsp_battery.h"
#include "lvgl.h"

#include <stdio.h>
#include <string.h>

// ---------------------------------------------------------------------------
// 主题色(深色电竞风)
// ---------------------------------------------------------------------------
#define C_BG     0x080B10
#define C_CARD   0x161B25
#define C_CARD2  0x10141C
#define C_LINE   0x28303F
#define C_TEXT   0xFFFFFF
#define C_DIM    0x9AA6B5
#define C_DIM2   0x5C6675
#define C_RED    0xE8382C
#define C_YEL    0xFFC93C
#define C_GRN    0x35D07F
#define C_BLUE   0x2E9BF0
#define C_SEL    0x1D2838

#define SCREEN_W 240
#define SCREEN_H 320
#define SBAR_H   22
#define HINT_H   24
#define BODY_Y   SBAR_H
#define BODY_H   (SCREEN_H - SBAR_H - HINT_H)

typedef enum {
    VIEW_MENU = 0,
    VIEW_LIVE,
    VIEW_HISTORY,
    VIEW_UPCOMING,
    VIEW_WIFI,
    VIEW_PASS,
} view_t;

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
static lv_obj_t *s_scr;
static lv_obj_t *s_body;      // 视图容器(随视图重建)
static lv_obj_t *s_hint;      // 底部提示条

static lv_obj_t *s_lbl_time;
static lv_obj_t *s_lbl_wifi;
static lv_obj_t *s_lbl_bat;
static lv_obj_t *s_bat_fill;
static lv_obj_t *s_net_dot;

static lv_timer_t *s_timer;
static lv_timer_t *s_click_timer;   // OK 单击延时器

static view_t s_view = VIEW_MENU;
static int    s_menu_sel;
static int    s_live_sel;
static int    s_list_sel;           // 战绩/预告共用
static int    s_ap_sel;
static bool   s_auto_fetched;       // 联网后自动拉一次

// 筛选后的下标表
static int s_live_idx[CS_MAX_MATCHES]; static int s_live_n;
static int s_hist_idx[CS_MAX_MATCHES]; static int s_hist_n;
static int s_upc_idx[CS_MAX_MATCHES];  static int s_upc_n;

static cs_net_state_t   s_last_net   = (cs_net_state_t)-1;
static cs_fetch_state_t s_last_fetch = (cs_fetch_state_t)-1;
static int              s_last_ap    = -1;
static int              s_bat_tick;

// 密码输入
static char s_pass[34];
static char s_target_ssid[33];
static int  s_set;                  // 当前字符集
static int  s_sel;                  // 字符选择器位置

static const char *SETS[] = {
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "0123456789",
    ".-_@#!$%&*+=?",
};
#define SET_COUNT ((int)(sizeof(SETS) / sizeof(SETS[0])))

// 主菜单条目
static const struct { const char *label; uint32_t acc; } MENU[] = {
    { "实时比分", C_RED  },
    { "近期战绩", C_BLUE },
    { "赛事预告", C_GRN  },
    { "网络设置", C_YEL  },
};
#define MENU_COUNT ((int)(sizeof(MENU) / sizeof(MENU[0])))

// ---------------------------------------------------------------------------
// 基础绘制 helper
// ---------------------------------------------------------------------------
static lv_obj_t *box(lv_obj_t *parent, int x, int y, int w, int h, uint32_t color, int radius)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_size(o, w, h);
    lv_obj_set_style_radius(o, radius, 0);
    lv_obj_set_style_border_width(o, 0, 0);
    lv_obj_set_style_pad_all(o, 0, 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(o, lv_color_hex(color), 0);
    return o;
}

static lv_obj_t *label(lv_obj_t *parent, const char *txt, const lv_font_t *font, uint32_t color)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, txt);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
    return l;
}

static lv_obj_t *label_at(lv_obj_t *parent, int x, int y, const char *txt,
                          const lv_font_t *font, uint32_t color)
{
    lv_obj_t *l = label(parent, txt, font, color);
    lv_obj_set_pos(l, x, y);
    return l;
}

// 定宽 + 对齐的标签
static lv_obj_t *label_w(lv_obj_t *parent, int x, int y, int w, const char *txt,
                         const lv_font_t *font, uint32_t color, lv_text_align_t al)
{
    lv_obj_t *l = label_at(parent, x, y, txt, font, color);
    lv_obj_set_width(l, w);
    lv_obj_set_style_text_align(l, al, 0);
    return l;
}

// 定宽 + 定高 + 超长自动省略号。
// 中英文混排按“字符数”手工截断会截出“BLAST 世..”这种难看的结果,
// 交给 LVGL 按真实字宽(LV_LABEL_LONG_DOT)处理更准。
static lv_obj_t *label_fit(lv_obj_t *parent, int x, int y, int w, int h,
                           const char *txt, const lv_font_t *font, uint32_t color,
                           lv_text_align_t al)
{
    lv_obj_t *l = label_w(parent, x, y, w, txt, font, color, al);
    lv_obj_set_height(l, h);
    lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
    return l;
}

// 按"字符数"截断 UTF-8,超出补 ".."(中文也不会被切断成乱码)
static void trunc_u8(char *dst, size_t cap, const char *src, int max_chars)
{
    if (!dst || cap == 0) return;
    if (!src) { dst[0] = 0; return; }
    size_t di = 0;
    int chars = 0;
    for (size_t si = 0; src[si] && di + 1 < cap; ) {
        unsigned char c = (unsigned char)src[si];
        int len = (c < 0x80) ? 1 : ((c >> 5) == 0x6 ? 2 : ((c >> 4) == 0xE ? 3 : 4));
        if (chars >= max_chars) {
            if (di + 2 < cap) { dst[di++] = '.'; dst[di++] = '.'; }
            break;
        }
        for (int k = 0; k < len && src[si + k] && di + 1 < cap; k++) dst[di++] = src[si + k];
        si += (size_t)len;
        chars++;
    }
    dst[di] = 0;
}

// 不依赖 snprintf(%s 长度未知,GCC 可能报 format-truncation)
static void scpy(char *dst, size_t cap, const char *src)
{
    if (!dst || cap == 0) return;
    if (!src) { dst[0] = 0; return; }
    size_t n = strlen(src);
    if (n > cap - 1) n = cap - 1;
    memcpy(dst, src, n);
    dst[n] = 0;
}

// 地图名 -> 主题色(贴近游戏里的地图观感)
static uint32_t map_color(const char *name)
{
    static const struct { const char *n; uint32_t c; } T[] = {
        { "Anubis",  0xD8A44C }, { "Inferno", 0xC0392B }, { "Mirage",  0xE8B84B },
        { "Dust",    0xD9A441 }, { "Nuke",    0x9AA0A6 }, { "Ancient", 0x2E8B57 },
        { "Vertigo", 0x7F8C8D }, { "Overpass",0x3AA76D }, { "Train",   0x8E6C3A },
        { "Cache",   0x4A6FA5 },
    };
    for (size_t i = 0; i < sizeof(T) / sizeof(T[0]); i++)
        if (strstr(name, T[i].n)) return T[i].c;
    return 0x5C6675;
}

static const char *status_cn(const char *st)
{
    if (strcmp(st, CS_ST_LIVE) == 0)     return "进行中";
    if (strcmp(st, CS_ST_FINISHED) == 0) return "已结束";
    return "未开始";
}

static uint32_t status_color(const char *st)
{
    if (strcmp(st, CS_ST_LIVE) == 0)     return C_RED;
    if (strcmp(st, CS_ST_FINISHED) == 0) return C_DIM2;
    return C_BLUE;
}

// 队标:找到真实图标就贴图,找不到画一个队色方块兜底(绝不显示文字缩写)
static void put_logo(lv_obj_t *parent, int x, int y, bool big,
                     const char *id, uint32_t color)
{
    const lv_image_dsc_t *dsc = big ? cs_logo_get(id) : cs_logo_get_small(id);
    if (dsc) {
        lv_obj_t *img = lv_image_create(parent);
        lv_image_set_src(img, dsc);
        lv_obj_set_pos(img, x, y);
        lv_obj_set_size(img, big ? 48 : 20, big ? 48 : 20);
        return;
    }
    box(parent, x, y, big ? 48 : 20, big ? 48 : 20, color, big ? 12 : 5);
}

// ---------------------------------------------------------------------------
// 状态栏(时间 / Wi-Fi / 电池)
// ---------------------------------------------------------------------------
static void update_sbar(void)
{
    char hhmm[16];
    cs_time_hhmm(hhmm, sizeof(hhmm));
    lv_label_set_text(s_lbl_time, hhmm);

    cs_net_state_t st = cs_net_state();
    const char *wtxt;
    uint32_t wcol;
    switch (st) {
    case CS_NET_ONLINE:     wtxt = cs_net_ssid(); if (!wtxt[0]) wtxt = "已联网"; wcol = C_GRN;  break;
    case CS_NET_CONNECTING: wtxt = "连接中"; wcol = C_YEL;  break;
    case CS_NET_SCANNING:   wtxt = "扫描中"; wcol = C_YEL;  break;
    case CS_NET_APLIST:     wtxt = "已扫描"; wcol = C_BLUE; break;
    case CS_NET_FAILED:     wtxt = "未联网"; wcol = C_RED;  break;
    default:                wtxt = "未联网"; wcol = C_DIM2; break;
    }
    char wbuf[32];
    scpy(wbuf, sizeof(wbuf), wtxt);
    lv_label_set_text(s_lbl_wifi, wbuf);
    lv_obj_set_style_text_color(s_lbl_wifi, lv_color_hex(wcol), 0);
    lv_obj_set_style_bg_color(s_net_dot, lv_color_hex(wcol), 0);

    // 电池每 2 秒读一次,避免频繁 I2C
    if (s_bat_tick-- <= 0) {
        s_bat_tick = 10;
        int soc = bsp_battery_soc();
        if (soc < 0) {
            lv_label_set_text(s_lbl_bat, "--%");
            lv_obj_set_style_bg_color(s_bat_fill, lv_color_hex(C_DIM2), 0);
            lv_obj_set_width(s_bat_fill, 8);
        } else {
            char bb[16];
            if (soc > 100) soc = 100;
            snprintf(bb, sizeof(bb), "%d%%", soc % 1000);
            lv_label_set_text(s_lbl_bat, bb);
            uint32_t c = soc > 60 ? C_GRN : (soc > 25 ? C_YEL : C_RED);
            lv_obj_set_style_bg_color(s_bat_fill, lv_color_hex(c), 0);
            int bw = 18 * soc / 100;
            lv_obj_set_width(s_bat_fill, bw < 2 ? 2 : bw);
        }
    }
}

static void build_sbar(void)
{
    lv_obj_t *sbar = box(s_scr, 0, 0, SCREEN_W, SBAR_H, C_CARD2, 0);

    s_net_dot  = box(sbar, 6, 8, 6, 6, C_DIM2, 3);
    s_lbl_wifi = label_fit(sbar, 15, 0, 78, SBAR_H, "未联网", &font_cn16, C_DIM2,
                           LV_TEXT_ALIGN_LEFT);

    lv_obj_t *tl = label_w(sbar, 0, 0, 46, "--:--", &font_cn16, C_TEXT, LV_TEXT_ALIGN_CENTER);
    lv_obj_set_height(tl, SBAR_H);
    lv_obj_align(tl, LV_ALIGN_TOP_MID, 0, 0);
    s_lbl_time = tl;

    s_lbl_bat = label_w(sbar, 140, 0, 44, "--%", &font_cn16, C_DIM, LV_TEXT_ALIGN_RIGHT);
    lv_obj_set_height(s_lbl_bat, SBAR_H);

    // 电池图标:外框 + 内填充 + 右凸点
    lv_obj_t *b = box(sbar, 190, 6, 22, 11, C_CARD2, 3);
    lv_obj_set_style_border_width(b, 1, 0);
    lv_obj_set_style_border_color(b, lv_color_hex(C_DIM2), 0);
    s_bat_fill = box(b, 2, 2, 8, 7, C_GRN, 2);
    box(sbar, 212, 9, 2, 5, C_DIM2, 1);
}

// ---------------------------------------------------------------------------
// 底部提示条
// ---------------------------------------------------------------------------
static void update_hint(void)
{
    const char *h;
    switch (s_view) {
    case VIEW_MENU:     h = "上下选择 确定进入 双击刷新"; break;
    case VIEW_LIVE:     h = "上下翻页 确定刷新 双击返回"; break;
    case VIEW_HISTORY:
    case VIEW_UPCOMING: h = "上下翻动 确定刷新 双击返回"; break;
    case VIEW_WIFI:     h = "上下选择 确定连接 双击返回"; break;
    default:            h = "上下选字 确定输入 双击返回"; break;
    }
    lv_obj_t *hl = lv_obj_get_child(s_hint, 0);
    if (!hl) hl = label(s_hint, h, &font_cn16, C_DIM);
    else     lv_label_set_text(hl, h);
}

// ---------------------------------------------------------------------------
// 数据筛选
// ---------------------------------------------------------------------------
static void rebuild_filters(void)
{
    s_live_n = cs_data_filter(CS_ST_LIVE, s_live_idx, CS_MAX_MATCHES);
    if (s_live_n == 0) {
        // 当前没有进行中的比赛时,退化成"最近一场已结束"当最新比分看
        s_live_n = cs_data_filter(CS_ST_FINISHED, s_live_idx, CS_MAX_MATCHES);
    }
    s_hist_n = cs_data_filter(CS_ST_FINISHED, s_hist_idx, CS_MAX_MATCHES);
    s_upc_n  = cs_data_filter(CS_ST_UPCOMING, s_upc_idx, CS_MAX_MATCHES);
}

static void clamp_sels(void)
{
    if (s_live_n > 0 && s_live_sel >= s_live_n) s_live_sel = 0;
    if (s_hist_n > 0 && s_list_sel >= s_hist_n) s_list_sel = 0;
    if (s_upc_n  > 0 && s_list_sel >= s_upc_n)  s_list_sel = 0;
    if (s_menu_sel >= MENU_COUNT) s_menu_sel = 0;
}

// ---------------------------------------------------------------------------
// 视图 1:主菜单
// ---------------------------------------------------------------------------
static void build_menu(void)
{
    const cs_data_t *d = cs_data();

    // 标题
    label_at(s_body, 12, 8, "CS2", &lv_font_montserrat_20, C_RED);
    label_at(s_body, 58, 6, "赛事看板", &font_cn16, C_TEXT);

    char sub[48];
    snprintf(sub, sizeof(sub), "共 %d 场 | %s", d->count % 1000,
             d->updated[0] ? d->updated : "本地数据");
    char sub2[40];
    trunc_u8(sub2, sizeof(sub2), sub, 12);
    label_at(s_body, 12, 30, sub2, &font_cn16, C_DIM2);

    // 条目标签 + 数量
    int cnt[MENU_COUNT] = { s_live_n, s_hist_n, s_upc_n, 0 };

    for (int i = 0; i < MENU_COUNT; i++) {
        int y = 58 + i * 50;
        bool sel = (i == s_menu_sel);
        lv_obj_t *row = box(s_body, 8, y, 224, 44, sel ? C_SEL : C_CARD, 8);
        if (sel) {
            lv_obj_set_style_border_width(row, 1, 0);
            lv_obj_set_style_border_color(row, lv_color_hex(C_BLUE), 0);
        }
        box(row, 8, 8, 5, 28, MENU[i].acc, 3);
        label_at(row, 24, 11, MENU[i].label, &font_cn16, sel ? C_TEXT : C_DIM);

        if (i < 3) {
            char cb[16];
            snprintf(cb, sizeof(cb), "%d 场", cnt[i] % 1000);
            lv_obj_t *cl = label(row, cb, &font_cn16, C_DIM2);
            lv_obj_align(cl, LV_ALIGN_RIGHT_MID, -10, 0);
        } else {
            cs_net_state_t st = cs_net_state();
            const char *nt = (st == CS_NET_ONLINE) ? "已联网" :
                             (st == CS_NET_CONNECTING) ? "连接中" : "未联网";
            lv_obj_t *cl = label(row, nt, &font_cn16, C_DIM2);
            lv_obj_align(cl, LV_ALIGN_RIGHT_MID, -10, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// 视图 2:实时比分
// ---------------------------------------------------------------------------
static void build_live(void)
{
    if (s_live_n <= 0) {
        label_at(s_body, 84, 120, "暂无比赛数据", &font_cn16, C_DIM);
        return;
    }
    if (s_live_sel >= s_live_n) s_live_sel = 0;
    const cs_match_t *m = &cs_data()->m[s_live_idx[s_live_sel]];

    // ---- 赛事头部 ----
    lv_obj_t *head = box(s_body, 8, 4, 224, 28, C_CARD, 6);
    box(head, 8, 9, 10, 10, status_color(m->status), 3);
    char ev[40];
    trunc_u8(ev, sizeof(ev), m->event, 9);
    label_at(head, 24, 4, ev, &font_cn16, C_TEXT);
    if (m->date[0]) {
        lv_obj_t *dl = label(head, m->date, &lv_font_montserrat_14, C_DIM);
        lv_obj_align(dl, LV_ALIGN_RIGHT_MID, -10, 0);
    }

    // ---- 比分卡 ----
    lv_obj_t *card = box(s_body, 8, 38, 224, 100, C_CARD, 8);

    put_logo(card, 12, 8, true, m->t1_logo, m->t1_color);
    put_logo(card, 164, 8, true, m->t2_logo, m->t2_color);

    // 队名交给 LVGL 按真实字宽省略(LV_LABEL_LONG_DOT),
    // 105 支战队里 GamerLegion / Virtus.pro 这类长名才不会被硬切。
    char tn[CS_TEAM_LEN * 2];
    trunc_u8(tn, sizeof(tn), m->t1_name, 12);
    label_fit(card, 4, 60, 72, 20, tn, &font_cn16, C_DIM, LV_TEXT_ALIGN_CENTER);
    trunc_u8(tn, sizeof(tn), m->t2_name, 12);
    label_fit(card, 148, 60, 72, 20, tn, &font_cn16, C_DIM, LV_TEXT_ALIGN_CENTER);

    // 中间大比分 / VS
    char sc[32];
    bool upcoming = (strcmp(m->status, CS_ST_UPCOMING) == 0);
    if (upcoming) snprintf(sc, sizeof(sc), "VS");
    else          snprintf(sc, sizeof(sc), "%d : %d", m->score1 % 100, m->score2 % 100);
    lv_obj_t *sl = label(card, sc, &lv_font_montserrat_28, C_TEXT);
    lv_obj_align(sl, LV_ALIGN_TOP_MID, 0, 16);

    // 状态与赛制合成一行:卡片中间可用区只有队标之间那 ~100px,
    // 分两行会和队名(两侧 y=60 起)挤在一起。
    char stbuf[24];
    if (m->bo[0]) snprintf(stbuf, sizeof(stbuf), "%s %s", status_cn(m->status), m->bo);
    else          scpy(stbuf, sizeof(stbuf), status_cn(m->status));
    lv_obj_t *stl = label(card, stbuf, &font_cn16, status_color(m->status));
    lv_obj_align(stl, LV_ALIGN_TOP_MID, 0, 50);

    // 页码放卡片底部居中:队标(x<60 / x>164)与两侧队名都不占这块
    char pc[32];
    snprintf(pc, sizeof(pc), "%d/%d", (s_live_sel + 1) % 1000, s_live_n % 1000);
    lv_obj_t *pl = label(card, pc, &lv_font_montserrat_14, C_DIM2);
    lv_obj_align(pl, LV_ALIGN_BOTTOM_MID, 0, -3);

    // ---- 逐图比分 ----
    lv_obj_t *maps = box(s_body, 8, 144, 224, 118, C_CARD, 8);
    label_at(maps, 10, 6, "地图比分", &font_cn16, C_DIM2);
    if (m->stage[0]) {
        char sg[24];
        trunc_u8(sg, sizeof(sg), m->stage, 6);
        lv_obj_t *sgl = label(maps, sg, &font_cn16, C_DIM2);
        lv_obj_align(sgl, LV_ALIGN_TOP_RIGHT, -10, 6);
    }

    if (m->map_count == 0) {
        label_at(maps, 76, 60, "地图待定", &font_cn16, C_DIM2);
        return;
    }
    for (int i = 0; i < m->map_count && i < 4; i++) {
        const cs_map_t *mp = &m->maps[i];
        int y = 30 + i * 21;
        box(maps, 10, y + 3, 4, 15, map_color(mp->name), 2);

        char mn[20];
        if (mp->cn[0]) trunc_u8(mn, sizeof(mn), mp->cn, 6);
        else           trunc_u8(mn, sizeof(mn), mp->name, 8);
        label_at(maps, 22, y + 1, mn, &font_cn16, C_TEXT);

        char ms[24];
        if (mp->s1 == 0 && mp->s2 == 0) snprintf(ms, sizeof(ms), "-");
        else snprintf(ms, sizeof(ms), "%d : %d", mp->s1 % 100, mp->s2 % 100);
        uint32_t mc = (mp->s1 == mp->s2) ? C_DIM : (mp->s1 > mp->s2 ? C_GRN : C_RED);
        lv_obj_t *ml = label(maps, ms, &font_cn16, mc);
        lv_obj_align(ml, LV_ALIGN_TOP_RIGHT, -12, y + 1);
    }
}

// ---------------------------------------------------------------------------
// 视图 3/4:战绩 / 预告 列表
// ---------------------------------------------------------------------------
static void build_list(bool upcoming)
{
    const int *idx = upcoming ? s_upc_idx : s_hist_idx;
    int n = upcoming ? s_upc_n : s_hist_n;

    // 头部
    lv_obj_t *head = box(s_body, 8, 4, 224, 24, C_CARD, 6);
    label_at(head, 10, 2, upcoming ? "赛事预告" : "近期战绩", &font_cn16, C_TEXT);
    char hb[24];
    snprintf(hb, sizeof(hb), "%d 场", n % 1000);
    lv_obj_t *hl = label(head, hb, &font_cn16, C_DIM2);
    lv_obj_align(hl, LV_ALIGN_RIGHT_MID, -10, 0);

    if (n <= 0) {
        label_at(s_body, 84, 130, upcoming ? "暂无赛事预告" : "暂无历史战绩", &font_cn16, C_DIM);
        return;
    }
    if (s_list_sel >= n) s_list_sel = 0;

    // 简单滚动窗口:选中项始终可见
    int visible = 5;
    int top = s_list_sel >= visible ? s_list_sel - visible + 1 : 0;

    for (int i = 0; i < visible; i++) {
        int k = top + i;
        if (k >= n) break;
        int y = 32 + i * 48;
        bool sel = (k == s_list_sel);
        const cs_match_t *m = &cs_data()->m[idx[k]];

        lv_obj_t *row = box(s_body, 8, y, 224, 44, sel ? C_SEL : C_CARD, 6);
        if (sel) {
            lv_obj_set_style_border_width(row, 1, 0);
            lv_obj_set_style_border_color(row, lv_color_hex(C_BLUE), 0);
        }

        // 第一行:日期/时间 + 赛事名
        char dl[24];
        if (upcoming && m->time[0]) snprintf(dl, sizeof(dl), "%s %s", m->date, m->time);
        else                        snprintf(dl, sizeof(dl), "%s", m->date[0] ? m->date : "--");
        char dl2[24];
        trunc_u8(dl2, sizeof(dl2), dl, 11);
        label_at(row, 6, 2, dl2, &lv_font_montserrat_14, upcoming ? C_YEL : C_DIM2);

        char ev[40];
        trunc_u8(ev, sizeof(ev), m->event, 10);
        label_fit(row, 96, 1, 118, 18, ev, &font_cn16, C_DIM2, LV_TEXT_ALIGN_LEFT);

        // 第二行:队标 + 队名 + 比分 + 队名 + 队标
        put_logo(row, 6, 22, false, m->t1_logo, m->t1_color);
        put_logo(row, 198, 22, false, m->t2_logo, m->t2_color);

        char t1[CS_TEAM_LEN * 2], t2[CS_TEAM_LEN * 2];
        // 列表行很窄(62px):JSON 给了 short 就用 short,否则用全名交给省略号
        trunc_u8(t1, sizeof(t1), m->t1_short[0] ? m->t1_short : m->t1_name, 12);
        trunc_u8(t2, sizeof(t2), m->t2_short[0] ? m->t2_short : m->t2_name, 12);
        label_fit(row, 28, 22, 62, 20, t1, &font_cn16, C_TEXT, LV_TEXT_ALIGN_LEFT);
        label_fit(row, 134, 22, 62, 20, t2, &font_cn16, C_TEXT, LV_TEXT_ALIGN_RIGHT);

        char sc[32];
        if (upcoming) snprintf(sc, sizeof(sc), "VS");
        else          snprintf(sc, sizeof(sc), "%d:%d", m->score1 % 100, m->score2 % 100);
        uint32_t sccol = C_TEXT;
        if (!upcoming) {
            if (m->score1 > m->score2)      sccol = C_GRN;
            else if (m->score2 > m->score1) sccol = C_RED;
            else                            sccol = C_DIM;
        }
        label_w(row, 90, 20, 44, sc, &lv_font_montserrat_20, sccol, LV_TEXT_ALIGN_CENTER);
    }
}

// ---------------------------------------------------------------------------
// 视图 5:Wi-Fi 列表
// ---------------------------------------------------------------------------
static void build_wifi(void)
{
    cs_net_state_t st = cs_net_state();

    lv_obj_t *head = box(s_body, 8, 4, 224, 26, C_CARD, 6);
    const char *t = "选择无线网络";
    uint32_t tc = C_TEXT;
    if (st == CS_NET_SCANNING)        { t = "正在扫描...";   tc = C_YEL; }
    else if (st == CS_NET_CONNECTING) { t = "正在连接...";   tc = C_YEL; }
    else if (st == CS_NET_ONLINE)     { t = "已连接";        tc = C_GRN; }
    else if (st == CS_NET_FAILED)     { t = "连接失败,确定重扫"; tc = C_RED; }
    label_at(head, 10, 3, t, &font_cn16, tc);

    lv_obj_t *list = box(s_body, 8, 36, 224, 232, C_CARD, 6);

    int n = cs_net_ap_count();
    if (n <= 0) {
        const char *msg = (st == CS_NET_SCANNING) ? "扫描附近网络..." : "未找到无线网络";
        label_at(list, 56, 100, msg, &font_cn16, C_DIM);
        return;
    }
    if (s_ap_sel >= n) s_ap_sel = 0;

    int top = (s_ap_sel >= 6) ? s_ap_sel - 5 : 0;   // 简易滚动窗口
    for (int i = 0; i < 6; i++) {
        int k = top + i;
        if (k >= n) break;
        int y = 6 + i * 36;
        bool sel = (k == s_ap_sel);

        lv_obj_t *row = box(list, 5, y, 214, 32, sel ? C_SEL : C_CARD, 5);
        if (sel) {
            lv_obj_set_style_border_width(row, 1, 0);
            lv_obj_set_style_border_color(row, lv_color_hex(C_BLUE), 0);
        }

        // 信号强度 3 格
        int rssi = cs_net_ap_rssi(k);
        int lvl = rssi > -55 ? 3 : (rssi > -70 ? 2 : 1);
        uint32_t bc = rssi > -55 ? C_GRN : (rssi > -70 ? C_YEL : C_RED);
        for (int j = 0; j < 3; j++) {
            int hh = 5 + j * 4;
            box(row, 8 + j * 6, 24 - hh, 4, hh, (j < lvl) ? bc : C_LINE, 1);
        }

        // 加密锁标记
        if (cs_net_ap_secure(k)) box(row, 32, 12, 9, 9, C_YEL, 2);

        char ss[40];
        trunc_u8(ss, sizeof(ss), cs_net_ap_ssid(k), 8);
        label_at(row, 48, 8, ss, &font_cn16, sel ? C_TEXT : C_DIM);

        if (strcmp(cs_net_ap_ssid(k), cs_net_ap_prev_ssid()) == 0) {
            lv_obj_t *sv = label(row, "已存", &font_cn16, C_GRN);
            lv_obj_align(sv, LV_ALIGN_RIGHT_MID, -8, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// 视图 6:密码输入(三键)
// ---------------------------------------------------------------------------
static void build_pass(void)
{
    lv_obj_t *head = box(s_body, 8, 4, 224, 26, C_CARD, 6);
    label_at(head, 10, 3, "输入无线密码", &font_cn16, C_YEL);

    // 目标网络 + 已输入
    lv_obj_t *card = box(s_body, 8, 36, 224, 78, C_CARD, 6);
    label_at(card, 10, 2, "目标网络", &font_cn16, C_DIM2);
    char ss[40];
    trunc_u8(ss, sizeof(ss), s_target_ssid, 12);
    label_at(card, 10, 24, ss, &font_cn16, C_TEXT);

    char pv[40];
    trunc_u8(pv, sizeof(pv), s_pass[0] ? s_pass : "尚未输入", 16);
    label_at(card, 10, 50, pv, &font_cn16, s_pass[0] ? C_TEXT : C_DIM2);

    // 字符选择器
    lv_obj_t *sel = box(s_body, 8, 122, 224, 100, C_CARD2, 6);
    lv_obj_set_style_border_width(sel, 1, 0);
    lv_obj_set_style_border_color(sel, lv_color_hex(C_LINE), 0);

    const char *set = SETS[s_set];
    int len = (int)strlen(set);
    char curbuf[12];
    uint32_t ccol;
    if (s_sel < len) {
        snprintf(curbuf, sizeof(curbuf), "%c", set[s_sel]);
        ccol = C_TEXT;
    } else if (s_sel == len) {
        snprintf(curbuf, sizeof(curbuf), "删");
        ccol = C_RED;
    } else if (s_sel == len + 1) {
        snprintf(curbuf, sizeof(curbuf), "换");
        ccol = C_BLUE;
    } else {
        snprintf(curbuf, sizeof(curbuf), "连");
        ccol = C_YEL;
    }
    lv_obj_t *cv = label(sel, curbuf, &lv_font_montserrat_28, ccol);
    lv_obj_align(cv, LV_ALIGN_TOP_MID, 0, 14);

    label_at(sel, 20, 28, "^", &lv_font_montserrat_20, C_DIM2);
    label_at(sel, 202, 28, "v", &lv_font_montserrat_20, C_DIM2);

    static const char *SETNAME[] = { "小写字母", "大写字母", "数字", "符号" };
    char info[48];
    snprintf(info, sizeof(info), "%s  %d/%d", SETNAME[s_set], s_set + 1, SET_COUNT);
    label_w(sel, 0, 70, 224, info, &font_cn16, C_DIM, LV_TEXT_ALIGN_CENTER);

    // 连接结果
    cs_net_state_t st = cs_net_state();
    if (st == CS_NET_CONNECTING) {
        label_at(s_body, 78, 234, "正在连接...", &font_cn16, C_YEL);
    } else if (st == CS_NET_FAILED) {
        label_at(s_body, 58, 234, "连接失败,请核对密码", &font_cn16, C_RED);
    }
}

// ---------------------------------------------------------------------------
// 视图切换与重建
// ---------------------------------------------------------------------------
static void rebuild(void)
{
    if (s_body) {
        lv_obj_delete(s_body);
        s_body = NULL;
    }
    s_body = box(s_scr, 0, BODY_Y, SCREEN_W, BODY_H, C_BG, 0);

    switch (s_view) {
    case VIEW_MENU:     build_menu();          break;
    case VIEW_LIVE:     build_live();          break;
    case VIEW_HISTORY:  build_list(false);     break;
    case VIEW_UPCOMING: build_list(true);      break;
    case VIEW_WIFI:     build_wifi();          break;
    default:            build_pass();          break;
    }
    update_hint();
}

static void set_view(view_t v)
{
    s_view = v;
    rebuild();
}

// ---------------------------------------------------------------------------
// OK 单击 / 双击动作
// ---------------------------------------------------------------------------
static void do_ok_single(void)
{
    switch (s_view) {
    case VIEW_MENU:
        switch (s_menu_sel) {
        case 0: s_live_sel = 0; set_view(VIEW_LIVE);     break;
        case 1: s_list_sel = 0; set_view(VIEW_HISTORY);  break;
        case 2: s_list_sel = 0; set_view(VIEW_UPCOMING); break;
        default:
            s_ap_sel = 0;
            set_view(VIEW_WIFI);
            cs_net_state_reset();
            cs_net_scan();
            break;
        }
        break;

    case VIEW_LIVE:
    case VIEW_HISTORY:
    case VIEW_UPCOMING:
        cs_data_fetch_reset();
        cs_data_refresh_async();
        update_hint();
        break;

    case VIEW_WIFI: {
        int n = cs_net_ap_count();
        if (n <= 0) {
            cs_net_state_reset();
            cs_net_scan();
            return;
        }
        if (s_ap_sel >= n) s_ap_sel = 0;
        const char *ssid = cs_net_ap_ssid(s_ap_sel);
        if (cs_net_ap_secure(s_ap_sel)) {
            // 有密码:先记住目标网络,再进密码页
            scpy(s_target_ssid, sizeof(s_target_ssid), ssid);
            s_pass[0] = 0;
            s_set = 0;
            s_sel = 0;
            set_view(VIEW_PASS);
        } else {
            cs_net_connect(ssid, "");
            rebuild();
        }
        break;
    }

    case VIEW_PASS: {
        const char *set = SETS[s_set];
        int len = (int)strlen(set);
        if (s_sel < len) {                       // 输入当前字符
            size_t pl = strlen(s_pass);
            if (pl < sizeof(s_pass) - 1) {
                s_pass[pl] = set[s_sel];
                s_pass[pl + 1] = 0;
            }
            rebuild();
        } else if (s_sel == len) {               // 删:退格
            size_t pl = strlen(s_pass);
            if (pl > 0) s_pass[pl - 1] = 0;
            rebuild();
        } else if (s_sel == len + 1) {           // 换:切换字符集
            s_set = (s_set + 1) % SET_COUNT;
            s_sel = 0;
            rebuild();
        } else {                                 // 连:提交连接
            cs_net_connect(s_target_ssid, s_pass);
            rebuild();
        }
        break;
    }
    }
}

static void do_ok_double(void)
{
    switch (s_view) {
    case VIEW_MENU:                          // 主菜单双击 = 刷新数据
        cs_data_fetch_reset();
        cs_data_refresh_async();
        update_hint();
        break;
    case VIEW_LIVE:
    case VIEW_HISTORY:
    case VIEW_UPCOMING:
        set_view(VIEW_MENU);
        break;
    case VIEW_WIFI:
        set_view(VIEW_MENU);
        break;
    default:                                 // 密码页 -> 回 AP 列表
        set_view(VIEW_WIFI);
        break;
    }
}

static void click_timer_cb(lv_timer_t *t)
{
    (void)t;
    s_click_timer = NULL;
    do_ok_single();
}

// ---------------------------------------------------------------------------
// 周期轮询(200ms)
// ---------------------------------------------------------------------------
static void tick(lv_timer_t *t)
{
    (void)t;
    update_sbar();

    cs_net_state_t ns = cs_net_state();
    if (ns != s_last_net) {
        s_last_net = ns;
        if (s_view == VIEW_WIFI || s_view == VIEW_PASS || s_view == VIEW_MENU) rebuild();
        if (ns == CS_NET_ONLINE && !s_auto_fetched) {
            s_auto_fetched = true;
            cs_data_fetch_reset();
            cs_data_refresh_async();
        }
    }

    int n = cs_net_ap_count();
    if (n != s_last_ap) {
        s_last_ap = n;
        if (s_view == VIEW_WIFI) rebuild();
    }

    cs_fetch_state_t fs = cs_data_fetch_state();
    if (fs != s_last_fetch) {
        s_last_fetch = fs;
        if (fs == CS_FETCH_OK) {
            rebuild_filters();
            clamp_sels();
            rebuild();
        } else {
            update_hint();
        }
    }
}

// ---------------------------------------------------------------------------
// 页面接口(enter / exit / key)
// ---------------------------------------------------------------------------
void demo_csboard_enter(void)
{
    s_scr = lv_obj_create(NULL);
    lv_obj_remove_flag(s_scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(s_scr, lv_color_hex(C_BG), 0);
    lv_obj_set_style_border_width(s_scr, 0, 0);
    lv_obj_set_style_pad_all(s_scr, 0, 0);

    s_view = VIEW_MENU;
    s_menu_sel = 0;
    s_live_sel = 0;
    s_list_sel = 0;
    s_ap_sel = 0;
    s_pass[0] = 0;
    s_target_ssid[0] = 0;
    s_set = 0;
    s_sel = 0;
    s_bat_tick = 0;
    s_auto_fetched = false;
    s_last_net = (cs_net_state_t)-1;
    s_last_fetch = (cs_fetch_state_t)-1;
    s_last_ap = -1;
    s_click_timer = NULL;

    build_sbar();

    s_hint = box(s_scr, 0, SCREEN_H - HINT_H, SCREEN_W, HINT_H, C_CARD2, 0);
    label(s_hint, "", &font_cn16, C_DIM);
    lv_obj_t *hl = lv_obj_get_child(s_hint, 0);
    if (hl) lv_obj_align(hl, LV_ALIGN_CENTER, 0, 0);

    // 先把缓存/内置数据显示出来,再谈联网
    cs_data_load_cache();
    rebuild_filters();
    cs_net_init();

    rebuild();
    s_timer = lv_timer_create(tick, 200, NULL);
    lv_screen_load(s_scr);
}

void demo_csboard_exit(void)
{
    if (s_click_timer) { lv_timer_delete(s_click_timer); s_click_timer = NULL; }
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }
    cs_net_shutdown();
    if (s_scr) {
        lv_obj_delete(s_scr);
        s_scr = NULL;
        s_hint = NULL;
        s_lbl_time = s_lbl_wifi = s_lbl_bat = s_bat_fill = s_net_dot = NULL;
    }
}

void demo_csboard_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // UP/DOWN 只有单击语义,立即执行(不引入延时,保证手感)
    if (ev == BSP_BTN_CLICK && (btn == BSP_BTN_UP || btn == BSP_BTN_DOWN)) {
        int dir = (btn == BSP_BTN_UP) ? -1 : 1;
        switch (s_view) {
        case VIEW_MENU:
            s_menu_sel = (s_menu_sel + MENU_COUNT + dir) % MENU_COUNT;
            rebuild();
            break;

        case VIEW_LIVE:
            if (s_live_n > 0) {
                s_live_sel = (s_live_sel + s_live_n + dir) % s_live_n;
                rebuild();
            }
            break;

        case VIEW_HISTORY:
        case VIEW_UPCOMING: {
            int n = (s_view == VIEW_HISTORY) ? s_hist_n : s_upc_n;
            if (n > 0) {
                s_list_sel = (s_list_sel + n + dir) % n;
                rebuild();
            }
            break;
        }

        case VIEW_WIFI: {
            int n = cs_net_ap_count();
            if (n > 0) {
                s_ap_sel = (s_ap_sel + n + dir) % n;
                rebuild();
            }
            break;
        }

        default: {
            int total = (int)strlen(SETS[s_set]) + 3;   // 字符 + 删/换/连
            s_sel = (s_sel + total + dir) % total;
            rebuild();
            break;
        }
        }
        return;
    }

    if (btn != BSP_BTN_OK) return;

    if (ev == BSP_BTN_CLICK) {
        // 延时 320ms 再执行,给双击判定留窗口
        if (s_click_timer) {
            lv_timer_reset(s_click_timer);
        } else {
            s_click_timer = lv_timer_create(click_timer_cb, 320, NULL);
        }
    } else if (ev == BSP_BTN_DOUBLE) {
        if (s_click_timer) { lv_timer_delete(s_click_timer); s_click_timer = NULL; }
        do_ok_double();
    }
}
