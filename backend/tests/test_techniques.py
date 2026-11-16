import numpy as np
import pytest

from app.core.market_rules import tick_size
from app.indicators.features import Fundamentals
from app.techniques import momentum, registry, trend, value
from app.techniques.params import DEFAULT_PARAMS as P
from tests.helpers import flat_bars, linear, make_bars, make_market, rising_index

CODE = "000001"


def last(market, code=CODE) -> int:
    return len(market.stocks[code]) - 1


# ── 트렌드 템플릿 ────────────────────────────────────────────────────────────

def test_trend_template_passes_for_steady_uptrend_leader():
    market = make_market({CODE: make_bars(10_000 * 1.003 ** np.arange(320))})
    result = trend.trend_template(market, CODE, last(market), P.trend)
    assert result.passed
    assert result.passed_count == 7
    assert result.score == pytest.approx(100.0)


def test_trend_template_fails_for_downtrend():
    market = make_market({CODE: make_bars(30_000 * 0.998 ** np.arange(320))})
    result = trend.trend_template(market, CODE, last(market), P.trend)
    assert not result.passed
    assert result.passed_count <= 2


def test_trend_template_needs_enough_history():
    market = make_market({CODE: make_bars(10_000 * 1.003 ** np.arange(150))})
    result = trend.trend_template(market, CODE, last(market), P.trend)
    assert result.state == "insufficient"
    assert not result.passed


def test_trend_template_allows_one_failed_rule():
    # 오르다가 최근에 50일선 아래로 살짝 내려온 경우: 7개 중 6개
    closes = np.concatenate([10_000 * 1.003 ** np.arange(300), linear(10_000 * 1.003**299, 10_000 * 1.003**299 * 0.93, 12)])
    market = make_market({CODE: make_bars(closes)})
    result = trend.trend_template(market, CODE, last(market), P.trend)
    failed = [c.key for c in result.checks if not c.passed]
    assert failed == ["above_50"]
    assert result.passed


# ── VCP ─────────────────────────────────────────────────────────────────────

def vcp_closes(depths=(0.15, 0.08, 0.04), final=19_500.0) -> np.ndarray:
    """상승 뒤 깊이가 depths인 수축이 차례로 나오는 종가."""
    parts = [linear(8_000, 20_000, 260)]
    peak = 20_000.0
    legs = [(10, 10), (8, 8), (6, 6)]
    for depth, (down, up) in zip(depths, legs, strict=True):
        trough = peak * (1 - depth)
        next_peak = peak * 0.99
        parts.append(linear(peak, trough, down))
        parts.append(linear(trough, next_peak, up))
        peak = next_peak
    closes = np.concatenate(parts)
    closes[-6:] = linear(closes[-7], final, 6)
    return closes


def vcp_volumes(n: int, dry: float = 0.4) -> np.ndarray:
    volumes = np.full(n, 1_000_000.0)
    volumes[-10:] = 1_000_000.0 * dry
    return volumes


def test_vcp_detects_tightening_contractions_and_plans_pivot_entry():
    closes = vcp_closes()
    market = make_market({CODE: make_bars(closes, volumes=vcp_volumes(len(closes)))})
    result = trend.vcp(market, CODE, last(market), P.vcp)
    assert result.passed, [(c.key, c.value, c.passed) for c in result.checks]
    assert result.state == "setup"
    plan = result.plan
    assert plan is not None and plan.entry_type == "trigger"
    assert plan.trigger > closes[-1]  # 아직 피벗 아래: 돌파해야 산다
    assert plan.chase_limit > plan.trigger
    assert plan.stop < plan.trigger
    assert plan.risk_pct <= P.vcp.max_risk
    assert plan.target == pytest.approx(plan.trigger + 2 * (plan.trigger - plan.stop), abs=tick_size(plan.target))
    for price in (plan.trigger, plan.stop, plan.chase_limit, plan.target):
        assert price % tick_size(price) == 0


def test_vcp_rejects_when_contractions_get_deeper():
    closes = vcp_closes(depths=(0.06, 0.10, 0.14))
    market = make_market({CODE: make_bars(closes, volumes=vcp_volumes(len(closes)))})
    result = trend.vcp(market, CODE, last(market), P.vcp)
    assert not result.passed
    assert result.plan is None


def test_vcp_rejects_when_volume_does_not_dry_up():
    closes = vcp_closes()
    market = make_market({CODE: make_bars(closes, volumes=vcp_volumes(len(closes), dry=1.3))})
    result = trend.vcp(market, CODE, last(market), P.vcp)
    dry = next(c for c in result.checks if c.key == "dryup")
    assert not dry.passed
    assert not result.passed


def test_vcp_switches_to_open_entry_once_price_is_above_pivot():
    closes = vcp_closes(final=20_000.0)  # 피벗(약 19,700) 위 +1.5%
    market = make_market({CODE: make_bars(closes, volumes=vcp_volumes(len(closes)))})
    result = trend.vcp(market, CODE, last(market), P.vcp)
    assert result.passed
    assert result.state == "actionable"
    assert result.plan.entry_type == "open"
    assert result.plan.chase_limit is not None


def test_vcp_marks_extended_and_gives_no_plan_far_above_pivot():
    closes = vcp_closes(final=21_500.0)  # 피벗 +9%
    market = make_market({CODE: make_bars(closes, volumes=vcp_volumes(len(closes)))})
    result = trend.vcp(market, CODE, last(market), P.vcp)
    assert result.state == "extended"
    assert result.plan is None
    assert not result.passed


def test_vcp_uses_only_past_bars():
    closes = vcp_closes()
    full = make_market({CODE: make_bars(closes, volumes=vcp_volumes(len(closes)))})
    extended = np.concatenate([closes, linear(closes[-1], closes[-1] * 1.2, 15)])
    longer = make_market({CODE: make_bars(extended, volumes=np.concatenate([vcp_volumes(len(closes)), np.full(15, 2e6)]))}, index=rising_index(len(extended)))
    i = last(full)
    assert trend.vcp(longer, CODE, i, P.vcp).plan.trigger == trend.vcp(full, CODE, i, P.vcp).plan.trigger


# ── CANSLIM 일봉 요소 ─────────────────────────────────────────────────────────

def canslim_bars(n: int = 300):
    steps = np.where(np.arange(n) % 2 == 0, 1.01, 0.997)
    closes = 10_000 * np.cumprod(steps)
    volumes = np.where(steps > 1, 1_500_000.0, 500_000.0)
    closes[-1] = closes[-2] * 1.02
    volumes[-1] = 3_000_000.0
    return make_bars(closes, volumes=volumes)


def test_canslim_passes_for_leader_breaking_out_on_volume():
    market = make_market({CODE: canslim_bars()})
    result = momentum.canslim_daily(market, CODE, last(market), P.canslim)
    assert result.passed, [(c.key, c.value, c.passed) for c in result.checks]
    plan = result.plan
    assert plan.entry_type == "open"
    close = market.stocks[CODE].close[-1]
    assert plan.stop == pytest.approx(close * 0.93, rel=0.01)
    assert plan.target == pytest.approx(close * 1.20, rel=0.01)


def test_canslim_blocks_buying_when_market_score_is_zero():
    n = 300
    falling = make_bars(np.concatenate([np.full(n - 30, 3000.0), linear(3000.0, 2500.0, 30)]), spread=0.003)
    market = make_market({CODE: canslim_bars(n)}, index=falling)
    result = momentum.canslim_daily(market, CODE, last(market), P.canslim)
    m = next(c for c in result.checks if c.key == "m_market")
    assert not m.passed
    assert not result.passed
    assert result.plan is None


def test_canslim_fails_far_below_52_week_high():
    closes = np.concatenate([10_000 * 1.004 ** np.arange(250), linear(10_000 * 1.004**249, 10_000 * 1.004**249 * 0.8, 50)])
    market = make_market({CODE: make_bars(closes)})
    result = momentum.canslim_daily(market, CODE, last(market), P.canslim)
    assert not result.passed


def test_market_m_score_bands():
    assert momentum.market_m_score(0.03) == 90
    assert momentum.market_m_score(0.0) == 70
    assert momentum.market_m_score(-0.01) == 40
    assert momentum.market_m_score(-0.04) == 20
    assert momentum.market_m_score(-0.06) == 0


# ── 모멘텀 버스트 ─────────────────────────────────────────────────────────────

def burst_bars(gain: float = 0.06, *, locked: bool = False, n: int = 120):
    base = flat_bars(n - 1)
    prev = float(base["close"].iloc[-1])
    closes = np.append(base["close"].to_numpy(), prev * (1 + gain))
    opens = np.append(base["open"].to_numpy(), prev * 1.005)
    highs = np.append(base["high"].to_numpy(), closes[-1] if locked else closes[-1] * 1.005)
    lows = np.append(base["low"].to_numpy(), prev * 1.002)
    volumes = np.append(base["volume"].to_numpy().astype(float), 3_000_000.0)
    return make_bars(closes, opens=opens, highs=highs, lows=lows, volumes=volumes)


def test_burst_passes_on_big_up_day_with_volume_from_tight_base():
    market = make_market({CODE: burst_bars()})
    result = momentum.momentum_burst(market, CODE, last(market), P.burst)
    assert result.passed, [(c.key, c.value, c.passed) for c in result.checks]
    assert result.score >= 80
    feat = market.stocks[CODE]
    assert result.plan.stop <= feat.low[-1]
    assert result.plan.max_hold_days == 5
    assert result.plan.trail_mult is None


def test_burst_ignores_small_gain():
    market = make_market({CODE: burst_bars(gain=0.02)})
    assert not momentum.momentum_burst(market, CODE, last(market), P.burst).passed


def test_burst_excludes_limit_up_locked_bar():
    market = make_market({CODE: burst_bars(gain=0.30, locked=True)})
    result = momentum.momentum_burst(market, CODE, last(market), P.burst)
    locked = next(c for c in result.checks if c.key == "not_locked")
    assert not locked.passed
    assert not result.passed


# ── 터틀 ─────────────────────────────────────────────────────────────────────

def test_turtle_enters_on_fresh_20_day_breakout_with_2n_stop():
    base = flat_bars(119)
    closes = np.append(base["close"].to_numpy(), 10_500.0)
    market = make_market({CODE: make_bars(closes)})
    i = last(market)
    result = momentum.turtle(market, CODE, i, P.turtle)
    assert result.passed
    feat = market.stocks[CODE]
    n = feat.f["atr20"][i]
    assert result.plan.stop == pytest.approx(10_500 - 2 * n, abs=tick_size(10_500))
    assert result.plan.exit_rule == "close_below_low10"


def test_turtle_does_not_repeat_signal_on_second_day_of_breakout():
    base = flat_bars(118)
    closes = np.concatenate([base["close"].to_numpy(), [10_500.0, 10_700.0]])
    market = make_market({CODE: make_bars(closes)})
    result = momentum.turtle(market, CODE, last(market), P.turtle)
    fresh = next(c for c in result.checks if c.key == "fresh")
    assert not fresh.passed
    assert not result.passed


def test_turtle_quiet_inside_range():
    market = make_market({CODE: flat_bars(120)})
    assert not momentum.turtle(market, CODE, last(market), P.turtle).passed


# ── 변동성 돌파 ───────────────────────────────────────────────────────────────

def test_volatility_breakout_plans_next_day_trigger_from_todays_range():
    closes = 10_000 * 1.004 ** np.arange(300)  # 상대강도 계산에 1년 치 봉이 필요하다
    highs = closes * 1.02
    lows = closes * 0.98
    market = make_market({CODE: make_bars(closes, highs=highs, lows=lows)})
    i = last(market)
    result = momentum.volatility_breakout(market, CODE, i, P.volbreak)
    assert result.passed
    plan = result.plan
    rng = highs[-1] - lows[-1]
    assert plan.entry_type == "vb"
    assert plan.vb_k == 0.5
    assert plan.vb_range == pytest.approx(rng)
    assert plan.reference_price == pytest.approx(closes[-1] + 0.5 * rng)
    assert plan.exit_on_next_open


def test_volatility_breakout_skips_stock_below_moving_averages():
    closes = 20_000 * 0.997 ** np.arange(200)
    market = make_market({CODE: make_bars(closes, highs=closes * 1.02, lows=closes * 0.98)})
    assert not momentum.volatility_breakout(market, CODE, last(market), P.volbreak).passed


def test_volatility_breakout_skips_when_range_is_too_small():
    closes = 10_000 * 1.004 ** np.arange(300)
    market = make_market({CODE: make_bars(closes, spread=0.002)})
    result = momentum.volatility_breakout(market, CODE, last(market), P.volbreak)
    assert not next(c for c in result.checks if c.key == "range").passed


# ── 가치 점검 ─────────────────────────────────────────────────────────────────

def value_market(target: Fundamentals):
    codes = [CODE, "V00001", "V00002", "V00003", "V00004"]
    bars = {c: flat_bars(120) for c in codes}
    funds = {
        CODE: target,
        "V00001": Fundamentals(per=18, pbr=2.0, roe=8, eps=500, bps=5_000),
        "V00002": Fundamentals(per=22, pbr=2.5, roe=10, eps=450, bps=4_000),
        "V00003": Fundamentals(per=30, pbr=3.0, roe=6, eps=300, bps=3_300),
        "V00004": Fundamentals(per=15, pbr=1.6, roe=12, eps=660, bps=6_200),
    }
    return make_market(bars, sectors={c: "반도체" for c in codes}, fundamentals=funds, peers=0)


def test_value_passes_for_cheap_and_profitable_within_sector():
    market = value_market(Fundamentals(per=7, pbr=0.8, roe=18, eps=1_400, bps=12_000))
    result = value.value_check(market, CODE, last(market), P.value)
    assert result.passed, [(c.key, c.value, c.passed) for c in result.checks]
    assert next(c for c in result.checks if c.key == "graham").passed


def test_value_fails_for_expensive_low_quality():
    market = value_market(Fundamentals(per=45, pbr=4.0, roe=3, eps=200, bps=2_500))
    assert not value.value_check(market, CODE, last(market), P.value).passed


def test_value_abstains_without_fundamentals():
    market = make_market({CODE: flat_bars(120)})
    result = value.value_check(market, CODE, last(market), P.value)
    assert result.state == "insufficient"


# ── 레지스트리 ───────────────────────────────────────────────────────────────

def test_evaluate_all_returns_every_technique():
    market = make_market({CODE: canslim_bars()})
    results = registry.evaluate_all(market, CODE, last(market))
    assert set(results) == set(registry.ALL_KEYS)


def test_best_plan_prefers_trend_technique_over_short_term_one():
    market = make_market({CODE: canslim_bars()})
    results = registry.evaluate_all(market, CODE, last(market))
    chosen = registry.best_plan(results)
    assert chosen is not None and chosen.key == momentum.CANSLIM_KEY


def test_best_plan_respects_enabled_list():
    market = make_market({CODE: canslim_bars()})
    results = registry.evaluate_all(market, CODE, last(market))
    assert registry.best_plan(results, enabled=(momentum.BURST_KEY,)) is None


def test_metas_cover_all_keys_with_rule_chips():
    metas = registry.metas()
    assert [m.key for m in metas] == list(registry.ALL_KEYS)
    assert all(m.rules and m.summary and m.origin for m in metas)
