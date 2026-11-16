"""기법 임계값. 전부 설정값이다.

기본값은 공개 저장소(tradermonty/claude-trading-skills)의 코드 기본값과 고전 규칙에서 가져왔고,
그 저장소 스스로 "실증 검증 안 됨"이라 밝힌 시작값이다. KRX 데이터 백테스트로 다시 맞춰야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TrendTemplateParams:
    min_low_gain: float = 0.25  # 52주 저가 대비 +25% 이상
    max_high_gap: float = 0.25  # 52주 고가 대비 −25% 이내
    min_rs: float = 70.0
    min_pass: int = 6  # 7개 중 6개


@dataclass(frozen=True, slots=True)
class VcpParams:
    lookback: int = 120
    zigzag_atr_mult: float = 1.5
    max_contractions: int = 4
    min_first_depth: float = 0.10
    max_depth_ratio: float = 0.70  # 다음 수축 깊이 ≤ 이전 × 0.70
    max_dryup: float = 0.70  # 10봉/50일 거래량 비율
    pivot_buffer: float = 0.001  # 진입 = 피벗 × 1.001
    chase_limit: float = 0.02  # 추격 한도 = 피벗 × 1.02
    max_below_pivot: float = 0.08  # 피벗보다 8% 넘게 아래면 아직 멀다
    breakout_zone: float = 0.03  # 피벗 +3%까지 돌파 구간
    stop_buffer: float = 0.01  # 손절 = 수축 저점 × 0.99
    max_risk: float = 0.08
    reward_multiple: float = 2.0


@dataclass(frozen=True, slots=True)
class CanslimParams:
    near_high: float = 0.05  # N: 52주 고가 −5% 이내
    breakout_volume: float = 1.4  # N: 거래량 1.4배
    udvr_full: float = 2.0  # S: 상승일/하락일 거래량비
    min_rs: float = 80.0  # L
    pass_score: float = 70.0
    stop_pct: float = 0.07  # 오닐 7~8% 손절
    target_pct: float = 0.20  # 20% 익절 규칙
    max_gap_from_close: float = 0.03


@dataclass(frozen=True, slots=True)
class BurstParams:
    min_gain: float = 0.04
    min_volume: int = 100_000
    max_base_width: float = 0.15
    max_risk: float = 0.10
    pass_score: float = 60.0
    max_hold_days: int = 5
    max_gap_from_close: float = 0.03


@dataclass(frozen=True, slots=True)
class TurtleParams:
    stop_n: float = 2.0  # 손절 = 진입 − 2N
    max_gap_from_close: float = 0.03


@dataclass(frozen=True, slots=True)
class VolBreakoutParams:
    k: float = 0.5
    min_range_pct: float = 0.02
    max_range_pct: float = 0.12
    min_rs: float = 50.0
    chase_limit: float = 0.02


@dataclass(frozen=True, slots=True)
class ValueParams:
    cheap_percentile: float = 35.0  # 업종 안 PER·PBR 백분위가 이 값 이하면 저평가
    quality_percentile: float = 60.0  # 업종 안 ROE 백분위가 이 값 이상이면 우량
    min_peers: int = 4


@dataclass(frozen=True, slots=True)
class TechniqueParams:
    trend: TrendTemplateParams = field(default_factory=TrendTemplateParams)
    vcp: VcpParams = field(default_factory=VcpParams)
    canslim: CanslimParams = field(default_factory=CanslimParams)
    burst: BurstParams = field(default_factory=BurstParams)
    turtle: TurtleParams = field(default_factory=TurtleParams)
    volbreak: VolBreakoutParams = field(default_factory=VolBreakoutParams)
    value: ValueParams = field(default_factory=ValueParams)


DEFAULT_PARAMS = TechniqueParams()
