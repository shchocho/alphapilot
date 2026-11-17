"""엔진 설정(사용자가 화면에서 바꾸는 값). KV 저장소에 JSON으로 둔다."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.committee.llm import DEFAULT_MODEL, EFFORTS, SELECTABLE_MODELS
from app.core.clock import now_kst
from app.core.market_rules import CostModel
from app.risk.limits import RiskLimits
from app.store.db import KV
from app.techniques.registry import ENTRY_KEYS

AUTOMATION_LABELS: dict[int, str] = {0: "알림만", 1: "모두 승인", 2: "한도 안 자동", 3: "완전 자동"}
STATE_LABELS: dict[str, str] = {"running": "가동 중", "paused": "일시정지", "stopped": "정지"}
ENV_LABELS: dict[str, str] = {"sim": "시뮬레이션", "mock": "모의투자", "live": "실전"}


class EngineSettings(BaseModel):
    env: Literal["sim", "mock", "live"] = "sim"
    state: Literal["running", "paused", "stopped"] = "stopped"
    # 재시작·재접속 뒤에는 사용자가 확인할 때까지 모든 주문을 승인 대기로 돌린다(데드맨 스위치).
    resume_check_required: bool = False
    automation_level: int = Field(1, ge=0, le=3)
    auto_max_order_value: int = Field(1_000_000, ge=0, le=1_000_000_000)  # 2단계: 이 금액 이하 매수만 자동

    decider: Literal["ai", "rules", "hybrid"] = "ai"  # hybrid = 규칙이 결론, 애매한 분기만 AI에게 묻는다
    ai_model: str = DEFAULT_MODEL
    ai_depth: Literal["light", "standard", "deep"] = "standard"
    ai_effort: str = "medium"
    ai_daily_budget_usd: float = Field(5.0, ge=0, le=500)
    max_candidates: int = Field(8, ge=1, le=30)

    enabled_techniques: list[str] = Field(default_factory=lambda: list(ENTRY_KEYS))
    commission_rate: float = Field(0.00015, ge=0, le=0.01)
    sell_tax_rate: float = Field(0.0020, ge=0, le=0.01)
    slippage_rate: float = Field(0.0005, ge=0, le=0.02)
    sim_initial_cash: int = Field(30_000_000, ge=1_000_000, le=100_000_000_000)
    extra_holidays: list[str] = Field(default_factory=list)

    @field_validator("ai_model")
    @classmethod
    def _known_model(cls, value: str) -> str:
        if value not in SELECTABLE_MODELS:
            raise ValueError("선택할 수 없는 모델입니다")
        return value

    @field_validator("ai_effort")
    @classmethod
    def _known_effort(cls, value: str) -> str:
        if value not in EFFORTS:
            raise ValueError("effort 값이 잘못됐습니다")
        return value

    @field_validator("enabled_techniques")
    @classmethod
    def _known_techniques(cls, value: list[str]) -> list[str]:
        unknown = [k for k in value if k not in ENTRY_KEYS]
        if unknown:
            raise ValueError(f"알 수 없는 기법: {unknown}")
        return [k for k in ENTRY_KEYS if k in value]

    def cost_model(self) -> CostModel:
        return CostModel(self.commission_rate, self.sell_tax_rate, self.slippage_rate)


WHOLE = "(전체)"


def tolerant_load[M: BaseModel](model: type[M], raw: Any) -> tuple[M, list[str]]:
    """저장된 값을 모델로 읽는다. 맞지 않는 필드만 기본값으로 되돌리고, 그래도 안 되면 전체를 기본값으로 한다.

    코드가 바뀌어 예전에 저장한 값이 더는 허용되지 않을 때(없어진 모델 이름, 좁아진 범위) 서버가 멈추지 않게 하기 위해서다.
    없어진 필드는 모델이 무시하므로 여기서 따로 다루지 않는다.
    """
    if not isinstance(raw, dict):
        return model(), ([] if raw is None else [WHOLE])
    try:
        return model.model_validate(raw), []
    except ValidationError as exc:
        bad = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
    try:
        return model.model_validate({k: v for k, v in raw.items() if k not in bad}), bad or [WHOLE]
    except ValidationError:
        return model(), [WHOLE]


class KVStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def get(self, key: str, default: Any = None) -> Any:
        with self._sf() as s:
            row = s.get(KV, key)
        return json.loads(row.value) if row is not None else default

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        with self._sf() as s, s.begin():
            row = s.get(KV, key)
            stamp = now_kst().isoformat(timespec="seconds")
            if row is None:
                s.add(KV(key=key, value=payload, updated_at=stamp))
            else:
                row.value, row.updated_at = payload, stamp

    def load_settings(self) -> EngineSettings:
        return self.load_settings_checked()[0]

    def load_settings_checked(self) -> tuple[EngineSettings, list[str]]:
        """(설정, 기본값으로 되돌린 필드). 저장된 값이 지금 버전에서 맞지 않아도 엔진이 멈추지 않게 한다."""
        return tolerant_load(EngineSettings, self.get("engine_settings", {}))

    def save_settings(self, settings: EngineSettings) -> None:
        self.set("engine_settings", settings.model_dump())

    def load_limits(self) -> RiskLimits:
        return self.load_limits_checked()[0]

    def load_limits_checked(self) -> tuple[RiskLimits, list[str]]:
        return tolerant_load(RiskLimits, self.get("risk_limits", {}))

    def save_limits(self, limits: RiskLimits) -> None:
        self.set("risk_limits", limits.model_dump())
