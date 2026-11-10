#!/usr/bin/env python3
"""The 2026 night before any count: data/needle/2026-mayors.json.

  python3 scripts/build_2026_night.py

Every race with its two contenders (and the third in an expected three-way race) from
data/2026-contenders.json, ballot numbers from BALLOT below, and no points yet. Electors, stations and
"last time" turnout are 2022's (the CEC publishes 2026 elector totals three days before the vote, and
per-station counts not at all); incumbent = the 2022 winner, with their party now: the 2026 ballot's party when
they are running again, else INCUMBENT_PARTY below, else the party they won under.
On the night, the live pipeline appends points in the same columns as the replayed nights.
"""
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stations as ST  # noqa: E402
from build_needle_data import ORDER, TONE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PARTY_FULL = {"國民黨": "中國國民黨", "民進黨": "民主進步黨", "民眾黨": "台灣民眾黨", "無黨籍": "無黨籍"}
# Ballot numbers and parties (中央社 2026-10-27, https://www.cna.com.tw/news/aipl/202610275002.aspx). Checked
# 2026-11-10 against the CEC's own candidate files (info.cec.gov.tw/vote2026/static/json/cand/C1/<county code>.json):
# every name and ballot number matches; minor-party names follow the CEC's spelling.
BALLOT = {
    "臺北市": "1 台灣麻將最大黨 郭璽|2 無黨籍 林志成|3 民進黨 沈伯洋|4 臺灣SoR無法黨 蕭文乾|5 國民黨 蔣萬安|6 三勢團結促進聯盟 唐新民",
    "新北市": "1 民進黨 蘇巧慧|2 無黨籍 蘇輝湟|3 國民黨 李四川",
    "桃園市": "1 民進黨 黃世杰|2 國民黨 張善政",
    "臺中市": "1 民進黨 何欣純|2 司法正義黨 洪麗華|3 國民黨 江啟臣",
    "臺南市": "1 臺灣SoR無法黨 蕭燐洪|2 國民黨 謝龍介|3 民進黨 陳亭妃|4 無黨籍 葉人文",
    "高雄市": "1 司法改革黨 張靜|2 無黨籍 王肇民|3 國民黨 柯志恩|4 無黨籍 洪方隆|5 民進黨 賴瑞隆",
    "基隆市": "1 民進黨 童子瑋|2 無黨籍 魏造文|3 國民黨 謝國樑",
    "新竹市": "1 無黨籍 高虹安|2 無黨籍 何志勇|3 民進黨 莊競程",
    "新竹縣": "1 民進黨 鄭朝方|2 國民黨 徐欣瑩|3 無黨籍 朱定瑀",
    "苗栗縣": "1 民進黨 陳品安|2 國民黨 鍾東錦",
    "南投縣": "1 國民黨 許淑華|2 民進黨 温世政",
    "彰化縣": "1 民進黨 陳素月|2 國民黨 魏平政|3 無黨籍 邱建富|4 無黨籍 陳重嘉",
    "雲林縣": "1 無黨籍 吳炳輝|2 國民黨 張嘉郡|3 民進黨 劉建國|4 無黨籍 林佳瑜",
    "嘉義市": "1 無黨籍 王義成|2 無黨籍 陳愷璜|3 民眾黨 張啓楷|4 民進黨 王美惠|5 無黨籍 黃宏成台灣阿成世界偉人財神總統",
    "嘉義縣": "1 無黨籍 吳品叡|2 民進黨 蔡易餘",
    "屏東縣": "1 國民黨 蘇清泉|2 民進黨 周春米",
    "宜蘭縣": "1 民進黨 林國漳|2 無黨籍 陳宏毅|3 國民黨 吳宗憲|4 無黨籍 劉燦輝|5 無黨籍 楊鉯婷",
    "臺東縣": "1 無黨籍 李吳穎智|2 民進黨 陳瑩|3 無黨籍 王志偉|4 國民黨 吳秀華",
    "花蓮縣": "1 無黨籍 魏嘉賢|2 無黨籍 張峻|3 國民黨 游淑貞|4 台灣工黨 羅佩秦",
    "澎湖縣": "1 無黨籍 許智富|2 台聯黨 周倪安|3 無黨籍 葉竹林|4 民進黨 吳淑瑾|5 國民黨 陳振中|6 無黨籍 陳盡川",
    "金門縣": "1 無黨籍 張國威|2 無黨籍 李文良|3 無黨籍 洪和成|4 無黨籍 張火木|5 國民黨 陳玉珍|6 無黨籍 梁文韜|7 無黨籍 黃世團",
    "連江縣": "1 國民黨 王忠銘|2 無黨籍 曹爾元",
}
# Incumbents not on the 2026 ballot whose party has changed since 2022 (none found as of 2026-11-10; the ones running
# again take their ballot party: 新竹市 高虹安 台灣民眾黨 -> 無黨籍, 苗栗縣 鍾東錦 無黨籍 -> 中國國民黨).
# Checked 2026-11-10: 宜蘭 林姿妙 still KMT (suspended since her 2024 conviction; appeal verdict 2027-03-24);
# 澎湖 陳光復 still DPP (in hospital since 2026-02; vice magistrate 林皆興 acting; his wife 吳淑瑾 runs for the DPP).
# Both stay the incumbent: neither has left office.
INCUMBENT_PARTY = {}
END = 8 * 60  # 00:00; extended live if the count runs later


def ballot(area):
    out = {}
    for item in BALLOT[area].split("|"):
        no, party, name = item.split(" ", 2)
        out[name] = {"no": int(no), "name": name, "party": PARTY_FULL.get(party, party)}
    return out


def cand(b, name):
    c = dict(b[name.rstrip("?")])
    c["tone"] = TONE.get(c["party"], "ind")
    return c


def main():
    contenders = json.load(open(ROOT / "data" / "2026-contenders.json"))
    prev_night = json.load(open(ROOT / "data" / "needle" / "2022-mayors.json"))
    st22 = ST.load("2022-mayors")
    winners = {}
    for r in prev_night["races"]:
        w = r["blue"] if r["blue"]["final"] >= r["other"]["final"] else r["other"]
        winners[r["area"]] = {k: w[k] for k in ("no", "name", "party", "tone")}
    for k in prev_night.get("skipped", []):  # 嘉義市: voted 2022-12-18
        winners[k["area"]] = k["incumbent"]
    races, changed = [], []
    for c in sorted(contenders["races"], key=lambda x: ORDER.index(x["area"])):
        area, b = c["area"], ballot(c["area"])
        inc = dict(winners[area])
        party = b[inc["name"]]["party"] if inc["name"] in b else INCUMBENT_PARTY.get(area, inc["party"])
        if party != inc["party"]:
            changed.append(f"{area} {inc['name']}: {inc['party']} -> {party}")
            inc.update(party=party, tone=TONE.get(party, "ind"), party2022=inc["party"], tone2022=inc["tone"])
        stn = st22[area]["stations"]
        E, C = sum(s["E"] for s in stn), sum(s["C"] for s in stn)
        e = {"area": area, "label": area + "長", "blue": cand(b, c["blue"]), "other": cand(b, c["other"]),
             "stations": len(stn), "electors": E, "prev_turnout": round(C / E, 4), "incumbent": inc,
             "sure": c.get("sure", True), "pts": []}
        tw = c.get("three_way") or {}
        if tw.get("status") == "expected" and tw.get("third"):
            e["third"], e["mode"] = cand(b, tw["third"]), "three"
        if tw.get("status"):
            e["three_way"] = tw["status"]
        races.append(e)
    out = {"id": "2026-mayors", "title": "2026 縣市長選舉", "date": "2026-11-28", "baseline": "2022-mayors+2024-president",
           "previous": "2022-mayors", "start": 0, "end": END, "live": True, "feed": "station",
           "turnout_sigma": prev_night.get("turnout_sigma"), "point_columns": prev_night["point_columns"],
           "note": "Before the count. Electors, stations and last-time turnout are 2022's; incumbent = 2022 winner, with their current party.",
           "races": races, "skipped": []}
    path = ROOT / "data" / "needle" / "2026-mayors.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{path.relative_to(ROOT)}: {len(races)} races; incumbent party changes: {'; '.join(changed) or 'none'}")


if __name__ == "__main__":
    main()
