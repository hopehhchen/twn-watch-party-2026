#!/usr/bin/env python3
"""Party-list vote (不分區) over election night: projected shares, seats and the chance of each seat split.

  python3 scripts/party_vote.py            # calibration table for 2020 and 2024

Projection, at each moment, from the stations counted so far (nothing from later in the night):
  - parties that ran last time: a proportional swing. At counted stations, a party got r times what its
    village shares in the previous party-list vote would have given it; stations still out get their
    village's previous share times r.
  - new parties (no previous vote): their counted share in the district (行政區), shrunk toward the county.
  - votes still out: each station's electors times the valid-vote rate (valid votes / electors) at the
    county's counted stations so far.
Uncertainty: each party's share gets a normal error, sd = C_SD * sqrt(p(1-p)) * (share of votes still out),
plus NEW_PARTY_SD for parties with no previous vote; C_SD is calibrated on 2020 and 2024 (below).
Seats: 34, parties at 5% or more, largest remainder (Hare-Niemeyer), from 1,000 draws.
"""
import math
import random
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stations as ST  # noqa: E402

SEATS, THRESHOLD = 34, 0.05
C_SD = 0.025  # calibrated on 2020 and 2024 (python3 scripts/party_vote.py); ranges run wide after 20% counted
NEW_PARTY_SD = 0.5  # extra sd for parties with no previous vote, as a multiple of the same formula
DRAWS = 1000
EARLY_N = 200  # sd x (1 + sqrt(EARLY_N / stations in)): x2 at 200 stations, x1.3 at 2,000
MIN_STATIONS = 50  # no seat odds before this many stations


def hare(shares, seats=SEATS):
    """{party: share} -> ({party: seats}, party that got the last seat awarded by remainder)."""
    ok = {p: s for p, s in shares.items() if s >= THRESHOLD}
    tot = sum(ok.values())
    if not tot:
        return {}, None
    q = {p: seats * s / tot for p, s in ok.items()}
    out = {p: int(v) for p, v in q.items()}
    left = seats - sum(out.values())
    order = sorted(q, key=lambda p: -(q[p] - out[p]))[:left]
    for p in order:
        out[p] += 1
    return out, (order[-1] if order else max(q, key=lambda p: q[p] - out[p] + 1))


def prev_shares(prev):
    """{(county, district, village): {party: share}}, plus district- and county-level fallbacks."""
    vb, d, c = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for county, r in ST.load(prev).items():
        names = [x["name"] for x in r["cands"]]
        for s in r["stations"]:
            for n, v in zip(names, s["v"]):
                vb[(county, s["district"], s["village"])][n] += v
                d[(county, s["district"])][n] += v
                c[county][n] += v

    def norm(m):
        return {k: {p: v / sum(x.values()) for p, v in x.items()} for k, x in m.items() if sum(x.values())}
    return norm(vb), norm(d), norm(c)


class PartyNight:
    def __init__(self, night, prev):
        tm = ST.times(night)
        self.st = []
        for county, r in ST.load(night).items():
            names = [x["name"] for x in r["cands"]]
            for s in r["stations"]:
                self.st.append((tm[(county, s["district"], s["no"])], county, s, names))
        self.st.sort(key=lambda x: x[0])
        self.parties = sorted({n for *_, names in self.st for n in names})
        vb, db, cb = prev_shares(prev)
        self.known = {p for m in cb.values() for p in m}
        self.base = []  # per station: {party: previous share}
        for _, county, s, _ in self.st:
            self.base.append(vb.get((county, s["district"], s["village"])) or db.get((county, s["district"])) or cb.get(county) or {})
        self.final = defaultdict(float)
        for _, _, s, names in self.st:
            for n, v in zip(names, s["v"]):
                self.final[n] += v

    def project(self, n):
        """Projected final shares and their sds after the first n stations (in report order)."""
        cnt, exp = defaultdict(float), defaultdict(float)
        dc, dt, cc, ct = defaultdict(lambda: defaultdict(float)), defaultdict(float), defaultdict(lambda: defaultdict(float)), defaultdict(float)
        cv, ce = defaultdict(float), defaultdict(float)  # county valid votes and electors at counted stations
        for i in range(n):
            _, county, s, names = self.st[i]
            V = sum(s["v"])
            cv[county] += V
            ce[county] += s["E"]
            dt[(county, s["district"])] += V
            ct[county] += V
            b = self.base[i]
            for nm, v in zip(names, s["v"]):
                cnt[nm] += v
                dc[(county, s["district"])][nm] += v
                cc[county][nm] += v
                exp[nm] += V * b.get(nm, 0)
        Cn = sum(cnt.values()) or 1
        rate_all = sum(cv.values()) / max(sum(ce.values()), 1) if ce else 0.6
        proj, left = defaultdict(float), 0.0
        for i in range(n, len(self.st)):
            _, county, s, names = self.st[i]
            Vhat = s["E"] * (cv[county] / ce[county] if ce[county] else rate_all)
            left += Vhat
            b = self.base[i]
            d = (county, s["district"])
            w = dt[d] / (dt[d] + 20000)
            for nm in names:
                if nm in self.known and exp[nm] > 0 and b.get(nm, 0) > 0:
                    proj[nm] += Vhat * b[nm] * cnt[nm] / exp[nm]
                else:
                    cs = cc[county][nm] / ct[county] if ct[county] else cnt[nm] / Cn
                    proj[nm] += Vhat * ((dc[d][nm] / dt[d]) * w + cs * (1 - w) if dt[d] else cs)
        tot = {p: cnt[p] + proj[p] for p in self.parties}
        T = sum(tot.values()) or 1
        share = {p: v / T for p, v in tot.items()}
        out_frac = left / (left + Cn)
        early = 1 + math.sqrt(EARLY_N / max(n, 1))  # few stations in: the swing itself is still unknown
        sd = {p: C_SD * math.sqrt(max(share[p] * (1 - share[p]), 0)) * out_frac * early * (1 + (NEW_PARTY_SD if p not in self.known else 0))
              for p in self.parties}
        counted = {p: cnt[p] / Cn for p in self.parties}
        return share, sd, counted, out_frac

    def seat_odds(self, share, sd, rng):
        """From DRAWS normal draws: the chance of each seat split (top splits), and of each party clearing 5%."""
        top = [p for p in self.parties if share[p] > 0.005]
        splits, clear = defaultdict(int), defaultdict(int)
        for _ in range(DRAWS):
            dr = {p: max(0.0, rng.gauss(share[p], sd[p])) for p in top}
            T = sum(dr.values())
            dr = {p: v / T for p, v in dr.items()}
            seats, _ = hare(dr)
            splits[tuple(sorted((p, k) for p, k in seats.items() if k))] += 1
            for p in top:
                clear[p] += dr[p] >= THRESHOLD
        ranked = sorted(splits.items(), key=lambda x: -x[1])
        return [(dict(k), v / DRAWS) for k, v in ranked], {p: clear[p] / DRAWS for p in top}


def calibrate(c_values=(0.025,)):
    global C_SD
    nights = [(n, p, PartyNight(n, p)) for n, p in (("2020-party", "2016-party"), ("2024-party", "2020-party"))]
    for c in c_values:
        C_SD = c
        print(f"C_SD = {c}")
        for night, prev, pn in nights:
            V = sum(pn.final.values())
            fsh = {p: v / V for p, v in pn.final.items()}
            fseats, _ = hare(fsh)
            fkey = {p: k for p, k in fseats.items() if k}
            rng = random.Random(1)
            row = []
            for f in (0.01, 0.05, 0.1, 0.2, 0.3, 0.7):
                share, sd, counted, out = pn.project(int(f * len(pn.st)))
                big = [p for p in pn.parties if fsh[p] > 0.01]
                cov = sum(abs(share[p] - fsh[p]) <= 1.2816 * sd[p] for p in big) / len(big)
                splits, clear = pn.seat_odds(share, sd, rng)
                pf = next((pr for sp, pr in splits if sp == fkey), 0.0)
                row.append(f"{int(100 * f)}%: held {cov:.2f}, P(final split) {pf:.2f}, top {splits[0][1]:.2f}{' =final' if splits[0][0] == fkey else ''}")
            print("  ", night, " | ".join(row))


if __name__ == "__main__":
    calibrate()
