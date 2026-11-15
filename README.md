# Alpaca paper-trading starter bot

A small, testable bot: daily bars → moving-average crossover signal → risk checks → market order.
It is **paper-only** (hard-wired in `alpaca_bot/config.py`) and **dry-run by default**.

The strategy is an example, not a recommendation. Replace `alpaca_bot/strategy.py` with your own logic.

## Run

```bash
pip install -r requirements.txt
python -m pytest -q             # offline tests, no keys needed
python -m alpaca_bot            # dry run: prints what it would do as JSON
python -m alpaca_bot --submit   # sends approved orders to the PAPER account
```

Keys come from `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (see `.env.example`). Never commit them.

## Risk checks (`alpaca_bot/risk.py`)

- No orders when the market is closed or the account is blocked
- Halts new orders once the day's loss reaches `BOT_MAX_DAILY_LOSS_PCT` (default 2%)
- Each position is capped at `BOT_MAX_POSITION_PCT` of equity (default 5%) and by buying power
- At most `BOT_MAX_ORDERS_PER_RUN` orders per run (default 3)
- Long-only: never doubles up a position, and sells only what it holds (no shorting)
- Every order carries a unique `client_order_id`, so Alpaca rejects duplicate submissions

## Related tools installed in the cloud environment

- `alpaca` CLI (`go install github.com/alpacahq/cli/cmd/alpaca@latest`)
- `alpaca-mcp-server` (`uv tool install alpaca-mcp-server`)
