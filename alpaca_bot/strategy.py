"""Moving-average crossover signal.

An example strategy, not a recommendation: it exists to show the plumbing
(data in, signal, risk checks, order out). Replace it with your own logic.
"""

from __future__ import annotations

from typing import Literal, Sequence

Signal = Literal["buy", "sell", "hold"]


def sma(values: Sequence[float], window: int) -> float:
    if window <= 0 or len(values) < window:
        raise ValueError(f"need at least {window} values, got {len(values)}")
    return sum(values[-window:]) / window


def crossover_signal(closes: Sequence[float], fast: int, slow: int) -> Signal:
    """'buy' when the fast average crosses above the slow one on the latest bar,
    'sell' when it crosses below, otherwise 'hold'."""
    if len(closes) < slow + 1:
        return "hold"
    prev, now = closes[:-1], closes
    prev_diff = sma(prev, fast) - sma(prev, slow)
    now_diff = sma(now, fast) - sma(now, slow)
    if prev_diff <= 0 < now_diff:
        return "buy"
    if prev_diff >= 0 > now_diff:
        return "sell"
    return "hold"
