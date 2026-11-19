"""Credentials. Paper trading is hard-wired: nothing here can select a live account.

Where the keys come from, first match wins (an empty value is skipped):

1. ``.env`` in the project folder. It is git-ignored, but if the project lives
   in Google Drive this file is synced to Google along with everything else.
2. ``.alpaca_bot.env`` in your home folder (``C:\\Users\\<you>`` on Windows,
   ``~`` on macOS/Linux). It stays on that one computer: recommended when the
   project folder is in Google Drive.
3. The ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY`` environment variables
   (used by Claude Code cloud sessions).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
HOME_ENV_FILE = Path.home() / ".alpaca_bot.env"


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse KEY=VALUE lines; ignores blanks, comments and surrounding quotes."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    # utf-8-sig also reads files that Windows Notepad saved with a BOM.
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    secret_key: str = ""

    @classmethod
    def from_env(cls, env_file: Path = ENV_FILE,
                 home_env_file: Path | None = None) -> "Settings":
        sources = [read_env_file(env_file), read_env_file(home_env_file or HOME_ENV_FILE)]

        def get(name: str) -> str:
            for values in sources:
                if values.get(name):
                    return values[name]
            return os.environ.get(name, "")

        return cls(api_key=get("ALPACA_API_KEY"), secret_key=get("ALPACA_SECRET_KEY"))

    def validate(self) -> None:
        if not self.api_key or not self.secret_key:
            raise SystemExit(
                "Alpaca paper keys not found. Put ALPACA_API_KEY and ALPACA_SECRET_KEY in "
                f"{HOME_ENV_FILE} (recommended) or in {ENV_FILE}, or set them as environment "
                "variables. In Claude Code cloud sessions, set ALPACA_SECRET_KEY to "
                "'proxy-injected'."
            )
