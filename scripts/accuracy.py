#!/usr/bin/env python3
"""How well the needle did on each replayed night, from the precomputed replays: data/accuracy.json.

  python3 scripts/accuracy.py

Reads data/needle/<night>.json (scripts/build_needle_data.py) and scores the per-station model at the
moment each race reached a share of its stations: win probability, projected margin and its 80% range,
projected turnout. Everything is compared with the race's own final count. The entry page shows it.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NIGHTS = ["2018-mayors", "2022-mayors", "2020-president", "2024-president"]
CHECKPOINTS = [0.01, 0.05, 0.10, 0.30, 0.70]
Z80 = 1.2816
# point columns (see build_needle_data.py)
T, N, B, O, P, M, SD, CERT, REME = 0, 1, 2, 3, 4, 5, 6, 7, 8
CC, TM = 17, 18


def clock(t):
    m = round(t) + 16 * 60
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def score_race(r):
    fin = r["blue"]["final"] - r["other"]["final"]
    two = r["blue"]["final"] + r["other"]["final"]
    blue_won = fin > 0
    pts, S = r["pts"], r["stations"]
    final_ballots = pts[-1][CC]
    out = {"area": r["area"], "winner": (r["blue"] if blue_won else r["other"])["name"],
           "margin_pts": round(100 * abs(fin) / two, 1), "at": {}}
    for f in CHECKPOINTS:
        p = next((q for q in pts if q[N] / S >= f), pts[-1])
        pw = p[P] if blue_won else 1 - p[P]
        out["at"][f] = {
            "p_winner": round(pw, 4),
            "margin_err_pts": round(100 * abs(p[M] - fin) / two, 2),
            "in_80": abs(p[M] - fin) <= Z80 * p[SD] or (p[SD] == 0 and p[M] == fin),
            "turnout_err_pts": round(100 * abs(p[TM] - final_ballots) / r["electors"], 2),
        }
    after5 = [q for q in pts if q[N] / S >= 0.05]
    out["max_p_loser_after_5pct"] = round(max((1 - q[P]) if blue_won else q[P] for q in after5), 4)
    hit95 = next((q for q in pts if (q[P] if blue_won else 1 - q[P]) >= 0.95
                  and all((x[P] if blue_won else 1 - x[P]) >= 0.95 for x in pts if x[T] >= q[T])), None)
    cert = next((q for q in pts if q[CERT]), None)
    out["stays_95_from"] = clock(hit95[T]) if hit95 else None
    out["decided_at"] = clock(cert[T]) if cert else None
    out["lead_minutes"] = round(cert[T] - hit95[T]) if hit95 and cert else None
    return out


def summarize(races):
    s = {}
    for f in CHECKPOINTS:
        xs = [r["at"][f] for r in races]
        s[f] = {
            "log_loss": round(sum(-math.log(max(x["p_winner"], 1e-6)) for x in xs) / len(xs), 3),
            "margin_err_pts": round(sum(x["margin_err_pts"] for x in xs) / len(xs), 1),
            "in_80": round(sum(x["in_80"] for x in xs) / len(xs), 2),
            "turnout_err_pts": round(sum(x["turnout_err_pts"] for x in xs) / len(xs), 1),
            "favorite_won": sum(x["p_winner"] > 0.5 for x in xs),
        }
    leads = sorted(r["lead_minutes"] for r in races if r["lead_minutes"] is not None)
    return {"n": len(races), "at": s,
            "wrong_way_90": [{"area": r["area"], "p": r["max_p_loser_after_5pct"], "winner": r["winner"]}
                             for r in races if r["max_p_loser_after_5pct"] >= 0.9],
            "median_lead_minutes": leads[len(leads) // 2] if leads else None}


def main():
    out = {"checkpoints": CHECKPOINTS, "nights": {}}
    for nid in NIGHTS:
        d = json.loads((ROOT / "data" / "needle" / f"{nid}.json").read_text())
        counties = [score_race(r) for r in d["races"] if r["area"] != "全國"]
        nat = next((score_race(r) for r in d["races"] if r["area"] == "全國"), None)
        out["nights"][nid] = {"title": d["title"], "baseline": d["baseline"], "counties": summarize(counties),
                              "races": counties, "national": nat,
                              "three_way": [r["area"] for r in d["races"] if r.get("mode") == "three"]}
        c = out["nights"][nid]["counties"]
        print(nid, "races", c["n"], "| 10%:", c["at"][0.1], "| wrong-way:", c["wrong_way_90"], "| lead", c["median_lead_minutes"])
        if nat:
            print("  national:", {k: v for k, v in nat.items() if k != "at"}, nat["at"][0.1])
    both = []
    for nid in ("2018-mayors", "2022-mayors"):
        both += out["nights"][nid]["races"]
    out["mayors_both"] = summarize(both)
    print("mayors both nights:", out["mayors_both"]["at"][0.1], out["mayors_both"]["wrong_way_90"])
    (ROOT / "data" / "accuracy.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
