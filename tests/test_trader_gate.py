import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from alpaca_bot.gate import check_bash, check_mcp_tool, check_order
from alpaca_bot.main import cmd_execute
from alpaca_bot.trader_plan import load_plan, max_qty, plan_from_dict, validate_plan

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)

BASE = {
    "id": "btc-test",
    "created_at": "2026-11-16T00:05:00Z",
    "symbol": "BTC/USD",
    "direction": "long",
    "status": "approved",
    "fase_panoramico": 3,
    "evento": 1,
    "checklist": {k: "PASS" for k in (
        "above_6180_after_fase2", "rising_highs_and_lows", "close_above_directriz_bajista",
        "referente_superado", "two_bullish_closes", "vacio_ge_2x_risk")},
    "entry": 101575, "target": 109765, "logical_stop": 97900, "stop": 97480,
    "vacio_disponible": 9000, "balance": 100000, "risk_pct": 0.02, "qty": 0.4884,
}


def plan(**kw):
    d = json.loads(json.dumps(BASE))
    d.update(kw)
    return d


@pytest.fixture
def plans(tmp_path):
    def write(**kw):
        d = plan(**kw)
        (tmp_path / f"{d['id']}.json").write_text(json.dumps(d))
        return tmp_path
    return write


# ------------------------------------------------------------- plan rules

def test_valid_plan_passes():
    assert validate_plan(plan_from_dict(plan())) == []


@pytest.mark.parametrize("change, expected", [
    ({"direction": "short"}, "only long"),
    ({"evento": None}, "evento"),
    ({"fase_panoramico": 5}, "fase 4-5"),
    ({"stop": 102000}, "below the entry"),
    ({"target": 105000}, "2:1"),
    ({"logical_stop": 96000, "stop": 96000}, "logical stop"),
    ({"stop": 98000}, "above the logical stop"),
    ({"vacio_disponible": 5000}, "vacío"),
    ({"risk_pct": 0.03}, "at most 2%"),
    ({"qty": 1.0}, "exceeds"),
])
def test_rule_violations(change, expected):
    errs = validate_plan(plan_from_dict(plan(**change)))
    assert any(expected in e for e in errs), errs


def test_checklist_item_not_pass():
    d = plan()
    d["checklist"]["two_bullish_closes"] = "NOT YET"
    assert any("two_bullish_closes" in e for e in validate_plan(plan_from_dict(d)))


def test_risk_split_across_simultaneous_trades():
    errs = validate_plan(plan_from_dict(plan(simultaneous_trades=2)))
    assert any("split" in e for e in errs)


def test_sizing_matches_course_formula():
    assert max_qty(plan_from_dict(plan())) == pytest.approx(0.4884, abs=1e-4)


def test_example_plan_is_valid_format_but_void():
    p = load_plan("example-btcusd", REPO / "trader_plans")
    assert p.status == "void"
    assert validate_plan(p) == []


# ------------------------------------------------------------- order gate

def buy(**kw):
    o = {"symbol": "BTC/USD", "side": "buy", "qty": "0.4884", "type": "limit",
         "limit_price": "101600", "time_in_force": "ioc", "client_order_id": "ct-btc-test-e1a2b3"}
    o.update(kw)
    return o


def test_buy_with_valid_plan_allowed(plans):
    assert check_order(buy(), plans(), NOW).allow


@pytest.mark.parametrize("change, expected", [
    ({"client_order_id": None}, "no Trader plan reference"),
    ({"client_order_id": "ct-nope-e1a2b3"}, "no Trader plan file"),
    ({"symbol": "ETH/USD"}, "is for BTC/USD"),
    ({"qty": "1"}, "exceeds"),
    ({"type": "market", "limit_price": None}, "limit orders"),
    ({"limit_price": "105000"}, "within 1%"),
    ({"notional": "1000", "qty": None}, "notional"),
])
def test_buy_rejections(plans, change, expected):
    v = check_order(buy(**change), plans(), NOW)
    assert not v.allow and expected in v.reason, v.reason


def test_expired_or_used_plan_blocks_buy(plans):
    d = plans()
    assert not check_order(buy(), d, NOW + timedelta(hours=40)).allow
    assert "needs 'approved'" in check_order(buy(), plans(status="open"), NOW).reason


def test_invalid_plan_blocks_buy(plans):
    v = check_order(buy(), plans(fase_panoramico=4), NOW)
    assert not v.allow and "fase 4-5" in v.reason


def test_protective_stop_must_be_at_plan_stop(plans):
    d = plans(status="open")
    stop = {"symbol": "BTC/USD", "side": "sell", "qty": "0.4884", "type": "stop_limit",
            "stop_price": "97480", "limit_price": "97190", "client_order_id": "ct-btc-test-s9f8e7"}
    assert check_order(stop, d, NOW).allow
    moved = dict(stop, stop_price="95000")
    assert "do not move the stop" in check_order(moved, d, NOW).reason
    exit_sell = {"symbol": "BTC/USD", "side": "sell", "qty": "0.4884", "type": "limit",
                 "limit_price": "109765", "client_order_id": "ct-btc-test-x1x2x3"}
    assert check_order(exit_sell, d, NOW).allow
    assert not check_order(exit_sell, plans(status="closed"), NOW).allow


def test_stock_bracket_must_match_plan(plans):
    d = plans(id="spy-test", symbol="SPY", entry=500, target=540, logical_stop=481,
              stop=480, vacio_disponible=45, qty=100)
    o = {"symbol": "SPY", "side": "buy", "qty": "100", "type": "limit", "limit_price": "500",
         "order_class": "bracket", "stop_loss_stop_price": "480",
         "take_profit_limit_price": "540", "client_order_id": "ct-spy-test-e1a2b3"}
    assert check_order(o, d, NOW).allow
    assert not check_order(dict(o, stop_loss_stop_price="450"), d, NOW).allow


def test_mcp_tools():
    assert not check_mcp_tool("mcp__Alpaca_Paper_Trading__place_option_order", {"qty": "1"}).allow
    assert not check_mcp_tool("mcp__Alpaca_Paper_Trading__replace_order_by_id",
                              {"order_id": "x"}).allow
    assert not check_mcp_tool("mcp__alpaca__place_crypto_order",
                              {"symbol": "BTC/USD", "side": "buy", "qty": "1"}).allow
    assert check_mcp_tool("mcp__Alpaca_Paper_Trading__get_account_info", {}) is None
    assert check_mcp_tool("mcp__Alpaca_Paper_Trading__cancel_order_by_id", {}) is None


def test_bash_routes(plans):
    d = plans()
    ok = ("alpaca order submit --symbol BTC/USD --side buy --qty 0.4884 --type limit "
          "--limit-price 101600 --client-order-id ct-btc-test-e1a2b3")
    assert check_bash(ok, d, NOW).allow
    assert not check_bash("alpaca order submit --symbol AAPL --side buy --qty 10 --type market",
                          d, NOW).allow
    assert check_bash("alpaca order submit --symbol AAPL --side buy --qty 1 --dry-run", d) is None
    assert not check_bash("alpaca order replace --order-id x --qty 2", d).allow
    assert not check_bash("echo '{}' | alpaca api POST /v2/orders", d).allow
    assert not check_bash("curl -X POST https://paper-api.alpaca.markets/v2/orders -d '{}'",
                          d).allow
    assert check_bash("alpaca account get", d) is None
    assert check_bash("alpaca order list", d) is None
    assert check_bash("ls -la", d) is None


# ------------------------------------------------------------- executor

def test_execute_dry_run_builds_gated_orders(plans):
    d = plans(created_at=datetime.now(timezone.utc).isoformat())
    out = cmd_execute("btc-test", submit=False, broker=None, plans_dir=d)
    assert out["result"].startswith("dry-run")
    assert out["entry_order"]["type"] == "limit"
    assert out["stop_order"]["stop_price"] == "97480.0"


def test_execute_cuts_size_when_balance_fell(plans):
    class B:
        def equity(self):
            return 90_000

        def submit_entry(self, *a):
            return "e1"

        def filled_qty(self, oid):
            return "filled", float(self.qty)

        def submit_stop(self, symbol, qty, stop, limit, cid):
            self.stop_qty = qty
            return "s1"

    d = plans(created_at=datetime.now(timezone.utc).isoformat())
    b = B()
    b.qty = "0.43956"
    out = cmd_execute("btc-test", submit=True, broker=b, plans_dir=d)
    assert float(out["entry_order"]["qty"]) < 0.4884
    assert out["stop_order_id"] == "s1" and b.stop_qty == 0.43956


def test_execute_rejects_invalid_plan(plans):
    d = plans(fase_panoramico=5, created_at=datetime.now(timezone.utc).isoformat())
    assert cmd_execute("btc-test", submit=False, plans_dir=d)["result"] == "rejected"


# ------------------------------------------------------------- the hook itself

def run_hook(event):
    r = subprocess.run([sys.executable, str(REPO / ".claude/hooks/trader_gate.py")],
                       input=json.dumps(event), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout


def test_hook_denies_unplanned_connector_order():
    code, out = run_hook({"tool_name": "mcp__Alpaca_Paper_Trading__place_crypto_order",
                          "tool_input": {"symbol": "BTC/USD", "side": "buy", "qty": "0.1"}})
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hook_ignores_non_orders():
    assert run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}) == (0, "")
    assert run_hook({"tool_name": "mcp__Alpaca_Paper_Trading__get_clock",
                     "tool_input": {}}) == (0, "")


def test_hook_fails_closed_on_bad_input():
    code, out = run_hook({"tool_name": "mcp__Alpaca_Paper_Trading__place_stock_order",
                          "tool_input": {"symbol": None, "side": None, "qty": {"x": 1}}})
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
