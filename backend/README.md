# CycloAI backend

Python backend for CycloAI: FastAPI owns auth, profiles, onboarding, chat persistence,
RAG retrieval and grounded training generation (Next.js becomes frontend-only).

## Commands

```bash
uv sync            # create/refresh the venv (Python 3.13, managed by uv)
uv run pytest      # run the test suite
uv run ruff check  # lint
```

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
- **I2 — Closed zone vocabulary.** Zones are the closed corpus set
  (Z1, Z2, Z3, Z4, Z5A, Z5B, Z5C) defined in `domain/zones.py`, a subset refinement
  of the Coggan model in `knowledge-base/training/zonas-entrenamiento-potencia.md`.
  Mapping is keyed on the parsed zone code token (`Zone 2: Aerobic` vs
  `Zone 5B: Aerobic` share the descriptor `Aerobic`); unknown codes, ambiguous bare
  descriptors and mismatched code/descriptor pairs raise dedicated `ZoneError`
  subclasses instead of being guessed. The KB document defines no %FTP bounds for
  the Z5A/Z5B/Z5C sub-zones; they stay absent rather than invented.
- **I3 — Provenance required.** Generated workouts carry non-empty `sources[]`.
- **I4 — Fail closed.** Schema or rule failure is an error, never a partially valid plan.
- **I5 — Derived metrics are computed.** `total_duration_s` and `estimated_tss` are
  `@computed_field` properties derived from the structure; they are not caller inputs.
  Step durations keep the three corpus forms (`N min`, `N sec`, `mm:ss`) as a
  discriminated union instead of normalising them away.
- **I6 — Free-text sessions are first-class.** `prescriptive: false` sessions carry a
  zone cap plus a duration and must not carry fabricated interval blocks.
