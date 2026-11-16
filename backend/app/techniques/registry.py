"""기법 목록과 일괄 평가.

화면의 '종목 발굴' 프리셋과 위원회 좌석이 이 목록을 읽는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.models import TechniqueResult
from app.indicators.features import Market
from app.techniques import momentum, trend, value
from app.techniques.params import DEFAULT_PARAMS, TechniqueParams


@dataclass(frozen=True, slots=True)
class TechniqueMeta:
    key: str
    name: str
    origin: str  # 원저자
    kind: str  # gate(관문) | entry(진입) | value(가치)
    summary: str
    rules: tuple[str, ...]  # 화면의 규칙 칩
    holding: str  # 보유 기간 성격
    data: str

    def to_dict(self) -> dict:
        return asdict(self)


def metas(p: TechniqueParams = DEFAULT_PARAMS) -> tuple[TechniqueMeta, ...]:
    return (
        TechniqueMeta(
            trend.TREND_KEY, "트렌드 템플릿", "Mark Minervini", "gate",
            "장기 이동평균이 정배열이고 52주 고가 근처에 있는 주도주",
            ("주가 > 150·200일선", "150일선 > 200일선", "200일선 상승", "주가 > 50일선",
             f"52주 저가 +{p.trend.min_low_gain * 100:.0f}% 이상", f"52주 고가 −{p.trend.max_high_gap * 100:.0f}% 이내",
             f"상대강도 > {p.trend.min_rs:.0f}", f"7개 중 {p.trend.min_pass}개 이상"),
            "몇 주~몇 달", "일봉",
        ),
        TechniqueMeta(
            trend.VCP_KEY, "VCP 돌파", "Mark Minervini", "entry",
            "수축이 점점 얕아지고 거래량이 마른 뒤, 마지막 고점을 넘는 순간",
            ("수축 2회 이상", f"첫 수축 ≥ {p.vcp.min_first_depth * 100:.0f}%", f"다음 수축 ≤ 이전 × {p.vcp.max_depth_ratio:.2f}",
             f"거래량 건조 ≤ {p.vcp.max_dryup:.2f}", "피벗 돌파 시 진입", f"위험 ≤ {p.vcp.max_risk * 100:.0f}%", "목표 2R"),
            "몇 주", "일봉",
        ),
        TechniqueMeta(
            momentum.CANSLIM_KEY, "CANSLIM 일봉 요소", "William O'Neil", "entry",
            "신고가 근처에서 거래량이 붙는 주도주 (N·S·L·M)",
            (f"52주 고가 −{p.canslim.near_high * 100:.0f}% 이내", f"돌파 거래량 ≥ {p.canslim.breakout_volume:.1f}배",
             f"상승/하락 거래량비 ≥ {p.canslim.udvr_full:.1f}", f"상대강도 ≥ {p.canslim.min_rs:.0f}", "지수 50일선 근처 이상",
             f"손절 −{p.canslim.stop_pct * 100:.0f}%", f"익절 +{p.canslim.target_pct * 100:.0f}%"),
            "몇 주~몇 달", "일봉 (C·A·I는 재무·수급 연결 뒤)",
        ),
        TechniqueMeta(
            momentum.BURST_KEY, "모멘텀 버스트", "Pradeep Bonde (Stockbee)", "entry",
            "조용한 베이스 뒤 거래량을 동반한 큰 양봉, 3~5일 단기",
            (f"당일 +{p.burst.min_gain * 100:.0f}% 이상", "거래량 전일보다 증가", f"{p.burst.min_volume:,}주 이상",
             f"베이스 폭 ≤ {p.burst.max_base_width * 100:.0f}%", "상한가 잠김 제외", "손절 = 당일 저가", f"최대 {p.burst.max_hold_days}일 보유"),
            "3~5일", "일봉",
        ),
        TechniqueMeta(
            momentum.TURTLE_KEY, "터틀 돌파", "Richard Dennis", "entry",
            "20일 고가를 새로 넘는 추세 추종",
            ("20일 고가 돌파", "새로 나온 돌파만", f"손절 = 진입 − {p.turtle.stop_n:.0f}N(ATR20)", "10일 저가 이탈 시 청산"),
            "몇 주", "일봉",
        ),
        TechniqueMeta(
            momentum.VOLBREAK_KEY, "변동성 돌파", "Larry Williams", "entry",
            "당일 시가 + k × 전일 범위를 장중에 넘으면 사서 다음 날 시가에 판다",
            (f"k = {p.volbreak.k:.1f}", "20·50일선 위", f"전일 범위 {p.volbreak.min_range_pct * 100:.0f}~{p.volbreak.max_range_pct * 100:.0f}%",
             f"상대강도 ≥ {p.volbreak.min_rs:.0f}", "다음 거래일 시가 청산"),
            "1일", "일봉 + 장중 시세",
        ),
        TechniqueMeta(
            value.VALUE_KEY, "가치 점검", "Benjamin Graham · Peter Lynch", "value",
            "같은 업종 안에서 싸고(PER·PBR) 돈을 잘 버는(ROE) 회사",
            (f"PER 또는 PBR 업종 백분위 ≤ {p.value.cheap_percentile:.0f}", f"ROE 업종 백분위 ≥ {p.value.quality_percentile:.0f}", "흑자"),
            "참고 관점", "재무 (증권사 연결 뒤)",
        ),
    )


ENTRY_KEYS: tuple[str, ...] = (trend.VCP_KEY, momentum.CANSLIM_KEY, momentum.BURST_KEY, momentum.TURTLE_KEY, momentum.VOLBREAK_KEY)
ALL_KEYS: tuple[str, ...] = (trend.TREND_KEY, *ENTRY_KEYS, value.VALUE_KEY)
# 기법이 겹칠 때 주문 계획으로 쓸 우선순위(보유 기간이 긴 추세 기법 먼저).
PLAN_PRIORITY: tuple[str, ...] = (trend.VCP_KEY, momentum.CANSLIM_KEY, momentum.TURTLE_KEY, momentum.BURST_KEY, momentum.VOLBREAK_KEY)


def evaluate_all(market: Market, code: str, i: int, p: TechniqueParams = DEFAULT_PARAMS) -> dict[str, TechniqueResult]:
    """한 종목의 i번째 봉(장 마감 시점) 기준 모든 기법 평가."""
    tt = trend.trend_template(market, code, i, p.trend)
    return {
        trend.TREND_KEY: tt,
        trend.VCP_KEY: trend.vcp(market, code, i, p.vcp, tt),
        momentum.CANSLIM_KEY: momentum.canslim_daily(market, code, i, p.canslim),
        momentum.BURST_KEY: momentum.momentum_burst(market, code, i, p.burst),
        momentum.TURTLE_KEY: momentum.turtle(market, code, i, p.turtle),
        momentum.VOLBREAK_KEY: momentum.volatility_breakout(market, code, i, p.volbreak),
        value.VALUE_KEY: value.value_check(market, code, i, p.value),
    }


def best_plan(results: dict[str, TechniqueResult], enabled: tuple[str, ...] = ENTRY_KEYS) -> TechniqueResult | None:
    """통과한 진입 기법 중 우선순위가 가장 높은 것."""
    for key in PLAN_PRIORITY:
        r = results.get(key)
        if key in enabled and r is not None and r.passed and r.plan is not None:
            return r
    return None
