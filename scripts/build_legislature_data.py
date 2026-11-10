#!/usr/bin/env python3
"""Legislative elections on the presidential nights (2020, 2024): data/legislature/<year>.json.

  python3 scripts/build_legislature_data.py [2020 2024]

- districts: the 73 single-seat districts, each as a needle race (same model and point columns as the
  mayoral races; baseline: the previous presidential race, village by village). A district where a third
  candidate finished in the top two or within 10 points of the winner also gets three-way columns.
- party: the party-list vote over the night (scripts/party_vote.py): projected shares with sds, counted
  shares, the most likely seat splits with their chances, and each party's chance of clearing 5%.
- indigenous: the two 3-seat indigenous races (平地, 山地), counted like a council district.
Every number at a given minute uses only stations reported by then (CEC station report times).
"""
import json
import random
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import needle as N  # noqa: E402
import party_vote as PV  # noqa: E402
import stations as ST  # noqa: E402
from build_cec_night import minute_ceiling  # noqa: E402
from build_needle_data import ORDER, TONE, TURNOUT_SIGMA, cand, race_entry, three_way_rule  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "legislature"
YEARS = {2020: dict(baseline="2016-president", prev_leg="2016-legislator", prev_party="2016-party", date="2020-01-11",
                    title="2020 立法委員選舉"),
         2024: dict(baseline="2020-president", prev_leg="2020-legislator", prev_party="2020-party", date="2024-01-13",
                    title="2024 立法委員選舉")}
INDEPENDENT = ("無", "無黨籍", "無黨籍及未經政黨推薦", "")


def party_name(p):
    return "無黨籍" if p.strip() in INDEPENDENT else p.strip()


def order_key(key):
    c = ST.county_of(key)
    n = int(key[len(c) + 1:-3]) if "第" in key else 0
    return (ORDER.index(c), n)


def prev_winners(prev_leg):
    """Winner of the same-numbered district in the previous legislative race (lines may have moved)."""
    out = {}
    for key, r in ST.load(prev_leg).items():
        tot = [sum(s["v"][k] for s in r["stations"]) for k in range(len(r["cands"]))]
        k = max(range(len(tot)), key=lambda i: tot[i])
        c = dict(r["cands"][k], party=party_name(r["cands"][k]["party"]))
        out[key] = {"no": c["no"], "name": c["name"], "party": c["party"], "tone": TONE.get(c["party"], "ind")}
        if key.endswith("第1選舉區") and sum(ST.county_of(x) == ST.county_of(key) for x in ST.load(prev_leg)) == 1:
            out[ST.county_of(key) + "選舉區"] = out[key]  # one-seat counties: "基隆市第1選舉區" in 2016 files
    return out


def districts(year, cfg, t0):
    target = f"{year}-legislator"
    races, inc = ST.load(target), prev_winners(cfg["prev_leg"])
    out = []
    for key in sorted(races, key=order_key):
        race = races[key]
        for c in race["cands"]:
            c["party"] = party_name(c["party"])
        ns = N.Night(target, key, cfg["baseline"])
        nd = N.Night(target, key, cfg["baseline"], granularity="district")
        total = [sum(s["v"][k] for s in race["stations"]) for k in range(len(race["cands"]))]
        rest = [k for k in sorted(range(len(total)), key=lambda k: -total[k]) if k not in (ns.ia, ns.ib)]
        third = rest[0] if rest and three_way_rule(total, ns.ia, ns.ib, rest[0]) else None
        e = race_entry(ns, nd, race, key, key, t0, inc.get(key), third)
        e["county"] = ST.county_of(key)
        out.append(e)
    return out


def party(year, cfg, t0):
    pn = PV.PartyNight(f"{year}-party", cfg["prev_party"])
    rng = random.Random(year)
    # parties listed on the page: any that ran above 1% last time, or reach 1% of the count at some point
    pts, keep = [], set()
    n_all = len(pn.st)
    marks = [i + 1 for i in range(n_all) if i + 1 == n_all or minute_ceiling(pn.st[i + 1][0]) != minute_ceiling(pn.st[i][0])]
    rows = []
    for n in marks:
        if n < PV.MIN_STATIONS:
            continue
        share, sd, counted, out_frac = pn.project(n)
        splits, clear = pn.seat_odds(share, sd, rng)
        t = round((minute_ceiling(pn.st[n - 1][0]) - t0).total_seconds() / 60)
        rows.append((t, n, out_frac, share, sd, counted, splits, clear))
        keep |= {p for p, v in counted.items() if v >= 0.01}
    prev_big = {p for m in PV.prev_shares(cfg["prev_party"])[2].values() for p, v in m.items() if v >= 0.01}
    parties = sorted(keep | (prev_big & set(pn.parties)), key=lambda p: -pn.final[p])
    idx = {p: i for i, p in enumerate(parties)}
    for t, n, out_frac, share, sd, counted, splits, clear in rows:
        pts.append([t, n, round(out_frac, 4),
                    [round(share[p], 5) for p in parties], [round(sd[p], 5) for p in parties],
                    [round(counted[p], 5) for p in parties],
                    [[[sp.get(p, 0) for p in parties], round(pr, 3)] for sp, pr in splits[:4]],
                    [round(clear.get(p, 0), 3) for p in parties]])
    V = sum(pn.final.values())
    fsh = {p: v / V for p, v in pn.final.items()}
    fseats, _ = PV.hare(fsh)
    return {"seats": PV.SEATS, "threshold": PV.THRESHOLD, "stations": n_all,
            "parties": [{"name": p, "tone": TONE.get(p, "oth"), "new": p not in pn.known,
                         "final": round(fsh[p], 5), "final_seats": fseats.get(p, 0)} for p in parties],
            "point_columns": ["t_min_after_16", "stations_in", "share_of_votes_still_out", "projected_share[]",
                              "sd[]", "counted_share[]", "top_splits [[seats per party], chance]", "p_clear_5pct[]"],
            "method": "scripts/party_vote.py", "pts": pts}


def indigenous(year, t0):
    out = []
    for kind, label in (("plains", "平地原住民"), ("mountain", "山地原住民")):
        races, tm = ST.load(f"{year}-{kind}"), ST.times(f"{year}-{kind}")
        cands = next(iter(races.values()))["cands"]
        st = sorted(((tm[(c, s["district"], s["no"])], s) for c, r in races.items() for s in r["stations"]), key=lambda x: x[0])
        E = sum(s["E"] for _, s in st)
        acc, rem, rows = [0] * len(cands), E, []
        for i, (t, s) in enumerate(st):
            acc = [a + v for a, v in zip(acc, s["v"])]
            rem -= s["E"]
            if i + 1 < len(st) and minute_ceiling(st[i + 1][0]) == minute_ceiling(t):
                continue
            rows.append([round((minute_ceiling(t) - t0).total_seconds() / 60), i + 1, rem] + acc)
        tot = rows[-1][3:]
        won = set(sorted(range(len(tot)), key=lambda k: -tot[k])[:3])
        out.append({"no": 1, "name": label, "seat_type": label, "seats": 3, "women": 0, "towns": ["全國"],
                    "stations": len(st), "electors": E,
                    "cands": [{"no": c["no"], "name": c["name"], "party": party_name(c["party"]),
                               "tone": TONE.get(party_name(c["party"]), "ind" if party_name(c["party"]) == "無黨籍" else "oth"),
                               "sex": 0, "final": tot[k], "victor": "*" if k in won else ""} for k, c in enumerate(cands)],
                    "pts": rows})
    return out


def build(year):
    cfg = YEARS[year]
    t0 = datetime.fromisoformat(cfg["date"] + "T16:00:00")
    ds = districts(year, cfg, t0)
    print(f"{year}: {len(ds)} districts")
    pv = party(year, cfg, t0)
    print(f"{year}: party list, {len(pv['pts'])} points, parties {[p['name'] for p in pv['parties']]}")
    ind = indigenous(year, t0)
    end = max([r["pts"][-1][0] for r in ds] + [pv["pts"][-1][0]] + [d["pts"][-1][0] for d in ind])
    return {"id": f"{year}-legislature", "title": cfg["title"], "date": cfg["date"], "baseline": cfg["baseline"],
            "previous": cfg["baseline"], "start": 0, "end": end, "turnout_sigma": TURNOUT_SIGMA["president"],
            "races": ds, "party": pv, "indigenous": ind,
            "note": "District needles: previous presidential race as the baseline. Incumbent = winner of the same-"
                    "numbered district last time (district lines may have changed)."}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for year in [int(a) for a in sys.argv[1:]] or list(YEARS):
        d = build(year)
        path = OUT / f"{year}.json"
        path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
