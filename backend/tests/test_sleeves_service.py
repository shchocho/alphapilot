"""바구니 서비스 통합 테스트: 샘플 데이터 + 메모리 DB + 가짜 AI."""

import asyncio
import json

import pytest
from sqlalchemy import select

from app.committee.llm import LlmError, LlmResult, LlmUsage
from app.config import Settings
from app.data.sample import SampleProvider
from app.data.universe import load_universe
from app.engine import service as service_module
from app.engine.service import EngineError, EngineService
from app.engine.settings import EngineSettings
from app.sleeves import ai as sleeve_ai
from app.sleeves import logic
from app.sleeves import service as sleeve_module
from app.sleeves.config import PlanConfig, SleeveConfig, WatchItem
from app.sleeves.service import SleeveService, plan_changes
from app.store.db import SleeveOrderRow, SleeveSignalRow, SleeveTradeRow, make_engine, make_session_factory
from tests.helpers import END, trading_days

DAYS = trading_days(8)
D1, D2 = DAYS[-3], DAYS[-2]
ETF = "069500"  # 유니버스 밖 종목(샘플 공급자는 아무 코드나 합성 봉을 만든다)

ARGUMENT = {"points": ["근거"], "strongest_evidence": "수치", "weakest_spot": "없음"}
RISK_OK = {"concerns": [], "severity": "low", "veto": False, "size": "full", "note": ""}


def chair(action: str, conviction: str = "high") -> dict:
    return {"action": action, "conviction": conviction, "thesis": "AI 근거", "key_risks": ["변동성"], "invalidation": "추세 이탈", "dissent": ""}


class FakeLlm:
    model = "claude-opus-5-5"

    def __init__(self, final: dict | None = None, risk: dict | None = None, fail: LlmError | None = None) -> None:
        self.final = final or chair("BUY_MORE")
        self.risk = risk or RISK_OK
        self.fail = fail
        self.calls: list[dict] = []

    async def complete(self, *, system, shared, task, schema, role):
        self.calls.append({"role": role, "shared": shared, "task": task, "schema": schema})
        if self.fail:
            raise self.fail
        answer = {"bull": ARGUMENT, "bear": ARGUMENT, "risk": self.risk, "chair": self.final, "branch": self.final}[role]
        return LlmResult(json.dumps(answer, ensure_ascii=False), LlmUsage(self.model, 2_000, 400))


@pytest.fixture
def sleeves(monkeypatch):
    stocks = load_universe()[:10]
    for module in (service_module, sleeve_module):
        monkeypatch.setattr(module, "load_universe", lambda: stocks)
        monkeypatch.setattr(module, "universe_map", lambda: {s.code: s for s in stocks})
    config = Settings(_env_file=None, AP_DATA_PROVIDER="sample")
    factory = make_session_factory(make_engine(None))
    svc = EngineService(config, factory, provider=SampleProvider(end=D1))
    svc.kv.save_settings(EngineSettings(decider="rules"))
    asyncio.run(svc.refresh_data())
    service = SleeveService(svc)
    service.codes = [s.code for s in stocks]
    return service


def plan(service, **over) -> PlanConfig:
    a, b = service.codes[:2]
    base = {
        "total": 1_000_000,
        "sleeves": [
            SleeveConfig(name="중장기", amount=500_000, items=[WatchItem(code=a, name="가"), WatchItem(code=b, name="나")],
                         cadence="weekly", installments=5, mode="paper", mandate="실적이 꾸준한 대형주를 길게 모은다"),
            SleeveConfig(name="ETF", amount=500_000, items=[WatchItem(code=ETF, name="KODEX 200", kind="etf")], cadence="monthly",
                         installments=10, mode="alert"),
        ],
    }
    base.update(over)
    return PlanConfig(**base)


def rows(service, table, **where):
    with service.sf() as s:
        stmt = select(table)
        for key, value in where.items():
            stmt = stmt.where(getattr(table, key) == value)
        return list(s.execute(stmt).scalars())


def advance_data(service, day):
    service.svc.provider = SampleProvider(end=day)
    asyncio.run(service.svc.refresh_data())


# ── 종목 확인·계획 저장 ──────────────────────────────────────────────────


def test_lookup_fetches_bars_for_a_code_outside_the_universe(sleeves):
    info = sleeves.lookup(ETF)
    assert info["code"] == ETF and not info["in_universe"] and info["bars"] > 100
    with pytest.raises(EngineError, match="6자리"):
        sleeves.lookup("12")


def test_save_creates_revision_books_and_deposits_only_for_paper(sleeves):
    sleeves.lookup(ETF)
    out = sleeves.save(plan(sleeves), "처음")
    assert out["rev"] == 1 and "첫 계획" in out["changes"][0]
    view = sleeves.overview()
    assert view["plan"]["rev"] == 1 and view["plan"]["allocated"] == 1_000_000
    ids = [s["id"] for s in view["sleeves"]]
    assert all(i.startswith("s") and len(i) == 7 for i in ids)
    deposits = rows(sleeves, SleeveTradeRow, kind="deposit")
    assert [d.amount for d in deposits] == [500_000]  # 알림만 바구니는 가상 장부에 돈을 넣지 않는다
    assert ETF in sleeves.svc.extra_codes()  # 다음 일봉 갱신에 바구니 종목을 더한다


def test_save_rejects_codes_without_bars(sleeves):
    with pytest.raises(EngineError, match="일봉이 없는"):
        sleeves.save(plan(sleeves))  # ETF를 확인(lookup)하지 않아 봉이 없다


# ── 심의 ────────────────────────────────────────────────────────────────


def test_first_run_judges_every_item_and_only_paper_makes_orders(sleeves):
    sleeves.lookup(ETF)
    sleeves.save(plan(sleeves))
    out = asyncio.run(sleeves.run())
    assert out["as_of"] == D1.isoformat() and len(out["sleeves"]) == 2
    signals = rows(sleeves, SleeveSignalRow)
    assert len(signals) == 3 and all(g.action in logic.ACTIONS for g in signals)
    orders = rows(sleeves, SleeveOrderRow)
    view = sleeves.overview()
    paper, alert = view["sleeves"]
    assert {o.sleeve_id for o in orders} <= {paper["id"]}
    assert alert["book"]["return_pct"] is None and alert["pending"] == []
    assert paper["book"]["installments_done"] == 1 and paper["due"] is False


def test_rerun_on_the_same_day_replaces_signals_and_restores_the_book(sleeves):
    sleeves.lookup(ETF)
    sleeves.save(plan(sleeves))
    asyncio.run(sleeves.run())
    first = {g.id for g in rows(sleeves, SleeveSignalRow)}
    nothing = asyncio.run(sleeves.run())
    assert nothing["run_id"] is None  # 차례가 아니면 돌리지 않는다
    asyncio.run(sleeves.run(force=True))
    live = rows(sleeves, SleeveSignalRow, replaced=False)
    assert len(live) == 3 and not first & {g.id for g in live}
    assert all(o.status in ("pending", "replaced") for o in rows(sleeves, SleeveOrderRow))
    view = sleeves.overview()
    assert view["sleeves"][0]["book"]["installments_done"] == 1  # 같은 날 다시 돌려도 회차는 한 번


def test_orders_fill_at_the_next_days_open(sleeves):
    sleeves.lookup(ETF)
    cfg = plan(sleeves)
    cfg.sleeves[0].decider = "rules"
    sleeves.save(cfg)
    asyncio.run(sleeves.run())
    pending = rows(sleeves, SleeveOrderRow, status="pending")
    if not pending:
        pytest.skip("샘플 데이터에서 첫 회차 매수가 나오지 않았다")
    advance_data(sleeves, D2)
    asyncio.run(sleeves.run())
    filled = rows(sleeves, SleeveOrderRow, status="filled")
    assert filled and all(o.filled_on == D2.isoformat() for o in filled)
    buys = rows(sleeves, SleeveTradeRow, kind="buy")
    view = sleeves.overview()
    paper = view["sleeves"][0]
    assert paper["book"]["positions"] and paper["book"]["cash"] == 500_000 - sum(b.amount + b.fee for b in buys)
    perf = sleeves.performance(paper["id"])
    assert perf["book"]["dates"][-1] == D2.isoformat() and "dca" in perf and "rules" in perf


def test_alert_mode_suggests_quantities_without_a_book(sleeves):
    sleeves.lookup(ETF)
    sleeves.save(plan(sleeves))
    asyncio.run(sleeves.run())
    etf = next(s for s in sleeves.overview()["sleeves"] if s["mode"] == "alert")
    signal = etf["latest"][0]
    if signal["action"] in ("BUY", "BUY_MORE"):
        assert signal["qty"] >= 0 and signal["amount"] >= 0
    assert etf["book"]["positions"] == []


# ── 판(리비전) ───────────────────────────────────────────────────────────


def test_amount_changes_deposit_or_are_refused_when_cash_is_short(sleeves):
    sleeves.lookup(ETF)
    sleeves.save(plan(sleeves))
    cur = sleeves.current()[1]
    more = cur.model_copy(deep=True)
    more.total = 1_200_000
    more.sleeves[0].amount = 700_000
    out = sleeves.save(more, "중장기 증액")
    assert out["rev"] == 2 and any("금액 50만원 → 70만원" in c for c in out["changes"])
    assert rows(sleeves, SleeveTradeRow, kind="deposit")[-1].amount == 200_000
    # 현금보다 많이 빼려 하면 거부
    with sleeves.sf() as s, s.begin():
        from app.store.db import SleeveBookRow

        row = s.get(SleeveBookRow, cur.sleeves[0].id)
        book = logic.Book.from_dict(json.loads(row.state))
        book.cash = 50_000
        book.positions[sleeves.codes[0]] = logic.Lot(10, 60_000.0, "가")
        row.state = json.dumps(book.to_dict())
    less = sleeves.current()[1].model_copy(deep=True)
    less.sleeves[0].amount = 100_000
    with pytest.raises(EngineError, match="뺄 수 없습니다"):
        sleeves.save(less)
    gone = sleeves.current()[1].model_copy(deep=True)
    gone.sleeves = gone.sleeves[1:]
    with pytest.raises(EngineError, match="가상 보유"):
        sleeves.save(gone)


def test_restore_makes_a_new_revision_with_the_old_config(sleeves):
    sleeves.lookup(ETF)
    sleeves.save(plan(sleeves), "처음")
    changed = sleeves.current()[1].model_copy(deep=True)
    changed.sleeves[0].mandate = "배당을 꾸준히 주는 종목만 모은다"
    changed.sleeves[0].cadence = "monthly"
    out = sleeves.save(changed, "지침 바꿈")
    assert any("운용 지침 수정" in c for c in out["changes"]) and any("매주 → 매월" in c for c in out["changes"])
    back = sleeves.restore(1)
    assert back["rev"] == 3
    revs = sleeves.revisions()
    assert [r["rev"] for r in revs] == [3, 2, 1]
    assert revs[0]["current"] and revs[0]["restored_from"] == 1 and revs[0]["note"] == "r1로 되돌림"
    assert revs[0]["config"]["sleeves"][0]["mandate"] == revs[2]["config"]["sleeves"][0]["mandate"]
    with pytest.raises(EngineError, match="지금 쓰는 판"):
        sleeves.restore(3)


def test_plan_changes_lists_added_and_removed_sleeves(sleeves):
    old = plan(sleeves)
    old.sleeves[0].id, old.sleeves[1].id = "s000001", "s000002"
    new = old.model_copy(deep=True)
    new.sleeves = new.sleeves[:1]
    new.sleeves[0].items = new.sleeves[0].items[:1]
    text = plan_changes(old, new)
    assert "'ETF' 바구니 뺌" in text and any("종목 뺌: 나" in t for t in text)


# ── AI ──────────────────────────────────────────────────────────────────


def ai_plan(service, decider="ai", depth="light") -> PlanConfig:
    a = service.codes[0]
    return PlanConfig(total=500_000, sleeves=[SleeveConfig(name="AI", amount=500_000, items=[WatchItem(code=a, name="가")],
                                                           decider=decider, depth=depth, cadence="daily", installments=5)])


def test_ai_sleeve_uses_the_mandate_and_the_chairs_answer(sleeves):
    fake = FakeLlm(chair("BUY_MORE"))
    sleeves.svc._llm_factory = lambda st: fake
    sleeves.save(ai_plan(sleeves))
    est = sleeves.estimate()
    assert est["calls"] == 1 and est["est_usd"] > 0
    asyncio.run(sleeves.run())
    g = rows(sleeves, SleeveSignalRow)[0]
    assert g.action == "BUY_MORE" and g.source == "ai" and g.transcript
    assert "운용 지침" in fake.calls[0]["shared"]
    assert fake.calls[0]["schema"]["properties"]["action"]["enum"] == ["BUY_MORE", "BUY", "WAIT"]  # 보유가 없으면 팔 수 없다


def test_ai_failure_means_wait_and_review(sleeves):
    sleeves.svc._llm_factory = lambda st: FakeLlm(fail=LlmError("timeout", "시간 초과"))
    sleeves.save(ai_plan(sleeves, depth="standard"))
    asyncio.run(sleeves.run())
    g = rows(sleeves, SleeveSignalRow)[0]
    assert g.action == "WAIT" and g.status == "review" and g.qty == 0
    assert rows(sleeves, SleeveOrderRow) == []


def test_ai_without_a_key_waits_instead_of_buying(sleeves):
    sleeves.save(ai_plan(sleeves))
    asyncio.run(sleeves.run())  # 키가 없다: AnthropicLlm이 not_configured
    g = rows(sleeves, SleeveSignalRow)[0]
    assert g.action == "WAIT" and g.status == "review"


def test_risk_veto_and_size_cut_override_the_chair():
    market_ctx = _ctx()
    vetoed, _ = asyncio.run(sleeve_ai.deliberate_sleeve(market_ctx, FakeLlm(chair("BUY"), risk={**RISK_OK, "veto": True, "note": "과열"}),
                                                        _Budget(), depth="standard"))
    assert vetoed.action == "WAIT" and "거부권" in vetoed.thesis
    cut, _ = asyncio.run(sleeve_ai.deliberate_sleeve(market_ctx, FakeLlm(chair("BUY_MORE"), risk={**RISK_OK, "size": "half"}),
                                                     _Budget(), depth="standard"))
    assert cut.action == "BUY"


def test_second_opinion_needs_conviction_to_add_risk():
    ctx = _ctx(rules="WAIT")
    low, t = asyncio.run(sleeve_ai.sleeve_second_opinion(ctx, "문턱 근처", FakeLlm(chair("BUY", "low")), _Budget()))
    assert low.action == "WAIT" and t.branch["adopted"] is False
    high, t = asyncio.run(sleeve_ai.sleeve_second_opinion(ctx, "문턱 근처", FakeLlm(chair("BUY", "high")), _Budget()))
    assert high.action == "BUY" and t.branch["adopted"] is True
    failed, t = asyncio.run(sleeve_ai.sleeve_second_opinion(ctx, "문턱 근처", FakeLlm(fail=LlmError("api", "x")), _Budget()))
    assert failed.action == "WAIT" and failed.source == "rules"


class _Budget:
    def check(self) -> None:
        pass

    def record(self, role, usage, ok, error) -> None:
        pass


def _ctx(rules: str = "BUY") -> sleeve_ai.SleeveContext:
    import numpy as np

    from app.core.models import StockInfo
    from app.regime.regime import compute_regime
    from tests.helpers import make_bars, make_market

    market = make_market({"A00001": make_bars(10_000 * (1.002 ** np.arange(300)))})
    regime = compute_regime(market)[-1]
    a = logic.assess(market, "A00001", END, regime)
    assert a is not None
    return sleeve_ai.SleeveContext(sleeve_name="중장기", mandate="길게", info=StockInfo("A00001", "가", "KOSPI", "테스트"), kind="stock",
                                   as_of=END, close=a.close, techniques=a.results, seats=a.seats, score=a.score, regime=regime,
                                   rules_action=rules, base_amount=50_000)  # type: ignore[arg-type]


# ── 미리 보기 ────────────────────────────────────────────────────────────


def test_preview_runs_both_baselines_for_a_draft_plan(sleeves):
    sleeves.lookup(ETF)
    out = asyncio.run(sleeves.preview(plan(sleeves), trading_days(200, D1)[0]))
    assert len(out["sleeves"]) == 2
    for sl in out["sleeves"]:
        assert sl["dca"]["summary"]["buys"] >= 1
        assert {"return_pct", "mdd_pct"} <= set(sl["rules"]["summary"])
    assert "AI 판단은" in out["note"]
