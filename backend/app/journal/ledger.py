"""해시로 이어 붙인 원장.

엔진이 한 일과 안 한 일(탈락·거부·만료)을 모두 한 줄씩 남긴다. 각 줄은 앞 줄의 해시를 포함해
해시를 만들기 때문에, 중간 기록을 고치거나 지우면 그 뒤의 검증이 깨진다(변조 감지).
화면의 '통장정리'가 이 원장을 읽는다.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import now_kst
from app.store.db import LedgerRow

GENESIS_HASH = "0" * 64

# 적요 유형 → 화면 표시 이름
KIND_LABELS: dict[str, str] = {
    "fill_buy": "매수 체결",
    "fill_sell": "매도 체결",
    "protective": "보호 청산",
    "stop_raise": "손절 상향",
    "decision": "위원회 판단",
    "gate_reduce": "수량 축소",
    "gate_block": "리스크 거부",
    "precheck": "사전 제외",
    "intent": "주문 계획",
    "approve": "승인",
    "reject": "거절",
    "expire": "만료",
    "skip": "미체결",
    "screen_out": "순위 밖",
    "cycle": "장후 심의",
    "regime": "시장 국면",
    "breaker": "손실 차단",
    "engine": "엔진",
    "settings": "설정 변경",
    "sleeve": "내 종목 운용",
    "data": "데이터",
    "broker": "증권사",
    "error": "오류",
}
MONEY_KINDS = frozenset({"fill_buy", "fill_sell", "protective"})


def _canonical(fields: dict[str, Any]) -> str:
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, fields: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(fields)).encode("utf-8")).hexdigest()


def _hash_fields(row: LedgerRow) -> dict[str, Any]:
    return {
        "ts": row.ts, "env": row.env, "day": row.day, "kind": row.kind, "chain_id": row.chain_id,
        "code": row.code, "name": row.name, "summary": row.summary, "qty": row.qty, "amount": row.amount,
        "cash_after": row.cash_after, "payload": row.payload,
    }


class Ledger:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory
        self._lock = threading.Lock()

    def append(
        self,
        *,
        env: str,
        kind: str,
        summary: str,
        day: str | None = None,
        chain_id: str = "",
        code: str | None = None,
        name: str | None = None,
        qty: int | None = None,
        amount: int | None = None,
        cash_after: int | None = None,
        payload: dict[str, Any] | None = None,
        ts: datetime | None = None,
    ) -> int:
        """한 줄을 덧붙이고 일련번호(거래번호)를 돌려준다."""
        with self._lock, self._sf() as s, s.begin():
            last = s.execute(select(LedgerRow.hash).order_by(LedgerRow.seq.desc()).limit(1)).scalar_one_or_none()
            row = LedgerRow(
                ts=(ts or now_kst()).isoformat(timespec="seconds"), env=env, day=day, kind=kind,
                chain_id=chain_id, code=code, name=name, summary=summary, qty=qty, amount=amount,
                cash_after=cash_after, payload=_canonical(payload or {}), prev_hash=last or GENESIS_HASH, hash="",
            )
            row.hash = compute_hash(row.prev_hash, _hash_fields(row))
            s.add(row)
            s.flush()
            return int(row.seq)

    def verify(self) -> tuple[bool, int | None]:
        """(이상 없음 여부, 처음 깨진 일련번호)."""
        prev = GENESIS_HASH
        with self._sf() as s:
            for row in s.execute(select(LedgerRow).order_by(LedgerRow.seq)).scalars():
                if row.prev_hash != prev or row.hash != compute_hash(row.prev_hash, _hash_fields(row)):
                    return False, int(row.seq)
                prev = row.hash
        return True, None

    def rows(
        self,
        *,
        env: str | None = None,
        after_seq: int = 0,
        before_seq: int | None = None,
        kinds: Iterable[str] | None = None,
        chain_id: str | None = None,
        code: str | None = None,
        limit: int = 200,
        newest_first: bool = True,
    ) -> list[LedgerRow]:
        stmt = select(LedgerRow).where(LedgerRow.seq > after_seq)
        if env:
            stmt = stmt.where(LedgerRow.env == env)
        if before_seq is not None:
            stmt = stmt.where(LedgerRow.seq < before_seq)
        if kinds:
            stmt = stmt.where(LedgerRow.kind.in_(list(kinds)))
        if chain_id:
            stmt = stmt.where(LedgerRow.chain_id == chain_id)
        if code:
            stmt = stmt.where(LedgerRow.code == code)
        stmt = stmt.order_by(LedgerRow.seq.desc() if newest_first else LedgerRow.seq).limit(limit)
        with self._sf() as s:
            return list(s.execute(stmt).scalars())

    def last_seq(self, env: str | None = None) -> int:
        stmt = select(LedgerRow.seq).order_by(LedgerRow.seq.desc()).limit(1)
        if env:
            stmt = stmt.where(LedgerRow.env == env)
        with self._sf() as s:
            return int(s.execute(stmt).scalar_one_or_none() or 0)

    def to_csv(self, env: str | None = None) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["거래번호", "시각", "환경", "거래일", "유형", "종목코드", "종목명", "적요", "수량", "금액", "현금잔액", "판단사슬", "해시"])
        for row in self.rows(env=env, limit=1_000_000, newest_first=False):
            writer.writerow([row.seq, row.ts, row.env, row.day or "", KIND_LABELS.get(row.kind, row.kind), row.code or "",
                             row.name or "", row.summary, row.qty if row.qty is not None else "",
                             row.amount if row.amount is not None else "", row.cash_after if row.cash_after is not None else "",
                             row.chain_id, row.hash])
        return buffer.getvalue()


def row_to_dict(row: LedgerRow) -> dict[str, Any]:
    return {
        "seq": row.seq, "ts": row.ts, "env": row.env, "day": row.day, "kind": row.kind,
        "kind_label": KIND_LABELS.get(row.kind, row.kind), "chain_id": row.chain_id, "code": row.code,
        "name": row.name, "summary": row.summary, "qty": row.qty, "amount": row.amount,
        "cash_after": row.cash_after, "payload": json.loads(row.payload or "{}"),
    }
