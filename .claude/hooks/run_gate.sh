#!/bin/sh
# Launcher for the Trader gate (trader_gate.py) that works on Windows (Git Bash),
# macOS and Linux. It finds whichever Python 3.10+ this computer has.
#
# Fails closed: if no suitable Python is found, an Alpaca order is blocked
# (exit 2). Commands that never mention Alpaca are let through without Python,
# because the gate would ignore them anyway.

dir="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
gate="$dir/.claude/hooks/trader_gate.py"
input="$(cat)"

# Fast path: the gate only acts on calls that mention Alpaca.
lower="$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')"
case "$lower" in
  *alpaca*) ;;
  *) exit 0 ;;
esac

for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    printf '%s' "$input" | PYTHONIOENCODING=utf-8 "$py" -B "$gate"
    exit $?
  fi
done

echo "Trader gate: Python 3.10 or newer was not found on this computer (tried python3, python, py). Alpaca orders stay blocked until it is installed: https://www.python.org/downloads/" >&2
exit 2
