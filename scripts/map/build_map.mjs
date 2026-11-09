// Builds data/map/taiwan-counties.json (county outlines as SVG paths, insets for 金門/連江/澎湖).
// cd scripts/map && npm install && Q=0.05 node build_map.mjs > ../../data/map/taiwan-counties.json
import fs from 'fs';
import * as topo from 'topojson-client';
import { presimplify, simplify, quantile } from 'topojson-simplify';
import { geoPath } from 'd3-geo';
const t = presimplify(JSON.parse(fs.readFileSync('node_modules/taiwan-atlas/counties-mercator-10t.json')));
const q = +(process.env.Q || 0.5);
const s = simplify(t, quantile(t, q));
const fc = topo.feature(s, s.objects.counties);
const path = geoPath(null).digits(1);
const [[x0, y0], [x1, y1]] = path.bounds({ type: 'GeometryCollection', geometries: [...fc.features.map(f => f.geometry), topo.mesh(s, s.objects.compBorders)] });
const out = { viewBox: [Math.floor(x0) - 4, Math.floor(y0) - 4, Math.ceil(x1 - x0) + 8, Math.ceil(y1 - y0) + 8], counties: {} };
for (const f of fc.features) out.counties[f.properties.COUNTYNAME.replace(/^台/, '臺')] = path(f);
out.insets = path(topo.mesh(s, s.objects.compBorders));
out.source = 'taiwan-atlas 2021.9.20 (MIT), counties-mercator-10t.json, derived from the Ministry of the Interior 直轄市、縣市界線 (data.gov.tw/dataset/7442, Open Government Data License)';
process.stdout.write(JSON.stringify(out));
