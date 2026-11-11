#!/usr/bin/env python3
"""Checks for the election-night pipeline. Run: python3 tests/test_live.py

  * the CEC page parser on saved 2022 pages (class-based markup) and the 2025 referendum page (id-based);
  * the town map covers every 2022 district name in the station data;
  * the live model on a full 2022 race rebuilt as town snapshots ends with the right winner, decided;
  * the outlet readers on small samples in the formats seen in 2022 and 2024 (中央社, the CEC feed via 公視,
    公視's TV counts, a plain page), and the checks that throw out implausible readings.
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
    k = P.parse_count((F / "T1-63000011100000000.html").read_text())  # a council page: seats, women's seats, sex
    assert (k["seats"], k["women"], k["sent"]) == (12, 3, 182) and k["rows"][0]["sex"] == 2 and k["rows"][1]["sex"] == 1


def test_council_list():
    spec = json.loads((ROOT / "data" / "live" / "council-2026.json").read_text())["counties"]
    assert len(spec) == 22 and sum(len(c["districts"]) for c in spec.values()) == 221
    for c in spec.values():
        for d in c["districts"]:
            assert len(d["page"].split("/")[1]) == 17 + 5 and d["electors_est"] > 0


def test_towns():
    import stations as ST
    towns = json.loads((ROOT / "data" / "live" / "towns-2022.json").read_text())["counties"]
    for county, race in ST.load("2022-mayors").items():
        assert {s["district"] for s in race["stations"]} == {t[1] for t in towns[county]["towns"]}, county


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


def test_outlets():
    import tempfile
    from outlets import Outlets
    races = [{"area": "臺北市", "electors": 2000000, "blue": {"no": 5, "name": "蔣萬安"}, "other": {"no": 3, "name": "沈伯洋"}},
             {"area": "花蓮縣", "electors": 260000, "blue": {"no": 1, "name": "甲"}, "other": {"no": 2, "name": "乙"}, "third": {"no": 3, "name": "丙"}}]
    ballots = {"臺北市": {"蔣萬安": {"no": 5}, "沈伯洋": {"no": 3}, "某甲": {"no": 1}},
               "花蓮縣": {"甲": {"no": 1}, "乙": {"no": 2}, "丙": {"no": 3}}}
    with tempfile.TemporaryDirectory() as d:
        o = Outlets(d, races, ballots)
        o.set_counties({"臺北市": {"code": "63000", "en": "Taipei City"}, "花蓮縣": {"code": "10015", "en": "Hualien County"}})
        cfg = {"id": "cna", "kind": "cna", "label": "中央社", "en": "CNA", "cohort": "reliable"}
        res = o.cna(cfg, json.dumps({"63000": {"code": "63000", "process": 10, "candidates": [
            {"candNo": 5, "tickets": 1000}, {"candNo": 3, "tickets": 900}, {"candNo": 1, "tickets": 5}]}}))
        assert res[0][1] == {"臺北市": {5: 1000, 3: 900, 1: 5}}
        tv = o.tv_json({"id": "tv", "channels": {"公視": {"id": "pts", "en": "PTS", "cohort": "reliable"}}}, json.dumps({"data": {
            "公視": [{"vote_name": "蔣萬安", "vote_count": 1100}, {"vote_name": "沈 伯洋", "vote_count": 950}],
            "三立": [{"vote_name": "蔣萬安", "vote_count": 1300}, {"vote_name": "沈伯洋", "vote_count": 1200}]}}))
        assert {m["id"]: (m["cohort"], r) for m, r in tv} == {"tv-pts": ("reliable", {"臺北市": {5: 1100, 3: 950}}),
                                                              "tv-三立": ("field", {"臺北市": {5: 1300, 3: 1200}})}
        pg = o.page_text({"id": "ltn", "label": "自由", "split": ["東森", "民視"]},
                         "<div>東森</div><td>蔣萬安</td><td>1,234</td><td>沈伯洋</td><td>1,100</td><p>民視</p>蔣萬安 1,240 沈伯洋 1,090", "臺北市")
        assert [r for _, r in pg] == [{"臺北市": {5: 1234, 3: 1100}}, {"臺北市": {5: 1240, 3: 1090}}]
        o.cec_feed({}, json.dumps({"ST": "1128183005", "TC": [
            {"prvCode": "63", "cityCode": "000", "deptCode": None, "areaCode": None, "candTksInfo": [{"candNo": 5, "tks": 10}],
             "tboxTot": 1755, "tboxRcv": 40, "prof3": 20, "prof7": 2026769},
            {"prvCode": "63", "cityCode": "000", "deptCode": "010", "candTksInfo": [{"candNo": 5, "tks": 7}], "tboxTot": 134, "tboxRcv": 3}],
            "T1": [{"prvCode": "10", "cityCode": "015", "areaCode": "10", "deptCode": None, "candTksInfo": [{"candNo": 1, "tks": 4}],
                    "tboxTot": 30, "tboxRcv": 2}]}))
        fb = o.fallback
        assert fb[("TC", "63000", "000")]["sent"] == 40 and fb[("TC", "63000", "010")]["votes"] == {5: 7}
        assert fb[("T", "T1/10015100000000000.html")]["total"] == 30 and fb["stamp"] == "11/28 18:30:05"
        # storing: a reading missing a contender, or above the electors, is dropped; unchanged readings aren't repeated
        assert o._store(res[0][0], {"臺北市": {5: 1000}}, 100) is False
        assert o._store(res[0][0], {"臺北市": {5: 3000000, 3: 1}}, 100) is False
        assert o._store(res[0][0], res[0][1], 100) is True and o._store(res[0][0], res[0][1], 101) is False
        assert o._store(res[0][0], {"臺北市": {5: 1500, 3: 1400}}, 102) is True
        src = o.sources(races[0])
        assert src[0]["series"] == [[100, 1000, 900, None], [102, 1500, 1400, None]] and src[0]["seen"] == 102
        assert o.sources(races[1]) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
