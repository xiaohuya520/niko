# CS2 赛事看板(ESP32-C3 / LVGL 9)

FoloToy AI Passport 上的 CS2 赛程看板演示页。深色电竞风、**纯中文界面**、
**真实战队官方队标**、连 Wi-Fi 自动拉取赛程,支持历史战绩与赛事预告。

---

## 1. 页面结构(一级 / 二级页)

```
┌────────────── 状态栏:Wi-Fi 名 · 北京时间 · 电量 ──────────────┐
│                                                                │
│  主菜单                                                        │
│   ├─ 实时比分    二级页:大比分 + 两队真实队标 + 逐图比分        │
│   ├─ 近期战绩    二级页:已结束比赛列表(胜绿负红)              │
│   ├─ 赛事预告    二级页:未开始比赛列表(日期 + 开赛时间)        │
│   └─ 网络设置    二级页:扫描 Wi-Fi → 选网 → 三键输入密码        │
│                                                                │
└────────────── 底部提示条:当前页按键说明 ─────────────────────┘
```

屏幕 240×320(ST7789P3 / SPI)。状态栏 22px,提示条 24px,正文 274px。

### 按键分工(板载 UP / DOWN / OK 三键)

| 页面 | UP / DOWN | OK 单击 | OK 双击 |
|------|-----------|---------|---------|
| 主菜单 | 切换条目 | 进入二级页 | 刷新赛程数据 |
| 实时比分 | 上/下一场比赛 | 刷新赛程数据 | 返回主菜单 |
| 近期战绩 / 赛事预告 | 上/下滚动列表 | 刷新赛程数据 | 返回主菜单 |
| 网络设置 | 上/下选 AP | 连接(有密码则进密码页) | 返回主菜单 |
| 密码输入 | 上/下选字符 | 输入字符 / 删 / 换字符集 / 提交连接 | 返回网络设置 |

> OK 长按由 `main.c` 统一拦截,用于退出演示页。
> OK 单击带 320ms 延时(等双击判定),避免"双击时先触发一次单击"。

### 密码输入(无触摸屏,纯三键)

字符选择器 = `当前字符集字符… + 删(退格) + 换(切字符集) + 连(提交)`。
字符集依次为 `小写字母 / 大写字母 / 数字 / 符号`。UP/DOWN 滚动选择,OK 单击执行。
配网成功后凭证写入 NVS,下次开机自动重连。

---

## 2. 界面文字与队标

### 中文字体

LVGL 内置的 `lv_font_source_han_sans_sc_*_cjk` 是**日文向的精选字集**
(仅 1442 字,不含"赛事/战绩/预告"等常用词),因此本项目**自带**一份字体:

* 生成文件:`main/cs_font_cn16.c`(脚本生成,勿手改)
* 字号 16px / bpp4,含 ASCII + **GB2312 全部一级汉字(3755 字)** + 符号区
* 字形位图约 **385KB**(已 RLE 压缩),`glyph_dsc` 等合计约 **460KB Flash**
* 覆盖范围足够显示任意中文(如中文 Wi-Fi 名称、中文赛事名)

### 真实战队队标

`main/cs_assets.c`(脚本生成)内嵌 **105 支战队的真实官方队标**,覆盖 HLTV 世界排名
前 100 的主流战队及其青训队(NAVI Junior / Spirit Academy / MOUZ NXT 等),
完整名单见 `tools/cs_teams.json`。部分代表:

| logo id | 战队 | logo id | 战队 | logo id | 战队 |
|---------|------|---------|------|---------|------|
| `g2` | G2 | `navi` | NAVI | `faze` | FaZe |
| `vitality` | Vitality | `spirit` | Spirit | `mouz` | MOUZ |
| `astralis` | Astralis | `aurora` | Aurora | `falcons` | Falcons |
| `virtuspro` | Virtus.pro | `mongolz` | The MongolZ | `furia` | FURIA |
| `tyloo` | TYLOO | `rareatom` | Rare Atom | `lynnvision` | Lynn Vision |
| `navijunior` | NAVI Junior | `spiritacad` | Spirit Academy | `mouz-nxt` | MOUZ NXT |

* 两档尺寸预生成:**48×48**(比分卡)与 **20×20**(列表缩略),固件内**不做运行时缩放**
* 格式 RGB565(已按队标亮度自动合成浅/深底板,并先裁掉 PNG 四周透明留白),
  105 支共约 **555KB Flash**(app 分区 3MB,余量约 240KB)
* **别名**:同一支队的常见写法都能命中,如 `navi` = `natus-vincere` = `na-vi`,
  `virtuspro` = `virtus-pro` = `vp`,`9pandas` = `9-pandas`(共 146 个 id)
* 未收录的 `logo` id → 回退成队色圆角方块,**不会**用英文缩写糊弄

> 队标来源:[lootmarket/esport-team-logos](https://github.com/lootmarket/esport-team-logos)
> 的 `csgo/` 目录,全部是各队官方 logo。新增战队只需在 `tools/cs_teams.json`
> 加一行、重新生成资源并重编固件(见 §4)。

---

## 3. 数据源与格式

固件从 HTTPS 拉一份 JSON,解析后显示。默认地址:

```
https://cdn.jsdelivr.net/gh/xiaohuya520/niko@firmware/cs_matches.json
```

走 jsDelivr CDN(国内可直连),指向本仓库 `firmware` 分支根目录的 `cs_matches.json`。
**改数据只要改这个 JSON 并推送到 `firmware` 分支,不用重新编译固件。**

### 字段说明

```json
{
  "updated": "09-11 15:40",          // 主菜单副标题显示的数据时间
  "matches": [
    {
      "status": "live",              // live 进行中 / finished 已结束 / upcoming 未开始
      "event":  "ESL 职业联赛 S21",   // 赛事名(中文)
      "stage":  "小组赛",             // 阶段,可空
      "date":   "09-11",             // MM-DD
      "time":   "20:00",             // 开赛时间(预告页显示)
      "bo":     "BO3",
      "team1":  { "name": "Virtus.pro", "short": "VP", "logo": "virtuspro", "color": "#F58220" },
      "team2":  { "name": "MOUZ",       "logo": "mouz",       "color": "#E43B2F" },
      "score1": 1, "score2": 1,
      "maps": [
        { "name": "Inferno", "cn": "炼狱小镇", "s1": 13, "s2": 9 }
      ]
    }
  ]
}
```

* `status` 决定进哪个页面:`live` → 实时比分,`finished` → 近期战绩,`upcoming` → 赛事预告
* `maps[].cn` 中文图名,留空则回退英文 `name`
* `team*.short` 可选:列表行只有 62px 宽,`name` 放不下时显示 `short`
  (如 `Virtus.pro` → `VP`、`GamerLegion` → `GL`;不写则自动用省略号截断)
* `team*.color` 用于强调色 / 队标缺失时的占位方块
* 大小上限:JSON ≤ **12KB**(NVS 缓存),单次下载也 ≤ **12KB**;建议控制在 10KB 内
* 数组顺序即显示顺序:建议"进行中 → 已结束(新→旧) → 未开始(近→远)"

### 断网兜底

1. 联网成功 → 解析 JSON 并写入 NVS
2. 下次开机先读 NVS 缓存,立即出画面
3. 无缓存 → 用固件内置的示例数据(`cs_net.c` 的 `k_builtin`)

---

## 4. 重新生成资源

字体与队标都是脚本生成的,源素材(PNG / TTF)不在仓库里(体积大),但**清单在**。

```bash
pip install pillow fonttools brotli
npm install lv_font_conv

# 1) 按 tools/cs_teams.json 清单下载 105 支真实队标 PNG
python tools/fetch_cs_logos.py --out .cache/logos

# 2) 生成字体 + 队标(会覆盖 main/cs_font_cn16.c 与 main/cs_assets.c)
python tools/gen_csboard_assets.py \
    --ttf        NotoSansSC-Regular.ttf \
    --logo-dir   .cache/logos \
    --teams-json tools/cs_teams.json \
    --out-dir    main
```

* `--logo-dir` 里每个 PNG 的文件名就是 `logo` id(`g2.png` → `"logo": "g2"`)
* `--teams-json` 决定登记哪些别名;不传则只按 PNG 文件名登记
* 新增战队:在 `tools/cs_teams.json` 的 `teams` 里加
  `{ "id": "战队id", "cn": "中文名", "repo": "仓库目录名" }`,再跑上面两步
* 字体推荐 Noto Sans SC(= 思源黑体);**woff2 转 TTF 时必须清 `flavor`**,
  否则 fontTools 只是重新封装,仍是 `wOF2` 签名,lv_font_conv 会报
  `Unsupported OpenType signature wOF2`

---

## 5. 编译与烧录

固件由 GitHub Actions 构建(`.github/workflows/build-firmware.yml`),
推送 `cs-firmware-v*` 标签触发,产物是一个可直接烧录的完整镜像
`FoloToy-AI-Passport-full.bin`(含分区表 + bootloader + app)。

```
分区:factory(app) 0x10000 起,3MB  —— 当前固件约 2.7MB(中文字体 0.46MB + 队标 0.55MB)
      nvs 0x9000 24KB(共享给 Wi-Fi 凭证 + JSON 缓存)
      cardid@0x356000 保持不变,勿动
```

板子进下载模式后,用 `esptool.py write_flash 0x0 FoloToy-AI-Passport-full.bin`
或官方烧录工具一次写入即可。

### 5.1 推送标签(本机代理会拦 git 协议时的备用路径)

本机网络上 `git push` 的 pack 协议会被代理拦掉(报 502 tunnel),但
GitHub REST API 是通的。此时可以只用 API 完成"提交 + 打标签":

```
取 refs/heads/firmware 的 head sha
  → POST /git/blobs                  每个改动文件一个 blob(base64)
  → POST /git/trees  { base_tree, tree:[...] }   只放改动文件即可增量
  → POST /git/commits { message, tree, parents:[head] }
  → PATCH /git/refs/heads/firmware   { sha, force }
  → POST /git/refs  { ref:"refs/tags/cs-firmware-vX", sha }   ← 这一步触发 CI
```

注意 `parents` 必须用**完整 40 位 sha**(短 sha 会被拒)。只改一两个文件时
用 `base_tree` + 少量 entry 做增量即可,不必重传几 MB 的字体源。

CI 成功后 `FoloToy-AI-Passport-full.bin` 在 Release 里;artifact 的下载端点
需要 `Accept: application/octet-stream` 走 API,直接开 zip 链接会 401。

---

## 6. 代码结构

| 文件 | 职责 |
|------|------|
| `main/cs_net.h` / `cs_net.c` | Wi-Fi 扫描/连接/NVS 凭证、HTTPS 拉取、JSON 解析、NVS 缓存、SNTP 对时。**不碰 LVGL** |
| `main/demo_csboard.c` | 全部 UI:状态栏 + 主菜单 + 4 个二级页 + 三键状态机 |
| `main/cs_assets.h` / `cs_assets.c` | 队标查表接口 + 105 支真实队标位图(生成) |
| `main/cs_font_cn16.c` | 生成的中文字体 |
| `tools/gen_csboard_assets.py` | 上面两个生成文件的产生脚本 |
| `tools/fetch_cs_logos.py` | 按清单下载真实队标 PNG |
| `tools/cs_teams.json` | 105 支战队的 id / 中文名 / 仓库目录清单 |
| `cs_matches.json` | 数据源(部署在 `firmware` 分支根目录) |

UI 侧 200ms 轮询 `cs_net_state()` / `cs_data_fetch_state()`,状态变化才重建视图,
不做无谓重绘。

## 7. 已知限制

* **仅 2.4GHz** Wi-Fi(C3 硬件限制)
* JSON 需 ≤ 12KB,否则 NVS 缓存写不进去(仍能正常显示,只是离线时回退到旧数据)
* 队标为内置白名单(105 支),名单外的战队显示队色方块;新增战队需重编固件
* 队标与字体占 app 分区约 1MB,余量约 240KB —— 还想大幅扩充名单时,
  应把队标移到独立 data 分区用 `esp_partition_mmap` 读取
* 时间依赖联网 SNTP(`ntp.aliyun.com`),未联网时状态栏显示 `--:--`
* 数据源目前是示例 JSON,接真实赛事数据需自己写个定时更新该 JSON 的脚本
