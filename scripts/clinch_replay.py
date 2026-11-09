#!/usr/bin/env python3
"""Replay one 2022 mayoral race to see when the winner was mathematically certain.

  python3 scripts/clinch_replay.py [county]        (default 臺北市)

Joins the CEC per-polling-station sheet (votes, valid ballots, electors per station) with the
per-station report times, then walks the night minute by minute and reports the first minute
each rule is met:

  50% line      leader > half of (electors x turnout cap x valid share)
  global cap    leader - runner-up > electors x turnout cap x valid share - valid counted so far
  station cap   leader - runner-up > electors at stations not yet counted x turnout cap

"station cap @ 100%" needs no turnout assumption at all: a station cannot cast more ballots than
it has electors. The others hold only if turnout really stays under the cap.

Report times cover all nine contests at a station, so they are "no earlier than" times.
Turnout history comes from data/raw/cec-mayor-turnout.tsv (CEC election database profiles).
"""
import re
import statistics as st
import sys
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_cec_night import RAW, clean, minute_ceiling, norm_station, read_times, rows_xls, to_int, zip_members  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def turnout_history(county):
    rows = [l.rstrip("\n").split("\t") for l in open(ROOT / "data/raw/cec-mayor-turnout.tsv", encoding="utf-8")]
    return [(int(r[0][:4]), float(r[7])) for r in rows if r[2] == county]


def stations_for(county):
    times = read_times(RAW / "2022-station-times.xls")
    for z in ("2022-municipal-mayor-stations.zip", "2022-county-mayor-stations.zip"):
        for name, data in zip_members(RAW / z):
            if f"({county})" in name and name.endswith(".xls"):
                break
        else:
            continue
        break
    else:
        sys.exit(f"no station sheet for {county}")
    R = list(rows_xls(data))
    hdr = next(i for i, r in enumerate(R) if any(clean(c) == "投開票所別" for c in r[:4]))
    H = [clean(c) for c in R[hdr]]
    gi = next(j for j, c in enumerate(H) if c.startswith("G選舉人數"))
    ai = next(j for j, c in enumerate(H) if c.startswith("A有效票數"))
    bi = next(j for j, c in enumerate(H) if c.startswith("C投票數"))
    cand = [(j, clean(c)) for j, c in enumerate(R[hdr + 1]) if re.match(r"\d+", clean(c))]
    out, district = [], None
    for r in R[hdr + 2:]:
        c0, c2 = clean(r[0]), clean(r[2])
        if c0 and not c2:
            district = c0
            continue
        if c2.isdigit():
            out.append(dict(t=times[(county, district, norm_station(c2))], E=to_int(r[gi]), A=to_int(r[ai]),
                            C=to_int(r[bi]), v=[to_int(r[j]) or 0 for j, _ in cand]))
    return [c for _, c in cand], sorted(out, key=lambda s: s["t"])


def main():
    county = sys.argv[1] if len(sys.argv) > 1 else "臺北市"
    hist = turnout_history(county)
    recent = [t for y, t in hist if 2010 <= y <= 2018]  # what was known before 2022
    last = [t for y, t in hist if y == 2018][0]
    sig = st.stdev(recent) if len(recent) > 1 else 0.0
    names, stations = stations_for(county)
    E = sum(s["E"] for s in stations)
    share = sum(s["A"] for s in stations) / sum(s["C"] for s in stations)
    print(f"{county}: {len(stations)} stations, {E:,} electors; turnout history {hist}")
    caps = {f"prev+1σ ({last + sig:.2f}%)": (last + sig) / 100,
            f"prev+2σ ({last + 2 * sig:.2f}%)": (last + 2 * sig) / 100,
            "100%": 1.0}
    first, cum, cv, remE, n = {}, [0] * len(names), 0, E, 0
    for m, grp in groupby(stations, key=lambda s: minute_ceiling(s["t"])):
        for s in grp:
            cum = [a + b for a, b in zip(cum, s["v"])]
            cv, remE, n = cv + s["A"], remE - s["E"], n + 1
        o = sorted(range(len(names)), key=lambda k: -cum[k])
        L, R = cum[o[0]], cum[o[1]]
        for k, c in caps.items():
            for rule, ok in (("50% line", L > 0.5 * E * c * share),
                             ("global cap", L - R > E * c * share - cv),
                             ("station cap", L - R > remE * c)):
                key = f"{rule} @ {k}"
                if ok and key not in first:
                    first[key] = (m.strftime("%H:%M"), n, f"{100 * n / len(stations):.1f}%", names[o[0]], L, R)
    for k in caps:
        for rule in ("50% line", "global cap", "station cap"):
            key = f"{rule} @ {k}"
            print(f"  {key:38s}", first.get(key, "never met"))


if __name__ == "__main__":
    main()
