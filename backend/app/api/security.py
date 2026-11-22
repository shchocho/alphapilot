"""인증과 세션. 실계좌 주문 권한이 있는 서버가 인터넷에 열리므로 보수적으로 만든다.

- 관리자 1명. 아이디 + 비밀번호(Argon2id) + TOTP 2단계 인증. 인증 앱을 잃어버리면 1회용 복구 코드로 들어온다.
- 최초 등록은 서버 환경변수의 1회용 값(AP_SETUP_TOKEN)이 있어야 한다. 새로 띄운 서버를 남이 먼저 차지하지 못하게 한다.
- 세션은 서버에 저장한다(쿠키에는 무작위 토큰만, DB에는 그 해시만). HttpOnly · Secure · SameSite=Strict.
- 상태를 바꾸는 요청은 세션에 묶인 CSRF 토큰 헤더가 있어야 한다.
- 위험한 동작(실전 전환, 한도 완화, 정지 해제)은 TOTP 재인증(step-up) 뒤 5분 동안만 허용한다.
- 로그인 실패는 IP별·전체로 세어 잠시 막는다.
- 증권사 키는 DB에 암호화해 두고(화면으로 다시 내려보내지 않는다), 바꾸려면 재인증해야 한다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
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
from app.store.db import AuditRow, BrokerKeyRow, LoginAttemptRow, SessionRow, UserRow

log = logging.getLogger("alphapilot.auth")

SESSION_COOKIE = "ap_session"
CSRF_HEADER = "x-csrf-token"
IDLE_TIMEOUT = timedelta(hours=12)
ABSOLUTE_TIMEOUT = timedelta(days=7)
ELEVATION_WINDOW = timedelta(minutes=5)
ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_FAILS_PER_IP = 5
MAX_FAILS_GLOBAL = 20
MIN_PASSWORD_LENGTH = 12
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
RECOVERY_CODE_COUNT = 10
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


def _norm_username(username: str) -> str:
    return (username or "").strip().lower()


def _hash_recovery(code: str) -> str:
    # 복구 코드는 40비트 무작위값이고 로그인 시도 제한 + 비밀번호 뒤에 있으므로 빠른 해시로 충분하다.
    return _hash_token((code or "").strip().lower().replace("-", "").replace(" ", ""))


def _is_totp_code(code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    return code.isdigit() and len(code) == 6


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

    def begin_setup(self, username: str, password: str, setup_token: str, ip: str) -> dict[str, str]:
        """비밀번호를 저장하고 TOTP 비밀값을 만든다. TOTP 코드를 확인(confirm_setup)해야 등록이 끝난다."""
        self._guard_rate(ip)
        if self.setup_state() == "done":
            raise AuthError(409, "already_setup", "이미 등록이 끝났습니다")
        try:
            self._check_setup_token(setup_token)
        except AuthError:
            self._record_attempt(ip, False)
            raise
        username = _norm_username(username)
        if not USERNAME_RE.match(username):
            raise AuthError(422, "bad_username", "아이디는 영문 소문자·숫자로 시작하는 3~32자(소문자, 숫자, . _ -)여야 합니다")
        self._check_password(password)
        secret = pyotp.random_base32()
        with self._sf() as s, s.begin():
            s.execute(delete(UserRow))
            s.add(UserRow(id=1, username=username, password_hash=_hasher.hash(password), totp_secret_enc=self._fernet.encrypt(secret.encode()).decode(),
                          totp_confirmed=False, totp_last_counter=0, created_at=_iso(now_kst())))
        return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)}

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AuthError(422, "weak_password", f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다")

    def confirm_setup(self, code: str, ip: str) -> list[str]:
        """인증 앱 코드를 확인해 등록을 끝내고, 인증 앱 분실용 복구 코드를 한 번만 돌려준다."""
        self._guard_rate(ip)
        with self._sf() as s, s.begin():
            user = s.get(UserRow, 1)
            if user is None or user.totp_confirmed:
                raise AuthError(409, "no_pending_setup", "확인할 등록이 없습니다")
            ok = self._verify_totp(user, code)
            self._record_attempt_in(s, ip, ok)  # 실패 기록이 롤백되지 않게, 예외는 트랜잭션 밖에서 던진다
            if ok:
                user.totp_confirmed = True
                codes = self._issue_recovery_codes(user)
        if not ok:
            raise AuthError(401, "bad_code", "인증 코드가 맞지 않습니다")
        self.audit("setup_completed", ip=ip)
        return codes

    # ── TOTP ───────────────────────────────────────────────────────────────

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise AuthError(500, "key_mismatch", "서버 비밀키가 바뀌어 인증 정보를 읽을 수 없습니다") from exc

    def _verify_totp(self, user: UserRow, code: str, secret_enc: str | None = None) -> bool:
        """앞뒤 30초까지 허용하되, 한 번 쓴 코드는 다시 받지 않는다(재사용 방지)."""
        code = (code or "").strip().replace(" ", "")
        if not (code.isdigit() and len(code) == 6):
            return False
        totp = pyotp.TOTP(self._decrypt(secret_enc or user.totp_secret_enc))
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

    def login(self, username: str, password: str, code: str, ip: str, user_agent: str) -> tuple[str, SessionInfo]:
        """code는 인증 앱의 6자리 코드나 복구 코드. 복구 코드로 들어오면 인증 앱을 다시 연결할 수 있게 재인증된 세션을 준다."""
        self._guard_rate(ip)
        generic = AuthError(401, "bad_credentials", "아이디, 비밀번호 또는 인증 코드가 맞지 않습니다")
        recovery = False
        with self._sf() as s, s.begin():
            user = s.get(UserRow, 1)
            if user is None or not user.totp_confirmed:
                raise AuthError(409, "setup_required", "먼저 관리자 등록을 끝내야 합니다")
            ok = self._password_ok(user, password)  # 아이디가 틀려도 해시 검사는 해서 응답 시간으로 구분되지 않게 한다
            ok = hmac.compare_digest(user.username.encode(), _norm_username(username).encode()) and ok
            if ok and _is_totp_code(code):
                ok = self._verify_totp(user, code)
            elif ok:
                ok = recovery = self._use_recovery_code(user, code)
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
                                 expires_at=_iso(now + ABSOLUTE_TIMEOUT), elevated_until=_iso(now + ELEVATION_WINDOW) if recovery else None,
                                 ip=ip, user_agent=user_agent[:250])
                s.add(row)
                info = SessionInfo(row.token_hash, row.csrf, recovery, row.expires_at)
        if failed:
            self.audit("login_failed", ip=ip)
            raise generic
        self.audit("login_recovery" if recovery else "login", ip=ip)
        return token, info

    @staticmethod
    def _password_ok(user: UserRow, password: str) -> bool:
        try:
            return _hasher.verify(user.password_hash, password or "")
        except (Argon2Error, InvalidHashError):
            return False

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

    # ── 계정 관리(재인증한 세션에서만 부른다) ─────────────────────────────────

    def _user(self, s: Session) -> UserRow:
        user = s.get(UserRow, 1)
        if user is None:
            raise AuthError(409, "setup_required", "먼저 관리자 등록을 끝내야 합니다")
        return user

    def account(self) -> dict[str, Any]:
        with self._sf() as s:
            user = self._user(s)
            return {"username": user.username, "recovery_codes_left": len(json.loads(user.recovery_codes or "[]"))}

    def change_password(self, session: SessionInfo, current: str, new: str, ip: str) -> int:
        """비밀번호를 바꾸고 이 세션을 뺀 나머지 기기를 로그아웃시킨다. 반환: 닫은 세션 수."""
        self._guard_rate(ip)
        self._check_password(new)
        with self._sf() as s, s.begin():
            user = self._user(s)
            ok = self._password_ok(user, current)
            self._record_attempt_in(s, ip, ok)
            if ok:
                user.password_hash = _hasher.hash(new)
                others = delete(SessionRow).where(SessionRow.token_hash != session.token_hash)
                closed = s.execute(others).rowcount or 0
        if not ok:
            self.audit("password_change_failed", ip=ip)
            raise AuthError(401, "bad_password", "지금 비밀번호가 맞지 않습니다")
        self.audit("password_changed", {"closed_sessions": closed}, ip)
        return int(closed)

    def _issue_recovery_codes(self, user: UserRow) -> list[str]:
        codes = [f"{h[:5]}-{h[5:]}" for h in (secrets.token_hex(5) for _ in range(RECOVERY_CODE_COUNT))]
        user.recovery_codes = json.dumps([_hash_recovery(c) for c in codes])
        return codes

    def _use_recovery_code(self, user: UserRow, code: str) -> bool:
        hashes: list[str] = json.loads(user.recovery_codes or "[]")
        digest = _hash_recovery(code)
        match = next((h for h in hashes if hmac.compare_digest(h, digest)), None)
        if match is None:
            return False
        hashes.remove(match)
        user.recovery_codes = json.dumps(hashes)
        return True

    def new_recovery_codes(self, ip: str) -> list[str]:
        """복구 코드를 새로 만든다. 이전 코드는 모두 못 쓰게 된다."""
        with self._sf() as s, s.begin():
            codes = self._issue_recovery_codes(self._user(s))
        self.audit("recovery_codes_issued", ip=ip)
        return codes

    def begin_totp_reset(self) -> dict[str, str]:
        """새 인증 앱 비밀값을 만든다. confirm_totp_reset에서 새 코드를 확인해야 바뀐다(그 전까지는 이전 앱이 그대로 쓰인다)."""
        secret = pyotp.random_base32()
        with self._sf() as s, s.begin():
            user = self._user(s)
            user.totp_pending_enc = self._fernet.encrypt(secret.encode()).decode()
            name = user.username
        return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=name, issuer_name=ISSUER)}

    def confirm_totp_reset(self, code: str, ip: str) -> None:
        self._guard_rate(ip)
        with self._sf() as s, s.begin():
            user = self._user(s)
            pending = user.totp_pending_enc
            if not pending:
                raise AuthError(409, "no_pending_reset", "다시 연결 중인 인증 앱이 없습니다")
            before = user.totp_last_counter
            user.totp_last_counter = 0  # 새 비밀값이라 이전 앱에서 쓴 코드 기록은 상관없다
            ok = self._verify_totp(user, code, pending)
            self._record_attempt_in(s, ip, ok)
            if ok:
                user.totp_secret_enc, user.totp_pending_enc = pending, None
            else:
                user.totp_last_counter = before
        if not ok:
            raise AuthError(401, "bad_code", "새 인증 앱의 코드가 맞지 않습니다")
        self.audit("totp_reset", ip=ip)

    # ── 증권사 키 ───────────────────────────────────────────────────────────

    def save_broker_keys(self, env: str, app_key: str, secret_key: str, ip: str) -> None:
        with self._sf() as s, s.begin():
            s.merge(BrokerKeyRow(env=env, app_key_enc=self._fernet.encrypt(app_key.encode()).decode(),
                                 secret_key_enc=self._fernet.encrypt(secret_key.encode()).decode(), updated_at=_iso(now_kst())))
        self.audit("broker_keys_saved", {"env": env}, ip)

    def delete_broker_keys(self, env: str, ip: str) -> None:
        with self._sf() as s, s.begin():
            s.execute(delete(BrokerKeyRow).where(BrokerKeyRow.env == env))
        self.audit("broker_keys_deleted", {"env": env}, ip)

    def broker_keys(self) -> dict[str, tuple[str, str]]:
        """DB에 둔 증권사 키(복호화). 서버 비밀키가 바뀌어 읽지 못하는 키는 건너뛰고 로그에 남긴다."""
        with self._sf() as s:
            rows = s.execute(select(BrokerKeyRow)).scalars().all()
        keys: dict[str, tuple[str, str]] = {}
        for row in rows:
            try:
                keys[row.env] = (self._decrypt(row.app_key_enc), self._decrypt(row.secret_key_enc))
            except AuthError:
                log.warning("증권사 키(%s)를 복호화하지 못했습니다. AP_SECRET_KEY가 바뀌었으면 설정 화면에서 다시 넣으세요", row.env)
        return keys

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
