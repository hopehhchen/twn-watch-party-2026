#!/usr/bin/env python3
"""Does the live needle ever call a race "decided" before it is? Replays 2018 and 2022 as town snapshots,
with each town's station sizes taken from the PREVIOUS election (as on the night: 2022's sizes for 2026),
and reports, per race, the first station at which the live model and the truth say decided.

  python3 scripts/live/check_certainty.py
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import needle as N  # noqa: E402
import stations as ST  # noqa: E402
from build_needle_data import NIGHTS, ORDER  # noqa: E402
from live_model import LiveRace  # noqa: E402
from replay_live import snapshot, towns_of  # noqa: E402

PREV = {"2022-mayors": "2018-mayors", "2018-mayors": "2014-mayors"}


def main():
    early = wrong = late_total = n_races = 0
    for night in ("2022-mayors", "2018-mayors"):
        cfg = NIGHTS[night]
        prev = ST.load(PREV[night])
        for county in ORDER:
            race = ST.load(night).get(county)
            if not race or race.get("no_times"):
                continue
            ns = N.Night(night, county, cfg["baseline"])
            nos = [c["no"] for c in race["cands"]]
            towns = towns_of(race)
            if county in prev:  # sizes from the previous election, where the town existed
                old = towns_of(prev[county])
                for d, v in towns.items():
                    if d in old:
                        v["sizes"] = old[d]["sizes"]
            lr = LiveRace(county, cfg["baseline"], nos, nos[ns.ia], nos[ns.ib], towns)
            fin = ns.final_axis - ns.final_rival
            M = len(ns.st)
            first_live = first_true = None
            for n in range(1, M + 1):
                remE_true = sum(s["E"] for s in ns.st[n:])
                m = sum(s["v"][ns.ia] - s["v"][ns.ib] for s in ns.st[:n])
                if first_true is None and (abs(m) > remE_true or n == M):
                    first_true = n
                if first_live is None:
                    e = lr.estimate(lr.load(snapshot(ns.st[:n], nos, {d: v["N"] for d, v in towns.items()})))
                    if e["certain"]:
                        first_live = n
                        wrong += (e["mean"] > 0) != (fin > 0)
                if first_live is not None and first_true is not None:
                    break
            n_races += 1
            if first_live < first_true:
                early += 1
                print(f"EARLY {night} {county}: live decided at station {first_live}, truly at {first_true}")
            late_total += first_live - first_true
    print(f"{n_races} races: decided early in {early}, on the wrong side in {wrong}; "
          f"on average {late_total / n_races:.1f} stations after the truth")


if __name__ == "__main__":
    main()
