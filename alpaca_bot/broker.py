"""Thin wrapper around alpaca-py (paper account only)."""

from __future__ import annotations

import time

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    StopLimitOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from .config import Settings
from .trader_plan import is_crypto


class Broker:
    def __init__(self, settings: Settings):
        self.trading = TradingClient(settings.api_key, settings.secret_key, paper=True)

    def equity(self) -> float:
        return float(self.trading.get_account().equity)

    def position_qty(self, symbol: str) -> float:
        for p in self.trading.get_all_positions():
            if p.symbol.replace("/", "") == symbol.replace("/", ""):
                return float(p.qty)
        return 0.0

    def submit_entry(self, symbol: str, qty: float, limit_price: float, client_order_id: str,
                     stop: float, target: float) -> str:
        if is_crypto(symbol):
            # Protocol step 5: limit IOC slightly above the ask; fills now or cancels.
            req = LimitOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY,
                                    time_in_force=TimeInForce.IOC, limit_price=limit_price,
                                    client_order_id=client_order_id)
        else:
            # Stocks: stop goes in with the entry as a bracket (never trade without a stop).
            req = LimitOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY,
                                    time_in_force=TimeInForce.DAY, limit_price=limit_price,
                                    client_order_id=client_order_id,
                                    order_class=OrderClass.BRACKET,
                                    take_profit=TakeProfitRequest(limit_price=target),
                                    stop_loss=StopLossRequest(stop_price=stop))
        return str(self.trading.submit_order(req).id)

    def filled_qty(self, order_id: str, wait_s: float = 10.0) -> tuple[str, float]:
        deadline = time.time() + wait_s
        while True:
            o = self.trading.get_order_by_id(order_id)
            status = str(o.status.value if hasattr(o.status, "value") else o.status)
            if status in {"filled", "canceled", "expired", "rejected"} or time.time() > deadline:
                return status, float(o.filled_qty or 0)
            time.sleep(1)

    def submit_stop(self, symbol: str, qty: float, stop: float, limit: float,
                    client_order_id: str) -> str:
        req = StopLimitOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL,
                                    time_in_force=TimeInForce.GTC, stop_price=stop,
                                    limit_price=limit, client_order_id=client_order_id)
        return str(self.trading.submit_order(req).id)
