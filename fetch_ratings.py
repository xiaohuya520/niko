"""NiKo 逐图 rating 回补工具（本地 / GitHub Actions 通用）。

背景：data.json 里 NiKo 每图 Rating 2.1 大量缺失。HLTV（唯一公开数据源）
对数据中心 IP 全线上 Cloudflare 挑战（本机沙箱、GitHub Actions、公共代理
都实测 403），所以本工具设计成「能抓就抓、抓不到就优雅退出」的幂等工具：

1. 读 data.json，找出缺 rating 的（日期, 对手）场次；
2. 逐图尝试 HLTV mapstats 页（links.hltv_maps 已有现成链接），
   连续 2 次被挑战/403 就立即停止（不硬刚 CF）；
3. 成功解析的写入 _cache/ratings/<mapid>.json 并合并进 ratings.json
   （该文件在仓库里持久保存，pipeline.assemble 每次构建都会合并）；
4. 任何时候运行 `python fetch_ratings.py --report` 可以看覆盖率。

用法：
    python fetch_ratings.py            # 尝试回补（网络不通时静默失败）
    python fetch_ratings.py --report   # 只打印覆盖率报告
"""
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CACHE = ROOT / "_cache" / "ratings"
STORE = ROOT / "ratings.json"


def opp_key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_store():
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def missing_list():
    """data.json 中缺 rating 的（date10, opponent, [mapids]）。"""
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    have = {(e.get("date"), opp_key(e.get("opponent") or ""))
            for e in load_store().get("entries", [])}
    out = []
    for m in data.get("recent_matches", []):
        d10 = m["date"][:10]
        k = opp_key(m["opponent"])
        if any(d10 == a and (k == b or k.startswith(b) or b.startswith(k))
               for a, b in have):
            continue
        maps = (m.get("links") or {}).get("hltv_maps") or []
        ids = []
        for mp in (m.get("maps") or []):
            if not mp.get("vetoed"):
                ids.append(None)
        # hltv_maps 的 game 序号对应非 veto 图的顺序
        game_to_url = {x["game"]: x["url"] for x in maps}
        idx = 0
        urls = []
        for mp in (m.get("maps") or []):
            if mp.get("vetoed"):
                continue
            idx += 1
            urls.append(game_to_url.get(idx))
        out.append({"date": d10, "opponent": m["opponent"], "urls": urls})
    return out


def mapid_from_url(u):
    if not u:
        return None
    q = urllib.parse.urlparse(u).query
    mm = re.search(r"matchid=(\d+)", q)
    if mm:
        return mm.group(1)
    mm = re.search(r"mapstatsid/(\d+)", u)
    return mm.group(1) if mm else None


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_niko_row(html):
    """从 mapstats 页抽 NiKo 那一行的 (kd, adr, rating2.1)。"""
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if not re.search(r">NiKo<", row):
            continue
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 6:
            rating = cells[-1]
            try:
                return {"kd": cells[1], "adr": cells[3], "rating": float(rating)}
            except ValueError:
                return None
    return None


def try_backfill(dry=False):
    todo = missing_list()
    total_missing_maps = sum(len([u for u in t["urls"] if u]) for t in todo)
    print(f"缺 rating 的场次：{len(todo)} 场 / 约 {total_missing_maps} 图")
    if dry:
        return

    CACHE.mkdir(parents=True, exist_ok=True)
    store = load_store()
    entries = store.setdefault("entries", [])
    got, fail_streak = 0, 0
    for t in todo:
        per_map = []
        ok_all = True
        for u in t["urls"]:
            mid = mapid_from_url(u)
            if not u or not mid:
                ok_all = False
                continue
            cf = CACHE / f"{mid}.json"
            if cf.exists():
                per_map.append(json.loads(cf.read_text(encoding="utf-8")))
                continue
            if fail_streak >= 2:
                print("  连续被 CF 挑战，本次停止（下次运行会继续尝试）")
                return
            try:
                html = fetch(u)
            except Exception as e:
                print(f"  {u} -> {type(e).__name__}")
                fail_streak += 1
                ok_all = False
                continue
            if "Just a moment" in html or "challenge" in html[:4000].lower():
                print(f"  mapstatsid={mid} 被 Cloudflare 挑战")
                fail_streak += 1
                ok_all = False
                time.sleep(2)
                continue
            fail_streak = 0
            row = parse_niko_row(html)
            if row:
                cf.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
                per_map.append(row)
                got += 1
                print(f"  {t['date']} vs {t['opponent']} map {mid}: rating {row['rating']}")
            else:
                print(f"  mapstatsid={mid} 未找到 NiKo 行")
                ok_all = False
            time.sleep(2.5)
        if ok_all and per_map:
            entries.append({
                "date": t["date"],
                "opponent": t["opponent"],
                "ratings": [r["rating"] for r in per_map],
                "kd": "/".join(r["kd"] for r in per_map if r.get("kd")) or None,
                "adr": round(sum(float(r["adr"]) for r in per_map
                                 if str(r.get("adr", "")).replace('.', '').isdigit())
                             / max(1, len(per_map)), 1) if per_map else None,
            })
            STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print(f"本次回补 {got} 图")


def report():
    todo = missing_list()
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    rm = data.get("recent_matches", [])
    have = len(rm) - len(todo)
    print(f"rating 覆盖：{have}/{len(rm)} 场（缺 {len(todo)}）")
    for t in todo[:8]:
        print(f"  - {t['date']} vs {t['opponent']}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        try_backfill(dry="--dry" in sys.argv)
        report()
