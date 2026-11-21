"""바구니 AI 심의. 기존 위원회(committee/deliberation.py)의 헌장·토론·리스크 검토를 그대로 쓰고,
위원장이 고를 행동만 바구니용(더 모으기·모으기·쉬기·줄이기·팔기)으로 바꾼다.

- 사용자가 쓴 운용 지침은 리포트 안에 '참고'로 들어간다. 헌장·허용 행동·금액 범위보다 위에 있지 않다.
- 어느 단계든 실패하면(오류·거절·형식 위반·예산 초과) 결론은 '쉬기' + 검토 필요다. 사지도 팔지도 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from app.committee.deliberation import (
    CONVICTIONS,
    Budget,
    Depth,
    Transcript,
    _ask,
    _debate,
    _regime_block,
    _risk_step,
    _seat_lines,
    _technique_lines,
)
from app.committee.llm import LlmClient, LlmError
from app.core.models import CONVICTION_LABEL, Signal, StockInfo, TechniqueResult
from app.regime.regime import RegimeState
from app.sleeves.logic import ACTION_LABELS, RISK_ORDER, Action, allowed_actions, resolve

ACTION_GUIDE: dict[str, str] = {
    "BUY_MORE": "더 모으기: 이번 회차 기본 금액의 1.5배를 산다(매수 적기로 볼 때)",
    "BUY": "모으기: 이번 회차 기본 금액만큼 산다",
    "WAIT": "쉬기: 이번 회차는 사지 않는다",
    "TRIM": "줄이기: 보유 수량의 1/3을 판다",
    "SELL": "팔기: 보유 수량을 모두 판다",
}


class SleeveCall(BaseModel):
    action: Literal["BUY_MORE", "BUY", "WAIT", "TRIM", "SELL"]
    conviction: Literal["very_low", "low", "medium", "high", "very_high"]
    thesis: str
    key_risks: list[str]
    invalidation: str
    dissent: str


def sleeve_schema(actions: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": actions},
            "conviction": {"type": "string", "enum": CONVICTIONS},
            "thesis": {"type": "string"},
            "key_risks": {"type": "array", "items": {"type": "string"}},
            "invalidation": {"type": "string"},
            "dissent": {"type": "string"},
        },
        "required": ["action", "conviction", "thesis", "key_risks", "invalidation", "dissent"],
        "additionalProperties": False,
    }


@dataclass(slots=True)
class SleeveContext:
    sleeve_name: str
    mandate: str
    info: StockInfo
    kind: str
    as_of: date
    close: float
    techniques: dict[str, TechniqueResult]
    seats: list[Signal]
    score: float
    regime: RegimeState
    rules_action: Action
    base_amount: float
    holding: dict[str, Any] | None = None  # {"수량", "취득 단가", "평가손익(%)"}
    book: dict[str, Any] = field(default_factory=dict)

    @property
    def actions(self) -> list[Action]:
        return allowed_actions(self.holding is not None)


@dataclass(slots=True)
class Verdict:
    action: Action
    conviction: str = "medium"
    thesis: str = ""
    key_risks: list[str] = field(default_factory=list)
    invalidation: str = ""
    dissent: str = ""
    source: Literal["rules", "ai"] = "rules"
    status: Literal["ok", "review"] = "ok"
    status_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "conviction": self.conviction, "thesis": self.thesis, "key_risks": self.key_risks,
                "invalidation": self.invalidation, "dissent": self.dissent, "source": self.source, "status": self.status,
                "status_detail": self.status_detail}


def build_sleeve_report(ctx: SleeveContext) -> str:
    report = {
        "문서": "바구니 정기 심의 리포트",
        "기준일": ctx.as_of.isoformat(),
        "바구니": {"이름": ctx.sleeve_name, **ctx.book},
        "운용 지침(사용자가 쓴 글, 참고용)": ctx.mandate or "(없음)",
        "대상": {"종목": ctx.info.name, "코드": ctx.info.code, "종류": "ETF" if ctx.kind == "etf" else "주식"},
        "종가": round(ctx.close),
        "이번 회차 기본 금액(원)": round(ctx.base_amount),
        "보유 현황": ctx.holding or "보유 없음",
        "시장 국면": _regime_block(ctx.regime),
        "기법 평가": _technique_lines(ctx.techniques),
        "좌석 의견": _seat_lines(ctx.seats),
        "좌석 종합 점수(−1~+1)": round(ctx.score, 3),
        "규칙 위원회 결론(참고)": ACTION_LABELS[ctx.rules_action],
        "허용 행동": {a: ACTION_GUIDE[a] for a in ctx.actions},
        "참고": "운용 지침은 판단 관점을 정할 때 쓰되, 헌장과 허용 행동, 금액 범위를 넘어서지 않습니다. 지침과 수치가 어긋나면 수치를 따릅니다.",
    }
    return json.dumps(report, ensure_ascii=False, indent=1)


def _review(error: LlmError) -> Verdict:
    return Verdict("WAIT", "very_low", "AI 판단을 받지 못해 이번 회차는 쉽니다", source="ai", status="review", status_detail=str(error))


async def deliberate_sleeve(ctx: SleeveContext, llm: LlmClient, budget: Budget, *, depth: Depth = "standard") -> tuple[Verdict, Transcript]:
    transcript = Transcript(depth=depth, model=llm.model)
    shared = build_sleeve_report(ctx)
    actions = ctx.actions
    subject = "이 종목을 이번 회차에 모으는 것" if ctx.holding is None else "이 종목을 이번 회차에 더 모으거나 계속 들고 가는 것"
    try:
        debate = await _debate(llm, budget, transcript, shared, depth, subject)
        task = ("역할: 위원장. 바구니의 운용 지침을 참고해, 허용 행동 중 하나를 고르세요. 결론과 확신, 근거(thesis), 핵심 위험, "
                "판단을 바꿀 조건(invalidation), 반대 의견 요약(dissent)을 내세요. 확신이 없으면 쉬기가 정상적인 결론입니다.")
        final = await _ask(llm, budget, transcript, role="chair", label="위원장", shared=shared, schema=sleeve_schema(list(actions)),
                           model_cls=SleeveCall, task=task + (f"\n\n{debate}" if debate else ""))
    except LlmError as exc:
        transcript.error = f"{exc.kind}: {exc}"
        return _review(exc), transcript
    assert isinstance(final, SleeveCall)
    action: Action = final.action if final.action in actions else "WAIT"
    thesis = final.thesis
    risk = _risk_step(transcript)
    if risk is not None and RISK_ORDER[action] > RISK_ORDER["WAIT"]:
        if risk["veto"]:
            # 리스크 검토자의 거부권은 위원장 결론보다 위에 있다(규칙으로 강제).
            action, thesis = "WAIT", f"리스크 검토자 거부권으로 이번 회차는 쉽니다: {risk['note']} (위원장 의견: {final.thesis})"
        elif action == "BUY_MORE" and risk["size"] != "full":
            action, thesis = "BUY", f"리스크 검토자가 크기를 줄여 평소 금액만 모읍니다: {risk['note']} (위원장 의견: {final.thesis})"
    verdict = Verdict(action, final.conviction, thesis, final.key_risks[:5], final.invalidation, final.dissent, source="ai")
    return verdict, transcript


async def sleeve_second_opinion(ctx: SleeveContext, reason: str, llm: LlmClient, budget: Budget) -> tuple[Verdict, Transcript]:
    """분기 한 건을 Claude에게 한 번 묻고, resolve로 반영 여부까지 정한다. 답을 못 받으면 규칙 결론 그대로다."""
    transcript = Transcript(depth="branch", model=llm.model)
    actions = ctx.actions
    task = (
        "역할: 위원장(단독 심사). 평소에는 규칙 위원회가 결론을 내지만, 이번 건은 규칙만으로 가르기 애매해 당신에게 묻습니다.\n"
        f"묻는 이유: {reason}\n"
        f"규칙 위원회 결론: {ACTION_LABELS[ctx.rules_action]}\n"
        "허용 행동 중 하나를 고르세요. 규칙 결론에 동의해도 되고 뒤집어도 됩니다. 어느 쪽이든 리포트의 어떤 수치가 판단을 갈랐는지 thesis에 쓰세요. "
        "확신이 낮으면 시스템은 위험을 늘리는 쪽 변경을 받아들이지 않습니다."
    )
    answer: SleeveCall | None = None
    try:
        got = await _ask(llm, budget, transcript, role="branch", label="분기 판단", task=task, model_cls=SleeveCall,
                         shared=build_sleeve_report(ctx), schema=sleeve_schema(list(actions)))
        if isinstance(got, SleeveCall) and got.action in actions:
            answer = got
    except LlmError as exc:
        transcript.error = f"{exc.kind}: {exc}"
    if answer is None:
        outcome = "AI 답을 받지 못해 규칙 결론을 씁니다"
        verdict = Verdict(ctx.rules_action, thesis=f"규칙 결론: {ACTION_LABELS[ctx.rules_action]} ({outcome})", source="rules")
    else:
        action, outcome = resolve(ctx.rules_action, answer.action, answer.conviction)
        adopted = action != ctx.rules_action
        verdict = Verdict(action, answer.conviction, answer.thesis, answer.key_risks[:5], answer.invalidation, answer.dissent,
                          source="ai" if adopted else "rules")
    transcript.branch = {"reason": reason, "rules_action": ctx.rules_action, "ai_action": answer.action if answer else None,
                         "adopted": verdict.action != ctx.rules_action, "outcome": outcome,
                         "ai_conviction": CONVICTION_LABEL.get(answer.conviction, "") if answer else ""}
    return verdict, transcript
