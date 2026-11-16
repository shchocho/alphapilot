"""실행 진입점. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

워커는 반드시 1개로 둔다. 엔진이 두 개 뜨면 주문이 중복될 수 있다.
"""

from app.api.factory import create_app

app = create_app()
