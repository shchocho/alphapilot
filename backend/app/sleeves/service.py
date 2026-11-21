"""바구니 운용 서비스: 계획 저장(리비전)·되돌리기, 종목 확인, 심의 실행, 가상 체결, 성과·미리 보기.

엔진 서비스(EngineService)의 DB·시세·AI 예산을 함께 쓰고, 날짜는 최신 일봉 기준으로 앞으로만 쌓아 간다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.committee.deliberation import Budget, Transcript
from app.committee.llm import LlmClient, LlmError, LlmResult, estimate_cost
from app.committee.rules_committee import _conviction
from app.core.clock import now_kst
from app.core.models import CONVICTION_LABEL, StockInfo
from app.data.provider import INDEX_CODES
from app.data.store import FULL_HISTORY_BARS
from app.data.universe import load_universe, universe_map
from app.engine.core import Event
from app.engine.service import BudgetGuard, EngineError, EngineService
from app.indicators.features import Market, build_market
from app.regime.regime import RegimeState
from app.sleeves import logic
from app.sleeves.ai import SleeveContext, Verdict, deliberate_sleeve, sleeve_second_opinion
from app.sleeves.config import (
    CADENCE_LABELS,
    CODE_PATTERN,
    DECIDER_LABELS,
    KIND_LABELS,
    MODE_LABELS,
    PlanConfig,
    SleeveConfig,
    guess_kind,
)
from app.store.db import (
    PlanRevisionRow,
    SleeveBookRow,
    SleeveOrderRow,
    SleeveRunRow,
    SleeveSignalRow,
    SleeveTradeRow,
)

log = logging.getLogger("alphapilot.sleeves")

CALLS_PER_DEPTH = {"light": 1, "standard": 4, "deep": 6}
EST_INPUT_TOKENS, EST_OUTPUT_TOKENS = 4_000, 600  # 호출 한 번의 어림 토큰(비용 미리 보기용)
AI_CONCURRENCY = 3  # 바구니를 동시에 심의할 때 Claude에 한 번에 보내는 호출 수


def _stamp() -> str:
    return now_kst().isoformat(timespec="seconds")


def _new_id(prefix: str = "", n: int = 12) -> str:
    return prefix + uuid.uuid4().hex[:n]


def won(amount: float) -> str:
    n = int(round(amount))
    return f"{n // 10_000:,}만원" if n % 10_000 == 0 and n >= 10_000 else f"{n:,}원"


# ── 판 비교(순수) ──────────────────────────────────────────────────────────


def plan_changes(old: PlanConfig | None, new: PlanConfig) -> list[str]:
    """두 판 사이에 바뀐 점을 사람이 읽을 문장으로."""
    if old is None:
        return [f"첫 계획: 총 {won(new.total)}, 바구니 {len(new.sleeves)}개"]
    out: list[str] = []
    if old.total != new.total:
        out.append(f"총 투입 금액 {won(old.total)} → {won(new.total)}")
    before = {s.id: s for s in old.sleeves}
    after = {s.id: s for s in new.sleeves}
    for sid, s in after.items():
        if sid not in before:
            out.append(f"'{s.name}' 바구니 추가({won(s.amount)}, 종목 {len(s.items)}개)")
    for sid, s in before.items():
        if sid not in after:
            out.append(f"'{s.name}' 바구니 뺌")
    for sid, s in after.items():
        o = before.get(sid)
        if o is None:
            continue
        label = f"'{s.name}'"
        if o.name != s.name:
            out.append(f"'{o.name}' 이름을 '{s.name}'으로 바꿈")
        if o.amount != s.amount:
            out.append(f"{label} 금액 {won(o.amount)} → {won(s.amount)}")
        old_items = {i.code: i for i in o.items}
        new_items = {i.code: i for i in s.items}
        added = [i.name or i.code for c, i in new_items.items() if c not in old_items]
        removed = [i.name or i.code for c, i in old_items.items() if c not in new_items]
        if added:
            out.append(f"{label} 종목 추가: {', '.join(added)}")
        if removed:
            out.append(f"{label} 종목 뺌: {', '.join(removed)}")
        if any(c in old_items and (old_items[c].weight != i.weight or old_items[c].kind != i.kind) for c, i in new_items.items()):
            out.append(f"{label} 종목 비중·종류 조정")
        if o.mandate != s.mandate:
            out.append(f"{label} 운용 지침 수정")
        for key, labels, name in (("decider", DECIDER_LABELS, "판단 주체"), ("cadence", CADENCE_LABELS, "심의 주기"), ("mode", MODE_LABELS, "방식")):
            if getattr(o, key) != getattr(s, key):
                out.append(f"{label} {name} {labels[getattr(o, key)]} → {labels[getattr(s, key)]}")
        if o.installments != s.installments:
            out.append(f"{label} 나눠 살 횟수 {o.installments}회 → {s.installments}회")
        if o.depth != s.depth:
            out.append(f"{label} AI 심의 깊이 변경")
    return out or ["바뀐 내용 없음"]


# ── 보조 ──────────────────────────────────────────────────────────────────


class _Throttled:
    """여러 바구니가 동시에 심의할 때 Claude 호출 수를 묶는다."""

    def __init__(self, llm: LlmClient, sem: asyncio.Semaphore) -> None:
        self._llm = llm
        self._sem = sem
        self.model = llm.model

    async def complete(self, **kwargs: Any) -> LlmResult:
        async with self._sem:
            return await self._llm.complete(**kwargs)


@dataclass(slots=True)
class _SleeveRun:
    cfg: SleeveConfig
    book: logic.Book
    signals: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    ai_calls: int = 0
    cost: float = 0.0


def _rules_thesis(a: logic.Assessment, action: str, allow_new_buys: bool) -> str:
    picked = sorted((s for s in a.seats if not s.abstained), key=lambda s: abs(s.value) * s.confidence, reverse=True)[:3]
    reasons = " · ".join(f"{s.label}: {s.summary}" for s in picked if s.summary)
    tail = " 시장 국면이 신규 매수를 막고 있어 더 모으기 대신 평소 금액만 모읍니다." if not allow_new_buys and action == "BUY" and a.score >= logic.MORE_AT else ""
    return f"좌석 종합 {a.score:+.2f} → {logic.ACTION_LABELS[action]}.{tail} {reasons}".strip()


def _seat_brief(a: logic.Assessment) -> list[dict[str, Any]]:
    return [{"label": s.label, "stance": s.stance, "value": round(s.value, 2), "summary": s.summary} for s in a.seats]


class SleeveService:
    def __init__(self, engine: EngineService) -> None:
        self.svc = engine
        self.sf = engine.sf
        self._lock = asyncio.Lock()
        self._market: tuple[tuple, Market] | None = None
        self.busy = ""
        self._looked_up: dict[str, tuple[str, str]] = {}  # 확인한 유니버스 밖 종목의 (이름, 종류)
        engine.sleeves = self  # 스케줄러가 장 마감 뒤 차례가 된 바구니를 심의한다
        engine.extra_codes = self.plan_codes  # 일봉 갱신에 바구니 종목을 더한다

    # ── 계획·판 ──────────────────────────────────────────────────────────

    def current(self) -> tuple[PlanRevisionRow, PlanConfig] | None:
        with self.sf() as s:
            row = s.execute(select(PlanRevisionRow).order_by(PlanRevisionRow.rev.desc()).limit(1)).scalar_one_or_none()
        return (row, PlanConfig.model_validate_json(row.config)) if row is not None else None

    def plan_codes(self) -> list[str]:
        cur = self.current()
        return cur[1].codes() if cur else []

    def _books(self, s: Session) -> dict[str, SleeveBookRow]:
        return {row.sleeve_id: row for row in s.execute(select(SleeveBookRow)).scalars()}

    def save(self, plan: PlanConfig, note: str = "", *, restored_from: int | None = None) -> dict[str, Any]:
        market = self.market(plan.codes())
        if market is None:
            raise EngineError("일봉 데이터가 없습니다. 설정에서 일봉을 먼저 갱신하세요")
        day = market.last_day()
        missing = [i.code for sl in plan.sleeves for i in sl.items if i.code not in market.stocks]
        if missing:
            raise EngineError(f"일봉이 없는 종목이 있습니다: {', '.join(missing)}. 종목을 다시 확인해 넣으세요")
        for sl in plan.sleeves:
            if not sl.id:
                sl.id = _new_id("s", 6)
        cur = self.current()
        old = cur[1] if cur else None
        before = {sl.id: sl for sl in old.sleeves} if old else {}
        prices = market.prices_on(day)
        stamp = _stamp()
        with self.sf() as s, s.begin():
            books = self._books(s)
            pending = s.execute(select(SleeveOrderRow).where(SleeveOrderRow.status == "pending")).scalars().all()
            reserved: dict[str, float] = {}
            pending_count: dict[str, int] = {}
            for o in pending:
                pending_count[o.sleeve_id] = pending_count.get(o.sleeve_id, 0) + 1
                if o.side == "buy":
                    reserved[o.sleeve_id] = reserved.get(o.sleeve_id, 0.0) + o.qty * prices.get(o.code, 0.0) * 1.002
            # 1) 검사: 뺄 수 없는 돈, 정리되지 않은 바구니
            for sid, o_cfg in before.items():
                book_row = books.get(sid)
                if sid in {sl.id for sl in plan.sleeves} or book_row is None or book_row.closed:
                    continue
                book = logic.Book.from_dict(json.loads(book_row.state))
                if o_cfg.mode == "paper" and (book.positions or pending_count.get(sid)):
                    raise EngineError(f"'{o_cfg.name}' 바구니에 가상 보유 종목이나 대기 주문이 있어 뺄 수 없습니다. 먼저 '모두 팔기'를 예약하고 체결된 뒤 빼세요")
            for sl in plan.sleeves:
                o_cfg = before.get(sl.id)
                book_row = books.get(sl.id)
                if o_cfg is None or book_row is None or book_row.closed:
                    continue
                book = logic.Book.from_dict(json.loads(book_row.state))
                if o_cfg.mode == "paper" and sl.mode == "alert" and (book.positions or pending_count.get(sl.id)):
                    raise EngineError(f"'{sl.name}' 바구니에 가상 보유 종목이나 대기 주문이 있어 알림만으로 바꿀 수 없습니다. 먼저 '모두 팔기'를 예약하세요")
                delta = sl.amount - o_cfg.amount
                if sl.mode == "paper" and o_cfg.mode == "paper" and delta < 0:
                    free = book.cash - reserved.get(sl.id, 0.0)
                    if -delta > free:
                        raise EngineError(f"'{sl.name}' 바구니의 쓸 수 있는 현금이 {int(max(free, 0)):,}원이라 {-delta:,}원을 뺄 수 없습니다. "
                                          f"금액을 {int(o_cfg.amount - max(free, 0)):,}원 이상으로 두거나 먼저 일부를 파세요")
            # 2) 새 판
            rev = (cur[0].rev + 1) if cur else 1
            changes = plan_changes(old, plan)
            s.add(PlanRevisionRow(rev=rev, created_at=stamp, day=day.isoformat(), note=note.strip()[:200], restored_from=restored_from,
                                  config=plan.model_dump_json()))
            # 3) 장부 반영
            after_ids = {sl.id for sl in plan.sleeves}
            for sid, o_cfg in before.items():
                book_row = books.get(sid)
                if sid in after_ids or book_row is None or book_row.closed:
                    continue
                book = logic.Book.from_dict(json.loads(book_row.state))
                if o_cfg.mode == "paper" and book.cash > 0:
                    s.add(SleeveTradeRow(sleeve_id=sid, rev=rev, d=day.isoformat(), kind="withdraw", amount=book.cash, created_at=stamp))
                book.contributed -= book.cash
                book.cash = 0
                book_row.state, book_row.closed, book_row.updated_at = json.dumps(book.to_dict()), True, stamp
            for sl in plan.sleeves:
                o_cfg = before.get(sl.id)
                book_row = books.get(sl.id)
                fresh = o_cfg is None or book_row is None or book_row.closed or (o_cfg.mode == "alert" and sl.mode == "paper")
                if fresh:
                    book = logic.Book(cash=sl.amount, contributed=sl.amount, started_on=day.isoformat())
                    if sl.mode == "paper":
                        s.add(SleeveTradeRow(sleeve_id=sl.id, rev=rev, d=day.isoformat(), kind="deposit", amount=sl.amount, created_at=stamp))
                    state = json.dumps(book.to_dict())
                    if book_row is None:
                        s.add(SleeveBookRow(sleeve_id=sl.id, state=state, snapshot=None, closed=False, updated_at=stamp))
                    else:
                        book_row.state, book_row.snapshot, book_row.closed, book_row.updated_at = state, None, False, stamp
                    continue
                assert o_cfg is not None and book_row is not None
                book = logic.Book.from_dict(json.loads(book_row.state))
                delta = sl.amount - o_cfg.amount
                if sl.mode == "alert":
                    book.cash, book.contributed = sl.amount, sl.amount
                elif delta:
                    book.cash += delta
                    book.contributed += delta
                    s.add(SleeveTradeRow(sleeve_id=sl.id, rev=rev, d=day.isoformat(), kind="deposit" if delta > 0 else "withdraw",
                                         amount=abs(delta), created_at=stamp))
                book_row.state, book_row.updated_at = json.dumps(book.to_dict()), stamp
        self.svc._log(self.svc.settings().env, Event("sleeve", f"운용 계획 r{rev} 저장: " + " · ".join(changes),
                                                     payload={"rev": rev, "note": note, "restored_from": restored_from}), day=day)
        self.svc.bus.publish("sleeves")
        return {"rev": rev, "changes": changes}

    def restore(self, rev: int, note: str = "") -> dict[str, Any]:
        with self.sf() as s:
            row = s.get(PlanRevisionRow, rev)
        if row is None:
            raise EngineError(f"r{rev} 판을 찾을 수 없습니다")
        cur = self.current()
        if cur and cur[0].rev == rev:
            raise EngineError("지금 쓰는 판입니다")
        plan = PlanConfig.model_validate_json(row.config)
        return self.save(plan, note or f"r{rev}로 되돌림", restored_from=rev)

    # ── 시세 ─────────────────────────────────────────────────────────────

    def market(self, extra: Iterable[str] = ()) -> Market | None:
        """유니버스 + 바구니 종목으로 만든 시장. 유니버스 밖 종목(ETF 등)이 없으면 엔진 시장을 그대로 쓴다."""
        base = self.svc.market
        if base is None:
            return None
        codes = sorted(set(self.plan_codes()) | set(extra))
        outside = [c for c in codes if c not in base.stocks]
        if not outside:
            return base
        key = (id(base), tuple(outside))
        if self._market is not None and self._market[0] == key:
            return self._market[1]
        universe = [s.code for s in load_universe()]
        bars = self.svc.store.load_many(universe + outside)
        index_bars = {c: frame for c in INDEX_CODES if not (frame := self.svc.store.load(c)).empty}
        info = dict(universe_map())
        names = self._names()
        for code in outside:
            name, kind = names.get(code, (code, "stock"))
            info[code] = StockInfo(code, name, "KOSPI", "ETF" if kind == "etf" else "기타")
        market = build_market(bars, index_bars, info, source=self.svc.provider.name)
        self._market = (key, market)
        return market

    def _names(self) -> dict[str, tuple[str, str]]:
        cur = self.current()
        out: dict[str, tuple[str, str]] = {}
        if cur:
            for sl in cur[1].sleeves:
                for item in sl.items:
                    out[item.code] = (item.name or item.code, item.kind)
        out.update(self._looked_up)
        return out

    def regime(self, day: date) -> RegimeState:
        base = self.svc.market
        assert base is not None
        t = base.cal_index(day)
        return self.svc.regimes[t if t is not None else -1]

    def lookup(self, code: str) -> dict[str, Any]:
        """종목 코드를 확인한다. 일봉이 없으면 받아 온다(유니버스 밖 ETF 등)."""
        import re

        code = code.strip().upper()
        if not re.fullmatch(CODE_PATTERN, code):
            raise EngineError("종목 코드는 6자리입니다(예: 069500)")
        uni = universe_map()
        name = uni[code].name if code in uni else ""
        bars = self.svc.store.load(code)
        if bars.empty or code not in uni:
            fetch = getattr(self.svc.provider, "fetch", None)
            try:
                if callable(fetch):
                    fetched_name, fresh = fetch(code, FULL_HISTORY_BARS)
                    name = name or fetched_name
                else:
                    fresh = self.svc.provider.daily_bars(code, FULL_HISTORY_BARS)
            except Exception as exc:  # noqa: BLE001 - 공급자 오류는 그대로 사용자에게 알린다
                raise EngineError(f"{code} 일봉을 받지 못했습니다: {exc}") from exc
            if fresh.empty and bars.empty:
                raise EngineError(f"{code} 종목의 일봉이 없습니다. 코드를 확인하세요")
            if not fresh.empty:
                self.svc.store.replace(code, fresh)
                bars = fresh
        name = name or code
        kind = guess_kind(name)
        self._looked_up[code] = (name, kind)
        self._market = None
        return {"code": code, "name": name, "kind": kind, "kind_label": KIND_LABELS[kind], "in_universe": code in uni,
                "close": float(bars["close"].iloc[-1]), "day": bars.index[-1].date().isoformat(), "bars": len(bars)}

    # ── 심의 ─────────────────────────────────────────────────────────────

    def _due(self, plan: PlanConfig, day: date, books: dict[str, logic.Book]) -> list[str]:
        out = []
        for sl in plan.sleeves:
            book = books.get(sl.id)
            last = date.fromisoformat(book.last_run) if book and book.last_run else None
            if logic.is_due(sl.cadence, day, last):
                out.append(sl.id)
        return out

    def _load_books(self) -> dict[str, logic.Book]:
        with self.sf() as s:
            return {sid: logic.Book.from_dict(json.loads(row.state)) for sid, row in self._books(s).items() if not row.closed}

    def estimate(self, *, force: bool = False, sleeve_ids: list[str] | None = None) -> dict[str, Any]:
        cur = self.current()
        market = self.market()
        st = self.svc.settings()
        budget = BudgetGuard(self.sf, st.env, st.ai_daily_budget_usd)
        base = {"ai_configured": self.svc.config.has_anthropic_key, "model": st.ai_model, "budget_usd": st.ai_daily_budget_usd,
                "spent_today_usd": round(budget.spent_today(), 4)}
        if cur is None or market is None:
            return {**base, "day": None, "due": [], "targets": [], "calls": 0, "est_usd": 0.0}
        day = market.last_day()
        due = self._due(cur[1], day, self._load_books())
        targets = [sl for sl in cur[1].sleeves if (sl.id in due or force) and (sleeve_ids is None or sl.id in sleeve_ids)]
        calls = 0
        for sl in targets:
            if sl.decider == "ai":
                calls += len(sl.items) * CALLS_PER_DEPTH[sl.depth]
            elif sl.decider == "hybrid":
                calls += len(sl.items)  # 최대치: 모든 종목이 분기일 때
        per_call = estimate_cost(st.ai_model, EST_INPUT_TOKENS, EST_OUTPUT_TOKENS)
        return {**base, "day": day.isoformat(), "due": due, "targets": [sl.id for sl in targets], "calls": calls,
                "est_usd": round(calls * per_call, 3)}

    async def run(self, *, trigger: str = "manual", force: bool = False, sleeve_ids: list[str] | None = None) -> dict[str, Any]:
        if self._lock.locked():
            raise EngineError("바구니 심의가 이미 돌고 있습니다. 끝난 뒤 다시 시도하세요")
        async with self._lock:
            try:
                return await self._run(trigger=trigger, force=force, sleeve_ids=sleeve_ids)
            finally:
                self.busy = ""
                self.svc.bus.publish("status")

    async def _run(self, *, trigger: str, force: bool, sleeve_ids: list[str] | None) -> dict[str, Any]:
        cur = self.current()
        if cur is None:
            raise EngineError("운용 계획이 없습니다. 먼저 바구니를 만들어 저장하세요")
        rev_row, plan = cur
        market = await asyncio.to_thread(self.market)
        if market is None:
            raise EngineError("일봉 데이터가 없습니다. 설정에서 일봉을 먼저 갱신하세요")
        day = market.last_day()
        self.busy = "바구니: 대기 주문 체결"
        self.svc.bus.publish("status")
        fills = self.settle(market)
        books = self._load_books()
        due = self._due(plan, day, books)
        targets = [sl for sl in plan.sleeves if (sl.id in due or force) and (sleeve_ids is None or sl.id in sleeve_ids)]
        if not targets:
            return {"run_id": None, "as_of": day.isoformat(), "rev": rev_row.rev, "sleeves": [], "fills": fills,
                    "message": "심의할 차례가 된 바구니가 없습니다"}

        run_id = _new_id(n=12)
        # 같은 날 다시 돌리면 앞선 결과를 되돌린다(장부는 그날 심의 직전으로, 신호·대기 주문은 교체됨으로)
        with self.sf() as s, s.begin():
            rows = self._books(s)
            for sl in targets:
                row = rows[sl.id]
                book = logic.Book.from_dict(json.loads(row.state))
                if book.last_run == day.isoformat() and row.snapshot:
                    book = logic.Book.from_dict(json.loads(row.snapshot))
                    s.execute(update(SleeveSignalRow).where(SleeveSignalRow.sleeve_id == sl.id, SleeveSignalRow.as_of == day.isoformat(),
                                                            SleeveSignalRow.replaced.is_(False)).values(replaced=True))
                    s.execute(update(SleeveOrderRow).where(SleeveOrderRow.sleeve_id == sl.id, SleeveOrderRow.made_on == day.isoformat(),
                                                           SleeveOrderRow.status == "pending").values(status="replaced", note="같은 날 다시 심의해 교체됨"))
                row.snapshot = json.dumps(book.to_dict())
                books[sl.id] = book
            # 그날 앞선 회차의 바구니가 모두 다시 심의되면 그 회차는 교체된 것으로 본다
            target_ids = {sl.id for sl in targets}
            for prior in s.execute(select(SleeveRunRow).where(SleeveRunRow.as_of == day.isoformat(), SleeveRunRow.replaced.is_(False))).scalars():
                if {x["sleeve_id"] for x in json.loads(prior.summary)} <= target_ids:
                    prior.replaced = True

        regime = self.regime(day)
        st = self.svc.settings()
        needs_ai = any(sl.decider in ("ai", "hybrid") for sl in targets)
        llm: LlmClient | None = None
        llm_error = ""
        if needs_ai:
            try:
                llm = self.svc._make_llm(st)
            except LlmError as exc:
                llm_error = str(exc)
        budget = BudgetGuard(self.sf, st.env, st.ai_daily_budget_usd)
        sem = asyncio.Semaphore(AI_CONCURRENCY)
        throttled = _Throttled(llm, sem) if llm is not None else None
        self.busy = f"바구니 {len(targets)}개를 동시에 심의하고 있습니다"
        self.svc.bus.publish("status")
        try:
            results = await asyncio.gather(*[
                self._run_sleeve(sl, books[sl.id], market, day, regime, throttled, budget, llm_error, run_id, rev_row.rev)
                for sl in targets
            ])
        finally:
            closer = getattr(llm, "aclose", None)
            if closer is not None:
                await closer()
        return self._persist(run_id, day, rev_row.rev, trigger, results, fills)

    async def _run_sleeve(self, cfg: SleeveConfig, book: logic.Book, market: Market, day: date, regime: RegimeState,
                          llm: LlmClient | None, budget: Budget, llm_error: str, run_id: str, rev: int) -> _SleeveRun:
        out = _SleeveRun(cfg, book, [], [])
        base_costs = self.svc.settings().cost_model()
        reserved = 0.0
        paper = cfg.mode == "paper"
        for item in cfg.items:
            info = market.info.get(item.code) or StockInfo(item.code, item.name or item.code, "KOSPI", "기타")
            name = item.name or info.name
            a = logic.assess(market, item.code, day, regime)
            signal_id = _new_id("g", 16)
            if a is None:
                out.signals.append({"id": signal_id, "code": item.code, "name": name, "action": "WAIT", "rules_action": "WAIT",
                                    "conviction": "very_low", "source": "rules", "status": "ok", "score": 0.0, "close": 0.0,
                                    "qty": 0, "amount": 0, "body": {"thesis": "그날 일봉이 없어(거래정지 등) 쉽니다", "key_risks": [],
                                                                     "invalidation": "", "dissent": "", "note": "", "seats": []},
                                    "transcript": None, "cost": 0.0})
                continue
            holding = item.code in book.positions
            can_sell = holding or not paper  # 알림만: 실제 보유를 모르므로 '보유 중이면' 줄이기·팔기 신호도 낸다
            pnl = book.pnl_pct(item.code, a.close)
            rules = logic.rules_action(a.score, can_sell, regime.allow_new_buys)
            lot = book.positions.get(item.code)
            ctx = SleeveContext(
                sleeve_name=cfg.name, mandate=cfg.mandate, info=StockInfo(item.code, name, info.market, info.sector), kind=item.kind,
                as_of=day, close=a.close, techniques=a.results, seats=a.seats, score=a.score, regime=regime, rules_action=rules,
                base_amount=cfg.base_amount(item.code),
                holding=({"수량": lot.qty, "취득 단가": round(lot.avg), "평가손익(%)": round(pnl * 100, 1)} if lot is not None
                         else ({"보유 여부": "알 수 없음(알림만 — 사용자가 직접 매매)"} if not paper else None)),
                book={"방식": MODE_LABELS[cfg.mode], "배정 금액(원)": cfg.amount, "남은 현금(원)": book.cash if paper else None,
                      "진행 회차": f"{book.installments_done} / {cfg.installments}"},
            )
            transcript: Transcript | None = None
            if cfg.decider == "rules":
                verdict = Verdict(rules, _conviction(abs(a.score)), _rules_thesis(a, rules, regime.allow_new_buys))
            elif llm is None:
                if cfg.decider == "ai":
                    verdict = Verdict("WAIT", "very_low", "AI를 쓸 수 없어 이번 회차는 쉽니다", source="ai", status="review",
                                      status_detail=llm_error or "AI 클라이언트 없음")
                else:
                    verdict = Verdict(rules, _conviction(abs(a.score)), _rules_thesis(a, rules, regime.allow_new_buys) + " (AI를 쓸 수 없어 규칙 결론)")
            elif cfg.decider == "ai":
                self.busy = f"바구니 '{cfg.name}': {name} 심의"
                verdict, transcript = await deliberate_sleeve(ctx, llm, budget, depth=cfg.depth)
            else:
                reason = logic.branch_reason(a.score, holding, pnl)
                if reason is None:
                    verdict = Verdict(rules, _conviction(abs(a.score)), _rules_thesis(a, rules, regime.allow_new_buys))
                else:
                    self.busy = f"바구니 '{cfg.name}': {name} 분기 판단"
                    verdict, transcript = await sleeve_second_opinion(ctx, reason, llm, budget)
                    if verdict.source == "rules":
                        verdict.thesis = _rules_thesis(a, verdict.action, regime.allow_new_buys) + f" ({transcript.branch['outcome'] if transcript.branch else ''})"
            if transcript is not None:
                out.ai_calls += len(transcript.steps)
                out.cost += transcript.cost_usd
            # 수량
            costs = logic.costs_for(item.kind, base_costs)
            qty, amount, note = 0, 0, ""
            if verdict.action in logic.BUY_MULTIPLIER:
                plan = logic.plan_buy(book, cfg, item.code, verdict.action, a.close, costs, reserved=reserved, track_carry=paper)
                qty, amount, note = plan.qty, plan.est_amount, plan.note
                if paper:
                    book.carry[item.code] = plan.carry_after
                    reserved += plan.est_amount
            elif verdict.action in ("TRIM", "SELL"):
                if paper:
                    qty = logic.plan_sell(book, item.code, verdict.action)
                    amount = int(round(qty * a.close))
                else:
                    note = "보유 중이라면 " + ("1/3을 줄이기를" if verdict.action == "TRIM" else "모두 팔기를") + " 검토하세요"
            out.signals.append({
                "id": signal_id, "code": item.code, "name": name, "action": verdict.action, "rules_action": rules,
                "conviction": verdict.conviction, "source": verdict.source, "status": verdict.status, "score": round(a.score, 4),
                "close": a.close, "qty": qty, "amount": amount,
                "body": {"thesis": verdict.thesis, "key_risks": verdict.key_risks, "invalidation": verdict.invalidation,
                         "dissent": verdict.dissent, "note": note, "status_detail": verdict.status_detail, "seats": _seat_brief(a),
                         "votes": a.votes, "kind": item.kind, "pnl_pct": round(pnl, 4) if holding else None,
                         "branch": transcript.branch if transcript is not None else None},
                "transcript": transcript.to_dict() if transcript is not None else None, "cost": transcript.cost_usd if transcript else 0.0,
            })
            if paper and qty > 0:
                out.orders.append({"id": _new_id("o", 16), "signal_id": signal_id, "code": item.code, "name": name, "kind": item.kind,
                                   "side": "buy" if verdict.action in logic.BUY_MULTIPLIER else "sell", "qty": qty})
        book.installments_done += 1
        book.last_run = day.isoformat()
        return out

    def _persist(self, run_id: str, day: date, rev: int, trigger: str, results: list[_SleeveRun], fills: list[dict[str, Any]]) -> dict[str, Any]:
        stamp = _stamp()
        summary = []
        with self.sf() as s, s.begin():
            rows = self._books(s)
            for r in results:
                tally: dict[str, int] = {}
                for g in r.signals:
                    tally[g["action"]] = tally.get(g["action"], 0) + 1
                    s.add(SleeveSignalRow(
                        id=g["id"], run_id=run_id, sleeve_id=r.cfg.id, rev=rev, as_of=day.isoformat(), code=g["code"], name=g["name"],
                        action=g["action"], rules_action=g["rules_action"], conviction=g["conviction"], source=g["source"], status=g["status"],
                        score=g["score"], close=g["close"], qty=g["qty"], amount=g["amount"], body=json.dumps(g["body"], ensure_ascii=False),
                        transcript=json.dumps(g["transcript"], ensure_ascii=False) if g["transcript"] else None, cost_usd=g["cost"],
                    ))
                for o in r.orders:
                    s.add(SleeveOrderRow(id=o["id"], sleeve_id=r.cfg.id, signal_id=o["signal_id"], rev=rev, made_on=day.isoformat(),
                                         code=o["code"], name=o["name"], kind=o["kind"], side=o["side"], qty=o["qty"], status="pending"))
                row = rows[r.cfg.id]
                row.state, row.updated_at = json.dumps(r.book.to_dict()), stamp
                summary.append({"sleeve_id": r.cfg.id, "name": r.cfg.name, "mode": r.cfg.mode, "decider": r.cfg.decider, "tally": tally,
                                "orders": len(r.orders), "ai_calls": r.ai_calls, "cost_usd": round(r.cost, 4)})
            s.add(SleeveRunRow(id=run_id, as_of=day.isoformat(), rev=rev, trigger=trigger, created_at=stamp,
                               summary=json.dumps(summary, ensure_ascii=False), ai_calls=sum(r.ai_calls for r in results),
                               cost_usd=round(sum(r.cost for r in results), 6)))
        parts = []
        for item in summary:
            acts = ", ".join(f"{logic.ACTION_LABELS[k]} {v}" for k, v in item["tally"].items())
            parts.append(f"'{item['name']}' {acts}")
        self.svc._log(self.svc.settings().env, Event("sleeve", f"바구니 심의(r{rev}): " + " · ".join(parts),
                                                     payload={"run_id": run_id, "trigger": trigger}), day=day)
        self.svc.bus.publish("sleeves")
        return {"run_id": run_id, "as_of": day.isoformat(), "rev": rev, "sleeves": summary, "fills": fills,
                "ai_calls": sum(r.ai_calls for r in results), "cost_usd": round(sum(r.cost for r in results), 4)}

    def settle(self, market: Market) -> list[dict[str, Any]]:
        """대기 주문을 만든 날 다음 거래일 시가에 체결한다. 봉이 안 생기면 기다리다 만료한다."""
        day = market.last_day()
        base_costs = self.svc.settings().cost_model()
        stamp = _stamp()
        fills: list[dict[str, Any]] = []
        with self.sf() as s, s.begin():
            orders = s.execute(select(SleeveOrderRow).where(SleeveOrderRow.status == "pending")).scalars().all()
            if not orders:
                return fills
            rows = self._books(s)
            books = {sid: logic.Book.from_dict(json.loads(row.state)) for sid, row in rows.items()}
            plan_rev = self.current()
            rev = plan_rev[0].rev if plan_rev else 0
            work: list[tuple[date, int, SleeveOrderRow]] = []
            for o in orders:
                made = date.fromisoformat(o.made_on)
                feat = market.stocks.get(o.code)
                t_made = market.cal_index(made)
                fill_day = None
                if feat is not None and t_made is not None:
                    for t in range(t_made + 1, len(market.calendar)):
                        d = market.calendar[t]
                        if feat.index_of(d) is not None:
                            fill_day = d
                            break
                if fill_day is None:
                    elapsed = (len(market.calendar) - 1 - t_made) if t_made is not None else logic.ORDER_EXPIRY_DAYS
                    if elapsed >= logic.ORDER_EXPIRY_DAYS:
                        o.status, o.note = "expired", f"{logic.ORDER_EXPIRY_DAYS}거래일 동안 체결할 봉이 없어 만료"
                    continue
                if fill_day > day:
                    continue
                work.append((fill_day, 0 if o.side == "sell" else 1, o))
            work.sort(key=lambda w: (w[0], w[1], w[2].made_on))
            for fill_day, _, o in work:
                book = books.get(o.sleeve_id)
                feat = market.stocks[o.code]
                i = feat.index_of(fill_day)
                assert i is not None
                if book is None:
                    o.status, o.note = "cancelled", "바구니가 없어 취소"
                    continue
                costs = logic.costs_for(o.kind, base_costs)
                fill = (logic.fill_buy(book, o.code, o.name, o.kind, o.qty, float(feat.open[i]), costs) if o.side == "buy"
                        else logic.fill_sell(book, o.code, o.qty, float(feat.open[i]), costs))
                if fill is None:
                    o.status, o.note, o.filled_on = "expired", "현금이 모자라거나 보유가 없어 체결하지 못함", fill_day.isoformat()
                    continue
                o.status, o.filled_on = "filled", fill_day.isoformat()
                if fill.qty < o.qty:
                    o.note = f"현금이 모자라 {fill.qty}주만 체결"
                s.add(SleeveTradeRow(sleeve_id=o.sleeve_id, rev=rev, d=fill_day.isoformat(), kind=fill.side, code=o.code, name=o.name,
                                     qty=fill.qty, price=fill.price, amount=fill.amount, fee=fill.fee, tax=fill.tax, pnl=fill.pnl,
                                     order_id=o.id, created_at=stamp))
                fills.append({"sleeve_id": o.sleeve_id, "day": fill_day.isoformat(), "code": o.code, "name": o.name, "side": fill.side,
                              "qty": fill.qty, "price": fill.price, "pnl": fill.pnl})
            for sid, book in books.items():
                rows[sid].state, rows[sid].updated_at = json.dumps(book.to_dict()), stamp
        if fills:
            text = ", ".join(f"{f['name']} {'매수' if f['side'] == 'buy' else '매도'} {f['qty']}주" for f in fills[:6])
            self.svc._log(self.svc.settings().env, Event("sleeve", f"바구니 가상 체결 {len(fills)}건: {text}"), day=day)
        return fills

    def liquidate(self, sleeve_id: str) -> dict[str, Any]:
        """가상 보유를 모두 다음 거래일 시가에 파는 주문을 넣는다."""
        cur = self.current()
        cfg = cur[1].sleeve(sleeve_id) if cur else None
        market = self.market()
        if cfg is None or market is None:
            raise EngineError("바구니를 찾을 수 없습니다")
        if cfg.mode != "paper":
            raise EngineError("알림만 바구니에는 가상 보유가 없습니다")
        day = market.last_day().isoformat()
        with self.sf() as s, s.begin():
            row = s.get(SleeveBookRow, sleeve_id)
            book = logic.Book.from_dict(json.loads(row.state)) if row else None
            if book is None or not book.positions:
                raise EngineError("팔 가상 보유 종목이 없습니다")
            s.execute(update(SleeveOrderRow).where(SleeveOrderRow.sleeve_id == sleeve_id, SleeveOrderRow.status == "pending")
                      .values(status="cancelled", note="모두 팔기로 취소"))
            for code, lot in book.positions.items():
                s.add(SleeveOrderRow(id=_new_id("o", 16), sleeve_id=sleeve_id, signal_id="", rev=cur[0].rev if cur else 0, made_on=day,
                                     code=code, name=lot.name, kind=lot.kind, side="sell", qty=lot.qty, status="pending", note="모두 팔기"))
            count = len(book.positions)
        self.svc._log(self.svc.settings().env, Event("sleeve", f"'{cfg.name}' 바구니 모두 팔기 예약 {count}종목(다음 거래일 시가)"))
        self.svc.bus.publish("sleeves")
        return {"orders": count}

    # ── 성과 ─────────────────────────────────────────────────────────────

    def book_curve(self, sleeve_id: str, market: Market, start: date | None = None) -> dict[str, list]:
        """체결·입출금 기록으로 바구니의 날짜별 평가금액을 다시 만든다."""
        with self.sf() as s:
            trades = s.execute(select(SleeveTradeRow).where(SleeveTradeRow.sleeve_id == sleeve_id).order_by(SleeveTradeRow.d, SleeveTradeRow.id)).scalars().all()
        if not trades:
            return {"dates": [], "equity": [], "contributed": []}
        first = date.fromisoformat(trades[0].d)
        begin = max(first, start) if start else first
        by_day: dict[str, list[SleeveTradeRow]] = {}
        for tr in trades:
            by_day.setdefault(tr.d, []).append(tr)
        cash, contributed = 0, 0
        qty: dict[str, int] = {}
        dates, equity, flows = [], [], []
        t0 = next((t for t, d in enumerate(market.calendar) if d >= first), len(market.calendar))
        for t in range(t0, len(market.calendar)):
            d = market.calendar[t]
            for tr in by_day.pop(d.isoformat(), []):
                if tr.kind == "deposit":
                    cash += tr.amount
                    contributed += tr.amount
                elif tr.kind == "withdraw":
                    cash -= tr.amount
                    contributed -= tr.amount
                elif tr.kind == "buy":
                    cash -= tr.amount + tr.fee
                    qty[tr.code] = qty.get(tr.code, 0) + tr.qty
                elif tr.kind == "sell":
                    cash += tr.amount - tr.fee - tr.tax
                    qty[tr.code] = qty.get(tr.code, 0) - tr.qty
            value = 0.0
            for code, q in qty.items():
                feat = market.stocks.get(code)
                j = feat.last_index_on_or_before(d) if feat is not None else None
                if q and feat is not None and j is not None:
                    value += q * float(feat.close[j])
            if d >= begin:
                dates.append(d.isoformat())
                equity.append(round(cash + value))
                flows.append(contributed)
        return {"dates": dates, "equity": equity, "contributed": flows}

    def performance(self, sleeve_id: str) -> dict[str, Any]:
        cur = self.current()
        cfg = cur[1].sleeve(sleeve_id) if cur else None
        market = self.market()
        if cfg is None or market is None:
            raise EngineError("바구니를 찾을 수 없습니다")
        books = self._load_books()
        book = books.get(sleeve_id)
        start = date.fromisoformat(book.started_on) if book and book.started_on else market.last_day()
        out = self._compare(cfg, market, start, market.last_day())
        if cfg.mode == "paper":
            curve = self.book_curve(sleeve_id, market, start)
            base = curve["contributed"][-1] if curve["contributed"] else cfg.amount
            out["book"] = {"dates": curve["dates"], "equity": curve["equity"], "contributed": curve["contributed"],
                           "summary": {"return_pct": round(curve["equity"][-1] / base - 1, 5) if curve["equity"] and base else 0.0}}
        out["started_on"] = start.isoformat()
        return out

    def _compare(self, cfg: SleeveConfig, market: Market, start: date, end: date) -> dict[str, Any]:
        costs = self.svc.settings().cost_model()
        out: dict[str, Any] = {"sleeve_id": cfg.id, "name": cfg.name, "start": start.isoformat(), "end": end.isoformat()}
        for policy in ("dca", "rules"):
            r = logic.replay(market, self.svc.regimes, cfg, start, end, policy, costs)
            out[policy] = {"dates": [d.isoformat() for d in r.dates], "equity": [round(e) for e in r.equity], "summary": r.summary(cfg.amount)}
        return out

    async def preview(self, plan: PlanConfig | None, start: date) -> dict[str, Any]:
        """과거 시작일부터 두 기준선(단순 적립·규칙만)으로 돌려 본다. AI는 쓰지 않는다."""
        target = plan or (self.current() or (None, None))[1]
        if target is None or not target.sleeves:
            raise EngineError("미리 볼 바구니가 없습니다")
        market = await asyncio.to_thread(self.market, target.codes())
        if market is None:
            raise EngineError("일봉 데이터가 없습니다")
        missing = [i.code for sl in target.sleeves for i in sl.items if i.code not in market.stocks]
        if missing:
            raise EngineError(f"일봉이 없는 종목이 있습니다: {', '.join(missing)}")
        end = market.last_day()
        if start >= end:
            raise EngineError("시작일은 최신 일봉보다 앞이어야 합니다")
        sleeves = []
        for i, sl in enumerate(target.sleeves):
            cfg = sl if sl.id else sl.model_copy(update={"id": f"s{i:06x}"})
            sleeves.append(await asyncio.to_thread(self._compare, cfg, market, start, end))
        kospi = market.indexes["KOSPI"]
        t0 = next((t for t, d in enumerate(market.calendar) if d >= start), 0)
        base = float(kospi.close[t0])
        bench = {"dates": [d.isoformat() for d in market.calendar[t0:]], "value": [round(float(c) / base - 1, 5) for c in kospi.close[t0:]]}
        return {"start": market.calendar[t0].isoformat(), "end": end.isoformat(), "sleeves": sleeves, "kospi": bench,
                "note": "규칙과 단순 적립만 과거로 돌립니다. AI 판단은 과거 주가를 이미 알 수 있어 넣지 않습니다. 지금 상장된 종목만 쓰므로 결과가 실제보다 좋게 나올 수 있습니다."}

    # ── 화면 ─────────────────────────────────────────────────────────────

    def overview(self) -> dict[str, Any]:
        cur = self.current()
        market = self.market()
        estimate = self.estimate()
        base = {"busy": self.busy, "data_day": market.last_day().isoformat() if market else None, "estimate": estimate,
                "options": {"cadence": CADENCE_LABELS, "decider": DECIDER_LABELS, "mode": MODE_LABELS, "kind": KIND_LABELS,
                            "actions": logic.ACTION_LABELS, "multipliers": logic.BUY_MULTIPLIER}}
        if cur is None:
            return {**base, "plan": None, "sleeves": [], "last_run": None}
        rev_row, plan = cur
        prices = market.prices_on(market.last_day()) if market else {}
        with self.sf() as s:
            book_rows = self._books(s)
            pending = s.execute(select(SleeveOrderRow).where(SleeveOrderRow.status == "pending").order_by(SleeveOrderRow.made_on)).scalars().all()
            last_run = s.execute(select(SleeveRunRow).where(SleeveRunRow.replaced.is_(False)).order_by(SleeveRunRow.created_at.desc()).limit(1)).scalar_one_or_none()
            latest: dict[str, list[SleeveSignalRow]] = {}
            for sl in plan.sleeves:
                day = s.execute(select(SleeveSignalRow.as_of).where(SleeveSignalRow.sleeve_id == sl.id, SleeveSignalRow.replaced.is_(False))
                                .order_by(SleeveSignalRow.as_of.desc()).limit(1)).scalar_one_or_none()
                latest[sl.id] = list(s.execute(select(SleeveSignalRow).where(SleeveSignalRow.sleeve_id == sl.id, SleeveSignalRow.as_of == day,
                                                                             SleeveSignalRow.replaced.is_(False))).scalars()) if day else []
        sleeves = []
        for sl in plan.sleeves:
            row = book_rows.get(sl.id)
            book = logic.Book.from_dict(json.loads(row.state)) if row else logic.Book(cash=sl.amount, contributed=sl.amount)
            positions = []
            for code, lot in book.positions.items():
                close = prices.get(code, lot.avg)
                positions.append({"code": code, "name": lot.name, "kind": lot.kind, "qty": lot.qty, "avg": round(lot.avg), "close": close,
                                  "value": round(lot.qty * close), "pnl_pct": round(close / lot.avg - 1, 4) if lot.avg else 0.0})
            equity = book.equity(prices)
            last = date.fromisoformat(book.last_run) if book.last_run else None
            sleeves.append({
                **sl.model_dump(), "cadence_label": CADENCE_LABELS[sl.cadence], "decider_label": DECIDER_LABELS[sl.decider],
                "mode_label": MODE_LABELS[sl.mode],
                "due": bool(market) and logic.is_due(sl.cadence, market.last_day(), last) if market else False,
                "book": {"cash": book.cash, "equity": round(equity), "contributed": book.contributed,
                         "return_pct": round(equity / book.contributed - 1, 5) if book.contributed and sl.mode == "paper" else None,
                         "installments_done": book.installments_done, "started_on": book.started_on, "last_run": book.last_run,
                         "carry": round(sum(book.carry.values())), "positions": sorted(positions, key=lambda p: -p["value"])},
                "latest": [signal_to_dict(g) for g in latest.get(sl.id, [])],
                "pending": [{"id": o.id, "code": o.code, "name": o.name, "side": o.side, "qty": o.qty, "made_on": o.made_on, "note": o.note}
                            for o in pending if o.sleeve_id == sl.id],
            })
        return {
            **base,
            "plan": {"rev": rev_row.rev, "created_at": rev_row.created_at, "day": rev_row.day, "note": rev_row.note, "total": plan.total,
                     "allocated": sum(sl.amount for sl in plan.sleeves), "config": plan.model_dump()},
            "sleeves": sleeves,
            "prices": {code: prices[code] for code in plan.codes() if code in prices},
            "last_run": run_to_dict(last_run) if last_run else None,
        }

    def revisions(self) -> list[dict[str, Any]]:
        with self.sf() as s:
            rows = list(s.execute(select(PlanRevisionRow).order_by(PlanRevisionRow.rev)).scalars())
            runs = s.execute(select(SleeveRunRow.rev, SleeveRunRow.id).where(SleeveRunRow.replaced.is_(False))).all()
            signals = s.execute(select(SleeveSignalRow.rev, SleeveSignalRow.action).where(SleeveSignalRow.replaced.is_(False))).all()
            trades = s.execute(select(SleeveTradeRow.rev, SleeveTradeRow.kind)).all()
        run_count: dict[int, int] = {}
        for rev, _ in runs:
            run_count[rev] = run_count.get(rev, 0) + 1
        sig: dict[int, dict[str, int]] = {}
        for rev, action in signals:
            sig.setdefault(rev, {})
            sig[rev][action] = sig[rev].get(action, 0) + 1
        fills: dict[int, int] = {}
        for rev, kind in trades:
            if kind in ("buy", "sell"):
                fills[rev] = fills.get(rev, 0) + 1
        combined = self._combined_curve()
        out = []
        prev: PlanConfig | None = None
        latest = rows[-1].rev if rows else None
        for k, row in enumerate(rows):
            cfg = PlanConfig.model_validate_json(row.config)
            end_day = rows[k + 1].day if k + 1 < len(rows) else None
            out.append({
                "rev": row.rev, "created_at": row.created_at, "day": row.day, "note": row.note, "restored_from": row.restored_from,
                "current": row.rev == latest, "changes": plan_changes(prev, cfg), "config": cfg.model_dump(),
                "runs": run_count.get(row.rev, 0), "signals": sig.get(row.rev, {}), "fills": fills.get(row.rev, 0),
                "period": {"start": row.day, "end": end_day, **_period_return(combined, row.day, end_day)},
            })
            prev = cfg
        return out[::-1]

    def _combined_curve(self) -> dict[str, tuple[float, float]]:
        """날짜 → (가상 운용 바구니 평가금액 합, 넣은 돈 합)."""
        market = self.market()
        if market is None:
            return {}
        with self.sf() as s:
            ids = [sid for (sid,) in s.execute(select(SleeveTradeRow.sleeve_id).group_by(SleeveTradeRow.sleeve_id))]
        total: dict[str, list[float]] = {}
        for sid in ids:
            curve = self.book_curve(sid, market)
            for d, e, c in zip(curve["dates"], curve["equity"], curve["contributed"], strict=True):
                acc = total.setdefault(d, [0.0, 0.0])
                acc[0] += e
                acc[1] += c
        return {d: (v[0], v[1]) for d, v in total.items()}

    def signals(self, sleeve_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.sf() as s:
            stmt = select(SleeveSignalRow).where(SleeveSignalRow.replaced.is_(False))
            if sleeve_id:
                stmt = stmt.where(SleeveSignalRow.sleeve_id == sleeve_id)
            rows = s.execute(stmt.order_by(SleeveSignalRow.as_of.desc(), SleeveSignalRow.sleeve_id, SleeveSignalRow.code).limit(limit)).scalars().all()
        return [signal_to_dict(r) for r in rows]

    def signal(self, signal_id: str) -> dict[str, Any]:
        with self.sf() as s:
            row = s.get(SleeveSignalRow, signal_id)
        if row is None:
            raise EngineError("판단 기록을 찾을 수 없습니다")
        return {**signal_to_dict(row), "transcript": json.loads(row.transcript) if row.transcript else None}


def _period_return(combined: dict[str, tuple[float, float]], start: str, end: str | None) -> dict[str, Any]:
    days = sorted(d for d in combined if d >= start and (end is None or d <= end))
    if len(days) < 2:
        return {"return_pct": None}
    e0, c0 = combined[days[0]]
    e1, c1 = combined[days[-1]]
    flows = c1 - c0
    if e0 <= 0:
        return {"return_pct": None}
    return {"return_pct": round((e1 - flows) / e0 - 1, 5)}


def signal_to_dict(row: SleeveSignalRow) -> dict[str, Any]:
    body = json.loads(row.body)
    return {"id": row.id, "run_id": row.run_id, "sleeve_id": row.sleeve_id, "rev": row.rev, "as_of": row.as_of, "code": row.code,
            "name": row.name, "action": row.action, "action_label": logic.ACTION_LABELS.get(row.action, row.action),
            "rules_action": row.rules_action, "conviction": row.conviction, "conviction_label": CONVICTION_LABEL.get(row.conviction, ""),
            "source": row.source, "status": row.status, "score": row.score, "close": row.close, "qty": row.qty, "amount": row.amount,
            "cost_usd": row.cost_usd, "has_transcript": bool(row.transcript), **body}


def run_to_dict(row: SleeveRunRow) -> dict[str, Any]:
    return {"id": row.id, "as_of": row.as_of, "rev": row.rev, "trigger": row.trigger, "created_at": row.created_at,
            "sleeves": json.loads(row.summary), "ai_calls": row.ai_calls, "cost_usd": row.cost_usd}
