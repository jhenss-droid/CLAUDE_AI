# Alpaca paper trading under the Trader method

Every Alpaca trade in this repository must come from a **Trader skill** (CreceTrader price action) analysis. There is no automatic signal generator. Trade ideas come only from that analysis, and code enforces the method's hard rules.

```
Trader skill analysis ──► trader_plans/<id>.json ──► validate ──► gated order ──► Alpaca (paper)
```

## How a trade happens

1. Ask Claude for a Trader analysis of the asset, e.g. "Trader: BTC/USD".
2. If the verdict is a trade, Claude saves the plan to `trader_plans/<id>.json` (format: `trader_plans/README.md`).
3. `python -m alpaca_bot validate <id>` checks the plan against the rules.
4. `python -m alpaca_bot execute <id>` shows the orders (dry run); add `--submit` to send them to the paper account.
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

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
```

Keys: `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (paper). When the cloud environment's proxy injects the real keys, set both variables to `proxy-injected`.

The analysis is one trading framework applied to paper trading, not financial advice.
