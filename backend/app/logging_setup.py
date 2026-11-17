"""로그 형식. 서버에서는 표준 출력으로 내보내고, 모으기·보관은 Docker가 맡는다(docker-compose.yml의 logging)."""

from __future__ import annotations

import logging

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MARK = "_alphapilot_handler"


def configure_logging(level: str = "INFO") -> None:
    """앱 로거(alphapilot·app.*)가 시각과 함께 찍히게 한다. 여러 번 불러도 처리기를 하나만 단다."""
    root = logging.getLogger()
    if not any(getattr(h, _MARK, False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(FORMAT, "%Y-%m-%dT%H:%M:%S%z"))
        setattr(handler, _MARK, True)
        root.addHandler(handler)
    root.setLevel(level)
    # 외부 라이브러리의 요청 단위 로그는 너무 많다
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
