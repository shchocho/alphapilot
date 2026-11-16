"""백테스트. 시뮬레이션과 같은 엔진 코어(prepare_cycle → 규칙 위원회 → finalize_cycle → execute_day)를 과거 구간에 돌린다.

- 판단 주체는 규칙 위원회(결정론)다. AI 판단은 과거 주가를 이미 알고 있을 수 있어 백테스트에 쓰지 않는다.
- T일 장 마감 뒤 결정하고 T+1일에 체결한다(같은 종가에 결정·체결하지 않는다).
- 수수료·세금·슬리피지를 반영한다.
- 한계: 유니버스가 현재 상장 종목 기준이라 상장폐지 종목이 빠져 있다(생존 편향). 결과가 실제보다 좋게 나올 수 있다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.backtest import metrics
from app.core import clock
from app.core.models import Fill, Intent, Portfolio
from app.engine.core import EngineConfig, EntryPrefilter, finalize_cycle, prepare_cycle, rules_decisions
from app.engine.sim import end_of_day, execute_day
from app.indicators.features import Market
from app.regime.regime import RegimeState

WARMUP_BARS = 252  # 1년 치 봉이 쌓인 뒤부터 매매(상대강도·52주 고저 계산)


# 사지 않은 후보의 단계: 리스크 거부(매수 판단 뒤), 사전 제외(심의 전), 순위 밖(하루 후보 수 초과)
REJECT_STAGE: dict[str, str] = {"gate_block": "리스크 거부", "precheck": "사전 제외", "screen_out": "순위 밖"}

@dataclass(slots=True)
class BacktestResult:
    start: date
    end: date
    initial_cash: int
    dates: list[date] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    benchmark: list[float] = field(default_factory=list)
    exposure: list[float] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)  # 탈락·거부·미체결 목록
    summary: dict[str, Any] = field(default_factory=dict)
    halted_on: date | None = None
    elapsed_sec: float = 0.0

    def to_dict(self, *, max_rejected: int = 300) -> dict[str, Any]:
        dd = metrics.drawdown_series(self.equity)
        return {
            "start": self.start.isoformat(), "end": self.end.isoformat(), "initial_cash": self.initial_cash,
            "curve": [
                {"d": d.isoformat(), "equity": round(e), "benchmark": round(b), "drawdown": round(x, 5), "exposure": round(p, 4)}
                for d, e, b, x, p in zip(self.dates, self.equity, self.benchmark, dd, self.exposure, strict=True)
            ],
            "monthly": metrics.monthly_returns(self.dates, self.equity),
            "trades": [
                {"day": f.day.isoformat(), "code": f.code, "name": f.name, "side": f.side, "qty": f.qty, "price": f.price,
                 "fee": f.fee, "tax": f.tax, "reason": f.reason, "technique": f.technique, "pnl": f.pnl,
                 "pnl_pct": round(f.pnl_pct, 5) if f.pnl_pct is not None else None, "hold_days": f.hold_days}
                for f in self.fills
            ],
            "rejected": self.rejected[-max_rejected:],
            "rejected_total": len(self.rejected),
            "summary": self.summary,
            "halted_on": self.halted_on.isoformat() if self.halted_on else None,
            "elapsed_sec": round(self.elapsed_sec, 2),
        }


def run_backtest(
    market: Market,
    regimes: list[RegimeState],
    cfg: EngineConfig,
    *,
    start: date | None = None,
    end: date | None = None,
    initial_cash: int = 10_000_000,
) -> BacktestResult:
    began = time.perf_counter()
    calendar = market.calendar
    first = WARMUP_BARS if len(calendar) > WARMUP_BARS + 5 else 0
    t0 = first if start is None else max(first, next((i for i, d in enumerate(calendar) if d >= start), len(calendar) - 1))
    t1 = len(calendar) - 1 if end is None else max(t0, max((i for i, d in enumerate(calendar) if d <= end), default=t0))

    portfolio = Portfolio(cash=initial_cash, peak_equity=float(initial_cash))
    prefilter = EntryPrefilter(market, cfg.params, cfg.enabled_techniques)
    kospi = market.indexes["KOSPI"]
    bench_base = float(kospi.close[t0])
    result = BacktestResult(start=calendar[t0], end=calendar[t1], initial_cash=initial_cash)
    history: list[tuple[date, float]] = []
    exits: list[tuple[date, str, float]] = []
    todays: list[Intent] = []
    last_price: dict[str, float] = {}

    for t in range(t0, t1 + 1):
        day = calendar[t]
        next_day = calendar[t + 1] if t + 1 < len(calendar) else clock.next_trading_day(day)
        bars = {}
        for code in set(portfolio.positions) | {it.code for it in todays}:
            feat = market.stocks.get(code)
            i = feat.index_of(day) if feat is not None else None
            if i is not None:
                bars[code] = feat.bar(i)
                last_price[code] = bars[code].close

        day_result = execute_day(day, portfolio, todays, bars, cfg.costs)
        end_of_day(day, portfolio, bars)
        result.fills.extend(day_result.fills)
        for fill in day_result.fills:
            if fill.side == "sell":
                exits.append((day, fill.reason, float(fill.pnl or 0)))
        for intent, why in day_result.skipped:
            result.rejected.append({"day": day.isoformat(), "code": intent.code, "name": intent.name, "stage": "미체결", "reason": why})

        equity = portfolio.equity(last_price)
        portfolio.peak_equity = max(portfolio.peak_equity, equity)
        result.dates.append(day)
        result.equity.append(equity)
        result.benchmark.append(initial_cash * float(kospi.close[t]) / bench_base)
        result.exposure.append(portfolio.exposure(last_price))

        draft = prepare_cycle(day, next_day, market, regimes[t], portfolio, cfg, equity_history=history,
                              recent_exits=exits[-10:], prefilter=prefilter, previous_day=calendar[t - 1] if t > 0 else None)
        history.append((day, equity))
        if draft.breaker.halt_engine and result.halted_on is None:
            result.halted_on = day
        entries, holds = rules_decisions(draft)
        cycle = finalize_cycle(draft, entries, holds, portfolio, cfg)
        for event in cycle.events:
            if event.kind in REJECT_STAGE:
                result.rejected.append({"day": day.isoformat(), "code": event.code, "name": event.name,
                                        "stage": REJECT_STAGE[event.kind], "reason": event.summary})
        todays = cycle.intents

    sells = [f for f in result.fills if f.side == "sell"]
    result.summary = metrics.summarize(result.dates, result.equity, result.benchmark, sells, result.exposure)
    result.summary["open_positions"] = len(portfolio.positions)
    result.summary["final_cash"] = portfolio.cash
    result.elapsed_sec = time.perf_counter() - began
    return result
