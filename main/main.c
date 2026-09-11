// main/main.c —— FoloToy AI Passport BSP 驱动参考示例:初始化 + 菜单 + 按键分发。
//
// 按键语义(全局统一):
//   上/下 短按   菜单中=移动选中项;演示页中=该页自定义
//   确定  短按   菜单中=进入选中项;演示页中=该页自定义
//   确定  长按   演示页中=返回菜单(由本文件统一拦截)
#include "bsp_i2c.h"
#include "bsp_display.h"
#include "bsp_button.h"
#include "bsp_audio.h"
#include "bsp_battery.h"
#include "bsp_pins.h"      // 错误日志里要打印 BSP_LCD_* 引脚号
#include "cs_assets.h"     // 队标 / 中文字体位图外置在 csres 分区,开机要先绑
#include "demo.h"
#include "ui_pixel.h"
#include "lvgl.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

static const char *TAG = "main";

static const demo_entry_t DEMOS[] = {
    { "Display", demo_display_enter, demo_display_exit, demo_display_key },
    { "Button",  demo_button_enter,  demo_button_exit,  demo_button_key  },
    { "Audio",   demo_audio_enter,   demo_audio_exit,   demo_audio_key   },
    { "Battery", demo_battery_enter, demo_battery_exit, demo_battery_key },
    { "Wi-Fi",   demo_wifi_enter,    demo_wifi_exit,    demo_wifi_key    },
    { "BLE",     demo_ble_enter,     demo_ble_exit,     demo_ble_key     },
    { "Low Power", demo_low_power_enter, demo_low_power_exit, demo_low_power_key },
    { "CS Board",  demo_csboard_enter,  demo_csboard_exit,  demo_csboard_key  },
};
#define DEMO_COUNT (sizeof(DEMOS) / sizeof(DEMOS[0]))

// 开机进入的页面(CS 看板在 DEMOS[] 中的下标)。
// 改这里就能换开机首屏:0=Display、4=Wi-Fi、7=CS Board。
#define DEMO_BOOT_IDX   7

// 各外设初始化结果:失败的项在菜单里标 [FAIL] 且不允许进入。
static bool s_ok[DEMO_COUNT];

static lv_obj_t *s_menu_scr;
static lv_obj_t *s_cards[DEMO_COUNT];
static lv_obj_t *s_rows[DEMO_COUNT];
static lv_obj_t *s_mascot;
static int  s_sel;                 // 当前选中项
static int  s_active = -1;         // 当前所在演示页;-1 = 在菜单

static void menu_refresh(void) {
    for (size_t i = 0; i < DEMO_COUNT; i++) {
        lv_label_set_text_fmt(s_rows[i], "%s%s",
                              DEMOS[i].name,
                              s_ok[i] ? "" : "  [FAIL]");
        ui_pixel_set_selected(s_cards[i], (int)i == s_sel, s_ok[i]);
        lv_obj_set_style_text_color(s_rows[i],
            s_ok[i] ? lv_color_hex(UI_INK) : lv_color_hex(0x7A2020), 0);
    }
}

static void menu_build(void) {
    s_menu_scr = ui_pixel_screen_create("FoloToy");

    for (size_t i = 0; i < DEMO_COUNT; i++) {
        int x = 11 + (int)(i % 2) * 112;
        int y = 52 + (int)(i / 2) * 47;
        s_cards[i] = ui_pixel_panel_create(s_menu_scr, x, y, 102, 40, UI_PAPER);
        s_rows[i] = lv_label_create(s_cards[i]);
        lv_obj_set_style_text_font(s_rows[i], &lv_font_montserrat_14, 0);
        lv_obj_set_style_text_align(s_rows[i], LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_center(s_rows[i]);
    }

    s_mascot = ui_pixel_mascot_create(s_menu_scr, 101, 242);

    menu_refresh();
    lv_screen_load(s_menu_scr);
}

static void enter_menu(void) {
    s_active = -1;
    menu_build();
}

// 供 CS Board 页面在顶层长按 OK 时调用:退出当前 demo 回到 FoloToy 主菜单。
void folotoy_back_to_menu(void) {
    if (s_active >= 0) {
        DEMOS[s_active].exit();
        enter_menu();
    }
}

// ---------------------------------------------------------------------------
// 按键事件改走独立任务。
// 按键回调原本直接在 button 组件的任务里做 LVGL 整屏重建 + esp_wifi 调用,
// 那个任务的栈有多深不受我们控制(组件内置默认值),键盘页一次 rebuild 要建
// 几十个 LVGL 对象,栈一旦吃紧就是莫名其妙的重启 —— 屏上表现正是"隔几秒白屏
// 一次"(重启时 LCD 复位会白一下)。这里只把事件丢进队列,由自带 6KB 栈的
// key_task 取出来、拿 LVGL 锁后再分发,深度不受组件约束。
// ---------------------------------------------------------------------------
typedef struct {
    uint8_t btn;
    uint8_t ev;
} key_evt_t;

static QueueHandle_t s_keyq;

static void dispatch_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if (s_active >= 0) {
        if (btn == BSP_BTN_OK && ev == BSP_BTN_LONG) {
            if (s_active == DEMO_BOOT_IDX) {
                // CS Board 自行处理层级返回(密码页->网络页->主菜单->FoloToy菜单)
                DEMOS[s_active].key(btn, ev);
            } else {
                DEMOS[s_active].exit();
                enter_menu();
            }
        } else {
            DEMOS[s_active].key(btn, ev);
        }
    } else if (ev == BSP_BTN_CLICK) {
        if (btn == BSP_BTN_UP)   { s_sel = (s_sel + DEMO_COUNT - 1) % DEMO_COUNT; menu_refresh(); }
        if (btn == BSP_BTN_DOWN) { s_sel = (s_sel + 1) % DEMO_COUNT;              menu_refresh(); }
        if (btn == BSP_BTN_OK && s_ok[s_sel]) {
            s_active = s_sel;
            ui_pixel_mascot_jump(s_mascot);
            lv_obj_delete(s_menu_scr);
            s_menu_scr = NULL;
            s_mascot = NULL;
            DEMOS[s_active].enter();
        } else if (btn == BSP_BTN_UP || btn == BSP_BTN_DOWN) {
            ui_pixel_mascot_jump(s_mascot);
        }
    }
}

// 按键回调只做入队,队列满就丢弃(界面还没消化完的连点没有意义)。
static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user) {
    (void)user;
    if (!s_keyq) return;
    key_evt_t e = { (uint8_t)btn, (uint8_t)ev };
    xQueueSend(s_keyq, &e, 0);
}

static void key_task(void *arg) {
    (void)arg;
    key_evt_t e;
    for (;;) {
        if (xQueueReceive(s_keyq, &e, portMAX_DELAY) != pdTRUE) continue;
        if (!bsp_lvgl_lock(1000)) continue;
        dispatch_key((bsp_btn_t)e.btn, (bsp_btn_ev_t)e.ev);
        bsp_lvgl_unlock();
    }
}

void app_main(void) {
    ESP_LOGI(TAG, "FoloToy AI Passport BSP demo 启动");
    esp_sleep_wakeup_cause_t wakeup = esp_sleep_get_wakeup_cause();
    if (wakeup != ESP_SLEEP_WAKEUP_UNDEFINED) {
        ESP_LOGI(TAG, "休眠唤醒原因: %d", wakeup);
    }

    bsp_i2c_init();
    bsp_i2c_scan();

    // 屏幕是本 demo 的 UI 载体,失败就没有菜单可言 —— 打清楚日志后退出,
    // 不做"串口菜单"降级(那会让本文件复杂一倍,违背参考示例的初衷)。
    if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {
        ESP_LOGE(TAG, "显示/LVGL 初始化失败,demo 无法继续。"
                      "检查 SPI 接线(MOSI=%d SCLK=%d CS=%d DC=%d BL=%d)",
                 BSP_LCD_MOSI, BSP_LCD_SCLK, BSP_LCD_CS, BSP_LCD_DC, BSP_LCD_BL);
        return;
    }
    bsp_display_backlight(100);

    // 其余外设单项失败不阻塞:菜单里标 [FAIL],其他项照常可测。
    // 按键事件队列与分发任务先建好,bsp_button_init 注册的回调才有的放。
    s_keyq = xQueueCreate(10, sizeof(key_evt_t));
    if (s_keyq && xTaskCreate(key_task, "ui_key", 6144, NULL, 5, NULL) != pdPASS) {
        vQueueDelete(s_keyq);
        s_keyq = NULL;
    }

    s_ok[0] = true;                                   // Display 已确认可用
    s_ok[1] = (bsp_button_init(on_key, NULL) == ESP_OK);
    s_ok[2] = (bsp_audio_init() == ESP_OK);
    s_ok[3] = (bsp_battery_init() == ESP_OK);
    s_ok[4] = true;                                    // 页面内按需初始化并显示错误
    s_ok[5] = true;
    s_ok[6] = true;
    s_ok[7] = true;                                   // CS Board 页面自包含,无外设依赖

    // 队标与中文字体的位图不在 app 里(在 csres 资源分区),先映射并绑定,
    // 否则中文会整字不画、队标会退化成占位徽章。失败只降级,不阻塞启动。
    if (!cs_assets_load()) {
        ESP_LOGW(TAG, "静态资源未加载:队标退化为占位徽章,中文不可用");
    }

    // 开机直奔 CS 看板,不再停在官方 demo 菜单上等用户按 7 下选到它。
    // 原来的菜单没丢:在 CS 看板里长按 OK 就回到菜单,工厂自检项照样能进去测。
    if (bsp_lvgl_lock(1000)) {
        s_active = DEMO_BOOT_IDX;
        s_sel = DEMO_BOOT_IDX;
        DEMOS[s_active].enter();
        bsp_lvgl_unlock();
    }

    ESP_LOGI(TAG, "就绪:Display=%d Button=%d Audio=%d Battery=%d",
             s_ok[0], s_ok[1], s_ok[2], s_ok[3]);
}
