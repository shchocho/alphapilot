"""백테스트 성과 지표. 일별 자산 곡선과 거래 목록에서 계산한다."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

from app.core.models import Fill

TRADING_DAYS = 252
MIN_TRADES_FOR_STATS = 30  # 이보다 적으면 승률 같은 지표를 믿기 어렵다


def daily_returns(values: list[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1] > 0]


def cagr(values: list[float]) -> float:
    if len(values) < 2 or values[0] <= 0 or values[-1] <= 0:
        return 0.0
    years = (len(values) - 1) / TRADING_DAYS
    return (values[-1] / values[0]) ** (1 / years) - 1 if years > 0 else 0.0


def max_drawdown(dates: list[date], values: list[float]) -> dict[str, Any]:
    """최대 낙폭과 그 구간(고점일, 저점일, 회복일)."""
    worst, peak_i, trough_i, cur_peak = 0.0, 0, 0, 0
    for i, v in enumerate(values):
        if v > values[cur_peak]:
            cur_peak = i
        dd = v / values[cur_peak] - 1 if values[cur_peak] > 0 else 0.0
        if dd < worst:
            worst, peak_i, trough_i = dd, cur_peak, i
    recovered = next((i for i in range(trough_i, len(values)) if values[i] >= values[peak_i]), None) if worst < 0 else None
    return {
        "pct": worst,
        "peak": dates[peak_i].isoformat() if dates else None,
        "trough": dates[trough_i].isoformat() if dates else None,
        "recovered": dates[recovered].isoformat() if recovered is not None else None,
        "days_to_trough": trough_i - peak_i,
    }


def drawdown_series(values: list[float]) -> list[float]:
    out, peak = [], -math.inf
    for v in values:
        peak = max(peak, v)
        out.append(v / peak - 1 if peak > 0 else 0.0)
    return out


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))


def sharpe(returns: list[float], risk_free_annual: float = 0.0) -> float:
    sd = _std(returns)
    if sd == 0:
        return 0.0
    excess = sum(returns) / len(returns) - risk_free_annual / TRADING_DAYS
    return excess / sd * math.sqrt(TRADING_DAYS)


def sortino(returns: list[float], risk_free_annual: float = 0.0) -> float:
    if not returns:
        return 0.0
    target = risk_free_annual / TRADING_DAYS
    downside = math.sqrt(sum(min(0.0, r - target) ** 2 for r in returns) / len(returns))
    if downside == 0:
        return 0.0
    return (sum(returns) / len(returns) - target) / downside * math.sqrt(TRADING_DAYS)


def trade_stats(sells: list[Fill]) -> dict[str, Any]:
    pnls = [f.pnl or 0 for f in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    n = len(pnls)
    by_reason: dict[str, int] = defaultdict(int)
    by_technique: dict[str, dict[str, float]] = defaultdict(lambda: {"trades": 0, "pnl": 0, "wins": 0})
    for f in sells:
        by_reason[f.reason] += 1
        row = by_technique[f.technique or "기타"]
        row["trades"] += 1
        row["pnl"] += f.pnl or 0
        row["wins"] += 1 if (f.pnl or 0) > 0 else 0
    return {
        "trades": n,
        "win_rate": len(wins) / n if n else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win == 0 else float("inf")),
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "payoff_ratio": (sum(wins) / len(wins)) / (-sum(losses) / len(losses)) if wins and losses else None,
        "avg_hold_days": sum(f.hold_days or 0 for f in sells) / n if n else 0.0,
        "best_pct": max((f.pnl_pct or 0.0 for f in sells), default=0.0),
        "worst_pct": min((f.pnl_pct or 0.0 for f in sells), default=0.0),
        "by_reason": dict(by_reason),
        "by_technique": {k: dict(v) for k, v in by_technique.items()},
        "enough_trades": n >= MIN_TRADES_FOR_STATS,
    }


def monthly_returns(dates: list[date], values: list[float]) -> list[dict[str, Any]]:
    """월별 수익률. 각 달의 마지막 값 ÷ 전달 마지막 값 − 1."""
    out: list[dict[str, Any]] = []
    if not dates:
        return out
    month_end: dict[tuple[int, int], float] = {}
    for d, v in zip(dates, values, strict=True):
        month_end[(d.year, d.month)] = v
    prev = values[0]
    for (year, month), v in month_end.items():
        out.append({"year": year, "month": month, "ret": v / prev - 1 if prev > 0 else 0.0})
        prev = v
    return out


def summarize(dates: list[date], equity: list[float], benchmark: list[float], sells: list[Fill], exposure: list[float],
              *, risk_free_annual: float = 0.0) -> dict[str, Any]:
    rets = daily_returns(equity)
    bench_rets = daily_returns(benchmark)
    stats = trade_stats(sells)
    return {
        "total_return": equity[-1] / equity[0] - 1 if equity and equity[0] > 0 else 0.0,
        "cagr": cagr(equity),
        "volatility": _std(rets) * math.sqrt(TRADING_DAYS),
        "sharpe": sharpe(rets, risk_free_annual),
        "sortino": sortino(rets, risk_free_annual),
        "max_drawdown": max_drawdown(dates, equity),
        "avg_exposure": sum(exposure) / len(exposure) if exposure else 0.0,
        "benchmark": {
            "total_return": benchmark[-1] / benchmark[0] - 1 if benchmark and benchmark[0] > 0 else 0.0,
            "cagr": cagr(benchmark),
            "max_drawdown": max_drawdown(dates, benchmark)["pct"] if benchmark else 0.0,
            "sharpe": sharpe(bench_rets, risk_free_annual),
        },
        "trades": stats,
        "days": len(dates),
    }
