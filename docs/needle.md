# Win probability over the night ("needle") — 2026-11-09

`scripts/needle.py` turns a partial count into a probability that each of a race's two contenders wins. It is backtested on the 2018 and 2022 mayoral nights (43 races), using the CEC's per-station results and the time each station's report was logged.

## Data (all from db.cec.gov.tw attachments; hashes in `data/raw/cec-stations/SHA256SUMS`)

| Election | Per-station results | Report times |
|---|---|---|
| 2014 mayors | yes | no |
| 2016 president | yes | no |
| 2018 mayors | yes | yes (logged for all contests and referendums at a station) |
| 2020 president | yes | no |
| 2022 mayors | yes (嘉義市 rerun not included) | yes |
| 2024 president | yes | yes |

`scripts/stations.py` reads them all into one shape. Station numbers are renumbered between elections, so baselines are matched by village (村里): 97–99% of electors match; the rest fall back to their district.

## Model

1. **Two contenders, one axis.** Only the two leading candidates count; their votes are renormalized to 100%. The race is scored as the KMT contender's share (DPP's when there is no KMT contender, e.g. 2022 新竹市).
2. **Baseline per village.** The same party's share of the top two in an earlier election. For Taipei 2022 that is 丁守中's share of 丁 + 柯文哲 in 2018, and 韓國瑜's share of 韓 + 蔡英文 in 2020: the non-KMT side stands in for this year's non-KMT contender, whoever they are. The previous mayoral and presidential races are averaged (in logit), which beat either alone.
3. **Swing from reported stations.** The difference between tonight's share and the baseline share at stations already in, citywide plus district deviations. It is applied to every station still out.
4. **What's left.** Each station still out: electors × its village's baseline turnout × a live turnout ratio (reported stations vs their own baseline turnout) × the share of ballots going to the top two.
5. **Uncertainty.** Shared error in the citywide swing, district-level error where a district has little reporting, station noise; estimated from the residuals at reported stations, with priors early on (picked by cross-validation: tune on 2018, test on 2022, and the reverse). The probability comes from a Student-t on the predicted final margin.
6. **Certainty.** Once the margin exceeds every elector at stations still out, P is 0 or 1.

## Backtest (blend baseline; 43 races; checkpoints = share of stations in)

| Stations in | Log loss (model / naive) | 80% intervals that held (model / naive) | Mean margin error, % of valid votes (model / naive) |
|---|---|---|---|
| 1% | 0.37 / 0.60 | 58% / 46% | 11.7 / 12.9 |
| 5% | 0.13 / 0.17 | 77% / 44% | 4.8 / 6.2 |
| 10% | 0.13 / 0.07 | 84% / 44% | 3.8 / 4.4 |
| 30% | 0.07 / 0.02 | 93% / 33% | 1.3 / 2.6 |
| 70% | 0.02 / 0.01 | 88% / 26% | 0.6 / 1.2 |

"Naive" assumes the votes still out split like the votes already counted, with sampling error only.

- The model's margin estimate is better at every stage, and its stated uncertainty roughly holds.
- The naive version's stated 80% intervals miss far more than 20% of the time: it is overconfident. It still scores better log loss after ~10% because no race in this sample flipped late, so its overconfidence went unpunished. It whipsaws in close races: 2022 屏東縣 went from 81% to 7% for 蘇清泉 between 18:00 and 18:30; 2018 嘉義市 showed 0.1% for the eventual winner at 18:00.
- 2018 臺北市 (柯文哲 by 3,567 votes): the model gave 丁守中 roughly 20–25% from 18:30 to 19:30 and under 10% from 21:00; the naive version showed 柯 at 99%+ from 18:00 on, much more sure than the count justified.

## Turnout

Win probability barely depends on the turnout assumption (log loss moves in the third decimal across a ±11-point scenario range), because turnout scales both sides. It matters for the projected margin in votes and for the "certain" line. Live turnout (reported stations vs their own baseline turnout) beats holding the baseline turnout fixed once ~5% of stations are in. Suggested slider: around 2022 turnout, σ ≈ 3.75 points (the spread of county turnout changes, 2014→2018 and 2018→2022), as a prior and what-if; the live estimate takes over as stations report.

## What could break this in 2026

- **Feed granularity.** The backtest uses station-level results. If the CEC's live feed only gives district totals, the same model still runs and stays calibrated but is weaker (log loss 1.1–1.8× the station-level figure through half the count). Not yet verified what the 2026 feed provides.
- **Station electors.** The backtest knows each station's electors; in 2026 those may only be known per village or district before results.
- **Contenders.** Picked here as the two leaders of the final result; in 2026 they are named before the night.
- **Small sample.** 43 races, few of them close. Calibration estimates are rough.
- Report times are when the CEC logged a station, for all contests at once (and, in 2018, referendums too).

Run: `python3 scripts/needle.py backtest`, or `python3 scripts/needle.py race 2018-mayors 臺北市 --baseline 2014-mayors+2016-president`.
