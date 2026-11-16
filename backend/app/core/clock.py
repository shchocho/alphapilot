"""한국 시간(KST)과 거래일 달력.

휴장일 목록은 보도 자료 기준이며 거래소가 임시 휴장을 추가할 수 있다. 그래서
1) 설정에서 휴장일을 더할 수 있고(extra_holidays),
2) 엔진은 "당일 지수 봉이 없으면 휴장"이라는 데이터 기반 확인을 함께 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# 2026년: 총 17일(보도 기준). 6/3 지방선거, 7/17 제헌절, 12/31 연말 휴장 포함.
_HOLIDAYS_2026 = (
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-01",
    "2026-05-05", "2026-05-25", "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24",
    "2026-09-25", "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31",
)
# 2027년: 법정 공휴일 규칙으로 계산한 잠정 목록. 거래소 공지로 반드시 다시 확인한다.
_HOLIDAYS_2027_TENTATIVE = (
    "2027-01-01", "2027-02-05", "2027-02-08", "2027-03-01", "2027-05-05", "2027-05-13",
    "2027-08-16", "2027-09-14", "2027-09-15", "2027-09-16", "2027-10-04", "2027-10-11",
    "2027-12-27", "2027-12-31",
)
KRX_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(d) for d in (*_HOLIDAYS_2026, *_HOLIDAYS_2027_TENTATIVE)
)
CALENDAR_CONFIRMED_THROUGH = date(2026, 12, 31)

SessionPhase = Literal["closed", "pre_open", "regular", "closing_auction", "after_close"]

_PRE_OPEN = time(8, 0)
_OPEN = time(9, 0)
_CLOSING_AUCTION = time(15, 20)
_CLOSE = time(15, 30)
_DAY_END = time(20, 0)


def now_kst() -> datetime:
    return datetime.now(KST)


def kst(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=KST)


def is_trading_day(day: date, extra_holidays: frozenset[date] = frozenset()) -> bool:
    if day.weekday() >= 5:
        return False
    return day not in KRX_HOLIDAYS and day not in extra_holidays


def next_trading_day(day: date, extra_holidays: frozenset[date] = frozenset()) -> date:
    """day 다음의 첫 거래일(day 자신은 제외)."""
    cursor = day + timedelta(days=1)
    while not is_trading_day(cursor, extra_holidays):
        cursor += timedelta(days=1)
    return cursor


def previous_trading_day(day: date, extra_holidays: frozenset[date] = frozenset()) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor, extra_holidays):
        cursor -= timedelta(days=1)
    return cursor


def session_phase(moment: datetime, extra_holidays: frozenset[date] = frozenset()) -> SessionPhase:
    """KRX 정규장 기준 구간. 1차 범위는 KRX만 다루므로 NXT·애프터마켓은 구분하지 않는다."""
    local = moment.astimezone(KST)
    if not is_trading_day(local.date(), extra_holidays):
        return "closed"
    t = local.time()
    if t < _PRE_OPEN or t >= _DAY_END:
        return "closed"
    if t < _OPEN:
        return "pre_open"
    if t < _CLOSING_AUCTION:
        return "regular"
    if t < _CLOSE:
        return "closing_auction"
    return "after_close"


def seconds_until_close(moment: datetime) -> int | None:
    """정규장 마감(15:30)까지 남은 초. 장중이 아니면 None."""
    local = moment.astimezone(KST)
    if session_phase(local) not in ("regular", "closing_auction"):
        return None
    close_at = datetime.combine(local.date(), _CLOSE, tzinfo=KST)
    return max(0, int((close_at - local).total_seconds()))
