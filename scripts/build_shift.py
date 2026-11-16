#!/usr/bin/env python3
"""Shift maps: how each village (村里) and town (鄉鎮市區) moved between an election and an earlier one, two ways:

  same kind ("same"):  2018 mayors vs 2014 · 2020 president vs 2016 · 2022 mayors vs 2018 · 2024 president vs 2020
  the last election of any kind ("last"): 2018 mayors vs 2016 president · 2020 president vs 2018 mayors ·
                       2022 mayors vs 2020 president · 2024 president vs 2022 mayors
  (legislative elections fall on presidential days; referendums are left out)

The measure is the blue side's margin over the other side, as a share of the two sides' votes, in percentage
points; the shift is this election's margin minus the previous one's. The sides are the ones the needle uses for
baselines (needle.blue_pair): KMT vs DPP tickets for president (2016's 宋楚瑜 and 2024's 柯文哲 set aside), and
for mayors the blue side vs the other of the top two, with the camp overrides in needle.CAMPS.

Places are matched by name (county, town, village) to the Ministry of the Interior's 2021 village map
(data/map/villages.json). Villages merged or renamed between elections don't match; their votes still count in
their town's arrow, but they get no arrow of their own. Match rates are printed and saved in each file.

  python3 scripts/build_shift.py      # writes data/shift/<year>.json and <year>-last.json
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stations  # noqa: E402
from needle import blue_pair  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAIRS = [("2018", "2018-mayors", "2014-mayors", "same"), ("2020", "2020-president", "2016-president", "same"),
         ("2022", "2022-mayors", "2018-mayors", "same"), ("2024", "2024-president", "2020-president", "same"),
         ("2018", "2018-mayors", "2016-president", "last"), ("2020", "2020-president", "2018-mayors", "last"),
         ("2022", "2022-mayors", "2020-president", "last"), ("2024", "2024-president", "2022-mayors", "last")]
kind = lambda elec: "mayors" if elec.endswith("mayors") else "president"
TONE = {"中國國民黨": "kmt", "民主進步黨": "dpp", "台灣民眾黨": "tpp", "時代力量": "npp", "親民黨": "pfp"}
MIN_VOTES = 100  # villages with fewer two-side votes in either election get no arrow (too noisy to read)
MIN_TOWN = 500  # likewise towns (烏坵鄉 has about 200)


def zh(s):
    return (s or "").replace("台", "臺") if (s or "").startswith("台") else (s or "")


def sides(elec, county, race, top_two):
    bp = blue_pair(race, (elec, county), top_two)
    if bp is None:
        return None
    a, b, how = bp
    return a, b, race["cands"][a], race["cands"][b]


def tally(elec, top_two):
    """{county: {"blue", "other", "towns": {town: [b, o]}, "villages": {(town, vill): [b, o]}}}"""
    out = {}
    for county, race in stations.load(elec).items():
        s = sides(elec, zh(county), race, top_two)
        if s is None:
            print(f"  {elec} {county}: no blue side, left out")
            continue
        a, b, ca, cb = s
        towns, vills = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        for st in race["stations"]:
            t, v = st["district"], st["village"]
            towns[t][0] += st["v"][a]
            towns[t][1] += st["v"][b]
            vills[(t, v)][0] += st["v"][a]
            vills[(t, v)][1] += st["v"][b]
        out[zh(county)] = {"blue": {k: ca[k] for k in ("no", "name", "party")}, "other": {k: cb[k] for k in ("no", "name", "party")},
                           "towns": towns, "villages": vills}
    return out


def margin(bo):
    b, o = bo
    return (b - o) / (b + o) if b + o else None


def main():
    geo = json.loads((ROOT / "data" / "map" / "villages.json").read_text())
    V, T = geo["villages"], geo["towns"]
    outdir = ROOT / "data" / "shift"
    outdir.mkdir(exist_ok=True)
    cache = {}
    for year, cur, prev, mode in PAIRS:
        for e in (cur, prev):
            if e not in cache:
                cache[e] = tally(e, kind(e) == "mayors")
        A, B = cache[prev], cache[cur]
        races, towns, vills = [], [], []
        n_v = n_vm = n_t = n_tm = 0
        for county in B:
            if county not in A:
                print(f"  {year} {county}: no previous race, left out")
                continue
            a, b = A[county], B[county]
            ca = [sum(x[0] for x in a["towns"].values()), sum(x[1] for x in a["towns"].values())]
            cb = [sum(x[0] for x in b["towns"].values()), sum(x[1] for x in b["towns"].values())]
            races.append({"area": county, "blue": b["blue"], "other": b["other"], "prev_blue": a["blue"], "prev_other": a["other"],
                          "tone": TONE.get(b["other"]["party"], "ind"), "prev_margin": round(100 * margin(ca), 1),
                          "margin": round(100 * margin(cb), 1), "shift": round(100 * (margin(cb) - margin(ca)), 1)})
            for t, bo in b["towns"].items():
                n_t += 1
                g = T.get(f"{county}|{t}")
                if t not in a["towns"] or not g:
                    continue
                n_tm += 1
                if min(sum(a["towns"][t]), sum(bo)) < MIN_TOWN:
                    continue
                towns.append([county, t, g["c"][0], g["c"][1], round(100 * margin(a["towns"][t]), 1), round(100 * margin(bo), 1), sum(bo)])
            for (t, v), bo in b["villages"].items():
                n_v += 1
                g = V.get(f"{county}|{t}|{v}")
                ao = a["villages"].get((t, v))
                if not g or not ao:
                    continue
                n_vm += 1
                if min(sum(ao), sum(bo)) < MIN_VOTES:
                    continue
                vills.append([f"{county}|{t}|{v}", g[0], g[1], round(100 * margin(ao), 1), round(100 * margin(bo), 1), sum(bo)])
        doc = {"year": year, "mode": mode, "election": cur, "previous": prev, "kind": kind(cur), "prev_kind": kind(prev),
               "columns": {"towns": ["county", "town", "x", "y", "prev_margin", "margin", "votes"],
                           "villages": ["key", "x", "y", "prev_margin", "margin", "votes"]},
               "matched": {"towns": [n_tm, n_t], "villages": [n_vm, n_v], "min_votes": MIN_VOTES, "min_town_votes": MIN_TOWN},
               "races": races, "towns": towns, "villages": vills}
        name = year if mode == "same" else f"{year}-last"
        (outdir / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        print(f"{name} ({cur} vs {prev}): {len(races)} races; towns matched {n_tm}/{n_t}; villages matched {n_vm}/{n_v}, "
              f"{len(vills)} with arrows")


if __name__ == "__main__":
    main()
