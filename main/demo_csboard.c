// main/demo_csboard.c —— CS2 赛事看板(可视化版 / ESP32-C3 + LVGL)。
//
// 三个视图(设备右侧 UP/DOWN/OK 三键切换):
//   MATCH : 深色比分卡 —— 赛事名 + 日期、两队徽章、大比分、BO3、逐图比分
//   WIFI  : AP 列表 —— 信号强度、加密锁标记,选中即连
//   PASS  : 三键密码输入 —— 字符集轮换 + 逐字符输入 + DEL/SET/OK
//
// 按键分工(OK 长按由 main.c 统一拦截返菜单,本页不使用):
//   MATCH : UP/DOWN 翻比赛 | OK 单击 刷新数据 | OK 双击 进 Wi-Fi 配网
//   WIFI  : UP/DOWN 选 AP  | OK 单击 连接/输密码 | OK 双击 返回看板
//   PASS  : UP/DOWN 滚字符 | OK 单击 输入/执行    | OK 双击 返回 AP 列表
//
// 注:OK 单击带 ~320ms 延时(等双击判定),避免"双击时先触发一次单击"的误操作。
//
// 字体限制:LVGL 内置 montserrat 仅含 Latin。中文 SSID / 队名会显示为空白,
// 需要中文界面得另嵌 CJK 字体子集(受 3MB 应用分区 + 无 PSRAM 限制)。
#include "demo.h"
#include "cs_net.h"
#include "bsp_battery.h"
#include "lvgl.h"

#include <stdio.h>
#include <string.h>

// ---------------------------------------------------------------------------
// 主题色(深色电竞风)
// ---------------------------------------------------------------------------
#define C_BG     0x0A0D12
#define C_CARD   0x171C26
#define C_CARD2  0x11151D
#define C_LINE   0x2A3242
#define C_TEXT   0xFFFFFF
#define C_DIM    0x8B97A6
#define C_DIM2   0x5A6473
#define C_RED    0xE43B2F
#define C_YEL    0xFFD928
#define C_GRN    0x3DD68C
#define C_BLUE   0x2AA3EF
#define C_SEL    0x1E2A3A

#define SCREEN_W 240
#define SCREEN_H 320
#define HINT_H   24

typedef enum { VIEW_MATCH = 0, VIEW_WIFI, VIEW_PASS } view_t;

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

static lv_timer_t *s_timer;
static lv_timer_t *s_click_timer;   // OK 单击延时器

static view_t s_view = VIEW_MATCH;
static int    s_idx;                // 比赛索引
static int    s_ap_sel;             // AP 选中索引
static bool   s_auto_fetched;       // 联网后自动拉一次

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

// 按"字符数"截断 UTF-8,超出补 ".."(中文 SSID 也不会被切断成乱码)
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
    return 0x5A6473;
}

// ---------------------------------------------------------------------------
// 状态栏(时间 / Wi-Fi / 电池)
// ---------------------------------------------------------------------------
static void build_sbar(void)
{
    lv_obj_t *sbar = box(s_scr, 0, 0, SCREEN_W, 22, C_CARD2, 0);

    s_lbl_wifi = label_at(sbar, 6, 4, "off", &lv_font_montserrat_14, C_DIM2);
    s_lbl_bat  = label_at(sbar, 152, 4, "--%", &lv_font_montserrat_14, C_DIM);
    lv_obj_t *tl = label_at(sbar, 0, 3, "--:--", &lv_font_montserrat_14, C_TEXT);
    lv_obj_align(tl, LV_ALIGN_TOP_MID, 0, 3);
    s_lbl_time = tl;

    // 电池图标:外框 + 内填充 + 右凸点
    lv_obj_t *b = box(sbar, 196, 6, 22, 11, C_CARD2, 3);
    lv_obj_set_style_border_width(b, 1, 0);
    lv_obj_set_style_border_color(b, lv_color_hex(C_DIM2), 0);
    s_bat_fill = box(b, 2, 2, 8, 7, C_GRN, 2);
    box(sbar, 218, 9, 2, 5, C_DIM2, 1);
}

static void update_sbar(void)
{
    char hhmm[8];
    cs_time_hhmm(hhmm, sizeof(hhmm));
    lv_label_set_text(s_lbl_time, hhmm);

    cs_net_state_t st = cs_net_state();
    const char *wtxt;
    uint32_t wcol;
    switch (st) {
    case CS_NET_ONLINE:     wtxt = cs_net_ssid(); if (!wtxt[0]) wtxt = "online"; wcol = C_GRN;  break;
    case CS_NET_CONNECTING: wtxt = "linking";   wcol = C_YEL;  break;
    case CS_NET_SCANNING:   wtxt = "scanning";  wcol = C_YEL;  break;
    case CS_NET_APLIST:     wtxt = "found";     wcol = C_BLUE; break;
    case CS_NET_FAILED:     wtxt = "no wifi";   wcol = C_RED;  break;
    default:                wtxt = "off";       wcol = C_DIM2; break;
    }
    char wbuf[22];
    trunc_u8(wbuf, sizeof(wbuf), wtxt, 8);
    lv_label_set_text(s_lbl_wifi, wbuf);
    lv_obj_set_style_text_color(s_lbl_wifi, lv_color_hex(wcol), 0);

    // 电池每 2 秒读一次,不拿 I2C 刷屏
    if (s_bat_tick-- <= 0) {
        s_bat_tick = 10;
        int soc = bsp_battery_soc();
        if (soc < 0) {
            lv_label_set_text(s_lbl_bat, "--%");
            lv_obj_set_style_bg_color(s_bat_fill, lv_color_hex(C_DIM2), 0);
            lv_obj_set_width(s_bat_fill, 8);
        } else {
            char bb[8];
            snprintf(bb, sizeof(bb), "%d%%", soc);
            lv_label_set_text(s_lbl_bat, bb);
            uint32_t c = soc > 60 ? C_GRN : (soc > 25 ? C_YEL : C_RED);
            lv_obj_set_style_bg_color(s_bat_fill, lv_color_hex(c), 0);
            int bw = 18 * soc / 100;
            lv_obj_set_width(s_bat_fill, bw < 2 ? 2 : bw);
        }
    }
}

// ---------------------------------------------------------------------------
// 底部提示条
// ---------------------------------------------------------------------------
static void update_hint(void)
{
    char buf[80];
    switch (s_view) {
    case VIEW_MATCH: {
        char m[40];
        trunc_u8(m, sizeof(m), cs_data_fetch_msg(), 20);
        snprintf(buf, sizeof(buf), "%s | %s", cs_data_is_from_net() ? "LIVE" : "OFFLINE", m);
        break;
    }
    case VIEW_WIFI:
        snprintf(buf, sizeof(buf), "UP/DN pick  OK join  2xOK back");
        break;
    default:
        snprintf(buf, sizeof(buf), "UP/DN char  OK input  2xOK back");
        break;
    }
    lv_obj_t *hl = lv_obj_get_child(s_hint, 0);
    if (hl) lv_label_set_text(hl, buf);
}

// ---------------------------------------------------------------------------
// 视图 1:比赛看板
// ---------------------------------------------------------------------------
static void build_match(void)
{
    const cs_data_t *d = cs_data();
    if (d->count <= 0) {
        label_at(s_body, 40, 120, "No match data", &lv_font_montserrat_20, C_DIM);
        return;
    }
    if (s_idx >= d->count) s_idx = 0;
    const cs_match_t *m = &d->m[s_idx];

    // ---- 赛事头部 ----
    lv_obj_t *head = box(s_body, 8, 26, 224, 30, C_CARD, 6);
    box(head, 8, 9, 12, 12, C_RED, 3);
    char ev[24];
    trunc_u8(ev, sizeof(ev), m->event, 16);
    label_at(head, 26, 7, ev, &lv_font_montserrat_14, C_TEXT);
    if (m->date[0]) {
        lv_obj_t *dl = label(head, m->date, &lv_font_montserrat_14, C_DIM);
        lv_obj_align(dl, LV_ALIGN_TOP_RIGHT, -8, 7);
    }

    // ---- 比分卡 ----
    lv_obj_t *card = box(s_body, 8, 60, 224, 106, C_CARD, 8);

    // 两队徽章(圆角方块 + 队名缩写)
    box(card, 14, 16, 54, 54, m->t1_color, 14);
    box(card, 156, 16, 54, 54, m->t2_color, 14);
    char sh[8];
    trunc_u8(sh, sizeof(sh), m->t1_short, 4);
    lv_obj_t *b1 = label(card, sh, &lv_font_montserrat_20, C_TEXT);
    lv_obj_align(b1, LV_ALIGN_TOP_LEFT, 14, 32);
    lv_obj_set_width(b1, 54);
    lv_obj_set_style_text_align(b1, LV_TEXT_ALIGN_CENTER, 0);
    trunc_u8(sh, sizeof(sh), m->t2_short, 4);
    lv_obj_t *b2 = label(card, sh, &lv_font_montserrat_20, C_TEXT);
    lv_obj_align(b2, LV_ALIGN_TOP_LEFT, 156, 32);
    lv_obj_set_width(b2, 54);
    lv_obj_set_style_text_align(b2, LV_TEXT_ALIGN_CENTER, 0);

    // 中间大比分 / VS
    char sc[20];
    if (strcmp(m->status, "upcoming") == 0) snprintf(sc, sizeof(sc), "VS");
    else snprintf(sc, sizeof(sc), "%d:%d", m->score1, m->score2);
    lv_obj_t *sl = label(card, sc, &lv_font_montserrat_28, C_TEXT);
    lv_obj_align(sl, LV_ALIGN_TOP_MID, 0, 28);

    // BO3 / LIVE 标签
    bool live = (strcmp(m->status, "live") == 0);
    lv_obj_t *bl = label(card, live ? "LIVE" : (m->bo[0] ? m->bo : "BO3"),
                         &lv_font_montserrat_14, live ? C_RED : C_DIM2);
    lv_obj_align(bl, LV_ALIGN_TOP_MID, 0, 66);

    // 队名(徽章下方)
    char tn[14];
    trunc_u8(tn, sizeof(tn), m->t1_name, 9);
    lv_obj_t *n1 = label_at(card, 8, 78, tn, &lv_font_montserrat_14, C_DIM);
    lv_obj_set_width(n1, 66);
    lv_obj_set_style_text_align(n1, LV_TEXT_ALIGN_CENTER, 0);
    trunc_u8(tn, sizeof(tn), m->t2_name, 9);
    lv_obj_t *n2 = label_at(card, 150, 78, tn, &lv_font_montserrat_14, C_DIM);
    lv_obj_set_width(n2, 66);
    lv_obj_set_style_text_align(n2, LV_TEXT_ALIGN_CENTER, 0);

    // 页码
    char pc[12];
    snprintf(pc, sizeof(pc), "%d/%d", s_idx + 1, d->count);
    lv_obj_t *pl = label(card, pc, &lv_font_montserrat_14, C_DIM2);
    lv_obj_align(pl, LV_ALIGN_TOP_RIGHT, -8, 4);

    // ---- 逐图比分 ----
    lv_obj_t *maps = box(s_body, 8, 172, 224, 112, C_CARD, 8);
    if (m->map_count == 0) {
        label_at(maps, 62, 46, "Maps TBD", &lv_font_montserrat_14, C_DIM2);
        return;
    }
    for (int i = 0; i < m->map_count && i < 4; i++) {
        const cs_map_t *mp = &m->maps[i];
        int y = 6 + i * 27;
        box(maps, 10, y + 5, 4, 17, map_color(mp->name), 2);
        char mn[14];
        trunc_u8(mn, sizeof(mn), mp->name, 10);
        label_at(maps, 22, y + 6, mn, &lv_font_montserrat_14, C_TEXT);

        char ms[20];
        if (mp->s1 == 0 && mp->s2 == 0) snprintf(ms, sizeof(ms), "-");
        else snprintf(ms, sizeof(ms), "%d:%d", mp->s1, mp->s2);
        uint32_t mc = (mp->s1 == mp->s2) ? C_DIM : (mp->s1 > mp->s2 ? C_GRN : C_RED);
        lv_obj_t *ml = label_at(maps, 0, y + 6, ms, &lv_font_montserrat_14, mc);
        lv_obj_align(ml, LV_ALIGN_TOP_RIGHT, -14, y + 6);

        if (i < m->map_count - 1) box(maps, 10, y + 28, 204, 1, C_LINE, 0);
    }
}

// ---------------------------------------------------------------------------
// 视图 2:Wi-Fi 列表
// ---------------------------------------------------------------------------
static void build_wifi(void)
{
    cs_net_state_t st = cs_net_state();

    lv_obj_t *head = box(s_body, 8, 26, 224, 26, C_CARD, 6);
    const char *t = "SELECT WI-FI";
    uint32_t tc = C_TEXT;
    if (st == CS_NET_SCANNING)        { t = "SCANNING...";        tc = C_YEL; }
    else if (st == CS_NET_CONNECTING) { t = "CONNECTING...";      tc = C_YEL; }
    else if (st == CS_NET_ONLINE)     { t = "CONNECTED";          tc = C_GRN; }
    else if (st == CS_NET_FAILED)     { t = "FAILED - OK rescan"; tc = C_RED; }
    label_at(head, 10, 5, t, &lv_font_montserrat_14, tc);

    lv_obj_t *list = box(s_body, 8, 56, 224, 228, C_CARD, 6);

    int n = cs_net_ap_count();
    if (n <= 0) {
        const char *msg = (st == CS_NET_SCANNING) ? "Scanning 2.4GHz..." : "No AP found";
        label_at(list, 26, 100, msg, &lv_font_montserrat_14, C_DIM);
        return;
    }
    if (s_ap_sel >= n) s_ap_sel = 0;

    int top = (s_ap_sel >= 6) ? s_ap_sel - 5 : 0;   // 简易滚动窗口
    for (int i = 0; i < 6; i++) {
        int idx = top + i;
        if (idx >= n) break;
        int y = 6 + i * 36;
        bool sel = (idx == s_ap_sel);

        lv_obj_t *row = box(list, 5, y, 214, 32, sel ? C_SEL : C_CARD, 5);
        if (sel) {
            lv_obj_set_style_border_width(row, 1, 0);
            lv_obj_set_style_border_color(row, lv_color_hex(C_BLUE), 0);
        }

        // 信号强度 3 格
        int rssi = cs_net_ap_rssi(idx);
        int lvl = rssi > -55 ? 3 : (rssi > -70 ? 2 : 1);
        uint32_t bc = rssi > -55 ? C_GRN : (rssi > -70 ? C_YEL : C_RED);
        for (int k = 0; k < 3; k++) {
            int h = 5 + k * 4;
            box(row, 8 + k * 6, 24 - h, 4, h, (k < lvl) ? bc : C_LINE, 1);
        }

        // 加密锁标记
        if (cs_net_ap_secure(idx)) box(row, 32, 12, 9, 9, C_YEL, 2);

        char ss[28];
        trunc_u8(ss, sizeof(ss), cs_net_ap_ssid(idx), 12);
        label_at(row, 48, 8, ss, &lv_font_montserrat_14, sel ? C_TEXT : C_DIM);

        if (strcmp(cs_net_ap_ssid(idx), cs_net_ap_prev_ssid()) == 0) {
            lv_obj_t *sv = label(row, "SAVED", &lv_font_montserrat_14, C_GRN);
            lv_obj_align(sv, LV_ALIGN_RIGHT_MID, -8, 0);
        }
    }
}

// ---------------------------------------------------------------------------
// 视图 3:密码输入
// ---------------------------------------------------------------------------
static void build_pass(void)
{
    lv_obj_t *head = box(s_body, 8, 26, 224, 26, C_CARD, 6);
    label_at(head, 10, 5, "ENTER PASSWORD", &lv_font_montserrat_14, C_YEL);

    // 目标网络 + 已输入
    lv_obj_t *card = box(s_body, 8, 56, 224, 76, C_CARD, 6);
    label_at(card, 10, 6, "Network", &lv_font_montserrat_14, C_DIM2);
    char ss[28];
    trunc_u8(ss, sizeof(ss), s_target_ssid, 17);
    label_at(card, 10, 23, ss, &lv_font_montserrat_14, C_TEXT);

    char pv[30];
    trunc_u8(pv, sizeof(pv), s_pass[0] ? s_pass : "(type password)", 20);
    label_at(card, 10, 48, pv, &lv_font_montserrat_20, s_pass[0] ? C_TEXT : C_DIM2);

    // 字符选择器
    lv_obj_t *sel = box(s_body, 8, 136, 224, 96, C_CARD2, 6);
    lv_obj_set_style_border_width(sel, 1, 0);
    lv_obj_set_style_border_color(sel, lv_color_hex(C_LINE), 0);

    const char *set = SETS[s_set];
    int len = (int)strlen(set);
    char curbuf[10];
    uint32_t ccol;
    if (s_sel < len) {
        snprintf(curbuf, sizeof(curbuf), "%c", set[s_sel]);
        ccol = C_TEXT;
    } else if (s_sel == len) {
        snprintf(curbuf, sizeof(curbuf), "DEL");
        ccol = C_RED;
    } else if (s_sel == len + 1) {
        snprintf(curbuf, sizeof(curbuf), "SET");
        ccol = C_BLUE;
    } else {
        snprintf(curbuf, sizeof(curbuf), "OK");
        ccol = C_YEL;
    }

    lv_obj_t *cv = label(sel, curbuf, &lv_font_montserrat_28, ccol);
    lv_obj_align(cv, LV_ALIGN_TOP_MID, 0, 12);

    lv_obj_t *up = label_at(sel, 22, 22, "^", &lv_font_montserrat_20, C_DIM2);
    (void)up;
    lv_obj_t *dn = label_at(sel, 204, 22, "v", &lv_font_montserrat_20, C_DIM2);
    (void)dn;

    static const char *SETNAME[] = { "abc", "ABC", "123", "sym" };
    char info[44];
    snprintf(info, sizeof(info), "set %d/%d  [%s]", s_set + 1, SET_COUNT, SETNAME[s_set]);
    lv_obj_t *il = label_at(sel, 0, 68, info, &lv_font_montserrat_14, C_DIM);
    lv_obj_set_width(il, 224);
    lv_obj_set_style_text_align(il, LV_TEXT_ALIGN_CENTER, 0);

    // 连接进度
    cs_net_state_t st = cs_net_state();
    if (st == CS_NET_CONNECTING) {
        label_at(s_body, 60, 240, "Connecting...", &lv_font_montserrat_14, C_YEL);
    } else if (st == CS_NET_FAILED) {
        label_at(s_body, 30, 240, "Failed - check password", &lv_font_montserrat_14, C_RED);
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
    s_body = box(s_scr, 0, 22, SCREEN_W, SCREEN_H - 22 - HINT_H, C_BG, 0);

    switch (s_view) {
    case VIEW_MATCH: build_match(); break;
    case VIEW_WIFI:  build_wifi();  break;
    default:         build_pass();  break;
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
    case VIEW_MATCH:
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
            // 有密码:先记目标网络,再进密码页
            snprintf(s_target_ssid, sizeof(s_target_ssid), "%s", ssid);
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
        } else if (s_sel == len) {               // DEL 退格
            size_t pl = strlen(s_pass);
            if (pl > 0) s_pass[pl - 1] = 0;
            rebuild();
        } else if (s_sel == len + 1) {           // SET 换字符集
            s_set = (s_set + 1) % SET_COUNT;
            s_sel = 0;
            rebuild();
        } else {                                 // OK 提交连接
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
    case VIEW_MATCH:
        s_ap_sel = 0;
        set_view(VIEW_WIFI);
        cs_net_state_reset();
        cs_net_scan();
        break;
    case VIEW_WIFI:
        set_view(VIEW_MATCH);
        break;
    default:
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
        if (s_view == VIEW_WIFI || s_view == VIEW_PASS) rebuild();
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
            s_idx = 0;
            if (s_view == VIEW_MATCH) rebuild();
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

    s_view = VIEW_MATCH;
    s_idx = 0;
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
    lv_obj_t *hl = label(s_hint, "", &lv_font_montserrat_14, C_DIM);
    lv_obj_align(hl, LV_ALIGN_CENTER, 0, 0);

    // 先把缓存/内置数据显示出来,再谈联网
    cs_data_load_cache();
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
        s_lbl_time = s_lbl_wifi = s_lbl_bat = s_bat_fill = NULL;
    }
}

void demo_csboard_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // UP/DOWN 只有单击语义,立即执行(不引入延时,保证手感)
    if (ev == BSP_BTN_CLICK && (btn == BSP_BTN_UP || btn == BSP_BTN_DOWN)) {
        switch (s_view) {
        case VIEW_MATCH: {
            const cs_data_t *d = cs_data();
            if (d->count > 0) {
                if (btn == BSP_BTN_UP) s_idx = (s_idx + d->count - 1) % d->count;
                else                   s_idx = (s_idx + 1) % d->count;
                rebuild();
            }
            break;
        }
        case VIEW_WIFI: {
            int n = cs_net_ap_count();
            if (n > 0) {
                if (btn == BSP_BTN_UP) s_ap_sel = (s_ap_sel + n - 1) % n;
                else                   s_ap_sel = (s_ap_sel + 1) % n;
                rebuild();
            }
            break;
        }
        default: {
            int total = (int)strlen(SETS[s_set]) + 3;   // 字符 + DEL/SET/OK
            if (btn == BSP_BTN_UP) s_sel = (s_sel + total - 1) % total;
            else                   s_sel = (s_sel + 1) % total;
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
