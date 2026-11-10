#!/usr/bin/env python3
"""Model review: candidate changes to the needle, scored on every replayed night.

  python3 scripts/model_review.py [variant ...]

Groups: mayors (2018, 2022; 43 races), presidential counties (2020, 2024; 44), legislative districts
(2020, 2024; 146). Each race is scored at 1/5/10/20/30/70% of its stations against its final margin:
log loss of the winner's chance, share of finals inside the stated 80% range, mean margin error (points of
the two contenders' votes). Variants (subclasses of needle.Night, nothing in the site changes):

  base      the current model
  size      + a swing slope on station size (log electors), estimated from counted stations (ridge)
  turnout   + turnout uncertainty in the margin's sd (from Night.turnout)
  early     + a wider swing prior while few districts are in (glob 0.05 -> 0.10)
  all       size + turnout + early
"""
import math
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import needle as N  # noqa: E402
import stations as ST  # noqa: E402
from needle import expit, logit, t_cdf  # noqa: E402

CP = (0.01, 0.05, 0.10, 0.20, 0.30, 0.70)
GROUPS = {
    "mayors": [("2018-mayors", "2014-mayors+2016-president"), ("2022-mayors", "2018-mayors+2020-president")],
    "pres-counties": [("2020-president", "2016-president"), ("2024-president", "2020-president")],
    "legislators": [("2020-legislator", "2016-president"), ("2024-legislator", "2020-president")],
}


class Variant(N.Night):
    size = turnout_sd = False
    glob = None
    s0 = None      # prior sd (logit) of the county-wide swing: shrinks the early swing toward the baseline
    huber = None   # Huber cut (in station sds) for down-weighting outlying stations

    def estimate(self, n):
        R, U = self.st[:n], self.st[n:]
        if self.granularity == "district":
            R = self._district_totals(R)
        ia, ib, pr = self.ia, self.ib, dict(self.prior)
        if self.glob is not None:
            pr["glob"] = self.glob
        for k in ("sigma", "tau", "k0", "n0"):
            if getattr(self, "p_" + k, None) is not None:
                pr[k] = getattr(self, "p_" + k)
        ka = sum(s["v"][ia] for s in R)
        kb = sum(s["v"][ib] for s in R)
        remE = sum(s["E"] for s in U)
        margin = ka - kb
        if (U and abs(margin) > remE) or not U:
            return dict(p=1.0 if margin > 0 else 0.0, mean=margin, sd=0.0, certain=True)
        res = []
        tnum = tden = fnum = fden = 0.0
        for s in R:
            two = s["v"][ia] + s["v"][ib]
            b = s["_b"]
            if two > 0:
                res.append((s["district"], logit(s["v"][ia] / two) - logit(b[0]), two, math.log(max(s["E"], 1))))
            tnum += s["C"]
            tden += b[1] * s["E"]
            fnum += two
            fden += b[2] * s["C"]
        k = pr["n0"] * 500
        rho = (tnum + k) / (tden + k) if tden else 1.0
        phi = (fnum + k) / (fden + k) if fden else 1.0
        W = sum(w for _, _, w, _ in res)
        delta = sum(r * w for _, r, w, _ in res) / W if W else 0.0
        if self.huber and len(res) >= 3:
            for _ in range(3):
                scale = max(math.sqrt(sum(w * (r - delta) ** 2 for _, r, w, _ in res) / W), pr["sigma"] / 2)
                res = [(d, r, w0 * min(1.0, self.huber * scale / max(abs(r - delta), 1e-9)), x) for (d, r, _, x), w0 in
                       zip(res, [two for two in self._w0(R)])]
                W = sum(w for _, _, w, _ in res)
                delta = sum(r * w for _, r, w, _ in res) / W
        # optional size slope: residual swing vs log electors, ridge toward 0
        beta, xbar = 0.0, 0.0
        if self.size and res:
            xbar = sum(x * w for *_, w, x in [(a, b_, w, x) for a, b_, w, x in res]) / W
            sxy = sum(w * (x - xbar) * (r - delta) for _, r, w, x in res)
            sxx = sum(w * (x - xbar) ** 2 for _, r, w, x in res)
            beta = sxy / (sxx + 40 * 0.3 * (W / len(res)))
            res = [(d, r - beta * (x - xbar), w, x) for d, r, w, x in res]
            delta = sum(r * w for _, r, w, _ in res) / W
        dsum = defaultdict(lambda: [0.0, 0.0, 0])
        for d, r, w, _ in res:
            dsum[d][0] += r * w
            dsum[d][1] += w
            dsum[d][2] += 1
        dmean = {d: (v[0] / v[1], v[2]) for d, v in dsum.items()}
        K = len(dmean)
        if res:
            within = sum(w * (r - dmean[d][0]) ** 2 for d, r, w, _ in res) / W
            nst = len(res)
        else:
            within, nst = 0.0, 0
        dof_w = max(nst - K, 0)
        sigma2 = (dof_w * within * nst / max(dof_w, 1) + pr["k0"] * pr["sigma"] ** 2) / (dof_w + pr["k0"])
        between = sum((m - delta) ** 2 for m, _ in dmean.values()) / (K - 1) if K > 1 else 0.0
        tau2 = (max(K - 1, 0) * between + pr["k0"] * pr["tau"] ** 2) / (max(K - 1, 0) + pr["k0"])
        frac_in = sum(s["E"] for s in R) / (sum(s["E"] for s in R) + remE)
        g2 = tau2 / max(K, 1) + sigma2 / max(nst, 1) + (pr["glob"] ** 2) * (1 - frac_in) ** 2 / (1 + K)
        delta_raw = delta
        if self.s0:
            v = tau2 / max(K, 1) + sigma2 / max(nst, 1)
            delta = delta * self.s0 ** 2 / (self.s0 ** 2 + v)
            g2 = g2 - v + v * self.s0 ** 2 / (self.s0 ** 2 + v)
        mean, G, var_station, net = margin, defaultdict(float), 0.0, 0.0
        for s in U:
            b = s["_b"]
            d = s["district"]
            dm, dn = dmean.get(d, (delta, 0))
            shrink = dn / (dn + pr["n0"] / 3)
            x = logit(b[0]) + delta + shrink * (dm - delta_raw) + beta * (math.log(max(s["E"], 1)) - xbar)
            y = expit(x)
            V = min(s["E"], s["E"] * min(b[1] * rho, 1.0) * min(b[2] * phi, 1.0))
            mean += V * (2 * y - 1)
            net += V * (2 * y - 1)
            gj = 2 * V * y * (1 - y)
            G[d] += gj
            var_station += gj * gj * sigma2
        var_d = sum(gk * gk * tau2 * (pr["n0"] / 3) / (dmean.get(d, (0, 0))[1] + pr["n0"] / 3) for d, gk in G.items())
        var_g = sum(G.values()) ** 2 * g2
        var_t = 0.0
        if self.turnout_sd:
            tr = self.turnout(n)
            left = max(tr["mean"] - tr["counted"], 1.0)
            var_t = (net * tr["sd"] / left) ** 2  # the votes still out scale together with turnout
        sd = math.sqrt(var_g + var_d + var_station + var_t)
        df = max(3, K - 1) if K < 30 else 200
        p = t_cdf(mean / sd, df) if sd > 0 else (1.0 if mean > 0 else 0.0)
        return dict(p=p, mean=mean, sd=sd, certain=False)


def _w0(self, R):
    return [s["v"][self.ia] + s["v"][self.ib] for s in R if s["v"][self.ia] + s["v"][self.ib] > 0]


Variant._w0 = _w0


def make(name):
    if ":" in name:  # e.g. "turnout,s0=0.25,huber=2"
        flags = {}
        for part in name.split(":"):
            k, _, v = part.partition("=")
            if k in ("sigma", "tau", "k0", "n0"):
                k = "p_" + k
            flags.update({"turnout": {"turnout_sd": True}, "size": {"size": True}}.get(k, {}) if not v else {k: float(v)})
        return type(f"V_{name}", (Variant,), flags)
    flags = {"base": {}, "size": {"size": True}, "turnout": {"turnout_sd": True}, "early": {"glob": 0.10},
             "all": {"size": True, "turnout_sd": True, "glob": 0.10}}[name]
    return type(f"V_{name}", (Variant,), flags)


def score(cls, target, base):
    rows = []
    for key in ST.load(target):
        try:
            nt = cls(target, key, base)
        except Exception:
            continue
        if nt.base is None:
            continue
        M = len(nt.st)
        fin, two = nt.final_axis - nt.final_rival, nt.final_axis + nt.final_rival
        if not two:
            continue
        row = {}
        for f in CP:
            e = nt.estimate(max(1, int(f * M)))
            pw = e["p"] if fin > 0 else 1 - e["p"]
            row[f] = (pw, 100 * abs(e["mean"] - fin) / two, abs(e["mean"] - fin) <= 1.2816 * e["sd"] or e["sd"] == 0 and e["mean"] == fin)
        rows.append(row)
    return rows


def main():
    names = sys.argv[1:] or ["base", "size", "turnout", "early", "all"]
    for g, nights in GROUPS.items():
        print(f"== {g}")
        for name in names:
            cls = make(name)
            rows = [r for t, b in nights for r in score(cls, t, b)]
            cells = []
            for f in CP:
                xs = [r[f] for r in rows]
                ll = sum(-math.log(max(x[0], 1e-6)) for x in xs) / len(xs)
                cells.append(f"{int(100 * f):>2}%: ll {ll:.3f} in80 {sum(x[2] for x in xs) / len(xs):.2f} err {sum(x[1] for x in xs) / len(xs):.1f}")
            print(f"  {name:<8} n={len(rows)} | " + " | ".join(cells))


if __name__ == "__main__":
    main()
