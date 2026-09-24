# CycloAI backend production image.
#
# Multi-stage: the builder resolves dependencies with uv and the final stage
# copies only the virtualenv, the application, and the migration/indexing
# tooling. The build toolchain (uv), caches, and dev dependencies never reach
# the final image.
#
# Python 3.13 matches the project pin (requires-python = ">=3.13,<3.14" and
# uv.lock's "==3.13.*"). Do NOT bump the minor: the dependency set is not
# verified beyond it.

FROM python:3.13-slim-bookworm AS builder

# uv is a build tool: it lives in the builder only. Pinned for reproducible
# builds; the dependency versions themselves come from uv.lock, not from uv.
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first so it is cached independently of source changes.
# --frozen makes uv fail instead of re-resolving if pyproject.toml and
# uv.lock ever disagree: the image installs exactly what the lockfile pins.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Then the application itself (editable install inside /app/.venv).
# README.md is needed because pyproject.toml declares it as the package readme.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Migration config and the deploy-step tooling: alembic/ for `alembic
# upgrade head`, scripts/ for `rag_index.py` (knowledge-base indexing).
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts


FROM python:3.13-slim-bookworm

# Dedicated unprivileged user: a container that serves HTTP has no business
# being root. Numeric UID so it is stable regardless of host UID allocation.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/scripts /app/scripts

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The platform may assign the port dynamically; respect PORT, default 8000.
EXPOSE 8000

# Healthcheck via the Python interpreter that is guaranteed to be in the
# image: a slim base ships no curl or wget. /openapi.json is targeted because
# building it needs no database or API key (importing the app opens no
# connections). A dedicated lightweight /health endpoint would be better
# (cheaper than serializing the whole OpenAPI schema every probe) but adding
# one means touching application source outside this image's scope.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c 'import os, sys, urllib.request; r = urllib.request.urlopen("http://127.0.0.1:%s/openapi.json" % os.environ.get("PORT", "8000"), timeout=4); sys.exit(0 if r.status == 200 else 1)'

USER app

CMD ["sh", "-c", "exec uvicorn cycloai.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
