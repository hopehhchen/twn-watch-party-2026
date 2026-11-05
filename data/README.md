# Data

## `finals/` — certified final results

The yardstick for the "reported more than the final" callout. One file per election:

| File | Election | Races |
|---|---|---|
| `2022-local-mayors.json` | 2022-11-26 mayors and county magistrates | 21 (6 municipalities + 15 counties/cities) |
| `2022-chiayi-city-mayor-rerun.json` | 2022-12-18 Chiayi City mayor (postponed vote) | 1 |
| `2024-president.json` | 2024-01-13 presidential election | 1 national + 22 counties |
| — | 2025 recall votes | **missing**, see below |

Each race has:

```jsonc
{
  "race_id": "2022-local-mayors/municipal-mayor/63_000",
  "office": "municipal-mayor",        // municipal-mayor | county-mayor | president
  "level": "county",                  // national | county
  "area_code": "63_000",              // CEC prv_code + city_code
  "area_name": "臺北市",
  "valid_votes": 1360951, "invalid_votes": 11228, "ballots_cast": 1372179,
  "electors": 2026769, "turnout_pct": 67.7,
  "options": [
    { "no": 6, "name": "蔣萬安", "party": "中國國民黨", "votes": 575590, "pct": 42.29, "elected": true }
  ]
}
```

Races are matched to live sources by **ballot number (`no`)**, not by name: at least one aggregator (Liberty Times, 2022) attached minor candidates' counts to the wrong names.

Notes:
- Presidential options also carry `running_mate`.
- For presidential **county** rows, `elected` is `null`: the CEC flags the national winner as victor in every county, even where that ticket lost the county.
- Names are decoded from CEC's `@HEX@` escapes for rare characters (e.g. `江@2F97F@淵` → `江聰淵`); the raw form is kept as `name_cec_raw`.
- Chiayi City had no mayoral vote on 2022-11-26, so it doesn't belong in a replay of that night.

### Checks run by `build-finals.mjs`
- Options sum to `valid_votes` in every race.
- `valid_votes + invalid_votes == ballots_cast`.
- Exactly one winner per race (where `elected` applies).

Also confirmed by hand: the 22 county rows of 2024 sum exactly to the national totals, and the 2022 Taipei/Pingtung/Hsinchu City and 2024 national figures match what 中央社, 自由時報 and 公視 display as CEC numbers.

## `raw/cec-finals.tsv` — the snapshot

A compact TSV taken from `db.cec.gov.tw/static/elections/data/{tickets,profiles}/…`, with its SHA-256 in `cec-finals.tsv.sha256`. Regenerate with:

```sh
node scripts/cec-snapshot.mjs   # needs network access to db.cec.gov.tw
node scripts/build-finals.mjs
```

The snapshot was first taken through a browser (this workspace can't reach db.cec.gov.tw directly); running `snapshotTsv` from `scripts/cec-snapshot.mjs` in the browser reproduced the same SHA-256.

## Known gaps

- **2025 recalls.** The CEC database lists all 35 recall cases from 2025 but marks every one `has_data: false` — no vote counts are published there. The CEC recall pages (web.cec.gov.tw → 公職人員罷免案專區) carry petition paperwork, not results. Still to find: an official machine-readable source (the CEC live-results host used on 2025-07-26 / 08-23, or the formal result announcements). Until then we should not fill this from news reports without labeling it as such.
- **Polling-station completion times.** Each election in the CEC database has an attachment `全國投開票所完成時間.xls` (time each polling station's result was entered). Combined with per-station results (`直轄市長.zip` etc.), this could reconstruct the CEC's own count curve for past elections — useful for replaying an election night. Not fetched yet.
