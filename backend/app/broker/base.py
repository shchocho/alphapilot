"""브로커 공통 인터페이스. 엔진은 이 인터페이스만 알고, 키움 세부 사항은 어댑터 안에 둔다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

OrderType = Literal["market", "limit"]
Side = Literal["buy", "sell"]


@dataclass(slots=True)
class BrokerPosition:
    code: str
    name: str
    qty: int
    sellable_qty: int
    avg_price: float
    last_price: float


@dataclass(slots=True)
class AccountSnapshot:
    cash: int  # 주문 가능 현금
    deposit: int  # 예수금
    total_equity: int  # 추정 예탁 자산
    positions: list[BrokerPosition] = field(default_factory=list)


@dataclass(slots=True)
class OrderRequest:
    code: str
    side: Side
    qty: int
    order_type: OrderType = "market"
    price: int | None = None  # 지정가일 때만


@dataclass(slots=True)
class OrderResult:
    ok: bool
    order_id: str = ""
    message: str = ""
    # 접수 여부를 알 수 없는 경우(시간 초과·연결 끊김·유량 초과). 다시 보내지 말고 미체결·체결 조회로 확인한다.
    ambiguous: bool = False


@dataclass(slots=True)
class BrokerOrder:
    order_id: str
    code: str
    name: str
    side: Side
    qty: int
    price: int
    remaining_qty: int
    filled_qty: int
    status: str
    time: str = ""
    original_order_id: str = ""


@dataclass(slots=True)
class BrokerFill:
    order_id: str
    code: str
    name: str
    side: Side
    qty: int
    price: int
    fee: int = 0
    tax: int = 0
    time: str = ""


@dataclass(slots=True)
class Quote:
    code: str
    price: int
    prev_close: int
    open: int
    high: int
    low: int
    volume: int | None
    upper_limit: int | None = None
    lower_limit: int | None = None


class Broker(Protocol):
    env: str

    async def account(self) -> AccountSnapshot: ...
    async def open_orders(self) -> list[BrokerOrder]: ...
    async def fills_today(self) -> list[BrokerFill]: ...
    async def place_order(self, request: OrderRequest) -> OrderResult: ...
    async def cancel_order(self, order: BrokerOrder) -> OrderResult: ...
    async def quote(self, code: str) -> Quote: ...
