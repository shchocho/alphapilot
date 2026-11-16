from datetime import date

import pandas as pd
import pytest

from app.data.naver import parse_chart_xml
from app.data.provider import DataProviderError, clean_bars
from app.data.sample import SampleProvider
from app.data.store import BarStore, refresh_bars
from app.store.db import make_engine, make_session_factory

NAVER_XML = """<?xml version="1.0" encoding="EUC-KR" ?>
<protocol>
  <chartdata symbol="005930" name="삼성전자" count="3" timeframe="day" precision="0" origintime="19900103">
    <item data="20261111|197100|208500|196300|208000|16238236" />
    <item data="20261112|208500|214000|206000|206500|19721557" />
    <item data="20261113|214000|216000|205000|209000|12822005" />
  </chartdata>
</protocol>"""


def make_store() -> BarStore:
    return BarStore(make_session_factory(make_engine(None)))


def test_naver_xml_parses_name_and_ohlcv():
    name, bars = parse_chart_xml(NAVER_XML)
    assert name == "삼성전자"
    assert list(bars.index.strftime("%Y-%m-%d")) == ["2026-11-11", "2026-11-12", "2026-11-13"]
    last = bars.iloc[-1]
    assert (last.open, last.high, last.low, last.close, last.volume) == (214000, 216000, 205000, 209000, 12822005)


def test_naver_xml_without_items_gives_empty_frame():
    name, bars = parse_chart_xml('<protocol><chartdata symbol="X" name="없음" count="0"></chartdata></protocol>')
    assert name == "없음"
    assert bars.empty


def test_clean_bars_fills_halted_day_with_close_and_zero_volume():
    raw = pd.DataFrame(
        {"open": [100.0, 0.0], "high": [110.0, 0.0], "low": [95.0, 0.0], "close": [105.0, 105.0], "volume": [10, 7]},
        index=pd.to_datetime(["2026-11-12", "2026-11-13"]),
    )
    cleaned = clean_bars(raw)
    halted = cleaned.iloc[-1]
    assert (halted.open, halted.high, halted.low, halted.volume) == (105.0, 105.0, 105.0, 0)


def test_clean_bars_sorts_and_drops_duplicate_dates():
    raw = pd.DataFrame(
        {"open": [3.0, 1.0, 2.0], "high": [3.0, 1.0, 2.0], "low": [3.0, 1.0, 2.0], "close": [3.0, 1.0, 2.0], "volume": [1, 1, 1]},
        index=pd.to_datetime(["2026-11-13", "2026-11-12", "2026-11-13"]),
    )
    cleaned = clean_bars(raw)
    assert list(cleaned["close"]) == [1.0, 2.0]


def test_sample_provider_is_deterministic():
    a = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 300)
    b = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 300)
    pd.testing.assert_frame_equal(a, b)


def test_sample_provider_gives_valid_bars_ending_on_requested_day():
    bars = SampleProvider(end=date(2026, 11, 13)).daily_bars("000660", 250)
    assert len(bars) == 250
    assert bars.index[-1] == pd.Timestamp("2026-11-13")
    assert (bars["high"] >= bars[["open", "close"]].max(axis=1)).all()
    assert (bars["low"] <= bars[["open", "close"]].min(axis=1)).all()
    assert (bars["volume"] > 0).all()


def test_sample_provider_has_index_series():
    kospi = SampleProvider(end=date(2026, 11, 13)).daily_bars("KOSPI", 100)
    assert len(kospi) == 100
    assert kospi["close"].iloc[-1] > 0


def test_store_round_trips_bars():
    store = make_store()
    bars = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 50)
    store.replace("005930", bars)
    pd.testing.assert_frame_equal(store.load("005930"), bars, check_freq=False)


def test_load_many_returns_one_frame_per_code():
    store = make_store()
    provider = SampleProvider(end=date(2026, 11, 13))
    for code in ("005930", "000660"):
        store.replace(code, provider.daily_bars(code, 30))
    frames = store.load_many(["005930", "000660", "999999"])
    assert set(frames) == {"005930", "000660"}
    assert len(frames["000660"]) == 30


class _ScriptedProvider:
    """호출마다 미리 정한 봉을 돌려주는 가짜 공급자."""

    name = "scripted"

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.calls: list[tuple[str, int]] = []

    def daily_bars(self, code: str, count: int) -> pd.DataFrame:
        self.calls.append((code, count))
        if code not in self.frames:
            raise DataProviderError("없는 종목")
        return self.frames[code].tail(count)


def test_refresh_fetches_full_history_for_new_code():
    store = make_store()
    bars = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 120)
    provider = _ScriptedProvider({"005930": bars})
    report = refresh_bars(provider, store, ["005930"], full_history=100)
    assert report.updated == ["005930"]
    assert provider.calls == [("005930", 100)]
    assert len(store.load("005930")) == 100


def test_refresh_appends_only_new_bars():
    store = make_store()
    bars = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 120)
    store.replace("005930", bars.iloc[:-3])
    report = refresh_bars(_ScriptedProvider({"005930": bars}), store, ["005930"])
    assert report.updated == ["005930"]
    pd.testing.assert_frame_equal(store.load("005930"), bars, check_freq=False)


def test_refresh_refetches_everything_when_adjusted_prices_changed():
    store = make_store()
    bars = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 120)
    store.replace("005930", bars.iloc[:-1])
    split = bars.copy()
    split[["open", "high", "low", "close"]] = split[["open", "high", "low", "close"]] / 5  # 액면분할
    report = refresh_bars(_ScriptedProvider({"005930": split}), store, ["005930"])
    assert report.refetched == ["005930"]
    assert store.load("005930")["close"].iloc[0] == pytest.approx(split["close"].iloc[0])


def test_refresh_records_failures_without_stopping():
    store = make_store()
    bars = SampleProvider(end=date(2026, 11, 13)).daily_bars("005930", 40)
    report = refresh_bars(_ScriptedProvider({"005930": bars}), store, ["999999", "005930"])
    assert "999999" in report.failed
    assert report.updated == ["005930"]
    assert not report.ok
