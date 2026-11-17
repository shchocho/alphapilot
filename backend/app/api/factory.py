"""FastAPI 앱 조립: 라우트, 인증 의존성, 보안 헤더, 실전 전환 잠금."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import views
from app.api.security import (
    CSRF_HEADER,
    HSTS,
    IDLE_TIMEOUT,
    MAX_BODY_BYTES,
    SECURITY_HEADERS,
    SESSION_COOKIE,
    Auth,
    AuthError,
    SessionInfo,
)
from app.backtest.runner import run_backtest
from app.broker.kiwoom.broker import KiwoomBroker
from app.broker.kiwoom.client import KiwoomClient
from app.broker.kiwoom.errors import KiwoomError
from app.config import Settings, get_settings
from app.core.clock import now_kst
from app.engine.core import EngineConfig
from app.engine.service import EngineError, EngineService, Scheduler
from app.journal.ledger import row_to_dict
from app.risk.limits import RiskLimits
from app.store.db import BacktestRow, make_engine, make_session_factory
from app.store.lock import EngineLock
from app.store.maintenance import MaintenancePlan, run_daily
from app.techniques.registry import ENTRY_KEYS

log = logging.getLogger("alphapilot")
STOCK_CODE = r"^\d{6}$"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ── 요청 본문 ─────────────────────────────────────────────────────────────────

class SetupBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    setup_token: str = Field("", max_length=256)


class CodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=8)


class DecideBody(BaseModel):
    approve: bool
    note: str = Field("", max_length=200)


class AdvanceBody(BaseModel):
    days: int = Field(1, ge=1, le=250)
    auto_approve: bool = False


class SeenBody(BaseModel):
    seq: int = Field(ge=0)


class EnvBody(BaseModel):
    env: Literal["sim", "mock", "live"]
    confirm: str = Field("", max_length=64)


class BrokerTestBody(BaseModel):
    env: Literal["mock", "live"]


class SimResetBody(BaseModel):
    start: date | None = None
    initial_cash: int | None = Field(None, ge=1_000_000, le=100_000_000_000)


class ConfirmBody(BaseModel):
    confirm: str = Field("", max_length=64)


class BacktestBody(BaseModel):
    start: date | None = None
    end: date | None = None
    initial_cash: int = Field(30_000_000, ge=1_000_000, le=100_000_000_000)
    techniques: list[str] = Field(default_factory=lambda: list(ENTRY_KEYS))
    max_candidates: int = Field(8, ge=1, le=30)


# 화면 파일의 콘텐츠 형식. 운영체제 설정(mimetypes)에 기대지 않는다: 윈도우는 .js를 text/plain으로 알려주기도 해서
# 그대로 두면 브라우저가 모듈 스크립트를 거부하고 빈 화면이 된다.
STATIC_TYPES: dict[str, str] = {
    ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
    ".json": "application/json", ".map": "application/json", ".webmanifest": "application/manifest+json", ".txt": "text/plain",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon",
    ".woff2": "font/woff2", ".woff": "font/woff",
}


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


# ── 의존성 (모듈 수준에 둬야 FastAPI가 타입 별칭을 해석한다) ─────────────────────

def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def require_session(request: Request) -> SessionInfo:
    auth: Auth = request.app.state.auth
    session = auth.session(request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise AuthError(401, "not_authenticated", "로그인이 필요합니다")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent.encode(), session.csrf.encode()):
            raise AuthError(403, "csrf", "요청을 확인할 수 없습니다. 페이지를 새로 고친 뒤 다시 시도하세요")
    return session


def require_elevated(session: Annotated[SessionInfo, Depends(require_session)]) -> SessionInfo:
    if not session.elevated:
        raise AuthError(403, "stepup_required", "이 동작은 인증 코드를 다시 입력해야 합니다")
    return session


Authed = Annotated[SessionInfo, Depends(require_session)]
Elevated = Annotated[SessionInfo, Depends(require_elevated)]


def create_app(
    config: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    service: EngineService | None = None,
    run_scheduler: bool = True,
) -> FastAPI:
    config = config or get_settings()
    factory = session_factory or make_session_factory(make_engine(config.db_path))
    db_engine = factory.kw.get("bind")
    svc = service or EngineService(config, factory)
    auth = Auth(config, factory)
    plan = MaintenancePlan(backup_dir=config.backup_dir, backup_keep=config.backup_keep, idle_timeout=IDLE_TIMEOUT)
    scheduler = Scheduler(svc, maintenance=(lambda now: run_daily(db_engine, factory, plan, now)) if db_engine is not None else None)
    engine_lock = EngineLock(config.lock_path)
    backtest_lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if run_scheduler:
            engine_lock.acquire()  # 엔진(스케줄러)은 데이터 폴더당 하나만. 이미 돌고 있으면 여기서 멈춘다
        try:
            svc.startup()
            if run_scheduler:
                scheduler.start()
            yield
            await scheduler.stop()
        finally:
            engine_lock.release()

    app = FastAPI(title="AlphaPilot", docs_url="/api/docs" if not config.is_prod else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if not config.is_prod else None, lifespan=lifespan)
    app.state.service = svc
    app.state.auth = auth
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*config.host_list, "testserver"] if not config.is_prod else config.host_list)

    @app.middleware("http")
    async def harden(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return _error(413, "too_large", "요청이 너무 큽니다")
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if config.is_prod:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(AuthError)
    async def _auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(EngineError)
    async def _engine_error(_: Request, exc: EngineError) -> JSONResponse:
        return _error(409, "engine", str(exc))

    @app.exception_handler(ValidationError)
    async def _validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        first = exc.errors()[0]
        return _error(422, "invalid", f"값이 올바르지 않습니다: {'.'.join(str(p) for p in first['loc'])} — {first['msg']}")

    @app.exception_handler(RequestValidationError)
    async def _request_invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"loc": (), "msg": "형식 오류"}
        where = ".".join(str(p) for p in first["loc"] if p not in ("body", "query", "path"))
        return _error(422, "invalid", f"값이 올바르지 않습니다{': ' + where if where else ''}")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        ref = uuid.uuid4().hex[:8]
        log.exception("처리하지 못한 오류 [%s]", ref)
        return _error(500, "internal", f"서버 오류가 발생했습니다(문의 코드 {ref})")

    # ── 공개 엔드포인트 ─────────────────────────────────────────────────────

    public = APIRouter(prefix="/api")

    @public.get("/health")
    def health(response: Response) -> dict[str, Any]:
        """컨테이너 상태 검사·외부 감시용. 로그인 없이 열려 있으므로 상태 이름만 알려 준다."""
        now = now_kst()
        try:
            with factory() as s:
                s.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001 - 어떤 DB 오류든 '비정상'으로 알린다
            log.exception("상태 검사: DB 접근 실패")
            db_ok = False
        scheduler_ok, scheduler_state = scheduler.health(now)
        ok = db_ok and scheduler_ok
        if not ok:
            response.status_code = 503
        return {"ok": ok, "time": now.isoformat(timespec="seconds"), "checks": {"db": "ok" if db_ok else "error", "scheduler": scheduler_state}}

    @public.get("/auth/state")
    def auth_state(request: Request) -> dict[str, Any]:
        session = auth.session(request.cookies.get(SESSION_COOKIE))
        return {
            "setup": auth.setup_state(), "authenticated": session is not None,
            "csrf": session.csrf if session else None, "elevated": bool(session and session.elevated),
            "setup_token_required": bool(config.setup_token.get_secret_value()) or config.is_prod,
        }

    @public.post("/auth/setup")
    def auth_setup(body: SetupBody, request: Request) -> dict[str, str]:
        return auth.begin_setup(body.password, body.setup_token, client_ip(request))

    @public.post("/auth/setup/confirm")
    def auth_setup_confirm(body: CodeBody, request: Request) -> dict[str, bool]:
        auth.confirm_setup(body.code, client_ip(request))
        return {"ok": True}

    @public.post("/auth/login")
    def auth_login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
        token, session = auth.login(body.password, body.code, client_ip(request), request.headers.get("user-agent", ""))
        response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=config.is_prod, samesite="strict", max_age=7 * 24 * 3600, path="/")
        return {"ok": True, "csrf": session.csrf}

    @public.post("/auth/logout")
    def auth_logout(request: Request, response: Response) -> dict[str, bool]:
        auth.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    # ── 인증 필요 ───────────────────────────────────────────────────────────

    api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])

    @api.post("/auth/stepup")
    def auth_stepup(body: CodeBody, session: Authed, request: Request) -> dict[str, Any]:
        return {"ok": True, "elevated_until": auth.step_up(session, body.code, client_ip(request))}

    @api.post("/auth/logout-all")
    def auth_logout_all(_: Elevated, response: Response) -> dict[str, int]:
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"closed": auth.logout_all()}

    @api.get("/auth/sessions")
    def auth_sessions() -> dict[str, Any]:
        return {"sessions": auth.sessions(), "audit": auth.audit_rows(60)}

    @api.get("/status")
    def status() -> dict[str, Any]:
        return svc.status()

    @api.get("/dashboard")
    def dashboard() -> dict[str, Any]:
        return views.dashboard(svc)

    @api.get("/ledger")
    def ledger(after: Annotated[int, Query(ge=0)] = 0, before: Annotated[int | None, Query(ge=1)] = None,
               kind: Annotated[str | None, Query(max_length=200)] = None, code: Annotated[str | None, Query(pattern=STOCK_CODE)] = None,
               limit: Annotated[int, Query(ge=1, le=500)] = 100) -> dict[str, Any]:
        kinds = [k for k in (kind or "").split(",") if k] or None
        rows = svc.ledger.rows(env=svc.settings().env, after_seq=after, before_seq=before, kinds=kinds, code=code, limit=limit)
        return {"rows": [row_to_dict(r) for r in rows]}

    @api.post("/ledger/seen")
    def ledger_seen(body: SeenBody) -> dict[str, int]:
        env = svc.settings().env
        seq = min(body.seq, svc.ledger.last_seq(env))
        svc.kv.set(f"ledger_seen:{env}", seq)
        return {"seen_seq": seq}

    @api.get("/ledger/chain/{chain_id}")
    def ledger_chain(chain_id: Annotated[str, Path_(r"^[0-9A-Za-z\-]{3,40}$")]) -> dict[str, Any]:
        return views.chain(svc, chain_id)

    @api.get("/ledger/verify")
    def ledger_verify() -> dict[str, Any]:
        ok, broken = svc.ledger.verify()
        return {"ok": ok, "broken_seq": broken}

    @api.get("/ledger/export.csv")
    def ledger_export() -> PlainTextResponse:
        body = "﻿" + svc.ledger.to_csv(svc.settings().env)  # 엑셀이 한글을 읽도록 BOM을 붙인다
        return PlainTextResponse(body, media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="alphapilot-ledger.csv"'})

    @api.get("/screener")
    def screener(technique: Annotated[str | None, Query(max_length=40)] = None) -> dict[str, Any]:
        return views.screener(svc, technique)

    @api.get("/stocks/search")
    def stock_search(q: Annotated[str, Query(min_length=1, max_length=30)]) -> dict[str, Any]:
        return {"results": views.search(svc, q)}

    @api.get("/stocks/{code}")
    def stock(code: Annotated[str, Path_(STOCK_CODE)]) -> dict[str, Any]:
        return views.stock_detail(svc, code)

    @api.get("/committee")
    def committee(day: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None) -> dict[str, Any]:
        return views.committee_sessions(svc, day)

    @api.get("/committee/{decision_id}")
    def committee_decision(decision_id: Annotated[str, Path_(r"^[0-9A-Za-z\-]{3,40}$")]) -> dict[str, Any]:
        return views.decision_detail(svc, decision_id)

    @api.get("/intents/pending")
    def intents_pending() -> dict[str, Any]:
        return {"cards": views.pending_cards(svc)}

    @api.post("/intents/{intent_id}/decide")
    def intent_decide(intent_id: Annotated[str, Path_(r"^[0-9A-Za-z\-]{3,40}$")], body: DecideBody, request: Request) -> dict[str, Any]:
        data = svc.decide_intent(intent_id, body.approve, body.note)
        auth.audit("intent_approved" if body.approve else "intent_rejected", {"intent": intent_id}, client_ip(request))
        return data

    @api.get("/portfolio")
    def portfolio() -> dict[str, Any]:
        return views.portfolio(svc)

    # 엔진 제어
    @api.post("/engine/start")
    def engine_start(request: Request, session: Authed) -> dict[str, Any]:
        # 정지에서 다시 켜는 것은 재인증이 필요하다(일시정지 해제는 필요 없다).
        if svc.settings().state == "stopped" and not session.elevated:
            raise AuthError(403, "stepup_required", "정지한 엔진을 다시 켜려면 인증 코드를 다시 입력해야 합니다")
        st = svc.start()
        auth.audit("engine_start", ip=client_ip(request))
        return {"state": st.state}

    @api.post("/engine/pause")
    def engine_pause(request: Request) -> dict[str, Any]:
        st = svc.pause()
        auth.audit("engine_pause", ip=client_ip(request))
        return {"state": st.state}

    @api.post("/engine/stop")
    def engine_stop(request: Request) -> dict[str, Any]:
        result = svc.stop()
        auth.audit("engine_stop", result, client_ip(request))
        return result

    @api.post("/engine/liquidate")
    def engine_liquidate(body: ConfirmBody, request: Request) -> dict[str, Any]:
        if body.confirm.strip() != "전량 매도":
            raise EngineError("확인 문구 '전량 매도'를 입력해야 합니다")
        result = svc.liquidate()
        auth.audit("engine_liquidate", result, client_ip(request))
        return result

    @api.post("/engine/confirm-resume")
    def engine_confirm_resume(request: Request) -> dict[str, Any]:
        st = svc.confirm_resume()
        auth.audit("engine_confirm_resume", ip=client_ip(request))
        return {"resume_check_required": st.resume_check_required}

    @api.post("/engine/advance")
    async def engine_advance(body: AdvanceBody) -> dict[str, Any]:
        return {"days": await svc.advance(body.days, auto_approve=body.auto_approve)}

    @api.post("/engine/refresh-data")
    async def engine_refresh() -> dict[str, Any]:
        report = await svc.refresh_data()
        return {"updated": len(report.updated), "unchanged": len(report.unchanged), "failed": report.failed, "refetched": len(report.refetched)}

    # 설정
    @api.get("/settings")
    def settings_get() -> dict[str, Any]:
        return views.settings_view(svc)

    @api.put("/settings/engine")
    def settings_engine(patch: dict[str, Any], request: Request, session: Authed) -> dict[str, Any]:
        current = svc.settings()
        raising = int(patch.get("automation_level", current.automation_level)) > current.automation_level
        if raising and not session.elevated:
            raise AuthError(403, "stepup_required", "자동화 단계를 올리려면 인증 코드를 다시 입력해야 합니다")
        updated = svc.update_settings(patch)
        auth.audit("settings_engine", {"keys": sorted(patch)}, client_ip(request))
        return updated.model_dump()

    @api.put("/settings/limits")
    def settings_limits(patch: dict[str, Any], request: Request, session: Authed) -> dict[str, Any]:
        preview = RiskLimits.model_validate({**svc.limits().model_dump(), **patch})
        loosened = preview.is_looser_than(svc.limits())
        if loosened and not session.elevated:
            return _error(403, "stepup_required", "한도를 느슨하게 바꾸려면 인증 코드를 다시 입력해야 합니다", loosened=loosened)  # type: ignore[return-value]
        updated, _ = svc.update_limits(patch)
        auth.audit("settings_limits", {"keys": sorted(patch), "loosened": loosened}, client_ip(request))
        return {"limits": updated.model_dump(), "loosened": loosened}

    @api.post("/settings/env")
    def settings_env(body: EnvBody, request: Request, session: Authed) -> dict[str, Any]:
        if body.env != "sim" and not session.elevated:
            raise AuthError(403, "stepup_required", "모의투자·실전으로 바꾸려면 인증 코드를 다시 입력해야 합니다")
        st = svc.switch_env(body.env, body.confirm)
        auth.audit("env_switch", {"env": st.env}, client_ip(request))
        return {"env": st.env}

    @api.post("/settings/broker/test")
    async def broker_test(body: BrokerTestBody, request: Request) -> dict[str, Any]:
        """키움 연결 테스트: 토큰 발급 + 잔고 조회(읽기 전용). 키 값은 응답에 넣지 않는다."""
        if not config.has_kiwoom_keys(body.env):
            prefix = "KIWOOM_MOCK" if body.env == "mock" else "KIWOOM_LIVE"
            return {"ok": False, "message": f"서버 환경변수 {prefix}_APP_KEY, {prefix}_SECRET_KEY가 설정되지 않았습니다"}
        client = KiwoomClient(body.env, *config.kiwoom_keys(body.env))
        try:
            token = await client.token()
            account = await KiwoomBroker(client).account()
            auth.audit("broker_test_ok", {"env": body.env}, client_ip(request))
            return {"ok": True, "token_expires_at": token.expires_at.isoformat(timespec="seconds"), "cash": account.cash,
                    "total_equity": account.total_equity, "positions": len(account.positions)}
        except KiwoomError as exc:
            auth.audit("broker_test_failed", {"env": body.env, "code": exc.code}, client_ip(request))
            return {"ok": False, "code": exc.code, "message": str(exc), "hint": exc.hint}
        except Exception as exc:  # noqa: BLE001 - 네트워크 오류 등
            return {"ok": False, "message": f"연결하지 못했습니다({type(exc).__name__})"}
        finally:
            await client.aclose()

    @api.post("/settings/sim-reset")
    def sim_reset(body: SimResetBody, request: Request) -> dict[str, Any]:
        if svc.settings().env != "sim":
            raise EngineError("시뮬레이션 환경에서만 초기화할 수 있습니다")
        result = svc.sim_reset(body.start, body.initial_cash)
        auth.audit("sim_reset", result, client_ip(request))
        return result

    # 백테스트
    @api.get("/backtests")
    def backtest_list() -> dict[str, Any]:
        return {"runs": views.backtests(svc)}

    @api.get("/backtests/{run_id}")
    def backtest_get(run_id: Annotated[str, Path_(r"^[0-9a-f]{8,32}$")]) -> dict[str, Any]:
        with svc.sf() as s:
            row = s.get(BacktestRow, run_id)
        if row is None:
            raise EngineError("백테스트 결과를 찾을 수 없습니다")
        return {"id": row.id, "created_at": row.created_at, "params": json.loads(row.params), **json.loads(row.result)}

    @api.post("/backtests")
    async def backtest_run(body: BacktestBody) -> dict[str, Any]:
        if svc.market is None:
            raise EngineError("일봉 데이터가 없습니다. 설정에서 데이터를 갱신하세요")
        if backtest_lock.locked():
            raise EngineError("다른 백테스트가 돌고 있습니다. 끝난 뒤 다시 시도하세요")
        unknown = [k for k in body.techniques if k not in ENTRY_KEYS]
        if unknown or not body.techniques:
            raise EngineError("기법을 하나 이상 올바르게 골라야 합니다")
        st = svc.settings()
        cfg = EngineConfig(limits=svc.limits(), costs=st.cost_model(), enabled_techniques=tuple(k for k in ENTRY_KEYS if k in body.techniques),
                           max_candidates=body.max_candidates)
        async with backtest_lock:
            result = await asyncio.to_thread(run_backtest, svc.market, svc.regimes, cfg, start=body.start, end=body.end, initial_cash=body.initial_cash)
        params = {**body.model_dump(mode="json"), "costs": {"commission_rate": st.commission_rate, "sell_tax_rate": st.sell_tax_rate,
                                                            "slippage_rate": st.slippage_rate},
                  "limits": svc.limits().model_dump(), "universe": len(svc.market.stocks), "data_source": svc.provider.name,
                  "decider": "rules"}
        run_id = uuid.uuid4().hex[:12]
        payload = result.to_dict()
        with svc.sf() as s, s.begin():
            s.add(BacktestRow(id=run_id, created_at=now_kst().isoformat(timespec="seconds"), params=json.dumps(params, ensure_ascii=False),
                              result=json.dumps(payload, ensure_ascii=False)))
        return {"id": run_id, "params": params, **payload}

    @api.get("/events")
    async def events(request: Request) -> StreamingResponse:
        queue = svc.bus.subscribe()

        async def stream() -> AsyncIterator[str]:
            try:
                yield "retry: 5000\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=20)
                        yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                    except TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                svc.bus.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    app.include_router(public)
    app.include_router(api)

    # ── 화면(정적 파일) ─────────────────────────────────────────────────────
    static_dir = config.static_dir
    if static_dir and Path(static_dir).is_dir():
        root = Path(static_dir).resolve()
        index = root / "index.html"

        def served(target: Path, *, immutable: bool) -> FileResponse:
            # 이름에 내용 해시가 붙은 자산은 오래 캐시하고, 화면 문서(index.html)는 매번 새 버전인지 확인하게 한다.
            return FileResponse(target, media_type=STATIC_TYPES.get(target.suffix.lower()),
                                headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            if path.startswith("api/"):
                return _error(404, "not_found", "없는 주소입니다")
            target = (root / path).resolve()
            if path and target.is_file() and root in target.parents:
                return served(target, immutable=path.startswith("assets/"))
            if path.startswith("assets/"):
                return _error(404, "not_found", "없는 파일입니다")
            return served(index, immutable=False)

    return app


def Path_(pattern: str):  # noqa: N802 - FastAPI Path에 정규식만 붙이는 짧은 도우미
    from fastapi import Path as FastApiPath

    return FastApiPath(pattern=pattern)

