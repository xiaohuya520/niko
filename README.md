# NiKo 赛事跟踪 · GitHub 仓库

这个仓库既是**实时数据源**，也是**永久在线的网页**（GitHub Pages）。
两者都不花钱、不需要你自己电脑开机。

- GitHub 仓库：https://github.com/xiaohuya520/niko
- 在线网址（Pages）：https://xiaohuya520.github.io/niko/

## 页面结构（一级 + 二级）

| 页面 | 内容 |
|------|------|
| `index.html` | 一级主页：下一站赛事倒计时、NiKo 头像与资料、可左右滑动的现役队友、近期战绩（点任意一场进详情）、近一年数据汇总 |
| `match.html?id=...` | 二级：单场比赛详情 —— 逐图回合比分、上下半场（进攻/防守）拆分、图池禁用情况、HLTV 全场/单图链接、每图录像 |
| `team.html` | 二级：Team Falcons 战队页 —— 五名选手 + 教练，带头像，点进个人页 |
| `player.html?id=...` | 二级：选手个人页 —— 中文资料、战队经历、生涯数据、外设与准星参数 |

一级页面所有数据块都可点击进入对应二级页。

## 两种用法

### 用法 A：只当数据源（保留现有网址）

网页继续用 https://579fd30392e94ab699a31eb11e93a71f.app.workbuddy.link ，
数据由本仓库的 Actions 更新，经 jsDelivr / raw.githubusercontent 传给网页。

适合：你想保留 WorkBuddy 那个链接。

### 用法 B：GitHub Pages 自己托管网页（推荐，最稳）

仓库里已经带了四个页面和 PWA 配置，开启 GitHub Pages 后网址是：

```
https://xiaohuya520.github.io/niko/
```

这个页面**同源直读本仓库的 `data.json`**，不依赖 jsDelivr、不依赖 WorkBuddy，
Actions 更新数据后网页自动就变了。手机浏览器打开 → 添加到主屏幕，
得到一个准星图标、全屏无地址栏，跟小程序体验一样。

## 数据源优先级

页面会自动依次尝试，谁先成功用谁（底部状态栏会显示当前用的是哪个）：

| 版本 | 顺序 |
|------|------|
| GitHub Pages 版 | 本仓库 data.json（本地）→ GitHub 直连 → jsDelivr → 内联缓存 |
| WorkBuddy 版 | jsDelivr → GitHub 直连 → 同源 data.json → 内联缓存 |

jsDelivr 国内访问稳，但对分支有最长 12 小时缓存；
raw.githubusercontent 几乎实时，国内偶尔不通。两者互为兜底。

## 文件说明

| 文件 | 作用 |
|------|------|
| `index.html` / `match.html` / `team.html` / `player.html` | 四个页面（CS 军事 HUD 风格，手机端优先，PWA 可加桌面） |
| `data.json` | 数据文件，由 Actions 每 30 分钟自动更新，含 58 场比赛的逐图详情 |
| `players.json` | Team Falcons 现役阵容资料（中文）+ 头像路径 |
| `assets/players/*.jpg` | 六名队员头像，来自 Liquipedia（CC-BY-SA 3.0） |
| `run.py` | 抓取 + 解析 + 合并主程序（纯 Python 标准库，无第三方依赖） |
| `pipeline.py` | 抓取与解析的共用逻辑，本地迭代与线上产出完全一致 |
| `parse_detail.py` | 从 bracket popup 解析逐图回合比分、上下半场、HLTV 对局 id |
| `parse_popup.py` | 旧版系列赛比分解析器（保留兜底） |
| `build_players.py` / `normalize_players.py` | 阵容资料抓取与中文化 |
| `base.json` | 静态数据：选手资料、未来赛程、已逐场核对的 HLTV 评分 |
| `manifest.json` / `icon.svg` / `.nojekyll` | PWA 与 Pages 配置 |
| `.github/workflows/update.yml` | 每 30 分钟自动跑 `run.py` 并提交 `data.json` |

## 部署步骤（一次性）

1. 在 GitHub 新建**公开（public）**仓库 `niko`（已建好）。
2. 推送本目录所有文件（含隐藏的 `.github/` 和 `.nojekyll`）：

```bash
cd "C:/Users/Administrator/WorkBuddy/2026-09-07-17-42-17/niko-tracker/github"
git push -f -u origin main
```

3. 仓库 **Settings → Actions → General → Workflow permissions** 设为
   **Read and write permissions**（让 Actions 能提交 `data.json`）。
4. 仓库 **Settings → Pages → Build and deployment**：
   Source 选 **Deploy from a branch**，Branch 选 **main / root**，点 Save。
   约 1 分钟后 https://xiaohuya520.github.io/niko/ 生效。
5. 进入 **Actions** 标签页手动 **Run workflow** 跑一次，看到绿色对勾即成功。
   之后每 30 分钟自动跑（GitHub 免费账户可能有几分钟排队延迟，属正常）。

## 维护

- **赛程/比分**：全自动，比赛结束后约 30 分钟内更新。
- **新增赛事**：若 Liquipedia 上出现新赛事而本仓库未收录，
  在 `run.py` 的 `PAGES` 列表里加上该赛事的 Liquipedia 页面路径即可
  （例如 `"BLAST/Open/2027/Spring"`）。
- **个人 rating**：HLTV 无公开 API，目前只覆盖已人工核对的 5 场
  （写在 `base.json` 的 `known_ratings`）。要给新场次补 rating，
  按 `"date" / "opponent" / "ratings"` 格式往里加即可，没填的场次显示「—」而非编造。
- **阵容变动**：改 `build_players.py` 的 `SQUAD` 列表并重新抓取；
  只想改中文备注时跑 `normalize_players.py`（不会重新下载头像）。
- **选手静态资料**（装备、准星、奖金等）：基本不变，如需更新改 `base.json`。
- **页面样式**：页面由 `build.py` 从模板生成，改完重新生成并 push，Pages 约 1 分钟生效。
- **改仓库地址**：页面里的 `REPO` 常量来自构建时的 `repo.txt`，改完重新生成页面。

## 已知边界

- 做不到回合级实时比分（如"13-7 进行中"），那需要 GRID 之类商业授权，年费六位数。
  现在能拿到的是系列赛比分 + 逐图回合比分，赛后 5–20 分钟由 Liquipedia 更新。
- 个人 rating 非全量，原因见上。
- 队名、选手 ID、外设型号、赛事名保留英文原名（专有名词，中文社区也这么叫）；
  地图名显示中文并在后面用小字标注英文原名。

## 许可证

赛程与系列赛比分数据来自 Liquipedia，遵循 **CC-BY-SA 3.0**，使用请署名。
