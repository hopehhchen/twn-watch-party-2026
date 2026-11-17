// Crosswalk between dated versions of the village map: for each village of an older version, the village of a
// newer version that contains its centroid. Lets the shift map carry an older election's votes into villages
// that were merged, split or renamed since. Only villages whose key changes are listed.
//   node build_village_crosswalk.mjs <folder with the dated files> > ../../data/map/village-crosswalk.json
import fs from 'fs';
import path from 'path';
import * as topo from 'topojson-client';
import { geoCentroid, geoContains, geoBounds } from 'd3-geo';
const dir = process.argv[2];
const PAIRS = [['20150401', '20181130'], ['20150401', '20191121'], ['20181130', '20191121'], ['20181130', '20221118'],
  ['20191121', '20221118'], ['20191121', '20230928'], ['20221118', '20230928'], ['20221118', '20260407'], ['20230928', '20260407']];
const zh = s => (s || '').replace(/^台/, '臺');
const names = p => [zh(p.COUNTYNAME || p.COUNTY || p.C_Name), p.TOWNNAME || p.TOWN || p.T_Name, p.VILLNAME || p.VILLAGE || p.V_Name];
const cache = {};
function load(ver) {
  if (cache[ver]) return cache[ver];
  const d = JSON.parse(fs.readFileSync(path.join(dir, ver + '.json')));
  const feats = (d.type === 'Topology' ? topo.feature(d, Object.values(d.objects)[0]).features : d.features)
    .map(f => { const [c, t, n] = names(f.properties || {}); return c && t && n && f.geometry ? { key: `${c}|${t}|${n}`, f, b: geoBounds(f), c: geoCentroid(f) } : null; })
    .filter(Boolean);
  return (cache[ver] = feats);
}
const out = { note: 'older village key -> newer village key, where they differ (by containment of the older centroid)', pairs: {} };
for (const [a, b] of PAIRS) {
  const A = load(a), B = load(b), Bkeys = new Set(B.map(x => x.key));
  const grid = new Map(), cell = 0.05, gk = (x, y) => `${Math.floor(x / cell)},${Math.floor(y / cell)}`;
  for (const v of B) for (let x = Math.floor(v.b[0][0] / cell); x <= Math.floor(v.b[1][0] / cell); x++) for (let y = Math.floor(v.b[0][1] / cell); y <= Math.floor(v.b[1][1] / cell); y++) {
    const k = `${x},${y}`; if (!grid.has(k)) grid.set(k, []); grid.get(k).push(v);
  }
  const map = {}; let moved = 0, lost = 0;
  for (const v of A) {
    if (Bkeys.has(v.key)) continue; // same village, same name: nothing to do
    const hit = (grid.get(gk(v.c[0], v.c[1])) || []).find(w => geoContains(w.f, v.c));
    if (hit) { map[v.key] = hit.key; moved++; } else lost++;
  }
  out.pairs[`${a}>${b}`] = map;
  process.stderr.write(`${a} > ${b}: ${moved} renamed/merged villages mapped, ${lost} not found\n`);
}
process.stdout.write(JSON.stringify(out));
