#!/usr/bin/env python3
"""Does each town have its own swing size? A backtest of per-town elasticity, symmetric and by direction.

  python3 scripts/elasticity_review.py

The needle applies one countywide swing (in logit) to every station still out, plus a district (town)
deviation learned live from that town's own counted stations. Here each town also gets an elasticity from
earlier elections: how far its blue share moved when its county's moved (town shift / county shift, per pair
of same-kind elections, averaged and shrunk toward 1). Variants:

  elastic   one elasticity per town, from every earlier pair
  bydir     separate elasticities for blue swings and green swings; on the night the direction of the swing
            so far picks which one applies

On the night the counted stations' swings are divided by their towns' elasticity (and weighted by its square)
to estimate the county's swing, and each uncounted station gets its town's elasticity times that swing.
Scored like model_review.py on the nights with earlier pairs to learn from: 2022 mayors (pairs 2014->2018
mayors, 2016->2020 president), 2020 president (2014->2018) and 2024 president (those plus 2018->2022).
"""
import math
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_review as MR  # noqa: E402
import needle as N  # noqa: E402
import stations as ST  # noqa: E402
from needle import expit, logit, t_cdf  # noqa: E402

PAIRS = {"2022-mayors": [("2014-mayors", "2018-mayors"), ("2016-president", "2020-president")],
         "2020-president": [("2014-mayors", "2018-mayors")],
         "2024-president": [("2014-mayors", "2018-mayors"), ("2016-president", "2020-president"), ("2018-mayors", "2022-mayors")]}
TESTS = {"mayors 2022": [("2022-mayors", "2018-mayors+2020-president")],
         "pres-counties 2020+2024": [("2020-president", "2016-president"), ("2024-president", "2020-president")]}
MIN_SHIFT = 0.08  # county shifts smaller than this (logit) say little about relative sizes
SHRINK_K = 1.0    # prior weight of elasticity 1, in pairs


def town_shares(night, county):
    race = ST.load(night).get(county)
    if not race:
        return None
    bp = N.blue_pair(race, (night, county), top_two="president" not in night)
    if not bp:
        return None
    ia, ib, _ = bp
    t = defaultdict(lambda: [0, 0])
    for s in race["stations"]:
        t[s["district"]][0] += s["v"][ia]
        t[s["district"]][1] += s["v"][ib]
    tot = [sum(x[0] for x in t.values()), sum(x[1] for x in t.values())]
    return {d: x[0] / max(x[0] + x[1], 1) for d, x in t.items() if x[0] + x[1] > 0}, tot[0] / max(sum(tot), 1)


def elasticities(target, county):
    """{town: (symmetric, blue-swing, green-swing)} from the earlier pairs."""
    raw = defaultdict(lambda: {"all": [], "+": [], "-": []})
    for a, b in PAIRS[target]:
        A, B = town_shares(a, county), town_shares(b, county)
        if not A or not B:
            continue
        dc = logit(B[1]) - logit(A[1])
        if abs(dc) < MIN_SHIFT:
            continue
        for d in set(A[0]) & set(B[0]):
            dt = logit(min(max(B[0][d], 0.01), 0.99)) - logit(min(max(A[0][d], 0.01), 0.99))
            r = max(-1.0, min(4.0, dt / dc))
            raw[d]["all"].append(r)
            raw[d]["+" if dc > 0 else "-"].append(r)
    def shrink(xs):
        return 1.0 + (sum(xs) / len(xs) - 1.0) * len(xs) / (len(xs) + SHRINK_K) if xs else 1.0
    return {d: tuple(min(2.5, max(0.3, shrink(v[k]))) for k in ("all", "+", "-")) for d, v in raw.items()}


class Elastic(MR.Variant):
    mode = "elastic"  # or "bydir"

    def __init__(self, target, county, baseline, **kw):
        super().__init__(target, county, baseline, **kw)
        self.el = elasticities(target, county) if target in PAIRS else {}

    def beta(self, d, sign):
        e = self.el.get(d)
        if not e:
            return 1.0
        if self.mode == "bydir":
            return e[1] if sign > 0 else e[2]
        return e[0]

    def estimate(self, n):
        R, U = self.st[:n], self.st[n:]
        ia, ib, pr = self.ia, self.ib, dict(self.prior)
        ka = sum(s["v"][ia] for s in R)
        kb = sum(s["v"][ib] for s in R)
        remE = sum(s["E"] for s in U)
        margin = ka - kb
        if (U and abs(margin) > remE) or not U:
            return dict(p=1.0 if margin > 0 else 0.0, mean=margin, sd=0.0, certain=True)
        raw = [(s["district"], logit(s["v"][ia] / (s["v"][ia] + s["v"][ib])) - logit(s["_b"][0]), s["v"][ia] + s["v"][ib])
               for s in R if s["v"][ia] + s["v"][ib] > 0]
        W0 = sum(w for *_, w in raw)
        sign = (sum(r * w for _, r, w in raw) / W0) if W0 else 0.0
        res = []
        tnum = tden = fnum = fden = 0.0
        for d, r, w in raw:
            b = self.beta(d, sign)
            res.append((d, r / b, w * b * b))
        for s in R:
            tnum += s["C"]
            tden += s["_b"][1] * s["E"]
            fnum += s["v"][ia] + s["v"][ib]
            fden += s["_b"][2] * s["C"]
        k = pr["n0"] * 500
        rho = (tnum + k) / (tden + k) if tden else 1.0
        phi = (fnum + k) / (fden + k) if fden else 1.0
        W = sum(w for _, _, w in res)
        delta = sum(r * w for _, r, w in res) / W if W else 0.0
        dsum = defaultdict(lambda: [0.0, 0.0, 0])
        for d, r, w in res:
            dsum[d][0] += r * w
            dsum[d][1] += w
            dsum[d][2] += 1
        dmean = {d: (v[0] / v[1], v[2]) for d, v in dsum.items()}
        K, nst = len(dmean), len(res)
        within = sum(w * (r - dmean[d][0]) ** 2 for d, r, w in res) / W if res else 0.0
        dof_w = max(nst - K, 0)
        sigma2 = (dof_w * within * nst / max(dof_w, 1) + pr["k0"] * pr["sigma"] ** 2) / (dof_w + pr["k0"])
        between = sum((m - delta) ** 2 for m, _ in dmean.values()) / (K - 1) if K > 1 else 0.0
        tau2 = (max(K - 1, 0) * between + pr["k0"] * pr["tau"] ** 2) / (max(K - 1, 0) + pr["k0"])
        frac_in = sum(s["E"] for s in R) / (sum(s["E"] for s in R) + remE)
        g2 = tau2 / max(K, 1) + sigma2 / max(nst, 1) + (pr["glob"] ** 2) * (1 - frac_in) ** 2 / (1 + K)
        if W0:
            yb = min(max(ka / max(ka + kb, 1), 0.05), 0.95)
            g2 += 1.0 / (W0 * yb * (1 - yb))
        mean, G, var_station = margin, defaultdict(float), 0.0
        for s in U:
            d = s["district"]
            b = self.beta(d, sign)
            dm, dn = dmean.get(d, (delta, 0))
            shrink = dn / (dn + pr["n0"] / 3)
            x = logit(s["_b"][0]) + b * (delta + shrink * (dm - delta))
            y = expit(x)
            V = min(s["E"], s["E"] * min(s["_b"][1] * rho, 1.0) * min(s["_b"][2] * phi, 1.0))
            mean += V * (2 * y - 1)
            gj = 2 * V * y * (1 - y) * b
            G[d] += gj
            var_station += (gj / b) ** 2 * sigma2
        var_d = sum(gk * gk * tau2 * (pr["n0"] / 3) / (dmean.get(d, (0, 0))[1] + pr["n0"] / 3) for d, gk in G.items())
        var_g = sum(G.values()) ** 2 * g2
        tr = self.turnout(n)
        left = max(tr["mean"] - tr["counted"], 1.0)
        var_t = ((mean - margin) * tr["sd"] / left) ** 2
        sd = math.sqrt(var_g + var_d + var_station + var_t)
        df = max(3, K - 1) if K < 30 else 200
        return dict(p=t_cdf(mean / sd, df) if sd > 0 else (1.0 if mean > 0 else 0.0), mean=mean, sd=sd, certain=False)


def main():
    base = type("Base", (MR.Variant,), {"turnout_sd": True, "samp": 1.0})
    variants = {"current": base, "elastic": type("E", (Elastic,), {"mode": "elastic"}), "bydir": type("D", (Elastic,), {"mode": "bydir"})}
    for g, nights in TESTS.items():
        print(f"== {g}")
        for name, cls in variants.items():
            rows = [r for t, b in nights for r in MR.score(cls, t, b)]
            cells = []
            for f in MR.CP:
                xs = [r[f] for r in rows]
                ll = sum(-math.log(max(x[0], 1e-6)) for x in xs) / len(xs)
                cells.append(f"{int(100 * f):>2}%: ll {ll:.3f} in80 {sum(x[2] for x in xs) / len(xs):.2f} err {sum(x[1] for x in xs) / len(xs):.1f}")
            print(f"  {name:<8} n={len(rows)} | " + " | ".join(cells))


if __name__ == "__main__":
    main()
