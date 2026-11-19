# Alpaca paper trading under the Trader method

Every Alpaca trade in this repository must come from a **Trader skill** (CreceTrader price action) analysis. There is no automatic signal generator. Trade ideas come only from that analysis, and code enforces the method's hard rules.

```
Trader skill analysis ──► trader_plans/<id>.json ──► validate ──► gated order ──► Alpaca (paper)
```

## Use it from any computer (Google Drive)

The project folder can live in Google Drive, e.g. `G:\My Drive\Claude` on Windows or `~/Google Drive/My Drive/Claude` on a Mac, and run from every computer that syncs it.

**What's shared through Drive:** the code, your Trader plans in `trader_plans/` and the safety rules.
**What stays on each computer:** Python, its packages (in `.alpaca-trader-venv` in your home folder) and, by default, your keys.

### Once per computer

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/. On Windows, tick "Add python.exe to PATH".
2. Windows only: install **Git for Windows** (https://git-scm.com/download/win). Claude Code uses its Git Bash to run the Trader safety check.
3. Run the setup script from the project folder:
   - Windows: double-click `setup_windows.bat`
   - macOS/Linux: `sh setup_mac_linux.sh`

   It creates the per-computer Python environment, installs the packages and runs the tests.
4. Save your paper keys in `.alpaca_bot.env` in your home folder. Copy the layout from `.env.example`.

Optional: the `alpaca` CLI and the local `alpaca-mcp-server` aren't needed. The Alpaca connector in the Claude app works on every computer you're signed in on.

### Running the bot

| | Windows | macOS/Linux |
|---|---|---|
| Check a plan | `trader.bat validate <id>` | `sh trader.sh validate <id>` |
| Dry run | `trader.bat execute <id>` | `sh trader.sh execute <id>` |
| Send to paper | `trader.bat execute <id> --submit` | `sh trader.sh execute <id> --submit` |

### Things to avoid in a synced folder

- **Don't run two computers on the same plan at the same time.** Drive may create "conflict" copies of a plan file.
- **Don't put the Python environment or the `.git` folder inside Drive.** They're computer-specific and break when synced. GitHub (`jhenss-droid/claude_ai`) keeps the history.
- **Keep keys out of Drive.** A `.env` file in the project folder works, but Drive syncs it to Google along with everything else.

## How a trade happens

1. Ask Claude for a Trader analysis of the asset, e.g. "Trader: BTC/USD".
2. If the verdict is a trade, Claude saves the plan to `trader_plans/<id>.json` (format: `trader_plans/README.md`).
3. `trader.bat validate <id>` (or `sh trader.sh validate <id>`, or `python -m alpaca_bot validate <id>` in a cloud session) checks the plan against the rules.
4. `trader.bat execute <id>` shows the orders (dry run); add `--submit` to send them to the paper account.
   - Crypto: a limit IOC entry, then a GTC stop-limit for the quantity actually filled.
   - Stocks: a limit bracket order with the stop and target attached.

## What is enforced

`alpaca_bot/trader_plan.py` checks every plan: stop below entry · reward:risk ≥ 2:1 · logical stop not further than the 2:1 stop · vacío disponible ≥ 2 × risk · risk ≤ 2% of the **current** balance (split across simultaneous trades) · all 6 EBT checklist items PASS · evento 1 or 2 · no buying in fases 4–5 · long only.

`.claude/hooks/trader_gate.py` (registered in `.claude/settings.json`) runs before every order Claude Code tries to place, whether through the Alpaca connector, a local Alpaca MCP server, the `alpaca` CLI or a raw API call. It blocks the order unless its `client_order_id` is `ct-<plan_id>-…` and the plan is valid. Order quantity can't exceed the plan's 2%-risk size, and a limit entry must be within 1% of the plan's entry.

These order types are **allowed**, each still tied to a plan. Turn any of them off in `POLICY` at the top of `alpaca_bot/gate.py`:

| Switch | What it allows |
|---|---|
| `options` | Option orders and spreads on the plan's underlying. Contracts are capped by the plan's `max_contracts` when it sets one |
| `replace_orders` | Changing an order after it's placed |
| `market_buys` | Market entries, sized by qty or a dollar amount within the plan's size |
| `trailing_stops` | Trailing-stop sells |
| `moving_stops` | Stops away from the plan's stop |
| `raw_api_orders` | Direct `/v2/orders` calls. When the order JSON is in the command, it gets the full checks; otherwise it must at least name a valid plan |

Options and trailing stops aren't covered by the Trader course, and the course says not to move stops or objectives. These switches are your choice to go beyond the method.

Cancelling orders and closing positions are always allowed, because they only reduce risk.

## Limits

The hook applies to Claude Code sessions in this repository. It can't control orders placed:
- in Alpaca's website or app
- from claude.ai chats or scheduled tasks outside this repository
- by other programs that use your keys

The safety check runs through `.claude/hooks/run_gate.sh`, which finds whichever Python 3.10+ the computer has (`python3`, `python` or `py`). It's set to **block** an order if it can't run, for example on a computer without Python, so a missing install can't let an unchecked order through.

## Tests

The setup scripts run them. Manually: `python -m pytest -q`.

Keys are read from, in order: `.env` in the project folder, `.alpaca_bot.env` in your home folder, then the `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` environment variables. In Claude Code cloud sessions the proxy injects the Secret Key, so `ALPACA_SECRET_KEY` is set to `proxy-injected` there.

The analysis is one trading framework applied to paper trading, not financial advice.
