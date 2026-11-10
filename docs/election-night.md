# Election night plan: 2026-11-28

Written 2026-11-10. All times are Taiwan time (UTC+8). "Unverified" means a date or fact we believe but haven't confirmed from an official source.

## Where things stand

Done: the 2026 page before the count (contenders, ballot numbers, incumbents, hatched map), four replayed nights, the model, the About page, the domain.

**Not built yet, and the critical path:** nothing on the site updates by itself. The page already loads `needle/2026-mayors.json` (and the council file) at runtime, so the night needs something that keeps those files fresh:

1. **Read the live count.** Find where the CEC publishes the 2026 count, in what format, how often, and at what level (per polling station, or only per township). Per-station data keeps the model at full strength; township totals still work, but the needle settles later (`docs/needle.md`, "Feed granularity"). Also check whether the CEC site is reachable from outside Taiwan on the night: unverified either way.
2. **Turn it into needle points.** Run `scripts/needle.py` on each new snapshot and append points in the same columns as the replayed nights; same for council seats.
3. **Publish the files.** A push to GitHub triggers a full Cloudflare build (about a minute, one at a time), which is too slow to repeat every minute. Proposed: write the live JSON to Cloudflare storage (R2 or KV) behind the existing Worker, with a 15–30 s cache.
4. **Live mode on the page.** Poll every 30 s; follow the real clock; unfreeze the 2026 view when the first points arrive; show "updated hh:mm"; warn if the data goes stale (say, nothing new for 5 minutes during the count).
5. **Other live sources** (the count watch). Find which outlets put up 2026 live pages or endpoints (in past cycles 中央社 and 公視 did), test them, and name them on the page only once they work.
6. **Where it runs.** Steps 1–3 need a machine that stays on through the night: most likely Hope's Mac, on power, sleep off, plus a fallback. This cloud workspace can't hold a long-running job.

## Timeline

| When | What | Who | Status |
|---|---|---|---|
| by 11/14 (Sat) | Find the CEC 2026 live results source and its format; decide the publishing setup (step 3) and where it runs | Claude researches, Hope decides | open |
| by 11/17 (Tue), 23:59 | **Take every poll number off the site.** Taiwan bans publishing, citing or commenting on election polls from 10 days before the vote until voting closes (公職人員選舉罷免法 §53; fines from NT$100,000). Here that runs 11/18 00:00 to 11/28 16:00. On the About page that means the poll lines in "Races to watch" and their links (蘇/李 numbers, the 28% line, the two poll sources), and the "Polls … credited where they appear" line in the credits | Claude edits, Hope approves | open |
| ~11/17 (unverified) | CEC announces the official candidate list. Check every name and ballot number against it, then rebuild (`scripts/build_2026_night.py`) | Claude | open |
| 11/18–11/27 | Campaign period. Poll ban in force | | |
| by 11/21 (Sat) | Live pipeline working end to end: replay 2022 through it as if live, to a test URL; page live mode working | Claude builds, Hope runs it on the Mac | open |
| by 11/21 | Count-watch sources picked and tested, if 2026 pages are up by then | Claude | open |
| by 11/24 | Taiwanese review back from reviewers (`docs/taigi-review.md`; regenerate it first) | Hope | open |
| 11/25 (Wed) | CEC announces elector totals, three days before the vote (選罷法 §38): city and county totals, not per station. Replace 2022's in `2026-mayors.json` | Claude | open |
| 11/26 (Thu) | Dress rehearsal on the real domain: full 2022 replay through the live path, on phones and desktop, both themes, all three languages; load check | both | open |
| 11/27 (Fri), evening | Code freeze: after this only data changes. Final rebuild; confirm the fallback machine | both | open |
| 11/28, 08:00 | Voting opens | | |
| 11/28, 14:00 | Pipeline up and polling; health checks; page still shows "before the count" | Hope | |
| 11/28, 15:30 | Final check; group chat open for reports from friends | Hope | |
| 11/28, 16:00 | Voting closes, counting starts. TV counts from about 16:00 | | |
| 11/28, ~17:00–17:30 | First CEC data usually reaches media; first needle points | | |
| 11/28, ~17:40 | Half the races have their first 1% of stations in (2022: 17:38; 2018: 17:52) | | |
| 11/28, ~18:00–19:00 | Most races pass 10–30% counted; needles settle in most races | | |
| 11/28, ~19:30 | TV channels switch to relaying the CEC (2024: from about 19:25) | | |
| 11/28, ~20:00–22:00 | Last mayoral races reach 70% (2022 median 19:53, latest 21:38); councils run later | | |
| 11/28, ~00:00 | Chart axis ends at 00:00 and extends if counting runs later | | |
| 11/29 (Sun) | Freeze the night: final snapshot, switch 2026 from live to replay, archive the raw feed; short note to friends | both | |
| after the CEC certifies results (unverified: about a week later) | Score 2026 against the certified results and add it to the accuracy section; review what broke | Claude | |

## On the night: watch for

- **Stale data:** no new CEC snapshot for 5 minutes while counting is under way.
- **Candidate mix-ups:** races are matched by ballot number, not name (`data/README.md`). One outlet attached minor candidates' counts to the wrong names in 2022.
- **Counts going backwards** in any source: hold the last good value and flag it.
- **Three-way races:** the watch list is set in advance (花蓮 expected). Switch a race to three-way live if a third candidate reaches the top two, or comes within 10 points of the leader, once 5% of stations are in (`docs/needle.md`).
- **Traffic:** static files on Cloudflare should hold. Keep the live JSON small and cached briefly.

## Open decisions

- Publishing setup for the live files (R2/KV behind the Worker, or something else).
- The machine on the night, and the fallback.
- Which outlets to show in the count watch.
- Whether to show council results live from the start, or only once the mayors are settled.
