# Win probability over the night ("needle") — 2026-11-09

`scripts/needle.py` turns a partial count into a probability that each of a race's two contenders wins. It is backtested on the 2018 and 2022 mayoral nights (43 races), using the CEC's per-station results and the time each station's report was logged.

## Data (all from db.cec.gov.tw attachments; hashes in `data/raw/cec-stations/SHA256SUMS`)

| Election | Per-station results | Report times |
|---|---|---|
| 2014 mayors | yes | no |
| 2016 president | yes | no |
| 2018 mayors | yes | yes (logged for all contests and referendums at a station) |
| 2020 president | yes | yes |
| 2022 mayors | yes (嘉義市: the 12/18 rerun, used as a baseline only) | yes |
| 2024 president | yes | yes |

`scripts/stations.py` reads them all into one shape. Station numbers are renumbered between elections, so baselines are matched by village (村里; a station covering several villages is keyed by the first): 98–100% of electors match exactly or to a village in the same district whose name differs by one character (variant spellings such as 晉/晋); the rest fall back to their district. The CEC's spreadsheets write rare characters as Private Use Area code points; `stations.py` maps all 32 that occur back to real characters (e.g. 江聰淵, 傅崐萁, 廍, 磘), checked against other years' village names and the CEC's own JSON.

## Model

1. **Two contenders, two sides.** Only the two main contenders count; their votes are renormalized to 100%. The race is scored as the "blue" contender's share: the KMT contender, or whoever faces the DPP when the KMT fields no one, with explicit overrides where labels mislead (see "Which side is blue" below).
2. **Baseline per village.** The blue side's share of the top two in an earlier election. For Taipei 2022 that is 丁守中's share of 丁 + 柯文哲 in 2018, and 韓國瑜's share of 韓 + 蔡英文 in 2020: the other side stands in for this year's non-blue contender, whoever they are. The previous mayoral and presidential races are averaged (in logit), which beat either alone.
3. **Swing from reported stations.** The difference between tonight's share and the baseline share at stations already in, citywide plus district deviations. It is applied to every station still out.
4. **What's left.** Each station still out: electors × its village's baseline turnout × a live turnout ratio (reported stations vs their own baseline turnout) × the share of ballots going to the top two.
5. **Uncertainty.** Shared error in the citywide swing, district-level error where a district has little reporting, station noise, and turnout (the votes still out, and the net margin they carry, scale together if turnout runs above or below its projection; from `Night.turnout`, added 2026-11-10); estimated from the residuals at reported stations, with priors early on (picked by cross-validation: tune on 2018, test on 2022, and the reverse). The probability comes from a Student-t on the predicted final margin.
6. **Certainty.** Once the margin exceeds every elector at stations still out, P is 0 or 1.

## Backtest (blend baseline; 43 races; checkpoints = share of stations in)

| Stations in | Log loss (model / naive) | 80% intervals that held (model / naive) | Mean margin error, % of valid votes (model / naive) |
|---|---|---|---|
| 1% | 0.37 / 0.60 | 56% / 46% | 11.6 / 12.9 |
| 5% | 0.13 / 0.17 | 79% / 44% | 4.6 / 6.2 |
| 10% | 0.13 / 0.07 | 84% / 44% | 3.7 / 4.4 |
| 30% | 0.07 / 0.02 | 93% / 33% | 1.4 / 2.6 |
| 70% | 0.02 / 0.01 | 86% / 26% | 0.6 / 1.2 |

"Naive" assumes the votes still out split like the votes already counted, with sampling error only.

- The model's margin estimate is better at every stage, and its stated uncertainty roughly holds.
- The naive version's stated 80% intervals miss far more than 20% of the time: it is overconfident. It still scores better log loss after ~10% because no race in this sample flipped late, so its overconfidence went unpunished. It whipsaws in close races: 2022 屏東縣 went from 81% to 7% for 蘇清泉 between 18:00 and 18:30; 2018 嘉義市 showed 0.1% for the eventual winner at 18:00.
- 2018 臺北市 (柯文哲 by 3,567 votes): the model gave 丁守中 roughly 20–25% from 18:30 to 19:30 and under 10% from 21:00; the naive version showed 柯 at 99%+ from 18:00 on, much more sure than the count justified.

## Which side is blue

Party labels decide most races. Where a top-two candidate is an independent or a third party, or both are KMT members, the side was set from what is known about the candidate (party moves, endorsements) and checked against the data: across villages, does the candidate's share against the other contender rise where the DPP presidential vote is high (r > 0, green-leaning) or where it is low (r < 0, blue-leaning)? For reference, 陳時中 vs 蔣萬安 (Taipei 2022) gives r = +0.97 to +0.99 and 周春米 vs 蘇清泉 (Pingtung 2022) +0.80.

| Race | Candidate | r vs DPP presidential share | Known | Treated as |
|---|---|---|---|---|
| 2014 臺北市 | 柯文哲 vs 連勝文 | +0.99 (2016) | DPP backed him, fielded no one | other side (green) |
| 2018 臺北市 | 柯文哲 vs 丁守中 | +0.93 / +0.94 (2016 / 2020) | ran against both parties | other side |
| 2014 新竹縣 | 鄭永金 vs 邱鏡淳 | +0.35 | ex-KMT independent | other side (default) |
| 2014 花蓮縣 | 傅崐萁 vs 蔡啟塔 | −0.22 to −0.41 | ex-KMT, later rejoined; his wife won as KMT in 2018 | **blue side** (override) |
| 2014–2022 金門縣 | 陳福海 vs KMT | +0.20 to −0.39 (37 villages) | local independent; no DPP base | other side |
| 2018 苗栗縣 | 徐定禎 vs 徐耀昌 | +0.64 / +0.66 | independent, later DPP nominee | other side |
| 2022 苗栗縣 | 鍾東錦 vs 徐定禎 | −0.93 / −0.92 | expelled by KMT, rejoined, 2026 KMT nominee | **blue side** (override) |
| 2018 新竹縣 | 徐欣瑩 (民國黨) vs 楊文科 | +0.69 / +0.77 | ex-KMT, 2026 KMT nominee | set aside: baseline uses 楊 vs 鄭朝方 (DPP) |
| 2022 新竹市 | 高虹安 vs 沈慧虹 | −0.71 / −0.79 | TPP in 2022; in 2026 an independent with no KMT nominee against her | **blue side** (override) |
| 2014, 2022 連江縣 | two KMT members | too few villages to test | 2022 nominee 王忠銘 vs 曹爾元, same pair in 2026 | 王 blue (override) |

Every case could be placed, so no longer lookback was needed. Swapping sides in single races (e.g. 2018 臺北市 as 丁 vs 姚文智 instead of 丁 vs 柯) changed the 2022 forecast by less than the noise between races, and not consistently in either direction.

## 2026 contenders

`data/2026-contenders.json`: all 22 races from the CEC's candidate list (2026-10-16) with ballot numbers and parties (中央社, 2026-10-27). Blue is a KMT nominee in 19 races; 新竹市 高虹安 (independent, no KMT nominee), 嘉義市 張啓楷 (TPP, joint KMT-TPP candidate) and 嘉義縣 吳品叡 (KMT-backed independent) are the exceptions. Not settled: **花蓮縣** (the second contender is 張峻 or 魏嘉賢) and **金門縣** (six independents against 陳玉珍; 李文良 is the most prominent). For those, "other" should be whichever non-blue candidate leads the count so far.

## Turnout

Win probability barely depends on the turnout assumption (log loss moves in the third decimal across a ±11-point scenario range), because turnout scales both sides. It matters for the projected margin in votes and for the "certain" line. Live turnout (reported stations vs their own baseline turnout) beats holding the baseline turnout fixed once ~5% of stations are in. The page used to offer a turnout slider, a what-if around last time's turnout; it was removed on 2026-11-10 in favour of the live estimate alone (`turnout_sigma` stays in the data, unused). One step on it was the typical county turnout change between consecutive elections of the same level: the root mean square over counties, both pairs pooled, including the nationwide shift. From the station files that is 5.8 points for mayors (2014→18: 3.0; 2018→22: 7.6) and 6.8 for presidents (2016→20: 9.1; 2020→24: 3.4). Until 2026-11-10 every night used 3.75, a mayoral figure that couldn't be reproduced from these files. The live estimate takes over as stations report.

**Same-level comparison.** Every turnout figure compares with the previous election of the same level: mayoral nights with the previous mayoral race, presidential nights with the previous presidential race. This covers the projection, the change shown, the map and the "last time" numbers. The win-probability baseline for mayors blends in the previous presidential race, but only for the vote split; the turnout part always comes from the mayoral race, the first part of the blend (`Night._baseline`). The 2026 night must keep the order `2022-mayors+2024-president`.

## Projected turnout (`Night.turnout`)

The same structure as the vote swing, on turnout: at each counted station, log(ballots / (electors × that village's turnout in the previous mayoral race)); a citywide ratio plus district deviations, applied to stations still out; uncertainty from the spread of those ratios, plus a floor for the stations still out differing from those in. Mean error in final turnout, 43 races:

| Stations in | 0% (last time's turnout) | 5% | 10% | 30% | 70% |
|---|---|---|---|---|---|
| Mean error, points of turnout | 3.7 | 2.2 | 1.9 | 1.1 | 0.4 |

In 2022 the stations still out had 3–5% more ballots than the early-reporting stations implied; in 2018 they didn't. The floor (`sys` in `TURNOUT_PRIOR`) is a compromise: its 80% ranges held about 81–95% of the time for 2022 and more often than intended for 2018 (too wide). Two nights aren't enough to tell which is typical.

The page uses this for the turnout view and for "estimated share of ballots counted" (counted ballots / projected total).

## 2020 presidential night

Added 2026-11-10 (report times: 109全國投開票所完成時間.xls, CEC attachments). Baseline: the 2016 presidential race at village level, the same rule as 2024. A blend with the 2018 mayoral races scored slightly better on this night (county log loss 0.035 vs 0.044 at 5% counted) but worse on 2024's. 宋楚瑜 (4%) is set aside in the dial; no county was three-way. The national projection ran low early (−2.38M ± 0.16M at 10% counted vs −2.65M final, 蔡英文's margin).

## Accuracy summary

`scripts/accuracy.py` scores every race in the replays at 1/5/10/30/70% of its stations against its own final count (`data/accuracy.json`, shown on the site's entry page). Margin errors there are in points of the two contenders' votes, not of all valid votes as in the backtest table above.
- At 10% counted, the favourite went on to win 40 of 43 mayoral races (2018, 2022) and 44 of 44 county races on the two presidential nights.
- No race gave the eventual loser 90% or more after 5% of stations were in.
- The stated 80% margin ranges were too narrow in the 2024 county races once a third of the stations were in (64–68% held; 59–64% before turnout uncertainty was added to the range on 2026-11-10), and early on most nights.

## 2024 presidential night and three-way races

- **National race:** every station in the country as one race (`NationalNight`), counties standing in for districts in the correlated error; 賴清德 vs 侯友宜 (柯文哲 set aside in the dial, his projected share shown alongside). Baseline: the 2020 presidential race at village level. It beat a blend with the 2022 mayoral races on this night (county log loss 0.070 vs 0.074; national ranges much tighter). The national projection leaned toward too big a 賴 margin all night (e.g. −1.09M ± 0.13M at 10% counted vs −0.91M final).
- **Three-way races** (柯文哲 in the top two, or within 10 points of the winner; 8 counties; picked from the final result here, set in advance in 2026): shares projected for all three, and win chances (below). The two candidates with an earlier election to compare with (侯 vs 賴) are split by the usual swing model; the third candidate's share at stations still out is their share at counted stations in the district, with a slope on station size (in 2024, 柯's share rose with station size in every county, r = 0.1–0.65, and larger stations report later) and district deviations, with uncertainty from both. Across 2024's 22 counties at 2–50% counted, the 80% ranges for all three shares held 81% of the time; 柯's share was off by 1.8 points on average, and still ran low early in some counties (苗栗: 26.5% projected at 20% counted vs 30.0% final).
- **Win chances in three-way races.** `Night.three_way` has two independent errors: the third candidate's remaining votes, and the blue–other margin among the rest. `needle.win3` integrates them on a grid to give each candidate's chance of finishing first. The page shows a two-way dial between the two likeliest winners, with the third candidate's chance beside it.
  - Chances start at the 5th station counted in a race. Before that, one or two stations' share for a candidate with no earlier election is a poor guide. Across the 22 counties, the log loss of the eventual winner's chance was 1.65 at 1 station, 0.64 at 2, 0.26 at 3 and 0.13 at 5.
  - These chances can't be checked well: eight three-way counties on one night.
  - Where they mattered, they looked right. In 新竹市 (final: 賴 34.8%, 柯 34.3%, 侯 30.9%), they gave 柯 about 42% at 20% counted. The two-way dial, which sets 柯 aside, gave 賴 97.5%.
  - In counties 柯 never threatened, the three-way chances score worse than the two-way p. This is expected: the two-way p can't be punished for ignoring a third candidate who never came close.
- **2026 three-way watch list** (`data/2026-contenders.json`, `three_way`; updated 2026-11-10). Adjust live if the count disagrees.
  - **花蓮縣: expected three-way.** 游淑貞 (KMT) vs 張峻 vs 魏嘉賢 (both independents; the DPP fielded no one). Model set-up: 游 vs the non-KMT side by the usual swing (baselines: 2022 mayoral and 2024 presidential, village level); the trailing independent as the third candidate, projected from the count. If 魏 overtakes 張 in the count, swap them.
  - **彰化縣: watch.** 邱建富 (independent, ex-DPP). Two-way unless 邱 gets within 10 points of the leader in the count.
  - **金門縣: watch.** 陳玉珍 (KMT) against several independents (李文良, 張國威 and others). "Other" is whichever independent leads the count. Possibly three-way if two independents split the anti-陳 vote evenly.
  - **澎湖縣: watch.** Six candidates.
  - **Live rule:** show a race as three-way when it is marked expected, or when a third candidate is in the top two or within 10 points of the leader with at least 5% of stations in. Win chances start at the 5th station.
- **County channel watch:** 華視's side panel rotated through county counts; `scripts/ocr_cts_county/` reads it off the recording's storyboard frames (party-color blocks, county-label templates, grayscale digit templates) and `scripts/clean_cts_county.py` drops misreads (a block whose shares jump more than 2 points from the same county's neighbouring blocks, then any value that breaks a non-decreasing run). Kept: 12 counties, 8–105 readings each (基隆市's 3 blocks dropped: values under 10,000 are misread). Eye check of 16 random blocks: 基隆 wrong, 1 of 39 other values wrong (dropped by the filter), 2 uncertain in the last digits. What the series shows: before ~18:15 華視's county counts ran far ahead of the CEC's logged station times (新北市 ~100,000 votes on 華視 before the CEC had logged a station); after that 華視 showed the CEC's numbers. The county race views carry it as a reliable source (floor = max of CEC and 華視).
- **Channel watch:** the national panel at the top of the page (and every county view, below its margin chart) carries the channels' on-screen counts at the clock time (公視 own count, 華視, 三立, TVBS), with the floor (max of reliable), the field (mean and range), and the model's projected final from the CEC count. A channel above the top of the model's 80% range is marked red, the live counterpart of "above the final".

## Legislative districts and the party vote (2020, 2024): backtest only

Per-station results for the 73 district races and the party-list vote, parsed by `scripts/stations.py` (`2016/2020/2024-legislator`, `-party`, `-plains`, `-mountain`). On the site since 2026-11-10 as "Show: Legislature" on the presidential nights (`scripts/build_legislature_data.py` → `data/legislature/<year>.json`).

**District needles** (`scripts/backtest_legislators.py`). The same model, each district as a race (KMT vs the main opponent). Baseline: the previous presidential race and the previous legislative race, averaged in logit at village level (the legislative part pools all of the county's districts, since lines are redrawn; turnout comes from the presidential part). Margin errors are in points of the two contenders' votes.

| Stations in | 1% | 5% | 10% | 20% | 30% | 70% |
|---|---|---|---|---|---|---|
| 2020: favourite won | 60/73 | 67/73 | 69/73 | 72/73 | 73/73 | 73/73 |
| 2020: margin error / 80% range held | 8.5 / 74% | 4.4 / 82% | 2.8 / 85% | 1.7 / 92% | 1.2 / 93% | 0.5 / 97% |
| 2024: favourite won | 59/73 | 68/73 | 69/73 | 70/73 | 69/73 | 73/73 |
| 2024: margin error / 80% range held | 12.3 / 75% | 4.9 / 88% | 3.7 / 90% | 2.5 / 86% | 1.6 / 90% | 0.5 / 99% |

- Baseline choice (log loss of the eventual winner's chance, 2020 / 2024 at 30% counted): presidential race only 0.072 / 0.107; with the previous legislative race 0.058 / 0.090; with the previous mayoral race 0.067 / 0.096. The legislative blend scored better in both years at every checkpoint (by 5–24%), which local candidate strength would explain. Until 2026-11-10 the site used the presidential race only; an earlier reading of this comparison called it a wash.
- Misses at 30% in 2024: 雲林縣1 (丁學忠 won by 1.8; the model gave him 18%), 新北市12 (廖先翔 won by 6.0; 44%), 新北市7 (葉元之 by 1.5; 43%), 南投縣2 (游顥 by 2.5; 46%). 新北市12 gave the eventual loser 92% at one point after 5% counted, 雲林縣1 85% (with the presidential baseline alone: 90%+ in both).
- Districts are smaller than counties and swing more on candidates, so the needle is less sure-footed than for mayors at the same share counted.

**Party vote** (`scripts/backtest_party_vote.py`; 34 seats, 5% threshold, largest remainder):
- The counted shares are a poor guide: early stations lean toward the big two. In 2024 the counted shares were 3 points off at 30% counted, and the seats from them were still wrong at 70% (TPP short).
- A proportional swing against the previous party-list vote, village by village, did much better. New parties without a previous vote (TPP in 2020) use their counted share in the district, shrunk toward the county.
  - 2024: shares off by 1.1 points at 10%, 0.6 at 30%; seats right from 10% counted.
  - 2020: 2.4 points at 10%, 1.2 at 30%, but one seat (DPP 14 / TPP 4 vs final 13 / 5) was still wrong at 70%. The last seat is decided by remainders a few thousand votes apart, so it needs a stated chance, not a single call.
- Women's half of each party's list seats doesn't change the party seat counts, only who sits.
- On the site (`scripts/party_vote.py`): votes still out are estimated from electors × the county's valid-vote rate so far, not the final turnout. Each party's share gets an error of 0.025·√(p(1−p)) × the share of votes still out, widened early (×(1 + √(200 / stations in))) and for new parties (×1.5). The page shows the three most likely seat splits from 1,000 draws, starting at the 50th station. Calibration: in 2024 the final split was the most likely one from 10% counted (34% then, 51% at 30%, 89% at 70%). In 2020 it never was: the most likely split kept 民眾黨 one seat short, with the final split at 8% (10% counted) to 38% (70%). The cause is the new-party projection.
- Indigenous seats (平地, 山地; 3 each): shown like a council district, counted with the decided test. 2020 山地's third seat went to 孔文吉 by 16 votes over 伍麗華.

## Model review (2026-11-10)

`scripts/model_review.py` scores candidate changes on every replayed race: 44 mayoral (2018, 2022), 44 presidential county races (2020, 2024) and 146 legislative districts (2020, 2024), at 1/5/10/20/30/70% of stations, by log loss of the eventual winner's chance, share of finals inside the 80% range, and margin error.

Adopted:
- **Turnout uncertainty in the margin's range** (`TURNOUT_IN_MARGIN`). The votes still out scale together with turnout, and so does the net margin they carry; the turnout projection's sd is now part of the margin's sd. Mayoral log loss at 1% counted fell from 0.46 to 0.37 and the 80% ranges held more often (1%: 59% → 64%; presidential counties at 30%: 75% → 82%), with no checkpoint worse.
- **Legislative baseline blend** (above).

Asked afterwards (2026-11-10): **a station-size slope with a prior that fades as stations come in.** The slope's prior mean was taken from the other night of the same kind (2018 for 2022 and the reverse; likewise for the presidential and legislative pairs), with a prior worth 12, 40 or 160 stations, so its weight shrinks as counted stations accumulate. Not adopted: the slope isn't stable from one election to the next. At the final count the average within-county slope was +0.065 (2018 mayors), +0.018 (2022), −0.080 (2020 presidential), +0.067 (2024 presidential, 柯文哲's urban vote), +0.018 and +0.070 (2020 and 2024 legislative). Borrowing last time's slope made presidential county log loss worse at 5–10% counted (0.070 → 0.113 at 5%) and left the others within noise.

Tried and not adopted (no gain, or gains at one stage paid for at another):
- A swing slope on station size (log electors), estimated live: better presidential margins early, worse log loss after 20%.
- Shrinking the early swing toward zero (a prior on the countywide shift): worse everywhere at prior sds of 0.15–0.25 logit, neutral at 0.4. Real swings between elections are large, so the shift shouldn't be pulled toward "no change".
- Down-weighting outlying stations (Huber weights at 1.5–2 sds): log loss within ±0.005; 80% ranges held slightly less often on presidential nights.
- Wider priors (station noise 0.35–0.45, district 0.12, global floor 0.10): the 80% ranges hold more often early, log loss no better or worse. The early misses are mostly swings in the wrong direction from unusual first stations (2018 金門 at 1 station, 2024 臺東 legislative), which a wider range only partly covers.
- Blending the intervening mayoral race into presidential county baselines: better at 1%, mixed after.

Still open:
- **Early stations aren't a random sample.** The first stations to report are small (rural, often indigenous townships) and swing differently. Nothing tried fixed this without hurting later; the site's notes say early numbers are rough.
- **Presidential county ranges** still run narrow after 10% counted (73–82% held). Log loss there is already low (nearly every county is lopsided), so this mostly affects the margin chart's band.
- **New parties in the party-list projection** (TPP 2020): the counted share in the district, shrunk toward the county, ran low all night. A size slope like the three-way model's might help; only one case to test it on.

## The 2026 night before the count (`scripts/build_2026_night.py`)

`data/needle/2026-mayors.json`: every race with its contenders (`data/2026-contenders.json`), ballot numbers (中央社 2026-10-27, transcribed 2026-11-10 from an automated reading of the page; **check against the CEC's ballot before the night**), and no points. Electors, stations and "last time" turnout are 2022's; the incumbent shown is the 2022 winner, under the party they won with. The results page opens on this night by default: 16:00 to 00:00 on the time axis (extended if counting runs later), empty chart frames, and space kept for the count watch in each county panel. 花蓮縣 is set up as three-way (游淑貞 / 張峻 / 魏嘉賢).

Feed policy on the page: per-station results whenever the feed has them; district totals only when it doesn't (`"feed": "district"` in the night's data), with a notice. The replays always use per-station results; the district-total columns stay in the data.

## What could break this in 2026

- **Feed granularity.** The backtest uses station-level results. If the CEC's live feed only gives district totals, the same model still runs and stays calibrated but is weaker (log loss 1.1–1.8× the station-level figure through half the count). Not yet verified what the 2026 feed provides.
- **Station electors.** Not published before the vote. The law (選罷法 §38) requires announcing elector totals three days before; past announcements give citywide totals for mayor (and district totals for council and referendum rolls), not per-village or per-station counts. Polling-station locations and the villages each covers are public (公告 2026-08-31). So until a station reports, its electors have to be estimated from 2022/2024 station data, scaled to the announced total.
- **Contenders.** In the backtest, picked as the two leaders of the final result; for 2026 they are set in advance (see above), with two races unsettled.
- **Small sample.** 43 races, few of them close. Calibration estimates are rough.
- Report times are when the CEC logged a station, for all contests at once (and, in 2018, referendums too).

Run: `python3 scripts/needle.py backtest`, or `python3 scripts/needle.py race 2018-mayors 臺北市 --baseline 2014-mayors+2016-president`.
