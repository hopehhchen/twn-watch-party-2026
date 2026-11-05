// Build data/finals/<election>.json from the CEC snapshot in data/raw/cec-finals.tsv.
//   node scripts/build-finals.mjs

import { readFile, writeFile, mkdir } from 'node:fs/promises';

const META = {
  '2022-local-mayors': {
    label: '2022 local elections: mayors and county magistrates',
    vote_date: '2022-11-26',
    notes: [
      'Chiayi City did not vote for mayor on 2022-11-26: the vote was postponed after a candidate died and held on 2022-12-18 (see 2022-chiayi-city-mayor-rerun).',
    ],
  },
  '2022-chiayi-city-mayor-rerun': {
    label: '2022 Chiayi City mayor (postponed vote)',
    vote_date: '2022-12-18',
    notes: [],
  },
  '2024-president': {
    label: '2024 presidential election',
    vote_date: '2024-01-13',
    notes: [
      "County-level rows carry no `elected` flag: the CEC marks the national winner as victor in every county, including counties where that ticket placed second or third.",
    ],
  },
};

// CEC writes characters outside its standard font as @HEX@ (a Unicode code point).
// Decode, then NFC-normalize so compatibility ideographs become their unified form.
export function decodeName(raw) {
  return raw.replace(/@([0-9A-Fa-f]{4,6})@/g, (_, h) => String.fromCodePoint(parseInt(h, 16))).normalize('NFC');
}

const num = (s) => (s === '' || s === undefined ? null : Number(s));

export function parseSnapshot(tsv) {
  const elections = {};
  let race = null;
  for (const line of tsv.split('\n')) {
    if (!line) continue;
    const f = line.split('\t');
    if (f[0] === 'R') {
      const [, election, office, level, area_code, area_name, valid, invalid, ballots, electors, turnout] = f;
      race = {
        race_id: `${election}/${office}/${level === 'N' ? 'national' : area_code}`,
        office,
        level: level === 'N' ? 'national' : 'county',
        area_code,
        area_name,
        valid_votes: num(valid),
        invalid_votes: num(invalid),
        ballots_cast: num(ballots),
        electors: num(electors),
        turnout_pct: num(turnout),
        options: [],
      };
      (elections[election] ??= []).push(race);
    } else if (f[0] === 'O') {
      const [, no, name, mate, party, votes, pct, victor] = f;
      const decoded = decodeName(name);
      const isPresCounty = race.office === 'president' && race.level === 'county';
      race.options.push({
        no: Number(no),
        name: decoded,
        ...(decoded !== name ? { name_cec_raw: name } : {}),
        ...(mate ? { running_mate: decodeName(mate) } : {}),
        party,
        votes: Number(votes),
        pct: Number(pct),
        elected: isPresCounty ? null : victor === '1',
      });
    } else {
      throw new Error(`unknown record type: ${line}`);
    }
  }
  return elections;
}

// Basic integrity checks; throws on failure.
export function check(races) {
  for (const r of races) {
    const sum = r.options.reduce((a, o) => a + o.votes, 0);
    if (sum !== r.valid_votes) throw new Error(`${r.race_id}: option votes ${sum} != valid ${r.valid_votes}`);
    if (r.valid_votes + r.invalid_votes !== r.ballots_cast)
      throw new Error(`${r.race_id}: valid + invalid != ballots_cast`);
    const winners = r.options.filter((o) => o.elected === true).length;
    if (r.options.every((o) => o.elected !== null) && winners !== 1)
      throw new Error(`${r.race_id}: expected 1 winner, got ${winners}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const tsv = await readFile('data/raw/cec-finals.tsv', 'utf8');
  const elections = parseSnapshot(tsv);
  await mkdir('data/finals', { recursive: true });
  for (const [key, races] of Object.entries(elections)) {
    check(races);
    const out = {
      election: key,
      ...META[key],
      status: 'final',
      source: {
        publisher: 'Central Election Commission (中央選舉委員會)',
        database: 'https://db.cec.gov.tw/',
        snapshot: 'data/raw/cec-finals.tsv',
      },
      races,
    };
    await writeFile(`data/finals/${key}.json`, JSON.stringify(out, null, 2) + '\n');
    console.log(`${key}: ${races.length} races OK`);
  }
}
