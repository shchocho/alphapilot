"""스키마 버전 관리.

적용한 스키마 버전은 SQLite의 PRAGMA user_version에 적는다.

표를 바꾸는 순서:
  1) `app/store/db.py`의 모델을 고친다.
  2) 아래 MIGRATIONS에 (새 버전, 설명, 적용 함수)를 더하고 LATEST를 그 버전으로 올린다.
     적용 함수는 이전 버전의 표를 새 모양으로 바꾸는 SQL을 실행한다(예: ALTER TABLE ... ADD COLUMN).
  3) 기존 DB로 시작해 보는 테스트를 더한다.

시작할 때:
  - 새 DB: 모델대로 표를 만들고 바로 LATEST로 적는다.
  - 버전 관리를 넣기 전에 만든 DB(user_version 0, 표 있음): v1로 본다.
  - 올릴 버전이 있으면 먼저 backups/에 사본을 남기고 하나씩 올린다. 중간에 실패하면 그 사본 경로를 알리고 멈춘다.
  - DB가 코드보다 새 버전이면(옛 코드로 되돌린 경우) 시작하지 않는다. 데이터를 망가뜨리지 않기 위해서다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Connection, Engine

from app.store.maintenance import backup_file, is_file_db

log = logging.getLogger("alphapilot.migrate")

Migration = tuple[int, str, Callable[[Connection], None]]

# v1: 2026-11-17 기준의 표 전체(버전 관리를 넣기 전에 만든 DB는 모두 이 모양이다).
MIGRATIONS: tuple[Migration, ...] = ()
LATEST = 1


class SchemaError(RuntimeError):
    pass


@dataclass(slots=True)
class MigrationReport:
    before: int
    after: int
    created: bool = False
    applied: list[str] = field(default_factory=list)
    backup: Path | None = None


def schema_version(conn: Connection) -> int:
    return int(conn.exec_driver_sql("PRAGMA user_version").scalar() or 0)


def _set_version(conn: Connection, version: int) -> None:
    conn.exec_driver_sql(f"PRAGMA user_version = {int(version)}")


def migrate(engine: Engine, metadata: MetaData, *, migrations: Sequence[Migration] = MIGRATIONS, latest: int = LATEST,
            backup_dir: Path | None = None) -> MigrationReport:
    numbers = [number for number, _, _ in migrations]
    if numbers != sorted(set(numbers)) or any(n <= 1 or n > latest for n in numbers) or (numbers and numbers[-1] != latest):
        raise SchemaError(f"마이그레이션 번호가 잘못됐습니다: {numbers} (LATEST={latest})")

    with engine.connect() as conn:
        version = schema_version(conn)
        has_tables = bool(inspect(conn).get_table_names())
    if version > latest:
        raise SchemaError(f"DB 스키마(v{version})가 이 코드(v{latest})보다 새것입니다. 코드를 최신으로 올리거나 맞는 백업으로 되돌리세요")

    if version == 0 and not has_tables:
        metadata.create_all(engine)
        with engine.begin() as conn:
            _set_version(conn, latest)
        return MigrationReport(before=0, after=latest, created=True)

    base = max(version, 1)
    pending = [m for m in migrations if m[0] > base]
    report = MigrationReport(before=version, after=latest)
    if pending and backup_dir is not None and is_file_db(engine):
        report.backup = backup_file(engine, backup_dir, f"pre-migrate-v{base}")
    for number, description, apply in pending:
        try:
            with engine.begin() as conn:
                apply(conn)
                _set_version(conn, number)
        except Exception as exc:
            where = f" 올리기 전 사본: {report.backup}" if report.backup else ""
            raise SchemaError(f"스키마 v{number}({description}) 적용 실패: {exc}.{where}") from exc
        report.applied.append(f"v{number}: {description}")
        log.info("스키마 v%d 적용: %s", number, description)
    # 마이그레이션 없이 더한 새 표가 있으면 만든다(기존 표는 바꾸지 않는다).
    metadata.create_all(engine)
    if version != latest:
        with engine.begin() as conn:
            _set_version(conn, latest)
    return report
