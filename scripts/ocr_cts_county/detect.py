import glob, os, numpy as np
from PIL import Image
def cls(c):
    r, g, b = c
    if b > 120 and r < 60 and g < 100: return 'B'
    if g > 130 and r < 110 and g - b > 40: return 'G'
    if g > 130 and b > 110 and r < 80 and g - b < 40: return 'T'
    return '.'
def blocks(a):
    """Return list of (y_lai, y_hou, y_ko) row centres for presidential blocks (賴 green, 侯 blue, 柯 teal)."""
    col = np.median(a[:, 56:66, :].astype(int), axis=1)
    lab = ''.join(cls(tuple(c)) for c in col)
    runs = []  # (label, start, end)
    i = 0
    while i < len(lab):
        j = i
        while j < len(lab) and lab[j] == lab[i]: j += 1
        if lab[i] != '.' and j - i >= 3: runs.append((lab[i], i, j - 1))
        i = j
    merged = []
    for r in runs:
        if merged and merged[-1][0] == r[0] and r[1] - merged[-1][2] <= 9:
            merged[-1] = (r[0], merged[-1][1], r[2])
        else:
            merged.append(r)
    runs = merged
    out = []
    for k in range(len(runs) - 2):
        (l1, s1, e1), (l2, s2, e2), (l3, s3, e3) = runs[k:k + 3]
        if (l1, l2, l3) == ('G', 'B', 'T') and 10 <= s2 - s1 <= 20 and 10 <= s3 - s2 <= 20:
            out.append(((s1 + e1) // 2, (s2 + e2) // 2, (s3 + e3) // 2))
    return out, lab
if __name__ == '__main__':
    files = sorted(glob.glob('crops/*.png'))
    res = []
    for f in files:
        a = np.asarray(Image.open(f).convert('RGB'))
        b, lab = blocks(a)
        if b: res.append((os.path.basename(f), b))
    print(len(res), 'frames;', sum(len(b) for _, b in res), 'blocks')
    from collections import Counter
    print(Counter(tuple(x[0] for x in b) for _, b in res).most_common(8))
    open('blocks.txt', 'w').write('\n'.join(f + ' ' + ';'.join(','.join(map(str, x)) for x in b) for f, b in res))
