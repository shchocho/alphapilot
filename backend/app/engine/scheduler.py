"""백그라운드 루프(Scheduler): 장 마감 뒤 일봉 갱신, 밀린 거래일 처리, 하루 한 번 DB 점검.

엔진 서비스(app/engine/service.py)의 공개 메서드만 부른다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any

from app.core import clock
from app.engine.core import Event
from app.engine.service import CAUGHT_UP_KEY, EngineService
from app.engine.settings import EngineSettings

log = logging.getLogger(__name__)


SCHEDULER_DONE_KEY = "scheduler_done_day"  # 일봉 갱신과 거래일 처리를 마친 날(재시작해도 같은 날 다시 하지 않는다)
MAINTENANCE_DONE_KEY = "maintenance_done_day"


class Scheduler:
    """백그라운드 루프. 서버 한 대가 사람 없이 24시간 돌 때를 기준으로 짰다.

    거래일 장 마감(15:45) 뒤:
      1) 일봉을 갱신한다. 오늘 봉이 아직 없거나 갱신이 실패하면 RETRY_EVERY마다 다시 시도하고,
         GIVE_UP_AT까지도 못 받으면 원장에 오류를 남기고 그날은 멈춘다(사람이 확인해야 한다).
      2) 시뮬레이션이 최신 일봉을 따라가던 중이면 밀린 거래일을 처리한다. 서버가 멈춰 며칠 밀렸어도
         MAX_CATCH_UP일까지는 차례로 따라잡는다. 과거 구간을 재생하던 중이면 자동으로 진행하지 않는다.
      3) 하루 한 번 DB 점검(백업·정리·무결성)을 한다.
    health()는 루프가 살아 있는지를 /api/health에 알려 준다.
    """

    REFRESH_AFTER = time(15, 45)
    RETRY_EVERY = timedelta(minutes=15)
    GIVE_UP_AT = time(23, 0)
    MAX_CATCH_UP = 5
    STALE_AFTER = timedelta(minutes=5)  # 쉬는 중 마지막 틱이 이보다 오래되면 멈춘 것으로 본다
    BUSY_LIMIT = timedelta(minutes=60)  # 한 틱(갱신·처리)이 이보다 오래 걸리면 걸린 것으로 본다
    STOP_GRACE = 45.0  # 끌 때 진행 중인 틱이 끝나기를 기다리는 초(docker-compose의 stop_grace_period보다 짧게)

    def __init__(self, service: EngineService, *, interval: float = 60.0,
                 maintenance: Callable[[datetime], dict[str, Any]] | None = None) -> None:
        self._service = service
        self._interval = interval
        self._maintenance = maintenance
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._wake = asyncio.Event()
        self._retry_at: datetime | None = None
        self._warned_day: date | None = None
        self.tick_started: datetime | None = None
        self.tick_finished: datetime | None = None

    def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._wake.clear()
            self._task = asyncio.create_task(self._run(), name="alphapilot-scheduler")

    async def stop(self, grace: float | None = None) -> None:
        """진행 중인 틱(일봉 갱신·거래일 처리)은 끝까지 하게 두고 멈춘다. grace초 안에 안 끝나면 그때 끊는다.

        거래일 처리 도중에 끊으면 체결은 반영됐는데 장후 심의·주문 계획은 없는 날이 생길 수 있어서다.
        """
        task = self._task
        if task is None:
            return
        self._stopping = True
        self._wake.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self.STOP_GRACE if grace is None else grace)
        except TimeoutError:
            log.warning("스케줄러가 %s초 안에 끝나지 않아 중단합니다", self.STOP_GRACE if grace is None else grace)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            self._task = None

    def health(self, now: datetime) -> tuple[bool, str]:
        """(정상 여부, 상태). 상태: off · starting · ok · busy · stale · stuck · dead."""
        if self._task is None:
            return True, "off"
        if self._task.done():
            return False, "dead"
        if self.tick_started is None:
            return True, "starting"
        if self.tick_finished is None or self.tick_finished < self.tick_started:
            within = now - self.tick_started <= self.BUSY_LIMIT
            return within, "busy" if within else "stuck"
        fresh = now - self.tick_finished <= self.STALE_AFTER
        return fresh, "ok" if fresh else "stale"

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick(clock.now_kst())
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 루프는 죽지 않고 오류를 기록한다
                log.exception("스케줄러 오류")
                self._service.last_error = f"{type(exc).__name__}: {exc}"
            if self._stopping:
                break
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self._interval)

    async def tick(self, now: datetime) -> None:
        self.tick_started = now
        try:
            await self._tick(now)
        finally:
            self.tick_finished = now

    async def _tick(self, now: datetime) -> None:
        service = self._service
        st = service.settings()
        today = now.date()
        if not clock.is_trading_day(today, service.holidays(st)) or now.time() < self.REFRESH_AFTER:
            return
        if service.kv.get(SCHEDULER_DONE_KEY) == today.isoformat():
            return
        if self._retry_at is not None and now < self._retry_at:
            return

        problem = ""
        try:
            await service.refresh_data()
            if service.market is None or service.market.last_day() < today:
                problem = "오늘 일봉이 아직 올라오지 않았습니다"
        except Exception as exc:  # noqa: BLE001 - 네트워크·공급자 오류는 다시 시도한다
            log.warning("일봉 갱신 실패: %s", exc)
            problem = f"일봉 갱신 실패({type(exc).__name__}: {exc})"

        if problem:
            if now.time() >= self.GIVE_UP_AT:
                self._retry_at = None
                service.kv.set(SCHEDULER_DONE_KEY, today.isoformat())
                service.log_event(st.env, Event("error", f"{today} {problem}. 오늘 자동 처리를 멈춥니다. 데이터를 갱신한 뒤 직접 진행하세요"))
            else:
                self._retry_at = now + self.RETRY_EVERY
                if self._warned_day != today:
                    self._warned_day = today
                    minutes = int(self.RETRY_EVERY.total_seconds() // 60)
                    service.log_event(st.env, Event("data", f"{problem}. {minutes}분마다 다시 시도합니다"))
            return

        self._retry_at = None
        service.kv.set(SCHEDULER_DONE_KEY, today.isoformat())
        try:
            await self._follow(service.settings())
            await self._sleeves()
        finally:
            await self._maintain(now)

    async def _sleeves(self) -> None:
        """내 종목 운용: 대기 주문을 체결하고 차례가 된 바구니를 심의한다. 실패해도 엔진은 멈추지 않는다."""
        service = self._service
        sleeves = service.sleeves
        if sleeves is None or sleeves.current() is None:
            return
        try:
            await sleeves.run(trigger="schedule")
        except Exception as exc:  # noqa: BLE001 - 바구니 오류가 자동매매 엔진을 막지 않게 기록만 한다
            log.exception("바구니 심의 실패")
            service.log_event(service.settings().env, Event("error", f"바구니 자동 심의 실패: {type(exc).__name__}: {exc}"))

    async def _follow(self, st: EngineSettings) -> None:
        """시뮬레이션이 최신을 따라가던 중이면 밀린 거래일을 처리한다."""
        service = self._service
        if st.env != "sim" or st.state == "stopped":
            return
        sim_day, behind = service.sim_lag()
        if sim_day is None or behind <= 0:
            return
        following = behind == 1 or sim_day == service.kv.get(CAUGHT_UP_KEY)
        if not following:
            return  # 과거 구간 재생 중: 사람이 진행한다
        if behind > self.MAX_CATCH_UP:
            service.log_event("sim", Event("engine", f"시뮬레이션이 {behind}거래일 밀렸습니다. 자동으로는 {self.MAX_CATCH_UP}일까지만 따라잡습니다. "
                                                "자동매매 화면에서 이어서 진행하세요"))
            return
        if behind > 1:
            service.log_event("sim", Event("engine", f"서버가 멈춘 사이 밀린 {behind}거래일을 차례로 처리합니다"))
        await service.advance(behind)

    async def _maintain(self, now: datetime) -> None:
        service = self._service
        if self._maintenance is None or service.kv.get(MAINTENANCE_DONE_KEY) == now.date().isoformat():
            return
        service.kv.set(MAINTENANCE_DONE_KEY, now.date().isoformat())
        env = service.settings().env
        try:
            report = await asyncio.to_thread(self._maintenance, now)
        except Exception as exc:  # noqa: BLE001 - 점검 실패가 매매를 막지는 않는다. 기록만 남긴다
            log.exception("일일 점검 실패")
            service.log_event(env, Event("error", f"일일 DB 점검 실패: {type(exc).__name__}: {exc}"))
            return
        integrity = report.get("integrity", "ok")
        parts = [f"백업 {report['backup']}" if report.get("backup") else "백업 안 함",
                 f"만료 세션 {report.get('sessions', 0)}건·로그인 기록 {report.get('login_attempts', 0)}건 정리",
                 f"무결성 {integrity}"]
        if integrity != "ok":
            service.log_event(env, Event("error", "일일 DB 점검에서 무결성 문제를 찾았습니다: " + " · ".join(parts)))
        else:
            service.log_event(env, Event("engine", "일일 DB 점검: " + " · ".join(parts)))
        log.info("일일 점검: %s", report)
