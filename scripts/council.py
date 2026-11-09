#!/usr/bin/env python3
"""Council (縣市議員 / 直轄市議員) results per polling station, 2018 and 2022, and seat allocation.

  load(year) -> {county: [District]}
  District = {"no", "name" (第01選舉區), "seat_type" (T1 區域 / T2 平地原住民 / T3 山地原住民),
              "seats", "women" (reserved seats), "cands": [{"no", "name", "party", "sex", "final", "victor"}],
              "stations": [{"district" (行政區), "village", "no", "E", "v": [votes per cand]}]}
  allocate(votes, sexes, seats, women) -> indices elected

Station sheets: data/raw/cec-stations/<year>-<municipal|county>-council-stations.zip (one workbook per
county, one sheet per electoral district). Seats, names, parties, sexes and the CEC's elected flags:
data/raw/cec-council-tickets.tsv. check() verifies that each candidate's station votes add up to the
CEC's final, and that allocate() on the finals reproduces the CEC's elected list exactly.

  python3 scripts/council.py      # runs check() for both years
"""
import csv
import re
import sys
from functools import lru_cache
from pathlib import Path

import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_cec_night import RAW, clean, norm_station, to_int, zip_members  # noqa: E402
from stations import fix  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "data" / "raw" / "cec-council-tickets.tsv"
CODES = {"63_000": "臺北市", "64_000": "高雄市", "65_000": "新北市", "66_000": "臺中市", "67_000": "臺南市",
         "68_000": "桃園市", "10_002": "宜蘭縣", "10_004": "新竹縣", "10_005": "苗栗縣", "10_007": "彰化縣",
         "10_008": "南投縣", "10_009": "雲林縣", "10_010": "嘉義縣", "10_013": "屏東縣", "10_014": "臺東縣",
         "10_015": "花蓮縣", "10_016": "澎湖縣", "10_017": "基隆市", "10_018": "新竹市", "10_020": "嘉義市",
         "09_007": "連江縣", "09_020": "金門縣"}
ZIPS = {2018: ["2018-municipal-council-stations.zip", "2018-county-council-stations.zip"],
        2022: ["2022-municipal-council-stations.zip", "2022-county-council-stations.zip"]}
DATES = {2018: "2018-11-24", 2022: "2022-11-26"}


def reserved_women(seats):
    """地方制度法 §33: a district electing 4 gets one seat reserved for women; one more per 4 more seats."""
    return seats // 4


def allocate(votes, sexes, seats, women):
    """Top `seats` by votes; if fewer than `women` women are among them, the top women outside replace the
    lowest men inside. Ties broken by ballot order (the CEC draws lots; none occur at a cutoff here)."""
    order = sorted(range(len(votes)), key=lambda k: (-votes[k], k))
    won = order[:seats]
    short = women - sum(sexes[k] == 2 for k in won)
    if short > 0:
        add = [k for k in order[seats:] if sexes[k] == 2][:short]
        men = [k for k in reversed(won) if sexes[k] != 2]
        drop = set(men[:len(add)])
        won = [k for k in won if k not in drop] + add
    return won


def _tickets(year):
    out = {}
    for r in csv.DictReader(TICKETS.open(encoding="utf-8"), delimiter="\t"):
        if not r["election"].startswith(str(year)):
            continue
        county = CODES[r["county_code"]]
        d = out.setdefault(county, {}).setdefault(int(re.search(r"\d+", r["district"]).group()), {
            "no": int(re.search(r"\d+", r["district"]).group()), "name": r["district"], "seat_type": r["seat_type"],
            "cands": []})
        d["cands"].append({"no": int(r["cand_no"]), "name": r["name"], "party": r["party"] or "無黨籍",
                           "sex": int(r["sex"]), "final": int(r["votes"]), "victor": r["victor"].strip()})
    for county in out.values():
        for d in county.values():
            d["cands"].sort(key=lambda c: c["no"])
            d["seats"] = sum(c["victor"] in ("*", "!") for c in d["cands"])
            d["women"] = reserved_women(d["seats"])
    return out


def _sheet(sh):
    rows = [sh.row_values(r) for r in range(sh.nrows)]
    hdr = next(i for i, r in enumerate(rows) if any(clean(c) in ("投開票所別", "投票所別") for c in r[:4]))
    H = [clean(c) for c in rows[hdr]]
    ia = next(j for j, c in enumerate(H) if "有效票數" in c)
    ie = next(j for j, c in enumerate(H) if "選舉人數" in c)
    cols, nos, names = [], [], []
    for j, c in enumerate(rows[hdr + 1][:ia]):
        m = re.match(r"\(?(\d+)\)?\s*(.*)", str(c or "").strip(), re.S)
        if m and j >= 3:
            cols.append(j)
            nos.append(int(m.group(1)))
            parts = [p.strip() for p in m.group(2).split("\n") if p.strip()]
            names.append((fix(parts[0]) if parts else "", fix(parts[1]) if len(parts) > 1 else ""))
    stations, district, village = [], None, None
    for r in rows[hdr + 2:]:
        r = list(r) + [None] * 3
        c0, c1, c2 = clean(r[0]), clean(r[1]), clean(r[2])
        if c0 and not c2:
            district = fix(c0)
            continue
        if c2.replace(".0", "").isdigit():
            village = (fix(c1.split("、")[0]) if c1 else None) or village
            stations.append({"district": district, "village": village, "no": norm_station(c2),
                             "E": to_int(r[ie]) or 0, "v": [to_int(r[j]) or 0 for j in cols]})
    return nos, names, stations


@lru_cache(maxsize=None)
def load(year):
    tk = _tickets(year)
    for z in ZIPS[year]:
        for name, data in zip_members(RAW / z):
            if not name.endswith(".xls"):
                continue
            county = re.search(r"\((\S{2,3}[縣市])\)", name).group(1)
            seen = set()
            for sh in xlrd.open_workbook(file_contents=data).sheets():
                title = clean(sh.row_values(0)[0])
                no = int(re.search(r"第(\d+)選舉區", title).group(1))
                if no in seen:  # a few workbooks repeat a sheet
                    continue
                seen.add(no)
                nos, names, st = _sheet(sh)
                d = tk[county][no]
                have = {c["no"] for c in d["cands"]}
                assert have <= set(nos), (year, county, no, nos)
                for n, (nm, party) in zip(nos, names):  # on the ballot but not in the CEC's results list
                    if n not in have:
                        d["cands"].append({"no": n, "name": nm, "party": party or "無黨籍", "sex": 0,
                                           "final": None, "victor": "", "note": "not in the CEC's results list"})
                d["cands"].sort(key=lambda c: c["no"])
                assert nos == [c["no"] for c in d["cands"]], (year, county, no, nos)
                d["stations"] = st
    out = {}
    for county, ds in tk.items():
        out[county] = [ds[k] for k in sorted(ds)]
        for d in out[county]:
            assert "stations" in d, (year, county, d["no"])
    return out


def check(year):
    bad_votes, bad_alloc, seats = 0, 0, 0
    for county, ds in load(year).items():
        for d in ds:
            tot = [sum(s["v"][k] for s in d["stations"]) for k in range(len(d["cands"]))]
            for t, c in zip(tot, d["cands"]):
                if c["final"] is None:
                    print(f"  on the ballot, not in the results list: {year} {county} {d['name']} "
                          f"{c['no']} {c['name']} ({t} votes at stations)")
                    c["final"] = t
                bad_votes += t != c["final"]
            won = set(allocate(tot, [c["sex"] for c in d["cands"]], d["seats"], d["women"]))
            cec = {k for k, c in enumerate(d["cands"]) if c["victor"] in ("*", "!")}
            bad_alloc += won != cec
            seats += d["seats"]
            if won != cec:
                print("  allocation differs:", year, county, d["name"])
    print(f"{year}: {sum(len(v) for v in load(year).values())} districts, {seats} seats; "
          f"candidate totals != CEC final: {bad_votes}; allocations != CEC: {bad_alloc}")
    return bad_votes == 0 and bad_alloc == 0


if __name__ == "__main__":
    ok = all([check(2018), check(2022)])
    sys.exit(0 if ok else 1)
