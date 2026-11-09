import numpy as np
from PIL import Image
def label_crop(a, ys):
    y0 = ys[0] - 6
    c = a[max(0, y0):y0 + 28, 24:40].astype(float).mean(axis=2)
    if c.shape != (28, 16): return None
    c = (c - c.mean()) / (c.std() + 1e-6)
    return c

import pickle
_T = None
def classify_county(a, ys):
    """Best county for a block's vertical label, trying small vertical shifts. Returns (name, r, margin)."""
    global _T
    if _T is None: _T = pickle.load(open('county_tpl.pkl', 'rb'))
    best = {}
    for dy in range(-3, 4):
        c = label_crop(a, (ys[0] + dy,))
        if c is None: continue
        for nm, t in _T.items():
            r = float((c * t).mean())
            if r > best.get(nm, -9): best[nm] = r
    order = sorted(best.items(), key=lambda kv: -kv[1])
    (n1, r1), (n2, r2) = order[0], order[1]
    return n1, r1, r1 - r2
