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
