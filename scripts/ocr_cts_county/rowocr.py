import numpy as np, cv2, json, pickle
S = 6
X0, X1 = 78, 123

def refine_y(a, y0):
    """Centre of the text band near y0 in the number area (rows with dark ink)."""
    lo, hi = max(0, y0 - 9), min(a.shape[0], y0 + 10)
    g = cv2.cvtColor(np.ascontiguousarray(a[lo:hi, X0:X1]), cv2.COLOR_RGB2GRAY)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (b > 0).sum(axis=1)
    rows = np.where(ink >= 3)[0]
    if not len(rows): return None
    # largest contiguous band
    bands, s = [], rows[0]
    for p, q in zip(rows, rows[1:]):
        if q != p + 1: bands.append((s, p)); s = q
    bands.append((s, rows[-1]))
    s, e = max(bands, key=lambda be: be[1] - be[0])
    if e - s < 4 or e - s > 10: return None
    return lo + (s + e) // 2

def row_img(a, y):
    c = np.ascontiguousarray(a[y - 6:y + 7, X0:X1])
    return cv2.resize(c, None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC)

def binar(c):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return b

def glyphs(b):
    """Connected components -> list of (x0, x1, y0, y1) sorted by x, noise removed."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(b, connectivity=8)
    H = b.shape[0]
    out = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < 25 or h < 8: continue
        if y + h < 0.2 * H or y > 0.85 * H: continue
        out.append([x, x + w, y, y + h])
    out.sort()
    # merge components that overlap heavily in x (pieces of one glyph)
    merged = []
    for g in out:
        if merged and g[0] < merged[-1][1] - 3:
            m = merged[-1]; merged[-1] = [min(m[0], g[0]), max(m[1], g[1]), min(m[2], g[2]), max(m[3], g[3])]
        else:
            merged.append(g)
    return merged

def split_number(b):
    """-> (head glyph boxes, tail glyph boxes) or None. Head = tall digits left of the 萬 mark;
    tail = the 4 smaller digits after it. Without 萬 (under 10,000): all digits are head-sized."""
    gs = glyphs(b)
    if not gs: return None
    hts = [g[3] - g[2] for g in gs]
    Hmax = max(hts)
    # the 萬 mark: a short, squat blob (much shorter than the tallest digit) followed by >= 3 glyphs
    wan = None
    for i, g in enumerate(gs):
        h = g[3] - g[2]; w = g[1] - g[0]
        if h < 0.62 * Hmax and i >= 1 and len(gs) - i - 1 >= 3:
            wan = i; break
    if wan is None:
        return gs, []
    head, tail = gs[:wan], gs[wan + 1:]
    # split merged tail glyphs by expected width
    if tail:
        widths = sorted(t[1] - t[0] for t in tail)
        unit = widths[0] if len(tail) >= 4 else (tail[-1][1] - tail[0][0]) / 4
        nt = []
        for t in tail:
            w = t[1] - t[0]; k = max(1, int(round(w / max(unit, 1))))
            for j in range(k):
                nt.append([t[0] + j * w // k, t[0] + (j + 1) * w // k, t[2], t[3]])
        tail = nt
    return head, tail

def norm_glyph(b, box, size=(12, 18)):
    x0, x1, y0, y1 = box
    g = b[y0:y1, x0:x1].astype(np.float32)
    if g.size == 0: return None
    g = cv2.resize(g, size, interpolation=cv2.INTER_AREA)
    g -= g.mean(); s = g.std()
    return g / s if s > 0 else None

# fixed slots in native pixels within the number area (x from X0); the text is right-aligned at 39
HEAD = [(10.0, 14.2), (14.6, 19.3)]
WAN = (19.8, 23.2)
TAIL = [(24.0 + i * 3.75, 24.0 + (i + 1) * 3.75) for i in range(4)]

def slot(b, x0, x1, dx=0, pad=0.4):
    xa = int(round((x0 - pad) * S)) + dx; xb = int(round((x1 + pad) * S)) + dx
    xa = max(0, xa); xb = min(b.shape[1], xb)
    g = b[:, xa:xb].astype(np.float32)
    rows = np.where(g.sum(axis=1) > 0)[0]
    if len(rows) < 6: return None
    g = g[rows.min():rows.max() + 1]
    g = cv2.resize(g, (12, 18), interpolation=cv2.INTER_AREA)
    g -= g.mean(); s = g.std()
    return g / s if s > 0 else None

def has_wan(b):
    xa, xb = int(WAN[0] * S), int(WAN[1] * S)
    return (b[:, xa:xb] > 0).mean() > 0.05

def ink_in(b, x0, x1):
    return (b[:, int(x0 * S):int(x1 * S)] > 0).mean()

def classify(g, tpl, shifts=None):
    best = []
    for d, ts in tpl.items():
        r = max(float((g * t).mean()) for t in ts)
        best.append((r, d))
    best.sort(reverse=True)
    return best[0][1], best[0][0], best[0][0] - best[1][0]

def read_row(b, tpl_head, tpl_tail):
    """-> (value, min_margin) or (None, reason)."""
    if not has_wan(b): return None, 'no 萬'
    digits, margins = [], []
    heads = [HEAD[1]] if ink_in(b, *HEAD[0]) < 0.04 else HEAD
    for (x0, x1), tpl in [(h, tpl_head) for h in heads] + [(t, tpl_tail) for t in TAIL]:
        best = None
        for dx in (-4, -2, 0, 2, 4):
            g = slot(b, x0, x1, dx)
            if g is None: continue
            d, r, m = classify(g, tpl)
            if best is None or r > best[1]: best = (d, r, m)
        if best is None: return None, 'empty slot'
        digits.append(best[0]); margins.append(best[2])
    return int(''.join(map(str, digits))), min(margins)
