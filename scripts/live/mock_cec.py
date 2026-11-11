#!/usr/bin/env python3
"""A stand-in for the CEC count site, for rehearsals: the 2022 count, replayed on the 2026 ballot.

  python3 scripts/live/mock_cec.py [--port 8790] [--speed 16] [--start 16:00] [--fail 0.03] [--layout 2025]

Serves /zh-TW/TC/<code>.html (county and town candidate votes), /zh-TW/SC/<code>.html (county turnout by
town) and /zh-TW/T1|T2|T3/<code>.html (council districts: 2022's count for each 2026 district with the same
number; districts new in 2026 answer 404) in the CEC's 2022 markup (or the 2025 id-based markup), with ETags. The clock starts at --start when the
server starts and runs --speed times faster (16: 16:00 to 24:00 in 30 minutes). Every 2022 station reports at
its logged time; its votes go to the 2026 candidates: 2022's blue side to 2026's blue, the other side to 2026's
other, the 2022 third-placed candidate to the 2026 third (in three-way races) and the rest to the rest.
嘉義市 voted in December 2022 with no logged times; its stations take 新竹市's times in order.
--fail makes that share of requests fail (500 or a 20 s stall) to exercise retries.
"""
import argparse
import hashlib
import json
import random
import sys
import time
import warnings
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import needle as N  # noqa: E402
import stations as ST  # noqa: E402
from build_2026_night import ballot  # noqa: E402


def build():
    night = json.loads((ROOT / "data" / "needle" / "2026-mayors.json").read_text())
    towns = json.loads((ROOT / "data" / "live" / "towns-2022.json").read_text())["counties"]
    st22, tm = ST.load("2022-mayors"), ST.times("2022-mayors")
    t0 = datetime(2022, 11, 26, 16, 0)
    hsinchu = sorted(tm[k] for k in tm if k[0] == "新竹市")
    races = {}
    for r in night["races"]:
        area = r["area"]
        race = st22[area]
        b = ballot(area)
        cands26 = sorted(b.values(), key=lambda c: c["no"])
        nos = [c["no"] for c in cands26]
        tot22 = [sum(s["v"][k] for s in race["stations"]) for k in range(len(race["cands"]))]
        try:
            ia, ib, _ = N.blue_pair(race, ("2022-mayors", area))
        except TypeError:
            ia, ib = sorted(range(len(tot22)), key=lambda k: -tot22[k])[:2]
        rest22 = [k for k in sorted(range(len(tot22)), key=lambda k: -tot22[k]) if k not in (ia, ib)]
        target = [r["blue"]["no"], r["other"]["no"]]
        third = (r.get("third") or {}).get("no")
        rest26 = ([third] if third else []) + [no for no in nos if no not in target and no != third]
        mapping = {ia: target[0], ib: target[1]}
        for k, no in zip(rest22, rest26):
            mapping[k] = no
        sts = []
        for i, s in enumerate(race["stations"]):
            key = ("嘉義市" if area == "嘉義市" else area, s["district"], s["no"])
            when = tm.get(key) if area != "嘉義市" else hsinchu[min(i, len(hsinchu) - 1)]
            minutes = (when - t0).total_seconds() / 60 if when else 400 + i * 0.1
            v = {no: 0 for no in nos}
            for k, x in enumerate(s["v"]):
                if k in mapping:
                    v[mapping[k]] += x
            sts.append({"d": s["district"], "t": minutes, "E": s["E"], "C": s["C"], "A": s["A"], "v": v})
        races[towns[area]["code"]] = {"area": area, "towns": towns[area]["towns"], "cands": cands26, "st": sts,
                                      "office": "市長" if area.endswith("市") and area in ("臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市", "基隆市", "新竹市", "嘉義市") else "縣長"}
    return races


def build_council():
    """2026 council page path -> the 2022 district with the same county, seat type and number (if any)."""
    import council as CO
    spec = json.loads((ROOT / "data" / "live" / "council-2026.json").read_text(encoding="utf-8"))["counties"]
    data, tm = CO.load(2022), ST.times("2022-mayors")
    t0 = datetime(2022, 11, 26, 16, 0)
    SEAT = {"T1": "區域", "T2": "平地原住民", "T3": "山地原住民"}
    out = {}
    for area, c in spec.items():
        old = {(SEAT[d["seat_type"]] if d["seat_type"] in SEAT else d["seat_type"], d["no"]): d for d in data[area]}
        for d in c["districts"]:
            o = old.get((d["seat_type"], d["no"]))
            if not o:
                continue
            keep = [k for k, x in enumerate(o["cands"]) if "note" not in x]
            sts = []
            for s_ in o["stations"]:
                when = tm.get((area, s_["district"], s_["no"]))
                sts.append(((when - t0).total_seconds() / 60 if when else 420.0, [s_["v"][k] for k in keep]))
            cands = [{"no": o["cands"][k]["no"], "name": o["cands"][k]["name"], "sex": o["cands"][k]["sex"],
                      "party": o["cands"][k]["party"] or "無"} for k in keep]
            out[d["page"].split("/")[1][:-5]] = {"area": area, "no": d["no"], "type": d["seat_type"], "seats": o["seats"],
                                                 "women": o["women"], "cands": cands, "st": sts}
    return out


def council_page(d, now, stamp):
    done = [v for t, v in d["st"] if t <= now]
    votes = [sum(v[k] for v in done) for k in range(len(d["cands"]))]
    V = sum(votes) or 1
    rows = "".join(f"""<tr><td class="electmark"></td><td>{c['no']}</td><td>{c['name']}</td><td>{'女' if c['sex'] == 2 else '男'}</td>
      <td class="numeric">{v:,}</td><td class="numeric">{100 * v / V:.2f}%</td><td>{c['party']}</td></tr>""" for c, v in zip(d["cands"], votes))
    kind = "" if d["type"] == "區域" else f"({d['type']})"
    return f"""<div class="table-header"><table class="title"><tr><td><b>{d['area']} 議員選舉 第{d['no']}選舉區{kind} 候選人得票數</b></td></tr></table>
<div class="subtitle"><div class="bullet">應選人數: {d['seats']}</div>{f'<div class="bullet">婦女應當選名額: {d["women"]}</div>' if d['women'] else ''}
<div class="bullet emph-right">投開票所數 已送/應送: {len(done)}/{len(d['st'])}</div></div></div>
<div class="table-content"><table class="tablesaw"><thead><tr><th scope="col">註記</th><th scope="col">號次</th><th scope="col">姓名</th><th scope="col">性別</th><th scope="col">得票數</th><th scope="col">得票率%</th><th scope="col">推薦之政黨</th></tr></thead>
<tbody>{rows}</tbody></table></div><div class="table-footer">資料更新時間: {stamp}</div>
"""


def table_2022(title, sent, total, cands, votes, stamp):
    V = sum(votes.values()) or 1
    rows = "".join(f"""
      <tr>
        <td class="electmark">&nbsp;</td>
        <td>{c['no']}</td>
        <td>{c['name']}</td>
        <td>男</td>
        <td class="numeric">{votes[c['no']]:,}</td>
        <td class="numeric">{100 * votes[c['no']] / V:.2f}%</td>
        <td>{'無' if c['party'] == '無黨籍' else c['party']}</td>
      </tr>""" for c in cands)
    return f"""<div class="table-header">
  <table class="title"><tr><td><img src="../_assets/img/search.png" /></td><td><b>{title}</b></td></tr></table>
  <div class="subtitle">
    <div class="bullet "><img src="../_assets/img/nav.gif" />應選人數: 1</div>
    <div class="bullet emph-right"><img src="../_assets/img/nav.gif" />投開票所數 已送/應送: {sent}/{total}</div>
  </div>
</div>
<div class="table-content">
  <table class="tablesaw">
    <thead><tr><th scope="col">註記</th><th scope="col">號次</th><th scope="col">姓名</th><th scope="col">性別</th><th scope="col">得票數</th><th scope="col">得票率%</th><th scope="col">推薦之政黨</th></tr></thead>
    <tbody>{rows}
    </tbody>
  </table>
</div>
<div class="table-footer"><div class="table-footer-right">資料更新時間: {stamp}</div></div>
"""


def table_2025(title, sent, total, cands, votes, stamp):
    V = sum(votes.values()) or 1
    rows = "".join(f"<tr><td></td><td>{c['no']}</td><td>{c['name']}</td><td>男</td><td class=\"numeric\">{votes[c['no']]:,}</td>"
                   f"<td class=\"numeric\">{100 * votes[c['no']] / V:.2f}%</td><td>{c['party']}</td></tr>" for c in cands)
    return f"""<div id="vote-table-header"><div class="vote-table-header-title"><img src="../assets/img/search.png" /> <b>{title}</b></div>
<div class="vote-table-header-subtitle"><div class="bullet"> <img src="../assets/img/nav.gif" />已送投票所數/總投票所數: {sent}/{total} </div></div></div>
<div id="vote-table-content"><table class="tablesaw"><thead><tr><th scope="col">註記</th><th scope="col">號次</th><th scope="col">姓名</th><th scope="col">性別</th><th scope="col">得票數</th><th scope="col">得票率%</th><th scope="col">推薦之政黨</th></tr></thead>
<tbody>{rows}</tbody></table></div><div id="vote-table-footer">資料更新時間: {stamp}</div>
"""


def turnout_page(title, rows, stamp):
    trs = "".join(f"<tr><td>{a}</td><td class=\"numeric\">{E:,}</td><td class=\"numeric\">{C:,}</td><td class=\"numeric\">{A:,}</td>"
                  f"<td class=\"numeric\">{C - A:,}</td><td class=\"numeric\">{(100 * C / E if E else 0):.2f}%</td></tr>" for a, E, C, A in rows)
    return f"""<div class="table-header"><table class="title"><tr><td><b>{title}</b></td></tr></table></div>
<div class="table-content"><table class="tablesaw"><thead><tr><th scope="col">行政區</th><th scope="col">選舉人數</th><th scope="col">投票數</th><th scope="col">有效票數</th><th scope="col">無效票數</th><th scope="col">投票率%</th></tr></thead>
<tbody>{trs}</tbody></table></div><div class="table-footer">資料更新時間: {stamp}</div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--speed", type=float, default=16)
    ap.add_argument("--start", default="16:00")
    ap.add_argument("--fail", type=float, default=0.0)
    ap.add_argument("--layout", default="2022", choices=["2022", "2025"])
    a = ap.parse_args()
    races = build()
    council = build_council()
    h, m = (int(x) for x in a.start.split(":"))
    t_start, real0 = (h - 16) * 60 + m, time.time()
    table = table_2025 if a.layout == "2025" else table_2022

    def sim_minutes():
        return t_start + (time.time() - real0) / 60 * a.speed

    def stamp(mins):
        t = datetime(2026, 11, 28, 16, 0) + timedelta(minutes=mins)
        return t.strftime("%m/%d %H:%M:%S")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def do_GET(self):
            if a.fail and random.random() < a.fail:
                if random.random() < 0.5:
                    self.send_error(500)
                    return
                time.sleep(20)
            parts = self.path.split("?")[0].strip("/").split("/")
            if len(parts) == 3 and parts[1] in ("T1", "T2", "T3") and parts[2].endswith(".html"):
                d = council.get(parts[2][:-5])
                now = sim_minutes()
                if not d or now < 0:
                    self.send_error(404)
                    return
                raw = council_page(d, now, stamp(now)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if len(parts) != 3 or parts[1] not in ("TC", "SC") or not parts[2].endswith(".html"):
                self.send_error(404)
                return
            code = parts[2][:-5]
            county, town = code[:5], code[7:10]
            race = races.get(county)
            if not race:
                self.send_error(404)
                return
            now = sim_minutes()
            if now < 0:
                self.send_error(404)
                return
            sts = race["st"]
            if parts[1] == "SC":
                rows, tot = [], [0, 0, 0]
                for tcode, name in race["towns"]:
                    ss = [s for s in sts if s["d"] == name]
                    E = sum(s["E"] for s in ss)
                    C = sum(s["C"] for s in ss if s["t"] <= now)
                    A = sum(s["A"] for s in ss if s["t"] <= now)
                    rows.append((name, E, C, A))
                    tot = [tot[0] + E, tot[1] + C, tot[2] + A]
                body = turnout_page(f"{race['area']} {race['office']}選舉 選舉概況", [("總計", *tot)] + rows, stamp(now))
            else:
                name = None if town == "000" else dict(race["towns"]).get(town)
                if town != "000" and name is None:
                    self.send_error(404)
                    return
                ss = [s for s in sts if name is None or s["d"] == name]
                done = [s for s in ss if s["t"] <= now]
                votes = {c["no"]: sum(s["v"][c["no"]] for s in done) for c in race["cands"]}
                title = f"{race['area']} {race['office']}選舉 候選人" + (f"在 {name}得票數" if name else "得票數")
                body = table(title, len(done), len(ss), race["cands"], votes, stamp(now))
            raw = body.encode()
            etag = '"' + hashlib.md5(raw).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("ETag", etag)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    print(f"mock CEC on http://127.0.0.1:{a.port}/zh-TW/  clock starts {a.start}, x{a.speed}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
