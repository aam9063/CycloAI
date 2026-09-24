# CycloAI backend

Python backend for CycloAI: FastAPI owns auth, profiles, onboarding, chat persistence,
RAG retrieval and grounded training generation (Next.js becomes frontend-only).

## Commands

```bash
uv sync            # create/refresh the venv (Python 3.13, managed by uv)
uv run pytest      # run the test suite
uv run ruff check  # lint
```

## Setup

The backend reads its environment **from `backend/.env`**, resolved from this module's
location rather than from the working directory. Note that this is a DIFFERENT file from
the repository-root `.env` that the Next.js app uses, and **nothing is inherited between
them** — a value present in one is not visible to the other.

### 1. Database

```bash
docker compose up -d          # from the repository root
cd backend && uv run alembic upgrade head
```

The schema needs the `vector` extension, so the Postgres image **must include pgvector**:
the compose file uses `pgvector/pgvector:pg16`. A plain `postgres` image fails at
`create extension vector`.

### 2. `backend/.env`

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | Must use the asyncpg driver form: `postgresql+asyncpg://user:password@host:port/dbname`. The compose credentials are development-only. |
| `GOOGLE_GENERATIVE_AI_API_KEY` | yes for RAG and generation | Used to embed knowledge on ingestion, to embed queries on retrieval, and by the generator. Ingestion and retrieval fail with a clear message naming this variable when it is missing. |
| `JWT_SECRET` | yes for auth | There is deliberately **no insecure default**: a development default that works would reach production as forgeable sessions. Generate one with `python -c "import secrets;print(secrets.token_urlsafe(48))"`. Rejected below 32 bytes, because an HMAC-SHA-256 key must be at least as long as the hash output. |
| `GEMINI_GENERATION_MODEL` | no | Defaults to `gemini-2.5-flash`. Note the frontend configures its own model through `GEMINI_CHAT_MODEL`, so the two are set separately. |

`backend/.env` is git-ignored. Start from `backend/.env.example` for the URL shape, and
create the file with real values locally — never commit it.

### 3. Verifying it works

```bash
uv run pytest                                    # unit tests, no database required
DATABASE_URL=... uv run pytest                   # adds the database integration tests
CYCLOAI_LIVE_SMOKE=1 uv run pytest tests/test_api_live_smoke.py -s
```

The last one is opt-in and deliberately skipped by default: it makes a **real** call to
the model API, so a plain test run must never spend quota.

## Deployment (container)

### Environment variables the container requires

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | asyncpg driver form: `postgresql+asyncpg://user:password@host:port/dbname`. Never baked into the image; the platform injects it. |
| `JWT_SECRET` | yes | No insecure default exists — without it the app refuses to issue sessions. |
| `GOOGLE_GENERATIVE_AI_API_KEY` | yes for RAG and generation | Same role as in local setup. |
| `CYCLOAI_ENV` | production only | Set to `production` to enable the session cookie's `Secure` flag. Without it the cookie is not sent over plain HTTP, so on a deployment that is not served over HTTPS there is **no session at all** — a deployment-shape requirement (serve production behind HTTPS), not a code detail. |

`backend/.env` is never copied into the image (excluded by `.dockerignore`);
locally pass variables with `--env-file backend/.env` for testing only.

### Base-image security posture

The image is built on `python:3.13-slim-trixie` (Debian 13), chosen over
`bookworm` because a scan measured the entire bookworm surface at 3 critical +
15 high CVEs; trixie measures 0 critical and a handful of high. The image is
**not** vulnerability-free. A measured `docker scout` run (see the Dockerfile
comment) shows a small residual of high-severity findings: in the base OS
layer, `perl` and `zlib1g` have no fixed version published upstream and are
`Essential: yes` in Debian or linked by Python, so they cannot be removed;
a couple more sit in Python packages (`msgpack`, `setuptools`) tracked by
`uv.lock`, which are bumped like any other dependency and are not a
Dockerfile concern. `apt-get upgrade` does not help and is deliberately
absent (see the Dockerfile). The practical response is to rebuild the image
periodically so it picks up patched base-image tags, and to scan in CI so the
residual stays tracked instead of being rediscovered in an editor. None of
these packages is reachable through the application's HTTP surface — that is
a risk judgement, not a guarantee.

### Build, migrate, index

```bash
docker build -f backend/Dockerfile -t cycloai-backend backend/   # context is backend/, not the repo root
```

Migrations are a deploy step and run **inside** the image (the `alembic` CLI
ships in its virtualenv):

```bash
docker run --rm --env-file backend/.env cycloai-backend alembic upgrade head
```

Before the RAG endpoints return anything, index the knowledge base **against
the production database**. The embeddings are DATA, not code: they live in
`knowledge_embeddings` rows, so they do not travel with the image. A fresh
deployment retrieves nothing until the corpus is indexed. `knowledge-base/`
lives outside the build context, so mount it read-only:

```bash
docker run --rm --env-file backend/.env \
  -v "$(pwd)/knowledge-base:/app/knowledge-base:ro" \
  cycloai-backend python scripts/rag_index.py
```

Finally, point the frontend at this service: `NEXT_PUBLIC_API_URL` must be the
backend's public URL.

## Layout

```
src/cycloai/
  domain/    # P1: zone model, canonical schema, parsers, validators (no infra)
  rag/       # P3: ingestion port, retrieval service
  generator/ # P4: retrieve -> prompt -> structured+prose -> validate
  auth/      # P5: users, argon2, JWT cookie
  db/        # P2: engine, models, repositories
  api/       # routers
tests/       # unit, rule and golden tests
```

## Design invariants

The canonical domain model (`src/cycloai/domain/`) makes these invariants structural,
not conventional (feature doc `odd/tasks/python-backend-rag-pipeline.md`, section 3.1):

- **I1 — No absolute physiological targets.** Steps carry a zone code and optional
  intent; the schema offers no field for bpm or watts and forbids unknown extras.
- **I2 — Closed zone vocabulary, one per training system.** Zones live in
  `domain/zones.py` as TWO seven-zone tables keyed by `(system, code)`: the power
  system in %FTP (Z1-Z7, from `knowledge-base/training/zonas-entrenamiento-potencia.md`)
  and the heart-rate system in %LTHR (Z1-Z4 plus the Z5A/Z5B/Z5C split of zone 5,
  from `knowledge-base/training/zonas-entrenamiento-pulso.md`, which quotes Joe
  Friel). A zone is identified by system AND code, never by a code alone, because
  Z1-Z4 resolve to DIFFERENT bounds in the two systems. Mapping is keyed on the
  parsed zone code token and never on the descriptor text. The athlete declares one
  system in onboarding and supplies the matching threshold (FTP or LTHR);
  `resolve_target` refuses to resolve a zone against the other system, and there is
  deliberately no %FTP-to-%LTHR conversion, because that relationship is individual
  and drifts.
- **I3 — Provenance required.** Generated workouts carry non-empty `sources[]`.
- **I4 — Fail closed.** Schema or rule failure is an error, never a partially valid plan.
- **I5 — Derived metrics are computed.** `total_duration_s` and `estimated_tss` are
  `@computed_field` properties derived from the structure; they are not caller inputs.
  `estimated_tss` accumulates ONLY power-system zones, because TSS is power-derived:
  heart-rate steps, RPE steps and the power zones Z6/Z7 (which the power document says
  TSS cannot quantify) contribute zero and are counted in
  `tss_uncovered_target_count`, so a `0.0` is never mistaken for "no work prescribed".
  Step durations keep the three corpus forms (`N min`, `N sec`, `mm:ss`) as a
  discriminated union instead of normalising them away.
- **I6 — Free-text sessions are first-class.** `prescriptive: false` sessions carry a
  zone cap plus a duration and must not carry fabricated interval blocks.
