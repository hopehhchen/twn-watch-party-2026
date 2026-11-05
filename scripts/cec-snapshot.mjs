// Snapshot final, certified results from the CEC election database (db.cec.gov.tw)
// into one compact, checksummable TSV: data/raw/cec-finals.tsv
//
//   node scripts/cec-snapshot.mjs          # needs network access to db.cec.gov.tw
//   node scripts/build-finals.mjs          # TSV -> data/finals/<election>.json
//
// `snapshotTsv` takes a `get(url) -> JSON` function so the same code can also be
// pasted into a browser console on db.cec.gov.tw (with base = '') when the host
// running Node can't reach the site. Compare the SHA-256 of the output with
// data/raw/cec-finals.tsv.sha256 to confirm both paths agree.
//
// TSV format, one record per line, tab-separated:
//   R  election  office  level(N|C)  area_code  area_name  valid  invalid  ballots_cast  electors  turnout_pct
//   O  cand_no  name  running_mate  party  votes  pct  is_victor(0|1)
// Each O line belongs to the R line above it. Names are CEC's raw strings
// (rare characters appear as @HEX@ codes; build-finals.mjs decodes them).

// theme_id values come from /static/elections/list/ELC_<subject>.json
export const ELECTIONS = {
  '2022-local-mayors': [
    ['C1', 'municipal-mayor', '05cc7b904c7a30cc7c88d5b10898c98e', false], // 111年直轄市長選舉 2022-11-26
    ['C2', 'county-mayor', '63615098f5afa8ec53159c4a86fc01d3', false], //    111年縣市長選舉 2022-11-26
  ],
  '2022-chiayi-city-mayor-rerun': [
    ['C2', 'county-mayor', '1275d73551f2c0caf202e803b1766057', false], //    111年嘉義市長重行選舉 2022-12-18
  ],
  '2024-president': [
    ['P0', 'president', '4d83db17c1707e3defae5dc4d4e9c800', true], //       第16任總統副總統選舉 2024-01-13
  ],
};

export async function snapshotTsv(get, base = 'https://db.cec.gov.tw') {
  const B = `${base}/static/elections/data`;
  const ALL = '00_000_00_000_0000';
  const ak = (r) => `${r.prv_code}_${r.city_code}`;
  const lines = [];
  for (const [key, themes] of Object.entries(ELECTIONS)) {
    for (const [s, office, id, national] of themes) {
      for (const lv of national ? ['N', 'C'] : ['C']) {
        const T = (await get(`${B}/tickets/ELC/${s}/00/${id}/${lv}/${ALL}.json`))[ALL];
        const P = (await get(`${B}/profiles/ELC/${s}/00/${id}/${lv}/${ALL}.json`))[ALL];
        for (const a of [...new Set(T.map(ak))]) {
          const p = P.find((x) => ak(x) === a) || {};
          const rows = T.filter((t) => ak(t) === a);
          lines.push(['R', key, office, lv, a, rows[0].area_name, p.valid_ticket, p.invalid_ticket,
            p.vote_ticket, p.votable_population, p.vote_to_elect].join('\t'));
          // Presidential running mates are separate rows (is_vice === 'Y') with the same votes.
          for (const t of rows.filter((t) => t.is_vice !== 'Y').sort((x, y) => x.cand_no - y.cand_no)) {
            const m = rows.find((v) => v.is_vice === 'Y' && v.cand_no === t.cand_no);
            lines.push(['O', t.cand_no, t.cand_name, m ? m.cand_name : '', t.party_name, t.ticket_num,
              t.ticket_percent, t.is_victor === '*' ? 1 : 0].join('\t'));
          }
        }
      }
    }
  }
  return lines.join('\n') + '\n';
}

if (typeof process !== 'undefined' && import.meta.url === `file://${process.argv[1]}`) {
  const { writeFile } = await import('node:fs/promises');
  const { createHash } = await import('node:crypto');
  const get = async (u) => {
    const r = await fetch(u);
    if (!r.ok) throw new Error(`${r.status} ${u}`);
    return r.json();
  };
  const tsv = await snapshotTsv(get);
  await writeFile('data/raw/cec-finals.tsv', tsv);
  const sha = createHash('sha256').update(tsv).digest('hex');
  await writeFile('data/raw/cec-finals.tsv.sha256', `${sha}  cec-finals.tsv\n`);
  console.log(`wrote data/raw/cec-finals.tsv (${tsv.split('\n').length - 1} lines, sha256 ${sha})`);
}
