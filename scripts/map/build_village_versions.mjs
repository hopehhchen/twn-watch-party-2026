// Village (村里) centroids for each dated version of the Ministry of the Interior's village boundaries, in the same
// projected space as data/map/taiwan-counties.json (taiwan-atlas's mercatorTw, which puts 澎湖/金門/連江/烏坵 in insets).
// Source: Finjon Kiang's mirror of the MOI 村里界圖 releases, github.com/kiang/taiwan_basecode (cunli/s_topo for
// 2018 on, cunli/geo for 2014 and 2015; MIT, data under the Open Government Data License).
//   git clone --filter=blob:none --no-checkout --depth 1 https://github.com/kiang/taiwan_basecode tb
//   (cd tb && git checkout HEAD -- cunli/s_topo/20181130.json ... cunli/geo/20140501.json ...)
//   node build_village_versions.mjs <folder with the files> > ../../data/map/village-versions.json
import fs from 'fs';
import path from 'path';
import * as topo from 'topojson-client';
import { geoCentroid } from 'd3-geo';
import mercatorTw from 'taiwan-atlas';
const dir = process.argv[2];
const pr = mercatorTw();
const zh = s => (s || '').replace(/^台/, '臺');
const r1 = n => Math.round(n * 10) / 10;
const names = p => [zh(p.COUNTYNAME || p.COUNTY || p.C_Name), p.TOWNNAME || p.TOWN || p.T_Name, p.VILLNAME || p.VILLAGE || p.V_Name];
const out = { source: 'MOI 村里界圖 releases via github.com/kiang/taiwan_basecode (MIT); Open Government Data License v1', versions: {} };
for (const f of fs.readdirSync(dir).filter(f => /^\d{8}\.json$/.test(f)).sort()) {
  const d = JSON.parse(fs.readFileSync(path.join(dir, f)));
  const feats = d.type === 'Topology' ? topo.feature(d, Object.values(d.objects)[0]).features : d.features;
  const v = {}; let skipped = 0;
  for (const ft of feats) {
    const [c, t, n] = names(ft.properties || {});
    if (!c || !t || !n || !ft.geometry) { skipped++; continue; }
    const ll = geoCentroid(ft);
    if (ll[0] < 118 || ll[1] < 21.7) { skipped++; continue; } // 東沙/南沙 (高雄市旗津區): off the map
    const p = pr(ll); if (!p) { skipped++; continue; }
    const key = `${c}|${t}|${n}`;
    if (v[key]) { // a village in several pieces: keep the larger-looking one's centroid (first wins); rare
      continue;
    }
    v[key] = [r1(p[0]), r1(p[1])];
  }
  out.versions[f.slice(0, 8)] = v;
  process.stderr.write(`${f}: ${Object.keys(v).length} villages (${skipped} skipped)\n`);
}
process.stdout.write(JSON.stringify(out));
