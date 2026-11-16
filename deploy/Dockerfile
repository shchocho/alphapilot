# AlphaPilot 서버 이미지: 화면(React)을 먼저 빌드하고, 파이썬 서버가 그 결과물을 함께 서빙한다.
# 빌드: 저장소 루트에서 `docker compose up -d --build`

# 1) 화면 빌드
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) 실행 이미지
FROM python:3.13-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    TZ=Asia/Seoul
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# 의존성은 잠금 파일 그대로 설치한다(개발용 도구 제외).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/app ./app
COPY --from=web /web/dist ./static

# 루트가 아닌 전용 계정으로 실행하고, 쓰기는 /data 볼륨에만 한다.
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin alphapilot \
    && mkdir -p /data \
    && chown -R alphapilot:alphapilot /data
USER alphapilot

ENV AP_ENV=prod \
    AP_DATA_DIR=/data \
    AP_STATIC_DIR=/app/static \
    PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# 매매 엔진은 프로세스 안에 하나만 있어야 하므로 워커는 반드시 1개다.
# 앱 포트는 밖에 열지 않고 Caddy만 접근하므로, Caddy가 넘겨주는 접속 주소(X-Forwarded-For)를 믿는다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
