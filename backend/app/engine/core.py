"""엔진 코어: 장 마감 뒤 사이클(보유 점검 → 후보 발굴 → 위원회 → 리스크 게이트 → 다음 거래일 주문 계획).

DB도 네트워크도 모르는 순수 로직이다. 시뮬레이션·백테스트·키움 모드가 같은 함수를 쓴다.
세 단계로 나뉜다.
  1) prepare_cycle  : 규칙으로 계산할 수 있는 모든 것(국면, 회로차단기, 청산 규칙, 후보와 주문 범위)
  2) (판단)          : 규칙 위원회 또는 AI 위원회가 후보·보유 종목마다 결론을 낸다
  3) finalize_cycle : 결론을 리스크 게이트에 통과시켜 주문 계획으로 만든다
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from app.committee import rules_committee
from app.committee.deliberation import EntryContext, HoldingContext
from app.committee.seats import blend, build_seats
from app.core.market_rules import CostModel
from app.core.models import (
    CONVICTION_LABEL,
    Decision,
    EntryPlan,
    Intent,
    Portfolio,
    Position,
    Signal,
    StockInfo,
    TechniqueResult,
)
from app.indicators.features import Features, Market
from app.regime.regime import RegimeState
from app.risk.breakers import BreakerState, evaluate_breakers
from app.risk.gate import GateContext, GateResult, gate_buy, gate_sell
from app.risk.limits import RiskLimits
from app.techniques import momentum, registry
from app.techniques.params import DEFAULT_PARAMS, TechniqueParams

REVIEW_BLEND_BELOW = 0.15  # 보유 종목: 좌석 종합이 이 값보다 낮으면 재심의
REVIEW_LOSS_BELOW = -0.04  # 보유 종목: 평가손익이 이 값보다 낮으면 재심의
EXIT_RULE_LABELS = {"close_below_sma50": "종가가 50일선 아래로 내려감", "close_below_low10": "10일 저가를 이탈함"}
ENTRY_KIND_LABEL = {"open": "시가 매수", "trigger": "돌파 매수", "vb": "변동성 돌파 매수"}


@dataclass(slots=True)
class EngineConfig:
    limits: RiskLimits = field(default_factory=RiskLimits)
    costs: CostModel = field(default_factory=CostModel)
    params: TechniqueParams = DEFAULT_PARAMS
    enabled_techniques: tuple[str, ...] = registry.ENTRY_KEYS
    max_candidates: int = 8
    review_holdings: bool = True


@dataclass(slots=True)
class Event:
    """원장에 남길 한 줄."""

    kind: str
    summary: str
    code: str | None = None
    name: str | None = None
    chain_id: str = ""
    qty: int | None = None
    amount: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Candidate:
    info: StockInfo
    chain_id: str
    rank_score: float
    close: float
    techniques: dict[str, TechniqueResult]
    primary: TechniqueResult
    seats: list[Signal]
    plan: EntryPlan
    max_qty: dict[str, int]
    avg_value20: float
    context: EntryContext


@dataclass(slots=True)
class Holding:
    info: StockInfo
    position: Position
    close: float
    pnl_pct: float
    seats: list[Signal]
    techniques: dict[str, TechniqueResult]
    exit_signals: list[str]
    needs_review: bool
    context: HoldingContext


@dataclass(slots=True)
class CycleDraft:
    day: date
    next_day: date
    regime: RegimeState
    breaker: BreakerState
    equity: float
    prices: dict[str, float]
    candidates: list[Candidate]
    holdings: list[Holding]
    ranked_out: list[tuple[StockInfo, str, float]]  # 신호는 있었지만 심의 대상에서 밀린 종목 (종목, 기법, 점수)
    precheck_blocked: list[tuple[StockInfo, str, str]]  # 게이트 사전 점검에서 막힌 종목 (종목, 기법, 사유)
    scanned: int = 0
    signalled: int = 0


@dataclass(slots=True)
class DecisionRecord:
    """판단 한 건의 전체 기록(화면·원장·DB 저장용)."""

    id: str
    chain_id: str
    as_of: date
    info: StockInfo
    kind: str
    decision: Decision
    seats: list[Signal]
    techniques: dict[str, TechniqueResult]
    plan: EntryPlan | None = None
    max_qty: dict[str, int] = field(default_factory=dict)
    gate: GateResult | None = None
    transcript: dict[str, Any] | None = None
    intent_id: str | None = None
    close: float = 0.0
    technique: str = ""  # 근거 기법 이름(진입) 또는 진입 때 쓴 기법(보유)

    def to_body(self) -> dict[str, Any]:
        return {
            "technique": self.technique,
            "seats": [s.to_dict() for s in self.seats],
            "techniques": [t.to_dict() for t in self.techniques.values()],
            "plan": self.plan.to_dict() if self.plan else None,
            "max_qty": self.max_qty,
            "final": self.decision.to_dict(),
            "gate": self.gate.to_dict() if self.gate else None,
            "transcript": self.transcript,
            "intent_id": self.intent_id,
            "close": self.close,
            "sector": self.info.sector,
            "market": self.info.market,
        }


@dataclass(slots=True)
class CycleResult:
    day: date
    next_day: date
    regime: RegimeState
    breaker: BreakerState
    records: list[DecisionRecord] = field(default_factory=list)
    intents: list[Intent] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


class EntryPrefilter:
    """기법이 통과할 가능성이 있는 (종목, 날짜)만 골라내는 값싼 사전 필터.

    각 기법의 '필요조건'만 벡터 연산으로 계산한다. 필터를 통과해도 기법 본 평가에서 떨어질 수 있고,
    필터에서 떨어진 종목은 본 평가에서도 반드시 떨어진다(누락 없음).
    """

    def __init__(self, market: Market, params: TechniqueParams, enabled: tuple[str, ...]) -> None:
        self._masks: dict[str, np.ndarray] = {}
        for code, feat in market.stocks.items():
            self._masks[code] = self._mask(market, code, feat, params, enabled)

    def passes(self, code: str, i: int) -> bool:
        mask = self._masks.get(code)
        return bool(mask is not None and i < len(mask) and mask[i])

    @staticmethod
    def _mask(market: Market, code: str, feat: Features, p: TechniqueParams, enabled: tuple[str, ...]) -> np.ndarray:
        f = feat.f
        c, v = feat.close, feat.volume
        rs = market.rs_pct.get(code)
        rs = rs if rs is not None else np.full(len(feat), np.nan)
        mask = np.zeros(len(feat), dtype=bool)
        with np.errstate(invalid="ignore", divide="ignore"):
            if "vcp" in enabled:
                mask |= (f["vol10"] / f["vol50"]) <= p.vcp.max_dryup
            if momentum.CANSLIM_KEY in enabled:
                mask |= (c >= f["hi252"] * (1 - p.canslim.near_high)) & (rs >= p.canslim.min_rs)
            if momentum.BURST_KEY in enabled:
                prev_v = np.concatenate([[np.inf], v[:-1]])
                mask |= (f["ret1"] >= p.burst.min_gain) & (v > prev_v) & (v >= p.burst.min_volume)
            if momentum.TURTLE_KEY in enabled:
                mask |= c > f["don20_hi"]
            if momentum.VOLBREAK_KEY in enabled:
                rng = f["range"] / c
                mask |= (c > f["sma20"]) & (c > f["sma50"]) & (rng >= p.volbreak.min_range_pct) & (rng <= p.volbreak.max_range_pct) & (rs >= p.volbreak.min_rs)
        return mask


def exit_signals(pos: Position, feat: Features, i: int) -> list[str]:
    """기법의 청산 규칙이 충족됐는지. 충족되면 AI 판단 없이 다음 거래일 시가에 판다."""
    c = float(feat.close[i])
    out: list[str] = []
    if pos.exit_rule == "close_below_sma50":
        sma50 = float(feat.f["sma50"][i])
        if not np.isnan(sma50) and c < sma50:
            out.append(EXIT_RULE_LABELS["close_below_sma50"])
    elif pos.exit_rule == "close_below_low10":
        low10 = float(feat.f["lo10"][i])
        if not np.isnan(low10) and c < low10:
            out.append(EXIT_RULE_LABELS["close_below_low10"])
    return out


def _gate_context(portfolio: Portfolio, prices: dict[str, float], equity: float, regime: RegimeState, breaker: BreakerState,
                  cfg: EngineConfig, avg_value20: float, pending: _Pending, orders_today: int) -> GateContext:
    return GateContext(
        equity=equity, cash=float(portfolio.cash), positions=portfolio.positions, prices=prices,
        exposure_cap=regime.exposure_cap, allow_new_buys=regime.allow_new_buys, breaker=breaker, costs=cfg.costs,
        avg_value20=avg_value20, pending_value=pending.value, pending_risk=pending.risk,
        pending_codes=frozenset(pending.codes), pending_by_sector=dict(pending.by_sector), orders_today=orders_today,
    )


@dataclass(slots=True)
class _Pending:
    value: float = 0.0
    risk: float = 0.0
    codes: set[str] = field(default_factory=set)
    by_sector: dict[str, float] = field(default_factory=dict)

    def add(self, info: StockInfo, gate: GateResult) -> None:
        self.value += gate.order_value
        self.risk += gate.risk_amount
        self.codes.add(info.code)
        self.by_sector[info.sector] = self.by_sector.get(info.sector, 0.0) + gate.order_value


def _portfolio_note(portfolio: Portfolio, prices: dict[str, float], equity: float, info: StockInfo, limits: RiskLimits) -> dict[str, Any]:
    sector_value = sum(p.qty * prices.get(c, p.avg_price) for c, p in portfolio.positions.items() if p.sector == info.sector)
    return {
        "현금 비중(%)": round(portfolio.cash / equity * 100, 1) if equity > 0 else 0,
        "보유 종목 수": f"{len(portfolio.positions)} / 최대 {limits.max_positions}",
        "같은 업종 비중(%)": round(sector_value / equity * 100, 1) if equity > 0 else 0,
        "종목당 한도(%)": round(limits.max_position_pct * 100),
    }


def prepare_cycle(
    day: date,
    next_day: date,
    market: Market,
    regime: RegimeState,
    portfolio: Portfolio,
    cfg: EngineConfig,
    *,
    equity_history: list[tuple[date, float]],
    recent_exits: list[tuple[date, str, float]],
    prefilter: EntryPrefilter | None = None,
    pending_codes: frozenset[str] = frozenset(),
    data_complete: bool = True,
    previous_day: date | None = None,
    orders_today: int = 0,
) -> CycleDraft:
    prices = {code: float(feat.close[i]) for code, feat in market.stocks.items() if (i := feat.last_index_on_or_before(day)) is not None}
    equity = portfolio.equity(prices)
    breaker = evaluate_breakers(equity_history, day, equity, max(portfolio.peak_equity, equity), recent_exits, cfg.limits,
                                data_complete=data_complete, previous_trading_day=previous_day)

    # 보유 종목 점검
    holdings: list[Holding] = []
    for code, pos in portfolio.positions.items():
        feat = market.stocks.get(code)
        info = market.info.get(code) or StockInfo(code, pos.name, "KOSPI", pos.sector)
        i = feat.index_of(day) if feat is not None else None
        if feat is None or i is None or pos.exit_on_next_open:
            continue
        results = registry.evaluate_all(market, code, i, cfg.params)
        seats = build_seats(market, code, i, results, regime)
        close = float(feat.close[i])
        pnl_pct = close / pos.avg_price - 1 if pos.avg_price > 0 else 0.0
        signals = exit_signals(pos, feat, i)
        needs_review = cfg.review_holdings and not signals and (blend(seats) < REVIEW_BLEND_BELOW or pnl_pct <= REVIEW_LOSS_BELOW)
        context = HoldingContext(info=info, as_of=day, close=close, position=pos, seats=seats, regime=regime, pnl_pct=pnl_pct,
                                 techniques=results, portfolio=_portfolio_note(portfolio, prices, equity, info, cfg.limits))
        holdings.append(Holding(info, pos, close, pnl_pct, seats, results, signals, needs_review, context))

    # 후보 발굴
    scanned = signalled = 0
    found: list[tuple[float, StockInfo, int, dict[str, TechniqueResult], TechniqueResult, list[Signal]]] = []
    for code, feat in market.stocks.items():
        if code in portfolio.positions or code in pending_codes:
            continue
        i = feat.index_of(day)
        if i is None:
            continue
        scanned += 1
        value20 = float(feat.f["value20"][i])
        if np.isnan(value20) or value20 < cfg.limits.min_avg_value:
            continue
        if prefilter is not None and not prefilter.passes(code, i):
            continue
        results = registry.evaluate_all(market, code, i, cfg.params)
        primary = registry.best_plan(results, cfg.enabled_techniques)
        if primary is None:
            continue
        signalled += 1
        seats = build_seats(market, code, i, results, regime)
        rank = 0.6 * primary.score + 0.4 * (blend(seats) + 1.0) * 50.0
        found.append((rank, market.info[code], i, results, primary, seats))
    found.sort(key=lambda row: (-row[0], row[1].code))

    candidates: list[Candidate] = []
    blocked: list[tuple[StockInfo, str, str]] = []
    pending = _Pending(codes=set(pending_codes))
    for rank, info, i, results, primary, seats in found[: cfg.max_candidates]:
        feat = market.stocks[info.code]
        plan = primary.plan
        assert plan is not None
        value20 = float(feat.f["value20"][i])
        gate_ctx = _gate_context(portfolio, prices, equity, regime, breaker, cfg, value20, pending, orders_today)
        max_qty: dict[str, int] = {}
        first_block = ""
        for conviction in ("low", "medium", "high", "very_high"):
            probe = Decision(info.code, info.name, "entry", "BUY", conviction)  # type: ignore[arg-type]
            gate = gate_buy(probe, plan, info, gate_ctx, cfg.limits)
            max_qty[conviction] = gate.qty
            if not gate.approved and not first_block:
                first_block = next((s.detail for s in gate.steps if s.outcome == "block"), "수량 0")
        if max(max_qty.values()) < 1:
            blocked.append((info, primary.name, first_block))
            continue
        close = float(feat.close[i])
        context = EntryContext(info=info, as_of=day, close=close, techniques=results, primary=primary, seats=seats, regime=regime,
                               plan=plan, max_qty=max_qty, portfolio=_portfolio_note(portfolio, prices, equity, info, cfg.limits))
        candidates.append(Candidate(info, f"{day:%y%m%d}-{info.code}", rank, close, results, primary, seats, plan, max_qty, value20, context))

    ranked_out = [(info, primary.name, primary.score) for _, info, _, _, primary, _ in found[cfg.max_candidates :]]
    return CycleDraft(day=day, next_day=next_day, regime=regime, breaker=breaker, equity=equity, prices=prices,
                      candidates=candidates, holdings=holdings, ranked_out=ranked_out, precheck_blocked=blocked,
                      scanned=scanned, signalled=signalled)


def rules_decisions(draft: CycleDraft) -> tuple[dict[str, tuple[Decision, dict | None]], dict[str, tuple[Decision, dict | None]]]:
    """규칙 위원회로 모든 후보·보유 종목의 결론을 낸다. 반환: (후보 결론, 보유 결론) — 키는 종목코드."""
    entries = {c.info.code: (rules_committee.decide_entry(c.info.code, c.info.name, c.seats, c.primary.name), None) for c in draft.candidates}
    holds = {
        h.info.code: (rules_committee.decide_holding(h.info.code, h.info.name, h.seats, []), None)
        for h in draft.holdings
        if h.needs_review
    }
    return entries, holds


def _intent_from_plan(cand: Candidate, draft: CycleDraft, qty: int, stop: int, decision: Decision) -> Intent:
    plan = cand.plan
    return Intent(
        id=f"{cand.chain_id}-b", chain_id=cand.chain_id, created_on=draft.day, trade_date=draft.next_day,
        code=cand.info.code, name=cand.info.name, side="buy", qty=qty, entry_type=plan.entry_type, status="approved",
        source="committee", technique=cand.primary.key, reason=decision.thesis, est_price=plan.reference_price,
        trigger=plan.trigger, chase_limit=plan.chase_limit, vb_k=plan.vb_k, vb_range=plan.vb_range, stop=stop,
        target=plan.target, trail_mult=plan.trail_mult, exit_on_next_open=plan.exit_on_next_open,
        max_hold_days=plan.max_hold_days, exit_rule=plan.exit_rule, conviction=decision.conviction, sector=cand.info.sector,
    )


def _branch_event(ev: list[Event], transcript: dict | None, info: StockInfo, chain: str) -> None:
    branch = (transcript or {}).get("branch")
    if branch:
        ev.append(Event("decision", f"AI 분기 판단 · {branch['reason']} → {branch['outcome']}", info.code, info.name, chain,
                        payload={"adopted": branch["adopted"]}))


def _votes_text(votes: dict[str, int]) -> str:
    return f"좌석 강세 {votes.get('bullish', 0)} · 약세 {votes.get('bearish', 0)} · 중립 {votes.get('neutral', 0)}"


def finalize_cycle(
    draft: CycleDraft,
    entry_decisions: dict[str, tuple[Decision, dict | None]],
    holding_decisions: dict[str, tuple[Decision, dict | None]],
    portfolio: Portfolio,
    cfg: EngineConfig,
    *,
    pending_codes: frozenset[str] = frozenset(),
    orders_today: int = 0,
) -> CycleResult:
    result = CycleResult(day=draft.day, next_day=draft.next_day, regime=draft.regime, breaker=draft.breaker)
    ev = result.events
    if draft.breaker.reasons:
        ev.append(Event("breaker", " / ".join(draft.breaker.reasons), payload=draft.breaker.to_dict()))

    # 보유 종목: 청산 규칙(자동) → 위원회 매도 판단
    for h in draft.holdings:
        chain = h.position.chain_id or f"{draft.day:%y%m%d}-{h.info.code}"
        if h.exit_signals:
            decision = Decision(h.info.code, h.info.name, "holding", "SELL", "high", thesis="청산 규칙 충족: " + ", ".join(h.exit_signals), source="rules")
            intent = Intent(id=f"{draft.day:%y%m%d}-{h.info.code}-s", chain_id=chain, created_on=draft.day, trade_date=draft.next_day,
                            code=h.info.code, name=h.info.name, side="sell", qty=h.position.qty, status="approved", source="rule_exit",
                            technique=h.position.technique, reason=decision.thesis, est_price=h.close, sector=h.info.sector)
            result.intents.append(intent)
            result.records.append(DecisionRecord(f"{draft.day:%y%m%d}-{h.info.code}-h", chain, draft.day, h.info, "holding", decision,
                                                 h.seats, h.techniques, intent_id=intent.id, close=h.close, technique=h.position.technique))
            ev.append(Event("intent", f"청산 규칙 충족({', '.join(h.exit_signals)}) → 다음 거래일 시가 매도", h.info.code, h.info.name, chain,
                            qty=h.position.qty, payload={"source": "rule_exit"}))
            continue
        if h.info.code not in holding_decisions:
            continue
        decision, transcript = holding_decisions[h.info.code]
        record = DecisionRecord(f"{draft.day:%y%m%d}-{h.info.code}-h", chain, draft.day, h.info, "holding", decision, h.seats,
                                h.techniques, transcript=transcript, close=h.close, technique=h.position.technique)
        result.records.append(record)
        _branch_event(ev, transcript, h.info, chain)
        if decision.status != "ok":
            ev.append(Event("decision", f"보유 재심의 보류: {decision.status_detail} (보유 유지, 보호 청산은 계속 작동)", h.info.code, h.info.name, chain))
            continue
        if decision.action == "SELL":
            gate = gate_sell(decision, portfolio.positions.get(h.info.code))
            record.gate = gate
            if gate.approved:
                intent = Intent(id=f"{draft.day:%y%m%d}-{h.info.code}-s", chain_id=chain, created_on=draft.day, trade_date=draft.next_day,
                                code=h.info.code, name=h.info.name, side="sell", qty=gate.qty, status="approved", source="committee",
                                technique=h.position.technique, reason=decision.thesis, est_price=h.close, conviction=decision.conviction,
                                sector=h.info.sector)
                record.intent_id = intent.id
                result.intents.append(intent)
                ev.append(Event("decision", f"매도 판단 · {decision.thesis}", h.info.code, h.info.name, chain, qty=gate.qty))
        else:
            ev.append(Event("decision", f"보유 유지 · {decision.thesis}", h.info.code, h.info.name, chain))

    # 신규 후보: 순위대로 게이트를 통과시키며 누적 한도를 쓴다
    pending = _Pending(codes=set(pending_codes))
    buy_count = 0
    for cand in draft.candidates:
        decision, transcript = entry_decisions.get(cand.info.code, (None, None))
        if decision is None:
            continue
        record = DecisionRecord(f"{cand.chain_id}-e", cand.chain_id, draft.day, cand.info, "entry", decision, cand.seats, cand.techniques,
                                plan=cand.plan, max_qty=cand.max_qty, transcript=transcript, close=cand.close, technique=cand.primary.key)
        result.records.append(record)
        _branch_event(ev, transcript, cand.info, cand.chain_id)
        label = CONVICTION_LABEL[decision.conviction]
        if decision.status != "ok":
            ev.append(Event("decision", f"판단 보류: {decision.status_detail} → 매수하지 않음", cand.info.code, cand.info.name, cand.chain_id))
            continue
        if decision.action != "BUY":
            ev.append(Event("decision", f"매수 보류 · {cand.primary.name} · {_votes_text(decision.votes)} · {decision.thesis}",
                            cand.info.code, cand.info.name, cand.chain_id))
            continue
        gate_ctx = _gate_context(portfolio, draft.prices, draft.equity, draft.regime, draft.breaker, cfg, cand.avg_value20, pending,
                                 orders_today + buy_count)
        gate = gate_buy(decision, cand.plan, cand.info, gate_ctx, cfg.limits)
        record.gate = gate
        ev.append(Event("decision", f"매수 판단 · {cand.primary.name} · 확신 {label} · {_votes_text(decision.votes)}",
                        cand.info.code, cand.info.name, cand.chain_id, payload={"source": decision.source}))
        if not gate.approved:
            ev.append(Event("gate_block", gate.summary(), cand.info.code, cand.info.name, cand.chain_id, payload={"blocked_by": gate.blocked_by}))
            continue
        if gate.reduced_by:
            ev.append(Event("gate_reduce", f"{gate.summary()} ({', '.join(s.detail for s in gate.steps if s.outcome == 'reduce')})",
                            cand.info.code, cand.info.name, cand.chain_id, qty=gate.qty))
        intent = _intent_from_plan(cand, draft, gate.qty, gate.stop or cand.plan.stop, decision)
        record.intent_id = intent.id
        result.intents.append(intent)
        pending.add(cand.info, gate)
        buy_count += 1
        ev.append(Event("intent", f"다음 거래일 {ENTRY_KIND_LABEL[cand.plan.entry_type]} 계획 · 손절 {intent.stop:,}원",
                        cand.info.code, cand.info.name, cand.chain_id, qty=gate.qty, amount=gate.order_value))

    for info, technique, why in draft.precheck_blocked:
        ev.append(Event("precheck", f"{technique} 신호였지만 심의 전에 제외: {why}", info.code, info.name, f"{draft.day:%y%m%d}-{info.code}"))
    for info, technique, score in draft.ranked_out[:10]:
        ev.append(Event("screen_out", f"{technique} 신호(점수 {score:.0f})였지만 심의 순위 밖", info.code, info.name, f"{draft.day:%y%m%d}-{info.code}"))

    buys = sum(1 for it in result.intents if it.side == "buy")
    sells = sum(1 for it in result.intents if it.side == "sell")
    ev.append(Event(
        "cycle",
        f"장후 심의 · 신호 {draft.signalled}종목 → 심의 {len(draft.candidates)} → 매수안 {buys} · 매도안 {sells} · 국면 {draft.regime.label}",
        payload={"scanned": draft.scanned, "signalled": draft.signalled, "candidates": len(draft.candidates), "buys": buys,
                 "sells": sells, "regime": draft.regime.label, "regime_score": round(draft.regime.score),
                 "exposure_cap": round(draft.regime.exposure_cap, 3)},
    ))
    return result
