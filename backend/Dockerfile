# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app ./backend/app

RUN python -m pip install --upgrade pip \
    && python -m pip wheel --wheel-dir /wheels ./backend


FROM python:3.12-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/app/.local/bin:${PATH}"

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

WORKDIR /app/backend

COPY --chown=app:app backend/alembic.ini ./alembic.ini
COPY --chown=app:app backend/alembic ./alembic
COPY --chown=app:app backend/scripts ./scripts
COPY --chown=app:app database /app/database

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
