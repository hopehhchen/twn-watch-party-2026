// Builds data/map/villages.json for the shift map: every village's (村里) centroid and every town's (鄉鎮市區)
// centroid and outline, in the same projected space as data/map/taiwan-counties.json (taiwan-atlas mercatorTw,
// with 金門/連江/澎湖 moved into insets).
// cd scripts/map && npm install && node build_villages.mjs > ../../data/map/villages.json
import fs from 'fs';
import * as topo from 'topojson-client';
import { presimplify, simplify, quantile } from 'topojson-simplify';
import { geoPath } from 'd3-geo';
const raw = JSON.parse(fs.readFileSync('node_modules/taiwan-atlas/villages-mercator-10t.json'));
const r1 = n => Math.round(n * 10) / 10;
const zh = s => s.replace(/^台/, '臺');
const full = geoPath(null);
const villages = {};
for (const f of topo.feature(raw, raw.objects.villages).features) {
  const p = f.properties;
  if (!p.VILLNAME) continue; // unnamed polygons (e.g. uninhabited land) carry no results
  const [x, y] = full.centroid(f);
  villages[`${zh(p.COUNTYNAME)}|${p.TOWNNAME}|${p.VILLNAME}`] = [r1(x), r1(y)];
}
// towns from their own file: the villages file's merged towns miss a few (萬丹, 麟洛, 竹田, 長治, 石岡)
const t = presimplify(JSON.parse(fs.readFileSync('node_modules/taiwan-atlas/towns-mercator-10t.json')));
const s = simplify(t, quantile(t, +(process.env.Q || 0.1)));
const path = geoPath(null).digits(1);
const towns = {};
for (const f of topo.feature(s, s.objects.towns).features) {
  const p = f.properties, [x, y] = full.centroid(f);
  towns[`${zh(p.COUNTYNAME)}|${p.TOWNNAME}`] = { c: [r1(x), r1(y)], en: p.TOWNENG, d: path(f) };
}
process.stdout.write(JSON.stringify({ villages, towns,
  source: 'taiwan-atlas 2021.9.20 (MIT), villages-mercator-10t.json and towns-mercator-10t.json, derived from the Ministry of the Interior 村里界圖 and 鄉鎮市區界線 (data.gov.tw/dataset/7438, 7441; Open Government Data License)' }));
