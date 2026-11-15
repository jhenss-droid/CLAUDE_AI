"""Run the bot once: read the account, compute signals, risk-check, (maybe) order.

    python -m alpaca_bot            # dry run: shows what it would do
    python -m alpaca_bot --submit   # sends orders to the PAPER account

Schedule it (cron, a scheduled task) shortly after the market opens.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime, timezone

from .config import Settings
from .risk import OrderIntent, RiskManager
from .strategy import crossover_signal


def run(settings: Settings, broker) -> dict:
    risk = RiskManager(settings)
    acct = broker.account_state()
    summary: dict = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "dry-run" if settings.dry_run else "paper-submit",
        "account": {
            "equity": acct.equity,
            "buying_power": acct.buying_power,
            "daily_pnl_pct": round(risk.daily_pnl_pct(acct) * 100, 3),
            "market_open": acct.market_open,
            "positions": acct.positions,
        },
        "symbols": [],
    }

    for symbol in settings.symbols:
        entry: dict = {"symbol": symbol}
        try:
            closes = broker.daily_closes(symbol, settings.slow_window + 1)
        except Exception as exc:  # one bad symbol should not stop the run
            entry["error"] = f"data: {exc}"
            summary["symbols"].append(entry)
            continue

        signal = crossover_signal(closes, settings.fast_window, settings.slow_window)
        entry["signal"] = signal
        entry["last_close"] = closes[-1] if closes else None
        if signal == "hold":
            summary["symbols"].append(entry)
            continue

        decision = risk.check(OrderIntent(symbol, signal, closes[-1]), acct)
        entry["qty"] = decision.intent.qty
        entry["approved"] = decision.approved
        entry["reasons"] = decision.reasons
        if decision.approved and not settings.dry_run:
            try:
                entry["order_id"] = broker.submit_market(symbol, signal, decision.intent.qty)
            except Exception as exc:
                entry["error"] = f"order: {exc}"
        summary["symbols"].append(entry)

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alpaca_bot")
    parser.add_argument(
        "--submit", action="store_true", help="send approved orders to the paper account"
    )
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.submit:
        settings = dataclasses.replace(settings, dry_run=False)
    settings.validate()

    from .broker import Broker  # imported late so tests need no credentials

    summary = run(settings, Broker(settings))
    json.dump(summary, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
