"""인증과 세션. 실계좌 주문 권한이 있는 서버가 인터넷에 열리므로 보수적으로 만든다.

- 관리자 1명. 비밀번호(Argon2id) + TOTP 2단계 인증.
- 최초 등록은 서버 환경변수의 1회용 값(AP_SETUP_TOKEN)이 있어야 한다. 새로 띄운 서버를 남이 먼저 차지하지 못하게 한다.
- 세션은 서버에 저장한다(쿠키에는 무작위 토큰만, DB에는 그 해시만). HttpOnly · Secure · SameSite=Strict.
- 상태를 바꾸는 요청은 세션에 묶인 CSRF 토큰 헤더가 있어야 한다.
- 위험한 동작(실전 전환, 한도 완화, 정지 해제)은 TOTP 재인증(step-up) 뒤 5분 동안만 허용한다.
- 로그인 실패는 IP별·전체로 세어 잠시 막는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.clock import now_kst
from app.store.db import AuditRow, LoginAttemptRow, SessionRow, UserRow

SESSION_COOKIE = "ap_session"
CSRF_HEADER = "x-csrf-token"
IDLE_TIMEOUT = timedelta(hours=12)
ABSOLUTE_TIMEOUT = timedelta(days=7)
ELEVATION_WINDOW = timedelta(minutes=5)
ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_FAILS_PER_IP = 5
MAX_FAILS_GLOBAL = 20
MIN_PASSWORD_LENGTH = 12
ISSUER = "AlphaPilot"

_hasher = PasswordHasher()  # Argon2id 기본 매개변수


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(slots=True)
class SessionInfo:
    token_hash: str
    csrf: str
    elevated: bool
    expires_at: str


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, config: Settings, session_factory: sessionmaker[Session]) -> None:
        self._config = config
        self._sf = session_factory
        self._fernet = Fernet(self._derive_key())

    # ── 키 ─────────────────────────────────────────────────────────────────

    def _derive_key(self) -> bytes:
        raw = self._config.secret_key.get_secret_value()
        if not raw:
            if self._config.is_prod:
                raise RuntimeError("운영 환경에서는 AP_SECRET_KEY 환경변수가 필요합니다")
            # 개발 환경: 데이터 폴더에 무작위 키를 만들어 둔다(저장소에 커밋하지 않는다).
            path = Path(self._config.data_dir) / ".dev_secret_key"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            raw = path.read_text(encoding="utf-8").strip()
        return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())

    # ── 감사 기록 ───────────────────────────────────────────────────────────

    def audit(self, action: str, detail: dict[str, Any] | None = None, ip: str = "", actor: str = "admin") -> None:
        with self._sf() as s, s.begin():
            s.add(AuditRow(ts=_iso(now_kst()), actor=actor, action=action, detail=json.dumps(detail or {}, ensure_ascii=False), ip=ip))

    # ── 상태 ───────────────────────────────────────────────────────────────

    def setup_state(self) -> str:
        """none(관리자 없음) | pending(TOTP 확인 전) | done."""
        with self._sf() as s:
            user = s.get(UserRow, 1)
        if user is None:
            return "none"
        return "done" if user.totp_confirmed else "pending"

    # ── 최초 등록 ───────────────────────────────────────────────────────────

    def _check_setup_token(self, token: str) -> None:
        expected = self._config.setup_token.get_secret_value()
        if not expected:
            if self._config.is_prod:
                raise AuthError(403, "setup_disabled", "서버에 AP_SETUP_TOKEN이 설정되지 않아 등록할 수 없습니다")
            return
        if not hmac.compare_digest(expected, token or ""):
            raise AuthError(403, "bad_setup_token", "등록용 값이 올바르지 않습니다")

    def begin_setup(self, password: str, setup_token: str, ip: str) -> dict[str, str]:
        """비밀번호를 저장하고 TOTP 비밀값을 만든다. TOTP 코드를 확인(confirm_setup)해야 등록이 끝난다."""
        self._guard_rate(ip)
        if self.setup_state() == "done":
            raise AuthError(409, "already_setup", "이미 등록이 끝났습니다")
        try:
            self._check_setup_token(setup_token)
        except AuthError:
            self._record_attempt(ip, False)
            raise
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AuthError(422, "weak_password", f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다")
        secret = pyotp.random_base32()
        with self._sf() as s, s.begin():
            s.execute(delete(UserRow))
            s.add(UserRow(id=1, password_hash=_hasher.hash(password), totp_secret_enc=self._fernet.encrypt(secret.encode()).decode(),
                          totp_confirmed=False, totp_last_counter=0, created_at=_iso(now_kst())))
        uri = pyotp.TOTP(secret).provisioning_uri(name="admin", issuer_name=ISSUER)
        return {"secret": secret, "otpauth_uri": uri}

    def confirm_setup(self, code: str, ip: str) -> None:
        self._guard_rate(ip)
        with self._sf() as s, s.begin():
            user = s.get(UserRow, 1)
            if user is None or user.totp_confirmed:
                raise AuthError(409, "no_pending_setup", "확인할 등록이 없습니다")
            ok = self._verify_totp(user, code)
            self._record_attempt_in(s, ip, ok)  # 실패 기록이 롤백되지 않게, 예외는 트랜잭션 밖에서 던진다
            if ok:
                user.totp_confirmed = True
        if not ok:
            raise AuthError(401, "bad_code", "인증 코드가 맞지 않습니다")
        self.audit("setup_completed", ip=ip)

    # ── TOTP ───────────────────────────────────────────────────────────────

    def _totp(self, user: UserRow) -> pyotp.TOTP:
        try:
            secret = self._fernet.decrypt(user.totp_secret_enc.encode()).decode()
        except InvalidToken as exc:
            raise AuthError(500, "key_mismatch", "서버 비밀키가 바뀌어 인증 정보를 읽을 수 없습니다") from exc
        return pyotp.TOTP(secret)

    def _verify_totp(self, user: UserRow, code: str) -> bool:
        """앞뒤 30초까지 허용하되, 한 번 쓴 코드는 다시 받지 않는다(재사용 방지)."""
        code = (code or "").strip().replace(" ", "")
        if not (code.isdigit() and len(code) == 6):
            return False
        totp = self._totp(user)
        now = now_kst()
        current = int(now.timestamp()) // 30
        for counter in (current - 1, current, current + 1):
            if counter <= user.totp_last_counter:
                continue
            if hmac.compare_digest(totp.at(counter * 30), code):
                user.totp_last_counter = counter
                return True
        return False

    # ── 로그인 시도 제한 ────────────────────────────────────────────────────

    def _record_attempt_in(self, s: Session, ip: str, ok: bool) -> None:
        s.add(LoginAttemptRow(ts=_iso(now_kst()), ip=ip, ok=ok))

    def _record_attempt(self, ip: str, ok: bool) -> None:
        with self._sf() as s, s.begin():
            self._record_attempt_in(s, ip, ok)

    def _guard_rate(self, ip: str) -> None:
        since = _iso(now_kst() - ATTEMPT_WINDOW)
        with self._sf() as s:
            by_ip = s.execute(select(func.count()).select_from(LoginAttemptRow).where(
                LoginAttemptRow.ts >= since, LoginAttemptRow.ip == ip, LoginAttemptRow.ok.is_(False))).scalar_one()
            overall = s.execute(select(func.count()).select_from(LoginAttemptRow).where(
                LoginAttemptRow.ts >= since, LoginAttemptRow.ok.is_(False))).scalar_one()
        if by_ip >= MAX_FAILS_PER_IP or overall >= MAX_FAILS_GLOBAL:
            raise AuthError(429, "too_many_attempts", "시도가 너무 많습니다. 15분 뒤에 다시 해 주세요")

    # ── 로그인·세션 ─────────────────────────────────────────────────────────

    def login(self, password: str, code: str, ip: str, user_agent: str) -> tuple[str, SessionInfo]:
        self._guard_rate(ip)
        generic = AuthError(401, "bad_credentials", "비밀번호 또는 인증 코드가 맞지 않습니다")
        with self._sf() as s, s.begin():
            user = s.get(UserRow, 1)
            if user is None or not user.totp_confirmed:
                raise AuthError(409, "setup_required", "먼저 관리자 등록을 끝내야 합니다")
            ok = False
            try:
                ok = _hasher.verify(user.password_hash, password or "")
            except (Argon2Error, InvalidHashError):
                ok = False
            if ok:
                ok = self._verify_totp(user, code)
            self._record_attempt_in(s, ip, ok)
            if not ok:
                s.flush()
                failed = True
            else:
                failed = False
                if _hasher.check_needs_rehash(user.password_hash):
                    user.password_hash = _hasher.hash(password)
                token = secrets.token_urlsafe(32)
                now = now_kst()
                row = SessionRow(token_hash=_hash_token(token), csrf=secrets.token_urlsafe(24), created_at=_iso(now), last_seen=_iso(now),
                                 expires_at=_iso(now + ABSOLUTE_TIMEOUT), elevated_until=None, ip=ip, user_agent=user_agent[:250])
                s.add(row)
                info = SessionInfo(row.token_hash, row.csrf, False, row.expires_at)
        if failed:
            self.audit("login_failed", ip=ip)
            raise generic
        self.audit("login", ip=ip)
        return token, info

    def session(self, token: str | None) -> SessionInfo | None:
        """쿠키 토큰으로 세션을 찾는다. 만료·유휴 초과면 지우고 None."""
        if not token:
            return None
        key = _hash_token(token)
        now = now_kst()
        with self._sf() as s, s.begin():
            row = s.get(SessionRow, key)
            if row is None:
                return None
            if _iso(now) >= row.expires_at or now - datetime.fromisoformat(row.last_seen) > IDLE_TIMEOUT:
                s.delete(row)
                return None
            row.last_seen = _iso(now)
            elevated = bool(row.elevated_until and _iso(now) < row.elevated_until)
            return SessionInfo(row.token_hash, row.csrf, elevated, row.expires_at)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._sf() as s, s.begin():
            s.execute(delete(SessionRow).where(SessionRow.token_hash == _hash_token(token)))

    def logout_all(self) -> int:
        with self._sf() as s, s.begin():
            count = s.execute(select(func.count()).select_from(SessionRow)).scalar_one()
            s.execute(delete(SessionRow))
        return int(count)

    def step_up(self, session: SessionInfo, code: str, ip: str) -> str:
        """TOTP 재인증. 성공하면 5분 동안 위험한 동작을 허용한다. 반환: 허용 만료 시각."""
        self._guard_rate(ip)
        with self._sf() as s, s.begin():
            user = s.get(UserRow, 1)
            row = s.get(SessionRow, session.token_hash)
            if user is None or row is None:
                raise AuthError(401, "not_authenticated", "로그인이 필요합니다")
            ok = self._verify_totp(user, code)
            self._record_attempt_in(s, ip, ok)
            if ok:
                row.elevated_until = _iso(now_kst() + ELEVATION_WINDOW)
                until = row.elevated_until
        if not ok:
            self.audit("stepup_failed", ip=ip)
            raise AuthError(401, "bad_code", "인증 코드가 맞지 않습니다(같은 코드는 한 번만 쓸 수 있습니다)")
        self.audit("stepup", ip=ip)
        return until

    def sessions(self) -> list[dict[str, Any]]:
        with self._sf() as s:
            rows = s.execute(select(SessionRow).order_by(SessionRow.last_seen.desc())).scalars().all()
        return [{"created_at": r.created_at, "last_seen": r.last_seen, "ip": r.ip, "user_agent": r.user_agent} for r in rows]

    def audit_rows(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._sf() as s:
            rows = s.execute(select(AuditRow).order_by(AuditRow.id.desc()).limit(limit)).scalars().all()
        return [{"ts": r.ts, "actor": r.actor, "action": r.action, "detail": json.loads(r.detail or "{}"), "ip": r.ip} for r in rows]


SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    # 차트 라이브러리가 인라인 스타일을 쓰므로 style만 인라인을 허용한다. 스크립트는 같은 출처만.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
    ),
}
HSTS = "max-age=31536000; includeSubDomains"
MAX_BODY_BYTES = 1_000_000
