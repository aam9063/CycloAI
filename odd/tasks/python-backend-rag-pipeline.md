# Feature: Python/FastAPI backend + grounded training-generation RAG

Workflow: ODD (default harness workflow; the repository's `CLAUDE.md` declares SDD, but SDD was explicitly declined for this program in favour of ODD tracking).
Phase: 1 — Domain core (in progress)
Owner: single writer at a time; one work-unit commit per task.

---

## 1. Context (evidence from repository exploration)

Current state, verified by two read-only mapping passes:

**Stack today**: Next.js 16 (App Router, `proxy.ts` instead of `middleware.ts`) + Supabase (Postgres, Auth, RLS, one Edge Function) + AI SDK v6 with `@ai-sdk/google` + Upstash Redis (rate limiting) + pgvector.

**What is actually live**

| Surface | Location | Notes |
| --- | --- | --- |
| Chat endpoint | `app/api/chat/route.ts` | POST, Supabase cookie session, Upstash limit 15/60s, RAG then `streamText`, model `GEMINI_CHAT_MODEL ?? gemini-3.5-flash` |
| Retrieval | `lib/ai/rag.ts` | `gemini-embedding-001`, 768 dims, `RETRIEVAL_QUERY`, RPC `search_knowledge` `match_count=4`; never throws, returns `''` on any failure |
| Ingestion (offline) | `scripts/rag-index.ts` | `##`-heading chunking (400 words, 50 overlap), `RETRIEVAL_DOCUMENT`, idempotent per `source_file`, quota backoff, `chunks × 700ms` pacing |
| System prompt | `lib/ai/system-prompt.ts` | Spanish, 10 behaviour rules, athlete profile + Strava block + RAG block; rule 10 forces plain text (no Markdown) |
| Persistence | `lib/db/*`, migrations 004/005 | `conversations`, `messages`; user message persisted pre-stream, assistant in `onFinish`/`onAbort` |
| Auth | `lib/supabase/*`, `app/(auth)/actions.ts` | Supabase Auth: email/password (register waitlist-blocked), Google OAuth via `/auth/callback` |
| Rate limiting | `lib/utils/ratelimit.ts` | Upstash; fails open when unconfigured |

**What is aspirational (documented but absent from code)**: the entire Strava integration (no OAuth, no sync, no writer for `ctl`/`atl`/`tsb`/`weekly_*`/`last_sync_at`), `lib/ai/tools.ts` and every tool call proposed in the report (`generate_training_plan`, `save_plan_to_profile`, …), plan persistence, `/plans` and `/dashboard` routes (protected in middleware but nonexistent), `conversations.summary` writer, and the `strava_tokens` / `activities` tables that `CLAUDE.md` specifies but no migration creates.

**Decisive finding**: there are **no workout domain types anywhere** in `lib/`. Training sessions exist only as prose, held together by prompt rule 5 (duration, zones, estimated TSS, warm-up/main/cool-down). There is no schema, no validator, and no plan persistence. The generator this feature builds is therefore new construction, not a refactor.

**Corpus inventory**: `knowledge-base/` holds 21 Markdown documents across `training/` (8), `nutrition/` (6), `physiology/` (5), `gym/` (4), each with YAML front matter (`title`, `category`, `keywords`) and `##` sections. `docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt` holds 14 structured workouts (E1–E14, separated by `--`); `docs/gym.txt` holds three gym blocks (lower body, upper body, core).

**Corpus format finding**: the cycling document is semi-structured, not prose — each step carries a role (`Warm up` / `Active` / `Recovery` / `Cool down`), a duration (`30 min`), an absolute target (`@ 67 bpm`) and a zone label (`Zone 1: Recovery`), with occasional `Repetir N veces` repeat markers, and some entries are free-text coach notes (E2, E4). The absolute `bpm` values belong to the source athlete, which drives design decision D3 below.

---

## 2. Locked decisions

| # | Decision | Value | Rationale |
| --- | --- | --- | --- |
| D1 | Scope | Full backend: FastAPI owns auth, profiles, onboarding, waitlist, chat persistence, RAG and generation. Next.js becomes frontend-only. | User decision; supersedes the narrower "RAG service only" option. |
| D2 | Database | PostgreSQL, provisioned with Docker Compose (postgres + pgvector). The Supabase database was deleted by the user, so there is no live data to migrate — only schema. | User decision. |
| D3 | Retrieval index | Postgres + pgvector, reusing migrations 006/007 as-is (vector(768), generated `fts` with `to_tsvector('spanish', …)`, HNSW m=16/ef=64, RRF k=60 hybrid). | Supersedes an earlier SQLite answer that predated D2. Postgres is now mandatory, and 006/007 already implement the exact retrieval design. FTS5 cannot match Postgres Spanish stemming. |
| D4 | Auth | Own implementation in FastAPI: `users` table, argon2 password hashing, httpOnly JWT cookie. Replaces Supabase Auth (email/password + Google OAuth). | User decision; consistent with leaving Supabase. |
| D5 | Athlete metrics | Manual entry first: athlete declares FTP and available hours; CTL/ATL/TSB computed in the backend from manually loaded activities. Strava plugs into the same columns later. | User decision; prerequisite for testing rules 2/3 without OAuth. |
| D6 | Generator output | Validated structured JSON (blocks/steps/zones/duration) **plus** coach prose. If the JSON fails validation the request fails closed. | User decision; the schema gate is the actual anti-hallucination mechanism. |
| D7 | Verification | Rule validator + golden tests against the E1–E14 corpus and the knowledge base. | User decision. |
| D8 | Runtime | `uv` with Python 3.13 pinned (`requires-python = ">=3.13,<3.14"`). | The machine runs 3.14.5; 3.13 avoids wheel-availability risk across FastAPI/SQLAlchemy/asyncpg/pydantic while uv downloads a managed interpreter. |

---

## 3. Canonical domain model (design core)

### 3.1 Invariants

- **I1 — No absolute physiological targets in generated output.** The model emits zone codes and intent, never `bpm` or `watts`. Absolute values are derived deterministically from the athlete's declared FTP and HR zones. Rationale: the corpus's `@ 67 bpm` values belong to the source athlete and are meaningless for any other rider; letting the model emit them is the single most likely hallucination.
- **I2 — Closed zone vocabulary.** Zones resolve against the Coggan model documented in `knowledge-base/training/zonas-entrenamiento-potencia.md` (Z1–Z7 with %FTP ranges). Corpus labels (`Recovery`, `Aerobic`, `Tempo`, `SubThreshold`) map onto it; an unmapped label is an error, not a guess.
- **I3 — Provenance required.** Every generated workout carries `sources[]` with `source_file` values that must exist in the retrieved chunk set. A citation outside the retrieved set fails validation.
- **I4 — Fail closed.** Schema or rule failure produces an error response, never a partially valid plan.
- **I5 — Derived metrics are computed, not generated.** `total_duration` and `estimated_tss` are computed from the structure; if the model supplies them they are discarded and recomputed.
- **I6 — Free-text sessions are a first-class shape.** Corpus entries such as E2 (`SOLO DARSE UN PASEO… NO PASAR DE Z2`) are represented as `prescriptive: false` with a zone cap and a duration, not coerced into fake interval structures.

### 3.2 Shapes (indicative; final field names fixed in task T2)

- `ZoneCode` — `Z1`…`Z7`.
- `StepRole` — `warmup` | `active` | `recovery` | `cooldown` | `work` | `rest`.
- `CyclingStep` — `duration_s`, `role`, `target: {kind: "zone", zone: ZoneCode, intent: str | None}`.
- `CyclingBlock` — `role`, `steps[]`, `repeat_count`.
- `CyclingWorkout` — `id`, `name`, `sport="cycling"`, `objective`, `blocks[]`, `total_duration_s` (derived), `estimated_tss` (derived), `prescriptive`, `notes`, `sources[]`.
- `GymSet` — `reps`, `rir`, `load_pct_1rm | load_absolute`, `tempo`.
- `GymExercise` — `name`, `sets: GymSet[]`, `rest_s`.
- `GymBlock` — `name` (`TREN INFERIOR` / `TREN SUPERIOR` / `CORE`), `activation[]`, `exercises[]`, `core[]`.
- `TrainingPlan` — `weeks[]`, each with `workouts[]` and derived weekly load metrics.

---

## 4. Target architecture

```
backend/                      # uv project, Python 3.13
  pyproject.toml, uv.lock, .python-version
  src/cycloai/
    domain/                   # P1: schema, parsers, validators, zone model  (no infra)
    rag/                      # P3: ingestion port, retrieval service
    generator/                # P4: retrieve -> prompt -> structured+prose -> validate
    auth/                     # P5: users, argon2, JWT cookie
    db/                       # P2: engine, models, repositories
    api/                      # routers: auth, profiles, onboarding, chat, waitlist, plans, rag
  alembic/versions/           # P2: 9 Supabase migrations ported
  tests/                      # golden + rule tests
docker-compose.yml            # P2: postgres + pgvector
```

Next.js keeps its UI and calls FastAPI for data; `lib/supabase/*` is removed in P7.

---

## 5. Phases

| Phase | Content | Depends on |
| --- | --- | --- |
| **P1 (current)** | Domain core: schema, parsers, golden fixtures, validators, tests. No infrastructure. | nothing |
| P2 | Infra: docker compose + pgvector, engine, Alembic port of migrations 001–009, settings. | Docker Desktop running |
| P3 | RAG: ingestion port of `rag-index.ts`, retrieval port of `search_knowledge`, tests. | P2 |
| P4 | Generator: prompt assembly, structured+prose output, validator gate, `POST /generate`. | P1, P3 |
| P5 | Auth + profiles + onboarding port. | P2 |
| P6 | Chat + `conversations`/`messages` persistence port. | P5 |
| P7 | Waitlist port + Next.js rewire to FastAPI, removal of `lib/supabase/*`. | P5, P6 |

---

## 6. Phase 1 tasks

Test-first is applied to the pure-logic core. No TDD mode is configured in this harness, so this is a convention for P1, not a harness-enforced gate. Runner: `uv run pytest`. Linter: `uv run ruff check`.

| ID | Task | Acceptance criteria | Status |
| --- | --- | --- | --- |
| T1 | Scaffold `backend/` uv project: pyproject, ruff + pytest config, package layout, smoke test | `uv sync` succeeds; `uv run pytest` green; `uv run ruff check` clean | pending |
| T2 | Canonical domain schema (pydantic v2) for zones, steps, blocks, cycling workout, gym workout, plan | Unit tests cover valid and invalid instances; invariants I1/I5/I6 expressible in the model | pending |
| T3 | Zone model + corpus label mapping | `Zone 1: Recovery` → `Z1`, `Zone 2: Aerobic` → `Z2`, `Zone 3: Tempo` → `Z3`, `Zone 4: SubThreshold` → `Z4`; unknown label raises; Z1–Z7 %FTP bounds match the knowledge-base document | pending |
| T4 | Cycling corpus parser (`docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt`, E1–E14) → canonical JSON, plus committed golden fixtures | All 14 sections parse; `Repetir N veces` modelled; E2/E4 become `prescriptive: false`; fixture regeneration is diff-stable | pending |
| T5 | Gym corpus parser (`docs/gym.txt`) → canonical JSON, plus committed golden fixtures | The three blocks parse; `5x20-15-15-10-10` expands correctly; RIR, rest and tempo captured | pending |
| T6 | Cycling rule validator | Rejects absolute bpm/watts (I1), mismatched duration sum, missing warm-up/cool-down where required, unknown zone codes; TSS estimate within a documented band | pending |
| T7 | Gym rule validator | Requires sets/reps/RIR; rejects hypertrophy ranges for main lifts; enforces cycling-specific intent per prompt rule 6 | pending |
| T8 | Plan-level validator | Enforces weekly load progression limit (≤ +10% per prompt rule 4), recovery-week cadence, and TSB gating (rules 2/3) | pending |

---

## 7. Risks and review workload

| Risk | Mitigation |
| --- | --- |
| Program is large (7 phases, multiple areas) | Strict phase discipline; one work-unit commit per task; no phase starts before the previous one's acceptance criteria are met |
| Python 3.14 wheel gaps | Pin 3.13 via `uv` (D8) |
| Docker daemon currently stopped | P2 is explicitly blocked until the user starts Docker Desktop; P1 has no infra dependency |
| Two datastores temptation | Rejected by D3: Postgres holds both application data and the retrieval index |
| Golden fixtures could encode wrong assumptions | Fixtures are generated from the corpus and reviewed as part of the task commit; the parser never invents structure for free-text entries (I6) |
| Reviewer load | Each task is a bounded diff inside `backend/`; parsers and validators are pure functions with tests |

## 8. Open questions

1. Whether the Next.js `proxy.ts` session refresh is replaced by FastAPI-issued cookies directly or by a thin Next.js BFF proxy (decided in P7).
2. Whether Google OAuth is retained after D4 moves auth into FastAPI, or dropped in favour of email/password only (decided in P5).
3. Whether the corpus `docs/*.txt` files remain the source of truth for seed workouts or are converted once into canonical fixtures and retired (decided in T4/T5).
