#!/bin/sh
# Runs the bot on macOS/Linux, e.g.:  sh trader.sh validate btcusd-2026-11-20
VENV_PY="$HOME/.alpaca-trader-venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "This computer is not set up yet. Run: sh setup_mac_linux.sh" >&2
  exit 1
fi
PYTHONPATH="$(cd "$(dirname "$0")" && pwd)"
PYTHONDONTWRITEBYTECODE=1
PYTHONIOENCODING=utf-8
export PYTHONPATH PYTHONDONTWRITEBYTECODE PYTHONIOENCODING
exec "$VENV_PY" -m alpaca_bot "$@"
