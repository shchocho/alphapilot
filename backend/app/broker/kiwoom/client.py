"""키움 REST API 클라이언트: 토큰, 유량 제한, 연속조회, 오류 분류.

근거는 docs/research/03-kiwoom-rest-api.md. 실제 API로 검증하지 못한 항목(§19)이 있으므로
키를 받은 뒤 반드시 모의투자 도메인에서 먼저 확인한다.

- 토큰은 엔진 프로세스 하나만 발급한다(6시간 뒤 재발급하면 기존 토큰이 폐기된다).
- 주문 TR은 여기서 자동 재시도하지 않는다. 결과가 애매하면 호출한 쪽이 미체결 조회로 확인한다.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx

from app.broker.kiwoom import parsing
from app.broker.kiwoom.errors import (
    AUTH_RETRY_CODES,
    KiwoomAuthError,
    KiwoomError,
    KiwoomNotConfigured,
    KiwoomRateLimited,
    classify,
)
from app.core.clock import now_kst

log = logging.getLogger(__name__)

KiwoomEnv = Literal["mock", "live"]
BASE_URL: dict[str, str] = {"mock": "https://mockapi.kiwoom.com", "live": "https://api.kiwoom.com"}
JSON_HEADERS = {"Content-Type": "application/json;charset=UTF-8"}
ORDER_API_IDS = frozenset({"kt10000", "kt10001", "kt10002", "kt10003"})
# 2026-11-12부터 초당 1회로 제한된 계좌 TR
SLOW_ACCOUNT_API_IDS = frozenset({
    "kt00001", "kt00002", "kt00003", "kt00004", "kt00005", "kt00007", "kt00008", "kt00009", "kt00013",
    "kt00015", "kt00016", "kt00017", "kt00018",
})
TOKEN_REFRESH_MARGIN = timedelta(minutes=10)


@dataclass(slots=True)
class Token:
    value: str
    expires_at: datetime

    def usable(self, now: datetime) -> bool:
        return bool(self.value) and now < self.expires_at - TOKEN_REFRESH_MARGIN


@dataclass(slots=True)
class KiwoomResponse:
    body: dict[str, Any]
    cont: bool
    next_key: str


class RateLimiter:
    """api-id별 최소 호출 간격. 공식 한도보다 조금 낮게 잡는다(실전 초당 4회, 모의·계좌 TR 초당 0.9회)."""

    def __init__(self, env: KiwoomEnv, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._env = env
        self._clock = clock
        self._sleep = sleep
        self._next_allowed: dict[str, float] = {}
        self._overrides: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def rate_for(self, api_id: str) -> float:
        if api_id in self._overrides:
            return self._overrides[api_id]
        if self._env == "mock" or api_id in SLOW_ACCOUNT_API_IDS:
            return 0.9
        return 4.0

    def slow_down(self, api_id: str) -> None:
        """유량 초과를 맞으면 그 TR의 속도를 절반으로 낮춘다."""
        self._overrides[api_id] = max(0.2, self.rate_for(api_id) / 2)

    async def wait(self, api_id: str) -> None:
        lock = self._locks.setdefault(api_id, asyncio.Lock())
        async with lock:
            now = self._clock()
            ready = self._next_allowed.get(api_id, 0.0)
            if ready > now:
                await self._sleep(ready - now)
                now = ready
            self._next_allowed[api_id] = now + 1.0 / self.rate_for(api_id)


class KiwoomClient:
    def __init__(
        self,
        env: KiwoomEnv,
        app_key: str,
        secret_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        load_token: Callable[[], Token | None] | None = None,
        save_token: Callable[[Token], None] | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = now_kst,
    ) -> None:
        self.env: KiwoomEnv = env
        self._app_key = app_key
        self._secret_key = secret_key
        self._http = http or httpx.AsyncClient(base_url=BASE_URL[env], timeout=httpx.Timeout(10.0, connect=5.0))
        self._load_token = load_token
        self._save_token = save_token
        self._limiter = limiter or RateLimiter(env, sleep=sleep)
        self._sleep = sleep
        self._now = now
        self._token: Token | None = None
        self._token_lock = asyncio.Lock()
        self.last_success: datetime | None = None

    @property
    def configured(self) -> bool:
        return bool(self._app_key and self._secret_key)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── 토큰 ───────────────────────────────────────────────────────────────

    async def token(self, *, force: bool = False) -> Token:
        if not self.configured:
            raise KiwoomNotConfigured("키움 앱키가 설정되지 않았습니다", api_id="au10001")
        async with self._token_lock:
            now = self._now()
            if not force:
                if self._token and self._token.usable(now):
                    return self._token
                stored = self._load_token() if self._load_token else None
                if stored and stored.usable(now):
                    self._token = stored
                    return stored
            self._token = await self._issue_token()
            if self._save_token:
                self._save_token(self._token)
            return self._token

    async def _issue_token(self) -> Token:
        payload = {"grant_type": "client_credentials", "appkey": self._app_key, "secretkey": self._secret_key}
        try:
            resp = await self._http.post("/oauth2/token", json=payload, headers=JSON_HEADERS)
        except httpx.HTTPError as exc:
            raise KiwoomError(f"토큰 발급 요청 실패: {type(exc).__name__}", api_id="au10001") from exc
        body = _json(resp)
        code = parsing.return_code(body)
        if resp.status_code != 200 or code != 0 or not body.get("token"):
            message = parsing.return_message(body) or f"HTTP {resp.status_code}"
            raise classify(parsing.detail_code(message) or code, message, api_id="au10001", http_status=resp.status_code)
        return Token(value=str(body["token"]), expires_at=parsing.parse_expiry(str(body["expires_dt"])))

    async def revoke(self) -> None:
        if not self._token:
            return
        payload = {"appkey": self._app_key, "secretkey": self._secret_key, "token": self._token.value}
        await self._http.post("/oauth2/revoke", json=payload, headers=JSON_HEADERS)
        self._token = None

    # ── 요청 ───────────────────────────────────────────────────────────────

    async def request(
        self,
        api_id: str,
        path: str,
        body: dict[str, Any],
        *,
        cont: bool = False,
        next_key: str = "",
        max_rate_retries: int = 3,
    ) -> KiwoomResponse:
        """TR 한 번 호출. 조회 TR은 유량 초과 시 백오프 후 재시도하고, 주문 TR은 재시도하지 않는다."""
        is_order = api_id in ORDER_API_IDS
        auth_retried = False
        rate_attempt = 0
        while True:
            token = await self.token()
            await self._limiter.wait(api_id)
            headers = {**JSON_HEADERS, "api-id": api_id, "authorization": f"Bearer {token.value}"}
            if cont:
                headers["cont-yn"] = "Y"
                headers["next-key"] = next_key
            resp = await self._http.post(path, json=body, headers=headers)  # 전송 오류는 그대로 올린다
            payload = _json(resp)
            code = parsing.return_code(payload)
            message = parsing.return_message(payload)
            detail = parsing.detail_code(message)
            # 최상위 3(인증 실패)·5(유량)·20(주문 거부)은 포장 코드다. 세부 코드가 메시지에 없으면 뜻으로 바꾼다.
            effective = detail if detail is not None else (code if code not in (0, 3, 5, 20) else None)
            if effective is None and code == 3:
                effective = 8005
            if effective is None and code == 5:
                effective = 1700

            if resp.status_code == 200 and code == 0:
                self.last_success = self._now()
                return KiwoomResponse(payload, resp.headers.get("cont-yn") == "Y", resp.headers.get("next-key", ""))

            error = classify(effective, message or f"HTTP {resp.status_code}", api_id=api_id, http_status=resp.status_code)
            if isinstance(error, KiwoomRateLimited):
                self._limiter.slow_down(api_id)
                if is_order or rate_attempt >= max_rate_retries:
                    raise error
                rate_attempt += 1
                await self._sleep(min(8.0, 0.5 * 2**rate_attempt) + random.uniform(0, 0.25))
                continue
            retryable_auth = resp.status_code == 401 or (effective in AUTH_RETRY_CODES)
            if isinstance(error, KiwoomAuthError) and retryable_auth and not auth_retried and not is_order:
                auth_retried = True
                await self.token(force=True)
                continue
            raise error

    async def paginate(
        self, api_id: str, path: str, body: dict[str, Any], list_key: str, *, max_pages: int = 20
    ) -> list[dict[str, Any]]:
        """연속조회. 다음 키는 응답 헤더(cont-yn, next-key)에서 읽어 그대로 돌려보낸다."""
        rows: list[dict[str, Any]] = []
        cont, next_key = False, ""
        for _ in range(max_pages):
            resp = await self.request(api_id, path, body, cont=cont, next_key=next_key)
            rows.extend(resp.body.get(list_key) or [])
            if not resp.cont or not resp.next_key:
                break
            cont, next_key = True, resp.next_key
        return rows


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
