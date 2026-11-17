"""엔진 서비스 통합 테스트: 샘플 데이터 + 메모리 DB + (필요할 때) 가짜 AI."""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app.backtest.runner import run_backtest
from app.committee.llm import LlmError, LlmResult, LlmUsage
from app.config import Settings
from app.core.clock import kst
from app.data.sample import SampleProvider
from app.data.universe import load_universe
from app.engine import repo
from app.engine import service as service_module
from app.engine.core import EngineConfig
from app.engine.service import (
    CAUGHT_UP_KEY,
    MAINTENANCE_DONE_KEY,
    SCHEDULER_DONE_KEY,
    EngineError,
    EngineService,
    Scheduler,
)
from app.engine.settings import EngineSettings
from app.risk.limits import RiskLimits
from app.store.db import (
    KV,
    AiUsageRow,
    DecisionRow,
    EquityRow,
    IntentRow,
    LedgerRow,
    PositionRow,
    TradeRow,
    make_engine,
    make_session_factory,
)
from tests.helpers import END

ARGUMENT = {"points": ["근거"], "strongest_evidence": "수치", "weakest_spot": "없음"}
RISK_OK = {"concerns": [], "severity": "low", "veto": False, "size": "full", "note": ""}
FINAL_BUY = {"action": "BUY", "conviction": "high", "size": "full", "tighter_stop": 0, "thesis": "AI 매수 근거",
             "key_risks": [], "invalidation": "손절 이탈", "dissent": ""}


class FakeLlm:
    model = "claude-opus-5-5"

    def __init__(self, final=FINAL_BUY, fail: LlmError | None = None) -> None:
        self.final, self.fail, self.calls = final, fail, 0

    async def complete(self, *, system, shared, task, schema, role):
        self.calls += 1
        if self.fail:
            raise self.fail
        answer = {"bull": ARGUMENT, "bear": ARGUMENT, "risk": RISK_OK, "chair": self.final, "branch": self.final}[role]
        return LlmResult(json.dumps(answer, ensure_ascii=False), LlmUsage(self.model, 2_000, 400))


@pytest.fixture(scope="module")
def prepared():
    """일봉을 한 번만 적재한 서비스와, 첫 매수가 일어나는 날짜."""
    stocks = load_universe()[:20]
    mp = pytest.MonkeyPatch()
    mp.setattr(service_module, "load_universe", lambda: stocks)
    mp.setattr(service_module, "universe_map", lambda: {s.code: s for s in stocks})
    config = Settings(_env_file=None, AP_DATA_PROVIDER="sample")
    factory = make_session_factory(make_engine(None))
    svc = EngineService(config, factory, provider=SampleProvider(end=END))
    import asyncio

    asyncio.run(svc.refresh_data())
    backtest = run_backtest(svc.market, svc.regimes, EngineConfig(), initial_cash=30_000_000)
    first_buy = next(f for f in backtest.fills if f.side == "buy")
    decision_day = svc.market.calendar[svc.market.cal_index(first_buy.day) - 1]
    yield svc, factory, decision_day, first_buy
    mp.undo()


@pytest.fixture
def svc(prepared):
    service, factory, decision_day, _ = prepared
    with factory() as s, s.begin():
        for table in (AiUsageRow, DecisionRow, IntentRow, TradeRow, EquityRow, PositionRow):
            s.execute(delete(table))
        s.execute(delete(KV))
    service._llm_factory = None
    service.last_error = ""
    service.kv.save_settings(EngineSettings(decider="rules", state="running"))
    service.kv.save_limits(RiskLimits())
    with factory() as s, s.begin():
        repo.reset_env(s, "sim", 30_000_000)
    service.kv.set("sim_start", decision_day.isoformat())
    return service


def intents(service, **kw) -> list[IntentRow]:
    with service.sf() as s:
        return repo.intents_for(s, "sim", **kw)


def rows(service, table):
    with service.sf() as s:
        return list(s.execute(select(table)).scalars())


# ── 데이터·상태 ───────────────────────────────────────────────────────────────

def test_refresh_builds_market_and_status_reports_it(svc):
    status = svc.status()
    assert status["has_data"] and status["data_day"] == END.isoformat()
    assert status["env"] == "sim" and status["broker"]["kind"] == "paper"
    assert status["regime"]["label"] in ("상승", "중립", "하락")
    assert status["sim_day"] is None


# ── 승인 흐름 ─────────────────────────────────────────────────────────────────

async def test_first_step_only_runs_the_after_close_cycle_and_waits_for_approval(svc, prepared):
    _, _, decision_day, first_buy = prepared
    result = await svc.advance(1)
    assert result[0]["day"] == decision_day.isoformat() and result[0]["fills"] == 0
    pending = intents(svc, statuses=("pending_approval",))
    assert first_buy.code in [r.code for r in pending]  # 자동화 1단계: 모두 승인 대기
    assert all(r.expires_at for r in pending)
    assert svc.status()["pending_approvals"] == len(pending)
    assert rows(svc, TradeRow) == []
    assert any(r.kind == "cycle" for r in svc.ledger.rows(env="sim"))


async def test_approved_intent_is_filled_on_the_next_trading_day(svc, prepared):
    _, _, _, first_buy = prepared
    await svc.advance(1)
    target = next(r for r in intents(svc, statuses=("pending_approval",)) if r.code == first_buy.code)
    svc.decide_intent(target.id, approve=True)
    result = await svc.advance(1)
    assert result[0]["day"] == first_buy.day.isoformat() and result[0]["fills"] >= 1
    trade = next(t for t in rows(svc, TradeRow) if t.code == first_buy.code)
    assert (trade.side, trade.price) == ("buy", first_buy.price)
    fill_row = next(r for r in svc.ledger.rows(env="sim", kinds=["fill_buy"]) if r.code == first_buy.code)
    assert fill_row.cash_after == 30_000_000 - trade.qty * trade.price - trade.fee
    with svc.sf() as s:
        assert first_buy.code in repo.load_portfolio(s, "sim", 30_000_000).positions


async def test_user_actions_in_simulation_are_dated_with_the_simulated_day(svc):
    # 승인·거절 같은 사용자 조작도 시뮬레이션에서는 그때의 시뮬레이션 날짜로 적는다(실제 날짜와 섞이면 순서를 읽기 어렵다).
    done = await svc.advance(1)
    row = intents(svc, statuses=("pending_approval",))[0]
    svc.decide_intent(row.id, approve=True)
    approve_row = svc.ledger.rows(env="sim", kinds=["approve"])[0]
    assert approve_row.day == done[0]["day"]


async def test_unapproved_intent_expires_and_nothing_is_bought(svc):
    await svc.advance(1)
    first_cycle = [r.id for r in intents(svc, statuses=("pending_approval",))]
    assert first_cycle
    await svc.advance(1)
    assert rows(svc, TradeRow) == []
    with svc.sf() as s:
        assert {s.get(IntentRow, i).status for i in first_cycle} == {"expired"}
    assert sum(1 for r in svc.ledger.rows(env="sim") if r.kind == "expire") >= len(first_cycle)


async def test_rejected_intent_is_not_executed(svc, prepared):
    _, _, _, first_buy = prepared
    await svc.advance(1)
    for row in intents(svc, statuses=("pending_approval",)):
        svc.decide_intent(row.id, approve=False, note="테스트 거절")
    await svc.advance(1)
    assert rows(svc, TradeRow) == []
    with pytest.raises(EngineError):
        svc.decide_intent("없는-아이디", approve=True)


async def test_decide_intent_twice_is_refused(svc):
    await svc.advance(1)
    row = intents(svc, statuses=("pending_approval",))[0]
    svc.decide_intent(row.id, approve=True)
    with pytest.raises(EngineError):
        svc.decide_intent(row.id, approve=True)


# ── 자동화 단계 ───────────────────────────────────────────────────────────────

async def test_level_three_approves_automatically_and_level_zero_only_notifies(svc):
    svc.update_settings({"automation_level": 3})
    await svc.advance(1)
    assert intents(svc, statuses=("approved",)) and not intents(svc, statuses=("pending_approval",))

    with svc.sf() as s, s.begin():
        repo.reset_env(s, "sim", 30_000_000)
    svc.update_settings({"automation_level": 0})
    await svc.advance(2)
    assert intents(svc, statuses=("notified",))
    assert rows(svc, TradeRow) == []


async def test_level_two_auto_approves_only_small_orders(svc):
    svc.update_settings({"automation_level": 2, "auto_max_order_value": 1})
    await svc.advance(1)
    assert intents(svc, statuses=("pending_approval",)) and not intents(svc, statuses=("approved",))
    with svc.sf() as s, s.begin():
        repo.reset_env(s, "sim", 30_000_000)
    svc.update_settings({"auto_max_order_value": 1_000_000_000})
    await svc.advance(1)
    assert intents(svc, statuses=("approved",))


async def test_restart_while_running_forces_approval_until_confirmed(svc):
    svc.update_settings({"automation_level": 3})
    svc.startup()  # 가동 중에 프로세스가 다시 뜬 상황
    assert svc.status()["resume_check_required"]
    await svc.advance(1)
    assert intents(svc, statuses=("pending_approval",)) and not intents(svc, statuses=("approved",))
    svc.confirm_resume()
    assert not svc.status()["resume_check_required"]


# ── 재생·원장 ─────────────────────────────────────────────────────────────────

async def test_replay_with_auto_approve_trades_and_keeps_a_valid_ledger(svc):
    results = await svc.advance(25, auto_approve=True)
    assert len(results) == 25
    trades = rows(svc, TradeRow)
    assert any(t.side == "buy" for t in trades)
    equity = rows(svc, EquityRow)
    assert len(equity) == 25 and all(e.cash >= 0 for e in equity)
    assert equity[0].benchmark == pytest.approx(30_000_000)
    assert svc.ledger.verify() == (True, None)
    assert svc.status()["behind_days"] >= 0


async def test_cannot_advance_past_the_latest_bar(svc, prepared):
    svc.kv.set("sim_start", END.isoformat())
    await svc.advance(1)
    with pytest.raises(EngineError):
        await svc.advance(1)


# ── AI 판단 ───────────────────────────────────────────────────────────────────

async def test_ai_mode_without_api_key_creates_no_buy_intent(svc):
    svc.update_settings({"decider": "ai", "automation_level": 3})
    await svc.advance(1)
    assert [r for r in intents(svc) if r.side == "buy"] == []
    decisions = rows(svc, DecisionRow)
    assert decisions and all(d.status == "review" for d in decisions if d.kind == "entry")
    assert any("판단 보류" in r.summary for r in svc.ledger.rows(env="sim"))


async def test_ai_mode_with_working_llm_creates_intents_and_records_cost(svc):
    fake = FakeLlm()
    svc._llm_factory = lambda st: fake
    svc.update_settings({"decider": "ai", "automation_level": 3})
    await svc.advance(1)
    assert [r for r in intents(svc, statuses=("approved",)) if r.side == "buy"]
    usage = rows(svc, AiUsageRow)
    assert len(usage) == fake.calls and fake.calls % 4 == 0  # 종목당 4회(강세·약세·리스크·위원장)
    assert svc.status()["ai"]["spent_today_usd"] > 0
    decision = next(d for d in rows(svc, DecisionRow) if d.action == "BUY")
    body = json.loads(decision.body)
    assert body["transcript"]["steps"][-1]["role"] == "chair" and decision.cost_usd > 0


async def test_ai_budget_exhausted_blocks_calls_and_buys(svc):
    fake = FakeLlm()
    svc._llm_factory = lambda st: fake
    svc.update_settings({"decider": "ai", "automation_level": 3, "ai_daily_budget_usd": 0})
    await svc.advance(1)
    assert fake.calls == 0
    assert [r for r in intents(svc) if r.side == "buy"] == []


async def test_ai_failure_blocks_buys(svc):
    svc._llm_factory = lambda st: FakeLlm(fail=LlmError("timeout", "시간 초과"))
    svc.update_settings({"decider": "ai", "automation_level": 3})
    await svc.advance(1)
    assert [r for r in intents(svc) if r.side == "buy"] == []
    assert all(not u.ok for u in rows(svc, AiUsageRow))


# ── 규칙 + AI 분기 ────────────────────────────────────────────────────────────

async def test_hybrid_mode_asks_claude_at_a_branch_and_applies_its_answer(svc, monkeypatch):
    fake = FakeLlm(final={**FINAL_BUY, "action": "HOLD", "conviction": "low", "thesis": "AI 보류 근거"})
    svc._llm_factory = lambda st: fake
    monkeypatch.setattr(service_module, "entry_branch", lambda seats, rules: "테스트 분기" if rules.action == "BUY" else None)
    svc.update_settings({"decider": "hybrid", "automation_level": 3})
    await svc.advance(1)
    flipped = [d for d in rows(svc, DecisionRow) if d.source == "ai"]
    assert fake.calls == len(flipped) >= 1 and len(rows(svc, AiUsageRow)) == fake.calls  # 분기마다 한 번만 묻는다
    assert [r for r in intents(svc) if r.side == "buy"] == []  # 규칙은 매수였지만 AI 답을 반영해 보류
    assert all(d.action == "HOLD" and json.loads(d.body)["transcript"]["branch"]["adopted"] for d in flipped)
    assert any("AI 분기 판단 · 테스트 분기" in r.summary for r in svc.ledger.rows(env="sim"))


async def test_hybrid_mode_makes_no_calls_when_nothing_is_a_branch(svc, monkeypatch):
    fake = FakeLlm()
    svc._llm_factory = lambda st: fake
    monkeypatch.setattr(service_module, "entry_branch", lambda seats, rules: None)
    svc.update_settings({"decider": "hybrid", "automation_level": 3})
    await svc.advance(1)
    assert fake.calls == 0 and [r for r in intents(svc, statuses=("approved",)) if r.side == "buy"]


@pytest.mark.parametrize("llm", [None, FakeLlm(fail=LlmError("timeout", "시간 초과"))], ids=["no_key", "timeout"])
async def test_hybrid_mode_falls_back_to_the_rules_decision_when_claude_is_unavailable(svc, monkeypatch, llm):
    svc._llm_factory = (lambda st: llm) if llm else None
    monkeypatch.setattr(service_module, "entry_branch", lambda seats, rules: "테스트 분기")
    svc.update_settings({"decider": "hybrid", "automation_level": 3})
    await svc.advance(1)
    assert [r for r in intents(svc, statuses=("approved",)) if r.side == "buy"]  # AI 없이도 규칙 결론대로 매수
    assert all(d.source == "rules" for d in rows(svc, DecisionRow))
    summaries = [r.summary for r in svc.ledger.rows(env="sim")]
    assert any(("건너뛰고 규칙 결론" if llm is None else "AI 답을 받지 못해") in s for s in summaries)


# ── 정지 제어 ─────────────────────────────────────────────────────────────────

async def test_pause_stops_new_buys_but_keeps_running_the_cycle(svc):
    svc.update_settings({"automation_level": 3})
    svc.pause()
    await svc.advance(1)
    assert [r for r in intents(svc, statuses=("approved", "pending_approval")) if r.side == "buy"] == []
    assert any(r.kind == "cycle" and "장후 심의" in r.summary for r in svc.ledger.rows(env="sim"))


async def test_stop_cancels_open_intents_and_skips_the_committee(svc):
    svc.update_settings({"automation_level": 3})
    await svc.advance(1)
    assert intents(svc, statuses=("approved",))
    result = svc.stop()
    assert result["cancelled"] >= 1 and svc.status()["state"] == "stopped"
    assert intents(svc, statuses=("approved", "pending_approval")) == []
    await svc.advance(1)
    assert rows(svc, TradeRow) == []
    assert any("건너뜁니다" in r.summary for r in svc.ledger.rows(env="sim"))


async def test_liquidate_sells_every_position_on_the_next_trading_day(svc):
    await svc.advance(12, auto_approve=True)
    with svc.sf() as s:
        held = set(repo.load_portfolio(s, "sim", 30_000_000).positions)
    if not held:
        pytest.skip("이 구간에는 보유 종목이 없습니다")
    result = svc.liquidate()
    assert result["sell_intents"] == len(held)
    await svc.advance(1)
    with svc.sf() as s:
        assert repo.load_portfolio(s, "sim", 30_000_000).positions == {}
    assert sum(1 for t in rows(svc, TradeRow) if t.reason == "liquidate") == len(held)


def test_start_requires_data(prepared):
    service, factory, _, _ = prepared
    empty = EngineService(service.config, make_session_factory(make_engine(None)), provider=SampleProvider(end=END))
    with pytest.raises(EngineError):
        empty.start()


# ── 설정 ─────────────────────────────────────────────────────────────────────

def test_settings_patch_is_validated_and_cannot_touch_protected_fields(svc):
    updated = svc.update_settings({"max_candidates": 5, "env": "live", "state": "stopped"})
    assert updated.max_candidates == 5 and updated.env == "sim" and updated.state == "running"
    with pytest.raises(ValueError):
        svc.update_settings({"ai_model": "not-a-model"})
    with pytest.raises(ValueError):
        svc.update_settings({"enabled_techniques": ["martingale"]})
    assert any(r.kind == "settings" for r in svc.ledger.rows(env="sim"))


def test_limit_changes_report_what_got_looser(svc):
    _, loosened = svc.update_limits({"max_position_pct": 0.2, "max_positions": 4})
    assert loosened == ["max_position_pct"]
    assert svc.limits().max_positions == 4
    with pytest.raises(ValueError):
        svc.update_limits({"max_position_pct": 5})


def test_sim_reset_clears_account_and_stops_engine(svc):
    info = svc.sim_reset(start=date(2026, 9, 1), initial_cash=50_000_000)
    assert info == {"start": "2026-09-01", "initial_cash": 50_000_000}
    status = svc.status()
    assert status["state"] == "stopped" and status["sim_day"] is None and status["risk"]["equity"] == 50_000_000


# ── 스케줄러 ──────────────────────────────────────────────────────────────────

async def test_scheduler_does_nothing_before_close_or_on_holidays(svc):
    calls = []

    async def fake_refresh():
        calls.append("refresh")

    svc.refresh_data = fake_refresh  # type: ignore[method-assign]
    scheduler = Scheduler(svc)
    await scheduler.tick(kst(2026, 11, 13, 10, 0))  # 장중
    await scheduler.tick(kst(2026, 11, 15, 16, 0))  # 일요일
    assert calls == []
    await scheduler.tick(kst(2026, 11, 13, 15, 50))  # 그날 봉이 들어왔다
    await scheduler.tick(kst(2026, 11, 13, 16, 30))  # 같은 날 두 번 갱신하지 않는다
    assert calls == ["refresh"]
    assert Scheduler(svc)._service.kv.get(SCHEDULER_DONE_KEY) == "2026-11-13"  # 재시작해도 같은 날 다시 하지 않는다
    del svc.refresh_data


def _events_since(svc, seq: int, kind: str) -> list[str]:
    with svc.sf() as s:
        return list(s.execute(select(LedgerRow.summary).where(LedgerRow.seq > seq, LedgerRow.kind == kind)).scalars())


async def test_scheduler_retries_until_the_days_bars_arrive_then_gives_up_loudly(svc):
    calls = []

    async def flaky_refresh():
        calls.append("refresh")
        if len(calls) == 1:
            raise ConnectionError("네이버 응답 없음")

    svc.refresh_data = flaky_refresh  # type: ignore[method-assign]
    start = svc.ledger.last_seq("sim")
    scheduler = Scheduler(svc)
    await scheduler.tick(kst(2026, 11, 16, 15, 50))  # 갱신 실패
    await scheduler.tick(kst(2026, 11, 16, 15, 55))  # 다시 시도할 때가 아직 아니다
    await scheduler.tick(kst(2026, 11, 16, 16, 6))  # 갱신은 됐지만 11-16 봉이 없다
    assert calls == ["refresh", "refresh"]
    warnings = _events_since(svc, start, "data")
    assert len(warnings) == 1 and "다시 시도" in warnings[0]  # 경고는 하루 한 번만

    await scheduler.tick(kst(2026, 11, 16, 23, 5))  # 끝내 못 받으면 멈추고 오류를 남긴다
    await scheduler.tick(kst(2026, 11, 16, 23, 30))
    assert len(calls) == 3
    errors = _events_since(svc, start, "error")
    assert len(errors) == 1 and "2026-11-16" in errors[0] and "직접 진행" in errors[0]
    del svc.refresh_data


async def _place_sim_behind(svc, behind: int) -> str:
    calendar = svc.market.calendar
    svc.kv.set("sim_start", calendar[-1 - behind].isoformat())
    await svc.advance(1)
    sim_day, lag = svc.sim_lag()
    assert lag == behind
    return sim_day


async def _noop_refresh():
    return None


async def test_scheduler_catches_up_days_missed_while_the_server_was_down(svc):
    sim_day = await _place_sim_behind(svc, 3)
    svc.kv.set(CAUGHT_UP_KEY, sim_day)  # 서버가 멈추기 전에는 최신을 따라가고 있었다
    svc.refresh_data = _noop_refresh  # type: ignore[method-assign]
    start = svc.ledger.last_seq("sim")
    await Scheduler(svc).tick(kst(2026, 11, 13, 16, 0))
    assert svc.sim_lag() == ("2026-11-13", 0)
    assert svc.kv.get(CAUGHT_UP_KEY) == "2026-11-13"
    assert any("밀린 3거래일" in e for e in _events_since(svc, start, "engine"))
    del svc.refresh_data


async def test_scheduler_leaves_a_historical_replay_to_the_user(svc):
    sim_day = await _place_sim_behind(svc, 3)  # 따라가던 표시가 없다 = 과거 구간 재생 중
    svc.refresh_data = _noop_refresh  # type: ignore[method-assign]
    await Scheduler(svc).tick(kst(2026, 11, 13, 16, 0))
    assert svc.sim_lag() == (sim_day, 3)
    del svc.refresh_data


async def test_scheduler_does_not_auto_replay_a_long_outage(svc):
    sim_day = await _place_sim_behind(svc, Scheduler.MAX_CATCH_UP + 2)
    svc.kv.set(CAUGHT_UP_KEY, sim_day)
    svc.refresh_data = _noop_refresh  # type: ignore[method-assign]
    start = svc.ledger.last_seq("sim")
    await Scheduler(svc).tick(kst(2026, 11, 13, 16, 0))
    assert svc.sim_lag() == (sim_day, Scheduler.MAX_CATCH_UP + 2)
    assert any("이어서 진행" in e for e in _events_since(svc, start, "engine"))
    del svc.refresh_data


async def test_daily_maintenance_runs_once_and_its_failure_does_not_stop_trading(svc):
    runs = []

    def maintenance(now):
        runs.append(now)
        return {"backup": "alphapilot-daily-x.db", "sessions": 2, "login_attempts": 1, "integrity": "ok"}

    svc.refresh_data = _noop_refresh  # type: ignore[method-assign]
    start = svc.ledger.last_seq("sim")
    scheduler = Scheduler(svc, maintenance=maintenance)
    await scheduler.tick(kst(2026, 11, 13, 16, 0))
    await scheduler.tick(kst(2026, 11, 13, 17, 0))
    assert len(runs) == 1
    assert any("일일 DB 점검" in e and "alphapilot-daily-x.db" in e for e in _events_since(svc, start, "engine"))

    def broken(now):
        raise OSError("디스크 가득 참")

    svc.kv.set(SCHEDULER_DONE_KEY, None)
    svc.kv.set(MAINTENANCE_DONE_KEY, None)
    await Scheduler(svc, maintenance=broken).tick(kst(2026, 11, 13, 18, 0))
    assert any("디스크 가득 참" in e for e in _events_since(svc, start, "error"))
    del svc.refresh_data


async def test_scheduler_health_reports_a_stalled_or_dead_loop(svc):
    import asyncio

    now = kst(2026, 11, 17, 12, 0)
    scheduler = Scheduler(svc)
    assert scheduler.health(now) == (True, "off")
    alive = asyncio.get_running_loop().create_future()
    scheduler._task = alive  # type: ignore[assignment]
    assert scheduler.health(now) == (True, "starting")
    scheduler.tick_started = scheduler.tick_finished = now - timedelta(minutes=1)
    assert scheduler.health(now) == (True, "ok")
    assert scheduler.health(now + timedelta(minutes=10)) == (False, "stale")
    scheduler.tick_started = now - timedelta(minutes=30)
    scheduler.tick_finished = now - timedelta(minutes=31)
    assert scheduler.health(now) == (True, "busy")
    assert scheduler.health(now + timedelta(minutes=40)) == (False, "stuck")
    alive.cancel()
    assert scheduler.health(now) == (False, "dead")
    scheduler._task = None


async def test_stopping_lets_a_running_tick_finish_but_cuts_a_hung_one(svc):
    import asyncio

    finished = []

    async def slow_tick(now):
        await asyncio.sleep(0.2)
        finished.append(now)

    scheduler = Scheduler(svc, interval=3600)
    scheduler.tick = slow_tick  # type: ignore[method-assign]
    scheduler.start()
    await asyncio.sleep(0.05)  # 틱이 도는 중에 끈다
    await scheduler.stop()
    assert len(finished) == 1 and scheduler.health(kst(2026, 11, 17, 12, 0)) == (True, "off")

    async def hung_tick(now):
        await asyncio.sleep(3600)

    stuck = Scheduler(svc, interval=3600)
    stuck.tick = hung_tick  # type: ignore[method-assign]
    stuck.start()
    await asyncio.sleep(0.01)
    await stuck.stop(grace=0.1)
    assert stuck._task is None


def test_startup_repairs_settings_saved_by_an_older_version(svc):
    raw = EngineSettings(decider="rules", state="stopped").model_dump()
    svc.kv.set("engine_settings", {**raw, "ai_model": "claude-retired-1"})
    start = svc.ledger.last_seq("sim")
    svc.startup()
    assert svc.kv.get("engine_settings")["ai_model"] == EngineSettings().ai_model
    assert svc.settings().decider == "rules"
    assert any("ai_model" in e for e in _events_since(svc, start, "settings"))
