"""Trader (CreceTrader) trade plans and the hard rules every plan must pass.

A plan is the written result of running the Trader skill on an asset. No order
may reach Alpaca unless it belongs to a plan that passes `validate_plan`.
The rules below are the non-negotiable parts of the method (Trader skill v2.0):

- Long only (the paper protocol covers longs; shorts need the skill updated first)
- A stop on every trade, below the entry
- Reward:risk of at least 2:1
- The logical stop (below 38.20 and the last lows) must not be further away than
  the 2:1 stop; if it is, there is no trade
- Vacío disponible >= 2 x the stop distance ("si no hay vacío, no hay entrada")
- Risk at most 2% of the CURRENT balance, split across simultaneous trades
- All six EBT checklist items PASS, and an evento (1 or 2) identified
- Never buy in fases 4-5 / end of a pauta on the panoramic timeframe

The method's judgement calls (where price is, fase counting, pivots, zonas)
stay with the analysis; the code checks the numbers that analysis produced.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_RISK_PCT = 0.02
MIN_REWARD_RISK = 2.0
PLAN_TTL = timedelta(hours=36)  # a buy must happen within ~one daily close of the analysis
TOLERANCE = 1e-6

CHECKLIST_ITEMS = (
    "above_6180_after_fase2",
    "rising_highs_and_lows",
    "close_above_directriz_bajista",
    "referente_superado",
    "two_bullish_closes",
    "vacio_ge_2x_risk",
)
PLAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
STATUSES = {"approved", "open", "closed", "void"}

DEFAULT_PLANS_DIR = Path(__file__).resolve().parent.parent / "trader_plans"


@dataclass
class Plan:
    id: str
    created_at: datetime
    symbol: str
    direction: str
    status: str
    evento: int | None
    fase_panoramico: int | None
    checklist: dict[str, str]
    entry: float
    target: float
    logical_stop: float
    stop: float
    vacio_disponible: float
    balance: float
    risk_pct: float
    qty: float
    simultaneous_trades: int = 1
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def risk_per_unit(self) -> float:
        return self.entry - self.stop

    @property
    def stop_2to1(self) -> float:
        return self.entry - (self.target - self.entry) / 2

    @property
    def reward_risk(self) -> float:
        rpu = self.risk_per_unit
        return (self.target - self.entry) / rpu if rpu > 0 else 0.0

    @property
    def max_risk_amount(self) -> float:
        return self.balance * self.risk_pct / max(self.simultaneous_trades, 1)


class PlanError(ValueError):
    pass


def is_crypto(symbol: str) -> bool:
    return "/" in symbol


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("-", "/")


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def plan_from_dict(d: dict) -> Plan:
    try:
        return Plan(
            id=str(d["id"]),
            created_at=_parse_time(str(d["created_at"])),
            symbol=normalize_symbol(str(d["symbol"])),
            direction=str(d["direction"]).lower(),
            status=str(d.get("status", "approved")).lower(),
            evento=d.get("evento"),
            fase_panoramico=d.get("fase_panoramico"),
            checklist={k: str(v).upper() for k, v in dict(d["checklist"]).items()},
            entry=float(d["entry"]),
            target=float(d["target"]),
            logical_stop=float(d["logical_stop"]),
            stop=float(d["stop"]),
            vacio_disponible=float(d["vacio_disponible"]),
            balance=float(d["balance"]),
            risk_pct=float(d["risk_pct"]),
            qty=float(d["qty"]),
            simultaneous_trades=int(d.get("simultaneous_trades", 1)),
            raw=d,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanError(f"malformed plan: {exc}") from exc


def load_plan(plan_id: str, plans_dir: Path = DEFAULT_PLANS_DIR) -> Plan:
    if not PLAN_ID_RE.match(plan_id):
        raise PlanError(f"invalid plan id {plan_id!r}")
    path = plans_dir / f"{plan_id}.json"
    if not path.is_file():
        raise PlanError(f"no Trader plan file {path.name} in {plans_dir.name}/")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path.name} is not valid JSON: {exc}") from exc
    plan = plan_from_dict(data)
    if plan.id != plan_id:
        raise PlanError(f"{path.name} has id {plan.id!r}, expected {plan_id!r}")
    return plan


def validate_plan(plan: Plan) -> list[str]:
    """Return every Trader rule the plan breaks (empty list = plan is valid)."""
    errs: list[str] = []
    if not PLAN_ID_RE.match(plan.id):
        errs.append("plan id must be 3-41 chars of a-z, 0-9 and '-'")
    if plan.status not in STATUSES:
        errs.append(f"status must be one of {sorted(STATUSES)}")
    if plan.direction != "long":
        errs.append("only long trades are covered by the Trader paper protocol")
    if plan.evento not in (1, 2):
        errs.append("evento must be 1 or 2 (no evento = no trade)")
    if plan.fase_panoramico in (4, 5):
        errs.append("panoramic timeframe is in fase 4-5: do not buy at the end of a pauta")
    elif plan.fase_panoramico is None:
        errs.append("fase_panoramico is required")

    missing = [k for k in CHECKLIST_ITEMS if k not in plan.checklist]
    failing = [k for k in CHECKLIST_ITEMS if plan.checklist.get(k) not in (None, "PASS")]
    if missing:
        errs.append(f"EBT checklist items missing: {', '.join(missing)}")
    if failing:
        errs.append(f"EBT checklist items not PASS: {', '.join(failing)}")

    for name in ("entry", "target", "logical_stop", "stop", "balance", "qty"):
        if not getattr(plan, name) > 0:
            errs.append(f"{name} must be positive")
    if errs:
        return errs

    if not plan.stop < plan.entry:
        errs.append("stop must be below the entry (never trade without a stop)")
    if not plan.target > plan.entry:
        errs.append("target must be above the entry")
    if errs:
        return errs

    if plan.reward_risk + TOLERANCE < MIN_REWARD_RISK:
        errs.append(f"reward:risk {plan.reward_risk:.2f}:1 is below 2:1")
    if plan.logical_stop + TOLERANCE < plan.stop_2to1:
        errs.append(
            f"logical stop {plan.logical_stop:g} is further than the 2:1 stop "
            f"{plan.stop_2to1:g}: no trade (do not shrink the stop to fit 2:1)"
        )
    if plan.stop > plan.logical_stop + TOLERANCE:
        errs.append(
            f"stop {plan.stop:g} is above the logical stop {plan.logical_stop:g} "
            "(below 38.20 and the last lows)"
        )
    if plan.vacio_disponible + TOLERANCE < 2 * plan.risk_per_unit:
        errs.append(
            f"vacío disponible {plan.vacio_disponible:g} < 2 x risk "
            f"{2 * plan.risk_per_unit:g}: si no hay vacío, no hay entrada"
        )
    if not 0 < plan.risk_pct <= MAX_RISK_PCT + TOLERANCE:
        errs.append(f"risk_pct {plan.risk_pct:.2%} must be above 0 and at most 2%")
    risk_amount = plan.qty * plan.risk_per_unit
    if risk_amount > plan.max_risk_amount * 1.005:
        errs.append(
            f"position risk ${risk_amount:,.2f} exceeds {plan.risk_pct:.2%} of balance"
            f"{' split across trades' if plan.simultaneous_trades > 1 else ''} "
            f"(${plan.max_risk_amount:,.2f})"
        )
    return errs


def max_qty(plan: Plan, decimals: int = 6) -> float:
    """Course sizing: monto de riesgo / riesgo por unidad, rounded down."""
    q = plan.max_risk_amount / plan.risk_per_unit
    factor = 10**decimals
    return math.floor(q * factor) / factor


def is_expired(plan: Plan, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now - plan.created_at > PLAN_TTL
