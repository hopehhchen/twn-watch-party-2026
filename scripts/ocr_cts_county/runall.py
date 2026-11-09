import json, numpy as np, cv2, csv
from PIL import Image
import evalgray as E
from rowocr import refine_y, row_img, binar, HEAD, TAIL, has_wan
th, tt = E.build(-1)
B = [l.split() for l in open('blocks_county.txt')]
out = []
for f, ys, nm, r, m in B:
    if nm == 'None' or float(r) < 0.85 or float(m) < 0.015: continue
    a = np.asarray(Image.open('crops/' + f).convert('RGB'))
    vals = []
    for y in map(int, ys.split(',')):
        yy = refine_y(a, y)
        if yy is None: vals.append((None, 0)); continue
        c = row_img(a, yy); b = binar(c)
        if not has_wan(b): vals.append((None, 0)); continue
        vals.append(E.read(b, E.prep(c), th, tt))
    t = f[9:15]; tpe = f"{(int(t[:2]) + 8) % 24:02d}:{t[2:4]}:{t[4:6]}"
    out.append([f, tpe, nm] + [v for v, _ in vals] + [round(mm, 3) for _, mm in vals])
with open('cts_county_raw.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['frame', 'taipei', 'county', 'lai', 'hou', 'ko', 'm_lai', 'm_hou', 'm_ko']); w.writerows(out)
print(len(out), 'blocks read')
