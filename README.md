# twn-watch-party-2026

A live vote-count tracker for Taiwan's 2026 local elections (投票日 2026-11-28), built on one idea: **real ballots only go up.**

## How it works

Sources are split into two cohorts:

| Cohort | Sources | Shown as |
|---|---|---|
| **Reliable** — counts real ballots, documented as such | CEC (中選會), CNA (relays CEC), PTS (公視), CTS (華視) | **MAX** across the cohort — a floor the final result can't go below |
| **Field** — commercial TV/web counts, partly estimated | TVBS, SET (三立), FTV (民視), EBC (東森), CTi (中天), TTV (台視), and others | **MEAN** with the spread visualized |

The site also keeps a record of every source that, at any point during the night, reported **more votes than the final certified count** for a candidate.

## The site

- **Entry page** (`index.html`): what the site does, how the model works, and how accurate it was on past nights. Bilingual (English / 繁中).
- **Results** (`live.html`): for each night, a needle per race (chance to win, projected margin), projected turnout, and council seats ("Show: Council"). Presidential nights also get the national race. 2024 adds the count watch: channels vs CEC vs the projected final. Replays: 2018 and 2022 local, 2020 and 2024 presidential.

Build: `python3 scripts/build_site.py _site` (GitHub Pages runs the same). The night files under `data/needle/` and `data/council/` come from `scripts/build_needle_data.py` and `scripts/build_council_data.py`, which need the raw CEC files. Model and backtests: [`docs/needle.md`](docs/needle.md). Accuracy summary: `scripts/accuracy.py` → `data/accuracy.json`.

## Example elections (development data)

- 2018 and 2022 local elections (mayors, councils)
- 2020 and 2024 presidential elections

## Status

- Certified final results for 2022 and 2024 are in [`data/finals/`](data/finals/) (from the CEC database, checksum-verified). See [`data/README.md`](data/README.md).
- Research notes: [`docs/research.md`](docs/research.md).
