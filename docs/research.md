# Research notes (2026-11-05)

## Why cohorts, not a plain MAX

The original idea: real ballots only go up, so `final ≥ max(source_i)` and taking the MAX across outlets gives the fastest valid count. That holds only if every source reports real tallies. Commercial TV counts in Taiwan don't, early in the night:

- Stations send staff to a **sample** of polling stations and weight the results up; a "調控" step can adjust figures by hand to keep viewers from switching channels. ([鏡電視公評人報告 2023/5](https://statics.mnews.tw/assets/documents/clibgbzkd008110pw8ypz5t0p.pdf))
- In 2022 the deviations split by camp: TVBS and 中天 widened 蔣萬安's lead; 三立 and 民視 narrowed 陳時中's deficit. A per-candidate MAX picks each candidate's friendliest station. (same source)
- Documented glitches: 2004 counts above the CEC final; 2020 東森 showing ~10M votes at 16:10; 2022 三立 swapping Pingtung candidates at 20:11. A MAX keeps any glitch forever.
- 2022: 三立 showed figures labeled "source: CEC" at 16:03; the CEC sent its first Taipei result around 17:20. ([PeoPo](https://www.peopo.org/news/610982))
- A 2020 monitoring report found 公視 and 華視 the most reliable stations. ([中央社](https://www.cna.com.tw/news/firstnews/202001180069.aspx))

Hence: MAX over the reliable cohort (CEC, CNA, PTS, CTS) as a floor; MEAN with spread for the rest; and a record of anyone who went over the final.

## Live sources seen in past cycles

| Source | What exists | Notes |
|---|---|---|
| 自由時報 `election.ltn.com.tw/2022/realtime/<City>` | Side-by-side 東森 / 民視 / 台視 / 中選會 per race | Still online; server-rendered; blocks bots. Minor-candidate rows misaligned in its comparison table. |
| 公視 `news.pts.org.tw/projects/2024-election-vote/` | `api/getVoteTv/?after=<unix>` per-station counts (三立, TVBS, 公視, 台視) | Endpoint still responds but only returns the final snapshot now. |
| 中央社 `cna.com.tw/project/20221126-election-live/` | `api/city.json` (relays CEC) | Good schema reference (`candNo`, `tickets`, `process`, `time`). |
| Wayback Machine | ~7 mid-count captures of 自由時報 2022 (18:32–20:28 Taipei) | Only real mid-count multi-source evidence found so far. |

## Election day 2026

Saturday 2026-11-28, voting 08:00–16:00. TV stations report from ~16:00; CEC data typically starts reaching media ~17:00–17:30.
