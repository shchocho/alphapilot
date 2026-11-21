"""바구니 순수 로직: 판단 규칙, 분기, 주기, 회차 금액·이월, 가상 체결, 과거 미리 보기."""

from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.market_rules import CostModel
from app.regime.regime import compute_regime
from app.sleeves import logic
from app.sleeves.config import PlanConfig, SleeveConfig, WatchItem, guess_kind
from tests.helpers import END, make_bars, make_market, trading_days

COSTS = CostModel()


def sleeve(**over) -> SleeveConfig:
    base = {"name": "중장기", "amount": 500_000, "items": [WatchItem(code="A00001", name="가")], "cadence": "monthly", "installments": 10}
    base.update(over)
    return SleeveConfig(**base)


# ── 계획 검증 ────────────────────────────────────────────────────────────


def test_plan_rejects_sleeves_larger_than_total():
    with pytest.raises(ValidationError, match="총 투입 금액"):
        PlanConfig(total=1_000_000, sleeves=[sleeve(amount=600_000), sleeve(name="ETF", amount=500_000)])


def test_plan_rejects_duplicate_codes_in_one_sleeve():
    with pytest.raises(ValidationError, match="같은 종목"):
        sleeve(items=[WatchItem(code="A00001"), WatchItem(code="A00001")])


def test_guess_kind_reads_etf_brand_prefix():
    assert guess_kind("KODEX 200") == "etf"
    assert guess_kind("TIGER 미국S&P500") == "etf"
    assert guess_kind("삼성전자") == "stock"


def test_base_amount_splits_installment_by_weight():
    cfg = sleeve(amount=600_000, installments=6, items=[WatchItem(code="A00001", weight=2), WatchItem(code="A00002", weight=1)])
    assert cfg.base_amount("A00001") == pytest.approx(100_000 * 2 / 3)
    assert cfg.base_amount("A00002") == pytest.approx(100_000 / 3)


# ── 판단 규칙 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("score", "holding", "allow", "expected"), [
    (0.30, False, True, "BUY_MORE"),
    (0.30, False, False, "BUY"),  # 신규 매수를 막는 국면에서는 더 모으기를 낮춘다
    (0.00, False, True, "BUY"),
    (-0.20, True, True, "WAIT"),
    (-0.50, False, True, "WAIT"),  # 보유가 없으면 줄일 것도 없다
    (-0.50, True, True, "TRIM"),
])
def test_rules_action_thresholds(score, holding, allow, expected):
    assert logic.rules_action(score, holding, allow) == expected


def test_branch_reason_near_threshold_or_losing_holding():
    assert logic.branch_reason(0.22, False, 0.0) is not None
    assert logic.branch_reason(0.10, False, 0.0) is None
    assert logic.branch_reason(0.10, True, -0.09) is not None
    assert logic.branch_reason(0.10, False, -0.20) is None  # 보유가 없으면 손실 분기도 없다


def test_resolve_follows_safer_answers_and_needs_conviction_for_riskier_ones():
    assert logic.resolve("BUY", "WAIT", "very_low")[0] == "WAIT"
    assert logic.resolve("WAIT", "BUY", "low")[0] == "WAIT"
    assert logic.resolve("WAIT", "BUY", "medium")[0] == "BUY"
    assert logic.resolve("TRIM", "TRIM", "low")[0] == "TRIM"


def test_is_due_by_cadence():
    mon, wed, next_mon = date(2026, 11, 16), date(2026, 11, 18), date(2026, 11, 23)
    assert logic.is_due("weekly", mon, None)
    assert not logic.is_due("weekly", wed, mon)
    assert logic.is_due("weekly", next_mon, wed)
    assert logic.is_due("daily", wed, mon)
    assert not logic.is_due("daily", mon, mon)
    assert not logic.is_due("monthly", date(2026, 11, 30), date(2026, 11, 2))
    assert logic.is_due("monthly", date(2026, 12, 1), date(2026, 11, 30))


# ── 회차 금액·이월 ────────────────────────────────────────────────────────


def test_plan_buy_carries_over_when_one_share_costs_more_than_installment():
    cfg = sleeve(amount=500_000, installments=10)  # 회차 금액 5만원
    book = logic.Book(cash=500_000)
    first = logic.plan_buy(book, cfg, "A00001", "BUY", 80_000, COSTS)
    assert first.qty == 0 and first.carry_after == pytest.approx(50_000)
    assert "다음 회차" in first.note
    book.carry["A00001"] = first.carry_after
    second = logic.plan_buy(book, cfg, "A00001", "BUY", 80_000, COSTS)
    assert second.qty == 1
    assert second.carry_after == pytest.approx(100_000 - logic.buy_unit(80_000, COSTS))


def test_plan_buy_never_spends_more_than_free_cash():
    cfg = sleeve(amount=500_000, installments=1)
    book = logic.Book(cash=120_000)
    plan = logic.plan_buy(book, cfg, "A00001", "BUY_MORE", 10_000, COSTS, reserved=50_000)
    assert plan.est_amount <= 70_000
    assert plan.qty == int(70_000 // logic.buy_unit(10_000, COSTS))


def test_plan_buy_alert_mode_only_suggests():
    cfg = sleeve(amount=500_000, installments=10)
    plan = logic.plan_buy(logic.Book(cash=0), cfg, "A00001", "BUY_MORE", 10_000, COSTS, track_carry=False)
    assert plan.qty == int(75_000 // logic.buy_unit(10_000, COSTS))  # 현금과 상관없이 권장 수량만
    assert logic.plan_buy(logic.Book(cash=0), cfg, "A00001", "WAIT", 10_000, COSTS).qty == 0


def test_plan_sell_trims_a_third_or_sells_all():
    book = logic.Book(cash=0, positions={"A00001": logic.Lot(10, 1000.0)})
    assert logic.plan_sell(book, "A00001", "TRIM") == 3
    assert logic.plan_sell(book, "A00001", "SELL") == 10
    assert logic.plan_sell(book, "A00001", "BUY") == 0
    assert logic.plan_sell(logic.Book(cash=0, positions={"A00001": logic.Lot(2, 1000.0)}), "A00001", "TRIM") == 1


# ── 가상 체결 ────────────────────────────────────────────────────────────


def test_fill_buy_shrinks_to_cash_when_open_gaps_up():
    book = logic.Book(cash=100_000)
    fill = logic.fill_buy(book, "A00001", "가", "stock", 10, 15_000, COSTS)
    assert fill is not None and fill.qty == 6
    assert book.cash == 100_000 - fill.amount - fill.fee >= 0
    assert book.positions["A00001"].qty == 6


def test_etf_sell_has_no_transaction_tax():
    book = logic.Book(cash=0, positions={"E00001": logic.Lot(10, 10_000.0, "ETF", "etf")})
    stock_book = logic.Book(cash=0, positions={"A00001": logic.Lot(10, 10_000.0)})
    etf = logic.fill_sell(book, "E00001", 10, 10_000, logic.costs_for("etf", COSTS))
    stock = logic.fill_sell(stock_book, "A00001", 10, 10_000, logic.costs_for("stock", COSTS))
    assert etf is not None and stock is not None
    assert etf.tax == 0 and stock.tax > 0
    assert "E00001" not in book.positions


# ── 과거 미리 보기 ──────────────────────────────────────────────────────


def _rising_market(n: int = 400):
    closes = 10_000 * (1.002 ** np.arange(n))
    return make_market({"A00001": make_bars(closes)})


def test_replay_dca_buys_every_month_and_tracks_contributions():
    market = _rising_market()
    regimes = compute_regime(market)
    start = trading_days(120)[0]
    cfg = sleeve(amount=600_000, installments=6, cadence="monthly")
    out = logic.replay(market, regimes, cfg, start, END, "dca", COSTS)
    months = len({(d.year, d.month) for d in out.dates})
    assert months - 1 <= out.runs <= months  # 달마다 한 번(마지막 날에는 다음 날이 없어 주문을 만들지 않는다)
    assert out.buys >= 5
    assert out.equity[-1] > 600_000  # 오르는 종목을 모았다
    assert out.summary(600_000)["return_pct"] > 0


def test_replay_never_uses_future_bars():
    market = _rising_market()
    regimes = compute_regime(market)
    days = trading_days(160)
    cut = days[100]
    cfg = sleeve(amount=600_000, installments=6, cadence="weekly")
    short = logic.replay(market, regimes, cfg, days[0], cut, "rules", COSTS)
    long = logic.replay(market, regimes, cfg, days[0], END, "rules", COSTS)
    # 끝 날짜를 뒤로 늘려도 그 전까지의 결과는 같다(뒤의 봉이 앞의 판단에 끼어들지 않는다)
    k = len(short.equity) - 1
    assert long.equity[:k] == pytest.approx(short.equity[:k], rel=1e-12)


def test_replay_rules_sells_a_falling_stock_dca_keeps_it():
    n = 400
    closes = np.concatenate([10_000 * (1.002 ** np.arange(300)), 10_000 * 1.002**299 * (0.985 ** np.arange(1, 101))])
    market = make_market({"A00001": make_bars(closes)})
    regimes = compute_regime(market)
    start = trading_days(n)[280]
    cfg = sleeve(amount=600_000, installments=6, cadence="weekly")
    rules = logic.replay(market, regimes, cfg, start, END, "rules", COSTS)
    dca = logic.replay(market, regimes, cfg, start, END, "dca", COSTS)
    assert dca.sells == 0
    assert rules.sells >= 1
    assert rules.equity[-1] > dca.equity[-1]
