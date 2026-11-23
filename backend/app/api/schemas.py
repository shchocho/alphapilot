"""API 요청 본문 모델. 길이·범위 제한으로 잘못된 입력을 라우트에 닿기 전에 막는다."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.sleeves.config import PlanConfig
from app.techniques.registry import ENTRY_KEYS

# 경로 매개변수 정규식
STOCK_CODE = r"^\d{6}$"
RECORD_ID = r"^[0-9A-Za-z\-]{3,40}$"  # 판단·주문 계획·판단 사슬 번호
DAY = r"^\d{4}-\d{2}-\d{2}$"


class SetupBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    setup_token: str = Field("", max_length=256)


class CodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=16)  # 인증 앱 6자리 또는 복구 코드(xxxxx-xxxxx)


class PasswordBody(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


class BrokerKeysBody(BaseModel):
    env: Literal["mock", "live"]
    app_key: str = Field(min_length=8, max_length=512)
    secret_key: str = Field(min_length=8, max_length=512)


class DecideBody(BaseModel):
    approve: bool
    note: str = Field("", max_length=200)


class AdvanceBody(BaseModel):
    days: int = Field(1, ge=1, le=250)
    auto_approve: bool = False


class SeenBody(BaseModel):
    seq: int = Field(ge=0)


class EnvBody(BaseModel):
    env: Literal["sim", "mock", "live"]
    confirm: str = Field("", max_length=64)


class BrokerTestBody(BaseModel):
    env: Literal["mock", "live"]


class SimResetBody(BaseModel):
    start: date | None = None
    initial_cash: int | None = Field(None, ge=1_000_000, le=100_000_000_000)


class ConfirmBody(BaseModel):
    confirm: str = Field("", max_length=64)


class PlanBody(BaseModel):
    config: PlanConfig
    note: str = Field("", max_length=200)


class RestoreBody(BaseModel):
    note: str = Field("", max_length=200)


class SleeveRunBody(BaseModel):
    force: bool = False
    sleeve_ids: list[str] | None = Field(None, max_length=6)


class PreviewBody(BaseModel):
    config: PlanConfig | None = None
    start: date


class BacktestBody(BaseModel):
    start: date | None = None
    end: date | None = None
    initial_cash: int = Field(30_000_000, ge=1_000_000, le=100_000_000_000)
    techniques: list[str] = Field(default_factory=lambda: list(ENTRY_KEYS))
    max_candidates: int = Field(8, ge=1, le=30)
