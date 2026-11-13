# Election night plan: 2026-11-28

Written 2026-11-10, updated the same day once the mayoral pipeline was built. All times are Taiwan time (UTC+8). "Unverified" means a date or fact we believe but haven't confirmed from an official source.

## What we know about the CEC's live count

- **Where:** the CEC's count site (計票資訊查詢網站). In 2025 it was `vote.cec.gov.tw/zh-TW/` (the referendum page `F1/00000000000000000.html`). Today that address forwards to the CEC's 2026 election page, so the count site isn't up yet. Another 2026 project reports that it's announced about a week before the vote (unverified).
- **Level:** the county and each town (鄉鎮市區), not polling stations. Each page gives every candidate's votes so far and the number of stations reported (已送/應送). Pages per cycle: 22 county + 368 town candidate pages (prefix `TC`) and 22 turnout pages (`SC`). The page code is county(5) + `00` + town(3) + `0000000`; the 2022 codes are in `data/live/towns-2022.json`, from the CEC's own 2022 site menu.
- **Markup:** changed between 2022 (class-based) and 2025 (id-based). The parser reads tables by their header labels, and works on saved pages of both (`tests/fixtures/cec/`, copies from the Wayback Machine collected by github.com/outsider987/vote, MIT).
- **Location:** the same project advises polling "from a Taiwan-located machine because the CEC may geo-limit" (unverified). From Hope's browser today, the CEC's 2026 election page loads; the count site itself isn't up to test.
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

### Other outlets (built 11/11)

`scripts/live/outlets.py`, switched on by settings (`data/live/outlets.json`), not code. An outlet is read once its `url` is set. The poller re-reads the settings every 5 minutes: first the copy on the repository's `night` branch, then the local one. So an address found on the night can be added from anywhere, and the friend's computer picks it up without a restart. Pushing to the `night` branch doesn't redeploy the site, because Cloudflare deploys only from `main`. **Check that in the Workers Builds settings before relying on it.**

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

- ~~Council seats live~~ **built 2026-11-11** (`scripts/live/council_live.py`): one CEC page per council district (221: the CEC's 2026 candidate files list 208; 臺南市's file isn't published yet, so its 13 districts come from 2022 — check when the CEC posts it). The page enables its Council view once the first district reports, and refetches the council file with the mayors'. No model: the page shows who would hold each seat if counting stopped, as on the replays; "decided" uses a generous estimate of the votes still out.
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
| by 11/24 | Taiwanese review back (`docs/taigi-review.md`, regenerated 11/10) | Hope | open |
| 11/25 (Wed) | CEC announces elector totals (選罷法 §38). The poller takes town electors from the turnout pages on the night anyway; update `2026-mayors.json` for the before-count page | Claude | open |
| 11/26 (Thu) | Dress rehearsal on the real domain at 16× (16:00–24:00 in 30 min), phones and desktop, all three languages; then rebuild the empty pre-count file | both | open |
| 11/27 (Fri), evening | Code freeze; final build on the night's machine; fallback machine ready | both | open |
| 11/28, 14:00 | Poller and publisher running (the count site has no data yet: the poller just waits) | Hope | |
| 11/28, 16:00 | Voting closes, counting starts | | |
| 11/28, ~17:00–17:30 | First CEC figures; first needle points | | |
| 11/28, ~17:40 | Half the races have their first 1% in (2022: 17:38; 2018: 17:52) | | |
| 11/28, ~18:00–20:00 | Most needles settle (replays: above 95% for the eventual winner typically 1–2 hours before the race is mathematically decided) | | |
| 11/28, ~21:00–24:00 | Last mayoral races decided (2022: count over at 23:40 with one referendum) | | |
| 11/29 (Sun) | Final snapshot; switch 2026 from live to a replay; keep the archive | both | |
| after certification (unverified: about a week) | Score 2026 against the certified results; add it to the accuracy section | Claude | |

## Open decisions

- **Where the poller runs.** If the CEC limits access by location, a machine outside Taiwan gets nothing. Options:
  - A small cloud server in Taiwan (Google Cloud's asia-east1 region is in Taiwan; a few dollars for the week).
  - A friend's computer in Taiwan.
  - Hope's Mac if he's in Taiwan that night.
  - Whichever is chosen, keep a second machine ready to take over, since the archive lets a new poller pick up where the old one stopped.
- ~~Model: sampling noise in tiny first stations~~ **applied 2026-11-11** (docs/needle.md, "Model review"); replays and the accuracy figures rebuilt.
- Count-watch sources (above). 臺南市's 2026 council districts once the CEC posts them.
