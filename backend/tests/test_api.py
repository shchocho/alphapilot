"""API 테스트: 인증·CSRF·재인증·실전 전환 잠금과 주요 화면 엔드포인트."""

import time

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.factory import create_app
from app.api.security import SESSION_COOKIE
from app.config import Settings
from app.data.sample import SampleProvider
from app.data.universe import load_universe
from app.engine import service as service_module
from app.engine.service import EngineService
from app.store.db import make_engine, make_session_factory
from tests.helpers import END

PASSWORD = "correct horse battery staple"
USERNAME = "hank"


class Session:
    """테스트용 로그인 도우미. TOTP 코드는 한 번만 쓸 수 있어서 호출마다 다음 시간 창의 코드를 쓴다."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.secret = ""
        self.csrf = ""
        self._step = 0

    def code(self) -> str:
        # 서버는 앞뒤 30초를 허용한다: 첫 호출은 직전 창, 다음은 현재 창, 그다음은 다음 창
        offset = (self._step - 1) * 30
        self._step += 1
        return pyotp.TOTP(self.secret).at(time.time() + offset)

    def reset_codes(self) -> None:
        """서버가 받은 코드 기록을 지워 다시 세 개(직전·현재·다음 창)를 쓸 수 있게 한다. 코드를 많이 쓰는 테스트용."""
        with self.client.app.state.auth._sf() as s, s.begin():
            s.execute(text("UPDATE users SET totp_last_counter = 0"))
        self._step = 0

    def setup(self, token: str = "") -> None:
        r = self.client.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD, "setup_token": token})
        assert r.status_code == 200, r.text
        self.secret = r.json()["secret"]
        r = self.client.post("/api/auth/setup/confirm", json={"code": self.code()})
        assert r.status_code == 200, r.text
        self.recovery_codes = r.json()["recovery_codes"]

    def login(self, code: str | None = None, password: str = PASSWORD):
        r = self.client.post("/api/auth/login", json={"username": USERNAME, "password": password, "code": code or self.code()})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf"]
        return r.json()

    def stepup(self) -> None:
        r = self.post("/api/auth/stepup", {"code": self.code()})
        assert r.status_code == 200, r.text

    def post(self, url: str, body: dict | None = None):
        return self.client.post(url, json=body or {}, headers={"x-csrf-token": self.csrf})

    def delete(self, url: str):
        return self.client.delete(url, headers={"x-csrf-token": self.csrf})

    def put(self, url: str, body: dict):
        return self.client.put(url, json=body, headers={"x-csrf-token": self.csrf})


def make(tmp_path, monkeypatch, **env) -> tuple[TestClient, EngineService, Settings]:
    stocks = load_universe()[:16]
    monkeypatch.setattr(service_module, "load_universe", lambda: stocks)
    monkeypatch.setattr(service_module, "universe_map", lambda: {s.code: s for s in stocks})
    config = Settings(_env_file=None, AP_DATA_PROVIDER="sample", AP_DATA_DIR=str(tmp_path), **env)
    factory = make_session_factory(make_engine(None))
    service = EngineService(config, factory, provider=SampleProvider(end=END))
    app = create_app(config, session_factory=factory, service=service, run_scheduler=False)
    return TestClient(app), service, config


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    client, service, config = make(tmp_path, monkeypatch)
    with client:
        yield client, service, config


@pytest.fixture
def user(ctx) -> Session:
    client, _, _ = ctx
    session = Session(client)
    session.setup()
    session.login()
    return session


# ── 인증 ─────────────────────────────────────────────────────────────────────

def test_health_is_public_but_everything_else_needs_login(ctx):
    client, _, _ = ctx
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["checks"] == {"db": "ok", "scheduler": "off"}
    for url in ("/api/status", "/api/dashboard", "/api/portfolio", "/api/settings", "/api/ledger", "/api/events", "/api/backtests"):
        r = client.get(url)
        assert r.status_code == 401, url
        assert r.json()["error"]["code"] == "not_authenticated"
    assert client.post("/api/engine/stop").status_code == 401


def test_setup_then_login_sets_a_hardened_session_cookie(ctx):
    client, _, _ = ctx
    assert client.get("/api/auth/state").json() == {"setup": "none", "authenticated": False, "csrf": None, "elevated": False, "setup_token_required": False}
    session = Session(client)
    session.setup()
    assert client.get("/api/auth/state").json()["setup"] == "done"
    r = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": session.code()})
    cookie = r.headers["set-cookie"].lower()
    assert SESSION_COOKIE in cookie and "httponly" in cookie and "samesite=strict" in cookie
    state = client.get("/api/auth/state").json()
    assert state["authenticated"] and state["csrf"] == r.json()["csrf"]


def test_weak_password_and_repeat_setup_are_refused(ctx):
    client, _, _ = ctx
    assert client.post("/api/auth/setup", json={"username": USERNAME, "password": "short", "setup_token": ""}).status_code == 422
    Session(client).setup()
    assert client.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD, "setup_token": ""}).status_code == 409


def test_setup_requires_the_server_token_when_configured(tmp_path, monkeypatch):
    client, _, _ = make(tmp_path, monkeypatch, AP_SETUP_TOKEN="one-time-value")
    with client:
        assert client.get("/api/auth/state").json()["setup_token_required"] is True
        assert client.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD, "setup_token": "guess"}).status_code == 403
        assert client.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD, "setup_token": "one-time-value"}).status_code == 200


def test_production_refuses_setup_without_a_token(tmp_path, monkeypatch):
    client, _, _ = make(tmp_path, monkeypatch, AP_ENV="prod", AP_SECRET_KEY="k" * 40, AP_ALLOWED_HOSTS="testserver")
    with client:
        r = client.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD, "setup_token": ""})
        assert r.status_code == 403 and r.json()["error"]["code"] == "setup_disabled"
        assert "strict-transport-security" in r.headers


def test_wrong_password_or_code_gives_the_same_generic_error(user, ctx):
    client, _, _ = ctx
    client.cookies.clear()
    bad_password = client.post("/api/auth/login", json={"username": USERNAME, "password": "wrong password here", "code": user.code()})
    bad_code = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": "000000"})
    assert bad_password.status_code == bad_code.status_code == 401
    assert bad_password.json() == bad_code.json()


def test_a_totp_code_cannot_be_used_twice(ctx):
    client, _, _ = ctx
    session = Session(client)
    session.setup()
    code = session.code()
    assert client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": code}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": code}).status_code == 401


def test_repeated_failures_are_rate_limited(ctx):
    client, _, _ = ctx
    Session(client).setup()
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": USERNAME, "password": "nope nope nope", "code": "123456"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": USERNAME, "password": "nope nope nope", "code": "123456"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"


def test_state_changing_requests_need_the_csrf_header(user, ctx):
    client, _, _ = ctx
    assert client.post("/api/engine/pause").status_code == 403
    assert client.post("/api/engine/pause", headers={"x-csrf-token": "forged"}).status_code == 403
    assert user.post("/api/engine/pause").status_code == 200
    assert client.get("/api/status").status_code == 200  # 읽기는 헤더가 없어도 된다


def test_logout_ends_the_session(user, ctx):
    client, _, _ = ctx
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/status").status_code == 401


# ── 아이디·복구 코드·비밀번호 변경·인증 앱 재연결 ─────────────────────────────

def test_login_needs_the_right_id_but_ignores_its_case(user, ctx):
    client, _, _ = ctx
    client.cookies.clear()
    wrong = client.post("/api/auth/login", json={"username": "someone", "password": PASSWORD, "code": "123456"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "bad_credentials"
    r = client.post("/api/auth/login", json={"username": " HANK ", "password": PASSWORD, "code": user.code()})
    assert r.status_code == 200
    assert client.get("/api/auth/account").json() == {"username": "hank", "recovery_codes_left": 10}


def test_setup_rejects_a_bad_login_id(ctx):
    client, _, _ = ctx
    r = client.post("/api/auth/setup", json={"username": "a b", "password": PASSWORD, "setup_token": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_username"


def test_a_recovery_code_works_once_and_lets_you_relink_the_authenticator(user, ctx):
    client, _, _ = ctx
    code = user.recovery_codes[0]
    client.cookies.clear()
    assert user.login(code=code.upper())["recovery"] is True
    assert client.get("/api/auth/state").json()["elevated"] is True  # 인증 앱 없이도 바로 다시 연결할 수 있게
    assert client.get("/api/auth/account").json()["recovery_codes_left"] == 9

    old_secret = user.secret
    r = user.post("/api/auth/totp/reset")
    assert r.status_code == 200 and r.json()["secret"] != old_secret
    assert user.post("/api/auth/totp/confirm", {"code": pyotp.TOTP(old_secret).now()}).status_code == 401
    user.secret = r.json()["secret"]
    assert user.post("/api/auth/totp/confirm", {"code": user.code()}).status_code == 200
    assert user.post("/api/auth/totp/confirm", {"code": user.code()}).status_code == 409  # 끝난 뒤에는 확인할 것이 없다

    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": code}).status_code == 401
    user.reset_codes()
    user.login()  # 새 인증 앱 코드로 들어온다


def test_new_recovery_codes_replace_the_old_ones_and_need_step_up(user, ctx):
    client, _, _ = ctx
    assert user.post("/api/auth/recovery-codes").json()["error"]["code"] == "stepup_required"
    user.stepup()
    fresh = user.post("/api/auth/recovery-codes").json()["recovery_codes"]
    assert len(fresh) == 10 and not set(fresh) & set(user.recovery_codes)
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": user.recovery_codes[1]}).status_code == 401
    user.login(code=fresh[0])


def test_changing_the_password_checks_the_current_one_and_signs_out_other_devices(user, ctx):
    client, _, _ = ctx
    other = TestClient(client.app)
    peer = Session(other)
    peer.secret = user.secret
    user.reset_codes()
    peer.login()  # 직전 창의 코드
    user._step = 1  # 재인증은 현재 창의 코드
    new = "a brand new long password"
    assert user.post("/api/auth/password", {"current": PASSWORD, "new": new}).json()["error"]["code"] == "stepup_required"
    user.stepup()
    assert user.post("/api/auth/password", {"current": "wrong wrong wrong", "new": new}).status_code == 401
    assert user.post("/api/auth/password", {"current": PASSWORD, "new": "short"}).status_code == 422
    assert user.post("/api/auth/password", {"current": PASSWORD, "new": new}).json() == {"closed": 1}
    assert client.get("/api/status").status_code == 200 and other.get("/api/status").status_code == 401
    client.cookies.clear()
    user.reset_codes()
    assert client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "code": user.code()}).status_code == 401
    user.login(password=new)


def test_broker_keys_are_stored_encrypted_override_env_and_are_never_sent_back(tmp_path, monkeypatch):
    client, _, config = make(tmp_path, monkeypatch, KIWOOM_MOCK_APP_KEY="ENV-APP-KEY-0001", KIWOOM_MOCK_SECRET_KEY="ENV-SECRET-0001")
    with client:
        user = Session(client)
        user.setup()
        user.login()
        assert client.get("/api/settings/broker/keys").json() == {"mock": "env", "live": None}
        body = {"env": "live", "app_key": "DB-LIVE-APP-KEY-1", "secret_key": "DB-LIVE-SECRET-1"}
        assert user.put("/api/settings/broker/keys", body).json()["error"]["code"] == "stepup_required"
        user.stepup()
        assert user.put("/api/settings/broker/keys", body).status_code == 200
        assert client.get("/api/settings/broker/keys").json() == {"mock": "env", "live": "db"}
        assert config.kiwoom_keys("live") == ("DB-LIVE-APP-KEY-1", "DB-LIVE-SECRET-1")
        assert client.get("/api/settings").json()["broker"]["live"]["configured"] is True
        assert client.get("/api/settings/live").status_code in (404, 405)  # 키를 읽어 가는 경로는 없다

        factory = client.app.state.auth._sf
        with factory() as s:
            raw = s.execute(text("SELECT app_key_enc || secret_key_enc FROM broker_keys")).scalar_one()
        assert "DB-LIVE" not in raw
        blob = client.get("/api/settings").text + client.get("/api/settings/broker/keys").text + client.get("/api/auth/sessions").text
        assert "DB-LIVE" not in blob

        assert user.put("/api/settings/broker/keys", {**body, "env": "mock"}).status_code == 200
        assert config.kiwoom_keys("mock") == ("DB-LIVE-APP-KEY-1", "DB-LIVE-SECRET-1")
        assert user.delete("/api/settings/broker/keys/mock").status_code == 200
        assert config.kiwoom_keys("mock") == ("ENV-APP-KEY-0001", "ENV-SECRET-0001")  # 지우면 .env 값으로 돌아간다


# ── 보안 헤더·입력 검증 ───────────────────────────────────────────────────────

def test_security_headers_are_set(ctx):
    client, _, _ = ctx
    headers = client.get("/api/health").headers
    assert headers["x-frame-options"] == "DENY" and headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in headers["content-security-policy"] and "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["cache-control"] == "no-store"


def test_unknown_host_header_is_rejected(ctx):
    client, _, _ = ctx
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_oversized_body_and_bad_paths_are_rejected(user, ctx):
    client, _, _ = ctx
    big = client.post("/api/auth/login", content=b"x" * 1_100_000, headers={"content-type": "application/json"})
    assert big.status_code == 413
    assert client.get("/api/stocks/DROP%20TABLE").status_code == 422
    assert client.get("/api/stocks/00593").status_code == 422
    assert user.post("/api/engine/advance", {"days": 9999}).status_code == 422


def test_secrets_never_appear_in_responses(tmp_path, monkeypatch):
    client, _, _ = make(tmp_path, monkeypatch, KIWOOM_MOCK_APP_KEY="MOCK-APP-KEY-VALUE", KIWOOM_MOCK_SECRET_KEY="MOCK-SECRET-VALUE",
                        ANTHROPIC_API_KEY="sk-ant-test-value")
    with client:
        session = Session(client)
        session.setup()
        session.login()
        blob = client.get("/api/settings").text + client.get("/api/status").text
        for secret in ("MOCK-APP-KEY-VALUE", "MOCK-SECRET-VALUE", "sk-ant-test-value", PASSWORD, session.secret):
            assert secret not in blob
        assert client.get("/api/settings").json()["broker"]["mock"]["configured"] is True


# ── 재인증이 필요한 동작 ───────────────────────────────────────────────────────

def test_loosening_limits_needs_step_up_but_tightening_does_not(user):
    assert user.put("/api/settings/limits", {"max_positions": 5}).status_code == 200
    r = user.put("/api/settings/limits", {"max_position_pct": 0.3})
    assert r.status_code == 403 and r.json()["error"]["loosened"] == ["max_position_pct"]
    user.stepup()
    r = user.put("/api/settings/limits", {"max_position_pct": 0.3})
    assert r.status_code == 200 and r.json()["limits"]["max_position_pct"] == 0.3
    assert user.put("/api/settings/limits", {"max_position_pct": 9}).status_code == 422


def test_raising_automation_level_needs_step_up(user):
    assert user.put("/api/settings/engine", {"automation_level": 3}).status_code == 403
    assert user.put("/api/settings/engine", {"automation_level": 0}).status_code == 200
    user.stepup()
    assert user.put("/api/settings/engine", {"automation_level": 3}).json()["automation_level"] == 3


def test_restarting_a_stopped_engine_needs_step_up(user):
    assert user.post("/api/engine/refresh-data").status_code == 200
    r = user.post("/api/engine/start")
    assert r.status_code == 403 and r.json()["error"]["code"] == "stepup_required"
    user.stepup()
    assert user.post("/api/engine/start").json() == {"state": "running"}
    assert user.post("/api/engine/pause").json() == {"state": "paused"}
    assert user.post("/api/engine/start").json() == {"state": "running"}  # 일시정지 해제는 재인증 없이


LIVE_KEYS = {"KIWOOM_LIVE_APP_KEY": "live-key", "KIWOOM_LIVE_SECRET_KEY": "live-secret"}


@pytest.mark.parametrize(
    ("env", "confirm", "expected"),
    [({}, "실전 매매를 시작합니다", "앱키가 서버에 설정되지 않았습니다"),
     (LIVE_KEYS, "실전 매매를 시작합니다", "ALLOW_LIVE_TRADING"),
     ({**LIVE_KEYS, "ALLOW_LIVE_TRADING": "true"}, "네", "확인 문구"),
     ({**LIVE_KEYS, "ALLOW_LIVE_TRADING": "true"}, "실전 매매를 시작합니다", "주문 실행기")],
)
def test_live_switch_needs_every_condition_and_is_still_locked(tmp_path, monkeypatch, env, confirm, expected):
    client, service, _ = make(tmp_path, monkeypatch, **env)
    with client:
        session = Session(client)
        session.setup()
        session.login()
        unelevated = session.post("/api/settings/env", {"env": "live", "confirm": confirm})
        assert unelevated.status_code == 403 and unelevated.json()["error"]["code"] == "stepup_required"
        session.stepup()
        r = session.post("/api/settings/env", {"env": "live", "confirm": confirm})
        assert r.status_code == 409 and expected in r.json()["error"]["message"]
        assert service.settings().env == "sim"  # 어떤 경우에도 전환되지 않는다


def test_broker_test_reports_missing_keys_without_calling_out(user):
    r = user.post("/api/settings/broker/test", {"env": "mock"})
    assert r.json()["ok"] is False and "KIWOOM_MOCK_APP_KEY" in r.json()["message"]


def test_liquidate_requires_the_confirmation_phrase(user):
    assert user.post("/api/engine/liquidate", {"confirm": "yes"}).status_code == 409
    assert user.post("/api/engine/liquidate", {"confirm": "전량 매도"}).status_code == 200


# ── 화면 엔드포인트 ───────────────────────────────────────────────────────────

@pytest.fixture
def running(user, ctx):
    client, service, _ = ctx
    assert user.post("/api/engine/refresh-data").status_code == 200
    user.stepup()
    assert user.put("/api/settings/engine", {"decider": "rules", "automation_level": 3}).status_code == 200
    assert user.post("/api/engine/start").status_code == 200
    service.kv.set("sim_start", service.market.calendar[-45].isoformat())
    r = user.post("/api/engine/advance", {"days": 40})
    assert r.status_code == 200 and len(r.json()["days"]) == 40
    return user


def test_dashboard_reports_account_risk_passbook_and_curve(running, ctx):
    client, _, _ = ctx
    data = client.get("/api/dashboard").json()
    assert data["source_label"] == "시뮬레이션"
    assert data["account"]["equity"] > 0 and len(data["curve"]) == 40
    assert set(data["risk"]) >= {"daily_used", "heat_pct", "positions", "max_positions", "drawdown_pct"}
    book = data["passbook"]
    assert book["new_count"] == len(book["rows"]) > 0 and book["rows"][0]["seq"] == book["last_seq"]
    assert data["regime"]["label"] in ("상승", "중립", "하락")
    seen = running.post("/api/ledger/seen", {"seq": book["last_seq"]})
    assert seen.json()["seen_seq"] == book["last_seq"]
    assert client.get("/api/dashboard").json()["passbook"]["new_count"] == 0


def test_ledger_endpoints_filter_verify_and_export(running, ctx):
    client, _, _ = ctx
    rows = client.get("/api/ledger", params={"kind": "cycle", "limit": 5}).json()["rows"]
    assert rows and all(r["kind"] == "cycle" for r in rows)
    assert client.get("/api/ledger/verify").json() == {"ok": True, "broken_seq": None}
    export = client.get("/api/ledger/export.csv")
    assert export.headers["content-type"].startswith("text/csv") and "거래번호" in export.text


def test_ledger_chain_follows_one_judgement_from_first_line_to_last(running, ctx):
    client, _, _ = ctx
    rows = client.get("/api/ledger", params={"limit": 300}).json()["rows"]
    chained = next(r for r in rows if r["chain_id"] and r["kind"] in ("decision", "intent", "fill_buy"))
    data = client.get(f"/api/ledger/chain/{chained['chain_id']}").json()
    seqs = [r["seq"] for r in data["rows"]]
    assert seqs == sorted(seqs) and chained["seq"] in seqs  # 오래된 줄부터 차례로
    assert all(r["chain_id"] == chained["chain_id"] for r in data["rows"])
    assert data["name"] == chained["name"] and "decision_id" in data
    assert client.get("/api/ledger/chain/zzz-000000").json()["rows"] == []
    assert client.get("/api/ledger/chain/a b").status_code == 422


def test_after_a_simulation_reset_the_passbook_and_chains_show_only_the_new_run(running, ctx):
    # 장부는 지우지 않는다(위변조 검사 대상). 대신 다시 시작한 뒤의 화면에는 지난 실행의 줄이 섞이지 않아야 한다.
    client, _, _ = ctx
    before = client.get("/api/ledger", params={"limit": 300}).json()["rows"]
    old = next(r for r in before if r["chain_id"] and r["kind"] == "decision")
    assert client.get(f"/api/ledger/chain/{old['chain_id']}").json()["rows"]
    assert running.post("/api/settings/sim-reset", {}).status_code == 200
    assert client.get(f"/api/ledger/chain/{old['chain_id']}").json()["rows"] == []
    book = client.get("/api/dashboard").json()["passbook"]
    assert [r["kind"] for r in book["rows"] + book["older"]] == ["engine"]  # "초기화했다"는 한 줄만 보인다
    assert len(client.get("/api/ledger", params={"limit": 300}).json()["rows"]) > len(before) - 1  # 장부 전체에는 그대로 남아 있다
    assert client.get("/api/ledger/verify").json()["ok"] is True


def test_screener_lists_techniques_with_counts_and_rows(running, ctx):
    client, _, _ = ctx
    data = client.get("/api/screener", params={"technique": "volatility_breakout"}).json()
    assert data["technique"] == "volatility_breakout"
    assert [t["key"] for t in data["techniques"]][0] == "trend_template"
    assert all({"code", "name", "score", "spark", "passed", "total"} <= set(r) for r in data["rows"])
    assert client.get("/api/screener", params={"technique": "nope"}).json()["technique"] == "trend_template"


def test_stock_detail_has_chart_checks_seats_and_regime(running, ctx):
    client, service, _ = ctx
    code = next(iter(service.market.stocks))
    data = client.get(f"/api/stocks/{code}").json()
    assert len(data["bars"]) == 260 and len(data["overlays"]["sma50"]) == 260
    assert len(data["techniques"]) == 7 and len(data["seats"]) == 8
    assert data["regime"]["label"] and "stats" in data
    assert client.get("/api/stocks/999999").status_code == 409
    hits = client.get("/api/stocks/search", params={"q": data["name"][:2]}).json()["results"]
    assert any(h["code"] == code for h in hits)


def test_committee_and_decision_detail(running, ctx):
    client, _, _ = ctx
    data = client.get("/api/committee").json()
    assert data["day"] and data["decider"] == "rules" and "scorecard" in data
    if data["decisions"]:
        detail = client.get(f"/api/committee/{data['decisions'][0]['id']}").json()
        assert {"seats", "final", "chain"} <= set(detail)


def test_portfolio_has_positions_intents_trades_and_journal(running, ctx):
    client, _, _ = ctx
    data = client.get("/api/portfolio").json()
    assert {"positions", "intents", "trades", "journal", "daily_pnl", "summary"} <= set(data)
    assert data["summary"]["equity"] > 0
    assert all(t["reason_label"] for t in data["trades"])


def test_approval_flow_over_the_api(user, ctx):
    client, service, _ = ctx
    user.post("/api/engine/refresh-data")
    user.stepup()
    user.put("/api/settings/engine", {"decider": "rules", "automation_level": 1})
    user.post("/api/engine/start")
    service.kv.set("sim_start", service.market.calendar[-30].isoformat())
    for _ in range(25):  # 승인 대기가 생길 때까지 하루씩 진행
        user.post("/api/engine/advance", {"days": 1})
        cards = client.get("/api/intents/pending").json()["cards"]
        if cards:
            break
    else:
        pytest.skip("이 구간에는 승인 대기가 생기지 않았습니다")
    card = cards[0]
    assert {"thesis", "amount", "technique_name", "expires_at"} <= set(card)
    assert user.post(f"/api/intents/{card['id']}/decide", {"approve": True}).json()["status"] == "approved"
    assert user.post(f"/api/intents/{card['id']}/decide", {"approve": True}).status_code == 409


def test_backtest_runs_and_is_stored(running, ctx):
    client, _, _ = ctx
    r = running.post("/api/backtests", {"initial_cash": 20_000_000, "techniques": ["turtle", "canslim_daily"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["params"]["decider"] == "rules" and data["params"]["techniques"] == ["turtle", "canslim_daily"]
    assert data["curve"] and "cagr" in data["summary"]
    assert client.get("/api/backtests").json()["runs"][0]["id"] == data["id"]
    assert client.get(f"/api/backtests/{data['id']}").json()["summary"] == data["summary"]
    assert running.post("/api/backtests", {"techniques": ["martingale"]}).status_code == 409


def test_settings_and_sim_reset(running, ctx):
    client, service, _ = ctx
    data = client.get("/api/settings").json()
    assert data["engine"]["env"] == "sim" and data["broker"]["runner_available"] is False
    assert [o["value"] for o in data["options"]["automation"]] == [0, 1, 2, 3]
    assert running.put("/api/settings/engine", {"ai_model": "gpt-9"}).status_code == 422
    assert running.post("/api/settings/sim-reset", {"initial_cash": 50_000_000}).status_code == 200
    assert client.get("/api/status").json()["sim_day"] is None
    assert client.get("/api/auth/sessions").json()["audit"]


# ── 화면 파일 서빙 ───────────────────────────────────────────────────────────

def test_built_screen_files_get_correct_types_even_when_the_os_maps_js_to_text_plain(tmp_path, monkeypatch):
    # 윈도우는 레지스트리 때문에 .js를 text/plain으로 알려주는 경우가 있다. 그러면 브라우저가 모듈 스크립트를 거부해 빈 화면이 된다.
    import starlette.responses

    monkeypatch.setattr(starlette.responses, "guess_type", lambda *_a, **_k: ("text/plain", None))
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("export {}", encoding="utf-8")
    (dist / "assets" / "app-abc123.css").write_text("body{}", encoding="utf-8")
    (dist / "assets" / "font-abc123.woff2").write_bytes(b"wOF2")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    client, _, _ = make(tmp_path / "data", monkeypatch, AP_STATIC_DIR=str(dist))
    with client:
        assert client.get("/assets/app-abc123.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/assets/app-abc123.css").headers["content-type"].startswith("text/css")
        assert client.get("/assets/font-abc123.woff2").headers["content-type"] == "font/woff2"
        assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")
        page = client.get("/portfolio")  # 화면 주소는 index.html로 답한다
        assert page.headers["content-type"].startswith("text/html") and "<title>t</title>" in page.text


def test_hashed_assets_are_cached_long_and_the_page_itself_is_revalidated(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("export {}", encoding="utf-8")
    client, _, _ = make(tmp_path / "data", monkeypatch, AP_STATIC_DIR=str(dist))
    with client:
        assert "immutable" in client.get("/assets/app-abc123.js").headers["cache-control"]
        assert client.get("/").headers["cache-control"] == "no-cache"
        # 없는 자산 주소에 index.html을 돌려주면 브라우저가 HTML을 스크립트로 읽으려다 실패한다
        assert client.get("/assets/missing-000000.js").status_code == 404
