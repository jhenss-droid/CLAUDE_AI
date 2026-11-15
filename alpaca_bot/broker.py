"""Thin wrapper around alpaca-py so the rest of the bot is easy to test."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from .config import Settings
from .risk import AccountState


class Broker:
    def __init__(self, settings: Settings):
        # paper=True always; see config.py.
        self.trading = TradingClient(settings.api_key, settings.secret_key, paper=True)
        self.data = StockHistoricalDataClient(settings.api_key, settings.secret_key)

    def account_state(self) -> AccountState:
        acct = self.trading.get_account()
        clock = self.trading.get_clock()
        positions = {p.symbol: float(p.qty) for p in self.trading.get_all_positions()}
        return AccountState(
            equity=float(acct.equity),
            last_equity=float(acct.last_equity),
            buying_power=float(acct.buying_power),
            trading_blocked=bool(acct.trading_blocked),
            market_open=bool(clock.is_open),
            positions=positions,
        )

    def daily_closes(self, symbol: str, days: int) -> list[float]:
        end = datetime.now(timezone.utc)
        # Calendar days to cover `days` trading sessions, with slack for holidays.
        start = end - timedelta(days=int(days * 1.6) + 10)
        req = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start, end=end
        )
        bars = self.data.get_stock_bars(req).data.get(symbol, [])
        return [float(b.close) for b in bars]

    def submit_market(self, symbol: str, side: str, qty: int) -> str:
        order = self.trading.submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                # Lets Alpaca reject accidental duplicate submissions.
                client_order_id=f"bot-{uuid.uuid4()}",
            )
        )
        return str(order.id)
