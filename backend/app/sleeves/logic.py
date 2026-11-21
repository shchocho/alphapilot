"""바구니 운용의 순수 로직: 판단 규칙, 회차·이월 금액 계산, 가상 체결, 과거 미리 보기(기준선).

DB도 네트워크도 모른다. 실시간 심의(service.py)와 미리 보기(replay)가 같은 함수를 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Any, Literal

from app.backtest import metrics
from app.committee.seats import blend, build_seats, votes
from app.core.market_rules import CostModel
from app.core.models import CONVICTION_ORDER, Signal, TechniqueResult
from app.indicators.features import Market
from app.regime.regime import RegimeState
from app.sleeves.config import Cadence, SleeveConfig
from app.techniques import registry

Action = Literal["BUY_MORE", "BUY", "WAIT", "TRIM", "SELL"]
ACTIONS: tuple[Action, ...] = ("BUY_MORE", "BUY", "WAIT", "TRIM", "SELL")
ACTION_LABELS: dict[str, str] = {"BUY_MORE": "더 모으기", "BUY": "모으기", "WAIT": "쉬기", "TRIM": "줄이기", "SELL": "팔기"}
RISK_ORDER: dict[str, int] = {"SELL": 0, "TRIM": 1, "WAIT": 2, "BUY": 3, "BUY_MORE": 4}  # 클수록 위험을 늘린다
BUY_MULTIPLIER: dict[str, float] = {"BUY_MORE": 1.5, "BUY": 1.0}
TRIM_FRACTION = 1 / 3

MORE_AT = 0.25  # 좌석 종합이 이 이상이면 더 모으기
BUY_AT = -0.10  # 이 이상이면 모으기
TRIM_AT = -0.35  # 이 이하이고 보유 중이면 줄이기
BRANCH_MARGIN = 0.08  # 문턱에서 이만큼 안쪽이면 애매한 분기
BRANCH_LOSS = -0.08  # 보유 손실이 이 이하면 분기
ORDER_EXPIRY_DAYS = 5  # 가상 주문이 이만큼 거래일 동안 체결되지 못하면 만료(거래정지 등)


# ── 판단 ─────────────────────────────────────────────────────────────────


def allowed_actions(holding: bool) -> list[Action]:
    return list(ACTIONS) if holding else ["BUY_MORE", "BUY", "WAIT"]


def rules_action(score: float, holding: bool, allow_new_buys: bool) -> Action:
    if score >= MORE_AT:
        return "BUY_MORE" if allow_new_buys else "BUY"
    if score >= BUY_AT:
        return "BUY"
    if score > TRIM_AT or not holding:
        return "WAIT"
    return "TRIM"


def branch_reason(score: float, holding: bool, pnl_pct: float) -> str | None:
    """규칙 결론이 애매하면 그 이유. 아니면 None."""
    for threshold, name in ((MORE_AT, "더 모으기"), (BUY_AT, "모으기"), (TRIM_AT, "줄이기")):
        if abs(score - threshold) < BRANCH_MARGIN:
            return f"좌석 종합 {score:+.2f}이 {name} 문턱({threshold:+.2f})에 가깝습니다"
    if holding and pnl_pct <= BRANCH_LOSS:
        return f"보유 손실이 {pnl_pct * 100:.1f}%입니다"
    return None


def resolve(rules: Action, answer: Action, conviction: str) -> tuple[Action, str]:
    """분기 모드: 위험을 줄이는 답은 따르고, 늘리는 답은 확신이 보통 이상일 때만 따른다."""
    if answer == rules:
        return rules, "AI도 규칙과 같은 결론입니다"
    if RISK_ORDER[answer] < RISK_ORDER[rules]:
        return answer, f"위험을 줄이는 답이라 따릅니다({ACTION_LABELS[rules]} → {ACTION_LABELS[answer]})"
    if CONVICTION_ORDER.index(conviction) >= CONVICTION_ORDER.index("medium"):  # type: ignore[arg-type]
        return answer, f"위험을 늘리는 답이지만 확신이 '보통' 이상이라 따릅니다({ACTION_LABELS[rules]} → {ACTION_LABELS[answer]})"
    return rules, f"위험을 늘리는 답인데 확신이 낮아 규칙 결론({ACTION_LABELS[rules]})을 씁니다"


def is_due(cadence: Cadence, day: date, last_run: date | None) -> bool:
    """심의할 차례인지. 매주·매월은 그 주·그 달에 아직 심의하지 않았으면 차례다(첫 거래일을 놓쳐도 따라잡는다)."""
    if last_run is None:
        return True
    if day <= last_run:
        return False
    if cadence == "daily":
        return True
    if cadence == "weekly":
        return day.isocalendar()[:2] != last_run.isocalendar()[:2]
    return (day.year, day.month) != (last_run.year, last_run.month)


@dataclass(slots=True)
class Assessment:
    """한 종목의 그날 장 마감 기준 판단 재료."""

    code: str
    i: int
    close: float
    results: dict[str, TechniqueResult]
    seats: list[Signal]
    score: float
    votes: dict[str, int]


def assess(market: Market, code: str, day: date, regime: RegimeState) -> Assessment | None:
    feat = market.stocks.get(code)
    i = feat.index_of(day) if feat is not None else None
    if feat is None or i is None:
        return None
    results = registry.evaluate_all(market, code, i)
    seats = build_seats(market, code, i, results, regime)
    return Assessment(code, i, float(feat.close[i]), results, seats, blend(seats), votes(seats))


# ── 장부 ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Lot:
    qty: int
    avg: float
    name: str = ""
    kind: str = "stock"


@dataclass(slots=True)
class Book:
    cash: int
    positions: dict[str, Lot] = field(default_factory=dict)
    carry: dict[str, float] = field(default_factory=dict)  # 1주가 안 돼 다음 회차로 넘긴 금액
    installments_done: int = 0
    contributed: int = 0  # 넣은 돈(배정 금액 + 추가 − 회수)
    started_on: str | None = None
    last_run: str | None = None

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(lot.qty * prices.get(code, lot.avg) for code, lot in self.positions.items())

    def pnl_pct(self, code: str, price: float) -> float:
        lot = self.positions.get(code)
        return price / lot.avg - 1 if lot is not None and lot.avg > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Book:
        positions = {code: Lot(**lot) for code, lot in (data.get("positions") or {}).items()}
        return cls(cash=int(data.get("cash", 0)), positions=positions, carry={k: float(v) for k, v in (data.get("carry") or {}).items()},
                   installments_done=int(data.get("installments_done", 0)), contributed=int(data.get("contributed", 0)),
                   started_on=data.get("started_on"), last_run=data.get("last_run"))

    def copy(self) -> Book:
        return Book.from_dict(self.to_dict())


def costs_for(kind: str, base: CostModel) -> CostModel:
    """ETF는 매도 증권거래세가 없다."""
    return replace(base, sell_tax_rate=0.0) if kind == "etf" else base


def buy_unit(price: float, costs: CostModel) -> float:
    """1주를 사는 데 드는 예상 금액(슬리피지 반영 체결가 + 수수료)."""
    return costs.buy_fill_price(price) * (1 + costs.commission_rate)


@dataclass(slots=True)
class BuyPlan:
    qty: int
    est_amount: int
    carry_after: float
    note: str


def plan_buy(book: Book, cfg: SleeveConfig, code: str, action: Action, close: float, costs: CostModel, *,
             reserved: float = 0.0, track_carry: bool = True) -> BuyPlan:
    """이번 회차 매수 수량. 가상 운용은 이월 금액과 남은 현금까지 따지고, 알림만은 권장 수량만 낸다."""
    mult = BUY_MULTIPLIER.get(action, 0.0)
    base = cfg.base_amount(code)
    unit = buy_unit(close, costs)
    if mult <= 0 or unit <= 0:
        return BuyPlan(0, 0, book.carry.get(code, 0.0), "")
    want = base * mult
    if not track_carry:
        qty = int(want // unit)
        note = "" if qty else f"1주 값({unit:,.0f}원)이 이번 회차 금액({want:,.0f}원)보다 큽니다"
        return BuyPlan(qty, int(round(qty * unit)), 0.0, note)
    budget = book.carry.get(code, 0.0) + want
    available = max(0.0, book.cash - reserved)
    spend = min(budget, available)
    qty = int(spend // unit)
    cost = qty * unit
    carry_after = min(budget - cost, max(0.0, available - cost))
    if qty:
        note = ""
    elif available < unit:
        note = "남은 현금으로는 1주도 살 수 없습니다"
    else:
        note = f"1주 값({unit:,.0f}원)에 못 미쳐 {carry_after:,.0f}원을 다음 회차로 넘깁니다"
    return BuyPlan(qty, int(round(cost)), carry_after, note)


def plan_sell(book: Book, code: str, action: Action) -> int:
    lot = book.positions.get(code)
    if lot is None or lot.qty <= 0:
        return 0
    if action == "SELL":
        return lot.qty
    if action == "TRIM":
        return max(1, math.floor(lot.qty * TRIM_FRACTION))
    return 0


@dataclass(slots=True)
class Fill:
    code: str
    name: str
    side: Literal["buy", "sell"]
    qty: int
    price: int
    amount: int
    fee: int
    tax: int
    pnl: int | None = None


def fill_buy(book: Book, code: str, name: str, kind: str, qty: int, open_price: float, costs: CostModel) -> Fill | None:
    """시가에 산다. 시가가 올라 현금이 모자라면 살 수 있는 만큼만 산다. 1주도 못 사면 None."""
    price = costs.buy_fill_price(open_price)
    afford = int(book.cash // (price * (1 + costs.commission_rate))) if price > 0 else 0
    qty = min(qty, afford)
    if qty < 1:
        return None
    amount = price * qty
    fee, tax = costs.fees("buy", amount)
    book.cash -= amount + fee
    lot = book.positions.get(code)
    if lot is None:
        book.positions[code] = Lot(qty, float(price), name, kind)
    else:
        lot.avg = (lot.avg * lot.qty + price * qty) / (lot.qty + qty)
        lot.qty += qty
    return Fill(code, name, "buy", qty, price, amount, fee, tax)


def fill_sell(book: Book, code: str, qty: int, open_price: float, costs: CostModel) -> Fill | None:
    lot = book.positions.get(code)
    if lot is None or lot.qty < 1:
        return None
    qty = min(qty, lot.qty)
    price = costs.sell_fill_price(open_price)
    amount = price * qty
    fee, tax = costs.fees("sell", amount)
    book.cash += amount - fee - tax
    pnl = int(round((price - lot.avg) * qty - fee - tax))
    lot.qty -= qty
    if lot.qty == 0:
        del book.positions[code]
    return Fill(code, lot.name, "sell", qty, price, amount, fee, tax, pnl)


# ── 과거 미리 보기(기준선) ──────────────────────────────────────────────────

Policy = Literal["dca", "rules"]
POLICY_LABELS: dict[str, str] = {"dca": "단순 적립", "rules": "규칙만", "book": "실제 운용"}


@dataclass(slots=True)
class ReplayResult:
    policy: str
    dates: list[date] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    invested: list[float] = field(default_factory=list)  # 평가금액 중 주식 비중
    buys: int = 0
    sells: int = 0
    runs: int = 0
    book: Book | None = None

    def summary(self, contributed: float) -> dict[str, Any]:
        if not self.equity:
            return {"return_pct": 0.0, "mdd_pct": 0.0, "buys": 0, "sells": 0, "runs": 0, "invested_pct": 0.0, "end_equity": contributed}
        mdd = metrics.max_drawdown(self.dates, self.equity)
        return {
            "return_pct": round(self.equity[-1] / contributed - 1, 5) if contributed > 0 else 0.0,
            "mdd_pct": round(mdd["pct"], 5), "buys": self.buys, "sells": self.sells, "runs": self.runs,
            "invested_pct": round(self.invested[-1], 4), "end_equity": round(self.equity[-1]),
        }


@dataclass(slots=True)
class _Order:
    code: str
    side: Literal["buy", "sell"]
    qty: int
    made: int  # 만든 날의 달력 번호


def replay(market: Market, regimes: list[RegimeState], cfg: SleeveConfig, start: date, end: date, policy: Policy,
           costs: CostModel) -> ReplayResult:
    """과거 구간을 결정론으로 돌린다. T일 종가로 판단하고 T+1일 시가에 체결한다(미래 가격을 쓰지 않는다).

    dca: 매 회차 기본 금액만큼 사고 팔지 않는다. rules: 규칙 판단을 따른다.
    """
    result = ReplayResult(policy=policy)
    calendar = market.calendar
    t0 = next((t for t, d in enumerate(calendar) if d >= start), None)
    if t0 is None:
        return result
    book = Book(cash=cfg.amount, contributed=cfg.amount, started_on=calendar[t0].isoformat())
    pending: list[_Order] = []
    last_run: date | None = None
    for t in range(t0, len(calendar)):
        day = calendar[t]
        if day > end:
            break
        # 1) 앞선 회차의 주문을 오늘 시가에 체결
        still: list[_Order] = []
        for order in pending:
            feat = market.stocks.get(order.code)
            i = feat.index_of(day) if feat is not None else None
            if feat is None or i is None:
                if t - order.made < ORDER_EXPIRY_DAYS:
                    still.append(order)
                continue
            item_costs = costs_for(cfg.kind_of(order.code), costs)
            if order.side == "buy":
                name = market.info[order.code].name if order.code in market.info else order.code
                if fill_buy(book, order.code, name, cfg.kind_of(order.code), order.qty, float(feat.open[i]), item_costs):
                    result.buys += 1
            elif fill_sell(book, order.code, order.qty, float(feat.open[i]), item_costs):
                result.sells += 1
        pending = still
        # 2) 차례가 된 날 장 마감 판단 → 다음 거래일 주문
        if t + 1 < len(calendar) and calendar[t + 1] <= end and is_due(cfg.cadence, day, last_run):
            last_run = day
            result.runs += 1
            reserved = 0.0
            for item in cfg.items:
                a = assess(market, item.code, day, regimes[t]) if policy == "rules" else None
                feat = market.stocks.get(item.code)
                i = feat.index_of(day) if feat is not None else None
                if i is None or feat is None:
                    continue
                close = float(feat.close[i])
                holding = item.code in book.positions
                action: Action = "BUY" if a is None else rules_action(a.score, holding, regimes[t].allow_new_buys)
                item_costs = costs_for(item.kind, costs)
                if action in BUY_MULTIPLIER:
                    plan = plan_buy(book, cfg, item.code, action, close, item_costs, reserved=reserved)
                    book.carry[item.code] = plan.carry_after
                    if plan.qty:
                        reserved += plan.est_amount
                        pending.append(_Order(item.code, "buy", plan.qty, t))
                elif (qty := plan_sell(book, item.code, action)) > 0:
                    pending.append(_Order(item.code, "sell", qty, t))
            book.installments_done += 1
        # 3) 그날 종가 평가
        prices = {code: float(feat.close[j]) for code in {i.code for i in cfg.items} | set(book.positions)
                  if (feat := market.stocks.get(code)) is not None and (j := feat.last_index_on_or_before(day)) is not None}
        equity = book.equity(prices)
        result.dates.append(day)
        result.equity.append(equity)
        result.invested.append((equity - book.cash) / equity if equity > 0 else 0.0)
    result.book = book
    return result
