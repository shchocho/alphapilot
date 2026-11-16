from datetime import date

import pytest
from sqlalchemy import update

from app.core.market_rules import CostModel
from app.core.models import DayBar, Intent, Portfolio, Position
from app.engine.sim import end_of_day, execute_day
from app.journal.ledger import GENESIS_HASH, Ledger, row_to_dict
from app.store.db import LedgerRow, make_engine, make_session_factory

D1, D2, D3 = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)
NO_COST = CostModel(commission_rate=0.0, sell_tax_rate=0.0, slippage_rate=0.0)
COSTS = CostModel(commission_rate=0.00015, sell_tax_rate=0.0020, slippage_rate=0.0005)


# ── 원장 ─────────────────────────────────────────────────────────────────────

def make_ledger():
    factory = make_session_factory(make_engine(None))
    return Ledger(factory), factory


def test_ledger_chains_rows_by_hash():
    ledger, _ = make_ledger()
    first = ledger.append(env="sim", kind="engine", summary="엔진 시작")
    second = ledger.append(env="sim", kind="fill_buy", summary="시가 매수", code="005930", name="삼성전자", qty=3, amount=627_000, cash_after=9_373_000)
    rows = ledger.rows(newest_first=False)
    assert (first, second) == (1, 2)
    assert rows[0].prev_hash == GENESIS_HASH
    assert rows[1].prev_hash == rows[0].hash
    assert ledger.verify() == (True, None)


def test_ledger_detects_tampering_with_an_old_row():
    ledger, factory = make_ledger()
    for i in range(4):
        ledger.append(env="sim", kind="fill_buy", summary=f"매수 {i}", amount=1_000 * (i + 1))
    with factory() as s, s.begin():
        s.execute(update(LedgerRow).where(LedgerRow.seq == 2).values(amount=999_999))
    assert ledger.verify() == (False, 2)


def test_ledger_detects_a_deleted_row():
    ledger, factory = make_ledger()
    for i in range(3):
        ledger.append(env="sim", kind="skip", summary=f"탈락 {i}")
    with factory() as s, s.begin():
        s.delete(s.get(LedgerRow, 2))
    assert ledger.verify() == (False, 3)


def test_ledger_filters_by_env_kind_and_sequence():
    ledger, _ = make_ledger()
    ledger.append(env="sim", kind="fill_buy", summary="a", chain_id="c1")
    ledger.append(env="mock", kind="fill_buy", summary="b")
    ledger.append(env="sim", kind="gate_block", summary="c", chain_id="c1")
    assert [r.summary for r in ledger.rows(env="sim")] == ["c", "a"]
    assert [r.summary for r in ledger.rows(env="sim", kinds=["gate_block"])] == ["c"]
    assert [r.summary for r in ledger.rows(after_seq=1, newest_first=False)] == ["b", "c"]
    assert [r.summary for r in ledger.rows(chain_id="c1", newest_first=False)] == ["a", "c"]
    assert ledger.last_seq("mock") == 2


def test_ledger_exports_csv_with_korean_headers_and_dict_rows():
    ledger, _ = make_ledger()
    ledger.append(env="sim", kind="fill_sell", summary="손절", code="000660", name="SK하이닉스", qty=2, amount=1_100_000, payload={"pnl": -30_000})
    csv_text = ledger.to_csv()
    assert csv_text.splitlines()[0].startswith("거래번호,시각,환경")
    assert "매도 체결" in csv_text
    as_dict = row_to_dict(ledger.rows()[0])
    assert as_dict["kind_label"] == "매도 체결"
    assert as_dict["payload"] == {"pnl": -30_000}


# ── 가상 체결 ─────────────────────────────────────────────────────────────────

def bar(o, h, l, c, v=1_000_000, atr=1_000.0, prev=None):  # noqa: E741
    return DayBar(open=o, high=h, low=l, close=c, volume=v, prev_close=prev or o, atr=atr)


def buy_intent(code="000001", qty=10, day=D1, entry_type="open", **kw) -> Intent:
    base = dict(id=f"i-{code}", chain_id=f"c-{code}", created_on=date(2026, 11, 9), trade_date=day, code=code,
                name=f"종목{code}", side="buy", qty=qty, entry_type=entry_type, status="approved", technique="vcp",
                est_price=50_000.0, stop=47_000, sector="반도체")
    base.update(kw)
    return Intent(**base)


def held(code="000001", qty=10, avg=50_000.0, stop=47_000, opened=date(2026, 11, 5), **kw) -> Position:
    return Position(code=code, name=f"종목{code}", qty=qty, avg_price=avg, opened_on=opened, technique="vcp",
                    stop=stop, entry_risk=avg - stop, highest_close=avg, chain_id=f"c-{code}", **kw)


def test_open_buy_fills_at_the_open_and_takes_cash():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent()
    result = execute_day(D1, pf, [intent], {"000001": bar(50_000, 51_000, 49_500, 50_500)}, NO_COST)
    fill = result.fills[0]
    assert (fill.side, fill.qty, fill.price, fill.reason) == ("buy", 10, 50_000, "entry_open")
    assert pf.cash == 500_000
    assert pf.positions["000001"].stop == 47_000
    assert intent.status == "filled"


def test_buy_price_includes_slippage_rounded_up_and_fee_is_in_cost_basis():
    pf = Portfolio(cash=1_000_000)
    execute_day(D1, pf, [buy_intent()], {"000001": bar(50_000, 51_000, 49_500, 50_500)}, COSTS)
    pos = pf.positions["000001"]
    assert pos.avg_price > 50_100  # 50,025 → 100원 단위 올림 50,100 + 수수료
    assert pf.cash == 1_000_000 - 501_000 - 75


def test_open_buy_is_skipped_when_gap_exceeds_chase_limit():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent(chase_limit=51_000)
    result = execute_day(D1, pf, [intent], {"000001": bar(52_000, 53_000, 51_500, 52_500)}, NO_COST)
    assert not result.fills
    assert intent.status == "skipped"
    assert "추격 한도" in result.skipped[0][1]
    assert pf.cash == 1_000_000


def test_open_buy_is_skipped_when_open_is_at_or_below_stop():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent()
    execute_day(D1, pf, [intent], {"000001": bar(46_900, 47_500, 46_000, 47_000)}, NO_COST)
    assert intent.status == "skipped"
    assert not pf.positions


def test_buy_quantity_shrinks_to_available_cash():
    pf = Portfolio(cash=260_000)
    execute_day(D1, pf, [buy_intent(qty=10)], {"000001": bar(50_000, 51_000, 49_500, 50_500)}, NO_COST)
    assert pf.positions["000001"].qty == 5
    assert pf.cash == 10_000


def test_no_fill_on_a_halted_day():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent()
    execute_day(D1, pf, [intent], {"000001": bar(50_000, 50_000, 50_000, 50_000, v=0)}, NO_COST)
    assert intent.status == "skipped"


def test_only_approved_intents_for_today_are_executed():
    pf = Portfolio(cash=2_000_000)
    pending = buy_intent(code="000002", status="pending_approval")
    tomorrow = buy_intent(code="000003", day=D2)
    bars = {c: bar(50_000, 51_000, 49_500, 50_500) for c in ("000002", "000003")}
    result = execute_day(D1, pf, [pending, tomorrow], bars, NO_COST)
    assert not result.fills
    assert pending.status == "pending_approval"


def test_stop_is_hit_on_the_entry_day_after_an_open_fill():
    pf = Portfolio(cash=1_000_000)
    result = execute_day(D1, pf, [buy_intent()], {"000001": bar(50_000, 50_500, 46_500, 47_500)}, NO_COST)
    assert [f.reason for f in result.fills] == ["entry_open", "stop"]
    assert result.fills[1].price == 47_000
    assert result.fills[1].pnl == -30_000
    assert not pf.positions


def test_gap_down_stop_fills_at_open_not_at_stop_price():
    pf = Portfolio(cash=0, positions={"000001": held()})
    result = execute_day(D1, pf, [], {"000001": bar(45_000, 46_000, 44_000, 45_500)}, NO_COST)
    fill = result.fills[0]
    assert (fill.reason, fill.price, fill.pnl) == ("stop", 45_000, -50_000)
    assert pf.cash == 450_000


def test_target_exit_and_sell_costs():
    pf = Portfolio(cash=0, positions={"000001": held(target=56_000)})
    result = execute_day(D1, pf, [], {"000001": bar(52_000, 57_000, 51_500, 56_500)}, COSTS)
    fill = result.fills[0]
    assert fill.reason == "target"
    assert fill.price == 55_900  # 56,000 − 슬리피지 → 100원 단위 내림
    assert fill.tax == round(559_000 * 0.0020)
    assert fill.pnl == 559_000 - fill.fee - fill.tax - 500_000


def test_trigger_entry_fills_at_trigger_when_touched_intraday():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent(entry_type="trigger", trigger=50_500, chase_limit=51_500, stop=47_500)
    result = execute_day(D1, pf, [intent], {"000001": bar(50_000, 51_000, 49_800, 50_800)}, NO_COST)
    assert (result.fills[0].reason, result.fills[0].price) == ("entry_trigger", 50_500)


def test_trigger_entry_fills_at_open_on_a_small_gap_and_skips_a_big_gap():
    small = buy_intent(entry_type="trigger", trigger=50_500, chase_limit=51_500, stop=47_500)
    pf = Portfolio(cash=1_000_000)
    result = execute_day(D1, pf, [small], {"000001": bar(51_000, 52_000, 50_800, 51_500)}, NO_COST)
    assert result.fills[0].price == 51_000

    big = buy_intent(entry_type="trigger", trigger=50_500, chase_limit=51_500, stop=47_500)
    pf = Portfolio(cash=1_000_000)
    result = execute_day(D1, pf, [big], {"000001": bar(52_000, 53_000, 51_800, 52_500)}, NO_COST)
    assert not result.fills and big.status == "skipped"


def test_trigger_entry_is_skipped_when_price_never_reaches_it():
    intent = buy_intent(entry_type="trigger", trigger=50_500, chase_limit=51_500, stop=47_500)
    result = execute_day(D1, Portfolio(cash=1_000_000), [intent], {"000001": bar(50_000, 50_400, 49_500, 50_200)}, NO_COST)
    assert not result.fills
    assert "닿지 않았습니다" in result.skipped[0][1]


def test_same_day_stop_after_trigger_entry_only_if_close_is_below_stop():
    survives = buy_intent(entry_type="trigger", trigger=50_500, chase_limit=51_500, stop=49_000)
    pf = Portfolio(cash=1_000_000)
    execute_day(D1, pf, [survives], {"000001": bar(50_000, 51_000, 48_500, 50_000)}, NO_COST)
    assert "000001" in pf.positions  # 저가가 손절 아래였지만 돌파 전일 수 있다

    stopped = buy_intent(entry_type="trigger", trigger=50_500, chase_limit=51_500, stop=49_000)
    pf = Portfolio(cash=1_000_000)
    result = execute_day(D1, pf, [stopped], {"000001": bar(50_000, 51_000, 48_500, 48_800)}, NO_COST)
    assert [f.reason for f in result.fills] == ["entry_trigger", "stop"]
    assert result.fills[1].price == 48_800


def test_volatility_breakout_computes_trigger_from_todays_open():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent(entry_type="vb", vb_k=0.5, vb_range=2_000.0, stop=1, exit_on_next_open=True, trail_mult=None)
    result = execute_day(D1, pf, [intent], {"000001": bar(50_000, 51_500, 49_800, 51_200)}, NO_COST)
    assert (result.fills[0].reason, result.fills[0].price) == ("entry_vb", 51_000)
    assert pf.positions["000001"].stop == 49_000  # 목표가 − 전일 범위


def test_volatility_breakout_position_is_sold_at_next_open():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent(entry_type="vb", vb_k=0.5, vb_range=2_000.0, stop=1, exit_on_next_open=True, trail_mult=None)
    execute_day(D1, pf, [intent], {"000001": bar(50_000, 51_500, 49_800, 51_200)}, NO_COST)
    end_of_day(D1, pf, {"000001": bar(50_000, 51_500, 49_800, 51_200)})
    result = execute_day(D2, pf, [], {"000001": bar(51_600, 52_000, 51_000, 51_800)}, NO_COST)
    assert (result.fills[0].reason, result.fills[0].price) == ("next_open_exit", 51_600)
    assert result.fills[0].pnl == 6_000
    assert result.fills[0].hold_days == 1  # 산 날 다음 거래일에 팔았으므로 1거래일 보유
    assert not pf.positions


def test_committee_sell_fills_at_open_and_frees_cash_for_a_buy():
    pf = Portfolio(cash=0, positions={"000001": held(qty=10)})
    sell = buy_intent(code="000001", side="sell", id="s1", source="committee")
    buy = buy_intent(code="000002", qty=9)
    bars = {"000001": bar(52_000, 53_000, 51_000, 52_500), "000002": bar(50_000, 51_000, 49_500, 50_500)}
    result = execute_day(D1, pf, [buy, sell], bars, NO_COST)
    assert [f.reason for f in result.fills] == ["committee_sell", "entry_open"]
    assert pf.cash == 520_000 - 450_000


def test_sell_intent_for_a_position_already_gone_is_skipped():
    sell = buy_intent(code="000001", side="sell", id="s1")
    result = execute_day(D1, Portfolio(cash=0), [sell], {"000001": bar(52_000, 53_000, 51_000, 52_500)}, NO_COST)
    assert sell.status == "skipped" and not result.fills


def test_end_of_day_raises_trailing_stop_and_counts_days():
    pf = Portfolio(cash=0, positions={"000001": held(trail_mult=2.0, opened=D1)})
    raised = end_of_day(D2, pf, {"000001": bar(53_000, 56_000, 52_500, 55_000, atr=1_500.0)})
    pos = pf.positions["000001"]
    assert raised == [("000001", 47_000, 52_000)]
    assert pos.highest_close == 55_000
    assert pos.days_held == 1


def test_time_exit_is_scheduled_after_max_hold_days():
    pf = Portfolio(cash=0, positions={"000001": held(max_hold_days=2, opened=D1, trail_mult=None)})
    b = {"000001": bar(50_000, 50_500, 49_500, 50_200)}
    end_of_day(D2, pf, b)
    assert not pf.positions["000001"].exit_on_next_open
    end_of_day(D3, pf, b)
    assert pf.positions["000001"].exit_on_next_open
    result = execute_day(date(2026, 11, 13), pf, [], b, NO_COST)
    assert result.fills[0].reason == "time_exit"
    assert result.fills[0].hold_days == 3  # 11/10에 사서 11/13에 팔았다: 3거래일


def test_portfolio_equity_and_exposure():
    pf = Portfolio(cash=500_000, positions={"000001": held(qty=10)})
    assert pf.equity({"000001": 55_000.0}) == pytest.approx(1_050_000)
    assert pf.exposure({"000001": 50_000.0}) == pytest.approx(0.5)


def test_same_day_stop_reports_zero_hold_days():
    pf = Portfolio(cash=1_000_000)
    intent = buy_intent(stop=49_000)
    result = execute_day(D1, pf, [intent], {"000001": bar(50_000, 50_500, 48_500, 48_800)}, NO_COST)
    sells = [f for f in result.fills if f.side == "sell"]
    assert sells and sells[0].reason == "stop"
    assert sells[0].hold_days == 0  # 산 날 바로 손절: 보유 0거래일
