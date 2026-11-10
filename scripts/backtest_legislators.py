#!/usr/bin/env python3
"""Backtest of the needle on the 73 legislative districts (2020, 2024): python3 scripts/backtest_legislators.py

Each district is scored at 1/5/10/20/30/70% of its stations against its final count, for several baselines.
"""
import sys, math, warnings; warnings.filterwarnings('ignore'); sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import needle as N, stations as ST
CP = (0.01, 0.05, 0.1, 0.2, 0.3, 0.7)
def run(night, base):
    res, skipped = [], []
    for key in sorted(ST.load(night)):
        try: ns = N.Night(night, key, base)
        except Exception as e: skipped.append((key, str(e)[:60])); continue
        if ns.base is None: skipped.append((key, ns.how)); continue
        M = len(ns.st); fin = ns.final_axis - ns.final_rival; two = ns.final_axis + ns.final_rival
        row = {'key': key, 'margin': 100 * fin / two, 'at': {}}
        for f in CP:
            e = ns.estimate(max(1, int(f * M)))
            pw = e['p'] if fin > 0 else 1 - e['p']
            row['at'][f] = (pw, 100 * abs(e['mean'] - fin) / two, abs(e['mean'] - fin) <= 1.2816 * e['sd'])
        # wrong-way after 5%
        mx = 0
        for n in range(max(1, int(0.05 * M)), M + 1, max(1, M // 40)):
            e = ns.estimate(n); mx = max(mx, (1 - e['p']) if fin > 0 else e['p'])
        row['wrong'] = mx
        res.append(row)
    return res, skipped
for night, bases in (('2020-legislator', ['2016-president', '2016-president+2016-legislator', '2016-president+2018-mayors']),
                     ('2024-legislator', ['2020-president', '2020-president+2022-mayors', '2020-president+2020-legislator'])):
    for base in bases:
        res, sk = run(night, base)
        out = []
        for f in CP:
            xs = [r['at'][f] for r in res]
            out.append(f"{int(f*100)}%: fav {sum(x[0] > .5 for x in xs)}/{len(xs)} err {sum(x[1] for x in xs)/len(xs):.1f} in80 {sum(x[2] for x in xs)/len(xs):.2f} ll {sum(-math.log(max(x[0],1e-6)) for x in xs)/len(xs):.3f}")
        print(night, base, '|', ' | '.join(out))
        print('   wrong-way>=0.9:', [(r['key'], round(r['wrong'], 3), round(r['margin'], 1)) for r in res if r['wrong'] >= 0.9], 'skipped:', sk)
