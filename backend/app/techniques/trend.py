"""추세 계열: 트렌드 템플릿(관문)과 VCP(변동성 수축 패턴) 돌파."""

from __future__ import annotations

import math

import numpy as np

from app.core.market_rules import round_down_tick, round_up_tick
from app.core.models import Check, EntryPlan, TechniqueResult
from app.indicators.core import zigzag
from app.indicators.features import Features, Market
from app.techniques.params import TrendTemplateParams, VcpParams

TREND_KEY = "trend_template"
VCP_KEY = "vcp"
_MIN_TREND_BARS = 222  # 200일선 + 22일 전 비교


def _nan(x: float) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _rs(market: Market, code: str, i: int) -> float:
    arr = market.rs_pct.get(code)
    if arr is None or i >= len(arr):
        return float("nan")
    return float(arr[i])


def trend_template(market: Market, code: str, i: int, p: TrendTemplateParams) -> TechniqueResult:
    """미너비니 트렌드 템플릿. 종목이 2단계 상승 추세에 있는지 보는 관문이다(진입 계획은 없다)."""
    name = "트렌드 템플릿"
    feat = market.stocks[code]
    f = feat.f
    if i < _MIN_TREND_BARS or _nan(float(f["sma200_22"][i])):
        return TechniqueResult(TREND_KEY, name, False, 0.0, state="insufficient", notes=["일봉이 222개 넘게 필요합니다"])

    c = float(feat.close[i])
    sma50, sma150, sma200 = float(f["sma50"][i]), float(f["sma150"][i]), float(f["sma200"][i])
    hi252, lo252 = float(f["hi252"][i]), float(f["lo252"][i])
    rs = _rs(market, code, i)
    from_low = c / lo252 - 1 if lo252 > 0 else float("nan")
    from_high = c / hi252 - 1 if hi252 > 0 else float("nan")

    checks = [
        Check("above_150_200", "주가가 150·200일선 위", round(c, 0), f"> {max(sma150, sma200):,.0f}", c > sma150 and c > sma200),
        Check("sma150_above_200", "150일선이 200일선 위", round(sma150, 0), f"> {sma200:,.0f}", sma150 > sma200),
        Check("sma200_rising", "200일선이 한 달 전보다 높음", round(sma200, 0), f"> {float(f['sma200_22'][i]):,.0f}", sma200 > float(f["sma200_22"][i])),
        Check("above_50", "주가가 50일선 위", round(c, 0), f"> {sma50:,.0f}", c > sma50),
        Check("from_52w_low", "52주 저가 대비 상승폭", round(from_low * 100, 1), f"≥ +{p.min_low_gain * 100:.0f}%", from_low >= p.min_low_gain),
        Check("from_52w_high", "52주 고가 대비 거리", round(from_high * 100, 1), f"≥ −{p.max_high_gap * 100:.0f}%", from_high >= -p.max_high_gap),
        Check("rs", "상대강도 백분위", None if _nan(rs) else round(rs, 0), f"> {p.min_rs:.0f}", (not _nan(rs)) and rs > p.min_rs),
    ]
    count = sum(1 for ch in checks if ch.passed)
    passed = count >= p.min_pass
    return TechniqueResult(TREND_KEY, name, passed, count / len(checks) * 100.0, checks, "actionable" if passed else "none")


def find_contractions(
    feat: Features, i: int, p: VcpParams
) -> tuple[list[tuple[int, float, int, float]], int]:
    """최근 구간의 수축(고점 → 저점) 목록과, 마지막 고점의 봉 번호를 돌려준다.

    원소: (고점 봉, 고점 가격, 저점 봉, 저점 가격). i 시점까지의 값만 쓴다.
    """
    start = max(0, i - p.lookback + 1)
    threshold = feat.f["atr14"] * p.zigzag_atr_mult
    pivots = zigzag(feat.high, feat.low, threshold, start, i)
    pairs: list[tuple[int, float, int, float]] = []
    for a, b in zip(pivots, pivots[1:], strict=False):
        if a[2] == "H" and b[2] == "L":
            pairs.append((a[0], a[1], b[0], b[1]))
    return pairs[-p.max_contractions :], (pivots[-1][0] if pivots else i)


def vcp(market: Market, code: str, i: int, p: VcpParams, trend: TechniqueResult | None = None) -> TechniqueResult:
    """VCP: 수축이 점점 얕아지고 거래량이 마르는 베이스. 마지막 수축 고점(피벗) 돌파에 진입한다."""
    name = "VCP 돌파"
    feat = market.stocks[code]
    f = feat.f
    if i < p.lookback or _nan(float(f["atr14"][i])) or _nan(float(f["vol50"][i])):
        return TechniqueResult(VCP_KEY, name, False, 0.0, state="insufficient", notes=["일봉이 부족합니다"])

    pairs, _ = find_contractions(feat, i, p)
    c = float(feat.close[i])
    depths = [(hp - lp) / hp for _, hp, _, lp in pairs if hp > 0]
    enough = len(depths) >= 2
    first_deep = enough and depths[0] >= p.min_first_depth
    tightening = enough and all(b <= a * p.max_depth_ratio + 1e-9 for a, b in zip(depths, depths[1:], strict=False))
    dryup = float(f["vol10"][i] / f["vol50"][i]) if f["vol50"][i] > 0 else float("nan")
    dry = (not _nan(dryup)) and dryup <= p.max_dryup

    pivot = pairs[-1][1] if pairs else float("nan")
    last_low = pairs[-1][3] if pairs else float("nan")
    dist = c / pivot - 1 if pairs and pivot > 0 else float("nan")
    near = (not _nan(dist)) and -p.max_below_pivot <= dist <= p.breakout_zone

    depth_text = " → ".join(f"{d * 100:.1f}%" for d in depths) if depths else None
    checks = [
        Check("contractions", "수축 횟수", len(depths), "≥ 2", enough),
        Check("first_depth", "첫 수축 깊이", round(depths[0] * 100, 1) if depths else None, f"≥ {p.min_first_depth * 100:.0f}%", bool(first_deep)),
        Check("tightening", "수축이 점점 얕아짐", depth_text, f"다음 ≤ 이전 × {p.max_depth_ratio:.2f}", bool(tightening)),
        Check("dryup", "거래량 건조(10봉/50일)", None if _nan(dryup) else round(dryup, 2), f"≤ {p.max_dryup:.2f}", bool(dry)),
        Check("pivot_distance", "피벗 대비 위치", None if _nan(dist) else round(dist * 100, 1), f"−{p.max_below_pivot * 100:.0f}% ~ +{p.breakout_zone * 100:.0f}%", bool(near)),
    ]
    pattern_ok = bool(enough and first_deep and tightening and dry)
    passed = pattern_ok and near

    rs = _rs(market, code, i)
    trend_score = trend.score if trend else 50.0
    quality = 0.0
    if enough:
        quality = min(100.0, 40.0 + 20.0 * (len(depths) - 1) + (30.0 if tightening else 0.0) + (10.0 if depths[-1] <= 0.08 else 0.0))
    dry_score = 0.0 if _nan(dryup) else (90.0 if dryup < 0.30 else 70.0 if dryup < 0.50 else 50.0 if dryup < 0.70 else 30.0 if dryup < 1.0 else 0.0)
    pivot_score = 0.0 if _nan(dist) else (100.0 if -0.03 <= dist <= p.breakout_zone else 60.0 if near else 0.0)
    rs_score = 0.0 if _nan(rs) else rs
    score = 0.25 * trend_score + 0.25 * quality + 0.20 * dry_score + 0.15 * pivot_score + 0.15 * rs_score

    notes: list[str] = []
    plan: EntryPlan | None = None
    state = "none"
    if pattern_ok and not _nan(dist):
        if dist > 0.10:
            state, notes = "extended", ["피벗보다 10% 넘게 올라 과열 구간입니다"]
        elif dist > p.breakout_zone:
            state, notes = "extended", ["피벗 돌파 구간(+3%)을 지나 따라 사지 않습니다"]
        elif dist < -p.max_below_pivot:
            state = "setup"
            notes = ["패턴은 맞지만 피벗까지 아직 멉니다"]
        else:
            stop = round_down_tick(last_low * (1 - p.stop_buffer))
            if c < pivot * (1 + p.pivot_buffer):
                trigger = round_up_tick(pivot * (1 + p.pivot_buffer))
                reference = float(trigger)
                plan = EntryPlan(entry_type="trigger", stop=stop, reference_price=reference, trigger=trigger,
                                 chase_limit=round_down_tick(pivot * (1 + p.chase_limit)), exit_rule="close_below_sma50")
                state = "setup"
            else:
                reference = c
                plan = EntryPlan(entry_type="open", stop=stop, reference_price=reference,
                                 chase_limit=round_down_tick(pivot * (1 + p.breakout_zone)), exit_rule="close_below_sma50")
                state = "actionable"
            if plan.risk_pct > p.max_risk or plan.risk_per_share <= 0:
                notes.append(f"손절까지 {plan.risk_pct * 100:.1f}%로 위험 한도 {p.max_risk * 100:.0f}%를 넘습니다")
                plan, passed, state = None, False, "none"
            else:
                plan.target = round_down_tick(reference + p.reward_multiple * plan.risk_per_share)
    if not np.isfinite(score):
        score = 0.0
    return TechniqueResult(VCP_KEY, name, passed, score, checks, state, plan, notes)
