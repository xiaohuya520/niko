"""NikoTracker 数据管线（GitHub Actions 版，仅标准库）。

抓取 Liquipedia 赛事页 -> 解析 Team Falcons 每一场系列赛（含逐图回合比分、
上下半场拆分、HLTV 对局链接）-> 与 base.json / players.json 合并 -> 写出
data.json。由 .github/workflows/update.yml 每 30 分钟自动运行一次。

抓取与解析逻辑与本机的 pipeline.py / parse_detail.py 完全一致，
保证本地迭代和线上产出一致。

⚠ 关键安全阀（write_guard）：
Liquipedia 对数据中心 IP（含 GitHub Actions）限流很严，抓取失败时 pages 为空，
旧版本仍会把「0 场比赛」的空 data.json 写回仓库并 push —— 线上的真实战绩
（58 场）就被覆盖成 0，页面全部显示 0 胜 0 负。
现在写入前会拿新数据和仓库里已有的数据比一比，明显变少就放弃写入，
宁可用旧数据也不要把页面清空。
"""
import datetime
import gzip
import json
import pathlib
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

# 新数据至少要达到旧数据的这个比例，才允许覆盖写入
MIN_KEEP = 0.8

# 需要抓取的 Liquipedia 赛事页（Major 拆成主页面 + Stage_3 + Playoffs）
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


def fetch(page, tries=4):
    """抓一个赛事页的渲染后 HTML。Liquipedia 要求自定义 UA，且限流较严。"""
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
        except Exception as e:          # noqa: BLE001
            last = e
            time.sleep(10)
    print(f"  FETCH FAIL {page}: {last}", file=sys.stderr)
    return None


def count_matches(path):
    """读一个 data.json 里有多少场系列赛；读不到返回 0。"""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return len(d.get("recent_matches") or [])
    except Exception:                   # noqa: BLE001
        return 0


def main():
    sys.path.insert(0, str(ROOT))
    import pipeline

    base = json.loads((ROOT / "base.json").read_text(encoding="utf-8"))
    squad = []
    pfile = ROOT / "players.json"
    if pfile.exists():
        squad = json.loads(pfile.read_text(encoding="utf-8")).get("squad", [])

    pages = {}
    for i, page in enumerate(PAGES):
        html = fetch(page)
        if not html:
            continue
        pages[page] = html
        print(f"  [{i+1}/{len(PAGES)}] {page} -> {len(html)} bytes", flush=True)
        if i + 1 < len(PAGES):
            time.sleep(31)             # Liquipedia: action=parse 限 1 次 / 30 秒

    matches = pipeline.build_matches(pages)
    data = pipeline.assemble(base, matches, squad)

    # ---------- 安全阀：不允许用「更差的数据」覆盖仓库 ----------
    out = ROOT / "data.json"
    old_n = count_matches(out)
    new_n = len(matches)
    if new_n == 0 or (old_n and new_n < old_n * MIN_KEEP):
        print("=" * 64)
        print(f"[SKIP WRITE] 本次只抓到 {new_n} 场系列赛（仓库现有 {old_n} 场，"
              f"阈值 {MIN_KEEP:.0%}）")
        print(f"             成功抓取页面 {len(pages)}/{len(PAGES)} 个")
        print("             判断为 Liquipedia 限流/抓取失败，已放弃写入，")
        print("             保留仓库里已有的 data.json —— 页面不会被清成 0。")
        print("=" * 64)
        return 0

    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    st = data["year_stats"]
    with_maps = sum(1 for m in matches if m.get("maps"))
    print(f"OK matches={st['matches']} {st['wins']}W-{st['losses']}L "
          f"winrate={st['win_rate']}% events={st['events']} "
          f"with_map_detail={with_maps} squad={len(squad)} "
          f"updated={data['meta']['updated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
