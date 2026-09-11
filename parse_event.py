"""把 Liquipedia 赛事页解析成结构化数据：参赛队伍 / 分组积分 / 分支图 / 赛程。

设计要点
--------
1) 分支图的轮次判定：Liquipedia 的 `brkts-round-body` 是**嵌套**的，
   越早的轮次嵌套越深。用祖先栈统计某个对阵身处几层 `brkts-round-body`，
   得到 depth；轮次序号 = maxDepth - depth。这样**轮空(bye)**也能正确归位
   （轮空队伍的首场比赛天然更浅 = 更晚的轮次）。
2) 胜负与比分要**按条目分别取**，不能整块正则（否则只会拿到胜者那一格）。
3) 参赛队伍来自 `team-participant-card`，标题来自最近的上一个 h2/h3/h4。
"""
import html as H
import re
from datetime import datetime, timezone

DIV_TOK = re.compile(r"<div\b([^>]*)>|</div>", re.I)

# ---------------------------------------------------------------- 小工具

def _cls(attrs: str) -> str:
    m = re.search(r'class="([^"]*)"', attrs or "")
    return m.group(1) if m else ""


def _text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = H.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def prep(h: str) -> str:
    """MediaWiki 会把类名里的下划线转义成 &#95;，先还原，否则类名全都匹配不到。"""
    return h.replace("&#95;", "_")


def headings(h: str):
    """返回 [(位置, 层级, 标题)]。"""
    out = []
    for m in re.finditer(r"<h([2-6])\b[^>]*>(.*?)</h\1>", h, re.S):
        t = _text(m.group(2))
        t = re.sub(r"\[edit\]$", "", t).strip()
        if t:
            out.append((m.start(), int(m.group(1)), t))
    return out


def nearest_heading(h: str, pos: int, hs=None) -> str:
    hs = hs if hs is not None else headings(h)
    best = ""
    for p, lvl, t in hs:
        if p < pos:
            best = t
        else:
            break
    return best


def section_html(h: str, name: str, hs=None) -> str:
    """取某个标题到下一个同级或更高级标题之间的 HTML。"""
    hs = hs if hs is not None else headings(h)
    for i, (p, lvl, t) in enumerate(hs):
        if t.lower() == name.lower():
            end = len(h)
            for p2, lvl2, _ in hs[i + 1:]:
                if lvl2 <= lvl:
                    end = p2
                    break
            return h[p:end]
    return ""


# ---------------------------------------------------------------- 参赛队伍

def parse_participants(h: str):
    """从 Participants 区取参赛队伍（含队标），按出现顺序去重。"""
    h = prep(h)
    seg = section_html(h, "Participants")
    if not seg:
        return []
    out, seen = [], set()
    # 队伍卡片：block-team team-participant-card__opponent … <a title="Team Falcons"><img src=...>
    for blk in re.split(r'team-participant-card__opponent(?:"|\s)', seg)[1:]:
        head = blk[:1200]
        nm = re.search(r'<a href="/counterstrike/[^"]+" title="([^"]+)"', head)
        if not nm:
            continue
        name = H.unescape(nm.group(1)).strip()
        if not name or name in seen:
            continue
        # 只要 lightmode / allmode 那一张，不要 darkmode
        logo = ""
        for im in re.finditer(r'<img[^>]*src="([^"]+)"', head):
            u = im.group(1)
            if "darkmode" in u:
                continue
            logo = u
            break
        seen.add(name)
        out.append({"name": name, "logo": logo})
    return out


# ---------------------------------------------------------------- 分组/瑞士轮

_ROUND_COLS = re.compile(r"^Round\s*(\d+)$", re.I)


def _standings_rows(seg: str):
    """积分表数据行 -> [{team, nums}]，跳过 TBD 占位行。"""
    rows = []
    for rm in re.finditer(r"<tr>(.*?)</tr>", seg, re.S):
        r = rm.group(1)
        if "<th" in r[:40]:
            continue
        # 队名：瑞士轮用 grouptableslot 里的 data-highlightingclass
        team = ""
        for m in re.finditer(r'data-highlightingclass="([^"]+)"', r):
            v = H.unescape(m.group(1)).strip()
            if v and v.upper() != "TBD":
                team = v
                break
        if not team:
            tn = re.search(r'<a href="/counterstrike/[^"]+" title="([^"]+)"', r)
            if tn:
                team = H.unescape(tn.group(1)).strip()
        if not team or team.upper() == "TBD":
            continue
        tds = re.findall(r"<td\b[^>]*>(.*?)</td>", r, re.S)
        nums = []
        for td in tds:
            t = _text(td)
            if re.fullmatch(r"\d+(?:[.:\-]\d+)?", t or ""):
                nums.append(t)
        rows.append({"team": re.sub(r"^Team\s+", "", team), "nums": nums})
    return rows


def parse_group_tables(h: str):
    """解析 Overview / Group Stage 里的分组/瑞士轮积分表。"""
    h = prep(h)
    out = []
    for tm in re.finditer(r'<table[^>]*class="[^"]*(?:swisstable|table2__table|wikitable)[^"]*"[^>]*>', h):
        start = tm.start()
        end = h.find("</table>", start)
        if end < 0:
            continue
        seg = h[start:end]
        title = nearest_heading(h, start) or "积分榜"
        head = re.search(r"<tr>(.*?)</tr>", seg, re.S)
        if not head:
            continue
        cols = [_text(c) for c in re.findall(r"<th\b[^>]*>(.*?)</th>", head.group(1), re.S)]
        cols = [c for c in cols if c]
        joined = " ".join(cols).lower()
        # 只认「队伍 + 战绩」型积分表，跳过国家分布之类
        if "team" not in joined or not any(k in joined for k in ("matches", "rounds", "pts", "points", "w")):
            continue
        rows = _standings_rows(seg)
        if len(rows) < 2:
            continue
        out.append({"title": title, "cols": cols, "rows": rows})
    # 合并同名表（宽/窄两份取并集）
    merged = {}
    for t in out:
        key = t["title"]
        if key not in merged:
            merged[key] = t
        else:
            have = {r["team"] for r in merged[key]["rows"]}
            for r in t["rows"]:
                if r["team"] not in have:
                    merged[key]["rows"].append(r)
    return list(merged.values())


# ---------------------------------------------------------------- 分支图

def _ancestor_depth(h: str, pos: int) -> int:
    """pos 处的元素，祖先里有几个 brkts-round-body（真·栈，闭合要配对）。"""
    stack, depth = [], 0
    for m in DIV_TOK.finditer(h, 0, pos):
        attrs = m.group(1)
        if attrs is None:                       # </div>
            if stack:
                if stack.pop():
                    depth -= 1
        else:
            is_rb = "brkts-round-body" in _cls(attrs)
            stack.append(is_rb)
            if is_rb:
                depth += 1
    return depth


def _entries(blk: str):
    """一个 brkts-match 里的两个对阵条目，逐条取胜负与比分。"""
    # 注意：不能用 \b —— `brkts-opponent-entry-left` 也会命中（- 前也是词边界），
    # 必须要求 entry 后面紧跟引号或空白，即真正的条目容器。
    marks = [m.start() for m in re.finditer(r'<div class="brkts-opponent-entry(?:"|\s)', blk)]
    out = []
    for i, s in enumerate(marks[:2]):
        p = blk[s: (marks[i + 1] if i + 1 < len(marks) else len(blk))]
        nm = re.search(r'aria-label="([^"]*)"', p[:400])
        short = re.search(r'data-team-shortname="([^"]*)"', p[:1500])
        sc = re.search(r'brkts-opponent-score-inner[^>]*>\s*(?:<b>)?\s*(\d+)', p)
        # 胜负标记在条目自己的 entry-left 上
        win = bool(re.search(r'brkts-opponent-entry-left[^"]*brkts-opponent-win', p[:600]))
        name = H.unescape(nm.group(1)).strip() if nm else ""
        name = re.sub(r"^Team\s+", "", name)
        if name.upper() in ("TBD", "TO BE DETERMINED", "–", "-"):
            name = ""
        out.append({
            "name": name,
            "full": name,
            "short": H.unescape(short.group(1)).strip() if short else "",
            "score": int(sc.group(1)) if sc else None,
            "win": win,
        })
    return out


def parse_brackets(h: str):
    """返回 [ {title, rounds:[{name, matches:[...]}]} ]"""
    hs = headings(h)
    starts = [m.start() for m in re.finditer(r'<div class="brkts-bracket[ "]', h)]
    brackets = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(h)
        body = h[s:end]
        # 截断到本容器真实结束（避免把后续无关内容算进来）
        mpos = [m.start() for m in re.finditer(r'<div class="brkts-match[ "]', body)]
        if not mpos:
            continue
        cut = min(len(body), mpos[-1] + 60000)
        body = body[:cut]

        heads = [H.unescape(x).strip()
                 for x in re.findall(r'<div class="brkts-header brkts-header-div"[^>]*>([^<]*)', body)]
        heads = [x for x in heads if x and x.lower() not in ("qualified", "eliminated")]

        matches = []
        for k, mi in enumerate(mpos):
            blk = body[mi: (mpos[k + 1] if k + 1 < len(mpos) else len(body))]
            ent = _entries(blk)
            if len(ent) < 2:
                continue
            # 赛前占位对阵（两边都还没队名）直接丢掉
            if not ent[0]["name"] and not ent[1]["name"]:
                continue
            ts = re.search(r'data-timestamp="(\d+)"', blk)
            bo = re.search(r'scoreholder-lower">\((Bo\d)\)', blk)
            details = re.search(r'data-highlighted-match|brkts-match-has-details', blk)
            matches.append({
                "a": ent[0], "b": ent[1],
                "ts": int(ts.group(1)) if ts else None,
                "bo": bo.group(1) if bo else "",
                "depth": _ancestor_depth(body, mi),
            })
        if not matches:
            continue
        maxd = max(m["depth"] for m in matches)
        for m in matches:
            m["round"] = maxd - m["depth"]
        nround = maxd
        rounds = []
        for r in range(nround + 1):
            ms = [m for m in matches if m["round"] == r]
            if not ms:
                continue
            name = heads[r] if r < len(heads) else f"第 {r + 1} 轮"
            ms.sort(key=lambda x: (x["ts"] or 0, x["a"]["name"]))
            rounds.append({"name": name, "matches": ms})
        if rounds:
            brackets.append({"title": nearest_heading(h, s, hs) or "分支图",
                             "rounds": rounds, "count": len(matches)})
    # 去重：同一容器窄/宽两份
    seen, uniq = set(), []
    for b in brackets:
        key = (b["title"], b["count"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    return uniq


# ---------------------------------------------------------------- 赛程 / 比分

def parse_schedule(h: str, limit=40):
    """从分支图里抽出带时间戳的对阵，作为赛程与实时比分来源。"""
    rows = []
    for b in parse_brackets(h):
        for rd in b["rounds"]:
            for m in rd["matches"]:
                if not m["ts"]:
                    continue
                rows.append({
                    "stage": b["title"],
                    "round": rd["name"],
                    "bo": m["bo"],
                    "ts": m["ts"],
                    "a": m["a"], "b": m["b"],
                })
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda x: x["ts"]):
        k = (r["ts"], r["a"]["name"], r["b"]["name"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq[:limit]


# ---------------------------------------------------------------- 概览信息

def parse_overview(h: str, name: str):
    """日期 / 赛制 / 奖池 / 地点 等。"""
    h = prep(h)
    out = {"name": name}
    about = section_html(h, "About")
    prize = section_html(h, "Prize Pool")
    fmt = section_html(h, "Format")

    def grab(seg, pats, keys):
        for pat, key in zip(pats, keys):
            m = re.search(pat, seg, re.S)
            if m:
                out[key] = _text(m.group(1))[:80]

    grab(about, [r'<div class="infobox-cell-2[^"]*">Dates?</div>\s*<div[^>]*>(.*?)</div>',
                 r'>Dates?</t[dh]>\s*<td[^>]*>(.*?)</td>',
                 r'<div class="infobox-cell-2[^"]*">Location</div>\s*<div[^>]*>(.*?)</div>',
                 r'<div class="infobox-cell-2[^"]*">Venue</div>\s*<div[^>]*>(.*?)</div>',
                 r'<div class="infobox-cell-2[^"]*">Prize Pool</div>\s*<div[^>]*>(.*?)</div>',
                 r'<div class="infobox-cell-2[^"]*">Teams</div>\s*<div[^>]*>(.*?)</div>'],
                ["dates", "dates", "location", "venue", "prize", "teams"])
    if "prize" not in out and prize:
        m = re.search(r'\$[\d,\.]+', _text(prize))
        if m:
            out["prize"] = m.group(0)
    if fmt:
        out["format_raw"] = _text(fmt)[:400]
    return out


def build(page_name, html_text, display_name=""):
    return {
        "page": page_name,
        "info": parse_overview(html_text, display_name or page_name),
        "participants": parse_participants(html_text),
        "groups": parse_group_tables(html_text),
        "brackets": parse_brackets(html_text),
        "schedule": parse_schedule(html_text),
    }


if __name__ == "__main__":
    import pathlib, sys, json
    for f in sys.argv[1:]:
        h = pathlib.Path(f).read_text(encoding="utf-8")
        d = build(pathlib.Path(f).stem, h, pathlib.Path(f).stem)
        print(f"===== {f}")
        print("  info:", {k: v for k, v in d["info"].items() if k != "format_raw"})
        print("  参赛队:", len(d["participants"]), [p["name"] for p in d["participants"]][:8])
        print("  分组表:", [(g["title"], len(g["rows"]), g["rows"][0]["nums"] if g["rows"] else []) for g in d["groups"]][:6])
        for b in d["brackets"]:
            print(f"  分支[{b['title']}] 共{b['count']}场:")
            for rd in b["rounds"]:
                print(f"     {rd['name']}: " + ", ".join(
                    f"{m['a']['name']} {m['a']['score']}-{m['b']['score']} {m['b']['name']}"
                    for m in rd["matches"][:6]))
        print("  赛程:", len(d["schedule"]))
