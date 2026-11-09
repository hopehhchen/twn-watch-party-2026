import json, numpy as np, cv2, sys
from PIL import Image
from rowocr import *
from labels import LABELS, LABELS2
rows = json.load(open('label_rows.json'))
rows2 = json.load(open('label_rows2.json'))
ALL = [(i, r) for i, r in enumerate(rows) if i in LABELS] + [(100 + i, r) for i, r in enumerate(rows2) if 100 + i in LABELS2]
LAB = {**LABELS, **LABELS2}
MODE = sys.argv[1] if len(sys.argv) > 1 else 'gray'
def prep(c):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = g.max() - g  # ink bright
    return g
data = []
for i, (f, y, nm) in ALL:
    a = np.asarray(Image.open('crops/' + f).convert('RGB')); yy = refine_y(a, y)
    if yy is None: continue
    c = row_img(a, yy)
    data.append((i, binar(c), prep(c), str(LAB[i])))
def gslot(g, b, x0, x1, dx=0, pad=0.4):
    xa = max(0, int(round((x0 - pad) * S)) + dx); xb = min(g.shape[1], int(round((x1 + pad) * S)) + dx)
    rows_ = np.where((b[:, xa:xb] > 0).sum(axis=1) > 0)[0]
    if len(rows_) < 6: return None
    h = g[rows_.min():rows_.max() + 1, xa:xb]
    h = cv2.resize(h, (12, 18), interpolation=cv2.INTER_AREA); h = h - h.mean(); s = h.std()
    return h / s if s > 0 else None
def build(excl):
    th, tt = {}, {}
    for i, b, g, s in data:
        if i == excl: continue
        head, tail = s[:-4], s[-4:]
        for (x0, x1), ch in zip(HEAD[-len(head):], head):
            t = gslot(g, b, x0, x1)
            if t is not None: th.setdefault(int(ch), []).append(t)
        for (x0, x1), ch in zip(TAIL, tail):
            t = gslot(g, b, x0, x1)
            if t is not None: tt.setdefault(int(ch), []).append(t)
    return th, tt
def read(b, g, th, tt):
    heads = [HEAD[1]] if ink_in(b, *HEAD[0]) < 0.04 else HEAD
    if len(heads) == 2 and ink_in(b, 5.6, 9.6) >= 0.04: heads = [(5.6, 9.8)] + heads  # 100萬 and up
    ds, ms = [], []
    for (x0, x1), tpl in [(h, th) for h in heads] + [(t, tt) for t in TAIL]:
        best = None
        for dx in (-4, -2, 0, 2, 4):
            t = gslot(g, b, x0, x1, dx)
            if t is None: continue
            sc = sorted(((max(float((t * u).mean()) for u in us), d) for d, us in tpl.items()), reverse=True)
            if best is None or sc[0][0] > best[1]: best = (sc[0][1], sc[0][0], sc[0][0] - sc[1][0])
        if best is None: return None, 0
        ds.append(best[0]); ms.append(best[2])
    return int(''.join(map(str, ds))), min(ms)
ok = 0; errs = []; good_m = []
for i, b, g, s in data:
    th, tt = build(i); v, m = read(b, g, th, tt)
    if str(v) == s: ok += 1; good_m.append(m)
    else: errs.append((i, s, v, round(m, 3)))
print(MODE, 'LOO exact', ok, '/', len(data)); print(errs)
print('margins of correct reads: ', sorted(round(x, 3) for x in good_m)[:12])
