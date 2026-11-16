"""키움 REST 응답 값 해석.

응답의 모든 값은 문자열이고, 문서에 드러나지 않는 함정이 많다(docs/research/03-kiwoom-rest-api.md §15):
- 가격의 +/−는 전일 대비 방향 표시다. 음수 가격이 아니다 → 절댓값
- 계좌 TR 금액은 0으로 채운 부호 포함 문자열("-00000000196888")
- 일부 API는 음수를 "--1200981"처럼 이중 부호로 보낸다
- 거래량이 4294967295(2³²−1)로 포화될 수 있다 → 결측으로 본다
- 잔고·조건검색의 종목코드는 "A005930"처럼 접두어가 붙는다
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.clock import KST

SATURATED_VOLUME = 4_294_967_295
_DETAIL_CODE = re.compile(r"\[(\d{3,5}):|CODE=(\d{3,5})|\[(\d{3,5})\]")
_STOCK_CODE = re.compile(r"^[A-Z]?(\d{6})(?:_(?:NX|AL))?$")


def kw_num(raw: Any) -> Decimal | None:
    """'+73,200' '-00000000196888' '--1200981' '-0' '' → Decimal 또는 None."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("%", "")
    negative = text.startswith("-")
    text = text.lstrip("+-")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return -value if (negative and value != 0) else value


def kw_int(raw: Any, default: int = 0) -> int:
    value = kw_num(raw)
    return int(value) if value is not None else default


def kw_float(raw: Any) -> float | None:
    value = kw_num(raw)
    return float(value) if value is not None else None


def kw_price(raw: Any) -> int | None:
    """가격: 부호는 방향 표시이므로 절댓값."""
    value = kw_num(raw)
    return int(abs(value)) if value is not None else None


def kw_volume(raw: Any) -> int | None:
    """거래량: 2³²−1 포화 값은 None."""
    value = kw_num(raw)
    if value is None or abs(value) >= SATURATED_VOLUME:
        return None
    return int(abs(value))


def normalize_code(raw: Any) -> str:
    """'A005930'·'005930_NX' → '005930'. 형식이 다르면 원문을 돌려준다."""
    text = str(raw or "").strip()
    match = _STOCK_CODE.match(text)
    return match.group(1) if match else text


def return_code(body: dict[str, Any]) -> int:
    """return_code는 정수 또는 숫자 문자열이고, 일부 TR은 returnCode로 온다."""
    raw = body.get("return_code", body.get("returnCode", 0))
    try:
        return int(str(raw).strip() or 0)
    except ValueError:
        return -1


def return_message(body: dict[str, Any]) -> str:
    return str(body.get("return_msg", body.get("returnMsg", "")) or "")


def detail_code(message: str) -> int | None:
    """메시지에 박힌 세부 코드('[8005:...]', 'CODE=8005', '[2000](RC4058...)')."""
    match = _DETAIL_CODE.search(message or "")
    if not match:
        return None
    return int(next(g for g in match.groups() if g))


def parse_expiry(expires_dt: str) -> datetime:
    """토큰 만료 시각 'YYYYMMDDHHmmss'(KST)."""
    return datetime.strptime(expires_dt, "%Y%m%d%H%M%S").replace(tzinfo=KST)
