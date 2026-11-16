"""리스크 한도. 모든 값은 설정에서 바꿀 수 있고, 범위를 벗어난 값은 거부한다.

기본값 출처: tradermonty(회로차단기 일 2%·주 5%·월 8%, heat 6%, 종목 10%, 업종 30%, 위험 8% 상한,
거래당 0.5% × 등급 배수), day-trader-skill-kr(현금 버퍼 10%, 비용/위험 0.30, 비용 차감 손익비 1.0).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

CONVICTION_MULTIPLIER: dict[str, float] = {
    "very_low": 0.5,
    "low": 0.75,
    "medium": 1.0,
    "high": 1.25,
    "very_high": 1.75,
}


class RiskLimits(BaseModel):
    # 계좌
    max_positions: int = Field(8, ge=1, le=30)
    max_position_pct: float = Field(0.10, gt=0, le=0.5)
    max_sector_pct: float = Field(0.30, gt=0, le=1.0)
    max_heat_pct: float = Field(0.06, gt=0, le=0.3)
    min_cash_pct: float = Field(0.10, ge=0, le=0.9)
    max_order_value_pct: float = Field(0.10, gt=0, le=0.5)
    max_orders_per_day: int = Field(20, ge=1, le=200)
    # 손실 회로차단기
    daily_loss_limit_pct: float = Field(0.02, gt=0, le=0.2)
    weekly_loss_limit_pct: float = Field(0.05, gt=0, le=0.3)
    monthly_loss_limit_pct: float = Field(0.08, gt=0, le=0.5)
    drawdown_reduce_pct: float = Field(0.05, gt=0, le=0.5)  # 사이즈 75%
    drawdown_half_pct: float = Field(0.10, gt=0, le=0.6)  # 사이즈 50%
    drawdown_block_pct: float = Field(0.15, gt=0, le=0.7)  # 신규 매수 중단
    drawdown_halt_pct: float = Field(0.20, gt=0, le=0.9)  # 엔진 정지
    consecutive_stops_pause: int = Field(2, ge=1, le=10)
    # 거래
    risk_per_trade_pct: float = Field(0.005, gt=0, le=0.05)
    min_buy_conviction: str = "low"
    max_stop_pct: float = Field(0.08, gt=0, le=0.3)
    max_cost_to_risk: float = Field(0.30, gt=0, le=1.0)
    min_reward_to_risk: float = Field(1.0, ge=0, le=10)
    # 유동성
    min_avg_value: int = Field(3_000_000_000, ge=0)  # 20일 평균 거래대금 하한(원)
    max_adv_pct: float = Field(0.01, gt=0, le=0.2)  # 주문 금액 ≤ 평균 거래대금의 1%
    # 승인 시 가격 재확인
    price_recheck_pct: float = Field(0.015, gt=0, le=0.1)

    @model_validator(mode="after")
    def _ordered_drawdown_steps(self) -> RiskLimits:
        steps = (self.drawdown_reduce_pct, self.drawdown_half_pct, self.drawdown_block_pct, self.drawdown_halt_pct)
        if list(steps) != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError("낙폭 단계는 축소 < 절반 < 신규 중단 < 엔진 정지 순서여야 합니다")
        if not (self.daily_loss_limit_pct <= self.weekly_loss_limit_pct <= self.monthly_loss_limit_pct):
            raise ValueError("손실 한도는 일 ≤ 주 ≤ 월 순서여야 합니다")
        if self.min_buy_conviction not in CONVICTION_MULTIPLIER:
            raise ValueError("min_buy_conviction 값이 잘못됐습니다")
        return self

    def is_looser_than(self, other: RiskLimits) -> list[str]:
        """other(이전 값)보다 느슨해진 항목 이름. 느슨하게 바꿀 때는 재인증을 요구한다."""
        higher_is_looser = (
            "max_positions", "max_position_pct", "max_sector_pct", "max_heat_pct", "max_order_value_pct",
            "max_orders_per_day", "daily_loss_limit_pct", "weekly_loss_limit_pct", "monthly_loss_limit_pct",
            "drawdown_reduce_pct", "drawdown_half_pct", "drawdown_block_pct", "drawdown_halt_pct",
            "consecutive_stops_pause", "risk_per_trade_pct", "max_stop_pct", "max_cost_to_risk", "max_adv_pct",
            "price_recheck_pct",
        )
        lower_is_looser = ("min_cash_pct", "min_reward_to_risk", "min_avg_value")
        loosened = [k for k in higher_is_looser if getattr(self, k) > getattr(other, k)]
        loosened += [k for k in lower_is_looser if getattr(self, k) < getattr(other, k)]
        order = list(CONVICTION_MULTIPLIER)
        if order.index(self.min_buy_conviction) < order.index(other.min_buy_conviction):
            loosened.append("min_buy_conviction")
        return loosened
