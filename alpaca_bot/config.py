"""Bot settings, read from environment variables.

Paper trading is hard-wired: there is no setting that switches this bot to a
live account. Going live should be a deliberate code change, not a typo in an
environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    secret_key: str = ""
    symbols: tuple[str, ...] = ("SPY", "AAPL", "MSFT")
    fast_window: int = 10
    slow_window: int = 30
    # Largest single position, as a fraction of account equity.
    max_position_pct: float = 0.05
    # Stop opening positions once the day's loss reaches this fraction of equity.
    max_daily_loss_pct: float = 0.02
    max_orders_per_run: int = 3
    # Dry run logs what would be ordered without sending anything.
    dry_run: bool = True
    paper: bool = field(default=True, init=False)

    @classmethod
    def from_env(cls) -> "Settings":
        symbols = os.environ.get("BOT_SYMBOLS", "SPY,AAPL,MSFT")
        return cls(
            api_key=os.environ.get("ALPACA_API_KEY", ""),
            secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
            symbols=tuple(s.strip().upper() for s in symbols.split(",") if s.strip()),
            fast_window=int(os.environ.get("BOT_FAST_WINDOW", 10)),
            slow_window=int(os.environ.get("BOT_SLOW_WINDOW", 30)),
            max_position_pct=float(os.environ.get("BOT_MAX_POSITION_PCT", 0.05)),
            max_daily_loss_pct=float(os.environ.get("BOT_MAX_DAILY_LOSS_PCT", 0.02)),
            max_orders_per_run=int(os.environ.get("BOT_MAX_ORDERS_PER_RUN", 3)),
            dry_run=_env_bool("BOT_DRY_RUN", True),
        )

    def validate(self) -> None:
        if not self.api_key or not self.secret_key:
            raise SystemExit(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set (use paper-trading keys)."
            )
        if self.fast_window >= self.slow_window:
            raise SystemExit("BOT_FAST_WINDOW must be smaller than BOT_SLOW_WINDOW.")
        if not 0 < self.max_position_pct <= 0.25:
            raise SystemExit("BOT_MAX_POSITION_PCT must be between 0 and 0.25.")
