"""24시간 서버 운영을 위한 DB·설정 관리: 마이그레이션, 백업, 정리, 단일 실행 잠금, 설정 복구, 운영 설정 점검."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, func, inspect, select, text

from app.config import Settings
from app.core.clock import kst
from app.engine.settings import WHOLE, EngineSettings, KVStore, tolerant_load
from app.risk.limits import RiskLimits
from app.store import migrate as migrate_module
from app.store.db import SLEEVE_TABLES, Base, LoginAttemptRow, SessionRow, make_engine, make_session_factory
from app.store.lock import EngineLock, EngineLockError
from app.store.maintenance import (
    MaintenancePlan,
    backup_file,
    prune_auth_records,
    prune_backups,
    quick_check,
    run_daily,
)
from app.store.migrate import LATEST, SchemaError, migrate, schema_version

NOW = kst(2026, 11, 17, 16, 0)


def version_of(path) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


# ── 마이그레이션 ──────────────────────────────────────────────────────────────

def test_a_new_database_is_created_at_the_latest_version(tmp_path):
    engine = make_engine(tmp_path / "ap.db")
    with engine.connect() as conn:
        assert schema_version(conn) == LATEST
        assert {"ledger", "users", "kv"} <= set(inspect(conn).get_table_names())


def test_a_database_from_before_versioning_is_taken_as_v1_without_touching_data(tmp_path):
    path = tmp_path / "ap.db"
    legacy = create_engine(f"sqlite:///{path.as_posix()}")
    v1_tables = [t for name, t in Base.metadata.tables.items() if name not in SLEEVE_TABLES]
    Base.metadata.create_all(legacy, tables=v1_tables)
    with legacy.begin() as conn:
        conn.execute(text("INSERT INTO kv(key, value, updated_at) VALUES ('engine_settings', '{}', 'x')"))
    legacy.dispose()
    assert version_of(path) == 0

    engine = make_engine(path)
    with engine.connect() as conn:
        assert schema_version(conn) == LATEST
        assert conn.execute(text("SELECT count(*) FROM kv")).scalar_one() == 1
        assert set(SLEEVE_TABLES) <= set(inspect(conn).get_table_names())  # v2: 바구니 표가 생겼다
    assert list((tmp_path / "backups").glob("*pre-migrate-v1*"))  # 올리기 전에 v1 사본을 남겼다


def test_a_new_database_already_has_the_sleeve_tables(tmp_path):
    engine = make_engine(tmp_path / "ap.db")
    with engine.connect() as conn:
        assert set(SLEEVE_TABLES) <= set(inspect(conn).get_table_names())
    assert not (tmp_path / "backups").exists()  # 새 DB는 올릴 버전이 없어 사본을 만들지 않는다


def _v1_metadata() -> MetaData:
    meta = MetaData()
    Table("notes", meta, Column("id", Integer, primary_key=True), Column("body", String))
    return meta


def test_pending_migrations_run_in_order_after_a_backup(tmp_path):
    path = tmp_path / "ap.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    migrate(engine, _v1_metadata(), migrations=(), latest=1)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO notes(body) VALUES ('남겨야 할 기록')"))

    def add_author(conn):
        conn.exec_driver_sql("ALTER TABLE notes ADD COLUMN author TEXT DEFAULT ''")

    def fill_author(conn):
        conn.exec_driver_sql("UPDATE notes SET author = 'owner'")

    report = migrate(engine, _v1_metadata(), migrations=((2, "작성자 칸", add_author), (3, "작성자 채움", fill_author)),
                     latest=3, backup_dir=tmp_path / "backups")
    assert report.applied == ["v2: 작성자 칸", "v3: 작성자 채움"]
    assert report.backup is not None and report.backup.exists() and version_of(report.backup) == 1
    with engine.connect() as conn:
        assert schema_version(conn) == 3
        assert conn.execute(text("SELECT body, author FROM notes")).one() == ("남겨야 할 기록", "owner")

    again = migrate(engine, _v1_metadata(), migrations=((2, "작성자 칸", add_author), (3, "작성자 채움", fill_author)), latest=3)
    assert again.applied == []  # 이미 올린 버전은 다시 하지 않는다


def test_a_failed_migration_stops_and_points_to_the_backup(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ap.db').as_posix()}")
    migrate(engine, _v1_metadata(), migrations=(), latest=1)

    def broken(conn):
        conn.exec_driver_sql("ALTER TABLE nowhere ADD COLUMN x TEXT")

    with pytest.raises(SchemaError, match="사본"):
        migrate(engine, _v1_metadata(), migrations=((2, "깨진 변경", broken),), latest=2, backup_dir=tmp_path / "backups")
    with engine.connect() as conn:
        assert schema_version(conn) == 1


def test_a_database_newer_than_the_code_is_refused(tmp_path):
    path = tmp_path / "ap.db"
    make_engine(path).dispose()
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {LATEST + 1}")
    with pytest.raises(SchemaError, match="새것"):
        make_engine(path)


def test_migration_numbers_must_line_up_with_latest():
    engine = create_engine("sqlite://")
    with pytest.raises(SchemaError):
        migrate(engine, _v1_metadata(), migrations=((3, "건너뜀", lambda c: None),), latest=2)


def test_the_shipped_migration_list_is_consistent():
    numbers = [n for n, _, _ in migrate_module.MIGRATIONS]
    assert numbers == sorted(set(numbers)) and (not numbers or numbers[-1] == LATEST)


# ── 백업·정리 ─────────────────────────────────────────────────────────────────

def test_backup_makes_a_consistent_copy_and_keeps_only_the_newest(tmp_path):
    engine = make_engine(tmp_path / "ap.db")
    factory = make_session_factory(engine)
    with factory() as s, s.begin():
        s.add(LoginAttemptRow(ts=NOW.isoformat(timespec="seconds"), ip="1.2.3.4", ok=True))
    dest = tmp_path / "backups"
    made = [backup_file(engine, dest, "daily", keep=2, now=NOW + timedelta(minutes=i)) for i in range(3)]
    left = sorted(p.name for p in dest.glob("*.db"))
    assert left == sorted(p.name for p in made[1:])
    with sqlite3.connect(made[-1]) as copy:
        assert copy.execute("SELECT count(*) FROM login_attempts").fetchone()[0] == 1
        assert copy.execute("PRAGMA user_version").fetchone()[0] == LATEST


def test_prune_only_touches_its_own_backup_names(tmp_path):
    (tmp_path / "alphapilot-daily-20260101-000000.db").write_bytes(b"")
    (tmp_path / "alphapilot-daily-20260102-000000.db").write_bytes(b"")
    (tmp_path / "keep-me.db").write_bytes(b"")
    removed = prune_backups(tmp_path, "daily", 1)
    assert [p.name for p in removed] == ["alphapilot-daily-20260101-000000.db"]
    assert (tmp_path / "keep-me.db").exists()


def test_expired_sessions_and_old_login_attempts_are_pruned(tmp_path):
    factory = make_session_factory(make_engine(None))
    iso = lambda moment: moment.isoformat(timespec="seconds")  # noqa: E731
    with factory() as s, s.begin():
        s.add_all([
            SessionRow(token_hash="live", csrf="c", created_at=iso(NOW), last_seen=iso(NOW), expires_at=iso(NOW + timedelta(days=3))),
            SessionRow(token_hash="expired", csrf="c", created_at=iso(NOW), last_seen=iso(NOW), expires_at=iso(NOW - timedelta(seconds=1))),
            SessionRow(token_hash="idle", csrf="c", created_at=iso(NOW), last_seen=iso(NOW - timedelta(hours=13)),
                       expires_at=iso(NOW + timedelta(days=3))),
            LoginAttemptRow(ts=iso(NOW - timedelta(days=31)), ip="x", ok=False),
            LoginAttemptRow(ts=iso(NOW - timedelta(days=1)), ip="x", ok=False),
        ])
    counts = prune_auth_records(factory, NOW, idle_timeout=timedelta(hours=12))
    assert counts == {"sessions": 2, "login_attempts": 1}
    with factory() as s:
        assert s.execute(select(SessionRow.token_hash)).scalars().all() == ["live"]
        assert s.execute(select(func.count()).select_from(LoginAttemptRow)).scalar_one() == 1


def test_daily_maintenance_backs_up_prunes_and_checks(tmp_path):
    engine = make_engine(tmp_path / "ap.db")
    factory = make_session_factory(engine)
    plan = MaintenancePlan(backup_dir=tmp_path / "backups", backup_keep=3, idle_timeout=timedelta(hours=12))
    report = run_daily(engine, factory, plan, NOW)
    assert report["integrity"] == "ok" and quick_check(engine) == "ok"
    assert (tmp_path / "backups" / str(report["backup"])).exists()

    off = run_daily(engine, factory, MaintenancePlan(backup_dir=tmp_path / "b2", backup_keep=0, idle_timeout=timedelta(hours=12)), NOW)
    assert "backup" not in off and not (tmp_path / "b2").exists()


# ── 단일 실행 잠금 ─────────────────────────────────────────────────────────────

def test_only_one_engine_can_hold_the_data_folder(tmp_path):
    first, second = EngineLock(tmp_path / "engine.lock"), EngineLock(tmp_path / "engine.lock")
    first.acquire()
    try:
        with pytest.raises(EngineLockError, match="하나만"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    assert second.held
    second.release()
    assert not second.held


# ── 저장된 설정 복구 ───────────────────────────────────────────────────────────

def test_an_outdated_setting_falls_back_to_its_default_instead_of_breaking_the_engine():
    raw = EngineSettings(decider="rules", automation_level=2).model_dump()
    raw["ai_model"] = "claude-retired-1"  # 코드가 바뀌어 더는 고를 수 없는 모델
    raw["removed_in_new_version"] = True  # 없어진 필드는 무시된다
    settings, repaired = tolerant_load(EngineSettings, raw)
    assert repaired == ["ai_model"]
    assert settings.ai_model == EngineSettings().ai_model
    assert settings.decider == "rules" and settings.automation_level == 2  # 나머지는 그대로


def test_unreadable_limits_fall_back_to_defaults():
    assert tolerant_load(RiskLimits, "not a dict") == (RiskLimits(), [WHOLE])
    assert tolerant_load(RiskLimits, None) == (RiskLimits(), [])
    limits, repaired = tolerant_load(RiskLimits, {"max_positions": 999})
    assert repaired == ["max_positions"] and limits == RiskLimits()


def test_the_kv_store_reports_what_it_repaired():
    kv = KVStore(make_session_factory(make_engine(None)))
    kv.set("engine_settings", {"ai_effort": "turbo", "decider": "hybrid"})
    settings, repaired = kv.load_settings_checked()
    assert repaired == ["ai_effort"] and settings.decider == "hybrid"
    assert kv.load_settings().decider == "hybrid"


# ── 운영 설정 점검 ────────────────────────────────────────────────────────────

def _prod(**env) -> Settings:
    values = {"AP_ENV": "prod", "AP_SECRET_KEY": "s" * 48, "AP_ALLOWED_HOSTS": "trade.example.com", **env}
    return Settings(_env_file=None, **values)


def test_production_settings_are_checked_before_start():
    assert _prod().production_problems() == []
    assert any("AP_SECRET_KEY" in p for p in _prod(AP_SECRET_KEY="short").production_problems())
    assert any("AP_ALLOWED_HOSTS" in p for p in _prod(AP_ALLOWED_HOSTS="localhost,127.0.0.1").production_problems())
    assert any("sample" in p for p in _prod(AP_DATA_PROVIDER="sample").production_problems())
    assert any("실전 키" in p for p in _prod(ALLOW_LIVE_TRADING="true").production_problems())


def test_ops_paths_live_in_the_data_folder(tmp_path):
    config = Settings(_env_file=None, AP_DATA_DIR=str(tmp_path))
    assert config.backup_dir == tmp_path / "backups" and config.lock_path == tmp_path / "engine.lock"
    assert config.backup_keep == 14


def test_kst_fixture_is_timezone_aware():
    assert isinstance(NOW, datetime) and NOW.utcoffset() == timedelta(hours=9)
