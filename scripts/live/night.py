#!/usr/bin/env python3
"""Election-night runner: everything the machine that reads the CEC needs, behind one command.

  python3 scripts/live/night.py check        # is this computer ready? (about 3 minutes; changes nothing online)
  python3 scripts/live/night.py rehearsal    # the 2022 count replayed on the 2026 ballot, published to a TEST site
  python3 scripts/live/night.py night        # the real thing: CEC count -> needle -> election-2026.tw

Normally started by the setup scripts in site/night/ (mac.sh, win.ps1), which download the code into a folder
"twn-night" in the home folder and make a private Python environment there. This script:

  * keeps the computer awake while it runs (macOS: caffeinate; Windows: SetThreadExecutionState);
  * asks once for the Cloudflare token and account ID and keeps them in twn-night/cloudflare.json;
  * builds the site, then runs the poller (scripts/live/poll.py) and the publisher (scripts/live/publish.py),
    restarting either if it stops, with their full logs in twn-night/logs/;
  * prints one plain status line every 30 seconds.

Stop with Ctrl+C (or by closing the window).
"""
import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = ROOT.parent if ROOT.parent.name == "twn-night" else ROOT  # the setup scripts put the code in twn-night/code
LOGS = WORK / "logs"
OUT = WORK / "live-out"          # the night's snapshots and file (kept: a restart picks up from here)
REH = WORK / "rehearsal-out"     # rehearsals (cleared each time)
CREDS = WORK / "cloudflare.json"
CONFIG = json.loads((ROOT / "data" / "live" / "night-config.json").read_text(encoding="utf-8"))
PY = sys.executable
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def say(msg=""):
    print(msg, flush=True)


def stamp():
    return datetime.now().strftime("%H:%M:%S")


# ---- keep the computer awake ------------------------------------------------------------------------------
def keep_awake():
    system = platform.system()
    if system == "Darwin":
        try:
            return subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
        except OSError:
            pass
    elif system == "Windows":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    return None


# ---- Cloudflare credentials -------------------------------------------------------------------------------
def creds(ask=True):
    if CREDS.exists():
        c = json.loads(CREDS.read_text(encoding="utf-8"))
        if c.get("token") and c.get("account"):
            return c
    if not ask:
        return None
    say()
    say("Hope sent you two codes for Cloudflare (the service that hosts the website).")
    token = input("  Paste the first one (the long TOKEN) and press Enter: ").strip()
    account = input("  Paste the second one (the ACCOUNT ID) and press Enter: ").strip()
    c = {"token": token, "account": account}
    CREDS.write_text(json.dumps(c), encoding="utf-8")
    try:
        os.chmod(CREDS, 0o600)
    except OSError:
        pass
    say("  Saved. (You won't be asked again on this computer.)")
    return c


def cf_env(c):
    return dict(ENV, CLOUDFLARE_API_TOKEN=c["token"], CLOUDFLARE_ACCOUNT_ID=c["account"], WRANGLER_SEND_METRICS="false", CI="1")


def npx(args, env, timeout=300):
    cmd = ["npx", "--yes", "wrangler@4.149.0"] + args
    kw = dict(cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8", errors="replace")
    if os.name == "nt":
        return subprocess.run(" ".join(cmd), shell=True, **kw)
    return subprocess.run(cmd, **kw)


# ---- running the pieces -----------------------------------------------------------------------------------
class Child:
    def __init__(self, name, args, env=ENV):
        self.name, self.args, self.env, self.p, self.restarts = name, args, env, None, 0
        self.log = LOGS / f"{name}.log"

    def start(self):
        fh = open(self.log, "a", encoding="utf-8")
        fh.write(f"\n==== {stamp()} start: {' '.join(self.args)}\n")
        fh.flush()
        self.p = subprocess.Popen([PY, "-u"] + self.args, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env=self.env)

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def keep(self):
        if not self.alive():
            if self.p is not None:
                self.restarts += 1
                say(f"{stamp()}  ! {self.name} stopped (exit {self.p.returncode}); restarting. Details: {self.log}")
            self.start()

    def stop(self):
        if self.alive():
            self.p.terminate()
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()

    def last(self, pattern=None):
        try:
            lines = self.log.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return ""
        for ln in reversed(lines):
            if not pattern or re.search(pattern, ln):
                return ln.strip()
        return ""


def build_site():
    say(f"{stamp()}  Building the site…")
    r = subprocess.run([PY, "scripts/build_site.py", "_site"], cwd=ROOT, capture_output=True, text=True, env=ENV,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        say(r.stdout[-2000:] + r.stderr[-2000:])
        sys.exit("Building the site failed. Send Hope a photo of this window.")


def summary(out):
    f = out / "needle" / "2026-mayors.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return "no results yet"
    counting = sum(1 for r in d["races"] if r["pts"])
    decided = sum(1 for r in d["races"] if r["pts"] and r["pts"][-1][7])
    return f"{counting} of 22 races counting, {decided} decided"


def run(children, banner, out, test_url_from=None):
    for c in children:
        c.start()
    say(banner)
    url_shown = False
    try:
        while True:
            time.sleep(30)
            for c in children:
                c.keep()
            pub = next(c for c in children if c.name == "publish")
            poll = next(c for c in children if c.name == "poll")
            cyc = poll.last(r"cycle ")
            pl = pub.last(r"published|NOT published|FAILED|waiting")
            ok = "FAILED" not in pl and "NOT" not in pl
            say(f"{stamp()}  {'OK ' if ok else '!! '} {summary(out)} | reading: {cyc[9:60] if cyc else 'starting'} | site: {pl[9:80] if pl else 'starting'}")
            if test_url_from and not url_shown:
                m = re.search(r"https://\S+workers\.dev", pub.log.read_text(encoding="utf-8", errors="replace"))
                if m:
                    say(f"\n  The test site is at: {m.group(0)}/live  (open it on your phone and watch it move)\n")
                    url_shown = True
    except KeyboardInterrupt:
        say("\nStopping…")
    finally:
        for c in children:
            c.stop()
        say("Stopped.")


# ---- the three modes --------------------------------------------------------------------------------------
def check():
    results = []

    def step(name, fn):
        say(f"  … {name}")
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, str(e)[:200]
        results.append((ok, name, note))
        say(f"    {'PASS' if ok else 'FAIL'}  {note}")

    def py():
        return sys.version_info >= (3, 9), platform.python_version()

    def pkgs():
        import certifi  # noqa: F401
        import openpyxl  # noqa: F401
        import xlrd  # noqa: F401
        return True, "openpyxl, xlrd, certifi"

    def tests():
        r = subprocess.run([PY, "tests/test_live.py"], cwd=ROOT, capture_output=True, text=True, env=ENV, timeout=600,
                           encoding="utf-8", errors="replace")
        return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else ""

    def cec():
        sys.path.insert(0, str(HERE))
        from poll import SSL, UA
        req = urllib.request.Request("https://info.cec.gov.tw/vote2026/static/contentJson/uioption.json", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20, context=SSL) as r:
            ok = r.status == 200
        base = CONFIG.get("count_base")
        if base:
            try:
                with urllib.request.urlopen(urllib.request.Request(base, headers={"User-Agent": UA}), timeout=20, context=SSL) as r:
                    return ok, f"CEC election page and count site reachable ({r.status})"
            except urllib.error.HTTPError as e:
                return False, f"CEC election page reachable, count site answered {e.code}"
        return ok, "CEC election page reachable (count site address not announced yet)"

    def mini():
        out = WORK / "check-out"
        for f in out.glob("**/*"):
            if f.is_file():
                f.unlink()
        mock = subprocess.Popen([PY, "-u", "scripts/live/mock_cec.py", "--port", "8791", "--speed", "240", "--start", "17:30"],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV)
        try:
            time.sleep(6)
            for _ in range(2):
                r = subprocess.run([PY, "scripts/live/poll.py", "--base", "http://127.0.0.1:8791/zh-TW/", "--out", str(out), "--once"],
                                   cwd=ROOT, capture_output=True, text=True, env=ENV, timeout=300, encoding="utf-8", errors="replace")
                time.sleep(5)
            d = json.loads((out / "needle" / "2026-mayors.json").read_text(encoding="utf-8"))
            n = sum(len(x["pts"]) for x in d["races"])
            return n > 0, f"practice count read and modelled ({n} points)"
        finally:
            mock.terminate()

    def node():
        r = npx(["--version"], ENV, timeout=600)
        return r.returncode == 0, ("wrangler " + r.stdout.strip()) if r.returncode == 0 else (r.stderr.strip()[-200:] or "npx not found: install Node.js")

    def cloud():
        c = creds(ask=False)
        if not c:
            return False, "no Cloudflare codes yet (they're asked for at the rehearsal; fine for now)"
        r = npx(["whoami"], cf_env(c), timeout=300)
        return r.returncode == 0, "Cloudflare codes work" if r.returncode == 0 else r.stdout.strip()[-200:] + r.stderr.strip()[-200:]

    say("\nChecking this computer. This takes a few minutes; nothing is published.\n")
    step("Python", py)
    step("Python packages", pkgs)
    step("The program's own tests", tests)
    step("Reaching the CEC from this computer", cec)
    step("A practice count, start to finish", mini)
    step("Node.js and the publishing tool", node)
    step("Cloudflare codes", cloud)
    say()
    must = [r for r in results if not r[0] and r[1] != "Cloudflare codes"]
    if not must:
        say("ALL GOOD. Please send Hope a photo of this window.")
    else:
        say("Something needs fixing:")
        for _, name, note in must:
            say(f"  - {name}: {note}")
        say("Please send Hope a photo of this window.")


def rehearsal():
    c = creds()
    build_site()
    for f in REH.glob("**/*"):
        if f.is_file():
            f.unlink()
    run([Child("mock", ["scripts/live/mock_cec.py", "--port", "8790", "--speed", "16", "--start", "15:58", "--fail", "0.02"]),
         Child("poll", ["scripts/live/poll.py", "--base", "http://127.0.0.1:8790/zh-TW/", "--out", str(REH), "--interval", "20"]),
         Child("publish", ["scripts/live/publish.py", "--src", str(REH / "needle" / "2026-mayors.json"), "--deploy",
                           "--worker", CONFIG["test_worker"], "--every", "30"], env=cf_env(c))],
        "\nREHEARSAL running: the 2022 count, 16:00 to midnight in 30 minutes, published to a TEST site (not the real one).\n"
        "A status line appears every 30 seconds. Press Ctrl+C to stop.\n", REH, test_url_from=True)


def night():
    base = os.environ.get("TWN_BASE") or CONFIG.get("count_base")
    if not base:
        sys.exit("The CEC count site's address isn't set yet. Ask Hope; nothing has been started.")
    c = creds()
    build_site()
    run([Child("poll", ["scripts/live/poll.py", "--base", base, "--out", str(OUT)]),
         Child("publish", ["scripts/live/publish.py", "--src", str(OUT / "needle" / "2026-mayors.json"), "--deploy",
                           "--worker", CONFIG["worker"]], env=cf_env(c))],
        f"\nELECTION NIGHT running: reading {base} every minute and publishing to election-2026.tw.\n"
        "Leave this window open and the computer plugged in. A status line appears every 30 seconds.\n"
        "Before 16:00 it just waits (\"no results yet\"). Press Ctrl+C only when Hope says it's over.\n", OUT)


def main():
    mode = (sys.argv[1:] or ["check"])[0]
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    keep_awake()
    {"check": check, "rehearsal": rehearsal, "night": night}[mode]()


if __name__ == "__main__":
    main()
