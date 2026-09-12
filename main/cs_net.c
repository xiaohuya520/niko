// main/cs_net.c —— CS 赛事看板的「联网 + 数据」层实现。
//
// 设计取舍:
//  - 本文件完全不碰 LVGL,只做 Wi-Fi / HTTP / JSON / NVS / SNTP,UI 侧轮询状态;
//  - 下载缓冲 12KB、JSON 缓存 8KB:ESP32-C3 无 PSRAM,且 NVS 分区只有 24KB,
//    还要和 Wi-Fi 凭证共享,所以上限卡得比较紧,数据源 JSON 需控制在 7KB 内;
//  - 数据源默认走 jsDelivr CDN(国内可达),指向用户仓库里的 JSON,
//    这样"改数据=改仓库里的 JSON",不需要重新编译固件。
#include "cs_net.h"
#include "demo_radio.h"

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_http_server.h"
#include "esp_mac.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_sntp.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *TAG = "cs_net";

// 默认数据源:仓库里的 JSON,走 jsDelivr(国内可访问)。
// 放在 firmware 分支,这样不碰仓库的 main(那里是用户的 NiKo 追踪页)。
// 换数据源:改这里,或在代码里调 cs_data_set_url()(值会存 NVS 覆盖默认)。
#define CS_DEFAULT_URL "https://cdn.jsdelivr.net/gh/xiaohuya520/niko@firmware/cs_matches.json"

#define CS_NVS_NS       "csboard"
#define CS_NVS_URL_KEY  "url"
#define CS_NVS_JSON_KEY "json"

#define CS_HTTP_BUF_MAX 12288    // 单次下载上限
#define CS_CACHE_MAX    12288    // 写进 NVS 的 JSON 上限(与下载缓冲同上限)
#define CS_AP_MAX       16       // 附近 AP 列表上限(原先 12,人多的地方经常装不下)

// 扫描参数:显式给出每个信道的驻留时间,让整轮扫描有明确的时间上限
// (2.4G 13 个信道 × ~220ms ≈ 3s),不会因为个别信道拖住而永远扫不完。
#define CS_SCAN_MIN_MS  80
#define CS_SCAN_MAX_MS  220

// 数据缓存用的资源分区(cardid 之后,见 partitions.csv)。
// 默认 nvs 只有 24KB,还要和 Wi-Fi 凭证共享,12KB 的 JSON 缓存塞进去太挤;
// 卡 id 之后的空闲 Flash 有 ~4.6MB,这里划 64KB 出来专门放数据。
#define CS_NVS_PART     "csdata"

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
static cs_net_state_t   s_state;
static cs_fetch_state_t s_fetch_state;
static char             s_fetch_msg[64];
static bool             s_wifi_ready;         // esp_wifi_init 已完成
static bool             s_wifi_started;
static bool             s_sntp_started;
static esp_netif_t     *s_sta_netif;
static esp_event_handler_instance_t s_h_wifi;
static esp_event_handler_instance_t s_h_ip;
static char             s_ip[20];
static char             s_ssid[33];
static char             s_prev_ssid[33];
static int              s_reconnect;

static wifi_ap_record_t s_aps[CS_AP_MAX];
static uint16_t         s_ap_count;
static volatile bool    s_scan_busy;      // 扫描任务运行中
static bool             s_scan_keep_online; // 扫描前已联网:扫完要恢复成 ONLINE
static int              s_scan_watch;     // 看门狗计数(UI 每 200ms +1)
static char             s_scan_msg[48];   // 最近一次扫描的错误说明

static char             s_conn_err[48];   // 最近一次连接失败的原因(中文,可上屏)
static int              s_conn_watch;     // CONNECTING 状态的看门狗计数(防"永远连接中")
static bool             s_deliberate;     // true=这次 DISCONNECTED 是我们自己调 disconnect 触发的,不算失败

static cs_data_t        s_data;
static bool             s_from_net;

// ---------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------
static void scpy(char *dst, size_t cap, const char *src)
{
    if (!src) { if (cap) dst[0] = 0; return; }
    size_t n = strlen(src);
    if (n > cap - 1) n = cap - 1;
    memcpy(dst, src, n);
    dst[n] = 0;
}

// ---------------------------------------------------------------------------
// 内置示例数据(断网/首次开机兜底,结构与线上 JSON 完全一致)
// ---------------------------------------------------------------------------
static const cs_data_t k_builtin = {
    .updated = "内置示例",
    .count = 5,
    .m = {
        {
            .event = "ESL 职业联赛 S21", .stage = "小组赛", .date = "09-11", .time = "20:00",
            .bo = "BO3", .status = CS_ST_LIVE,
            .t1_name = "G2", .t1_logo = "g2", .t1_color = 0xE4AE39,
            .t2_name = "NAVI", .t2_logo = "navi", .t2_color = 0xF2E14C,
            .score1 = 1, .score2 = 1, .map_count = 3,
            .maps = {
                { "Inferno", "炼狱小镇", 13, 9, 1 },
                { "Nuke",    "核子危机", 8, 13, 2 },
                { "Mirage",  "荒漠迷城", 0, 0, 0 },
            },
        },
        {
            .event = "BLAST 世界总决赛", .stage = "半决赛", .date = "09-10", .time = "22:30",
            .bo = "BO3", .status = CS_ST_FINISHED,
            .t1_name = "Vitality", .t1_logo = "vitality", .t1_color = 0xFFD928,
            .t2_name = "MOUZ", .t2_logo = "mouz", .t2_color = 0xE43B2F,
            .score1 = 2, .score2 = 0, .map_count = 2,
            .maps = {
                { "Dust2",  "炙热沙城", 13, 7, 1 },
                { "Ancient","远古遗迹", 13, 10, 1 },
            },
        },
        {
            .event = "IEM 卡托维兹", .stage = "四分之一决赛", .date = "09-09", .time = "19:00",
            .bo = "BO3", .status = CS_ST_FINISHED,
            .t1_name = "Spirit", .t1_logo = "spirit", .t1_color = 0x8C6239,
            .t2_name = "FaZe", .t2_logo = "faze", .t2_color = 0xB01C24,
            .score1 = 1, .score2 = 2, .map_count = 3,
            .maps = {
                { "Mirage",  "荒漠迷城", 13, 11, 1 },
                { "Overpass","死亡游乐园", 9, 13, 2 },
                { "Nuke",    "核子危机", 11, 13, 2 },
            },
        },
        {
            .event = "PGL 哥本哈根大师赛", .stage = "小组赛", .date = "09-12", .time = "18:00",
            .bo = "BO3", .status = CS_ST_UPCOMING,
            .t1_name = "Aurora", .t1_logo = "aurora", .t1_color = 0x2AA3EF,
            .t2_name = "Astralis", .t2_logo = "astralis", .t2_color = 0xE43B2F,
            .score1 = 0, .score2 = 0, .map_count = 0,
        },
        {
            .event = "PGL 哥本哈根大师赛", .stage = "小组赛", .date = "09-12", .time = "21:00",
            .bo = "BO3", .status = CS_ST_UPCOMING,
            .t1_name = "Falcons", .t1_logo = "falcons", .t1_color = 0x00B36B,
            .t2_name = "G2", .t2_logo = "g2", .t2_color = 0xE4AE39,
            .score1 = 0, .score2 = 0, .map_count = 0,
        },
    },
};

// ---------------------------------------------------------------------------
// Wi-Fi
// ---------------------------------------------------------------------------
static void start_sntp(void)
{
    if (s_sntp_started) return;
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("ntp.aliyun.com");
    cfg.start = true;
    if (esp_netif_sntp_init(&cfg) == ESP_OK) {
        s_sntp_started = true;
        ESP_LOGI(TAG, "SNTP 已启动");
    }
}

// 把 STA 断开原因码翻译成一句用户能看懂的话(直接上屏,拍照就能定位问题)。
// 常见码: 2=AUTH_EXPIRE 15=4WAY_HANDSHAKE_TIMEOUT 200=BEACON_TIMEOUT
//         201=NO_AP_FOUND 202=AUTH_FAIL 203/204/205=关联/握手/建链失败
static void conn_err_set(int reason)
{
    switch (reason) {
    case 15:  scpy(s_conn_err, sizeof(s_conn_err), "密码可能不对");      break;
    case 2:   scpy(s_conn_err, sizeof(s_conn_err), "认证超时,信号弱");   break;
    case 201: scpy(s_conn_err, sizeof(s_conn_err), "找不到这个网络");    break;
    case 202: scpy(s_conn_err, sizeof(s_conn_err), "认证失败");          break;
    case 203:
    case 204:
    case 205: scpy(s_conn_err, sizeof(s_conn_err), "连接被路由器拒绝");  break;
    case 200: scpy(s_conn_err, sizeof(s_conn_err), "信号不稳,靠近些");   break;
    default:
        snprintf(s_conn_err, sizeof(s_conn_err), "连接失败(代码%d)", reason % 1000);
        break;
    }
}

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    switch (id) {
    case WIFI_EVENT_STA_DISCONNECTED: {
        const wifi_event_sta_disconnected_t *d = (const wifi_event_sta_disconnected_t *)data;
        int reason = d ? (int)d->reason : -1;
        ESP_LOGW(TAG, "Wi-Fi 断开, reason=%d", reason);
        s_ip[0] = 0;
        // 配网/扫描期间不自动重连:否则 esp_wifi_connect() 会把正在跑的扫描打断,
        // 表现就是"一直停在扫描页"。扫描任务自己会在扫完后让用户重新连接。
        if (s_scan_busy) break;
        // 我们主动断开(cs_net_connect 换目标前的 disconnect)不记失败也不重试,
        // 紧跟着的 esp_wifi_connect() 已经按新配置发起连接。
        if (s_deliberate) { s_deliberate = false; break; }
        if (s_state == CS_NET_CONNECTING || s_state == CS_NET_ONLINE) {
            conn_err_set(reason);
            if (s_reconnect < 3) {
                s_reconnect++;
                esp_wifi_connect();
                s_state = CS_NET_CONNECTING;
            } else {
                scpy(s_fetch_msg, sizeof(s_fetch_msg), "Wi-Fi connect failed");
                s_state = CS_NET_FAILED;
            }
        }
        break;
    }
    case WIFI_EVENT_SCAN_DONE:
        // 扫描结果统一由 scan_task() 用阻塞式调用取走,这里不再 get_ap_records,
        // 免得事件线程和扫描任务同时取同一份结果。
        ESP_LOGI(TAG, "扫描事件完成");
        break;
    default:
        break;
    }
}

static void on_ip_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    if (id != IP_EVENT_STA_GOT_IP) return;
    const ip_event_got_ip_t *ev = (const ip_event_got_ip_t *)data;
    snprintf(s_ip, sizeof(s_ip), IPSTR, IP2STR(&ev->ip_info.ip));
    s_state = CS_NET_ONLINE;
    s_reconnect = 0;
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) scpy(s_ssid, sizeof(s_ssid), (const char *)ap.ssid);
    ESP_LOGI(TAG, "已联网: %s  IP=%s", s_ssid, s_ip);
    start_sntp();
}

static esp_err_t wifi_bring_up(void)
{
    if (s_wifi_started) return ESP_OK;

    esp_err_t err = demo_radio_nvs_prepare();
    if (err != ESP_OK) return err;
    err = demo_radio_network_prepare();
    if (err != ESP_OK) return err;

    if (!s_sta_netif) {
        s_sta_netif = esp_netif_create_default_wifi_sta();
        if (!s_sta_netif) return ESP_ERR_NO_MEM;
    }

    if (!s_wifi_ready) {
        wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
        err = esp_wifi_init(&cfg);
        if (err == ESP_ERR_INVALID_STATE) {
            // 别的页面(如 Wi-Fi demo)已经初始化过,直接复用其驱动。
            ESP_LOGW(TAG, "Wi-Fi 驱动已被初始化,复用");
            err = ESP_OK;
        }
        if (err != ESP_OK) return err;
        s_wifi_ready = true;
    }

    if (!s_h_wifi) {
        esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL, &s_h_wifi);
        esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_ip_event, NULL, &s_h_ip);
    }

    // 凭证持久化到 NVS:下次开机不用重新输密码。
    err = esp_wifi_set_storage(WIFI_STORAGE_FLASH);
    if (err != ESP_OK) ESP_LOGW(TAG, "set_storage: %s", esp_err_to_name(err));

    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        // 可能已被设成 STA,忽略。
        ESP_LOGW(TAG, "set_mode: %s", esp_err_to_name(err));
    }
    err = esp_wifi_start();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;
    s_wifi_started = true;

    // 读一下上次保存的 SSID,菜单里可以标注"上次连接"。
    wifi_config_t wc;
    memset(&wc, 0, sizeof(wc));
    if (esp_wifi_get_config(WIFI_IF_STA, &wc) == ESP_OK)
        scpy(s_prev_ssid, sizeof(s_prev_ssid), (const char *)wc.sta.ssid);

    return ESP_OK;
}

esp_err_t cs_net_init(void)
{
    if (s_state != CS_NET_OFF) return ESP_OK;

    esp_err_t err = wifi_bring_up();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Wi-Fi 启动失败: %s", esp_err_to_name(err));
        s_state = CS_NET_FAILED;
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Wi-Fi init failed");
        return err;
    }
    s_state = CS_NET_READY;

    // 已有凭证就直接连,省得每次手动配网。
    if (s_prev_ssid[0]) {
        cs_net_autoconnect();
    } else {
        cs_net_scan();
    }
    return ESP_OK;
}

void cs_net_shutdown(void)
{
    // 刻意不 deinit Wi-Fi:保留连接状态,退出页面再进来可秒开。
    // 只有需要彻底关射频时才调用(例如低功耗场景)。
}

cs_net_state_t cs_net_state(void)        { return s_state; }
void           cs_net_state_reset(void)  { if (s_state == CS_NET_FAILED) s_state = CS_NET_READY; s_scan_msg[0] = 0; s_conn_err[0] = 0; s_conn_watch = 0; }
bool           cs_net_online(void)       { return s_state == CS_NET_ONLINE; }
const char    *cs_net_ip(void)           { return s_ip; }
const char    *cs_net_ssid(void)         { return s_ssid; }
const char    *cs_net_conn_err(void)     { return s_conn_err; }
const char    *cs_net_ap_prev_ssid(void) { return s_prev_ssid; }

// 扫描任务:在独立任务里用阻塞式 esp_wifi_scan_start()。
// 旧实现是"发起异步扫描 + 等 WIFI_EVENT_SCAN_DONE 事件",一旦事件没来(或事件里
// 取结果失败),界面就永远停在"正在扫描"。阻塞式调用有明确的时间上限,而且结果
// 由发起扫描的人自己取,不存在"谁先取到"的竞争。
static void scan_task(void *arg)
{
    (void)arg;

    // STA 正在"连接中"时 scan_start 会直接返回 ESP_ERR_WIFI_STATE,先松开它;
    // 这期间产生的 DISCONNECTED 事件会被 s_scan_busy 挡掉,不会触发自动重连。
    // 已经连上(ONLINE)的情况不动连接:边连边扫是允许的,没必要把用户的网断掉。
    if (s_state == CS_NET_CONNECTING) {
        esp_wifi_disconnect();
        vTaskDelay(pdMS_TO_TICKS(150));
    }

    wifi_scan_config_t cfg = { 0 };
    cfg.scan_type = WIFI_SCAN_TYPE_ACTIVE;
    cfg.show_hidden = false;
    cfg.scan_time.active.min = CS_SCAN_MIN_MS;
    cfg.scan_time.active.max = CS_SCAN_MAX_MS;

    esp_err_t err = esp_wifi_scan_start(&cfg, true);   // true = 阻塞到本轮扫完
    uint16_t  total = 0;
    uint16_t  got   = 0;

    if (err == ESP_OK) err = esp_wifi_scan_get_ap_num(&total);
    if (err == ESP_OK) {
        // 先看总数再取:buffer 小于总数时直接取会报 NOT_ENOUGH_MEMORY。
        uint16_t cap = CS_AP_MAX;
        esp_err_t g = esp_wifi_scan_get_ap_records(&cap, s_aps);
        if (g != ESP_OK) {
            err = g;
        } else {
            // 双保险:*number 的语义在不同 IDF 版本里是"写入条数"或"发现总数",
            // 统一夹到数组容量以内,绝不让后续按下标访问越界。
            got = (cap > CS_AP_MAX) ? CS_AP_MAX : cap;
            if (got > total) got = total;
        }
    }

    if (err == ESP_OK) {
        s_ap_count = got;
        // 扫完后回到扫描前的连接状态:本来就联网的别因为"扫了一下"变成未联网。
        s_state = s_scan_keep_online ? CS_NET_ONLINE : CS_NET_APLIST;
        s_scan_msg[0] = 0;
        ESP_LOGI(TAG, "扫描完成: 取到 %u 个(共发现 %u 个)", (unsigned)got, (unsigned)total);
    } else {
        s_ap_count = 0;
        s_state = s_scan_keep_online ? CS_NET_ONLINE : CS_NET_FAILED;
        scpy(s_scan_msg, sizeof(s_scan_msg), "扫描失败,按确定重试");
        ESP_LOGE(TAG, "扫描失败: %s", esp_err_to_name(err));
    }

    s_scan_busy = false;
    vTaskDelete(NULL);
}

void cs_net_scan(void)
{
    if (s_scan_busy) return;                 // 已经有一轮在跑,忽略重复请求
    if (!s_wifi_started) {
        if (wifi_bring_up() != ESP_OK) {
            s_state = CS_NET_FAILED;
            scpy(s_scan_msg, sizeof(s_scan_msg), "Wi-Fi 启动失败");
            return;
        }
    }

    s_scan_keep_online = (s_state == CS_NET_ONLINE);
    s_scan_busy = true;
    s_scan_watch = 0;
    s_ap_count = 0;
    s_scan_msg[0] = 0;
    s_state = CS_NET_SCANNING;
    if (xTaskCreate(scan_task, "cs_scan", 4096, NULL, 6, NULL) != pdPASS) {
        s_scan_busy = false;
        s_state = CS_NET_FAILED;
        scpy(s_scan_msg, sizeof(s_scan_msg), "扫描任务创建失败");
    }
}

bool        cs_net_scan_busy(void) { return s_scan_busy; }
const char *cs_net_scan_msg(void)  { return s_scan_msg; }

void cs_net_scan_watchdog(void)
{
    // 连接兜底:正常连接十几秒内必有结果(GOT_IP 或 DISCONNECTED 事件),
    // 卡在 CONNECTING 超过 20 秒说明底层没动静,强制判失败,界面给出出口。
    if (s_state == CS_NET_CONNECTING) {
        if (++s_conn_watch < 100) return;        // 200ms × 100 = 20s
        s_conn_watch = 0;
        s_state = CS_NET_FAILED;
        if (!s_conn_err[0]) scpy(s_conn_err, sizeof(s_conn_err), "连接超时,请重试");
        // 把底层还在跑的连接尝试掐掉,免得它几秒后又把状态翻回来
        s_deliberate = true;
        esp_wifi_disconnect();
        ESP_LOGW(TAG, "连接超时,强制判失败");
        return;
    }
    s_conn_watch = 0;

    if (s_state != CS_NET_SCANNING) { s_scan_watch = 0; return; }
    if (++s_scan_watch < 75) return;         // 200ms × 75 = 15s
    s_scan_watch = 0;
    ESP_LOGW(TAG, "扫描超时,强制收尾");
    esp_wifi_scan_stop();                    // 若任务还阻塞在 scan_start 上,这会让它返回
    s_scan_busy = false;
    s_ap_count = 0;
    s_state = s_scan_keep_online ? CS_NET_ONLINE : CS_NET_FAILED;
    scpy(s_scan_msg, sizeof(s_scan_msg), "扫描超时,按确定重试");
}

int         cs_net_ap_count(void)     { return s_ap_count; }
const char *cs_net_ap_ssid(int idx)   { return (idx >= 0 && idx < (int)s_ap_count) ? (const char *)s_aps[idx].ssid : ""; }
int         cs_net_ap_rssi(int idx)   { return (idx >= 0 && idx < (int)s_ap_count) ? s_aps[idx].rssi : -99; }
bool        cs_net_ap_secure(int idx) { return (idx >= 0 && idx < (int)s_ap_count) && s_aps[idx].authmode != WIFI_AUTH_OPEN; }

void cs_net_connect(const char *ssid, const char *password)
{
    if (!ssid || !ssid[0]) return;
    if (wifi_bring_up() != ESP_OK) { s_state = CS_NET_FAILED; return; }

    s_conn_err[0] = 0;
    s_conn_watch = 0;
    s_reconnect = 0;

    wifi_config_t wc;
    memset(&wc, 0, sizeof(wc));
    scpy((char *)wc.sta.ssid, sizeof(wc.sta.ssid), ssid);
    if (password) scpy((char *)wc.sta.password, sizeof(wc.sta.password), password);
    wc.sta.threshold.authmode = (password && password[0]) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    // 快扫 + 按信号排序:连接目标明确(用户刚从列表里选的),没必要全信道兜圈子;
    // PMF 显式给出 capable=true:新一点的 Wi-Fi 6 路由器(尤其是 WPA3 混合模式)
    // 没这一项会握手失败,表现就是"密码明明是对的却连不上"。
    wc.sta.scan_method = WIFI_FAST_SCAN;
    wc.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
    wc.sta.pmf_cfg.capable = true;
    wc.sta.pmf_cfg.required = false;

    esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &wc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "set_config: %s", esp_err_to_name(err));
        s_state = CS_NET_FAILED;
        scpy(s_conn_err, sizeof(s_conn_err), "网络配置失败");
        return;
    }
    scpy(s_ssid, sizeof(s_ssid), ssid);
    scpy(s_prev_ssid, sizeof(s_prev_ssid), ssid);
    // 先改状态再断开:s_deliberate 让这次 disconnect 的 DISCONNECTED 事件被
    // 事件处理器忽略(不算失败、不抢跑重试),紧跟的 esp_wifi_connect() 按新配置发起连接。
    s_state = CS_NET_CONNECTING;
    s_deliberate = true;
    esp_wifi_disconnect();
    esp_wifi_connect();
    ESP_LOGI(TAG, "正在连接 %s", ssid);
}

void cs_net_autoconnect(void)
{
    if (!s_wifi_started) return;
    wifi_config_t wc;
    memset(&wc, 0, sizeof(wc));
    if (esp_wifi_get_config(WIFI_IF_STA, &wc) != ESP_OK || !wc.sta.ssid[0]) return;
    scpy(s_ssid, sizeof(s_ssid), (const char *)wc.sta.ssid);
    s_reconnect = 0;
    s_state = CS_NET_CONNECTING;
    esp_wifi_connect();
    ESP_LOGI(TAG, "用已保存凭证连接 %s", s_ssid);
}

void cs_net_forget(void)
{
    wifi_config_t wc;
    memset(&wc, 0, sizeof(wc));
    esp_wifi_set_config(WIFI_IF_STA, &wc);
    s_prev_ssid[0] = 0;
    s_ssid[0] = 0;
    s_ip[0] = 0;
    if (s_wifi_started) esp_wifi_disconnect();
    s_state = CS_NET_READY;
}

// ---------------------------------------------------------------------------
// 扫码配网:设备起热点 FoloToy-CS-XXXX(WPA2,密码 12345678),屏幕显示二维码,
// 手机相机扫码(或手动连热点)后,浏览器打开 http://192.168.4.1 选网输密码。
// 热点工作在 APSTA 模式,STA 原有连接不受影响;配网页可反复提交,直到连上。
// ---------------------------------------------------------------------------
static bool           s_qr_active;
static char           s_qr_ssid[24];
static httpd_handle_t s_httpd;
static const char    *QR_PASS = "12345678";

bool        cs_net_qr_active(void) { return s_qr_active; }
const char *cs_net_qr_ssid(void)   { return s_qr_ssid; }
const char *cs_net_qr_pass(void)   { return QR_PASS; }
const char *cs_net_qr_url(void)    { return "http://192.168.4.1"; }

// 往 dst[n] 追加字符串,返回新的 n(自带截断,不触发 -Wformat-truncation)
static int jput(char *dst, int cap, int n, const char *s)
{
    if (!s) s = "";
    while (*s && n < cap - 1) dst[n++] = *s++;
    dst[n] = 0;
    return n;
}

// SSID 进 JSON 前要转义双引号与反斜杠
static void jesc(const char *src, char *dst, size_t cap)
{
    size_t n = 0;
    for (; *src && n + 2 < cap; src++) {
        if (*src == '"' || *src == '\\') dst[n++] = '\\';
        dst[n++] = *src;
    }
    dst[n] = 0;
}

// "a=1&b=2" 里取 key 的值并做 URL 解码(+ 和 %XX)
static void url_decode(char *s)
{
    char *w = s;
    while (*s) {
        if (*s == '%' && s[1] && s[2]) {
            char hx[3] = { s[1], s[2], 0 };
            *w++ = (char)strtol(hx, NULL, 16);
            s += 3;
        } else if (*s == '+') {
            *w++ = ' '; s++;
        } else {
            *w++ = *s++;
        }
    }
    *w = 0;
}

static bool form_field(const char *body, const char *key, char *out, size_t cap)
{
    size_t kl = strlen(key);
    const char *p = body;
    while (p && *p) {
        if (strncmp(p, key, kl) == 0 && p[kl] == '=') {
            const char *e = strchr(p + kl + 1, '&');
            size_t n = e ? (size_t)(e - p - kl - 1) : strlen(p + kl + 1);
            if (n >= cap) n = cap - 1;
            memcpy(out, p + kl + 1, n);
            out[n] = 0;
            url_decode(out);
            return true;
        }
        p = strchr(p, '&');
        if (p) p++;
    }
    return false;
}

// 配网页(内嵌 HTML,全部用单引号/无引号属性,方便放进 C 字符串)
static const char PAGE_HTML[] =
"<!doctype html><html><head><meta charset=utf-8>"
"<meta name=viewport content=width=device-width,initial-scale=1>"
"<title>FoloToy 配网</title></head>"
"<body style='font-family:sans-serif;max-width:420px;margin:24px auto'>"
"<h3>CS 看板 Wi-Fi 配网</h3>"
"<label>无线网络<br><input id=ssid list=apl style=width:100%;height:36px></label>"
"<datalist id=apl></datalist>"
"<label>密码<br><input id=pwd type=password style=width:100%;height:36px></label>"
"<p><button onclick=go() style=width:100%;height:44px;font-size:18px>连接</button>"
"<button onclick=rescan() style=width:100%;height:36px>重新扫描</button></p>"
"<p id=msg>正在读取网络列表...</p>"
"<script>"
"function ld(){fetch('/aplist').then(r=>r.json()).then(a=>{"
"apl.innerHTML='';a.forEach(function(x){var o=document.createElement('option');"
"o.value=x[0];o.textContent=x[0]+' ('+x[1]+'dBm'+(x[2]?',加密':'')+')';apl.appendChild(o);});"
"msg.textContent='请选择网络并输入密码';});}"
"function rescan(){msg.textContent='扫描中...';fetch('/scan').then(function(){"
"setTimeout(ld,4000);});}"
"function go(){msg.textContent='发送中...';"
"fetch('/connect',{method:'POST',"
"headers:{'Content-Type':'application/x-www-form-urlencoded'},"
"body:'ssid='+encodeURIComponent(ssid.value)+'&pwd='+encodeURIComponent(pwd.value)})"
".then(function(){poll();});}"
"function poll(){fetch('/status').then(r=>r.json()).then(function(j){"
"msg.textContent=j.cn;"
"if(j.state=='online')msg.textContent='已连上 '+j.ssid+' ,可以关闭此页';"
"else setTimeout(poll,2000);});}"
"ld();"
"</script></body></html>";

static esp_err_t h_root(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    return httpd_resp_send(req, PAGE_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t h_aplist(httpd_req_t *req)
{
    static char jb[1024];
    int n = 0;
    n = jput(jb, sizeof(jb), n, "[");
    for (int i = 0; i < (int)s_ap_count; i++) {
        char esc[70];
        jesc((const char *)s_aps[i].ssid, esc, sizeof(esc));
        if (n > (int)sizeof(jb) - 90) break;
        char num[24];
        snprintf(num, sizeof(num), "%d,%d", s_aps[i].rssi,
                 s_aps[i].authmode != WIFI_AUTH_OPEN ? 1 : 0);
        if (i) n = jput(jb, sizeof(jb), n, ",");
        n = jput(jb, sizeof(jb), n, "[\"");
        n = jput(jb, sizeof(jb), n, esc);
        n = jput(jb, sizeof(jb), n, "\",");
        n = jput(jb, sizeof(jb), n, num);
        n = jput(jb, sizeof(jb), n, "]");
    }
    n = jput(jb, sizeof(jb), n, "]");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, jb, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t h_scan(httpd_req_t *req)
{
    // CONNECTING 时不扫(会把正在发起的连接断掉),其余状态都允许重扫
    if (!s_scan_busy && s_state != CS_NET_SCANNING && s_state != CS_NET_CONNECTING)
        cs_net_scan();
    return httpd_resp_send(req, "ok", HTTPD_RESP_USE_STRLEN);
}

static esp_err_t h_status(httpd_req_t *req)
{
    static char jb[192];
    const char *cn = "";
    switch (s_state) {
    case CS_NET_READY:      cn = "等待选择网络";       break;
    case CS_NET_SCANNING:   cn = "正在扫描附近网络..."; break;
    case CS_NET_APLIST:     cn = "请选择网络";         break;
    case CS_NET_CONNECTING: cn = "正在连接,请稍候...";  break;
    case CS_NET_ONLINE:     cn = "已连上网络";         break;
    case CS_NET_FAILED:     cn = s_conn_err[0] ? s_conn_err : "连接失败,可在网页重试"; break;
    default:                cn = "等待手机扫码连接热点"; break;
    }
    const char *st = "off";
    if (s_state == CS_NET_SCANNING)        st = "scanning";
    else if (s_state == CS_NET_CONNECTING) st = "connecting";
    else if (s_state == CS_NET_ONLINE)     st = "online";
    else if (s_state == CS_NET_FAILED)     st = "failed";

    char esc[70];
    jesc(s_ssid, esc, sizeof(esc));
    int n = 0;
    n = jput(jb, sizeof(jb), n, "{\"state\":\"");
    n = jput(jb, sizeof(jb), n, st);
    n = jput(jb, sizeof(jb), n, "\",\"cn\":\"");
    n = jput(jb, sizeof(jb), n, cn);
    n = jput(jb, sizeof(jb), n, "\",\"ssid\":\"");
    n = jput(jb, sizeof(jb), n, esc);
    n = jput(jb, sizeof(jb), n, "\",\"ip\":\"");
    n = jput(jb, sizeof(jb), n, s_ip);
    n = jput(jb, sizeof(jb), n, "\"}");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, jb, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t h_connect(httpd_req_t *req)
{
    if (req->content_len <= 0 || req->content_len > 200)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "参数长度不对");
    char body[208];
    int got = httpd_req_recv(req, body, req->content_len);
    if (got <= 0) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "读取失败");
    body[got] = 0;

    char ssid[33], pwd[65];
    if (!form_field(body, "ssid", ssid, sizeof(ssid)) || !ssid[0])
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "缺少网络名称");
    if (!form_field(body, "pwd", pwd, sizeof(pwd))) pwd[0] = 0;

    cs_net_connect(ssid, pwd);
    return httpd_resp_send(req, "ok", HTTPD_RESP_USE_STRLEN);
}

bool cs_net_qr_start(void)
{
    if (s_qr_active) return true;
    if (!s_wifi_started && wifi_bring_up() != ESP_OK) return false;

    // AP netif 只建一次(与 STA netif 并存)
    static bool s_ap_netif;
    if (!s_ap_netif) {
        if (!esp_netif_create_default_wifi_ap()) return false;
        s_ap_netif = true;
    }
    if (esp_wifi_set_mode(WIFI_MODE_APSTA) != ESP_OK) return false;

    // 热点名带 MAC 尾巴,多台设备互不冲突
    uint8_t mac[6] = { 0 };
    esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    snprintf(s_qr_ssid, sizeof(s_qr_ssid), "FoloToy-CS-%02X%02X",
             mac[4] % 256, mac[5] % 256);

    wifi_config_t ap;
    memset(&ap, 0, sizeof(ap));
    scpy((char *)ap.ap.ssid, sizeof(ap.ap.ssid), s_qr_ssid);
    ap.ap.ssid_len = (uint8_t)strlen(s_qr_ssid);
    scpy((char *)ap.ap.password, sizeof(ap.ap.password), QR_PASS);
    ap.ap.channel = 6;
    ap.ap.max_connection = 2;
    ap.ap.authmode = WIFI_AUTH_WPA2_PSK;
    if (esp_wifi_set_config(WIFI_IF_AP, &ap) != ESP_OK) return false;

    if (!s_httpd) {
        httpd_config_t hc = HTTPD_DEFAULT_CONFIG();
        hc.stack_size = 6144;
        hc.lru_purge_enable = true;
        if (httpd_start(&s_httpd, &hc) != ESP_OK) { s_httpd = NULL; return false; }
        static const httpd_uri_t URIS[] = {
            { "/",       HTTP_GET,  h_root,    NULL },
            { "/aplist", HTTP_GET,  h_aplist,  NULL },
            { "/scan",   HTTP_GET,  h_scan,    NULL },
            { "/status", HTTP_GET,  h_status,  NULL },
            { "/connect",HTTP_POST, h_connect, NULL },
        };
        for (size_t i = 0; i < sizeof(URIS) / sizeof(URIS[0]); i++)
            httpd_register_uri_handler(s_httpd, &URIS[i]);
    }

    s_qr_active = true;
    ESP_LOGI(TAG, "配网热点已开启: %s  密码 %s  地址 %s",
             s_qr_ssid, QR_PASS, cs_net_qr_url());
    return true;
}

void cs_net_qr_stop(void)
{
    if (!s_qr_active && !s_httpd) return;
    if (s_httpd) { httpd_stop(s_httpd); s_httpd = NULL; }
    // 回到纯 STA 模式。若切模式把原连接甩掉了,这里负责重新发起连接
    // (事件里的 DISCONNECTED 已被 s_deliberate 挡掉,不会走重试计数)。
    s_deliberate = true;
    esp_wifi_set_mode(WIFI_MODE_STA);
    if (s_state == CS_NET_ONLINE || s_state == CS_NET_CONNECTING) {
        s_deliberate = false;      // 接下来若真断开,按正常失败/重试处理
        esp_wifi_connect();
    }
    s_qr_active = false;
    ESP_LOGI(TAG, "配网热点已关闭");
}

// ---------------------------------------------------------------------------
// NVS 句柄:优先用 cardid 之后的 csdata 资源分区(64KB),失败回退默认 nvs。
// 这样 12KB 的 JSON 缓存不再挤占只有 24KB 的 nvs(那里还要放 Wi-Fi 凭证)。
// ---------------------------------------------------------------------------
static bool s_csdata_tried;
static bool s_csdata_ok;

static bool csdata_ready(void)
{
    if (s_csdata_tried) return s_csdata_ok;
    s_csdata_tried = true;

    // 先确保 NVS 子系统本身初始化(幂等),再初始化资源分区。
    if (demo_radio_nvs_prepare() != ESP_OK) return false;

    esp_err_t err = nvs_flash_init_partition(CS_NVS_PART);
    if (err == ESP_OK) {
        s_csdata_ok = true;
        ESP_LOGI(TAG, "数据缓存分区 %s 就绪", CS_NVS_PART);
    } else {
        ESP_LOGW(TAG, "资源分区 %s 不可用(%s),回退到默认 nvs",
                 CS_NVS_PART, esp_err_to_name(err));
    }
    return s_csdata_ok;
}

static esp_err_t kv_open(const char *ns, nvs_open_mode_t mode, nvs_handle_t *out)
{
    if (csdata_ready() &&
        nvs_open_from_partition(CS_NVS_PART, ns, mode, out) == ESP_OK) {
        return ESP_OK;
    }
    return nvs_open(ns, mode, out);
}

// ---------------------------------------------------------------------------
// 数据源 URL(可存 NVS 覆盖,便于不改固件换源)
// ---------------------------------------------------------------------------
static char s_url[160];

const char *cs_data_url(void)
{
    if (s_url[0]) return s_url;
    nvs_handle_t h;
    if (kv_open(CS_NVS_NS, NVS_READONLY, &h) == ESP_OK) {
        size_t len = sizeof(s_url);
        if (nvs_get_str(h, CS_NVS_URL_KEY, s_url, &len) != ESP_OK) s_url[0] = 0;
        nvs_close(h);
    }
    if (!s_url[0]) scpy(s_url, sizeof(s_url), CS_DEFAULT_URL);
    return s_url;
}

void cs_data_set_url(const char *url)
{
    if (!url || !url[0]) return;
    scpy(s_url, sizeof(s_url), url);
    nvs_handle_t h;
    if (kv_open(CS_NVS_NS, NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_str(h, CS_NVS_URL_KEY, s_url);
        nvs_commit(h);
        nvs_close(h);
    }
    ESP_LOGI(TAG, "数据源已更新: %s", s_url);
}

// ---------------------------------------------------------------------------
// JSON 解析
// ---------------------------------------------------------------------------
static void jstr(cJSON *o, const char *key, char *dst, size_t cap, const char *def)
{
    cJSON *j = o ? cJSON_GetObjectItem(o, key) : NULL;
    scpy(dst, cap, (j && cJSON_IsString(j)) ? j->valuestring : def);
}

static uint32_t jcolor(cJSON *o, const char *key, uint32_t def)
{
    cJSON *j = o ? cJSON_GetObjectItem(o, key) : NULL;
    if (!j || !cJSON_IsString(j)) return def;
    const char *s = j->valuestring;
    if (*s == '#') s++;
    unsigned v = (unsigned)strtoul(s, NULL, 16);
    return v ? (v & 0xFFFFFFu) : def;
}

static int jint(cJSON *o, const char *key, int def)
{
    cJSON *j = o ? cJSON_GetObjectItem(o, key) : NULL;
    return cJSON_IsNumber(j) ? j->valueint : def;
}

static bool parse_matches(const char *json, cs_data_t *out)
{
    cJSON *root = cJSON_Parse(json);
    if (!root) return false;

    memset(out, 0, sizeof(*out));
    jstr(root, "updated", out->updated, sizeof(out->updated), "net");

    cJSON *arr = cJSON_GetObjectItem(root, "matches");
    if (!cJSON_IsArray(arr)) { cJSON_Delete(root); return false; }

    int n = cJSON_GetArraySize(arr);
    if (n > CS_MAX_MATCHES) n = CS_MAX_MATCHES;

    for (int i = 0; i < n; i++) {
        cJSON *mi = cJSON_GetArrayItem(arr, i);
        if (!cJSON_IsObject(mi)) continue;

        cs_match_t *m = &out->m[out->count];
        jstr(mi, "event",  m->event,  sizeof(m->event),  "CS2 赛事");
        jstr(mi, "stage",  m->stage,  sizeof(m->stage),  "");
        jstr(mi, "date",   m->date,   sizeof(m->date),   "");
        jstr(mi, "time",   m->time,   sizeof(m->time),   "");
        jstr(mi, "bo",     m->bo,     sizeof(m->bo),     "BO3");
        jstr(mi, "status", m->status, sizeof(m->status), CS_ST_UPCOMING);

        cJSON *t1 = cJSON_GetObjectItem(mi, "team1");
        jstr(t1, "name",  m->t1_name,  sizeof(m->t1_name),  "TBD");
        jstr(t1, "short", m->t1_short, sizeof(m->t1_short), "");
        jstr(t1, "logo",  m->t1_logo,  sizeof(m->t1_logo),  "");
        m->t1_color = jcolor(t1, "color", 0xE43B2F);

        cJSON *t2 = cJSON_GetObjectItem(mi, "team2");
        jstr(t2, "name",  m->t2_name,  sizeof(m->t2_name),  "TBD");
        jstr(t2, "short", m->t2_short, sizeof(m->t2_short), "");
        jstr(t2, "logo",  m->t2_logo,  sizeof(m->t2_logo),  "");
        m->t2_color = jcolor(t2, "color", 0x2AA3EF);

        m->score1 = jint(mi, "score1", 0);
        m->score2 = jint(mi, "score2", 0);

        cJSON *maps = cJSON_GetObjectItem(mi, "maps");
        if (cJSON_IsArray(maps)) {
            int mn = cJSON_GetArraySize(maps);
            if (mn > CS_MAX_MAPS) mn = CS_MAX_MAPS;
            for (int k = 0; k < mn; k++) {
                cJSON *km = cJSON_GetArrayItem(maps, k);
                if (!cJSON_IsObject(km)) continue;
                cs_map_t *mp = &m->maps[m->map_count];
                jstr(km, "name", mp->name, sizeof(mp->name), "Map");
                jstr(km, "cn",   mp->cn,   sizeof(mp->cn),   "");
                mp->s1 = jint(km, "s1", 0);
                mp->s2 = jint(km, "s2", 0);
                mp->winner = jint(km, "winner", mp->s1 > mp->s2 ? 1 : (mp->s2 > mp->s1 ? 2 : 0));
                m->map_count++;
            }
        }
        out->count++;
    }

    cJSON_Delete(root);
    return out->count > 0;
}

// ---------------------------------------------------------------------------
// NVS 缓存
// ---------------------------------------------------------------------------
static esp_err_t cache_save(const char *json)
{
    nvs_handle_t h;
    esp_err_t err = kv_open(CS_NVS_NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_set_str(h, CS_NVS_JSON_KEY, json);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}

static esp_err_t cache_load(char *out, size_t cap)
{
    nvs_handle_t h;
    esp_err_t err = kv_open(CS_NVS_NS, NVS_READONLY, &h);
    if (err != ESP_OK) return err;
    size_t len = cap;
    err = nvs_get_str(h, CS_NVS_JSON_KEY, out, &len);
    nvs_close(h);
    return err;
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
typedef struct {
    char *buf;
    int   len;
    int   cap;
} http_sink_t;

static esp_err_t http_on_data(esp_http_client_event_t *e)
{
    http_sink_t *s = (http_sink_t *)e->user_data;
    if (e->event_id != HTTP_EVENT_ON_DATA || !s || e->data_len <= 0) return ESP_OK;
    int room = s->cap - s->len - 1;
    if (room > 0) {
        int cp = e->data_len < room ? e->data_len : room;
        memcpy(s->buf + s->len, e->data, (size_t)cp);
        s->len += cp;
        s->buf[s->len] = 0;
    }
    return ESP_OK;
}

static esp_err_t http_get(const char *url, char *buf, int cap, int *out_len)
{
    http_sink_t sink = { buf, 0, cap };
    buf[0] = 0;

    esp_http_client_config_t cfg = {
        .url = url,
        .event_handler = http_on_data,
        .user_data = &sink,
        .timeout_ms = 20000,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .buffer_size = 2048,
        .buffer_size_tx = 1024,
    };
    esp_http_client_handle_t cli = esp_http_client_init(&cfg);
    if (!cli) return ESP_FAIL;

    esp_err_t err = esp_http_client_perform(cli);
    int code = esp_http_client_get_status_code(cli);
    esp_http_client_cleanup(cli);

    if (err != ESP_OK) return err;
    if (code != 200) return ESP_ERR_INVALID_RESPONSE;
    if (sink.len <= 0) return ESP_ERR_INVALID_SIZE;
    if (out_len) *out_len = sink.len;
    return ESP_OK;
}

// ---------------------------------------------------------------------------
// 数据访问
// ---------------------------------------------------------------------------
const cs_data_t *cs_data(void)          { return &s_data; }
bool             cs_data_is_from_net(void) { return s_from_net; }
cs_fetch_state_t cs_data_fetch_state(void) { return s_fetch_state; }
const char      *cs_data_fetch_msg(void)   { return s_fetch_msg; }
void             cs_data_fetch_reset(void) { if (s_fetch_state != CS_FETCH_RUNNING) s_fetch_state = CS_FETCH_IDLE; }

int cs_data_filter(const char *st, int *idx_out, int max)
{
    int n = 0;
    if (!idx_out || max <= 0) return 0;
    for (int i = 0; i < s_data.count && n < max; i++) {
        if (!st || strcmp(s_data.m[i].status, st) == 0) idx_out[n++] = i;
    }
    return n;
}

void cs_data_use_builtin(void)
{
    s_data = k_builtin;
    s_from_net = false;
    scpy(s_fetch_msg, sizeof(s_fetch_msg), "内置示例数据");
}

esp_err_t cs_data_load_cache(void)
{
    // 用堆而不是静态 BSS:16 场比赛的 JSON 已经接近 10KB,没必要常驻占 RAM。
    char *buf = (char *)malloc(CS_CACHE_MAX);
    if (!buf) {
        ESP_LOGW(TAG, "缓存缓冲分配失败,用内置示例");
        cs_data_use_builtin();
        return ESP_ERR_NO_MEM;
    }
    esp_err_t err = cache_load(buf, CS_CACHE_MAX);
    if (err != ESP_OK) {
        free(buf);
        ESP_LOGW(TAG, "无缓存(%s),用内置示例", esp_err_to_name(err));
        cs_data_use_builtin();
        return err;
    }
    bool ok = parse_matches(buf, &s_data);
    free(buf);
    if (!ok) {
        ESP_LOGW(TAG, "缓存解析失败,用内置示例");
        cs_data_use_builtin();
        return ESP_ERR_INVALID_RESPONSE;
    }
    s_from_net = false;
    scpy(s_fetch_msg, sizeof(s_fetch_msg), "已载入本地缓存");
    ESP_LOGI(TAG, "已载入缓存: %d 场", s_data.count);
    return ESP_OK;
}

static void fetch_task(void *arg)
{
    (void)arg;
    char *buf = (char *)malloc(CS_HTTP_BUF_MAX);
    if (!buf) {
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "内存不足");
        s_fetch_state = CS_FETCH_FAIL;
        vTaskDelete(NULL);
        return;
    }

    int len = 0;
    const char *url = cs_data_url();
    ESP_LOGI(TAG, "拉取 %s", url);
    esp_err_t err = http_get(url, buf, CS_HTTP_BUF_MAX, &len);

    if (err == ESP_OK) {
        cs_data_t tmp;
        if (parse_matches(buf, &tmp)) {
            s_data = tmp;
            s_from_net = true;
            if (len < CS_CACHE_MAX) {
                esp_err_t ce = cache_save(buf);
                if (ce != ESP_OK) ESP_LOGW(TAG, "缓存写入失败: %s", esp_err_to_name(ce));
            }
            snprintf(s_fetch_msg, sizeof(s_fetch_msg), "已更新 %d 场比赛", s_data.count % 1000);
            s_fetch_state = CS_FETCH_OK;
            ESP_LOGI(TAG, "数据已更新: %d 场, %d 字节", s_data.count, len);
        } else {
            scpy(s_fetch_msg, sizeof(s_fetch_msg), "数据解析失败");
            s_fetch_state = CS_FETCH_FAIL;
        }
    } else {
        snprintf(s_fetch_msg, sizeof(s_fetch_msg), "网络错误: %s", esp_err_to_name(err));
        s_fetch_state = CS_FETCH_FAIL;
        ESP_LOGE(TAG, "拉取失败: %s", esp_err_to_name(err));
    }

    free(buf);
    vTaskDelete(NULL);
}

void cs_data_refresh_async(void)
{
    if (s_fetch_state == CS_FETCH_RUNNING) return;
    if (!cs_net_online()) {
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Wi-Fi 未连接");
        s_fetch_state = CS_FETCH_FAIL;
        return;
    }
    s_fetch_state = CS_FETCH_RUNNING;
    scpy(s_fetch_msg, sizeof(s_fetch_msg), "正在拉取数据...");
    if (xTaskCreate(fetch_task, "cs_fetch", 8192, NULL, 5, NULL) != pdPASS) {
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "任务创建失败");
        s_fetch_state = CS_FETCH_FAIL;
    }
}

// ---------------------------------------------------------------------------
// 时间(状态栏 HH:MM,北京时间)
// ---------------------------------------------------------------------------
void cs_time_hhmm(char *out, int n)
{
    if (!out || n <= 0) return;
    time_t now = time(NULL);
    if (now < 1600000000) { snprintf(out, (size_t)n, "--:--"); return; }
    time_t bj = now + 8 * 3600;
    struct tm tmv;
    gmtime_r(&bj, &tmv);
    snprintf(out, (size_t)n, "%02d:%02d", tmv.tm_hour % 100, tmv.tm_min % 100);
}
