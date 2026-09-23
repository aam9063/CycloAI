"""Prompt-assembly tests for the generator (P4a) — no network, no database.

The properties under test are the prompt requirements of the phase:

- the athlete's OWN zone vocabulary only, never the other system's (the two
  systems are not interchangeable and no conversion exists);
- invariant I1 stated explicitly: absolute magnitudes forbidden, absolute
  targets derived by us from the declared threshold;
- the strict JSON shape carried with the canonical model's field names;
- retrieved knowledge embedded when present, and the knowledge section
  OMITTED CLEANLY (no dangling heading) when retrieval returns nothing;
- the CITABLE source identifiers of the retrieval result displayed verbatim,
  with the rule that "sources" may only contain those identifiers and must be
  EMPTY when no knowledge was provided;
- per-system unit vocabulary that never leaks across systems: a power
  athlete's prompt speaks watts/%FTP, a heart-rate athlete's speaks
  bpm/%LTHR, and neither unit appears in the other's prompt.
"""

from __future__ import annotations

import re

from cycloai.domain.zones import AthleteThresholds, TrainingSystem
from cycloai.generator.prompt import GenerationRequest, build_workout_prompt
from cycloai.rag.retrieval import RetrievedKnowledge

POWER_REQUEST = GenerationRequest(
    objective="Mejorar mi potencia general",
    thresholds=AthleteThresholds(TrainingSystem.POWER, ftp_watts=250.0),
    weekly_hours=8.0,
    gym_days_per_week=2,
    has_power_meter=True,
)

HEART_RATE_REQUEST = GenerationRequest(
    objective="Construir base aeróbica",
    thresholds=AthleteThresholds(TrainingSystem.HEART_RATE, lthr_bpm=160.0),
    weekly_hours=6.0,
)

#: No knowledge retrieved (or retrieval failed): empty text, NO citable ids.
NO_KNOWLEDGE = RetrievedKnowledge(text="", citation_ids=frozenset())

POWER_ONLY_CODES = ("Z5", "Z6", "Z7")
HEART_RATE_ONLY_CODES = ("Z5A", "Z5B", "Z5C")
SHARED_CODES = ("Z1", "Z2", "Z3", "Z4")


def test_prompt_shows_only_the_athletes_own_system_zones() -> None:
    power_prompt = build_workout_prompt(POWER_REQUEST, knowledge=NO_KNOWLEDGE)
    for code in (*SHARED_CODES, *POWER_ONLY_CODES):
        assert code in power_prompt, f"power prompt must show its own zone {code}"
    for code in HEART_RATE_ONLY_CODES:
        assert code not in power_prompt, f"heart-rate zone {code} leaked into a power prompt"

    heart_rate_prompt = build_workout_prompt(HEART_RATE_REQUEST, knowledge=NO_KNOWLEDGE)
    for code in (*SHARED_CODES, *HEART_RATE_ONLY_CODES):
        assert code in heart_rate_prompt, f"heart-rate prompt must show its own zone {code}"
    for code in POWER_ONLY_CODES:
        # A bare Z5/Z6/Z7 must be absent; \b keeps Z5 from matching inside Z5A.
        assert re.search(rf"\b{code}\b", heart_rate_prompt) is None, (
            f"power zone {code} leaked into a heart-rate prompt"
        )


def test_prompt_states_i1_and_that_we_derive_absolute_targets() -> None:
    for request in (POWER_REQUEST, HEART_RATE_REQUEST):
        prompt = build_workout_prompt(request, knowledge=NO_KNOWLEDGE)
        assert "NUNCA emitas magnitudes absolutas" in prompt
        assert "los deriva el sistema a partir del umbral declarado" in prompt
        assert "invariante I1" in prompt


def test_prompt_carries_the_json_shape_of_the_canonical_model() -> None:
    prompt = build_workout_prompt(POWER_REQUEST, knowledge=NO_KNOWLEDGE)
    for field in (
        '"prose"',
        '"workout"',
        '"blocks"',
        '"steps"',
        '"role"',
        '"duration"',
        '"kind": "zone"',
        '"intent"',
        '"rpe"',
        '"cadence"',
        '"repeat_count"',
        '"sources"',
        '"prescriptive"',
        '"zone_cap"',
        '"freeform_duration_s"',
    ):
        assert field in prompt, f"the JSON shape must carry the canonical field {field}"


def test_prompt_embeds_retrieved_knowledge_when_present() -> None:
    knowledge = RetrievedKnowledge(
        text="Fragmento: la carga semanal no debe subir más de un 10%.",
        citation_ids=frozenset({"guias/carga-semanal.md"}),
    )
    prompt = build_workout_prompt(POWER_REQUEST, knowledge=knowledge)
    assert "## BASE DE CONOCIMIENTO RELEVANTE" in prompt
    assert "<BASE_DE_CONOCIMIENTO>" in prompt
    assert knowledge.text in prompt


def test_prompt_shows_the_citable_identifiers_alongside_the_sources_rule() -> None:
    """The displayed ids ARE the values the gate accepts, shown verbatim."""
    knowledge = RetrievedKnowledge(
        text="Fragmento sobre zonas.",
        citation_ids=frozenset({"docs/b.md", "docs/a.md"}),
    )
    prompt = build_workout_prompt(POWER_REQUEST, knowledge=knowledge)
    assert "FUENTES CITABLES" in prompt
    assert "- docs/a.md" in prompt
    assert "- docs/b.md" in prompt
    # The shape example cites a REAL displayed id — never an invented path.
    assert '"sources": ["docs/a.md"]' in prompt
    # The superseded hardcoded example path is gone for good: it was itself an
    # invitation to cite a source the model was never shown.
    assert "zonas-entrenamiento-potencia.md" not in prompt


def test_prompt_states_sources_must_be_empty_without_knowledge() -> None:
    prompt = build_workout_prompt(POWER_REQUEST, knowledge=NO_KNOWLEDGE)
    # The example shape shows the EMPTY sources list...
    assert '"sources": []' in prompt
    # ...and the rule states the emptiness requirement explicitly.
    assert 'debe ser exactamente []' in prompt


def test_prompt_omits_the_knowledge_section_cleanly_when_retrieval_is_empty() -> None:
    prompt = build_workout_prompt(POWER_REQUEST, knowledge=NO_KNOWLEDGE)
    assert "## BASE DE CONOCIMIENTO RELEVANTE" not in prompt
    # The tag survives ONLY inside injection-safety rule 0, never as a section.
    assert prompt.count("<BASE_DE_CONOCIMIENTO>") == 1
    assert "</BASE_DE_CONOCIMIENTO>" not in prompt


def test_power_prompt_shows_watts_vocabulary_and_no_heart_rate_vocabulary() -> None:
    prompt = build_workout_prompt(POWER_REQUEST, knowledge=NO_KNOWLEDGE)
    assert "vatios" in prompt
    assert "% FTP" in prompt
    assert "FTP declarado: 250 vatios" in prompt
    # No heart-rate vocabulary may leak into a power athlete's prompt.
    assert "bpm" not in prompt
    assert "pulsaciones" not in prompt
    assert "LTHR" not in prompt


def test_heart_rate_prompt_shows_bpm_vocabulary_and_no_power_vocabulary() -> None:
    prompt = build_workout_prompt(HEART_RATE_REQUEST, knowledge=NO_KNOWLEDGE)
    assert "bpm" in prompt
    assert "% LTHR" in prompt
    assert "LTHR declarado: 160" in prompt
    # No power vocabulary may leak into a heart-rate athlete's prompt. This is
    # exactly where the superseded "work in watts" phrasing must not survive.
    assert "vatios" not in prompt
    assert "FTP" not in prompt
