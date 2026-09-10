"""生成 NiKo 赛事跟踪站：一级页 + 三个二级页（比赛详情 / 队伍 / 选手）。

所有页面内联 data.json，离线可直接打开；联网时会尝试拉取更新后的 data.json 覆盖。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).parent
DATA = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
_gh = ROOT / "github"
REPO = (ROOT / "repo.txt").read_text(encoding="utf-8").strip() or "__REPO__"

CSS = r"""
/* ========== 清爽紫罗兰仪表盘风（参考 Ecourse UI） ========== */
:root{
  --bg:#EEF0FB;            /* 浅紫灰背景 */
  --bg2:#E3E6F8;           /* 背景加深 */
  --panel:#FFFFFF;         /* 白卡片 */
  --panel2:#F4F5FE;        /* 淡紫面板 */
  --panel3:#E9EBFA;        /* 更深一档 */
  --line:#E5E8F6;          /* 卡片描边 */
  --line-soft:#D6DAF0;
  --hi:#FFFFFF;
  --shadow-c:transparent;
  --ink:#2E3256;           /* 主文字 · 深藏青 */
  --ink2:#7B81A8;          /* 次文字 */
  --dim:#A6ABC9;
  --amber:#5B5CE6;         /* 主题靛蓝（沿用变量名，JS 无需改动） */
  --amber2:#7C7DF2;
  --amber-bg:#E9EAFE;
  --win:#18B76B;           /* 胜 · 绿 */
  --win-bg:#DFF6EA;
  --loss:#EE5A6C;          /* 负 · 珊瑚红 */
  --loss-bg:#FDE7EA;
  --ct:#4C7FD9;
  --t:#F08C4A;
  --exp:#9C6BEB;
  --shadow-lg:0 18px 40px -18px rgba(76,79,168,.28);
  --shadow-md:0 10px 24px -12px rgba(76,79,168,.22);
  --shadow-sm:0 4px 12px -4px rgba(76,79,168,.14);
  --mono:"JetBrains Mono","SF Mono",Consolas,"Courier New",monospace;
  --sans:"Segoe UI","PingFang SC","HarmonyOS Sans SC","Microsoft YaHei",system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
img{display:block}
body{
  background-color:var(--bg);
  background-image:radial-gradient(1200px 500px at 85% -10%, #E4E2FB 0%, transparent 60%),
                   radial-gradient(900px 420px at -10% 0%, #EDE3F9 0%, transparent 55%);
  background-repeat:no-repeat;
  color:var(--ink);
  font-family:var(--sans);
  font-size:15px;
  line-height:1.55;
  min-height:100vh;
  text-rendering:optimizeLegibility;
  -webkit-font-smoothing:antialiased;
}
a{color:inherit;text-decoration:none}
.wrap{max-width:760px;margin:0 auto;padding:0 16px 80px}

/* === 顶栏 === */
.hud{position:sticky;top:0;z-index:50;
  background:rgba(255,255,255,.82);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  box-shadow:0 1px 0 var(--line)}
.hud-in{max-width:760px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;gap:11px}
.brand{display:flex;flex-direction:column;line-height:1.15}
.brand b{font-size:19px;letter-spacing:.14em;font-weight:800;color:var(--ink)}
.brand small{font-size:10px;color:#fff;letter-spacing:.22em;font-family:var(--mono);
  background:linear-gradient(135deg,var(--amber),var(--amber2));
  padding:2px 8px;margin-top:3px;border-radius:999px;
  display:inline-block;width:fit-content}
.hud .ava{width:36px;height:36px;flex:none;border-radius:12px}
.status{margin-left:auto;display:flex;align-items:center;gap:7px;
  font-family:var(--mono);font-size:11px;letter-spacing:.08em;
  background:var(--panel2);color:var(--ink);
  border:1px solid var(--line);
  padding:6px 12px;border-radius:999px;box-shadow:var(--shadow-sm)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--amber)}
.dot.live{background:var(--loss);animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* === 准星装饰（品牌图标）=== */
.crosshair{width:34px;height:34px;flex:none;position:relative;
  background:linear-gradient(135deg,var(--amber),var(--amber2));
  border-radius:11px;box-shadow:0 6px 14px -6px rgba(91,92,230,.55)}
.crosshair::before,.crosshair::after{content:"";position:absolute;background:#fff;border-radius:2px}
.crosshair::before{left:50%;top:8px;width:3px;height:18px;transform:translateX(-50%)}
.crosshair::after{top:50%;left:8px;height:3px;width:18px;transform:translateY(-50%)}
.crosshair span{display:none}

/* === 头像 === */
.av{background:var(--panel2);border:1px solid var(--line);object-fit:cover;flex:none;display:block;border-radius:16px}
.av-xl{width:78px;height:78px}
.av-lg{width:62px;height:62px}
.av-ph{display:grid;place-items:center;font-family:var(--mono);font-weight:700;color:var(--amber);
  background:linear-gradient(135deg,#ECEDFE,#E4E4FD);border:1px solid var(--line);flex:none;border-radius:16px}
.av-ph-xl{width:78px;height:78px;font-size:22px}
.av-ph-lg{width:62px;height:62px;font-size:19px}

.prof{display:flex;align-items:center;gap:14px;background:var(--panel);
  border:1px solid var(--line);border-radius:20px;padding:16px 18px;margin-top:18px;
  box-shadow:var(--shadow-md)}
.prof .nick{font-size:22px;font-weight:800;letter-spacing:.02em;color:var(--ink)}
.prof .full{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-top:2px}
.prof .meta{font-family:var(--mono);font-size:11px;color:var(--amber);margin-top:6px;letter-spacing:.04em;
  background:var(--amber-bg);padding:3px 9px;display:inline-block;border-radius:999px}
.prof-link{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--amber);
  background:var(--amber-bg);padding:6px 11px;border-radius:999px;letter-spacing:.08em;white-space:nowrap}

/* === 横向滚动：队友 === */
.scroller{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 12px;scroll-snap-type:x mandatory;
  -webkit-overflow-scrolling:touch;scrollbar-width:none}
.scroller::-webkit-scrollbar{display:none}
.pc{flex:0 0 132px;scroll-snap-align:start;background:var(--panel);
  border:1px solid var(--line);border-radius:18px;padding:14px 10px;text-align:center;
  box-shadow:var(--shadow-sm)}
.pc:active{transform:scale(.97)}
.pc .ph{width:62px;height:62px;margin:0 auto 10px}
.pc .ph .av,.pc .ph .av-ph{border-radius:16px}
.pc .pid{font-size:15px;font-weight:700;letter-spacing:.02em;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.pc .prole{font-family:var(--mono);font-size:10px;color:var(--amber);background:var(--amber-bg);
  padding:2px 8px;display:inline-block;margin-top:5px;letter-spacing:.06em;border-radius:999px}
.pc .pnat{font-family:var(--mono);font-size:10px;color:var(--ink2);margin-top:4px}
.hint{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.1em;margin-bottom:6px}

/* === 章节 === */
.sec{margin-top:32px;position:relative}
.sec-h{display:flex;align-items:center;gap:10px;margin-bottom:13px}
.sec-h b{font-size:14px;letter-spacing:.12em;color:#fff;font-family:var(--sans);font-weight:700;
  background:linear-gradient(135deg,var(--amber),var(--amber2));
  padding:6px 14px;border-radius:999px;box-shadow:0 6px 14px -6px rgba(91,92,230,.5)}
.sec-h i{flex:1;height:1px;background:var(--line-soft)}
.sec-h em{font-family:var(--mono);font-size:11px;color:var(--ink2);font-style:normal;letter-spacing:.06em}
.sec-h a em{color:var(--amber);font-weight:700}

/* === 下一场比赛 hero === */
.hero{margin-top:18px;background:var(--panel);border:1px solid var(--line);border-radius:24px;position:relative;
  box-shadow:var(--shadow-lg);
  overflow:hidden}
.hero::after{content:"";position:absolute;right:-40px;bottom:-30px;width:230px;height:170px;
  background:radial-gradient(closest-side,rgba(124,125,242,.14),transparent);
  pointer-events:none}
.hero-top{display:flex;align-items:center;gap:8px;padding:14px 18px 0}
.tag{font-family:var(--mono);font-size:11px;letter-spacing:.18em;color:#fff;
  background:linear-gradient(135deg,var(--amber),var(--amber2));
  padding:4px 11px;border-radius:999px;font-weight:700}
.hero-body{padding:18px 16px 22px;text-align:center;position:relative;z-index:1}
.vs{display:flex;align-items:center;justify-content:center;gap:14px;margin:6px 0 4px;flex-wrap:wrap}
.team{font-size:27px;font-weight:800;letter-spacing:.02em;color:var(--ink)}
.team.tbd{color:var(--dim)}
.vs-mid{font-family:var(--mono);font-size:13px;color:#fff;
  background:linear-gradient(135deg,var(--amber),var(--amber2));
  padding:4px 11px;letter-spacing:.08em;font-weight:700;border-radius:999px}
.hero-sub{font-family:var(--mono);font-size:12px;color:var(--ink2);letter-spacing:.04em}
.hero-note{font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:.04em;margin-top:10px;
  background:var(--amber-bg);padding:4px 11px;display:inline-block;border-radius:999px}

/* === 倒计时（干净数字，绝无重影）=== */
.cd{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0 6px}
.cd div{background:linear-gradient(180deg,#F6F7FF,#EFF0FD);
  border:1px solid var(--line);border-radius:18px;padding:14px 4px 12px;
  box-shadow:inset 0 1px 0 #fff}
.cd b{display:block;font-family:var(--sans);font-size:32px;font-weight:800;color:var(--amber);
  font-variant-numeric:tabular-nums;font-feature-settings:"tnum";
  line-height:1;text-shadow:none;letter-spacing:0}
.cd span{font-size:10px;color:var(--ink2);letter-spacing:.3em;font-family:var(--mono);margin-top:7px;display:block}

/* === 未来赛程卡 === */
.up{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.up-c{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:15px 17px;position:relative;
  box-shadow:var(--shadow-sm)}
.up-c .n{font-size:16px;font-weight:700;letter-spacing:.01em;color:var(--ink);padding-right:64px}
.up-c .d{font-family:var(--mono);font-size:12px;color:var(--amber);margin-top:4px;font-weight:700}
.up-c .m{font-family:var(--mono);font-size:11px;color:var(--ink2);margin-top:8px;letter-spacing:.03em}
.tier{position:absolute;top:13px;right:14px;font-family:var(--mono);font-size:10px;
  color:var(--amber);background:var(--amber-bg);padding:4px 9px;letter-spacing:.06em;font-weight:700;border-radius:999px}

/* === 战绩 rows === */
.rows{display:flex;flex-direction:column;gap:10px}
.row{display:flex;align-items:center;gap:12px;background:var(--panel);
  border:1px solid var(--line);border-left:4px solid var(--line-soft);border-radius:16px;padding:12px 14px;
  box-shadow:var(--shadow-sm)}
.row:active{transform:scale(.985)}
.row.W{border-left-color:var(--win)}
.row.L{border-left-color:var(--loss)}
.res{width:30px;height:30px;flex:none;display:grid;place-items:center;font-family:var(--mono);
  font-size:13px;font-weight:700;color:#fff;border-radius:10px}
.res.W{background:var(--win)} .res.L{background:var(--loss)}
.sc{font-family:var(--mono);font-size:17px;font-weight:700;font-variant-numeric:tabular-nums;flex:none;width:58px;color:var(--ink)}
.info{flex:1;min-width:0}
.info .o{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.info .e{font-family:var(--mono);font-size:11px;color:var(--ink2);margin-top:2px;letter-spacing:.02em}
.rt{flex:none;text-align:right;font-family:var(--mono)}
.rt b{font-size:14px;color:var(--ink);font-weight:700}
.rt small{display:block;font-size:10px;color:var(--ink2);letter-spacing:.04em}
.bar{width:56px;height:6px;background:var(--panel3);margin-top:5px;margin-left:auto;border-radius:999px;overflow:hidden}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--amber),var(--amber2));border-radius:999px}
.chev{flex:none;color:var(--dim);font-size:18px}
.more{display:block;width:100%;margin-top:10px;background:var(--panel);
  border:1px solid var(--line);color:var(--amber);font-family:var(--mono);font-size:12px;letter-spacing:.1em;
  padding:12px;border-radius:14px;cursor:pointer;font-weight:700;box-shadow:var(--shadow-sm)}
.more:active{transform:scale(.985)}

/* === 数据统计格子 === */
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(112px,1fr))}
.st{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 15px;
  box-shadow:var(--shadow-sm)}
.st span{display:block;font-family:var(--mono);font-size:10px;color:var(--ink2);letter-spacing:.1em}
.st b{display:block;font-family:var(--sans);font-size:23px;font-weight:800;margin-top:6px;
  color:var(--ink);font-variant-numeric:tabular-nums}
.st.hl b{color:var(--win)}
.st-sub{font-family:var(--mono);font-size:11px;color:var(--ink2);margin-top:3px}

/* === 资料表 === */
.kv{background:var(--panel);border:1px solid var(--line);border-radius:18px;
  box-shadow:var(--shadow-sm);overflow:hidden}
.kv-row{display:flex;gap:12px;padding:11px 16px;border-bottom:1px dashed var(--line-soft);font-size:14px}
.kv-row:last-child{border-bottom:none}
.kv-row span{flex:none;width:96px;font-family:var(--mono);font-size:11px;color:var(--ink2);
  letter-spacing:.06em;padding-top:3px;font-weight:700}
.kv-row b{font-weight:500;color:var(--ink)}

/* === 比赛地图 === */
.map{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--line-soft);
  border-radius:16px;padding:13px 15px;margin-bottom:10px;
  box-shadow:var(--shadow-sm)}
.map.W{border-left-color:var(--win)} .map.L{border-left-color:var(--loss)}
.map.veto{border-left-color:var(--line-soft);opacity:.55}
.map-h{display:flex;align-items:baseline;gap:9px;margin-bottom:8px;flex-wrap:wrap}
.map-h b{font-size:16px;letter-spacing:.02em;color:var(--ink)}
.map-h em{font-family:var(--mono);font-size:10px;font-style:normal;color:var(--ink2);letter-spacing:.06em;
  background:var(--panel2);padding:3px 8px;border-radius:999px}
.map-en{font-family:var(--mono);font-size:10px;color:var(--dim);margin-left:7px;letter-spacing:.04em}
.map-res{margin-left:auto;font-family:var(--mono);font-size:11px;letter-spacing:.06em;font-weight:700;
  padding:3px 10px;border-radius:999px}
.map-res.W{color:#fff;background:var(--win)} .map-res.L{color:#fff;background:var(--loss)}
.mline{display:flex;align-items:center;gap:9px;margin-top:5px}
.mline .who{font-family:var(--mono);font-size:11px;color:var(--ink2);flex:none;width:60px;letter-spacing:.03em;font-weight:700}
.mline .rounds{font-family:var(--mono);font-size:18px;font-weight:700;flex:none;width:40px;
  text-align:right;font-variant-numeric:tabular-nums;color:var(--ink)}
.mline .halves{font-family:var(--mono);font-size:10px;color:var(--ink2);flex:none;width:74px}
.mline .tbar{flex:1;height:6px;background:var(--panel3);border-radius:999px;overflow:hidden}
.mline .tbar i{display:block;height:100%;background:linear-gradient(90deg,var(--win),#3ED48C);border-radius:999px}
.mline.L .tbar i{background:linear-gradient(90deg,var(--loss),#FF8A96)}

/* === 链接按钮 === */
.links{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}
.lk{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--amber);
  background:var(--panel);border:1px solid var(--line);padding:8px 14px;font-weight:700;
  border-radius:999px;box-shadow:var(--shadow-sm)}
.lk:active{transform:scale(.97)}

/* === 队伍格 === */
.team-grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.tc{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:16px 14px;text-align:center;
  box-shadow:var(--shadow-sm)}
.tc:active{transform:scale(.98)}
.tc .ph{width:76px;height:76px;margin:0 auto 10px}
.tc .ph .av,.tc .ph .av-ph{border-radius:20px}
.tc .pid{font-size:17px;font-weight:800;letter-spacing:.02em;color:var(--ink)}
.tc .pfull{font-family:var(--mono);font-size:10px;color:var(--ink2);margin-top:2px}
.tc .prole{font-family:var(--mono);font-size:11px;color:var(--amber);background:var(--amber-bg);
  padding:3px 10px;display:inline-block;margin-top:7px;letter-spacing:.06em;font-weight:700;border-radius:999px}
.tc .pdesc{font-size:11px;color:var(--ink2);margin-top:6px;line-height:1.4}

/* === 准星练习 === */
.xh{display:grid;place-items:center;background:linear-gradient(180deg,#F6F7FF,#EFF0FD);
  border:1px solid var(--line);border-radius:18px;
  height:130px;margin-top:10px;position:relative;overflow:hidden}
.xh i{position:absolute;background:var(--amber);border-radius:1px}

/* === 页脚 === */
.foot{margin-top:32px;padding-top:18px;border-top:1px solid var(--line-soft);
  font-family:var(--mono);font-size:11px;color:var(--ink2);line-height:1.8}
.foot a{color:var(--amber);font-weight:700}
.syncbar{display:flex;align-items:center;gap:8px;margin-top:16px;font-family:var(--mono);font-size:11px;color:var(--ink2);
  background:var(--panel);padding:9px 14px;border:1px solid var(--line);border-radius:999px;
  box-shadow:var(--shadow-sm)}
.syncbar .lk{background:var(--amber-bg);border-color:transparent}
.empty{padding:28px 14px;text-align:center;color:var(--ink2);font-family:var(--mono);font-size:12px;
  background:var(--panel2);border:1px dashed var(--line-soft);border-radius:18px;margin-top:8px}
.back{margin-top:16px}

/* 移动端微调 */
@media(max-width:380px){
  .hud-in{padding:10px 12px;gap:9px}
  .brand b{font-size:17px}
  .prof .nick{font-size:19px}
  .team{font-size:22px}
  .cd b{font-size:26px}
  .row{padding:11px 12px;gap:10px}
  .res{width:26px;height:26px;font-size:12px}
  .sc{width:50px;font-size:15px}
}
"""

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

async function boot(){
  await pullNewest();
  render();
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
<link rel="icon" type="image/svg+xml" href="assets/pixel/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="assets/pixel/favicon.png">
<link rel="apple-touch-icon" href="assets/pixel/apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<style>{CSS}</style>
</head>
<body data-page="{pid}">
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
<link rel="icon" type="image/svg+xml" href="assets/pixel/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="assets/pixel/favicon.png">
<link rel="apple-touch-icon" href="assets/pixel/apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<style>{CSS}</style>
</head>
<body data-page="{pid}">
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
