"""하루 체결 재현(가상 계좌). 시뮬레이션과 백테스트가 같은 함수를 쓴다.

일봉(시·고·저·종)만으로 하루를 재현하므로 장중 순서를 알 수 없는 경우엔 **불리한 쪽**을 택한다.
- 시가가 손절가 아래면 시가에 체결(갭 손실 반영)
- 같은 날 손절과 익절이 모두 닿으면 손절 먼저
- 돌파 진입한 날의 손절은 종가가 손절가 이하일 때만 종가에 체결(저가가 진입 전일 수 있으므로)
- 매수는 호가단위 올림 + 슬리피지, 매도는 내림 − 슬리피지
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.market_rules import CostModel, round_down_tick, round_up_tick
from app.core.models import DayBar, Fill, Intent, Portfolio, Position
from app.risk.exits import check_protective, stop_reason, trailed_stop

GAP_GUARD = 0.05  # 계획에 추격 한도가 없을 때: 시가가 예상가보다 5% 넘게 높으면 사지 않는다


@dataclass(slots=True)
class DayResult:
    fills: list[Fill] = field(default_factory=list)
    skipped: list[tuple[Intent, str]] = field(default_factory=list)  # (계획, 미체결 사유)


def _sell(portfolio: Portfolio, pos: Position, raw_price: float, day: date, reason: str, costs: CostModel,
          intent_id: str | None = None) -> Fill:
    price = costs.sell_fill_price(raw_price)
    amount = price * pos.qty
    fee, tax = costs.fees("sell", amount)
    pnl = int(round(amount - fee - tax - pos.avg_price * pos.qty))
    cost_basis = pos.avg_price * pos.qty
    # 보유 거래일: 산 날 판 경우 0, 다음 거래일에 팔면 1. days_held는 산 다음 날부터 장 마감마다 1씩 늘므로 파는 날 몫을 더한다.
    hold_days = pos.days_held + (1 if day > pos.opened_on else 0)
    fill = Fill(
        day=day, code=pos.code, name=pos.name, side="sell", qty=pos.qty, price=price, fee=fee, tax=tax,
        reason=reason, chain_id=pos.chain_id, intent_id=intent_id, technique=pos.technique, pnl=pnl,
        pnl_pct=(pnl / cost_basis) if cost_basis > 0 else 0.0, hold_days=hold_days,
    )
    portfolio.cash += amount - fee - tax
    del portfolio.positions[pos.code]
    return fill


def _buy(portfolio: Portfolio, intent: Intent, raw_price: float, day: date, reason: str, costs: CostModel,
         stop: int) -> tuple[Fill | None, str]:
    """매수 체결. 현금이 모자라면 살 수 있는 만큼만 산다. 반환: (체결, 미체결 사유)."""
    price = costs.buy_fill_price(raw_price)
    if price <= stop:
        return None, "체결가가 손절가 이하입니다"
    qty = intent.qty
    per_share = price * (1 + costs.commission_rate)
    affordable = int(portfolio.cash // per_share)
    if affordable < qty:
        qty = affordable
    if qty < 1:
        return None, "현금이 모자랍니다"
    amount = price * qty
    fee, _ = costs.fees("buy", amount)
    portfolio.cash -= amount + fee
    avg = (amount + fee) / qty  # 수수료를 포함한 취득 단가
    portfolio.positions[intent.code] = Position(
        code=intent.code, name=intent.name, qty=qty, avg_price=avg, opened_on=day, technique=intent.technique,
        stop=stop, entry_risk=max(0.0, avg - stop), sector=intent.sector, target=intent.target,
        trail_mult=intent.trail_mult, highest_close=float(price), exit_on_next_open=intent.exit_on_next_open,
        max_hold_days=intent.max_hold_days, exit_rule=intent.exit_rule, chain_id=intent.chain_id,
    )
    fill = Fill(day=day, code=intent.code, name=intent.name, side="buy", qty=qty, price=price, fee=fee, tax=0,
                reason=reason, chain_id=intent.chain_id, intent_id=intent.id, technique=intent.technique)
    return fill, ""


def execute_day(day: date, portfolio: Portfolio, intents: list[Intent], bars: dict[str, DayBar], costs: CostModel) -> DayResult:
    """승인된 주문 계획과 보유 종목을 그날 봉으로 체결한다. portfolio와 intents의 상태가 바뀐다."""
    result = DayResult()
    approved = [it for it in intents if it.status == "approved" and it.trade_date == day]
    bought_today: set[str] = set()
    triggered_today: set[str] = set()

    def skip(intent: Intent, why: str) -> None:
        intent.status = "skipped"
        intent.note = why
        result.skipped.append((intent, why))

    # 1) 시가 매도: 다음 날 시가 청산 예약(변동성 돌파·보유 기간 만료)과 위원회 매도
    for code in list(portfolio.positions):
        pos = portfolio.positions[code]
        bar = bars.get(code)
        if pos.exit_on_next_open and pos.opened_on < day and bar is not None and bar.volume > 0:
            reason = "time_exit" if (pos.max_hold_days is not None and pos.days_held >= pos.max_hold_days) else "next_open_exit"
            result.fills.append(_sell(portfolio, pos, bar.open, day, reason, costs))
    for intent in approved:
        if intent.side != "sell":
            continue
        pos = portfolio.positions.get(intent.code)
        bar = bars.get(intent.code)
        if pos is None:
            skip(intent, "이미 보유하고 있지 않습니다")
        elif bar is None or bar.volume <= 0:
            skip(intent, "거래가 없는 날입니다")
        else:
            reason = intent.source if intent.source in ("rule_exit", "liquidate", "manual") else "committee_sell"
            result.fills.append(_sell(portfolio, pos, bar.open, day, reason, costs, intent.id))
            intent.status = "filled"

    # 2) 시가 매수
    for intent in approved:
        if intent.side != "buy" or intent.entry_type != "open":
            continue
        bar = bars.get(intent.code)
        if bar is None or bar.volume <= 0:
            skip(intent, "거래가 없는 날입니다")
            continue
        if intent.code in portfolio.positions:
            skip(intent, "이미 보유 중입니다")
            continue
        limit = intent.chase_limit if intent.chase_limit is not None else intent.est_price * (1 + GAP_GUARD)
        if limit and bar.open > limit:
            skip(intent, f"시가 {bar.open:,.0f}원이 추격 한도 {limit:,.0f}원을 넘었습니다")
            continue
        stop = intent.stop or 0
        fill, why = _buy(portfolio, intent, bar.open, day, "entry_open", costs, stop)
        if fill is None:
            skip(intent, why)
            continue
        intent.status = "filled"
        result.fills.append(fill)
        bought_today.add(intent.code)

    # 3) 장중 보호 청산 (시가에 산 종목 포함)
    for code in list(portfolio.positions):
        pos = portfolio.positions[code]
        bar = bars.get(code)
        if bar is None or bar.volume <= 0:
            continue
        if code in bought_today:
            # 시가 체결 뒤의 움직임만 본다: 시가는 이미 지났으므로 저가·고가만 확인
            if bar.low <= pos.stop:
                result.fills.append(_sell(portfolio, pos, float(pos.stop), day, stop_reason(pos), costs))
            elif pos.target is not None and bar.high >= pos.target:
                result.fills.append(_sell(portfolio, pos, float(pos.target), day, "target", costs))
            continue
        hit = check_protective(pos, bar.open, bar.high, bar.low)
        if hit is not None:
            reason, raw = hit
            result.fills.append(_sell(portfolio, pos, raw, day, reason, costs))

    # 4) 장중 돌파 진입
    for intent in approved:
        if intent.side != "buy" or intent.entry_type not in ("trigger", "vb"):
            continue
        bar = bars.get(intent.code)
        if bar is None or bar.volume <= 0:
            skip(intent, "거래가 없는 날입니다")
            continue
        if intent.code in portfolio.positions:
            skip(intent, "이미 보유 중입니다")
            continue
        if intent.entry_type == "vb":
            trigger = round_up_tick(bar.open + (intent.vb_k or 0.5) * (intent.vb_range or 0.0))
            stop = round_down_tick(trigger - (intent.vb_range or 0.0))
            chase = None
            reason = "entry_vb"
        else:
            trigger = intent.trigger or 0
            stop = intent.stop or 0
            chase = intent.chase_limit
            reason = "entry_trigger"
        if trigger <= 0:
            skip(intent, "돌파 기준가가 없습니다")
            continue
        if bar.open >= trigger:
            if chase is not None and bar.open > chase:
                skip(intent, f"시가 {bar.open:,.0f}원이 추격 한도 {chase:,.0f}원을 넘었습니다")
                continue
            raw = bar.open
        elif bar.high >= trigger:
            raw = float(trigger)
        else:
            skip(intent, f"돌파 기준가 {trigger:,}원에 닿지 않았습니다")
            continue
        fill, why = _buy(portfolio, intent, raw, day, reason, costs, stop)
        if fill is None:
            skip(intent, why)
            continue
        intent.status = "filled"
        result.fills.append(fill)
        triggered_today.add(intent.code)

    # 5) 돌파 진입한 날의 손절: 종가가 손절가 이하일 때만
    for code in triggered_today:
        pos = portfolio.positions.get(code)
        bar = bars.get(code)
        if pos is not None and bar is not None and bar.close <= pos.stop:
            result.fills.append(_sell(portfolio, pos, bar.close, day, stop_reason(pos), costs))
    return result


def end_of_day(day: date, portfolio: Portfolio, bars: dict[str, DayBar]) -> list[tuple[str, int, int]]:
    """장 마감 처리: 최고 종가·추적 손절·보유 일수·기간 만료 예약. 반환: 손절가가 오른 종목 [(코드, 이전, 이후)]."""
    raised: list[tuple[str, int, int]] = []
    for code, pos in portfolio.positions.items():
        bar = bars.get(code)
        if bar is None:
            continue
        new_stop = trailed_stop(pos, bar.close, bar.atr)
        pos.highest_close = max(pos.highest_close, bar.close)
        if new_stop > pos.stop:
            raised.append((code, pos.stop, new_stop))
            pos.stop = new_stop
        if pos.opened_on < day:
            pos.days_held += 1
        if pos.max_hold_days is not None and pos.days_held >= pos.max_hold_days:
            pos.exit_on_next_open = True
    return raised
