#!/usr/bin/env python3
"""華視 (CTS) per-county counts on the 2024 presidential night: clean the OCR reads into a series.

  python3 scripts/clean_cts_county.py

Input: data/raw/cts-county/ocr-reads.csv, one row per county block read off CTS's rotating side panel
(YouTube storyboard frames, 320x180, about one per 10 s; reader in scripts/ocr_cts_county/).
Output: data/nights/2024-president.cts-county.json.

The reads are noisy: the frames are tiny (digits ~5 px tall), and a misread leading digit (1 vs 7,
3 vs 5) changes a value by tens of thousands. Cleaning, per county:
  1. Drop a whole block when any candidate's share of the three differs by more than MAX_SHARE_GAP
     from the median share of the same county's other blocks within WINDOW minutes (a misread leading
     digit shifts it by far more; real share changes over 15 minutes of counting are smaller). The
     CEC's own count is no reference here: its station log times on this night ran 30+ minutes behind
     the channels (新北市 had ~100,000 votes on CTS before the CEC had logged a single station).
  2. Per candidate, keep the longest-by-weight non-decreasing run of the remaining values (counts only
     go up), dropping isolated reads that break it.
  3. Drop counties left with fewer than MIN_BLOCKS blocks.
Spot-checked by eye on 16 random blocks (48 values): 基隆市's 3 blocks were misread (values under
10,000 shown without 萬, which the reader mishandles) and are dropped (too few consistent blocks); of the other 39
values, 1 was clearly wrong (a 萬 digit; dropped by rule 1) and 2 were uncertain in the last digits (≤ 20 votes).
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stations as ST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "cts-county" / "ocr-reads.csv"
OUT = ROOT / "data" / "nights" / "2024-president.cts-county.json"
MAX_SHARE_GAP = 0.02  # vs the median share of the same county's other blocks within WINDOW minutes
WINDOW = 15
MIN_BLOCKS = 5
KEYS = ("lai", "hou", "ko")
NAMES = {"lai": "賴清德", "hou": "侯友宜", "ko": "柯文哲"}


def cec_by_minute():
    """{county: [(datetime, [lai, hou, ko])]} cumulative CEC counts at each station report."""
    races, tm = ST.load("2024-president"), ST.times("2024-president")
    out = {}
    for county, race in races.items():
        idx = {c["name"]: k for k, c in enumerate(race["cands"])}
        ks = [idx[NAMES[k]] for k in KEYS]
        rows = sorted(((tm[(county, s["district"], s["no"])], s) for s in race["stations"]
                      if (county, s["district"], s["no"]) in tm), key=lambda x: x[0])
        acc, seq = [0, 0, 0], []
        for t, s in rows:
            acc = [a + s["v"][k] for a, k in zip(acc, ks)]
            seq.append((t, acc))
        out[county] = seq
    return out


def r_time(t):
    return t.strftime("%H:%M:%S")


def at(seq, t):
    last = [0, 0, 0]
    for tt, v in seq:
        if tt > t:
            break
        last = v
    return last


def monotone(points):
    """Max-weight non-decreasing subsequence of [(t, v)] in time order (weight 1 each)."""
    n = len(points)
    best, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if points[j][1] <= points[i][1] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k]) if n else -1
    keep = []
    while i >= 0:
        keep.append(points[i])
        i = prev[i]
    return keep[::-1]


def main():
    blocks, dropped = {}, {}
    for r in csv.DictReader(RAW.open()):
        county = r["county"]
        t = datetime.fromisoformat("2024-01-13T" + r["taipei"])
        try:
            v = [int(r[k]) for k in KEYS]
        except ValueError:
            dropped.setdefault(county, []).append([r["taipei"], "unreadable"])
            continue
        blocks.setdefault(county, []).append((t, v))
    for county, bl in blocks.items():
        sh = [[x / sum(v) for x in v] for _, v in bl]
        keep = []
        for i, (t, v) in enumerate(bl):
            near = [sh[j] for j, (u, _) in enumerate(bl) if j != i and abs((u - t).total_seconds()) <= WINDOW * 60]
            if len(near) < 2:
                dropped.setdefault(county, []).append([r_time(t), "no neighbours to check against"])
                continue
            ref = [sorted(x[k] for x in near)[len(near) // 2] for k in range(3)]
            gap = max(abs(a - b) for a, b in zip(sh[i], ref))
            if gap > MAX_SHARE_GAP:
                dropped.setdefault(county, []).append([r_time(t), f"share gap {100 * gap:.1f} pts"])
                continue
            keep.append((t, v))
        blocks[county] = keep
    out = {}
    for county, bl in blocks.items():
        bl.sort()
        kept = {}
        for i, k in enumerate(KEYS):
            kept[k] = {t: v for t, v in monotone([(t, v[i]) for t, v in bl])}
        times = sorted(t for t, _ in bl if all(t in kept[k] for k in KEYS))
        if len(times) < MIN_BLOCKS:
            dropped.setdefault(county, []).append(["*", f"only {len(times)} clean blocks; county dropped"])
            continue
        out[county] = [[t.strftime("%H:%M:%S")] + [kept[k][t] for k in KEYS] for t in times]
    final = {c: [sum(s["v"][[x["name"] for x in r["cands"]].index(NAMES[k])] for s in r["stations"]) for k in KEYS]
             for c, r in ST.load("2024-president").items()}
    above = {c: [row for row in rows if any(v > f for v, f in zip(row[1:], final[c]))] for c, rows in out.items()}
    doc = {
        "election": "2024-president", "outlet": "cts", "label": "華視", "race": "county",
        "source": {"kind": "broadcast frames (YouTube storyboard, 320x180), CTS's rotating county side panel",
                   "video_id": "5uAUgdJnb70", "time_semantics": "nominal frame time, Asia/Taipei; ~10 s",
                   "reader": "scripts/ocr_cts_county/ (party-color block detection, county label templates, "
                             "grayscale digit templates); cleaning: scripts/clean_cts_county.py"},
        "series_columns": ["time", "賴清德", "侯友宜", "柯文哲"],
        "counties": out,
        "final": {c: final[c] for c in out},
        "checks": {"dropped": dropped, "above_final": {c: a for c, a in above.items() if a}},
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    for c, rows in out.items():
        print(f"  {c}: {len(rows)} blocks, {rows[0][0]}–{rows[-1][0]}, dropped {len(dropped.get(c, []))}")
    print("not kept:", {c: len(d) for c, d in dropped.items() if c not in out})
    print("above final:", doc["checks"]["above_final"] or "none")


if __name__ == "__main__":
    main()
