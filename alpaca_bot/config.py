"""Credentials. Paper trading is hard-wired: nothing here can select a live account.

Keys come from a `.env` file in the repository folder when it exists (it is
git-ignored, so it is never pushed), otherwise from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse KEY=VALUE lines; ignores blanks, comments and surrounding quotes."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    secret_key: str = ""

    @classmethod
    def from_env(cls, env_file: Path = ENV_FILE) -> "Settings":
        file_values = read_env_file(env_file)

        def get(name: str) -> str:
            # A non-empty value in .env wins over the environment variable.
            return file_values.get(name) or os.environ.get(name, "")

        return cls(api_key=get("ALPACA_API_KEY"), secret_key=get("ALPACA_SECRET_KEY"))

    def validate(self) -> None:
        if not self.api_key or not self.secret_key:
            raise SystemExit(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set (paper keys; when the "
                "proxy injects them, set both to 'proxy-injected')."
            )
