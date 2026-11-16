"""모멘텀·돌파 계열: CANSLIM 일봉 요소, 모멘텀 버스트, 터틀 돌파, 변동성 돌파."""

from __future__ import annotations

import math
from datetime import date

from app.core.market_rules import is_limit_up_locked, round_down_tick
from app.core.models import Check, EntryPlan, TechniqueResult
from app.indicators.features import Market
from app.techniques.params import BurstParams, CanslimParams, TurtleParams, VolBreakoutParams

CANSLIM_KEY = "canslim_daily"
BURST_KEY = "momentum_burst"
TURTLE_KEY = "turtle"
VOLBREAK_KEY = "volatility_breakout"


def _nan(x: float) -> bool:
    return isinstance(x, float) and math.isnan(x)


def _rs(market: Market, code: str, i: int) -> float:
    arr = market.rs_pct.get(code)
    return float(arr[i]) if arr is not None and i < len(arr) else float("nan")


def index_distance(market: Market, code: str, day: date) -> float:
    """종목이 속한 시장 지수의 50일 지수이동평균 대비 이격(소수). 값이 없으면 NaN."""
    idx = market.index_for(code)
    j = idx.last_index_on_or_before(day)
    if j is None:
        return float("nan")
    ema50 = float(idx.f["ema50"][j])
    if _nan(ema50) or ema50 <= 0:
        return float("nan")
    return float(idx.close[j]) / ema50 - 1.0


def market_m_score(distance: float) -> float:
    """CANSLIM의 M(시장 방향) 점수. 0이면 매수 금지."""
    if _nan(distance):
        return 40.0
    if distance >= 0.02:
        return 90.0
    if distance >= 0.0:
        return 70.0
    if distance >= -0.02:
        return 40.0
    if distance >= -0.05:
        return 20.0
    return 0.0


def canslim_daily(market: Market, code: str, i: int, p: CanslimParams) -> TechniqueResult:
    """오닐 CANSLIM 중 일봉으로 계산되는 N(신고가)·S(수급)·L(주도주)·M(시장).

    C·A(분기·연간 이익 성장)와 I(기관)는 재무·수급 데이터가 필요해 1차 범위에서 뺐다.
    """
    name = "CANSLIM 일봉 요소"
    feat = market.stocks[code]
    f = feat.f
    if i < 130 or _nan(float(f["hi252"][i])) or _nan(float(f["udvr60"][i])) or _nan(float(f["vol50"][i])):
        return TechniqueResult(CANSLIM_KEY, name, False, 0.0, state="insufficient", notes=["일봉이 부족합니다"])

    c = float(feat.close[i])
    hi252 = float(f["hi252"][i])
    gap_to_high = c / hi252 - 1
    near_high = gap_to_high >= -p.near_high
    vol_ratio = float(feat.volume[i] / f["vol50"][i]) if f["vol50"][i] > 0 else 0.0
    volume_surge = vol_ratio >= p.breakout_volume and float(f["ret1"][i]) > 0
    udvr = float(f["udvr60"][i])
    rs = _rs(market, code, i)
    distance = index_distance(market, code, feat.day(i))
    m_score = market_m_score(distance)

    n_score = 100.0 if (near_high and volume_surge) else 70.0 if near_high else 40.0 if gap_to_high >= -0.10 else 10.0
    s_score = 100.0 if udvr >= p.udvr_full else 80.0 if udvr >= 1.5 else 60.0 if udvr >= 1.2 else 40.0 if udvr >= 1.0 else 20.0
    l_score = 15.0 if _nan(rs) else 100.0 if rs >= 90 else 85.0 if rs >= 80 else 65.0 if rs >= 70 else 40.0 if rs >= 50 else 15.0
    score = 0.30 * n_score + 0.20 * s_score + 0.30 * l_score + 0.20 * m_score
    leader = (not _nan(rs)) and rs >= p.min_rs

    checks = [
        Check("n_near_high", "N: 52주 고가 대비 거리", round(gap_to_high * 100, 1), f"≥ −{p.near_high * 100:.0f}%", near_high),
        Check("n_volume", "N: 돌파 거래량(50일 평균 대비)", round(vol_ratio, 2), f"≥ {p.breakout_volume:.1f}배", volume_surge),
        Check("s_udvr", "S: 상승일/하락일 거래량비(60일)", round(udvr, 2), f"≥ {p.udvr_full:.1f}", udvr >= p.udvr_full),
        Check("l_rs", "L: 상대강도 백분위", None if _nan(rs) else round(rs, 0), f"≥ {p.min_rs:.0f}", leader),
        Check("m_market", "M: 지수의 50일선 이격", None if _nan(distance) else round(distance * 100, 1), "≥ −5% (0점이면 매수 금지)", m_score > 0),
    ]
    passed = bool(score >= p.pass_score and near_high and leader and m_score > 0)
    plan = None
    notes: list[str] = []
    if m_score <= 0:
        notes.append("시장(M) 점수가 0이라 매수하지 않습니다")
    if passed:
        plan = EntryPlan(
            entry_type="open", stop=round_down_tick(c * (1 - p.stop_pct)), reference_price=c,
            chase_limit=round_down_tick(c * (1 + p.max_gap_from_close)), target=round_down_tick(c * (1 + p.target_pct)),
            exit_rule="close_below_sma50",
        )
    return TechniqueResult(CANSLIM_KEY, name, passed, score, checks, "actionable" if passed else "none", plan, notes)


def momentum_burst(market: Market, code: str, i: int, p: BurstParams) -> TechniqueResult:
    """Stockbee 모멘텀 버스트: 조용한 베이스 뒤 거래량을 동반한 +4% 이상 양봉. 3~5일 단기 보유."""
    name = "모멘텀 버스트"
    feat = market.stocks[code]
    f = feat.f
    if i < 60 or _nan(float(f["vol50"][i])) or _nan(float(f["sma20"][i])):
        return TechniqueResult(BURST_KEY, name, False, 0.0, state="insufficient", notes=["일봉이 부족합니다"])

    c, low, high = float(feat.close[i]), float(feat.low[i]), float(feat.high[i])
    volume, prev_volume = float(feat.volume[i]), float(feat.volume[i - 1])
    gain = float(f["ret1"][i])
    locked = is_limit_up_locked(c, high, float(feat.close[i - 1]))
    hi10, lo10 = float(f["hi10_prev"][i]), float(f["lo10_prev"][i])
    base_width = (hi10 - lo10) / lo10 if lo10 > 0 else float("nan")
    vol_ratio = volume / float(f["vol50"][i]) if f["vol50"][i] > 0 else 0.0
    close_pos = float(f["close_pos"][i])
    risk = (c - low) / c if c > 0 else 1.0
    extension = c / float(f["sma20"][i]) - 1
    prior_run = float(f["ret3"][i - 1]) if not _nan(float(f["ret3"][i - 1])) else 0.0
    distance = index_distance(market, code, feat.day(i))

    trig_gain = gain >= p.min_gain
    trig_volume = volume > prev_volume and volume >= p.min_volume
    triggered = trig_gain and trig_volume and not locked

    score = 0.0
    score += 20.0 if triggered else 0.0
    score += 15.0 if vol_ratio >= 2.0 else 10.0 if vol_ratio >= 1.5 else 5.0 if vol_ratio >= 1.0 else 0.0
    score += 25.0 if (not _nan(base_width) and base_width <= p.max_base_width) else 12.0 if (not _nan(base_width) and base_width <= 0.25) else 0.0
    score += 10.0 if close_pos >= 0.7 else 5.0 if close_pos >= 0.5 else 0.0
    score += 15.0 if risk <= 0.04 else 10.0 if risk <= 0.07 else 5.0 if risk <= p.max_risk else 0.0
    not_extended = extension <= 0.15 and prior_run < 0.15
    score += 10.0 if not_extended else 0.0
    score += 5.0 if (not _nan(distance) and distance >= 0) else 0.0

    checks = [
        Check("gain", "당일 상승률", round(gain * 100, 1), f"≥ +{p.min_gain * 100:.0f}%", trig_gain),
        Check("volume", "거래량(전일보다 많고 최소 수량 이상)", int(volume), f"> 전일, ≥ {p.min_volume:,}주", trig_volume),
        Check("not_locked", "상한가 잠김 아님", "잠김" if locked else "아님", "상한가 마감 봉 제외", not locked),
        Check("base", "직전 10일 베이스 폭", None if _nan(base_width) else round(base_width * 100, 1), f"≤ {p.max_base_width * 100:.0f}%", (not _nan(base_width)) and base_width <= p.max_base_width),
        Check("risk", "당일 저가까지 거리", round(risk * 100, 1), f"≤ {p.max_risk * 100:.0f}%", risk <= p.max_risk),
        Check("not_extended", "과열 아님(20일선 이격·직전 3일 상승)", round(extension * 100, 1), "이격 ≤ 15%, 직전 3일 < 15%", not_extended),
    ]
    passed = bool(triggered and risk <= p.max_risk and score >= p.pass_score)
    plan = None
    if passed:
        plan = EntryPlan(
            entry_type="open", stop=round_down_tick(low), reference_price=c,
            chase_limit=round_down_tick(c * (1 + p.max_gap_from_close)), trail_mult=None,
            max_hold_days=p.max_hold_days,
        )
    notes = ["상한가에 잠겨 마감해 다음 날 사기 어렵습니다"] if locked else []
    return TechniqueResult(BURST_KEY, name, passed, score, checks, "actionable" if passed else "none", plan, notes)


def turtle(market: Market, code: str, i: int, p: TurtleParams) -> TechniqueResult:
    """터틀 돌파(시스템 1): 20일 고가를 새로 넘으면 진입, 2N 손절, 10일 저가 이탈 시 청산."""
    name = "터틀 돌파"
    feat = market.stocks[code]
    f = feat.f
    if i < 60 or _nan(float(f["don55_hi"][i])) or _nan(float(f["atr20"][i])):
        return TechniqueResult(TURTLE_KEY, name, False, 0.0, state="insufficient", notes=["일봉이 부족합니다"])

    c = float(feat.close[i])
    don20, don55 = float(f["don20_hi"][i]), float(f["don55_hi"][i])
    n = float(f["atr20"][i])
    broke20 = c > don20
    fresh = float(feat.close[i - 1]) <= float(f["don20_hi"][i - 1])
    broke55 = c > don55
    sma200 = float(f["sma200"][i])
    above200 = (not _nan(sma200)) and c > sma200
    vol50 = float(f["vol50"][i])
    busy = (not _nan(vol50)) and float(feat.volume[i]) > vol50

    checks = [
        Check("break20", "20일 고가 돌파", round(c, 0), f"> {don20:,.0f}", broke20),
        Check("fresh", "새로 나온 돌파(전일은 돌파 전)", "새 돌파" if fresh else "이미 돌파 중", "전일 종가 ≤ 전일의 20일 고가", fresh),
        Check("break55", "55일 고가 돌파(강한 신호)", round(c, 0), f"> {don55:,.0f}", broke55),
        Check("above200", "200일선 위(참고)", None if _nan(sma200) else round(sma200, 0), "주가 > 200일선", above200),
    ]
    passed = bool(broke20 and fresh)
    score = (50.0 if broke20 else 0.0) + (25.0 if broke55 else 0.0) + (15.0 if above200 else 0.0) + (10.0 if busy else 0.0)
    plan = None
    if passed and n > 0:
        plan = EntryPlan(
            entry_type="open", stop=round_down_tick(c - p.stop_n * n), reference_price=c,
            chase_limit=round_down_tick(c * (1 + p.max_gap_from_close)), trail_mult=None,
            exit_rule="close_below_low10",
        )
    return TechniqueResult(TURTLE_KEY, name, passed, score, checks, "actionable" if passed else "none", plan)


def volatility_breakout(market: Market, code: str, i: int, p: VolBreakoutParams) -> TechniqueResult:
    """변동성 돌파: 다음 거래일 시가 + k × 오늘 범위를 장중에 넘으면 진입, 그다음 거래일 시가에 청산.

    오늘(i) 장 마감 뒤 내일 쓸 후보를 고르는 평가다. 목표가는 내일 시가가 정해져야 계산된다.
    """
    name = "변동성 돌파"
    feat = market.stocks[code]
    f = feat.f
    if i < 60 or _nan(float(f["sma50"][i])):
        return TechniqueResult(VOLBREAK_KEY, name, False, 0.0, state="insufficient", notes=["일봉이 부족합니다"])

    c = float(feat.close[i])
    rng = float(feat.high[i] - feat.low[i])
    range_pct = rng / c if c > 0 else 0.0
    sma20, sma50 = float(f["sma20"][i]), float(f["sma50"][i])
    sma200 = float(f["sma200"][i])
    rs = _rs(market, code, i)
    uptrend = c > sma20 and c > sma50
    range_ok = p.min_range_pct <= range_pct <= p.max_range_pct
    strong = (not _nan(rs)) and rs >= p.min_rs

    checks = [
        Check("uptrend", "20·50일선 위", round(c, 0), f"> {max(sma20, sma50):,.0f}", uptrend),
        Check("range", "오늘 범위(고가 − 저가)", round(range_pct * 100, 1), f"{p.min_range_pct * 100:.0f}% ~ {p.max_range_pct * 100:.0f}%", range_ok),
        Check("rs", "상대강도 백분위", None if _nan(rs) else round(rs, 0), f"≥ {p.min_rs:.0f}", strong),
    ]
    passed = bool(uptrend and range_ok and strong)
    score = min(100.0, 40.0 + (0.0 if _nan(rs) else rs * 0.3) + (20.0 if (not _nan(sma200) and c > sma200) else 0.0)
                + (10.0 if float(feat.volume[i]) > float(f["vol50"][i]) else 0.0)) if passed else 0.0
    plan = None
    if passed:
        reference = c + p.k * rng  # 내일 시가가 오늘 종가와 같다고 본 예상 목표가
        plan = EntryPlan(
            entry_type="vb", stop=round_down_tick(reference - rng), reference_price=reference,
            vb_k=p.k, vb_range=rng, trail_mult=None, exit_on_next_open=True,
        )
    return TechniqueResult(VOLBREAK_KEY, name, passed, score, checks, "setup" if passed else "none", plan)
