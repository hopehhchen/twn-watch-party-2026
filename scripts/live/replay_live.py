#!/usr/bin/env python3
"""Score the live (town-totals) needle on past nights, rebuilt as the CEC count site would have shown them.

  python3 scripts/live/replay_live.py [2022-mayors 2018-mayors]

For each race, at 1/5/10/20/30/70% of stations reported (in the CEC's logged order): the town snapshot
(votes per candidate, stations sent/total, ballots counted) goes through live_model.LiveRace, and the result
is compared with the replay's station-feed and district-feed models at the same moment. Scores: log loss of
the eventual winner's chance, mean margin error (points of the two contenders' votes), and share of finals
inside the 80% range.
"""
import math
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import needle as N  # noqa: E402
import stations as ST  # noqa: E402
from build_needle_data import NIGHTS, ORDER  # noqa: E402
from live_model import LiveRace  # noqa: E402

CP = (0.01, 0.05, 0.10, 0.20, 0.30, 0.70)


def towns_of(race):
    t = defaultdict(lambda: {"E": 0, "N": 0, "sizes": []})
    for s in race["stations"]:
        t[s["district"]]["E"] += s["E"]
        t[s["district"]]["N"] += 1
        t[s["district"]]["sizes"].append(s["E"])
    for v in t.values():
        v["sizes"].sort(reverse=True)
    return dict(t)


def snapshot(stations_in, nos, totals):
    snap = {}
    for s in stations_in:
        x = snap.setdefault(s["district"], {"sent": 0, "total": totals[s["district"]], "votes": defaultdict(int), "C": 0})
        x["sent"] += 1
        x["C"] += s["C"]
        for no, v in zip(nos, s["v"]):
            x["votes"][no] += v
    return snap


def score(night, verbose=False):
    cfg = NIGHTS[night]
    rows = []
    for county in ORDER:
        race = ST.load(night).get(county)
        if race is None or race.get("no_times"):
            continue
        ns = N.Night(night, county, cfg["baseline"])
        nd = N.Night(night, county, cfg["baseline"], granularity="district")
        nos = [c["no"] for c in race["cands"]]
        towns = towns_of(race)
        ratio = sum(s["A"] for s in race["stations"]) / max(sum(s["C"] for s in race["stations"]), 1)
        lr = LiveRace(county, cfg["baseline"], nos, nos[ns.ia], nos[ns.ib], towns, valid_ratio=0.988)
        fin, two = ns.final_axis - ns.final_rival, ns.final_axis + ns.final_rival
        M = len(ns.st)
        out = {}
        for f in CP:
            n = max(1, int(f * M))
            snap = snapshot(ns.st[:n], nos, {d: v["N"] for d, v in towns.items()})
            k = lr.load(snap)
            e = {"station": ns.estimate(n), "district": nd.estimate(n), "live": lr.estimate(k)}
            out[f] = {m: ((x["p"] if fin > 0 else 1 - x["p"]), 100 * abs(x["mean"] - fin) / two,
                          abs(x["mean"] - fin) <= 1.2816 * x["sd"] or (x["sd"] == 0 and x["mean"] == fin)) for m, x in e.items()}
            if verbose:
                print(county, f, {m: round(v[0], 3) for m, v in out[f].items()})
        rows.append(out)
    return rows


def main():
    nights = sys.argv[1:] or ["2022-mayors", "2018-mayors"]
    allrows = []
    for night in nights:
        rows = score(night)
        allrows += rows
        report(night, rows)
    if len(nights) > 1:
        report("both", allrows)


def report(label, rows):
    print(f"== {label} ({len(rows)} races)")
    for m in ("station", "district", "live"):
        cells = []
        for f in CP:
            xs = [r[f][m] for r in rows]
            ll = sum(-math.log(max(x[0], 1e-6)) for x in xs) / len(xs)
            fav = sum(x[0] > 0.5 for x in xs)
            cells.append(f"{int(100 * f):>2}%: ll {ll:.3f} fav {fav}/{len(xs)} in80 {sum(x[2] for x in xs) / len(xs):.2f} err {sum(x[1] for x in xs) / len(xs):.1f}")
        print(f"  {m:<9}| " + " | ".join(cells))


if __name__ == "__main__":
    main()
