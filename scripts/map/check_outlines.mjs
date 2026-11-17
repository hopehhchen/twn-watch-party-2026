// Checks the outline sources for holes: every interior ring of a merged county must lie inside another county
// (嘉義市 inside 嘉義縣 is real); anything else is a gap in the map. Also reports polygons without a county or town.
//   node check_outlines.mjs <folder with cunli/topo files> 20221118 20230928 ...
import fs from 'fs';
import path from 'path';
import * as topo from 'topojson-client';
import { geoContains, geoCentroid, geoArea } from 'd3-geo';
const [dir, ...vers] = process.argv.slice(2);
const zh = s => (s || '').replace(/^台/, '臺');
for (const v of vers) {
  const t = JSON.parse(fs.readFileSync(path.join(dir, v + '.json'))), name = Object.keys(t.objects)[0];
  const G = t.objects[name].geometries.filter(g => { const c = geoCentroid(topo.feature(t, g)); return c[0] >= 118 && c[1] >= 21.7; });
  const noName = G.filter(g => !g.properties || !g.properties.COUNTYNAME || !g.properties.TOWNNAME).length;
  const counties = [...new Set(G.map(g => zh(g.properties.COUNTYNAME)))];
  const merged = Object.fromEntries(counties.map(c => [c, topo.merge(t, G.filter(g => zh(g.properties.COUNTYNAME) === c))]));
  const holes = [];
  for (const [c, mp] of Object.entries(merged)) for (const poly of mp.coordinates) for (const ring of poly.slice(1)) {
    const hole = { type: 'Polygon', coordinates: [ring.slice().reverse()] };
    const pt = geoCentroid(hole), area = geoArea(hole) * 6371 ** 2; // km²
    if (area > 1000) continue; // a reversed (outer) ring, not a hole
    const inOther = Object.entries(merged).some(([o, g]) => o !== c && geoContains(g, pt));
    if (!inOther) holes.push(`${c} near ${pt.map(x => x.toFixed(4)).join(',')} (${(area * 1e6).toFixed(0)} m²)`);
  }
  console.log(`${v}: ${G.length} polygons, ${noName} without county/town, ${holes.length} holes` + (holes.length ? '\n  ' + holes.slice(0, 15).join('\n  ') : ''));
}
