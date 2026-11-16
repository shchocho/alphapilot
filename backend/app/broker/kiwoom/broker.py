"""키움 REST 브로커 어댑터. 1차 범위는 KRX만 다룬다(모의투자가 KRX만 지원하므로 모의·실전 동작을 맞춘다).

실제 API로 검증하지 못한 구현이다. 문서 예시 기반 계약 테스트만 통과했으므로,
키를 받은 뒤 모의투자 도메인에서 '연결 테스트'와 소액 주문으로 먼저 확인해야 한다.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
import pandas as pd

from app.broker.base import (
    AccountSnapshot,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    OrderRequest,
    OrderResult,
    Quote,
)
from app.broker.kiwoom import parsing as kw
from app.broker.kiwoom.client import KiwoomClient
from app.broker.kiwoom.errors import KiwoomError, KiwoomRateLimited
from app.data.provider import clean_bars, empty_bars
from app.indicators.features import Fundamentals

log = logging.getLogger(__name__)

EXCHANGE = "KRX"
ORDER_TYPE_CODE = {"limit": "0", "market": "3"}  # trde_tp: 0 보통(지정가), 3 시장가
CHART_LIST_KEYS = {"ka10081": "stk_dt_pole_chart_qry", "ka11081": "result_list"}
# ka10099 orderWarning: 2 정리매매, 3 단기과열, 4 투자위험, 5 투자경고
WARNING_LABELS = {"2": "정리매매", "3": "단기과열", "4": "투자위험", "5": "투자경고"}


def _side(io_type_name: str) -> str:
    return "sell" if "매도" in (io_type_name or "") else "buy"


class KiwoomBroker:
    def __init__(self, client: KiwoomClient, *, chart_api_id: str = "ka10081") -> None:
        self._c = client
        self.env = client.env
        self._chart_api_id = chart_api_id

    @property
    def client(self) -> KiwoomClient:
        return self._c

    # ── 계좌 ───────────────────────────────────────────────────────────────

    async def account(self) -> AccountSnapshot:
        balance = await self._c.request("kt00018", "/api/dostk/acnt", {"qry_tp": "1", "dmst_stex_tp": EXCHANGE})
        deposit = await self._c.request("kt00001", "/api/dostk/acnt", {"qry_tp": "3"})
        positions = [
            BrokerPosition(
                code=kw.normalize_code(row.get("stk_cd")), name=str(row.get("stk_nm", "")).strip(),
                qty=kw.kw_int(row.get("rmnd_qty")), sellable_qty=kw.kw_int(row.get("trde_able_qty")),
                avg_price=float(kw.kw_num(row.get("pur_pric")) or 0), last_price=float(kw.kw_price(row.get("cur_prc")) or 0),
            )
            for row in balance.body.get("acnt_evlt_remn_indv_tot") or []
        ]
        return AccountSnapshot(
            cash=kw.kw_int(deposit.body.get("ord_alow_amt")), deposit=kw.kw_int(deposit.body.get("entr")),
            total_equity=kw.kw_int(balance.body.get("prsm_dpst_aset_amt")),
            positions=[p for p in positions if p.qty > 0],
        )

    async def open_orders(self) -> list[BrokerOrder]:
        rows = await self._c.paginate(
            "ka10075", "/api/dostk/acnt", {"all_stk_tp": "0", "trde_tp": "0", "stk_cd": "", "stex_tp": "1"}, "oso"
        )
        return [
            BrokerOrder(
                order_id=str(r.get("ord_no", "")).strip(), code=kw.normalize_code(r.get("stk_cd")),
                name=str(r.get("stk_nm", "")).strip(), side=_side(str(r.get("io_tp_nm", ""))),  # type: ignore[arg-type]
                qty=kw.kw_int(r.get("ord_qty")), price=kw.kw_price(r.get("ord_pric")) or 0,
                remaining_qty=kw.kw_int(r.get("oso_qty")), filled_qty=kw.kw_int(r.get("cntr_qty")),
                status=str(r.get("ord_stt", "")).strip(), time=str(r.get("tm", "")).strip(),
                original_order_id=str(r.get("orig_ord_no", "")).strip(),
            )
            for r in rows
        ]

    async def fills_today(self) -> list[BrokerFill]:
        rows = await self._c.paginate(
            "ka10076", "/api/dostk/acnt",
            {"stk_cd": "", "qry_tp": "0", "sell_tp": "0", "ord_no": "", "stex_tp": "1"}, "cntr",
        )
        fills = []
        for r in rows:
            qty = kw.kw_int(r.get("cntr_qty"))
            if qty <= 0:
                continue
            fills.append(BrokerFill(
                order_id=str(r.get("ord_no", "")).strip(), code=kw.normalize_code(r.get("stk_cd")),
                name=str(r.get("stk_nm", "")).strip(), side=_side(str(r.get("io_tp_nm", ""))),  # type: ignore[arg-type]
                qty=qty, price=kw.kw_price(r.get("cntr_pric")) or 0, fee=kw.kw_int(r.get("tdy_trde_cmsn")),
                tax=kw.kw_int(r.get("tdy_trde_tax")), time=str(r.get("ord_tm", "")).strip(),
            ))
        return fills

    # ── 주문 ───────────────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResult:
        if request.qty < 1:
            return OrderResult(False, message="주문 수량이 1주 미만입니다")
        if request.order_type == "limit" and not request.price:
            return OrderResult(False, message="지정가 주문에 가격이 없습니다")
        api_id = "kt10000" if request.side == "buy" else "kt10001"
        body = {
            "dmst_stex_tp": EXCHANGE, "stk_cd": request.code, "ord_qty": str(request.qty),
            "ord_uv": str(request.price) if request.order_type == "limit" else "",
            "trde_tp": ORDER_TYPE_CODE[request.order_type], "cond_uv": "",
        }
        return await self._send_order(api_id, body)

    async def cancel_order(self, order: BrokerOrder) -> OrderResult:
        """미체결 잔량을 수량을 명시해 취소한다. '0'(잔량 전부)은 계산 실수로 새어 나가면 위험해 쓰지 않는다."""
        if not (order.order_id.isdigit() and order.remaining_qty >= 1):
            return OrderResult(False, message="취소할 주문 번호나 잔량이 올바르지 않습니다")
        body = {"dmst_stex_tp": EXCHANGE, "orig_ord_no": order.order_id, "stk_cd": order.code,
                "cncl_qty": str(order.remaining_qty)}
        return await self._send_order("kt10003", body)

    async def _send_order(self, api_id: str, body: dict[str, Any]) -> OrderResult:
        """주문 TR은 다시 보내지 않는다. 접수 여부가 불분명하면 ambiguous로 알려 호출한 쪽이 조회로 확인하게 한다."""
        try:
            resp = await self._c.request(api_id, "/api/dostk/ordr", body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            log.warning("주문 응답을 받지 못했습니다(%s): %s", api_id, type(exc).__name__)
            return OrderResult(False, message="응답을 받지 못했습니다. 미체결·체결 조회로 접수 여부를 확인합니다", ambiguous=True)
        except KiwoomRateLimited as exc:
            return OrderResult(False, message=f"호출 한도 초과: {exc}", ambiguous=True)
        except KiwoomError as exc:
            hint = f" ({exc.hint})" if exc.hint else ""
            return OrderResult(False, message=f"{exc}{hint}")
        order_id = str(resp.body.get("ord_no", "")).strip()
        if not order_id:
            return OrderResult(False, message="주문번호가 없는 응답입니다. 조회로 확인합니다", ambiguous=True)
        return OrderResult(True, order_id=order_id, message=kw.return_message(resp.body))

    # ── 시세·종목 ───────────────────────────────────────────────────────────

    async def quote(self, code: str) -> Quote:
        resp = await self._c.request("ka10007", "/api/dostk/mrkcond", {"stk_cd": code})
        b = resp.body
        return Quote(
            code=code, price=kw.kw_price(b.get("cur_prc")) or 0, prev_close=kw.kw_price(b.get("pred_close_pric")) or 0,
            open=kw.kw_price(b.get("open_pric")) or 0, high=kw.kw_price(b.get("high_pric")) or 0,
            low=kw.kw_price(b.get("low_pric")) or 0, volume=kw.kw_volume(b.get("trde_qty")),
            upper_limit=kw.kw_price(b.get("upl_pric")), lower_limit=kw.kw_price(b.get("lst_pric")),
        )

    async def daily_bars(self, code: str, count: int, *, base: date | None = None) -> pd.DataFrame:
        """수정주가 일봉. 최신 → 과거 순으로 오는 행을 날짜 오름차순으로 정리한다."""
        base_dt = (base or date.today()).strftime("%Y%m%d")
        list_key = CHART_LIST_KEYS[self._chart_api_id]
        body = {"stk_cd": code, "base_dt": base_dt, "upd_stkpc_tp": "1"}
        rows: list[dict[str, Any]] = []
        cont, next_key = False, ""
        for _ in range(10):
            resp = await self._c.request(self._chart_api_id, "/api/dostk/chart", body, cont=cont, next_key=next_key)
            rows.extend(resp.body.get(list_key) or [])
            if len(rows) >= count or not resp.cont or not resp.next_key:
                break
            cont, next_key = True, resp.next_key
        records = []
        for r in rows:
            close, day = kw.kw_price(r.get("cur_prc")), str(r.get("dt", "")).strip()
            if not close or len(day) != 8:
                continue
            records.append({
                "date": pd.Timestamp(day), "open": kw.kw_price(r.get("open_pric")) or 0,
                "high": kw.kw_price(r.get("high_pric")) or 0, "low": kw.kw_price(r.get("low_pric")) or 0,
                "close": close, "volume": kw.kw_volume(r.get("trde_qty")) or 0,
            })
        if not records:
            return empty_bars()
        return clean_bars(pd.DataFrame(records).set_index("date")).tail(count)

    async def fundamentals(self, code: str) -> Fundamentals:
        """주식기본정보(ka10001). PER·ROE는 외부 제공 값이라 주 1회 수준으로만 바뀐다."""
        resp = await self._c.request("ka10001", "/api/dostk/stkinfo", {"stk_cd": code})
        b = resp.body
        return Fundamentals(
            per=kw.kw_float(b.get("per")), pbr=kw.kw_float(b.get("pbr")), roe=kw.kw_float(b.get("roe")),
            eps=kw.kw_float(b.get("eps")), bps=kw.kw_float(b.get("bps")), as_of=date.today().isoformat(),
        )

    async def stock_master(self, market_type: str) -> list[dict[str, Any]]:
        """종목 목록(ka10099). market_type: '0' 코스피, '10' 코스닥. 매매 제한 표시를 flags로 정리한다."""
        rows = await self._c.paginate("ka10099", "/api/dostk/stkinfo", {"mrkt_tp": market_type}, "list")
        out = []
        for r in rows:
            flags = []
            warning = str(r.get("orderWarning", "0")).strip()
            if warning in WARNING_LABELS:
                flags.append(WARNING_LABELS[warning])
            audit = str(r.get("auditInfo", "")).strip()
            if audit and audit != "정상":
                flags.append(audit)
            out.append({
                "code": kw.normalize_code(r.get("code")), "name": str(r.get("name", "")).strip(),
                "sector": str(r.get("upName", "")).strip(), "market": str(r.get("marketName", "")).strip(),
                "flags": flags, "nxt": str(r.get("nxtEnable", "")).strip() == "Y",
            })
        return out
