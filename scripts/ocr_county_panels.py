#!/usr/bin/env python3
"""Read per-county presidential tallies from 華視 (CTS) 2024 side panels.

華視 kept a side panel that alternated between legislative races and the presidential count for two
counties at a time (blocks of three rows: 賴清德, 侯友宜, 柯文哲, with the county name written
vertically on the left). The panel's vertical position varies, so blocks are found by the party
icons' colours, then each number is read with the digit templates of ocr_storyboard.py and the county
name is matched against templates of the vertical county labels.

Works on side-panel crops of the storyboard frames: full-frame box (104, 8, 236, 132), saved as PNG
with the frame's name.

  python3 scripts/ocr_county_panels.py detect <crops_dir>            # list blocks found
  python3 scripts/ocr_county_panels.py train  <crops_dir> <labels.json>
  python3 scripts/ocr_county_panels.py read   <crops_dir> <out.csv>
"""
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ocr_storyboard as O  # noqa: E402

HERE = Path(__file__).parent
TPL = HERE / "ocr_templates" / "2024-CTS-county.npz"
LAY = {"light_text": False, "head_pitch": 8.0, "tail_pitch": 5.4, "wan_gap": 7.0, "digits_y_min": 0,
       "tail_y_min": 0, "head_ink_min": 0.12, "allow_no_head": True, "max_shift": 1.0, "min_score": 0.45}
ICON_X = (50, 57)
NUM_X = (84, 123)
LABEL_X = (24, 40)
ROWS = ("lai", "hou", "ko")  # ballot order on screen: 賴 (2), 侯 (3), 柯 (1)


def icon_class(px):
    b, g, r = [int(v) for v in px]
    if b > 100 and r < 70 and g < 90:
        return "B"
    if g > 110 and r < 90 and b > 90 and abs(g - b) < 50:
        return "T"
    if g > 120 and r < 120 and b < 110 and g - b > 40:
        return "G"
    return "."


def find_blocks(img):
    """Blocks of rows (y centres of the 賴, 侯, 柯 rows), top to bottom."""
    H = img.shape[0]
    seq = []
    for y in range(H):
        cls = [icon_class(img[y, x]) for x in range(*ICON_X)]
        c = max("GBT.", key=cls.count)
        seq.append(c if cls.count(c) >= 4 else ".")
    runs, y = [], 0
    while y < H:
        c = seq[y]
        y2 = y
        while y2 + 1 < H and seq[y2 + 1] == c:
            y2 += 1
        if c != "." and y2 - y >= 3:
            runs.append((c, (y + y2) / 2))
        y = y2 + 1
    blocks = []
    for i in range(len(runs) - 2):
        (a, ya), (b, yb), (c, yc) = runs[i:i + 3]
        if (a, b, c) == ("G", "B", "T") and 10 <= yb - ya <= 22 and 10 <= yc - yb <= 22:
            blocks.append((ya, yb, yc))
    return blocks


def name_vec(img, yc):
    g = cv2.cvtColor(img[int(yc - 6):int(yc + 6), 58:82], cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = g - g.mean()
    n = np.linalg.norm(g)
    return (g / n).ravel() if n else g.ravel()


def presidential_blocks(img, refs):
    """Blocks whose three name tags look like 賴清德 / 侯友宜 / 柯文哲 (legislative races also come
    in green-blue-teal rows sometimes)."""
    out = []
    for b in find_blocks(img):
        if b[0] < 7 or b[2] > img.shape[0] - 7:
            continue
        if min(float(name_vec(img, y) @ r) for y, r in zip(b, refs)) > 0.6:
            out.append(b)
    return out


def boxes(img, block):
    H = img.shape[0]
    out = {}
    for name, yc in zip(ROWS, block):
        y0, y1 = int(round(yc - 7)), int(round(yc + 7))
        if y0 < 0 or y1 > H:
            return None
        out[name] = (NUM_X[0], y0, NUM_X[1], y1)
    ya = block[0]
    out["label"] = (LABEL_X[0], max(0, int(ya - 9)), LABEL_X[1], min(H, int(block[2] + 8)))
    return out


def label_vec(img, box):
    x0, y0, x1, y1 = box
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (16, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    g = g - g.mean()
    n = np.linalg.norm(g)
    return (g / n).ravel() if n else g.ravel()


def crops(d):
    for p in sorted(Path(d).glob("*.png")):
        yield p, cv2.imread(str(p))


def detect(d):
    for p, img in crops(d):
        for k, b in enumerate(find_blocks(img)):
            print(p.name[:15], k, [round(v) for v in b])


def train(d, labels_path):
    """labels.json: {"<frame>|<block index>": {"county": "臺南市", "lai": 39682, "hou": 21504, "ko": 20328}}"""
    labels = json.loads(Path(labels_path).read_text())
    refs = np.load(Path(labels_path).with_name("namerefs.npy"))
    samples = {"head": [[] for _ in range(10)], "tail": [[] for _ in range(10)]}
    counties = {}
    for p, img in crops(d):
        bl = presidential_blocks(img, refs)
        for k, b in enumerate(bl):
            lab = labels.get(f"{p.name[:15]}|{k}")
            if not lab:
                continue
            bx = boxes(img, b)
            if bx is None:
                continue
            counties.setdefault(lab["county"], []).append(label_vec(img, bx["label"]))
            for name in ROWS:
                v = lab.get(name)
                if v is None:
                    continue
                x0, y0, x1, y1 = bx[name]
                seg = O.segment(O.binarize(img[y0:y1, x0:x1], LAY["light_text"]), LAY)
                if seg is None:
                    print("no segment", p.name[:15], k, name)
                    continue
                (hb, hr), (tb, tr) = seg
                digits = str(v)
                head, tail = (digits[:-4], digits[-4:]) if len(digits) > 4 else ("", digits)
                if len(hr) != len(head) or len(tr) != len(tail):
                    print("slot mismatch", p.name[:15], k, name, v, len(hr), len(tr))
                    continue
                for (a, b2), ch in zip(hr, head):
                    samples["head"][int(ch)].append(O.norm(O.rows(hb[:, a:b2])))
                for (a, b2), ch in zip(tr, tail):
                    samples["tail"][int(ch)].append(O.norm(O.rows(tb[:, a:b2])))
    tpl = {}
    for key in ("head", "tail"):
        for dgt in range(10):
            s = samples[key][dgt] or samples["tail" if key == "head" else "head"][dgt]
            tpl[f"{key}{dgt}"] = np.mean(s, axis=0) if s else np.zeros(O.SLOT[::-1], np.float32)
        print(key, [len(samples[key][i]) for i in range(10)])
    names = sorted(counties)
    tpl["name_refs"] = refs
    tpl["county_names"] = np.array(names)
    tpl["county_vecs"] = np.stack([np.mean(counties[n], axis=0) for n in names])
    TPL.parent.mkdir(exist_ok=True)
    np.savez(TPL, **tpl)
    print("counties:", {n: len(counties[n]) for n in names})


def load_tpl():
    z = np.load(TPL, allow_pickle=False)
    tpl = {"head": [z[f"head{i}"] for i in range(10)], "tail": [z[f"tail{i}"] for i in range(10)]}
    return tpl, list(z["county_names"]), z["county_vecs"], z["name_refs"]


def read(d, out):
    tpl, names, vecs, refs = load_tpl()
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "block", "county", "county_score", "county_margin", "lai", "hou", "ko", "min_margin"])
        for p, img in crops(d):
            for k, b in enumerate(presidential_blocks(img, refs)):
                bx = boxes(img, b)
                if bx is None:
                    continue
                s = vecs @ label_vec(img, bx["label"])
                order = np.argsort(s)[::-1]
                vals, margins = [], []
                for name in ROWS:
                    v, m = O.read_number(img, bx[name], LAY, tpl)
                    vals.append(v)
                    margins.append(m if v is not None else 0.0)
                w.writerow([p.name[:15], k, names[order[0]], round(float(s[order[0]]), 3),
                            round(float(s[order[0]] - s[order[1]]), 3)] + vals + [round(min(margins), 3)])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "detect":
        detect(sys.argv[2])
    elif cmd == "train":
        train(sys.argv[2], sys.argv[3])
    elif cmd == "read":
        read(sys.argv[2], sys.argv[3])
