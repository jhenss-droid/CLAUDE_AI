"""Execute Trader plans on the Alpaca PAPER account.

    python -m alpaca_bot validate <plan_id>          # check a plan against the rules
    python -m alpaca_bot execute <plan_id>           # dry run: show the orders
    python -m alpaca_bot execute <plan_id> --submit  # send them to the paper account

There is no signal generation here: trade ideas come only from the Trader skill.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys

from .gate import check_order
from .trader_plan import (
    DEFAULT_PLANS_DIR, PlanError, is_crypto, load_plan, max_qty, validate_plan,
)


def _cid(plan_id: str, leg: str) -> str:
    return f"ct-{plan_id}-{leg}{secrets.token_hex(3)}"


def cmd_validate(plan_id: str, plans_dir=DEFAULT_PLANS_DIR) -> int:
    try:
        plan = load_plan(plan_id, plans_dir)
    except PlanError as exc:
        print(f"INVALID: {exc}")
        return 1
    errors = validate_plan(plan)
    report = {
        "plan": plan.id, "symbol": plan.symbol, "status": plan.status,
        "reward_risk": round(plan.reward_risk, 3), "stop_2to1": round(plan.stop_2to1, 6),
        "risk_per_unit": round(plan.risk_per_unit, 6),
        "max_risk_amount": round(plan.max_risk_amount, 2),
        "max_qty": max_qty(plan), "plan_qty": plan.qty,
        "valid": not errors, "errors": errors,
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


def build_orders(plan, equity: float) -> tuple[dict, dict | None, list[str]]:
    """Entry (and, for crypto, protective stop) orders for a plan, sized on CURRENT equity."""
    notes: list[str] = []
    qty = plan.qty
    current_cap = equity * plan.risk_pct / max(plan.simultaneous_trades, 1) / plan.risk_per_unit
    if qty > current_cap:
        qty = float(f"{current_cap:.6f}") if is_crypto(plan.symbol) else float(int(current_cap))
        notes.append(f"qty cut to {qty:g}: balance is now ${equity:,.2f} (2% rule uses the "
                     "current balance)")
    if not is_crypto(plan.symbol):
        qty = float(int(qty))
    entry = {
        "symbol": plan.symbol, "side": "buy", "qty": str(qty), "type": "limit",
        "limit_price": str(plan.entry), "client_order_id": _cid(plan.id, "e"),
    }
    stop = None
    if is_crypto(plan.symbol):
        stop = {
            "symbol": plan.symbol, "side": "sell", "qty": str(qty), "type": "stop_limit",
            "stop_price": str(plan.stop), "limit_price": str(round(plan.stop * 0.997, 2)),
            "client_order_id": _cid(plan.id, "s"),
        }
    else:
        entry.update(order_class="bracket", stop_loss_stop_price=str(plan.stop),
                     take_profit_limit_price=str(plan.target))
    return entry, stop, notes


def cmd_execute(plan_id: str, submit: bool, broker=None, plans_dir=DEFAULT_PLANS_DIR) -> dict:
    plan = load_plan(plan_id, plans_dir)
    errors = validate_plan(plan)
    if errors:
        return {"plan": plan_id, "result": "rejected", "errors": errors}
    equity = broker.equity() if broker else plan.balance
    entry, stop, notes = build_orders(plan, equity)
    if float(entry["qty"]) <= 0:
        return {"plan": plan_id, "result": "rejected", "errors": ["size rounds to zero"]}

    for order in filter(None, (entry, stop)):
        verdict = check_order(order, plans_dir)
        if not verdict.allow:
            return {"plan": plan_id, "result": "rejected", "errors": [verdict.reason]}

    out: dict = {"plan": plan_id, "mode": "paper-submit" if submit else "dry-run",
                 "entry_order": entry, "stop_order": stop, "notes": notes}
    if not submit:
        out["result"] = "dry-run: nothing sent"
        return out

    entry_id = broker.submit_entry(plan.symbol, float(entry["qty"]), plan.entry,
                                   entry["client_order_id"], plan.stop, plan.target)
    out["entry_order_id"] = entry_id
    if stop is None:  # stock bracket: stop went with the entry
        out["result"] = "entry sent with bracket stop/target; verify it fills"
        return out
    status, filled = broker.filled_qty(entry_id)
    out["entry_status"], out["filled_qty"] = status, filled
    if filled <= 0:
        out["result"] = f"entry not filled ({status}); no position, no stop needed"
        return out
    out["stop_order_id"] = broker.submit_stop(plan.symbol, filled, plan.stop,
                                              float(stop["limit_price"]),
                                              stop["client_order_id"])
    out["result"] = ("filled; protective stop sent for the filled qty. Update the plan "
                     "status to 'open' and log the trade.")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="alpaca_bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("plan_id")
    e = sub.add_parser("execute")
    e.add_argument("plan_id")
    e.add_argument("--submit", action="store_true", help="send to the PAPER account")
    args = p.parse_args(argv)

    if args.cmd == "validate":
        return cmd_validate(args.plan_id)

    broker = None
    if args.submit:
        from .broker import Broker
        from .config import Settings

        settings = Settings.from_env()
        settings.validate()
        broker = Broker(settings)
    try:
        out = cmd_execute(args.plan_id, args.submit, broker)
    except PlanError as exc:
        out = {"plan": args.plan_id, "result": "rejected", "errors": [str(exc)]}
    json.dump(out, sys.stdout, indent=2, default=str)
    print()
    return 0 if out.get("result") != "rejected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
