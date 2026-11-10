#!/usr/bin/env python3
"""Per-polling-station results for every election we model, in one shape.

  load(election) -> {county: Race}
  times(election) -> {(county, district, station_no): datetime} or {} when there is no file

Race = {"cands": [{"no", "name", "party"}], "stations": [Station]}
Station = {"district", "village", "no", "E" (electors), "C" (ballots cast), "A" (valid), "v": [votes per cand]}

Sources (data/raw/cec-stations/, from db.cec.gov.tw election attachments; SHA256SUMS lists the hashes
the CEC publishes): 縣表3-1 sheets for mayors, 總統-A05-4 sheets for presidents.

  python3 scripts/stations.py        # prints a summary and cross-election station match rates
"""
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_cec_night import RAW, clean, norm_station, read_times, rows_xls, rows_xlsx, to_int, zip_members  # noqa: E402

ELECTIONS = {
    "2014-mayors": dict(zips=["2014-municipal-mayor-stations.zip", "2014-county-mayor-stations.zip"], date="2014-11-29"),
    "2018-mayors": dict(zips=["2018-municipal-mayor-stations.zip", "2018-county-mayor-stations.zip"], date="2018-11-24",
                        times="2018-station-times.xlsx"),
    "2022-mayors": dict(zips=["2022-municipal-mayor-stations.zip", "2022-county-mayor-stations.zip"], date="2022-11-26",
                        times="2022-station-times.xls",
                        extra={"嘉義市": "2022-chiayi-city-rerun-stations.xls"}),  # 嘉義市 voted 2022-12-18
    "2016-president": dict(zips=["2016-president-stations.zip"], date="2016-01-16", pick="A05-4"),
    "2020-president": dict(zips=["2020-president-stations.zip"], date="2020-01-11", pick="A05-4",
                           times="2020-station-times.xls"),
    "2024-president": dict(zips=["2024-president-stations.zip"], date="2024-01-13", pick="A05-4",
                           times="2024-station-times.xlsx"),
    # district legislators (區域立委): one sheet per electoral district; races keyed "臺北市第1選舉區"
    "2016-legislator": dict(zips=["2016-legislator-stations.zip"], date="2016-01-16", pick="立委-A05-2-",
                            per_sheet=True),
    "2016-party": dict(zips=["2016-legislator-stations.zip"], date="2016-01-16", pick="立委-A05-6-", parties=True),
    "2020-legislator": dict(zips=["2020-legislator-stations.zip"], date="2020-01-11", pick="區域立委-A05-2-",
                            times="2020-station-times.xls", per_sheet=True),
    "2024-legislator": dict(zips=["2024-legislator-stations.zip"], date="2024-01-13", pick="區域立委-A05-2-",
                            times="2024-station-times.xlsx", per_sheet=True),
    # party-list vote (不分區政黨票), one sheet per county; "candidates" are parties
    "2020-party": dict(zips=["2020-legislator-stations.zip"], date="2020-01-11", pick="不分區立委-A05-6",
                       times="2020-station-times.xls", parties=True),
    # indigenous legislators (平地/山地原住民): one national 3-seat race each, counted per county sheet
    "2020-plains": dict(zips=["2020-legislator-stations.zip"], date="2020-01-11", pick="平地立委-A05-4",
                        times="2020-station-times.xls"),
    "2020-mountain": dict(zips=["2020-legislator-stations.zip"], date="2020-01-11", pick="山地立委-A05-4",
                          times="2020-station-times.xls"),
    "2024-plains": dict(zips=["2024-legislator-stations.zip"], date="2024-01-13", pick="平地立委-A05-4",
                        times="2024-station-times.xlsx"),
    "2024-mountain": dict(zips=["2024-legislator-stations.zip"], date="2024-01-13", pick="山地立委-A05-4",
                          times="2024-station-times.xlsx"),
    "2024-party": dict(zips=["2024-legislator-stations.zip"], date="2024-01-13", pick="不分區立委-A05-6",
                       times="2024-station-times.xlsx", parties=True),
}


def county_of(key):
    """'臺北市第1選舉區' or '基隆市選舉區' (one-seat counties) -> the county; a county name is returned as is."""
    return re.sub(r"(第\d+)?選舉區$", "", key)

# presidential sheets name the tickets but not their parties
PRESIDENT_PARTY = {"朱立倫": "中國國民黨", "韓國瑜": "中國國民黨", "侯友宜": "中國國民黨",
                   "蔡英文": "民主進步黨", "賴清德": "民主進步黨",
                   "宋楚瑜": "親民黨", "柯文哲": "台灣民眾黨"}

COUNTY_ALIAS = {"桃園縣": "桃園市", "臺北縣": "新北市"}

# The CEC's spreadsheets write rare characters as Private Use Area code points (its own font).
# Mapped back by matching against the same village in other years' files, or, for candidate names,
# against the CEC's JSON (which spells them as @HEX@ Unicode, e.g. 江@2F97F@淵 = 江聰淵 after NFC).
PUA = {
    "\ue000": "𦰡", "\ue001": "𥕢", "\ue006": "塭", "\ue007": "壳", "\ue008": "磘", "\ue018": "聰", "\ue01a": "硘",
    "\ue01c": "嵵", "\ue01d": "廍", "\ue01f": "獇", "\ue02a": "欍", "\ue34c": "双", "\ue434": "坂", "\ue435": "坔",
    "\ue5c5": "响", "\ue6c0": "凉", "\ue6ff": "峯", "\ue730": "晋", "\ue808": "堃", "\ue82f": "崐", "\ue8d7": "脚",
    "\ue929": "黄", "\ue93a": "厦", "\uea0d": "硦", "\uea47": "菓", "\ueab7": "塩", "\ued74": "槺", "\uee8e": "濓",
    "\ueea9": "磜", "\ueebe": "舘", "\uf073": "壠", "\uf19f": "鷄",
}
_PUA_RE = re.compile("[\ue000-\uf8ff]")


def fix(text):
    return _PUA_RE.sub(lambda m: PUA.get(m.group(0), m.group(0)), text) if text else text


def _county(name):
    m = re.search(r"\((\S{2,3}[縣市])\)", name)
    return COUNTY_ALIAS.get(m.group(1), m.group(1)) if m else None


def _col(header, *keys, exclude=()):
    for j, c in enumerate(header):
        if any(k in c for k in keys) and not any(x in c for x in exclude):
            return j
    raise KeyError(keys)


def _sheets(name, data):
    """(sheet title, rows) for every sheet of a workbook."""
    import io
    if name.endswith(".xls"):
        import xlrd
        for sh in xlrd.open_workbook(file_contents=data).sheets():
            yield sh.name, [sh.row_values(r) for r in range(sh.nrows)]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        for ws in wb.worksheets:
            yield ws.title, [list(r) for r in ws.iter_rows(values_only=True)]


def parse_sheet(rows, president, parties=False):
    rows = list(rows)
    hdr = next(i for i, r in enumerate(rows) if any(clean(c) in ("投開票所別", "投票所別") for c in r[:4]))
    H = [clean(c) for c in rows[hdr]]
    ia = _col(H, "有效票數")
    ic = _col(H, "投票數", exclude=("有效", "無效", "已領"))
    ie = _col(H, "選舉人數")
    cands, cols = [], []
    for j, c in enumerate(rows[hdr + 1]):
        raw = str(c or "").strip()
        m = re.match(r"\(?(\d+)\)?\s*(.*)", raw, re.S)
        if not raw or not m or j >= ia:
            continue
        parts = [p.strip() for p in re.split(r"[\n\r]+", m.group(2)) if p.strip()]
        if not parts and not president:  # 2022 嘉義市 rerun: number, name and party on three rows
            parts = [clean(rows[hdr + 2][j]), clean(rows[hdr + 3][j])]
        parts = [fix(p) for p in parts]
        if parties:  # party-list sheets: the "candidate" is the party
            name = fix(re.sub(r"\s", "", m.group(2)))
            party = name
        elif president:
            name = fix(re.sub(r"\s", "", m.group(2)))[:3]
            party = PRESIDENT_PARTY.get(name, "")
        else:
            name = parts[0] if parts else ""
            party = parts[1] if len(parts) > 1 else ""
        cands.append({"no": int(m.group(1)), "name": name, "party": party})
        cols.append(j)
    stations, district, village = [], None, None
    for r in rows[hdr + 2:]:
        r = list(r) + [None] * 3
        c0, c1, c2 = clean(r[0]), clean(r[1]), clean(r[2])
        if c0 and not c2:
            district = fix(c0)
            continue
        if c2.replace(".0", "").isdigit():
            village = (fix(c1.split("、")[0]) if c1 else None) or village  # stations spanning villages: first one
            stations.append({"district": district, "village": village, "no": norm_station(c2),
                             "E": to_int(r[ie]) or 0, "C": to_int(r[ic]) or 0, "A": to_int(r[ia]) or 0,
                             "v": [to_int(r[j]) or 0 for j in cols]})
    return {"cands": cands, "stations": stations}


@lru_cache(maxsize=None)
def load(election):
    cfg = ELECTIONS[election]
    president = "president" in election
    out = {}
    for z in cfg["zips"]:
        for name, data in zip_members(RAW / z):
            if cfg.get("pick") and cfg["pick"] not in name:
                continue
            if not name.endswith((".xls", ".xlsx")):
                continue
            county = _county(name)
            if not county:
                continue
            if cfg.get("per_sheet"):
                for title, rows in _sheets(name, data):
                    m = re.search(r"第(\d+)選(?:舉)?區", title)  # 2016 sheets: "第01選區"
                    out[f"{county}第{int(m.group(1))}選舉區" if m else f"{county}選舉區"] = parse_sheet(rows, False)
                continue
            rows = rows_xls(data) if name.endswith(".xls") else rows_xlsx(data)
            out[county] = parse_sheet(rows, president, parties=cfg.get("parties", False))
    for county, fname in cfg.get("extra", {}).items():
        data = (RAW / fname).read_bytes()
        out[county] = parse_sheet(rows_xls(data) if fname.endswith(".xls") else rows_xlsx(data), president)
        out[county]["no_times"] = True  # not on the main election night
    return out


@lru_cache(maxsize=None)
def times(election):
    cfg = ELECTIONS[election]
    if "times" not in cfg:
        return {}
    path = RAW / cfg["times"]
    t = read_times(path)
    if t:
        return t
    # 2018 file: 縣市 / 行政區 / 投開票所 / 'MM/DD HH:MM:SS' (no year)
    year = int(cfg["date"][:4])
    rows = rows_xls(path.read_bytes()) if path.suffix == ".xls" else rows_xlsx(path.read_bytes())
    for row in rows:
        county, district, st, ts = (clean(x) for x in row[:4])
        m = re.match(r"(\d+)/(\d+)(\d\d:\d\d:\d\d)$", ts)
        if m and st.replace(".0", "").isdigit():
            t[(COUNTY_ALIAS.get(county, county), district, norm_station(st))] = datetime.strptime(
                f"{year}-{m.group(1)}-{m.group(2)} {m.group(3)}", "%Y-%m-%d %H:%M:%S")
    return t


def leftover_pua():
    """Any Private Use Area characters still in names (should be none)."""
    out = set()
    for e in ELECTIONS:
        for c, r in load(e).items():
            for k in r["cands"]:
                out |= set(_PUA_RE.findall(k["name"]))
            for s in r["stations"]:
                out |= set(_PUA_RE.findall((s["district"] or "") + (s["village"] or "")))
    return out


def check(election):
    """Every station's candidate votes add up to its valid ballots."""
    bad = 0
    for county, race in load(election).items():
        for s in race["stations"]:
            if sum(s["v"]) != s["A"]:
                bad += 1
    return bad


def main():
    for e in ELECTIONS:
        d = load(e)
        n = sum(len(r["stations"]) for r in d.values())
        t = times(e)
        miss = sum(1 for c, r in d.items() for s in r["stations"] if t and (c, s["district"], s["no"]) not in t)
        print(f"{e}: {len(d)} counties, {n} stations, vote-sum mismatches {check(e)}, "
              f"times {len(t)} (stations without a time: {miss if t else 'n/a'})")
    print("unmapped private-use characters:", sorted(hex(ord(c)) for c in leftover_pua()) or "none")
    print("station match rates by (county, district, station no) and by (+ village):")
    for a, b in (("2014-mayors", "2018-mayors"), ("2018-mayors", "2022-mayors"), ("2016-president", "2018-mayors"),
                 ("2020-president", "2022-mayors"), ("2022-mayors", "2024-president")):
        A, B = load(a), load(b)
        k1 = {(c, s["district"], s["no"]) for c, r in A.items() for s in r["stations"]}
        k2 = {(c, s["district"], s["village"], s["no"]) for c, r in A.items() for s in r["stations"]}
        bs = [(c, s) for c, r in B.items() for s in r["stations"]]
        m1 = sum((c, s["district"], s["no"]) in k1 for c, s in bs) / len(bs)
        m2 = sum((c, s["district"], s["village"], s["no"]) in k2 for c, s in bs) / len(bs)
        print(f"  {a} -> {b}: {100 * m1:.1f}%  {100 * m2:.1f}%")


if __name__ == "__main__":
    main()
