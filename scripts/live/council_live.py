#!/usr/bin/env python3
"""Election night, councils: every council district's count from the CEC, as data/council/<year>.json.

There is no model here: the page shows who would hold each seat if counting stopped now (scripts/council.py,
allocate), and marks a seat decided only when the votes still out can't change it. The CEC's district page
(prefix T1 regional, T2 平地原住民, T3 山地原住民; code county + district + zeros) gives seats, reserved
women's seats, stations sent/total and every candidate's votes and sex. The district list is the CEC's
2026 candidate files (data/live/council-2026.json; 臺南市 from 2022 until the CEC publishes its file).

Electors still out (the page's bound on what could still change) aren't on the CEC's pages, so they are
estimated generously: the district's electors (council-2026.json, electors_est) x the share not yet counted,
using the same "early stations are smaller" curve as the mayoral races, plus 15%.
"""
import json
import os
from pathlib import Path

from cec_parse import parse_count
from live_model import counted_share

ROOT = Path(__file__).resolve().parent.parent.parent
TONE = {"中國國民黨": "kmt", "民主進步黨": "dpp", "台灣民眾黨": "tpp", "時代力量": "npp", "台灣基進": "tsp", "親民黨": "pfp", "無黨籍": "ind"}
PAD = 1.15


def party(name):
    return "無黨籍" if name.strip() in ("無", "無黨籍", "無黨籍及未經政黨推薦", "") else name.strip()


class CouncilLive:
    def __init__(self, out, year=2026, date="2026-11-28"):
        self.out = Path(out)
        (self.out / "council").mkdir(parents=True, exist_ok=True)
        spec = json.loads((ROOT / "data" / "live" / "council-2026.json").read_text(encoding="utf-8"))["counties"]
        self.doc = {"id": f"{year}-council", "year": year, "date": date, "title": f"{year} 縣市議員選舉", "start": 0, "end": 480,
                    "point_columns": ["t_min_after_16", "stations_in", "electors_left", "...votes per candidate, in cands order"],
                    "live": True, "counties": []}
        self.pages = {}
        for area, c in spec.items():
            ds = []
            for d in c["districts"]:
                x = {"no": d["no"], "name": f"第{d['no']:02d}選舉區", "seat_type": d["seat_type"], "seats": d["seats"],
                     "towns": d["towns"], "women": d["women"], "stations": 0, "electors": d["electors_est"], "cands": [], "pts": []}
                ds.append(x)
                self.pages[d["page"]] = x
            self.doc["counties"].append({"area": area, "districts": ds})
        self.sig = {}
        prev = self.out / "council" / "2026.json"
        if prev.exists():  # after a restart: keep what was already counted
            old = json.loads(prev.read_text(encoding="utf-8"))
            have = {(c["area"], d["seat_type"], d["no"]): d for c in old["counties"] for d in c["districts"]}
            for c in self.doc["counties"]:
                for d in c["districts"]:
                    o = have.get((c["area"], d["seat_type"], d["no"]))
                    if o and o["pts"]:
                        d.update({k: o[k] for k in ("cands", "pts", "stations", "seats", "women")})
            for p, d in self.pages.items():
                if d["pts"]:
                    self.sig[p] = (d["pts"][-1][1], tuple(d["pts"][-1][3:]))

    def urls(self, base):
        return [f"{base.rstrip('/')}/{p}" for p in self.pages]

    def step(self, base, pages, t_of, fallback=None):
        """Append a point to every district whose count moved. t_of(updated stamp) -> minutes after 16:00.
        fallback: {("T", page): {"sent", "total", "votes": {no: n}}} from the CEC's media feed (outlets.py), used when it
        is further along than the district's page; it has no names, so only for districts already read once."""
        moved = 0
        for p, d in self.pages.items():
            body, _ = pages.get(f"{base.rstrip('/')}/{p}", (None, False))
            pg = None
            if body:
                try:
                    pg = parse_count(body)
                except ValueError:
                    pass
            f = (fallback or {}).get(("T", p))
            if f and d["cands"] and set(f["votes"]) == {c["no"] for c in d["cands"]} and (pg is None or f["sent"] > pg["sent"]):
                pg = {"sent": f["sent"], "total": f["total"], "seats": None, "women": None, "updated": fallback.get("stamp"),
                      "rows": [{"no": c["no"], "name": c["name"], "party": c["party"], "sex": c["sex"], "votes": f["votes"][c["no"]],
                                "mark": ""} for c in d["cands"]]}
            if pg is None:
                continue
            if not d["cands"] or len(d["cands"]) != len(pg["rows"]):
                d["cands"] = [{"no": r["no"], "name": r["name"], "party": party(r["party"]), "tone": TONE.get(party(r["party"]), "oth"),
                               "sex": r["sex"], "final": 0, "victor": ""} for r in pg["rows"]]
            if pg["seats"]:
                d["seats"], d["women"] = pg["seats"], pg["women"]
            d["stations"] = pg["total"] or d["stations"]
            votes = [r["votes"] for r in pg["rows"]]
            sig = (pg["sent"], tuple(votes))
            if self.sig.get(p) == sig or pg["sent"] == 0:
                continue
            self.sig[p] = sig
            f = pg["sent"] / max(pg["total"], 1)
            left = 0 if f >= 1 else round(d["electors"] * (1 - counted_share(f)) * PAD)
            t = round(t_of(pg["updated"]))
            row = [t, pg["sent"], left] + votes
            if d["pts"] and t <= d["pts"][-1][0]:
                row[0] = d["pts"][-1][0]
                d["pts"][-1] = row
            else:
                d["pts"].append(row)
            for c, r in zip(d["cands"], pg["rows"]):
                c["final"] = r["votes"] if f >= 1 else 0
                c["victor"] = "*" if (f >= 1 and r["mark"]) else ""
            moved += 1
        return moved

    def counting(self):
        return any(d["pts"] for c in self.doc["counties"] for d in c["districts"])

    def write(self, now):
        last = max((d["pts"][-1][0] for c in self.doc["counties"] for d in c["districts"] if d["pts"]), default=0)
        self.doc["end"] = max(480, int(last) + 30) if last > 450 else 480
        self.doc["updated"] = now.isoformat(timespec="seconds")
        path = self.out / "council" / "2026.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return path
