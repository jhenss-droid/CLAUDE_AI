#!/bin/sh
# One-time setup on a macOS or Linux computer. Safe to run again:
#     sh setup_mac_linux.sh
set -e
PROJECT="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.alpaca-trader-venv"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 &&
     "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required: https://www.python.org/downloads/ (macOS: brew install python)" >&2
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating the Python environment for this computer in $VENV ..."
  "$PY" -m venv "$VENV" || {
    echo "Could not create it. On Debian/Ubuntu run: sudo apt install python3-venv" >&2; exit 1; }
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$PROJECT/requirements.txt"

echo "Running the tests..."
cd "$PROJECT"
"$VENV/bin/python" -B -m pytest -q -p no:cacheprovider
echo
echo "Setup complete. Run the bot with:  sh trader.sh validate <plan_id>"
