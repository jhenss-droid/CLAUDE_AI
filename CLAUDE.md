# Project rules

## Every Alpaca trade goes through the Trader skill

This rule covers all Alpaca orders made from this repository: the Alpaca Paper Trading connector, the local `alpaca-mcp-server`, the `alpaca` CLI, and `python -m alpaca_bot`.

1. **Analyse first.** Run the Trader skill (CreceTrader price action) on the asset and follow its 14-step procedure. Do not use moving averages, RSI, MACD or any other indicator as a signal.
2. **Write the plan.** Save the result as `trader_plans/<plan_id>.json`, using the format in `trader_plans/README.md`. Then run `python -m alpaca_bot validate <plan_id>` and fix the plan or drop the trade until it is valid.
3. **Send orders that reference the plan.** Every order's `client_order_id` must be `ct-<plan_id>-<suffix>`. `python -m alpaca_bot execute <plan_id> --submit` does this for you.
4. **No plan, no trade.** If the analysis says no trade, do not place one. Never edit a plan's numbers to get past a check.

`.claude/hooks/trader_gate.py` enforces this by blocking any order that has no valid plan. Do not disable or work around the hook.

The user has allowed these order types, as long as each order references a valid plan:
- options, on the plan's underlying, capped by the plan's `max_contracts` when it sets one
- changing an order after it is placed
- market buys
- trailing stops
- moving a stop
- direct API order calls

Options and trailing stops are not covered by the Trader course, and the course says not to move stops or objectives. When using any of these, say so in the plan's `log`. The switches are in `POLICY` at the top of `alpaca_bot/gate.py`.

Paper trading only. Any real-money order needs the user's explicit confirmation every time, and real-money trading is not configured in this repository.

After every action, log it in the plan file: set `status` and fill in the `log` entries (date, entry, stop, target, result, fees, R multiple).
