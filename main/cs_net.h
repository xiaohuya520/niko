// main/cs_net.h —— CS 赛事看板的「联网 + 数据」层。
//
// 职责:
//   1) Wi-Fi STA 配网:扫描 AP、连接、保存凭证(下次自动重连);
//   2) 从数据源 URL 拉取 JSON 赛程,解析成 cs_data_t;
//   3) 把 JSON 原文缓存进 NVS,断网时显示上次数据;
//   4) 提供北京时间(HH:MM)给状态栏。
//
// 本层不碰 LVGL。UI 只读结果,所有耗时动作(扫描/连接/下载)都在后台任务里跑,
// UI 侧用 cs_net_state() / cs_data_fetch_state() 轮询。
#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

// ---------------- 数据模型 ----------------
#define CS_MAX_MAPS     5
#define CS_MAX_MATCHES  16

#define CS_EVENT_LEN    40
#define CS_DATE_LEN     12
#define CS_TIME_LEN     8
#define CS_BO_LEN       6
#define CS_STATUS_LEN   10
#define CS_TEAM_LEN     20
#define CS_SHORT_LEN    8
// 队标 id 最长的是 "astralis-talent"(15 字符),留到 24 免得被截断后查不到表
#define CS_LOGO_LEN     24
#define CS_MAP_LEN      20
#define CS_UPDATED_LEN  24

// 比赛状态(与 JSON 里 status 字段一致)
#define CS_ST_LIVE      "live"       // 进行中
#define CS_ST_FINISHED  "finished"   // 已结束(历史战绩)
#define CS_ST_UPCOMING  "upcoming"   // 未开始(赛事预告)

typedef struct {
    char name[CS_MAP_LEN];   // 英文图名 Mirage / Inferno ...(用于配色)
    char cn[CS_MAP_LEN];     // 中文图名 荒漠迷城 ...
    int  s1;                 // 左队(team1)得分
    int  s2;                 // 右队(team2)得分
    int  winner;             // 1=左胜 2=右胜 0=未知
} cs_map_t;

typedef struct {
    char     event[CS_EVENT_LEN];   // 赛事名(中文,如 "BLAST 世界总决赛")
    char     stage[CS_EVENT_LEN];   // 阶段(如 "决赛"/"半决赛"),可空
    char     date[CS_DATE_LEN];     // 09-11
    char     time[CS_TIME_LEN];     // 20:00(预告用)
    char     bo[CS_BO_LEN];         // BO3
    char     status[CS_STATUS_LEN]; // live / finished / upcoming
    char     t1_name[CS_TEAM_LEN];  // G2 / NAVI ...(真实队名,保持原文)
    char     t1_short[CS_SHORT_LEN];// 列表窄栏用的短名(可空;空则用 name)
    char     t1_logo[CS_LOGO_LEN];  // 队标 id,对应 cs_logo_get()
    uint32_t t1_color;
    char     t2_name[CS_TEAM_LEN];
    char     t2_short[CS_SHORT_LEN];
    char     t2_logo[CS_LOGO_LEN];
    uint32_t t2_color;
    int      score1;
    int      score2;
    int      map_count;
    cs_map_t maps[CS_MAX_MAPS];
} cs_match_t;

typedef struct {
    char       updated[CS_UPDATED_LEN];  // 数据更新时间串
    int        count;
    cs_match_t m[CS_MAX_MATCHES];
} cs_data_t;

// ---------------- Wi-Fi 状态 ----------------
typedef enum {
    CS_NET_OFF = 0,      // 未初始化
    CS_NET_READY,        // 已初始化,空闲
    CS_NET_SCANNING,     // 扫描中
    CS_NET_APLIST,       // 扫描完成,列表可读
    CS_NET_CONNECTING,   // 正在连接
    CS_NET_ONLINE,       // 已拿到 IP
    CS_NET_FAILED,       // 扫描/连接失败
} cs_net_state_t;

// ---------------- 数据拉取状态 ----------------
typedef enum {
    CS_FETCH_IDLE = 0,
    CS_FETCH_RUNNING,
    CS_FETCH_OK,
    CS_FETCH_FAIL,
} cs_fetch_state_t;

// 初始化 Wi-Fi(幂等)。成功后尝试用已保存凭证自动重连。
esp_err_t cs_net_init(void);
void      cs_net_shutdown(void);

cs_net_state_t cs_net_state(void);
void           cs_net_state_reset(void);     // 把 FAILED 清回 READY
bool           cs_net_online(void);
const char    *cs_net_ip(void);
const char    *cs_net_ssid(void);

// 扫描(异步,内部起独立任务)。完成后 state 变 CS_NET_APLIST(或 CS_NET_FAILED)。
// 可以重复调用:正在扫时会被忽略。
void cs_net_scan(void);

// UI 侧每 200ms 调一次。扫描超过约 15s 仍未完成就强制收尾成 CS_NET_FAILED,
// 保证界面不会永远停在"正在扫描"。
void        cs_net_scan_watchdog(void);
bool        cs_net_scan_busy(void);      // 扫描任务是否在跑
const char *cs_net_scan_msg(void);       // 最近一次扫描的错误说明(空串=无)

int         cs_net_ap_count(void);
const char *cs_net_ap_ssid(int idx);
int         cs_net_ap_rssi(int idx);     // dBm
bool        cs_net_ap_secure(int idx);
const char *cs_net_ap_prev_ssid(void);   // 上次连过的 SSID(用于列表标注)

// 连接指定 SSID。password 可为 NULL/空串(开放网络)。异步,完成后 state 变 ONLINE/FAILED。
void cs_net_connect(const char *ssid, const char *password);
void cs_net_autoconnect(void);
void cs_net_forget(void);                // 清除保存的凭证

// ---------------- 数据源 ----------------
const char *cs_data_url(void);
void        cs_data_set_url(const char *url);   // 保存到 NVS

const cs_data_t *cs_data(void);          // 当前数据(可能来自 NVS 缓存或内置示例)
bool             cs_data_is_from_net(void);

esp_err_t cs_data_load_cache(void);      // 从 NVS 载入缓存;无缓存则载入内置示例
void      cs_data_use_builtin(void);

// 按状态筛选:把 cs_data() 中 status == st 的下标写进 idx_out(最多 max 个),
// 返回命中个数。st 传 NULL 表示不过滤(全部)。
int cs_data_filter(const char *st, int *idx_out, int max);

// 异步联网刷新。完成后 cs_data_fetch_state() 变 OK/FAIL,cs_data() 为新数据。
void            cs_data_refresh_async(void);
cs_fetch_state_t cs_data_fetch_state(void);
const char     *cs_data_fetch_msg(void);
void            cs_data_fetch_reset(void);   // 清回 IDLE

// 北京时间 HH:MM;未同步成功时写 "--:--"。
void cs_time_hhmm(char *out, int n);
