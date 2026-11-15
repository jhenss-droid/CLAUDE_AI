"""The Trader gate: decides whether an order may be sent to Alpaca.

Every order must carry a client_order_id of the form ``ct-<plan_id>-<suffix>``
that points at a valid plan in trader_plans/ (one Trader skill analysis).
That link is always required. What else is checked depends on POLICY below.

Buy (opens a position)
  - plan passes every Trader rule, status "approved", created < 36 h ago
  - same symbol (options: same underlying), qty <= plan qty
  - limit orders: limit price within 1% of the plan entry
  - market orders: allowed when POLICY["market_buys"]
  - stock brackets: stop leg at the plan stop (unless moving stops is allowed)
Sell (closes / protects)
  - plan exists for the same symbol with status "approved" or "open"
  - qty <= plan qty
  - stop / stop-limit sells at the plan stop, unless POLICY["moving_stops"]
  - trailing stops when POLICY["trailing_stops"]

Cancelling orders and closing positions are not gated: they only reduce risk.
"""

from __future__ import annotations

import json
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

# Order types the user has chosen to allow (16 Nov 2026). Several go beyond the
# Trader course (options and trailing stops are not covered; the course says not
# to move stops or objectives). Set any of these to False to block it again.
POLICY = {
    "options": True,          # option orders, tied to a plan on the underlying
    "replace_orders": True,   # changing an order after it is placed
    "market_buys": True,      # market entries (otherwise limit only)
    "trailing_stops": True,   # trailing-stop sells
    "moving_stops": True,     # stops away from the plan stop
    "raw_api_orders": True,   # direct /v2/orders calls (must still name a plan)
}

CLIENT_ID_RE = re.compile(r"^ct-([a-z0-9][a-z0-9-]{2,40}?)-[A-Za-z0-9]{4,}$")
CLIENT_ID_ANYWHERE_RE = re.compile(r"ct-([a-z0-9][a-z0-9-]{2,40}?)-[A-Za-z0-9]{4,}")
OCC_RE = re.compile(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$")
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


def occ_underlying(symbol: str) -> str | None:
    m = OCC_RE.match(symbol.strip().upper())
    return m.group(1) if m else None


def _plan_for(cid: str, plans_dir: Path):
    """(plan, None) for a valid plan reference, else (None, Verdict deny)."""
    m = CLIENT_ID_RE.match(cid or "")
    if not m:
        return None, Verdict(False, f"order has no Trader plan reference. {HOW_TO}")
    try:
        plan = load_plan(m.group(1), plans_dir)
    except PlanError as exc:
        return None, Verdict(False, f"{exc}. {HOW_TO}")
    errors = validate_plan(plan)
    if errors:
        return None, Verdict(False, f"plan {plan.id} breaks Trader rules: " + "; ".join(errors))
    return plan, None


def _status_ok(plan, opening: bool, now: datetime | None) -> Verdict | None:
    if opening:
        if plan.status != "approved":
            return Verdict(False, f"plan {plan.id} is '{plan.status}', opening needs 'approved'")
        if is_expired(plan, now):
            return Verdict(False, f"plan {plan.id} is older than 36 h: re-run the analysis")
    elif plan.status not in ("approved", "open"):
        return Verdict(False, f"plan {plan.id} is '{plan.status}', no exits allowed")
    return None


def check_order(order: dict, plans_dir: Path = DEFAULT_PLANS_DIR,
                now: datetime | None = None) -> Verdict:
    """order: symbol, side, qty, notional, type, limit_price, stop_price,
    client_order_id, order_class, stop_loss_stop_price, take_profit_limit_price."""
    symbol = normalize_symbol(str(order.get("symbol") or ""))
    if occ_underlying(symbol):
        return check_option_order(order, plans_dir, now)

    side = str(order.get("side") or "").lower()
    otype = str(order.get("type") or "market").lower()
    plan, deny = _plan_for(str(order.get("client_order_id") or ""), plans_dir)
    if deny:
        return deny
    if plan.symbol != symbol:
        return Verdict(False, f"plan {plan.id} is for {plan.symbol}, order is for {symbol}")

    qty, notional = _f(order.get("qty")), _f(order.get("notional"))
    if qty is None and notional is None:
        return Verdict(False, "order qty is required")
    if qty is not None and (qty <= 0 or qty > plan.qty * 1.000001):
        return Verdict(False, f"qty {qty:g} must be above 0 and within the plan's "
                              f"2%-risk size {plan.qty:g}")
    if notional is not None and notional > plan.qty * plan.entry * 1.01:
        return Verdict(False, f"notional ${notional:,.2f} exceeds the plan's size "
                              f"(~${plan.qty * plan.entry:,.2f})")

    if side == "buy":
        bad = _status_ok(plan, True, now)
        if bad:
            return bad
        if otype == "market":
            if not POLICY["market_buys"]:
                return Verdict(False, "entries must be limit orders (no market buys)")
        elif otype == "limit":
            if not _within(_f(order.get("limit_price")), plan.entry, 0.01):
                return Verdict(False, f"limit price must be within 1% of the plan entry "
                                      f"{plan.entry:g}")
        else:
            return Verdict(False, f"entry type {otype!r} not allowed (use limit or market)")
        bracket = str(order.get("order_class") or "").lower() == "bracket"
        if bracket or order.get("stop_loss_stop_price"):
            sl = _f(order.get("stop_loss_stop_price"))
            if sl is None:
                return Verdict(False, "a bracket needs a stop-loss leg")
            if not POLICY["moving_stops"] and not _within(sl, plan.stop, 0.005):
                return Verdict(False, f"bracket stop must be at the plan stop {plan.stop:g}")
        return Verdict(True, f"Trader plan {plan.id}: entry approved")

    if side == "sell":
        bad = _status_ok(plan, False, now)
        if bad:
            return bad
        if otype == "trailing_stop" and not POLICY["trailing_stops"]:
            return Verdict(False, "trailing stops are not allowed")
        if (otype in ("stop", "stop_limit") and not POLICY["moving_stops"]
                and not _within(_f(order.get("stop_price")), plan.stop, 0.005)):
            return Verdict(False, f"protective stop must be at the plan stop {plan.stop:g} "
                                  "(do not move the stop)")
        return Verdict(True, f"Trader plan {plan.id}: exit/stop approved")

    return Verdict(False, f"unknown side {side!r}")


def check_option_order(order: dict, plans_dir: Path = DEFAULT_PLANS_DIR,
                       now: datetime | None = None) -> Verdict:
    """Options: every leg's underlying must be the plan's symbol. The plan's
    Trader analysis is on the underlying; contracts are capped by the plan's
    optional `max_contracts`."""
    if not POLICY["options"]:
        return Verdict(False, "options are not allowed")
    plan, deny = _plan_for(str(order.get("client_order_id") or ""), plans_dir)
    if deny:
        return deny
    legs = order.get("legs") or [{"symbol": order.get("symbol"), "side": order.get("side")}]
    for leg in legs:
        und = occ_underlying(str(leg.get("symbol") or ""))
        if und is None:
            return Verdict(False, f"{leg.get('symbol')!r} is not an option contract symbol")
        if und != plan.symbol:
            return Verdict(False, f"plan {plan.id} is for {plan.symbol}, option is on {und}")
    intent = str(order.get("position_intent") or "").lower()
    side = str(order.get("side") or "").lower()
    opening = intent.endswith("to_open") or (not intent and (side == "buy" or len(legs) > 1))
    bad = _status_ok(plan, opening, now)
    if bad:
        return bad
    contracts = _f(order.get("qty"))
    cap = _f(plan.raw.get("max_contracts"))
    if contracts is None or contracts <= 0:
        return Verdict(False, "option qty (contracts) is required")
    if cap is not None and contracts > cap:
        return Verdict(False, f"{contracts:g} contracts exceeds the plan's max_contracts {cap:g}")
    return Verdict(True, f"Trader plan {plan.id}: option order on {plan.symbol} approved")


# ---------------------------------------------------------------- tool inputs

def check_mcp_tool(tool_name: str, tool_input: dict, plans_dir: Path = DEFAULT_PLANS_DIR,
                   now: datetime | None = None) -> Verdict | None:
    """Verdict for an Alpaca MCP tool call, or None if the tool is not gated."""
    action = tool_name.rsplit("__", 1)[-1]
    if action == "place_option_order":
        return check_option_order(tool_input, plans_dir, now)
    if action == "replace_order_by_id":
        if POLICY["replace_orders"]:
            return Verdict(True, "order change allowed (the original order is plan-linked)")
        return Verdict(False, "changing a placed order is not allowed; cancel and re-send")
    if action in ("place_stock_order", "place_crypto_order"):
        return check_order(tool_input, plans_dir, now)
    return None


_CLI_FLAGS = {
    "--symbol": "symbol", "--side": "side", "--qty": "qty", "--notional": "notional",
    "--type": "type", "--limit-price": "limit_price", "--stop-price": "stop_price",
    "--client-order-id": "client_order_id", "--order-class": "order_class",
    "--stop-loss-stop-price": "stop_loss_stop_price",
    "--take-profit-limit-price": "take_profit_limit_price",
    "--position-intent": "position_intent",
}
_RAW_ORDER_RE = re.compile(r"/v2/orders|/v1/orders", re.I)
_RAW_WRITE_RE = re.compile(r"\b(POST|PATCH|PUT)\b|-X\s*(POST|PATCH|PUT)|--data|-d\s", re.I)


def _parse_cli_order(tokens: list[str]) -> dict:
    order: dict = {}
    i = 0
    while i < len(tokens):
        key, _, inline = tokens[i].partition("=")
        if key in _CLI_FLAGS:
            if inline:
                order[_CLI_FLAGS[key]] = inline
            elif i + 1 < len(tokens):
                order[_CLI_FLAGS[key]] = tokens[i + 1]
                i += 1
        i += 1
    return order


def _json_body(command: str) -> dict | None:
    """The order JSON inside a shell command, if there is one with a symbol."""
    start, end = command.find("{"), command.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        body = json.loads(command[start:end + 1])
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, dict) and body.get("symbol") else None


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
                if POLICY["replace_orders"]:
                    return Verdict(True, "order change allowed")
                return Verdict(False, "changing a placed order is not allowed")
            if sub == "submit":
                rest = tokens[i + 3:]
                if "--dry-run" in rest:
                    return None
                return check_order(_parse_cli_order(rest), plans_dir, now)

    # Raw API writes (alpaca api POST /v2/orders, curl ... alpaca.markets/v2/orders)
    if _RAW_ORDER_RE.search(command) and _RAW_WRITE_RE.search(command):
        if not POLICY["raw_api_orders"]:
            return Verdict(False, "raw API order calls are not allowed")
        if re.search(r"\bPATCH\b|-X\s*PATCH", command, re.I):
            if POLICY["replace_orders"]:
                return Verdict(True, "order change via API allowed")
            return Verdict(False, "changing a placed order is not allowed")
        body = _json_body(command)
        if body is not None:
            return check_order(body, plans_dir, now)
        m = CLIENT_ID_ANYWHERE_RE.search(command)
        if not m:
            return Verdict(False, "raw API orders must include client_order_id "
                                  f"'ct-<plan_id>-<suffix>'. {HOW_TO}")
        plan, deny = _plan_for(m.group(0), plans_dir)
        if deny:
            return deny
        if plan.status not in ("approved", "open"):
            return Verdict(False, f"plan {plan.id} is '{plan.status}'")
        return Verdict(True, f"raw API order linked to Trader plan {plan.id} "
                             "(body not parsed: the symbol/qty checks do not apply)")
    return None
