#!/usr/bin/env python3
"""Win probability over election night from a partial count ("needle"), with a backtest.

  python3 scripts/needle.py backtest          # 2018 and 2022 nights, all races, both baselines
  python3 scripts/needle.py race 2022-mayors 臺北市 [--baseline 2018-mayors]

Model (two contenders per race, everyone else ignored):
  * Sides. Each race is scored as the "blue" contender's share of the two contenders' votes. Blue is
    the KMT contender; with no KMT contender, whoever faces the DPP; CAMPS overrides the few races
    where labels mislead (independents, two KMT members, a KMT-backed independent).
  * Baseline. For each village (村里) in an earlier election: the blue side's share of that race's
    top two (by the same rules; presidential races: KMT ticket vs DPP ticket), its turnout, and the
    fraction of ballots that went to those two.
  * Swing. At reported stations, logit(target share) - logit(baseline share) estimates the swing:
    one citywide swing plus district (行政區) deviations shrunk toward it.
  * Size of what's left. Each unreported station: its electors x village turnout x a citywide
    turnout ratio (reported stations vs their own baseline) x the top-two fraction, likewise.
  * Uncertainty. Shared error in the citywide swing, a district error for districts with little or no
    reporting, and station noise; all estimated from the reported stations' residuals, padded by a
    prior early on. Probability from a Student-t on the predicted final margin.
  * Certainty. When the margin exceeds every elector left at unreported stations, P is 0 or 1.

Nothing here uses the final result of the race being predicted, except to pick its two contenders
(known before the night in practice) and to score the backtest.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stations as ST  # noqa: E402
from build_cec_night import minute_ceiling  # noqa: E402

KMT, DPP = "中國國民黨", "民主進步黨"
PRIOR = dict(tau=0.08, sigma=0.25, k0=8, n0=10, glob=0.05)  # logit-scale priors; chosen by cross-validation 2018<->2022


def logit(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def expit(x):
    return 1 / (1 + math.exp(-x))


def t_cdf(x, df):
    """Student-t CDF via the regularized incomplete beta (continued fraction)."""
    if df > 200:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    z = df / (df + x * x)
    ib = _betainc(df / 2, 0.5, z)
    return 1 - 0.5 * ib if x > 0 else 0.5 * ib


def _betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x > (a + 1) / (a + b + 2):
        return 1 - _betainc(b, a, 1 - x)
    f, c, d = 1.0, 1.0, 0.0
    for i in range(200):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1 + num * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + num / c
        c = c if abs(c) > 1e-30 else 1e-30
        f *= c * d
        if abs(1 - c * d) < 1e-10:
            break
    return math.exp(lbeta) / a * (f - 1)


def contenders(race):
    """Indices of the two candidates with most votes (in practice: named before the night)."""
    tot = [sum(s["v"][k] for s in race["stations"]) for k in range(len(race["cands"]))]
    return sorted(range(len(tot)), key=lambda k: -tot[k])[:2]


# Which candidate stands on the "blue" side of a race, when the party label alone doesn't say.
# (election, county): (blue-side name, other-side name). Evidence in docs/needle.md: party moves,
# endorsements, and the village-level correlation of each candidate's share with the presidential vote.
CAMPS = {
    ("2014-mayors", "花蓮縣"): ("傅", "蔡啟塔"),      # 傅崐萁 (ex-KMT, independent) carried the blue machine
    ("2014-mayors", "連江縣"): ("劉增應", "楊綏生"),  # both KMT; 劉 was the nominee and the 2018 incumbent
    ("2018-mayors", "新竹縣"): ("楊文科", "鄭朝方"),  # as a baseline: KMT vs DPP; 徐欣瑩 (民國黨, 2nd) set aside
    ("2022-mayors", "連江縣"): ("王忠銘", "曹爾元"),  # both KMT members; 王 the nominee, same pair in 2026
    ("2022-mayors", "苗栗縣"): ("鍾東錦", "徐定禎"),  # 鍾 (independent, since rejoined KMT) vs DPP
    ("2022-mayors", "新竹市"): ("高虹安", "沈慧虹"),  # TPP vs DPP; 高's share tracks blue areas
}
BASELINE_ONLY = {("2018-mayors", "新竹縣")}  # as the race being predicted, its real top two (楊 vs 徐) apply


def _find(cands, name):
    return next(k for k, c in enumerate(cands) if c["name"].startswith(name))


def blue_pair(race, key, top_two=True, role="baseline"):
    """(blue index, other index, how) for a race; None when it can't be decided."""
    cands = race["cands"]
    if key in CAMPS and not (role == "target" and key in BASELINE_ONLY):
        a, b = (_find(cands, n) for n in CAMPS[key])
        return a, b, f"{cands[a]['name']} vs {cands[b]['name']} (camp override)"
    tot = [sum(s["v"][k] for s in race["stations"]) for k in range(len(cands))]
    order = sorted(range(len(tot)), key=lambda k: -tot[k])
    if not top_two:  # presidential: the KMT ticket against the DPP ticket
        a = next(k for k in order if cands[k]["party"] == KMT)
        b = next(k for k in order if cands[k]["party"] == DPP)
        return a, b, f"{cands[a]['name']} vs {cands[b]['name']}"
    pair = order[:2]
    parties = [cands[k]["party"] for k in pair]
    if KMT in parties and parties.count(KMT) == 1:
        a = pair[parties.index(KMT)]
    elif DPP in parties:
        a = pair[1 - parties.index(DPP)]
    else:
        return None
    b = pair[1] if a == pair[0] else pair[0]
    return a, b, f"{cands[a]['name']} vs {cands[b]['name']}"


def baseline_shares(base_race, key):
    """Per village: (blue share of the two sides, turnout, two-side fraction of ballots). Returns (dict, how)."""
    bp = blue_pair(base_race, key, top_two="president" not in key[0])
    if bp is None:
        return None, "can't tell which side is blue"
    a, b, how = bp
    agg = defaultdict(lambda: [0, 0, 0, 0])  # axis, rival, ballots, electors
    for s in base_race["stations"]:
        g = agg[(s["district"], s["village"])]
        g[0] += s["v"][a]
        g[1] += s["v"][b]
        g[2] += s["C"]
        g[3] += s["E"]
    out, dist = {}, defaultdict(lambda: [0, 0, 0, 0])
    for (d, v), g in agg.items():
        for i in range(4):
            dist[d][i] += g[i]
        if g[0] + g[1] > 0 and g[3] > 0:
            out[(d, v)] = (g[0] / (g[0] + g[1]), g[2] / g[3], (g[0] + g[1]) / max(g[2], 1))
    city = [sum(g[i] for g in agg.values()) for i in range(4)]
    for d, g in dist.items():
        if g[0] + g[1] > 0 and g[3] > 0:
            out[(d, None)] = (g[0] / (g[0] + g[1]), g[2] / g[3], (g[0] + g[1]) / max(g[2], 1))
    out[(None, None)] = (city[0] / (city[0] + city[1]), city[2] / city[3], (city[0] + city[1]) / city[2])
    return out, how


def base_for(base, s):
    return base.get((s["district"], s["village"])) or base.get((s["district"], None)) or base[(None, None)]


class Night:
    """One race on one night, against one baseline."""

    def __init__(self, target, county, baseline, prior=PRIOR, turnout_shift=0.0, live_turnout=True,
                 granularity="station"):
        """turnout_shift: the audience's turnout scenario, in percentage points relative to the baseline
        election's turnout (e.g. +2.5 = one sigma up). It is the prior for turnout; once stations report,
        the observed turnout (versus those stations' own baseline turnout) takes over, unless
        live_turnout=False, which holds the scenario all night."""
        self.turnout_shift, self.live_turnout, self.granularity = turnout_shift, live_turnout, granularity
        self.race = ST.load(target)[county]
        self.county, self.target, self.baseline, self.prior = county, target, baseline, prior
        bp = blue_pair(self.race, (target, county), role="target")
        if bp is None:
            raise ValueError(f"{target} {county}: no blue side")
        self.ia, self.ib, self.target_how = bp
        self.axis = "blue"
        self.base, self.how = self._baseline(baseline, county)
        tm = ST.times(target)
        self.st = sorted(self.race["stations"], key=lambda s: tm[(county, s["district"], s["no"])])
        self.t = [tm[(county, s["district"], s["no"])] for s in self.st]
        for s in self.st:
            s["_b"] = base_for(self.base, s) if self.base else None
            if self.base and granularity == "district":  # the feed only gives district totals
                s["_b"] = self.base.get((s["district"], None)) or self.base[(None, None)]
        self.final_axis = sum(s["v"][self.ia] for s in self.st)
        self.final_rival = sum(s["v"][self.ib] for s in self.st)

    def _baseline(self, baseline, county):
        parts, why = [], []
        for b in baseline.split("+"):
            races = ST.load(b)
            if county not in races:
                why.append(f"no {b} race")
                continue
            d, how = baseline_shares(races[county], (b, county))
            if d is None:
                why.append(f"{b}: {how}")
                continue
            parts.append((d, how))
        if not parts:
            return None, "; ".join(why)
        if len(parts) == 1:  # e.g. 2022 嘉義市 voted in December: only the presidential baseline
            if why:
                return parts[0][0], parts[0][1] + f" (only; {'; '.join(why)})"
            return parts[0]
        (d1, h1), (d2, h2) = parts
        out = {}
        for k, v in d1.items():
            w = d2.get(k) or d2.get((k[0], None)) or d2[(None, None)]
            out[k] = (expit((logit(v[0]) + logit(w[0])) / 2), v[1], v[2])
        return out, f"{h1} + {h2}"

    def estimate(self, n):
        """Forecast after the first n stations (in report order) are in."""
        R, U = self.st[:n], self.st[n:]
        if self.granularity == "district":
            R = self._district_totals(R)
        ia, ib, pr = self.ia, self.ib, self.prior
        ka = sum(s["v"][ia] for s in R)
        kb = sum(s["v"][ib] for s in R)
        remE = sum(s["E"] for s in U)
        margin = ka - kb
        if U and abs(margin) > remE:
            return dict(p=1.0 if margin > 0 else 0.0, mean=margin, sd=0.0, certain=True, n=n)
        if not U:
            return dict(p=1.0 if margin > 0 else 0.0, mean=margin, sd=0.0, certain=True, n=n)
        # residuals at reported stations
        res = []  # (district, resid_logit, weight)
        tnum = tden = fnum = fden = 0.0
        for s in R:
            two = s["v"][ia] + s["v"][ib]
            b = s["_b"]
            if two > 0:
                res.append((s["district"], logit(s["v"][ia] / two) - logit(b[0]), two))
            tnum += s["C"]
            tden += b[1] * s["E"]
            fnum += two
            fden += b[2] * s["C"]
        city_t = self.base[(None, None)][1]
        rho0 = 1 + self.turnout_shift / 100 / city_t
        k = pr["n0"] * 500  # prior weight, in expected ballots
        rho = (tnum + rho0 * k) / (tden + k) if (tden and self.live_turnout) else rho0
        phi = (fnum + pr["n0"] * 500) / (fden + pr["n0"] * 500) if fden else 1.0
        W = sum(w for _, _, w in res)
        delta = sum(r * w for _, r, w in res) / W if W else 0.0
        # district means
        dsum = defaultdict(lambda: [0.0, 0.0, 0])
        for d, r, w in res:
            dsum[d][0] += r * w
            dsum[d][1] += w
            dsum[d][2] += 1
        dmean = {d: (v[0] / v[1], v[2]) for d, v in dsum.items()}
        K = len(dmean)
        # station noise: weighted var of residuals around their district means
        if res:
            within = sum(w * (r - dmean[d][0]) ** 2 for d, r, w in res) / W
            nst = len(res)
        else:
            within, nst = 0.0, 0
        dof_w = max(nst - K, 0)
        sigma2 = (dof_w * within * nst / max(dof_w, 1) + pr["k0"] * pr["sigma"] ** 2) / (dof_w + pr["k0"])
        between = sum((m - delta) ** 2 for m, _ in dmean.values()) / (K - 1) if K > 1 else 0.0
        tau2 = (max(K - 1, 0) * between + pr["k0"] * pr["tau"] ** 2) / (max(K - 1, 0) + pr["k0"])
        # global swing uncertainty: shrinks with districts and stations, never below a floor of the
        # chance that unreported areas swing differently from reported ones
        frac_in = sum(s["E"] for s in R) / (sum(s["E"] for s in R) + remE)
        g2 = tau2 / max(K, 1) + sigma2 / max(nst, 1) + (pr["glob"] ** 2) * (1 - frac_in) ** 2 / (1 + K)
        # predictions for unreported stations
        mean = margin
        G = defaultdict(float)
        var_station = 0.0
        for s in U:
            b = s["_b"]
            d = s["district"]
            dm, dn = dmean.get(d, (delta, 0))
            shrink = dn / (dn + pr["n0"] / 3)
            x = logit(b[0]) + delta + shrink * (dm - delta)
            y = expit(x)
            V = min(s["E"], s["E"] * min(b[1] * rho, 1.0) * min(b[2] * phi, 1.0))
            mean += V * (2 * y - 1)
            gj = 2 * V * y * (1 - y)
            G[d] += gj
            var_station += gj * gj * sigma2
        var_d = 0.0
        for d, gk in G.items():
            dn = dmean.get(d, (0, 0))[1]
            var_d += gk * gk * tau2 * (pr["n0"] / 3) / (dn + pr["n0"] / 3)
        var_g = sum(G.values()) ** 2 * g2
        sd = math.sqrt(var_g + var_d + var_station)
        df = max(3, K - 1) if K < 30 else 200
        p = t_cdf(mean / sd, df) if sd > 0 else (1.0 if mean > 0 else 0.0)
        return dict(p=p, mean=mean, sd=sd, certain=False, n=n, delta=delta, rho=rho, K=K)

    @staticmethod
    def _district_totals(R):
        agg = {}
        for s in R:
            a = agg.setdefault(s["district"], {"district": s["district"], "E": 0, "C": 0, "A": 0,
                                               "v": [0] * len(s["v"]), "_b": s["_b"]})
            a["E"] += s["E"]
            a["C"] += s["C"]
            a["A"] += s["A"]
            a["v"] = [x + y for x, y in zip(a["v"], s["v"])]
        return list(agg.values())

    def naive(self, n):
        """Remaining stations vote like the counted ones (sampling error only)."""
        R, U = self.st[:n], self.st[n:]
        ia, ib = self.ia, self.ib
        ka = sum(s["v"][ia] for s in R)
        kb = sum(s["v"][ib] for s in R)
        if not U or ka + kb == 0:
            return dict(p=1.0 if ka > kb else 0.0, mean=ka - kb, sd=0.0)
        y = ka / (ka + kb)
        shares = [(s["v"][ia] / (s["v"][ia] + s["v"][ib]), s["v"][ia] + s["v"][ib]) for s in R if s["v"][ia] + s["v"][ib]]
        W = sum(w for _, w in shares)
        s2 = sum(w * (x - y) ** 2 for x, w in shares) / W
        Ecount = sum(s["E"] for s in R)
        Vrem = sum(s["E"] for s in U) * (ka + kb) / Ecount
        mean = ka - kb + Vrem * (2 * y - 1)
        sd = 2 * Vrem * math.sqrt(s2 / len(shares))
        return dict(p=0.5 * (1 + math.erf(mean / sd / math.sqrt(2))) if sd else float(mean > 0), mean=mean, sd=sd)


BACKTESTS = {"2018-mayors": ["2014-mayors", "2016-president", "2014-mayors+2016-president"],
             "2022-mayors": ["2018-mayors", "2020-president", "2018-mayors+2020-president"]}
CHECKPOINTS = [0.01, 0.03, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70]


def backtest(prior=PRIOR, verbose=True):
    rows = []
    for target, bases in BACKTESTS.items():
        for county, race in ST.load(target).items():
            if race.get("no_times"):
                continue
            for bl in bases:
                nt = Night(target, county, bl, prior)
                if nt.base is None:
                    if verbose:
                        print(f"  skip {target} {county} vs {bl}: {nt.how}")
                    continue
                truth = nt.final_axis - nt.final_rival
                N = len(nt.st)
                for cp in CHECKPOINTS:
                    n = max(1, int(round(cp * N)))
                    e = nt.estimate(n)
                    nv = nt.naive(n)
                    rows.append(dict(target=target, county=county, base=bl, cp=cp, truth=truth, win=truth > 0,
                                     p=e["p"], mean=e["mean"], sd=e["sd"], certain=e["certain"],
                                     np=nv["p"], nmean=nv["mean"], nsd=nv["sd"], valid=nt.final_axis + nt.final_rival,
                                     time=nt.t[n - 1].strftime("%H:%M")))
    return rows


def summarize(rows, label=""):
    def stats(sub, pk, mk, sk):
        brier = sum((r[pk] - r["win"]) ** 2 for r in sub) / len(sub)
        z = [(r["truth"] - r[mk]) / r[sk] for r in sub if r[sk] > 0]
        in80 = sum(abs(x) < 1.2816 for x in z) / len(z) if z else float("nan")
        in95 = sum(abs(x) < 1.96 for x in z) / len(z) if z else float("nan")
        wrong90 = sum(1 for r in sub if (r[pk] > 0.9 and not r["win"]) or (r[pk] < 0.1 and r["win"]))
        conf90 = sum(1 for r in sub if r[pk] > 0.9 or r[pk] < 0.1)
        err = sum(abs(r["truth"] - r[mk]) / r["valid"] for r in sub) / len(sub) * 100
        ll = sum(-math.log(min(max(r[pk], 0.002), 0.998) if r["win"] else 1 - min(max(r[pk], 0.002), 0.998))
                 for r in sub) / len(sub)
        return brier, in80, in95, wrong90, conf90, err, ll
    print(f"\n{label}")
    print("baseline         in%  | model: logloss brier in80% in95% wrong/confident(>90%) |margin err|%valid"
          " || naive: logloss brier in80% wrong/conf err")
    kinds = {"prev mayors": lambda b: "+" not in b and "mayors" in b,
             "prev president": lambda b: "+" not in b and "president" in b,
             "blend": lambda b: "+" in b}
    for bl_kind, fn in kinds.items():
        for cp in CHECKPOINTS:
            sub = [r for r in rows if r["cp"] == cp and fn(r["base"])]
            if not sub:
                continue
            b, i8, i9, w, c, er, ll = stats(sub, "p", "mean", "sd")
            nb, ni8, _, nw, nc, ner, nll = stats(sub, "np", "nmean", "nsd")
            print(f"{bl_kind:15s} {cp * 100:4.0f}  |  {ll:.3f}  {b:.3f} {100 * i8:4.0f}  {100 * i9:4.0f}   {w:3d}/{c:<3d}"
                  f"          {er:5.2f}      ||  {nll:.3f}  {nb:.3f} {100 * ni8:4.0f}  {nw:3d}/{nc:<3d} {ner:5.2f}")


def race_cli(target, county, baseline):
    nt = Night(target, county, baseline)
    names = [nt.race["cands"][k]["name"] for k in (nt.ia, nt.ib)]
    print(f"{target} {county}: axis {nt.axis} = {names[0]} vs {names[1]}; baseline {baseline}: {nt.how}")
    print(f"final: {nt.final_axis:,} vs {nt.final_rival:,}")
    N = len(nt.st)
    last = None
    for n in range(1, N + 1):
        m = minute_ceiling(nt.t[n - 1])
        if n < N and minute_ceiling(nt.t[n]) == m:
            continue
        hm = m.strftime("%H:%M")
        if last and hm[:4] == last[:4] and n < N:  # print every 10 minutes
            continue
        last = hm
        e = nt.estimate(n)
        nv = nt.naive(n)
        print(f"  {hm}  {n:5d}/{N} ({100 * n / N:5.1f}%)  P({names[0]})={e['p']:.3f}  margin {e['mean']:+10,.0f} ± {e['sd']:8,.0f}"
              f"{'  CERTAIN' if e['certain'] else ''}   naive P={nv['p']:.3f}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    if len(sys.argv) > 1 and sys.argv[1] == "race":
        bl = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BACKTESTS[sys.argv[2]][0]
        race_cli(sys.argv[2], sys.argv[3], bl)
    else:
        rows = backtest()
        summarize(rows, "Backtest: 2018 and 2022 mayoral nights")
