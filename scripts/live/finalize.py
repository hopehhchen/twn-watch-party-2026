#!/usr/bin/env python3
"""After election night: turn the night's live files into the 2026 replay.

  python3 scripts/live/finalize.py --src ~/twn-night/live-out      # on 11/29, with the night machine's output

Copies the poller's last mayoral and council files (needle/2026-mayors.json, council/2026.json under --src) into
data/needle/ and data/council/, marked as no longer live, so the page shows 2026 like the past nights: a replay with
play and the slider, starting from the first results. Checks first that the files are whole and that the count
reached its end (every race decided, or --force). Then rebuild the site (python3 scripts/build_site.py _site),
check it, and push: Cloudflare rebuilds from the repository.

scripts/build_2026_night.py refuses to overwrite a finalized file, so the pre-count file can't come back by accident.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="the night's output folder (holds needle/ and council/)")
    ap.add_argument("--force", action="store_true", help="finalize even if some race isn't decided yet")
    a = ap.parse_args()
    src = Path(a.src).expanduser()
    needle = json.loads((src / "needle" / "2026-mayors.json").read_text(encoding="utf-8"))
    council = json.loads((src / "council" / "2026.json").read_text(encoding="utf-8"))

    races = needle["races"]
    if len(races) < 22 or any(not r["pts"] for r in races):
        sys.exit(f"{sum(1 for r in races if r['pts'])} of {len(races)} races have points; is this the night's folder?")
    dist = needle.get("feed") == "district"  # town totals: the page reads the district-feed columns

    def decided(r):  # as the page judges it: certain_district (14), or certain3 for the district feed (36) in three-way races
        p = r["pts"][-1]
        col = (36 if dist else 29) if r.get("mode") == "three" else (14 if dist else 7)
        return bool(p[col]) if len(p) > col else False

    open_ = [r["area"] for r in races if not decided(r)]
    if open_ and not a.force:
        sys.exit(f"not decided yet: {', '.join(open_)}. Wait for the count to finish, or use --force.")

    last = max(r["pts"][-1][0] for r in races)
    for doc in (needle, council):
        doc["live"] = False
        doc["end"] = max(doc.get("end") or 0, last)
        doc.pop("council_live", None)
    needle["note"] = ("Final snapshot of the count as published on election night (" + str(needle.get("updated")) +
                      "): the CEC's town totals, read every minute. Certified results may differ slightly.")

    for doc, path in ((needle, ROOT / "data" / "needle" / "2026-mayors.json"), (council, ROOT / "data" / "council" / "2026.json")):
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: written ({path.stat().st_size / 1024:.0f} KB)")
    decided = sum(1 for r in races if decided(r))
    cd = sum(1 for c in council["counties"] for d in c["districts"] if d["pts"])
    ct = sum(len(c["districts"]) for c in council["counties"])
    print(f"mayors: {decided} of 22 decided; councils: {cd} of {ct} districts with results; last point at minute {last}")
    print("Next: python3 scripts/build_site.py _site, check the 2026 replay locally, then commit and push.")


if __name__ == "__main__":
    main()
