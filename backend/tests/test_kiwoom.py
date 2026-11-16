"""키움 REST 어댑터 계약 테스트. 문서 예시(docs/research/03-kiwoom-rest-api.md) 형태의 응답을 HTTP 모킹으로 흉내 낸다.

실제 키움 서버를 호출하지 않는다. 실주문 경로는 이 테스트에서 절대 실행되지 않는다.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from app.broker.base import BrokerOrder, OrderRequest
from app.broker.kiwoom import parsing as kw
from app.broker.kiwoom.broker import KiwoomBroker
from app.broker.kiwoom.client import BASE_URL, KiwoomClient, RateLimiter, Token
from app.broker.kiwoom.errors import KiwoomAuthError, KiwoomError, KiwoomNotConfigured, KiwoomRateLimited
from app.core.clock import kst

MOCK = BASE_URL["mock"]
NOW = kst(2026, 11, 16, 8, 5)
OK = {"return_code": 0, "return_msg": "정상적으로 처리되었습니다"}
TOKEN_BODY = {"expires_dt": "20261117080500", "token_type": "bearer", "token": "TKN-1", **OK}


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(**kw_args) -> tuple[KiwoomClient, FakeSleep]:
    sleep = FakeSleep()
    limiter = RateLimiter("mock", clock=lambda: 0.0, sleep=FakeSleep())
    http = httpx.AsyncClient(base_url=MOCK)
    client = KiwoomClient("mock", "app-key", "secret-key", http=http, limiter=limiter, sleep=sleep, now=lambda: NOW, **kw_args)
    return client, sleep


def body_of(route, index: int = -1) -> dict:
    return json.loads(route.calls[index].request.content)


# ── 값 해석 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [("+73,200", Decimal("73200")), ("-00000000196888", Decimal("-196888")), ("--1200981", Decimal("-1200981")),
     ("000000017598258", Decimal("17598258")), ("-0", Decimal("0")), ("-0.00", Decimal("0")), ("", None),
     (None, None), ("abc", None), ("46.25", Decimal("46.25"))],
)
def test_kw_num_handles_signs_padding_and_blanks(raw, expected):
    assert kw.kw_num(raw) == expected


def test_price_sign_is_direction_not_negative_value():
    assert kw.kw_price("-78800") == 78_800
    assert kw.kw_price("+70100") == 70_100
    assert kw.kw_price("") is None


def test_saturated_volume_is_treated_as_missing():
    assert kw.kw_volume("4294967295") is None
    assert kw.kw_volume("-82") == 82


@pytest.mark.parametrize(("raw", "code"), [("A005930", "005930"), ("005930", "005930"), ("005930_NX", "005930"), ("Q500001", "500001"), ("", "")])
def test_stock_codes_are_normalised_to_six_digits(raw, code):
    assert kw.normalize_code(raw) == code


def test_return_code_accepts_int_string_and_camel_case():
    assert kw.return_code({"return_code": 0}) == 0
    assert kw.return_code({"return_code": "3"}) == 3
    assert kw.return_code({"returnCode": 20}) == 20
    assert kw.return_code({}) == 0


@pytest.mark.parametrize(
    ("message", "code"),
    [("인증에 실패했습니다[8005:Token이 유효하지 않습니다]", 8005), ("LOGIN 실패 CODE=8005", 8005),
     ("[2000](RC4058:모의투자 장종료)", 2000), ("정상", None)],
)
def test_detail_code_is_extracted_from_message(message, code):
    assert kw.detail_code(message) == code


def test_token_expiry_is_parsed_as_kst():
    assert kw.parse_expiry("20261116083713") == kst(2026, 11, 16, 8, 37, 13)


# ── 토큰 ─────────────────────────────────────────────────────────────────────

@respx.mock
async def test_token_request_sends_only_content_type_and_credentials():
    route = respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    client, _ = make_client()
    token = await client.token()
    request = route.calls.last.request
    assert token.value == "TKN-1"
    assert token.expires_at == kst(2026, 11, 17, 8, 5)
    assert body_of(route) == {"grant_type": "client_credentials", "appkey": "app-key", "secretkey": "secret-key"}
    assert "api-id" not in request.headers and "authorization" not in request.headers


@respx.mock
async def test_token_is_cached_and_saved_once():
    route = respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    saved: list[Token] = []
    client, _ = make_client(save_token=saved.append)
    await client.token()
    await client.token()
    assert route.call_count == 1
    assert [t.value for t in saved] == ["TKN-1"]


@respx.mock
async def test_stored_token_is_reused_without_issuing_a_new_one():
    route = respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    stored = Token("STORED", NOW + timedelta(hours=5))
    client, _ = make_client(load_token=lambda: stored)
    assert (await client.token()).value == "STORED"
    assert route.call_count == 0


@respx.mock
async def test_token_close_to_expiry_is_reissued():
    route = respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    stale = Token("OLD", NOW + timedelta(minutes=5))  # 만료 10분 전부터 갱신
    client, _ = make_client(load_token=lambda: stale)
    assert (await client.token()).value == "TKN-1"
    assert route.call_count == 1


@respx.mock
async def test_unregistered_ip_is_reported_as_auth_error_with_hint():
    respx.post(f"{MOCK}/oauth2/token").respond(json={"return_code": 3, "return_msg": "인증에 실패했습니다[8050:IP가 등록되지 않았습니다]"})
    client, _ = make_client()
    with pytest.raises(KiwoomAuthError) as info:
        await client.token()
    assert info.value.code == 8050
    assert "IP" in info.value.hint


async def test_missing_keys_raise_not_configured():
    client = KiwoomClient("mock", "", "")
    with pytest.raises(KiwoomNotConfigured):
        await client.token()
    await client.aclose()


# ── 요청 ─────────────────────────────────────────────────────────────────────

@respx.mock
async def test_request_sends_api_id_and_bearer_token():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/stkinfo").respond(json={"stk_cd": "005930", **OK})
    client, _ = make_client()
    resp = await client.request("ka10001", "/api/dostk/stkinfo", {"stk_cd": "005930"})
    headers = route.calls.last.request.headers
    assert headers["api-id"] == "ka10001"
    assert headers["authorization"] == "Bearer TKN-1"
    assert "cont-yn" not in headers
    assert resp.body["stk_cd"] == "005930"
    assert client.last_success == NOW


@respx.mock
async def test_business_error_with_http_200_raises():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    respx.post(f"{MOCK}/api/dostk/stkinfo").respond(json={"return_code": 2, "return_msg": "오류[1902:종목 정보가 없습니다]"})
    client, _ = make_client()
    with pytest.raises(KiwoomError) as info:
        await client.request("ka10001", "/api/dostk/stkinfo", {"stk_cd": "999999"})
    assert info.value.code == 1902
    assert not isinstance(info.value, KiwoomAuthError | KiwoomRateLimited)


@respx.mock
async def test_invalid_token_triggers_one_reissue_and_retry():
    token_route = respx.post(f"{MOCK}/oauth2/token").mock(side_effect=[
        httpx.Response(200, json=TOKEN_BODY), httpx.Response(200, json={**TOKEN_BODY, "token": "TKN-2"}),
    ])
    data_route = respx.post(f"{MOCK}/api/dostk/acnt").mock(side_effect=[
        httpx.Response(200, json={"return_code": 3, "return_msg": "인증에 실패했습니다[8005:Token이 유효하지 않습니다]"}),
        httpx.Response(200, json={"entr": "000000001000000", **OK}),
    ])
    client, _ = make_client()
    resp = await client.request("kt00001", "/api/dostk/acnt", {"qry_tp": "3"})
    assert resp.body["entr"] == "000000001000000"
    assert token_route.call_count == 2
    assert data_route.calls.last.request.headers["authorization"] == "Bearer TKN-2"


@respx.mock
async def test_auth_failure_is_not_retried_forever():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/acnt").respond(json={"return_code": 3, "return_msg": "[8005:Token이 유효하지 않습니다]"})
    client, _ = make_client()
    with pytest.raises(KiwoomAuthError):
        await client.request("kt00001", "/api/dostk/acnt", {"qry_tp": "3"})
    assert route.call_count == 2


@respx.mock
async def test_rate_limited_query_backs_off_and_retries():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/rkinfo").mock(side_effect=[
        httpx.Response(429, json={"return_code": 5, "return_msg": "허용된 요청 개수를 초과하였습니다"}),
        httpx.Response(200, json={"trde_prica_upper": [], **OK}),
    ])
    client, sleep = make_client()
    await client.request("ka10032", "/api/dostk/rkinfo", {"mrkt_tp": "000", "mang_stk_incls": "0", "stex_tp": "1"})
    assert route.call_count == 2
    assert len(sleep.calls) == 1 and sleep.calls[0] >= 1.0


@respx.mock
async def test_rate_limit_gives_up_after_bounded_retries():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/rkinfo").respond(status_code=429, json={"return_code": 5, "return_msg": "초과"})
    client, _ = make_client()
    with pytest.raises(KiwoomRateLimited):
        await client.request("ka10032", "/api/dostk/rkinfo", {}, max_rate_retries=2)
    assert route.call_count == 3


@respx.mock
async def test_pagination_reads_headers_and_echoes_next_key():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/acnt").mock(side_effect=[
        httpx.Response(200, json={"oso": [{"ord_no": "0000001"}], **OK}, headers={"cont-yn": "Y", "next-key": "KEY-2"}),
        httpx.Response(200, json={"oso": [{"ord_no": "0000002"}], **OK}, headers={"cont-yn": "N", "next-key": ""}),
    ])
    client, _ = make_client()
    rows = await client.paginate("ka10075", "/api/dostk/acnt", {"all_stk_tp": "0"}, "oso")
    assert [r["ord_no"] for r in rows] == ["0000001", "0000002"]
    second = route.calls[1].request
    assert second.headers["cont-yn"] == "Y" and second.headers["next-key"] == "KEY-2"
    assert json.loads(second.content) == {"all_stk_tp": "0"}  # 본문은 그대로


async def test_rate_limiter_spaces_calls_per_api_id():
    now = [0.0]
    waits = FakeSleep()
    limiter = RateLimiter("live", clock=lambda: now[0], sleep=waits)
    await limiter.wait("ka10001")
    await limiter.wait("ka10001")  # 초당 4회 → 0.25초 간격
    await limiter.wait("kt00018")  # 다른 TR은 따로 센다
    assert waits.calls == [pytest.approx(0.25)]
    assert limiter.rate_for("kt00018") == 0.9
    assert RateLimiter("mock").rate_for("ka10001") == 0.9
    limiter.slow_down("ka10001")
    assert limiter.rate_for("ka10001") == 2.0


# ── 브로커: 계좌 ──────────────────────────────────────────────────────────────

BALANCE = {
    "tot_evlt_amt": "000000025789890", "prsm_dpst_aset_amt": "000001012632507",
    "acnt_evlt_remn_indv_tot": [
        {"stk_cd": "A005930", "stk_nm": "삼성전자", "evltv_prft": "-00000000196888", "pur_pric": "000000000124500",
         "rmnd_qty": "000000000000003", "trde_able_qty": "000000000000003", "cur_prc": "000000059000"},
        {"stk_cd": "A000660", "stk_nm": "SK하이닉스", "pur_pric": "000000000500000", "rmnd_qty": "000000000000000",
         "trde_able_qty": "000000000000000", "cur_prc": "000000566000"},
    ],
    "return_code": 0, "return_msg": "조회가 완료되었습니다",
}


@respx.mock
async def test_account_parses_padded_amounts_and_prefixed_codes():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/acnt").mock(side_effect=[
        httpx.Response(200, json=BALANCE),
        httpx.Response(200, json={"entr": "000000005000000", "ord_alow_amt": "000000004800000", **OK}),
    ])
    client, _ = make_client()
    snapshot = await KiwoomBroker(client).account()
    assert body_of(route, 0) == {"qry_tp": "1", "dmst_stex_tp": "KRX"}
    assert route.calls[0].request.headers["api-id"] == "kt00018"
    assert route.calls[1].request.headers["api-id"] == "kt00001"
    assert (snapshot.cash, snapshot.deposit, snapshot.total_equity) == (4_800_000, 5_000_000, 1_012_632_507)
    assert len(snapshot.positions) == 1  # 수량 0인 행은 뺀다
    pos = snapshot.positions[0]
    assert (pos.code, pos.name, pos.qty, pos.avg_price, pos.last_price) == ("005930", "삼성전자", 3, 124_500.0, 59_000.0)


@respx.mock
async def test_open_orders_and_fills_are_mapped():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    respx.post(f"{MOCK}/api/dostk/acnt").mock(side_effect=[
        httpx.Response(200, json={"oso": [{"ord_no": "0000139", "stk_cd": "005930", "stk_nm": "삼성전자", "ord_stt": "접수",
                                           "ord_qty": "10", "ord_pric": "70000", "oso_qty": "7", "cntr_qty": "3",
                                           "io_tp_nm": "+매수", "tm": "093012", "orig_ord_no": "0000000"}], **OK}),
        httpx.Response(200, json={"cntr": [{"ord_no": "0000139", "stk_cd": "005930", "stk_nm": "삼성전자", "io_tp_nm": "-매도",
                                            "cntr_pric": "70100", "cntr_qty": "3", "tdy_trde_cmsn": "31", "tdy_trde_tax": "420",
                                            "ord_tm": "093015"},
                                           {"ord_no": "0000140", "stk_cd": "000660", "cntr_qty": "0"}], **OK}),
    ])
    broker = KiwoomBroker(make_client()[0])
    order = (await broker.open_orders())[0]
    assert (order.order_id, order.side, order.qty, order.remaining_qty, order.filled_qty, order.price) == ("0000139", "buy", 10, 7, 3, 70_000)
    fills = await broker.fills_today()
    assert len(fills) == 1
    assert (fills[0].side, fills[0].qty, fills[0].price, fills[0].fee, fills[0].tax) == ("sell", 3, 70_100, 31, 420)


# ── 브로커: 주문 ──────────────────────────────────────────────────────────────

@respx.mock
async def test_market_buy_order_body_uses_strings_and_blank_price():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").respond(json={"ord_no": "0000138", "dmst_stex_tp": "KRX", "return_code": 0, "return_msg": "매수주문이 완료되었습니다."})
    result = await KiwoomBroker(make_client()[0]).place_order(OrderRequest("005930", "buy", 4))
    assert result.ok and result.order_id == "0000138" and not result.ambiguous
    assert route.calls.last.request.headers["api-id"] == "kt10000"
    assert body_of(route) == {"dmst_stex_tp": "KRX", "stk_cd": "005930", "ord_qty": "4", "ord_uv": "", "trde_tp": "3", "cond_uv": ""}


@respx.mock
async def test_limit_sell_order_uses_sell_api_id_and_price():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").respond(json={"ord_no": "0000141", **OK})
    await KiwoomBroker(make_client()[0]).place_order(OrderRequest("005930", "sell", 2, "limit", 70_100))
    assert route.calls.last.request.headers["api-id"] == "kt10001"
    assert body_of(route)["ord_uv"] == "70100" and body_of(route)["trde_tp"] == "0"


@respx.mock
async def test_order_timeout_is_ambiguous_and_never_resent():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").mock(side_effect=httpx.ReadTimeout("timeout"))
    result = await KiwoomBroker(make_client()[0]).place_order(OrderRequest("005930", "buy", 1))
    assert not result.ok and result.ambiguous
    assert route.call_count == 1


@respx.mock
async def test_rate_limited_order_is_ambiguous_and_never_resent():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").respond(status_code=429, json={"return_code": 5, "return_msg": "초과"})
    result = await KiwoomBroker(make_client()[0]).place_order(OrderRequest("005930", "buy", 1))
    assert not result.ok and result.ambiguous
    assert route.call_count == 1


@respx.mock
async def test_rejected_order_is_a_clear_failure_not_ambiguous():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").respond(json={"return_code": 20, "return_msg": "[2000](RC4058:모의투자 장종료)"})
    result = await KiwoomBroker(make_client()[0]).place_order(OrderRequest("005930", "buy", 1))
    assert not result.ok and not result.ambiguous
    assert "장종료" in result.message
    assert route.call_count == 1


@respx.mock
async def test_order_with_expired_token_is_not_auto_retried():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").respond(json={"return_code": 3, "return_msg": "[8005:Token이 유효하지 않습니다]"})
    result = await KiwoomBroker(make_client()[0]).place_order(OrderRequest("005930", "buy", 1))
    assert not result.ok
    assert route.call_count == 1


async def test_invalid_orders_are_refused_before_any_request():
    broker = KiwoomBroker(KiwoomClient("mock", "k", "s"))
    assert not (await broker.place_order(OrderRequest("005930", "buy", 0))).ok
    assert not (await broker.place_order(OrderRequest("005930", "buy", 1, "limit", None))).ok
    await broker.client.aclose()


@respx.mock
async def test_cancel_sends_explicit_remaining_quantity_never_zero():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/ordr").respond(json={"ord_no": "0000141", "base_orig_ord_no": "0000139", "cncl_qty": "000000000007", **OK})
    broker = KiwoomBroker(make_client()[0])
    order = BrokerOrder("0000139", "005930", "삼성전자", "buy", 10, 70_000, remaining_qty=7, filled_qty=3, status="접수")
    result = await broker.cancel_order(order)
    assert result.ok and result.order_id == "0000141"
    assert route.calls.last.request.headers["api-id"] == "kt10003"
    assert body_of(route) == {"dmst_stex_tp": "KRX", "orig_ord_no": "0000139", "stk_cd": "005930", "cncl_qty": "7"}

    nothing_left = BrokerOrder("0000139", "005930", "삼성전자", "buy", 10, 70_000, remaining_qty=0, filled_qty=10, status="체결")
    assert not (await broker.cancel_order(nothing_left)).ok
    assert route.call_count == 1


# ── 브로커: 시세·종목 ─────────────────────────────────────────────────────────

@respx.mock
async def test_daily_bars_are_sorted_ascending_with_absolute_prices():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/chart").respond(json={
        "stk_cd": "005930",
        "stk_dt_pole_chart_qry": [
            {"cur_prc": "-70100", "trde_qty": "9263135", "dt": "20261113", "open_pric": "+69800", "high_pric": "+70500", "low_pric": "-69600"},
            {"cur_prc": "+69500", "trde_qty": "4294967295", "dt": "20261112", "open_pric": "69000", "high_pric": "69900", "low_pric": "68800"},
        ], **OK})
    bars = await KiwoomBroker(make_client()[0]).daily_bars("005930", 10, base=date(2026, 11, 13))
    assert body_of(route) == {"stk_cd": "005930", "base_dt": "20261113", "upd_stkpc_tp": "1"}
    assert list(bars.index.strftime("%Y-%m-%d")) == ["2026-11-12", "2026-11-13"]
    assert list(bars["close"]) == [69_500.0, 70_100.0]
    assert bars["volume"].iloc[0] == 0  # 포화 값은 결측(0)
    assert bars["low"].iloc[1] == 69_600.0


@respx.mock
async def test_quote_and_fundamentals_handle_signs_and_blanks():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    respx.post(f"{MOCK}/api/dostk/mrkcond").respond(json={"cur_prc": "-208500", "pred_close_pric": "209000", "open_pric": "+214000",
                                                          "high_pric": "+216000", "low_pric": "-205000", "trde_qty": "12822005",
                                                          "upl_pric": "+271500", "lst_pric": "-146500", **OK})
    respx.post(f"{MOCK}/api/dostk/stkinfo").respond(json={"stk_cd": "005930", "per": "13.52", "eps": "5212", "roe": "", "pbr": "1.21", "bps": "58120", **OK})
    broker = KiwoomBroker(make_client()[0])
    quote = await broker.quote("005930")
    assert (quote.price, quote.prev_close, quote.low, quote.upper_limit, quote.lower_limit) == (208_500, 209_000, 205_000, 271_500, 146_500)
    fund = await broker.fundamentals("005930")
    assert (fund.per, fund.pbr, fund.roe, fund.eps) == (13.52, 1.21, None, 5212.0)


@respx.mock
async def test_stock_master_marks_restricted_stocks():
    respx.post(f"{MOCK}/oauth2/token").respond(json=TOKEN_BODY)
    route = respx.post(f"{MOCK}/api/dostk/stkinfo").respond(json={"list": [
        {"code": "005930", "name": "삼성전자", "auditInfo": "정상", "orderWarning": "0", "upName": "전기전자", "marketName": "거래소", "nxtEnable": "Y"},
        {"code": "123456", "name": "위험종목", "auditInfo": "관리종목", "orderWarning": "5", "upName": "기타", "marketName": "코스닥"},
    ], **OK})
    rows = await KiwoomBroker(make_client()[0]).stock_master("0")
    assert body_of(route) == {"mrkt_tp": "0"}
    assert rows[0]["flags"] == [] and rows[0]["nxt"] is True
    assert rows[1]["flags"] == ["투자경고", "관리종목"]
