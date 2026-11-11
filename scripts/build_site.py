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
  favicon.svg, favicon.ico, favicon-32.png, apple-touch-icon.png, icon-512.png
               tab and home-screen icons (the vote stamp), from site/icons/
  og-image.png the preview picture for links shared on social sites (Open Graph / Twitter Card tags in both
               templates); drawn from site/og-src/og-image.html, rendered at 1200x630 with Playwright

Templates hold the marker /*__DATA__*/null, replaced by one JSON object. The night files come from
scripts/build_needle_data.py and scripts/build_council_data.py, which need the raw CEC files.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDLE_NIGHTS = ["2018-mayors", "2020-president", "2022-mayors", "2024-president", "2026-mayors"]  # 2026: before the count (scripts/build_2026_night.py)
COUNCIL_YEARS = {"2018-mayors": 2018, "2022-mayors": 2022, "2026-mayors": 2026}  # 2026: filled live on the night
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
                    "legis": f"legislature/{LEGIS_YEARS[nid]}.json" if nid in LEGIS_YEARS else None,
                    "live": bool(d.get("live"))})
    return out


# Entry-page hero replay (mock): real races replayed in about ten seconds each. One won by each side, all
# with a needle that moved: 2022 屏東 swung both ways in its first hour, 2018 嘉義市 was decided at 23:32,
# 2018 臺北 not until 02:36.
HERO_RACES = [("2022-mayors", "屏東縣"), ("2018-mayors", "嘉義市"), ("2018-mayors", "臺北市")]


def hero_data(names):
    races = []
    for nid, area in HERO_RACES:
        r = next(x for x in json.loads((ROOT / "data" / "needle" / f"{nid}.json").read_text())["races"] if x["area"] == area)
        pts = [[x[0], round(x[4], 3), x[2], x[3], x[1], int(bool(x[7]))] for x in r["pts"]]
        blue_won = r["blue"]["final"] > r["other"]["final"]
        pw = [q[1] if blue_won else 1 - q[1] for q in pts]
        below = [k for k, v in enumerate(pw) if v < 0.9]
        t90 = pts[below[-1] + 1][0] if below else pts[0][0]
        decided = next(q[0] for q in pts if q[5])
        side = lambda c: {"name": c["name"], "en": names.get(c["name"]), "tone": c["tone"]}
        races.append({"year": nid[:4], "area": area, "stations": r["stations"], "blue": side(r["blue"]), "other": side(r["other"]),
                      "winner": side(r["blue"] if blue_won else r["other"]), "t90": t90, "decided": decided,
                      "start": max(0, pts[0][0] - 12), "end": decided + 4, "pts": pts})
    return {"ms": 9000, "hold": 3200, "races": races}


def render(template, data, out_path):
    tpl = (ROOT / "site" / template).read_text()
    marker = "/*__DATA__*/null"
    assert marker in tpl, template
    body = tpl.replace(marker, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    # templates start with <title>, <meta> and <link>/<style>/<script> tags: they belong in <head>
    split = body.index('<div class="wrap"')
    out_path.write_text(HEAD + body[:split] + "</head>\n<body>\n" + body[split:] + "\n</body>\n</html>\n")
    print(f"{out_path}: {out_path.stat().st_size / 1024:.0f} KB")


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_site")
    out.mkdir(parents=True, exist_ok=True)
    nights = night_index()
    mapd = json.loads((ROOT / "data" / "map" / "taiwan-counties.json").read_text())
    names = {n["zh"]: n["en"] for n in json.loads((ROOT / "data" / "names-en.json").read_text())["names"]}
    render("live-template.html", {"nights": nights, "map": mapd, "names": names}, out / "live.html")
    if (ROOT / "site" / "index-template.html").exists():
        render("index-template.html", {"nights": nights, "accuracy": json.loads((ROOT / "data" / "accuracy.json").read_text())},
               out / "index.html")
        # mock: the entry page with the hero replay (not linked from anywhere; for review)
        idx = (out / "index.html").read_text()
        frag = (ROOT / "site" / "hero-replay.html").read_text()
        frag = frag.replace("<script>", "<script>window.HERO = " + json.dumps(hero_data(names), ensure_ascii=False, separators=(",", ":")) + ";\n", 1)
        i = idx.index('<section class="hero">')
        j = idx.index("</section>", i)
        mock = idx[:i] + '<section class="hero rp">' + idx[i + len('<section class="hero">'):j] + frag + idx[j:]
        mock = mock.replace("<head>", '<head>\n<meta name="robots" content="noindex">', 1)
        (out / "mock-hero.html").write_text(mock)
        print(f"{out / 'mock-hero.html'}: {len(mock) / 1024:.0f} KB")
    for sub, src in (("needle", ROOT / "data" / "needle"), ("council", ROOT / "data" / "council"),
                     ("legislature", ROOT / "data" / "legislature")):
        (out / sub).mkdir(exist_ok=True)
        for f in src.glob("*.json"):
            shutil.copy(f, out / sub / f.name)
    (out / "night").mkdir(exist_ok=True)
    for f in (ROOT / "site" / "night").glob("*"):  # election-night setup scripts for the machine that reads the CEC
        shutil.copy(f, out / "night" / f.name)
    for f in (ROOT / "site" / "icons").glob("*"):  # tab icons (the vote stamp): favicon.svg/.ico/-32.png, apple-touch-icon.png
        shutil.copy(f, out / f.name)
    (out / "needle.html").write_text(REDIRECT.replace("{hash}", ""))
    (out / "council.html").write_text(REDIRECT.replace("{hash}", "#2022/council"))
    print(f"{out}: needle/, council/ data and redirects")


if __name__ == "__main__":
    main()
