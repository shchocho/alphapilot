"""합성(샘플) 일봉 공급자. 테스트와 네트워크가 없을 때 쓴다.

같은 (코드, 기준일)에는 항상 같은 데이터를 돌려준다. 시장 공통 요인(상승 → 조정 → 회복)에
종목별 베타와 고유 추세를 섞어, 추세 종목·횡보 종목·하락 종목이 고르게 나오게 한다.
실제 시세가 아니므로 화면에는 반드시 '샘플 데이터'라고 표시한다.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core import clock
from app.core.market_rules import round_down_tick
from app.data.provider import INDEX_CODES, clean_bars

_HISTORY_DAYS = 900


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def _trading_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if clock.is_trading_day(cursor):
            days.append(cursor)
        cursor -= timedelta(days=1)
    return days[::-1]


def _market_factor(n: int) -> np.ndarray:
    """시장 공통 일간 수익률: 상승 → 급한 조정 → 회복 → 완만한 상승이 반복된다."""
    rng = np.random.default_rng(_seed("market-factor"))
    drift = np.empty(n)
    pattern = [(160, 0.0009), (35, -0.0035), (25, 0.0025), (120, 0.0007), (45, -0.0015), (90, 0.0012)]
    i = 0
    k = 0
    while i < n:
        length, mu = pattern[k % len(pattern)]
        drift[i : i + length] = mu
        i += length
        k += 1
    return drift + rng.normal(0.0, 0.009, n)


class SampleProvider:
    name = "sample"

    def __init__(self, end: date | None = None) -> None:
        self._end = end or date(2026, 11, 13)
        self._days = _trading_days(self._end, _HISTORY_DAYS)
        self._market = _market_factor(_HISTORY_DAYS)

    def daily_bars(self, code: str, count: int) -> pd.DataFrame:
        frame = self._index_bars(code) if code in INDEX_CODES else self._stock_bars(code)
        return frame.tail(count)

    def _index_bars(self, code: str) -> pd.DataFrame:
        rng = np.random.default_rng(_seed(f"index-{code}"))
        n = _HISTORY_DAYS
        beta = 1.0 if code == "KOSPI" else 1.25
        rets = beta * self._market + rng.normal(0.0, 0.002, n)
        base = 3200.0 if code == "KOSPI" else 880.0
        close = base * np.exp(np.cumsum(rets))
        spread = np.abs(rng.normal(0.006, 0.002, n)) * close
        open_ = np.concatenate([[close[0]], close[:-1]]) * (1 + rng.normal(0.0, 0.002, n))
        high = np.maximum(open_, close) + spread * 0.5
        low = np.minimum(open_, close) - spread * 0.5
        # 하락일에 거래량이 늘도록 해 분산일이 생기게 한다.
        volume = (4e8 * (1 + 8 * np.clip(-rets, 0, None) * 10) * rng.lognormal(0, 0.18, n)).astype("int64")
        frame = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=pd.DatetimeIndex(self._days, name="date"),
        )
        return clean_bars(frame.round(2))

    def _stock_bars(self, code: str) -> pd.DataFrame:
        rng = np.random.default_rng(_seed(f"stock-{code}"))
        n = _HISTORY_DAYS
        beta = float(rng.uniform(0.6, 1.6))
        style = rng.choice(["leader", "steady", "laggard", "volatile"], p=[0.3, 0.3, 0.25, 0.15])
        own_drift = {"leader": 0.0011, "steady": 0.0003, "laggard": -0.0006, "volatile": 0.0002}[style]
        own_vol = {"leader": 0.016, "steady": 0.011, "laggard": 0.015, "volatile": 0.028}[style]
        rets = beta * self._market + own_drift + rng.normal(0.0, own_vol, n)
        # 가끔 큰 양봉(모멘텀 버스트)과 조용한 수축 구간을 넣는다.
        bursts = rng.random(n) < 0.012
        rets = np.where(bursts, np.abs(rets) + rng.uniform(0.04, 0.09, n), rets)
        quiet = (np.arange(n) % 97) > 80
        rets = np.where(quiet & ~bursts, rets * 0.35, rets)
        rets = np.clip(rets, -0.29, 0.29)

        start_price = float(np.exp(rng.uniform(np.log(4_000), np.log(400_000))))
        close = start_price * np.exp(np.cumsum(rets))
        prev = np.concatenate([[close[0]], close[:-1]])
        open_ = prev * (1 + rng.normal(0.0, own_vol * 0.3, n))
        day_range = np.abs(rng.normal(own_vol * 1.4, own_vol * 0.4, n)) * close
        high = np.maximum(open_, close) + day_range * rng.uniform(0.1, 0.6, n)
        low = np.minimum(open_, close) - day_range * rng.uniform(0.1, 0.6, n)
        base_volume = float(np.exp(rng.uniform(np.log(150_000), np.log(6_000_000))))
        volume = base_volume * rng.lognormal(0, 0.35, n) * (1 + 14 * np.abs(rets))
        volume = np.where(quiet & ~bursts, volume * 0.45, volume)

        frame = pd.DataFrame(
            {
                "open": [round_down_tick(max(x, 1)) for x in open_],
                "high": [round_down_tick(max(x, 1)) for x in high],
                "low": [round_down_tick(max(x, 1)) for x in low],
                "close": [round_down_tick(max(x, 1)) for x in close],
                "volume": volume.astype("int64"),
            },
            index=pd.DatetimeIndex(self._days, name="date"),
        )
        return clean_bars(frame)
