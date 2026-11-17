"""엔진 단일 실행 잠금.

매매 엔진(스케줄러)은 한 데이터 폴더에 하나만 돌아야 한다. 둘이 돌면 같은 주문이 두 번 나갈 수 있다.
데이터 폴더의 engine.lock 파일을 운영체제 잠금으로 잡고, 이미 잡혀 있으면 시작하지 않는다.
프로세스가 죽으면 운영체제가 잠금을 풀어 주므로, 남은 파일 때문에 다음 시작이 막히지는 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO


class EngineLockError(RuntimeError):
    pass


class EngineLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 - 잠금을 잡는 동안 열어 둔다
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise EngineLockError(
                f"다른 AlphaPilot 엔진이 이미 이 데이터 폴더를 쓰고 있습니다({self.path}). 엔진은 하나만 띄웁니다"
            ) from exc
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
