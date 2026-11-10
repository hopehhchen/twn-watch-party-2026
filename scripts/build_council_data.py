#!/usr/bin/env python3
"""Council results over election night, 2018 and 2022: data/council/<year>.json.

  python3 scripts/build_council_data.py

For every electoral district: candidates (name, party, sex, final votes, CEC elected flag), seats and
reserved women's seats, and the cumulative count at every minute in which one of its stations
reported (station report times are the CEC's station-time files, which log all contests at a station
at once). The page works out who would hold each seat if counting stopped at that minute.
"""
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import council as CO  # noqa: E402
import stations as ST  # noqa: E402
from build_cec_night import minute_ceiling  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "council"
TONE = {"中國國民黨": "kmt", "民主進步黨": "dpp", "台灣民眾黨": "tpp", "時代力量": "npp", "台灣基進": "tsp", "親民黨": "pfp", "無黨籍": "ind"}
INDEPENDENT = ("無黨籍及未經政黨推薦", "無", "無黨籍", "")


def party(name):
    return "無黨籍" if name.strip() in INDEPENDENT else name.strip()


ORDER = ["臺北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "臺中市", "彰化縣", "南投縣",
         "雲林縣", "嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣",
         "金門縣", "連江縣"]
SEAT_TYPE = {"T1": "區域", "T2": "平地原住民", "T3": "山地原住民"}


def build(year):
    data = CO.load(year)
    CO.check(year)
    tm = ST.times(f"{year}-mayors")
    t0 = datetime.fromisoformat(CO.DATES[year] + "T16:00:00")
    counties, missing, end = [], 0, 0
    for county in ORDER:
        ds = []
        for d in data[county]:
            keep = [k for k, c in enumerate(d["cands"]) if "note" not in c]
            cands = [{"no": c["no"], "name": c["name"], "party": party(c["party"]), "tone": TONE.get(party(c["party"]), "oth"),
                      "sex": c["sex"], "final": c["final"], "victor": c["victor"]} for c in (d["cands"][k] for k in keep)]
            st = []
            for s in d["stations"]:
                t = tm.get((county, s["district"], s["no"]))
                if t is None:
                    missing += 1
                    continue
                st.append((t, s))
            st.sort(key=lambda x: x[0])
            E = sum(s["E"] for _, s in st)
            acc, rem, rows = [0] * len(keep), E, []
            for i, (t, s) in enumerate(st):
                acc = [a + s["v"][k] for a, k in zip(acc, keep)]
                rem -= s["E"]
                if i + 1 < len(st) and minute_ceiling(st[i + 1][0]) == minute_ceiling(t):
                    continue
                tt = round((minute_ceiling(t) - t0).total_seconds() / 60)
                rows.append([tt, i + 1, rem] + acc)
            end = max(end, rows[-1][0])
            towns = list(dict.fromkeys(s["district"] for s in d["stations"]))
            ds.append({"no": d["no"], "name": d["name"], "seat_type": SEAT_TYPE[d["seat_type"]], "seats": d["seats"],
                       "towns": towns,
                       "women": d["women"], "stations": len(st), "electors": E, "cands": cands, "pts": rows})
        counties.append({"area": county, "districts": ds})
    if missing:
        raise SystemExit(f"{year}: {missing} stations without a report time")
    return {"id": f"{year}-council", "year": year, "date": CO.DATES[year], "title": f"{year} 縣市議員選舉",
            "start": 0, "end": end,
            "point_columns": ["t_min_after_16", "stations_in", "electors_left", "...votes per candidate, in cands order"],
            "counties": counties}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for year in [int(a) for a in sys.argv[1:]] or [2018, 2022]:
        d = build(year)
        path = OUT / f"{year}.json"
        path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
