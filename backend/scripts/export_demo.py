"""GitHub Pages용 읽기 전용 데모 데이터를 만든다.

임시 DB에서 일봉을 받고 시뮬레이션을 몇 달 돌린 뒤, 화면이 읽는 GET 응답을 frontend/public/demo/*.json으로 저장한다.
실행: cd backend && uv run python scripts/export_demo.py [시작일 YYYY-MM-DD]
그다음: cd frontend && npm run build:demo
"""

import json
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "frontend" / "public" / "demo"
sys.path.insert(0, str(ROOT))

os.environ["AP_ENV"] = "dev"
os.environ["AP_DATA_DIR"] = tempfile.mkdtemp(prefix="alphapilot-demo-")
os.environ.setdefault("AP_DATA_PROVIDER", "naver")
for secret in ("ANTHROPIC_API_KEY", "KIWOOM_MOCK_APP_KEY", "KIWOOM_MOCK_SECRET_KEY", "KIWOOM_LIVE_APP_KEY", "KIWOOM_LIVE_SECRET_KEY"):
    os.environ.pop(secret, None)  # 데모 응답에 실제 연결 상태가 섞이지 않게 한다

from fastapi.testclient import TestClient  # noqa: E402

from app.api.factory import create_app, require_session  # noqa: E402
from app.api.security import SessionInfo  # noqa: E402
from app.config import Settings  # noqa: E402
from app.techniques.registry import ENTRY_KEYS  # noqa: E402

LEDGER_KINDS = ["", "fill_buy,fill_sell,protective,stop_raise", "intent,approve,reject,expire,skip",
                "decision,gate_reduce,gate_block,precheck,screen_out,cycle,regime", "engine,settings,breaker,data,broker,error"]


def key(url: str) -> str:
    """frontend/src/lib/demo.ts의 demoKey와 같은 규칙."""
    return re.sub(r"[^A-Za-z0-9-]", "_", url.removeprefix("/api/"))


def find(value, name: str, out: set) -> set:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == name and isinstance(v, (str, int)):
                out.add(str(v))
            find(v, name, out)
    elif isinstance(value, list):
        for v in value:
            find(v, name, out)
    return out


def main() -> None:
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=120)
    app = create_app(Settings(), run_scheduler=False)
    app.dependency_overrides[require_session] = lambda: SessionInfo(token_hash="demo", csrf="demo", elevated=True, expires_at="2099-01-01T00:00:00")
    saved: dict[str, object] = {}

    with TestClient(app) as client:
        def call(method: str, url: str, body: object = None) -> object:
            r = client.request(method, url, json=body)
            if r.status_code >= 400:
                raise SystemExit(f"{method} {url} -> {r.status_code} {r.text[:300]}")
            return r.json()

        def grab(url: str) -> object:
            if url not in saved:
                saved[url] = call("GET", url)
            return saved[url]

        print("일봉 갱신(몇 분 걸린다)…", flush=True)
        print(call("POST", "/api/engine/refresh-data"), flush=True)
        call("PUT", "/api/settings/engine", {"decider": "rules"})
        call("POST", "/api/settings/sim-reset", {"start": start.isoformat()})
        call("POST", "/api/engine/start")
        svc = app.state.service
        days = 0
        while (day := svc._next_sim_day()[0]) is not None:
            # 마지막 거래일은 자동 승인 없이 돌려 승인 대기 카드를 남긴다
            call("POST", "/api/engine/advance", {"days": 1, "auto_approve": day != svc.market.calendar[-1]})
            days += 1
            print(f"  {day} 처리", flush=True)
        print(f"{days}거래일 진행", flush=True)
        print("백테스트…", flush=True)
        bt = call("POST", "/api/backtests", {"start": (start - timedelta(days=365)).isoformat()})

        for url in ["/api/status", "/api/dashboard", "/api/portfolio", "/api/settings", "/api/intents/pending", "/api/backtests",
                    f"/api/backtests/{bt['id']}", "/api/auth/sessions", "/api/ledger/verify", "/api/screener", "/api/committee"]:
            grab(url)
        for t in ENTRY_KEYS:
            grab(f"/api/screener?technique={t}")
        for limit in range(100, 600, 100):
            for kinds in LEDGER_KINDS:
                grab(f"/api/ledger?limit={limit}" + (f"&kind={kinds}" if kinds else ""))
        for day in saved["/api/committee"]["days"]:
            grab(f"/api/committee?day={day}")
        for decision in sorted(find([v for k, v in saved.items() if k.startswith("/api/committee")], "id", set())):
            grab(f"/api/committee/{decision}")
        for chain in sorted(find(list(saved.values()), "chain_id", set())):
            if chain.isdigit():
                grab(f"/api/ledger/chain/{chain}")
        for code in sorted(c for c in find(list(saved.values()), "code", set()) if re.fullmatch(r"\d{6}", c)):
            grab(f"/api/stocks/{code}")
        market = app.state.service.market
        saved["/api/stocks/_all"] = [{"code": i.code, "name": i.name, "market": i.market, "sector": i.sector}
                                     for i in market.info.values() if i.code in market.stocks]

    sessions = saved["/api/auth/sessions"]
    sessions["sessions"] = []
    for row in sessions["audit"]:
        row["ip"] = ""

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for url, body in saved.items():
        (OUT / f"{key(url)}.json").write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.glob("*.json"))
    print(f"{len(saved)}개 응답, {size / 1e6:.1f}MB -> {OUT}")


if __name__ == "__main__":
    main()
