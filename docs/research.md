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

## Rebuilding other outlets' counts over the night (2026-11-05)

Goal: for 2022 and 2024, each outlet's reported count over time, to set against the CEC's own rebuilt count (`data/nights/`) and the finals.

### Web pages and APIs: sparse at best
- Outlet APIs that are still online (公視 `getVoteTv`, 中央社 `city.json`, 自由時報 pages) now return only end-of-night values.
- Wayback Machine: 自由時報 2022 has ~7 mid-count captures. 聯合報 `udn.com/vote2022/` has **549 captures across 91 distinct minutes (16:02–22:57 Taipei)**. Not yet examined: Wayback throttled our queries (HTTP 429/503) before we could list them. Worth a slow, careful follow-up.
- Other outlets' 2022/2024 pages: CDX queries didn't complete under the throttling, so coverage is unknown, not zero.

### YouTube recordings: the most promising source
Full-length recordings of election-night coverage are still up, each with an exact stream start time (`liveBroadcastDetails.startTimestamp`). Most channels also show a clock on screen.

| Election | Recordings found (hours) |
|---|---|
| 2024 | CEC 6.7, 華視 6.2, 公視 7.9, TVBS 7.6, 三立 11.9, 民視 8.1, 聯合 5.7, 寰宇 6.1 (東森's link is dead) |
| 2022 | CEC 8, 華視 4, 公視 6.5, 東森 8, 聯合 5.9, 台視 7.1, 三立 11.9, TVBS 7, 年代 3, 壹電視 3.9, 民視 1.6 |

Neither the workspace nor the Mac's shell can reach YouTube, and video won't play in the automated Chrome tab (tab reported as hidden). What *does* work is YouTube's **storyboard**, the preview-frame sprite sheets, fetched in the browser:

- **2024 recordings: 320×180 frames every 10 s.** Main tallies are readable. Example, 三立 at on-screen clock 17:59:44: 賴清德 3,015,260 / 侯友宜 2,654,454 / 柯文哲 2,210,099, with on-screen percentages 38.3 / 33.7 / 28.0 matching those numbers. (The CEC's own count at 18:00 had 賴 at ~418k.)
- **2022 recordings: only 160×90 frames.** Only full-screen race cards are readable (e.g. TVBS around 19:00: 桃園 張善政 425,357 / 鄭運鵬 318,115). Sidebar tallies are not.
- One 三立 2024 sprite sheet mixed in frames from unrelated programming, so each frame's time should come from the **on-screen clock**, not from the frame's position in the video.

Implication: 2024 can probably get a dense per-station series for the presidential race. 2022 would get scattered points, mostly for whichever races got full-screen cards.

### What the 2024 broadcasts show (from `data/nights/`)

賴清德 (final 5,586,019), as shown on screen versus the CEC's own count:

| Taipei | CEC | 公視 own | 華視 | 三立 | TVBS |
|---|---|---|---|---|---|
| 17:00 | 1,681 | 181,911 | 316,144 | 2,153,603 | 2,138,552 |
| 17:30 | 52,630 | 535,582 | 1,424,191 | 2,847,673 | 2,848,972 |
| 18:00 | 417,780 | 664,870 | 2,417,079 | 3,004,720 | 3,014,518 |
| 18:30 | 1,492,076 | (CEC relay) | 3,164,015 | 3,183,475 | 3,070,948 |
| 19:00 | 3,094,968 | | 3,688,341 | 3,713,897 | 3,676,973 |
| 19:30 | 4,463,222 | | 4,427,956 | 4,427,956 | 4,427,956 |

- Commercial channels were far ahead of the CEC early: at 17:00 三立 and TVBS each showed ~2.1M for 賴, when the CEC had counted 38 polling stations.
- Their own counts then flattened around 3.0–3.7M (18:00–19:00) while the CEC caught up. 三立 added only tens of votes per minute from about 18:30 to 19:00.
- From about **19:25–19:30, 華視, 三立 and TVBS show identical numbers**, about a minute behind the CEC rebuild: they had switched to relaying the CEC feed.
- 公視's own count was the slowest. The CEC overtook it around 18:10, and 公視 then switched its panel to the CEC relay.
- **No channel showed any candidate above the final at any point in 16:00–20:00.** 2024 had no over-reporting to call out.

Implication for the site: the "reliable MAX" floor is mainly useful from 16:00 to ~18:00. After that the CEC is ahead of the honest counters, and by ~19:30 everyone relays the CEC anyway. The early field numbers are where the spread, and the risk, is.

## Election day 2026

Saturday 2026-11-28, voting 08:00–16:00. TV stations report from ~16:00; CEC data typically starts reaching media ~17:00–17:30.
