"""종목별 특성(지표 열)과 시장 전체 묶음(Market).

특성은 전 기간에 대해 한 번 계산하고 봉 번호로 읽는다. 모든 열이 과거만 보는 이동 계산이라
"i번째 값은 i일 장 마감 시점에 알 수 있는 값"이다. 백테스트와 실시간이 같은 값을 읽는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.core.models import DayBar, StockInfo
from app.indicators import core as ind

TRADING_DAYS_YEAR = 252


@dataclass(slots=True)
class Fundamentals:
    """재무 요약(키움 주식기본정보 수준). 없으면 가치 좌석은 기권한다."""

    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    eps: float | None = None
    bps: float | None = None
    as_of: str = ""


@dataclass(slots=True)
class Features:
    code: str
    dates: np.ndarray  # datetime64[D]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    f: dict[str, np.ndarray]
    _pos: dict[date, int] = field(default_factory=dict, repr=False)

    def __len__(self) -> int:
        return len(self.dates)

    def index_of(self, day: date) -> int | None:
        """그 날짜의 봉 번호. 봉이 없으면(거래정지·상장 전) None."""
        return self._pos.get(day)

    def last_index_on_or_before(self, day: date) -> int | None:
        i = int(np.searchsorted(self.dates, np.datetime64(day), side="right")) - 1
        return i if i >= 0 else None

    def day(self, i: int) -> date:
        return self.dates[i].astype("datetime64[D]").astype(date)

    def bar(self, i: int) -> DayBar:
        prev_close = float(self.close[i - 1]) if i > 0 else float(self.close[i])
        atr = self.f["atr14"][i]
        return DayBar(
            open=float(self.open[i]), high=float(self.high[i]), low=float(self.low[i]),
            close=float(self.close[i]), volume=float(self.volume[i]), prev_close=prev_close,
            atr=float(atr) if not np.isnan(atr) else 0.0,
        )


def compute_features(code: str, bars: pd.DataFrame) -> Features:
    o = bars["open"].to_numpy(dtype=float)
    h = bars["high"].to_numpy(dtype=float)
    l = bars["low"].to_numpy(dtype=float)  # noqa: E741
    c = bars["close"].to_numpy(dtype=float)
    v = bars["volume"].to_numpy(dtype=float)
    dates = bars.index.to_numpy().astype("datetime64[D]")

    f: dict[str, np.ndarray] = {}
    f["sma20"] = ind.sma(c, 20)
    f["sma50"] = ind.sma(c, 50)
    f["sma150"] = ind.sma(c, 150)
    f["sma200"] = ind.sma(c, 200)
    f["sma200_22"] = ind.shift(f["sma200"], 22)
    f["ema50"] = ind.ema(c, 50)
    f["atr14"] = ind.atr(h, l, c, 14)
    f["atr20"] = ind.atr(h, l, c, 20)
    f["hi252"] = ind.rolling_max(h, TRADING_DAYS_YEAR, min_periods=120)
    f["lo252"] = ind.rolling_min(l, TRADING_DAYS_YEAR, min_periods=120)
    f["vol10"] = ind.sma(v, 10)
    f["vol50"] = ind.sma(v, 50)
    f["value20"] = ind.sma(c * v, 20)
    # 돌파 기준선은 "오늘을 뺀" 직전 N일 고가·저가다.
    f["don20_hi"] = ind.shift(ind.rolling_max(h, 20), 1)
    f["don55_hi"] = ind.shift(ind.rolling_max(h, 55), 1)
    f["lo10"] = ind.shift(ind.rolling_min(l, 10), 1)
    f["lo20"] = ind.shift(ind.rolling_min(l, 20), 1)
    f["hi10_prev"] = ind.shift(ind.rolling_max(h, 10), 1)
    f["lo10_prev"] = f["lo10"]
    f["rsi2"] = ind.rsi(c, 2)
    f["ret1"] = ind.pct_change(c, 1)
    f["ret3"] = ind.pct_change(c, 3)
    f["roc20"] = ind.pct_change(c, 20)
    f["roc63"] = ind.pct_change(c, 63)
    f["roc126"] = ind.pct_change(c, 126)
    f["roc189"] = ind.pct_change(c, 189)
    f["roc252"] = ind.pct_change(c, 252)
    # 상대강도 원점수: 최근 분기에 가중치를 더 준다(IBD 방식의 근사).
    f["rs_raw"] = 0.4 * f["roc63"] + 0.2 * f["roc126"] + 0.2 * f["roc189"] + 0.2 * f["roc252"]
    # 12-1 모멘텀: 최근 1개월을 뺀 11개월 수익률
    with np.errstate(divide="ignore", invalid="ignore"):
        f["mom_12_1"] = ind.shift(c, 21) / ind.shift(c, 252) - 1.0
    up_volume = np.where(f["ret1"] > 0, v, 0.0)
    down_volume = np.where(f["ret1"] < 0, v, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        f["udvr60"] = ind.rolling_sum(up_volume, 60) / ind.rolling_sum(down_volume, 60)
        f["close_pos"] = np.where(h > l, (c - l) / (h - l), 0.5)
    f["prev_range"] = ind.shift(h - l, 1)
    f["range"] = h - l

    features = Features(code=code, dates=dates, open=o, high=h, low=l, close=c, volume=v, f=f)
    features._pos = {d.astype(date): i for i, d in enumerate(dates)}
    return features


@dataclass(slots=True)
class Breadth:
    """시장 폭. 달력(지수 날짜)에 맞춘 배열."""

    above200_ema8: np.ndarray  # 200일선 위 종목 비율(0~1)의 8일 EMA
    uptrend_ratio: np.ndarray  # 상승 추세 종목 비율(0~1)
    counted: np.ndarray  # 그날 계산에 들어간 종목 수


@dataclass(slots=True)
class Market:
    stocks: dict[str, Features]
    indexes: dict[str, Features]
    info: dict[str, StockInfo]
    calendar: list[date]
    rs_pct: dict[str, np.ndarray]
    breadth: Breadth
    fundamentals: dict[str, Fundamentals] = field(default_factory=dict)
    source: str = ""
    _cal_pos: dict[date, int] = field(default_factory=dict, repr=False)

    def cal_index(self, day: date) -> int | None:
        return self._cal_pos.get(day)

    def index_for(self, code: str) -> Features:
        market = self.info[code].market if code in self.info else "KOSPI"
        return self.indexes.get(market) or self.indexes["KOSPI"]

    def last_day(self) -> date:
        return self.calendar[-1]

    def prices_on(self, day: date) -> dict[str, float]:
        """그날(또는 그 이전 마지막 거래일) 종가."""
        out: dict[str, float] = {}
        for code, feat in self.stocks.items():
            i = feat.last_index_on_or_before(day)
            if i is not None:
                out[code] = float(feat.close[i])
        return out


def _wide(stocks: dict[str, Features], key: str, calendar_index: pd.DatetimeIndex) -> pd.DataFrame:
    series = {
        code: pd.Series(feat.f[key] if key in feat.f else getattr(feat, key), index=pd.DatetimeIndex(feat.dates))
        for code, feat in stocks.items()
    }
    return pd.DataFrame(series).reindex(calendar_index)


def build_market(
    bars: dict[str, pd.DataFrame],
    index_bars: dict[str, pd.DataFrame],
    info: dict[str, StockInfo],
    *,
    fundamentals: dict[str, Fundamentals] | None = None,
    source: str = "",
    min_bars: int = 60,
) -> Market:
    stocks = {code: compute_features(code, frame) for code, frame in bars.items() if len(frame) >= min_bars}
    indexes = {code: compute_features(code, frame) for code, frame in index_bars.items() if len(frame) >= min_bars}
    if "KOSPI" not in indexes:
        raise ValueError("KOSPI 지수 봉이 필요합니다")
    calendar_np = indexes["KOSPI"].dates
    calendar = [d.astype(date) for d in calendar_np]
    cal_index = pd.DatetimeIndex(calendar_np)

    rs_pct: dict[str, np.ndarray] = {}
    if stocks:
        raw = _wide(stocks, "rs_raw", cal_index)
        ranked = raw.rank(axis=1, pct=True) * 100.0
        for code, feat in stocks.items():
            rs_pct[code] = ranked[code].reindex(pd.DatetimeIndex(feat.dates)).to_numpy()

        close = _wide(stocks, "close", cal_index)
        sma20 = _wide(stocks, "sma20", cal_index)
        sma50 = _wide(stocks, "sma50", cal_index)
        sma200 = _wide(stocks, "sma200", cal_index)
        lo252 = _wide(stocks, "lo252", cal_index)
        roc20 = _wide(stocks, "roc20", cal_index)
        valid = sma200.notna() & close.notna()
        counted = valid.sum(axis=1).to_numpy()
        above = ((close > sma200) & valid).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)
        uptrend = (
            (close > sma20) & (close > sma200) & (sma50 > sma200) & (close >= lo252 * 1.30) & (roc20 > 0) & valid
        ).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)
        breadth = Breadth(
            above200_ema8=above.ewm(span=8, adjust=False, min_periods=1).mean().to_numpy(),
            uptrend_ratio=uptrend.to_numpy(),
            counted=counted,
        )
    else:
        nan = np.full(len(calendar), np.nan)
        breadth = Breadth(above200_ema8=nan, uptrend_ratio=nan.copy(), counted=np.zeros(len(calendar)))

    market = Market(
        stocks=stocks, indexes=indexes, info=info, calendar=calendar, rs_pct=rs_pct, breadth=breadth,
        fundamentals=fundamentals or {}, source=source,
    )
    market._cal_pos = {d: i for i, d in enumerate(calendar)}
    return market
