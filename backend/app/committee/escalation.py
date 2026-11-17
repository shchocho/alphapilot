"""분기 판단(판단 주체 '규칙 + AI 분기'). 규칙이 결론을 내고, 규칙만으로 가르기 애매한 분기에서만 Claude에게 한 번 묻는다.

세 단계다.
  1) 인지: entry_branch / holding_branch — 규칙 결론과 좌석 의견을 보고 물어볼 분기인지 정한다(결정론).
  2) 질문: second_opinion — 리포트, 규칙 결론, 묻는 이유를 주고 허용 행동 중에서 고르게 한다(종목당 Claude 1회).
  3) 반영: resolve — AI 답을 받아들일지 정한다. 위험을 줄이는 쪽은 그대로 따르고, 늘리는 쪽은 AI 확신이 충분할 때만 따른다.
     답을 받지 못하면(오류·거절·예산 초과) 규칙 결론을 그대로 쓴다.

리스크 좌석 거부권과 약세장 매수 금지는 안전 규칙이라 분기로 올리지 않는다. 결론은 이후 리스크 게이트를 다시 통과한다.
"""

from __future__ import annotations

from dataclasses import replace

from app.committee.deliberation import (
    CONVICTIONS,
    SIZE_FRACTIONS,
    Budget,
    EntryContext,
    FinalCall,
    HoldingContext,
    Transcript,
    _ask,
    build_entry_report,
    build_holding_report,
    final_schema,
)
from app.committee.llm import LlmClient, LlmError
from app.committee.rules_committee import BUY_THRESHOLD, SELL_THRESHOLD, safety_hold
from app.committee.seats import blend, seat, votes
from app.core.models import CONVICTION_LABEL, Decision, Signal

BORDERLINE = 0.08  # 좌석 종합이 매수·매도 문턱에서 이 안쪽이면 경계선으로 본다
SPLIT_BEARISH = 2  # 매수 결론인데 약세 좌석이 이만큼이면 의견이 갈린 것으로 본다
LOSS_BRANCH = -0.04  # 보유: 평가손익이 이 값 이하인데 규칙이 보유라면 묻는다(engine.core.REVIEW_LOSS_BELOW와 같은 값)
MIN_CONVICTION_TO_ADD_RISK = "medium"  # 위험을 늘리는 쪽(보류→매수, 매도→보유)으로 뒤집으려면 필요한 AI 확신


def entry_branch(seats: list[Signal], rules: Decision) -> str | None:
    """신규 매수 후보를 Claude에게 물어볼 이유. 물어볼 분기가 아니면 None."""
    if safety_hold(seats) is not None:
        return None  # 거부권·약세장 보류는 AI가 뒤집을 수 없으니 묻지 않는다
    score = blend(seats)
    if abs(score - BUY_THRESHOLD) <= BORDERLINE:
        return f"좌석 종합 {score:+.2f}가 매수 기준 {BUY_THRESHOLD:+.2f} 바로 근처라 규칙만으로 가르기 어렵습니다"
    if rules.action == "BUY":
        bearish = votes(seats)["bearish"]
        if bearish >= SPLIT_BEARISH:
            return f"규칙은 매수지만 약세 좌석이 {bearish}개라 의견이 갈립니다"
        risk = seat(seats, "risk")
        if risk is not None and not risk.abstained and risk.value < 0.0:
            return f"규칙은 매수지만 리스크 좌석이 경고합니다({risk.summary})"
    return None


def holding_branch(seats: list[Signal], rules: Decision, pnl_pct: float) -> str | None:
    """보유 종목을 Claude에게 물어볼 이유. 물어볼 분기가 아니면 None."""
    score = blend(seats)
    if abs(score - SELL_THRESHOLD) <= BORDERLINE:
        return f"좌석 종합 {score:+.2f}가 매도 기준 {SELL_THRESHOLD:+.2f} 바로 근처라 규칙만으로 가르기 어렵습니다"
    if rules.action == "HOLD" and pnl_pct <= LOSS_BRANCH:
        return f"평가손익 {pnl_pct * 100:+.1f}%로 손실 중인데 청산 규칙은 아직 충족되지 않았습니다"
    return None


def _ko(action: str, kind: str) -> str:
    return {"BUY": "매수", "SELL": "매도"}.get(action, "보류" if kind == "entry" else "보유")


def resolve(rules: Decision, final: FinalCall | None) -> tuple[Decision, str]:
    """AI 답을 반영할지 정한다. 반환: (최종 결론, 어떻게 처리했는지 한 줄)."""
    if final is None:
        return rules, "AI 답을 받지 못해 규칙 결론을 그대로 씁니다"
    conviction = CONVICTION_LABEL[final.conviction]
    if final.action == rules.action:
        if rules.action != "BUY":
            return rules, f"AI도 같은 결론입니다(확신 {conviction})"
        # 같은 매수라도 수량과 손절은 AI가 줄이는 쪽으로만 반영한다(게이트가 손절 범위를 다시 검사한다)
        tightened = replace(rules, size_fraction=min(rules.size_fraction, SIZE_FRACTIONS[final.size]),
                            stop=final.tighter_stop if final.tighter_stop > 0 else rules.stop)
        return tightened, f"AI도 매수에 동의했습니다(확신 {conviction}). 수량과 손절은 줄이는 쪽 의견만 반영합니다"
    adds_risk = final.action == "BUY" or rules.action == "SELL"
    if adds_risk and CONVICTIONS.index(final.conviction) < CONVICTIONS.index(MIN_CONVICTION_TO_ADD_RISK):
        return rules, f"AI는 {_ko(final.action, rules.kind)} 의견이지만 확신이 {conviction}이라 위험을 늘리는 쪽으로는 바꾸지 않습니다"
    flipped = Decision(
        code=rules.code, name=rules.name, kind=rules.kind, action=final.action, conviction=final.conviction,
        size_fraction=SIZE_FRACTIONS[final.size] if final.action == "BUY" else 1.0,
        stop=final.tighter_stop if final.action == "BUY" and final.tighter_stop > 0 else None, thesis=final.thesis,
        key_risks=final.key_risks[:5], invalidation=final.invalidation, dissent=final.dissent, source="ai", votes=rules.votes,
    )
    return flipped, f"AI 의견대로 {_ko(rules.action, rules.kind)}에서 {_ko(final.action, rules.kind)}로 바꿨습니다(확신 {conviction})"


async def second_opinion(ctx: EntryContext | HoldingContext, rules: Decision, reason: str, llm: LlmClient,
                         budget: Budget) -> tuple[Decision, Transcript]:
    """분기 한 건을 Claude에게 묻고, resolve로 반영 여부까지 정한 결론을 돌려준다."""
    entry = isinstance(ctx, EntryContext)
    actions = ["BUY", "HOLD"] if entry else ["SELL", "HOLD"]
    transcript = Transcript(depth="branch", model=llm.model)
    task = (
        "역할: 위원장(단독 심사). 평소에는 규칙 위원회가 결론을 내지만, 이번 건은 규칙만으로 가르기 애매해 당신에게 묻습니다.\n"
        f"묻는 이유: {reason}\n"
        f"규칙 위원회 결론: {rules.action} · {rules.thesis}\n"
        f"허용 행동은 {' 또는 '.join(actions)}입니다. 규칙 결론에 동의해도 되고 뒤집어도 됩니다. "
        "어느 쪽이든 리포트의 어떤 수치가 판단을 갈랐는지 thesis에 쓰세요. "
        "확신(conviction)은 근거의 강도대로 매기세요. 확신이 낮으면 시스템은 위험을 늘리는 쪽 변경을 받아들이지 않습니다. "
        + ("매수라면 포지션 크기(size)를 정하고, 손절을 좁히려면 tighter_stop에 가격을, 아니면 0을 넣으세요."
           if entry else "size와 tighter_stop은 이 심의에서 쓰지 않으니 full과 0을 넣으세요.")
    )
    final: FinalCall | None = None
    try:
        answer = await _ask(llm, budget, transcript, role="branch", label="분기 판단", task=task, model_cls=FinalCall,
                            shared=build_entry_report(ctx) if entry else build_holding_report(ctx), schema=final_schema(actions))
        if isinstance(answer, FinalCall) and answer.action in actions:
            final = answer
    except LlmError as exc:
        transcript.error = f"{exc.kind}: {exc}"
    decision, outcome = resolve(rules, final)
    transcript.branch = {"reason": reason, "rules_action": rules.action, "ai_action": final.action if final else None,
                         "adopted": decision is not rules, "outcome": outcome}
    return decision, transcript
