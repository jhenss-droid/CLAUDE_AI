# Trader plans

Each file `<plan_id>.json` is the written result of one Trader skill analysis. An Alpaca order is only accepted when its `client_order_id` is `ct-<plan_id>-<suffix>` and the plan passes the rules in `alpaca_bot/trader_plan.py`.

## Fields

| Field | Meaning |
|---|---|
| `id` | Same as the file name, lowercase, e.g. `btcusd-2026-11-16` |
| `created_at` | ISO time of the analysis. A buy must happen within 36 hours of it |
| `symbol` | `BTC/USD` for crypto, `SPY` for stocks |
| `direction` | `long` (the only direction the paper protocol covers) |
| `status` | `approved` → `open` (filled, stop placed) → `closed`; or `void` |
| `timeframes` | panorámico / principal / sincronización |
| `fase_panoramico` | Fase number on the panoramic timeframe (4 or 5 means no buy) |
| `evento` | `1` or `2` |
| `checklist` | The 6 EBT items, each `PASS` (`FAIL` or `NOT YET` means no trade) |
| `entry`, `target`, `logical_stop`, `stop` | Prices. `target` is the 200 (or 125) level; `logical_stop` is below 38.20 and the last lows; `stop` is the stop actually used |
| `vacio_disponible` | Distance from the entry to the first opposing 1st/2nd-grade level |
| `balance`, `risk_pct`, `simultaneous_trades` | Current balance, risk (at most 0.02), and how many trades share that risk |
| `qty` | Size: `balance × risk_pct ÷ simultaneous_trades ÷ (entry − stop)`, rounded down |
| `max_contracts` | Optional. Most option contracts any single order on this plan may use (the analysis is on the underlying) |
| `analysis` | The Trader output (structured template), including INFERRED/UNKNOWN items |
| `log` | Actions and results |

## Rules checked by code

Stop below entry · reward:risk ≥ 2:1 · logical stop not further than the 2:1 stop · stop at or below the logical stop · vacío ≥ 2 × risk · risk ≤ 2% of the current balance · all 6 checklist items PASS · evento 1 or 2 · not fase 4–5 · long only.

`example-btcusd.json` shows the format. Its status is `void`, so it can never be traded.
