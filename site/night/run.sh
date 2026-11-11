#!/bin/bash
# Election-night runner for election-2026.tw, for macOS (and Linux). Paste ONE of these lines into Terminal:
#
#   bash -c "$(curl -fsSL https://election-2026.tw/night/run.sh)"                      # set up, then check this computer
#   TWN_MODE=rehearsal bash -c "$(curl -fsSL https://election-2026.tw/night/run.sh)"   # practice run to a test site
#   TWN_MODE=night bash -c "$(curl -fsSL https://election-2026.tw/night/run.sh)"       # election night
#
# Each time it downloads the latest code into ~/twn-night/code (results and settings in ~/twn-night are kept),
# makes a private Python environment in ~/twn-night/venv, and starts scripts/live/night.py.
set -euo pipefail
MODE="${TWN_MODE:-check}"
DIR="$HOME/twn-night"
ZIP="${TWN_ZIP:-https://github.com/hopehhchen/twn-watch-party-2026/archive/refs/heads/main.zip}"

say() { printf '%s\n' "$*"; }
stop() { say ""; say "STOPPED: $*"; say "Please send Hope a photo of this window."; exit 1; }

say ""
say "=== election-2026.tw night runner ($MODE) ==="

# 1. Python 3.9 or newer (prefer the one from python.org; Apple's /usr/bin/python3 may ask to install developer tools)
PY=""
for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 python3; do
  p="$(command -v "$c" 2>/dev/null || true)"
  [ -z "$p" ] && continue
  if [ "$p" = "/usr/bin/python3" ] && [ "$(uname)" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
  if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$p"; break; fi
done
[ -n "$PY" ] || stop "Python isn't installed yet. Install it from https://www.python.org/downloads/ (step 1 of the guide), then paste the line again."
say "Python: $("$PY" --version 2>&1)"

# 2. Node.js (for the publishing tool)
command -v npx >/dev/null 2>&1 || [ -x /usr/local/bin/npx ] || stop "Node.js isn't installed yet. Install the LTS version from https://nodejs.org/ (step 2 of the guide), then paste the line again."
export PATH="/usr/local/bin:$PATH"
say "Node.js: $(node --version 2>&1)"

# 3. The code (fresh copy each time)
mkdir -p "$DIR"
say "Downloading the program…"
curl -fsSL -o "$DIR/code.zip" "$ZIP" || stop "Couldn't download the program. Is the internet working?"
rm -rf "$DIR/code" "$DIR"/twn-watch-party-2026-*
unzip -q "$DIR/code.zip" -d "$DIR" || stop "Couldn't unpack the program."
mv "$DIR"/twn-watch-party-2026-* "$DIR/code"
rm -f "$DIR/code.zip"

# 4. A private Python environment with the packages the program needs
if [ ! -x "$DIR/venv/bin/python" ]; then
  say "Setting up Python (first time only)…"
  "$PY" -m venv "$DIR/venv" || stop "Couldn't set up Python. (On Linux: sudo apt install python3-venv)"
fi
"$DIR/venv/bin/python" -m pip install -q --disable-pip-version-check openpyxl==3.1.5 xlrd==2.0.2 certifi numpy || stop "Couldn't install the Python packages. Is the internet working?"

# 5. Go
cd "$DIR/code"
export PYTHONUTF8=1
exec "$DIR/venv/bin/python" -u scripts/live/night.py "$MODE"
