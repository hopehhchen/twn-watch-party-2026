// Outlines for the shift map, one file per village-map version: county shapes, town (鄉鎮市區) lines and village
// (村里) lines, all cut from the same topology so they meet exactly, projected like data/map/taiwan-counties.json
// (taiwan-atlas mercatorTw). Sources must be true topologies (shared borders stored once):
//   2022 on: the MOI releases mirrored in github.com/kiang/taiwan_basecode, cunli/topo/<version>.json;
//   20181130 and 20191121: that mirror's full-size 2018/2019 files have broken coordinates and its simplified ones
//   don't share borders, so those two use taiwan-atlas's 2021 villages-10t.json (the same MOI map, September 2021;
//   it differs from 2019 mainly by Pingtung's 2022 mergers, which came later).
//   node build_outlines.mjs <folder with cunli/topo files> <out folder> 20181130 20191121 20221118 20230928
import fs from 'fs';
import path from 'path';
import * as topo from 'topojson-client';
import { presimplify, simplify, quantile } from 'topojson-simplify';
import { geoPath, geoCentroid } from 'd3-geo';
import mercatorTw from 'taiwan-atlas';
const [dir, outdir, ...vers] = process.argv.slice(2);
const zh = s => (s || '').replace(/^台/, '臺');
const path2 = geoPath(mercatorTw()).digits(2);
for (const v of vers) {
  const ATLAS = v === '20181130' || v === '20191121';
  let t = JSON.parse(fs.readFileSync(ATLAS ? 'node_modules/taiwan-atlas/villages-10t.json' : path.join(dir, v + '.json')));
  if (ATLAS) t.objects = { villages: t.objects.villages };
  const name = Object.keys(t.objects)[0];
  // drop 東沙/南沙 (off the map) before anything else
  t.objects[name].geometries = t.objects[name].geometries.filter(g => {
    const c = geoCentroid(topo.feature(t, g)); return c[0] >= 118 && c[1] >= 21.7;
  });
  if (!ATLAS) { // taiwan-atlas is simplified already; the full MOI topologies keep about 6% of their points
    t = presimplify(t);
    t = simplify(t, quantile(t, +(process.env.Q || 0.06)));
  }
  const G = t.objects[name].geometries, P = g => g.properties || {};
  const county = g => zh(P(g).COUNTYNAME), town = g => `${county(g)}|${P(g).TOWNNAME}`;
  const counties = {};
  for (const c of [...new Set(G.map(county))].filter(Boolean))
    counties[c] = path2(topo.merge(t, G.filter(g => county(g) === c)));
  const towns = path2(topo.mesh(t, t.objects[name], (a, b) => a !== b && town(a) !== town(b) && county(a) === county(b)));
  const villages = path2(topo.mesh(t, t.objects[name], (a, b) => a !== b && town(a) === town(b)));
  const out = { version: v, counties, towns, villages };
  const f = path.join(outdir, `outlines-${v}.json`);
  fs.writeFileSync(f, JSON.stringify(out));
  process.stderr.write(`${v}: ${(fs.statSync(f).size / 1024).toFixed(0)} KB (towns ${(towns.length / 1024).toFixed(0)} KB, villages ${(villages.length / 1024).toFixed(0)} KB)\n`);
}
