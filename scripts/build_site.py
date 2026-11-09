#!/usr/bin/env python3
"""Build the sample page site/index.html from site/template.html and the data in data/.

  python3 scripts/build_site.py

The template contains the marker /*__DATA__*/null; it is replaced by one JSON object with
everything the page needs, so the page is self-contained (no fetches).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NIGHTS = ROOT / "data" / "nights"
FINALS = ROOT / "data" / "finals"

PARTY_COLOR = {
    "民主進步黨": "dpp",
    "中國國民黨": "kmt",
    "台灣民眾黨": "tpp",
    "時代力量": "npp",
}


def tmin(hhmm):
    """'HH:MM' or 'HH:MM:SS' -> minutes since 16:00 (fractional seconds kept)."""
    p = [int(x) for x in hhmm.split(":")]
    return (p[0] - 16) * 60 + p[1] + (p[2] / 60 if len(p) > 2 else 0)


def load(name):
    return json.loads((NIGHTS / name).read_text())


def night_2024():
    fin = json.loads((FINALS / "2024-president.json").read_text())
    nat = next(r for r in fin["races"] if r["level"] == "national")
    cands = [
        {"no": o["no"], "name": o["name"], "mate": o.get("running_mate"), "party": o["party"],
         "tone": PARTY_COLOR.get(o["party"], "ind"), "final": o["votes"]}
        for o in nat["options"]
    ]
    nos = [c["no"] for c in cands]
    cec = load("2024-president.cec.json")["races"][0]
    cec_series = [[tmin(r[0])] + r[2:] for r in cec["series"]]
    cec_stations = [[tmin(r[0]), r[1]] for r in cec["series"]]

    def outlet(key):
        d = load(f"2024-president.{key}.json")
        assert d["options"] == nos
        return [[round(tmin(r[0]), 3)] + r[1:] for r in d["series"]]

    sources = [
        {"id": "cec", "label": "中選會", "en": "Central Election Commission", "cohort": "reliable",
         "series": cec_series,
         "note": "Rebuilt from the CEC's per-polling-station results and report times."},
        {"id": "pts", "label": "公視", "en": "PTS, own count", "cohort": "reliable",
         "series": outlet("pts-own"), "ends": tmin("18:20"),
         "note": "PTS's own count (公廣布點). From 18:20 PTS showed the CEC count instead."},
        {"id": "cts", "label": "華視", "en": "CTS", "cohort": "reliable", "series": outlet("cts"),
         "note": "Read from CTS's election-night stream."},
        {"id": "set", "label": "三立", "en": "SET", "cohort": "field", "series": outlet("set"),
         "note": "Read from SET's election-night stream."},
        {"id": "tvbs", "label": "TVBS", "en": "TVBS", "cohort": "field", "series": outlet("tvbs"),
         "note": "Read from TVBS's election-night stream."},
    ]
    return {
        "id": "2024",
        "title": "2024 presidential election",
        "title_zh": "第16任總統副總統選舉",
        "date": "2024-01-13",
        "race": "Nationwide",
        "start": 0, "end": 240, "featured": tmin("17:50"),
        "stations_total": cec["stations_total"],
        "candidates": cands,
        "sources": sources,
        "cec_stations": cec_stations,
    }


def night_2022():
    fin = json.loads((FINALS / "2022-local-mayors.json").read_text())
    cec = {r["area_name"]: r for r in load("2022-local-mayors.cec.json")["races"]}
    ltn = load("2022-local-mayors.ltn-wayback.json")
    races = []
    for cap in ltn["captures"]:
        f = next(r for r in fin["races"] if r["area_name"] == cap["area_name"])
        c = cec[cap["area_name"]]
        cands = [
            {"no": o["no"], "name": o["name"], "party": o["party"],
             "tone": PARTY_COLOR.get(o["party"], "ind"), "final": o["votes"]}
            for o in f["options"] if str(o["no"]) in cap["rows"]
        ]
        nos = [x["no"] for x in cands]
        idx = [c["options"].index(n) for n in nos]
        curve = [[tmin(r[0]), r[1]] + [r[2 + i] for i in idx] for r in c["series"]]
        t = tmin(cap["taipei"])
        snap = {k: [cap["rows"][str(n)][k] for n in nos] for k in ("cec_as_relayed", "ebc", "ftv", "ttv")}
        races.append({
            "area_name": cap["area_name"],
            "office": "縣長" if f["office"] == "county-mayor" and cap["area_name"].endswith("縣") else "市長",
            "time": t,
            "taipei": cap["taipei"],
            "url": cap["url"],
            "note": cap.get("note"),
            "stations_total": c["stations_total"],
            "candidates": cands,
            "snapshot": snap,
            "cec_curve": curve,
        })
    order = {"屏東縣": 0, "新竹市": 1, "臺南市": 2}
    races.sort(key=lambda r: order.get(r["area_name"], 9))
    return {
        "id": "2022",
        "title": "2022 local elections: mayors",
        "title_zh": "111年直轄市長及縣市長選舉",
        "date": "2022-11-26",
        "sources": [
            {"id": "cec_as_relayed", "label": "中選會", "en": "CEC, as shown by Liberty Times", "cohort": "reliable"},
            {"id": "ebc", "label": "東森", "en": "EBC", "cohort": "field"},
            {"id": "ftv", "label": "民視", "en": "FTV", "cohort": "field"},
            {"id": "ttv", "label": "台視", "en": "TTV", "cohort": "field"},
        ],
        "races": races,
    }


STANDALONE_HEAD = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font-size:14px}img{max-width:100%}[hidden]{display:none!important}</style>
"""


def needle_data():
    """Precomputed by scripts/build_needle_data.py (needs the raw station files and xlrd/openpyxl)."""
    out = []
    for night in ("2018-mayors", "2022-mayors", "2024-president"):
        out.append(json.loads((ROOT / "data" / "needle" / f"{night}.json").read_text()))
    return {"nights": out, "map": json.loads((ROOT / "data" / "map" / "taiwan-counties.json").read_text())}


def render(template, data, name, standalone_dir):
    tpl = (ROOT / "site" / template).read_text()
    marker = "/*__DATA__*/null"
    assert marker in tpl
    out = tpl.replace(marker, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    (ROOT / "site" / name).write_text(out)
    print(f"site/{name}: {len(out) / 1024:.0f} KB")
    if standalone_dir:
        dest = standalone_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        # the template starts with <title>, <meta> and <link>/<style> tags: they belong in <head>
        split = out.index('<div class="wrap">')
        dest.write_text(STANDALONE_HEAD + out[:split] + "</head>\n<body>\n" + out[split:] + "\n</body>\n</html>\n")
        print(f"{dest}: standalone document")


def main():
    """site/index.html and site/needle.html are page bodies (the artifact viewer adds its own <head>).
    With --standalone OUT, also write complete HTML documents next to OUT (for GitHub Pages)."""
    import sys
    sdir = Path(sys.argv[sys.argv.index("--standalone") + 1]).parent if "--standalone" in sys.argv else None
    render("template.html", {"nights": [night_2024(), night_2022()]}, "index.html", sdir)
    render("needle-template.html", needle_data(), "needle.html", sdir)


if __name__ == "__main__":
    main()
