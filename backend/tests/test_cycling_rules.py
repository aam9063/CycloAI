"""Tests for the cycling rule validator (task T6).

Measured corpus expectations pinned here:

- The 27 structured (prescriptive) parsed corpus workouts ALL carry both a
  warm-up and a cool-down role, so ``missing_warmup``/``missing_cooldown``
  have zero false positives on real corpus data.
- Exactly 24 of those 27 carry ``Repetir N veces`` markers, so exactly 24
  ``repeat_duration_unreliable`` warnings fire across the corpus.
- The corpus is heart-rate anchored: under a POWER athlete's thresholds every
  corpus zone is unresolvable (``resolve_target`` raises
  ``MissingThresholdError``; there is deliberately no conversion), and under
  a heart-rate athlete's thresholds everything resolves.

The false-positive guard for ``absolute_target_forbidden`` is explicit: the
legitimate system identifier ``"system": "heart_rate"`` is a VALUE under the
``system`` key and must never be read as a magnitude.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cycloai.domain.cycling_corpus import (
    CORPUS_FILENAME,
    ParsedCorpus,
    parse_cycling_corpus_file,
)
from cycloai.domain.cycling_rules import (
    CyclingValidationReport,
    Severity,
    validate_cycling_payload,
    validate_parsed_workout,
)
from cycloai.domain.workout import ZoneTarget
from cycloai.domain.zones import AthleteThresholds, TrainingSystem

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "docs" / CORPUS_FILENAME

HR_ATHLETE = AthleteThresholds(system=TrainingSystem.HEART_RATE, lthr_bpm=160.0)
POWER_ATHLETE = AthleteThresholds(system=TrainingSystem.POWER, ftp_watts=250.0)

CORPUS_SOURCE = f"docs/{CORPUS_FILENAME}"


@pytest.fixture(scope="module")
def corpus() -> ParsedCorpus:
    return parse_cycling_corpus_file(CORPUS_PATH)


def _step(
    role: str,
    system: str = "heart_rate",
    zone: str = "Z2",
    **target_extra,
) -> dict:
    target = {"kind": "zone", "system": system, "zone": zone}
    target.update(target_extra)
    return {
        "duration": {"kind": "minutes", "minutes": 10},
        "role": role,
        "target": target,
    }


def _hr_payload() -> dict:
    """A well-formed prescriptive heart-rate payload (provenance + roles)."""
    return {
        "id": "cycling-test",
        "name": "Test session",
        "objective": "Aerobic base",
        "prescriptive": True,
        "sources": [CORPUS_SOURCE],
        "blocks": [
            {"role": "warmup", "steps": [_step("warmup", zone="Z1")]},
            {"role": "active", "steps": [_step("active", zone="Z2")]},
            {"role": "cooldown", "steps": [_step("cooldown", zone="Z1")]},
        ],
    }


def _power_payload() -> dict:
    """A well-formed prescriptive power payload spanning Z1-Z5."""
    return {
        "id": "cycling-power",
        "name": "Power session",
        "objective": "Threshold work",
        "prescriptive": True,
        "sources": [CORPUS_SOURCE],
        "blocks": [
            {"role": "warmup", "steps": [_step("warmup", "power", "Z1")]},
            {
                "role": "active",
                "steps": [
                    _step("active", "power", "Z2"),
                    _step("active", "power", "Z3"),
                    _step("active", "power", "Z4"),
                    _step("active", "power", "Z5"),
                ],
            },
            {"role": "cooldown", "steps": [_step("cooldown", "power", "Z1")]},
        ],
    }


def _error_codes(report: CyclingValidationReport) -> list[str]:
    return [finding.code for finding in report.errors]


def _warning_codes(report: CyclingValidationReport) -> list[str]:
    return [finding.code for finding in report.warnings]


# --- I1: absolute_target_forbidden -------------------------------------------


def test_bpm_magnitude_is_forbidden() -> None:
    payload = _hr_payload()
    payload["blocks"][1]["steps"][0] = _step("active", zone="Z2", bpm=127)
    report = validate_cycling_payload(payload)
    assert "absolute_target_forbidden" in _error_codes(report)
    assert not report.ok
    finding = next(f for f in report.errors if f.code == "absolute_target_forbidden")
    assert finding.severity is Severity.ERROR
    assert finding.block_index == 1
    assert finding.step_index == 0


def test_watts_magnitude_is_forbidden() -> None:
    payload = _power_payload()
    payload["blocks"][1]["steps"][1] = _step("active", "power", "Z3", watts=200)
    report = validate_cycling_payload(payload, thresholds=POWER_ATHLETE)
    assert "absolute_target_forbidden" in _error_codes(report)


def test_system_heart_rate_value_is_not_a_magnitude() -> None:
    # FALSE-POSITIVE GUARD: "system": "heart_rate" is a system identifier, not
    # a magnitude; detection is by key name and "system" is not a magnitude key.
    payload = _hr_payload()
    assert all(
        step["target"]["system"] == "heart_rate"
        for block in payload["blocks"]
        for step in block["steps"]
    )
    report = validate_cycling_payload(payload, thresholds=HR_ATHLETE)
    assert "absolute_target_forbidden" not in _error_codes(report)
    assert report.ok


# --- I3: missing_provenance ----------------------------------------------------


def test_absent_sources_is_missing_provenance() -> None:
    payload = _hr_payload()
    del payload["sources"]
    report = validate_cycling_payload(payload)
    assert "missing_provenance" in _error_codes(report)


def test_empty_sources_is_missing_provenance() -> None:
    payload = _hr_payload()
    payload["sources"] = []
    report = validate_cycling_payload(payload)
    assert "missing_provenance" in _error_codes(report)


def test_blank_sources_are_missing_provenance() -> None:
    payload = _hr_payload()
    payload["sources"] = ["   "]
    report = validate_cycling_payload(payload)
    assert "missing_provenance" in _error_codes(report)


# --- I3: citation-subset rule (unretrieved_source) ------------------------------


def test_source_outside_citation_set_is_unretrieved_and_named() -> None:
    payload = _hr_payload()
    payload["sources"] = [CORPUS_SOURCE, "docs/invented-document.pdf"]
    report = validate_cycling_payload(payload, citation_set={CORPUS_SOURCE})
    assert "unretrieved_source" in _error_codes(report)
    assert not report.ok
    finding = next(f for f in report.errors if f.code == "unretrieved_source")
    assert finding.severity is Severity.ERROR
    # The message must NAME the offending value so a reviewer can see which
    # citation was invented.
    assert "docs/invented-document.pdf" in finding.message
    # The legitimate citation is not flagged.
    assert all(CORPUS_SOURCE not in f.message for f in report.errors)


def test_sources_within_citation_set_produce_no_provenance_error() -> None:
    payload = _hr_payload()
    report = validate_cycling_payload(
        payload, citation_set={CORPUS_SOURCE, "docs/other-chunk.md"}
    )
    assert "unretrieved_source" not in _error_codes(report)
    assert "missing_provenance" not in _error_codes(report)


def test_empty_citation_set_with_empty_sources_is_valid() -> None:
    # The case that must NOT be rejected: nothing was retrieved, so citing
    # nothing is correct — otherwise every knowledge-less generation fails.
    payload = _hr_payload()
    payload["sources"] = []
    report = validate_cycling_payload(payload, citation_set=set())
    assert "missing_provenance" not in _error_codes(report)
    assert "unretrieved_source" not in _error_codes(report)
    assert report.ok


def test_empty_citation_set_with_any_citation_is_fabricated() -> None:
    payload = _hr_payload()
    report = validate_cycling_payload(payload, citation_set=set())
    assert "unretrieved_source" in _error_codes(report)
    finding = next(f for f in report.errors if f.code == "unretrieved_source")
    assert CORPUS_SOURCE in finding.message


def test_citation_set_none_keeps_previous_non_empty_behaviour() -> None:
    # No citation_set: a source that was never retrieved is NOT checked and
    # the legacy non-empty rule alone applies, unchanged.
    payload = _hr_payload()
    payload["sources"] = ["docs/never-retrieved.pdf"]
    report = validate_cycling_payload(payload)
    assert _error_codes(report) == []
    # And the legacy missing-provenance behaviour is unchanged.
    payload["sources"] = []
    report = validate_cycling_payload(payload)
    assert "missing_provenance" in _error_codes(report)


def test_citation_set_none_with_absent_sources_still_requires_provenance() -> None:
    payload = _hr_payload()
    del payload["sources"]
    report = validate_cycling_payload(payload, citation_set=None)
    assert "missing_provenance" in _error_codes(report)


def test_malformed_sources_do_not_raise_out_of_the_validator() -> None:
    # 'sources' key absent entirely.
    report = validate_cycling_payload({"blocks": []}, citation_set={"doc-a"})
    assert isinstance(report, CyclingValidationReport)
    assert "missing_provenance" in _error_codes(report)
    # 'sources' of the wrong type.
    report = validate_cycling_payload(
        {"sources": "docs/not-a-list.pdf", "blocks": []}, citation_set={"doc-a"}
    )
    assert "missing_provenance" in _error_codes(report)
    # Non-string entries: they carry no citable value and must not raise.
    report = validate_cycling_payload(
        {"sources": ["doc-a", 42], "blocks": []}, citation_set={"doc-a"}
    )
    assert "unretrieved_source" not in _error_codes(report)


def test_subset_rule_and_non_empty_rule_do_not_contradict() -> None:
    # Empty set + empty sources: the non-empty rule must NOT fire.
    payload = _hr_payload()
    payload["sources"] = []
    empty_report = validate_cycling_payload(payload, citation_set=set())
    assert _error_codes(empty_report) == []
    # Non-empty set + non-member citation: the non-empty rule must NOT mask
    # (or be masked by) the subset rule — only the subset error fires.
    payload["sources"] = ["docs/fabricated.pdf"]
    fabricated_report = validate_cycling_payload(
        payload, citation_set={CORPUS_SOURCE}
    )
    assert {f.code for f in fabricated_report.errors} == {"unretrieved_source"}
    # Non-empty set + subset citation: both rules satisfied together.
    payload["sources"] = [CORPUS_SOURCE]
    ok_report = validate_cycling_payload(payload, citation_set={CORPUS_SOURCE})
    assert ok_report.errors == []


# --- Roles: missing_warmup / missing_cooldown / empty_workout -----------------


def test_missing_warmup_role_is_an_error() -> None:
    payload = _hr_payload()
    payload["blocks"] = [
        block for block in payload["blocks"] if block["steps"][0]["role"] != "warmup"
    ]
    report = validate_cycling_payload(payload)
    assert "missing_warmup" in _error_codes(report)
    assert "missing_cooldown" not in _error_codes(report)


def test_missing_cooldown_role_is_an_error() -> None:
    payload = _hr_payload()
    payload["blocks"] = [
        block for block in payload["blocks"] if block["steps"][0]["role"] != "cooldown"
    ]
    report = validate_cycling_payload(payload)
    assert "missing_cooldown" in _error_codes(report)
    assert "missing_warmup" not in _error_codes(report)


def test_empty_workout_no_blocks() -> None:
    payload = _hr_payload()
    payload["blocks"] = []
    report = validate_cycling_payload(payload)
    assert "empty_workout" in _error_codes(report)
    # An empty workout trivially has no roles: the role checks are skipped.
    assert "missing_warmup" not in _error_codes(report)
    assert "missing_cooldown" not in _error_codes(report)


def test_empty_workout_blocks_without_steps() -> None:
    payload = _hr_payload()
    payload["blocks"] = [{"role": "warmup", "steps": []}]
    report = validate_cycling_payload(payload)
    assert "empty_workout" in _error_codes(report)


def test_free_text_payload_skips_structural_role_rules() -> None:
    payload = {"prescriptive": False, "sources": [CORPUS_SOURCE], "blocks": []}
    report = validate_cycling_payload(payload)
    assert report.errors == []


# --- unresolvable_zone (delegated to resolve_target) ---------------------------


def test_heart_rate_zone_under_power_athlete_is_unresolvable() -> None:
    payload = _hr_payload()
    report = validate_cycling_payload(payload, thresholds=POWER_ATHLETE)
    assert "unresolvable_zone" in _error_codes(report)
    finding = next(f for f in report.errors if f.code == "unresolvable_zone")
    # The reason must come from resolve_target itself, not a reimplementation:
    # its message states there is no conversion between the two systems.
    assert "no conversion exists" in finding.message


def test_power_only_zone_code_under_heart_rate_athlete_is_unresolvable() -> None:
    payload = _hr_payload()
    payload["blocks"][1]["steps"][0] = _step("active", "heart_rate", "Z6")
    report = validate_cycling_payload(payload, thresholds=HR_ATHLETE)
    assert "unresolvable_zone" in _error_codes(report)


def test_zone_resolvability_is_not_evaluated_without_thresholds() -> None:
    payload = _hr_payload()
    report = validate_cycling_payload(payload)
    assert [finding.code for finding in report.not_evaluated] == ["unresolvable_zone"]
    # Not evaluated is NOT a pass and NOT a failure:
    assert "unresolvable_zone" not in _error_codes(report)
    assert "unresolvable_zone" not in _warning_codes(report)


# --- missing_system warning -----------------------------------------------------


def test_missing_system_is_a_warning_naming_the_cause() -> None:
    payload = _hr_payload()
    for block in payload["blocks"]:
        for step in block["steps"]:
            del step["target"]["system"]
    report = validate_cycling_payload(payload)
    assert "missing_system" in _warning_codes(report)
    assert "missing_system" not in _error_codes(report)
    finding = next(f for f in report.warnings if f.code == "missing_system")
    assert finding.severity is Severity.WARNING


# --- repeat_duration_unreliable (parsed workouts only) --------------------------


def test_parsed_workout_with_repeat_markers_warns_and_does_not_expand(
    corpus: ParsedCorpus,
) -> None:
    marked = [parsed for parsed in corpus.workouts if parsed.repeat_markers]
    assert marked, "corpus fixture lost its repeat markers"
    parsed = marked[0]
    report = validate_parsed_workout(parsed)
    assert "repeat_duration_unreliable" in _warning_codes(report)
    assert report.ok  # a warning does not block
    finding = next(f for f in report.warnings if f.code == "repeat_duration_unreliable")
    assert "understate" in finding.message
    # No expansion is attempted: the parsed workout is untouched and every
    # block keeps the parser's repeat_count = 1.
    assert parsed.workout is not None
    assert all(block.repeat_count == 1 for block in parsed.workout.blocks)


def test_parsed_workout_without_markers_has_no_repeat_warning(
    corpus: ParsedCorpus,
) -> None:
    unmarked = [parsed for parsed in corpus.workouts if not parsed.repeat_markers]
    assert unmarked
    for parsed in unmarked:
        report = validate_parsed_workout(parsed)
        assert "repeat_duration_unreliable" not in _warning_codes(report)


# --- Whole-corpus measured expectations -----------------------------------------


def test_corpus_prescriptive_workouts_have_zero_role_false_positives(
    corpus: ParsedCorpus,
) -> None:
    structured = [parsed for parsed in corpus.workouts if parsed.workout is not None]
    assert len(structured) == 27
    for parsed in structured:
        report = validate_parsed_workout(parsed)
        codes = _error_codes(report)
        assert "missing_warmup" not in codes
        assert "missing_cooldown" not in codes
        assert "empty_workout" not in codes


def test_corpus_exactly_24_of_27_repeat_warnings(corpus: ParsedCorpus) -> None:
    structured = [parsed for parsed in corpus.workouts if parsed.workout is not None]
    warned = [
        parsed
        for parsed in structured
        if "repeat_duration_unreliable"
        in _warning_codes(validate_parsed_workout(parsed))
    ]
    assert len(warned) == 24


def test_corpus_zones_resolve_under_heart_rate_athlete(corpus: ParsedCorpus) -> None:
    structured = [parsed for parsed in corpus.workouts if parsed.workout is not None]
    for parsed in structured:
        report = validate_parsed_workout(parsed, thresholds=HR_ATHLETE)
        assert report.errors == []
        assert report.not_evaluated == []


def test_corpus_zones_unresolvable_under_power_athlete(corpus: ParsedCorpus) -> None:
    structured = [parsed for parsed in corpus.workouts if parsed.workout is not None]
    checked = 0
    for parsed in structured:
        assert parsed.workout is not None
        has_zone_steps = any(
            isinstance(step.target, ZoneTarget)
            for block in parsed.workout.blocks
            for step in block.steps
        )
        report = validate_parsed_workout(parsed, thresholds=POWER_ATHLETE)
        if not has_zone_steps:
            # The two RPE-only corpus workouts carry no zone reference, so
            # there is nothing to resolve and nothing to reject.
            assert {f.code for f in report.errors} <= {"unresolvable_zone"}
            continue
        checked += 1
        assert report.errors, "a heart-rate zone resolved under a power athlete"
        assert {f.code for f in report.errors} == {"unresolvable_zone"}
        assert all("no conversion exists" in f.message for f in report.errors)
    # 25 of the 27 structured workouts carry zone steps (2 are RPE-only).
    assert checked == 25


# --- Well-formed payloads --------------------------------------------------------


def test_wellformed_heart_rate_payload_is_ok() -> None:
    report = validate_cycling_payload(_hr_payload())
    assert report.ok
    assert report.is_valid  # alias
    assert report.errors == []
    assert report.warnings == []


def test_power_payload_z1_to_z5_resolves_under_power_athlete() -> None:
    report = validate_cycling_payload(_power_payload(), thresholds=POWER_ATHLETE)
    assert report.ok
    assert report.errors == []
    assert report.warnings == []
    assert report.not_evaluated == []


def test_power_payload_z1_to_z5_unresolvable_under_heart_rate_athlete() -> None:
    report = validate_cycling_payload(_power_payload(), thresholds=HR_ATHLETE)
    assert {f.code for f in report.errors} == {"unresolvable_zone"}
