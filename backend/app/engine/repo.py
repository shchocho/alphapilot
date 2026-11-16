"""엔진 상태의 DB 저장·복원. 도메인 객체(Portfolio, Intent …)와 표 사이를 오간다."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.models import Fill, Intent, Portfolio, Position
from app.engine.core import DecisionRecord
from app.store.db import AccountRow, DecisionRow, EquityRow, IntentRow, PositionRow, TradeRow

_INTENT_COLUMNS = {"id", "chain_id", "decision_id", "created_on", "trade_date", "code", "name", "side", "qty", "status"}
_POSITION_COLUMNS = {"code", "name", "qty", "avg_price"}


def _stamp() -> str:
    return now_kst().isoformat(timespec="seconds")


# ── 계좌·보유 ────────────────────────────────────────────────────────────────

def get_account(s: Session, env: str, initial_cash: int) -> AccountRow:
    row = s.get(AccountRow, env)
    if row is None:
        row = AccountRow(env=env, cash=initial_cash, initial_cash=initial_cash, peak_equity=float(initial_cash), sim_day=None)
        s.add(row)
        s.flush()
    return row


def load_portfolio(s: Session, env: str, initial_cash: int) -> Portfolio:
    account = get_account(s, env, initial_cash)
    positions: dict[str, Position] = {}
    for row in s.execute(select(PositionRow).where(PositionRow.env == env)).scalars():
        body = json.loads(row.body)
        body["opened_on"] = date.fromisoformat(body["opened_on"])
        positions[row.code] = Position(code=row.code, name=row.name, qty=row.qty, avg_price=row.avg_price, **body)
    return Portfolio(cash=int(account.cash), positions=positions, peak_equity=float(account.peak_equity))


def save_portfolio(s: Session, env: str, portfolio: Portfolio, initial_cash: int) -> None:
    account = get_account(s, env, initial_cash)
    account.cash = int(portfolio.cash)
    account.peak_equity = float(portfolio.peak_equity)
    s.execute(delete(PositionRow).where(PositionRow.env == env))
    for pos in portfolio.positions.values():
        body = {k: v for k, v in asdict(pos).items() if k not in _POSITION_COLUMNS}
        body["opened_on"] = pos.opened_on.isoformat()
        s.add(PositionRow(env=env, code=pos.code, name=pos.name, qty=pos.qty, avg_price=pos.avg_price,
                          body=json.dumps(body, ensure_ascii=False)))


# ── 주문 계획 ─────────────────────────────────────────────────────────────────

def intent_to_row(env: str, intent: Intent, expires_at: str | None = None) -> IntentRow:
    data = asdict(intent)
    body = {k: v for k, v in data.items() if k not in _INTENT_COLUMNS}
    return IntentRow(
        id=intent.id, env=env, chain_id=intent.chain_id, decision_id=intent.decision_id,
        created_on=intent.created_on.isoformat(), trade_date=intent.trade_date.isoformat(), code=intent.code,
        name=intent.name, side=intent.side, qty=intent.qty, status=intent.status,
        body=json.dumps(body, ensure_ascii=False, default=str), expires_at=expires_at, created_at=_stamp(),
    )


def row_to_intent(row: IntentRow) -> Intent:
    body = json.loads(row.body)
    known = {f.name for f in fields(Intent)}
    extra = {k: v for k, v in body.items() if k in known}
    return Intent(
        id=row.id, chain_id=row.chain_id, created_on=date.fromisoformat(row.created_on),
        trade_date=date.fromisoformat(row.trade_date), code=row.code, name=row.name, side=row.side,  # type: ignore[arg-type]
        qty=row.qty, status=row.status, decision_id=row.decision_id, **{k: v for k, v in extra.items() if k not in _INTENT_COLUMNS},
    )


def intent_to_dict(row: IntentRow) -> dict[str, Any]:
    body = json.loads(row.body)
    return {
        "id": row.id, "env": row.env, "chain_id": row.chain_id, "decision_id": row.decision_id, "created_on": row.created_on,
        "trade_date": row.trade_date, "code": row.code, "name": row.name, "side": row.side, "qty": row.qty,
        "status": row.status, "expires_at": row.expires_at, "decided_at": row.decided_at, **body,
    }


def upsert_intent(s: Session, env: str, intent: Intent, expires_at: str | None = None) -> None:
    existing = s.get(IntentRow, intent.id)
    if existing is not None:
        s.delete(existing)
        s.flush()
    s.add(intent_to_row(env, intent, expires_at))


def sync_intent_status(s: Session, intent: Intent) -> None:
    row = s.get(IntentRow, intent.id)
    if row is None:
        return
    row.status = intent.status
    row.qty = intent.qty
    body = json.loads(row.body)
    body["note"] = intent.note
    row.body = json.dumps(body, ensure_ascii=False, default=str)


def intents_for(s: Session, env: str, *, trade_date: date | None = None, statuses: tuple[str, ...] | None = None) -> list[IntentRow]:
    stmt = select(IntentRow).where(IntentRow.env == env)
    if trade_date is not None:
        stmt = stmt.where(IntentRow.trade_date == trade_date.isoformat())
    if statuses:
        stmt = stmt.where(IntentRow.status.in_(statuses))
    return list(s.execute(stmt.order_by(IntentRow.created_at, IntentRow.id)).scalars())


# ── 판단·체결·자산 ────────────────────────────────────────────────────────────

def save_decision(s: Session, env: str, record: DecisionRecord) -> None:
    existing = s.get(DecisionRow, record.id)
    if existing is not None:
        s.delete(existing)
        s.flush()
    cost = float((record.transcript or {}).get("cost_usd", 0.0))
    s.add(DecisionRow(
        id=record.id, env=env, as_of=record.as_of.isoformat(), code=record.info.code, name=record.info.name,
        kind=record.kind, action=record.decision.action, conviction=record.decision.conviction,
        source=record.decision.source, status=record.decision.status, chain_id=record.chain_id,
        body=json.dumps(record.to_body(), ensure_ascii=False, default=str), cost_usd=cost, created_at=_stamp(),
    ))


def decision_to_dict(row: DecisionRow, *, full: bool = True) -> dict[str, Any]:
    body = json.loads(row.body)
    base = {
        "id": row.id, "env": row.env, "as_of": row.as_of, "code": row.code, "name": row.name, "kind": row.kind,
        "action": row.action, "conviction": row.conviction, "source": row.source, "status": row.status,
        "chain_id": row.chain_id, "cost_usd": row.cost_usd, "created_at": row.created_at,
    }
    if full:
        return {**base, **body}
    final = body.get("final", {})
    gate = body.get("gate") or {}
    return {**base, "thesis": final.get("thesis", ""), "votes": final.get("votes", {}), "status_detail": final.get("status_detail", ""),
            "gate_summary": gate.get("summary"), "gate_qty": gate.get("qty"), "intent_id": body.get("intent_id"),
            "technique": body.get("technique", ""),
            "close": body.get("close"), "sector": body.get("sector")}


def save_fill(s: Session, env: str, fill: Fill, broker_order_id: str | None = None) -> None:
    s.add(TradeRow(
        env=env, day=fill.day.isoformat(), code=fill.code, name=fill.name, side=fill.side, qty=fill.qty, price=fill.price,
        fee=fill.fee, tax=fill.tax, reason=fill.reason, technique=fill.technique, chain_id=fill.chain_id,
        intent_id=fill.intent_id, pnl=fill.pnl, pnl_pct=fill.pnl_pct, hold_days=fill.hold_days, broker_order_id=broker_order_id,
    ))


def trade_to_dict(row: TradeRow) -> dict[str, Any]:
    return {
        "id": row.id, "day": row.day, "code": row.code, "name": row.name, "side": row.side, "qty": row.qty, "price": row.price,
        "fee": row.fee, "tax": row.tax, "reason": row.reason, "technique": row.technique, "chain_id": row.chain_id,
        "pnl": row.pnl, "pnl_pct": row.pnl_pct, "hold_days": row.hold_days, "amount": row.qty * row.price,
    }


def save_equity(s: Session, env: str, day: date, equity: float, cash: int, exposure: float, benchmark: float | None) -> None:
    row = s.get(EquityRow, (env, day.isoformat()))
    if row is None:
        s.add(EquityRow(env=env, d=day.isoformat(), equity=equity, cash=cash, exposure=exposure, benchmark=benchmark))
    else:
        row.equity, row.cash, row.exposure, row.benchmark = equity, cash, exposure, benchmark


def equity_history(s: Session, env: str) -> list[tuple[date, float]]:
    rows = s.execute(select(EquityRow.d, EquityRow.equity).where(EquityRow.env == env).order_by(EquityRow.d)).all()
    return [(date.fromisoformat(d), float(e)) for d, e in rows]


def recent_exits(s: Session, env: str, limit: int = 10) -> list[tuple[date, str, float]]:
    rows = s.execute(
        select(TradeRow.day, TradeRow.reason, TradeRow.pnl).where(TradeRow.env == env, TradeRow.side == "sell")
        .order_by(TradeRow.id.desc()).limit(limit)
    ).all()
    return [(date.fromisoformat(d), reason, float(pnl or 0)) for d, reason, pnl in reversed(rows)]


def orders_on(s: Session, env: str, day: date) -> int:
    return int(s.execute(select(func.count()).select_from(TradeRow).where(TradeRow.env == env, TradeRow.day == day.isoformat())).scalar_one())


def reset_env(s: Session, env: str, initial_cash: int) -> None:
    """한 환경의 계좌·보유·주문 계획·체결·자산 기록을 지운다(시뮬레이션 다시 시작). 원장은 지우지 않는다."""
    for table in (PositionRow, IntentRow, TradeRow, EquityRow, DecisionRow):
        s.execute(delete(table).where(table.env == env))
    account = s.get(AccountRow, env)
    if account is not None:
        s.delete(account)
        s.flush()
    s.add(AccountRow(env=env, cash=initial_cash, initial_cash=initial_cash, peak_equity=float(initial_cash), sim_day=None))
