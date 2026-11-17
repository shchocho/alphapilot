"""운영 중 DB 관리: 온라인 백업, 만료된 로그인 기록 정리, WAL 정리, 무결성 점검.

서버가 돌고 있는 채로 실행해도 된다. 백업은 SQLite 온라인 백업 API를 쓰므로 쓰기 중에도 일관된 사본이 나온다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import now_kst
from app.store.db import LoginAttemptRow, SessionRow

BACKUP_PREFIX = "alphapilot"


def is_file_db(engine: Engine) -> bool:
    database = engine.url.database
    return bool(database) and database != ":memory:"


def backup_file(engine: Engine, dest_dir: Path, label: str = "daily", *, keep: int | None = None,
                now: datetime | None = None) -> Path:
    """DB 사본을 dest_dir/alphapilot-<label>-<시각>.db로 만든다. keep이 있으면 같은 label의 오래된 사본을 그 개수만 남긴다."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or now_kst()).strftime("%Y%m%d-%H%M%S")
    target = dest_dir / f"{BACKUP_PREFIX}-{label}-{stamp}.db"
    raw = engine.raw_connection()
    try:
        copy = sqlite3.connect(target)
        try:
            raw.driver_connection.backup(copy)
        finally:
            copy.close()
    finally:
        raw.close()
    if keep is not None:
        prune_backups(dest_dir, label, keep)
    return target


def prune_backups(dest_dir: Path, label: str, keep: int) -> list[Path]:
    """같은 label의 사본 중 최근 keep개만 남기고 지운다. 이 모듈이 만든 이름의 파일만 건드린다."""
    copies = sorted(dest_dir.glob(f"{BACKUP_PREFIX}-{label}-*.db"), key=lambda p: p.name, reverse=True)
    removed = copies[max(keep, 1):]
    for old in removed:
        old.unlink(missing_ok=True)
    return removed


def prune_auth_records(session_factory: sessionmaker[Session], now: datetime, *, idle_timeout: timedelta,
                       login_keep: timedelta = timedelta(days=30)) -> dict[str, int]:
    """만료된 세션과 오래된 로그인 시도 기록을 지운다. 감사 기록(audit)과 원장은 지우지 않는다."""
    now_text = now.isoformat(timespec="seconds")
    idle_cutoff = (now - idle_timeout).isoformat(timespec="seconds")
    login_cutoff = (now - login_keep).isoformat(timespec="seconds")
    with session_factory() as s, s.begin():
        sessions = s.execute(delete(SessionRow).where(
            (SessionRow.expires_at <= now_text) | (SessionRow.last_seen < idle_cutoff))).rowcount
        attempts = s.execute(delete(LoginAttemptRow).where(LoginAttemptRow.ts < login_cutoff)).rowcount
    return {"sessions": int(sessions or 0), "login_attempts": int(attempts or 0)}


def quick_check(engine: Engine) -> str:
    """PRAGMA quick_check 결과. 정상이면 'ok'."""
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA quick_check").fetchall()
    return "; ".join(str(r[0]) for r in rows[:5]) or "ok"


def compact(engine: Engine) -> None:
    """WAL 파일을 본 DB에 합쳐 비우고, 쿼리 통계를 갱신한다."""
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.exec_driver_sql("PRAGMA optimize")


@dataclass(slots=True)
class MaintenancePlan:
    backup_dir: Path | None  # None이면 백업하지 않는다
    backup_keep: int  # 0이면 백업하지 않는다
    idle_timeout: timedelta
    login_keep: timedelta = timedelta(days=30)


def run_daily(engine: Engine, session_factory: sessionmaker[Session], plan: MaintenancePlan, now: datetime) -> dict[str, object]:
    """하루 한 번 하는 점검을 모두 돌리고 결과를 돌려준다. 백업이 무결성 점검보다 먼저다(점검이 실패해도 사본은 남긴다)."""
    report: dict[str, object] = {}
    if plan.backup_dir is not None and plan.backup_keep > 0 and is_file_db(engine):
        report["backup"] = backup_file(engine, plan.backup_dir, "daily", keep=plan.backup_keep, now=now).name
    report.update(prune_auth_records(session_factory, now, idle_timeout=plan.idle_timeout, login_keep=plan.login_keep))
    report["integrity"] = quick_check(engine)
    if is_file_db(engine):
        compact(engine)
    return report
