from datetime import date

import pytest

from app.core import clock
from app.core.market_rules import (
    CostModel,
    price_limits,
    round_down_tick,
    round_up_tick,
    tick_size,
)


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (1, 1),
        (1_999, 1),
        (2_000, 5),
        (4_995, 5),
        (5_000, 10),
        (19_990, 10),
        (20_000, 50),
        (49_950, 50),
        (50_000, 100),
        (199_900, 100),
        (200_000, 500),
        (499_500, 500),
        (500_000, 1_000),
        (1_233_000, 1_000),
    ],
)
def test_tick_size_follows_2023_krx_brackets(price, expected):
    assert tick_size(price) == expected


def test_round_down_tick_snaps_to_the_bracket_grid():
    assert round_down_tick(70_149) == 70_100
    assert round_down_tick(4_999) == 4_995
    assert round_down_tick(208_700) == 208_500


def test_round_up_tick_crosses_bracket_boundaries_onto_a_valid_price():
    assert round_up_tick(4_996) == 5_000
    assert round_up_tick(199_950) == 200_000
    assert round_up_tick(70_100) == 70_100


def test_rounded_prices_are_always_valid_ticks():
    for raw in (1_234.5, 4_998.2, 19_994.9, 49_975.0, 199_999.0, 499_999.0, 765_432.1):
        for rounded in (round_down_tick(raw), round_up_tick(raw)):
            assert rounded % tick_size(rounded) == 0


def test_price_limits_are_thirty_percent_snapped_inward():
    upper, lower = price_limits(100_000)
    assert upper == 130_000
    assert lower == 70_000
    upper, lower = price_limits(10_150)
    assert upper == 13_190  # 13,195 → 10원 단위 내림
    assert lower == 7_110  # 7,105 → 10원 단위 올림


def test_buy_cost_has_commission_only():
    costs = CostModel(commission_rate=0.00015, sell_tax_rate=0.0020, slippage_rate=0.0)
    fee, tax = costs.fees("buy", 1_000_000)
    assert (fee, tax) == (150, 0)


def test_sell_cost_adds_transaction_tax():
    costs = CostModel(commission_rate=0.00015, sell_tax_rate=0.0020, slippage_rate=0.0)
    fee, tax = costs.fees("sell", 1_000_000)
    assert (fee, tax) == (150, 2_000)


def test_round_trip_cost_per_share_counts_both_sides():
    costs = CostModel(commission_rate=0.00015, sell_tax_rate=0.0020, slippage_rate=0.0005)
    per_share = costs.round_trip_per_share(100_000)
    # 수수료 15×2 + 세금 200 + 슬리피지 50×2
    assert per_share == pytest.approx(330.0)


def test_weekend_is_not_a_trading_day():
    assert not clock.is_trading_day(date(2026, 11, 14))  # 토요일
    assert not clock.is_trading_day(date(2026, 11, 15))  # 일요일
    assert clock.is_trading_day(date(2026, 11, 16))


def test_listed_2026_holidays_are_closed():
    assert not clock.is_trading_day(date(2026, 6, 3))  # 지방선거
    assert not clock.is_trading_day(date(2026, 7, 17))  # 제헌절
    assert not clock.is_trading_day(date(2026, 12, 31))  # 연말 휴장


def test_next_trading_day_skips_weekend_and_holidays():
    assert clock.next_trading_day(date(2026, 11, 13)) == date(2026, 11, 16)
    assert clock.next_trading_day(date(2026, 12, 30)) == date(2027, 1, 4)


def test_extra_holidays_can_be_injected():
    extra = frozenset({date(2026, 11, 16)})
    assert not clock.is_trading_day(date(2026, 11, 16), extra_holidays=extra)


def test_session_phase_by_kst_time():
    assert clock.session_phase(clock.kst(2026, 11, 16, 8, 0)) == "pre_open"
    assert clock.session_phase(clock.kst(2026, 11, 16, 9, 0)) == "regular"
    assert clock.session_phase(clock.kst(2026, 11, 16, 15, 25)) == "closing_auction"
    assert clock.session_phase(clock.kst(2026, 11, 16, 15, 31)) == "after_close"
    assert clock.session_phase(clock.kst(2026, 11, 15, 10, 0)) == "closed"
