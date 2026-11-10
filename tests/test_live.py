#!/usr/bin/env python3
"""Checks for the election-night pipeline. Run: python3 tests/test_live.py

  * the CEC page parser on saved 2022 pages (class-based markup) and the 2025 referendum page (id-based);
  * the town map covers every 2022 district name in the station data;
  * the live model on a full 2022 race rebuilt as town snapshots ends with the right winner, decided.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "live"))
import cec_parse as P  # noqa: E402

F = ROOT / "tests" / "fixtures" / "cec"


def test_parser():
    c = P.parse_count((F / "TC-10013000000000000.html").read_text())
    assert (c["sent"], c["total"]) == (711, 711)
    assert [(r["no"], r["name"], r["votes"]) for r in c["rows"]] == [(1, "詹智鈞", 19156), (2, "蘇清泉", 206460), (3, "周春米", 217537)]
    assert c["updated"] == "11/26 23:53:49"
    t = P.parse_count((F / "TC-10013000100000000.html").read_text())
    assert t["sent"] == 137 and "屏東市" in t["title"]
    s = P.parse_turnout((F / "SC-63000000000000000.html").read_text())
    assert s["rows"][0] == {"area": "總計", "E": 2026769, "C": 1372179, "A": 1360951, "invalid": 11228}
    assert len(s["rows"]) == 13
    assert P._sent((F / "F1-2025-referendum.html").read_text()) == (17832, 17832)


def test_towns():
    import stations as ST
    towns = json.loads((ROOT / "data" / "live" / "towns-2022.json").read_text())["counties"]
    for county, race in ST.load("2022-mayors").items():
        assert {s["district"] for s in race["stations"]} == {n for _, n in towns[county]["towns"]}, county


def test_live_race():
    import warnings
    warnings.filterwarnings("ignore")
    import needle as N
    import stations as ST
    from live_model import LiveRace
    from replay_live import snapshot, towns_of
    race = ST.load("2022-mayors")["屏東縣"]
    ns = N.Night("2022-mayors", "屏東縣", "2018-mayors+2020-president")
    nos = [c["no"] for c in race["cands"]]
    towns = towns_of(race)
    lr = LiveRace("屏東縣", "2018-mayors+2020-president", nos, nos[ns.ia], nos[ns.ib], towns)
    e = lr.estimate(lr.load(snapshot(ns.st, nos, {d: v["N"] for d, v in towns.items()})))
    assert e["certain"] and e["p"] == 0.0  # 周春米 (other side) won
    half = lr.row(300, snapshot(ns.st[:350], nos, {d: v["N"] for d, v in towns.items()}))
    assert half[1] == 350 and 0 <= half[4] <= 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
