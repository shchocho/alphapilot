"""실행 진입점. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

워커는 반드시 1개로 둔다. 엔진이 두 개 뜨면 주문이 중복될 수 있다(둘째 프로세스는 store/lock.py가 막는다).
운영(AP_ENV=prod)에서는 설정에 빠진 것이 있으면 시작하지 않고 무엇을 고칠지 알린다.
"""

from app.api.factory import create_app
from app.config import get_settings
from app.logging_setup import configure_logging

config = get_settings()
configure_logging(config.log_level)
if config.is_prod and (problems := config.production_problems()):
    raise SystemExit("운영 설정을 먼저 고치세요:\n- " + "\n- ".join(problems))

app = create_app(config)
