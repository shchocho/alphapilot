"""위원회 좌석(결정론). 관점마다 −1~+1 의견과 확신을 내고, 데이터가 없으면 기권한다.

좌석 이름은 실존 투자자가 아니라 관점이다. AI는 이 좌석들의 의견을 증거로 읽고 토론한다.
"""

from __future__ import annotations

import math

from app.core.models import Signal, TechniqueResult
from app.indicators.features import Market
from app.regime.regime import RegimeState
from app.techniques import momentum, trend, value

SEAT_WEIGHTS: dict[str, float] = {
    "trend": 0.20,
    "breakout": 0.20,
    "growth": 0.15,
    "momentum": 0.15,
    "overheat": 0.10,
    "value": 0.05,
    "risk": 0.10,
    "regime": 0.15,
}
SEAT_LABELS: dict[str, str] = {
    "trend": "추세",
    "breakout": "돌파",
    "growth": "성장·수급",
    "momentum": "모멘텀",
    "overheat": "과열·눌림",
    "value": "가치",
    "risk": "리스크",
    "regime": "시장 국면",
}
RISK_VETO = -0.6  # 리스크 좌석이 이 값 이하면 규칙 위원회는 매수하지 않는다


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _nan(x: float) -> bool:
    return isinstance(x, float) and math.isnan(x)


def _abstain(seat: str, why: str, as_of: str) -> Signal:
    return Signal(seat=seat, label=SEAT_LABELS[seat], value=0.0, confidence=0.0, abstained=True, summary=why, as_of=as_of)


def _components(result: TechniqueResult) -> list[dict]:
    return [{"name": c.label, "points": 1 if c.passed else 0, "max_points": 1, "detail": f"{c.value} (기준 {c.threshold})"} for c in result.checks]


def build_seats(market: Market, code: str, i: int, results: dict[str, TechniqueResult], regime: RegimeState) -> list[Signal]:
    feat = market.stocks[code]
    f = feat.f
    as_of = feat.day(i).isoformat()
    c = float(feat.close[i])
    seats: list[Signal] = []

    # 추세
    tt = results[trend.TREND_KEY]
    if tt.state == "insufficient":
        seats.append(_abstain("trend", "일봉이 부족해 추세를 판단하지 않습니다", as_of))
    else:
        seats.append(Signal("trend", SEAT_LABELS["trend"], _clip((tt.score / 100.0 - 0.5) * 2), 0.8,
                            summary=f"트렌드 템플릿 {tt.passed_count}/7 통과", components=_components(tt), as_of=as_of))

    # 돌파
    breakouts = [results[k] for k in (trend.VCP_KEY, momentum.TURTLE_KEY, momentum.BURST_KEY)]
    passed = [r for r in breakouts if r.passed]
    if all(r.state == "insufficient" for r in breakouts):
        seats.append(_abstain("breakout", "일봉이 부족해 돌파를 판단하지 않습니다", as_of))
    elif passed:
        best = max(passed, key=lambda r: r.score)
        seats.append(Signal("breakout", SEAT_LABELS["breakout"], _clip(0.5 + 0.5 * best.score / 100.0), 0.7,
                            summary=f"{', '.join(r.name for r in passed)} 신호", components=_components(best), as_of=as_of))
    elif any(r.state == "extended" for r in breakouts):
        seats.append(Signal("breakout", SEAT_LABELS["breakout"], -0.2, 0.5, summary="돌파 뒤 이미 늘어진 구간", as_of=as_of))
    else:
        seats.append(Signal("breakout", SEAT_LABELS["breakout"], 0.0, 0.3, summary="돌파 신호 없음", as_of=as_of))

    # 성장·수급 (CANSLIM 일봉 요소)
    cs = results[momentum.CANSLIM_KEY]
    if cs.state == "insufficient":
        seats.append(_abstain("growth", "일봉이 부족합니다", as_of))
    else:
        seats.append(Signal("growth", SEAT_LABELS["growth"], _clip((cs.score - 50.0) / 50.0), 0.6,
                            summary=f"신고가·수급 점수 {cs.score:.0f}", components=_components(cs), as_of=as_of))

    # 모멘텀
    rs_arr = market.rs_pct.get(code)
    rs = float(rs_arr[i]) if rs_arr is not None else float("nan")
    mom = float(f["mom_12_1"][i])
    if _nan(rs) or _nan(mom):
        seats.append(_abstain("momentum", "1년 치 봉이 없어 모멘텀을 계산하지 않습니다", as_of))
    else:
        v = 0.6 * (rs - 50.0) / 50.0 + 0.4 * _clip(mom / 0.5)
        seats.append(Signal("momentum", SEAT_LABELS["momentum"], _clip(v), 0.7,
                            summary=f"상대강도 {rs:.0f}, 12-1개월 수익률 {mom * 100:+.0f}%",
                            components=[{"name": "상대강도 백분위", "points": round(rs), "max_points": 100, "detail": ""},
                                        {"name": "12-1개월 수익률", "points": round(mom * 100, 1), "max_points": None, "detail": "%"}],
                            as_of=as_of))

    # 과열·눌림
    sma20, sma200, rsi2 = float(f["sma20"][i]), float(f["sma200"][i]), float(f["rsi2"][i])
    if _nan(sma20) or _nan(rsi2):
        seats.append(_abstain("overheat", "일봉이 부족합니다", as_of))
    else:
        ext = c / sma20 - 1.0
        if ext > 0.10:
            v, text = -_clip((ext - 0.10) / 0.15, 0.0, 1.0), f"20일선 대비 {ext * 100:+.0f}%로 과열"
        elif rsi2 < 10 and not _nan(sma200) and c > sma200:
            v, text = 0.4, f"상승 추세 속 단기 눌림(RSI2 {rsi2:.0f})"
        else:
            v, text = 0.0, f"20일선 대비 {ext * 100:+.0f}%, 과열 아님"
        seats.append(Signal("overheat", SEAT_LABELS["overheat"], v, 0.5, summary=text, as_of=as_of))

    # 가치
    vc = results[value.VALUE_KEY]
    if vc.state == "insufficient":
        seats.append(_abstain("value", vc.notes[0] if vc.notes else "재무 데이터 없음", as_of))
    else:
        seats.append(Signal("value", SEAT_LABELS["value"], _clip((vc.score - 50.0) / 50.0), 0.6,
                            summary=f"업종 안 가치 점수 {vc.score:.0f}", components=_components(vc), as_of=as_of))

    # 리스크
    atr = float(f["atr14"][i])
    value20 = float(f["value20"][i])
    if _nan(atr) or _nan(value20) or c <= 0:
        seats.append(_abstain("risk", "변동성·유동성 데이터가 부족합니다", as_of))
    else:
        atr_pct = atr / c
        v = 0.2 if atr_pct < 0.04 else -0.2 if atr_pct < 0.06 else -0.6
        notes = [f"일 변동성(ATR) {atr_pct * 100:.1f}%"]
        if value20 < 5_000_000_000:
            v -= 0.3
            notes.append(f"거래대금 {value20 / 1e8:.0f}억으로 얇음")
        worst = float(min(f["ret1"][max(0, i - 59) : i + 1], default=0.0))
        if worst < -0.15:
            v -= 0.2
            notes.append(f"최근 60일 최대 하루 낙폭 {worst * 100:.0f}%")
        seats.append(Signal("risk", SEAT_LABELS["risk"], _clip(v), 0.7, summary=", ".join(notes), as_of=as_of))

    # 시장 국면
    seats.append(Signal("regime", SEAT_LABELS["regime"], _clip((regime.score - 50.0) / 50.0), 0.8,
                        summary=f"{regime.label} (점수 {regime.score:.0f}, 노출 상한 {regime.exposure_cap * 100:.0f}%)",
                        components=regime.components, as_of=regime.day.isoformat()))
    return seats


def blend(seats: list[Signal]) -> float:
    """좌석 의견의 가중 평균(−1~+1). 기권한 좌석은 빼고 가중치를 다시 나눈다. 확신이 가중치에 곱해진다."""
    num = den = 0.0
    for s in seats:
        if s.abstained:
            continue
        w = SEAT_WEIGHTS.get(s.seat, 0.0) * s.confidence
        num += w * s.value
        den += w
    return num / den if den > 0 else 0.0


def votes(seats: list[Signal]) -> dict[str, int]:
    counts = {"bullish": 0, "bearish": 0, "neutral": 0, "abstain": 0}
    for s in seats:
        counts[s.stance] += 1
    return counts


def seat(seats: list[Signal], name: str) -> Signal | None:
    return next((s for s in seats if s.seat == name), None)
