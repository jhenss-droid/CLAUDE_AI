import pytest

from alpaca_bot.config import Settings
from alpaca_bot.main import run
from alpaca_bot.risk import AccountState, OrderIntent, RiskManager
from alpaca_bot.strategy import crossover_signal, sma

S = Settings(api_key="k", secret_key="s", symbols=("AAA",), fast_window=3, slow_window=5)


def acct(**kw):
    base = dict(equity=100_000, last_equity=100_000, buying_power=200_000,
                trading_blocked=False, market_open=True, positions={})
    base.update(kw)
    return AccountState(**base)


# --- strategy -------------------------------------------------------------

def test_sma():
    assert sma([1, 2, 3, 4], 2) == 3.5
    with pytest.raises(ValueError):
        sma([1], 2)


def test_crossover_buy_sell_hold():
    falling_then_jump = [10, 9, 8, 7, 6, 5, 20]
    rising_then_drop = [5, 6, 7, 8, 9, 10, 1]
    assert crossover_signal(falling_then_jump, 3, 5) == "buy"
    assert crossover_signal(rising_then_drop, 3, 5) == "sell"
    assert crossover_signal([5] * 7, 3, 5) == "hold"
    assert crossover_signal([1, 2], 3, 5) == "hold"  # not enough data


# --- risk -----------------------------------------------------------------

def test_buy_sized_to_max_position_pct():
    d = RiskManager(S).check(OrderIntent("AAA", "buy", 100.0), acct())
    assert d.approved and d.intent.qty == 50  # 5% of 100k / $100


def test_blocks_when_market_closed_or_blocked():
    rm = RiskManager(S)
    assert not rm.check(OrderIntent("AAA", "buy", 100.0), acct(market_open=False)).approved
    assert not rm.check(OrderIntent("AAA", "buy", 100.0), acct(trading_blocked=True)).approved


def test_daily_loss_halt():
    d = RiskManager(S).check(OrderIntent("AAA", "buy", 100.0), acct(equity=97_000))
    assert not d.approved and "daily loss" in d.reasons[0]


def test_no_double_buy_and_no_shorting():
    rm = RiskManager(S)
    assert not rm.check(OrderIntent("AAA", "buy", 100.0), acct(positions={"AAA": 5})).approved
    assert not rm.check(OrderIntent("AAA", "sell", 100.0), acct()).approved
    d = rm.check(OrderIntent("AAA", "sell", 100.0), acct(positions={"AAA": 5}))
    assert d.approved and d.intent.qty == 5


def test_order_cap_per_run():
    s = Settings(api_key="k", secret_key="s", max_orders_per_run=1)
    rm = RiskManager(s)
    assert rm.check(OrderIntent("A", "buy", 10.0), acct()).approved
    assert not rm.check(OrderIntent("B", "buy", 10.0), acct()).approved


def test_settings_always_paper():
    assert Settings().paper is True


# --- end to end with a fake broker ---------------------------------------

class FakeBroker:
    def __init__(self, closes, state):
        self.closes, self.state, self.orders = closes, state, []

    def account_state(self):
        return self.state

    def daily_closes(self, symbol, days):
        return self.closes

    def submit_market(self, symbol, side, qty):
        self.orders.append((symbol, side, qty))
        return "order-1"


def test_dry_run_sends_nothing():
    b = FakeBroker([10, 9, 8, 7, 6, 5, 20], acct())
    out = run(S, b)
    assert out["symbols"][0]["approved"] is True
    assert b.orders == []


def test_submit_mode_places_approved_order():
    import dataclasses
    b = FakeBroker([10, 9, 8, 7, 6, 5, 20], acct())
    out = run(dataclasses.replace(S, dry_run=False), b)
    assert b.orders == [("AAA", "buy", 250)]  # 5% of 100k / $20
    assert out["symbols"][0]["order_id"] == "order-1"
