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

**Corpus inventory**: `knowledge-base/` holds 21 Markdown documents across `training/` (8), `nutrition/` (6), `physiology/` (5), `gym/` (4), each with YAML front matter (`title`, `category`, `keywords`) and `##` sections. `docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt` holds **29 workouts separated by 25 `--` separators**: 5 labelled (E1, E3, E5 interval workouts with 7 bpm steps each; E2 and E4 free text — E2 carries one prose body line, E4's free text lives in its header line) plus 24 unlabelled sections with no header, each starting with a `Warm up` role line. **361 steps**: 329 with `@ N bpm` plus a zone label, 32 with `@ N RPE` and no zone (two unlabelled sections are RPE-only, 16 steps each — structured, NOT free text). 49 cadence lines (`N-N rpm` ×35, `Nrpm` ×14); roles are run-length encoded (319 role lines, 42 steps inherit); 80 `Repetir N veces` markers (semantics unresolved, see open questions). `docs/gym.txt` is a hand-written 61-line coach's list, not an export, and it is far less regular than the cycling corpus. Three blocks: `TREN INFERIOR` (with an `ACTIVACIÓN:` sub-section), `TREN SUPERIOR` and `CORE`, separated by two `--` lines. 19 exercises and 10 prose items, with **zero unparsed lines**: 1 title + 3 block headers + 1 section header + 2 separators + 19 exercises + 3 rest lines + 10 prose items = 39 non-blank lines out of 61. Exercise detection is by evidence (a set pattern or a step count), never by position, so prose is never coerced into a fake exercise. Irregularity the model and parser had to absorb: set tokens appear as `4x14`, as slash ranges (`3x8/10`, `3x10/12`) and as hyphen ramps (`5x20-15-15-10-10`), in both `x` and `X`; exercises appear as `Name: sets`, as `-Name--> sets,`, and once reps-first with no name or colon (`3x25 crunch abdomen`); one exercise counts steps rather than reps (`10 PASOS A CADA DIRECCIÓN`); RIR appears on only **3 of 19** exercises and once inside a parenthetical the author never closed; rest is Spanish notation (`´` minutes, `´´` seconds) meaning 90 s / 120 s / 120 s; and the whole `CORE` block is prose with no sets at all. Two documented judgment calls, both defended by the verifier: `4x25-30` is read as a four-set **range** (a two-value tail under a count of 4 has no precedent in this corpus, and every genuine ramp lists one value per declared set), and `5x12-12-10-10` emits **four** sets while the leading count says five, because the author's own note reads `LAS DOS PRIMERAS ... LAS DOS ÚLTIMAS` — a 2+2 partition that only covers four sets.

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
| D7 | Verification | Rule validator + golden tests against the cycling corpus (29 measured workouts) and the knowledge base. | User decision. |
| D8 | Runtime | `uv` with Python 3.13 pinned (`requires-python = ">=3.13,<3.14"`). | The machine runs 3.14.5; 3.13 avoids wheel-availability risk across FastAPI/SQLAlchemy/asyncpg/pydantic while uv downloads a managed interpreter. |
| D9 | Training system is chosen per athlete in onboarding | Onboarding asks **whether the athlete trains by heart rate or by power**. Heart rate is the default-facing option because a power meter is an expensive accessory many bikes do not have. If the athlete picks power, onboarding asks for **FTP** and the plan is prescribed in watts. If the athlete picks heart rate, onboarding asks for **LTHR** and the plan is prescribed in bpm. | Owner's decision, and it is the right shape: the zone system is an attribute of the athlete, not a global choice, so the same corpus can serve both. It resolves the two blockers below. A plan must never mix the two as if equivalent, and no HR-to-power conversion factor is used, because the relationship is individual and drifts. |

---

## 3. Canonical domain model (design core)

### 3.1 Invariants

- **I1 — No absolute physiological targets in generated output.** The model emits zone codes and intent, never `bpm` or `watts`. Absolute values are derived deterministically from the athlete's declared FTP and HR zones. Rationale: the corpus's `@ 67 bpm` values belong to the source athlete and are meaningless for any other rider; letting the model emit them is the single most likely hallucination.
- **I2 — Closed zone vocabulary.** The implemented closed set is Z1, Z2, Z3, Z4, Z5A, Z5B, Z5C (`cycloai.domain.zones.ZoneCode`) — a subset refinement of the Coggan model documented in `knowledge-base/training/zonas-entrenamiento-potencia.md`, whose %FTP bounds cover only Coggan Z1–Z5; the KB defines NO bounds for Z5A/Z5B/Z5C, so they are deliberately absent, not guessed. Corpus labels resolve only through `zone_from_label`; an unmapped label is an error, not a guess.
- **I3 — Provenance required.** Every generated workout carries `sources[]` with `source_file` values that must exist in the retrieved chunk set. A citation outside the retrieved set fails validation.
- **I4 — Fail closed.** Schema or rule failure produces an error response, never a partially valid plan.
- **I5 — Derived metrics are computed, not generated.** `total_duration` and `estimated_tss` are computed from the structure; if the model supplies them they are discarded and recomputed. **TSS is power-derived**, so `estimated_tss` accumulates ONLY zones of the power system: heart-rate steps, RPE steps, and the power zones Z6/Z7 (which `knowledge-base/training/zonas-entrenamiento-potencia.md` says TSS cannot quantify — Z6 is "difícil de estimar" and Z7 "no se cuantifica de manera adecuada con TSS o IF") all contribute zero and are reported in `tss_uncovered_target_count`, so a `0.0` is never mistaken for "no work was prescribed".
- **I6 — Free-text sessions are a first-class shape.** I6 remains the enforced shape for a typed free-text workout: the domain model's validator requires a `zone_cap` and a `freeform_duration_s` for any non-prescriptive workout. The corpus states neither for E2/E4, so the corpus parser deliberately does not fabricate them: it represents those entries with `workout=None` plus a `free_text` payload instead of a `CyclingWorkout` (`cycloai.domain.cycling_corpus`). Trade-off: free-text corpus entries are carried verbatim as text, not as validated `prescriptive: false` workouts.

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
| T1 | Scaffold `backend/` uv project: pyproject, ruff + pytest config, package layout, smoke test | `uv sync` succeeds; `uv run pytest` green; `uv run ruff check` clean | done (commit `9804cf0`); not reviewed/approved |
| T2 | Canonical domain schema (pydantic v2) for zones, steps, blocks, cycling workout, gym workout, plan | Unit tests cover valid and invalid instances; invariants I1/I5/I6 expressible in the model | done, extended in T4 with `RpeTarget`/`CadenceTarget` (commit `9804cf0` base); not reviewed/approved |
| T3 | Zone model + corpus label mapping | `Zone 1: Recovery` → `Z1`, `Zone 2: Aerobic` → `Z2`, `Zone 3: Tempo` → `Z3`, `Zone 4: SubThreshold` → `Z4`; unknown label raises; closed set Z1, Z2, Z3, Z4, Z5A, Z5B, Z5C | done (commit `9804cf0`); not reviewed/approved |
| T4 | Cycling corpus parser (`docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt`) → canonical JSON, plus committed golden fixtures | All 29 workouts parse; 361 steps (329 bpm/zone, 32 RPE); 49 cadence steps; 42 role-inherited steps; 80 `Repetir N veces` markers captured structurally; `unparsed == []`; fixture regeneration byte-identical | implemented (uncommitted worktree, pending review); `Repetir` semantics unresolved (see open questions); Z5C TSS uses the Coggan Z5 midpoint 107.5 as a documented proxy |
| T5 | Gym corpus parser (`docs/gym.txt`) → canonical JSON, plus committed golden fixtures | The three blocks parse; `5x20-15-15-10-10` expands correctly; RIR, rest and tempo captured | done — parser + 36 tests + 3 fixtures in this task's work unit; 172 tests green; line accounting balances exactly; verified independently and the two judgment calls were defended on corpus evidence; not reviewed/approved |
| T6 | Cycling rule validator | **Measured design, which replaced the originally planned rules.** (1) Rejects absolute bpm/watts (I1) — and this must validate the RAW generator payload, not the canonical model, because the model has no such fields and a model-level check would be vacuous. (2) Warm-up and cool-down roles required: measured 0 violations across the 27 prescriptive corpus workouts, so it is safe as a hard error. (3) Every zone must resolve against the athlete's declared system and threshold (enabled by T9). (4) Workouts carrying `Repetir` markers warn that their duration and therefore their TSS are unreliable, because the markers are captured but never expanded: 24 of the 27 prescriptive workouts are affected. (5) Provenance (`sources`) must be present and non-empty (I3). The originally planned "duration sum matches" rule was measured to be VACUOUS — `total_duration_s` IS that sum, so comparing them can never fail — and is dropped rather than kept as decoration | done — `cycling_rules.py` (494 lines) + 24 tests; the I1 rule lives on the RAW payload because a model-level check would be vacuous, and it does not false-positive on the legitimate `"system": "heart_rate"` value (detection is by key name, with a test named for exactly that); unresolvable zones delegate to `resolve_target` rather than reimplementing it, so the "no conversion exists" reasoning stays in one place, and the rule is reported as not-evaluated when no thresholds are supplied. Measured on the real corpus: 25 of 29 workouts reject under a power athlete (the exceptions are the 2 free-text and 2 RPE-only sessions) and 24 carry the `Repetir` warning. Committed as `709dc2e` |
| T7 | Gym rule validator | Sets and reps required; **RIR must be optional** (it appears on only 3 of 19 exercises); rest in seconds; **errors only for structural defects**, and an unknown exercise name is a **warning, not a rejection** (decision: the knowledge base documents 6 exercises and the corpus 19 and they barely share names, so failing closed on unknown names would reject legitimate content today); **no hypertrophy-range rule** (measured and discarded: 7 of 19 exercises legitimately exceed 12 reps, including a 20-rep warm-up set on the leg press and 25-30 rep abdominal work) | done — `gym_rules.py` + 20 tests; the corpus yields 0 errors and exactly 16 `no_intensity_anchor` warnings; verified independently (exclusion list audited heading by heading, all 17 correct; alias map and rule reachability confirmed); known follow-up T7b below |
| T7b | Index knowledge-base heading short forms so the vocabulary matches how an exercise is actually named | A generated name using the bare short form (parenthetical stripped, alternate-after-`o` split, `y sus variaciones` dropped) resolves with no `unknown_exercise_name` warning, while a genuinely invented name still warns. Motivated by independent verification: headings are keyed verbatim, so `Pallof press` does not match `Pallof Press (anti-rotación)` and produces a false warning | pending |
| T8 | Plan-level validator | Enforces weekly load progression limit (≤ +10% per prompt rule 4), recovery-week cadence, and TSB gating (rules 2/3) | done — `plan_rules.py` + 19 boundary tests; the load metric is now DECLARED (`"hours"` or `"tss"`) instead of assumed, which resolves the residue honestly: a plan is never compared across metrics, and TSS over a plan containing heart-rate or perceived-exertion prescriptions WARNS that the load figure is incomplete rather than faking precision. No HR-to-power conversion exists. The sustained-debt variant of the TSB rule is reported as NOT EVALUATED (it needs a per-week history; metrics are manual per D5), so silence never reads as a pass. Thresholds are sourced: 10% and 3:1 and the 30-50% unload band from `principios-periodizacion-ciclismo.md`, TSB -25 from `plan-base-aerobica-16-semanas.md`, TSB -20/+15 from the system prompt. High-intensity detection verified against real corpus workouts (12 of them contain Z5+ steps), not only synthetic ones |
| T9 | Zone reference carries its training system, and the athlete declares either FTP or LTHR | A zone reference cannot be interpreted without knowing its system (`Z2` is a power band in one model and a heart-rate band in the other); an athlete declares exactly one system and supplies the matching threshold (FTP for power, LTHR for heart rate); resolution to an absolute target uses only the declared system, and no HR-to-power conversion exists. Motivated by decision D9 and required before T6 can derive targets for the corpus's heart-rate zones | done — `zones.py` now holds two 7-zone tables keyed by `(system, code)`, with `ZoneRef`, `AthleteThresholds`, `ResolvedTarget` and `resolve_target`; `ZoneTarget.system` is REQUIRED with no default and validates the pair; the corpus parser declares `heart_rate`; 227 tests green and the 29 fixtures changed by pure insertion of the system field (0 unintended changes, verified at byte level). Verified independently: the merge-back detector is the assertion that Z1-Z4 have different bounds per system, no conversion helper or %FTP↔%LTHR arithmetic exists anywhere, and no assertion was weakened |
| T9b | System-aware TSS, so a heart-rate prescription stops inheriting power-model numbers | Two coupled fixes established by verification. (1) `estimated_tss` keys its TSS/hour midpoints on the bare zone code, ignoring `step.target.system`, and the midpoints come from the POWER document, so a heart-rate session's TSS is computed from power-model numbers (and Z5A/Z5B/Z5C all collapse to one Coggan-Z5 midpoint); the pulse document contains no TSS data at all, so there is no honest substitute until an HR-based load is defined. (2) The `load_metric_mismatch` guard in `plan_rules` takes its count as a caller-supplied parameter defaulting to 0 and never derives it from `ZoneTarget.system`, which now exists — so the guard currently covers nothing automatically. Acceptance: the non-power count is derived from the zone targets rather than trusted from the caller, and a heart-rate prescription either carries no power-derived TSS or is explicitly marked as not applicable | done — `estimated_tss` accumulates only power-system zones and the new `tss_uncovered_target_count` reports the excluded targets so a 0.0 is never read as "no work prescribed"; `plan_rules` now DERIVES the non-power count from the plan, so the guard warns with nothing supplied by the caller; the POWER Z5/Z6/Z7 `KeyError` is fixed (Z5 gains the documented 107.5; Z6/Z7 count as uncovered because the knowledge base says TSS cannot quantify them, so no midpoint was invented). Two tests that encoded the defect were rewritten, not deleted. Committed as `148fd81` |
| T9c | Give `CyclingWorkout.zone_cap` a training system | `zone_cap` is still a bare `ZoneCode`, the same bug class T9 fixed: a cap of `Z4` cannot be interpreted without knowing whether it means 91-105 %FTP or 94-99 %LTHR. Nothing computes with it today, so this is latent rather than active. Acceptance: the cap carries its system and the shape validators keep their current behaviour for the corpus | pending |

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

0. **Open decision blocking the generator (reopened and reframed).** The earlier framing — "the knowledge base defines %FTP bounds only for Coggan Z1–Z5, not for Z5A/Z5B/Z5C" — was WRONG and is superseded. The real finding is an **incompatible-model problem, not a missing table**: the cycling corpus is anchored to **heart rate** (every target is in `bpm`) and uses a 7-band structure of 4 zones plus `5A/5B/5C`, while the knowledge base is anchored to **power** (`%FTP`, Coggan Z1–Z7, no sub-zones at all). The 4-plus-3 structure and the corpus's Zone 4 band (139–145 bpm, i.e. 95–99% of an implied threshold near 146 bpm) match Joe Friel's LTHR model, whose Zone 4 is documented as 94–99% of LTHR for cycling. Sources and book editions vary in the label words (one table labels 5a `VO2max` rather than `SuperThreshold`), so the identification is "same LTHR family, wording varies", not settled.

   Consequences that must be decided together:
   - **(a) Zone system discriminator.** A zone code alone is ambiguous: `Z2` can mean a power band or a heart-rate band. `ZoneTarget` should record which system it belongs to. No external input needed; this is a design fix.
   - **(b) Athlete LTHR.** Deriving an absolute target for a corpus zone needs the athlete's threshold heart rate. `profiles` has `ftp_estimated` and no LTHR field, so the product collects no such input today.
   - **(c) Knowledge-base heart-rate zones.** Generation cannot prescribe the corpus's zones until the knowledge base carries a heart-rate/LTHR zone model with those bands. This is authoring domain content: the measured bands above are the anchor, plus the citable 94–99% LTHR rule for Zone 4. Owner's call; a sourced draft can be prepared for review.
   - **(d) No mechanical HR-to-power conversion.** The relationship is individual and shifts with fitness, so a fixed conversion factor would be fabricated precision — the exact failure mode I1 exists to prevent.
   - **(e) The load metric.** TSS is derived from power, but the corpus prescribes heart rate, so weekly load cannot be computed as TSS without power data. T8's progression rule therefore needs a decided metric first: an HR-based load (hrTSS / TRIMP) or power data from the athlete. This is a separate decision from (a)–(d).
   - **(f) RPE steps need none of the above.** 32 of 361 steps carry RPE and no zone; RPE is a perception scale by construction, so no absolute derivation applies and none is fabricated.

   **RESOLVED by D9, with a residue.** The owner's insight settles (b) and (a): the training system is an attribute of the ATHLETE, chosen in onboarding, so onboarding collects **either FTP (power) or LTHR (heart rate)** and the plan is prescribed in that system. (a) therefore stops being an open question and becomes an implementation requirement: a zone reference must carry its system, because `Z2` is a power band in one model and a heart-rate band in the other. (d) stands as closed. (f) stands as closed. (c) is advanced but not finished: `knowledge-base/training/zonas-entrenamiento-pulso.md` now documents the seven LTHR bands with the measured corpus instance and the cited source, so the retrieval side has the content; what remains is the domain/model work to consume it. The residue is (e): the load metric must still be chosen, and D9 narrows it rather than removing it — a power athlete's load is TSS as usual, while a heart-rate athlete needs an HR-based load (hrTSS or TRIMP), and T8's progression rule cannot be written before that choice.
1. **`Repetir N veces` semantics remain UNRESOLVED (T4).** The exporter emits repeated groups textually more than once AND places the marker after them, so it is unclear whether the marker closes a repeated group or states a repetition count. T4 captures the marker structurally (count + step index) without interpreting it; every parsed block keeps `repeat_count = 1`.
2. Whether the Next.js `proxy.ts` session refresh is replaced by FastAPI-issued cookies directly or by a thin Next.js BFF proxy (decided in P7).
3. Whether Google OAuth is retained after D4 moves auth into FastAPI, or dropped in favour of email/password only (decided in P5).
4. Whether the corpus `docs/*.txt` files remain the source of truth for seed workouts or are converted once into canonical fixtures and retired (decided in T4/T5).
