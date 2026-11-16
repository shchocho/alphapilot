"""손실 회로차단기. 계좌 수준에서 신규 매수를 막거나 사이즈를 줄이거나 엔진을 세운다.

판단에 필요한 데이터가 불완전하면 막는 쪽으로 간다(fail-closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.risk.limits import RiskLimits


@dataclass(slots=True)
class BreakerState:
    new_buys_blocked: bool = False
    halt_engine: bool = False
    size_multiplier: float = 1.0
    reasons: list[str] = field(default_factory=list)
    daily_pct: float = 0.0
    weekly_pct: float = 0.0
    monthly_pct: float = 0.0
    drawdown_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "new_buys_blocked": self.new_buys_blocked, "halt_engine": self.halt_engine,
            "size_multiplier": self.size_multiplier, "reasons": list(self.reasons),
            "daily_pct": round(self.daily_pct, 5), "weekly_pct": round(self.weekly_pct, 5),
            "monthly_pct": round(self.monthly_pct, 5), "drawdown_pct": round(self.drawdown_pct, 5),
        }


def _base_before(history: list[tuple[date, float]], today: date, same_period) -> float | None:
    """today가 속한 기간(주·월)이 시작되기 직전의 마지막 자산."""
    base = None
    for day, equity in history:
        if day >= today or same_period(day):
            continue
        base = equity
    return base


def evaluate_breakers(
    history: list[tuple[date, float]],
    today: date,
    equity: float,
    peak_equity: float,
    recent_exit_reasons: list[tuple[date, str, float]],
    limits: RiskLimits,
    *,
    data_complete: bool = True,
    previous_trading_day: date | None = None,
) -> BreakerState:
    """history: 과거 일별 자산(오름차순, today 제외 가능). recent_exit_reasons: 최근 청산 (날짜, 사유, 손익) 오름차순."""
    state = BreakerState()
    if not data_complete:
        state.new_buys_blocked = True
        state.reasons.append("데이터가 불완전해 신규 매수를 막았습니다")

    past = [(d, e) for d, e in history if d < today]
    if past and past[-1][1] > 0:
        state.daily_pct = equity / past[-1][1] - 1
    week = today.isocalendar()[:2]
    week_base = _base_before(history, today, lambda d: d.isocalendar()[:2] == week)
    if week_base:
        state.weekly_pct = equity / week_base - 1
    month_base = _base_before(history, today, lambda d: (d.year, d.month) == (today.year, today.month))
    if month_base:
        state.monthly_pct = equity / month_base - 1
    if peak_equity > 0:
        state.drawdown_pct = min(0.0, equity / peak_equity - 1)

    for label, value, limit in (
        ("일", state.daily_pct, limits.daily_loss_limit_pct),
        ("주", state.weekly_pct, limits.weekly_loss_limit_pct),
        ("월", state.monthly_pct, limits.monthly_loss_limit_pct),
    ):
        if value <= -limit:
            state.new_buys_blocked = True
            state.reasons.append(f"{label} 손실 {value * 100:.1f}%가 한도 −{limit * 100:.0f}%에 닿았습니다")

    dd = -state.drawdown_pct
    if dd >= limits.drawdown_halt_pct:
        state.halt_engine = True
        state.new_buys_blocked = True
        state.size_multiplier = 0.0
        state.reasons.append(f"고점 대비 −{dd * 100:.1f}%: 엔진을 정지합니다")
    elif dd >= limits.drawdown_block_pct:
        state.new_buys_blocked = True
        state.size_multiplier = 0.0
        state.reasons.append(f"고점 대비 −{dd * 100:.1f}%: 신규 매수를 중단합니다")
    elif dd >= limits.drawdown_half_pct:
        state.size_multiplier = 0.5
        state.reasons.append(f"고점 대비 −{dd * 100:.1f}%: 주문 크기를 절반으로 줄입니다")
    elif dd >= limits.drawdown_reduce_pct:
        state.size_multiplier = 0.75
        state.reasons.append(f"고점 대비 −{dd * 100:.1f}%: 주문 크기를 75%로 줄입니다")

    n = limits.consecutive_stops_pause
    tail = recent_exit_reasons[-n:]
    if len(tail) == n and all(reason in ("stop", "trail_stop") and pnl < 0 for _, reason, pnl in tail):
        last_day = tail[-1][0]
        if last_day == today or (previous_trading_day is not None and last_day == previous_trading_day):
            state.new_buys_blocked = True
            state.reasons.append(f"손절이 {n}번 이어져 하루 동안 신규 매수를 쉽니다")
    return state
