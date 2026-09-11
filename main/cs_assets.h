// main/cs_assets.h —— 看板用的静态资源(队标 + 中文字体)。
//
// cs_assets.c / cs_font_cn16.c 都是脚本生成的,不要手改:
//   tools/gen_csboard_assets.py
#pragma once

#include "lvgl.h"

// 中文字体 16px(ASCII + GB2312 常用汉字)。生成的,别手改。
extern const lv_font_t font_cn16;

// 按 id(如 "g2" / "navi",大小写无关)取真实战队队标;未收录返回 NULL,
// 调用方应回退到"占位徽章"(纯队色方块)而不是留空。
//   cs_logo_get()       48x48,比分卡用
//   cs_logo_get_small() 20x20,战绩/预告列表缩略用(预生成,固件不做运行时缩放)
//
// 已收录的 id 见 tools/cs_teams.json(含别名,如 navi / natus-vincere 等价)。
const lv_image_dsc_t *cs_logo_get(const char *id);
const lv_image_dsc_t *cs_logo_get_small(const char *id);
