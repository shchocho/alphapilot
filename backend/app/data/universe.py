"""유니버스(매매 대상 종목 목록).

1차 범위는 시가총액·거래대금 상위 종목을 묶은 고정 목록(`universe.csv`)이다.
업종 분류는 직접 붙인 거친 분류라서, 키움 종목 마스터(ka10099)를 연결하면 그쪽 업종명으로 바꾼다.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from app.core.models import StockInfo

_CSV = Path(__file__).with_name("universe.csv")


@lru_cache
def load_universe(path: Path | None = None) -> tuple[StockInfo, ...]:
    source = path or _CSV
    with source.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return tuple(StockInfo(code=r["code"], name=r["name"], market=r["market"], sector=r["sector"]) for r in rows)


def universe_map(path: Path | None = None) -> dict[str, StockInfo]:
    return {s.code: s for s in load_universe(path)}
