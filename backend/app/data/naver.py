"""네이버 금융 차트의 공개 일봉 공급자 (비공식 경로).

키움 API 키를 받기 전 시뮬레이션용이다. 공식 API가 아니라서 형식이 바뀌거나 막힐 수 있고,
개인적인 조회 용도로만 쓴다. 요청 사이에 간격을 두고, 받은 봉은 SQLite에 캐시해 다시 받지 않는다.
키움을 연결한 뒤에는 키움 일봉이 기본 공급자가 된다.
"""

from __future__ import annotations

import html
import re
import time

import httpx
import pandas as pd

from app.data.provider import DataProviderError, clean_bars, empty_bars

_URL = "https://fchart.stock.naver.com/sise.nhn"
_ITEM = re.compile(r'<item data="(\d{8})\|([\d.]+)\|([\d.]+)\|([\d.]+)\|([\d.]+)\|(\d+)"')
_NAME = re.compile(r'<chartdata[^>]*\bname="([^"]*)"')


def parse_chart_xml(text: str) -> tuple[str, pd.DataFrame]:
    """(종목명, 봉) 을 돌려준다. 봉이 없으면 빈 DataFrame."""
    name_match = _NAME.search(text)
    name = html.unescape(name_match.group(1)) if name_match else ""
    rows = _ITEM.findall(text)
    if not rows:
        return name, empty_bars()
    frame = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d")
    for col in ("open", "high", "low", "close"):
        frame[col] = frame[col].astype(float)
    frame["volume"] = frame["volume"].astype("int64")
    return name, clean_bars(frame.set_index("date"))


class NaverProvider:
    name = "naver"

    def __init__(self, client: httpx.Client | None = None, min_interval: float = 0.12) -> None:
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"})
        self._min_interval = min_interval
        self._last_call = 0.0

    def fetch(self, code: str, count: int) -> tuple[str, pd.DataFrame]:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        params = {"symbol": code, "timeframe": "day", "count": str(count), "requestType": "0"}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client.get(_URL, params=params)
                self._last_call = time.monotonic()
                resp.raise_for_status()
                return parse_chart_xml(resp.content.decode("euc-kr", errors="replace"))
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))
        raise DataProviderError(f"일봉을 받지 못했습니다: {code} ({last_error})")

    def daily_bars(self, code: str, count: int) -> pd.DataFrame:
        return self.fetch(code, count)[1]
