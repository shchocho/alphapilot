from datetime import date

import pytest
from pydantic import ValidationError

from app.core.market_rules import CostModel
from app.core.models import Decision, EntryPlan, Position, StockInfo
from app.risk.breakers import BreakerState, evaluate_breakers
from app.risk.exits import check_protective, check_quote, stop_reason, trailed_stop
from app.risk.gate import GateContext, gate_buy, gate_sell
from app.risk.limits import RiskLimits

INFO = StockInfo("000001", "테스트전자", "KOSPI", "반도체")
COSTS = CostModel()
LIMITS = RiskLimits()


def plan(ref=50_000.0, stop=47_000, target=None) -> EntryPlan:
    return EntryPlan(entry_type="open", stop=stop, reference_price=ref, target=target)


def decision(**kw) -> Decision:
    base = dict(code="000001", name="테스트전자", kind="entry", action="BUY", conviction="medium")
    base.update(kw)
    return Decision(**base)


def ctx(**kw) -> GateContext:
    base = dict(
        equity=100_000_000.0, cash=100_000_000.0, positions={}, prices={}, exposure_cap=1.0, allow_new_buys=True,
        breaker=BreakerState(), costs=COSTS, avg_value20=50_000_000_000.0,
    )
    base.update(kw)
    return GateContext(**base)


def position(code="000002", qty=100, avg=50_000.0, stop=47_000, sector="반도체", **kw) -> Position:
    return Position(code=code, name=f"보유{code}", qty=qty, avg_price=avg, opened_on=date(2026, 11, 2),
                    technique="vcp", stop=stop, entry_risk=avg - stop, sector=sector, **kw)


# ── 수량 계산 ────────────────────────────────────────────────────────────────

def test_base_quantity_is_risk_budget_over_per_share_risk():
    # 1억 × 0.5% × 1.0 = 50만 원 위험 예산, 1주 위험 3,000원 → 166주
    result = gate_buy(decision(), plan(), INFO, ctx(), LIMITS)
    assert result.approved
    assert result.base_qty == 166
    assert result.qty == 166
    assert result.risk_amount == 166 * 3_000
    assert result.summary() == "통과"


@pytest.mark.parametrize(("conviction", "expected"), [("low", 125), ("medium", 166), ("high", 208), ("very_high", 291)])
def test_conviction_scales_the_risk_budget(conviction, expected):
    assert gate_buy(decision(conviction=conviction), plan(), INFO, ctx(), LIMITS).base_qty == expected


def test_size_fraction_can_only_shrink():
    half = gate_buy(decision(size_fraction=0.5), plan(), INFO, ctx(), LIMITS)
    over = gate_buy(decision(size_fraction=3.0), plan(), INFO, ctx(), LIMITS)
    assert half.base_qty == 83
    assert over.base_qty == 166  # 1을 넘는 요청은 1로 본다


def test_drawdown_multiplier_shrinks_size():
    result = gate_buy(decision(), plan(), INFO, ctx(breaker=BreakerState(size_multiplier=0.5)), LIMITS)
    assert result.base_qty == 83


# ── 차단 조건 (표 기반) ────────────────────────────────────────────────────────

BLOCK_CASES = [
    ("action", dict(), dict(), dict(action="HOLD")),
    ("decision_status", dict(), dict(), dict(status="review", status_detail="AI 응답 시간 초과")),
    ("circuit_breaker", dict(), dict(breaker=BreakerState(new_buys_blocked=True, reasons=["일 손실 한도"])), dict()),
    ("circuit_breaker", dict(), dict(breaker=BreakerState(halt_engine=True)), dict()),
    ("market_regime", dict(), dict(allow_new_buys=False), dict()),
    ("stock_flags", dict(), dict(blocked_flags=frozenset({"투자경고"})), dict()),
    ("already_held", dict(), dict(positions={"000001": None}), dict()),
    ("duplicate", dict(), dict(pending_codes=frozenset({"000001"})), dict()),
    ("max_orders", dict(), dict(orders_today=20), dict()),
    ("conviction", dict(), dict(), dict(conviction="very_low")),
    ("liquidity_floor", dict(), dict(avg_value20=1_000_000_000.0), dict()),
    ("stop_invalid", dict(stop=50_000), dict(), dict()),
    ("max_stop", dict(stop=45_000), dict(), dict()),  # −10%
    ("reward_to_risk", dict(target=51_000), dict(), dict()),  # 보상 1,000 vs 위험 3,000
    ("zero_qty", dict(), dict(cash=5_000_000.0), dict()),  # 현금 버퍼(10%) 아래
]


@pytest.mark.parametrize(("rule", "plan_kw", "ctx_kw", "decision_kw"), BLOCK_CASES)
def test_gate_blocks(rule, plan_kw, ctx_kw, decision_kw):
    if "positions" in ctx_kw and ctx_kw["positions"].get("000001") is None:
        ctx_kw = {**ctx_kw, "positions": {"000001": position(code="000001")}}
    result = gate_buy(decision(**decision_kw), plan(**plan_kw), INFO, ctx(**ctx_kw), LIMITS)
    assert not result.approved
    assert result.qty == 0
    assert result.blocked_by == [rule]
    assert result.summary().startswith("거부")


def test_gate_blocks_when_position_count_is_at_limit():
    held = {f"{i:06d}": position(code=f"{i:06d}", qty=1, sector=f"업종{i}") for i in range(10, 16)}
    result = gate_buy(decision(), plan(), INFO, ctx(positions=held, pending_codes=frozenset({"A", "B"})), LIMITS)
    assert result.blocked_by == ["max_positions"]


def test_gate_blocks_when_costs_eat_the_risk():
    tight = plan(ref=50_000.0, stop=49_800)  # 위험 200원, 왕복 비용 약 165원
    result = gate_buy(decision(), tight, INFO, ctx(), LIMITS)
    assert result.blocked_by == ["cost_to_risk"]


# ── 한도별 축소 ───────────────────────────────────────────────────────────────

def test_position_cap_reduces_quantity():
    wide = plan(ref=50_000.0, stop=49_000)  # 위험 1,000원 → 500주(2,500만 원) → 종목당 10%(1,000만 원) = 200주
    result = gate_buy(decision(), wide, INFO, ctx(), LIMITS)
    assert result.approved
    assert result.base_qty == 500
    assert result.qty == 200
    assert "max_position" in result.reduced_by
    assert result.summary() == "축소 통과: 500주 → 200주"


def test_liquidity_cap_reduces_quantity():
    result = gate_buy(decision(), plan(), INFO, ctx(avg_value20=400_000_000.0), RiskLimits(min_avg_value=0))
    assert result.qty == 80  # 4억 × 1% = 400만 원 ÷ 5만 원
    assert "liquidity" in result.reduced_by


def test_sector_cap_counts_held_and_pending_value():
    held = {"000002": position(qty=500, avg=50_000.0)}  # 반도체 2,500만 원
    context = ctx(positions=held, prices={"000002": 50_000.0}, pending_by_sector={"반도체": 3_000_000.0})
    result = gate_buy(decision(), plan(), INFO, context, LIMITS)
    # 업종 한도 3,000만 − 2,500만 − 300만 = 200만 원 → 40주
    assert result.qty == 40
    assert "max_sector" in result.reduced_by


def test_heat_cap_counts_open_risk_of_existing_positions():
    held = {"000002": position(qty=1_800, avg=50_000.0, stop=47_000, sector="금융")}  # 열린 위험 540만 원
    context = ctx(equity=100_000_000.0, positions=held, prices={"000002": 50_000.0})
    result = gate_buy(decision(), plan(), INFO, context, RiskLimits(max_position_pct=0.5, max_sector_pct=1.0))
    # heat 한도 600만 − 540만 = 60만 원 ÷ 3,000원 = 200주인데, 위험 예산 기준 166주가 더 작다
    assert result.qty == 166
    tighter = ctx(positions={"000002": position(qty=1_900, avg=50_000.0, stop=47_000, sector="금융")}, prices={"000002": 50_000.0})
    result = gate_buy(decision(), plan(), INFO, tighter, RiskLimits(max_position_pct=0.5, max_sector_pct=1.0))
    assert result.qty == 100  # 600만 − 570만 = 30만 원 ÷ 3,000원
    assert "max_heat" in result.reduced_by


def test_exposure_cap_from_market_regime_reduces_quantity():
    held = {"000002": position(qty=900, avg=50_000.0, sector="금융")}  # 4,500만 원 투자 중
    context = ctx(positions=held, prices={"000002": 50_000.0}, exposure_cap=0.5, cash=55_000_000.0)
    result = gate_buy(decision(), plan(), INFO, context, LIMITS)
    assert result.qty == 100  # 5,000만 − 4,500만 = 500만 원
    assert "exposure_cap" in result.reduced_by


def test_cash_buffer_reduces_quantity():
    context = ctx(cash=14_000_000.0)  # 최소 현금 1,000만 원을 빼면 400만 원
    result = gate_buy(decision(), plan(), INFO, context, LIMITS)
    assert result.qty == 79
    assert "cash" in result.reduced_by


def test_pending_plans_use_up_cash_and_exposure():
    context = ctx(cash=30_000_000.0, pending_value=15_000_000.0)
    result = gate_buy(decision(), plan(), INFO, context, LIMITS)
    assert result.qty == 99  # (3,000만 − 1,500만 − 1,000만) ÷ 약 50,033원


# ── 손절 조정 ─────────────────────────────────────────────────────────────────

def test_ai_may_tighten_the_stop_which_changes_size():
    result = gate_buy(decision(stop=48_000), plan(), INFO, ctx(), LIMITS)
    assert result.stop == 48_000
    assert result.base_qty == 250  # 위험 2,000원


@pytest.mark.parametrize("bad_stop", [46_000, 49_900, 48_030])
def test_ai_cannot_loosen_or_misprice_the_stop(bad_stop):
    result = gate_buy(decision(stop=bad_stop), plan(), INFO, ctx(), LIMITS)
    assert result.stop == 47_000
    assert any(s.rule == "stop_adjust" and "허용 범위 밖" in s.detail for s in result.steps)


def test_gate_never_raises_quantity_above_base():
    for conviction in ("low", "medium", "high", "very_high"):
        result = gate_buy(decision(conviction=conviction), plan(), INFO, ctx(), LIMITS)
        assert result.qty <= result.base_qty


# ── 매도 ─────────────────────────────────────────────────────────────────────

def test_gate_sell_approves_full_position():
    result = gate_sell(decision(action="SELL", kind="holding"), position(qty=37))
    assert result.approved and result.qty == 37


@pytest.mark.parametrize(
    ("kw", "pos", "rule"),
    [(dict(action="HOLD"), "held", "action"), (dict(action="SELL"), None, "not_held"),
     (dict(action="SELL", status="review"), "held", "decision_status")],
)
def test_gate_sell_blocks(kw, pos, rule):
    result = gate_sell(decision(kind="holding", **kw), position() if pos else None)
    assert result.blocked_by == [rule]


def test_gate_result_serialises():
    data = gate_buy(decision(), plan(), INFO, ctx(), LIMITS).to_dict()
    assert data["approved"] and data["steps"]


# ── 회로차단기 ────────────────────────────────────────────────────────────────

MON, TUE, WED = date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)
PREV_FRI = date(2026, 11, 6)
OCT_END = date(2026, 10, 30)


def test_no_breaker_in_calm_conditions():
    state = evaluate_breakers([(PREV_FRI, 100.0), (MON, 100.5)], TUE, 100.4, 100.5, [], LIMITS)
    assert not state.new_buys_blocked and state.size_multiplier == 1.0 and not state.reasons


def test_daily_loss_limit_blocks_new_buys():
    state = evaluate_breakers([(MON, 100.0)], TUE, 97.9, 100.0, [], LIMITS)
    assert state.new_buys_blocked
    assert state.daily_pct == pytest.approx(-0.021)
    assert "일 손실" in state.reasons[0]


def test_weekly_loss_uses_last_equity_before_this_week():
    history = [(PREV_FRI, 100.0), (MON, 98.5), (TUE, 97.0)]
    state = evaluate_breakers(history, WED, 94.9, 100.0, [], RiskLimits(drawdown_reduce_pct=0.3, drawdown_half_pct=0.4, drawdown_block_pct=0.5, drawdown_halt_pct=0.6))
    assert state.weekly_pct == pytest.approx(-0.051)
    assert any("주 손실" in r for r in state.reasons)


def test_monthly_loss_uses_last_equity_before_this_month():
    history = [(OCT_END, 100.0), (PREV_FRI, 95.0), (MON, 93.0), (TUE, 92.5)]
    loose = RiskLimits(weekly_loss_limit_pct=0.3, monthly_loss_limit_pct=0.3, drawdown_reduce_pct=0.3, drawdown_half_pct=0.4, drawdown_block_pct=0.5, drawdown_halt_pct=0.6)
    assert not evaluate_breakers(history, WED, 92.3, 100.0, [], loose).new_buys_blocked
    state = evaluate_breakers(history, WED, 91.9, 100.0, [], RiskLimits(weekly_loss_limit_pct=0.08, drawdown_reduce_pct=0.3, drawdown_half_pct=0.4, drawdown_block_pct=0.5, drawdown_halt_pct=0.6))
    assert state.monthly_pct == pytest.approx(-0.081)
    assert any("월 손실" in r for r in state.reasons)


@pytest.mark.parametrize(
    ("equity", "multiplier", "blocked", "halted"),
    [(96.0, 1.0, False, False), (94.9, 0.75, False, False), (89.9, 0.5, False, False),
     (84.9, 0.0, True, False), (79.9, 0.0, True, True)],
)
def test_drawdown_ladder(equity, multiplier, blocked, halted):
    loose = RiskLimits(daily_loss_limit_pct=0.2, weekly_loss_limit_pct=0.3, monthly_loss_limit_pct=0.5)
    state = evaluate_breakers([(MON, equity)], TUE, equity, 100.0, [], loose)
    assert (state.size_multiplier, state.new_buys_blocked, state.halt_engine) == (multiplier, blocked, halted)


def test_two_stop_outs_in_a_row_pause_new_buys_for_a_day():
    exits = [(PREV_FRI, "target", 50_000.0), (MON, "stop", -30_000.0), (TUE, "trail_stop", -10_000.0)]
    state = evaluate_breakers([(MON, 100.0)], TUE, 100.0, 100.0, exits, LIMITS)
    assert state.new_buys_blocked
    next_day = evaluate_breakers([(MON, 100.0), (TUE, 100.0)], WED, 100.0, 100.0, exits, LIMITS, previous_trading_day=TUE)
    assert next_day.new_buys_blocked
    later = evaluate_breakers([(MON, 100.0)], date(2026, 11, 13), 100.0, 100.0, exits, LIMITS, previous_trading_day=date(2026, 11, 12))
    assert not later.new_buys_blocked


def test_profitable_trailing_stop_does_not_count_as_a_loss_streak():
    exits = [(MON, "stop", -30_000.0), (TUE, "trail_stop", 40_000.0)]
    assert not evaluate_breakers([(MON, 100.0)], TUE, 100.0, 100.0, exits, LIMITS).new_buys_blocked


def test_incomplete_data_fails_closed():
    state = evaluate_breakers([], TUE, 100.0, 100.0, [], LIMITS, data_complete=False)
    assert state.new_buys_blocked
    assert state.to_dict()["reasons"]


# ── 한도 모델 ────────────────────────────────────────────────────────────────

def test_limits_reject_out_of_range_values():
    with pytest.raises(ValidationError):
        RiskLimits(max_position_pct=0.9)
    with pytest.raises(ValidationError):
        RiskLimits(drawdown_reduce_pct=0.2, drawdown_half_pct=0.1)
    with pytest.raises(ValidationError):
        RiskLimits(daily_loss_limit_pct=0.1, weekly_loss_limit_pct=0.05)
    with pytest.raises(ValidationError):
        RiskLimits(min_buy_conviction="certain")


def test_loosened_fields_are_detected_for_step_up_auth():
    old = RiskLimits()
    new = RiskLimits(max_position_pct=0.2, min_cash_pct=0.05, risk_per_trade_pct=0.004, min_buy_conviction="very_low")
    assert set(new.is_looser_than(old)) == {"max_position_pct", "min_cash_pct", "min_buy_conviction"}
    assert RiskLimits(max_positions=5).is_looser_than(old) == []


# ── 보호 청산 ─────────────────────────────────────────────────────────────────

def test_stop_fills_at_stop_price_when_touched_intraday():
    pos = position(stop=47_000)
    assert check_protective(pos, open_=49_000, high=49_500, low=46_500) == ("stop", 47_000.0)


def test_gap_down_through_stop_fills_at_the_open():
    pos = position(stop=47_000)
    assert check_protective(pos, open_=45_000, high=46_000, low=44_000) == ("stop", 45_000)


def test_target_fills_at_target_or_at_gap_open():
    pos = position(stop=47_000, target=56_000)
    assert check_protective(pos, open_=52_000, high=57_000, low=51_000) == ("target", 56_000.0)
    assert check_protective(pos, open_=58_000, high=59_000, low=57_000) == ("target", 58_000)


def test_stop_wins_when_both_stop_and_target_are_touched():
    pos = position(stop=47_000, target=56_000)
    assert check_protective(pos, open_=50_000, high=57_000, low=46_000)[0] == "stop"


def test_nothing_happens_inside_the_band():
    pos = position(stop=47_000, target=56_000)
    assert check_protective(pos, open_=50_000, high=52_000, low=48_000) is None


def test_raised_stop_is_reported_as_trailing_stop():
    pos = position(avg=50_000.0, stop=52_000)
    pos.entry_risk = 3_000.0
    assert stop_reason(pos) == "trail_stop"
    assert check_protective(pos, open_=53_000, high=53_500, low=51_500)[0] == "trail_stop"


def test_quote_check_for_live_monitoring():
    pos = position(stop=47_000, target=56_000)
    assert check_quote(pos, 46_900) == "stop"
    assert check_quote(pos, 56_100) == "target"
    assert check_quote(pos, 50_000) is None


def test_trailing_stop_only_moves_up():
    pos = position(stop=47_000, trail_mult=2.0, highest_close=52_000.0)
    assert trailed_stop(pos, close=55_000.0, atr=1_500.0) == 52_000  # 55,000 − 3,000
    assert trailed_stop(pos, close=48_000.0, atr=1_500.0) == 49_000  # 최고 종가 52,000 기준
    pos.stop = 51_000
    assert trailed_stop(pos, close=50_000.0, atr=1_500.0) == 51_000  # 내려가지 않는다
    pos.trail_mult = None
    assert trailed_stop(pos, close=60_000.0, atr=1_500.0) == 51_000


# ── 남은 분기 ────────────────────────────────────────────────────────────────

def test_target_with_enough_reward_passes_the_ratio_check():
    result = gate_buy(decision(), plan(target=57_000), INFO, ctx(), LIMITS)  # 보상 7,000 vs 위험 3,000
    assert result.approved
    assert "reward_to_risk" not in result.blocked_by


def test_breakers_skip_drawdown_when_no_peak_is_known():
    state = evaluate_breakers([], TUE, 100.0, 0.0, [], LIMITS)
    assert state.drawdown_pct == 0.0
    assert not state.new_buys_blocked
