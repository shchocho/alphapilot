"""위원회 테스트. Claude는 가짜 클라이언트로 대신한다(실제 API를 호출하지 않는다)."""

import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from app.committee import rules_committee
from app.committee.deliberation import (
    EntryContext,
    FinalCall,
    HoldingContext,
    build_entry_report,
    build_holding_report,
    deliberate_entry,
    deliberate_holding,
)
from app.committee.escalation import entry_branch, holding_branch, resolve, second_opinion
from app.committee.llm import AnthropicLlm, LlmError, LlmResult, LlmUsage, estimate_cost
from app.committee.seats import SEAT_WEIGHTS, blend, build_seats, seat, votes
from app.core.models import Decision, Position, Signal, StockInfo
from app.regime.regime import compute_regime
from app.techniques import registry
from tests.helpers import flat_bars, make_bars, make_market

CODE = "000001"
INFO = StockInfo(CODE, "테스트전자", "KOSPI", "반도체")


def leader_market():
    steps = np.where(np.arange(300) % 2 == 0, 1.01, 0.997)
    closes = 10_000 * np.cumprod(steps)
    closes[-1] = closes[-2] * 1.02
    volumes = np.where(steps > 1, 1_500_000.0, 500_000.0)
    volumes[-1] = 3_000_000.0
    return make_market({CODE: make_bars(closes, volumes=volumes)})


def seats_for(market, code=CODE):
    i = len(market.stocks[code]) - 1
    results = registry.evaluate_all(market, code, i)
    return build_seats(market, code, i, results, compute_regime(market)[-1]), results


def sig(name: str, value: float, confidence: float = 1.0, abstained: bool = False) -> Signal:
    return Signal(seat=name, label=name, value=value, confidence=confidence, abstained=abstained, summary=f"{name} 근거")


# ── 좌석 ─────────────────────────────────────────────────────────────────────

def test_every_seat_is_present_for_a_stock_with_full_history():
    seats, _ = seats_for(leader_market())
    assert [s.seat for s in seats] == list(SEAT_WEIGHTS)
    assert seat(seats, "trend").stance == "bullish"
    assert seat(seats, "momentum").value == pytest.approx(1.0)


def test_value_seat_abstains_without_fundamentals():
    seats, _ = seats_for(leader_market())
    assert seat(seats, "value").abstained
    assert seat(seats, "value").stance == "abstain"


def test_seats_abstain_when_history_is_too_short():
    seats, _ = seats_for(make_market({CODE: flat_bars(80)}))
    assert seat(seats, "trend").abstained
    assert seat(seats, "momentum").abstained


def test_overheat_seat_turns_bearish_when_price_is_stretched_above_20_day_average():
    closes = np.concatenate([np.full(280, 10_000.0), 10_000 * 1.03 ** np.arange(1, 13)])
    seats, _ = seats_for(make_market({CODE: make_bars(closes)}))
    assert seat(seats, "overheat").stance == "bearish"


def test_risk_seat_penalises_high_volatility():
    rng = np.random.default_rng(7)
    closes = 10_000 * np.cumprod(1 + rng.normal(0, 0.06, 300).clip(-0.25, 0.25))
    seats, _ = seats_for(make_market({CODE: make_bars(closes, spread=0.04)}))
    assert seat(seats, "risk").value <= -0.6


def test_blend_ignores_abstentions_and_weights_by_confidence():
    assert blend([sig("trend", 1.0), sig("value", -1.0, abstained=True)]) == pytest.approx(1.0)
    assert blend([sig("trend", 1.0, 1.0), sig("breakout", -1.0, 1.0)]) == pytest.approx(0.0)
    assert blend([sig("trend", 1.0, 1.0), sig("breakout", -1.0, 0.5)]) == pytest.approx((0.2 - 0.1) / 0.3)
    assert blend([sig("value", 0.5, abstained=True)]) == 0.0


def test_votes_count_stances():
    counts = votes([sig("trend", 0.5), sig("risk", -0.5), sig("regime", 0.0), sig("value", 0.0, abstained=True)])
    assert counts == {"bullish": 1, "bearish": 1, "neutral": 1, "abstain": 1}


# ── 규칙 위원회 ───────────────────────────────────────────────────────────────

def test_rules_committee_buys_a_leader_in_a_healthy_market():
    seats, _ = seats_for(leader_market())
    decision = rules_committee.decide_entry(CODE, "테스트전자", seats, "CANSLIM 일봉 요소")
    assert (decision.action, decision.source, decision.status) == ("BUY", "rules", "ok")
    assert decision.conviction in ("high", "very_high")
    assert "CANSLIM" in decision.thesis


def test_rules_committee_holds_below_buy_threshold():
    decision = rules_committee.decide_entry(CODE, "x", [sig("trend", 0.2), sig("regime", 0.1), sig("risk", 0.0)], "VCP")
    assert decision.action == "HOLD"
    assert "못 미칩니다" in decision.thesis


def test_risk_seat_veto_blocks_a_buy_even_with_strong_signals():
    seats = [sig("trend", 1.0), sig("breakout", 1.0), sig("momentum", 1.0), sig("regime", 0.6), sig("risk", -0.7)]
    decision = rules_committee.decide_entry(CODE, "x", seats, "VCP")
    assert decision.action == "HOLD"
    assert "거부권" in decision.thesis


def test_weak_market_blocks_new_buys():
    seats = [sig("trend", 1.0), sig("breakout", 1.0), sig("momentum", 1.0), sig("regime", -0.3), sig("risk", 0.2)]
    assert rules_committee.decide_entry(CODE, "x", seats, "VCP").action == "HOLD"


def test_rules_committee_is_deterministic():
    seats, _ = seats_for(leader_market())
    a = rules_committee.decide_entry(CODE, "x", seats, "t").to_dict()
    b = rules_committee.decide_entry(CODE, "x", seats, "t").to_dict()
    assert a == b


def test_holding_is_sold_on_exit_rule_or_bearish_blend_and_kept_otherwise():
    bullish = [sig("trend", 0.8), sig("regime", 0.5)]
    bearish = [sig("trend", -0.8), sig("regime", -0.5)]
    assert rules_committee.decide_holding(CODE, "x", bullish, ["종가가 50일선 아래"]).action == "SELL"
    assert rules_committee.decide_holding(CODE, "x", bearish, []).action == "SELL"
    assert rules_committee.decide_holding(CODE, "x", bullish, []).action == "HOLD"


# ── AI 심의 ───────────────────────────────────────────────────────────────────

ARGUMENT = {"points": ["트렌드 템플릿 7/7"], "strongest_evidence": "상대강도 100", "weakest_spot": "재무 데이터 없음"}
RISK_OK = {"concerns": ["변동성 보통"], "severity": "low", "veto": False, "size": "three_quarters", "note": "크기 조금 축소"}
FINAL_BUY = {"action": "BUY", "conviction": "high", "size": "full", "tighter_stop": 0, "thesis": "주도주 돌파",
             "key_risks": ["시장 조정"], "invalidation": "50일선 이탈", "dissent": "재무 근거 부족"}


class FakeLlm:
    """역할별로 미리 정한 응답(또는 예외)을 돌려준다."""

    model = "claude-opus-5-5"

    def __init__(self, script: dict) -> None:
        self.script = script
        self.calls: list[dict] = []

    async def complete(self, *, system, shared, task, schema, role):
        self.calls.append({"role": role, "system": system, "shared": shared, "task": task, "schema": schema})
        answer = self.script[role]
        if isinstance(answer, Exception):
            raise answer
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        return LlmResult(text=text, usage=LlmUsage(model=self.model, input_tokens=3_000, output_tokens=500, cache_read_tokens=1_000))


class FakeBudget:
    def __init__(self, exhausted: bool = False) -> None:
        self.exhausted = exhausted
        self.records: list[tuple] = []

    def check(self) -> None:
        if self.exhausted:
            raise LlmError("budget", "하루 AI 예산을 넘었습니다")

    def record(self, role, usage, ok, error) -> None:
        self.records.append((role, usage, ok, error))


def entry_ctx() -> EntryContext:
    market = leader_market()
    seats, results = seats_for(market)
    primary = registry.best_plan(results)
    return EntryContext(
        info=INFO, as_of=date(2026, 11, 13), close=float(market.stocks[CODE].close[-1]), techniques=results,
        primary=primary, seats=seats, regime=compute_regime(market)[-1], plan=primary.plan,
        max_qty={"low": 30, "medium": 40, "high": 50, "very_high": 70}, portfolio={"현금 비중(%)": 100},
    )


def holding_ctx() -> HoldingContext:
    market = leader_market()
    seats, results = seats_for(market)
    close = float(market.stocks[CODE].close[-1])
    position = Position(code=CODE, name="테스트전자", qty=10, avg_price=close * 0.9, opened_on=date(2026, 10, 20),
                        technique="canslim_daily", stop=int(close * 0.85), entry_risk=close * 0.05, days_held=18)
    return HoldingContext(info=INFO, as_of=date(2026, 11, 13), close=close, position=position, seats=seats,
                          regime=compute_regime(market)[-1], pnl_pct=0.11, techniques=results)


async def test_standard_deliberation_runs_bull_bear_risk_then_chair():
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY})
    budget = FakeBudget()
    decision, transcript = await deliberate_entry(entry_ctx(), llm, budget, depth="standard")
    assert [c["role"] for c in llm.calls] == ["bull", "bear", "risk", "chair"]
    assert (decision.action, decision.conviction, decision.source, decision.status) == ("BUY", "high", "ai", "ok")
    assert decision.size_fraction == 0.75  # 위원장 full, 리스크 검토자 three_quarters → 더 작은 쪽
    assert decision.stop is None
    assert [s["role"] for s in transcript.steps] == ["bull", "bear", "risk", "chair"]
    assert [r[0] for r in budget.records] == ["bull", "bear", "risk", "chair"]
    assert all(ok for _, _, ok, _ in budget.records)


async def test_all_calls_share_the_same_system_and_report_prefix_for_caching():
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY})
    await deliberate_entry(entry_ctx(), llm, FakeBudget())
    assert len({c["system"] for c in llm.calls}) == 1
    assert len({c["shared"] for c in llm.calls}) == 1
    assert "강세 논거" in llm.calls[1]["task"]  # 약세 연구원은 강세 논거를 받는다
    assert "리스크 검토" in llm.calls[3]["task"]


async def test_chair_schema_only_allows_buy_or_hold_for_entries():
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY})
    await deliberate_entry(entry_ctx(), llm, FakeBudget())
    assert llm.calls[-1]["schema"]["properties"]["action"]["enum"] == ["BUY", "HOLD"]
    assert llm.calls[-1]["schema"]["additionalProperties"] is False


async def test_risk_reviewer_veto_overrides_a_buy_from_the_chair():
    veto = {**RISK_OK, "veto": True, "severity": "high", "note": "변동성 과다"}
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": veto, "chair": FINAL_BUY})
    decision, _ = await deliberate_entry(entry_ctx(), llm, FakeBudget())
    assert decision.action == "HOLD"
    assert "거부권" in decision.thesis and "변동성 과다" in decision.thesis


async def test_tighter_stop_is_passed_through_for_the_gate_to_validate():
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": {**FINAL_BUY, "tighter_stop": 21_000}})
    decision, _ = await deliberate_entry(entry_ctx(), llm, FakeBudget())
    assert decision.stop == 21_000


@pytest.mark.parametrize(
    ("script_patch", "kind"),
    [({"chair": "이건 JSON이 아닙니다"}, "invalid_output"),
     ({"chair": {"action": "SELL_EVERYTHING"}}, "invalid_output"),
     ({"bear": LlmError("refusal", "거절")}, "refusal"),
     ({"risk": LlmError("timeout", "시간 초과")}, "timeout"),
     ({"bull": LlmError("rate_limit", "한도")}, "rate_limit")],
)
async def test_any_failure_becomes_hold_and_review_never_a_buy(script_patch, kind):
    script = {"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY, **script_patch}
    budget = FakeBudget()
    decision, transcript = await deliberate_entry(entry_ctx(), FakeLlm(script), budget)
    assert (decision.action, decision.status, decision.source) == ("HOLD", "review", "ai")
    assert transcript.error.startswith(kind)
    assert budget.records[-1][2] is False and budget.records[-1][3] == kind


async def test_budget_exhausted_makes_no_call_and_holds():
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY})
    decision, transcript = await deliberate_entry(entry_ctx(), llm, FakeBudget(exhausted=True))
    assert llm.calls == []
    assert (decision.action, decision.status) == ("HOLD", "review")
    assert transcript.error.startswith("budget")


async def test_light_depth_is_one_call_and_deep_is_six():
    script = {"bull": ARGUMENT, "bear": ARGUMENT, "bull_rebuttal": ARGUMENT, "bear_rebuttal": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY}
    light = FakeLlm(script)
    await deliberate_entry(entry_ctx(), light, FakeBudget(), depth="light")
    assert [c["role"] for c in light.calls] == ["chair"]
    deep = FakeLlm(script)
    await deliberate_entry(entry_ctx(), deep, FakeBudget(), depth="deep")
    assert [c["role"] for c in deep.calls] == ["bull", "bear", "bull_rebuttal", "bear_rebuttal", "risk", "chair"]


async def test_transcript_records_tokens_and_cost_per_step():
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": FINAL_BUY})
    _, transcript = await deliberate_entry(entry_ctx(), llm, FakeBudget())
    step_cost = estimate_cost("claude-opus-5-5", 3_000, 500, 1_000)
    assert transcript.steps[0]["cost_usd"] == pytest.approx(step_cost)
    assert transcript.cost_usd == pytest.approx(4 * step_cost)
    assert transcript.to_dict()["depth"] == "standard"


def test_entry_report_states_the_fixed_envelope_and_allowed_actions():
    report = json.loads(build_entry_report(entry_ctx()))
    assert report["대상"]["종목"] == "테스트전자"
    assert report["허용 행동"] == ["BUY", "HOLD"]
    envelope = report["주문 계획(규칙이 계산, 변경 불가 범위)"]
    assert envelope["확신 등급별 최대 수량"]["high"] == 50
    assert envelope["계획 손절가"] > 0
    assert len(report["좌석 의견"]) == 8


def test_anonymised_report_hides_name_code_sector_and_date():
    text = build_entry_report(entry_ctx(), anonymize=True)
    assert "테스트전자" not in text and CODE not in text and "2026-11-13" not in text and "반도체" not in text
    assert "익명 종목" in text


async def test_holding_review_can_sell_or_hold():
    sell = {**FINAL_BUY, "action": "SELL", "thesis": "주도력 약화"}
    llm = FakeLlm({"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": sell})
    decision, _ = await deliberate_holding(holding_ctx(), llm, FakeBudget())
    assert (decision.action, decision.kind, decision.source) == ("SELL", "holding", "ai")
    assert llm.calls[-1]["schema"]["properties"]["action"]["enum"] == ["SELL", "HOLD"]
    assert "보유 현황" in build_holding_report(holding_ctx())


async def test_holding_review_failure_keeps_the_position():
    llm = FakeLlm({"bull": LlmError("api", "서버 오류")})
    decision, _ = await deliberate_holding(holding_ctx(), llm, FakeBudget())
    assert (decision.action, decision.status) == ("HOLD", "review")


# ── 비용·SDK 호출 형태 ────────────────────────────────────────────────────────

def test_cost_estimate_uses_model_prices_and_cache_rates():
    # Opus 5.5: 입력 $4, 출력 $20, 캐시 읽기 $0.20 (100만 토큰당)
    assert estimate_cost("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
    assert estimate_cost("claude-opus-5-5", 0, 1_000_000) == pytest.approx(20.0)
    assert estimate_cost("claude-opus-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.20)
    assert estimate_cost("claude-opus-5-5", 0, 0, cache_write=1_000_000) == pytest.approx(5.0)
    assert estimate_cost("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)


class _FakeMessages:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs: dict | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _sdk_response(text="{}", stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason, model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=800, cache_creation_input_tokens=0),
    )


def _llm_with(fake_beta=None, fake_plain=None, model="claude-opus-5-5") -> AnthropicLlm:
    llm = AnthropicLlm("test-key", model=model, effort="medium")
    llm._client = SimpleNamespace(beta=SimpleNamespace(messages=fake_beta), messages=fake_plain)
    return llm


async def test_opus_request_uses_refusal_fallback_structured_output_and_cache_breakpoint():
    beta = _FakeMessages(_sdk_response('{"ok": true}'))
    llm = _llm_with(fake_beta=beta)
    result = await llm.complete(system="헌장", shared="리포트", task="역할", schema={"type": "object"}, role="chair")
    kw = beta.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert "thinking" not in kw and "temperature" not in kw
    content = kw["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "리포트", "cache_control": {"type": "ephemeral"}}
    assert content[1] == {"type": "text", "text": "역할"}
    assert result.text == '{"ok": true}'
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.cache_read_tokens) == (1200, 300, 800)


async def test_haiku_request_goes_through_the_plain_endpoint_without_fallbacks():
    plain = _FakeMessages(_sdk_response())
    llm = _llm_with(fake_plain=plain, model="claude-haiku-5-5")
    await llm.complete(system="s", shared="r", task="t", schema={}, role="bull")
    assert "fallbacks" not in plain.kwargs and "betas" not in plain.kwargs


@pytest.mark.parametrize(("stop_reason", "kind"), [("refusal", "refusal"), ("max_tokens", "truncated")])
async def test_refusal_and_truncation_raise_typed_errors(stop_reason, kind):
    llm = _llm_with(fake_beta=_FakeMessages(_sdk_response(stop_reason=stop_reason)))
    with pytest.raises(LlmError) as info:
        await llm.complete(system="s", shared="r", task="t", schema={}, role="chair")
    assert info.value.kind == kind
    assert info.value.usage.input_tokens == 1200  # 거절돼도 쓴 토큰은 기록한다


async def test_sdk_timeout_is_mapped_to_a_typed_error():
    import anthropic
    import httpx2

    timeout = anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    llm = _llm_with(fake_beta=_FakeMessages(timeout))
    with pytest.raises(LlmError) as info:
        await llm.complete(system="s", shared="r", task="t", schema={}, role="chair")
    assert info.value.kind == "timeout"


def test_missing_api_key_is_not_configured():
    with pytest.raises(LlmError) as info:
        AnthropicLlm("")
    assert info.value.kind == "not_configured"


def test_unknown_model_falls_back_to_default():
    assert AnthropicLlm("k", model="gpt-something").model == "claude-opus-5-5"


# ── 분기 판단(규칙 + AI 분기) ─────────────────────────────────────────────────

def rules_entry(seats) -> Decision:
    return rules_committee.decide_entry(CODE, "x", seats, "기법")


def final(action: str, conviction: str = "medium", size: str = "full", stop: int = 0) -> FinalCall:
    return FinalCall(action=action, conviction=conviction, size=size, tighter_stop=stop, thesis="AI 근거", key_risks=[],
                     invalidation="", dissent="")


def test_entry_branch_asks_only_when_rules_alone_cannot_tell():
    clear = [sig("trend", 0.8), sig("regime", 0.5), sig("risk", 0.2)]
    assert rules_entry(clear).action == "BUY" and entry_branch(clear, rules_entry(clear)) is None
    borderline = [sig("trend", 0.3), sig("regime", 0.3)]  # 종합 +0.30, 기준 +0.25
    assert "근처" in entry_branch(borderline, rules_entry(borderline))
    split = [sig("trend", 1.0), sig("breakout", 1.0), sig("momentum", 1.0), sig("regime", 0.5), sig("overheat", -0.5),
             sig("value", -0.5), sig("risk", 0.2)]
    assert "의견이 갈립니다" in entry_branch(split, rules_entry(split))
    caution = [sig("trend", 1.0), sig("breakout", 1.0), sig("regime", 0.5), sig("risk", -0.3)]
    assert "리스크 좌석이 경고" in entry_branch(caution, rules_entry(caution))


def test_entry_branch_never_escalates_a_safety_hold():
    weak_market = [sig("trend", 0.6), sig("regime", -0.1)]  # 종합 +0.30으로 경계선이지만 약세장
    vetoed = [sig("trend", 0.9), sig("regime", 0.5), sig("risk", -0.7)]
    for seats in (weak_market, vetoed):
        assert rules_entry(seats).action == "HOLD" and entry_branch(seats, rules_entry(seats)) is None


def test_holding_branch_asks_on_a_loss_without_exit_rule_or_near_the_sell_line():
    strong = [sig("trend", 0.8), sig("regime", 0.5)]
    keep = rules_committee.decide_holding(CODE, "x", strong, [])
    assert "손실 중" in holding_branch(strong, keep, -0.06)
    assert holding_branch(strong, keep, 0.05) is None
    near = [sig("trend", -0.3), sig("regime", -0.3)]  # 종합 -0.30, 기준 -0.25
    assert "매도 기준" in holding_branch(near, rules_committee.decide_holding(CODE, "x", near, []), 0.05)


def test_resolve_follows_claude_toward_less_risk_but_needs_conviction_to_add_risk():
    hold, buy = Decision(CODE, "x", "entry", "HOLD", thesis="규칙"), Decision(CODE, "x", "entry", "BUY", thesis="규칙")
    assert resolve(buy, None)[0] is buy  # 답이 없으면 규칙 결론
    assert resolve(hold, final("BUY", "low"))[0] is hold  # 확신 낮은 매수 전환은 받지 않는다
    flipped, _ = resolve(hold, final("BUY", "medium", "half"))
    assert (flipped.action, flipped.source, flipped.size_fraction) == ("BUY", "ai", 0.5)
    cooled, _ = resolve(buy, final("HOLD", "very_low"))  # 위험을 줄이는 쪽은 확신과 상관없이 따른다
    assert (cooled.action, cooled.source, cooled.thesis) == ("HOLD", "ai", "AI 근거")
    agreed, _ = resolve(buy, final("BUY", "high", "quarter", 9_500))  # 같은 결론이면 줄이는 쪽만 반영
    assert (agreed.source, agreed.thesis, agreed.size_fraction, agreed.stop) == ("rules", "규칙", 0.25, 9_500)
    sell, keep = Decision(CODE, "x", "holding", "SELL"), Decision(CODE, "x", "holding", "HOLD")
    assert resolve(sell, final("HOLD", "low"))[0] is sell
    assert resolve(sell, final("HOLD", "high"))[0].action == "HOLD"
    assert resolve(keep, final("SELL", "low"))[0].action == "SELL"


async def test_second_opinion_makes_one_call_and_records_why_and_what_happened():
    rules = Decision(CODE, "테스트전자", "entry", "BUY", thesis="규칙 매수")
    llm = FakeLlm({"branch": {**FINAL_BUY, "action": "HOLD", "conviction": "low"}})
    budget = FakeBudget()
    decision, transcript = await second_opinion(entry_ctx(), rules, "약세 좌석이 2개라 의견이 갈립니다", llm, budget)
    assert [c["role"] for c in llm.calls] == ["branch"] and len(budget.records) == 1
    assert "약세 좌석이 2개" in llm.calls[0]["task"] and "규칙 매수" in llm.calls[0]["task"]
    assert llm.calls[0]["schema"]["properties"]["action"]["enum"] == ["BUY", "HOLD"]
    assert (decision.action, decision.source) == ("HOLD", "ai")
    branch = transcript.to_dict()["branch"]
    assert branch["adopted"] and (branch["rules_action"], branch["ai_action"]) == ("BUY", "HOLD")

    held = Decision(CODE, "테스트전자", "holding", "HOLD", thesis="보유 유지")
    llm = FakeLlm({"branch": {**FINAL_BUY, "action": "SELL"}})
    decision, _ = await second_opinion(holding_ctx(), held, "손실 중", llm, FakeBudget())
    assert decision.action == "SELL" and llm.calls[0]["schema"]["properties"]["action"]["enum"] == ["SELL", "HOLD"]


async def test_second_opinion_keeps_the_rules_decision_when_claude_gives_no_usable_answer():
    rules = Decision(CODE, "테스트전자", "entry", "BUY", thesis="규칙 매수")
    cases = [
        (FakeLlm({"branch": LlmError("timeout", "시간 초과")}), FakeBudget()),
        (FakeLlm({"branch": "JSON이 아님"}), FakeBudget()),
        (FakeLlm({"branch": FINAL_BUY}), FakeBudget(exhausted=True)),
    ]
    for llm, budget in cases:
        decision, transcript = await second_opinion(entry_ctx(), rules, "의견이 갈립니다", llm, budget)
        assert decision is rules and transcript.error and transcript.branch["adopted"] is False
    assert cases[2][0].calls == []  # 예산을 넘으면 호출하지 않는다
