# CS 赛事看板 · 固件出包与烧录指南

把 CS 赛事看板做成了一份可直接烧进 **FoloToy AI Passport** 硬件（ESP32-C3 / 8MB Flash / 无 PSRAM）的固件页面，已集成进官方 BSP 参考示例。

## 一、这次改了什么

| 文件 | 改动 |
|---|---|
| `main/demo_csboard.c` | **新增**：CS 看板页面（选手护照 / 赛事 / 积分榜三视图） |
| `main/demo.h` | 新增 `demo_csboard_*` 三个函数声明 |
| `main/main.c` | 菜单 `DEMOS[]` 加 `CS Board` 一项；`s_ok[7]` 标为可用 |
| `main/CMakeLists.txt` | 编译源文件列表加入 `demo_csboard.c` |

其余硬件驱动（`components/bsp`）、分区表、LVGL 配置均沿用原工程，无需改动。

## 二、设备上的三键怎么用

硬件右侧三键（UP / DOWN / OK，共用一个 ADC 引脚分压识别）：

- **UP / DOWN**：在当前视图内导航（护照页翻选手、赛事页翻场次、积分榜滚名次）
- **OK 单击**：三个视图循环切换 —— 选手护照 → 赛事 → 积分榜 → 选手护照
- **OK 长按**：由主程序统一拦截，返回主菜单（和原工程其它 demo 一致）

## 三、三大视图内容（示例数据，离线可跑）

- **PLAYER CARD**：NiKo / m0NESY / ZywOo / donk 四名选手，含 Rating、K/D、ADR、HS%、能力条（AIM/CLUT/IQ）
- **MATCHES**：对阵双方、BO 局制、时间、状态（LIVE / SOON）
- **WORLD RANKING**：战队世界排名 + 积分

> UI 文本一律 ASCII：LVGL 默认 `montserrat` 字体为 Latin，不含中文与块字符。
> 若需中文界面，需额外嵌入 CJK 字体子集（受 3MB 应用分区 + 无 PSRAM 限制，建议保持英文 UI）。

## 四、怎么拿到可烧录的 `.bin`（二选一）

> 本机未安装 ESP-IDF，无法在此直接编译。下面两种都是官方支持路径。

### 方式 A：GitHub Actions 自动出包（最省事，不用装任何环境）

1. 把**整个 `ai-passport` 文件夹**上传到你的 GitHub 仓库（网页拖拽、或 GitHub Desktop 都行）。
2. 给代码打一个 tag（如 `v1.0`）并推送；或到仓库 **Actions → Build firmware** 页面点 `Run workflow` 手动触发。
3. 构建完成后，到 **Releases**（打 tag 时）或 **Artifacts** 下载 `FoloToy-AI-Passport-full.bin`。

> 工程内已自带 `.github/workflows/build-firmware.yml`，调用官方 `espressif/esp-idf-ci-action@v5.5.3`，自动执行 `./tools/validate.sh --firmware` 并产出合并镜像。

### 方式 B：本机 ESP-IDF 5.5.3 编译（装一次，之后点按钮）

1. 安装 **ESP-IDF 5.5.3**（Espressif 官网一键安装器）+ **VS Code ESP-IDF 插件**。
2. 用 VS Code 打开本目录，左侧 ESP-IDF 插件点 **Build**（图形化，不用敲命令）。
3. 编译产物在 `build/FoloToy-AI-Passport-full.bin`。

## 五、怎么烧录（GUI 优先）

### 方式 1：ESP Web Tools 网页烧录（最推荐，纯浏览器，零安装）

1. 打开 Espressif 官方网页烧录工具（esptool-js / ESP Web Tools）。
2. 点 **Connect**，选设备串口（手机会让授权）。
3. 把 `FoloToy-AI-Passport-full.bin` 拖进去，地址填 `0x0`，点 **Flash**。

> 适合「空白设备」或首次烧录。已写入 `cardid` 身份分区的设备，请用方式 2 的分段烧录，避免覆盖受保护分区。

### 方式 2：VS Code ESP-IDF 插件（图形化）

1. 插件里选好串口号和速率。
2. 点 **Flash**（烧录）+ **Monitor**（看日志），全程按钮操作。

### 方式 3：命令行（备用，懂一点再用）

```bash
# 空白设备：合并镜像烧到 0x0
esptool.py --chip esp32c3 -p COMx --baud 921600 write_flash 0x0 build/FoloToy-AI-Passport-full.bin

# 已配置设备：用分段烧录（不碰受保护的 cardid 分区）
idf.py flash
```

## 六、换成你自己的真实数据

打开 `main/demo_csboard.c`，改顶部三组数组即可：

- `PLAYERS[]` —— 选手档案
- `MATCHES[]` —— 赛事列表
- `RANKS[]`   —— 战队排名

想接实时接口（对接你之前的 NiKo 追踪需求）：在 `demo_csboard_enter()` 里用 `bsp_wifi_*` + 简易 HTTP 拉取 HLTV / PandaScore / bo3.gg，解析后刷新上面数组再 `render()`。工程已预留这个扩展点。
