"""抓取「当前/下一站 + 最近赛事」的分组、分支、赛程，产出 event.json。

数据源：Liquipedia（CC BY-SA 3.0）。解析见 parse_event.py。

- 优先读本地缓存 _cache/events/*.html，缺失才联网（Liquipedia parse 限流 1 次/30 秒）。
- 队标下载到 assets/teams/，避免热链。
- 日期区间：有对阵时间戳就用时间戳，没有就用 base.json/data.json 里已确认的赛程。
"""
import datetime as dt
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

import parse_event as PE

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "_cache" / "events"
OUT_JSON = ROOT / "event.json"
TEAM_DIR = ROOT / "assets" / "teams"
UA = {"User-Agent": "NikoTracker/1.0 (personal CS2 fan page; contact: user@example.com)",
      "Accept-Encoding": "gzip"}

# 缓存文件名与页面名不一致时的别名
CACHE_ALIAS = {"ESL/Pro League/Season 24": "epl_s24.html"}

# 展示用配置（tag: next=当前/下一站, recent=最近赛事）
CONFIG = [
    {"page": "ESL/Pro League/Season 24", "zh": "ESL 职业联赛 S24", "short": "EPL S24",
     "tag": "next", "tier": "S-Tier", "match": "ESL Pro League"},
    {"page": "Intel Extreme Masters/2026/Beijing", "zh": "IEM 北京 2026", "short": "IEM 北京",
     "tag": "next", "tier": "S-Tier", "match": "Beijing"},
    {"page": "BLAST/Open/2026/Fall", "zh": "BLAST 公开赛 波尔图站", "short": "BLAST 波尔图",
     "tag": "recent", "tier": "S-Tier", "match": "BLAST"},
    {"page": "Intel Extreme Masters/2026/Cologne/Playoffs", "zh": "IEM 科隆 Major 2026",
     "short": "IEM 科隆", "tag": "recent", "tier": "S-Tier", "match": "Cologne",
     "teams_page": "Intel Extreme Masters/2026/Cologne"},
]

CONFIG_CACHE = ROOT / "_cache" / "events_cache.json"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def cache_path(page: str) -> pathlib.Path:
    if page in CACHE_ALIAS:
        return CACHE / CACHE_ALIAS[page]
    return CACHE / (page.replace("/", "_").replace(" ", "_") + ".html")


def fetch_page(page: str) -> str:
    url = "https://liquipedia.net/counterstrike/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "text", "format": "json"})
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120)
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        import gzip
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))["parse"]["text"]["*"]


def load_html(page: str, allow_net: bool):
    p = cache_path(page)
    if p.exists() and p.stat().st_size > 2000:
        return p.read_text(encoding="utf-8"), "cache"
    if not allow_net:
        return "", "missing"
    h = fetch_page(page)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(h, encoding="utf-8")
    return h, "net"


def norm_team(n: str) -> str:
    n = re.sub(r"^Team\s+", "", n or "").strip()
    return n


def download_logo(logo: str) -> str:
    """把队标下到 assets/teams/，返回本地相对路径（失败返回空）。"""
    if not logo:
        return ""
    TEAM_DIR.mkdir(parents=True, exist_ok=True)
    stem = pathlib.Path(logo.split("?")[0]).stem
    stem = re.sub(r"^\d+px-", "", stem)          # 去掉缩略图前缀 43px-
    fn = slug(stem) + ".png"
    dst = TEAM_DIR / fn
    if dst.exists() and dst.stat().st_size > 200:
        return f"assets/teams/{fn}"
    urls = []
    if re.search(r"/\d+px-", logo):
        urls.append(re.sub(r"/\d+px-", "/88px-", logo))
    urls.append(logo)
    for u in urls:
        full = u if u.startswith("http") else "https://liquipedia.net" + u
        try:
            data = urllib.request.urlopen(
                urllib.request.Request(full, headers=UA), timeout=60).read()
            if len(data) > 200:
                dst.write_bytes(data)
                return f"assets/teams/{fn}"
        except Exception:
            continue
    return ""


def summarize_format(h: str) -> str:
    seg = PE.section_html(h, "Format")
    if not seg:
        return ""
    txt = PE._text(seg)
    txt = re.sub(r"^\s*Format\s*", "", txt)
    txt = re.sub(r"^\[\s*edit\s*\]\s*", "", txt).strip()
    # 只保留第一段（阶段 + 参赛队数 + 赛制 + 晋级规则）
    cut = txt.split("Click here")[0].split("First Round")[0].strip()
    cut = re.sub(r"\s+", " ", cut)
    return cut[:180]


def build_event(cfg, html_text, base_info, now):
    h = html_text
    d = PE.build(cfg["page"], h, cfg["zh"])
    parts = d["participants"]
    if not parts and cfg.get("teams_page"):
        # 淘汰赛子页面没有参赛队名单，回主页面取（只读缓存，避免额外联网）
        alt_p = cache_path(cfg["teams_page"])
        if alt_p.exists():
            parts = PE.parse_participants(alt_p.read_text(encoding="utf-8"))

    # 队标 -> 本地
    teams = []
    for p in parts[:24]:
        logo = download_logo(p.get("logo", ""))
        teams.append({"name": norm_team(p["name"]), "logo": logo})

    # 日期区间
    ts_all = [m["ts"] for b in d["brackets"] for rd in b["rounds"]
              for m in rd["matches"] if m["ts"]]
    start_iso = end_iso = ""
    if ts_all:
        lo, hi = min(ts_all), max(ts_all)
        start_iso = dt.datetime.fromtimestamp(lo, dt.timezone.utc).isoformat(timespec="seconds")
        end_iso = dt.datetime.fromtimestamp(hi + 4 * 3600, dt.timezone.utc).isoformat(timespec="seconds")
    if cfg["tag"] == "next" and base_info:
        start_iso = base_info.get("start") or start_iso
        date_text = base_info.get("date_text", "")
        tier = base_info.get("tier") or cfg["tier"]
        note = base_info.get("note", "")
    else:
        tier = cfg["tier"]
        note = ""
        date_text = ""
        if start_iso:
            a = dt.datetime.fromisoformat(start_iso)
            b = dt.datetime.fromisoformat(end_iso) if end_iso else a
            date_text = (f"{a.month:02d}/{a.day:02d}–{b.month:02d}/{b.day:02d}"
                         if a.month == b.month else
                         f"{a.month:02d}/{a.day:02d}–{b.month:02d}/{b.day:02d}")

    # 状态
    status = "upcoming"
    if start_iso:
        s = dt.datetime.fromisoformat(start_iso)
        e = dt.datetime.fromisoformat(end_iso) if end_iso else s + dt.timedelta(days=7)
        if now < s:
            status = "upcoming"
        elif now <= e:
            status = "live"
        else:
            status = "done"
    elif cfg["tag"] == "recent":
        status = "done"

    # 分支图：中文标注
    brackets = []
    for b in d["brackets"]:
        rounds = []
        for rd in b["rounds"]:
            ms = []
            for m in rd["matches"]:
                ms.append({
                    "a": {"name": norm_team(m["a"]["name"]), "score": m["a"]["score"],
                          "win": m["a"]["win"]},
                    "b": {"name": norm_team(m["b"]["name"]), "score": m["b"]["score"],
                          "win": m["b"]["win"]},
                    "ts": m["ts"], "bo": m["bo"],
                })
            rounds.append({"name": rd["name"], "matches": ms})
        if rounds:
            brackets.append({"title": b["title"], "rounds": rounds, "count": b["count"]})

    # 赛程（有时间的对阵）
    sched = []
    for r in d["schedule"]:
        sched.append({
            "stage": r["stage"], "round": r["round"], "bo": r["bo"], "ts": r["ts"],
            "a": norm_team(r["a"]["name"]), "b": norm_team(r["b"]["name"]),
            "sa": r["a"]["score"], "sb": r["b"]["score"],
        })

    groups = [{"title": g["title"], "cols": g["cols"], "rows": g["rows"]} for g in d["groups"]]

    return {
        "id": slug(cfg["page"]),
        "tag": cfg["tag"],
        "name": cfg["zh"],
        "short": cfg["short"],
        "tier": tier,
        "note": note,
        "status": status,
        "start": start_iso,
        "end": end_iso,
        "date_text": date_text,
        "prize": d["info"].get("prize", ""),
        "format": summarize_format(h),
        "teams": teams,
        "groups": groups,
        "brackets": brackets,
        "schedule": sched,
        "source": "https://liquipedia.net/counterstrike/" + urllib.parse.quote(cfg["page"]),
    }


def main():
    allow_net = "--offline" not in sys.argv
    now = dt.datetime.now(dt.timezone.utc)
    base = {}
    try:
        bj = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        for t in bj.get("upcoming_tournaments", []):
            base[t.get("short", "")] = t
            base[t.get("name", "")] = t
    except Exception as e:
        print("读取 data.json 失败:", e)

    events = []
    for i, cfg in enumerate(CONFIG):
        html, src = load_html(cfg["page"], allow_net)
        if not html:
            print(f"[跳过] {cfg['zh']} — 无缓存且未联网")
            continue
        if src == "net" and i + 1 < len(CONFIG):
            time.sleep(32)
        # 匹配基础赛程信息
        info = None
        for k, v in base.items():
            if cfg["match"] and cfg["match"].lower() in (k or "").lower():
                info = v
                break
            if cfg["short"] and cfg["short"].lower() in (k or "").lower():
                info = v
                break
        try:
            ev = build_event(cfg, html, info, now)
        except Exception as e:
            print(f"[失败] {cfg['zh']}: {type(e).__name__} {e}")
            continue
        events.append(ev)
        n_teams = len(ev["teams"])
        n_br = sum(len(rd["matches"]) for b in ev["brackets"] for rd in b["rounds"])
        print(f"[ok:{src}] {ev['name']:22} 状态={ev['status']:8} 队={n_teams:3} "
              f"分支={len(ev['brackets'])}({n_br}场) 分组={len(ev['groups'])} 赛程={len(ev['schedule'])}")

    events.sort(key=lambda e: (0 if e["tag"] == "next" else 1, e["start"] or "9999"))
    data = {
        "updated": now.isoformat(timespec="seconds"),
        "featured": next((e for e in events if e["tag"] == "next"), None),
        "events": events,
        "source_note": "赛事分组、分支图与赛程抓取自 Liquipedia（CC BY-SA 3.0）。",
    }
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print("已写出 event.json：", OUT_JSON.stat().st_size // 1024, "KB，赛事数", len(events))


if __name__ == "__main__":
    main()
