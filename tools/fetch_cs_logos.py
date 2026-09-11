#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
按 tools/cs_teams.json 清单,从 lootmarket/esport-team-logos 仓库下载真实战队队标 PNG。

用法:
    python tools/fetch_cs_logos.py --out .cache/logos            # 下全部
    python tools/fetch_cs_logos.py --out .cache/logos --only g2 navi

下载完再用 tools/gen_csboard_assets.py 生成 main/cs_assets.c。
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://raw.githubusercontent.com/lootmarket/esport-team-logos/master/csgo/'


def pick_png(tree, repo_dir):
    files = [f for f in tree.get(repo_dir, []) if f.lower().endswith('.png')]
    if not files:
        return None
    exact = [f for f in files if f.lower() == (repo_dir + '-logo.png').lower()]
    if exact:
        return exact[0]
    logo = [f for f in files if 'logo' in f.lower()] or files
    logo.sort(key=lambda x: (len(x), x))
    return logo[0]


def fetch_tree(ctx):
    url = 'https://api.github.com/repos/lootmarket/esport-team-logos/git/trees/master?recursive=1'
    req = urllib.request.Request(url, headers={'User-Agent': 'wb',
                                               'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
        t = json.loads(r.read())
    tree = {}
    for e in t.get('tree', []):
        p = e['path']
        if e['type'] != 'blob' or not p.lower().startswith('csgo/') or not p.lower().endswith('.png'):
            continue
        parts = p.split('/')
        tree.setdefault(parts[1], []).append('/'.join(parts[2:]))
    return tree


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument('--manifest', default=os.path.join(here, 'cs_teams.json'))
    ap.add_argument('--out', required=True, help='PNG 输出目录')
    ap.add_argument('--only', nargs='*', help='只下这些 id')
    ap.add_argument('--workers', type=int, default=6)
    a = ap.parse_args()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    man = json.load(open(a.manifest, encoding='utf-8'))['teams']
    if a.only:
        want = {x.lower() for x in a.only}
        man = [t for t in man if t['id'].lower() in want]
    os.makedirs(a.out, exist_ok=True)

    tree = fetch_tree(ctx)
    print('csgo 战队目录数 =', len(tree))

    def one(t):
        tid, rd = t['id'], t['repo']
        dst = os.path.join(a.out, tid + '.png')
        if os.path.exists(dst) and os.path.getsize(dst) > 200:
            return (tid, 'cached', 0)
        sub = pick_png(tree, rd)
        if not sub:
            return (tid, 'NOPNG', 0)
        url = BASE + rd + '/' + sub
        err = ''
        for _ in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'wb'})
                with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
                    data = r.read()
                if len(data) > 200:
                    open(dst, 'wb').write(data)
                    return (tid, 'ok', len(data))
                return (tid, 'TOOSMALL', len(data))
            except Exception as e:
                err = type(e).__name__
                time.sleep(1)
        return (tid, 'FAIL:' + err, 0)

    ok = bad = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for tid, st, n in ex.map(one, man):
            if st in ('ok', 'cached'):
                ok += 1
            else:
                bad += 1
                print('  !!', tid, st)
    print('[ok] %d 张,失败 %d 张 -> %s' % (ok, bad, a.out))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
