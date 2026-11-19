"""Checks that the project keeps working when copied to another computer,
e.g. a Google Drive folder such as 'G:\\My Drive\\Claude' (note the space)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from alpaca_bot.trader_plan import load_plan, validate_plan

REPO = Path(__file__).resolve().parents[1]
SH = shutil.which("sh")
needs_sh = pytest.mark.skipif(SH is None, reason="no POSIX sh on this computer")

ORDER = {"tool_name": "mcp__Alpaca_Paper_Trading__place_crypto_order",
         "tool_input": {"symbol": "BTC/USD", "side": "buy", "qty": "0.1"}}
NOT_AN_ORDER = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}


def test_plan_saved_by_windows_notepad_loads(tmp_path):
    example = json.loads((REPO / "trader_plans/example-btcusd.json").read_text(encoding="utf-8"))
    example["analysis"] = "Vacío disponible ≥ 2 × riesgo; fase 3 — sincronización OK"
    raw = json.dumps(example, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    (tmp_path / "example-btcusd.json").write_bytes(b"\xef\xbb\xbf" + raw.encode("utf-8"))
    plan = load_plan("example-btcusd", tmp_path)
    assert validate_plan(plan) == []
    assert "Vacío" in plan.raw["analysis"]


def test_hook_uses_project_dir_placeholder_and_fails_closed():
    settings = json.loads((REPO / ".claude/settings.json").read_text(encoding="utf-8"))
    hook = settings["hooks"]["PreToolUse"][0]
    assert "PowerShell" in hook["matcher"] and "Bash" in hook["matcher"]
    cmd = hook["hooks"][0]
    assert '"${CLAUDE_PROJECT_DIR}/.claude/hooks/run_gate.sh"' in cmd["command"]
    assert cmd["onFailure"] == "block"


@pytest.fixture
def drive_copy(tmp_path):
    """A copy of the project in a folder whose path has a space, like 'My Drive'."""
    dest = tmp_path / "My Drive" / "Claude"
    shutil.copytree(REPO, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache"))
    return dest


def run_launcher(project: Path, event: dict, path_env: str | None = None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    if path_env is not None:
        env["PATH"] = path_env
    return subprocess.run([SH, str(project / ".claude/hooks/run_gate.sh")],
                          input=json.dumps(event), capture_output=True, text=True,
                          env=env, timeout=60)


@needs_sh
def test_launcher_blocks_unplanned_order_from_path_with_spaces(drive_copy):
    r = run_launcher(drive_copy, ORDER)
    assert r.returncode == 0
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not list(drive_copy.rglob("__pycache__")), "hook should not write bytecode"


@needs_sh
def test_launcher_lets_non_alpaca_commands_through(drive_copy):
    r = run_launcher(drive_copy, NOT_AN_ORDER)
    assert (r.returncode, r.stdout) == (0, "")


@needs_sh
def test_launcher_without_python_blocks_orders_only(drive_copy, tmp_path):
    # A PATH that has the basic shell tools but no Python at all.
    bin_dir = tmp_path / "bin-no-python"
    bin_dir.mkdir()
    for tool in ("cat", "tr", "dirname"):
        found = shutil.which(tool)
        assert found, tool
        (bin_dir / tool).symlink_to(found)
    r = run_launcher(drive_copy, ORDER, path_env=str(bin_dir))
    assert r.returncode == 2 and "Python 3.10" in r.stderr
    r = run_launcher(drive_copy, NOT_AN_ORDER, path_env=str(bin_dir))
    assert r.returncode == 0


def test_windows_scripts_use_crlf_and_unix_scripts_use_lf():
    for name in ("setup_windows.bat", "trader.bat"):
        data = (REPO / name).read_bytes()
        assert data.count(b"\r\n") == data.count(b"\n"), name
    for name in ("setup_mac_linux.sh", "trader.sh", ".claude/hooks/run_gate.sh"):
        assert b"\r" not in (REPO / name).read_bytes(), name
