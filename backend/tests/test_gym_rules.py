"""Tests for the gym rule validator.

Real-corpus expectations, measured on ``docs/gym.txt`` and pinned exactly:

- 0 errors; exactly 16 warnings, all of code ``no_intensity_anchor``.
- The 16 are the 19 exercises minus the 3 that carry RIR (the parser never
  sets ``load``, so no exercise gets an intensity anchor from load).
- Zero ``unknown_exercise_name`` warnings: the default vocabulary covers every
  corpus name through knowledge-base headings plus the alias map.
- Zero ``empty_block`` warnings: the CORE block carries 6 prose items.
- 19 exercises across 3 blocks, 19 distinct normalized names before alias
  folding.

The alias map folds both crunch spellings (``crunch abdomen`` /
``crunch de abdomen``) onto ONE vocabulary entry while keeping the incline
bench press (corpus typo ``pres banca inclinado`` -> ``press banca
inclinado``) distinct from the flat ``press banca``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cycloai.domain.gym_corpus import (
    CORPUS_FILENAME,
    ParsedGymCorpus,
    parse_gym_corpus_file,
)
from cycloai.domain.gym_rules import (
    MAX_REPS,
    MAX_SETS,
    ExerciseVocabulary,
    GymValidationReport,
    Severity,
    normalize_name,
    validate_gym_blocks,
)
from cycloai.domain.workout import GymBlock, GymBlockName, GymExercise, GymSet

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "docs" / CORPUS_FILENAME

RIR_EXERCISES = {"Prensa", "Extensión de isquios", "Subida al cajón"}


@pytest.fixture(scope="module")
def corpus() -> ParsedGymCorpus:
    return parse_gym_corpus_file(CORPUS_PATH)


@pytest.fixture(scope="module")
def vocabulary() -> ExerciseVocabulary:
    return ExerciseVocabulary.default()


def _all_exercises(parsed: ParsedGymCorpus) -> list[GymExercise]:
    return [
        exercise
        for block in parsed.blocks
        for exercise in (*block.activation, *block.exercises, *block.core)
    ]


def _make_block(
    *exercises: GymExercise, name: GymBlockName = GymBlockName.LOWER_BODY
) -> GymBlock:
    return GymBlock(name=name, exercises=list(exercises))


def _exercise(name: str, *sets: GymSet, rest_s: int | None = None) -> GymExercise:
    return GymExercise(name=name, sets=list(sets), rest_s=rest_s)


def _codes(report: GymValidationReport) -> list[str]:
    return [finding.code for finding in report.errors]


def _warning_codes(report: GymValidationReport) -> list[str]:
    return [finding.code for finding in report.warnings]


# --- Real corpus: measured expectations -------------------------------------


def test_real_corpus_zero_errors_and_exactly_16_no_anchor_warnings(
    corpus: ParsedGymCorpus,
) -> None:
    report = validate_gym_blocks(corpus.blocks)
    assert report.errors == []
    assert len(report.warnings) == 16
    assert {warning.code for warning in report.warnings} == {"no_intensity_anchor"}


def test_real_corpus_no_unknown_exercise_or_empty_block_warnings(
    corpus: ParsedGymCorpus,
) -> None:
    report = validate_gym_blocks(corpus.blocks)
    codes = set(_warning_codes(report))
    assert "unknown_exercise_name" not in codes
    assert "empty_block" not in codes


def test_real_corpus_19_exercises_3_blocks_19_distinct_names(
    corpus: ParsedGymCorpus,
) -> None:
    assert len(corpus.blocks) == 3
    exercises = _all_exercises(corpus)
    assert len(exercises) == 19
    normalized = [normalize_name(exercise.name) for exercise in exercises]
    assert len(set(normalized)) == 19


def test_real_corpus_rir_and_rest_exercises_produce_no_w2(corpus: ParsedGymCorpus) -> None:
    report = validate_gym_blocks(corpus.blocks)
    w2_exercises = {
        warning.exercise for warning in report.warnings if warning.code == "no_intensity_anchor"
    }
    for name in RIR_EXERCISES:
        assert name not in w2_exercises, name

    # The 3 exercises with RIR and the 3 with rest are the same 3 exercises.
    rir = {e.name for e in _all_exercises(corpus) if any(s.rir is not None for s in e.sets)}
    rested = {e.name for e in _all_exercises(corpus) if e.rest_s is not None}
    assert rir == RIR_EXERCISES
    assert rested == RIR_EXERCISES
    # Everything else does get the warning: 19 - 3 == 16.
    assert len(w2_exercises) == 16


def test_real_corpus_every_warning_carries_block_and_exercise_location(
    corpus: ParsedGymCorpus,
) -> None:
    report = validate_gym_blocks(corpus.blocks)
    for warning in report.warnings:
        assert warning.block in {name.value for name in GymBlockName}
        assert warning.exercise is not None


# --- Vocabulary --------------------------------------------------------------


def test_default_vocabulary_covers_every_corpus_name(
    corpus: ParsedGymCorpus, vocabulary: ExerciseVocabulary
) -> None:
    for exercise in _all_exercises(corpus):
        assert vocabulary.contains(exercise.name), exercise.name


def test_alias_map_folds_both_crunch_spellings_to_one_entry(
    vocabulary: ExerciseVocabulary,
) -> None:
    assert vocabulary.contains("crunch abdomen")
    assert vocabulary.contains("Crunch de Abdomen")
    assert vocabulary.canonical_name("crunch de abdomen") == "crunch abdomen"
    # One vocabulary entry, not two: the folded spelling is not stored.
    assert normalize_name("crunch abdomen") in vocabulary.names
    assert normalize_name("crunch de abdomen") not in vocabulary.names


def test_alias_map_keeps_the_two_bench_presses_distinct(
    vocabulary: ExerciseVocabulary,
) -> None:
    assert vocabulary.contains("Pres banca inclinado")  # corpus typo
    assert vocabulary.canonical_name("Pres banca inclinado") == "press banca inclinado"
    assert vocabulary.canonical_name("Press banca") == "press banca"
    incline = vocabulary.canonical_name("pres banca inclinado")
    flat = vocabulary.canonical_name("press banca")
    assert incline != flat
    assert incline in vocabulary.names
    assert flat in vocabulary.names


def test_normalization_folds_case_accents_and_whitespace() -> None:
    assert normalize_name("  CAMINATA   Lateral  ÁÉÍÓÚ ") == "caminata lateral aeiou"
    assert normalize_name("Abducción de CADERA") == "abduccion de cadera"
    assert normalize_name("crunch\tde\nabdomen") == "crunch de abdomen"


# --- Error rules (E1-E6), built in memory ------------------------------------


def test_e1_no_sets() -> None:
    # GymExercise forbids empty sets, so bypass validation deliberately.
    block = _make_block(GymExercise.model_construct(name="Sin series", sets=[]))
    report = validate_gym_blocks([block])
    assert _codes(report) == ["no_sets"]
    finding = report.errors[0]
    assert finding.severity is Severity.ERROR
    assert finding.block == "TREN INFERIOR"
    assert finding.exercise == "Sin series"


def test_e2_reps_outside_1_to_50() -> None:
    boundaries = _make_block(
        _exercise("Minimo", GymSet(reps=1)),
        _exercise("Maximo", GymSet(reps=MAX_REPS)),
    )
    assert validate_gym_blocks([boundaries]).errors == []

    over = _make_block(_exercise("Excesivo", GymSet(reps=MAX_REPS + 1)))
    report = validate_gym_blocks([over])
    assert _codes(report) == ["reps_out_of_range"]
    assert str(MAX_REPS + 1) in report.errors[0].message

    # A range whose upper bound crosses the ceiling is also caught.
    ranged = _make_block(_exercise("Rango", GymSet(reps=25, reps_max=MAX_REPS + 5)))
    assert _codes(validate_gym_blocks([ranged])) == ["reps_out_of_range"]


def test_e3_more_than_10_sets() -> None:
    at_ceiling = _make_block(_exercise("Diez", *[GymSet(reps=8)] * MAX_SETS))
    assert validate_gym_blocks([at_ceiling]).errors == []

    over = _make_block(_exercise("Once", *[GymSet(reps=8)] * (MAX_SETS + 1)))
    report = validate_gym_blocks([over])
    assert _codes(report) == ["too_many_sets"]


def test_e4_blank_exercise_name() -> None:
    block = _make_block(_exercise("   ", GymSet(reps=10)))
    report = validate_gym_blocks([block])
    assert _codes(report) == ["blank_exercise_name"]
    # E4 already covers the blank name: no W1 fires for it.
    assert "unknown_exercise_name" not in _warning_codes(report)


def test_e5_duplicate_normalized_name_within_one_block() -> None:
    duplicated = _make_block(
        _exercise("Press banca", GymSet(reps=10)),
        _exercise("press banca", GymSet(reps=10)),
    )
    report = validate_gym_blocks([duplicated])
    assert _codes(report) == ["duplicate_exercise_name"]

    accented = _make_block(
        _exercise("Abducción de cadera", GymSet(reps=10)),
        _exercise("abduccion de cadera", GymSet(reps=10)),
    )
    assert _codes(validate_gym_blocks([accented])) == ["duplicate_exercise_name"]

    # The same name in DIFFERENT blocks is fine.
    spread = [
        _make_block(_exercise("Press banca", GymSet(reps=10))),
        _make_block(_exercise("Press banca", GymSet(reps=10)), name=GymBlockName.UPPER_BODY),
    ]
    assert validate_gym_blocks(spread).errors == []


def test_e6_rest_of_zero_or_negative_when_declared() -> None:
    # GymExercise enforces rest_s > 0, so bypass validation for these values.
    block = _make_block(
        GymExercise.model_construct(name="Cero", sets=[GymSet(reps=10)], rest_s=0),
        GymExercise.model_construct(name="Negativo", sets=[GymSet(reps=10)], rest_s=-30),
    )
    report = validate_gym_blocks([block])
    assert _codes(report) == ["non_positive_rest", "non_positive_rest"]

    undeclared = _make_block(_exercise("Sin rest", GymSet(reps=10)))
    assert validate_gym_blocks([undeclared]).errors == []


# --- Warning rules (W1-W3), built in memory ----------------------------------


def test_w1_unknown_exercise_name(vocabulary: ExerciseVocabulary) -> None:
    block = _make_block(_exercise("Sentadilla búlgara con bosu invertido", GymSet(reps=10)))
    report = validate_gym_blocks([block], vocabulary=vocabulary)
    assert report.errors == []
    unknown = [w for w in report.warnings if w.code == "unknown_exercise_name"]
    assert len(unknown) == 1
    assert unknown[0].severity is Severity.WARNING
    assert unknown[0].exercise == "Sentadilla búlgara con bosu invertido"


def test_w2_fires_without_any_intensity_anchor(vocabulary: ExerciseVocabulary) -> None:
    block = _make_block(_exercise("Sin ancla", GymSet(reps=10)))
    report = validate_gym_blocks([block], vocabulary=vocabulary)
    anchors = [w for w in report.warnings if w.code == "no_intensity_anchor"]
    assert len(anchors) == 1


def test_w2_not_fired_with_rir_or_load(vocabulary: ExerciseVocabulary) -> None:
    from cycloai.domain.workout import GymLoadAbsoluteKg

    block = _make_block(
        _exercise("Con RIR", GymSet(reps=10, rir=2)),
        _exercise("Con carga", GymSet(reps=10, load=GymLoadAbsoluteKg(kg=40))),
    )
    report = validate_gym_blocks([block], vocabulary=vocabulary)
    assert [w.code for w in report.warnings if w.code == "no_intensity_anchor"] == []


def test_w3_empty_block_and_prose_only_block() -> None:
    empty = GymBlock(name=GymBlockName.CORE)
    report = validate_gym_blocks([empty])
    assert _warning_codes(report) == ["empty_block"]
    assert report.errors == []

    prose_only = GymBlock(name=GymBlockName.CORE, prose_items=["SIN CALENTAMIENTO."])
    report = validate_gym_blocks([prose_only])
    assert _warning_codes(report) == []


# --- Report convenience -------------------------------------------------------


def test_report_ok_and_is_valid_follow_errors_not_warnings(
    vocabulary: ExerciseVocabulary,
) -> None:
    clean = GymBlock(name=GymBlockName.UPPER_BODY, prose_items=["notas del bloque"])
    report = validate_gym_blocks([clean], vocabulary=vocabulary)
    assert report.ok
    assert report.is_valid

    warned = GymBlock(name=GymBlockName.CORE)
    report = validate_gym_blocks([warned], vocabulary=vocabulary)
    assert report.warnings and report.ok

    failing = _make_block(_exercise("Press banca", GymSet(reps=MAX_REPS + 1)))
    report = validate_gym_blocks([failing], vocabulary=vocabulary)
    assert not report.ok
    assert not report.is_valid
