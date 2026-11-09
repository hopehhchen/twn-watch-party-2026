# Data

## `finals/` — certified final results

The yardstick for the "reported more than the final" callout. One file per election:

| File | Election | Races |
|---|---|---|
| `2022-local-mayors.json` | 2022-11-26 mayors and county magistrates | 21 (6 municipalities + 15 counties/cities) |
| `2022-chiayi-city-mayor-rerun.json` | 2022-12-18 Chiayi City mayor (postponed vote) | 1 |
| `2024-president.json` | 2024-01-13 presidential election | 1 national + 22 counties |

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

## `nights/` — the CEC's count over election night

`<election>.cec.json` rebuilds how the CEC's official count grew during the night, from two CEC attachments in `raw/cec-stations/`:
votes per candidate at every polling station, and the time each station's report was logged (全國投開票所完成時間).

| File | Races | Stations | First → last report (Taipei time) |
|---|---|---|---|
| `2022-local-mayors.cec.json` | 21 | 17,649 | Taipei 17:14 → 21:41 (varies by city) |
| `2024-president.cec.json` | national + 22 counties | 17,795 | 16:31 → 21:57 |

Each race has `series`: one row per minute in which any station reported,
`[HH:MM, stations_reported, votes for each option in "options" order…]`, cumulative. Times are rounded **up** to the minute.

Checks:
- Every race's last row equals the certified final in `finals/` exactly, and every station in the results has a report time (the build fails otherwise).
- 2024 at 18:00: rebuilt 2,110 stations / 賴 417,780 / 侯 327,970 / 柯 221,906. 中央社 published the CEC's 18:00 count as 2,112 stations / 417,866 / 328,262 / 222,006. ([CNA](https://www.cna.com.tw/news/aipl/202401130135.aspx))
- 2022 against 自由時報's CEC column in Wayback captures: Pingtung and Hsinchu City match the rebuild **exactly**, 3–4 minutes before the capture time (feed + page delay). Tainan's archived CEC figure appears ~6 minutes *earlier* than the rebuild; Taipei's lies between two rebuilt minutes.

**What the timestamps mean.** The time is when a polling station's report was logged by the CEC. In 2022 the log covers all nine local contests at a station, so a mayoral count may have been entered somewhat earlier. Read the curve as accurate to within a few minutes, not as an exact replay of what the CEC website showed.

Rebuild: `python3 scripts/build_cec_night.py` (needs `xlrd`, `openpyxl`). Raw files and their SHA-256 values (matching what the CEC lists for each attachment) are in `raw/cec-stations/`.

### Broadcast counts: `<election>.<outlet>.json`

What each TV channel showed on screen during the night, read from YouTube's storyboard frames of its election-night stream (320×180, one frame per minute, 16:00–20:00 Taipei time):

- `series`: `[HH:MM:SS, votes for each option in "options" order…]`, with `null` where that minute's frame didn't show the tally (cutaways, animations).
- `checks.removed_outliers`: isolated readings that broke the trend on both sides, treated as misreads and removed.
- `checks.decreases`: any drop that survived cleaning (a reported count going down).
- `checks.above_final`: any reading above the certified final.

| File | Channel | Coverage (Taipei time) | Notes |
|---|---|---|---|
| `2024-president.cts.json` | 華視 | 16:00–20:00 | one layout all night |
| `2024-president.tvbs.json` | TVBS | 16:00–20:00 | boxes reorder by rank; matched to candidates by colour |
| `2024-president.set.json` | 三立 | 16:00–20:00 | two layouts (bars until ~17:50, leader panel after) |
| `2024-president.pts-own.json` | 公視 own count (公廣布點) | 16:30–18:20 | shown beside a CEC column until ~18:20 |

**公視 after ~18:20 is not published.** Its later panel relays the CEC count: every readable 侯 value matched the CEC rebuild in the same minute. That makes it redundant with `*.cec.json`. Its large 賴 box also reads poorly (leave-one-out 6 of 18).

**Verification.**
- Leave-one-out on the hand-read labels gives 0 wrong readings for every published layout.
- A random sample of 20 published minutes (52 numbers, five per channel) was checked by eye: **0 errors**. With 0 of 52 wrong, the error rate is plausibly under ~6%, not proven zero.
- Every reading flagged as a drop or as above the final was checked by eye. In this data each one was a misread (6↔8, 9↔0/8, 2↔7), so none remains. **A broadcast count is only called out as above the final after a person has looked at the frame.**

How the numbers are read: `scripts/ocr_storyboard.py` matches digits against templates built for each channel's font from hand-read frames. The layouts, crop boxes and hand-read labels are in `scripts/ocr_layouts.json`. Accuracy is measured with leave-one-out over those labels (train without a frame, then read it). A reading is used only when every digit clears a confidence margin, so unclear frames are skipped rather than guessed. The frames themselves are not in the repo.

### 華視 county panel: `2024-president.cts-county.json`

華視 rotated county counts through a side panel. These are read from storyboard frames (~one per 10 s) by `scripts/ocr_cts_county/` and cleaned by `scripts/clean_cts_county.py`; the raw reads (499 county blocks) are in `raw/cts-county/ocr-reads.csv`.

- `counties`: `{county: [[HH:MM:SS, 賴, 侯, 柯], …]}` for 12 counties (8–105 readings each). 基隆市 is left out: its 3 blocks were misread.
- `checks.dropped`: blocks removed and why. A block is removed when a share jumps by more than 2 points from the same county's blocks within 15 minutes. After that, any value breaking a non-decreasing run is removed too.
- `checks.above_final`: none.

**Less reliable than the national tallies.** The digits are ~5 px tall and the reader is weaker: about 86–93% of rows read correctly in leave-one-out, against 100% for the national layouts. Hence the filtering.

An eye check of 16 random blocks found:
- 基隆 wrong.
- 1 of the other 39 values wrong (in the 萬 digit, removed by the filter).
- 2 uncertain in the last digits (≤ 20 votes).

A thousands-digit misread that keeps the series rising can survive.

**Timing.** Up to ~18:15, 華視's county counts ran well ahead of the CEC's station log times. Afterwards they equal the CEC's numbers.

## `raw/cec-finals.tsv` — the snapshot

A compact TSV taken from `db.cec.gov.tw/static/elections/data/{tickets,profiles}/…`, with its SHA-256 in `cec-finals.tsv.sha256`. Regenerate with:

```sh
node scripts/cec-snapshot.mjs   # needs network access to db.cec.gov.tw
node scripts/build-finals.mjs
```

The snapshot was first taken through a browser (this workspace can't reach db.cec.gov.tw directly); running `snapshotTsv` from `scripts/cec-snapshot.mjs` in the browser reproduced the same SHA-256.


## `raw/cec-mayor-turnout.tsv` — mayoral turnout history

One row per mayoral race, 1994–2022 (直轄市長 since 1994; 縣市長 since 2009), from the CEC database's district-level profiles (`/static/elections/data/profiles/ELC/<C1|C2>/00/<theme>/C/00_000_00_000_0000.json`). Columns, tab-separated, no header:

`vote_date  subject(C1=special municipality, C2=county/city)  area  electors  ballots_cast  valid  invalid  turnout_pct`

Checked: valid + invalid = ballots for every row, and turnout_pct = ballots / electors to 0.01. The SHA-256 in `cec-mayor-turnout.tsv.sha256` matches the copy assembled in the browser. 2022 嘉義市 is the 12/18 rerun.

The 2026 elector counts are not here: by law (公職人員選舉罷免法 第38條) the commission announces them three days before voting, i.e. by 2026-11-25.

## `raw/cec-stations/` — per-polling-station results, 2014–2024

Mayoral (2014, 2018, 2022) and presidential (2016, 2020, 2024) per-station sheets, plus the 2018, 2022 and 2024 station report-time files. All downloaded from the CEC election database attachments; `SHA256SUMS` matches the hashes the CEC publishes. `scripts/stations.py` reads them into one shape and checks that each station's candidate votes add up to its valid ballots (they all do). Used by `scripts/needle.py`; see `docs/needle.md`.

## Council (議員) results, 2018 and 2022

- `raw/cec-stations/<year>-<municipal|county>-council-stations.zip`: per-polling-station votes for every council candidate, one sheet per electoral district (選舉區), including the indigenous districts. Same layout as the mayoral sheets; report times are the same station-time files as the mayoral races.
- `raw/cec-council-tickets.tsv` (+ `.sha256`): every candidate's final votes with the CEC's elected flag, from the database's district-level JSON. Columns: election, subject (T1 直轄市議員 / T2 縣市議員), seat_type (T1 區域, T2 平地原住民, T3 山地原住民), county_code, district_code, district, cand_no, name, party, sex (1 male, 2 female), votes, victor. victor: `*` elected, `!` elected through the women's quota, `-` displaced by the quota, blank not elected. 912 seats in 2018 (908 `*` + 4 `!`), 910 in 2022 (906 + 4).

### `council/<year>.json` — the council count over the night

Built by `scripts/build_council_data.py` from the two files above and the station report times. Seat counts and allocation come from `scripts/council.py`. Each electoral district has:
- its candidates and seats, plus the seats reserved for women;
- `pts`: `[t_min_after_16, stations_in, electors_left, votes per candidate…]`, cumulative, one row per minute in which one of its stations reported.

Checks (run on every build):
- Each candidate's station votes add up to the CEC's final.
- The seat allocation on the finals, including the women's quota (地方制度法 §33: one reserved seat per 4 seats), reproduces the CEC's elected list in every district: 214 districts and 912 seats in 2018, 215 and 910 in 2022.

Five ballot numbers (2018 屏東縣 ×3, 2022 新北市 ×2) appear on the station sheets with 0 votes but not in the CEC's results list. They are left out.

The council page (`site/council-template.html`) loads these files at runtime, so `build_site.py --standalone` copies them next to the page.
