from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.core.models import StockInfo
from app.data.sample import SampleProvider
from app.indicators import core as ind
from app.indicators.features import build_market, compute_features


def test_sma_is_plain_average_of_last_n():
    out = ind.sma(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    assert np.isnan(out[:2]).all()
    assert list(out[2:]) == [2.0, 3.0, 4.0]


def test_shift_moves_values_forward():
    out = ind.shift(np.array([1.0, 2.0, 3.0]), 1)
    assert np.isnan(out[0])
    assert list(out[1:]) == [1.0, 2.0]


def test_true_range_uses_previous_close_for_gaps():
    high = np.array([10.0, 12.0])
    low = np.array([9.0, 11.5])
    close = np.array([9.5, 11.8])
    tr = ind.true_range(high, low, close)
    assert tr[0] == pytest.approx(1.0)
    assert tr[1] == pytest.approx(12.0 - 9.5)  # 갭 상승: 고가 − 전일 종가


def test_atr_of_constant_range_equals_that_range():
    n = 40
    close = np.full(n, 100.0)
    out = ind.atr(close + 1, close - 1, close, 14)
    assert out[-1] == pytest.approx(2.0)


def test_rsi_is_100_when_price_only_rises_and_0_when_it_only_falls():
    up = ind.rsi(np.arange(1.0, 30.0), 2)
    down = ind.rsi(np.arange(30.0, 1.0, -1.0), 2)
    assert up[-1] == pytest.approx(100.0)
    assert down[-1] == pytest.approx(0.0)


def test_pct_change_over_k_bars():
    out = ind.pct_change(np.array([100.0, 110.0, 121.0]), 2)
    assert out[2] == pytest.approx(0.21)


def test_zigzag_confirms_turns_only_after_threshold_reversal():
    #        0    1    2    3    4    5    6
    high = np.array([10.0, 12.0, 15.0, 13.0, 11.0, 13.5, 14.0])
    low = np.array([9.0, 11.0, 14.0, 11.5, 10.0, 12.0, 13.0])
    thr = np.full(7, 3.0)
    pivots = ind.zigzag(high, low, thr, 0, 6)
    assert pivots[0] == (0, 9.0, "L")
    assert pivots[1] == (2, 15.0, "H")
    assert pivots[2] == (4, 10.0, "L")
    assert pivots[-1][2] == "H"  # 진행 중인 상승의 임시 고점


def _sample_bars(code: str, count: int = 400) -> pd.DataFrame:
    return SampleProvider(end=date(2026, 11, 13)).daily_bars(code, count)


def test_features_do_not_look_ahead():
    """앞부분만 잘라 계산한 값이 전체로 계산한 값과 같아야 한다."""
    bars = _sample_bars("005930")
    full = compute_features("005930", bars)
    cut = compute_features("005930", bars.iloc[:300])
    for key, values in cut.f.items():
        np.testing.assert_allclose(values, full.f[key][:300], rtol=1e-9, atol=1e-9, equal_nan=True, err_msg=key)


def test_donchian_high_excludes_today():
    bars = _sample_bars("005930")
    feat = compute_features("005930", bars)
    i = 250
    assert feat.f["don20_hi"][i] == pytest.approx(bars["high"].iloc[i - 20 : i].max())


def test_index_of_returns_none_for_missing_day():
    feat = compute_features("005930", _sample_bars("005930"))
    assert feat.index_of(date(2026, 11, 13)) == len(feat) - 1
    assert feat.index_of(date(2026, 11, 14)) is None
    assert feat.last_index_on_or_before(date(2026, 11, 15)) == len(feat) - 1


def _market(codes: list[str]):
    provider = SampleProvider(end=date(2026, 11, 13))
    bars = {c: provider.daily_bars(c, 500) for c in codes}
    index_bars = {"KOSPI": provider.daily_bars("KOSPI", 500), "KOSDAQ": provider.daily_bars("KOSDAQ", 500)}
    info = {c: StockInfo(c, f"종목{c}", "KOSPI", "테스트") for c in codes}
    return build_market(bars, index_bars, info, source="sample")


def test_rs_percentile_ranks_strongest_stock_highest():
    codes = [f"{n:06d}" for n in range(1, 31)]
    market = _market(codes)
    last_raw = {c: market.stocks[c].f["rs_raw"][-1] for c in codes}
    strongest = max(last_raw, key=last_raw.get)
    weakest = min(last_raw, key=last_raw.get)
    assert market.rs_pct[strongest][-1] == pytest.approx(100.0)
    assert market.rs_pct[weakest][-1] == pytest.approx(100.0 / 30)


def test_breadth_is_a_ratio_between_zero_and_one():
    market = _market([f"{n:06d}" for n in range(1, 21)])
    tail = market.breadth.above200_ema8[-50:]
    assert np.nanmin(tail) >= 0.0
    assert np.nanmax(tail) <= 1.0
    assert market.breadth.counted[-1] == 20


def test_market_calendar_follows_kospi_dates():
    market = _market(["000001"])
    assert market.last_day() == date(2026, 11, 13)
    assert market.cal_index(date(2026, 11, 13)) == len(market.calendar) - 1
    assert market.cal_index(date(2026, 11, 14)) is None
