"""SQLite(WAL) 연결과 테이블 정의.

단일 프로세스·단일 워커 전제다. 엔진이 두 개 뜨면 주문이 중복될 수 있으므로 워커 수를 늘리지 않는다(store/lock.py가 막는다).
표를 바꿀 때는 store/migrate.py의 안내대로 마이그레이션을 더한다. create_all은 기존 표를 바꾸지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import BigInteger, Boolean, Float, Integer, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class BarRow(Base):
    __tablename__ = "bars"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    d: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    o: Mapped[float] = mapped_column(Float)
    h: Mapped[float] = mapped_column(Float)
    l: Mapped[float] = mapped_column(Float)  # noqa: E741
    c: Mapped[float] = mapped_column(Float)
    v: Mapped[int] = mapped_column(BigInteger)


class KV(Base):
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(32))


class LedgerRow(Base):
    """해시로 이어 붙인 원장. 화면의 '통장정리'가 이 표를 읽는다."""

    __tablename__ = "ledger"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32))
    env: Mapped[str] = mapped_column(String(8), index=True)
    day: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    chain_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cash_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    env: Mapped[str] = mapped_column(String(8), index=True)
    as_of: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(8))
    conviction: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    chain_id: Mapped[str] = mapped_column(String(32), index=True)
    body: Mapped[str] = mapped_column(Text)  # JSON: seats, techniques, envelope, transcript, final, gate
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[str] = mapped_column(String(32))


class IntentRow(Base):
    __tablename__ = "intents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    env: Mapped[str] = mapped_column(String(8), index=True)
    chain_id: Mapped[str] = mapped_column(String(32), index=True)
    decision_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_on: Mapped[str] = mapped_column(String(10))
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    body: Mapped[str] = mapped_column(Text)  # JSON: Intent 나머지 필드
    expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))


class TradeRow(Base):
    """체결 한 건."""

    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    env: Mapped[str] = mapped_column(String(8), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    fee: Mapped[int] = mapped_column(Integer, default=0)
    tax: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(24))
    technique: Mapped[str] = mapped_column(String(32), default="")
    chain_id: Mapped[str] = mapped_column(String(32), default="")
    intent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pnl: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    hold_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PositionRow(Base):
    __tablename__ = "positions"
    env: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    qty: Mapped[int] = mapped_column(Integer)
    avg_price: Mapped[float] = mapped_column(Float)
    body: Mapped[str] = mapped_column(Text)  # JSON: Position 나머지 필드


class AccountRow(Base):
    __tablename__ = "accounts"
    env: Mapped[str] = mapped_column(String(8), primary_key=True)
    cash: Mapped[int] = mapped_column(BigInteger)
    initial_cash: Mapped[int] = mapped_column(BigInteger)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    sim_day: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 시뮬레이션이 마지막으로 처리한 거래일


class EquityRow(Base):
    __tablename__ = "equity"
    env: Mapped[str] = mapped_column(String(8), primary_key=True)
    d: Mapped[str] = mapped_column(String(10), primary_key=True)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[int] = mapped_column(BigInteger)
    exposure: Mapped[float] = mapped_column(Float)
    benchmark: Mapped[float | None] = mapped_column(Float, nullable=True)


class AiUsageRow(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32))
    day: Mapped[str] = mapped_column(String(10), index=True)  # 비용을 세는 달력 날짜(KST)
    env: Mapped[str] = mapped_column(String(8))
    role: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(48))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(String(64), default="")
    decision_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_enc: Mapped[str] = mapped_column(Text)
    totp_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_counter: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[str] = mapped_column(String(32))


class SessionRow(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32))
    last_seen: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[str] = mapped_column(String(32))
    elevated_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(256), default="")


class LoginAttemptRow(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    ok: Mapped[bool] = mapped_column(Boolean)


class AuditRow(Base):
    """설정 변경·모드 전환·로그인 같은 관리 행위 기록."""

    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str] = mapped_column(Text, default="{}")
    ip: Mapped[str] = mapped_column(String(64), default="")


class BacktestRow(Base):
    __tablename__ = "backtests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(32))
    params: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)


def make_engine(db_path: Path | str | None) -> Engine:
    """db_path가 None이면 메모리 DB(테스트용)."""
    if db_path is None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # pragma: no cover - 드라이버 콜백
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    from app.store.migrate import migrate  # migrate가 이 모듈의 표를 쓰므로 여기서 불러온다

    migrate(engine, Base.metadata, backup_dir=None if db_path is None else Path(db_path).parent / "backups")
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
