# When is a race decided? (2026-11-09)

Three rules, checked against the CEC's own 2022 count with `scripts/clinch_replay.py`.

| Rule | Condition | Needs a turnout guess? |
|---|---|---|
| 50% line | leader > ½ × electors × turnout cap × valid share | yes, and it matters a lot |
| global cap | leader − runner-up > electors × cap × valid share − valid counted | yes |
| station cap | leader − runner-up > electors at uncounted stations × cap | barely; at 100% none at all |

The 50% line is sufficient, never necessary: with three or more serious candidates the winner may never reach it (臺北 2022: 蔣萬安 42.29%). The global cap is the same test as "2 × leader + all other non-runner-up votes > maximum total", so it covers multi-candidate races. The station cap swaps the citywide guess for the electors actually left at uncounted stations, which is what makes it tight.

## 2022 backtest (cap = turnout known before 2022)

"prev" is the race's 2018 turnout, σ is the spread of 2010–2018 turnouts (2009–2018 for 縣市).

| Race (winner's share) | 50% line @ prev+1σ | station cap @ prev+1σ | station cap @ 100% (certain) |
|---|---|---|---|
| 臺北市 (42.3%) | never | 20:07, 91.4% of stations in | 20:15, 93.8% |
| 新北市 (62.4%) | 20:27, 98.1% | 19:45, 85.5% | 19:52, 89.3% |
| 高雄市 (58.1%) | never (turnout fell to 58.6%) | 19:28, 89.6% | 19:35, 92.0% |
| 新竹市 (45.0%) | never | 20:42, 93.5% | 20:46, 95.5% |

Times are when the stations' reports were logged by the CEC (rounded up to the minute); they cover all nine contests, so they are "no earlier than" times.

Take-aways:
- The turnout assumption barely moves the station-cap rule: going from prev+1σ to 100% (no assumption) costs 4–8 minutes.
- Any rule that is *certain* is late (~90% counted), because it allows every remaining vote to go to the runner-up.
- For an earlier, honest signal, show how much of the remaining vote the runner-up would need. 臺北 2022, with 蔣 keeping his 42.5%: 陳時中 needed ~52% of the rest at 19:00 (he was getting 32%), ~72% at 19:30, and more than 100% by 20:00.
