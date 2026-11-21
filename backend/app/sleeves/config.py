"""운용 계획(총액 + 바구니) 모델. 저장할 때마다 새 판(리비전)이 된다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Cadence = Literal["daily", "weekly", "monthly"]
Decider = Literal["rules", "ai", "hybrid"]
Mode = Literal["alert", "paper"]
Kind = Literal["stock", "etf"]
Depth = Literal["light", "standard", "deep"]

CODE_PATTERN = r"^[0-9A-Z]{6}$"
SLEEVE_ID_PATTERN = r"^s[0-9a-f]{6}$"
MAX_SLEEVES = 6
MAX_ITEMS = 15

CADENCE_LABELS: dict[str, str] = {"daily": "매일", "weekly": "매주", "monthly": "매월"}
DECIDER_LABELS: dict[str, str] = {"rules": "규칙", "ai": "AI 위원회", "hybrid": "규칙 + AI 분기"}
MODE_LABELS: dict[str, str] = {"alert": "알림만", "paper": "가상 운용"}
KIND_LABELS: dict[str, str] = {"stock": "주식", "etf": "ETF"}

# ETF 운용사 브랜드. 이름이 이것으로 시작하면 ETF로 본다(사용자가 바꿀 수 있다).
ETF_BRANDS = ("KODEX", "TIGER", "ACE", "RISE", "SOL", "KBSTAR", "HANARO", "ARIRANG", "KOSEF", "PLUS", "TIMEFOLIO", "TIME",
              "WON", "1Q", "KIWOOM", "BNK", "TREX", "FOCUS", "UNICORN", "VITA", "HK", "에셋플러스", "마이다스", "마이티", "파워",
              "히어로즈", "DAISHIN343", "KCGI", "ITF", "KINDEX", "KOACT", "흥국", "TRUSTON")


def guess_kind(name: str) -> Kind:
    head = name.strip().upper()
    return "etf" if any(head.startswith(brand.upper()) for brand in ETF_BRANDS) else "stock"


class WatchItem(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field("", max_length=60)
    kind: Kind = "stock"
    weight: float = Field(1.0, gt=0, le=10)


class SleeveConfig(BaseModel):
    id: str = Field("", pattern=rf"^$|{SLEEVE_ID_PATTERN}")
    name: str = Field(min_length=1, max_length=20)
    amount: int = Field(ge=10_000, le=10_000_000_000)
    items: list[WatchItem] = Field(min_length=1, max_length=MAX_ITEMS)
    mandate: str = Field("", max_length=1500)
    decider: Decider = "rules"
    depth: Depth = "standard"
    cadence: Cadence = "weekly"
    installments: int = Field(12, ge=1, le=120)
    mode: Mode = "paper"

    @field_validator("name", "mandate")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("items")
    @classmethod
    def _unique_codes(cls, items: list[WatchItem]) -> list[WatchItem]:
        codes = [i.code for i in items]
        if len(codes) != len(set(codes)):
            raise ValueError("한 바구니에 같은 종목을 두 번 넣을 수 없습니다")
        return items

    def weight_of(self, code: str) -> float:
        total = sum(i.weight for i in self.items)
        item = next((i for i in self.items if i.code == code), None)
        return item.weight / total if item is not None and total > 0 else 0.0

    def base_amount(self, code: str) -> float:
        """한 회차에 이 종목에 쓰는 기본 금액."""
        return self.amount / self.installments * self.weight_of(code)

    def kind_of(self, code: str) -> Kind:
        item = next((i for i in self.items if i.code == code), None)
        return item.kind if item is not None else "stock"


class PlanConfig(BaseModel):
    total: int = Field(ge=100_000, le=100_000_000_000)
    sleeves: list[SleeveConfig] = Field(default_factory=list, max_length=MAX_SLEEVES)

    @model_validator(mode="after")
    def _fits(self) -> PlanConfig:
        allocated = sum(s.amount for s in self.sleeves)
        if allocated > self.total:
            raise ValueError(f"바구니 금액의 합({allocated:,}원)이 총 투입 금액({self.total:,}원)보다 큽니다")
        names = [s.name for s in self.sleeves]
        if len(names) != len(set(names)):
            raise ValueError("바구니 이름이 겹칩니다")
        ids = [s.id for s in self.sleeves if s.id]
        if len(ids) != len(set(ids)):
            raise ValueError("바구니 번호가 겹칩니다")
        return self

    def sleeve(self, sleeve_id: str) -> SleeveConfig | None:
        return next((s for s in self.sleeves if s.id == sleeve_id), None)

    def codes(self) -> list[str]:
        seen: dict[str, None] = {}
        for s in self.sleeves:
            for item in s.items:
                seen.setdefault(item.code, None)
        return list(seen)
