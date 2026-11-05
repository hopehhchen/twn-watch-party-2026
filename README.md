# twn-watch-party-2026

A live vote-count tracker for Taiwan's 2026 local elections (投票日 2026-11-28), built on one idea: **real ballots only go up.**

## How it works

Sources are split into two cohorts:

| Cohort | Sources | Shown as |
|---|---|---|
| **Reliable** — counts real ballots, documented as such | CEC (中選會), CNA (relays CEC), PTS (公視), CTS (華視) | **MAX** across the cohort — a floor the final result can't go below |
| **Field** — commercial TV/web counts, partly estimated | TVBS, SET (三立), FTV (民視), EBC (東森), CTi (中天), TTV (台視), and others | **MEAN** with the spread visualized |

The site also keeps a record of every source that, at any point during the night, reported **more votes than the final certified count** for a candidate.

## Example elections (development data)

- 2022 local elections (mayors)
- 2024 presidential election
- 2025 recall votes (counted as 同意 / 不同意 rather than candidates)

## Status

Early setup. See `docs/` for research notes as they're added.
