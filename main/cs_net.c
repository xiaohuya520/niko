// main/cs_net.c —— CS 赛事看板的「联网 + 数据」层实现。
//
// 设计取舍:
//  - 本文件完全不碰 LVGL,只做 Wi-Fi / HTTP / JSON / NVS / SNTP,UI 侧轮询状态;
//  - 下载缓冲与 JSON 缓存都设成小上限(6KB / 4KB),因为 ESP32-C3 无 PSRAM,
//    NVS 分区也只有 24KB,必须留余量给 Wi-Fi 凭证与 PHY 校准数据;
//  - 数据源默认走 jsDelivr CDN(国内可达),指向用户仓库里的 JSON,
//    这样"改数据=改仓库里的 JSON",不需要重新编译固件。
#include "cs_net.h"
#include "demo_radio.h"

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_sntp.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"

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

#define CS_HTTP_BUF_MAX 6144     // 单次下载上限
#define CS_CACHE_MAX    4096     // 写进 NVS 的 JSON 上限
#define CS_AP_MAX       12

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
static cs_net_state_t   s_state;
static cs_fetch_state_t s_fetch_state;
static char             s_fetch_msg[48];
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
// 内置示例数据(断网/首次开机兜底,结构与线上 JSON 一致)
// ---------------------------------------------------------------------------
static const cs_data_t k_builtin = {
    .updated = "built-in",
    .count = 4,
    .m = {
        {
            .event = "BLAST Open Fall", .date = "08/31", .bo = "BO3", .status = "finished",
            .t1_name = "G2", .t1_short = "G2", .t1_color = 0xE4AE39,
            .t2_name = "Aurora", .t2_short = "AUR", .t2_color = 0x2AA3EF,
            .score1 = 2, .score2 = 1, .map_count = 3,
            .maps = { { "Anubis", 7, 13 }, { "Inferno", 19, 16 }, { "Mirage", 13, 1 } },
        },
        {
            .event = "ESL Pro League S21", .date = "09/02", .bo = "BO3", .status = "live",
            .t1_name = "Falcons", .t1_short = "FLC", .t1_color = 0x00B36B,
            .t2_name = "Vitality", .t2_short = "VIT", .t2_color = 0xFFD928,
            .score1 = 1, .score2 = 1, .map_count = 3,
            .maps = { { "Dust2", 13, 9 }, { "Nuke", 8, 13 }, { "Mirage", 0, 0 } },
        },
        {
            .event = "IEM Katowice 2026", .date = "09/05", .bo = "BO3", .status = "upcoming",
            .t1_name = "Spirit", .t1_short = "SPR", .t1_color = 0x8C6239,
            .t2_name = "MOUZ", .t2_short = "MOUZ", .t2_color = 0xE43B2F,
            .score1 = 0, .score2 = 0, .map_count = 0,
        },
        {
            .event = "PGL Major Cluj", .date = "09/08", .bo = "BO5", .status = "upcoming",
            .t1_name = "NAVI", .t1_short = "NAVI", .t1_color = 0xF2E14C,
            .t2_name = "FaZe", .t2_short = "FaZe", .t2_color = 0xB01C24,
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

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    switch (id) {
    case WIFI_EVENT_STA_DISCONNECTED: {
        const wifi_event_sta_disconnected_t *d = (const wifi_event_sta_disconnected_t *)data;
        ESP_LOGW(TAG, "Wi-Fi 断开, reason=%d", d ? d->reason : -1);
        s_ip[0] = 0;
        if (s_state == CS_NET_CONNECTING || s_state == CS_NET_ONLINE) {
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
    case WIFI_EVENT_SCAN_DONE: {
        uint16_t n = CS_AP_MAX;
        s_ap_count = 0;
        esp_err_t err = esp_wifi_scan_get_ap_records(&n, s_aps);
        if (err == ESP_OK) {
            s_ap_count = n;
            s_state = CS_NET_APLIST;
            ESP_LOGI(TAG, "扫描完成, %u 个 AP", (unsigned)n);
        } else {
            ESP_LOGE(TAG, "取扫描结果失败: %s", esp_err_to_name(err));
            s_state = CS_NET_FAILED;
        }
        break;
    }
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
void           cs_net_state_reset(void)  { if (s_state == CS_NET_FAILED) s_state = CS_NET_READY; }
bool           cs_net_online(void)       { return s_state == CS_NET_ONLINE; }
const char    *cs_net_ip(void)           { return s_ip; }
const char    *cs_net_ssid(void)         { return s_ssid; }
const char    *cs_net_ap_prev_ssid(void) { return s_prev_ssid; }

void cs_net_scan(void)
{
    if (!s_wifi_started) {
        if (wifi_bring_up() != ESP_OK) { s_state = CS_NET_FAILED; return; }
    }
    esp_err_t err = esp_wifi_scan_start(NULL, false);
    if (err == ESP_OK) {
        s_state = CS_NET_SCANNING;
    } else {
        ESP_LOGE(TAG, "scan_start: %s", esp_err_to_name(err));
        s_state = CS_NET_FAILED;
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Scan failed");
    }
}

int         cs_net_ap_count(void)     { return s_ap_count; }
const char *cs_net_ap_ssid(int idx)   { return (idx >= 0 && idx < s_ap_count) ? (const char *)s_aps[idx].ssid : ""; }
int         cs_net_ap_rssi(int idx)   { return (idx >= 0 && idx < s_ap_count) ? s_aps[idx].rssi : -99; }
bool        cs_net_ap_secure(int idx) { return (idx >= 0 && idx < s_ap_count) && s_aps[idx].authmode != WIFI_AUTH_OPEN; }

void cs_net_connect(const char *ssid, const char *password)
{
    if (!ssid || !ssid[0]) return;
    if (wifi_bring_up() != ESP_OK) { s_state = CS_NET_FAILED; return; }

    wifi_config_t wc;
    memset(&wc, 0, sizeof(wc));
    scpy((char *)wc.sta.ssid, sizeof(wc.sta.ssid), ssid);
    if (password) scpy((char *)wc.sta.password, sizeof(wc.sta.password), password);
    wc.sta.threshold.authmode = (password && password[0]) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;

    esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &wc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "set_config: %s", esp_err_to_name(err));
        s_state = CS_NET_FAILED;
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Wi-Fi config failed");
        return;
    }
    scpy(s_ssid, sizeof(s_ssid), ssid);
    scpy(s_prev_ssid, sizeof(s_prev_ssid), ssid);
    s_reconnect = 0;
    s_state = CS_NET_CONNECTING;
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
// 数据源 URL(可存 NVS 覆盖,便于不改固件换源)
// ---------------------------------------------------------------------------
static char s_url[160];

const char *cs_data_url(void)
{
    if (s_url[0]) return s_url;
    nvs_handle_t h;
    if (nvs_open(CS_NVS_NS, NVS_READONLY, &h) == ESP_OK) {
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
    if (nvs_open(CS_NVS_NS, NVS_READWRITE, &h) == ESP_OK) {
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
    return v ? (v & 0xFFFFFF) : def;
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
        jstr(mi, "event",  m->event,  sizeof(m->event),  "CS2 Match");
        jstr(mi, "date",   m->date,   sizeof(m->date),   "");
        jstr(mi, "bo",     m->bo,     sizeof(m->bo),     "BO3");
        jstr(mi, "status", m->status, sizeof(m->status), "upcoming");

        cJSON *t1 = cJSON_GetObjectItem(mi, "team1");
        jstr(t1, "name",  m->t1_name,  sizeof(m->t1_name),  "TBD");
        jstr(t1, "short", m->t1_short, sizeof(m->t1_short), "TBD");
        m->t1_color = jcolor(t1, "color", 0xE43B2F);

        cJSON *t2 = cJSON_GetObjectItem(mi, "team2");
        jstr(t2, "name",  m->t2_name,  sizeof(m->t2_name),  "TBD");
        jstr(t2, "short", m->t2_short, sizeof(m->t2_short), "TBD");
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
                mp->s1 = jint(km, "s1", 0);
                mp->s2 = jint(km, "s2", 0);
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
    esp_err_t err = nvs_open(CS_NVS_NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_set_str(h, CS_NVS_JSON_KEY, json);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}

static esp_err_t cache_load(char *out, size_t cap)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(CS_NVS_NS, NVS_READONLY, &h);
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

void cs_data_use_builtin(void)
{
    s_data = k_builtin;
    s_from_net = false;
    scpy(s_fetch_msg, sizeof(s_fetch_msg), "built-in sample");
}

esp_err_t cs_data_load_cache(void)
{
    static char buf[CS_CACHE_MAX];
    esp_err_t err = cache_load(buf, sizeof(buf));
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "无缓存(%s),用内置示例", esp_err_to_name(err));
        cs_data_use_builtin();
        return err;
    }
    if (!parse_matches(buf, &s_data)) {
        ESP_LOGW(TAG, "缓存解析失败,用内置示例");
        cs_data_use_builtin();
        return ESP_ERR_INVALID_RESPONSE;
    }
    s_from_net = false;
    scpy(s_fetch_msg, sizeof(s_fetch_msg), "cached");
    ESP_LOGI(TAG, "已载入缓存: %d 场", s_data.count);
    return ESP_OK;
}

static void fetch_task(void *arg)
{
    (void)arg;
    char *buf = (char *)malloc(CS_HTTP_BUF_MAX);
    if (!buf) {
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Out of memory");
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
            snprintf(s_fetch_msg, sizeof(s_fetch_msg), "Updated %d matches", s_data.count);
            s_fetch_state = CS_FETCH_OK;
            ESP_LOGI(TAG, "数据已更新: %d 场, %d 字节", s_data.count, len);
        } else {
            scpy(s_fetch_msg, sizeof(s_fetch_msg), "JSON parse failed");
            s_fetch_state = CS_FETCH_FAIL;
        }
    } else {
        snprintf(s_fetch_msg, sizeof(s_fetch_msg), "Net err: %s", esp_err_to_name(err));
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
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Wi-Fi not connected");
        s_fetch_state = CS_FETCH_FAIL;
        return;
    }
    s_fetch_state = CS_FETCH_RUNNING;
    scpy(s_fetch_msg, sizeof(s_fetch_msg), "Fetching...");
    if (xTaskCreate(fetch_task, "cs_fetch", 8192, NULL, 5, NULL) != pdPASS) {
        scpy(s_fetch_msg, sizeof(s_fetch_msg), "Task create failed");
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
    if (now < 1600000000) { snprintf(out, n, "--:--"); return; }
    time_t bj = now + 8 * 3600;
    struct tm tmv;
    gmtime_r(&bj, &tmv);
    snprintf(out, n, "%02d:%02d", tmv.tm_hour, tmv.tm_min);
}
