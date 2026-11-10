#!/usr/bin/env python3
"""The needle on live CEC data: town (鄉鎮市區) totals instead of per-station results.

The CEC count site gives, for each town, every candidate's votes so far and how many of its polling stations
have reported (已送/應送), but not which ones. So the live race is the replay model's "district feed"
(needle.Night with granularity="district") with two approximations:

  * counted part of a town: one pseudo-station with the town's votes and electors = town electors x
    counted_share(sent/total) (early-reporting stations are smaller than average; SIZE_H), ballots from the
    turnout page when it agrees with the votes, else valid votes / the valid share of ballots;
  * uncounted part: (total - sent) pseudo-stations sharing the rest of the town's electors.

Every pseudo-station takes its town's baseline (same as the district feed). scripts/live/replay_live.py
runs this on the 2018 and 2022 nights, rebuilt as town snapshots, and scores it against the replays.

  race = LiveRace(area, baseline, cands, towns)          # cands: [{"no", ...}], blue/other/third by ballot no
  row = race.row(t_min, snapshot)                       # same columns as data/needle/<night>.json points
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import needle as N  # noqa: E402

MIN_STATIONS_WIN3 = 5  # as build_needle_data.py
# Stations that report first are smaller. Share of a town's electors at its counted stations, divided by the share
# of its stations counted, by tenth of stations counted (pooled 2018, 2020, 2022, 2024 nights; each night within
# 0.04 of these): early on the counted stations hold ~75% of their average share.
SIZE_H = [0.70, 0.747, 0.807, 0.846, 0.875, 0.899, 0.918, 0.939, 0.957, 0.973, 0.99, 1.0]
SIZE_F = [0.0, 0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.0]


BOUND_PAD = 1.1  # stations can grow between elections: pad the largest-stations bound by 10%


def counted_share(f):
    """Share of a town's electors at its counted stations when a share f of its stations is counted."""
    for k in range(1, len(SIZE_F)):
        if f <= SIZE_F[k]:
            w = (f - SIZE_F[k - 1]) / (SIZE_F[k] - SIZE_F[k - 1])
            return f * (SIZE_H[k - 1] + w * (SIZE_H[k] - SIZE_H[k - 1]))
    return 1.0


class LiveRace(N.Night):
    def __init__(self, area, baseline, nos, blue_no, other_no, towns, third_no=None, valid_ratio=0.988,
                 prior=N.PRIOR):
        """nos: every candidate's ballot number; towns: {town: {"E": electors, "N": stations, "sizes": [station
        electors, largest first]}} (from the last election until the CEC's own figures arrive); valid_ratio: valid
        votes / ballots cast last time."""
        self.turnout_shift, self.live_turnout, self.granularity, self.prior = 0.0, True, "station", prior
        self.county = self.target = area
        self.base, self.how = self._baseline(baseline, area)
        if self.base is None:
            raise ValueError(f"{area}: no baseline ({self.how})")
        self.nos = list(nos)
        self.towns = {d: dict(v) for d, v in towns.items()}
        self.valid_ratio = valid_ratio
        self.set_sides(blue_no, other_no, third_no)
        self.st, self.t = [], []

    def set_sides(self, blue_no, other_no, third_no=None):
        self.blue_no, self.other_no, self.third_no = blue_no, other_no, third_no
        self.ia, self.ib = self.nos.index(blue_no), self.nos.index(other_no)
        self.i3 = self.nos.index(third_no) if third_no is not None else None

    def _tb(self, d):
        return self.base.get((d, None)) or self.base[(None, None)]

    def load(self, snap):
        """snap: {town: {"sent", "total", "votes": {no: n}, "C": ballots or None, "E": electors or None}}.
        Builds self.st (counted pseudo-stations first) and returns n, the number counted."""
        R, U = [], []
        self.rem_bound = 0.0  # certainty needs the margin to beat the largest stations each town could have left
        for d, info in self.towns.items():
            s = snap.get(d) or {}
            total = s.get("total") or info["N"]
            sent = min(s.get("sent") or 0, total)
            E_d = s.get("E") or info["E"]
            b = self._tb(d)
            if sent:
                v = [int((s.get("votes") or {}).get(no, 0)) for no in self.nos]
                A = sum(v)
                C = s.get("C")
                if not C or abs(C * self.valid_ratio - A) > 0.02 * max(A, 1):  # turnout page out of step: estimate
                    C = round(A / self.valid_ratio)
                R.append({"district": d, "E": E_d * counted_share(sent / total), "C": C, "A": A, "v": v, "_b": b})
            left = E_d * (1 - counted_share(sent / total))
            sizes = info.get("sizes") or []
            big = sum(sizes[:total - sent]) if len(sizes) >= total - sent else (total - sent) * (max(sizes) if sizes else left)
            self.rem_bound += max(left, big * E_d / max(info["E"], 1)) * BOUND_PAD
            for _ in range(total - sent):
                U.append({"district": d, "E": left / (total - sent), "C": 0, "A": 0, "v": [0] * len(self.nos), "_b": b})
        self.st = R + U
        return len(R)

    def stations(self, snap):
        """(stations in, stations in all) from the snapshot."""
        sent = sum(min((snap.get(d) or {}).get("sent") or 0, (snap.get(d) or {}).get("total") or i["N"]) for d, i in self.towns.items())
        total = sum((snap.get(d) or {}).get("total") or i["N"] for d, i in self.towns.items())
        return sent, total

    def row(self, t_min, snap):
        """One point, in data/needle/<night>.json's columns. Station and district columns are the same here:
        the live feed is the district feed."""
        n = self.load(snap)
        sent, _ = self.stations(snap)
        if n == 0:
            return None
        a = self.estimate(n)
        tr = self.turnout(n)
        row = [round(t_min), sent, a["ka"], a["kb"],
               round(a["p"], 4), round(a["mean"]), round(a["sd"]), int(a["certain"]),
               round(a["remE"]), round(a["eb"]), round(a["vrem"]),
               round(a["p"], 4), round(a["mean"]), round(a["sd"]), int(a["certain"]), round(a["vrem"]),
               round(a.get("rho", 1.0), 4),
               tr["counted"], round(tr["mean"]), round(tr["sd"]), round(tr["mean"]), round(tr["sd"])]
        if self.i3 is not None:
            r = self.three_way(n, self.i3)
            seven = [round(x, 4) for x in r["mean"]] + [round(x, 4) for x in r["sd"]] + [int(r["certain"])]
            pw = [round(x, 4) for x in r["p_win"]] if sent >= MIN_STATIONS_WIN3 else [None] * 3
            row += [sum(s["v"][self.i3] for s in self.st[:n])] + seven + seven + pw + pw
        return row
