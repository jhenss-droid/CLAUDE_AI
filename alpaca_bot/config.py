"""Credentials. Paper trading is hard-wired: nothing here can select a live account."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    secret_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.environ.get("ALPACA_API_KEY", ""),
            secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
        )

    def validate(self) -> None:
        if not self.api_key or not self.secret_key:
            raise SystemExit(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set (paper keys; when the "
                "proxy injects them, set both to 'proxy-injected')."
            )
