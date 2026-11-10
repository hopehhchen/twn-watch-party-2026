# Decisions to revisit

Things set aside on purpose, to look at again before 2026-11-28. Newest first.

## Council page

- **Ordering districts by closest seat line** (removed 2026-11-10). The council page had a "Closest seat line" order for a county's districts, and a nationwide "Closest seat lines right now" list under the seat tally. Both are gone for now. Open questions:
  - Is a closest-seat-line view worth the space?
  - What should "closest" mean? The removed version used the gap between the last candidate in and the first out, divided by votes per seat counted so far, among districts at least half counted. Early in the night it surfaced 3-vote gaps that meant little.
  - The code is in git history: commit f221719, `site/council-template.html`, functions `closest` and `closeList`.
- **One timeline with the needle page.** The council page has its own replay controls. Consider merging both pages into a single replay with a "Show: Council" option.

## Needle page

- **National panel** (added 2026-11-10): on phones the 2024 version (dial, two charts, count watch) is long before the map. Consider collapsing the charts or the count watch there.
- **Count watch** now uses bars plus a collapsible per-source table. Check that the old table isn't missed.
- Control bar is busy. The turnout scenario slider is possibly redundant now that "Live" works.
- Votes vs points switch on the margin chart: keep one?
- Dial left/right vs chart top/bottom orientation: make consistent.
- Chance chart centre label: "50–50" (current) vs "0".
- Shorten four-character names; English/Chinese language switch.
- Page size (~2 MB): load nights lazily, as the council page does.
