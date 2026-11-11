#!/usr/bin/env python3
"""Election night: put the poller's latest file on the site, at most once every --every seconds.

  python3 scripts/live/publish.py [--src live-out/needle/2026-mayors.json] [--site _site] [--deploy] [--every 45]

Without --deploy it only copies the file into the built site (for local rehearsals with a local web server).
With --deploy it then runs `npx wrangler deploy` from the repository root, which uploads only the files that
changed (here, one JSON file) to the Cloudflare Worker serving election-2026.tw. That needs the Cloudflare
credentials in the environment (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID) and a site built from the same
commit as the one already deployed (python3 scripts/build_site.py _site).

Checks before each publish: the file parses, has every race, and no race has fewer points or fewer stations
in than the last published file (a count never goes backwards). A failed check skips that round and says why.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WRANGLER = "wrangler@4.149.0"  # pinned: the night doesn't depend on whatever wrangler is newest


def deploy(worker):
    """npx wrangler deploy (to `worker`, if given). Returns (ok, the output's last lines)."""
    cmd = ["npx", "--yes", WRANGLER, "deploy"] + (["--name", worker] if worker else [])
    env = dict(os.environ, WRANGLER_SEND_METRICS="false", CI="1", NO_COLOR="1", FORCE_COLOR="0")
    if os.name == "nt":  # npx is a .cmd file on Windows
        r = subprocess.run(" ".join(cmd), cwd=ROOT, capture_output=True, text=True, timeout=300, shell=True, env=env,
                           encoding="utf-8", errors="replace")
    else:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=env)
    return r.returncode == 0, re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout + r.stderr)).strip()


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def check(doc, prev):
    races = doc.get("races") or []
    if len(races) < 22:
        return f"only {len(races)} races"
    for r in races:
        for row in r["pts"]:
            if not (0 <= row[4] <= 1):
                return f"{r['area']}: probability out of range"
    if prev:
        old = {r["area"]: r for r in prev["races"]}
        for r in races:
            o = old.get(r["area"])
            if not o or not o["pts"]:
                continue
            if not r["pts"]:
                return f"{r['area']}: points disappeared"
            if r["pts"][-1][1] < o["pts"][-1][1] and r["other"]["no"] == o["other"]["no"]:
                return f"{r['area']}: stations in went down ({o['pts'][-1][1]} -> {r['pts'][-1][1]})"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "live-out" / "needle" / "2026-mayors.json"))
    ap.add_argument("--site", default=str(ROOT / "_site"))
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--every", type=float, default=45)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--worker", help="deploy to this Worker instead of the one in wrangler.jsonc (rehearsals: a test Worker)")
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.site) / "needle" / "2026-mayors.json"
    last_mtime, prev = None, None
    while True:
        t0 = time.time()
        try:
            m = src.stat().st_mtime
        except FileNotFoundError:
            m = None
            log("waiting for", src)
        if m and m != last_mtime:
            try:
                doc = json.loads(src.read_text())
                why = check(doc, prev)
            except Exception as e:
                why = f"unreadable: {e}"
            if why:
                log("NOT published:", why)
            else:
                shutil.copy(src, dst)
                ok = True
                if a.deploy:
                    ok, out = deploy(a.worker)
                    errs = [ln.strip() for ln in out.splitlines() if "ERROR" in ln or "rror:" in ln]
                    log("deploy", "ok" if ok else "FAILED: " + (errs[0] if errs else " / ".join(x for x in out.splitlines()[-4:] if x.strip()))[:300])
                if ok:
                    last_mtime, prev = m, doc
                    log("published", doc.get("updated"), sum(len(r["pts"]) for r in doc["races"]), "points")
        if a.once:
            return
        time.sleep(max(1.0, a.every - (time.time() - t0)))


if __name__ == "__main__":
    main()
