"""국내 주식 시장 규칙: 호가단위, 가격제한폭, 거래 비용.

호가단위는 2023-01-25 개편 이후 코스피·코스닥 공통 표다(주식 기준, ETF·ETN·ELW는 범위 밖).
가격제한폭은 주문 사전 점검용 근사값이다. 실전에서는 키움 주식기본정보의 상·하한가를 우선한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Side = Literal["buy", "sell"]

_TICK_BRACKETS: tuple[tuple[int, int], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
)
_TOP_TICK = 1_000
PRICE_LIMIT_RATE = 0.30


def tick_size(price: float) -> int:
    """가격이 속한 구간의 호가단위(원)."""
    for upper, tick in _TICK_BRACKETS:
        if price < upper:
            return tick
    return _TOP_TICK


def round_down_tick(price: float) -> int:
    """호가단위에 맞춰 내림. 손절가·매도가처럼 낮아져야 안전한 값에 쓴다."""
    tick = tick_size(price)
    return int(math.floor(price / tick + 1e-9) * tick)


def round_up_tick(price: float) -> int:
    """호가단위에 맞춰 올림. 진입가처럼 높아져야 안전한 값에 쓴다.

    구간 경계(예: 4,996 → 5,000)를 넘어가도 경계값은 위 구간 호가의 배수라 유효하다.
    """
    tick = tick_size(price)
    return int(math.ceil(price / tick - 1e-9) * tick)


def price_limits(base_price: float) -> tuple[int, int]:
    """(상한가, 하한가). 기준가 ±30%를 호가단위 안쪽으로 맞춘다."""
    upper = round_down_tick(base_price * (1 + PRICE_LIMIT_RATE))
    lower = round_up_tick(base_price * (1 - PRICE_LIMIT_RATE))
    return upper, lower


def is_limit_up_locked(close: float, high: float, prev_close: float) -> bool:
    """상한가에 잠겨 마감한 봉인지. 이런 봉의 돌파 신호는 다음 날 살 수 없을 가능성이 크다."""
    if prev_close <= 0:
        return False
    upper, _ = price_limits(prev_close)
    return close >= upper and close >= high


@dataclass(frozen=True, slots=True)
class CostModel:
    """거래 비용. 비율은 소수(0.00015 = 0.015%)."""

    commission_rate: float = 0.00015
    sell_tax_rate: float = 0.0020
    slippage_rate: float = 0.0005

    def fees(self, side: Side, amount: float) -> tuple[int, int]:
        """(수수료, 세금) 원 단위. 세금은 매도에만 붙는다."""
        fee = int(round(amount * self.commission_rate))
        tax = int(round(amount * self.sell_tax_rate)) if side == "sell" else 0
        return fee, tax

    def round_trip_per_share(self, price: float) -> float:
        """한 주를 사고파는 데 드는 예상 비용(수수료 2회 + 매도세 + 슬리피지 2회)."""
        return price * (2 * self.commission_rate + self.sell_tax_rate + 2 * self.slippage_rate)

    def buy_fill_price(self, raw: float) -> int:
        """매수 체결가 추정: 슬리피지를 더해 호가단위로 올림."""
        return round_up_tick(raw * (1 + self.slippage_rate))

    def sell_fill_price(self, raw: float) -> int:
        """매도 체결가 추정: 슬리피지를 빼고 호가단위로 내림."""
        return max(1, round_down_tick(raw * (1 - self.slippage_rate)))
