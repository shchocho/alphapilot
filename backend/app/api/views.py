"""화면용 읽기 모델. 엔진 상태를 화면이 바로 쓸 수 있는 형태로 묶는다(쓰기 없음)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import func, select

from app.broker.kiwoom.client import BASE_URL as KIWOOM_BASE_URL
from app.committee.deliberation import DEPTH_LABELS
from app.committee.llm import MODEL_LABELS, SELECTABLE_MODELS
from app.committee.seats import SEAT_LABELS, blend, build_seats
from app.core.models import CONVICTION_LABEL
from app.engine import repo
from app.engine.service import FILL_SUMMARY, EngineError, EngineService
from app.engine.settings import AUTOMATION_LABELS, ENV_LABELS
from app.journal.ledger import KIND_LABELS, row_to_dict
from app.store.db import AiUsageRow, BacktestRow, DecisionRow, EquityRow, IntentRow, TradeRow
from app.techniques import registry

SPARK_BARS = 40
PASSBOOK_ROWS = 40  # 관제 화면 통장정리에 보내는 최소 줄 수(새 줄이 적으면 확인한 줄로 채운다)
CHART_BARS = 260


def _clean(value: Any) -> Any:
    """NaN·무한대를 None으로 바꾼다(JSON 직렬화용)."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _as_of(svc: EngineService) -> date:
    """화면의 기준일: 시뮬레이션이 처리한 마지막 거래일, 없으면 최신 일봉 날짜."""
    if svc.market is None:
        raise EngineError("일봉 데이터가 없습니다. 설정에서 데이터를 갱신하세요")
    sim_day = svc.sim_day()
    return date.fromisoformat(sim_day) if sim_day else svc.market.last_day()


def _positions(svc: EngineService, env: str, initial_cash: int, as_of: date) -> tuple[list[dict[str, Any]], float, int]:
    assert svc.market is not None
    prices = svc.market.prices_on(as_of)
    with svc.sf() as s, s.begin():
        portfolio = repo.load_portfolio(s, env, initial_cash)
    equity = portfolio.equity(prices)
    rows = []
    for code, pos in portfolio.positions.items():
        price = prices.get(code, pos.avg_price)
        value = pos.qty * price
        rows.append({
            "code": code, "name": pos.name, "sector": pos.sector, "qty": pos.qty, "avg_price": round(pos.avg_price),
            "price": round(price), "value": round(value), "pnl": round(pos.unrealized(price)),
            "pnl_pct": price / pos.avg_price - 1 if pos.avg_price else 0.0, "weight": value / equity if equity else 0.0,
            "technique": pos.technique, "technique_name": _technique_name(pos.technique), "opened_on": pos.opened_on.isoformat(),
            "days_held": pos.days_held, "stop": pos.stop, "target": pos.target,
            "stop_distance": (price - pos.stop) / price if price else None,
            "target_distance": (pos.target - price) / price if (pos.target and price) else None,
            "trailing": pos.trail_mult is not None, "exit_on_next_open": pos.exit_on_next_open, "exit_rule": pos.exit_rule,
            "open_risk": round(pos.open_risk(price)), "chain_id": pos.chain_id,
        })
    rows.sort(key=lambda r: -r["value"])
    return rows, equity, portfolio.cash


def _technique_name(key: str) -> str:
    return next((m.name for m in registry.metas() if m.key == key), key)


def _decision_brief(svc: EngineService, decision_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not decision_ids:
        return {}
    with svc.sf() as s:
        rows = s.execute(select(DecisionRow).where(DecisionRow.id.in_(decision_ids))).scalars().all()
    return {r.id: repo.decision_to_dict(r, full=False) for r in rows}


def pending_cards(svc: EngineService) -> list[dict[str, Any]]:
    """승인 카드: 무엇을·왜·위험·기한."""
    st = svc.settings()
    with svc.sf() as s:
        rows = repo.intents_for(s, st.env, statuses=("pending_approval",))
        cards = [repo.intent_to_dict(r) for r in rows]
    briefs = _decision_brief(svc, [c["decision_id"] for c in cards if c.get("decision_id")])
    prices = svc.market.prices_on(_as_of(svc)) if svc.market is not None else {}
    for card in cards:
        brief = briefs.get(card.get("decision_id") or "", {})
        price = prices.get(card["code"])
        est = card.get("est_price") or 0
        card.update({
            "technique_name": _technique_name(card.get("technique", "")),
            "conviction_label": CONVICTION_LABEL.get(card.get("conviction") or "", ""),
            "thesis": brief.get("thesis", card.get("reason", "")), "votes": brief.get("votes", {}),
            "gate_summary": brief.get("gate_summary"), "decision_source": brief.get("source"),
            "amount": round(card["qty"] * est), "last_price": price,
            "risk_pct": (est - card["stop"]) / est if (card.get("stop") and est) else None,
        })
    return cards


def dashboard(svc: EngineService) -> dict[str, Any]:
    st = svc.settings()
    limits = svc.limits()
    status = svc.status()
    as_of = _as_of(svc)
    positions, equity, cash = _positions(svc, st.env, st.sim_initial_cash, as_of)
    with svc.sf() as s:
        curve = s.execute(select(EquityRow).where(EquityRow.env == st.env).order_by(EquityRow.d)).scalars().all()
        next_rows = repo.intents_for(s, st.env, statuses=("approved",))
        plans = [repo.intent_to_dict(r) for r in next_rows if r.trade_date > as_of.isoformat()]
        realized = s.execute(select(func.coalesce(func.sum(TradeRow.pnl), 0)).where(TradeRow.env == st.env, TradeRow.side == "sell")).scalar_one()
    initial = st.sim_initial_cash if st.env == "sim" else (curve[0].equity if curve else equity)
    prev_equity = curve[-2].equity if len(curve) >= 2 else initial
    peak = max([c.equity for c in curve] + [equity])
    heat = sum(p["open_risk"] for p in positions)
    epoch = svc.ledger_epoch(st.env)
    seen = max(status["ledger_seen_seq"], epoch)
    fresh = svc.ledger.rows(env=st.env, after_seq=seen, limit=60)
    # 확인한 줄도 넉넉히 함께 보낸다: 화면이 '걸러진 후보' 줄을 접으면 남는 줄이 적어지기 때문이다.
    older = svc.ledger.rows(env=st.env, after_seq=epoch, before_seq=seen + 1, limit=PASSBOOK_ROWS - len(fresh)) if len(fresh) < PASSBOOK_ROWS else []
    counts: dict[str, int] = defaultdict(int)
    for row in fresh:
        counts[row.kind] += 1
    regime = None
    if svc.market is not None and svc.regimes:
        t = svc.market.cal_index(as_of)
        regime = svc.regimes[t if t is not None else -1].to_dict()
    return {
        "as_of": as_of.isoformat(),
        "source_label": ENV_LABELS[st.env],
        "account": {
            "equity": round(equity), "cash": cash, "invested": round(equity - cash), "exposure": (equity - cash) / equity if equity else 0.0,
            "initial_cash": round(initial), "total_return": equity / initial - 1 if initial else 0.0,
            "day_pnl": round(equity - prev_equity), "day_pct": equity / prev_equity - 1 if prev_equity else 0.0,
            "realized_pnl": int(realized), "unrealized_pnl": sum(p["pnl"] for p in positions),
        },
        "risk": {
            "daily_used": status["risk"]["daily_used"], "daily_limit_pct": limits.daily_loss_limit_pct,
            "daily_limit_amount": round(prev_equity * limits.daily_loss_limit_pct),
            "heat_pct": heat / equity if equity else 0.0, "heat_limit_pct": limits.max_heat_pct,
            "positions": len(positions), "max_positions": limits.max_positions,
            "drawdown_pct": equity / peak - 1 if peak else 0.0, "drawdown_halt_pct": limits.drawdown_halt_pct,
            "exposure_cap": regime["exposure_cap"] if regime else None,
        },
        "pending": pending_cards(svc),
        "plans": plans,
        "passbook": {
            "seen_seq": seen, "last_seq": status["ledger_last_seq"], "new_count": len(fresh),
            "counts": {KIND_LABELS.get(k, k): v for k, v in counts.items()},
            "fills": counts.get("fill_buy", 0) + counts.get("fill_sell", 0) + counts.get("protective", 0),
            "blocks": counts.get("gate_block", 0), "passes": counts.get("screen_out", 0) + counts.get("precheck", 0) + counts.get("skip", 0) + counts.get("expire", 0),
            "rows": [row_to_dict(r) for r in fresh], "older": [row_to_dict(r) for r in older],
        },
        "watch": positions,
        "curve": [{"d": c.d, "equity": round(c.equity), "benchmark": round(c.benchmark) if c.benchmark else None} for c in curve],
        "regime": regime,
    }


def screener(svc: EngineService, technique: str | None) -> dict[str, Any]:
    if svc.market is None:
        raise EngineError("일봉 데이터가 없습니다. 설정에서 데이터를 갱신하세요")
    market = svc.market
    as_of = _as_of(svc)
    cfg = svc.engine_config()
    metas = registry.metas(cfg.params)
    key = technique if technique in registry.ALL_KEYS else metas[0].key
    rows: list[dict[str, Any]] = []
    counts = {m.key: 0 for m in metas}
    excluded_illiquid = 0
    no_bar = 0
    for code, feat in market.stocks.items():
        i = feat.index_of(as_of)
        if i is None:
            no_bar += 1
            continue
        value20 = float(feat.f["value20"][i])
        liquid = not math.isnan(value20) and value20 >= cfg.limits.min_avg_value
        if not liquid:
            excluded_illiquid += 1
            continue
        results = registry.evaluate_all(market, code, i, cfg.params)
        for k, r in results.items():
            if r.passed:
                counts[k] += 1
        r = results[key]
        if not r.passed:
            continue
        info = market.info[code]
        close = float(feat.close[i])
        prev = float(feat.close[i - 1]) if i > 0 else close
        rs = market.rs_pct.get(code)
        rows.append({
            "code": code, "name": info.name, "market": info.market, "sector": info.sector, "close": round(close),
            "change": round(close - prev), "change_pct": close / prev - 1 if prev else 0.0, "score": round(r.score, 1),
            "passed": r.passed_count, "total": len(r.checks), "state": r.state, "value20": round(value20),
            "rs": _clean(round(float(rs[i]), 0)) if rs is not None else None,
            "spark": [round(float(x)) for x in feat.close[max(0, i - SPARK_BARS + 1) : i + 1]],
            "also": [_technique_name(k) for k, other in results.items() if other.passed and k != key],
            "plan": r.plan.to_dict() if r.plan else None, "notes": r.notes,
        })
    rows.sort(key=lambda row: (-row["score"], row["code"]))
    return {
        "as_of": as_of.isoformat(), "technique": key,
        "techniques": [{**m.to_dict(), "count": counts[m.key], "enabled": m.key in cfg.enabled_techniques or m.kind != "entry"} for m in metas],
        "rows": rows, "universe": len(market.stocks), "excluded_illiquid": excluded_illiquid, "no_bar": no_bar,
        "min_avg_value": cfg.limits.min_avg_value, "data_source": svc.provider.name,
    }


def stock_detail(svc: EngineService, code: str) -> dict[str, Any]:
    if svc.market is None or code not in svc.market.stocks:
        raise EngineError("종목을 찾을 수 없습니다")
    market = svc.market
    st = svc.settings()
    as_of = _as_of(svc)
    feat = market.stocks[code]
    info = market.info[code]
    i = feat.last_index_on_or_before(as_of)
    if i is None:
        raise EngineError("기준일 이전의 봉이 없습니다")
    cfg = svc.engine_config()
    results = registry.evaluate_all(market, code, i, cfg.params)
    t = market.cal_index(feat.day(i))
    regime = svc.regimes[t if t is not None else -1]
    seats = build_seats(market, code, i, results, regime)
    start = max(0, i - CHART_BARS + 1)
    days = [feat.day(k).isoformat() for k in range(start, i + 1)]
    bars = [
        {"d": days[k - start], "o": float(feat.open[k]), "h": float(feat.high[k]), "l": float(feat.low[k]), "c": float(feat.close[k]), "v": int(feat.volume[k])}
        for k in range(start, i + 1)
    ]
    overlays = {
        name: [_clean(round(float(x), 1)) if not np.isnan(x) else None for x in feat.f[name][start : i + 1]]
        for name in ("sma20", "sma50", "sma150", "sma200")
    }
    close = float(feat.close[i])
    prev = float(feat.close[i - 1]) if i > 0 else close
    with svc.sf() as s:
        latest = s.execute(select(DecisionRow).where(DecisionRow.env == st.env, DecisionRow.code == code).order_by(DecisionRow.as_of.desc(), DecisionRow.created_at.desc()).limit(1)).scalar_one_or_none()
        decision = repo.decision_to_dict(latest) if latest else None
        trades = [repo.trade_to_dict(r) for r in s.execute(select(TradeRow).where(TradeRow.env == st.env, TradeRow.code == code).order_by(TradeRow.id)).scalars()]
        open_intents = [repo.intent_to_dict(r) for r in repo.intents_for(s, st.env, statuses=("pending_approval", "approved")) if r.code == code]
    positions, _, _ = _positions(svc, st.env, st.sim_initial_cash, as_of)
    position = next((p for p in positions if p["code"] == code), None)
    rs = market.rs_pct.get(code)
    fund = market.fundamentals.get(code)
    return {
        "as_of": feat.day(i).isoformat(), "code": code, "name": info.name, "market": info.market, "sector": info.sector,
        "close": round(close), "change": round(close - prev), "change_pct": close / prev - 1 if prev else 0.0,
        "prev_day": feat.day(i - 1).isoformat() if i > 0 else None,
        "stats": {
            "hi252": _clean(float(feat.f["hi252"][i])), "lo252": _clean(float(feat.f["lo252"][i])), "value20": _clean(float(feat.f["value20"][i])),
            "atr_pct": _clean(float(feat.f["atr14"][i]) / close) if close else None, "rs": _clean(float(rs[i])) if rs is not None else None,
            "volume": int(feat.volume[i]), "vol_ratio": _clean(float(feat.volume[i] / feat.f["vol50"][i])) if feat.f["vol50"][i] else None,
        },
        "bars": bars, "overlays": overlays,
        "techniques": [r.to_dict() for r in results.values()],
        "seats": [s_.to_dict() for s_ in seats], "seat_blend": round(blend(seats), 3),
        "regime": regime.to_dict(), "decision": decision, "position": position, "trades": trades, "intents": open_intents,
        "fundamentals": {"per": fund.per, "pbr": fund.pbr, "roe": fund.roe, "eps": fund.eps, "bps": fund.bps, "as_of": fund.as_of} if fund else None,
        "data_source": svc.provider.name,
    }


def search(svc: EngineService, query: str, limit: int = 12) -> list[dict[str, str]]:
    if svc.market is None:
        return []
    q = query.strip().lower()
    if not q:
        return []
    hits = [info for info in svc.market.info.values() if info.code in svc.market.stocks and (q in info.name.lower() or info.code.startswith(q))]
    hits.sort(key=lambda info: (not info.name.lower().startswith(q), info.name))
    return [{"code": i.code, "name": i.name, "market": i.market, "sector": i.sector} for i in hits[:limit]]


def committee_sessions(svc: EngineService, as_of: str | None) -> dict[str, Any]:
    st = svc.settings()
    with svc.sf() as s:
        days = [d for (d,) in s.execute(select(DecisionRow.as_of).where(DecisionRow.env == st.env).group_by(DecisionRow.as_of).order_by(DecisionRow.as_of.desc()).limit(60))]
        day = as_of if as_of in days else (days[0] if days else None)
        rows = s.execute(select(DecisionRow).where(DecisionRow.env == st.env, DecisionRow.as_of == day).order_by(DecisionRow.kind, DecisionRow.created_at)).scalars().all() if day else []
        decisions = [repo.decision_to_dict(r, full=False) for r in rows]
        cost = float(s.execute(select(func.coalesce(func.sum(DecisionRow.cost_usd), 0.0)).where(DecisionRow.env == st.env, DecisionRow.as_of == day)).scalar_one()) if day else 0.0
        graded = _scorecard(s, st.env)
    for d in decisions:
        d["technique_name"] = _technique_name(d.get("technique") or "")
        d["conviction_label"] = CONVICTION_LABEL.get(d["conviction"], "")
    tally = defaultdict(int)
    for d in decisions:
        tally["review" if d["status"] != "ok" else d["action"]] += 1
    return {"days": days, "day": day, "decisions": decisions, "tally": dict(tally), "cost_usd": round(cost, 4),
            "decider": st.decider, "depth_label": DEPTH_LABELS[st.ai_depth], "scorecard": graded, "seat_labels": SEAT_LABELS}


def _scorecard(s, env: str) -> dict[str, Any]:
    """위원회 실적: 매수 판단이 실제 거래로 이어진 뒤의 결과(판단 사슬 기준)."""
    sells = s.execute(select(TradeRow.chain_id, TradeRow.pnl, TradeRow.pnl_pct).where(TradeRow.env == env, TradeRow.side == "sell")).all()
    by_chain = {chain: (pnl or 0, pct or 0.0) for chain, pnl, pct in sells}
    buys = s.execute(select(DecisionRow.chain_id, DecisionRow.source).where(DecisionRow.env == env, DecisionRow.kind == "entry", DecisionRow.action == "BUY")).all()
    out: dict[str, Any] = {}
    for source in ("ai", "rules"):
        closed = [by_chain[c] for c, src in buys if src == source and c in by_chain]
        wins = sum(1 for pnl, _ in closed if pnl > 0)
        out[source] = {"closed": len(closed), "wins": wins, "win_rate": wins / len(closed) if closed else None,
                       "avg_pct": sum(p for _, p in closed) / len(closed) if closed else None, "enough": len(closed) >= 20}
    return out


def decision_detail(svc: EngineService, decision_id: str) -> dict[str, Any]:
    st = svc.settings()
    with svc.sf() as s:
        row = s.get(DecisionRow, decision_id)
        if row is None or row.env != st.env:
            raise EngineError("판단 기록을 찾을 수 없습니다")
        data = repo.decision_to_dict(row)
        intent = s.get(IntentRow, data.get("intent_id")) if data.get("intent_id") else None
        data["intent"] = repo.intent_to_dict(intent) if intent else None
    data["technique_name"] = _technique_name(data.get("technique") or "")
    data["conviction_label"] = CONVICTION_LABEL.get(data["conviction"], "")
    data["chain"] = [row_to_dict(r) for r in svc.ledger.rows(env=st.env, after_seq=svc.ledger_epoch(st.env), chain_id=data["chain_id"], newest_first=False, limit=50)]
    return data


def chain(svc: EngineService, chain_id: str) -> dict[str, Any]:
    """판단 사슬 하나: 같은 사슬 번호를 가진 장부 줄을 오래된 것부터 차례로, 그 사슬의 위원회 판단과 함께 돌려준다."""
    st = svc.settings()
    rows = [row_to_dict(r) for r in svc.ledger.rows(env=st.env, after_seq=svc.ledger_epoch(st.env), chain_id=chain_id, newest_first=False, limit=200)]
    with svc.sf() as s:
        decision_id = s.execute(select(DecisionRow.id).where(DecisionRow.env == st.env, DecisionRow.chain_id == chain_id)
                                .order_by(DecisionRow.created_at.desc()).limit(1)).scalar_one_or_none()
    named = next((r for r in rows if r["name"]), None)
    return {"chain_id": chain_id, "code": named["code"] if named else None, "name": named["name"] if named else None,
            "decision_id": decision_id, "rows": rows}


def portfolio(svc: EngineService) -> dict[str, Any]:
    st = svc.settings()
    as_of = _as_of(svc)
    positions, equity, cash = _positions(svc, st.env, st.sim_initial_cash, as_of)
    with svc.sf() as s:
        intents = [repo.intent_to_dict(r) for r in s.execute(select(IntentRow).where(IntentRow.env == st.env).order_by(IntentRow.created_at.desc(), IntentRow.id).limit(200)).scalars()]
        trades = [repo.trade_to_dict(r) for r in s.execute(select(TradeRow).where(TradeRow.env == st.env).order_by(TradeRow.id.desc()).limit(500)).scalars()]
    for item in intents:
        item["technique_name"] = _technique_name(item.get("technique", ""))
    for trade in trades:
        trade["reason_label"] = FILL_SUMMARY.get(trade["reason"], trade["reason"])
        trade["technique_name"] = _technique_name(trade["technique"])
    # 매매일지: 판단 사슬 하나(진입 → 청산)를 한 건으로 묶는다.
    by_chain: dict[str, dict[str, Any]] = {}
    for trade in reversed(trades):
        entry = by_chain.setdefault(trade["chain_id"] or f"t{trade['id']}", {"chain_id": trade["chain_id"], "code": trade["code"], "name": trade["name"],
                                                                              "technique_name": trade["technique_name"], "buy": None, "sell": None})
        entry["buy" if trade["side"] == "buy" else "sell"] = trade
    journal = [j for j in by_chain.values() if j["buy"]]
    journal.sort(key=lambda j: (j["sell"] or j["buy"])["day"], reverse=True)
    daily: dict[str, int] = defaultdict(int)
    for trade in trades:
        if trade["side"] == "sell" and trade["pnl"] is not None:
            daily[trade["day"]] += trade["pnl"]
    closed = [j for j in journal if j["sell"]]
    wins = sum(1 for j in closed if (j["sell"]["pnl"] or 0) > 0)
    return {
        "as_of": as_of.isoformat(), "source_label": ENV_LABELS[st.env],
        "summary": {"equity": round(equity), "cash": cash, "invested": round(equity - cash), "unrealized": sum(p["pnl"] for p in positions),
                    "realized": sum(daily.values()), "closed_trades": len(closed), "win_rate": wins / len(closed) if closed else None},
        "positions": positions, "intents": intents, "trades": trades, "journal": journal,
        "daily_pnl": [{"d": d, "pnl": v} for d, v in sorted(daily.items())],
    }


def settings_view(svc: EngineService) -> dict[str, Any]:
    st = svc.settings()
    cfg = svc.config
    with svc.sf() as s:
        usage = s.execute(select(AiUsageRow.day, func.sum(AiUsageRow.cost_usd), func.count()).group_by(AiUsageRow.day).order_by(AiUsageRow.day.desc()).limit(14)).all()
    return {
        "engine": st.model_dump(),
        "limits": svc.limits().model_dump(),
        "options": {
            "automation": [{"value": k, "label": v} for k, v in AUTOMATION_LABELS.items()],
            "models": [{"value": m, "label": MODEL_LABELS[m]} for m in SELECTABLE_MODELS],
            "depths": [{"value": k, "label": v} for k, v in DEPTH_LABELS.items()],
            "techniques": [m.to_dict() for m in registry.metas() if m.kind == "entry"],
        },
        "ai": {"configured": cfg.has_anthropic_key, "usage": [{"day": d, "cost_usd": round(float(c or 0), 4), "calls": int(n)} for d, c, n in usage]},
        "broker": {
            "mock": {"configured": cfg.has_kiwoom_keys("mock"), "base_url": KIWOOM_BASE_URL["mock"]},
            "live": {"configured": cfg.has_kiwoom_keys("live"), "base_url": KIWOOM_BASE_URL["live"], "allowed_by_server": cfg.allow_live_trading},
            "runner_available": svc.live_runner_available,
        },
        "data": {"source": svc.provider.name, "day": svc.market.last_day().isoformat() if svc.market else None,
                 "stocks": len(svc.market.stocks) if svc.market else 0, "refreshed_at": svc.data_refreshed_at},
        "sim_start": svc.kv.get("sim_start"),
        "server": {"env": cfg.app_env, "allowed_hosts": cfg.host_list},
    }


def backtests(svc: EngineService) -> list[dict[str, Any]]:
    with svc.sf() as s:
        rows = s.execute(select(BacktestRow).order_by(BacktestRow.created_at.desc()).limit(30)).scalars().all()
    out = []
    for row in rows:
        result = json.loads(row.result)
        summary = result.get("summary", {})
        out.append({"id": row.id, "created_at": row.created_at, "params": json.loads(row.params), "start": result.get("start"), "end": result.get("end"),
                    "total_return": summary.get("total_return"), "cagr": summary.get("cagr"), "mdd": (summary.get("max_drawdown") or {}).get("pct"),
                    "sharpe": summary.get("sharpe"), "trades": (summary.get("trades") or {}).get("trades")})
    return out
