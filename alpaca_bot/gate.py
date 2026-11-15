"""The Trader gate: decides whether an order may be sent to Alpaca.

Every order must carry a client_order_id of the form ``ct-<plan_id>-<suffix>``
that points at a plan in trader_plans/. The gate then checks:

Buy (opens a long)
  - plan passes every Trader rule, status "approved", created < 36 h ago
  - same symbol, qty <= plan qty
  - limit order, limit price within 1% of the plan entry (no market buys)
  - stock brackets: stop leg at the plan stop and take-profit at the plan target
Sell (closes / protects a long)
  - plan exists for the same symbol with status "approved" or "open"
  - qty <= plan qty
  - a stop or stop-limit sell must sit at the plan stop (within 0.5%)
Always blocked
  - options orders (not part of the method)
  - replacing an order (the method says the order is placed and not touched;
    cancel and re-send through the gate instead)

Cancelling orders and closing positions are not gated: they only reduce risk.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .trader_plan import (
    DEFAULT_PLANS_DIR,
    PlanError,
    is_expired,
    load_plan,
    normalize_symbol,
    validate_plan,
)

CLIENT_ID_RE = re.compile(r"^ct-([a-z0-9][a-z0-9-]{2,40}?)-[A-Za-z0-9]{4,}$")
HOW_TO = (
    "Run the Trader skill on the asset, save the result as trader_plans/<plan_id>.json "
    "(see trader_plans/README.md), then send the order with client_order_id "
    "'ct-<plan_id>-<suffix>'."
)


@dataclass
class Verdict:
    allow: bool
    reason: str


def _f(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _within(value: float | None, ref: float, pct: float) -> bool:
    return value is not None and abs(value - ref) <= ref * pct


def check_order(order: dict, plans_dir: Path = DEFAULT_PLANS_DIR,
                now: datetime | None = None) -> Verdict:
    """order: symbol, side, qty, notional, type, limit_price, stop_price,
    client_order_id, order_class, stop_loss_stop_price, take_profit_limit_price."""
    side = str(order.get("side") or "").lower()
    otype = str(order.get("type") or "market").lower()
    symbol = normalize_symbol(str(order.get("symbol") or ""))
    cid = str(order.get("client_order_id") or "")

    m = CLIENT_ID_RE.match(cid)
    if not m:
        return Verdict(False, f"order has no Trader plan reference. {HOW_TO}")
    try:
        plan = load_plan(m.group(1), plans_dir)
    except PlanError as exc:
        return Verdict(False, f"{exc}. {HOW_TO}")

    if plan.symbol != symbol:
        return Verdict(False, f"plan {plan.id} is for {plan.symbol}, order is for {symbol}")
    errors = validate_plan(plan)
    if errors:
        return Verdict(False, f"plan {plan.id} breaks Trader rules: " + "; ".join(errors))
    if order.get("notional") not in (None, ""):
        return Verdict(False, "size orders by qty from the plan, not by notional amount")
    qty = _f(order.get("qty"))
    if qty is None or qty <= 0:
        return Verdict(False, "order qty is required")
    if qty > plan.qty * 1.000001:
        return Verdict(False, f"qty {qty:g} exceeds the plan's 2%-risk size {plan.qty:g}")

    if side == "buy":
        if plan.status != "approved":
            return Verdict(False, f"plan {plan.id} is '{plan.status}', a buy needs 'approved'")
        if is_expired(plan, now):
            return Verdict(False, f"plan {plan.id} is older than 36 h: re-run the analysis")
        if otype != "limit":
            return Verdict(False, "entries must be limit orders (no market buys)")
        if not _within(_f(order.get("limit_price")), plan.entry, 0.01):
            return Verdict(False, f"limit price must be within 1% of the plan entry {plan.entry:g}")
        if str(order.get("order_class") or "").lower() == "bracket" or order.get(
            "stop_loss_stop_price"
        ):
            if not _within(_f(order.get("stop_loss_stop_price")), plan.stop, 0.005):
                return Verdict(False, f"bracket stop must be at the plan stop {plan.stop:g}")
            tp = _f(order.get("take_profit_limit_price"))
            if tp is not None and not _within(tp, plan.target, 0.005):
                return Verdict(False, f"bracket target must be at the plan target {plan.target:g}")
        return Verdict(True, f"Trader plan {plan.id}: entry approved")

    if side == "sell":
        if plan.status not in ("approved", "open"):
            return Verdict(False, f"plan {plan.id} is '{plan.status}', no sells allowed")
        if otype in ("stop", "stop_limit") and not _within(
            _f(order.get("stop_price")), plan.stop, 0.005
        ):
            return Verdict(False, f"protective stop must be at the plan stop {plan.stop:g} "
                                  "(do not move the stop)")
        if otype == "trailing_stop":
            return Verdict(False, "trailing stops are not part of the method")
        return Verdict(True, f"Trader plan {plan.id}: exit/stop approved")

    return Verdict(False, f"unknown side {side!r}")


# ---------------------------------------------------------------- tool inputs

def check_mcp_tool(tool_name: str, tool_input: dict, plans_dir: Path = DEFAULT_PLANS_DIR,
                   now: datetime | None = None) -> Verdict | None:
    """Verdict for an Alpaca MCP tool call, or None if the tool is not gated."""
    action = tool_name.rsplit("__", 1)[-1]
    if action == "place_option_order":
        return Verdict(False, "options are not part of the Trader method")
    if action == "replace_order_by_id":
        return Verdict(False, "orders are not modified under the Trader method "
                              "('uno coloca la orden y no la toca'); cancel and re-send")
    if action in ("place_stock_order", "place_crypto_order"):
        return check_order(tool_input, plans_dir, now)
    return None


_CLI_FLAGS = {
    "--symbol": "symbol", "--side": "side", "--qty": "qty", "--notional": "notional",
    "--type": "type", "--limit-price": "limit_price", "--stop-price": "stop_price",
    "--client-order-id": "client_order_id", "--order-class": "order_class",
    "--stop-loss-stop-price": "stop_loss_stop_price",
    "--take-profit-limit-price": "take_profit_limit_price",
}
_RAW_ORDER_RE = re.compile(r"/v2/orders|/v1/orders", re.I)
_RAW_WRITE_RE = re.compile(r"\b(POST|PATCH|PUT)\b|-X\s*(POST|PATCH|PUT)|--data|-d\s", re.I)


def _parse_cli_order(tokens: list[str]) -> dict:
    order: dict = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        key, _, inline = tok.partition("=")
        if key in _CLI_FLAGS:
            if inline:
                order[_CLI_FLAGS[key]] = inline
            elif i + 1 < len(tokens):
                order[_CLI_FLAGS[key]] = tokens[i + 1]
                i += 1
        i += 1
    return order


def check_bash(command: str, plans_dir: Path = DEFAULT_PLANS_DIR,
               now: datetime | None = None) -> Verdict | None:
    """Verdict for a shell command that would place an Alpaca order, else None."""
    if "alpaca" not in command.lower():
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    # Alpaca CLI: alpaca order submit|replace ...
    for i, tok in enumerate(tokens):
        if tok.endswith("alpaca") and tokens[i + 1:i + 2] == ["order"]:
            sub = tokens[i + 2] if i + 2 < len(tokens) else ""
            if sub == "replace":
                return Verdict(False, "orders are not modified under the Trader method; "
                                      "cancel and re-send")
            if sub == "submit":
                rest = tokens[i + 3:]
                if "--dry-run" in rest:
                    return None
                return check_order(_parse_cli_order(rest), plans_dir, now)

    # Raw API writes (alpaca api POST /v2/orders, curl ... alpaca.markets/v2/orders)
    if _RAW_ORDER_RE.search(command) and _RAW_WRITE_RE.search(command):
        return Verdict(False, "raw API order calls bypass the Trader checks; use the "
                              "connector, the CLI or 'python -m alpaca_bot execute'")
    return None
