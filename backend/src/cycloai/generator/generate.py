"""Workout generation pipeline (phase P4a): retrieve → prompt → model → gate.

The pipeline order IS the design:

1. The athlete's declared training system and threshold come in as one
   :class:`~cycloai.domain.zones.AthleteThresholds`.
2. Knowledge is retrieved through the INJECTED ``retrieve`` callable, which
   yields ONE :class:`~cycloai.rag.retrieval.RetrievedKnowledge` value object
   (display text plus citable identifiers). Any failure or empty result
   degrades to an empty-text/empty-ids object and never fails generation —
   the same never-throw contract as
   :func:`cycloai.rag.search.search_knowledge_base`, re-guarded here because
   the callable is caller-supplied.
3. The prompt is built per athlete (own system's zones only, I1 stated).
4. The model is called through the INJECTED ``model_client`` callable.
5. The RAW payload is validated with
   :func:`cycloai.domain.cycling_rules.validate_cycling_payload` BEFORE any
   domain-model parsing. This ordering is the only genuine enforcement point
   of invariant I1: the ``CyclingWorkout`` model cannot hold ``bpm``/``watts``
   fields (``extra="forbid"``), so pydantic would discard an offending value
   before any model-level check could see it. Validating after parsing would
   be vacuously green forever. ``_run_attempt`` makes the order structural:
   the parse call is unreachable while the raw report carries errors.

   The gate also receives the citation set, and DELIBERATELY the same one
   the prompt displayed: the prompt text and the citation set are derived
   from the SAME ``RetrievedKnowledge`` retrieval result, so they cannot
   drift apart. A display set that differs from the checked set is exactly
   how the earlier bug happened — the prompt rendered chunks under
   ``metadata.title`` while the gate checked ``source_file``, so the model
   was asked to cite something it was NEVER shown and every honest citation
   was rejected as unretrieved. An unretrieved citation is therefore caught
   on the RAW payload together with the other I1/I3 findings, before any
   parsing; when nothing was retrieved the set is empty and ``sources`` must
   be empty.
6. Only then the payload is parsed into the canonical model, and validated
   again at model level with the plan rule validators (TSB gating and
   friends, warnings advisory, errors blocking).
7. On any failure the model is retried ONCE with the concrete findings, then
   the service FAILS CLOSED: ``GenerationResult.workout`` is ``None``, the
   findings say why, and a final ``retries_exhausted`` finding names the
   exhaustion. A caller distinguishes "the model produced something invalid
   twice" (``ok=False``, findings present) from "the request was fine and
   there was no knowledge" (``ok=True``, ``knowledge_used=False``).

Both injected callables keep the whole pipeline testable without network or
database; only a live run wraps the real retrieval and a real model client.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError

from cycloai.domain.cycling_rules import CyclingValidationReport, validate_cycling_payload
from cycloai.domain.plan_rules import AthleteLoadState, PlanValidationReport, validate_training_plan
from cycloai.domain.workout import CyclingWorkout, PlanWeek, TrainingPlan
from cycloai.generator.prompt import GenerationRequest, build_workout_prompt
from cycloai.rag.retrieval import RetrievedKnowledge

__all__ = [
    "MAX_ATTEMPTS",
    "GenerationFinding",
    "GenerationResult",
    "ModelClient",
    "RetrieveFn",
    "build_retry_prompt",
    "generate_workout",
]

#: The model client contract: prompt text in, raw model text out.
ModelClient = Callable[[str], Awaitable[str]]

#: The retrieval contract: query text in, ONE retrieval result out — the
#: rendered knowledge text AND the citable identifiers, derived together so
#: the prompt cannot display a citation the gate would reject.
RetrieveFn = Callable[[str], Awaitable[RetrievedKnowledge]]

#: The no-knowledge result: no text, no citable sources. ``sources`` must
#: then be empty and any citation is fabricated.
EMPTY_KNOWLEDGE = RetrievedKnowledge(text="", citation_ids=frozenset())

#: One initial attempt plus exactly one findings-aware retry.
MAX_ATTEMPTS = 2

#: Where a finding came from, so a caller can tell a model-response problem
#: from a domain-rule problem without re-deriving it.
SOURCE_MODEL_RESPONSE = "model_response"
SOURCE_RAW_PAYLOAD = "raw_payload"
SOURCE_MODEL_RULES = "model_rules"


@dataclass(frozen=True, slots=True)
class GenerationFinding:
    """One gate finding, normalised across the three validation layers.

    ``source`` is one of ``model_response`` (the reply was not usable JSON in
    the required envelope), ``raw_payload`` (a finding of the raw cycling
    validator, taken verbatim) or ``model_rules`` (a finding of the plan rule
    validators on the parsed model). ``severity`` is ``"error"`` or
    ``"warning"``; only errors block, warnings ride along for observability.
    """

    source: str
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """The structured result AND the prose AND the findings, always.

    On success ``ok`` is True and ``workout``/``prose`` are populated (with
    advisory findings, if any). On failure ``ok`` is False and ``workout`` is
    None: never a partially valid plan, never silently dropped invalid parts.
    """

    ok: bool
    workout: CyclingWorkout | None
    prose: str | None
    findings: list[GenerationFinding] = field(default_factory=list)
    knowledge_used: bool = False
    attempts: int = 0


def _location_prefix(block_index: int | None, step_index: int | None) -> str:
    if block_index is None:
        return ""
    if step_index is None:
        return f"[block {block_index}] "
    return f"[block {block_index}, step {step_index}] "


def _findings_from_cycling_report(report: CyclingValidationReport) -> list[GenerationFinding]:
    """Normalise the raw validator's findings (errors AND warnings)."""
    out: list[GenerationFinding] = []
    for finding in (*report.errors, *report.warnings):
        prefix = _location_prefix(finding.block_index, finding.step_index)
        out.append(
            GenerationFinding(
                source=SOURCE_RAW_PAYLOAD,
                code=finding.code,
                severity=finding.severity.value,
                message=f"{prefix}{finding.message}",
            )
        )
    return out


def _findings_from_plan_report(report: PlanValidationReport) -> list[GenerationFinding]:
    out: list[GenerationFinding] = []
    for finding in (*report.errors, *report.warnings):
        week = f"[week {finding.week}] " if finding.week is not None else ""
        out.append(
            GenerationFinding(
                source=SOURCE_MODEL_RULES,
                code=finding.code,
                severity=finding.severity.value,
                message=f"{week}{finding.message}",
            )
        )
    return out


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\s*|\s*```$")


def _strip_code_fences(text: str) -> str:
    """Defensively drop a single surrounding Markdown code fence, if any."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    return _FENCE_RE.sub("", stripped).strip()


@dataclass(frozen=True, slots=True)
class _ParsedResponse:
    payload: dict
    prose: str


def _parse_model_response(text: str) -> _ParsedResponse | list[GenerationFinding]:
    """Parse the model reply into ``(payload, prose)`` or clear findings.

    A malformed or non-JSON response is a validation failure with a clear
    finding, never an exception escaping the service.
    """
    try:
        data = json.loads(_strip_code_fences(text))
    except json.JSONDecodeError as err:
        return [
            GenerationFinding(
                source=SOURCE_MODEL_RESPONSE,
                code="response_not_json",
                severity="error",
                message=(
                    "the model response is not valid JSON: "
                    f"{err.msg} (line {err.lineno}, column {err.colno})"
                ),
            )
        ]
    if not isinstance(data, dict):
        return [
            GenerationFinding(
                source=SOURCE_MODEL_RESPONSE,
                code="response_shape_invalid",
                severity="error",
                message=(
                    "the model response must be a JSON object with 'prose' and "
                    f"'workout' keys; got {type(data).__name__} instead"
                ),
            )
        ]
    prose = data.get("prose")
    payload = data.get("workout")
    problems: list[str] = []
    if not isinstance(prose, str) or not prose.strip():
        problems.append("'prose' must be a non-empty string")
    if not isinstance(payload, dict):
        problems.append("'workout' must be a JSON object")
    if problems:
        return [
            GenerationFinding(
                source=SOURCE_MODEL_RESPONSE,
                code="response_shape_invalid",
                severity="error",
                message="the model response envelope is invalid: " + "; ".join(problems),
            )
        ]
    return _ParsedResponse(payload=payload, prose=prose)


def _model_level_findings(
    workout: CyclingWorkout, request: GenerationRequest
) -> list[GenerationFinding]:
    """Rule validators on the PARSED model, wrapped as a one-week plan.

    The plan-level validators own the TSB gating and load rules; a single
    generated session is validated as a one-week plan in the always-derivable
    ``hours`` metric (never the power-derived TSS metric, which would warn
    about this plan's own heart-rate prescriptions). The athlete state is
    only supplied when the caller gave all three metrics; otherwise the TSB
    rules land in ``not_evaluated`` instead of passing silently, which is the
    validator's own contract and does not block.
    """
    plan = TrainingPlan(id=workout.id, weeks=[PlanWeek(number=1, workouts=[workout])])
    athlete_state = None
    if None not in (request.ctl, request.atl, request.tsb):
        athlete_state = AthleteLoadState(
            ctl=float(request.ctl), atl=float(request.atl), tsb=float(request.tsb)
        )
    report = validate_training_plan(plan, load_metric="hours", athlete_state=athlete_state)
    return _findings_from_plan_report(report)


def _retrieval_query(request: GenerationRequest) -> str:
    parts = [request.objective, request.guidance or "", request.target_event or ""]
    return " ".join(part.strip() for part in parts if part and part.strip())


async def _retrieve_knowledge(
    request: GenerationRequest, retrieve: RetrieveFn | None, log: Callable[[str], None]
) -> RetrievedKnowledge:
    """Retrieve knowledge for the request, degrading to EMPTY on ANY failure."""
    query = _retrieval_query(request)
    if retrieve is None or not query:
        return EMPTY_KNOWLEDGE
    try:
        result = await retrieve(query)
    except Exception as err:  # noqa: BLE001 - the contract is retrieval NEVER fails generation
        log(f"[generator] knowledge retrieval failed, continuing without it: {err}")
        return EMPTY_KNOWLEDGE
    if isinstance(result, str):
        # Legacy adapters that predate the citable-set contract: they supply
        # display text but NO verified citation identifiers, so the knowledge
        # is shown without a citation permission set and the gate (fed an
        # empty set) requires empty sources — fail closed, never an impossible
        # citation demand.
        return RetrievedKnowledge(text=result, citation_ids=frozenset())
    return result


def build_retry_prompt(previous_prompt: str, findings: Sequence[GenerationFinding]) -> str:
    """Re-prompt with the concrete validation findings from the failed attempt."""
    lines = "\n".join(f"- [{finding.code}] {finding.message}" for finding in findings)
    return (
        f"{previous_prompt}\n"
        "\n"
        "## INTENTO ANTERIOR RECHAZADO\n"
        "Tu respuesta anterior fue rechazada por el validador por estas razones "
        "concretas:\n"
        f"{lines}\n"
        "\n"
        "Corrige EXACTAMENTE esos problemas y responde de nuevo con el objeto JSON "
        "completo y válido, bajo las mismas reglas de formato. No devuelvas nada fuera "
        "del JSON."
    )


async def _run_attempt(
    prompt: str,
    request: GenerationRequest,
    model_client: ModelClient,
    citation_set: set[str],
) -> tuple[_ParsedResponse | None, CyclingWorkout | None, list[GenerationFinding]]:
    """One prompt → model → gate pass. NEVER parses while raw errors stand.

    The gate order is structural: raw-payload validation runs first and its
    errors short-circuit BEFORE ``CyclingWorkout.model_validate`` is reached,
    so an absolute magnitude is always seen by the raw validator and never
    silently discarded by pydantic first. ``citation_set`` is the set of
    citable identifiers the PROMPT displayed (see the module docstring: same
    retrieval result, deliberately), so a fabricated citation is caught here
    on the raw payload, before any parsing.
    """
    response = await model_client(prompt)
    parsed = _parse_model_response(response)
    if isinstance(parsed, list):
        return None, None, parsed

    # STEP 5 — validate the RAW payload FIRST, before parsing into the model.
    report = validate_cycling_payload(
        parsed.payload, thresholds=request.thresholds, citation_set=citation_set
    )
    if not report.ok:
        return None, None, _findings_from_cycling_report(report)

    # STEP 6 — only now build the canonical model...
    try:
        workout = CyclingWorkout.model_validate(parsed.payload)
    except ValidationError as err:
        return (
            None,
            None,
            [
                GenerationFinding(
                    source=SOURCE_MODEL_RULES,
                    code="workout_model_invalid",
                    severity="error",
                    message="the payload does not satisfy the canonical model: "
                    f"{err.error_count()} error(s); first: "
                    + str(err.errors()[0].get("msg", err)),
                )
            ],
        )

    # ...and validate again at model level with the rule validators.
    rule_findings = _model_level_findings(workout, request)
    errors = [finding for finding in rule_findings if finding.severity == "error"]
    if errors:
        return None, None, errors
    return parsed, workout, rule_findings


async def generate_workout(
    request: GenerationRequest,
    *,
    model_client: ModelClient,
    retrieve: RetrieveFn | None = None,
    log: Callable[[str], None] = print,
) -> GenerationResult:
    """Generate one validated cycling workout plus coach prose, fail closed.

    Args:
        request: the athlete's declared data (system + threshold included).
        model_client: the INJECTED model callable; tests inject a fake.
        retrieve: the INJECTED retrieval callable yielding ONE
            :class:`~cycloai.rag.retrieval.RetrievedKnowledge` (text plus the
            citable identifiers); ``None`` or a failure simply means no
            knowledge section. Never fails generation.
        log: sink for the retrieval degradation note.

    Returns:
        A :class:`GenerationResult` that always carries findings. After the
        one retry is exhausted the result fails closed with a final
        ``retries_exhausted`` finding.
    """
    knowledge = await _retrieve_knowledge(request, retrieve, log)
    knowledge_used = bool(knowledge.text.strip())
    prompt = build_workout_prompt(request, knowledge)

    findings: list[GenerationFinding] = []
    attempts = 0
    for _attempt in range(MAX_ATTEMPTS):
        attempts += 1
        parsed, workout, attempt_findings = await _run_attempt(
            prompt, request, model_client, set(knowledge.citation_ids)
        )
        if parsed is not None and workout is not None:
            # Success: raw warnings and advisory model-rule findings ride along.
            return GenerationResult(
                ok=True,
                workout=workout,
                prose=parsed.prose,
                findings=attempt_findings,
                knowledge_used=knowledge_used,
                attempts=attempts,
            )
        findings.extend(attempt_findings)
        prompt = build_retry_prompt(prompt, attempt_findings)

    findings.append(
        GenerationFinding(
            source=SOURCE_MODEL_RESPONSE,
            code="retries_exhausted",
            severity="error",
            message="generation failed closed: the model produced an invalid response on "
            "the initial attempt AND on the one retry; no plan is returned",
        )
    )
    return GenerationResult(
        ok=False,
        workout=None,
        prose=None,
        findings=findings,
        knowledge_used=knowledge_used,
        attempts=attempts,
    )
