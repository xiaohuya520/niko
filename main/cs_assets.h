// main/cs_assets.h —— 看板用的静态资源(队标 + 中文字体)。
//
// 位图本体不在 app 里:队标与中文字体位图都放在 Flash 资源分区 csres
// (由 prebuilt/csres.bin 提供,tools/pack_csres.py 生成,合并镜像时注入)。
// 因此 **用任何资源之前必须先 cs_assets_load()** —— 它在 app_main() 里调一次。
//
// cs_assets.c 是脚本生成的(tools/pack_csres.py),不要手改。
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "lvgl.h"

// 中文字体 16px(ASCII + GB2312 常用汉字)。生成的,别手改。
// 位图由 cs_assets_load() 绑定到 csres 分区;没加载时字形不可用。
extern const lv_font_t font_cn16;

// 把 csres 分区映射进地址空间,并按包内偏移绑定队标与中文字体位图。
// 必须在第一次使用 font_cn16 / cs_logo_* 之前调用(app_main 里)。
// 返回 false 表示分区缺失或资源包损坏 —— 队标会退化为占位徽章。
bool cs_assets_load(void);

// 由 cs_assets_load() 调用,把字体位图绑到映射区。
// 实现就在生成的 cs_font_cn16.c 里(那里能摸到 font_dsc)。
bool cs_font_cn16_bind(const void *bitmap, uint32_t len);

// 按 id(如 "g2" / "navi",大小写无关)取真实战队队标;未收录返回 NULL,
// 调用方应回退到"占位徽章"(纯队色方块)而不是留空。
//   cs_logo_get()       48x48,比分卡用
//   cs_logo_get_small() 20x20,战绩/预告列表缩略用(预生成,固件不做运行时缩放)
//
// 已收录的 id 见 tools/cs_teams.json(含别名,如 navi / natus-vincere 等价)。
const lv_image_dsc_t *cs_logo_get(const char *id);
const lv_image_dsc_t *cs_logo_get_small(const char *id);
