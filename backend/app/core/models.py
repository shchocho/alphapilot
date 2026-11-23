"""도메인 모델. 엔진 코어가 쓰는 순수 데이터 구조로, DB나 HTTP를 모른다.

금액은 정수 원, 비율은 소수(0.01 = 1%), 날짜는 `datetime.date`(KST 거래일)다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

Side = Literal["buy", "sell"]
EntryType = Literal["open", "trigger", "vb"]
Action = Literal["BUY", "SELL", "HOLD"]
Conviction = Literal["very_low", "low", "medium", "high", "very_high"]
Env = Literal["sim", "mock", "live"]

CONVICTION_ORDER: tuple[Conviction, ...] = ("very_low", "low", "medium", "high", "very_high")
CONVICTION_LABEL: dict[str, str] = {
    "very_low": "매우 낮음",
    "low": "낮음",
    "medium": "보통",
    "high": "높음",
    "very_high": "매우 높음",
}


@dataclass(slots=True)
class StockInfo:
    code: str
    name: str
    market: str  # KOSPI | KOSDAQ
    sector: str


@dataclass(slots=True)
class DayBar:
    """하루 봉 + 그날 체결 재현에 필요한 값."""

    open: float
    high: float
    low: float
    close: float
    volume: float
    prev_close: float
    atr: float  # 그날 종가 기준 ATR(14). 추적 손절 갱신에 쓴다.


@dataclass(slots=True)
class Check:
    """기법 규칙 한 줄: 실제 값과 기준, 통과 여부."""

    key: str
    label: str
    value: float | str | None
    threshold: str
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EntryPlan:
    """기법이 제안하는 진입·청산 계획. 가격은 호가단위에 맞춘 정수 원."""

    entry_type: EntryType
    stop: int
    reference_price: float  # 수량 계산 기준이 되는 예상 진입가
    trigger: int | None = None  # entry_type == "trigger": 이 가격 이상에서 진입
    chase_limit: int | None = None  # 이 가격을 넘으면 따라 사지 않는다
    vb_k: float | None = None  # entry_type == "vb": 목표가 = 당일 시가 + k × 전일 범위
    vb_range: float | None = None
    target: int | None = None
    trail_mult: float | None = 2.0  # 추적 손절: 최고 종가 − trail_mult × ATR
    exit_on_next_open: bool = False
    max_hold_days: int | None = None
    exit_rule: str | None = None  # "close_below_sma50" | "close_below_low10"

    @property
    def risk_per_share(self) -> float:
        return max(0.0, self.reference_price - self.stop)

    @property
    def risk_pct(self) -> float:
        if self.reference_price <= 0:
            return 0.0
        return self.risk_per_share / self.reference_price

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TechniqueResult:
    key: str
    name: str
    passed: bool
    score: float  # 0~100
    checks: list[Check] = field(default_factory=list)
    state: str = "none"  # insufficient | none | setup | actionable | extended
    plan: EntryPlan | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "passed": self.passed,
            "score": round(self.score, 1),
            "state": self.state,
            "checks": [c.to_dict() for c in self.checks],
            "plan": self.plan.to_dict() if self.plan else None,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class Signal:
    """위원회 좌석 한 자리의 의견(결정론). 데이터가 부족하면 기권한다."""

    seat: str
    label: str
    value: float  # −1(강한 약세) ~ +1(강한 강세)
    confidence: float  # 0~1
    abstained: bool = False
    summary: str = ""
    components: list[dict[str, Any]] = field(default_factory=list)  # {name, points, max_points, detail}
    as_of: str = ""
    rule_version: str = "1"

    @property
    def stance(self) -> str:
        if self.abstained:
            return "abstain"
        if self.value >= 0.2:
            return "bullish"
        if self.value <= -0.2:
            return "bearish"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stance"] = self.stance
        data["value"] = round(self.value, 3)
        data["confidence"] = round(self.confidence, 3)
        return data


@dataclass(slots=True)
class Position:
    code: str
    name: str
    qty: int
    avg_price: float
    opened_on: date
    technique: str
    stop: int
    entry_risk: float  # 진입 시 1주당 위험(진입가 − 손절가)
    sector: str = ""
    target: int | None = None
    trail_mult: float | None = None
    highest_close: float = 0.0
    exit_on_next_open: bool = False
    max_hold_days: int | None = None
    exit_rule: str | None = None
    chain_id: str = ""
    days_held: int = 0  # 진입일 0, 이후 거래일마다 1씩 늘어난다

    def open_risk(self, price: float) -> float:
        """지금 가격에서 손절가까지 내려가면 줄어드는 금액."""
        return max(0.0, price - self.stop) * self.qty

    def unrealized(self, price: float) -> float:
        return (price - self.avg_price) * self.qty


@dataclass(slots=True)
class Portfolio:
    cash: int
    positions: dict[str, Position] = field(default_factory=dict)
    peak_equity: float = 0.0

    def equity(self, prices: dict[str, float]) -> float:
        total = float(self.cash)
        for code, pos in self.positions.items():
            total += pos.qty * prices.get(code, pos.avg_price)
        return total

    def exposure(self, prices: dict[str, float]) -> float:
        equity = self.equity(prices)
        if equity <= 0:
            return 0.0
        invested = sum(p.qty * prices.get(c, p.avg_price) for c, p in self.positions.items())
        return invested / equity


@dataclass(slots=True)
class Intent:
    """주문 계획 한 건. 승인·만료·체결 상태를 가진다."""

    id: str
    chain_id: str
    created_on: date
    trade_date: date
    code: str
    name: str
    side: Side
    qty: int
    entry_type: EntryType = "open"
    status: str = "approved"  # pending_approval | approved | rejected | expired | filled | skipped | notified
    source: str = "committee"  # committee | protective | rule_exit | manual | liquidate
    technique: str = ""
    reason: str = ""
    est_price: float = 0.0
    trigger: int | None = None
    chase_limit: int | None = None
    vb_k: float | None = None
    vb_range: float | None = None
    stop: int | None = None
    target: int | None = None
    trail_mult: float | None = None
    exit_on_next_open: bool = False
    max_hold_days: int | None = None
    exit_rule: str | None = None
    conviction: str | None = None
    sector: str = ""
    decision_id: str | None = None
    note: str = ""


@dataclass(slots=True)
class Fill:
    day: date
    code: str
    name: str
    side: Side
    qty: int
    price: int
    fee: int
    tax: int
    reason: str  # entry_open | entry_trigger | entry_vb | stop | trail_stop | target | next_open_exit | time_exit | rule_exit | committee_sell | liquidate | manual
    chain_id: str = ""
    intent_id: str | None = None
    technique: str = ""
    pnl: int | None = None  # 매도일 때 실현손익(비용 차감)
    pnl_pct: float | None = None
    hold_days: int | None = None

    @property
    def amount(self) -> int:
        return self.qty * self.price


@dataclass(slots=True)
class Decision:
    """위원회 최종 판단(AI 또는 규칙). 게이트를 통과해야 주문 계획이 된다."""

    code: str
    name: str
    kind: Literal["entry", "holding"]
    action: Action
    conviction: Conviction = "medium"
    size_fraction: float = 1.0  # 허용 수량 대비 사용할 비율(0~1). 게이트는 줄이기만 한다.
    stop: int | None = None  # 계획 손절보다 좁히는(높이는) 것만 허용
    thesis: str = ""
    key_risks: list[str] = field(default_factory=list)
    invalidation: str = ""
    dissent: str = ""
    source: Literal["ai", "rules"] = "rules"
    status: Literal["ok", "review"] = "ok"  # review = AI 응답 실패 등으로 보류 처리
    status_detail: str = ""
    votes: dict[str, int] = field(default_factory=dict)  # {"bullish": n, "bearish": n, "neutral": n, "abstain": n}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
