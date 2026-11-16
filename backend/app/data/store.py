"""일봉 캐시(SQLite)와 갱신 로직."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.data.provider import DailyBarProvider, DataProviderError, clean_bars, empty_bars
from app.store.db import BarRow

log = logging.getLogger(__name__)

FULL_HISTORY_BARS = 800
_OVERLAP_BARS = 6
_ADJUSTMENT_TOLERANCE = 0.005  # 겹치는 봉의 종가가 0.5% 넘게 다르면 수정주가가 바뀐 것으로 본다


@dataclass(slots=True)
class RefreshReport:
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    refetched: list[str] = field(default_factory=list)  # 수정주가 변경으로 전체를 다시 받은 종목

    @property
    def ok(self) -> bool:
        return not self.failed


class BarStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def load(self, code: str) -> pd.DataFrame:
        with self._sf() as s:
            rows = s.execute(
                select(BarRow.d, BarRow.o, BarRow.h, BarRow.l, BarRow.c, BarRow.v)
                .where(BarRow.code == code)
                .order_by(BarRow.d)
            ).all()
        if not rows:
            return empty_bars()
        frame = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        frame["date"] = pd.to_datetime(frame["date"])
        return clean_bars(frame.set_index("date"))

    def load_many(self, codes: Iterable[str]) -> dict[str, pd.DataFrame]:
        wanted = list(codes)
        with self._sf() as s:
            rows = s.execute(
                select(BarRow.code, BarRow.d, BarRow.o, BarRow.h, BarRow.l, BarRow.c, BarRow.v)
                .where(BarRow.code.in_(wanted))
                .order_by(BarRow.code, BarRow.d)
            ).all()
        out: dict[str, pd.DataFrame] = {}
        if not rows:
            return out
        frame = pd.DataFrame(rows, columns=["code", "date", "open", "high", "low", "close", "volume"])
        frame["date"] = pd.to_datetime(frame["date"])
        for code, group in frame.groupby("code", sort=False):
            out[str(code)] = clean_bars(group.drop(columns="code").set_index("date"))
        return out

    def last_dates(self) -> dict[str, str]:
        with self._sf() as s:
            rows = s.execute(select(BarRow.code, func.max(BarRow.d)).group_by(BarRow.code)).all()
        return {code: last for code, last in rows}

    def replace(self, code: str, bars: pd.DataFrame) -> None:
        with self._sf() as s, s.begin():
            s.execute(delete(BarRow).where(BarRow.code == code))
            self._insert(s, code, bars)

    def upsert(self, code: str, bars: pd.DataFrame) -> None:
        with self._sf() as s, s.begin():
            self._insert(s, code, bars)

    @staticmethod
    def _insert(session: Session, code: str, bars: pd.DataFrame) -> None:
        if bars.empty:
            return
        payload = [
            {"code": code, "d": idx.strftime("%Y-%m-%d"), "o": float(r.open), "h": float(r.high),
             "l": float(r.low), "c": float(r.close), "v": int(r.volume)}
            for idx, r in zip(bars.index, bars.itertuples(index=False), strict=True)
        ]
        # SQLite 변수 한도 때문에 나눠 넣는다.
        for start in range(0, len(payload), 400):
            chunk = payload[start : start + 400]
            chunk_stmt = sqlite_insert(BarRow).values(chunk)
            chunk_stmt = chunk_stmt.on_conflict_do_update(
                index_elements=[BarRow.code, BarRow.d],
                set_={"o": chunk_stmt.excluded.o, "h": chunk_stmt.excluded.h, "l": chunk_stmt.excluded.l,
                      "c": chunk_stmt.excluded.c, "v": chunk_stmt.excluded.v},
            )
            session.execute(chunk_stmt)


def refresh_bars(
    provider: DailyBarProvider,
    store: BarStore,
    codes: Iterable[str],
    *,
    full_history: int = FULL_HISTORY_BARS,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> RefreshReport:
    """캐시에 없는 봉만 받아 채운다.

    이미 받은 구간과 겹치는 봉의 종가가 달라졌으면(액면분할·권리락 등으로 수정주가가 바뀐 경우)
    그 종목은 전체 기간을 다시 받는다.
    """
    report = RefreshReport()
    wanted = list(codes)
    last = store.last_dates()
    today = pd.Timestamp.now(tz="Asia/Seoul").normalize().tz_localize(None)
    for i, code in enumerate(wanted):
        if on_progress:
            on_progress(i, len(wanted), code)
        try:
            if code not in last:
                bars = provider.daily_bars(code, full_history)
                if bars.empty:
                    report.failed[code] = "봉이 없습니다"
                    continue
                store.replace(code, bars)
                report.updated.append(code)
                continue

            gap_days = max(0, (today - pd.Timestamp(last[code])).days)
            count = min(full_history, gap_days + _OVERLAP_BARS + 2)
            fresh = provider.daily_bars(code, count)
            if fresh.empty:
                report.failed[code] = "봉이 없습니다"
                continue
            cached = store.load(code)
            overlap = fresh.index.intersection(cached.index)
            if len(overlap) > 0:
                drift = (fresh.loc[overlap, "close"] / cached.loc[overlap, "close"] - 1).abs().max()
                if drift > _ADJUSTMENT_TOLERANCE:
                    full = provider.daily_bars(code, full_history)
                    store.replace(code, full)
                    report.refetched.append(code)
                    continue
            new_rows = fresh[fresh.index > cached.index[-1]] if not cached.empty else fresh
            if new_rows.empty:
                # 마지막 봉이 장중 값으로 저장됐을 수 있으니 겹치는 마지막 봉은 덮어쓴다.
                store.upsert(code, fresh.tail(1))
                report.unchanged.append(code)
            else:
                store.upsert(code, fresh[fresh.index >= cached.index[-1]] if not cached.empty else fresh)
                report.updated.append(code)
        except DataProviderError as exc:
            log.warning("일봉 갱신 실패 %s: %s", code, exc)
            report.failed[code] = str(exc)
    return report
