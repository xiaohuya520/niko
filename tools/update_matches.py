#!/usr/bin/env python3
# tools/update_matches.py —— 抓取 CS2 真实赛程/实时比分,生成固件用的 cs_matches.json。
#
# 数据源: Sofascore 非官方 API(免费、免 key):
#   live : GET /api/v1/sport/esports/events/live
#   按日 : GET /api/v1/category/1572/scheduled-events/{YYYY-MM-DD}   (1572=Counter Strike)
# 窗口: 北京时间,近期战绩=前3天,赛事预告=未来7天(含今天)。
# 输出: 与固件 parse_matches 匹配的 JSON;总字节 <11400(固件 12KB 缓冲),场次 <=16。
# 兜底: 抓取全部失败时保留旧文件退出 0(cron 保持绿色,设备继续用 NVS 缓存)。
#
# 用法: python3 tools/update_matches.py cs_matches.json
import json
import ssl
import sys
import time
import traceback
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
API = "https://api.sofascore.com/api/v1"
CS_CAT = 1572                     # Sofascore 的 Counter Strike 分类 id
MAX_MATCHES = 16
MAX_BYTES = 11400                 # 固件 CS_HTTP_BUF_MAX=12288,留余量

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE   # Actions runner 与本机均可能缺中间证书

# 已知队色(与现网 cs_matches.json 保持一致);未收录队伍用名字哈希生成稳定颜色
TEAM_COLORS = {
    "g2": "#E4AE39", "navi": "#F2E14C", "vitality": "#FFD928", "mouz": "#E43B2F",
    "spirit": "#8C6239", "faze": "#B01C24", "aurora": "#2AA3EF", "astralis": "#E43B2F",
    "falcons": "#00B36B", "virtuspro": "#FDB913", "liquid": "#0C1A2C", "mibr": "#FFD700",
    "furia": "#000000", "mongolz": "#E4B33C", "nip": "#FFD400", "heroic": "#2DBBA9",
    "complexity": "#0D2FA8", "cloud9": "#01AEF0", "big": "#F4C50F", "fnatic": "#FF5900",
    "eternalfire": "#B01C24", "nemiga": "#2E9BF0", "monte": "#8C3BEF", "m80": "#E4382C",
    "legacy": "#00B36B", "imperial": "#00A859", "pain": "#E43B2F", "tyloo": "#B01C24",
    "rareatom": "#E43B8C", "lynnvision": "#2E9BF0", "sashi": "#2AA3EF", "b8": "#2AA3EF",
    "betboom": "#FFC93C", "passionua": "#FFC93C", "parivision": "#35D07F",
    "gamerlegion": "#E43B2F", "ecstatic": "#2E9BF0", "amkal": "#35D07F",
}
# Sofascore 队名 → 本仓库队标 id 的别名(规范写法已在 cs_teams.json 里能直接对上的不列)
TEAM_ALIASES = {
    "natusvincere": "navi", "virtuspro": "virtuspro", "themoncolz": "mongolz",
    "fazeclan": "faze", "teamliquid": "liquid", "teamfalcons": "falcons",
    "teamspirit": "spirit", "auroragaming": "aurora", "teamvitality": "vitality",
    "9zteam": "9z", "teamnexus": "", "flyquest": "", "theprofessor": "",
}

MAP_CN = {
    "mirage": ("Mirage", "荒漠迷城"), "inferno": ("Inferno", "炼狱小镇"),
    "nuke": ("Nuke", "核子危机"), "dust2": ("Dust2", "炙热沙城"),
    "ancient": ("Ancient", "远古遗迹"), "anubis": ("Anubis", "阿努比斯"),
    "train": ("Train", "列车停放站"), "overpass": ("Overpass", "死亡游乐园"),
    "vertigo": ("Vertigo", "殒命大厦"), "office": ("Office", "办公室"),
    "cache": ("Cache", "缓存 stored"), "mills": ("Mills", "磨坊"),
    "grail": ("Grail", "圣杯"), "jura": ("Jura", "汝拉"),
}
CN_NUM = "一二三四五"


def http_json(url, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2)
    raise RuntimeError("%s -> %s" % (url, last))


def bj(ts):
    """unix 秒 → 北京时间 datetime"""
    return datetime.fromtimestamp(ts, timezone.utc) + timedelta(hours=8)


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def load_team_table(repo_root):
    """tools/cs_teams.json: {teams:[{id, cn, repo}]} → 名称映射表"""
    table = {}
    try:
        with open(repo_root + "/tools/cs_teams.json", encoding="utf-8") as f:
            j = json.load(f)
        for t in j["teams"]:
            table[norm(t["id"])] = t["id"]
            table[norm(t["cn"])] = t["id"]
    except Exception:
        pass
    return table


def hash_color(name):
    h = 2166136261
    for ch in name:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    # 电竞深色风:亮度压在中间档,饱和度拉高
    return "#%02X%02X%02X" % (60 + h % 160, 60 + (h >> 8) % 160, 60 + (h >> 16) % 160)


def team_info(raw, table):
    name = (raw or {}).get("name") or "TBD"
    key = norm(name)
    alias = TEAM_ALIASES.get(key, None)
    logo = alias if alias is not None else table.get(key, "")
    color = TEAM_COLORS.get(logo) if logo else None
    if not color:
        color = hash_color(key or "tbd")
    return {"name": name[:20], "logo": logo, "color": color}


def stage_of(ev):
    ri = ev.get("roundInfo") or {}
    if ri.get("name"):
        return str(ri["name"])[:40]
    if ri.get("round"):
        return "第%d轮" % ri["round"]
    if ri.get("cupRoundType") == 1:
        return "淘汰赛"
    return ""


def is_csgo(ev):
    cat = (ev.get("tournament") or {}).get("category") or {}
    return cat.get("slug") == "csgo" or cat.get("name") == "Counter Strike"


def maps_of(ev):
    """period1..5 → 逐图比分;地图名 Sofascore 不给,用通用名;全 0 的空图丢弃。"""
    out = []
    h = ev.get("homeScore") or {}
    a = ev.get("awayScore") or {}
    for i in range(1, 6):
        s1, s2 = h.get("period%d" % i), a.get("period%d" % i)
        if s1 is None and s2 is None:
            break
        if (s1 or 0) + (s2 or 0) > 0:
            base, cn = ("Map", "第%s图" % CN_NUM[i - 1])
            out.append({"name": base, "cn": cn,
                        "s1": int(s1 or 0), "s2": int(s2 or 0)})
    return out


def conv(ev, table):
    ts = ev.get("startTimestamp", 0)
    d = bj(ts)
    st = (ev.get("status") or {}).get("type") or "notstarted"
    status = {"inprogress": "live", "finished": "finished"}.get(st, "upcoming")
    ut = (ev.get("tournament") or {}).get("uniqueTournament") or {}
    ename = ut.get("name") or (ev.get("tournament") or {}).get("name") or "CS2"
    best = ev.get("bestOf") or 3
    m = {
        "event": ename[:40],
        "stage": stage_of(ev),
        "date": d.strftime("%m-%d"),
        "time": d.strftime("%H:%M"),
        "bo": "BO%d" % best,
        "status": status,
        "team1": team_info(ev.get("homeTeam"), table),
        "team2": team_info(ev.get("awayTeam"), table),
        "score1": int((ev.get("homeScore") or {}).get("current") or 0),
        "score2": int((ev.get("awayScore") or {}).get("current") or 0),
        "maps": [] if status == "upcoming" else maps_of(ev),
    }
    return m


def collect(days):
    live = http_json(API + "/sport/esports/events/live").get("events", [])
    per_day = {}
    for d in days:
        try:
            per_day[d] = http_json("%s/category/%d/scheduled-events/%s" % (API, CS_CAT, d)).get("events", [])
        except Exception as e:
            print("  [warn] %s 抓取失败: %s" % (d, e))
            per_day[d] = []
    return live, per_day


def build(table):
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    days = [(now + timedelta(days=k)).strftime("%Y-%m-%d") for k in range(-3, 8)]
    live_all, per_day = collect(days)

    # category/1572 是整个电竞分类,必须按项目过滤出 CS2
    live = [e for e in live_all if is_csgo(e)]

    def dkey(e):
        return e.get("startTimestamp", 0)

    # 预告:今天起 7 天,按时间正序,只留 notstarted
    upc = []
    for d in days[3:]:
        upc += [e for e in per_day.get(d, [])
                if (e.get("status") or {}).get("type") == "notstarted" and is_csgo(e)]
    upc.sort(key=dkey)

    # 战绩:前 3 天(含今天已结束),按时间倒序(最近在前)
    fin = []
    for d in days[:4]:
        fin += [e for e in per_day.get(d, [])
                if (e.get("status") or {}).get("type") == "finished" and is_csgo(e)]
    fin.sort(key=dkey, reverse=True)

    # 配额:live 最多 6 场;预告/战绩各至少保 4~5 场(有货时),剩下的给另一边
    matches = [conv(e, table) for e in live[:6]]
    nlive = len(matches)
    n_upc = min(len(upc), max(4, MAX_MATCHES - nlive - min(len(fin), 5)))
    matches += [conv(e, table) for e in upc[:n_upc]]
    matches += [conv(e, table) for e in fin[:max(0, MAX_MATCHES - len(matches))]]

    # 去重(同一场比赛可能同时出现在 live 和当日 scheduled 里)
    seen, uniq = set(), []
    for m in matches:
        k = (m["event"], m["team1"]["name"], m["team2"]["name"], m["date"], m["time"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(m)

    # 场次硬上限;优先保 live,其次预告,最后战绩(从尾部砍)
    if len(uniq) > MAX_MATCHES:
        nlive = sum(1 for m in uniq if m["status"] == "live")
        head = uniq[:nlive]
        rest = uniq[nlive:]
        nupc = MAX_MATCHES - len(head)
        head += rest[:max(0, nupc)]
        uniq = head

    data = {"updated": now.strftime("%m-%d %H:%M"), "matches": uniq}

    # 字节预算:超了从尾部(战绩优先砍)再砍
    def size(d):
        return len(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    while size(data) > MAX_BYTES and len(data["matches"]) > 1:
        for i in range(len(data["matches"]) - 1, -1, -1):
            if data["matches"][i]["status"] == "finished":
                del data["matches"][i]
                break
        else:
            data["matches"].pop()

    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "cs_matches.json"
    import os
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        table = load_team_table(repo_root)
        text = build(table)
    except Exception:
        print("抓取失败,保留旧数据:\n%s" % traceback.format_exc())
        sys.exit(1)

    n = len(text.encode("utf-8"))
    cnt = json.loads(text).get("matches") and len(json.loads(text)["matches"]) or 0
    print("生成 cs_matches.json: %d 场, %d 字节" % (cnt, n))

    # 内容没变就不写,工作流不会产生空提交
    try:
        with open(out_path, "rb") as f:
            old = f.read()
        if old == text.encode("utf-8"):
            print("数据无变化,跳过")
            return
    except FileNotFoundError:
        pass

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("已写入 %s" % out_path)


if __name__ == "__main__":
    main()
