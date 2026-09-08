"""NikoTracker data pipeline (GitHub Actions ready, stdlib only).

Fetches Liquipedia CS2 event pages, parses every Team Falcons series over the
last year, merges with the static base.json, and writes data.json that the web
page consumes. Designed to run unattended on GitHub Actions every 30 minutes.
"""
import datetime
import gzip
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).parent
UA = {
    "User-Agent": "NikoTracker/1.0 (CS2 fan page; contact: user@example.com)",
    "Accept-Encoding": "gzip",
}
API = "https://liquipedia.net/counterstrike/api.php?"

# Liquipedia page paths to fetch. Major splits into the main page + Stage_3 + Playoffs.
PAGES = [
    "BLAST/Open/2025/Fall",
    "FISSURE/Playground/2",
    "FISSURE/Playground/3",
    "ESL/Pro_League/Season_22",
    "BLAST/Bounty/2026/Winter",
    "Intel_Extreme_Masters/2026/Kraków",
    "PGL/2026/Cluj-Napoca",
    "BLAST/Open/2026/Spring",
    "BLAST/Open/2026/Fall",
    "Intel_Extreme_Masters/2026/Rio",
    "PGL/2026/Astana",
    "CS_Asia_Championships/2026",
    "Esports_World_Cup/2026",
    "Intel_Extreme_Masters/2026/Cologne",
    "BLAST/Bounty/2026/Summer",
    "Intel_Extreme_Masters/2026/Cologne/Stage_3",
    "Intel_Extreme_Masters/2026/Cologne/Playoffs",
    "BLAST/Bounty/2026/Summer/Qualifier",
]

EVENT_NAMES = {
    "BLAST/Open/2025/Fall": "BLAST 公开赛 2025 秋季",
    "FISSURE/Playground/2": "FISSURE Playground #2",
    "FISSURE/Playground/3": "FISSURE Playground #3",
    "ESL/Pro_League/Season_22": "ESL 职业联赛 S22",
    "BLAST/Bounty/2026/Winter": "BLAST Bounty 冬季赛 2026",
    "Intel_Extreme_Masters/2026/Kraków": "IEM 克拉科夫 2026",
    "PGL/2026/Cluj-Napoca": "PGL 克卢日-纳波卡 2026",
    "BLAST/Open/2026/Spring": "BLAST 公开赛 鹿特丹站",
    "BLAST/Open/2026/Fall": "BLAST 波尔图公开赛",
    "Intel_Extreme_Masters/2026/Rio": "IEM 里约 2026",
    "PGL/2026/Astana": "PGL 阿斯塔纳 2026",
    "CS_Asia_Championships/2026": "CS 亚洲锦标赛 2026",
    "Esports_World_Cup/2026": "电竞世界杯 2026",
    "Intel_Extreme_Masters/2026/Cologne": "IEM 科隆 Major 2026",
    "BLAST/Bounty/2026/Summer": "BLAST Bounty 夏季赛 2026",
    "Intel_Extreme_Masters/2026/Cologne/Stage_3": "IEM 科隆 Major 2026",
    "Intel_Extreme_Masters/2026/Cologne/Playoffs": "IEM 科隆 Major 2026",
    "BLAST/Bounty/2026/Summer/Qualifier": "BLAST Bounty 夏季赛资格赛",
}

SINCE = datetime.datetime(2025, 9, 1, tzinfo=datetime.timezone.utc)


def fetch(page, tries=4):
    url = API + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "text", "format": "json"})
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            r = urllib.request.urlopen(req, timeout=90)
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))["parse"]["text"]["*"]
        except Exception as e:
            last = e
            time.sleep(10)
    print(f"  FETCH FAIL {page}: {last}", file=sys.stderr)
    return None


def parse_matches(html):
    from parse_popup import extract
    out = []
    for m in extract(html):
        if "Falcons" not in m["left"] + m["right"]:
            continue
        if not m["ts"]:
            continue
        dt = datetime.datetime.fromtimestamp(m["ts"], datetime.timezone.utc)
        if dt < SINCE:
            continue
        fi = 0 if "Falcons" in m["left"] else 1
        opp = (m["right"] if fi == 0 else m["left"]).replace("Team ", "")
        fs, os_ = m["score"][fi], m["score"][1 - fi]
        out.append({
            "date": dt.strftime("%Y-%m-%dT%H:%M:00Z"),
            "opponent": opp,
            "score": f"{fs}-{os_}",
            "result": "W" if (m["left_win"] == (fi == 0)) else "L",
            "bo": m["bo"],
            "event": None,
            "stage": "",
            "niko": {"ratings": []},
        })
    return out


def main():
    base = json.loads((ROOT / "base.json").read_text(encoding="utf-8"))
    known = {(d["date"], d["opponent"]): d["ratings"] for d in base.get("known_ratings", [])}

    all_matches = []
    for i, page in enumerate(PAGES):
        html = fetch(page)
        if html is None:
            continue
        print(f"  [{i+1}/{len(PAGES)}] {page} -> {len(html)} bytes, "
              f"scoreholders={html.count('match-info-header-scoreholder\"')}", flush=True)
        name = EVENT_NAMES.get(page, page.split("/")[-1].replace("_", " "))
        for mm in parse_matches(html):
            mm["event"] = name
            all_matches.append(mm)
        if i + 1 < len(PAGES):
            time.sleep(31)  # Liquipedia: 1 parse request / 30s

    seen, uniq = set(), []
    for m in sorted(all_matches, key=lambda x: x["date"], reverse=True):
        k = (m["date"], m["opponent"], m["score"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(m)

    for m in uniq:
        m["niko"] = {"ratings": known.get((m["date"][:10], m["opponent"]), [])}

    w = sum(1 for m in uniq if m["result"] == "W")
    base["recent_matches"] = uniq
    base["year_stats"] = {
        "span": "近一年",
        "from": uniq[-1]["date"][:10] if uniq else "",
        "to": uniq[0]["date"][:10] if uniq else "",
        "matches": len(uniq),
        "wins": w,
        "losses": len(uniq) - w,
        "win_rate": round(w / len(uniq) * 100, 1) if uniq else 0,
        "events": len(set(m["event"] for m in uniq)),
    }
    base["meta"]["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    (ROOT / "data.json").write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK matches={len(uniq)} {w}W-{len(uniq)-w}L "
          f"winrate={base['year_stats']['win_rate']}% events={base['year_stats']['events']} "
          f"updated={base['meta']['updated']}")


if __name__ == "__main__":
    main()
