"""Validation-gate tests for the generator (P4a) — no network, no database.

The gate's defining property is the ORDER: the RAW payload is validated with
``validate_cycling_payload`` BEFORE any domain-model parsing, because the
canonical model cannot hold ``bpm``/``watts`` fields (``extra="forbid"``) and
pydantic would discard an offending value before any model-level check could
see it. ``test_bpm_target_is_rejected_before_any_parsing`` asserts that order
DIRECTLY, by replacing the parse symbol in the pipeline module with a spy
that fails the test the moment parsing is attempted.

Everything else here covers the fail-closed contract: exactly one
findings-aware retry, no partially valid plan ever returned, non-JSON or
mis-shaped responses rejected with a clear finding. Provenance is checked
against the SAME retrieval result the prompt displayed (one
``RetrievedKnowledge`` value object feeds both), so a citation the prompt
ever showed is rejected as fabricated on the raw payload — and when
retrieval is empty or fails, ``sources`` must be EMPTY and the generation
still succeeds end to end (the regression guard for the display/check
contradiction found earlier).
"""

from __future__ import annotations

import json

from cycloai.domain.workout import CyclingWorkout
from cycloai.domain.zones import AthleteThresholds, TrainingSystem
from cycloai.generator import generate as generate_module
from cycloai.generator.generate import generate_workout
from cycloai.generator.prompt import GenerationRequest
from cycloai.rag.retrieval import RetrievedKnowledge

HEART_RATE_REQUEST = GenerationRequest(
    objective="Sesión de base aeróbica",
    thresholds=AthleteThresholds(TrainingSystem.HEART_RATE, lthr_bpm=160.0),
    weekly_hours=6.0,
)

KNOWLEDGE_FRAGMENT = "Fragmento: la carga semanal no debe subir más de un 10%."

#: The one source identifier the knowledge-bearing retrieves make citable —
#: and therefore the one value the prompt displays as citable.
PULSO_SOURCE = "knowledge-base/training/zonas-entrenamiento-pulso.md"


def make_envelope() -> dict:
    """A payload the gate must ACCEPT for a heart-rate athlete (LTHR 160)."""
    return {
        "prose": "Hoy toca rodar suave: escucha tu respiración y mantén el ritmo.",
        "workout": {
            "id": "sesion-base",
            "name": "Base aeróbica",
            "sport": "cycling",
            "objective": "Resistencia aeróbica",
            "prescriptive": True,
            "blocks": [
                {
                    "role": "warmup",
                    "repeat_count": 1,
                    "steps": [
                        {
                            "duration": {"kind": "minutes", "minutes": 15},
                            "role": "warmup",
                            "target": {
                                "kind": "zone",
                                "system": "heart_rate",
                                "zone": "Z1",
                                "intent": "suave",
                            },
                        }
                    ],
                },
                {
                    "role": "active",
                    "repeat_count": 1,
                    "steps": [
                        {
                            "duration": {"kind": "minutes", "minutes": 60},
                            "role": "active",
                            "target": {
                                "kind": "zone",
                                "system": "heart_rate",
                                "zone": "Z2",
                                "intent": "ritmo de conversación",
                            },
                            "cadence": {"min_rpm": 85, "max_rpm": 95},
                        }
                    ],
                },
                {
                    "role": "cooldown",
                    "repeat_count": 1,
                    "steps": [
                        {
                            "duration": {"kind": "minutes", "minutes": 10},
                            "role": "cooldown",
                            "target": {
                                "kind": "zone",
                                "system": "heart_rate",
                                "zone": "Z1",
                            },
                        }
                    ],
                },
            ],
            "notes": "Hidrátate cada 20 minutos.",
            "sources": [PULSO_SOURCE],
        },
    }


class FakeModel:
    """Injected model client: scripted responses, recorded prompts."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


async def empty_retrieve(query: str) -> RetrievedKnowledge:
    """No results at all: no text and NO citable identifiers."""
    return RetrievedKnowledge(text="", citation_ids=frozenset())


async def ok_retrieve(query: str) -> RetrievedKnowledge:
    """Knowledge WITH citable identifiers: the prompt displays PULSO_SOURCE."""
    return RetrievedKnowledge(text=KNOWLEDGE_FRAGMENT, citation_ids=frozenset({PULSO_SOURCE}))


async def failing_retrieve(query: str) -> RetrievedKnowledge:
    raise RuntimeError("database unavailable")


def finding_codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


async def test_valid_payload_passes_and_yields_model_plus_prose() -> None:
    """Citing a source the prompt actually displayed is accepted END TO END."""
    model = FakeModel(json.dumps(make_envelope(), ensure_ascii=False))
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=ok_retrieve)

    assert result.ok is True
    assert isinstance(result.workout, CyclingWorkout)
    assert result.prose == "Hoy toca rodar suave: escucha tu respiración y mantén el ritmo."
    assert result.workout.total_duration_s == (15 + 60 + 10) * 60
    assert result.knowledge_used is True
    assert result.attempts == 1
    assert all(finding.severity == "warning" for finding in result.findings)


async def test_bpm_target_is_rejected_before_any_parsing(monkeypatch) -> None:
    """The I1 gate must fire on the RAW payload, BEFORE the domain parse.

    The parse symbol in the pipeline module is replaced with a spy that
    records any attempt and fails loudly: if parsing ever ran first, pydantic
    would discard the bpm field and the I1 check could never see it — the
    exact vacuous-green future this ordering exists to prevent.
    """

    class ParseSpy:
        def __init__(self) -> None:
            self.called = False

        def model_validate(self, payload: dict) -> None:
            self.called = True
            raise AssertionError("domain parsing ran before raw-payload validation")

    bad = make_envelope()
    bad["workout"]["blocks"][1]["steps"][0]["target"]["bpm"] = 140
    bad_response = json.dumps(bad, ensure_ascii=False)

    spy = ParseSpy()
    monkeypatch.setattr(generate_module, "CyclingWorkout", spy)
    try:
        model = FakeModel(bad_response, bad_response)
        result = await generate_workout(
            HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve
        )
    finally:
        monkeypatch.undo()

    assert spy.called is False, "parsing must be unreachable while raw errors stand"
    assert result.ok is False
    assert result.workout is None
    assert "absolute_target_forbidden" in finding_codes(result)
    i1 = next(f for f in result.findings if f.code == "absolute_target_forbidden")
    assert i1.source == "raw_payload"
    assert i1.severity == "error"
    assert "bpm" in i1.message


async def test_unknown_zone_code_is_rejected() -> None:
    bad = make_envelope()
    bad["workout"]["blocks"][1]["steps"][0]["target"]["zone"] = "Z9"
    bad_response = json.dumps(bad, ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)

    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert "unresolvable_zone" in finding_codes(result)


async def test_non_json_response_is_rejected_with_a_clear_finding() -> None:
    model = FakeModel("Lo siento, no puedo generar una sesión hoy.", "Siguiendo tu indicación…")
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert "response_not_json" in finding_codes(result)


async def test_wrong_envelope_shape_is_rejected_with_a_clear_finding() -> None:
    model = FakeModel(json.dumps({"foo": "bar"}), json.dumps({"foo": "bar"}))
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert "response_shape_invalid" in finding_codes(result)


async def test_envelope_missing_prose_is_rejected() -> None:
    envelope = make_envelope()
    del envelope["prose"]
    response = json.dumps(envelope, ensure_ascii=False)
    model = FakeModel(response, response)

    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is False
    assert "response_shape_invalid" in finding_codes(result)


async def test_two_invalid_attempts_fail_closed_with_no_plan() -> None:
    bad = make_envelope()
    bad["workout"]["blocks"][1]["steps"][0]["target"]["zone"] = "Z9"
    bad_response = json.dumps(bad, ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)

    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert result.prose is None
    assert result.attempts == 2
    assert "retries_exhausted" in finding_codes(result)
    exhausted = next(f for f in result.findings if f.code == "retries_exhausted")
    assert "retry" in exhausted.message.lower()


async def test_retry_reprompts_with_the_concrete_findings() -> None:
    bad = make_envelope()
    bad["workout"]["blocks"][1]["steps"][0]["target"]["bpm"] = 140
    bad_response = json.dumps(bad, ensure_ascii=False)
    good_response = json.dumps(make_envelope(), ensure_ascii=False)
    model = FakeModel(bad_response, good_response)

    # ok_retrieve, not empty_retrieve: the good response cites PULSO_SOURCE,
    # which must be citable or the retry would be rejected as a fabricated
    # citation before ever succeeding.
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=ok_retrieve)

    assert result.ok is True
    assert result.attempts == 2
    assert len(model.prompts) == 2
    first, second = model.prompts
    assert second.startswith(first), "the retry must re-prompt over the original prompt"
    assert "INTENTO ANTERIOR RECHAZADO" in second
    # The concrete findings from the first attempt must be IN the retry prompt.
    assert "absolute_target_forbidden" in second
    assert "absolute physiological magnitude" in second


async def test_payload_passing_raw_gate_but_failing_model_parse_is_rejected() -> None:
    """Raw-valid, model-invalid: the canonical model is its own second gate."""
    bad = make_envelope()
    # minutes: 0 is invisible to the raw validator but violates the model.
    bad["workout"]["blocks"][1]["steps"][0]["duration"]["minutes"] = 0
    bad_response = json.dumps(bad, ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)

    # ok_retrieve: the payload's citation must pass the gate so the failure
    # under test is the MODEL PARSE, not a fabricated citation firing first.
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=ok_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert "workout_model_invalid" in finding_codes(result)


async def test_blank_workout_id_is_caught_by_the_model_level_rules() -> None:
    bad = make_envelope()
    bad["workout"]["id"] = "  "
    bad_response = json.dumps(bad, ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)

    # ok_retrieve: the citation must pass the gate so the blank-id finding is
    # produced by the MODEL-LEVEL rules, which is what this test asserts.
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=ok_retrieve)

    assert result.ok is False
    assert "blank_plan_id" in finding_codes(result)


async def test_retrieval_failure_does_not_fail_generation() -> None:
    """Regression guard: retrieval failed → no citable ids → sources EMPTY.

    The model correctly cites nothing; the generation still SUCCEEDS end to
    end. This is the end-to-end assertion of the contract that resolves the
    earlier contradiction (empty retrieval + mandatory non-empty sources).
    """
    envelope = make_envelope()
    envelope["workout"]["sources"] = []
    model = FakeModel(json.dumps(envelope, ensure_ascii=False))
    result = await generate_workout(
        HEART_RATE_REQUEST, model_client=model, retrieve=failing_retrieve
    )

    assert result.ok is True
    assert isinstance(result.workout, CyclingWorkout)
    assert result.workout.sources == []
    assert result.knowledge_used is False
    assert result.attempts == 1


async def test_empty_retrieval_does_not_fail_generation() -> None:
    """Regression guard: retrieval returned NOTHING → sources EMPTY, success."""
    envelope = make_envelope()
    envelope["workout"]["sources"] = []
    model = FakeModel(json.dumps(envelope, ensure_ascii=False))
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is True
    assert isinstance(result.workout, CyclingWorkout)
    assert result.workout.sources == []
    assert result.knowledge_used is False
    assert "BASE DE CONOCIMIENTO" not in model.prompts[0]


async def test_free_text_session_passes_the_gate() -> None:
    envelope = make_envelope()
    envelope["workout"] = {
        "id": "sesion-libre",
        "name": "Rodillo técnico",
        "sport": "cycling",
        "objective": "Soltería de pierna",
        "prescriptive": False,
        "zone_cap": "Z2",
        "freeform_duration_s": 3600,
        "sources": [],  # nothing was retrieved: citing anything would be fabricated
    }
    model = FakeModel(json.dumps(envelope, ensure_ascii=False))

    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is True
    assert result.workout is not None
    assert result.workout.prescriptive is False
    assert result.workout.total_duration_s == 3600


async def test_citing_an_unretrieved_source_is_rejected_with_a_finding_naming_it() -> None:
    """Knowledge was retrieved, but the model cites something OUTSIDE it."""

    async def other_retrieve(query: str) -> RetrievedKnowledge:
        return RetrievedKnowledge(
            text=KNOWLEDGE_FRAGMENT,
            citation_ids=frozenset({"knowledge-base/otro-documento.md"}),
        )

    bad_response = json.dumps(make_envelope(), ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=other_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert "unretrieved_source" in finding_codes(result)
    finding = next(f for f in result.findings if f.code == "unretrieved_source")
    assert finding.source == "raw_payload"
    assert finding.severity == "error"
    # The finding NAMES the fabricated citation value.
    assert PULSO_SOURCE in finding.message


async def test_empty_retrieval_with_a_citation_is_rejected_as_fabricated() -> None:
    """Nothing was retrieved, yet the model cites a source: fabricated."""
    bad_response = json.dumps(make_envelope(), ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)
    result = await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=empty_retrieve)

    assert result.ok is False
    assert result.workout is None
    assert "unretrieved_source" in finding_codes(result)
    finding = next(f for f in result.findings if f.code == "unretrieved_source")
    assert PULSO_SOURCE in finding.message


async def test_displayed_citable_ids_and_checked_citation_set_are_one_retrieval_result(
    monkeypatch,
) -> None:
    """The no-drift property, asserted DIRECTLY on the gate's citation_set.

    The whole point of the RetrievedKnowledge contract: the identifiers the
    prompt displays and the set the raw-payload gate checks are the SAME
    data, because both come from the ONE retrieval result. This test spies on
    ``validate_cycling_payload`` to capture what the gate actually received
    and compares it against what the prompt actually displayed.
    """
    captured: dict[str, set[str] | None] = {}
    real_validate = generate_module.validate_cycling_payload

    def spy(payload, *, thresholds=None, citation_set=None):
        captured["citation_set"] = citation_set
        return real_validate(payload, thresholds=thresholds, citation_set=citation_set)

    monkeypatch.setattr(generate_module, "validate_cycling_payload", spy)

    ids = frozenset({"docs/a.md", "docs/b.md"})

    async def retrieve(query: str) -> RetrievedKnowledge:
        return RetrievedKnowledge(text=KNOWLEDGE_FRAGMENT, citation_ids=ids)

    bad_response = json.dumps(make_envelope(), ensure_ascii=False)
    model = FakeModel(bad_response, bad_response)
    # The payload cites PULSO_SOURCE (not in ids) so the result fails closed;
    # what matters is that the gate RAN and we captured its citation set.
    await generate_workout(HEART_RATE_REQUEST, model_client=model, retrieve=retrieve)

    assert captured["citation_set"] == set(ids)
    prompt = model.prompts[0]
    # Every checked identifier is displayed verbatim in the prompt...
    for cid in sorted(ids):
        assert f"- {cid}" in prompt
    # ...and the shape example cites one of those very ids.
    assert '"sources": ["docs/a.md"]' in prompt
