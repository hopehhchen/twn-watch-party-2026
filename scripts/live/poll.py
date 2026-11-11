#!/usr/bin/env python3
"""Election night: read the CEC count site every minute, run the needle, write the night's JSON.

  python3 scripts/live/poll.py --base https://<count host>/zh-TW/ [--out live-out] [--once] [--interval 60]
  python3 scripts/live/poll.py --probe --base ...          # fetch and parse one page of each kind, then stop

Each cycle fetches, for the 22 mayoral races: the county page and every town page (TC prefix: votes per
candidate and stations sent/total) and the county turnout page (SC prefix: electors and ballots by town).
Pages that haven't changed (ETag / Last-Modified) are not downloaded again; a page that fails or doesn't
parse keeps its last good value. Every cycle's parsed snapshot is archived (out/archive/), so the night can
be recomputed from scratch after a fix: on start, the poller rebuilds every race from what's already archived.

Output: out/needle/2026-mayors.json, the same file the page loads (data/needle/2026-mayors.json plus points),
written atomically. scripts/live/publish.py puts it on the site.

Contenders: blue and other come from the file. Where the file marks "other" as unsettled (金門: name ending
"?"), other is whichever non-blue candidate leads the count. A race switches to three-way, once 5% of its
stations are in, when a third candidate is in the top two or within 10 points of the leader (docs/needle.md);
花蓮 is three-way from the start. When contenders change, that race's points are recomputed from the archive.
"""
import argparse
import gzip
import json
import os
import sys
import time
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import stations as ST  # noqa: E402
from cec_parse import parse_count, parse_turnout  # noqa: E402
from council_live import CouncilLive  # noqa: E402
from live_model import LiveRace  # noqa: E402

TW = timezone(timedelta(hours=8))
try:  # Python from python.org on a Mac has no certificates of its own: use certifi's when installed
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()
UA = "twn-watch-party-2026 (election-2026.tw; https://github.com/hopehhchen/twn-watch-party-2026)"
NIGHT_FILE = ROOT / "data" / "needle" / "2026-mayors.json"
TOWNS_FILE = ROOT / "data" / "live" / "towns-2022.json"


def log(*a):
    print(datetime.now(TW).strftime("%H:%M:%S"), *a, flush=True)


class Fetcher:
    """Conditional GETs with a timeout, a couple of retries, and the last good body kept per URL."""

    def __init__(self, timeout=15, retries=2, workers=6):
        self.timeout, self.retries, self.workers = timeout, retries, workers
        self.cache = {}  # url -> (etag, last_modified, body)
        self.stats = {}

    def get(self, url):
        etag, lm, body = self.cache.get(url, (None, None, None))
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
            if etag:
                req.add_header("If-None-Match", etag)
            if lm:
                req.add_header("If-Modified-Since", lm)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=SSL) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", "replace")
                    self.cache[url] = (r.headers.get("ETag"), r.headers.get("Last-Modified"), text)
                    self.stats["200"] = self.stats.get("200", 0) + 1
                    return text, True
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    self.stats["304"] = self.stats.get("304", 0) + 1
                    return body, False
                self.stats[str(e.code)] = self.stats.get(str(e.code), 0) + 1
                if e.code in (403, 404):
                    return body, False  # not published yet / blocked: keep what we had
            except Exception as e:  # timeouts, resets
                self.stats["err"] = self.stats.get("err", 0) + 1
                last = e
            time.sleep(0.5 * (attempt + 1))
        return body, False

    def get_many(self, urls):
        self.stats = {}
        with ThreadPoolExecutor(self.workers) as ex:
            return dict(zip(urls, ex.map(self.get, urls)))


def page_url(base, prefix, county, town="000"):
    return f"{base.rstrip('/')}/{prefix}/{county}00{town}0000000.html"


def tmin(updated, fallback):
    """Minutes after 16:00 on the night from the page's '11/28 18:05:32' stamp (else the fetch time)."""
    try:
        md, hms = updated.split()
        mo, d = (int(x) for x in md.split("/"))
        h, mi, s = (int(x) for x in hms.split(":"))
        when = datetime(fallback.year, mo, d, h, mi, s, tzinfo=TW)
    except Exception:
        when = fallback
    t0 = fallback.replace(hour=16, minute=0, second=0, microsecond=0)
    return (when - t0).total_seconds() / 60


class Night:
    def __init__(self, out):
        self.out = Path(out)
        (self.out / "archive").mkdir(parents=True, exist_ok=True)
        (self.out / "needle").mkdir(parents=True, exist_ok=True)
        self.doc = json.loads(NIGHT_FILE.read_text(encoding="utf-8"))
        self.council = CouncilLive(self.out)
        self.towns = json.loads(TOWNS_FILE.read_text())["counties"]
        st22 = ST.load("2022-mayors")
        self.models, self.last = {}, {}
        for r in self.doc["races"]:
            area = r["area"]
            tw = {}
            for s in st22[area]["stations"]:
                x = tw.setdefault(s["district"], {"E": 0, "N": 0, "sizes": []})
                x["E"] += s["E"]
                x["N"] += 1
                x["sizes"].append(s["E"])
            for x in tw.values():
                x["sizes"].sort(reverse=True)
            valid = sum(s["A"] for s in st22[area]["stations"]) / max(sum(s["C"] for s in st22[area]["stations"]), 1)
            nos = sorted({r["blue"]["no"], r["other"]["no"]} | ({r["third"]["no"]} if r.get("third") else set()))
            r["_nos"] = nos  # filled with every candidate's number from the first page
            r["_towns"], r["_valid"] = tw, valid
            r["_open"] = r["other"]["name"].endswith("?") or not r.get("sure", True)

    # ---- one cycle -------------------------------------------------------------------------------------
    def urls(self, base):
        out = []
        for r in self.doc["races"]:
            c = self.towns[r["area"]]
            out.append(page_url(base, "TC", c["code"]))
            out += [page_url(base, "TC", c["code"], code) for code, *_ in c["towns"]]
            out.append(page_url(base, "SC", c["code"]))
        return out + self.council.urls(base)

    def snapshot(self, base, pages, now):
        """{area: {"county": parsed county page, "towns": {town: {...}}, "turnout": {...}, "t": minutes}}"""
        snap, errors = {}, []
        for r in self.doc["races"]:
            area, c = r["area"], self.towns[r["area"]]
            entry = {"towns": {}, "county": None, "turnout": None}
            body, _ = pages.get(page_url(base, "TC", c["code"]), (None, False))
            if body:
                try:
                    entry["county"] = parse_count(body)
                except ValueError as e:
                    errors.append(f"{area} county: {e}")
            tpage, _ = pages.get(page_url(base, "SC", c["code"]), (None, False))
            turnout = {}
            if tpage:
                try:
                    turnout = {row["area"]: row for row in parse_turnout(tpage)["rows"]}
                except ValueError as e:
                    errors.append(f"{area} turnout: {e}")
            entry["turnout"] = turnout.get("總計")
            stamps = []
            for code, name, *_ in c["towns"]:
                body, _ = pages.get(page_url(base, "TC", c["code"], code), (None, False))
                if not body:
                    continue
                try:
                    p = parse_count(body)
                except ValueError as e:
                    errors.append(f"{area} {name}: {e}")
                    continue
                tr = turnout.get(name) or {}
                entry["towns"][name] = {"sent": p["sent"], "total": p["total"], "votes": {x["no"]: x["votes"] for x in p["rows"]},
                                        "C": tr.get("C"), "E": tr.get("E"), "names": {x["no"]: x["name"] for x in p["rows"]}}
                if p["updated"]:
                    stamps.append(p["updated"])
            entry["t"] = round(tmin(max(stamps), now) if stamps else tmin(None, now), 2)
            snap[area] = entry
        return snap, errors

    def archive(self, snap, now):
        f = self.out / "archive" / f"{now.strftime('%Y%m%d-%H%M%S')}.json.gz"
        with gzip.open(f, "wt", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False)

    # ---- contenders --------------------------------------------------------------------------------------
    def sides(self, r, towns):
        """(blue, other, third or None, mode) for this snapshot, applying the live rules."""
        tot = {}
        for t in towns.values():
            for no, v in t["votes"].items():
                tot[int(no)] = tot.get(int(no), 0) + v
        blue, other = r["blue"]["no"], r["other"]["no"]
        third = r["third"]["no"] if r.get("third") else None
        if not tot:
            return blue, other, third, r.get("mode", "two")
        ranked = sorted((no for no in tot if no != blue), key=lambda no: -tot[no])
        if r["_open"] and ranked:
            other = ranked[0]
        if r.get("mode") == "three" and third is not None:  # keep the two non-blue leaders as other/third
            pair = [no for no in ranked if no in (other, third)] or ranked[:2]
            if len(ranked) >= 2 and set(ranked[:2]) != {other, third}:
                pair = ranked[:2]
            other, third = (pair + [third])[:2]
            return blue, other, third, "three"
        sent = sum(t["sent"] for t in towns.values())
        total = sum(t["total"] for t in towns.values()) or 1
        cand3 = next((no for no in ranked if no != other), None)
        V = sum(tot.values()) or 1
        top = max(tot.values())
        if cand3 is not None and sent / total >= 0.05:
            order = sorted(tot, key=lambda no: -tot[no])
            if cand3 in order[:2] or (top - tot[cand3]) / V < 0.10:
                return blue, other, cand3, "three"
        return blue, other, None, "two"

    def apply_sides(self, r, blue, other, third, mode, names):
        changed = (other != r["other"]["no"]) or ((r.get("third") or {}).get("no") != third) or (mode != r.get("mode", "two"))
        if not changed:
            return False
        def cand(no):
            from build_needle_data import TONE
            nm = names.get(no) or names.get(str(no)) or str(no)
            party = r.get("_parties", {}).get(no, "")
            return {"no": no, "name": nm, "party": party or "無黨籍", "tone": TONE.get(party, "ind")}
        if other != r["other"]["no"]:
            r["other"] = cand(other)
        if third is not None:
            r["third"], r["mode"] = cand(third), "three"
        else:
            r.pop("third", None)
            r["mode"] = "two"
        log(f"{r['area']}: contenders now {r['blue']['name']} / {r['other']['name']}" + (f" / {r['third']['name']}" if third else ""))
        return True

    # ---- model -------------------------------------------------------------------------------------------
    def model(self, r, nos):
        key = (r["area"], tuple(nos), r["blue"]["no"], r["other"]["no"], (r.get("third") or {}).get("no"))
        m = self.models.get(r["area"])
        if m is None or m[0] != key:
            lr = LiveRace(r["area"], self.doc["baseline"], nos, r["blue"]["no"], r["other"]["no"], r["_towns"],
                          third_no=(r.get("third") or {}).get("no"), valid_ratio=r["_valid"])
            self.models[r["area"]] = (key, lr)
        return self.models[r["area"]][1]

    def step(self, snap):
        """Append a point to every race whose count moved. Returns the races that changed."""
        moved = []
        for r in self.doc["races"]:
            e = snap.get(r["area"])
            if not e or not e["towns"]:
                continue
            names = {}
            for t in e["towns"].values():
                names.update({int(k): v for k, v in t["names"].items()})
            if e["county"]:
                r["_parties"] = {x["no"]: (x["party"] if x["party"] != "無" else "無黨籍") for x in e["county"]["rows"]}
            nos = sorted(names) or r["_nos"]
            sig = self._sig(e["towns"])
            blue, other, third, mode = self.sides(r, e["towns"])
            if self.apply_sides(r, blue, other, third, mode, names):
                self.recompute(r, nos)
                self.last[r["area"]] = sig
                moved.append(r["area"])
                continue
            if self.last.get(r["area"]) == sig:
                continue
            self.last[r["area"]] = sig
            row = self.model(r, nos).row(e["t"], e["towns"])
            if row is None:
                continue
            if r["pts"] and row[0] < r["pts"][-1][0]:
                row[0] = r["pts"][-1][0]
            if r["pts"] and row[0] == r["pts"][-1][0]:
                r["pts"][-1] = row
            else:
                r["pts"].append(row)
            self.meta(r, e)
            moved.append(r["area"])
        return moved

    def meta(self, r, e):
        tot = sum(t["total"] for t in e["towns"].values())
        if tot:
            r["stations"] = tot
        if e.get("turnout") and e["turnout"].get("E"):
            r["electors"] = e["turnout"]["E"]

    @staticmethod
    def _norm(towns):
        return {k: {**v, "votes": {int(a): b for a, b in v["votes"].items()}, "names": {int(a): b for a, b in v.get("names", {}).items()}}
                for k, v in towns.items()}

    @staticmethod
    def _sig(towns):
        return json.dumps({k: (v["sent"], sorted(v["votes"].items())) for k, v in sorted(towns.items())})

    def resume(self):
        """After a restart: take contenders from the latest archived snapshot and rebuild every race's points."""
        files = sorted((self.out / "archive").glob("*.json.gz"))
        if not files:
            return
        log(f"resuming from {len(files)} saved snapshots")
        with gzip.open(files[-1], "rt", encoding="utf-8") as fh:
            latest = json.load(fh)
        for r in self.doc["races"]:
            e = latest.get(r["area"])
            if not e or not e["towns"]:
                continue
            towns = self._norm(e["towns"])
            names = {}
            for t in towns.values():
                names.update(t["names"])
            if e.get("county"):
                r["_parties"] = {x["no"]: (x["party"] if x["party"] != "無" else "無黨籍") for x in e["county"]["rows"]}
            self.apply_sides(r, *self.sides(r, towns), names)
            self.recompute(r, sorted(names) or r["_nos"])
            self.last[r["area"]] = self._sig(towns)
            self.meta(r, {**e, "towns": towns})

    def recompute(self, r, nos):
        """Rebuild a race's points from every archived snapshot (after its contenders changed, or a restart)."""
        r["pts"] = []
        m = self.model(r, nos)
        prev = None
        for f in sorted((self.out / "archive").glob("*.json.gz")):
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                e = json.load(fh).get(r["area"])
            if not e or not e["towns"]:
                continue
            towns = self._norm(e["towns"])
            sig = self._sig(towns)
            if sig == prev:
                continue
            prev = sig
            row = m.row(e["t"], towns)
            if row is None:
                continue
            if r["pts"] and row[0] <= r["pts"][-1][0]:
                row[0] = r["pts"][-1][0]
                r["pts"][-1] = row
            else:
                r["pts"].append(row)
        log(f"{r['area']}: {len(r['pts'])} points recomputed")

    def write(self, now):
        doc = {k: v for k, v in self.doc.items() if k != "races" and not k.startswith("_")}
        doc["races"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in self.doc["races"]]
        last = max((r["pts"][-1][0] for r in doc["races"] if r["pts"]), default=0)
        doc["end"] = max(self.doc["end"], int(last) + 30) if last > self.doc["end"] - 30 else self.doc["end"]
        doc["updated"] = now.isoformat(timespec="seconds")
        doc["council_live"] = self.council.counting()  # the page enables its Council view once this is true
        path = self.out / "needle" / "2026-mayors.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(tmp, path)
        return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="count site root, e.g. https://vote.cec.gov.tw/zh-TW/ (default: data/live/night-config.json)")
    ap.add_argument("--out", default=str(ROOT / "live-out"))
    ap.add_argument("--interval", type=float, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--date", default="2026-11-28", help="the night (for page timestamps)")
    ap.add_argument("--wait-until", help="Taiwan time (e.g. 2026-11-28T15:50) before which only one page is checked every "
                                         "10 minutes: the night runner can start hours early without hammering the CEC")
    a = ap.parse_args()
    if not a.base:
        a.base = json.loads((ROOT / "data" / "live" / "night-config.json").read_text())["count_base"]
        if not a.base:
            sys.exit("The CEC count site's address isn't set yet (data/live/night-config.json, count_base).")
    night, fetcher = Night(a.out), Fetcher()
    if a.probe:
        c = night.towns["臺北市"]
        for u in (page_url(a.base, "TC", c["code"]), page_url(a.base, "TC", c["code"], c["towns"][0][0]), page_url(a.base, "SC", c["code"])):
            body, _ = fetcher.get(u)
            print(u, fetcher.stats)
            if body:
                kind = parse_turnout if "/SC/" in u else parse_count
                try:
                    print("  ", json.dumps(kind(body), ensure_ascii=False)[:300])
                except ValueError as e:
                    print("   PARSE FAILED:", e, body[:300])
        return
    day = datetime.fromisoformat(a.date).replace(tzinfo=TW)
    night.resume()  # no-op on a fresh start; after a restart, picks up where the last run stopped
    if a.wait_until:
        until = datetime.fromisoformat(a.wait_until).replace(tzinfo=TW)
        probe = page_url(a.base, "TC", night.towns["臺北市"]["code"])
        while datetime.now(TW) < until:
            fetcher.stats = {}
            body, _ = fetcher.get(probe)
            log(f"waiting until {until:%H:%M} (Taiwan time) to start reading; the CEC count site answered: {fetcher.stats}")
            time.sleep(min(600, max(1, (until - datetime.now(TW)).total_seconds())))
    first, path = True, night.out / "needle" / "2026-mayors.json"
    while True:
        t_start = time.time()
        now = datetime.now(TW)
        now_night = day.replace(hour=now.hour, minute=now.minute, second=now.second) if a.date else now
        pages = fetcher.get_many(night.urls(a.base))
        snap, errors = night.snapshot(a.base, pages, now_night)
        night.archive(snap, now)
        moved = night.step(snap)
        cmoved = night.council.step(a.base, pages, lambda u: tmin(u, now_night))
        if cmoved or first:
            night.council.write(now)
        if cmoved and not moved and not night.doc.get("_council_flag"):
            moved, night.doc["_council_flag"] = ["council"], True  # rewrite the mayors' file once so the flag goes out
        if moved or first:  # "updated" in the file = when the figures last changed (the page warns if that gets old)
            path = night.write(now)
        first = False
        log(f"cycle {time.time() - t_start:.1f}s {fetcher.stats} moved: {', '.join(moved) or '-'}; council districts moved: {cmoved}"
            + (f" | {len(errors)} parse errors, e.g. {errors[0]}" if errors else ""))
        if a.once:
            print(path)
            return
        time.sleep(max(1.0, a.interval - (time.time() - t_start)))


if __name__ == "__main__":
    main()
