#!/usr/bin/env python3
"""PreToolUse hook: every Alpaca order must come from a valid Trader plan.

Reads the tool call on stdin and denies it unless alpaca_bot.gate approves.
Fails closed: if anything goes wrong while checking an order tool, the call is denied.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True  # keep __pycache__ out of the synced folder
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def decide(allow: bool, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if allow else "deny",
            "permissionDecisionReason": f"Trader gate: {reason}",
        }
    }))
    sys.exit(0)


def main() -> None:
    try:
        # Read raw bytes as UTF-8: Windows would otherwise decode stdin with its
        # legacy code page and mangle non-ASCII text.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        tool = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}
        from alpaca_bot.gate import check_bash, check_mcp_tool

        if tool in ("Bash", "PowerShell"):
            verdict = check_bash(str(tool_input.get("command", "")))
        else:
            verdict = check_mcp_tool(tool, tool_input)
    except Exception as exc:  # fail closed
        decide(False, f"could not verify the order ({exc!r}); blocked")
        return

    if verdict is None:
        sys.exit(0)  # not an order: normal permission flow
    if verdict.allow:
        # Approved by the gate, but still goes through the normal permission prompt.
        print(f"Trader gate: {verdict.reason}", file=sys.stderr)
        sys.exit(0)
    decide(False, verdict.reason)


if __name__ == "__main__":
    main()
