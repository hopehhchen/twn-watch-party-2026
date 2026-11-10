#!/usr/bin/env python3
"""Build the site into a folder (default _site/) for GitHub Pages.

  python3 scripts/build_site.py [OUT_DIR]

  index.html   entry page: what the site does, how the model works, how accurate it was
               (site/index-template.html + data/accuracy.json)
  live.html    the results page: needles, turnout and council for every night
               (site/live-template.html; the county map is embedded)
  needle/<night>.json, council/<year>.json, legislature/<year>.json
               the nights' data, loaded by live.html when a night (or the council or legislature view) is opened
  needle.html, council.html
               redirects to live.html, for links to the earlier prototype pages

Templates hold the marker /*__DATA__*/null, replaced by one JSON object. The night files come from
scripts/build_needle_data.py and scripts/build_council_data.py, which need the raw CEC files.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDLE_NIGHTS = ["2018-mayors", "2020-president", "2022-mayors", "2024-president"]
COUNCIL_YEARS = {"2018-mayors": 2018, "2022-mayors": 2022}
LEGIS_YEARS = {"2020-president": 2020, "2024-president": 2024}

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
"""

REDIRECT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>TWN Watch Party</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>location.replace('live.html' + (location.hash || '{hash}'));</script>
<meta http-equiv="refresh" content="0; url=live.html{hash}"></head>
<body><p><a href="live.html{hash}">Moved to live.html</a></p></body></html>
"""


def night_index():
    out = []
    for nid in NEEDLE_NIGHTS:
        d = json.loads((ROOT / "data" / "needle" / f"{nid}.json").read_text())
        out.append({"id": nid, "title": d["title"], "date": d["date"], "src": f"needle/{nid}.json",
                    "council": f"council/{COUNCIL_YEARS[nid]}.json" if nid in COUNCIL_YEARS else None,
                    "legis": f"legislature/{LEGIS_YEARS[nid]}.json" if nid in LEGIS_YEARS else None})
    return out


def render(template, data, out_path):
    tpl = (ROOT / "site" / template).read_text()
    marker = "/*__DATA__*/null"
    assert marker in tpl, template
    body = tpl.replace(marker, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    # templates start with <title>, <meta> and <link>/<style>/<script> tags: they belong in <head>
    split = body.index('<div class="wrap">')
    out_path.write_text(HEAD + body[:split] + "</head>\n<body>\n" + body[split:] + "\n</body>\n</html>\n")
    print(f"{out_path}: {out_path.stat().st_size / 1024:.0f} KB")


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_site")
    out.mkdir(parents=True, exist_ok=True)
    nights = night_index()
    mapd = json.loads((ROOT / "data" / "map" / "taiwan-counties.json").read_text())
    render("live-template.html", {"nights": nights, "map": mapd}, out / "live.html")
    if (ROOT / "site" / "index-template.html").exists():
        render("index-template.html", {"nights": nights, "accuracy": json.loads((ROOT / "data" / "accuracy.json").read_text())},
               out / "index.html")
    for sub, src in (("needle", ROOT / "data" / "needle"), ("council", ROOT / "data" / "council"),
                     ("legislature", ROOT / "data" / "legislature")):
        (out / sub).mkdir(exist_ok=True)
        for f in src.glob("*.json"):
            shutil.copy(f, out / sub / f.name)
    (out / "needle.html").write_text(REDIRECT.replace("{hash}", ""))
    (out / "council.html").write_text(REDIRECT.replace("{hash}", "#2022/council"))
    print(f"{out}: needle/, council/ data and redirects")


if __name__ == "__main__":
    main()
