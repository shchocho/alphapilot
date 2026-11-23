"""규칙 위원회(결정론). 좌석 의견을 가중 평균해 결론을 낸다.

백테스트의 판단 주체이고, AI 키가 없는 시뮬레이션에서 사용자가 명시적으로 고를 수 있다.
같은 입력에는 항상 같은 결론이 나온다.
"""

from __future__ import annotations

from app.committee.seats import RISK_VETO, blend, seat, votes
from app.core.models import Conviction, Decision, Signal

BUY_THRESHOLD = 0.25
SELL_THRESHOLD = -0.25


def conviction_for(score: float) -> Conviction:
    if score >= 0.60:
        return "very_high"
    if score >= 0.45:
        return "high"
    if score >= 0.30:
        return "medium"
    if score >= BUY_THRESHOLD:
        return "low"
    return "very_low"


def _sentence(seats: list[Signal], stance: str, limit: int = 3) -> str:
    picked = sorted((s for s in seats if s.stance == stance), key=lambda s: abs(s.value) * s.confidence, reverse=True)
    return " · ".join(f"{s.label}: {s.summary}" for s in picked[:limit])


def safety_hold(seats: list[Signal]) -> str | None:
    """좌석 종합과 상관없이 매수를 막는 안전 규칙(리스크 거부권, 약세장). 해당하면 그 사유, 아니면 None."""
    risk = seat(seats, "risk")
    regime = seat(seats, "regime")
    if risk is not None and not risk.abstained and risk.value <= RISK_VETO:
        return f"리스크 좌석 거부권: {risk.summary}"
    if regime is not None and regime.value < 0.0:
        return f"시장 국면이 약해 새로 사지 않습니다: {regime.summary}"
    return None


def decide_entry(code: str, name: str, seats: list[Signal], technique_name: str) -> Decision:
    score = blend(seats)
    tally = votes(seats)
    dissent = _sentence(seats, "bearish")
    blocked = safety_hold(seats)
    if blocked is not None:
        return Decision(code, name, "entry", "HOLD", conviction_for(score), thesis=blocked, dissent=dissent, source="rules", votes=tally)
    if score >= BUY_THRESHOLD:
        return Decision(
            code, name, "entry", "BUY", conviction_for(score),
            thesis=f"{technique_name} 신호. " + _sentence(seats, "bullish"),
            key_risks=[s.summary for s in seats if s.stance == "bearish"][:3],
            invalidation="손절가 이탈 또는 기법의 청산 규칙 충족",
            dissent=dissent, source="rules", votes=tally,
        )
    return Decision(code, name, "entry", "HOLD", conviction_for(score),
                    thesis=f"좌석 의견 종합 {score:+.2f}로 매수 기준 {BUY_THRESHOLD:+.2f}에 못 미칩니다",
                    dissent=dissent, source="rules", votes=tally)


def decide_holding(code: str, name: str, seats: list[Signal], exit_signals: list[str]) -> Decision:
    score = blend(seats)
    tally = votes(seats)
    if exit_signals:
        return Decision(code, name, "holding", "SELL", "high", thesis="청산 규칙 충족: " + ", ".join(exit_signals),
                        source="rules", votes=tally)
    if score <= SELL_THRESHOLD:
        return Decision(code, name, "holding", "SELL", "medium",
                        thesis=f"좌석 의견 종합 {score:+.2f}로 약세. " + _sentence(seats, "bearish"),
                        dissent=_sentence(seats, "bullish"), source="rules", votes=tally)
    return Decision(code, name, "holding", "HOLD", conviction_for(max(score, 0.0)),
                    thesis=f"좌석 의견 종합 {score:+.2f}. 보유 유지", dissent=_sentence(seats, "bearish"),
                    source="rules", votes=tally)
