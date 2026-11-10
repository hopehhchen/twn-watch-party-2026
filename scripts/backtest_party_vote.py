#!/usr/bin/env python3
"""Party-list vote (不分區) projection, 2020 and 2024: python3 scripts/backtest_party_vote.py

Compares counted shares ("naive") with a proportional swing against the previous party-list vote, village by
village (new parties: their counted share in the district, shrunk toward the county), and the 34-seat
allocation (5% threshold, largest remainder) each would give, against the final.
"""
import sys, warnings, math; warnings.filterwarnings('ignore'); sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import stations as ST
from collections import defaultdict
SEATS, THR = 34, 0.05
def hare(shares, seats=SEATS):
    ok = {p: s for p, s in shares.items() if s >= THR}; tot = sum(ok.values())
    q = {p: seats * s / tot for p, s in ok.items()}; base = {p: int(v) for p, v in q.items()}
    left = seats - sum(base.values())
    for p in sorted(q, key=lambda p: -(q[p] - base[p]))[:left]: base[p] += 1
    return base
def stations(night):
    tm = ST.times(night); out = []
    for county, r in ST.load(night).items():
        names = [c['name'] for c in r['cands']]
        for s in r['stations']:
            out.append((tm[(county, s['district'], s['no'])], county, s, names))
    out.sort(key=lambda x: x[0]); return out
def village_base(prev):
    vb = defaultdict(lambda: defaultdict(float)); vt = defaultdict(float); db = defaultdict(lambda: defaultdict(float)); dt = defaultdict(float)
    for county, r in ST.load(prev).items():
        names = [c['name'] for c in r['cands']]
        for s in r['stations']:
            k = (county, s['district'], s['village']); d = (county, s['district'])
            for n, v in zip(names, s['v']): vb[k][n] += v; db[d][n] += v
            vt[k] += sum(s['v']); dt[d] += sum(s['v'])
    return vb, vt, db, dt
def run(night, prev):
    S = stations(night); final = defaultdict(float)
    for _, c, s, names in S:
        for n, v in zip(names, s['v']): final[n] += v
    V = sum(final.values()); fsh = {p: v / V for p, v in final.items()}; fseats = hare(fsh)
    print(night, 'final', {p: f"{100*x:.2f}%" for p, x in sorted(fsh.items(), key=lambda x: -x[1]) if x > 0.01}, fseats)
    if prev: vb, vt, db, dt = village_base(prev)
    N = len(S)
    for f in (0.01, 0.05, 0.1, 0.3, 0.7):
        n = int(f * N); cnt = defaultdict(float); exp = defaultdict(float)
        dc = defaultdict(lambda: defaultdict(float)); dtot = defaultdict(float); cc = defaultdict(lambda: defaultdict(float)); ctot = defaultdict(float)
        for _, c, s, names in S[:n]:
            tot = sum(s['v'])
            dtot[(c, s['district'])] += tot; ctot[c] += tot
            for nm, v in zip(names, s['v']): cnt[nm] += v; dc[(c, s['district'])][nm] += v; cc[c][nm] += v
            if prev:
                k = (c, s['district'], s['village']); src, t = (vb[k], vt[k]) if vt[k] else (db[(c, s['district'])], dt[(c, s['district'])])
                for nm in names: exp[nm] += tot * (src.get(nm, 0) / t if t else 0)
        C = sum(cnt.values()); naive = {p: v / C for p, v in cnt.items()}
        line = f"  {int(f*100):>2}%: naive err {100*sum(abs(naive.get(p,0)-fsh[p]) for p in fsh)/2:.2f} pts, seats {'OK' if hare(naive)==fseats else hare(naive)}"
        if prev:
            # proportional swing per party; parties with no baseline keep their counted share
            proj = defaultdict(float); Vleft = 0
            for _, c, s, names in S[n:]:
                tot = sum(s['v']); k = (c, s['district'], s['village']); src, t = (vb[k], vt[k]) if vt[k] else (db[(c, s['district'])], dt[(c, s['district'])])
                for nm in names:
                    b = src.get(nm, 0) / t if t else 0
                    if exp[nm] > 0 and b > 0: proj[nm] += tot * b * cnt[nm] / exp[nm]
                    else:  # no baseline (new party): its counted share in the district, else the county, else nationwide
                        d = (c, s['district']); w = dtot[d] / (dtot[d] + 20000)
                        cs = cc[c][nm] / ctot[c] if ctot[c] else naive.get(nm, 0)
                        proj[nm] += tot * ((dc[d][nm] / dtot[d]) * w + cs * (1 - w) if dtot[d] else cs)
            P = {p: cnt[p] + proj[p] for p in fsh}; T = sum(P.values()); P = {p: v / T for p, v in P.items()}
            line += f" | swing err {100*sum(abs(P.get(p,0)-fsh[p]) for p in fsh)/2:.2f} pts, seats {'OK' if hare(P)==fseats else hare(P)}"
        print(line)
run('2024-party', '2020-party'); run('2020-party', '2016-party')
