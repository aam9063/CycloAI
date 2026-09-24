"""Tests for the measured gym corpus parser.

The whole-corpus tests assert the measured totals exactly (``docs/gym.txt``,
61 lines, clean UTF-8):

- title ``EJEMPLO ENTRENAMIENTO GYM PARA CICLISMO:``
- 3 blocks in order: ``TREN INFERIOR``, ``TREN SUPERIOR``, ``CORE``
- 19 exercises total, 10 prose items total, ``unparsed == []``
- TREN INFERIOR: activation=3, exercises=6, prose_items=2
- TREN SUPERIOR: activation=0, exercises=10, prose_items=2
- CORE: 0 exercises (all ``core`` lists empty), prose_items=6

Two documented judgment calls are pinned as-is (not "fixed"):

1. ``4x25-30`` reads as a RANGE (four sets of 25-30), not a two-set ramp: a
   two-set ramp is never written in this corpus, and the declared count wins.
2. ``5x12-12-10-10`` declares five sets but lists four; the listed ramp is
   authoritative, so four sets are emitted and the leading count is treated as
   the author's slip. Neither "fixed" nor failed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cycloai.domain.gym_corpus import (
    CORPUS_FILENAME,
    GymCorpusParseError,
    ParsedGymCorpus,
    UnparsedLine,
    parse_gym_corpus,
    parse_gym_corpus_file,
)
from cycloai.domain.workout import GymBlock, GymBlockName, GymExercise

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "docs" / CORPUS_FILENAME
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "gym"

CORE_PROSE_VERBATIM = [
    "SIN CALENTAMIENTO.",
    "PLANCHA FRONTAL 2 APOYOS (codo y pie contrario) 15” cada lado",
    "PUENTE DE PIERNAS FITBALL A UNA PIERNA 10 reps/pierna",
    "APERTURAS PIERNA LATERAL TUMBADO 15 reps/pierna",
    "PUENTE DE CADERA UN APOYO ARRIBA Y ABAJO 10reps/pierna",
    "PLANCHA LATERAL A UNA PIERNA 15”/lado",
]


@pytest.fixture(scope="module")
def corpus() -> ParsedGymCorpus:
    return parse_gym_corpus_file(CORPUS_PATH)


def _all_exercises(parsed: ParsedGymCorpus) -> list[GymExercise]:
    exercises: list[GymExercise] = []
    for block in parsed.blocks:
        exercises.extend(block.activation)
        exercises.extend(block.exercises)
        exercises.extend(block.core)
    return exercises


def _find(parsed: ParsedGymCorpus, name: str) -> GymExercise:
    matches = [e for e in _all_exercises(parsed) if e.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, found {len(matches)}"
    return matches[0]


def _reps(exercise: GymExercise) -> list[int]:
    return [s.reps for s in exercise.sets]


def _reps_max(exercise: GymExercise) -> list[int | None]:
    return [s.reps_max for s in exercise.sets]


# --- Whole-corpus measured totals -------------------------------------------


def test_title(corpus: ParsedGymCorpus) -> None:
    assert corpus.title == "EJEMPLO ENTRENAMIENTO GYM PARA CICLISMO:"


def test_no_unparsed_lines(corpus: ParsedGymCorpus) -> None:
    assert corpus.unparsed == []


def test_block_order_and_names(corpus: ParsedGymCorpus) -> None:
    assert [block.name for block in corpus.blocks] == [
        GymBlockName.LOWER_BODY,
        GymBlockName.UPPER_BODY,
        GymBlockName.CORE,
    ]
    assert [block.name.value for block in corpus.blocks] == [
        "TREN INFERIOR",
        "TREN SUPERIOR",
        "CORE",
    ]


def test_block_counts(corpus: ParsedGymCorpus) -> None:
    lower, upper, core = corpus.blocks
    assert (len(lower.activation), len(lower.exercises), len(lower.prose_items)) == (3, 6, 2)
    assert (len(upper.activation), len(upper.exercises), len(upper.prose_items)) == (0, 10, 2)
    assert (len(core.activation), len(core.exercises), len(core.prose_items)) == (0, 0, 6)


def test_exercise_and_prose_totals(corpus: ParsedGymCorpus) -> None:
    assert len(_all_exercises(corpus)) == 19
    assert sum(len(block.prose_items) for block in corpus.blocks) == 10
    # All `core` lists are empty everywhere: the CORE block is pure prose.
    assert all(block.core == [] for block in corpus.blocks)


def test_activation_names_and_sets_in_order(corpus: ParsedGymCorpus) -> None:
    lower = corpus.blocks[0]
    clamshell, caminata, abduccion = lower.activation

    assert clamshell.name == "CLAMSHELL GLUTEO"
    assert _reps(clamshell) == [12, 12, 12]

    assert caminata.name == "CAMINATA LATERAL CON BANDA ELÁSTICA"
    assert len(caminata.sets) == 1
    assert caminata.sets[0].reps == 10
    assert caminata.sets[0].unit == "steps"

    assert abduccion.name == "ABDUCCIÓN DE CADERA CON BANDA ELÁSTICA"
    assert _reps(abduccion) == [15, 15, 15]


# --- Measured set readings per exercise -------------------------------------


@pytest.mark.parametrize(
    ("name", "reps"),
    [
        ("Prensa", [20, 15, 15, 10, 10]),
        ("Extensión de isquios", [12, 12, 10, 10]),
        ("Subida al cajón", [15, 10, 8, 8]),
        ("Gemelo", [14, 14, 14, 14]),
        ("Press banca", [13, 13, 13, 13]),
        ("Pres banca inclinado", [12, 10, 8]),
        ("Remo polea baja", [10, 10, 8, 8]),
        ("Press francés", [7, 7, 7, 7]),
        ("crunch abdomen", [25, 25, 25]),
    ],
)
def test_flat_and_ramp_set_readings(corpus: ParsedGymCorpus, name: str, reps: list[int]) -> None:
    exercise = _find(corpus, name)
    assert _reps(exercise) == reps
    assert _reps_max(exercise) == [None] * len(reps)


@pytest.mark.parametrize(
    ("name", "count", "low", "high"),
    [
        ("Hip thrust", 3, 8, 10),
        ("Crunch de abdomen", 4, 25, 30),
        ("Extensión triceps con cuerda", 3, 10, 12),
    ],
)
def test_range_set_readings(
    corpus: ParsedGymCorpus, name: str, count: int, low: int, high: int
) -> None:
    exercise = _find(corpus, name)
    assert len(exercise.sets) == count
    assert _reps(exercise) == [low] * count
    assert _reps_max(exercise) == [high] * count


def test_rir_appears_on_exactly_three_exercises(corpus: ParsedGymCorpus) -> None:
    rir_by_name = {e.name: {s.rir for s in e.sets} for e in _all_exercises(corpus)}
    with_rir = {name: values.pop() for name, values in rir_by_name.items() if values != {None}}
    assert with_rir == {"Prensa": 5, "Extensión de isquios": 5, "Subida al cajón": 4}
    for exercise in _all_exercises(corpus):
        if exercise.name not in with_rir:
            assert all(s.rir is None for s in exercise.sets), exercise.name


def test_rest_values(corpus: ParsedGymCorpus) -> None:
    assert _find(corpus, "Prensa").rest_s == 90
    assert _find(corpus, "Extensión de isquios").rest_s == 120
    assert _find(corpus, "Subida al cajón").rest_s == 120


def test_notes_verbatim(corpus: ParsedGymCorpus) -> None:
    assert _find(corpus, "Prensa").note == "la primera de calentamiento"
    isquios = _find(corpus, "Extensión de isquios")
    assert isquios.note is not None
    assert "LAS DOS PRIMERAS A RITMO NORMAL" in isquios.note
    assert _find(corpus, "Gemelo").note is None


# --- Prose preserved verbatim -----------------------------------------------


def test_core_prose_items_verbatim_in_order(corpus: ParsedGymCorpus) -> None:
    assert corpus.blocks[2].prose_items == CORE_PROSE_VERBATIM


def test_lower_body_prose_includes_warmup_and_planks(corpus: ParsedGymCorpus) -> None:
    prose = corpus.blocks[0].prose_items
    assert "10´ de calentamiento en elíptica, comba, bici, etc." in prose
    assert "3 planchas de 1 minuto." in prose


# --- Focused grammar behaviour ----------------------------------------------


def test_uppercase_and_lowercase_x_are_equivalent() -> None:
    upper = parse_gym_corpus("TREN INFERIOR:\nTest: 3X12\n")
    lower = parse_gym_corpus("TREN INFERIOR:\nTest: 3x12\n")
    assert upper.blocks[0].exercises[0].sets == lower.blocks[0].exercises[0].sets
    assert _reps(upper.blocks[0].exercises[0]) == [12, 12, 12]


def test_range_versus_ramp_rule_for_all_forms() -> None:
    text = "\n".join(
        [
            "TREN INFERIOR:",
            "A: 4x25-30",  # two-element hyphen tail with count != 2 -> RANGE
            "B: 3x8/10",  # slash tail -> RANGE
            "C: 5x20-15-15-10-10",  # multi-element hyphen tail -> RAMP
            "D: 2x12-10",  # count == 2 with two-element tail -> genuine RAMP
        ]
    )
    parsed = parse_gym_corpus(text)
    a, b, c, d = parsed.blocks[0].exercises

    # Judgment call 1: declared count wins over the two-number tail.
    assert len(a.sets) == 4
    assert a.sets[0].reps == 25 and a.sets[0].reps_max == 30
    assert all(s.reps == 25 and s.reps_max == 30 for s in a.sets)

    assert len(b.sets) == 3
    assert all(s.reps == 8 and s.reps_max == 10 for s in b.sets)

    assert _reps(c) == [20, 15, 15, 10, 10]
    assert all(s.reps_max is None for s in c.sets)

    assert _reps(d) == [12, 10]
    assert all(s.reps_max is None for s in d.sets)


def test_declared_count_slip_emits_listed_ramp() -> None:
    # Judgment call 2: 5x12-12-10-10 lists four values; the listed ramp is
    # authoritative, so four sets are emitted (neither "fixed" nor failed).
    parsed = parse_gym_corpus("TREN INFERIOR:\nTest: 5x12-12-10-10\n")
    (exercise,) = parsed.blocks[0].exercises
    assert _reps(exercise) == [12, 12, 10, 10]
    assert len(exercise.sets) == 4


def test_rir_optional_and_captured_inside_unclosed_parenthetical() -> None:
    without = parse_gym_corpus("TREN INFERIOR:\nTest: 3x10\n")
    (plain,) = without.blocks[0].exercises
    assert all(s.rir is None for s in plain.sets)

    # The author leaves the parenthetical unclosed in the corpus; RIR is still
    # captured from inside it.
    with_rir = parse_gym_corpus("TREN INFERIOR:\nTest: 5x20-15-15-10-10 (RIR 5\n")
    (exercise,) = with_rir.blocks[0].exercises
    assert all(s.rir == 5 for s in exercise.sets)


def test_rest_attaches_to_the_exercise_above_it() -> None:
    text = "\n".join(["TREN INFERIOR:", "Prensa: 5x20-15-15-10-10", "1´ 30´´ REC"])
    parsed = parse_gym_corpus(text)
    (exercise,) = parsed.blocks[0].exercises
    assert exercise.rest_s == 90  # 1 minute 30 seconds


def test_rest_line_without_preceding_exercise_raises() -> None:
    with pytest.raises(GymCorpusParseError, match="no preceding exercise"):
        parse_gym_corpus("1´ 30´´ REC")
    with pytest.raises(GymCorpusParseError, match="no preceding exercise"):
        parse_gym_corpus("TREN INFERIOR:\n1´ 30´´ REC")


def test_arrow_form() -> None:
    parsed = parse_gym_corpus("TREN INFERIOR:\n-Press banca--> 4x13,\n")
    (exercise,) = parsed.blocks[0].exercises
    assert exercise.name == "Press banca"
    assert _reps(exercise) == [13, 13, 13, 13]


def test_reps_first_form() -> None:
    parsed = parse_gym_corpus("TREN INFERIOR:\n3x25 crunch abdomen\n")
    (exercise,) = parsed.blocks[0].exercises
    assert exercise.name == "crunch abdomen"
    assert _reps(exercise) == [25, 25, 25]
    assert exercise.note is None


def test_steps_unit() -> None:
    parsed = parse_gym_corpus("TREN INFERIOR:\nACTIVACIÓN:\nBanda: 10 PASOS A CADA DIRECCIÓN\n")
    (exercise,) = parsed.blocks[0].activation
    assert len(exercise.sets) == 1
    assert exercise.sets[0].unit == "steps"
    assert exercise.sets[0].reps == 10
    assert exercise.sets[0].reps_max is None


def test_separator_lines_carry_no_structure() -> None:
    text = "\n".join(["TREN INFERIOR:", "Prensa: 2x10", "--", "1´ REC", "--"])
    parsed = parse_gym_corpus(text)
    (exercise,) = parsed.blocks[0].exercises
    # The separator is consumed: it is not prose, it does not create a block,
    # and it does not detach the rest line from the exercise above it.
    assert parsed.blocks[0].prose_items == []
    assert len(parsed.blocks) == 1
    assert exercise.rest_s == 60


def test_unclassifiable_line_outside_any_block_is_recorded() -> None:
    parsed = parse_gym_corpus("EJEMPLO ENTRENAMIENTO GYM PARA CICLISMO:\nlinea suelta\n")
    assert parsed.unparsed == [UnparsedLine(line_number=2, text="linea suelta")]


# --- Decoding ---------------------------------------------------------------


def test_non_utf8_corpus_file_raises(tmp_path: Path) -> None:
    # 0xE9 is valid cp1252 (é) but invalid UTF-8: there is no codec fallback.
    bad = tmp_path / "corpus.txt"
    bad.write_bytes(b"caf\xe9 3x12")
    with pytest.raises(UnicodeDecodeError):
        parse_gym_corpus_file(bad)


# --- Fixtures ---------------------------------------------------------------


def test_fixtures_match_parser_output(corpus: ParsedGymCorpus) -> None:
    fixture_files = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(fixture_files) == len(corpus.blocks) == 3
    for index, block in enumerate(corpus.blocks, start=1):
        name = f"{index:02d}-{block.name.value.lower().replace(' ', '-')}.json"
        path = FIXTURE_DIR / name
        assert path.exists(), f"missing fixture {name}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(block, GymBlock)
        assert data == block.model_dump(mode="json")
