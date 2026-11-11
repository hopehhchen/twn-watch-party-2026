#!/usr/bin/env python3
"""The 2026 council file before the count: data/council/2026.json (every district, no candidates or points yet).

  python3 scripts/build_2026_council.py

On the night, scripts/live/poll.py fills the same file from the CEC's district pages (candidates, seats,
counts); the page enables its Council view once the mayors' file says council counting has started.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "live"))
from council_live import CouncilLive  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    tmp = ROOT / "data"
    c = CouncilLive(tmp, year=2026)
    for co in c.doc["counties"]:
        for d in co["districts"]:
            d["pts"], d["cands"] = [], []
    path = c.write(datetime.now(timezone(timedelta(hours=8))))
    print(path.relative_to(ROOT), sum(len(x["districts"]) for x in c.doc["counties"]), "districts")
