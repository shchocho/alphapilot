"""시세 공급자 인터페이스와 봉 데이터 규약.

봉 DataFrame 규약: 인덱스는 날짜(DatetimeIndex, 오름차순, 중복 없음),
열은 open·high·low·close(실수)·volume(정수). 수정주가 기준.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]
INDEX_CODES = ("KOSPI", "KOSDAQ")


class DataProviderError(RuntimeError):
    pass


class DailyBarProvider(Protocol):
    name: str

    def daily_bars(self, code: str, count: int) -> pd.DataFrame:
        """최근 count개 일봉. 종목코드 6자리 또는 지수 이름(KOSPI·KOSDAQ)."""
        ...


def empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=BAR_COLUMNS, index=pd.DatetimeIndex([], name="date").as_unit("ns")).astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": "int64"}
    )


def clean_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """정렬·중복 제거·거래정지 봉 보정을 거친 규약 형태로 만든다.

    거래정지일에는 시가·고가·저가가 0으로 올 수 있다. 그런 봉은 종가로 채우고 거래량 0으로 둔다.
    """
    if frame.empty:
        return empty_bars()
    out = frame[BAR_COLUMNS].copy()
    out.index = pd.DatetimeIndex(pd.to_datetime(out.index)).normalize().as_unit("ns")
    out.index.name = "date"
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out[out["close"] > 0]
    halted = (out["open"] <= 0) | (out["high"] <= 0) | (out["low"] <= 0)
    if halted.any():
        for col in ("open", "high", "low"):
            out[col] = np.where(halted, out["close"], out[col])
        out["volume"] = np.where(halted, 0, out["volume"])
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out.astype({"open": float, "high": float, "low": float, "close": float, "volume": "int64"})
