"""테스트용 봉·시장 만들기 도우미."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core import clock
from app.core.models import StockInfo
from app.data.provider import clean_bars
from app.indicators.features import Fundamentals, Market, build_market

END = date(2026, 11, 13)


def trading_days(count: int, end: date = END) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if clock.is_trading_day(cursor):
            days.append(cursor)
        cursor -= timedelta(days=1)
    return days[::-1]


def make_bars(
    closes,
    *,
    opens=None,
    highs=None,
    lows=None,
    volumes=None,
    spread: float = 0.005,
    end: date = END,
) -> pd.DataFrame:
    """종가 배열로 봉을 만든다. 시가는 전일 종가, 고가·저가는 ±spread가 기본."""
    c = np.asarray(closes, dtype=float)
    n = len(c)
    o = np.asarray(opens, dtype=float) if opens is not None else np.concatenate([[c[0]], c[:-1]])
    h = np.asarray(highs, dtype=float) if highs is not None else np.maximum(o, c) * (1 + spread)
    l = np.asarray(lows, dtype=float) if lows is not None else np.minimum(o, c) * (1 - spread)  # noqa: E741
    v = np.asarray(volumes, dtype=float) if volumes is not None else np.full(n, 1_000_000.0)
    frame = pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": v.astype("int64")},
        index=pd.DatetimeIndex(trading_days(n, end), name="date"),
    )
    return clean_bars(frame)


def linear(start: float, stop: float, n: int) -> np.ndarray:
    """start 다음 값부터 stop까지 n개(끝점 포함, 시작점 제외)."""
    return np.linspace(start, stop, n + 1)[1:]


def flat_bars(n: int, price: float = 10_000.0, wiggle: float = 0.003, drift: float = 0.0) -> pd.DataFrame:
    """횡보 봉. drift를 음수로 주면 서서히 내려가 어떤 진입 기법에도 걸리지 않는다."""
    t = np.arange(n)
    closes = price * (1 + drift) ** t * (1 + wiggle * np.sin(t * 1.3))
    return make_bars(closes)


def rising_index(n: int, daily: float = 0.001) -> pd.DataFrame:
    return make_bars(3000.0 * (1 + daily) ** np.arange(n), spread=0.003)


def make_market(
    bars: dict[str, pd.DataFrame],
    *,
    index: pd.DataFrame | None = None,
    sectors: dict[str, str] | None = None,
    fundamentals: dict[str, Fundamentals] | None = None,
    peers: int = 9,
    peer_drift: float = 0.0,
) -> Market:
    """대상 종목에 횡보하는 비교 종목(peers개)을 더해 시장을 만든다. 상대강도 백분위 계산용."""
    n = max(len(b) for b in bars.values())
    all_bars = dict(bars)
    for k in range(peers):
        all_bars[f"P{k:05d}"] = flat_bars(n, price=10_000.0 + 500 * k, drift=peer_drift)
    idx = index if index is not None else rising_index(n)
    info = {
        code: StockInfo(code, f"종목{code}", "KOSPI", (sectors or {}).get(code, "테스트"))
        for code in all_bars
    }
    return build_market(all_bars, {"KOSPI": idx, "KOSDAQ": idx}, info, fundamentals=fundamentals, source="test")
