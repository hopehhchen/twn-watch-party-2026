#!/usr/bin/env python3
"""Turn per-frame broadcast readings (scripts/ocr_storyboard.py output) into an outlet's
count series for one election night, and compare it with the certified final.

  python3 scripts/build_outlet_series.py <readings.csv> <election> <outlet> <video_id> [--label TEXT]

Writes data/nights/<election>.<outlet>.json.

Cleaning: OCR misreads show up as isolated points that break the trend on BOTH sides
(e.g. 1,013,708 misread as 1,913,708 between 955,000 and 1,060,000). Such points are
removed and listed under `removed_outliers`. A persistent drop is kept and listed under
`decreases`, because a reported count going down is itself a finding.
"""
import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def clean(points):
    """points: [(time, value)] in time order -> (kept, removed)."""
    kept, removed = list(points), []
    changed = True
    while changed:
        changed = False
        for i in range(1, len(kept) - 1):
            (_, a), (t, v), (_, b) = kept[i - 1], kept[i], kept[i + 1]
            if a <= b and (v > b or v < a):
                removed.append({"time": t, "value": v, "between": [a, b]})
                del kept[i]
                changed = True
                break
    # endpoints: drop a first/last point that breaks the trend against its two neighbours
    if len(kept) >= 3 and kept[0][1] > kept[1][1] and kept[1][1] <= kept[2][1]:
        removed.append({"time": kept[0][0], "value": kept[0][1], "between": [None, kept[1][1]]})
        kept.pop(0)
    if len(kept) >= 3 and kept[-1][1] < kept[-2][1] and kept[-3][1] <= kept[-2][1]:
        removed.append({"time": kept[-1][0], "value": kept[-1][1], "between": [kept[-2][1], None]})
        kept.pop()
    return kept, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("election")
    ap.add_argument("outlet")
    ap.add_argument("video_id")
    ap.add_argument("--label", default="")
    ap.add_argument("--start", default="16:00:00")
    ap.add_argument("--end", default="20:00:59")
    a = ap.parse_args()

    # a.csv may list several readings files (one per on-screen layout), comma-separated, each
    # optionally limited to a time window:  file.csv@HH:MM-HH:MM
    merged = {}
    fields = set()
    for spec in a.csv.split(","):
        path, _, win = spec.partition("@")
        lo, hi = (win.split("-") + [""])[:2] if win else ("00:00", "23:59")
        for r in csv.DictReader(open(path)):
            if not (lo <= r["taipei"][:5] <= hi):
                continue
            row = merged.setdefault(r["taipei"], {"taipei": r["taipei"]})
            for k, v in r.items():
                if re.match(r"no_\d+_", k):
                    fields.add(k)
                    c = float(r.get(f"conf_{k}") or 0)
                    if v and c > row.get(f"_c_{k}", -1):
                        row[k], row[f"_c_{k}"] = v, c
                    row.setdefault(k, "")
    fields = sorted(fields)
    nos = {f: int(f.split("_")[1]) for f in fields}
    rows = [merged[t] for t in sorted(merged) if a.start <= t <= a.end]

    finals = json.loads((ROOT / "data" / "finals" / f"{a.election}.json").read_text())
    nat = next(r for r in finals["races"] if r["level"] == "national")
    final = {o["no"]: o["votes"] for o in nat["options"]}

    per, removed, decreases, over = {}, {}, {}, {}
    for f in fields:
        pts = [(r["taipei"], int(r[f])) for r in rows if r[f]]
        kept, rem = clean(pts)
        per[f] = dict(kept)
        removed[nos[f]] = rem
        decreases[nos[f]] = [
            {"from_time": t0, "from": v0, "to_time": t1, "to": v1}
            for (t0, v0), (t1, v1) in zip(kept, kept[1:]) if v1 < v0
        ]
        over[nos[f]] = [{"time": t, "value": v, "final": final[nos[f]]} for t, v in kept if v > final[nos[f]]]

    order = sorted(nos.values())
    by_no = {nos[f]: f for f in fields}
    series = []
    for r in rows:
        vals = [per[by_no[n]].get(r["taipei"]) for n in order]
        if any(v is not None for v in vals):
            series.append([r["taipei"]] + vals)

    out = {
        "election": a.election,
        "outlet": a.outlet,
        "label": a.label,
        "race": "national",
        # layout names (from the readings file names) and the window each was used for
        "layouts": [Path(p.partition("@")[0]).stem + (("@" + p.partition("@")[2]) if "@" in p else "")
                    for p in a.csv.split(",")],
        "source": {
            "kind": "broadcast frames (YouTube storyboard, 320x180, one frame per minute)",
            "video_id": a.video_id,
            "time_semantics": "nominal frame time (stream start + frame offset), Asia/Taipei; accurate to ~10 s",
            "reader": "scripts/ocr_storyboard.py (template matching; leave-one-out tested on hand-labelled frames)",
        },
        "options": order,
        "series_columns": ["time"] + [f"no_{n}" for n in order],
        "series": series,
        "final": [final[n] for n in order],
        "checks": {
            "removed_outliers": {str(k): v for k, v in removed.items() if v},
            "decreases": {str(k): v for k, v in decreases.items() if v},
            "above_final": {str(k): v for k, v in over.items() if v},
        },
    }
    path = ROOT / "data" / "nights" / f"{a.election}.{a.outlet}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    c = out["checks"]
    print(f"{a.outlet}: {len(series)} minutes; removed {sum(len(v) for v in c['removed_outliers'].values())} outliers; "
          f"decreases {sum(len(v) for v in c['decreases'].values())}; above final {sum(len(v) for v in c['above_final'].values())}")
    for k, v in c["removed_outliers"].items():
        print("   removed", k, v[:4])
    for k, v in c["decreases"].items():
        print("   DECREASE", k, v[:4])
    for k, v in c["above_final"].items():
        print("   ABOVE FINAL", k, v[:4])


if __name__ == "__main__":
    main()
