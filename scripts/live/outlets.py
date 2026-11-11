#!/usr/bin/env python3
"""Election night: other outlets' counts (for the count watch) and a second route to the CEC's numbers.

Everything here is switched on by settings, not code: data/live/outlets.json lists the outlets, each with a
kind (which reader to use) and a url that stays null until the outlet's 2026 page is up. The poller re-reads
the settings every few minutes, first from the "remote" address in that file (a file on the repository's
`night` branch, which doesn't redeploy the site when changed), then from the local copy, so an address can be
added on the night without touching the code or the machine running it.

Readers (kinds):
  cna        中央社's feed (2022: project/20221126-election-live/api/city.json): per county, every candidate's
             ballot number and votes, plus the share of stations in. Shown in the count watch.
  cec_feed   the CEC's own media feed as outlets republish it (公視 2022: {"ST", "TC": [...], "T1": [...]}, rows
             with prvCode/cityCode/deptCode/areaCode, candTksInfo, tboxTot/tboxRcv, prof1-7; 公視 2024 used one
             file per county in the same fields). Not shown as a separate row: it is the CEC's count, used as a
             fallback whenever it is further along than what the CEC's count site gave us (a town, county or
             council district is taken from whichever has more stations in).
  tv_json    on-screen TV counts by channel, keyed by candidate name (公視 2024: tv/latest.json,
             {"data": {"三立": [{"vote_name", "vote_count"}, ...], ...}}). One count-watch row per channel.
  page_text  any page that prints candidates' names followed by their votes (自由時報, 聯合報 ...). The page's
             text is searched for each candidate's name and the first number after it. "split" (optional) cuts
             the page at channel names first, giving one row per channel. Crude, so readings are checked.

A url may hold {code} (the CEC county code), {area} (臺北市), {en} (Taipei City) or {slug} (from the outlet's
own "slugs": {"臺北市": "Taipei", ...}); it is then read once per race.

A reading is kept only when it covers both contenders of a race and no candidate has more votes than the
race has electors. Each source's readings are stored as they change ([minutes after 16:00, {ballot no:
votes}]), so a change of contenders re-maps them, and the whole history is saved (out/outlets-state.json)
and picked up again after a restart.
"""
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "data" / "live" / "outlets.json"
REFRESH = 300  # seconds between settings reloads

_TAG = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.S | re.I)
_NUM = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")


def _text(html):
    import html as H
    return re.sub(r"\s+", " ", H.unescape(_TAG.sub(" ", html)))


def _norm(name):
    return re.sub(r"[\s‧·・．.]", "", name or "")


class Outlets:
    def __init__(self, out, races, ballots, fetcher=None, config=CONFIG):
        """races: the night's race dicts (area, electors, blue/other/third); ballots: {area: {name: {"no", ...}}}."""
        self.out, self.races, self.fetcher, self.config = Path(out), races, fetcher, Path(config)
        self.by_area = {r["area"]: r for r in races}
        self.names = {}  # normalized candidate name -> (area, no); a name on two ballots maps to neither
        dup = set()
        for area, b in ballots.items():
            for name, c in b.items():
                k = _norm(name)
                if k in self.names:
                    dup.add(k)
                self.names[k] = (area, c["no"])
        for k in dup:
            del self.names[k]
        self.code_area, self.en = {}, {}
        self.cfg, self.loaded = {"outlets": []}, 0
        self.state = {}  # source id -> {"meta": {...}, "areas": {area: [[t, {no: v}], ...]}, "seen": t}
        self.fallback = {}  # see cec_feed()
        self.msgs = {}
        f = self.out / "outlets-state.json"
        if f.exists():
            try:
                self.state = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass

    # ---- settings ------------------------------------------------------------------------------------------
    def reload(self, force=False):
        if not force and time.time() - self.loaded < REFRESH:
            return
        self.loaded = time.time()
        cfg = {"outlets": []}
        try:
            cfg = json.loads(self.config.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self.msgs["settings"] = f"local outlet settings unreadable: {e}"
        remote = cfg.get("remote")
        if remote and self.fetcher:
            body, _ = self.fetcher.get(remote)
            if body:
                try:
                    r = json.loads(body)
                    if isinstance(r.get("outlets"), list):
                        cfg = r
                except ValueError:
                    self.msgs["settings"] = "remote outlet settings didn't parse; using the local copy"
        self.cfg = cfg

    def active(self):
        return [o for o in self.cfg.get("outlets", []) if o.get("url") and not o.get("off")]

    def urls(self):
        self.reload()
        out = []
        for o in self.active():
            u = o["url"]
            out += [u.format(**x) for x in self._fill(o)] if "{" in u else [u]
        return out

    def _fill(self, o):
        """For a url with {code}/{area}/{en}: one url per race; values from the county list (set by the poller)."""
        slugs = o.get("slugs")  # optional {area: the outlet's own name for it}, used as {slug}
        return [{"code": code, "area": area, "en": self.en.get(area, ""), "slug": (slugs or {}).get(area, "")}
                for code, area in self.code_area.items() if not slugs or area in slugs]

    def set_counties(self, towns):
        self.code_area = {c["code"]: area for area, c in towns.items() if area in self.by_area}
        self.en = {area: c.get("en", "") for area, c in towns.items()}

    # ---- one cycle -------------------------------------------------------------------------------------------
    def read(self, pages):
        """pages: {url: (body, changed)} from the fetcher. Parses every outlet (filling self.fallback); commit() stores."""
        self.fallback, self.pending = {}, []
        for o in self.active():
            u = o["url"]
            got = [(u.format(**x), x["area"]) for x in self._fill(o)] if "{" in u else [(u, None)]
            for url, area in got:
                body, _ = pages.get(url, (None, False))
                if not body:
                    continue
                try:
                    res = getattr(self, o["kind"])(o, body, area)
                except Exception as e:  # a reader must never stop the night
                    self.msgs[o["id"]] = f"{o['id']}: {type(e).__name__}: {e}"
                    continue
                self.pending += res or []

    def commit(self, t):
        """Store the readings from read() at t (minutes after 16:00). Returns True when any count-watch source moved."""
        moved = False
        for meta, readings in getattr(self, "pending", []):
            moved |= self._store(meta, readings, t)
        self.pending = []
        if moved:
            self.save()
        return moved

    def _check(self, area, v):
        r = self.by_area.get(area)
        if not r:
            return False
        if r["blue"]["no"] not in v or (r["other"]["no"] not in v and not r["other"]["name"].endswith("?")):
            return False
        cap = r.get("electors") or 10 ** 8
        return all(0 <= x <= cap for x in v.values())

    def _store(self, meta, readings, t):
        s = self.state.setdefault(meta["id"], {"meta": meta, "areas": {}, "seen": None})
        s["meta"], s["seen"] = meta, round(t, 2)
        moved = False
        for area, v in readings.items():
            v = {int(k): int(x) for k, x in v.items() if x is not None}
            if not self._check(area, v):
                continue
            ser = s["areas"].setdefault(area, [])
            if ser and {int(k): x for k, x in ser[-1][1].items()} == v:
                continue
            row = [round(t, 2), {str(k): x for k, x in v.items()}]
            if ser and row[0] <= ser[-1][0]:
                ser[-1] = row
            else:
                ser.append(row)
            moved = True
        return moved

    def save(self):
        f = self.out / "outlets-state.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(f)

    def sources(self, race):
        """The race's count-watch rows, in the page's format: series rows [t, blue, other, third]."""
        nos = [race["blue"]["no"], race["other"]["no"], (race.get("third") or {}).get("no")]
        out = []
        for sid, s in self.state.items():
            ser = s["areas"].get(race["area"])
            if not ser:
                continue
            rows = [[p[0]] + [p[1].get(str(no)) if no is not None else None for no in nos] for p in ser]
            m = s["meta"]
            out.append({"id": sid, "label": m["label"], "en": m.get("en", m["label"]), "cohort": m.get("cohort", "field"),
                        "series": rows, "seen": s["seen"], "stale": m.get("stale", 10)})
        return out or None

    # ---- readers -------------------------------------------------------------------------------------------
    def _meta(self, o, **kw):
        m = {"id": o["id"], "label": o.get("label", o["id"]), "en": o.get("en", o.get("label", o["id"])),
             "cohort": o.get("cohort", "field"), "stale": o.get("stale", 10)}
        m.update(kw)
        return m

    def cna(self, o, body, area=None):
        d = json.loads(body)
        rows = d.values() if isinstance(d, dict) else d
        out = {}
        for c in rows:
            if not isinstance(c, dict) or "candidates" not in c:
                continue
            a = self.code_area.get(str(c.get("code", "")))
            if not a:
                continue
            out[a] = {int(x["candNo"]): int(x.get("tickets") or 0) for x in c["candidates"] if x.get("candNo") is not None}
        return [(self._meta(o), out)]

    def tv_json(self, o, body, area=None):
        d = json.loads(body)
        d = d.get("data", d) if isinstance(d, dict) else d
        chans = o.get("channels", {})
        res = []
        for ch, items in (d.items() if isinstance(d, dict) else []):
            out = {}
            for it in self._walk(items):
                name = it.get(o.get("name_field", "vote_name")) or it.get("name")
                val = it.get(o.get("count_field", "vote_count"))
                hit = self.names.get(_norm(name))
                if hit and isinstance(val, (int, float)):
                    out.setdefault(hit[0], {})[hit[1]] = int(val)
            if out:
                c = chans.get(ch, {})
                res.append((self._meta(o, id=f"{o['id']}-{c.get('id', ch)}", label=ch, en=c.get("en", ch),
                                       cohort=c.get("cohort", o.get("cohort", "field"))), out))
        return res

    @staticmethod
    def _walk(x):
        if isinstance(x, dict):
            if any(isinstance(v, (int, float)) for v in x.values()) and any(isinstance(v, str) for v in x.values()):
                yield x
            for v in x.values():
                if isinstance(v, (dict, list)):
                    yield from Outlets._walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from Outlets._walk(v)

    def page_text(self, o, body, area=None):
        text = _text(body)
        parts = [(None, text)]
        if o.get("split"):
            cuts = sorted((m.start(), lab) for lab in o["split"] for m in [re.search(re.escape(lab), text)] if m)
            parts = [(lab, text[s:(cuts[i + 1][0] if i + 1 < len(cuts) else len(text))]) for i, (s, lab) in enumerate(cuts)]
        res = []
        win = o.get("window", 60)
        for lab, chunk in parts:
            out = {}
            for k, (a, no) in self.names.items():
                if area and a != area:
                    continue
                i = chunk.find(k)
                if i < 0:
                    continue
                m = _NUM.search(chunk, i + len(k), i + len(k) + win)
                if m:
                    out.setdefault(a, {})[no] = int(m.group().replace(",", ""))
            if out:
                c = o.get("channels", {}).get(lab, {}) if lab else {}
                res.append((self._meta(o, id=f"{o['id']}-{c.get('id', lab)}" if lab else o["id"],
                                       label=f"{o.get('label', o['id'])}·{lab}" if lab else o.get("label", o["id"]),
                                       en=f"{o.get('en', o['id'])} · {c.get('en', lab)}" if lab else o.get("en", o["id"]),
                                       cohort=c.get("cohort", o.get("cohort", "field"))), out))
        return res

    def cec_feed(self, o, body, area=None):
        """Fills self.fallback: {("TC", county, town): page} and {("T", page path): page}; page = sent/total/votes/C/E."""
        d = json.loads(body)
        if isinstance(d, dict) and isinstance(d.get("ST"), str) and len(d["ST"]) == 10:  # MMDDHHMMSS
            st = d["ST"]
            self.fallback["stamp"] = f"{st[0:2]}/{st[2:4]} {st[4:6]}:{st[6:8]}:{st[8:10]}"  # as the CEC's pages print it
        groups = d.items() if isinstance(d, dict) else [("TC", d)]
        for kind, rows in groups:
            if not isinstance(rows, list) or kind not in ("TC", "T1", "T2", "T3", "P1"):
                continue
            kind = "TC" if kind == "P1" else kind  # 2024's per-county files (for testing with that year's format)
            for x in rows:
                county = f"{x.get('prvCode', '')}{x.get('cityCode', '')}"
                cands = x.get("candTksInfo") or x.get("cand_tks_infos") or []
                page = {"sent": x.get("tboxRcv"), "total": x.get("tboxTot"), "C": x.get("prof3"), "E": x.get("prof7"),
                        "votes": {int(c["candNo"]): int(c.get("tks") or 0) for c in cands}}
                if page["sent"] is None or page["total"] is None:
                    continue
                if kind == "TC":
                    if x.get("areaCode") or x.get("liCode") or x.get("tboxNo"):
                        continue
                    town = x.get("deptCode") or "000"
                    self.fallback[("TC", county, town)] = page
                elif not x.get("deptCode") and x.get("areaCode"):
                    self.fallback[("T", f"{kind}/{county}{x['areaCode']}0000000000.html")] = page
        return []

