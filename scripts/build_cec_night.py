#!/usr/bin/env python3
"""Reconstruct the CEC's own count over election night from per-polling-station data.

Inputs (data/raw/cec-stations/, downloaded from db.cec.gov.tw election attachments):
  <year>-station-times.xls(x)   全國投開票所完成時間: when each polling station's report was logged
  <year>-*-stations.zip         per-polling-station votes for each candidate

Output: data/nights/<election>.cec.json — for each race, the cumulative vote count for
every candidate at each minute in which at least one station reported.

Caveat: the time is when a station's report was *logged* in the CEC system. For 2022 the
file covers the whole local election (nine contests at once), so it may be later than the
moment that station's mayoral numbers were entered. Treat the curve as the CEC's count
"no earlier than" each timestamp; it is not a record of what the CEC website displayed.

Usage: python3 scripts/build_cec_night.py
Requires: xlrd, openpyxl
"""
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
import xlrd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "cec-stations"
OUT = ROOT / "data" / "nights"
FINALS = ROOT / "data" / "finals"


def zip_members(path):
    """Yield (decoded_name, bytes); CEC zips store Big5 (cp950) names without the UTF-8 flag."""
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.is_dir():
                continue
            name = i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("cp950")
            yield Path(name).name, z.read(i)


def to_int(v):
    if v is None or v == "":
        return None
    return int(float(str(v).replace(",", "")))


def norm_station(v):
    return str(to_int(v))


def clean(s):
    return re.sub(r"[\s\u3000]+", "", str(s or ""))


def rows_xls(data):
    sh = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
    for r in range(sh.nrows):
        yield sh.row_values(r)


def rows_xlsx(data):
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True).worksheets[0]
    for row in ws.iter_rows(values_only=True):
        yield list(row)


def read_times(path):
    """{(county, district, station_no): datetime}"""
    rows = rows_xls(path.read_bytes()) if path.suffix == ".xls" else rows_xlsx(path.read_bytes())
    out = {}
    for row in rows:
        county, district, station, ts = (clean(x) for x in row[:4])
        if not station or not station.replace(".0", "").isdigit():
            continue
        m = re.match(r"(\d+)/(\d+)/(\d+)(\d\d:\d\d:\d\d)", ts)
        if not m:
            continue
        y = int(m.group(1))
        y = y + 1911 if y < 1911 else y  # ROC calendar (113 -> 2024)
        out[(county, district, norm_station(station))] = datetime.strptime(
            f"{y}-{m.group(2)}-{m.group(3)} {m.group(4)}", "%Y-%m-%d %H:%M:%S"
        )
    return out


def parse_station_sheet(rows):
    """Parse a CEC 'candidate votes per polling station' sheet.

    Returns (candidate_numbers, [(district, station_no, [votes...]), ...]).
    Layout: header row with '投開票所別'; next row holds candidate cells like '6\\n蔣萬安\\n...'
    or '(2)\\n賴清德\\n蕭美琴'; then a grand-total row, district subtotal rows (district in col 0,
    no station), and station rows (district blank, village in col 1, station no in col 2).
    """
    rows = list(rows)
    hdr = next(i for i, r in enumerate(rows) if any(clean(c) == "投開票所別" for c in r[:4]))
    cand_row = rows[hdr + 1]
    cand_cols, cand_nos = [], []
    for j, c in enumerate(cand_row):
        m = re.match(r"\(?(\d+)\)?\s*\n", str(c or ""))
        if m:
            cand_cols.append(j)
            cand_nos.append(int(m.group(1)))
    stations, district = [], None
    for r in rows[hdr + 2:]:
        c0, c2 = clean(r[0]), clean(r[2]) if len(r) > 2 else ""
        if c0 and not c2:
            district = c0  # district subtotal row (or the grand total row)
            continue
        if c2 and c2.isdigit():
            votes = [to_int(r[j]) or 0 for j in cand_cols]
            stations.append((district, norm_station(c2), votes))
    return cand_nos, stations


def county_from_name(name):
    m = re.search(r"\((\D{2,3}[縣市])\)", name)
    return m.group(1) if m else None


def minute_ceiling(t):
    """Round a report time up to the next whole minute: by HH:MM, these stations were in."""
    base = t.replace(second=0, microsecond=0)
    return base if t == base else base + timedelta(minutes=1)


def cumulate(events, width):
    """events: [(datetime, [votes...])] -> [[HH:MM, stations_reported, cum...], ...]"""
    by_min = defaultdict(list)
    for t, v in events:
        by_min[minute_ceiling(t)].append(v)
    series, cum, n = [], [0] * width, 0
    for k in sorted(by_min):
        for v in by_min[k]:
            cum = [a + b for a, b in zip(cum, v)]
            n += 1
        series.append([k.strftime("%H:%M"), n] + cum)
    return series, cum, n


def build(election, race_files, times, finals, national=None):
    """race_files: [(county_name, filename, bytes)]"""
    fin = {r["area_name"]: r for r in finals["races"]}
    races, problems = [], []
    nat_events = []
    for county, fname, data in race_files:
        rows = rows_xls(data) if fname.endswith(".xls") else rows_xlsx(data)
        cand_nos, stations = parse_station_sheet(rows)
        events, missing = [], []
        for district, st, votes in stations:
            t = times.get((county, district, st))
            if t is None:
                missing.append(f"{district}#{st}")
                continue
            events.append((t, votes))
        series, cum, _ = cumulate(events, len(cand_nos))
        f = fin.get(county)
        final_votes = {o["no"]: o["votes"] for o in f["options"]} if f else {}
        end = dict(zip(cand_nos, cum))
        status = "matches final" if end == final_votes else "MISMATCH"
        if status != "matches final":
            problems.append(f"{county}: end {end} vs final {final_votes}")
        if missing:
            problems.append(f"{county}: {len(missing)} stations without a report time, e.g. {missing[:3]}")
        races.append({
            "area_name": county,
            "area_code": f["area_code"] if f else None,
            "options": cand_nos,
            "stations_total": len(stations),
            "end_state": status,
            "series_columns": ["time", "stations_reported"] + [f"no_{c}" for c in cand_nos],
            "series": series,
        })
        if national is not None:
            nat_events.extend(events)
    if national is not None:
        series, cum, n = cumulate(nat_events, 3)
        nf = next(r for r in finals["races"] if r["level"] == "national")
        end = dict(zip([1, 2, 3], cum))
        ok = end == {o["no"]: o["votes"] for o in nf["options"]}
        if not ok:
            problems.append(f"national: end {end} mismatch")
        races.insert(0, {
            "area_name": "全國", "area_code": "00_000", "options": [1, 2, 3],
            "stations_total": n, "end_state": "matches final" if ok else "MISMATCH",
            "series_columns": ["time", "stations_reported", "no_1", "no_2", "no_3"],
            "series": series,
        })
    return races, problems


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {
        "2022-local-mayors": (
            RAW / "2022-station-times.xls",
            [RAW / "2022-municipal-mayor-stations.zip", RAW / "2022-county-mayor-stations.zip"],
            lambda n: n.endswith(".xls"),
            False,
            "2022-11-26",
        ),
        "2024-president": (
            RAW / "2024-station-times.xlsx",
            [RAW / "2024-president-stations.zip"],
            lambda n: "A05-4" in n,  # per-polling-station sheets, one per county
            True,
            "2024-01-13",
        ),
    }
    failed = False
    for election, (tpath, zips, pick, national, date) in jobs.items():
        times = read_times(tpath)
        finals = json.loads((FINALS / f"{election}.json").read_text())
        files = []
        for z in zips:
            for name, data in zip_members(z):
                if pick(name):
                    files.append((county_from_name(name), name, data))
        races, problems = build(election, files, times, finals, national=True if national else None)
        out = {
            "election": election,
            "vote_date": date,
            "source": "CEC per-polling-station results joined with per-station report times (db.cec.gov.tw attachments)",
            "timezone": "Asia/Taipei",
            "time_semantics": "minute by which the station's report had been logged in the CEC system (rounded up)",
            "races": races,
        }
        (OUT / f"{election}.cec.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{election}: {len(races)} races, {len(times)} station times")
        for p in problems:
            print("  PROBLEM:", p)
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
