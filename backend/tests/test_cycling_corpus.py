"""Tests for the measured cycling corpus parser (task T4).

The whole-corpus tests assert the measured totals exactly:

- 29 workouts = 5 labelled (E1, E3, E5 interval; E2, E4 free text) + 24 unlabelled
- 361 steps: 329 bpm/zone steps, 32 RPE steps (RPE steps carry no zone)
- 49 cadence-bearing steps (``N-N rpm`` and ``Nrpm`` forms)
- 319 role lines with run-length encoding, so 42 steps inherit a role
- 80 ``Repetir N veces`` markers (N in 1..6), captured structurally
- ``unparsed == []`` for the whole corpus
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cycloai.domain.cycling_corpus import (
    CORPUS_FILENAME,
    CyclingCorpusParseError,
    ParsedCorpus,
    parse_cycling_corpus,
    parse_cycling_corpus_file,
    parsed_workout_to_dict,
)
from cycloai.domain.workout import (
    CadenceTarget,
    ClockDuration,
    MinutesDuration,
    RpeTarget,
    SecondsDuration,
    StepRole,
    ZoneTarget,
)
from cycloai.domain.zones import ZoneCode

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "docs" / CORPUS_FILENAME
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "cycling"


@pytest.fixture(scope="module")
def corpus() -> ParsedCorpus:
    return parse_cycling_corpus_file(CORPUS_PATH)


def _steps(parsed):
    assert parsed.workout is not None, f"workout {parsed.label} is not structured"
    return [step for block in parsed.workout.blocks for step in block.steps]


# --- Whole-corpus measured totals -------------------------------------------


def test_whole_corpus_totals(corpus: ParsedCorpus) -> None:
    assert corpus.unparsed == []
    assert corpus.title == "EJEMPLO DE ENTRENAMIENTO PARA CICLISMO:"
    assert len(corpus.workouts) == 29


def test_labelled_and_unlabelled_split(corpus: ParsedCorpus) -> None:
    labelled = [parsed for parsed in corpus.workouts if parsed.label is not None]
    unlabelled = [parsed for parsed in corpus.workouts if parsed.label is None]
    assert len(labelled) == 5
    assert {parsed.label for parsed in labelled} == {"E1", "E2", "E3", "E4", "E5"}
    assert len(unlabelled) == 24
    assert all(parsed.name is None for parsed in unlabelled)


def test_free_text_workouts_are_exactly_e2_and_e4(corpus: ParsedCorpus) -> None:
    free_text = [parsed for parsed in corpus.workouts if parsed.workout is None]
    assert [parsed.label for parsed in free_text] == ["E2", "E4"]
    e2, e4 = free_text
    assert e2.free_text  # E2 carries one prose line as its body
    assert e4.free_text is None  # E4 has no body; its free text is the header
    assert e4.name is not None and e4.name.startswith("SALIDA LIBRE")
    assert e4.repeat_markers == ()
    for label in ("E1", "E3", "E5"):
        parsed = next(p for p in corpus.workouts if p.label == label)
        assert parsed.workout is not None
        assert parsed.free_text is None
        assert len(_steps(parsed)) == 7


def test_step_target_totals(corpus: ParsedCorpus) -> None:
    all_steps = [step for parsed in corpus.workouts if parsed.workout for step in _steps(parsed)]
    assert len(all_steps) == 361
    zone_steps = [step for step in all_steps if isinstance(step.target, ZoneTarget)]
    rpe_steps = [step for step in all_steps if isinstance(step.target, RpeTarget)]
    assert len(zone_steps) == 329
    assert len(rpe_steps) == 32


def test_rpe_steps_never_carry_a_zone(corpus: ParsedCorpus) -> None:
    for parsed in corpus.workouts:
        if parsed.workout is None:
            continue
        for step in _steps(parsed):
            if isinstance(step.target, RpeTarget):
                assert 1 <= step.target.rpe <= 10


def test_zone_steps_use_the_closed_vocabulary(corpus: ParsedCorpus) -> None:
    for parsed in corpus.workouts:
        if parsed.workout is None:
            continue
        for step in _steps(parsed):
            if isinstance(step.target, ZoneTarget):
                assert step.target.zone in ZoneCode


def test_cadence_bearing_steps_total(corpus: ParsedCorpus) -> None:
    total = 0
    for parsed in corpus.workouts:
        if parsed.workout is None:
            continue
        total += sum(1 for step in _steps(parsed) if step.cadence is not None)
    assert total == 49


def test_role_inherited_steps_total(corpus: ParsedCorpus) -> None:
    assert sum(parsed.inherited_role_steps for parsed in corpus.workouts) == 42


def test_repeat_markers_total(corpus: ParsedCorpus) -> None:
    markers = [marker for parsed in corpus.workouts for marker in parsed.repeat_markers]
    assert len(markers) == 80
    assert all(1 <= marker.count <= 6 for marker in markers)


# --- Focused grammar behaviour -----------------------------------------------


def test_role_inheritance_and_role_change() -> None:
    # RPE targets keep the synthetic section free of zone-attachment ambiguity.
    text = "\n".join(
        [
            "Warm up",
            "10 min @ 5 RPE",
            "5 min @ 6 RPE",
            "45 sec @ 7 RPE",
            "Active",
            "1:00 @ 8 RPE",
        ]
    )
    parsed = parse_cycling_corpus(text).workouts[0]
    steps = _steps(parsed)
    assert [step.role for step in steps] == [
        StepRole.WARMUP,
        StepRole.WARMUP,
        StepRole.WARMUP,
        StepRole.ACTIVE,
    ]
    # Only the first step after each role line is explicit; the other two inherit.
    assert parsed.inherited_role_steps == 2


def test_zone_label_before_target_attaches_to_next_step() -> None:
    text = "Warm up\nZone 2: Aerobic\n10 min @ 100 bpm\n"
    parsed = parse_cycling_corpus(text).workouts[0]
    (step,) = _steps(parsed)
    assert isinstance(step.target, ZoneTarget)
    assert step.target.zone is ZoneCode.Z2


def test_duration_forms_round_trip_exactly() -> None:
    # Zone-before-target layout: each step has exactly one zone line.
    text = "\n".join(
        [
            "Warm up",
            "Zone 1: Recovery",
            "15 min @ 100 bpm",
            "Zone 2: Aerobic",
            "45 sec @ 110 bpm",
            "Zone 3: Tempo",
            "36:20 @ 120 bpm",
        ]
    )
    parsed = parse_cycling_corpus(text).workouts[0]
    steps = _steps(parsed)
    first, second, third = steps

    assert isinstance(first.duration, MinutesDuration)
    assert first.duration.minutes == 15
    assert first.duration.total_seconds == 900

    assert isinstance(second.duration, SecondsDuration)
    assert second.duration.seconds == 45

    # The clock form is preserved verbatim, never normalised.
    assert isinstance(third.duration, ClockDuration)
    assert third.duration.clock == "36:20"
    assert third.duration.total_seconds == 2180


def test_cadence_both_forms() -> None:
    text = "\n".join(
        [
            "Warm up",
            "10 min @ 100 bpm",
            "Zone 1: Recovery",
            "85-95 rpm",
            "Zone 2: Aerobic",
            "10 min @ 105 bpm",
            "90rpm",
        ]
    )
    parsed = parse_cycling_corpus(text).workouts[0]
    first, second = _steps(parsed)

    assert isinstance(first.cadence, CadenceTarget)
    assert (first.cadence.min_rpm, first.cadence.max_rpm) == (85, 95)

    # Single-value form maps through CadenceTarget.from_single.
    assert isinstance(second.cadence, CadenceTarget)
    assert (second.cadence.min_rpm, second.cadence.max_rpm) == (90, 90)


def test_intents_attach_to_the_right_step_and_never_as_zones() -> None:
    text = "\n".join(
        [
            "Warm up",
            "10 min @ 100 bpm",
            "Zone 1: Recovery",
            "APRIETA",
            "10 min @ 105 bpm",
            "Zone 2: Aerobic",
            "NO TIENES QUE LLEGAR A ESTE PULSO",
            "A TOPE",
        ]
    )
    parsed = parse_cycling_corpus(text).workouts[0]
    first, second = _steps(parsed)

    assert isinstance(first.target, ZoneTarget)
    assert first.target.zone is ZoneCode.Z1
    assert first.target.intent == "APRIETA"

    # Both intent lines belong to the same (second) step.
    assert isinstance(second.target, ZoneTarget)
    assert second.target.zone is ZoneCode.Z2
    assert second.target.intent == "NO TIENES QUE LLEGAR A ESTE PULSO | A TOPE"

    assert parsed.step_intents == (
        ("APRIETA",),
        ("NO TIENES QUE LLEGAR A ESTE PULSO", "A TOPE"),
    )


def test_intent_matching_is_case_insensitive() -> None:
    text = "\n".join(
        [
            "Warm up",
            "10 min @ 100 bpm",
            "Zone 1: Recovery",
            "a tope",
            "10 min @ 105 bpm",
            "Zone 1: Recovery",
            "ACELERACIÓN",
        ]
    )
    parsed = parse_cycling_corpus(text).workouts[0]
    first, second = _steps(parsed)
    assert isinstance(first.target, ZoneTarget)
    assert first.target.intent == "a tope"
    assert isinstance(second.target, ZoneTarget)
    assert second.target.intent == "ACELERACIÓN"


def test_rpe_step_has_no_zone_in_mixed_section() -> None:
    text = "\n".join(
        [
            "Warm up",
            "10 min @ 7 RPE",
            "Zone 3: Tempo",
            "5 min @ 200 bpm",
        ]
    )
    parsed = parse_cycling_corpus(text).workouts[0]
    first, second = _steps(parsed)
    assert isinstance(first.target, RpeTarget)
    assert first.target.rpe == 7
    assert isinstance(second.target, ZoneTarget)
    assert second.target.zone is ZoneCode.Z3


def test_first_step_without_role_raises() -> None:
    with pytest.raises(CyclingCorpusParseError, match="no role available"):
        parse_cycling_corpus("E1:Test\n10 min @ 100 bpm\nZone 1: Recovery\n")


# --- Fail-closed zone/cadence attachment (no silent drops) --------------------


def test_zone_line_before_rpe_target_raises_fail_closed() -> None:
    # A zone line cannot belong to an RPE step: it must never be dropped
    # silently (the step builder ignores zones for RPE targets).
    text = "\n".join(["Warm up", "Zone 1: Recovery", "10 min @ 5 RPE"])
    with pytest.raises(CyclingCorpusParseError, match="RPE target cannot carry"):
        parse_cycling_corpus(text)


def test_zone_line_outside_any_workout_raises() -> None:
    with pytest.raises(CyclingCorpusParseError, match="outside any workout"):
        parse_cycling_corpus("Zone 1: Recovery\n")


def test_second_consecutive_orphan_zone_line_raises() -> None:
    text = "\n".join(
        ["Warm up", "Zone 1: Recovery", "Zone 2: Aerobic", "10 min @ 100 bpm"]
    )
    with pytest.raises(CyclingCorpusParseError, match="second consecutive zone"):
        parse_cycling_corpus(text)


def test_second_consecutive_orphan_cadence_line_raises() -> None:
    text = "\n".join(
        [
            "Warm up",
            "Zone 1: Recovery",
            "10 min @ 100 bpm",
            "85-95 rpm",  # attaches to step 1
            "85-95 rpm",  # orphan: step 1 already carries a cadence
            "90rpm",  # second consecutive orphan cadence
        ]
    )
    with pytest.raises(
        CyclingCorpusParseError, match="second consecutive unassigned"
    ):
        parse_cycling_corpus(text)


def test_unassigned_pending_zone_at_workout_boundary_raises() -> None:
    # A zone line still pending when the workout ends can belong to no step.
    at_separator = "Warm up\nZone 1: Recovery\n10 min @ 100 bpm\nZone 2: Aerobic\n--\n"
    with pytest.raises(CyclingCorpusParseError, match="cannot belong to any step"):
        parse_cycling_corpus(at_separator)
    at_end_of_text = "Warm up\nZone 1: Recovery\n10 min @ 100 bpm\nZone 2: Aerobic\n"
    with pytest.raises(CyclingCorpusParseError, match="cannot belong to any step"):
        parse_cycling_corpus(at_end_of_text)


# --- Decoding ----------------------------------------------------------------


def test_non_utf8_corpus_file_raises(tmp_path: Path) -> None:
    # 0xE9 is valid cp1252 (é) but invalid UTF-8: the removed cp1252 fallback
    # would have decoded this silently into mojibake.
    bad = tmp_path / "corpus.txt"
    bad.write_bytes(b"caf\xe9 10 min @ 100 bpm")
    with pytest.raises(UnicodeDecodeError):
        parse_cycling_corpus_file(bad)


def test_unclassifiable_line_is_recorded_not_dropped() -> None:
    text = "\n".join(
        [
            "Warm up",
            "10 min @ 100 bpm",
            "Zone 1: Recovery",
            "linea sin clasificar alguna",
        ]
    )
    parsed = parse_cycling_corpus(text)
    assert len(parsed.unparsed) == 1
    assert parsed.unparsed[0].line_number == 4
    assert parsed.unparsed[0].text == "linea sin clasificar alguna"


# --- Fixtures ----------------------------------------------------------------


def test_fixtures_match_parser_output(corpus: ParsedCorpus) -> None:
    fixture_files = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(fixture_files) == len(corpus.workouts) == 29
    for index, parsed in enumerate(corpus.workouts, start=1):
        if parsed.label is not None:
            name = f"{index:02d}-{parsed.label.lower()}.json"
        else:
            name = f"{index:02d}-unlabelled.json"
        path = FIXTURE_DIR / name
        assert path.exists(), f"missing fixture {name}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == parsed_workout_to_dict(parsed)
