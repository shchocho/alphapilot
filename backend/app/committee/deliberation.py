"""AI 위원회 심의: 강세 연구원 → 약세 연구원 → 리스크 검토 → 위원장 최종 판단.

AI는 규칙이 미리 정한 범위(허용 행동, 최대 수량, 계획 손절) 안에서만 고른다.
어느 단계든 실패하면(오류·거절·시간 초과·형식 위반·예산 초과) 결론은 HOLD + '검토 필요'다.
절대 매수로 해석하지 않는다. 결론은 이후 리스크 게이트를 다시 통과해야 한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from app.committee.llm import LlmClient, LlmError, LlmUsage
from app.committee.seats import votes
from app.core.models import Decision, EntryPlan, Position, Signal, StockInfo, TechniqueResult
from app.regime.regime import RegimeState

Depth = Literal["light", "standard", "deep"]
DEPTH_LABELS: dict[str, str] = {"light": "간단(1회 호출)", "standard": "표준(4회 호출)", "deep": "심층(6회 호출)"}
SIZE_FRACTIONS: dict[str, float] = {"full": 1.0, "three_quarters": 0.75, "half": 0.5, "quarter": 0.25}
CONVICTIONS = ["very_low", "low", "medium", "high", "very_high"]

CHARTER = """당신은 한 개인 투자자의 국내 주식 자동매매 시스템 안에서 일하는 투자위원회 구성원입니다.
시스템은 규칙으로 계산한 '분석 리포트'를 주고, 위원회는 토론해 결론을 냅니다.

지켜야 할 것:
1. 리포트에 있는 수치만 근거로 씁니다. 리포트에 없는 뉴스, 실적, 소문, 목표주가를 만들어 내지 않습니다. 모르는 것은 모른다고 씁니다.
2. 기준일 이후에 일어난 일이나 당신이 기억하는 그 종목의 과거 주가 흐름으로 판단하지 않습니다. 판단 재료는 리포트뿐입니다.
3. 허용된 행동만 고를 수 있습니다. 수량과 손절 한도는 시스템의 리스크 게이트가 강제하며, 당신의 결론은 거기서 줄어들거나 거부될 수 있습니다.
4. 확신이 없으면 HOLD가 정상적인 결론입니다. 억지로 매수 논리를 만들지 않습니다.
5. 손절 같은 보호 청산은 규칙이 따로 실행합니다. 당신은 그것을 끄거나 늦출 수 없습니다.
6. 요청받은 JSON 형식으로만 답합니다. 문장은 한국어로 짧게 쓰고, 주장마다 리포트의 수치를 인용합니다.

역할:
- 강세 연구원: 지금 사야 하는(또는 계속 보유해야 하는) 가장 강한 논거를 세웁니다. 약점을 숨기지 않습니다.
- 약세 연구원: 사면 안 되는(또는 팔아야 하는) 이유를 찾고 강세 논거의 허점을 반박합니다.
- 리스크 검토자: 변동성, 유동성, 시장 국면, 포지션 크기를 보고 크기를 줄이거나 거부권을 행사합니다.
- 위원장: 토론과 리스크 검토를 읽고 최종 결론을 냅니다. 반대 의견과 판단을 바꿀 조건을 함께 적습니다."""

ARGUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "points": {"type": "array", "items": {"type": "string"}},
        "strongest_evidence": {"type": "string"},
        "weakest_spot": {"type": "string"},
    },
    "required": ["points", "strongest_evidence", "weakest_spot"],
    "additionalProperties": False,
}
RISK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "concerns": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "veto": {"type": "boolean"},
        "size": {"type": "string", "enum": list(SIZE_FRACTIONS)},
        "note": {"type": "string"},
    },
    "required": ["concerns", "severity", "veto", "size", "note"],
    "additionalProperties": False,
}


def final_schema(actions: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": actions},
            "conviction": {"type": "string", "enum": CONVICTIONS},
            "size": {"type": "string", "enum": list(SIZE_FRACTIONS)},
            "tighter_stop": {"type": "integer"},
            "thesis": {"type": "string"},
            "key_risks": {"type": "array", "items": {"type": "string"}},
            "invalidation": {"type": "string"},
            "dissent": {"type": "string"},
        },
        "required": ["action", "conviction", "size", "tighter_stop", "thesis", "key_risks", "invalidation", "dissent"],
        "additionalProperties": False,
    }


class Argument(BaseModel):
    points: list[str]
    strongest_evidence: str
    weakest_spot: str


class RiskReview(BaseModel):
    concerns: list[str]
    severity: Literal["low", "medium", "high"]
    veto: bool
    size: Literal["full", "three_quarters", "half", "quarter"]
    note: str


class FinalCall(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    conviction: Literal["very_low", "low", "medium", "high", "very_high"]
    size: Literal["full", "three_quarters", "half", "quarter"]
    tighter_stop: int
    thesis: str
    key_risks: list[str]
    invalidation: str
    dissent: str


class Budget(Protocol):
    def check(self) -> None:
        """예산을 넘었으면 LlmError('budget')를 던진다."""
        ...

    def record(self, role: str, usage: LlmUsage | None, ok: bool, error: str) -> None: ...


@dataclass(slots=True)
class EntryContext:
    info: StockInfo
    as_of: date
    close: float
    techniques: dict[str, TechniqueResult]
    primary: TechniqueResult
    seats: list[Signal]
    regime: RegimeState
    plan: EntryPlan
    max_qty: dict[str, int]  # 확신 등급별 허용 최대 수량(규칙이 계산)
    portfolio: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HoldingContext:
    info: StockInfo
    as_of: date
    close: float
    position: Position
    seats: list[Signal]
    regime: RegimeState
    pnl_pct: float
    techniques: dict[str, TechniqueResult] = field(default_factory=dict)
    portfolio: dict[str, Any] = field(default_factory=dict)


def _identity(info: StockInfo, anonymize: bool) -> dict[str, str]:
    if anonymize:
        return {"종목": "익명 종목", "시장": info.market, "업종": "비공개"}
    return {"종목": info.name, "코드": info.code, "시장": info.market, "업종": info.sector}


def _seat_lines(seats: list[Signal]) -> list[dict[str, Any]]:
    stance_ko = {"bullish": "강세", "bearish": "약세", "neutral": "중립", "abstain": "기권"}
    return [
        {"좌석": s.label, "의견": stance_ko[s.stance], "값": round(s.value, 2), "확신": round(s.confidence, 2), "근거": s.summary}
        for s in seats
    ]


def _technique_lines(techniques: dict[str, TechniqueResult]) -> list[dict[str, Any]]:
    out = []
    for r in techniques.values():
        if r.state == "insufficient":
            continue
        out.append({
            "기법": r.name, "통과": r.passed, "점수": round(r.score), "상태": r.state,
            "규칙": [f"{'O' if c.passed else 'X'} {c.label}: {c.value} (기준 {c.threshold})" for c in r.checks],
            "메모": r.notes,
        })
    return out


def _regime_block(regime: RegimeState) -> dict[str, Any]:
    return {
        "국면": regime.label, "점수": round(regime.score), "총 노출 상한(%)": round(regime.exposure_cap * 100),
        "신규 매수 허용": regime.allow_new_buys, "분산일(25·15·5일)": list(regime.dist_counts),
        "구성": [f"{c['name']}: {c['detail']} → {c['score']}점" for c in regime.components],
    }


def build_entry_report(ctx: EntryContext, *, anonymize: bool = False) -> str:
    plan = ctx.plan
    entry_kind = {"open": "다음 거래일 시가 매수", "trigger": "돌파 기준가 도달 시 매수", "vb": "변동성 돌파(시가 + k×전일 범위) 도달 시 매수, 그다음 거래일 시가 매도"}[plan.entry_type]
    report = {
        "문서": "신규 매수 심의 리포트",
        "기준일": "비공개" if anonymize else ctx.as_of.isoformat(),
        "대상": _identity(ctx.info, anonymize),
        "종가": round(ctx.close),
        "시장 국면": _regime_block(ctx.regime),
        "기법 평가": _technique_lines(ctx.techniques),
        "좌석 의견": _seat_lines(ctx.seats),
        "주문 계획(규칙이 계산, 변경 불가 범위)": {
            "근거 기법": ctx.primary.name, "진입 방식": entry_kind, "예상 진입가": round(plan.reference_price),
            "돌파 기준가": plan.trigger, "추격 한도": plan.chase_limit, "계획 손절가": plan.stop,
            "손절까지(%)": round(plan.risk_pct * 100, 1), "목표가": plan.target,
            "확신 등급별 최대 수량": ctx.max_qty,
            "손절 조정": "계획 손절가보다 높게(좁게)만 조정할 수 있음. 조정하지 않으려면 0",
        },
        "계좌 상황": ctx.portfolio,
        "허용 행동": ["BUY", "HOLD"],
    }
    return json.dumps(report, ensure_ascii=False, indent=1)


def build_holding_report(ctx: HoldingContext, *, anonymize: bool = False) -> str:
    pos = ctx.position
    report = {
        "문서": "보유 종목 재심의 리포트",
        "기준일": "비공개" if anonymize else ctx.as_of.isoformat(),
        "대상": _identity(ctx.info, anonymize),
        "종가": round(ctx.close),
        "보유 현황": {
            "수량": pos.qty, "취득 단가": round(pos.avg_price), "평가손익(%)": round(ctx.pnl_pct * 100, 1),
            "보유 일수(거래일)": pos.days_held, "진입 기법": pos.technique, "현재 손절가": pos.stop, "목표가": pos.target,
            "손절까지(%)": round((ctx.close - pos.stop) / ctx.close * 100, 1) if ctx.close > 0 else None,
        },
        "시장 국면": _regime_block(ctx.regime),
        "기법 평가": _technique_lines(ctx.techniques),
        "좌석 의견": _seat_lines(ctx.seats),
        "계좌 상황": ctx.portfolio,
        "허용 행동": ["SELL", "HOLD"],
        "참고": "손절·추적 손절·기법의 청산 규칙은 이 심의와 상관없이 규칙이 실행한다. 여기서는 그보다 먼저 팔지 여부만 판단한다.",
    }
    return json.dumps(report, ensure_ascii=False, indent=1)


@dataclass(slots=True)
class Transcript:
    depth: str
    model: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    branch: dict[str, Any] | None = None  # 분기 판단(escalation.py)일 때만: 묻는 이유와 반영 결과

    @property
    def cost_usd(self) -> float:
        return round(sum(step.get("cost_usd", 0.0) for step in self.steps), 6)

    def to_dict(self) -> dict[str, Any]:
        return {"depth": self.depth, "model": self.model, "steps": self.steps, "error": self.error, "cost_usd": self.cost_usd,
                **({"branch": self.branch} if self.branch else {})}


async def _ask(llm: LlmClient, budget: Budget, transcript: Transcript, *, role: str, label: str, shared: str,
               task: str, schema: dict[str, Any], model_cls: type[BaseModel]) -> BaseModel:
    budget.check()
    try:
        result = await llm.complete(system=CHARTER, shared=shared, task=task, schema=schema, role=role)
    except LlmError as exc:
        budget.record(role, getattr(exc, "usage", None), False, exc.kind)
        raise
    try:
        parsed = model_cls.model_validate_json(result.text)
    except ValidationError as exc:
        budget.record(role, result.usage, False, "invalid_output")
        raise LlmError("invalid_output", f"{label}의 응답이 형식에 맞지 않습니다") from exc
    budget.record(role, result.usage, True, "")
    transcript.steps.append({
        "role": role, "label": label, "content": parsed.model_dump(), "model": result.usage.model,
        "input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens,
        "cache_read_tokens": result.usage.cache_read_tokens, "cost_usd": round(result.usage.cost_usd, 6),
    })
    return parsed


def _dump(model: BaseModel) -> str:
    return json.dumps(model.model_dump(), ensure_ascii=False)


async def _debate(llm: LlmClient, budget: Budget, transcript: Transcript, shared: str, depth: Depth, subject: str) -> str:
    """강세·약세 토론과 리스크 검토를 돌리고, 위원장에게 넘길 요약 텍스트를 돌려준다."""
    if depth == "light":
        return ""
    bull = await _ask(llm, budget, transcript, role="bull", label="강세 연구원", shared=shared, schema=ARGUMENT_SCHEMA, model_cls=Argument,
                      task=f"역할: 강세 연구원. {subject}의 가장 강한 논거를 리포트의 수치로만 세우세요. 논거가 약하면 약하다고 쓰세요.")
    bear = await _ask(llm, budget, transcript, role="bear", label="약세 연구원", shared=shared, schema=ARGUMENT_SCHEMA, model_cls=Argument,
                      task=f"역할: 약세 연구원. 아래 강세 논거를 읽고, {subject}에 반대하는 이유와 강세 논거의 허점을 리포트의 수치로 반박하세요.\n\n강세 논거: {_dump(bull)}")
    debate = f"강세 논거: {_dump(bull)}\n약세 논거: {_dump(bear)}"
    if depth == "deep":
        bull2 = await _ask(llm, budget, transcript, role="bull_rebuttal", label="강세 재반박", shared=shared, schema=ARGUMENT_SCHEMA, model_cls=Argument,
                           task=f"역할: 강세 연구원. 약세 논거에 답하세요. 받아들일 지적은 받아들이고, 남는 논거만 다시 세우세요.\n\n{debate}")
        bear2 = await _ask(llm, budget, transcript, role="bear_rebuttal", label="약세 재반박", shared=shared, schema=ARGUMENT_SCHEMA, model_cls=Argument,
                           task=f"역할: 약세 연구원. 강세 재반박에 답하세요. 여전히 남는 위험만 정리하세요.\n\n{debate}\n강세 재반박: {_dump(bull2)}")
        debate += f"\n강세 재반박: {_dump(bull2)}\n약세 재반박: {_dump(bear2)}"
    risk = await _ask(llm, budget, transcript, role="risk", label="리스크 검토자", shared=shared, schema=RISK_SCHEMA, model_cls=RiskReview,
                      task=("역할: 리스크 검토자. 토론을 읽고 변동성·유동성·시장 국면·포지션 크기 관점의 우려를 정리하세요. "
                            "크기를 줄여야 하면 size를 낮추고, 진행하면 안 된다고 보면 veto를 true로 하세요.\n\n" + debate))
    return debate + f"\n리스크 검토: {_dump(risk)}"


def _review(code: str, name: str, kind: str, seats: list[Signal], error: LlmError) -> Decision:
    return Decision(code=code, name=name, kind=kind, action="HOLD", conviction="very_low", thesis="AI 판단을 받지 못해 보류합니다",  # type: ignore[arg-type]
                    source="ai", status="review", status_detail=str(error), votes=votes(seats))


def _risk_step(transcript: Transcript) -> dict[str, Any] | None:
    return next((s["content"] for s in transcript.steps if s["role"] == "risk"), None)


async def deliberate_entry(ctx: EntryContext, llm: LlmClient, budget: Budget, *, depth: Depth = "standard",
                           anonymize: bool = False) -> tuple[Decision, Transcript]:
    transcript = Transcript(depth=depth, model=llm.model)
    shared = build_entry_report(ctx, anonymize=anonymize)
    try:
        debate = await _debate(llm, budget, transcript, shared, depth, "이 종목을 지금 사는 것")
        task = ("역할: 위원장. 허용 행동은 BUY 또는 HOLD입니다. 결론과 확신, 포지션 크기(size), 근거(thesis), 핵심 위험, "
                "판단을 바꿀 조건(invalidation), 반대 의견 요약(dissent)을 내세요. 손절을 좁히려면 tighter_stop에 가격을, 아니면 0을 넣으세요.")
        final = await _ask(llm, budget, transcript, role="chair", label="위원장", shared=shared, schema=final_schema(["BUY", "HOLD"]),
                           model_cls=FinalCall, task=task + (f"\n\n{debate}" if debate else ""))
    except LlmError as exc:
        transcript.error = f"{exc.kind}: {exc}"
        return _review(ctx.info.code, ctx.info.name, "entry", ctx.seats, exc), transcript
    assert isinstance(final, FinalCall)

    action = final.action if final.action in ("BUY", "HOLD") else "HOLD"
    fraction = SIZE_FRACTIONS[final.size]
    thesis = final.thesis
    risk = _risk_step(transcript)
    if risk is not None:
        fraction = min(fraction, SIZE_FRACTIONS[risk["size"]])
        if risk["veto"] and action == "BUY":
            # 리스크 검토자의 거부권은 위원장 결론보다 위에 있다(규칙으로 강제).
            action = "HOLD"
            thesis = f"리스크 검토자 거부권으로 매수하지 않습니다: {risk['note']} (위원장 의견: {final.thesis})"
    decision = Decision(
        code=ctx.info.code, name=ctx.info.name, kind="entry", action=action, conviction=final.conviction,  # type: ignore[arg-type]
        size_fraction=fraction, stop=final.tighter_stop if final.tighter_stop > 0 else None, thesis=thesis,
        key_risks=final.key_risks[:5], invalidation=final.invalidation, dissent=final.dissent, source="ai", votes=votes(ctx.seats),
    )
    return decision, transcript


async def deliberate_holding(ctx: HoldingContext, llm: LlmClient, budget: Budget, *, depth: Depth = "standard",
                             anonymize: bool = False) -> tuple[Decision, Transcript]:
    transcript = Transcript(depth=depth, model=llm.model)
    shared = build_holding_report(ctx, anonymize=anonymize)
    try:
        debate = await _debate(llm, budget, transcript, shared, depth, "이 종목을 계속 보유하는 것")
        task = ("역할: 위원장. 허용 행동은 SELL 또는 HOLD입니다. 규칙에 따른 청산보다 먼저 팔아야 할 이유가 분명할 때만 SELL을 고르세요. "
                "size와 tighter_stop은 이 심의에서 쓰지 않으니 full과 0을 넣으세요.")
        final = await _ask(llm, budget, transcript, role="chair", label="위원장", shared=shared, schema=final_schema(["SELL", "HOLD"]),
                           model_cls=FinalCall, task=task + (f"\n\n{debate}" if debate else ""))
    except LlmError as exc:
        transcript.error = f"{exc.kind}: {exc}"
        return _review(ctx.info.code, ctx.info.name, "holding", ctx.seats, exc), transcript
    assert isinstance(final, FinalCall)
    action = final.action if final.action in ("SELL", "HOLD") else "HOLD"
    decision = Decision(
        code=ctx.info.code, name=ctx.info.name, kind="holding", action=action, conviction=final.conviction,  # type: ignore[arg-type]
        thesis=final.thesis, key_risks=final.key_risks[:5], invalidation=final.invalidation, dissent=final.dissent,
        source="ai", votes=votes(ctx.seats),
    )
    return decision, transcript
