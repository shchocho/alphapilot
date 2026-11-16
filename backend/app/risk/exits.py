"""보호 청산 규칙(손절·익절·추적 손절). AI를 거치지 않는 결정론 규칙이다."""

from __future__ import annotations

from app.core.market_rules import round_down_tick
from app.core.models import Position


def stop_reason(pos: Position) -> str:
    """손절가가 진입 때보다 올라가 있으면 추적 손절로 부른다."""
    initial = pos.avg_price - pos.entry_risk
    return "trail_stop" if pos.stop > initial + 1e-6 else "stop"


def check_protective(pos: Position, open_: float, high: float, low: float) -> tuple[str, float] | None:
    """하루 봉으로 보호 청산 여부를 본다. 반환: (사유, 체결 기준가).

    보수적으로 본다: 시가가 손절 아래면 시가에, 같은 날 손절과 익절이 모두 닿으면 손절이 먼저다.
    """
    if open_ <= pos.stop:
        return stop_reason(pos), open_
    if pos.target is not None and open_ >= pos.target:
        return "target", open_
    if low <= pos.stop:
        return stop_reason(pos), float(pos.stop)
    if pos.target is not None and high >= pos.target:
        return "target", float(pos.target)
    return None


def check_quote(pos: Position, last_price: float) -> str | None:
    """실시간 현재가로 보는 보호 청산(키움 모드의 장중 감시)."""
    if last_price <= pos.stop:
        return stop_reason(pos)
    if pos.target is not None and last_price >= pos.target:
        return "target"
    return None


def trailed_stop(pos: Position, close: float, atr: float) -> int:
    """장 마감 뒤 추적 손절 갱신값. 최고 종가 − 배수 × ATR. 절대 내려가지 않는다."""
    if pos.trail_mult is None or atr <= 0:
        return pos.stop
    highest = max(pos.highest_close, close)
    candidate = round_down_tick(highest - pos.trail_mult * atr)
    return max(pos.stop, candidate)
