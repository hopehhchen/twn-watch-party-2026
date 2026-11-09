#!/usr/bin/env python3
"""Precompute the needle replay for the 2018 and 2022 mayoral nights: data/needle/<night>.json.

  python3 scripts/build_needle_data.py

For every race, at every minute in which a station reported: stations in, the two contenders'
counted votes, and the model's output twice, once as if the feed gave per-station results and once
as if it only gave district totals. The site embeds these files (build_site.py), so the page itself
needs no model code. Real CEC data; nothing simulated.
"""
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import needle as N  # noqa: E402
import stations as ST  # noqa: E402
from build_cec_night import minute_ceiling  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "needle"
ORDER = ["臺北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "臺中市", "彰化縣", "南投縣",
         "雲林縣", "嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣",
         "金門縣", "連江縣"]
TONE = {"中國國民黨": "kmt", "民主進步黨": "dpp", "台灣民眾黨": "tpp", "時代力量": "npp"}
NIGHTS = {
    "2022-mayors": dict(baseline="2018-mayors+2020-president", title="2022 縣市長選舉", date="2022-11-26",
                        previous="2018-mayors"),
    "2018-mayors": dict(baseline="2014-mayors+2016-president", title="2018 縣市長選舉", date="2018-11-24",
                        previous="2014-mayors"),
}
# turnout spread for the scenario slider: county turnout change between elections, 2014->18 and 2018->22
TURNOUT_SIGMA = 3.75


def cand(race, k, total):
    c = race["cands"][k]
    return {"no": c["no"], "name": c["name"], "party": c["party"] or "無黨籍", "tone": TONE.get(c["party"], "ind"),
            "final": total[k]}


def incumbents(prev):
    """Winner of the previous mayoral race in each county (party at that election)."""
    out = {}
    for county, race in ST.load(prev).items():
        total = [sum(s["v"][k] for s in race["stations"]) for k in range(len(race["cands"]))]
        k = max(range(len(total)), key=lambda i: total[i])
        out[county] = {k2: v for k2, v in cand(race, k, total).items() if k2 != "final"}
    return out


def turnout_cols(ns, nd, n):
    a, d = ns.turnout(n), nd.turnout(n)
    return [a["counted"], round(a["mean"]), round(a["sd"]), round(d["mean"]), round(d["sd"])]


def build(night):
    cfg = NIGHTS[night]
    inc = incumbents(cfg["previous"])
    t0 = datetime.fromisoformat(cfg["date"] + "T16:00:00")
    races, skipped = [], []
    loaded = ST.load(night)
    for county in ORDER:
        race = loaded.get(county)
        if race is None:
            continue
        if race.get("no_times"):
            skipped.append({"area": county, "why": "voted on 2022-12-18 (rerun); not part of this night",
                            "incumbent": inc.get(county)})
            continue
        ns = N.Night(night, county, cfg["baseline"])
        nd = N.Night(night, county, cfg["baseline"], granularity="district")
        total = [sum(s["v"][k] for s in race["stations"]) for k in range(len(race["cands"]))]
        others = sum(total) - total[ns.ia] - total[ns.ib]
        pts = []
        M = len(ns.st)
        for n in range(1, M + 1):
            if n < M and minute_ceiling(ns.t[n]) == minute_ceiling(ns.t[n - 1]):
                continue
            t = (minute_ceiling(ns.t[n - 1]) - t0).total_seconds() / 60
            a, d = ns.estimate(n), nd.estimate(n)
            pts.append([round(t), n, a["ka"], a["kb"],
                        round(a["p"], 4), round(a["mean"]), round(a["sd"]), int(a["certain"]),
                        a["remE"], round(a["eb"]), round(a["vrem"]),
                        round(d["p"], 4), round(d["mean"]), round(d["sd"]), int(d["certain"]), round(d["vrem"]),
                        round(a.get("rho", 1.0), 4)]
                       + turnout_cols(ns, nd, n))
        races.append({
            "area": county,
            "blue": cand(race, ns.ia, total), "other": cand(race, ns.ib, total), "others_final": others,
            "stations": M, "electors": sum(s["E"] for s in race["stations"]),
            "prev_turnout": round(ns.base[(None, None)][1], 4),
            "pair_how": ns.target_how, "baseline_how": ns.how, "incumbent": inc.get(county),
            "pts": pts,
        })
        print(f"  {night} {county}: {len(pts)} points")
    end = max(r["pts"][-1][0] for r in races)
    return {"id": night, "title": cfg["title"], "date": cfg["date"], "baseline": cfg["baseline"],
            "start": 0, "end": end, "turnout_sigma": TURNOUT_SIGMA, "previous": cfg["previous"],
            "point_columns": ["t_min_after_16", "stations_in", "blue_votes", "other_votes",
                              "p_blue", "margin_mean", "margin_sd", "certain", "electors_left",
                              "ballots_left_at_baseline_turnout", "two_way_votes_left",
                              "p_blue_district", "margin_mean_district", "margin_sd_district",
                              "certain_district", "two_way_votes_left_district", "live_turnout_ratio",
                              "ballots_counted", "ballots_final_mean", "ballots_final_sd",
                              "ballots_final_mean_district", "ballots_final_sd_district"],
            "races": races, "skipped": skipped}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for night in NIGHTS:
        d = build(night)
        path = OUT / f"{night}.json"
        path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
