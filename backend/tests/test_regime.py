import numpy as np
import pytest

from app.indicators.features import compute_features
from app.regime.regime import (
    compute_regime,
    cycle_states,
    distribution_counts,
    distribution_flags,
    distribution_level,
    exposure_from_score,
)
from tests.helpers import linear, make_bars, make_market


def index_from_returns(returns, volumes=None, start=3000.0):
    closes = start * np.cumprod(1 + np.asarray(returns, dtype=float))
    vols = np.asarray(volumes, dtype=float) if volumes is not None else np.full(len(closes), 1e8)
    return compute_features("KOSPI", make_bars(closes, volumes=vols, spread=0.002))


def test_distribution_day_needs_drop_and_higher_volume():
    idx = index_from_returns([0.0, -0.005, -0.005, 0.001, -0.001], volumes=[1e8, 2e8, 1e8, 3e8, 4e8])
    flags = distribution_flags(idx)
    # 1: 하락 + 거래량 증가 ✓ / 2: 하락이지만 거래량 감소 ✗ / 3: 상승 ✗ / 4: −0.1%는 기준(−0.2%) 미달 ✗
    assert list(flags) == [False, True, False, False, False]


def test_distribution_days_are_counted_in_25_15_5_session_windows():
    returns = [0.0] * 40
    volumes = [1e8] * 40
    for t in (12, 20, 30, 38):  # 마지막 날(39) 기준 나이 27, 19, 9, 1
        returns[t] = -0.004
        volumes[t] = 2e8
    idx = index_from_returns(returns, volumes)
    counts = distribution_counts(idx, 39, distribution_flags(idx))
    assert counts == (3, 2, 1)


def test_distribution_day_expires_after_five_percent_recovery():
    returns = [0.0] * 30
    volumes = [1e8] * 30
    returns[10], volumes[10] = -0.004, 2e8
    returns[15] = 0.06  # 분산일 종가 대비 +5% 넘게 회복
    idx = index_from_returns(returns, volumes)
    flags = distribution_flags(idx)
    assert distribution_counts(idx, 14, flags) == (1, 1, 1)
    assert distribution_counts(idx, 29, flags) == (0, 0, 0)


@pytest.mark.parametrize(
    ("counts", "level"),
    [((0, 0, 0), "normal"), ((3, 1, 0), "caution"), ((5, 2, 1), "high"), ((2, 2, 2), "high"),
     ((4, 3, 1), "high"), ((6, 3, 1), "severe"), ((4, 4, 1), "severe")],
)
def test_distribution_level_thresholds(counts, level):
    assert distribution_level(counts) == level


def test_cycle_goes_correction_rally_attempt_then_follow_through_day():
    #         상승 5일           조정 4일(−4.9%)             반등 1~3일           4일째 +1.5% 거래량 증가
    returns = [0.004] * 5 + [-0.012, -0.013, -0.012, -0.013] + [0.003, 0.002, 0.003] + [0.015] + [0.002] * 3
    volumes = [1e8] * 12 + [2e8] + [1e8] * 3
    states = cycle_states(index_from_returns(returns, volumes))
    assert states[4] == "uptrend"
    assert states[8] == "correction"
    assert states[9] == "rally_attempt"
    assert states[12] == "confirmed"


def test_follow_through_needs_volume_and_day_four_or_later():
    base = [0.004] * 5 + [-0.012, -0.013, -0.012, -0.013]
    early = cycle_states(index_from_returns(base + [0.003, 0.015, 0.002], [1e8] * 10 + [2e8, 1e8]))
    assert "confirmed" not in early  # 반등 2일째의 급등은 FTD가 아니다
    quiet = cycle_states(index_from_returns(base + [0.003, 0.002, 0.003, 0.015], [1e8] * 12 + [0.5e8]))
    assert quiet[-1] == "rally_attempt"  # 거래량이 줄면 FTD가 아니다


def test_undercutting_follow_through_day_low_returns_to_correction():
    returns = [0.004] * 5 + [-0.012, -0.013, -0.012, -0.013] + [0.003, 0.002, 0.003, 0.015] + [-0.03]
    volumes = [1e8] * 12 + [2e8] + [1e8]
    states = cycle_states(index_from_returns(returns, volumes))
    assert states[12] == "confirmed"
    assert states[13] == "correction"


def test_exposure_from_score_is_piecewise_linear():
    assert exposure_from_score(90) == 1.0
    assert exposure_from_score(65) == pytest.approx(0.75)
    assert exposure_from_score(50) == pytest.approx(0.50)
    assert exposure_from_score(30) == pytest.approx(0.25)
    assert exposure_from_score(0) == 0.0


def test_regime_is_bullish_when_index_and_breadth_are_strong():
    n = 320
    stocks = {f"S{k:05d}": make_bars(10_000 * 1.003 ** np.arange(n)) for k in range(6)}
    market = make_market(stocks, peers=0)
    state = compute_regime(market)[-1]
    assert state.label == "상승"
    assert state.allow_new_buys
    assert state.exposure_cap == pytest.approx(1.0)
    assert state.dist_level == "normal"
    assert not state.missing


def test_regime_blocks_new_buys_in_a_broad_downtrend():
    n = 320
    falling = 20_000 * 0.998 ** np.arange(n)
    stocks = {f"S{k:05d}": make_bars(falling * (1 + 0.01 * k)) for k in range(6)}
    index = make_bars(np.concatenate([np.full(n - 40, 3000.0), linear(3000.0, 2550.0, 40)]), spread=0.002)
    market = make_market(stocks, index=index, peers=0)
    state = compute_regime(market)[-1]
    assert state.label == "하락"
    assert not state.allow_new_buys
    assert state.exposure_cap <= 0.5


def test_severe_distribution_caps_exposure_at_half_even_if_trend_is_up():
    n = 320
    returns = np.full(n, 0.0025)
    volumes = np.full(n, 1e8)
    for t in range(n - 12, n, 2):  # 최근 12일 중 6일이 분산일
        returns[t] = -0.003
        volumes[t] = 2e8
    index = make_bars(3000.0 * np.cumprod(1 + returns), volumes=volumes, spread=0.002)
    stocks = {f"S{k:05d}": make_bars(10_000 * 1.003 ** np.arange(n)) for k in range(6)}
    state = compute_regime(make_market(stocks, index=index, peers=0))[-1]
    assert state.dist_level == "severe"
    assert state.exposure_cap <= 0.5


def test_regime_reports_missing_breadth_and_penalises_score():
    n = 150  # 200일선이 아직 없어 시장 폭을 계산할 수 없다
    market = make_market({"S00001": make_bars(10_000 * 1.003 ** np.arange(n))}, peers=0)
    state = compute_regime(market)[-1]
    assert "시장 폭" in state.missing
    full = compute_regime(make_market({"S00001": make_bars(10_000 * 1.003 ** np.arange(320))}, peers=0))[-1]
    assert state.score < full.score


def test_breadth_on_a_given_day_does_not_change_when_later_bars_arrive():
    n = 320
    stocks = {f"S{k:05d}": make_bars(10_000 * (1.002 + 0.0005 * k) ** np.arange(n)) for k in range(4)}
    full = make_market(stocks, peers=0)
    cut = make_market({c: b.iloc[:280] for c, b in stocks.items()}, index=full_index_slice(n, 280), peers=0)
    assert len(compute_regime(full)) == n
    assert full.breadth.above200_ema8[279] == pytest.approx(cut.breadth.above200_ema8[-1])
    assert full.breadth.uptrend_ratio[279] == pytest.approx(cut.breadth.uptrend_ratio[-1])


def full_index_slice(n: int, upto: int):
    from tests.helpers import rising_index

    return rising_index(n).iloc[:upto]
