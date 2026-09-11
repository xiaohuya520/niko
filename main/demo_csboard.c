// main/demo_csboard.c —— CS 赛事看板(ESP32-C3 / LVGL 参考示例页)。
//
// 复用设备右侧 UP/DOWN/OK 三键:
//   UP/DOWN  —— 在当前视图内导航(护照:切选手 / 赛事:翻场次 / 积分榜:滚名次)
//   OK 单击   —— 三视图循环切换:选手护照 -> 赛事 -> 积分榜 -> 选手护照
//   OK 长按   —— 由 main.c 统一拦截,返回主菜单
//
// 注意:LVGL 默认 montserrat 字体为 Latin,不含中文与块字符(U+2588 等),
// 故本页 UI 文本一律使用 ASCII。如需中文,需额外嵌入 CJK 字体子集
// (受 3MB 应用分区 + 无 PSRAM 限制,建议保持英文 UI)。
#include "demo.h"
#include "bsp_button.h"
#include "ui_pixel.h"
#include "lvgl.h"
#include <stdio.h>

/* ===================== 数据源(示例) ===================== */
/* 后续可替换为真实接口抓取的数据:在 enter() 里用 bsp_wifi + 简易 HTTP
 * 拉取 HLTV / PandaScore / bo3.gg,解析后刷新下列数组即可。 */
typedef struct {
    const char *name, *team, *ba, *role;
    float rating, kd, adr;
    int   hs, aim, clut, iq;
} player_t;

static const player_t PLAYERS[] = {
    {"NiKo",   "FaZe Clan",  "BA", "Rifler", 1.12, 1.05, 76.3, 48, 81, 62, 85},
    {"m0NESY", "G2 Esports", "RS", "AWPer",  1.20, 1.10, 74.1, 55, 88, 70, 78},
    {"ZywOo",  "Vitality",   "FR", "AWPer",  1.30, 1.18, 80.5, 52, 90, 82, 80},
    {"donk",   "Spirit",     "RU", "Rifler", 1.25, 1.15, 79.2, 49, 86, 75, 72},
};
#define NPLAYERS (int)(sizeof(PLAYERS) / sizeof(PLAYERS[0]))

typedef struct { const char *a, *b, *bo, *time, *st; } match_t;
static const match_t MATCHES[] = {
    {"FaZe", "Vitality", "BO3", "19:00",    "LIVE"},
    {"G2",   "Spirit",   "BO1", "21:00",    "SOON"},
    {"MOUZ", "NAVI",     "BO3", "tomorrow", "SOON"},
    {"Liquid", "FURIA",  "BO1", "+2d",      "SOON"},
    {"Vitality", "Spirit", "BO5", "Major GF", "SOON"},
    {"FaZe", "G2",       "BO3", "+3d",      "SOON"},
};
#define NMATCHES (int)(sizeof(MATCHES) / sizeof(MATCHES[0]))

typedef struct { int r; const char *team; int pts; } rank_t;
static const rank_t RANKS[] = {
    {1, "Vitality", 987}, {2, "Spirit", 812}, {3, "FaZe", 654},
    {4, "MOUZ", 533}, {5, "G2", 498}, {6, "NAVI", 470},
};
#define NRANKS (int)(sizeof(RANKS) / sizeof(RANKS[0]))

/* ===================== 视图状态 ===================== */
static lv_obj_t *s_scr, *s_body, *s_mascot;
static int s_view;                 // 0 选手护照 / 1 赛事 / 2 积分榜
static int s_player, s_match, s_rank;

/* 能力条:[#####----] 共 8 格 */
static void bar(char *buf, int v) {
    int full = v * 8 / 100;
    int i = 0;
    buf[i++] = '[';
    for (int k = 0; k < 8; k++) buf[i++] = (k < full) ? '#' : '-';
    buf[i++] = ']';
    buf[i] = '\0';
}

static void render_player(char *o, size_t n) {
    char b1[12], b2[12], b3[12];
    bar(b1, PLAYERS[s_player].aim);
    bar(b2, PLAYERS[s_player].clut);
    bar(b3, PLAYERS[s_player].iq);
    const player_t *p = &PLAYERS[s_player];
    snprintf(o, n,
        "PLAYER CARD\n"
        "%s / %s\n"
        "Age %d  %s  %s\n"
        "Rate %.2f  K/D %.2f\n"
        "ADR %.1f  HS%% %d\n"
        "AIM   %s %d\n"
        "CLUT  %s %d\n"
        "IQ    %s %d\n"
        "UP/DN:player OK:next",
        p->name, p->team, p->age, p->ba, p->role,
        p->rating, p->kd, p->adr, p->hs,
        b1, p->aim, b2, p->clut, b3, p->iq);
}

static void render_matches(char *o, size_t n) {
    int i = s_match % NMATCHES;
    int j = (i + 1) % NMATCHES;
    snprintf(o, n,
        "MATCHES %d/%d\n"
        "%s vs %s\n"
        "%s  %s  %s\n"
        "--- next ---\n"
        "%s vs %s\n"
        "%s  %s  %s\n"
        "UP/DN:scroll OK:card",
        i + 1, NMATCHES,
        MATCHES[i].a, MATCHES[i].b, MATCHES[i].bo, MATCHES[i].time, MATCHES[i].st,
        MATCHES[j].a, MATCHES[j].b, MATCHES[j].bo, MATCHES[j].time, MATCHES[j].st);
}

static void render_ranking(char *o, size_t n) {
    int i = s_rank % NRANKS;
    snprintf(o, n,
        "WORLD RANKING\n"
        "#%d %s  %d\n"
        "#%d %s  %d\n"
        "#%d %s  %d\n"
        "#%d %s  %d\n"
        "#%d %s  %d\n"
        "UP/DN:scroll OK:menu",
        RANKS[i].r, RANKS[i].team, RANKS[i].pts,
        RANKS[(i + 1) % NRANKS].r, RANKS[(i + 1) % NRANKS].team, RANKS[(i + 1) % NRANKS].pts,
        RANKS[(i + 2) % NRANKS].r, RANKS[(i + 2) % NRANKS].team, RANKS[(i + 2) % NRANKS].pts,
        RANKS[(i + 3) % NRANKS].r, RANKS[(i + 3) % NRANKS].team, RANKS[(i + 3) % NRANKS].pts,
        RANKS[(i + 4) % NRANKS].r, RANKS[(i + 4) % NRANKS].team, RANKS[(i + 4) % NRANKS].pts);
}

static void render(void) {
    char buf[256];
    if (s_view == 0)      render_player(buf, sizeof buf);
    else if (s_view == 1) render_matches(buf, sizeof buf);
    else                  render_ranking(buf, sizeof buf);
    lv_label_set_text(s_body, buf);
}

void demo_csboard_enter(void) {
    s_view = 0; s_player = 0; s_match = 0; s_rank = 0;
    s_scr = ui_pixel_screen_create("CS BOARD");
    lv_obj_t *panel = ui_pixel_panel_create(s_scr, 18, 58, 204, 184, UI_PAPER);
    s_body = lv_label_create(panel);
    lv_obj_set_style_text_font(s_body, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(s_body, lv_color_hex(UI_INK), 0);
    lv_obj_set_style_text_align(s_body, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_align(s_body, LV_ALIGN_TOP_LEFT, 6, 6);
    s_mascot = ui_pixel_mascot_create(s_scr, 101, 238);
    render();
    lv_screen_load(s_scr);
}

void demo_csboard_exit(void) {
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_body = s_mascot = NULL; }
}

void demo_csboard_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if (ev != BSP_BTN_CLICK) return;
    if (btn == BSP_BTN_OK) {
        s_view = (s_view + 1) % 3;          // 三视图循环切换
        ui_pixel_mascot_jump(s_mascot);
    } else if (btn == BSP_BTN_UP) {
        if (s_view == 0)      s_player = (s_player + NPLAYERS - 1) % NPLAYERS;
        else if (s_view == 1) s_match  = (s_match  + NMATCHES - 1) % NMATCHES;
        else                  s_rank   = (s_rank   + NRANKS   - 1) % NRANKS;
    } else { /* DOWN */
        if (s_view == 0)      s_player = (s_player + 1) % NPLAYERS;
        else if (s_view == 1) s_match  = (s_match  + 1) % NMATCHES;
        else                  s_rank   = (s_rank   + 1) % NRANKS;
    }
    render();
}
