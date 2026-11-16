"""기본 지표. 모든 함수는 과거 값만 사용한다(i번째 결과는 0..i 구간만으로 정해진다)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()
    return out


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """와일더 평활(RMA). ATR·RSI 계산에 쓴다."""
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy()


def shift(x: np.ndarray, k: int) -> np.ndarray:
    """k봉 전 값(k > 0). 앞쪽은 NaN."""
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:-k] if k > 0 else x
    return out


def rolling_max(x: np.ndarray, n: int, min_periods: int | None = None) -> np.ndarray:
    return pd.Series(x).rolling(n, min_periods=min_periods or n).max().to_numpy()


def rolling_min(x: np.ndarray, n: int, min_periods: int | None = None) -> np.ndarray:
    return pd.Series(x).rolling(n, min_periods=min_periods or n).min().to_numpy()


def rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n, min_periods=n).sum().to_numpy()


def pct_change(x: np.ndarray, k: int = 1) -> np.ndarray:
    prev = shift(x, k)
    with np.errstate(divide="ignore", invalid="ignore"):
        return x / prev - 1.0


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = shift(close, 1)
    ranges = np.vstack([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr = np.nanmax(ranges, axis=0)
    tr[0] = high[0] - low[0]
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    return wilder(true_range(high, low, close), n)


def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=np.nan)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain[0] = np.nan
    loss[0] = np.nan
    avg_gain = pd.Series(gain).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy()
    avg_loss = pd.Series(loss).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100.0 - 100.0 / (1.0 + rs)
    out = np.where(avg_loss == 0, np.where(avg_gain == 0, 50.0, 100.0), out)
    out[np.isnan(avg_gain)] = np.nan
    return out


def zigzag(
    high: np.ndarray, low: np.ndarray, threshold: np.ndarray, start: int, end: int
) -> list[tuple[int, float, str]]:
    """되돌림이 threshold(가격 단위) 이상일 때마다 전환점을 확정한다.

    반환: [(봉 번호, 가격, "H" | "L")]. 마지막 원소는 아직 확정되지 않은 진행 중 극점이다.
    end 시점까지의 값만 쓴다.
    """
    pivots: list[tuple[int, float, str]] = []
    direction = ""
    hi = lo = start
    for j in range(start, end + 1):
        thr = threshold[j]
        if np.isnan(thr) or thr <= 0:
            continue
        if not direction:
            if high[j] > high[hi]:
                hi = j
            if low[j] < low[lo]:
                lo = j
            if hi < j and high[hi] - low[j] >= thr:
                pivots.append((hi, float(high[hi]), "H"))
                direction, lo = "down", j
            elif lo < j and high[j] - low[lo] >= thr:
                pivots.append((lo, float(low[lo]), "L"))
                direction, hi = "up", j
        elif direction == "down":
            if low[j] < low[lo]:
                lo = j
            elif high[j] - low[lo] >= thr:
                pivots.append((lo, float(low[lo]), "L"))
                direction, hi = "up", j
        else:
            if high[j] > high[hi]:
                hi = j
            elif high[hi] - low[j] >= thr:
                pivots.append((hi, float(high[hi]), "H"))
                direction, lo = "down", j
    if direction == "down":
        pivots.append((lo, float(low[lo]), "L"))
    elif direction == "up":
        pivots.append((hi, float(high[hi]), "H"))
    return pivots
