"""生成 NiKo 赛事跟踪站：一级页 + 三个二级页（比赛详情 / 队伍 / 选手）。

所有页面内联 data.json，离线可直接打开；联网时会尝试拉取更新后的 data.json 覆盖。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).parent
DATA = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
_gh = ROOT / "github"
REPO = (ROOT / "repo.txt").read_text(encoding="utf-8").strip() or "__REPO__"

CSS = r"""/* ========== NiKo 赛事跟踪 · 视觉升级（正规 + 设计感）========== */
:root{
  --bg:#ECEAF8;
  --bg2:#E3E0F5;
  --panel:#FFFFFF;
  --panel2:#F5F4FE;
  --panel3:#E8E6F8;
  --line:#E7E5F7;
  --line-soft:#D8D5F0;
  --hi:#FFFFFF;
  --shadow-c:transparent;
  --ink:#242A52;
  --ink2:#6B7099;
  --dim:#A0A4C6;
  --amber:#5B5CE6;
  --amber2:#8B5CF6;
  --amber-bg:#ECEAFE;
  --cyan:#1FB6C9;
  --win:#15B981;
  --win-bg:#DCF6EC;
  --loss:#F0566E;
  --loss-bg:#FDE6EA;
  --ct:#4C7FD9;
  --t:#F0904A;
  --exp:#9C6BEB;
  --grad:linear-gradient(120deg,#5B5CE6 0%,#8B5CF6 46%,#1FB6C9 100%);
  --grad-num:linear-gradient(180deg,#4F46E5 0%,#7C3AED 55%,#0EA5B7 100%);
  --grad-soft:linear-gradient(120deg,#ECEAFE,#F4EAFD 58%,#E2F6F9);
  --glow:0 26px 56px -24px rgba(91,92,230,.55);
  --shadow-lg:0 26px 54px -26px rgba(66,68,158,.36);
  --shadow-md:0 14px 30px -16px rgba(66,68,158,.28);
  --shadow-sm:0 7px 18px -9px rgba(66,68,158,.18);
  --sans:"Noto Sans SC","PingFang SC","HarmonyOS Sans SC","Microsoft YaHei",system-ui,sans-serif;
  --display:"Noto Serif SC","Songti SC",serif;
  --mono:"Rajdhani","Noto Sans SC","SF Mono",Consolas,"Courier New",monospace;
  --tech:"Rajdhani","Noto Sans SC",system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
img{display:block}
body{
  background-color:var(--bg);
  background-image:
    radial-gradient(1100px 520px at 88% -12%, #E9E3FE 0%, transparent 60%),
    radial-gradient(900px 460px at -12% 4%, #E6F6F8 0%, transparent 58%),
    radial-gradient(circle at 1px 1px, rgba(36,42,82,.05) 1px, transparent 0);
  background-size:auto,auto,22px 22px;
  background-attachment:fixed;
  color:var(--ink);
  font-family:var(--sans);
  font-size:16px;
  line-height:1.72;
  min-height:100vh;
  text-rendering:optimizeLegibility;
  -webkit-font-smoothing:antialiased;
}
a{color:inherit;text-decoration:none}
.wrap{max-width:780px;margin:0 auto;padding:0 16px 88px}

/* === 顶栏 === */
.hud{position:sticky;top:0;z-index:50;
  background:rgba(255,255,255,.78);
  backdrop-filter:blur(16px) saturate(140%);-webkit-backdrop-filter:blur(16px) saturate(140%);
  border-top:3px solid transparent;border-image:var(--grad) 1;
  box-shadow:0 1px 0 var(--line)}
.hud-in{max-width:780px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;gap:12px}
.brand{display:flex;flex-direction:column;line-height:1.12}
.brand b{font-family:var(--tech);font-size:25px;letter-spacing:.2em;font-weight:700;
  background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:var(--amber)}
.brand small{font-family:var(--tech);font-size:10px;color:#fff;letter-spacing:.32em;font-weight:600;
  background:var(--grad);padding:3px 10px;margin-top:4px;border-radius:999px;display:inline-block;width:fit-content}
.hud .ava{width:38px;height:38px;flex:none;border-radius:13px}
.status{margin-left:auto;display:flex;align-items:center;gap:8px;
  font-family:var(--mono);font-size:12px;letter-spacing:.1em;font-weight:600;
  background:var(--panel2);color:var(--ink);
  border:1px solid var(--line);padding:7px 13px;border-radius:999px;box-shadow:var(--shadow-sm)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--amber)}
.dot.live{background:var(--loss);animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}

/* === 准星品牌图标 === */
.crosshair{width:36px;height:36px;flex:none;position:relative;
  background:var(--grad);border-radius:12px;box-shadow:0 8px 18px -7px rgba(91,92,230,.6)}
.crosshair::before,.crosshair::after{content:"";position:absolute;background:#fff;border-radius:2px}
.crosshair::before{left:50%;top:8px;width:3px;height:19px;transform:translateX(-50%)}
.crosshair::after{top:50%;left:8px;height:3px;width:19px;transform:translateY(-50%)}
.crosshair span{display:none}

/* === 头像 === */
.av{background:var(--panel2);border:1px solid var(--line);object-fit:cover;flex:none;display:block;border-radius:16px;
  box-shadow:0 0 0 2px #fff,0 0 0 4px var(--line)}
.av-xl{width:84px;height:84px}
.av-lg{width:66px;height:66px}
.av-ph{display:grid;place-items:center;font-family:var(--tech);font-weight:700;color:var(--amber);
  background:var(--grad-soft);border:1px solid var(--line);flex:none;border-radius:16px;
  box-shadow:0 0 0 2px #fff,0 0 0 4px var(--line)}
.av-ph-xl{width:84px;height:84px;font-size:24px}
.av-ph-lg{width:66px;height:66px;font-size:20px}

.prof{display:flex;align-items:center;gap:16px;background:linear-gradient(180deg,#fff,#FBFAFF);
  border:1px solid var(--line);border-radius:24px;padding:18px 20px;margin-top:18px;
  box-shadow:var(--shadow-md);position:relative;overflow:hidden}
.prof::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:5px;border-radius:3px;background:var(--grad)}
.prof .nick{font-family:var(--tech);font-size:27px;font-weight:700;letter-spacing:.04em;color:var(--ink);padding-left:6px}
.prof .full{font-family:var(--mono);font-size:13px;color:var(--ink2);margin-top:3px;letter-spacing:.04em;padding-left:6px}
.prof .meta{font-family:var(--mono);font-size:11px;color:var(--amber);margin-top:8px;letter-spacing:.06em;
  background:var(--amber-bg);padding:4px 11px;display:inline-block;border-radius:999px;font-weight:600;padding-left:11px}
.prof-link{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--amber);font-weight:600;
  background:var(--amber-bg);padding:7px 13px;border-radius:999px;letter-spacing:.08em;white-space:nowrap}

/* === 队友横滑 === */
.scroller{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 12px;scroll-snap-type:x mandatory;
  -webkit-overflow-scrolling:touch;scrollbar-width:none}
.scroller::-webkit-scrollbar{display:none}
.pc{flex:0 0 136px;scroll-snap-align:start;background:var(--panel);
  border:1px solid var(--line);border-radius:20px;padding:15px 10px;text-align:center;
  box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.pc::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;background:var(--grad);opacity:.85}
.pc:active{transform:scale(.97)}
.pc .ph{width:64px;height:64px;margin:0 auto 11px}
.pc .ph .av,.pc .ph .av-ph{border-radius:16px}
.pc .pid{font-size:16px;font-weight:700;letter-spacing:.02em;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.pc .prole{font-family:var(--mono);font-size:10px;color:var(--amber);background:var(--amber-bg);
  padding:3px 9px;display:inline-block;margin-top:6px;letter-spacing:.08em;border-radius:999px;font-weight:600}
.pc .pnat{font-family:var(--mono);font-size:11px;color:var(--ink2);margin-top:5px;letter-spacing:.06em}
.hint{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.16em;margin-bottom:7px;text-transform:uppercase}

/* === 章节 === */
.sec{margin-top:36px;position:relative}
.sec-h{display:flex;align-items:center;gap:12px;margin-bottom:15px}
.sec-h b{font-family:var(--display);font-size:19px;font-weight:700;color:var(--ink);letter-spacing:.04em;
  position:relative;padding-left:15px}
.sec-h b::before{content:"";position:absolute;left:0;top:.2em;bottom:.2em;width:5px;border-radius:3px;background:var(--grad)}
.sec-h i{flex:1;height:1px;background:linear-gradient(90deg,var(--line-soft),transparent)}
.sec-h em{font-family:var(--mono);font-size:12px;color:var(--amber);font-style:normal;letter-spacing:.14em;font-weight:600}
.sec-h a em{color:var(--amber);font-weight:700}

/* === 下一场比赛 hero（深色渐变焦点）=== */
.hero{margin-top:18px;position:relative;border-radius:28px;overflow:hidden;
  background:linear-gradient(135deg,#4738C8 0%,#6B49D6 44%,#1F9FB4 115%);
  box-shadow:var(--glow);border:1px solid rgba(255,255,255,.18);color:#fff}
.hero::before{content:"";position:absolute;inset:0;pointer-events:none;mix-blend-mode:overlay;
  background:
    radial-gradient(120% 80% at 85% 0%, rgba(255,255,255,.22), transparent 55%),
    repeating-linear-gradient(135deg, rgba(255,255,255,.06) 0 2px, transparent 2px 13px)}
.hero::after{content:"";position:absolute;right:-40px;bottom:-30px;width:260px;height:200px;
  background:radial-gradient(closest-side,rgba(255,255,255,.22),transparent);pointer-events:none}
.hero-top{display:flex;align-items:center;gap:9px;padding:16px 20px 0;position:relative;z-index:1}
.tag{font-family:var(--mono);font-size:11px;letter-spacing:.2em;color:#fff;font-weight:600;
  background:rgba(255,255,255,.16);padding:5px 13px;border-radius:999px;backdrop-filter:blur(4px)}
.hero-body{padding:20px 16px 24px;text-align:center;position:relative;z-index:1}
.vs{display:flex;align-items:center;justify-content:center;gap:16px;margin:8px 0 4px;flex-wrap:wrap}
.team{font-size:32px;font-weight:700;letter-spacing:.03em;color:#fff;font-family:var(--tech);
  text-shadow:0 2px 16px rgba(0,0,0,.28)}
.team.tbd{color:rgba(255,255,255,.62)}
.vs-mid{font-family:var(--mono);font-size:14px;color:#fff;font-weight:600;letter-spacing:.1em;
  background:rgba(255,255,255,.18);padding:5px 13px;border-radius:999px;backdrop-filter:blur(4px)}
.hero-sub{font-family:var(--mono);font-size:13px;color:rgba(255,255,255,.85);letter-spacing:.06em}
.hero-note{font-family:var(--mono);font-size:12px;color:#fff;letter-spacing:.05em;margin-top:12px;
  background:rgba(255,255,255,.16);padding:5px 13px;display:inline-block;border-radius:999px;backdrop-filter:blur(4px)}

/* === 倒计时 === */
.cd{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin:22px 0 6px}
.cd div{background:var(--grad-soft);border:1px solid var(--line);border-radius:20px;padding:16px 4px 14px;
  box-shadow:inset 0 1px 0 #fff;position:relative;overflow:hidden}
.cd div::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--grad);opacity:.8}
.cd b{display:block;font-family:var(--tech);font-size:42px;font-weight:700;
  background:var(--grad-num);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:var(--amber);
  font-variant-numeric:tabular-nums;font-feature-settings:"tnum";line-height:1}
.cd span{font-family:var(--mono);font-size:10px;color:var(--ink2);letter-spacing:.34em;margin-top:8px;display:block;text-transform:uppercase}

/* === 未来赛程卡 === */
.up{display:grid;gap:13px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.up-c{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:16px 18px;position:relative;
  box-shadow:var(--shadow-sm);overflow:hidden}
.up-c::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--grad);opacity:.85}
.up-c .n{font-size:17px;font-weight:700;letter-spacing:.01em;color:var(--ink);padding-right:64px}
.up-c .d{font-family:var(--mono);font-size:13px;color:var(--amber);margin-top:5px;font-weight:600;letter-spacing:.04em}
.up-c .m{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-top:9px;letter-spacing:.04em}
.tier{position:absolute;top:14px;right:14px;font-family:var(--mono);font-size:10px;text-transform:uppercase;
  color:var(--amber);background:var(--amber-bg);padding:4px 10px;letter-spacing:.08em;font-weight:600;border-radius:999px}

/* === 战绩 rows === */
.rows{display:flex;flex-direction:column;gap:11px}
.row{display:flex;align-items:center;gap:13px;background:var(--panel);
  border:1px solid var(--line);border-left:4px solid var(--line-soft);border-radius:18px;padding:13px 15px;
  box-shadow:var(--shadow-sm)}
.row:active{transform:scale(.985)}
.row.W{border-left-color:var(--win)}
.row.L{border-left-color:var(--loss)}
.res{width:32px;height:32px;flex:none;display:grid;place-items:center;font-family:var(--mono);
  font-size:13px;font-weight:700;color:#fff;border-radius:11px}
.res.W{background:var(--win)} .res.L{background:var(--loss)}
.sc{font-family:var(--tech);font-size:19px;font-weight:700;font-variant-numeric:tabular-nums;flex:none;width:60px;color:var(--ink);letter-spacing:.02em}
.info{flex:1;min-width:0}
.info .o{font-size:16px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.info .e{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-top:3px;letter-spacing:.04em}
.rt{flex:none;text-align:right;font-family:var(--mono)}
.rt b{font-size:15px;color:var(--ink);font-weight:700}
.rt small{display:block;font-size:11px;color:var(--ink2);letter-spacing:.05em}
.bar{width:58px;height:7px;background:var(--panel3);margin-top:6px;margin-left:auto;border-radius:999px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--grad);border-radius:999px}
.chev{flex:none;color:var(--dim);font-size:19px}
.more{display:block;width:100%;margin-top:11px;background:var(--panel);
  border:1px solid var(--line);color:var(--amber);font-family:var(--mono);font-size:13px;letter-spacing:.14em;font-weight:600;
  padding:13px;border-radius:16px;cursor:pointer;box-shadow:var(--shadow-sm)}
.more:active{transform:scale(.985)}

/* === 数据统计 === */
.grid{display:grid;gap:11px;grid-template-columns:repeat(auto-fit,minmax(112px,1fr))}
.st{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:16px 17px;
  box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.st::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--grad);opacity:.8}
.st span{display:block;font-family:var(--mono);font-size:11px;color:var(--ink2);letter-spacing:.12em;text-transform:uppercase}
.st b{display:block;font-family:var(--tech);font-size:30px;font-weight:700;margin-top:7px;
  background:var(--grad-num);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:var(--amber);
  font-variant-numeric:tabular-nums;line-height:1}
.st.hl b{background:none;-webkit-text-fill-color:var(--win);color:var(--win)}
.st-sub{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-top:4px;letter-spacing:.04em}

/* === 资料表 === */
.kv{background:var(--panel);border:1px solid var(--line);border-radius:20px;
  box-shadow:var(--shadow-sm);overflow:hidden}
.kv-row{display:flex;gap:12px;padding:12px 17px;border-bottom:1px dashed var(--line-soft);font-size:15px}
.kv-row:last-child{border-bottom:none}
.kv-row span{flex:none;width:96px;font-family:var(--mono);font-size:12px;color:var(--ink2);
  letter-spacing:.06em;padding-top:3px;font-weight:600;text-transform:uppercase}
.kv-row b{font-weight:500;color:var(--ink)}

/* === 比赛地图 === */
.map{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--line-soft);
  border-radius:18px;padding:14px 16px;margin-bottom:11px;box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.map.W{border-left-color:var(--win)} .map.L{border-left-color:var(--loss)}
.map.veto{border-left-color:var(--line-soft);opacity:.55}
.map-h{display:flex;align-items:baseline;gap:9px;margin-bottom:9px;flex-wrap:wrap}
.map-h b{font-size:17px;letter-spacing:.02em;color:var(--ink);font-weight:700}
.map-h em{font-family:var(--mono);font-size:10px;font-style:normal;color:var(--ink2);letter-spacing:.08em;
  background:var(--panel2);padding:3px 9px;border-radius:999px}
.map-en{font-family:var(--mono);font-size:11px;color:var(--dim);margin-left:7px;letter-spacing:.05em}
.map-res{margin-left:auto;font-family:var(--mono);font-size:12px;letter-spacing:.08em;font-weight:600;
  padding:4px 11px;border-radius:999px}
.map-res.W{color:#fff;background:var(--win)} .map-res.L{color:#fff;background:var(--loss)}
.mline{display:flex;align-items:center;gap:10px;margin-top:6px}
.mline .who{font-family:var(--mono);font-size:12px;color:var(--ink2);flex:none;width:62px;letter-spacing:.04em;font-weight:600}
.mline .rounds{font-family:var(--tech);font-size:19px;font-weight:700;flex:none;width:42px;
  text-align:right;font-variant-numeric:tabular-nums;color:var(--ink)}
.mline .halves{font-family:var(--mono);font-size:11px;color:var(--ink2);flex:none;width:76px}
.mline .tbar{flex:1;height:7px;background:var(--panel3);border-radius:999px;overflow:hidden}
.mline .tbar i{display:block;height:100%;background:linear-gradient(90deg,var(--win),#3ED48C);border-radius:999px}
.mline.L .tbar i{background:linear-gradient(90deg,var(--loss),#FF8A96)}

/* === 链接按钮 === */
.links{display:flex;flex-wrap:wrap;gap:10px;margin-top:17px}
.lk{font-family:var(--mono);font-size:12px;letter-spacing:.08em;color:var(--amber);font-weight:600;
  background:var(--panel);border:1px solid var(--line);padding:9px 15px;
  border-radius:999px;box-shadow:var(--shadow-sm)}
.lk:active{transform:scale(.97)}

/* === 队伍格 === */
.team-grid{display:grid;gap:13px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.tc{background:var(--panel);border:1px solid var(--line);border-radius:22px;padding:17px 14px;text-align:center;
  box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.tc::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;background:var(--grad);opacity:.85}
.tc:active{transform:scale(.98)}
.tc .ph{width:80px;height:80px;margin:0 auto 11px}
.tc .ph .av,.tc .ph .av-ph{border-radius:20px}
.tc .pid{font-size:18px;font-weight:800;letter-spacing:.02em;color:var(--ink)}
.tc .pfull{font-family:var(--mono);font-size:11px;color:var(--ink2);margin-top:3px;letter-spacing:.04em}
.tc .prole{font-family:var(--mono);font-size:11px;color:var(--amber);background:var(--amber-bg);
  padding:4px 11px;display:inline-block;margin-top:8px;letter-spacing:.08em;font-weight:600;border-radius:999px}
.tc .pdesc{font-size:12px;color:var(--ink2);margin-top:7px;line-height:1.5}

/* === 准星练习 === */
.xh{display:grid;place-items:center;background:var(--grad-soft);
  border:1px solid var(--line);border-radius:20px;height:140px;margin-top:11px;position:relative;overflow:hidden}
.xh i{position:absolute;background:var(--amber);border-radius:1px}

/* === 页脚 === */
.foot{margin-top:36px;padding-top:20px;border-top:1px solid var(--line-soft);
  font-family:var(--mono);font-size:12px;color:var(--ink2);line-height:1.9;letter-spacing:.04em}
.foot a{color:var(--amber);font-weight:600}
.syncbar{display:flex;align-items:center;gap:9px;margin-top:17px;font-family:var(--mono);font-size:12px;color:var(--ink2);
  background:var(--panel);padding:10px 15px;border:1px solid var(--line);border-radius:999px;
  box-shadow:var(--shadow-sm)}
.syncbar .lk{background:var(--amber-bg);border-color:transparent}
.empty{padding:30px 14px;text-align:center;color:var(--ink2);font-family:var(--mono);font-size:13px;
  background:var(--panel2);border:1px dashed var(--line-soft);border-radius:20px;margin-top:9px}
.back{margin-top:17px}

/* ==== CS 武器背景 ==== */
.arms{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;
  transform:translate3d(0,var(--sy,0px),0);transition:transform .6s cubic-bezier(.22,.9,.3,1)}
.arm{position:absolute;height:auto;color:var(--ink);fill:currentColor;opacity:.09;
  transform:rotate(var(--r,0deg));animation:armDrift var(--d,26s) ease-in-out infinite;animation-delay:var(--dl,0s)}
@keyframes armDrift{0%,100%{transform:rotate(var(--r,0deg)) translate3d(0,0,0)}50%{transform:rotate(var(--r,0deg)) translate3d(0,-18px,0)}}
.arm-1{--r:-9deg;--d:30s;width:60vw;max-width:660px;right:-9vw;top:8vh;opacity:.1;color:var(--amber2)}
.arm-2{--r:8deg;--d:26s;--dl:-6s;width:46vw;max-width:500px;left:-12vw;top:32vh}
.arm-3{--r:-6deg;--d:34s;--dl:-14s;width:42vw;max-width:460px;right:-7vw;top:56vh;opacity:.075}
.arm-4{--r:-16deg;--d:22s;--dl:-3s;width:19vw;max-width:200px;left:5vw;top:16vh;opacity:.07}
.arm-5{--r:14deg;--d:24s;--dl:-9s;width:22vw;max-width:230px;right:8vw;bottom:7vh;opacity:.08;color:var(--cyan)}
.arm-6{--r:-10deg;--d:20s;--dl:-5s;width:12vw;max-width:128px;left:24vw;bottom:14vh;opacity:.07}
.arm-7{--r:18deg;--d:28s;--dl:-11s;width:11vw;max-width:118px;left:6vw;bottom:3vh;opacity:.065}
.hero-arms{position:absolute;right:-8%;bottom:-8%;width:64%;z-index:0;pointer-events:none;
  color:rgba(255,255,255,.92);fill:currentColor;opacity:.14;animation:heroArm 18s ease-in-out infinite}
@keyframes heroArm{0%,100%{transform:translate3d(0,0,0) rotate(0deg)}50%{transform:translate3d(-12px,-9px,0) rotate(-1.6deg)}}

/* ==== 点击反馈 ==== */
.wrap{position:relative;z-index:1}
a,button,.row,.pc,.tc,.lk,.more,.up-c,.st,.map,.prof,.syncbar{
  position:relative;overflow:hidden;
  transition:transform .18s cubic-bezier(.2,.9,.3,1.35),box-shadow .3s ease,background-color .3s ease,border-color .3s ease,color .3s ease}
a:active,button:active,.row:active,.pc:active,.tc:active,.lk:active,.more:active,
.up-c:active,.st:active,.map:active,.prof:active,.pressed{transform:scale(.972)}
.ripple{position:absolute;border-radius:50%;pointer-events:none;z-index:3;
  background:radial-gradient(circle,rgba(91,92,230,.5) 0%,rgba(139,92,246,.25) 42%,rgba(139,92,246,0) 72%);
  animation:ripple .62s cubic-bezier(.2,.7,.3,1) forwards}
@keyframes ripple{from{transform:scale(0);opacity:.95}to{transform:scale(2.4);opacity:0}}
.hitmark{position:absolute;width:24px;height:24px;margin:-12px 0 0 -12px;pointer-events:none;z-index:4;animation:hit .5s cubic-bezier(.2,.8,.3,1) forwards}
.hitmark::before,.hitmark::after{content:"";position:absolute;left:50%;top:50%;width:2px;height:19px;margin:-9.5px 0 0 -1px;background:var(--amber);border-radius:2px}
.hitmark::before{transform:rotate(45deg)}
.hitmark::after{transform:rotate(-45deg)}
@keyframes hit{0%{transform:scale(.35) rotate(-25deg);opacity:0}25%{transform:scale(1) rotate(0deg);opacity:.95}100%{transform:scale(1.35) rotate(8deg);opacity:0}}
@media(hover:hover){
  .row:hover,.pc:hover,.tc:hover,.up-c:hover,.st:hover,.map:hover,.prof:hover{
    transform:translateY(-4px);box-shadow:var(--shadow-lg);border-color:var(--line-soft)}
  .lk:hover{background:var(--amber);color:#fff;border-color:transparent;transform:translateY(-2px);
    box-shadow:0 14px 26px -14px rgba(91,92,230,.75)}
  .more:hover{background:var(--amber-bg);border-color:var(--amber2)}
  .crosshair:hover{transform:rotate(90deg) scale(1.08)}
}
.crosshair{transition:transform .45s cubic-bezier(.2,.9,.3,1.5),box-shadow .3s ease}

/* ==== 过渡动画 ==== */
@keyframes pageIn{from{opacity:0;transform:translateY(14px)}}
@keyframes hudIn{from{opacity:0;transform:translateY(-100%)}}
.wrap{animation:pageIn .55s cubic-bezier(.22,.9,.3,1) backwards}
.hud{animation:hudIn .5s cubic-bezier(.22,.9,.3,1) backwards}
@keyframes riseIn{from{opacity:0;transform:translateY(18px) scale(.99)}to{opacity:1;transform:none}}
.rv{opacity:0}
.rv.in{animation:riseIn .6s cubic-bezier(.22,.9,.3,1) forwards;animation-delay:var(--rd,0s)}
body.leaving .wrap{opacity:0;transform:translateY(-10px);transition:opacity .2s ease,transform .2s ease}
body.leaving .hud,body.leaving .arms{opacity:0;transition:opacity .2s ease}

@media(prefers-reduced-motion:reduce){
  .arm,.hero-arms,.wrap,.hud{animation:none!important}
  .rv{opacity:1!important}
  .ripple,.hitmark{display:none!important}
  *{transition-duration:.01ms!important}
}

/* 移动端微调 */
@media(max-width:380px){
  .hud-in{padding:10px 12px;gap:9px}
  .brand b{font-size:21px}
  .prof .nick{font-size:23px}
  .team{font-size:26px}
  .cd b{font-size:34px}
  .row{padding:12px 12px;gap:10px}
  .res{width:28px;height:28px;font-size:12px}
  .sc{width:52px;font-size:16px}
}"""

# ===== CS 经典武器剪影（内联 SVG sprite，纯几何图形绘制）=====
ARMS_SPRITE = """<svg id="armsSprite" aria-hidden="true"
  style="position:absolute;width:0;height:0;overflow:hidden">
  <symbol id="w-awp" viewBox="0 0 240 90"><g fill="currentColor">
    <path d="M2 30 L2 58 L34 54 L62 50 L96 48 L96 29 Z"/>
    <path d="M46 29 L80 21 L96 21 L96 29 Z"/>
    <rect x="96" y="26" width="62" height="22" rx="3"/>
    <rect x="106" y="12" width="52" height="13" rx="4"/>
    <rect x="98" y="13" width="11" height="12" rx="3"/>
    <rect x="152" y="10" width="17" height="18" rx="5"/>
    <rect x="112" y="24" width="6" height="5"/><rect x="146" y="24" width="6" height="5"/>
    <rect x="156" y="34" width="74" height="8"/><rect x="224" y="31" width="14" height="14" rx="2"/>
    <path d="M112 48 L134 48 L138 70 L116 70 Z"/><path d="M98 48 L114 48 L110 70 L96 68 Z"/>
    <path d="M120 52 L127 52 L125 60 L118 60 Z"/>
    <path d="M186 42 L193 42 L205 68 L199 68 Z"/><path d="M176 42 L182 42 L172 68 L166 68 Z"/>
    <rect x="140" y="49" width="15" height="7" rx="3"/>
  </g></symbol>
  <symbol id="w-ak" viewBox="0 0 240 90"><g fill="currentColor">
    <path d="M2 34 L92 28 L92 48 L46 50 L2 50 Z"/>
    <rect x="88" y="25" width="36" height="24" rx="2"/>
    <rect x="112" y="19" width="13" height="8" rx="1"/>
    <rect x="122" y="30" width="48" height="14" rx="3"/>
    <rect x="122" y="22" width="42" height="7" rx="2"/>
    <rect x="166" y="32" width="58" height="7"/><rect x="216" y="30" width="11" height="11" rx="2"/>
    <rect x="200" y="20" width="7" height="13"/>
    <path d="M100 49 L124 49 C136 60 142 72 142 84 L120 82 C118 70 110 58 100 49 Z"/>
    <path d="M86 49 L102 49 L98 72 L84 70 Z"/>
    <path d="M104 53 L111 53 L109 61 L103 61 Z"/>
    <rect x="118" y="29" width="16" height="6" rx="2"/>
  </g></symbol>
  <symbol id="w-m4" viewBox="0 0 240 90"><g fill="currentColor">
    <path d="M2 24 L12 27 L34 30 L34 50 L12 50 L2 47 Z"/>
    <rect x="34" y="32" width="52" height="10"/>
    <rect x="86" y="25" width="38" height="22" rx="2"/>
    <rect x="96" y="17" width="24" height="8" rx="2"/>
    <rect x="122" y="29" width="52" height="13" rx="3"/>
    <rect x="170" y="32" width="54" height="7"/><rect x="218" y="30" width="11" height="11" rx="2"/>
    <rect x="196" y="18" width="6" height="14"/>
    <path d="M100 47 L122 47 L130 82 L108 80 Z"/>
    <path d="M86 47 L101 47 L96 70 L82 68 Z"/>
    <path d="M104 51 L111 51 L109 59 L103 59 Z"/>
  </g></symbol>
  <symbol id="w-deagle" viewBox="0 0 170 100"><g fill="currentColor">
    <rect x="20" y="32" width="100" height="14" rx="3"/>
    <rect x="112" y="34" width="18" height="12" rx="2"/>
    <rect x="104" y="26" width="6" height="7"/><rect x="30" y="26" width="8" height="7"/>
    <rect x="42" y="46" width="70" height="8" rx="2"/>
    <path d="M66 52 L88 52 L72 96 L52 96 Z"/>
    <path d="M88 52 C104 52 109 60 101 68 L93 66 C97 60 95 56 88 56 Z"/>
    <path d="M94 56 L101 56 L99 65 L93 65 Z"/>
    <path d="M20 30 L32 26 L36 36 L22 38 Z"/>
  </g></symbol>
  <symbol id="w-knife" viewBox="0 0 150 100"><g fill="currentColor">
    <path d="M50 38 C88 46 112 42 128 20 C116 52 88 68 50 64 Z"/>
    <path d="M46 32 L56 64 L32 72 C20 74 14 64 20 54 Z"/>
    <circle cx="18" cy="58" r="9.5" fill="none" stroke="currentColor" stroke-width="4.5"/>
  </g></symbol>
  <symbol id="w-he" viewBox="0 0 110 130"><g fill="currentColor">
    <rect x="24" y="44" width="64" height="78" rx="30"/>
    <rect x="40" y="32" width="30" height="14" rx="4"/>
    <path d="M62 28 L94 12 L98 24 L66 40 Z"/>
    <circle cx="54" cy="15" r="9" fill="none" stroke="currentColor" stroke-width="4.5"/>
  </g></symbol>
  <symbol id="w-flash" viewBox="0 0 110 130"><g fill="currentColor">
    <rect x="30" y="42" width="52" height="80" rx="11"/>
    <rect x="42" y="30" width="28" height="13" rx="3"/>
    <path d="M62 26 L92 11 L96 22 L66 37 Z"/>
    <circle cx="55" cy="14" r="8.5" fill="none" stroke="currentColor" stroke-width="4.5"/>
  </g></symbol>
</svg>"""

ARMS_BG = """<div class="arms" aria-hidden="true">
  <svg class="arm arm-1" viewBox="0 0 240 90"><use href="#w-awp"/></svg>
  <svg class="arm arm-2" viewBox="0 0 240 90"><use href="#w-ak"/></svg>
  <svg class="arm arm-3" viewBox="0 0 240 90"><use href="#w-m4"/></svg>
  <svg class="arm arm-4" viewBox="0 0 170 100"><use href="#w-deagle"/></svg>
  <svg class="arm arm-5" viewBox="0 0 150 100"><use href="#w-knife"/></svg>
  <svg class="arm arm-6" viewBox="0 0 110 130"><use href="#w-he"/></svg>
  <svg class="arm arm-7" viewBox="0 0 110 130"><use href="#w-flash"/></svg>
</div>"""

CORE_JS = r"""
const REPO = '__REPO__';
let D = JSON.parse(document.getElementById('niko-data').textContent);
let FRESH = null;
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const params = new URLSearchParams(location.search);

function bj(iso){
  if(!iso) return '';
  const d = new Date(iso), p = n => String(n).padStart(2,'0');
  const wk = ['周日','周一','周二','周三','周四','周五','周六'][d.getDay()];
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${wk} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function boText(bo){ return {Bo1:'单图决胜',Bo3:'三局两胜',Bo5:'五局三胜'}[bo] || bo || ''; }
/* 地图名中文化（保留英文原名，CS 玩家两种叫法都在用） */
const MAP_ZH = {'Dust II':'炙热沙城 II','Mirage':'荒漠迷城','Inferno':'炼狱小镇',
  'Nuke':'核子危机','Ancient':'远古遗迹','Anubis':'阿努比斯神庙',
  'Train':'列车停放站','Overpass':'死亡游乐园','Vertigo':'殒命大厦'};
function mapName(m){
  const zh = MAP_ZH[m];
  return zh ? `${esc(zh)}<span class="map-en">${esc(m)}</span>` : esc(m);
}
function tierText(t){ return String(t||'').replace('S-Tier','S 级').replace('A-Tier','A 级'); }
function ini(id){ return esc(String(id||'?').slice(0,2).toUpperCase()); }

/* 头像：有图用图，无图或加载失败用首两位字母兜底 */
function avatar(src, name, cls){
  const ph = `<div class="av-ph av-ph-${cls}">${ini(name)}</div>`;
  if(!src) return ph;
  // onerror 里的 HTML 必须把双引号转成实体，否则会提前闭合属性
  const fb = ph.replace(/"/g, '&quot;').replace(/\n/g, '');
  return `<img class="av av-${cls}" src="${esc(src)}" alt="${esc(name)}"
    onerror="this.outerHTML='${fb}'">`;
}
function dataOf(){ return FRESH || D; }

async function pullNewest(){
  const urls = [];
  if(REPO && REPO !== '__REPO__'){
    urls.push(['https://cdn.jsdelivr.net/gh/' + REPO + '@main/data.json', 'jsDelivr']);
    urls.push(['https://raw.githubusercontent.com/' + REPO + '/main/data.json', 'GitHub 直连']);
  }
  urls.push(['./data.json', '同源']);
  for(const [u, tag] of urls){
    try{
      const r = await fetch(u + '?t=' + Date.now(), {cache:'no-store'});
      if(!r.ok) continue;
      const d = await r.json();
      if(d && d.recent_matches){ FRESH = d; return tag; }
    }catch(e){}
  }
  return null;
}
async function sync(labelEl){
  const tag = await pullNewest();
  if(labelEl) labelEl.textContent = tag
    ? `● 已同步最新数据（${tag}）`
    : '○ 离线缓存（未能联网）';
  if(tag) { const cur = location.hash; }
  return tag;
}
function startCountdown(target, onChange){
  const el = {
    d: document.getElementById('cdD'), h: document.getElementById('cdH'),
    m: document.getElementById('cdM'), s: document.getElementById('cdS')
  };
  if(!el.d) return;
  const tick = () => {
    let diff = target ? (new Date(target) - Date.now()) / 1000 : 0;
    if(diff < 0) diff = 0;
    const dd = Math.floor(diff / 86400), hh = Math.floor(diff % 86400 / 3600),
          mm = Math.floor(diff % 3600 / 60), ss = Math.floor(diff % 60);
    el.d.textContent = dd; el.h.textContent = String(hh).padStart(2,'0');
    el.m.textContent = String(mm).padStart(2,'0'); el.s.textContent = String(ss).padStart(2,'0');
    const st = document.getElementById('statusTxt'), dot = document.getElementById('dot');
    if(st && diff <= 0){ st.textContent = '进行中'; dot.classList.add('live'); }
    else if(st){ st.textContent = '待战'; }
  };
  tick(); setInterval(tick, 1000);
}
function drawCrosshair(x, boxId){
  const box = document.getElementById(boxId || 'xhBox');
  if(!box || !x || !x.style) return;
  const len = 6 + Number(x.size || 1) * 2;
  const th = Number(x.thickness || 1);
  const gap = Math.abs(Number(x.gap || 0));
  const c = document.createElement('div');
  c.style.cssText = 'position:relative;width:0;height:0';
  const mk = () => { const i = document.createElement('i'); return i; };
  // 用四个小方块模拟 CS style 4 准星
  [[0,-gap-len],[0,gap],[-gap-len,0],[gap,0]].forEach(([lx,ly]) => {
    const i = mk();
    i.style.width = (lx === 0 ? th : len) + 'px';
    i.style.height = (lx === 0 ? len : th) + 'px';
    i.style.left = lx + 'px';
    i.style.top = ly + 'px';
    c.appendChild(i);
  });
  box.innerHTML = ''; box.appendChild(c);
}
"""

INDEX_JS = CORE_JS + r"""
let LIMIT = 12;
function matchRow(m, maxR){
  const rs = (m.niko && m.niko.ratings) || [];
  const avg = rs.length ? rs.reduce((a,b)=>a+b,0)/rs.length : null;
  return `<a class="row ${m.result}" href="match.html?id=${encodeURIComponent(m.id)}">
    <div class="res ${m.result}">${m.result === 'W' ? '胜' : '负'}</div>
    <div class="sc">${esc(m.score)}</div>
    <div class="info">
      <div class="o">${esc(m.opponent)}</div>
      <div class="e">${esc(m.event)} · ${boText(m.bo)}</div>
    </div>
    <div class="rt">${avg !== null
      ? `<b>${avg.toFixed(2)}</b><small>评分</small>
         <div class="bar"><i style="width:${Math.min(100, avg/maxR*100)}%"></i></div>`
      : `<small style="padding-top:6px">—</small>`}</div>
    <div class="chev">›</div>
  </a>`;
}

function render(){
  const d = dataOf(), P = d.player, YS = d.year_stats, LIST = d.recent_matches, SQ = d.squad || [];
  const c = P.career || {}, g = P.gear || {}, x = P.crosshair || {};
  const maxR = Math.max(...LIST.flatMap(m => (m.niko && m.niko.ratings) || [0]), 1);

  let heroTag, heroInner, target = null;
  if(d.next_match){
    heroTag = '下一场比赛'; target = d.next_match.datetime;
    heroInner = `<div class="vs"><div class="team">FALCONS</div><div class="vs-mid">VS</div>
      <div class="team">${esc(d.next_match.opponent)}</div></div>
      <div class="hero-sub">${esc(d.next_match.event)} · ${boText(d.next_match.bo)}</div>`;
  }else if((d.upcoming_tournaments||[]).length){
    const t = d.upcoming_tournaments[0];
    heroTag = '下一站赛事'; target = t.start;
    heroInner = `<div class="vs"><div class="team">${esc(t.name)}</div></div>
      <div class="hero-sub">${esc(t.date_text)} · ${tierText(t.tier)}</div>
      <div class="hero-note">对阵尚未公布 · 已确认参赛</div>`;
  }else{
    heroTag = '暂无赛程';
    heroInner = `<div class="vs"><div class="team tbd">待定</div></div>
      <div class="hero-sub">暂时没有已公布的比赛</div>`;
  }

  const upHtml = (d.upcoming_tournaments||[]).map(t => `
    <div class="up-c">
      <div class="tier">${tierText(t.tier)}</div>
      <div class="n">${esc(t.name)}</div>
      <div class="d">${esc(t.date_text)}</div>
      <div class="m">${new Date(t.start).getUTCFullYear()} 年 · 已确认参赛</div>
    </div>`).join('') || '<div class="empty">暂无已公布赛程</div>';

  const shown = LIST.slice(0, LIMIT);
  const btn = LIST.length > LIMIT
    ? `<button class="more" id="moreBtn">展开全部 ${LIST.length} 场</button>` : '';
  const mates = SQ.filter(p => p.role !== '教练');
  const mateHtml = mates.map(p => `
    <a class="pc" href="player.html?id=${encodeURIComponent(p.id)}">
      <div class="ph">${avatar(p.photo, p.id, 'lg')}</div>
      <div class="pid">${esc(p.id)}</div>
      <div class="prole">${esc(p.role)}</div>
      <div class="pnat">${esc(p.nationality)}${p.age ? ' · ' + p.age + '岁' : ''}</div>
    </a>`).join('');

  const stats = [
    ['近三个月评分', P.rating_3m.toFixed(2), true],
    ['世界排名', '#' + P.team_rank, false],
    ['近三个月图数', P.maps_3m, false],
    ['生涯击杀', (c.kills||0).toLocaleString('en-US'), false],
    ['生涯 K/D', (c.kd||0).toFixed(2), false],
    ['生涯 ADR', c.adr, false],
    ['爆头率', (c.hs||0) + '%', false],
    ['生涯 MVP', c.mvp, false],
    ['TOP20 次数', c.top20, false],
    ['生涯奖金', P.winnings, false],
  ].map(([k,v,hl]) => `<div class="st${hl?' hl':''}"><span>${k}</span><b>${v}</b></div>`).join('');

  const mj = P.major || {};
  const majorHtml = mj.title ? `
    <div class="st hl" style="grid-column:1/-1">
      <span>MAJOR 冠军</span>
      <b style="font-size:15px">${esc(mj.title)}</b>
      <div class="st-sub">${esc(mj.date||'')} ${esc(mj.result||'')}</div>
    </div>` : '';

  const gearRows = Object.entries({
    '鼠标': g.mouse, '鼠标垫': g.mousepad, '游戏内灵敏度': g.sens, 'DPI': g.dpi,
    'eDPI': g.edpi, '轮询率': g.polling, '显示器': g.monitor, '刷新率': g.refresh,
    '分辨率': g.resolution, '键盘': g.keyboard, '耳机': g.headset
  }).filter(([,v]) => v).map(([k,v]) =>
    `<div class="kv-row"><span>${k}</span><b>${esc(v)}</b></div>`).join('');

  const xHtml = x.style ? `
    <div class="xh" id="xhBox"></div>
    <div class="kv" style="margin-top:10px">
      <div class="kv-row"><span>参数</span><b>样式 ${esc(x.style)} · 长度 ${esc(x.size)} · 粗细 ${esc(x.thickness)} · 间隙 ${esc(x.gap)}</b></div>
      <div class="kv-row"><span>颜色</span><b>${esc(x.color)} 号${x.outline==='No'?' · 无描边':''}${x.dot==='No'?' · 无中心点':''}</b></div>
      <div class="kv-row"><span>分享码</span><b style="font-family:var(--mono);font-size:11px">${esc(P.crosshair_sharecode||'—')}</b></div>
    </div>` : '<div class="empty">暂无准星数据</div>';

  document.getElementById('app').innerHTML = `
  <div class="hero">
    <div class="hero-top"><span class="tag">${heroTag}</span></div>
    <div class="hero-body">
      ${heroInner}
      <div class="cd">
        <div><b id="cdD">--</b><span>天</span></div>
        <div><b id="cdH">--</b><span>时</span></div>
        <div><b id="cdM">--</b><span>分</span></div>
        <div><b id="cdS">--</b><span>秒</span></div>
      </div>
      <div class="hero-sub">${target ? '开赛（北京时间）：' + bj(target) : ''}</div>
    </div>
  </div>

  <a class="prof" href="player.html?id=${encodeURIComponent(P.nick)}">
    ${avatar(P.photo, P.nick, 'xl')}
    <div class="prof-txt">
      <div class="nick">${esc(P.nick)}</div>
      <div class="full">${esc(P.full_name)}</div>
      <div class="meta">${esc(P.team)} · ${esc(P.role)} · ${esc(P.country)}${P.age?' · '+P.age+' 岁':''}</div>
    </div>
    <div class="prof-link">详情 ›</div>
  </a>

  <div class="sec">
    <div class="sec-h"><b>现役队友</b><i></i><a href="team.html"><em>查看队伍 ›</em></a></div>
    <div class="hint">← 左右滑动查看全部 ${mates.length} 人 →</div>
    <div class="scroller">${mateHtml}</div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>未来赛程</b><i></i><em>${(d.upcoming_tournaments||[]).length} 项赛事</em></div>
    <div class="up">${upHtml}</div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>${esc(YS.span)}战绩</b><i></i><em>${YS.wins} 胜 ${YS.losses} 负</em></div>
    <div class="rows" id="recList">${shown.map(m => matchRow(m, maxR)).join('')}${btn}</div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>赛季概览</b><i></i><em>${esc(YS.from)} 至 ${esc(YS.to)}</em></div>
    <div class="grid">
      <div class="st"><span>系列赛总数</span><b>${YS.matches}</b></div>
      <div class="st hl"><span>系列赛胜率</span><b>${YS.win_rate}%</b></div>
      <div class="st"><span>参赛站数</span><b>${YS.events}</b></div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>选手数据</b><i></i><em>来源 HLTV</em></div>
    <div class="grid">${stats}${majorHtml}</div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>外设与设置</b><i></i><em>来源 Liquipedia</em></div>
    <div class="kv">${gearRows || '<div class="empty">暂无数据</div>'}</div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>准星</b><i></i><em>${P.crosshair_sharecode?'含分享码':''}</em></div>
    ${xHtml}
  </div>

  <div class="syncbar">
    <span id="liveStatus">○ 正在获取最新数据…</span>
    <button class="lk" id="refreshBtn" style="cursor:pointer">↻ 刷新</button>
  </div>
  <div class="foot">
    数据来源：Liquipedia Counter-Strike Wiki（CC BY-SA 3.0）· HLTV.org<br>
    时间均已换算为北京时间（UTC+8）；个人评分仅覆盖已逐场核对的比赛，其余显示「—」。<br>
    点任意一场比赛可看逐图详情。最近更新：__UPDATED__
  </div>`;

  drawCrosshair(x);
  startCountdown(target);
  const mb = document.getElementById('moreBtn');
  if(mb) mb.onclick = () => {
    const all = LIST.length;
    LIMIT = LIMIT >= all ? 12 : all;
    render();
    sync(document.getElementById('liveStatus'));
  };
  const rb = document.getElementById('refreshBtn');
  if(rb) rb.onclick = async () => {
    document.getElementById('liveStatus').textContent = '○ 正在刷新…';
    const tag = await pullNewest();
    render();
    sync(document.getElementById('liveStatus'));
  };
}

/* ===== 视觉增强：武器背景 / 点击反馈 / 过渡动画 ===== */
const TAP_SEL = 'a,button,.row,.pc,.tc,.lk,.more,.up-c,.st,.map,.prof,.hero';
const SVGNS = 'http://www.w3.org/2000/svg';
const NO_ANIM = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* hero 卡片里放一把 AWP 水印 */
function fxArms(){
  document.querySelectorAll('.hero').forEach(h => {
    if(h.querySelector('.hero-arms')) return;
    const s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('class', 'hero-arms');
    s.setAttribute('viewBox', '0 0 240 90');
    s.setAttribute('aria-hidden', 'true');
    const u = document.createElementNS(SVGNS, 'use');
    u.setAttribute('href', '#w-awp');
    s.appendChild(u); h.appendChild(s);
  });
}
/* 滚动渐显（逐块错峰） */
function fxReveal(){
  const els = document.querySelectorAll('#app > *');
  if(!els.length) return;
  if(NO_ANIM || !('IntersectionObserver' in window)){
    els.forEach(e => { e.classList.add('rv','in'); }); return;
  }
  const io = new IntersectionObserver(ents => {
    ents.forEach(en => {
      if(en.isIntersecting){ en.target.classList.add('in'); io.unobserve(en.target); }
    });
  }, {rootMargin:'0px 0px -6% 0px', threshold:.03});
  let i = 0;
  els.forEach(e => {
    e.classList.add('rv');
    e.style.setProperty('--rd', (Math.min(i, 5) * 0.07) + 's'); i++;
    io.observe(e);
  });
}
/* 点击 = 涟漪 + CS 命中标记 + 按压回弹（含 iOS 兜底） */
function fxRipple(){
  const release = () => document.querySelectorAll('.pressed')
    .forEach(e => e.classList.remove('pressed'));
  document.addEventListener('pointerup', release, {passive:true});
  document.addEventListener('pointercancel', release, {passive:true});
  window.addEventListener('blur', release);
  document.addEventListener('pointerdown', e => {
    const t = e.target.closest ? e.target.closest(TAP_SEL) : null;
    if(!t) return;
    t.classList.add('pressed');
    setTimeout(() => t.classList.remove('pressed'), 320);
    if(NO_ANIM) return;
    const r = t.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const size = Math.max(r.width, r.height) * 1.1;
    const sp = document.createElement('span');
    sp.className = 'ripple';
    sp.style.cssText = 'width:' + size + 'px;height:' + size + 'px;left:'
      + (x - size / 2) + 'px;top:' + (y - size / 2) + 'px';
    const hm = document.createElement('i');
    hm.className = 'hitmark';
    hm.style.cssText = 'left:' + x + 'px;top:' + y + 'px';
    t.appendChild(sp); t.appendChild(hm);
    setTimeout(() => { sp.remove(); hm.remove(); }, 640);
  }, {passive:true});
}
/* 武器层轻微视差 */
function fxParallax(){
  const arms = document.querySelector('.arms');
  if(!arms || NO_ANIM) return;
  let raf = 0;
  addEventListener('scroll', () => {
    if(raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      arms.style.setProperty('--sy', (scrollY * -0.035).toFixed(1) + 'px');
    });
  }, {passive:true});
}
/* 站内跳转淡出过渡 */
function fxLeave(){
  document.addEventListener('click', e => {
    if(e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest ? e.target.closest('a[href]') : null;
    if(!a || a.target === '_blank' || a.hasAttribute('download')) return;
    const href = a.getAttribute('href') || '';
    if(/^(https?:)?\/\//i.test(href) && new URL(href, location.href).origin !== location.origin) return;
    const u = new URL(href, location.href);
    if(u.pathname.split('/').pop() === location.pathname.split('/').pop() && u.hash) return;
    if(!/\.html?($|\?)/i.test(u.pathname)) return;
    e.preventDefault();
    document.body.classList.add('leaving');
    setTimeout(() => { location.href = u.href; }, 200);
  }, true);
}
let __fxBound = false;
function fx(){
  fxArms(); fxReveal();
  if(__fxBound) return;
  __fxBound = true;
  fxRipple(); fxParallax(); fxLeave();
  const app = document.getElementById('app');
  if(app && 'MutationObserver' in window){
    let t = 0;
    new MutationObserver(() => {
      clearTimeout(t); t = setTimeout(() => { fxArms(); fxReveal(); }, 30);
    }).observe(app, {childList:true});
  }
  /* 兜底：2.5 秒后还没显形的一律显示，避免任何情况下白屏 */
  setTimeout(() => document.querySelectorAll('.rv:not(.in)')
    .forEach(e => e.classList.add('in')), 2500);
}

async function boot(){
  await pullNewest();
  render();
  fx();
  sync(document.getElementById('liveStatus'));
}
"""

MATCH_JS = CORE_JS + r"""
function render(){
  const d = dataOf(), id = params.get('id');
  const m = d.recent_matches.find(x => x.id === id);
  const app = document.getElementById('app');
  if(!m){
    app.innerHTML = `<div class="back"><a class="lk" href="index.html">‹ 返回</a></div>
      <div class="empty" style="margin-top:30px">找不到这场比赛<br><br>
      <a class="lk" href="index.html">返回首页</a></div>`;
    return;
  }
  const played = (m.maps||[]).filter(p => !p.vetoed);
  const vetoed = (m.maps||[]).filter(p => p.vetoed);
  const rs = (m.niko && m.niko.ratings) || [];
  const avg = rs.length ? rs.reduce((a,b)=>a+b,0)/rs.length : null;

  const maxRound = Math.max(...played.map(p =>
    Math.max(Number(p.falcons.rounds)||0, Number(p.opponent.rounds)||0)), 13);

  const mapHtml = played.map((p, i) => {
    const fw = p.falcons_win;
    const fr = Number(p.falcons.rounds)||0, orr = Number(p.opponent.rounds)||0;
    return `<div class="map ${fw ? 'W' : 'L'}">
      <div class="map-h">
        <b>第 ${i+1} 图 · ${mapName(p.map)}</b>
        <em>${fr + orr > 24 ? '加时 · ' : ''}共 ${fr + orr} 回合</em>
        <div class="map-res ${fw?'W':'L'}">${fw ? '胜' : '负'} ${fr}-${orr}</div>
      </div>
      <div class="mline ${fw?'':'L'}">
        <div class="who">${esc(d.player.nick)}</div>
        <div class="rounds">${fr}</div>
        <div class="tbar"><i style="width:${Math.min(100, fr/maxRound*100)}%"></i></div>
        <div class="halves">进攻 ${esc(p.falcons.t)||'—'} / 防守 ${esc(p.falcons.ct)||'—'}</div>
      </div>
      <div class="mline ${fw?'L':''}">
        <div class="who">${esc(m.opponent)}</div>
        <div class="rounds">${orr}</div>
        <div class="tbar"><i style="width:${Math.min(100, orr/maxRound*100)}%"></i></div>
        <div class="halves">进攻 ${esc(p.opponent.t)||'—'} / 防守 ${esc(p.opponent.ct)||'—'}</div>
      </div>
    </div>`;
  }).join('') || '<div class="empty">暂无逐图数据</div>';

  const vetoHtml = vetoed.length ? `
    <div class="sec">
      <div class="sec-h"><b>未选用地图</b><i></i><em>双方已禁用</em></div>
      <div class="rows">${vetoed.map(p => `
        <div class="map veto" style="margin-bottom:0">
          <div class="map-h"><b>${mapName(p.map)}</b><em>Bo${(m.maps||[]).length>3?3:1} 未启用</em></div>
        </div>`).join('')}</div>
    </div>` : '';

  const links = [];
  if(m.links && m.links.hltv_match) links.push([m.links.hltv_match, 'HLTV 全场统计']);
  (m.links && m.links.hltv_maps || []).forEach(g =>
    links.push([g.url, `第 ${g.game} 图 HLTV 数据`]));
  (m.links && m.links.vods || []).forEach(v =>
    links.push([v.url, `第 ${v.game} 图录像`]));
  const linkHtml = links.length
    ? `<div class="links">${links.map(([u,t]) =>
        `<a class="lk" href="${esc(u)}" target="_blank" rel="noopener">${esc(t)} ↗</a>`).join('')}</div>`
    : '';

  app.innerHTML = `
  <div class="back"><a class="lk" href="index.html">‹ 返回首页</a></div>
  <div class="hero">
    <div class="hero-top"><span class="tag">比赛详情</span></div>
    <div class="hero-body">
      <div class="vs">
        <div class="team">FALCONS</div>
        <div class="vs-mid">${esc(m.score)}</div>
        <div class="team">${esc(m.opponent)}</div>
      </div>
      <div class="hero-sub">${esc(bj(m.date))}</div>
      <div class="hero-note">${m.result === 'W' ? '取胜' : '落败'} · ${boText(m.bo)} · ${esc(m.event)}</div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>逐图详情</b><i></i><em>${played.length} 张地图</em></div>
    ${mapHtml}
  </div>

  ${vetoHtml}

  <div class="sec">
    <div class="sec-h"><b>${esc(d.player.nick)} 本场数据</b><i></i><em>HLTV</em></div>
    <div class="grid">
      <div class="st"><span>系列赛评分</span><b>${avg !== null ? avg.toFixed(2) : '—'}</b></div>
      ${(m.niko||{}).kd ? `<div class="st"><span>击杀 / 死亡</span><b>${esc(m.niko.kd)}</b></div>` : ''}
      ${(m.niko||{}).adr ? `<div class="st"><span>场均伤害 ADR</span><b>${esc(m.niko.adr)}</b></div>` : ''}
    </div>
    ${(m.niko||{}).note ? `<div class="kv" style="margin-top:10px">
      <div class="kv-row"><span>备注</span><b>${esc(m.niko.note)}</b></div></div>` : ''}
    ${!avg && !(m.niko||{}).kd ? '<div class="empty">本场尚未核对个人数据</div>' : ''}
  </div>

  ${linkHtml ? `<div class="sec"><div class="sec-h"><b>相关链接</b><i></i><em>跳转外部站点</em></div>${linkHtml}</div>` : ''}

  <div class="syncbar"><span id="liveStatus">○ 正在获取最新数据…</span></div>
  <div class="foot">
    地图回合按「进攻方 / 防守方」拆分；加时回合不计入该项统计。<br>
    数据来源：Liquipedia（CC BY-SA 3.0）。最近更新：__UPDATED__
  </div>`;
}

async function boot(){ await pullNewest(); render(); sync(document.getElementById('liveStatus')); }
"""

TEAM_JS = CORE_JS + r"""
function render(){
  const d = dataOf(), P = d.player, SQ = d.squad || [];
  const app = document.getElementById('app');
  const cards = SQ.map(p => `
    <a class="tc" href="player.html?id=${encodeURIComponent(p.id)}">
      <div class="ph">${avatar(p.photo, p.id, 'lg')}</div>
      <div class="pid">${esc(p.id)}</div>
      <div class="pfull">${esc(p.name || '')}</div>
      <div class="prole">${esc(p.role)}</div>
      <div class="pdesc">${esc(p.note || '')}</div>
    </a>`).join('') || '<div class="empty">暂无阵容数据</div>';

  app.innerHTML = `
  <div class="back"><a class="lk" href="index.html">‹ 返回首页</a></div>
  <div class="hero">
    <div class="hero-top"><span class="tag">所属战队</span></div>
    <div class="hero-body">
      <div class="vs"><div class="team">${esc(P.team)}</div></div>
      <div class="hero-sub">${esc(P.country)} · 世界排名 #${esc(P.team_rank)} · ${esc(P.team_points)} 分</div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>成员</b><i></i><em>${SQ.length} 人</em></div>
    <div class="team-grid">${cards}</div>
  </div>

  <div class="sec">
    <div class="sec-h"><b>战队信息</b><i></i><em>Liquipedia</em></div>
    <div class="kv">
      <div class="kv-row"><span>战队名</span><b>${esc(P.team)}</b></div>
      <div class="kv-row"><span>当前世界排名</span><b>第 ${esc(P.team_rank)} 位（${esc(P.team_points)} 分）</b></div>
      <div class="kv-row"><span>核心选手</span><b>${esc(P.nick)}</b></div>
      <div class="kv-row"><span>加入时间</span><b>${esc(P.joined || '—')}</b></div>
      <div class="kv-row"><span>阵容</span><b>${SQ.map(p => esc(p.id)).join(' · ')}</b></div>
      <div class="kv-row"><span>资料页</span><b><a href="https://liquipedia.net/counterstrike/Team_Falcons"
        target="_blank" rel="noopener" style="color:var(--amber)">Liquipedia ↗</a></b></div>
    </div>
  </div>

  <div class="syncbar"><span id="liveStatus">○ 正在获取最新数据…</span></div>
  <div class="foot">阵容与选手资料抓取自 Liquipedia（CC BY-SA 3.0）。最近更新：__UPDATED__</div>`;
}

async function boot(){ await pullNewest(); render(); sync(document.getElementById('liveStatus')); }
"""

PLAYER_JS = CORE_JS + r"""
function render(){
  const d = dataOf(), id = params.get('id') || d.player.nick;
  const app = document.getElementById('app');
  const p = (d.squad || []).find(x => x.id === id);
  if(!p){
    app.innerHTML = `<div class="back"><a class="lk" href="index.html">‹ 返回</a></div>
      <div class="empty" style="margin-top:30px">没有这位选手的资料<br><br>
      <a class="lk" href="team.html">查看阵容</a></div>`;
    return;
  }
  const isNiko = p.id === d.player.nick;
  const P = d.player, c = P.career || {}, g = P.gear || {}, x = P.crosshair || {};

  const rows = [
    ['本名', p.name], ['国籍', p.nationality], ['出生', p.born],
    ['年龄', p.age ? p.age + ' 岁' : ''], ['队内角色', p.role],
    ['选手状态', p.status], ['职业年限', p.years_active], ['所属战队', p.team],
    ['生涯奖金', p.winnings], ['昵称', p.nicknames], ['曾用 ID', p.alt_ids]
  ].filter(([,v]) => v).map(([k,v]) =>
    `<div class="kv-row"><span>${k}</span><b>${esc(v)}</b></div>`).join('');

  const histHtml = (p.history || []).length ? `
    <div class="sec">
      <div class="sec-h"><b>战队经历</b><i></i><em>近期 ${p.history.length} 段</em></div>
      <div class="kv">${p.history.slice().reverse().map(h =>
        `<div class="kv-row"><span>${esc(h.from)}</span><b>${esc(h.team)}
          <span style="color:var(--dim);font-family:var(--mono);font-size:11px">
          （至 ${esc(h.to)}）</span></b></div>`).join('')}</div>
    </div>` : '';

  const nikoExtra = isNiko ? `
    <div class="sec">
      <div class="sec-h"><b>生涯数据</b><i></i><em>HLTV</em></div>
      <div class="grid">
        <div class="st hl"><span>近三个月评分</span><b>${P.rating_3m.toFixed(2)}</b></div>
        <div class="st"><span>世界排名</span><b>#${esc(P.team_rank)}</b></div>
        <div class="st"><span>总击杀</span><b>${(c.kills||0).toLocaleString('en-US')}</b></div>
        <div class="st"><span>生涯 K/D</span><b>${(c.kd||0).toFixed(2)}</b></div>
        <div class="st"><span>生涯 ADR</span><b>${esc(c.adr)}</b></div>
        <div class="st"><span>每回合击杀</span><b>${esc(c.kpr)}</b></div>
        <div class="st"><span>爆头率</span><b>${esc(c.hs)}%</b></div>
        <div class="st"><span>出场地图数</span><b>${(c.maps||0).toLocaleString('en-US')}</b></div>
        <div class="st"><span>生涯 MVP</span><b>${esc(c.mvp)}</b></div>
        <div class="st"><span>TOP20 次数</span><b>${esc(c.top20)}</b></div>
      </div>
      ${(P.major||{}).title ? `<div class="kv" style="margin-top:10px">
        <div class="kv-row"><span>MAJOR</span><b>${esc(P.major.title)}
          <span style="color:var(--dim);font-family:var(--mono);font-size:11px">${esc(P.major.result||'')}</span></b></div>
        ${P.major.note ? `<div class="kv-row"><span>备注</span><b>${esc(P.major.note)}</b></div>` : ''}
      </div>` : ''}
    </div>
    <div class="sec">
      <div class="sec-h"><b>外设与设置</b><i></i><em>Liquipedia</em></div>
      <div class="kv">${Object.entries({
        '鼠标': g.mouse, '鼠标垫': g.mousepad, '游戏内灵敏度': g.sens, 'DPI': g.dpi,
        'eDPI': g.edpi, '轮询率': g.polling, '显示器': g.monitor, '刷新率': g.refresh,
        '分辨率': g.resolution, '键盘': g.keyboard, '耳机': g.headset
      }).filter(([,v]) => v).map(([k,v]) =>
        `<div class="kv-row"><span>${k}</span><b>${esc(v)}</b></div>`).join('')}</div>
    </div>
    <div class="sec">
      <div class="sec-h"><b>准星</b><i></i><em>${P.crosshair_sharecode?'含分享码':''}</em></div>
      <div class="xh" id="xhBox"></div>
      <div class="kv" style="margin-top:10px">
        <div class="kv-row"><span>参数</span><b>样式 ${esc(x.style||'—')} · 长度 ${esc(x.size||'—')} · 粗细 ${esc(x.thickness||'—')} · 间隙 ${esc(x.gap||'—')}</b></div>
        <div class="kv-row"><span>分享码</span><b style="font-family:var(--mono);font-size:11px">${esc(P.crosshair_sharecode||'—')}</b></div>
      </div>
    </div>` : '';

  app.innerHTML = `
  <div class="back"><a class="lk" href="team.html">‹ 返回队伍</a></div>
  <div class="prof" style="margin-top:16px">
    ${avatar(p.photo, p.id, 'xl')}
    <div class="prof-txt">
      <div class="nick">${esc(p.id)}</div>
      <div class="full">${esc(p.name || '')}</div>
      <div class="meta">${esc(p.role)}${p.age ? ' · ' + p.age + ' 岁' : ''} · ${esc(p.nationality)}</div>
    </div>
  </div>
  ${p.note ? `<div class="kv" style="margin-top:10px">
    <div class="kv-row"><span>简介</span><b>${esc(p.note)}</b></div></div>` : ''}

  <div class="sec">
    <div class="sec-h"><b>选手资料</b><i></i><em>Liquipedia</em></div>
    <div class="kv">${rows}</div>
  </div>

  ${nikoExtra}
  ${histHtml}

  <div class="links">
    <a class="lk" href="${esc(p.url||'#')}" target="_blank" rel="noopener">Liquipedia 资料页 ↗</a>
    <a class="lk" href="index.html">返回首页</a>
  </div>

  <div class="syncbar"><span id="liveStatus">○ 正在获取最新数据…</span></div>
  <div class="foot">选手资料抓取自 Liquipedia（CC BY-SA 3.0）。最近更新：__UPDATED__</div>`;

  if(isNiko) drawCrosshair(x);
}

async function boot(){ await pullNewest(); render(); sync(document.getElementById('liveStatus')); }
"""

PAGES = [
    ("index.html", "index", "NiKo // 赛事跟踪", INDEX_JS,
     "NiKo（Nikola Kovač）赛事跟踪：Team Falcons 赛程、比分与选手数据"),
    ("match.html", "match", "比赛详情 // NiKo", MATCH_JS, "NiKo 比赛逐图详情"),
    ("team.html", "team", "Team Falcons // 阵容", TEAM_JS, "Team Falcons 现役阵容与选手资料"),
    ("player.html", "player", "选手资料 // NiKo", PLAYER_JS, "NiKo 与队友的选手资料"),
]


def build_page(fname, pid, title, js, desc):
    updated = DATA["meta"]["updated"]
    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#EEF0FB">
<meta name="description" content="{desc}">
<title>{title}</title>
<!-- 图标 = NiKo 本人高清照片（2048px 原图裁切，人脸居中），非像素图 -->
<link rel="icon" type="image/png" sizes="48x48" href="assets/pixel/favicon-48.png?v=3">
<link rel="icon" type="image/png" sizes="32x32" href="assets/pixel/favicon.png?v=3">
<!-- iOS 主屏图标：补齐多档高分辨率尺寸，系统会自动挑最清晰的一张 -->
<link rel="apple-touch-icon" sizes="180x180" href="assets/pixel/apple-touch-icon.png?v=3">
<link rel="apple-touch-icon" sizes="152x152" href="assets/pixel/apple-touch-icon-152.png?v=3">
<meta name="apple-mobile-web-app-title" content="NIKO">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="manifest.json">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body data-page="{pid}">
{ARMS_SPRITE}
{ARMS_BG}
<div class="hud"><div class="hud-in">
  <div class="crosshair"><span></span></div>
  <div class="brand"><b>NIKO</b><small>赛事跟踪</small></div>
  <div class="status"><i class="dot" id="dot"></i><span id="statusTxt">待战</span></div>
</div></div>
<div class="wrap" id="app"></div>
<script id="niko-data" type="application/json">__DATA__</script>
<script>
__JS__
render();
boot();
</script>
</body>
</html>"""
    return (body.replace("__JS__", js)
                .replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
                .replace("__UPDATED__", updated)
                .replace("__REPO__", REPO))


def main():
    payload = json.dumps(DATA, ensure_ascii=False)
    # 内联数据里不能出现 </script>，否则会截断脚本标签
    payload = payload.replace("</script", "<\\/script")
    built = []
    for fname, pid, title, js, desc in PAGES:
        updated = DATA["meta"]["updated"]
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#EEF0FB">
<meta name="description" content="{desc}">
<title>{title}</title>
<!-- 图标 = NiKo 本人高清照片（2048px 原图裁切，人脸居中），非像素图 -->
<link rel="icon" type="image/png" sizes="48x48" href="assets/pixel/favicon-48.png?v=3">
<link rel="icon" type="image/png" sizes="32x32" href="assets/pixel/favicon.png?v=3">
<!-- iOS 主屏图标：补齐多档高分辨率尺寸，系统会自动挑最清晰的一张 -->
<link rel="apple-touch-icon" sizes="180x180" href="assets/pixel/apple-touch-icon.png?v=3">
<link rel="apple-touch-icon" sizes="152x152" href="assets/pixel/apple-touch-icon-152.png?v=3">
<meta name="apple-mobile-web-app-title" content="NIKO">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="manifest.json">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body data-page="{pid}">
{ARMS_SPRITE}
{ARMS_BG}
<div class="hud"><div class="hud-in">
  <div class="crosshair"><span></span></div>
  <div class="brand"><b>NIKO</b><small>赛事跟踪</small></div>
  <div class="status"><i class="dot" id="dot"></i><span id="statusTxt">待战</span></div>
</div></div>
<div class="wrap" id="app"></div>
<script id="niko-data" type="application/json">{payload}</script>
<script>
{js.replace("__REPO__", REPO).replace("__UPDATED__", updated)}
render();
boot();
</script>
</body>
</html>"""
        (ROOT / fname).write_text(html, encoding="utf-8")
        if _gh.exists():
            (_gh / fname).write_text(html, encoding="utf-8")
        built.append((fname, len(html)))
    for name, size in built:
        print(f"{name:14s} {size/1024:6.1f} KB")


if __name__ == "__main__":
    main()
