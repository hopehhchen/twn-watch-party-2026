# Election night plan: 2026-11-28

Written 2026-11-10, updated the same day once the mayoral pipeline was built. All times are Taiwan time (UTC+8). "Unverified" means a date or fact we believe but haven't confirmed from an official source.

## What we know about the CEC's live count

- **Where:** the CEC's count site (計票資訊查詢網站). In 2025 it was `vote.cec.gov.tw/zh-TW/` (the referendum page `F1/00000000000000000.html`). Today that address forwards to the CEC's 2026 election page, so the count site isn't up yet. Another 2026 project reports that it's announced about a week before the vote (unverified).
- **Level:** the county and each town (鄉鎮市區), not polling stations. Each page gives every candidate's votes so far and the number of stations reported (已送/應送). Pages per cycle: 22 county + 368 town candidate pages (prefix `TC`) and 22 turnout pages (`SC`). The page code is county(5) + `00` + town(3) + `0000000`; the 2022 codes are in `data/live/towns-2022.json`, from the CEC's own 2022 site menu.
- **Markup:** changed between 2022 (class-based) and 2025 (id-based). The parser reads tables by their header labels, and works on saved pages of both (`tests/fixtures/cec/`, copies from the Wayback Machine collected by github.com/outsider987/vote, MIT).
- **Location:** the same project advises polling "from a Taiwan-located machine because the CEC may geo-limit" (unverified). On 11/10 the CEC's 2026 election page loaded from Hope's browser; on 11/17 the count host returned 403 from HiNetCDN on every path (see "Readiness check" below).
- **Candidates:** the CEC's candidate files (`info.cec.gov.tw/vote2026/static/json/cand/C1/<county code>.json`) are up. All 22 races match our names and ballot numbers (checked 11/10).
- **Same night:** one national referendum (廢除非核家園, 第22案). 2022 also had one referendum; its count ended at 23:40.

## The pipeline (built 11/10)

```
CEC count site --(every 60 s)--> scripts/live/poll.py --> live-out/needle/2026-mayors.json --> scripts/live/publish.py --> election-2026.tw
                                   | archive of every snapshot (live-out/archive/)                 (npx wrangler deploy)       page refetches every 30 s
```

- **`scripts/live/cec_parse.py`** reads the candidate and turnout pages.
- **`scripts/live/live_model.py`** runs the needle on town totals (the replay's "district feed"). Two approximations, both tested:
  - The counted part of a town gets an elector count corrected for the fact that early stations are small. On the 2018/2020/2022/2024 nights the counted stations held about 75% of their average share early in a town's count; `SIZE_H`.
  - The uncounted part splits the rest of the town's electors.
  - "Decided" needs the lead to beat the largest stations each town could still have out, from 2022's sizes plus 10%.
- **`scripts/live/poll.py`** fetches with conditional requests, 4 at a time, with timeouts and retries. A page that fails keeps its last good value. It applies the contender rules:
  - 金門's "other" is whoever leads among non-KMT candidates.
  - 花蓮's "other" is whichever independent leads. No race is set as three-way in advance (decided 11/13, including 花蓮).
  - Any race goes three-way once 5% is in if a third candidate is in the top two or within 10 points of the leader.
  - When a race's contenders change, its points are recomputed from the archive. `--rebuild` recomputes the whole night after a fix.
- **`scripts/live/publish.py`** checks each new file before it goes up: it parses, has all 22 races, and no count went backwards. It then deploys at most every 45 s.
- **The page** (`live-template.html`) fetches the file again every 30 s and follows the latest moment. A slider looks back over the count (it never plays), and "Live" returns to now. It shows "Updated hh:mm:ss · CEC count", and warns if nothing new arrives for 5 minutes while races are still undecided.
- **`scripts/live/mock_cec.py`** is a stand-in count site for rehearsals: the 2022 count replayed on the 2026 ballot, at any speed, in either markup, with optional failures (`--fail 0.03`).

**Tests**
- `python3 tests/test_live.py`: parser, town map, one full race.
- `python3 scripts/live/replay_live.py`: scores against the replays. Town totals match the replay's district feed: log loss at 1/5/10/30% counted 0.44 / 0.22 / 0.14 / 0.08, against 0.37 / 0.14 / 0.13 / 0.07 with per-station results.
- `python3 scripts/live/check_certainty.py`: 43 races, never "decided" early or on the wrong side; on average 14 stations after the truth.
- Rehearsal on 11/10: mock site at 60× with 3% failures → poller every 10 s → publisher → local site. The page followed the count, kept a reader's look-back position across refreshes, and returned with "Live". No errors.

### Readiness check, 11/17 (from Hope's browser, outside Taiwan)

| Source | What we saw | Next |
|---|---|---|
| CEC count site `vote.cec.gov.tw` | Every path, including `/robots.txt`, returns 403 "FORBIDDEN" from server `HiNetCDN`. On 11/10 the same address forwarded to the CEC's 2026 election page. The friend's browser in Taiwan gets the same 403 (11/17), so it's a lock on the whole site before launch, not (or not only) a block on visitors outside Taiwan. Whether it also blocks foreign visitors once it opens is still unknown. | When the CEC announces the site: friend and Hope both open it. If only the friend gets through, the night must run from her machine (planned anyway). Then set `count_base` in `data/live/night-config.json` and she reruns the check. |
| CEC candidate files `info.cec.gov.tw/vote2026/` | Load normally. 臺南市's council file is now up (patched in). | none |
| 中央社 | `cna.com.tw/project/20261128-election-live/` and its `api/*.json` are 404; the home page links only a news topic. In 2022 and 2024 the page went up about 3 days before the vote. | Check again 11/25. |
| 公視 | `news.pts.org.tw/projects/2026-election/election/` is up, showing placeholder figures (e.g. "全國開票進度：80%"). No data file loads yet; its scripts reference only build metadata. | Check again 11/25; look for the feed and `tv/` files. |
| 自由時報 | `election.ltn.com.tw/2026/` is up; its "開票實況" link has no address yet; `/2026/realtime` is 404. | Check again 11/25. |
| 聯合報 | `udn.com/vote2026/realtime` ("即時選情") is a news list, not counts. | Check again 11/25. |

**11/23 evening:** the friend's Mac passed `deploycheck` (ALL GOOD: it published to election-2026.tw and read its marker back), and her rerun rehearsal published to https://twn-watch-party-2026-test.hope770310.workers.dev/live, which advanced with the replay (checked from Hope's browser). The address line had been missing because publish.py dropped a successful deploy's output; fixed the same evening.

**11/27, 00:20:** the count host still answers 403 FORBIDDEN (from Taiwan too); search engines index vote.cec.gov.tw/zh-TW/index.html as the CEC's 計票資訊查詢網站 (with 2025's referendum), so the pre-set address is very likely right. 中央社: no web count page announced, only a YouTube live stream 16:00–18:30. 公視: its results page now reads `news.pts.org.tw/projects/2026-election/api/public/election/2026/mayors`, the CEC's media feed per county (test figures stamped 11/18 until the night); switched on as count-watch source "公視" (`pts_api`, ignores data stamped before 11/28 16:00), on main and the night branch. 自由時報: 開票實況 link still empty. 聯合報: 即時選情 is news.

**11/23:** the count host still answers 403 FORBIDDEN from Hope's browser. A CEC briefing reported on 11/12 (udn) says the count-information site runs on several domestic mirrors (HiNet CDN) plus an overseas backup mirror (AWS CDN); whether visitors abroad get the AWS mirror or a block is still unknown. `night-check.txt` is not on election-2026.tw, so the deploy check from the friend's Mac has not succeeded yet (or not been run).

### Other outlets (built 11/11)

`scripts/live/outlets.py`, switched on by settings (`data/live/outlets.json`), not code. An outlet is read once its `url` is set. The poller re-reads the settings every 5 minutes: first the copy on the repository's `night` branch, then the local one. So an address found on the night can be added from anywhere, and the friend's computer picks it up without a restart. Pushing to the `night` branch doesn't redeploy the site: **checked 11/18** in Workers Builds (production branch `main`; "Builds for Preview branches" off), and the branch was created from `main` the same day. On the night, change only `data/live/outlets.json` there (GitHub's web editor is enough); raw.githubusercontent.com can take up to about 5 minutes to serve the change, then the poller's next settings read picks it up.

| Kind | What it reads | 2022 / 2024 example | Used for |
|---|---|---|---|
| `cna` | 中央社's JSON: per county, ballot number and votes, % of stations in | `cna.com.tw/project/20221126-election-live/api/city.json` | count watch (reliable) |
| `cec_feed` | the CEC's own media feed as 公視 republished it: `{"ST", "TC": [...], "T1": [...]}` with stations sent/total per town and district | 公視 2022: `d3prffu8f9hpuw.cloudfront.net/campaign-2022/assets/data/final.json` (end-of-night copy; the in-count file name is unknown); 2024: `.../2024-election-vote/vote/p1-63-000.json` | **fallback for the CEC's numbers**: needle and councils |
| `tv_json` | TV channels' on-screen counts keyed by candidate name | 公視 2024: `.../2024-election-vote/tv/latest.json` (2022's local-election page had none) | count watch, one row per channel |
| `page_text` | any page printing names then votes; optional split at channel names | 自由時報 2022 realtime pages (東森, 民視, 台視, CEC); 聯合報 | count watch (crude; readings checked) |

**Fallback.** For each town, county and council district, the poller takes whichever source has more stations in: the CEC's page or the feed. If the CEC's count site goes down, the needle and councils carry on from the feed. This was rehearsed with `mock_cec.py --down`.
- The feed has no names. Mayoral names come from the ballot.
- A council district falls back only after its CEC page has been read once, because its candidates' names and sex come from that page.
- When the CEC site fails, the poller tries the rest of its pages once each without retries, so a cycle still takes seconds.

**Checks.** A reading counts only if it covers both contenders and no candidate has more votes than the race has electors. Readings are stored as they change, with the time of the CEC's latest page, in `live-out/outlets-state.json`, and picked up again after a restart.

**The page.** The count watch now works for two-way races too:
- It shows the floor (the highest reliable count), the field (other sources, range and mean), and the projected final with its 80% range. Two-way races use half the projected two-way total, plus or minus half the projected margin; the range combines margin and turnout.
- It appears for races with outlet readings. Before the count, a placeholder says what will appear. After the count starts with no outlets, it doesn't show at all.
- "Reliable" means the CEC, 中央社, and 公視's or 華視's own counts. Everything else is "field".

**Mock.** `mock_cec.py` serves all three JSON kinds from the same 2022 count:
- 中央社 one minute behind.
- TV counts 5–10 minutes ahead, and inflated early for 三立 and 民視.

The rehearsal and the check use `data/live/outlets-mock.json`.

### Rehearsal on 11/18 (container, mock at 60×, 2025 markup, 3% failures, CEC down from 18:30, poller killed and restarted)

No errors. The poller resumed from its archive and carried on from the outlet feed once the CEC was down (all 368 towns); publishing never refused a file. Cycles took about 47 s with the CEC up (≈640 pages, every page changing at 60×) and 18–48 s with it down, the spread being the mock's 20 s stalls against the 15 s timeout. The page in live mode, then `finalize.py` and the page as a replay: no errors.

### Running it

```sh
# once, on the machine that runs the night (repository at the frozen commit)
pip install --break-system-packages openpyxl xlrd   # what scripts/stations.py needs to read the CEC station files
python3 scripts/build_site.py _site
export CLOUDFLARE_API_TOKEN=...  CLOUDFLARE_ACCOUNT_ID=...    # a token that can deploy this Worker
python3 scripts/live/poll.py --probe --base https://<count host>/zh-TW/    # when the site is announced: must parse

# the night (two terminals; start by 15:30)
python3 scripts/live/poll.py --base https://<count host>/zh-TW/
python3 scripts/live/publish.py --deploy

# rehearsal (three terminals): stand-in site, poller, publisher into a local copy
python3 scripts/live/mock_cec.py --speed 16 --start 16:00 --fail 0.03
python3 scripts/live/poll.py --base http://127.0.0.1:8790/zh-TW/ --interval 20
python3 scripts/live/publish.py            # copies into _site; serve _site with python3 -m http.server
```

**Rules for the night**
- No pushes to GitHub after the code freeze. A push makes Cloudflare rebuild the site from the repository, which would put the empty pre-count file back until the next publish (about a minute). It could also mismatch the code the publisher deploys.
- The publisher deploys the local `_site`, so that copy must be built from the same commit as the site.

## Not built yet

- ~~Council seats live~~ **built 2026-11-11** (`scripts/live/council_live.py`): one CEC page per council district (221, from the CEC's 2026 candidate files; 臺南市's file appeared by 11/17: same 13 districts and towns as 2022, but one seat moved from district 1 (now 5) to district 11 (now 6); patched 11/17). The page enables its Council view once the first district reports, and refetches the council file with the mayors'. No model: the page shows who would hold each seat if counting stopped, as on the replays; "decided" uses a generous estimate of the votes still out.
- ~~Count watch~~ **built 2026-11-11**; see "Other outlets" below. Each outlet's 2026 address is still to find once its page is up.
- **Turnout view on 2026:** works from the same points; checked only in the rehearsal.

## Timeline

| When | What | Who | Status |
|---|---|---|---|
| done 11/10 | Poll figures removed from the site and the repository's current files (ban 11/18 00:00 – 11/28 16:00, 選罷法 §53) | Claude | done |
| done 11/10 | Candidate names and ballot numbers checked against the CEC's candidate files: all 22 match | Claude | done |
| done 11/10 | Mayoral pipeline: parser, live model, poller, publisher, page live mode, stand-in site, tests, first rehearsal | Claude | done |
| by 11/14 (Sat) | Decide where it runs on the night (a Taiwan-located machine is safest; see below) and set up a Cloudflare deploy token there | Hope | open |
| done 11/11 | Council seats live (built, rehearsed with the 2022 count) | Claude | done |
| by 11/21 (Sat) | Full rehearsal on the machine that will run the night, deploying to a test Worker, not the real site | both | open |
| ~11/21 (unverified) | CEC announces the count site: `poll.py --probe` from the night's machine; refresh `towns-2022.json` from the 2026 site menu if towns changed | Claude + Hope | open |
| by 11/24 | Taiwanese review back (`docs/taigi-review.md`) | Hope | done 11/26 ("good"); the draft notes are removed from the site |
| 11/25 (Wed) | Recheck outlet pages. **11/25 midday:** 中央社's `project/20261128-election-live/` and its data files still 404 (no other link from its topic page); 公視's page still marked 測試版 with no data file. Check again 11/27 and on the night (the `night` branch lets us switch one on without a deploy) | Claude | partly |
| 11/25 (Wed) | CEC announced elector totals on 11/24 (19,576,028 for mayors). Now in `data/2026-electors.json` → `2026-mayors.json` (`electors`; the 2022 figure kept as `electors_2022`). The poller scales each county's 2022 town electors to the new total until the turnout pages give each town's own figure | Claude | done 11/25 |
| by 11/24 | `TWN_MODE=deploycheck` on the night's machine: republishes the site as it is to election-2026.tw (no visible change) and confirms the real site took it, via a random marker file `night-check.txt` | friend | open |
| 11/26 (Thu) | Dress rehearsal on the real domain at 16× (16:00–24:00 in 30 min), phones and desktop, all three languages; then rebuild the empty pre-count file | both | open |
| 11/28 (Sat), morning | Code freeze moved here (Hope, 11/26): Hope and the friend start the night machine together that morning; Hope's Mac runs `TWN_MODE=standby` as the backup. The count site address is pre-set to `https://vote.cec.gov.tw/zh-TW/` (the CEC's host in 2022–2025); a different address can be set as `count_base` in `data/live/outlets.json` on the `night` branch and the poller switches within ~10 minutes, no restart | both | open |
| 11/28, 14:00 | Poller and publisher running (the count site has no data yet: the poller just waits) | Hope | |
| 11/28, 16:00 | Voting closes, counting starts | | |
| 11/28, ~17:00–17:30 | First CEC figures; first needle points | | |
| 11/28, ~17:40 | Half the races have their first 1% in (2022: 17:38; 2018: 17:52) | | |
| 11/28, ~18:00–20:00 | Most needles settle (replays: above 95% for the eventual winner typically 1–2 hours before the race is mathematically decided) | | |
| 11/28, ~21:00–24:00 | Last mayoral races decided (2022: count over at 23:40 with one referendum) | | |
| 11/29 (Sun) | Copy `~/twn-night/live-out` from the night's machine (zip it; keep the archive). `python3 scripts/live/finalize.py --src <that folder>` turns the live files into the 2026 replay (refuses until every race is decided); rebuild, check, push. The landing page and the results page switch their wording by themselves (before / live / after, from `needle/2026-status.json` and the 2026 file); still to rewrite by hand: the landing page's "Live results" paragraph (name the outlets actually used, past tense) and the 台文 footer note once the review is in | both | |
| after certification (unverified: about a week) | Score 2026 against the certified results; add it to the accuracy section | Claude | |

## Open decisions

- **A backup machine, and what it can carry over.** A second machine started mid-night (`TWN_MODE=night`) reads the CEC from that moment: the needles and counts are right, but the charts' history on the site starts at the handover, because the archive stays on the first machine. Carrying the published history over is buildable (seed from the live file); worth it only if there is a backup machine. **Hope, 11/18:** decide after seeing whether the CEC's count site answers machines outside Taiwan.
- ~~The orange "District totals only" notice~~ **done 11/18:** now a grey note ("Town totals only: …").

- **Where the poller runs.** If the CEC limits access by location, a machine outside Taiwan gets nothing. Options:
  - A small cloud server in Taiwan (Google Cloud's asia-east1 region is in Taiwan; a few dollars for the week).
  - A friend's computer in Taiwan.
  - Hope's Mac if he's in Taiwan that night.
  - Whichever is chosen, keep a second machine ready to take over, since the archive lets a new poller pick up where the old one stopped.
- ~~Model: sampling noise in tiny first stations~~ **applied 2026-11-11** (docs/needle.md, "Model review"); replays and the accuracy figures rebuilt.
- Count-watch sources (above).
