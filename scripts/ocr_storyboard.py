#!/usr/bin/env python3
"""Read candidate tallies from TV broadcast frames (YouTube storyboard frames, 320x180).

Broadcasters show tallies as  <head>萬<tail>  (e.g. 475萬7697 = 4,757,697) in a fixed font.
Tesseract is unreliable at this resolution, so this reads digits by template matching:

  1. crop each number box (scripts/ocr_layouts.json, native 320x180 pixels), upscale, binarize;
  2. find the 萬 mark (a small blob between the large head digits and the small tail digits);
  3. split the head into fixed-pitch slots and the tail into 4 equal slots;
  4. classify each slot against per-channel digit templates built from hand-labelled frames.

Usage:
  python3 scripts/ocr_storyboard.py train <frames_dir> <layout>          # build templates from labels
  python3 scripts/ocr_storyboard.py read  <frames_dir> <layout> <out.csv>

Each value comes with a confidence (the smallest best-vs-second-best margin over its digits);
reads below `min_margin`, or that fail the shape checks, are left empty.

Frames are named <UTC YYYYmmddTHHMMSS>_<sheet>_<pos>.jpg (nominal time = stream start +
frame index x interval). Requires: opencv-python, numpy.
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
LAYOUTS = json.loads((HERE / "ocr_layouts.json").read_text())
TEMPLATES = HERE / "ocr_templates"
TPE = timezone(timedelta(hours=8))
SCALE = 6
SLOT = (16, 24)  # normalized glyph size (w, h)


lay_strip_borders = [False]


def binarize(crop, light_text, strip_borders=False):
    lay_strip_borders[0] = strip_borders
    c = cv2.resize(crop, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
    mode = cv2.THRESH_BINARY if light_text else cv2.THRESH_BINARY_INV
    _, b = cv2.threshold(g, 0, 255, mode + cv2.THRESH_OTSU)
    if not lay_strip_borders[0]:
        return b  # text = 255
    # erase box borders: near the crop edges, rows/columns that are almost entirely "ink" are
    # frame lines, not digits (only near the edges, so a digit's own strokes are never touched)
    H, W = b.shape
    rows_full = (b > 0).mean(axis=1) > 0.7
    cols_full = (b > 0).mean(axis=0) > 0.9
    edge_r = np.zeros(H, bool)
    edge_r[: int(0.2 * H)] = True
    edge_r[int(0.8 * H):] = True
    edge_c = np.zeros(W, bool)
    edge_c[: int(0.06 * W)] = True
    edge_c[int(0.94 * W):] = True
    b[rows_full & edge_r, :] = 0
    b[:, cols_full & edge_c] = 0
    return b  # text = 255


def segment(b, lay):
    """Return (head_slots, tail_slots) as lists of binary glyph images, or None.

    Anchors on the rightmost ink column (numbers are right-aligned): the tail is the 4 slots
    of `tail_pitch` ending there, then a `wan_gap` for the 萬 mark, then up to 3 head slots of
    `head_pitch` going left, kept while they contain ink. Works when digits touch.
    """
    y0 = int(lay.get("digits_y_min", 0) * SCALE)
    band = b[y0:, :]
    ty0 = int(lay.get("tail_y_min", lay.get("digits_y_min", 0)) * SCALE)
    tband = b[ty0:, :]  # rows holding the (smaller) tail digits only
    cols = (tband > 0).sum(axis=0)
    ink = np.nonzero(cols > 0.2 * tband.shape[0])[0]
    if len(ink) == 0:
        return None
    R = int(ink.max()) + 1
    tp, hp, gap = lay["tail_pitch"] * SCALE, lay["head_pitch"] * SCALE, lay["wan_gap"] * SCALE
    tail_x = [int(round(R - 4 * tp + i * tp)) for i in range(5)]
    if tail_x[0] < 0:
        return None
    head_right = R - 4 * tp - gap
    head = []
    for k in range(1, 4):
        x0 = int(round(head_right - k * hp))
        x1 = int(round(head_right - (k - 1) * hp))
        if x0 < -0.3 * hp:
            break
        slot = band[:, max(0, x0):x1]
        if slot.size == 0 or (slot > 0).mean() < lay.get("head_ink_min", 0.08):
            break
        head.insert(0, slot)
    if not head:
        # numbers below 10,000 have no 萬 and 1-4 digits; only accept that reading when there
        # is no ink at all left of the tail area (otherwise the head was just missed)
        if not lay.get("allow_no_head"):
            return None
        left = band[:, : max(0, int(round(R - 4 * tp - 0.5 * tp)))]
        if (left > 0).sum() > 0.01 * max(1, left.size):
            return None
        L = int(ink.min())
        n = int(min(4, max(1, round((R - L) / tp))))
        return (band, []), (tband, [(tail_x[i], tail_x[i + 1]) for i in range(4 - n, 4)])

    head_ranges = []
    for k in range(len(head), 0, -1):
        head_ranges.append((int(round(head_right - k * hp)), int(round(head_right - (k - 1) * hp))))
    tail_ranges = [(tail_x[i], tail_x[i + 1]) for i in range(4)]
    return (band, head_ranges), (tband, tail_ranges)


def rows(g):
    r = np.nonzero((g > 0).sum(axis=1))[0]
    return g[r.min(): r.max() + 1] if len(r) else g


def classify_slot(band, x0, x1, tpl, max_shift):
    """Best digit for a slot, letting the window slide +/- max_shift px to absorb pitch drift."""
    best = None
    for dx in range(-max_shift, max_shift + 1, 2):
        a, b = max(0, x0 + dx), min(band.shape[1], x1 + dx)
        if b - a < (x1 - x0) * 0.6:
            continue
        r = classify(rows(band[:, a:b]), tpl)
        if best is None or r[2] > best[2]:
            best = r
    return best


def norm(g):
    if g.size == 0:
        return np.zeros(SLOT[::-1], np.float32)
    ys, xs = np.nonzero(g)
    if len(xs):
        g = g[:, max(0, xs.min() - 1): xs.max() + 2]  # trim side margins (narrow '1')
    return cv2.resize(g, SLOT, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def classify(g, tpl):
    v = norm(g).ravel()
    v = v - v.mean()
    scores = []
    for d in range(10):
        t = tpl[d].ravel() - tpl[d].mean()
        den = np.linalg.norm(v) * np.linalg.norm(t)
        scores.append(float(v @ t / den) if den else -1.0)
    order = np.argsort(scores)[::-1]
    return int(order[0]), scores[order[0]] - scores[order[1]], scores[order[0]]


def read_number(img, box, lay, tpl):
    x0, y0, x1, y1 = box
    seg = segment(binarize(img[y0:y1, x0:x1], lay["light_text"], lay.get("strip_borders", False)), lay)
    if seg is None:
        return None, 0.0
    shift = int(lay.get("max_shift", 1.5) * SCALE)
    digits, margins = [], []
    for (band, ranges), key in zip(seg, ("head", "tail")):
        for a, b in ranges:
            d, m, s = classify_slot(band, a, b, tpl[key], shift)
            if s < lay.get("min_score", 0.5):
                return None, 0.0
            digits.append(str(d))
            margins.append(m)
    if digits[0] == "0":
        return None, 0.0
    return int("".join(digits)), float(min(margins))


def assign(img, lay):
    """Map candidate field -> box. Boxes are positional; with "colors", a box belongs to the
    candidate whose hue range contains the box's median background hue (for broadcasters that
    reorder candidates by rank)."""
    if "colors" not in lay:
        return dict(lay["boxes"])
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    out = {}
    dy0, dy1 = lay.get("color_probe", [0, None])  # rows to sample, relative to the box top
    for box in lay["boxes"].values():
        x0, y0, x1, y1 = box
        h = hsv[y0 + dy0: (y1 if dy1 is None else y0 + dy1), x0:x1]
        m = h[:, :, 1] > 80
        if m.sum() < 20:
            continue
        hue = float(np.median(h[:, :, 0][m]))
        for field, (lo, hi) in lay["colors"].items():
            if lo <= hue <= hi and field not in out:
                out[field] = box
    return out


def frames(frames_dir):
    for p in sorted(Path(frames_dir).glob("*.jpg")):
        utc = datetime.strptime(p.name[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        yield p, utc


def train(frames_dir, layout):
    lay = LAYOUTS[layout]
    acc = {"head": [[] for _ in range(10)], "tail": [[] for _ in range(10)]}
    for prefix, labels in lay["labels"].items():
        p = next(Path(frames_dir).glob(f"{prefix}*.jpg"))
        img = cv2.imread(str(p))
        boxes = assign(img, lay)
        for field, value in labels.items():
            x0, y0, x1, y1 = boxes[field]
            seg = segment(binarize(img[y0:y1, x0:x1], lay["light_text"], lay.get("strip_borders", False)), lay)
            if seg is None:
                raise SystemExit(f"cannot segment {p.name} {field}")
            (hb, hr), (tb, tr) = seg
            s = str(value)
            hs, ts = s[:-4], s[-4:]
            if len(hr) != len(hs) or len(tr) != len(ts):
                raise SystemExit(f"{p.name} {field}: {len(hr)}+{len(tr)} slots for {value}")
            for (a, b), ch in zip(hr, hs):
                acc["head"][int(ch)].append(norm(rows(hb[:, max(0, a):b])))
            for (a, b), ch in zip(tr, ts):
                acc["tail"][int(ch)].append(norm(rows(tb[:, a:b])))
    tpl = {}
    for key, other in (("head", "tail"), ("tail", "head")):
        rows_ = []
        for d in range(10):
            ex = acc[key][d] or acc[other][d]  # glyph shapes match across sizes after normalizing
            if not ex:
                raise SystemExit(f"{layout}: no examples at all for digit {d}")
            rows_.append(np.mean(ex, axis=0))
        tpl[key] = np.stack(rows_)
    TEMPLATES.mkdir(exist_ok=True)
    np.savez(TEMPLATES / f"{layout}.npz", **tpl)
    counts = {k: [len(v) for v in acc[k]] for k in acc}
    print(f"{layout}: templates saved; examples per digit {counts}")


def read(frames_dir, layout, out_path):
    lay = LAYOUTS[layout]
    z = np.load(TEMPLATES / f"{layout}.npz")
    tpl = {"head": z["head"], "tail": z["tail"]}
    names = lay["fields"]
    n = 0
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "utc", "taipei"] + names + [f"conf_{f}" for f in names])
        for p, utc in frames(frames_dir):
            img = cv2.imread(str(p))
            boxes = assign(img, lay)
            vals, confs = [], []
            for f in names:
                v, m = read_number(img, boxes[f], lay, tpl) if f in boxes else (None, 0.0)
                ok = v is not None and m >= lay.get("min_margin", 0.05)
                vals.append(v if ok else "")
                confs.append(f"{m:.3f}")
            w.writerow([p.name, utc.strftime("%H:%M:%S"), utc.astimezone(TPE).strftime("%H:%M:%S")] + vals + confs)
            n += 1
    print(f"{layout}: {n} frames -> {out_path}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "train":
        train(sys.argv[2], sys.argv[3])
    elif cmd == "read":
        read(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
