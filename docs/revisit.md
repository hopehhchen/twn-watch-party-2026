# Decisions to revisit

Things set aside on purpose, to look at again before 2026-11-28. Newest first.

## Before the night: official CEC releases to check

- **Candidate list and ballot numbers.** `scripts/build_2026_night.py` has them from 中央社 (2026-10-27), read off the page automatically. Check every name and number against the CEC's own announcement of the candidate list (and the 選舉公報) when it comes out, then rebuild. My understanding is that the CEC announces the list the day before the campaign period starts (選罷法 §34; the mayoral campaign period is 10 days, so around 11/17), but I haven't confirmed the article or the date.
- **Elector totals.** Announced three days before the vote (選罷法 §38), so by 11/25: city- and county-wide totals, not per station. Replace the 2022 electors in `data/needle/2026-mayors.json` with them.
- **Model:** keep as is (decided 2026-11-10) until there's a better idea than the ones tested in `docs/needle.md` "Model review".

## Council page

- **Ordering districts by closest seat line** (removed 2026-11-10). The council page had a "Closest seat line" order for a county's districts, and a nationwide "Closest seat lines right now" list under the seat tally. Both are gone for now. Open questions:
  - Is a closest-seat-line view worth the space?
  - What should "closest" mean? The removed version used the gap between the last candidate in and the first out, divided by votes per seat counted so far, among districts at least half counted. Early in the night it surfaced 3-vote gaps that meant little.
  - The code is in git history: commit f221719, `site/council-template.html` (since merged into `site/live-template.html`), functions `closest` and `closeList`.
- **One timeline with the needle page** (done 2026-11-10: "Show: Council" on the results page).

## Needle page

- **National panel** (added 2026-11-10): on phones the 2024 version (dial, two charts, count watch) is long before the map. Consider collapsing the charts or the count watch there.
- **Count watch** now uses bars plus a collapsible per-source table. Check that the old table isn't missed.
- Control bar: the turnout slider, feed switch and jitter checkbox were removed 2026-11-10 (live turnout only; feed chosen by what the CEC provides; needle motion always on, off for reduced-motion).
- Needle motion on the small card dials: not added. With 22 races updating at once during playback, every card would be moving; the big dials (national, race panel) have it.
- Votes vs points switch on the margin chart: keep one?
- Dial left/right vs chart top/bottom orientation: make consistent.
- Chance chart centre label: "50–50" (current) vs "0".
- Shorten four-character names; English/Chinese language switch.
- Page size: done 2026-11-10 (nights load on demand; live.html ~150 KB).

## Parties

- **Council tallies for smaller parties** (2026-11-10): no separate tallies for now (the user will ask a wider group of testers). 台灣基進 and 親民黨 have their own colors, but in the council tally they count under "other parties" with the rest. Councilors-elect from parties without one: 2018: 親民黨 8, 無黨團結聯盟 5, 台灣團結聯盟 5, 民國黨 3, 綠黨 3, 新黨 2, 勞動黨 2, 社會民主黨 1, 中華民族致公黨 1; 2022: 無黨團結聯盟 7, 台灣團結聯盟 3, 親民黨 2, 台灣基進 2, 新黨 1, 社會民主黨 1, 綠黨 1, 勞動黨 1, 正神名黨 1.
- **English party initials**: KMT, DPP, TPP, NPP, TSP, PFP, NP, NPSU, TSU, GPT, SDP, MKT, CUPP, Ind. Parties without established English initials keep their Chinese names.

## Entry page

- **Races to watch** (rewritten 2026-11-10 from news and analysts' previews): refresh the polls cited before the night. Polls by TVBS are not cited anywhere on the site (strong house effect, per the user); TVBS's on-screen vote counts stay in the count watch.
- **Credits**: draft in `docs/credits-draft.md`, not published.

## Language

- **Taiwanese (台文)** as a third language: built as a draft (selector label 台文 since 2026-11-10); review list in `docs/taigi-review.md`.
- **Candidate names in English mode** (built 2026-11-10): `data/names-en.json`, mayoral and presidential nights only; council and legislative candidates stay in Chinese. Wikipedia's candidate and results tables cite no sources, so names were checked against Focus Taiwan (CNA), Taipei Times and Legislative Yuan pages: all 2026 contenders are confirmed by CNA; 37 names from earlier nights (mostly 2018/2022 runners-up) rest on Wikipedia tables only. Decisions (2026-11-10) are listed in the file (`decisions`) and explained on the English pages. Possible follow-up: the CEC's archived English results pages seem to carry candidates' English names, which would be a better source for the earlier nights.
