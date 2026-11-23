"""시장 국면: 분산일, 팔로스루 데이(FTD), 시장 폭을 묶어 총 노출 상한을 정한다.

규칙은 오닐 계열 시장 타이밍(분산일·FTD)과 tradermonty exposure-coach의 결합 방식을 따른다.
수급 입력(기관·외국인)은 1차 범위에 없어 가중치를 나머지 입력으로 다시 나눈다.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np

from app.indicators.features import Features, Market
from app.techniques.momentum import market_m_score


@dataclass(frozen=True, slots=True)
class RegimeParams:
    dist_drop: float = -0.002  # 지수 −0.2% 이하
    dist_window: int = 25
    dist_recover: float = 0.05  # 분산일 종가 대비 +5% 회복하면 소멸
    correction_drop: float = -0.03
    correction_down_days: int = 3
    ftd_gain: float = 0.0125
    ftd_first_day: int = 4
    ftd_last_day: int = 10
    buy_floor: float = 50.0  # 결합 점수가 이 값 미만이면 신규 매수 금지
    cash_floor: float = 30.0  # 이 값 미만이면 현금 우선


DEFAULT_REGIME_PARAMS = RegimeParams()

_DIST_CAP = {"normal": 1.0, "caution": 1.0, "high": 0.75, "severe": 0.5}
_DIST_SCORE = {"normal": 100.0, "caution": 70.0, "high": 40.0, "severe": 15.0}
_DIST_LABEL = {"normal": "정상", "caution": "주의", "high": "높음", "severe": "심각"}
_CYCLE_SCORE = {"uptrend": 80.0, "confirmed": 75.0, "rally_attempt": 45.0, "correction": 20.0}
_CYCLE_LABEL = {"uptrend": "상승 추세", "confirmed": "FTD 확인", "rally_attempt": "반등 시도", "correction": "조정"}


@dataclass(slots=True)
class RegimeState:
    day: date
    score: float
    label: str  # 상승 | 중립 | 하락
    exposure_cap: float  # 0~1
    allow_new_buys: bool
    dist_level: str
    dist_counts: tuple[int, int, int]  # (25일, 15일, 5일)
    cycle: str
    index_distance: float
    breadth_above200: float
    uptrend_ratio: float
    components: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["day"] = self.day.isoformat()
        data["dist_label"] = _DIST_LABEL[self.dist_level]
        data["cycle_label"] = _CYCLE_LABEL[self.cycle]
        for key in ("index_distance", "breadth_above200", "uptrend_ratio", "score", "exposure_cap"):
            value = data[key]
            data[key] = None if isinstance(value, float) and math.isnan(value) else round(value, 4)
        return data


def distribution_flags(idx: Features, p: RegimeParams = DEFAULT_REGIME_PARAMS) -> np.ndarray:
    """분산일 여부(불리언 배열). 지수가 기준 이상 하락하고 거래량이 전일보다 늘어난 날."""
    ret = idx.f["ret1"]
    volume = idx.volume
    flags = np.zeros(len(idx), dtype=bool)
    flags[1:] = (ret[1:] <= p.dist_drop) & (volume[1:] > volume[:-1])
    return flags


def distribution_counts(idx: Features, t: int, flags: np.ndarray, p: RegimeParams = DEFAULT_REGIME_PARAMS) -> tuple[int, int, int]:
    """t일 기준 살아 있는 분산일 수 (25·15·5세션). 이후 지수가 +5% 회복한 분산일은 뺀다."""
    counts = [0, 0, 0]
    start = max(1, t - p.dist_window + 1)
    for j in range(start, t + 1):
        if not flags[j]:
            continue
        if j < t and float(np.max(idx.close[j + 1 : t + 1])) >= idx.close[j] * (1 + p.dist_recover):
            continue
        age = t - j
        counts[0] += 1
        if age < 15:
            counts[1] += 1
        if age < 5:
            counts[2] += 1
    return counts[0], counts[1], counts[2]


def distribution_level(counts: tuple[int, int, int]) -> str:
    d25, d15, d5 = counts
    if d25 >= 6 or d15 >= 4:
        return "severe"
    if d25 >= 5 or d15 >= 3 or d5 >= 2:
        return "high"
    if d25 >= 3:
        return "caution"
    return "normal"


def cycle_states(idx: Features, p: RegimeParams = DEFAULT_REGIME_PARAMS) -> list[str]:
    """날짜별 시장 주기 상태: uptrend → correction → rally_attempt → confirmed(FTD)."""
    n = len(idx)
    close, low, volume = idx.close, idx.low, idx.volume
    states = ["uptrend"] * n
    state = "uptrend"
    peak = float(close[0])
    down_days = 0
    swing_low = 0.0
    rally_day = 0
    ftd_low: float | None = None
    for t in range(1, n):
        c = float(close[t])
        ret = c / float(close[t - 1]) - 1.0
        volume_up = volume[t] > volume[t - 1]
        if state in ("uptrend", "confirmed"):
            if c >= peak:
                peak, down_days = c, 0
                if state == "confirmed":
                    state, ftd_low = "uptrend", None
            else:
                if ret < 0:
                    down_days += 1
                failed_ftd = state == "confirmed" and ftd_low is not None and c < ftd_low
                if failed_ftd or (c / peak - 1.0 <= p.correction_drop and down_days >= p.correction_down_days):
                    state, swing_low, rally_day, ftd_low = "correction", c, 0, None
        elif state == "correction":
            if c >= peak:
                state, peak, down_days = "uptrend", c, 0
            elif c < swing_low:
                swing_low, rally_day = c, 0
            elif ret > 0:
                state, rally_day = "rally_attempt", 1
        else:  # rally_attempt
            if c >= peak:
                state, peak, down_days = "uptrend", c, 0
            elif c < swing_low:
                state, swing_low, rally_day = "correction", c, 0
            else:
                rally_day += 1
                if p.ftd_first_day <= rally_day <= p.ftd_last_day and ret >= p.ftd_gain and volume_up:
                    state, ftd_low, down_days = "confirmed", float(low[t]), 0
        states[t] = state
    return states


def _breadth_score(ratio: float) -> float:
    for floor, score in ((0.70, 95.0), (0.60, 80.0), (0.50, 65.0), (0.40, 45.0), (0.30, 30.0)):
        if ratio >= floor:
            return score
    return 15.0


def _participation_score(ratio: float) -> float:
    for floor, score in ((0.50, 90.0), (0.37, 70.0), (0.25, 50.0), (0.097, 30.0)):
        if ratio >= floor:
            return score
    return 10.0


def exposure_from_score(score: float) -> float:
    """결합 점수 → 총 노출 상한(0~1). 구간별 선형."""
    if score >= 80:
        return 1.0
    if score >= 65:
        return 0.75 + (score - 65) / 15 * 0.25
    if score >= 50:
        return 0.50 + (score - 50) / 15 * 0.25
    if score >= 30:
        return 0.25 + (score - 30) / 20 * 0.25
    return max(0.0, score / 30 * 0.25)


def compute_regime(market: Market, p: RegimeParams = DEFAULT_REGIME_PARAMS) -> list[RegimeState]:
    """달력의 모든 날짜에 대한 국면. 각 날짜의 값은 그날 장 마감까지의 데이터만 쓴다."""
    idx = market.indexes["KOSPI"]
    flags = distribution_flags(idx, p)
    cycles = cycle_states(idx, p)
    out: list[RegimeState] = []
    for t, day in enumerate(market.calendar):
        ema50 = float(idx.f["ema50"][t])
        distance = float(idx.close[t]) / ema50 - 1.0 if not math.isnan(ema50) and ema50 > 0 else float("nan")
        m_score = market_m_score(distance)
        counts = distribution_counts(idx, t, flags, p)
        level = distribution_level(counts)
        above = float(market.breadth.above200_ema8[t])
        participation = float(market.breadth.uptrend_ratio[t])
        cycle = cycles[t]

        parts: list[tuple[str, str, float, float, str]] = []  # (key, name, weight, score, detail)
        missing: list[str] = []
        if math.isnan(distance):
            missing.append("지수 추세")
        else:
            parts.append(("trend", "지수 추세", 0.25, m_score, f"코스피 50일선 이격 {distance * 100:+.1f}%"))
        parts.append(("top_risk", "천장 위험(분산일)", 0.20, _DIST_SCORE[level], f"25일 {counts[0]}개 · {_DIST_LABEL[level]}"))
        if math.isnan(above):
            missing.append("시장 폭")
        else:
            parts.append(("breadth", "시장 폭(200일선 위 비율)", 0.15, _breadth_score(above), f"{above * 100:.0f}%"))
        if math.isnan(participation):
            missing.append("상승 추세 참여율")
        else:
            parts.append(("participation", "상승 추세 참여율", 0.15, _participation_score(participation), f"{participation * 100:.0f}%"))
        parts.append(("cycle", "시장 주기", 0.10, _CYCLE_SCORE[cycle], _CYCLE_LABEL[cycle]))

        weight_sum = sum(w for _, _, w, _, _ in parts)
        score = sum(w * s for _, _, w, s, _ in parts) / weight_sum if weight_sum else 0.0
        score = max(0.0, score - 10.0 * len(missing))
        cap = min(exposure_from_score(score), _DIST_CAP[level])
        allow = score >= p.buy_floor and m_score > 0
        label = "상승" if score >= 65 else "중립" if score >= p.buy_floor else "하락"
        out.append(RegimeState(
            day=day, score=score, label=label, exposure_cap=cap, allow_new_buys=allow, dist_level=level,
            dist_counts=counts, cycle=cycle, index_distance=distance, breadth_above200=above,
            uptrend_ratio=participation,
            components=[{"key": k, "name": n, "weight": w, "score": round(s, 1), "detail": d} for k, n, w, s, d in parts],
            missing=missing,
        ))
    return out
