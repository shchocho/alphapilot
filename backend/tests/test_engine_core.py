from datetime import date

import numpy as np
import pytest

from app.backtest import metrics
from app.backtest.runner import run_backtest
from app.core.models import Decision, Fill, Portfolio, Position, StockInfo
from app.data.sample import SampleProvider
from app.engine.core import (
    EngineConfig,
    EntryPrefilter,
    exit_signals,
    finalize_cycle,
    prepare_cycle,
    rules_decisions,
)
from app.indicators.features import build_market
from app.regime.regime import compute_regime
from app.risk.limits import RiskLimits
from app.techniques import registry
from tests.helpers import END, linear, make_bars, make_market

CODE = "000001"
NEXT = date(2026, 11, 16)
ONLY_CANSLIM = ("canslim_daily",)  # 비교용 횡보 종목이 다른 기법에 걸리지 않게, 사이클 테스트는 한 기법만 켠다
CFG = EngineConfig(enabled_techniques=ONLY_CANSLIM)


def leader_bars(n: int = 300, scale: float = 1.0):
    steps = np.where(np.arange(n) % 2 == 0, 1.01, 0.997)
    closes = 10_000 * scale * np.cumprod(steps)
    closes[-1] = closes[-2] * 1.02
    volumes = np.where(steps > 1, 1_500_000.0, 500_000.0)
    volumes[-1] = 3_000_000.0
    return make_bars(closes, volumes=volumes)


def cycle_inputs(bars: dict, cash: int = 100_000_000, **market_kw):
    market_kw.setdefault("peer_drift", -0.0005)  # 비교 종목은 서서히 내려가 후보가 되지 않는다
    market = make_market(bars, **market_kw)
    regime = compute_regime(market)[-1]
    return market, regime, Portfolio(cash=cash, peak_equity=float(cash))


def draft_for(market, regime, portfolio, cfg=None, **kw):
    return prepare_cycle(END, NEXT, market, regime, portfolio, cfg or CFG, equity_history=[], recent_exits=[], **kw)


# ── 장후 사이클 ───────────────────────────────────────────────────────────────

def test_leader_becomes_a_candidate_with_a_rule_computed_envelope():
    market, regime, portfolio = cycle_inputs({CODE: leader_bars()})
    draft = draft_for(market, regime, portfolio)
    assert [c.info.code for c in draft.candidates] == [CODE]
    cand = draft.candidates[0]
    assert cand.primary.key == "canslim_daily"
    assert cand.max_qty["low"] <= cand.max_qty["medium"] <= cand.max_qty["high"] <= cand.max_qty["very_high"]
    assert cand.max_qty["medium"] >= 1
    assert cand.context.max_qty == cand.max_qty
    assert draft.signalled == 1


def test_rules_buy_becomes_an_approved_intent_for_the_next_trading_day():
    market, regime, portfolio = cycle_inputs({CODE: leader_bars()})
    draft = draft_for(market, regime, portfolio)
    entries, holds = rules_decisions(draft)
    result = finalize_cycle(draft, entries, holds, portfolio, CFG)
    intent = result.intents[0]
    assert (intent.side, intent.status, intent.trade_date, intent.created_on) == ("buy", "approved", NEXT, END)
    assert intent.qty >= 1 and intent.stop < draft.candidates[0].close
    record = result.records[0]
    assert record.gate.approved and record.intent_id == intent.id
    kinds = [e.kind for e in result.events]
    assert kinds.count("decision") == 1 and "intent" in kinds and kinds[-1] == "cycle"
    assert record.to_body()["final"]["action"] == "BUY"


def test_ai_failure_never_produces_a_buy_intent():
    market, regime, portfolio = cycle_inputs({CODE: leader_bars()})
    draft = draft_for(market, regime, portfolio)
    failed = Decision(CODE, "x", "entry", "HOLD", "very_low", source="ai", status="review", status_detail="timeout: Claude 응답 시간 초과")
    result = finalize_cycle(draft, {CODE: (failed, {"error": "timeout"})}, {}, portfolio, CFG)
    assert result.intents == []
    assert any("판단 보류" in e.summary for e in result.events)


def test_buy_decision_marked_review_is_blocked_even_if_action_says_buy():
    market, regime, portfolio = cycle_inputs({CODE: leader_bars()})
    draft = draft_for(market, regime, portfolio)
    odd = Decision(CODE, "x", "entry", "BUY", "high", source="ai", status="review", status_detail="invalid_output")
    assert finalize_cycle(draft, {CODE: (odd, None)}, {}, portfolio, CFG).intents == []


def test_held_and_pending_stocks_are_not_candidates():
    market, regime, portfolio = cycle_inputs({CODE: leader_bars()})
    assert draft_for(market, regime, portfolio, pending_codes=frozenset({CODE})).candidates == []
    close = float(market.stocks[CODE].close[-1])
    portfolio.positions[CODE] = Position(CODE, "x", 10, close * 0.9, date(2026, 10, 1), "vcp", int(close * 0.8), close * 0.1)
    draft = draft_for(market, regime, portfolio)
    assert draft.candidates == []
    assert [h.info.code for h in draft.holdings] == [CODE]


def test_illiquid_stock_is_filtered_before_any_evaluation():
    bars = leader_bars()
    bars["volume"] = (bars["volume"] / 50).astype("int64")  # 거래대금 약 3~6억
    market, regime, portfolio = cycle_inputs({CODE: bars})
    draft = draft_for(market, regime, portfolio)
    assert draft.candidates == [] and draft.signalled == 0


def test_weak_market_blocks_candidates_at_the_precheck():
    falling = make_bars(np.concatenate([np.full(260, 3000.0), linear(3000.0, 2500.0, 40)]), spread=0.003)
    market, regime, portfolio = cycle_inputs({CODE: leader_bars(), "000002": leader_bars(scale=2.0)}, index=falling)
    assert not regime.allow_new_buys
    draft = draft_for(market, regime, portfolio)
    assert draft.candidates == []
    entries, holds = rules_decisions(draft)
    result = finalize_cycle(draft, entries, holds, portfolio, CFG)
    assert result.intents == []


def test_candidate_excluded_before_review_is_logged_as_precheck_not_as_a_gate_block():
    # 심의 전에 걸러진 후보는 '사전 제외'로 적는다. 매수 판단 뒤의 리스크 거부와 섞이면 거부 건수가 부풀려진다.
    market, regime, portfolio = cycle_inputs({CODE: leader_bars(), "000002": leader_bars(scale=2.0)})
    close = float(market.stocks["000002"].close[-1])
    portfolio.positions["000002"] = Position("000002", "x", 10, close * 0.9, date(2026, 10, 1), "vcp", int(close * 0.8), close * 0.1)
    cfg = EngineConfig(limits=RiskLimits(max_positions=1), enabled_techniques=ONLY_CANSLIM)
    draft = draft_for(market, regime, portfolio, cfg)
    assert draft.candidates == [] and [info.code for info, _, _ in draft.precheck_blocked] == [CODE]
    entries, holds = rules_decisions(draft)
    result = finalize_cycle(draft, entries, holds, portfolio, cfg)
    kinds = [e.kind for e in result.events]
    assert kinds.count("precheck") == 1 and "gate_block" not in kinds


def test_second_candidate_in_same_sector_sees_the_first_ones_pending_value():
    bars = {CODE: leader_bars(), "000002": leader_bars(scale=3.0)}
    market, regime, portfolio = cycle_inputs(bars, sectors={CODE: "반도체", "000002": "반도체"})
    cfg = EngineConfig(limits=RiskLimits(max_sector_pct=0.12, max_position_pct=0.10), enabled_techniques=ONLY_CANSLIM)
    draft = draft_for(market, regime, portfolio, cfg)
    entries, holds = rules_decisions(draft)
    result = finalize_cycle(draft, entries, holds, portfolio, cfg)
    values = [it.qty * it.est_price for it in result.intents]
    assert len(values) == 2
    assert sum(values) <= 100_000_000 * 0.12 * 1.001  # 업종 한도 12% 안에 둘의 합이 들어온다
    assert values[1] < values[0]


def test_max_candidates_limits_deliberation_and_logs_the_rest():
    bars = {f"{k:06d}": leader_bars(scale=1 + 0.2 * k) for k in range(1, 6)}
    market, regime, portfolio = cycle_inputs(bars, peers=20)  # 5종목 모두 상대강도 상위 20%에 들도록
    cfg = EngineConfig(max_candidates=2, enabled_techniques=ONLY_CANSLIM)
    draft = draft_for(market, regime, portfolio, cfg)
    assert len(draft.candidates) == 2 and len(draft.ranked_out) == 3
    result = finalize_cycle(draft, *rules_decisions(draft), portfolio, cfg)
    assert sum(1 for e in result.events if e.kind == "screen_out") == 3


# ── 보유 종목 ─────────────────────────────────────────────────────────────────

def held_market(final_drop: float):
    closes = np.concatenate([10_000 * 1.003 ** np.arange(290), linear(10_000 * 1.003**289, 10_000 * 1.003**289 * (1 - final_drop), 10)])
    return cycle_inputs({CODE: make_bars(closes)})


def hold(portfolio, close, exit_rule="close_below_sma50", avg_ratio=0.9):
    portfolio.positions[CODE] = Position(CODE, "보유종목", 10, close * avg_ratio, date(2026, 10, 1), "vcp", int(close * 0.7),
                                         close * 0.1, exit_rule=exit_rule, chain_id="chain-1")


def test_exit_rule_creates_a_sell_intent_without_any_committee_decision():
    market, regime, portfolio = held_market(final_drop=0.12)
    hold(portfolio, float(market.stocks[CODE].close[-1]))
    draft = draft_for(market, regime, portfolio)
    assert draft.holdings[0].exit_signals and not draft.holdings[0].needs_review
    result = finalize_cycle(draft, {}, {}, portfolio, CFG)  # 위원회 결론이 하나도 없어도
    intent = result.intents[0]
    assert (intent.side, intent.source, intent.qty, intent.chain_id) == ("sell", "rule_exit", 10, "chain-1")


def test_exit_signals_follow_the_positions_exit_rule():
    market, _, portfolio = held_market(final_drop=0.12)
    feat = market.stocks[CODE]
    i = len(feat) - 1
    hold(portfolio, float(feat.close[-1]), exit_rule="close_below_low10")
    assert exit_signals(portfolio.positions[CODE], feat, i) == ["10일 저가를 이탈함"]
    hold(portfolio, float(feat.close[-1]), exit_rule=None)
    assert exit_signals(portfolio.positions[CODE], feat, i) == []


def test_healthy_holding_is_not_sent_for_review():
    market, regime, portfolio = held_market(final_drop=0.0)
    hold(portfolio, float(market.stocks[CODE].close[-1]))
    draft = draft_for(market, regime, portfolio)
    assert not draft.holdings[0].needs_review
    assert finalize_cycle(draft, *rules_decisions(draft), portfolio, CFG).intents == []


def test_losing_holding_is_reviewed_and_committee_sell_becomes_an_intent():
    market, regime, portfolio = held_market(final_drop=0.03)
    close = float(market.stocks[CODE].close[-1])
    hold(portfolio, close, exit_rule=None, avg_ratio=1.08)  # −7% 손실 중
    draft = draft_for(market, regime, portfolio)
    assert draft.holdings[0].needs_review
    sell = Decision(CODE, "보유종목", "holding", "SELL", "medium", thesis="주도력 약화", source="ai")
    result = finalize_cycle(draft, {}, {CODE: (sell, None)}, portfolio, CFG)
    assert [(it.side, it.source) for it in result.intents] == [("sell", "committee")]
    failed = Decision(CODE, "보유종목", "holding", "HOLD", "very_low", source="ai", status="review", status_detail="refusal")
    assert finalize_cycle(draft, {}, {CODE: (failed, None)}, portfolio, CFG).intents == []


# ── 사전 필터 ─────────────────────────────────────────────────────────────────

def sample_market(count: int = 24, bars: int = 520):
    provider = SampleProvider(end=END)
    codes = [f"{n:06d}" for n in range(100, 100 + count)]
    frames = {c: provider.daily_bars(c, bars) for c in codes}
    index = {"KOSPI": provider.daily_bars("KOSPI", bars), "KOSDAQ": provider.daily_bars("KOSDAQ", bars)}
    info = {c: StockInfo(c, f"샘플{c}", "KOSPI", f"업종{int(c) % 5}") for c in codes}
    return build_market(frames, index, info, source="sample")


def test_prefilter_never_drops_a_stock_that_would_pass_a_technique():
    market = sample_market(count=12)
    cfg = EngineConfig()
    prefilter = EntryPrefilter(market, cfg.params, cfg.enabled_techniques)
    passed_any = 0
    for code, feat in market.stocks.items():
        for i in range(260, len(feat), 3):
            if registry.best_plan(registry.evaluate_all(market, code, i, cfg.params)) is not None:
                passed_any += 1
                assert prefilter.passes(code, i), (code, i)
    assert passed_any > 20  # 검사가 실제로 의미 있는 표본을 봤는지


# ── 백테스트 ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def backtest():
    market = sample_market()
    return run_backtest(market, compute_regime(market), EngineConfig(), initial_cash=50_000_000), market


def test_backtest_runs_over_the_period_and_trades(backtest):
    result, market = backtest
    assert result.dates[0] == market.calendar[252] and result.dates[-1] == market.calendar[-1]
    assert len(result.equity) == len(result.dates) == len(result.benchmark)
    assert result.equity[0] == 50_000_000
    assert any(f.side == "buy" for f in result.fills) and any(f.side == "sell" for f in result.fills)
    assert min(result.equity) > 0


def test_backtest_is_deterministic(backtest):
    result, market = backtest
    again = run_backtest(market, compute_regime(market), EngineConfig(), initial_cash=50_000_000)
    assert again.equity == result.equity
    assert [(f.day, f.code, f.side, f.qty, f.price) for f in again.fills] == [(f.day, f.code, f.side, f.qty, f.price) for f in result.fills]


def test_backtest_never_fills_on_the_first_day_and_respects_limits(backtest):
    result, _ = backtest
    assert all(f.day > result.dates[0] for f in result.fills)  # T일 결정 → T+1일 체결
    assert max(result.exposure) <= 1.0 + 1e-9
    held: dict[str, int] = {}
    for f in result.fills:
        held[f.code] = held.get(f.code, 0) + (f.qty if f.side == "buy" else -f.qty)
        assert held[f.code] >= 0  # 없는 주식을 판 적이 없다
        assert len([c for c, q in held.items() if q > 0]) <= RiskLimits().max_positions


def test_backtest_output_serialises_with_summary_and_rejections(backtest):
    result, _ = backtest
    data = result.to_dict()
    assert {"curve", "monthly", "trades", "rejected", "summary"} <= set(data)
    assert {"cagr", "sharpe", "max_drawdown", "trades", "benchmark"} <= set(data["summary"])
    assert data["curve"][0]["drawdown"] == 0
    assert data["summary"]["trades"]["trades"] == sum(1 for f in result.fills if f.side == "sell")


def test_backtest_period_can_be_restricted(backtest):
    _, market = backtest
    start, end = market.calendar[400], market.calendar[450]
    result = run_backtest(market, compute_regime(market), EngineConfig(), start=start, end=end)
    assert (result.dates[0], result.dates[-1]) == (start, end)


# ── 지표 ─────────────────────────────────────────────────────────────────────

def test_cagr_doubling_in_one_trading_year_is_100_percent():
    values = list(np.linspace(100.0, 200.0, 253))
    assert metrics.cagr(values) == pytest.approx(1.0)


def test_max_drawdown_finds_peak_trough_and_recovery():
    dates = [date(2026, 1, d) for d in range(1, 8)]
    dd = metrics.max_drawdown(dates, [100, 120, 90, 96, 110, 121, 115])
    assert dd["pct"] == pytest.approx(-0.25)
    assert (dd["peak"], dd["trough"], dd["recovered"]) == ("2026-01-02", "2026-01-03", "2026-01-06")
    assert metrics.drawdown_series([100, 120, 90]) == pytest.approx([0, 0, -0.25])


def test_sharpe_and_sortino_signs_and_zero_cases():
    assert metrics.sharpe([0.01, 0.01, 0.01]) == 0.0  # 변동이 없으면 0으로 둔다
    up = [0.01, -0.005, 0.012, -0.004, 0.009]
    assert metrics.sharpe(up) > 0 and metrics.sortino(up) > metrics.sharpe(up)
    assert metrics.sharpe([-x for x in up]) < 0


def _sell(pnl: int, pct: float, reason="stop", technique="vcp", hold_days=3) -> Fill:
    return Fill(day=date(2026, 1, 5), code="1", name="n", side="sell", qty=1, price=1, fee=0, tax=0, reason=reason,
                technique=technique, pnl=pnl, pnl_pct=pct, hold_days=hold_days)


def test_trade_stats_win_rate_profit_factor_and_sample_warning():
    stats = metrics.trade_stats([_sell(300, 0.06, "target"), _sell(-100, -0.02), _sell(-100, -0.02), _sell(100, 0.02, "trail_stop", "turtle")])
    assert stats["trades"] == 4 and stats["win_rate"] == 0.5
    assert stats["profit_factor"] == pytest.approx(2.0)
    assert stats["payoff_ratio"] == pytest.approx(2.0)
    assert stats["by_reason"] == {"target": 1, "stop": 2, "trail_stop": 1}
    assert stats["by_technique"]["vcp"]["trades"] == 3
    assert not stats["enough_trades"]
    assert metrics.trade_stats([])["profit_factor"] is None


def test_monthly_returns_use_month_end_values():
    dates = [date(2026, 1, 30), date(2026, 2, 2), date(2026, 2, 27), date(2026, 3, 2)]
    rows = metrics.monthly_returns(dates, [100.0, 104.0, 110.0, 99.0])
    assert [(r["month"], round(r["ret"], 4)) for r in rows] == [(1, 0.0), (2, 0.1), (3, -0.1)]
