"""Pre-trade risk checks. Every order passes through `RiskManager.check`."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import Settings


@dataclass
class AccountState:
    equity: float
    last_equity: float
    buying_power: float
    trading_blocked: bool
    market_open: bool
    positions: dict[str, float] = field(default_factory=dict)  # symbol -> qty


@dataclass
class OrderIntent:
    symbol: str
    side: str  # "buy" or "sell"
    price: float
    qty: int = 0


@dataclass
class Decision:
    approved: bool
    intent: OrderIntent
    reasons: list[str]


class RiskManager:
    def __init__(self, settings: Settings):
        self.s = settings
        self.orders_approved = 0

    def daily_pnl_pct(self, acct: AccountState) -> float:
        if acct.last_equity <= 0:
            return 0.0
        return (acct.equity - acct.last_equity) / acct.last_equity

    def halted(self, acct: AccountState) -> str | None:
        if acct.trading_blocked:
            return "account trading is blocked"
        if not acct.market_open:
            return "market is closed"
        if self.daily_pnl_pct(acct) <= -self.s.max_daily_loss_pct:
            return (
                f"daily loss {self.daily_pnl_pct(acct):.2%} hit limit "
                f"-{self.s.max_daily_loss_pct:.2%}"
            )
        return None

    def check(self, intent: OrderIntent, acct: AccountState) -> Decision:
        reasons: list[str] = []
        held = acct.positions.get(intent.symbol, 0.0)

        halt = self.halted(acct)
        if halt:
            reasons.append(halt)
        if self.orders_approved >= self.s.max_orders_per_run:
            reasons.append(f"order cap of {self.s.max_orders_per_run} per run reached")
        if intent.price <= 0:
            reasons.append("no valid price")

        if intent.side == "buy":
            if held > 0:
                reasons.append(f"already holding {held:g} {intent.symbol}")
            budget = min(acct.equity * self.s.max_position_pct, acct.buying_power)
            qty = math.floor(budget / intent.price) if intent.price > 0 else 0
            if qty < 1:
                reasons.append(f"position budget ${budget:,.2f} buys less than 1 share")
            intent.qty = qty
        elif intent.side == "sell":
            # Long-only: sell closes what we hold, never opens a short.
            if held <= 0:
                reasons.append(f"no {intent.symbol} position to sell")
            intent.qty = int(held)
        else:
            reasons.append(f"unknown side {intent.side!r}")

        approved = not reasons
        if approved:
            self.orders_approved += 1
        return Decision(approved, intent, reasons)
