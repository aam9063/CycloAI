# CycloAI backend production image.
#
# Multi-stage: the builder resolves dependencies with uv and the final stage
# copies only the virtualenv, the application, and the migration/indexing
# tooling. The build toolchain (uv), caches, and dev dependencies never reach
# the final image.
#
# Base: Debian 13 (trixie), not bookworm. Measured with docker scout
# (2025): bookworm's base layer carries 3 critical + 15 high CVEs, all in
# Debian packages (perl-base, util-linux, libssl3, zlib1g); trixie carries
# 0 critical + 5 high and 62 fewer packages. Most bookworm findings have NO
# fixed version upstream, so `apt-get upgrade` here would change nothing and
# make builds non-reproducible. It is deliberately absent: the fix is this
# base-image tag plus periodic rebuilds, not an upgrade layer. Do NOT
# "fix" the scanner warning with an apt-get upgrade.
#
# Python 3.13 matches the project pin (requires-python = ">=3.13,<3.14" and
# uv.lock's "==3.13.*"). Do NOT bump the minor: the dependency set is not
# verified beyond it.

FROM python:3.13-slim-trixie AS builder

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


FROM python:3.13-slim-trixie

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

# Remove the system Python's pip and its vendored packages (this deletes
# site-packages/pip wholesale, including the msgpack and setuptools copies
# bundled under pip/_vendor/). This is NOT application cleanup: pip is a
# build-time tool the runtime never invokes — the app runs /app/.venv/bin/python
# and the container command is the venv's uvicorn — and those vendored packages
# are not ours (they live in the BASE IMAGE's system site-packages, not in
# /app/.venv, and `import msgpack` under the image's own interpreter already
# fails). Removing them is what takes the scan from 5 high findings to 2. Do
# not "restore" pip here for debugging convenience: debugging belongs in the
# builder stage or an ephemeral overlay, and the system interpreter itself
# stays as the fallback and the source of the standard library. Nothing else
# in the system Python is touched.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
    && rm -rf /usr/local/lib/python3.13/site-packages/pip-*.dist-info

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
