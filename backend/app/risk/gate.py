"""리스크 게이트. 위원회(AI 또는 규칙)의 결론은 여기를 통과해야 주문 계획이 된다.

게이트는 수량을 **줄이거나 거부만** 한다. 늘리지 않는다. AI가 무엇을 말하든 한도는 규칙이 지킨다.
차단(block)은 주문을 만들지 않고, 축소(reduce)는 수량을 줄이며, 모든 단계가 기록으로 남는다.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from app.core.market_rules import CostModel, tick_size
from app.core.models import CONVICTION_LABEL, CONVICTION_ORDER, Decision, EntryPlan, Position, StockInfo
from app.risk.breakers import BreakerState
from app.risk.limits import CONVICTION_MULTIPLIER, RiskLimits


@dataclass(slots=True)
class GateStep:
    rule: str
    outcome: str  # pass | reduce | block | note
    detail: str
    qty_after: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class GateResult:
    approved: bool
    qty: int
    stop: int | None
    steps: list[GateStep] = field(default_factory=list)
    order_value: int = 0
    risk_amount: int = 0
    base_qty: int = 0  # 한도 적용 전 수량(위험 기준)

    @property
    def blocked_by(self) -> list[str]:
        return [s.rule for s in self.steps if s.outcome == "block"]

    @property
    def reduced_by(self) -> list[str]:
        return [s.rule for s in self.steps if s.outcome == "reduce"]

    def summary(self) -> str:
        if not self.approved:
            blocks = [s.detail for s in self.steps if s.outcome == "block"]
            return "거부: " + (blocks[0] if blocks else "수량 0")
        if self.reduced_by:
            return f"축소 통과: {self.base_qty}주 → {self.qty}주"
        return "통과"

    def to_dict(self) -> dict:
        return {
            "approved": self.approved, "qty": self.qty, "stop": self.stop, "order_value": self.order_value,
            "risk_amount": self.risk_amount, "base_qty": self.base_qty, "summary": self.summary(),
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass(slots=True)
class GateContext:
    equity: float
    cash: float
    positions: dict[str, Position]
    prices: dict[str, float]
    exposure_cap: float  # 시장 국면이 정한 총 노출 상한(0~1)
    allow_new_buys: bool  # 시장 국면이 신규 매수를 허용하는지
    breaker: BreakerState
    costs: CostModel
    avg_value20: float  # 대상 종목의 20일 평균 거래대금
    sectors: dict[str, str] = field(default_factory=dict)  # 보유 종목 코드 → 업종
    pending_value: float = 0.0  # 같은 거래일에 이미 잡힌 매수 계획 금액
    pending_risk: float = 0.0
    pending_codes: frozenset[str] = frozenset()
    pending_by_sector: dict[str, float] = field(default_factory=dict)
    orders_today: int = 0
    blocked_flags: frozenset[str] = frozenset()  # 투자경고·거래정지 등(증권사 종목 마스터 기준)

    def invested(self) -> float:
        return sum(p.qty * self.prices.get(c, p.avg_price) for c, p in self.positions.items())

    def open_risk(self) -> float:
        return sum(max(0.0, self.prices.get(c, p.avg_price) - p.stop) * p.qty for c, p in self.positions.items())

    def sector_value(self, sector: str) -> float:
        held = sum(
            p.qty * self.prices.get(c, p.avg_price)
            for c, p in self.positions.items()
            if (self.sectors.get(c) or p.sector) == sector
        )
        return held + self.pending_by_sector.get(sector, 0.0)


def _block(result: GateResult, rule: str, detail: str) -> GateResult:
    result.steps.append(GateStep(rule, "block", detail, 0))
    result.approved = False
    result.qty = 0
    return result


def _clamp(result: GateResult, qty: int, cap_value: float, price: float, rule: str, label: str) -> int:
    """금액 한도(cap_value)에 맞춰 수량을 줄인다. 줄였으면 기록한다."""
    allowed = max(0, int(math.floor(cap_value / price))) if price > 0 else 0
    if allowed < qty:
        result.steps.append(GateStep(rule, "reduce", f"{label}: {qty}주 → {allowed}주", allowed))
        return allowed
    result.steps.append(GateStep(rule, "pass", label, qty))
    return qty


def gate_buy(decision: Decision, plan: EntryPlan, info: StockInfo, ctx: GateContext, limits: RiskLimits) -> GateResult:
    """매수 결론 검증. 순서: 차단 조건 → 손절·비용 검증 → 위험 기준 수량 → 한도별 축소."""
    result = GateResult(approved=True, qty=0, stop=plan.stop)
    ref = plan.reference_price

    # 1) 차단 조건
    if decision.action != "BUY":
        return _block(result, "action", "매수 결론이 아닙니다")
    if decision.status != "ok":
        return _block(result, "decision_status", f"판단이 보류 상태입니다({decision.status_detail or '검토 필요'})")
    if ctx.breaker.halt_engine or ctx.breaker.new_buys_blocked:
        reason = ctx.breaker.reasons[0] if ctx.breaker.reasons else "회로차단기 작동"
        return _block(result, "circuit_breaker", reason)
    if not ctx.allow_new_buys:
        return _block(result, "market_regime", "시장 국면이 신규 매수를 허용하지 않습니다")
    if ctx.blocked_flags:
        return _block(result, "stock_flags", "매매 제한 종목: " + ", ".join(sorted(ctx.blocked_flags)))
    if info.code in ctx.positions:
        return _block(result, "already_held", "이미 보유 중인 종목입니다(추가 매수는 1차 범위 밖)")
    if info.code in ctx.pending_codes:
        return _block(result, "duplicate", "같은 종목의 주문 계획이 이미 있습니다")
    if len(ctx.positions) + len(ctx.pending_codes) >= limits.max_positions:
        return _block(result, "max_positions", f"보유 종목 수 한도 {limits.max_positions}개에 닿았습니다")
    if ctx.orders_today >= limits.max_orders_per_day:
        return _block(result, "max_orders", f"일일 주문 수 한도 {limits.max_orders_per_day}건에 닿았습니다")
    if CONVICTION_ORDER.index(decision.conviction) < CONVICTION_ORDER.index(limits.min_buy_conviction):  # type: ignore[arg-type]
        return _block(result, "conviction", f"확신 '{CONVICTION_LABEL[decision.conviction]}'은 매수 기준 '{CONVICTION_LABEL[limits.min_buy_conviction]}'에 못 미칩니다")
    if ctx.avg_value20 < limits.min_avg_value:
        return _block(result, "liquidity_floor", f"20일 평균 거래대금 {ctx.avg_value20 / 1e8:.0f}억 원이 기준 {limits.min_avg_value / 1e8:.0f}억 원에 못 미칩니다")

    # 2) 손절: AI는 계획 손절을 좁히는(높이는) 것만 할 수 있다.
    stop = plan.stop
    if decision.stop is not None and decision.stop != plan.stop:
        valid = plan.stop < decision.stop < ref * 0.99 and decision.stop % tick_size(decision.stop) == 0
        if valid:
            stop = decision.stop
            result.steps.append(GateStep("stop_adjust", "note", f"손절을 {plan.stop:,}원 → {stop:,}원으로 좁혔습니다"))
        else:
            result.steps.append(GateStep("stop_adjust", "note", f"제안 손절 {decision.stop:,}원은 허용 범위 밖이라 계획 손절 {plan.stop:,}원을 씁니다"))
    result.stop = stop
    risk_per_share = ref - stop
    if risk_per_share <= 0:
        return _block(result, "stop_invalid", "손절가가 진입가보다 낮지 않습니다")
    risk_pct = risk_per_share / ref
    if risk_pct > limits.max_stop_pct + 1e-9:
        return _block(result, "max_stop", f"손절까지 {risk_pct * 100:.1f}%로 한도 {limits.max_stop_pct * 100:.0f}%를 넘습니다")
    result.steps.append(GateStep("max_stop", "pass", f"손절까지 {risk_pct * 100:.1f}%"))

    # 3) 비용
    cost = ctx.costs.round_trip_per_share(ref)
    if cost / risk_per_share > limits.max_cost_to_risk:
        return _block(result, "cost_to_risk", f"비용이 위험의 {cost / risk_per_share * 100:.0f}%로 한도 {limits.max_cost_to_risk * 100:.0f}%를 넘습니다")
    if plan.target is not None:
        net_reward = plan.target - ref - cost
        reward_to_risk = net_reward / (risk_per_share + cost)
        if reward_to_risk < limits.min_reward_to_risk:
            return _block(result, "reward_to_risk", f"비용 차감 손익비 {reward_to_risk:.2f}가 기준 {limits.min_reward_to_risk:.1f}에 못 미칩니다")
    result.steps.append(GateStep("costs", "pass", f"왕복 비용 1주당 약 {cost:,.0f}원"))

    # 4) 위험 기준 수량
    fraction = min(1.0, max(0.0, decision.size_fraction))
    budget = ctx.equity * limits.risk_per_trade_pct * CONVICTION_MULTIPLIER[decision.conviction] * ctx.breaker.size_multiplier * fraction
    qty = int(math.floor(budget / risk_per_share))
    result.base_qty = qty
    detail = f"위험 예산 {budget:,.0f}원 ÷ 1주 위험 {risk_per_share:,.0f}원 = {qty}주"
    if ctx.breaker.size_multiplier < 1.0:
        detail += f" (낙폭으로 크기 {ctx.breaker.size_multiplier * 100:.0f}%)"
    result.steps.append(GateStep("risk_budget", "pass", detail, qty))

    # 5) 한도별 축소 (줄이기만 한다)
    qty = _clamp(result, qty, ctx.equity * limits.max_position_pct, ref, "max_position", f"종목당 비중 {limits.max_position_pct * 100:.0f}%")
    qty = _clamp(result, qty, ctx.equity * limits.max_order_value_pct, ref, "max_order_value", f"1회 주문 금액 {limits.max_order_value_pct * 100:.0f}%")
    qty = _clamp(result, qty, ctx.avg_value20 * limits.max_adv_pct, ref, "liquidity", f"평균 거래대금의 {limits.max_adv_pct * 100:.0f}%")
    sector_room = ctx.equity * limits.max_sector_pct - ctx.sector_value(info.sector)
    qty = _clamp(result, qty, sector_room, ref, "max_sector", f"업종({info.sector}) 비중 {limits.max_sector_pct * 100:.0f}%")
    heat_room = ctx.equity * limits.max_heat_pct - ctx.open_risk() - ctx.pending_risk
    qty = _clamp(result, qty, heat_room, risk_per_share, "max_heat", f"열린 위험 합계 {limits.max_heat_pct * 100:.0f}%")
    exposure_room = ctx.equity * ctx.exposure_cap - ctx.invested() - ctx.pending_value
    qty = _clamp(result, qty, exposure_room, ref, "exposure_cap", f"시장 국면 노출 상한 {ctx.exposure_cap * 100:.0f}%")
    cash_room = (ctx.cash - ctx.pending_value - ctx.equity * limits.min_cash_pct) / (1 + ctx.costs.commission_rate + ctx.costs.slippage_rate)
    qty = _clamp(result, qty, cash_room, ref, "cash", f"현금(최소 {limits.min_cash_pct * 100:.0f}% 유지)")

    if qty < 1:
        return _block(result, "zero_qty", "한도를 적용하니 살 수 있는 수량이 없습니다")
    result.qty = qty
    result.order_value = int(round(qty * ref))
    result.risk_amount = int(round(qty * risk_per_share))
    return result


def gate_sell(decision: Decision, position: Position | None) -> GateResult:
    """매도 결론 검증. 보유 수량 전부를 판다(노출을 줄이는 방향이라 한도 검사가 없다)."""
    result = GateResult(approved=True, qty=0, stop=None)
    if decision.action != "SELL":
        return _block(result, "action", "매도 결론이 아닙니다")
    if position is None or position.qty <= 0:
        return _block(result, "not_held", "보유하지 않은 종목입니다")
    if decision.status != "ok":
        return _block(result, "decision_status", "판단이 보류 상태라 보유를 유지합니다(보호 청산은 계속 작동)")
    result.qty = position.qty
    result.base_qty = position.qty
    result.steps.append(GateStep("sell", "pass", f"보유 {position.qty}주 전량 매도", position.qty))
    return result
