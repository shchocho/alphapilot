"""엔진 서비스: 코어 로직에 DB·원장·AI·자동화 단계·정지 제어를 붙인다.

1차 범위에서 실제로 주문을 실행하는 환경은 가상 계좌(sim)뿐이다. 키움 모의·실전 환경은
연결 테스트(토큰 발급·잔고 조회)까지만 제공하고, 실제 주문 실행기는 키를 받은 뒤
모의투자 도메인에서 검증하며 붙인다(그 전에는 mock·live로 전환할 수 없다).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.committee.deliberation import deliberate_entry, deliberate_holding
from app.committee.llm import AnthropicLlm, LlmClient, LlmError, LlmUsage
from app.config import Settings
from app.core import clock
from app.core.models import Decision, Intent
from app.data.naver import NaverProvider
from app.data.provider import INDEX_CODES, DailyBarProvider
from app.data.sample import SampleProvider
from app.data.store import BarStore, RefreshReport, refresh_bars
from app.data.universe import load_universe, universe_map
from app.engine import repo
from app.engine.core import (
    CycleDraft,
    EngineConfig,
    EntryPrefilter,
    Event,
    finalize_cycle,
    prepare_cycle,
    rules_decisions,
)
from app.engine.settings import AUTOMATION_LABELS, ENV_LABELS, STATE_LABELS, EngineSettings, KVStore
from app.engine.sim import end_of_day, execute_day
from app.indicators.features import Market, build_market
from app.journal.ledger import Ledger
from app.regime.regime import RegimeState, compute_regime
from app.risk.limits import RiskLimits
from app.store.db import AccountRow, AiUsageRow, EquityRow, IntentRow

log = logging.getLogger(__name__)

FILL_SUMMARY = {
    "entry_open": "시가 매수", "entry_trigger": "돌파 매수", "entry_vb": "변동성 돌파 매수",
    "stop": "손절", "trail_stop": "추적 손절", "target": "목표가 익절", "next_open_exit": "다음 날 시가 청산",
    "time_exit": "보유 기간 만료 청산", "rule_exit": "청산 규칙 매도", "committee_sell": "위원회 매도",
    "liquidate": "전량 매도", "manual": "수동 주문",
}
LEDGER_EPOCH_KEY = "ledger_epoch:sim"
PROTECTIVE_REASONS = frozenset({"stop", "trail_stop", "target", "next_open_exit", "time_exit"})


class EngineError(RuntimeError):
    """사용자에게 그대로 보여줄 수 있는 엔진 오류."""


class EventBus:
    """화면에 실시간으로 알릴 이벤트(SSE)."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, kind: str, data: dict[str, Any] | None = None) -> None:
        message = {"kind": kind, "data": data or {}}
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(message)


class BudgetGuard:
    """AI 하루 예산. 넘으면 호출을 막고(→ 판단 보류), 모든 호출의 토큰·추정 비용을 기록한다."""

    def __init__(self, session_factory: sessionmaker[Session], env: str, daily_budget_usd: float,
                 today: Callable[[], date] = lambda: clock.now_kst().date()) -> None:
        self._sf = session_factory
        self._env = env
        self._budget = daily_budget_usd
        self._today = today

    def spent_today(self) -> float:
        with self._sf() as s:
            total = s.execute(select(func.coalesce(func.sum(AiUsageRow.cost_usd), 0.0)).where(AiUsageRow.day == self._today().isoformat())).scalar_one()
        return float(total)

    def check(self) -> None:
        if self.spent_today() >= self._budget:
            raise LlmError("budget", f"하루 AI 예산 ${self._budget:.2f}을 다 썼습니다")

    def record(self, role: str, usage: LlmUsage | None, ok: bool, error: str) -> None:
        with self._sf() as s, s.begin():
            s.add(AiUsageRow(
                ts=clock.now_kst().isoformat(timespec="seconds"), day=self._today().isoformat(), env=self._env, role=role,
                model=usage.model if usage else "", input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0, cache_read_tokens=usage.cache_read_tokens if usage else 0,
                cost_usd=usage.cost_usd if usage else 0.0, ok=ok, error=error,
            ))


class EngineService:
    def __init__(
        self,
        config: Settings,
        session_factory: sessionmaker[Session],
        *,
        provider: DailyBarProvider | None = None,
        llm_factory: Callable[[EngineSettings], LlmClient] | None = None,
    ) -> None:
        self.config = config
        self.sf = session_factory
        self.kv = KVStore(session_factory)
        self.store = BarStore(session_factory)
        self.ledger = Ledger(session_factory)
        self.bus = EventBus()
        self.provider: DailyBarProvider = provider or (SampleProvider() if config.data_provider == "sample" else NaverProvider())
        self.market: Market | None = None
        self.regimes: list[RegimeState] = []
        self._prefilter: tuple[tuple, EntryPrefilter] | None = None
        self._llm_factory = llm_factory
        self._lock = asyncio.Lock()
        self.busy: str = ""
        self.last_error: str = ""
        self.data_refreshed_at: str | None = None

    # ── 설정 ───────────────────────────────────────────────────────────────

    def settings(self) -> EngineSettings:
        return self.kv.load_settings()

    def limits(self) -> RiskLimits:
        return self.kv.load_limits()

    def update_settings(self, patch: dict[str, Any]) -> EngineSettings:
        current = self.settings()
        protected = {"env", "state", "resume_check_required"}
        changed = {k: v for k, v in patch.items() if k not in protected and getattr(current, k, None) != v}
        updated = EngineSettings.model_validate({**current.model_dump(), **changed})
        if changed:
            self.kv.save_settings(updated)
            self._log(updated.env, Event("settings", "설정 변경: " + ", ".join(sorted(changed)), payload={"changed": changed}))
        return updated

    def update_limits(self, patch: dict[str, Any]) -> tuple[RiskLimits, list[str]]:
        """(새 한도, 느슨해진 항목). 느슨해지는 변경은 호출한 쪽(API)이 재인증을 요구한다."""
        current = self.limits()
        updated = RiskLimits.model_validate({**current.model_dump(), **patch})
        loosened = updated.is_looser_than(current)
        changed = {k: v for k, v in updated.model_dump().items() if getattr(current, k) != v}
        if changed:
            self.kv.save_limits(updated)
            self._log(self.settings().env, Event("settings", "리스크 한도 변경: " + ", ".join(sorted(changed)),
                                                 payload={"changed": changed, "before": {k: getattr(current, k) for k in changed}}))
        return updated, loosened

    def engine_config(self, st: EngineSettings | None = None) -> EngineConfig:
        st = st or self.settings()
        return EngineConfig(limits=self.limits(), costs=st.cost_model(), enabled_techniques=tuple(st.enabled_techniques),
                            max_candidates=st.max_candidates)

    def _holidays(self, st: EngineSettings) -> frozenset[date]:
        out = set()
        for text in st.extra_holidays:
            with contextlib.suppress(ValueError):
                out.add(date.fromisoformat(text))
        return frozenset(out)

    # ── 데이터 ─────────────────────────────────────────────────────────────

    def load_market(self) -> bool:
        """캐시된 일봉으로 시장 객체를 만든다. 지수 봉이 없으면 False."""
        codes = [s.code for s in load_universe()]
        bars = self.store.load_many(codes)
        index_bars = {c: frame for c in INDEX_CODES if not (frame := self.store.load(c)).empty}
        if "KOSPI" not in index_bars or not bars:
            return False
        self.market = build_market(bars, index_bars, universe_map(), source=self.provider.name)
        self.regimes = compute_regime(self.market)
        self._prefilter = None
        return True

    async def refresh_data(self) -> RefreshReport:
        async with self._lock:
            self.busy = "일봉을 갱신하고 있습니다"
            self.bus.publish("status")
            try:
                codes = [s.code for s in load_universe()] + list(INDEX_CODES)
                report = await asyncio.to_thread(refresh_bars, self.provider, self.store, codes)
                await asyncio.to_thread(self.load_market)
                self.data_refreshed_at = clock.now_kst().isoformat(timespec="seconds")
                summary = f"일봉 갱신: 새 봉 {len(report.updated)}종목, 변동 없음 {len(report.unchanged)}, 실패 {len(report.failed)}"
                if report.refetched:
                    summary += f", 수정주가 재수신 {len(report.refetched)}"
                self._log(self.settings().env, Event("data", summary, payload={"failed": report.failed, "source": self.provider.name}))
                return report
            finally:
                self.busy = ""
                self.bus.publish("status")

    def prefilter(self, cfg: EngineConfig) -> EntryPrefilter:
        assert self.market is not None
        key = (id(self.market), cfg.params, cfg.enabled_techniques)
        if self._prefilter is None or self._prefilter[0] != key:
            self._prefilter = (key, EntryPrefilter(self.market, cfg.params, cfg.enabled_techniques))
        return self._prefilter[1]

    # ── 원장 ───────────────────────────────────────────────────────────────

    def _log(self, env: str, event: Event, *, day: date | None = None, cash_after: int | None = None) -> int:
        day_text = day.isoformat() if day else None
        if day_text is None and env == "sim":
            # 시뮬레이션에서 사용자가 한 조작(승인·거절·설정)은 그때의 시뮬레이션 날짜로 적는다. 읽기만 한다(쓰기 잠금을 잡지 않는다).
            with self.sf() as s:
                day_text = s.execute(select(AccountRow.sim_day).where(AccountRow.env == "sim")).scalar_one_or_none()
        seq = self.ledger.append(env=env, kind=event.kind, summary=event.summary, day=day_text,
                                 chain_id=event.chain_id, code=event.code, name=event.name, qty=event.qty, amount=event.amount,
                                 cash_after=cash_after, payload=event.payload)
        self.bus.publish("ledger", {"seq": seq, "kind": event.kind})
        return seq

    # ── 엔진 제어 ──────────────────────────────────────────────────────────

    def startup(self) -> None:
        """프로세스 시작 시 호출. 가동 중에 꺼졌다 켜졌으면 안전한 쪽(승인 대기)으로 돌린다."""
        st = self.settings()
        self.load_market()
        if st.state == "running" and not st.resume_check_required:
            st.resume_check_required = True
            self.kv.save_settings(st)
            self._log(st.env, Event("engine", "재시작을 감지했습니다. 확인하기 전까지 모든 주문을 승인 대기로 돌립니다"))

    def _set_state(self, state: str, summary: str, **changes: Any) -> EngineSettings:
        st = self.settings()
        st.state = state  # type: ignore[assignment]
        for key, value in changes.items():
            setattr(st, key, value)
        self.kv.save_settings(st)
        self._log(st.env, Event("engine", summary, payload={"state": state}))
        self.bus.publish("status")
        return st

    def start(self) -> EngineSettings:
        if self.market is None:
            raise EngineError("일봉 데이터가 없습니다. 먼저 데이터를 갱신하세요")
        return self._set_state("running", "엔진 가동", resume_check_required=False)

    def confirm_resume(self) -> EngineSettings:
        st = self.settings()
        st.resume_check_required = False
        self.kv.save_settings(st)
        self._log(st.env, Event("engine", f"재시작 점검 확인: 자동화 단계 '{AUTOMATION_LABELS[st.automation_level]}'로 돌아갑니다"))
        self.bus.publish("status")
        return st

    def pause(self) -> EngineSettings:
        return self._set_state("paused", "일시정지: 새 매수를 멈춥니다. 미체결·보유·보호 청산은 그대로 둡니다")

    def stop(self) -> dict[str, Any]:
        """정지: 새 주문을 멈추고 실행 전 주문 계획을 모두 취소한다. 보유와 보호 청산은 유지한다."""
        st = self._set_state("stopped", "정지: 새 주문을 멈추고 실행 전 주문 계획을 취소합니다. 보유와 보호 청산은 유지합니다")
        cancelled = self._cancel_open_intents(st.env, "정지로 취소")
        return {"state": st.state, "cancelled": cancelled}

    def liquidate(self) -> dict[str, Any]:
        """전량 매도 후 정지: 정지 처리 뒤 모든 보유 종목의 매도 계획을 다음 거래일 시가로 만든다."""
        result = self.stop()
        st = self.settings()
        created = 0
        with self.sf() as s, s.begin():
            portfolio = repo.load_portfolio(s, st.env, st.sim_initial_cash)
            account = repo.get_account(s, st.env, st.sim_initial_cash)
            base = date.fromisoformat(account.sim_day) if account.sim_day else clock.now_kst().date()
            trade_date = self._next_day(base, st)
            for pos in portfolio.positions.values():
                intent = Intent(id=f"{base:%y%m%d}-{pos.code}-liq", chain_id=pos.chain_id or f"{base:%y%m%d}-{pos.code}", created_on=base,
                                trade_date=trade_date, code=pos.code, name=pos.name, side="sell", qty=pos.qty, status="approved",
                                source="liquidate", technique=pos.technique, reason="전량 매도 후 정지", sector=pos.sector)
                repo.upsert_intent(s, st.env, intent)
                created += 1
        self._log(st.env, Event("engine", f"전량 매도 예약: {created}종목을 다음 거래일({trade_date}) 시가에 매도합니다", payload={"count": created}))
        return {**result, "sell_intents": created, "trade_date": trade_date.isoformat()}

    def _cancel_open_intents(self, env: str, note: str) -> int:
        events: list[Event] = []
        with self.sf() as s, s.begin():
            rows = repo.intents_for(s, env, statuses=("pending_approval", "approved"))
            for row in rows:
                if row.side == "sell" and '"source": "liquidate"' in row.body:
                    continue
                row.status = "cancelled"
                row.decided_at = clock.now_kst().isoformat(timespec="seconds")
                events.append(Event("expire", f"{note}: {'매수' if row.side == 'buy' else '매도'} 계획 {row.qty}주", row.code, row.name, row.chain_id, qty=row.qty))
        for event in events:
            self._log(env, event)
        return len(events)

    # ── 환경 전환 ──────────────────────────────────────────────────────────

    live_runner_available = False  # 키움 주문 실행기: 모의투자 도메인 검증 뒤에 켠다
    LIVE_CONFIRM_PHRASE = "실전 매매를 시작합니다"

    def switch_env(self, target: str, confirm: str = "") -> EngineSettings:
        """환경 전환. 실전은 키·서버 잠금 해제·확인 문구가 모두 있어야 한다(재인증은 API 계층이 확인)."""
        st = self.settings()
        if target not in ENV_LABELS:
            raise EngineError("알 수 없는 환경입니다")
        if target == st.env:
            return st
        if target != "sim":
            if not self.config.has_kiwoom_keys(target):  # type: ignore[arg-type]
                raise EngineError(f"키움 {ENV_LABELS[target]} 앱키가 서버에 설정되지 않았습니다")
            if target == "live":
                if not self.config.allow_live_trading:
                    raise EngineError("서버 환경변수 ALLOW_LIVE_TRADING=true가 없어 실전으로 전환할 수 없습니다")
                if confirm.strip() != self.LIVE_CONFIRM_PHRASE:
                    raise EngineError("확인 문구가 일치하지 않습니다")
            if not self.live_runner_available:
                raise EngineError("키움 주문 실행기는 모의투자 도메인에서 검증한 뒤 켜집니다. 지금은 연결 테스트까지만 할 수 있습니다")
        previous = st.env
        st.env = target  # type: ignore[assignment]
        st.state = "stopped"
        st.automation_level = min(st.automation_level, 1)  # 환경이 바뀌면 승인 단계부터 다시 시작한다
        self.kv.save_settings(st)
        self._log(target, Event("engine", f"환경 전환: {ENV_LABELS[previous]} → {ENV_LABELS[target]} (엔진 정지, 자동화 '모두 승인' 이하로)"))
        self.bus.publish("status")
        return st

    # ── 승인 ───────────────────────────────────────────────────────────────

    def decide_intent(self, intent_id: str, approve: bool, note: str = "") -> dict[str, Any]:
        st = self.settings()
        with self.sf() as s, s.begin():
            row = s.get(IntentRow, intent_id)
            if row is None or row.env != st.env:
                raise EngineError("주문 계획을 찾을 수 없습니다")
            if row.status != "pending_approval":
                raise EngineError(f"승인 대기 상태가 아닙니다(현재: {row.status})")
            row.status = "approved" if approve else "rejected"
            row.decided_at = clock.now_kst().isoformat(timespec="seconds")
            side = "매수" if row.side == "buy" else "매도"
            summary = f"{side} {row.qty}주 {'승인' if approve else '거절'}" + (f" · {note}" if note else "")
            event = Event("approve" if approve else "reject", summary, row.code, row.name, row.chain_id, qty=row.qty)
            data = repo.intent_to_dict(row)
        self._log(st.env, event)
        self.bus.publish("status")
        return data

    # ── 시뮬레이션 진행 ────────────────────────────────────────────────────

    def _next_day(self, day: date, st: EngineSettings) -> date:
        if self.market is not None:
            t = self.market.cal_index(day)
            if t is not None and t + 1 < len(self.market.calendar):
                return self.market.calendar[t + 1]
        return clock.next_trading_day(day, self._holidays(st))

    def sim_reset(self, start: date | None = None, initial_cash: int | None = None) -> dict[str, Any]:
        st = self.settings()
        if initial_cash is not None:
            st = self.update_settings({"sim_initial_cash": initial_cash})
        with self.sf() as s, s.begin():
            repo.reset_env(s, "sim", st.sim_initial_cash)
        self.kv.set("sim_start", start.isoformat() if start else None)
        # 원장은 지우지 않는다. 대신 "이번 실행은 여기서부터"라는 경계를 남겨, 화면과 판단 사슬에 지난 실행의 줄이 섞이지 않게 한다.
        self.kv.set(LEDGER_EPOCH_KEY, self.ledger.last_seq("sim"))
        self._set_state("stopped", f"시뮬레이션 초기화: 시작 자금 {st.sim_initial_cash:,}원" + (f", 시작일 {start}" if start else ""))
        return {"start": start.isoformat() if start else None, "initial_cash": st.sim_initial_cash}

    def _next_sim_day(self) -> tuple[date | None, bool]:
        """(다음에 처리할 거래일, 첫 처리 여부). 처리할 날이 없으면 (None, False)."""
        assert self.market is not None
        calendar = self.market.calendar
        st = self.settings()
        with self.sf() as s, s.begin():
            account = repo.get_account(s, "sim", st.sim_initial_cash)
            last = account.sim_day
        if last is None:
            start_text = self.kv.get("sim_start")
            if start_text:
                start = date.fromisoformat(start_text)
                day = next((d for d in calendar if d >= start), None)
                return day, True
            return calendar[-1], True
        t = self.market.cal_index(date.fromisoformat(last))
        if t is None or t + 1 >= len(calendar):
            return None, False
        return calendar[t + 1], False

    async def advance(self, days: int = 1, *, auto_approve: bool = False) -> list[dict[str, Any]]:
        """시뮬레이션을 거래일 단위로 진행한다. auto_approve는 과거 구간 재생용(승인 대기를 자동 승인)."""
        if self.market is None:
            raise EngineError("일봉 데이터가 없습니다. 먼저 데이터를 갱신하세요")
        if self.settings().env != "sim":
            raise EngineError("거래일 진행은 시뮬레이션에서만 쓸 수 있습니다")
        results: list[dict[str, Any]] = []
        async with self._lock:
            try:
                for _ in range(max(1, min(days, 250))):
                    day, first = self._next_sim_day()
                    if day is None:
                        break
                    self.busy = f"{day} 처리 중"
                    self.bus.publish("status")
                    results.append(await self._advance_one(day, first=first, auto_approve=auto_approve))
                    if self.settings().state == "stopped" and results[-1].get("halted"):
                        break
                    await asyncio.sleep(0)
            except Exception as exc:  # noqa: BLE001 - 어떤 오류든 기록하고 다시 올린다
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._log("sim", Event("error", f"거래일 처리 중 오류: {self.last_error}"))
                raise
            finally:
                self.busy = ""
                self.bus.publish("status")
        if not results:
            raise EngineError("처리할 새 거래일이 없습니다. 장 마감 뒤 데이터를 갱신하면 다음 거래일을 처리할 수 있습니다")
        return results

    async def _advance_one(self, day: date, *, first: bool, auto_approve: bool) -> dict[str, Any]:
        assert self.market is not None
        env = "sim"
        st = self.settings()
        cfg = self.engine_config(st)
        market = self.market
        t = market.cal_index(day)
        assert t is not None
        events: list[tuple[Event, int | None]] = []  # (이벤트, 현금 잔액)
        fills_count = 0

        # 1) 오늘 주문 계획 체결 + 장 마감 처리
        with self.sf() as s, s.begin():
            portfolio = repo.load_portfolio(s, env, st.sim_initial_cash)
            account = repo.get_account(s, env, st.sim_initial_cash)
            rows = repo.intents_for(s, env, trade_date=day, statuses=("pending_approval", "approved"))
            for row in rows:
                if row.status == "pending_approval":
                    if auto_approve:
                        row.status = "approved"
                        events.append((Event("approve", "재생 구간 자동 승인", row.code, row.name, row.chain_id, qty=row.qty), None))
                    else:
                        row.status = "expired"
                        events.append((Event("expire", f"승인하지 않아 만료: {'매수' if row.side == 'buy' else '매도'} {row.qty}주", row.code, row.name, row.chain_id, qty=row.qty), None))
                if row.status == "approved" and row.side == "buy" and st.state != "running":
                    row.status = "cancelled"
                    events.append((Event("expire", f"엔진이 {STATE_LABELS[st.state]} 상태라 매수하지 않음", row.code, row.name, row.chain_id, qty=row.qty), None))
            intents = [repo.row_to_intent(r) for r in rows if r.status == "approved"]
            bars = {}
            for code in set(portfolio.positions) | {it.code for it in intents}:
                feat = market.stocks.get(code)
                i = feat.index_of(day) if feat is not None else None
                if feat is not None and i is not None:
                    bars[code] = feat.bar(i)
            cash = portfolio.cash
            if not first:
                day_result = execute_day(day, portfolio, intents, bars, cfg.costs)
                for fill in day_result.fills:
                    repo.save_fill(s, env, fill)
                    fills_count += 1
                    if fill.side == "buy":
                        cash -= fill.amount + fill.fee
                        text = f"{FILL_SUMMARY.get(fill.reason, fill.reason)} · {fill.price:,}원"
                        events.append((Event("fill_buy", text, fill.code, fill.name, fill.chain_id, qty=fill.qty, amount=fill.amount,
                                             payload={"reason": fill.reason, "fee": fill.fee, "technique": fill.technique}), cash))
                    else:
                        cash += fill.amount - fill.fee - fill.tax
                        kind = "protective" if fill.reason in PROTECTIVE_REASONS else "fill_sell"
                        text = f"{FILL_SUMMARY.get(fill.reason, fill.reason)} · {fill.price:,}원 · 손익 {fill.pnl:+,}원 ({(fill.pnl_pct or 0) * 100:+.1f}%)"
                        events.append((Event(kind, text, fill.code, fill.name, fill.chain_id, qty=fill.qty, amount=fill.amount,
                                             payload={"reason": fill.reason, "pnl": fill.pnl, "pnl_pct": fill.pnl_pct, "fee": fill.fee,
                                                      "tax": fill.tax, "hold_days": fill.hold_days}), cash))
                for intent, why in day_result.skipped:
                    events.append((Event("skip", f"체결되지 않음: {why}", intent.code, intent.name, intent.chain_id, qty=intent.qty), None))
                for intent in intents:
                    repo.sync_intent_status(s, intent)
                for code, before, after in end_of_day(day, portfolio, bars):
                    pos = portfolio.positions[code]
                    events.append((Event("stop_raise", f"추적 손절 상향 {before:,}원 → {after:,}원", code, pos.name, pos.chain_id), None))
            prices = market.prices_on(day)
            equity = portfolio.equity(prices)
            portfolio.peak_equity = max(portfolio.peak_equity, equity)
            repo.save_portfolio(s, env, portfolio, st.sim_initial_cash)
            first_row = s.execute(select(EquityRow.d).where(EquityRow.env == env).order_by(EquityRow.d).limit(1)).scalar_one_or_none()
            base_day = date.fromisoformat(first_row) if first_row else day
            kospi = market.indexes["KOSPI"]
            base_t = market.cal_index(base_day) or t
            benchmark = st.sim_initial_cash * float(kospi.close[t]) / float(kospi.close[base_t])
            repo.save_equity(s, env, day, equity, portfolio.cash, portfolio.exposure(prices), benchmark)
            account.sim_day = day.isoformat()
        for event, cash_after in events:
            self._log(env, event, day=day, cash_after=cash_after)

        # 2) 장 마감 뒤 사이클
        halted = False
        cycle_summary: dict[str, Any] = {}
        if st.state == "stopped":
            self._log(env, Event("cycle", "엔진이 정지 상태라 장후 심의를 건너뜁니다(보호 청산만 처리)"), day=day)
        else:
            cycle_summary, halted = await self._after_close(day, t, st, cfg)
        self.bus.publish("status")
        return {"day": day.isoformat(), "fills": fills_count, "equity": round(equity), "halted": halted, **cycle_summary}

    async def _after_close(self, day: date, t: int, st: EngineSettings, cfg: EngineConfig) -> tuple[dict[str, Any], bool]:
        assert self.market is not None
        env = st.env
        market = self.market
        next_day = self._next_day(day, st)
        with self.sf() as s, s.begin():
            portfolio = repo.load_portfolio(s, env, st.sim_initial_cash)
            history = [h for h in repo.equity_history(s, env) if h[0] < day]
            exits = repo.recent_exits(s, env)
            open_rows = repo.intents_for(s, env, trade_date=next_day, statuses=("pending_approval", "approved"))
            pending_codes = frozenset(r.code for r in open_rows if r.side == "buy")
        draft = prepare_cycle(day, next_day, market, self.regimes[t], portfolio, cfg, equity_history=history, recent_exits=exits,
                              prefilter=self.prefilter(cfg), pending_codes=pending_codes,
                              previous_day=market.calendar[t - 1] if t > 0 else None)
        if st.decider == "rules":
            entries, holds = rules_decisions(draft)
        else:
            entries, holds = await self._ai_decisions(draft, st)
        cycle = finalize_cycle(draft, entries, holds, portfolio, cfg, pending_codes=pending_codes)

        expires_at = datetime.combine(next_day, datetime.min.time(), tzinfo=clock.KST).replace(hour=15, minute=20).isoformat(timespec="seconds")
        approval_events: list[Event] = []
        with self.sf() as s, s.begin():
            for record in cycle.records:
                repo.save_decision(s, env, record)
            for intent in cycle.intents:
                intent.status, note = self._initial_status(intent, st)
                if note:
                    intent.note = note
                intent.decision_id = next((r.id for r in cycle.records if r.intent_id == intent.id), None)
                repo.upsert_intent(s, env, intent, expires_at if intent.status == "pending_approval" else None)
                side = "매수" if intent.side == "buy" else "매도"
                if intent.status == "pending_approval":
                    approval_events.append(Event("intent", f"{side} {intent.qty}주 승인 대기 · {next_day.month}월 {next_day.day}일 15:20까지", intent.code, intent.name, intent.chain_id, qty=intent.qty))
                elif intent.status == "notified":
                    approval_events.append(Event("intent", f"알림만: {side} {intent.qty}주 계획(주문하지 않음)", intent.code, intent.name, intent.chain_id, qty=intent.qty))
                elif intent.status == "cancelled":
                    approval_events.append(Event("expire", note, intent.code, intent.name, intent.chain_id, qty=intent.qty))
        for event in [*cycle.events[:-1], *approval_events, cycle.events[-1]]:
            self._log(env, event, day=day)

        halted = False
        if draft.breaker.halt_engine and st.state != "stopped":
            self._set_state("stopped", "낙폭 한도에 닿아 엔진을 정지했습니다. 설정과 보유 종목을 점검하세요")
            self._cancel_open_intents(env, "엔진 정지로 취소")
            halted = True
        last = cycle.events[-1].payload
        return {"candidates": last.get("candidates", 0), "buys": last.get("buys", 0), "sells": last.get("sells", 0),
                "regime": draft.regime.label}, halted

    def _initial_status(self, intent: Intent, st: EngineSettings) -> tuple[str, str]:
        """자동화 단계에 따른 주문 계획의 첫 상태. 청산 규칙·전량 매도는 단계와 상관없이 실행한다."""
        if intent.source in ("rule_exit", "liquidate", "protective"):
            return "approved", ""
        if intent.side == "buy" and st.state != "running":
            return "cancelled", f"엔진이 {STATE_LABELS[st.state]} 상태라 매수 계획을 만들지 않습니다"
        level = min(st.automation_level, 1) if st.resume_check_required else st.automation_level
        if level == 0:
            return "notified", ""
        if level == 1:
            return "pending_approval", ""
        if intent.side == "sell":
            return "approved", ""
        if level == 2 and intent.qty * intent.est_price > st.auto_max_order_value:
            return "pending_approval", ""
        return "approved", ""

    def _make_llm(self, st: EngineSettings) -> LlmClient:
        if self._llm_factory is not None:
            return self._llm_factory(st)
        return AnthropicLlm(self.config.anthropic_api_key.get_secret_value(), model=st.ai_model, effort=st.ai_effort)

    async def _ai_decisions(self, draft: CycleDraft, st: EngineSettings) -> tuple[dict[str, tuple[Decision, dict | None]], dict[str, tuple[Decision, dict | None]]]:
        entries: dict[str, tuple[Decision, dict | None]] = {}
        holds: dict[str, tuple[Decision, dict | None]] = {}
        review_targets = [h for h in draft.holdings if h.needs_review]
        if not draft.candidates and not review_targets:
            return entries, holds
        try:
            llm = self._make_llm(st)
        except LlmError as exc:
            for cand in draft.candidates:
                entries[cand.info.code] = (Decision(cand.info.code, cand.info.name, "entry", "HOLD", "very_low", thesis="AI 판단을 받지 못해 보류합니다",
                                                    source="ai", status="review", status_detail=str(exc)), None)
            for h in review_targets:
                holds[h.info.code] = (Decision(h.info.code, h.info.name, "holding", "HOLD", "very_low", thesis="AI 판단을 받지 못해 보류합니다",
                                               source="ai", status="review", status_detail=str(exc)), None)
            return entries, holds
        budget = BudgetGuard(self.sf, st.env, st.ai_daily_budget_usd)
        try:
            for h in review_targets:
                self.busy = f"AI 위원회: {h.info.name} 보유 재심의"
                self.bus.publish("status")
                decision, transcript = await deliberate_holding(h.context, llm, budget, depth=st.ai_depth)
                holds[h.info.code] = (decision, transcript.to_dict())
            for cand in draft.candidates:
                self.busy = f"AI 위원회: {cand.info.name} 심의"
                self.bus.publish("status")
                decision, transcript = await deliberate_entry(cand.context, llm, budget, depth=st.ai_depth)
                entries[cand.info.code] = (decision, transcript.to_dict())
        finally:
            closer = getattr(llm, "aclose", None)
            if closer is not None:
                await closer()
        return entries, holds

    # ── 상태 요약 ──────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        st = self.settings()
        limits = self.limits()
        now = clock.now_kst()
        with self.sf() as s, s.begin():
            account = repo.get_account(s, st.env, st.sim_initial_cash)
            pending = s.execute(select(func.count()).select_from(IntentRow).where(IntentRow.env == st.env, IntentRow.status == "pending_approval")).scalar_one()
            last_two = s.execute(select(EquityRow.d, EquityRow.equity).where(EquityRow.env == st.env).order_by(EquityRow.d.desc()).limit(2)).all()
            sim_day = account.sim_day
            initial_cash = int(account.initial_cash)
        daily_pct = (last_two[0][1] / last_two[1][1] - 1) if len(last_two) == 2 and last_two[1][1] > 0 else 0.0
        equity = float(last_two[0][1]) if last_two else float(initial_cash)
        regime = None
        data_day = None
        if self.market is not None:
            data_day = self.market.last_day().isoformat()
            t = self.market.cal_index(date.fromisoformat(sim_day)) if sim_day else len(self.regimes) - 1
            if t is not None and self.regimes:
                r = self.regimes[t]
                regime = {"label": r.label, "score": round(r.score), "exposure_cap": round(r.exposure_cap, 3), "allow_new_buys": r.allow_new_buys, "day": r.day.isoformat()}
        budget = BudgetGuard(self.sf, st.env, st.ai_daily_budget_usd)
        phase = clock.session_phase(now, self._holidays(st))
        return {
            "env": st.env, "env_label": ENV_LABELS[st.env], "state": st.state, "state_label": STATE_LABELS[st.state],
            "automation_level": st.automation_level, "automation_label": AUTOMATION_LABELS[st.automation_level],
            "resume_check_required": st.resume_check_required, "decider": st.decider,
            "sim_day": sim_day, "data_day": data_day, "data_source": self.provider.name, "data_refreshed_at": self.data_refreshed_at,
            "has_data": self.market is not None,
            "behind_days": self._behind_days(sim_day),
            "session": {"phase": phase, "seconds_to_close": clock.seconds_until_close(now), "now": now.isoformat(timespec="seconds"),
                        "calendar_confirmed_through": clock.CALENDAR_CONFIRMED_THROUGH.isoformat()},
            "regime": regime,
            "pending_approvals": int(pending),
            "risk": {"daily_pct": round(daily_pct, 5), "daily_limit_pct": limits.daily_loss_limit_pct,
                     "daily_used": round(min(1.0, max(0.0, -daily_pct) / limits.daily_loss_limit_pct), 4), "equity": round(equity)},
            "ai": {"configured": self.config.has_anthropic_key or self._llm_factory is not None, "model": st.ai_model,
                   "spent_today_usd": round(budget.spent_today(), 4), "budget_usd": st.ai_daily_budget_usd},
            "broker": {"kind": "paper" if st.env == "sim" else "kiwoom", "mock_keys": self.config.has_kiwoom_keys("mock"),
                       "live_keys": self.config.has_kiwoom_keys("live"), "live_allowed": self.config.allow_live_trading},
            "busy": self.busy, "last_error": self.last_error,
            "ledger_last_seq": self.ledger.last_seq(st.env), "ledger_seen_seq": int(self.kv.get(f"ledger_seen:{st.env}", 0) or 0),
        }

    def ledger_epoch(self, env: str) -> int:
        """이 번호보다 큰 장부 줄이 '이번 실행'의 기록이다. 시뮬레이션을 다시 시작하면 올라간다(다른 환경은 항상 0)."""
        return int(self.kv.get(LEDGER_EPOCH_KEY, 0) or 0) if env == "sim" else 0

    def _behind_days(self, sim_day: str | None) -> int:
        """시뮬레이션이 최신 일봉보다 며칠 뒤에 있는지."""
        if self.market is None or sim_day is None:
            return 0
        t = self.market.cal_index(date.fromisoformat(sim_day))
        return 0 if t is None else len(self.market.calendar) - 1 - t


class Scheduler:
    """백그라운드 루프: 장 마감 뒤 일봉을 갱신하고, 시뮬레이션이 최신 상태면 새 거래일을 처리한다."""

    def __init__(self, service: EngineService, *, interval: float = 60.0) -> None:
        self._service = service
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._last_refresh: date | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="alphapilot-scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.tick(clock.now_kst())
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 루프는 죽지 않고 오류를 기록한다
                log.exception("스케줄러 오류")
                self._service.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self._interval)

    async def tick(self, now: datetime) -> None:
        service = self._service
        st = service.settings()
        today = now.date()
        after_close = now.time() >= (datetime.min + timedelta(hours=15, minutes=45)).time()
        if not clock.is_trading_day(today, service._holidays(st)) or not after_close or self._last_refresh == today:
            return
        self._last_refresh = today
        await service.refresh_data()
        # 최신 일봉 바로 전날까지 따라와 있을 때만 자동으로 하루를 처리한다(과거 재생 중에는 자동 진행하지 않는다).
        if st.env == "sim" and st.state != "stopped" and service._behind_days(service.status()["sim_day"]) == 1:
            await service.advance(1)
