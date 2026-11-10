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
    # presidential: the 2020 presidential race alone beat a blend with the 2022 mayoral races on this night
    "2024-president": dict(baseline="2020-president", title="2024 總統選舉", date="2024-01-13",
                           previous="2020-president", national=True),
}
NIGHTS_DIR = ROOT / "data" / "nights"
CHANNELS = [  # 2024 broadcast counts read from the channels' streams (data/nights/2024-president.<id>.json)
    ("pts", "pts-own", "公視", "PTS, own count", "reliable"),
    ("cts", "cts", "華視", "CTS", "reliable"),
    ("set", "set", "三立", "SET", "field"),
    ("tvbs", "tvbs", "TVBS", "TVBS", "field"),
]


def three_way_rule(total, ia, ib, third):
    """Show a race as three-way (projected shares, no win chance) when the third candidate finished in
    the top two, or within 10 points of the winner. In 2026 this is decided before the night, from polls;
    in the replay it uses the final result, which is hindsight."""
    order = sorted(range(len(total)), key=lambda k: -total[k])
    V = sum(total)
    if third in order[:2]:
        return True
    return (total[order[0]] - total[third]) / V < 0.10
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


# Three-way win chances are left out (null) until a race has this many stations in: with no earlier election
# for the third candidate, one or two stations' share is a poor guide (2024 backtest, all 22 counties: log loss
# of the eventual winner's chance 1.65 at 1 station, 0.64 at 2, 0.26 at 3, 0.13 at 5).
MIN_STATIONS_WIN3 = 5


def three_cols(ns, nd, n, third):
    out, pw = [], []
    for nt in (ns, nd):
        r = nt.three_way(n, third)
        out += [round(x, 4) for x in r["mean"]] + [round(x, 4) for x in r["sd"]] + [int(r["certain"])]
        pw += [round(x, 4) for x in r["p_win"]] if n >= MIN_STATIONS_WIN3 else [None] * 3
    cnt = sum(s["v"][third] for s in ns.st[:n])
    return [cnt] + out + pw


def race_entry(ns, nd, race, area, label, t0, inc=None, third=None):
    total = [sum(s["v"][k] for s in race["stations"]) for k in range(len(race["cands"]))]
    others = sum(total) - total[ns.ia] - total[ns.ib]
    pts = []
    M = len(ns.st)
    for n in range(1, M + 1):
        if n < M and minute_ceiling(ns.t[n]) == minute_ceiling(ns.t[n - 1]):
            continue
        t = (minute_ceiling(ns.t[n - 1]) - t0).total_seconds() / 60
        a, d = ns.estimate(n), nd.estimate(n)
        row = [round(t), n, a["ka"], a["kb"],
               round(a["p"], 4), round(a["mean"]), round(a["sd"]), int(a["certain"]),
               a["remE"], round(a["eb"]), round(a["vrem"]),
               round(d["p"], 4), round(d["mean"]), round(d["sd"]), int(d["certain"]), round(d["vrem"]),
               round(a.get("rho", 1.0), 4)] + turnout_cols(ns, nd, n)
        if third is not None:
            row += three_cols(ns, nd, n, third)
        pts.append(row)
    e = {
        "area": area, "label": label,
        "blue": cand(race, ns.ia, total), "other": cand(race, ns.ib, total), "others_final": others,
        "stations": M, "electors": sum(s["E"] for s in race["stations"]),
        "prev_turnout": round(ns.base[(None, None)][1], 4),
        "pair_how": ns.target_how, "baseline_how": ns.how, "incumbent": inc,
        "pts": pts,
    }
    if third is not None:
        e["third"] = cand(race, third, total)
        e["mode"] = "three" if three_way_rule(total, ns.ia, ns.ib, third) and area != "全國" else "two"
    print(f"  {area}: {len(pts)} points" + (f" ({e['mode']})" if third is not None else ""))
    return e


def channel_sources(night):
    if night != "2024-president":
        return None
    out = []
    for key, fname, label, en, cohort in CHANNELS:
        d = json.loads((NIGHTS_DIR / f"2024-president.{fname}.json").read_text())
        nos = d["options"]  # ballot numbers: 1 柯文哲, 2 賴清德, 3 侯友宜
        idx = {no: i for i, no in enumerate(nos)}

        def tmin(hhmm):
            p = [int(x) for x in hhmm.split(":")]
            return round((p[0] - 16) * 60 + p[1] + (p[2] / 60 if len(p) > 2 else 0), 2)
        series = [[tmin(r[0])] + [r[1 + idx[no]] for no in (3, 2, 1)] for r in d["series"]]  # blue, other, third
        out.append({"id": key, "label": label, "en": en, "cohort": cohort, "series": series,
                    "ends": tmin("18:20") if key == "pts" else None})
    return out


def county_sources(night, county):
    """華視's rotating county panel (data/nights/2024-president.cts-county.json), where it was read."""
    if night != "2024-president":
        return None
    d = json.loads((NIGHTS_DIR / "2024-president.cts-county.json").read_text())
    rows = d["counties"].get(county)
    if not rows:
        return None

    def tmin(hhmm):
        h, m, sec = (int(x) for x in hhmm.split(":"))
        return round((h - 16) * 60 + m + sec / 60, 2)
    # file columns: 賴, 侯, 柯 -> blue (侯), other (賴), third (柯)
    return [{"id": "cts", "label": "華視", "en": "CTS (county panel)", "cohort": "reliable",
             "series": [[tmin(r[0]), r[2], r[1], r[3]] for r in rows], "ends": None, "stale": 15}]


def build(night):
    cfg = NIGHTS[night]
    inc = incumbents(cfg["previous"])
    t0 = datetime.fromisoformat(cfg["date"] + "T16:00:00")
    races, skipped = [], []
    loaded = ST.load(night)
    if cfg.get("national"):
        ns = N.NationalNight(night, cfg["baseline"])
        nd = N.NationalNight(night, cfg["baseline"], granularity="district")
        nat = {"cands": ns.race["cands"], "stations": ns.race["stations"]}
        third = next(k for k in range(len(nat["cands"])) if k not in (ns.ia, ns.ib))
        e = race_entry(ns, nd, nat, "全國", "全國 · 總統", t0, None, third)
        e["sources"] = channel_sources(night)
        races.append(e)
        for county in ORDER:
            ns = N.Night(night, county, cfg["baseline"])
            nd = N.Night(night, county, cfg["baseline"], granularity="district")
            e = race_entry(ns, nd, loaded[county], county, f"{county} · 總統", t0, inc.get(county), third)
            src = county_sources(night, county)
            if src:
                e["sources"] = src
            races.append(e)
    for county in ([] if cfg.get("national") else ORDER):
        race = loaded.get(county)
        if race is None:
            continue
        if race.get("no_times"):
            skipped.append({"area": county, "why": "voted on 2022-12-18 (rerun); not part of this night",
                            "incumbent": inc.get(county)})
            continue
        ns = N.Night(night, county, cfg["baseline"])
        nd = N.Night(night, county, cfg["baseline"], granularity="district")
        races.append(race_entry(ns, nd, race, county, f"{county}長", t0, inc.get(county)))
    end = max(r["pts"][-1][0] for r in races)
    return {"id": night, "title": cfg["title"], "date": cfg["date"], "baseline": cfg["baseline"],
            "start": 0, "end": end, "turnout_sigma": TURNOUT_SIGMA, "previous": cfg["previous"],
            "point_columns": ["t_min_after_16", "stations_in", "blue_votes", "other_votes",
                              "p_blue", "margin_mean", "margin_sd", "certain", "electors_left",
                              "ballots_left_at_baseline_turnout", "two_way_votes_left",
                              "p_blue_district", "margin_mean_district", "margin_sd_district",
                              "certain_district", "two_way_votes_left_district", "live_turnout_ratio",
                              "ballots_counted", "ballots_final_mean", "ballots_final_sd",
                              "ballots_final_mean_district", "ballots_final_sd_district",
                              "(three-way races) third_votes", "share_blue", "share_other", "share_third",
                              "sd_blue", "sd_other", "sd_third", "certain3", "...same seven for district feed",
                              "p_win_blue", "p_win_other", "p_win_third", "...same three for district feed"],
            "races": races, "skipped": skipped}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for night in (sys.argv[1:] or NIGHTS):
        d = build(night)
        path = OUT / f"{night}.json"
        path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
