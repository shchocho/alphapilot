"""가치 점검: PER·PBR·ROE를 업종 안 백분위로 본다.

미국 종목용 절대 임계값(ROE > 15%, P/E < 15 등)은 한국 시장 분포와 달라 쓰지 않는다.
재무 데이터가 없으면(키움 연결 전) 평가하지 않는다(위원회 좌석은 기권).
"""

from __future__ import annotations

import math

from app.core.models import Check, TechniqueResult
from app.indicators.features import Market
from app.techniques.params import ValueParams

VALUE_KEY = "value_check"


def _percentile(value: float, peers: list[float]) -> float:
    """peers 안에서 value 이하인 비율(0~100)."""
    if not peers:
        return float("nan")
    return 100.0 * sum(1 for x in peers if x <= value) / len(peers)


def value_check(market: Market, code: str, i: int, p: ValueParams) -> TechniqueResult:
    name = "가치 점검"
    fund = market.fundamentals.get(code)
    info = market.info.get(code)
    if fund is None or info is None or fund.per is None or fund.pbr is None or fund.roe is None:
        return TechniqueResult(VALUE_KEY, name, False, 0.0, state="insufficient", notes=["재무 데이터가 없습니다(증권사 연결 뒤 활성화)"])

    peers = [market.fundamentals[c] for c, s in market.info.items() if s.sector == info.sector and c in market.fundamentals]
    pers = [x.per for x in peers if x.per is not None and x.per > 0]
    pbrs = [x.pbr for x in peers if x.pbr is not None and x.pbr > 0]
    roes = [x.roe for x in peers if x.roe is not None]
    if min(len(pers), len(pbrs), len(roes)) < p.min_peers:
        return TechniqueResult(VALUE_KEY, name, False, 0.0, state="insufficient", notes=[f"같은 업종 비교 대상이 {p.min_peers}개 미만입니다"])

    profitable = fund.per > 0 and (fund.eps is None or fund.eps > 0)
    per_pct = _percentile(fund.per, pers) if fund.per > 0 else 100.0
    pbr_pct = _percentile(fund.pbr, pbrs) if fund.pbr > 0 else 100.0
    roe_pct = _percentile(fund.roe, roes)
    cheap = per_pct <= p.cheap_percentile or pbr_pct <= p.cheap_percentile
    quality = roe_pct >= p.quality_percentile

    feat = market.stocks.get(code)
    price = float(feat.close[i]) if feat is not None else float("nan")
    graham = None
    graham_ok = False
    if fund.eps and fund.bps and fund.eps > 0 and fund.bps > 0 and not math.isnan(price):
        graham = math.sqrt(22.5 * fund.eps * fund.bps)
        graham_ok = graham >= price

    checks = [
        Check("profitable", "흑자(EPS > 0)", fund.eps, "> 0", profitable),
        Check("per_pct", "PER 업종 안 백분위(낮을수록 저평가)", round(per_pct, 0), f"≤ {p.cheap_percentile:.0f}", per_pct <= p.cheap_percentile),
        Check("pbr_pct", "PBR 업종 안 백분위(낮을수록 저평가)", round(pbr_pct, 0), f"≤ {p.cheap_percentile:.0f}", pbr_pct <= p.cheap_percentile),
        Check("roe_pct", "ROE 업종 안 백분위(높을수록 우량)", round(roe_pct, 0), f"≥ {p.quality_percentile:.0f}", quality),
        Check("graham", "그레이엄 수(√(22.5×EPS×BPS))", None if graham is None else round(graham, 0), "≥ 현재가", graham_ok),
    ]
    passed = bool(profitable and cheap and quality)
    score = ((100.0 - per_pct) + (100.0 - pbr_pct) + roe_pct) / 3.0 if profitable else 0.0
    return TechniqueResult(VALUE_KEY, name, passed, score, checks, "actionable" if passed else "none")
