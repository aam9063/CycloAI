"""Gym rule validator for CycloAI prescriptions.

Structural errors (E1-E6) and advisory warnings (W1-W3) over parsed gym
blocks. E2 (reps ceiling of 50) and E3 (sets ceiling of 10) are SANITY
CEILINGS chosen far above the measured corpus maxima (30 reps, 5 sets);
they are not attempts to mirror the corpus.

Deliberately REJECTED rules, measured against the real corpus
(docs/gym.txt, 19 exercises across 3 blocks) so nobody reintroduces them:

- No rule rejects high-rep or "hypertrophy" ranges: 7 of 19 exercises
  legitimately exceed 12 reps, including a 20-rep warm-up set on the leg
  press and 25-30 rep abdominal work.
- No rule requires a RIR declaration: RIR appears on only 3 of 19
  exercises, so requiring it would fail closed on legitimate content.

An exercise name outside the known vocabulary is a WARNING (W1), not an
error: the knowledge base documents 6 exercises and the corpus 19, and
they barely share names, so rejecting unknown names would fail closed on
legitimate content today. Errors are reserved for structural defects.

Vocabulary
----------
The default vocabulary (:meth:`ExerciseVocabulary.default`) is built from two
sources:

- the exercise names of ``docs/gym.txt``, parsed via
  :func:`cycloai.domain.gym_corpus.parse_gym_corpus_file` with
  ``CORPUS_FILENAME`` resolved against the repository root;
- the ``##`` headings of the Markdown files under ``knowledge-base/gym/``,
  excluding the structural (non-exercise) headings listed explicitly in
  ``_STRUCTURAL_KB_HEADINGS``. The exclusion list is documented and
  exhaustive on purpose: no silent filtering.

Alias map
---------
``_ALIAS_MAP`` is explicitly declared domain knowledge the owner should
extend over time. Measured fact motivating it: normalization alone does NOT
merge these names, because they differ by a word or a letter, not by case:

- ``crunch abdomen`` and ``crunch de abdomen`` are the same exercise written
  two ways in the corpus.
- the corpus typo ``pres banca inclinado`` means the incline bench press
  (``press banca inclinado``), which is DISTINCT from the flat
  ``press banca`` and must never be merged with it.

Alias targets are canonical corrected forms and are added to the vocabulary
themselves, so folding a typo never maps onto a name that would fail W1.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from cycloai.domain.gym_corpus import CORPUS_FILENAME, parse_gym_corpus_file
from cycloai.domain.workout import GymBlock, GymBlockName

__all__ = [
    "MAX_REPS",
    "MAX_SETS",
    "ExerciseVocabulary",
    "Finding",
    "GymValidationReport",
    "Severity",
    "normalize_name",
    "validate_gym_blocks",
]

#: Sanity ceiling for reps per set (E2). The measured corpus maximum is 30;
#: this ceiling is deliberately far above it and does not mirror the corpus.
MAX_REPS = 50

#: Sanity ceiling for sets per exercise (E3). The measured corpus maximum is
#: 5; this ceiling is deliberately far above it and does not mirror the corpus.
MAX_SETS = 10


class Severity(StrEnum):
    """Severity of a validation finding."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation finding: stable machine code, severity, message, location.

    ``block`` carries the block name and ``exercise`` the exercise name when
    applicable, so every finding can be acted on without re-deriving context.
    """

    code: str
    severity: Severity
    message: str
    block: str | None = None
    exercise: str | None = None


@dataclass(frozen=True, slots=True)
class GymValidationReport:
    """Result of validating gym blocks: structural errors plus advisory warnings."""

    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there are no structural errors; warnings do not block."""
        return not self.errors

    @property
    def is_valid(self) -> bool:
        """Alias of :attr:`ok`."""
        return not self.errors


#: Structural headings under knowledge-base/gym/ that are NOT exercise names.
#: Explicit and exhaustive by design: everything listed here is excluded from
#: the default vocabulary, and nothing else is. Verified by grepping the
#: knowledge base (27 ``##`` headings across 4 files; the 10 exercise headings
#: below are the ones kept).
_STRUCTURAL_KB_HEADINGS: frozenset[str] = frozenset(
    {
        # core-estabilizacion-ciclista.md
        "Principios del entrenamiento de core para ciclistas",
        "Trabajo de glúteo medio específico",
        "Integración del core en la sesión semanal",
        # ejercicios-fuerza-ciclismo.md
        "Estabilización de hombros y espalda alta",
        "Orden de ejercicios y estructura de la sesión",
        # movilidad-flexibilidad-ciclista.md
        "Por qué la movilidad importa más allá del rendimiento",
        "Protocolo de movilidad de cadera",
        "Movilidad de columna torácica",
        "Trabajo de isquiotibiales y cadena posterior",
        "Rutina integrada pre y post entreno",
        "Frecuencia y progresión",
        # periodizacion-gimnasio-ciclista.md
        "Fases de la periodización anual",
        "Gestión de la interferencia concurrente",
        "Frecuencia y distribución semanal por fase",
        "Progresión de cargas y seguimiento",
        "Señales de interferencia excesiva y ajuste",
        "Transición entre fases y planificación inversa",
    }
)

#: Declared alias map: normalized name -> canonical normalized form. This is
#: domain knowledge the owner should extend; it exists because normalization
#: alone cannot merge names that differ by a word or a letter (see module
#: docstring for the measured facts behind each entry).
_ALIAS_MAP: dict[str, str] = {
    "crunch de abdomen": "crunch abdomen",
    "pres banca inclinado": "press banca inclinado",
}


def normalize_name(name: str) -> str:
    """Normalize an exercise name: casefold + accent stripping + whitespace collapse."""
    collapsed = " ".join(name.split())
    decomposed = unicodedata.normalize("NFKD", collapsed)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def _canonical(name: str) -> str:
    """Fold a normalized name through the alias map to its canonical form."""
    return _ALIAS_MAP.get(name, name)


@dataclass(frozen=True, slots=True)
class ExerciseVocabulary:
    """Closed set of known exercise names, stored in normalized canonical form.

    Build the default vocabulary with :meth:`default`; test membership with
    :meth:`contains` (or ``in``), which normalizes the candidate name and folds
    it through the alias map first.
    """

    names: frozenset[str]

    @classmethod
    def default(cls) -> ExerciseVocabulary:
        """Build the default vocabulary from the corpus and the knowledge base."""
        return _default_vocabulary()

    @classmethod
    def from_names(cls, names: Iterable[str]) -> ExerciseVocabulary:
        """Build a vocabulary from raw names, normalizing and folding each one."""
        return cls(frozenset(_canonical(normalize_name(name)) for name in names))

    def canonical_name(self, name: str) -> str:
        """Return the canonical normalized form of ``name`` (alias folding included)."""
        return _canonical(normalize_name(name))

    def contains(self, name: str) -> bool:
        """True when the normalized, alias-folded name is in the vocabulary."""
        return self.canonical_name(name) in self.names

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.contains(name)


def _find_repo_root() -> Path:
    """Locate the repository root by walking up from this module until the
    corpus file (``docs/<CORPUS_FILENAME>``) is found."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "docs" / CORPUS_FILENAME).is_file():
            return candidate
    raise FileNotFoundError(
        f"could not locate the repository root containing docs/{CORPUS_FILENAME} "
        f"starting from {__file__}"
    )


def _kb_exercise_headings(root: Path) -> list[str]:
    """Collect the ``##`` headings of knowledge-base/gym/*.md that are exercise
    names, excluding the documented structural headings."""
    headings: list[str] = []
    for path in sorted((root / "knowledge-base" / "gym").glob("*.md")):
        for line in path.read_text(encoding="utf-8").split("\n"):
            if not line.startswith("## "):
                continue
            heading = line[3:].strip()
            if heading not in _STRUCTURAL_KB_HEADINGS:
                headings.append(heading)
    return headings


@lru_cache(maxsize=1)
def _default_vocabulary() -> ExerciseVocabulary:
    root = _find_repo_root()
    parsed = parse_gym_corpus_file(root / "docs" / CORPUS_FILENAME)
    names = [
        exercise.name
        for block in parsed.blocks
        for exercise in (*block.activation, *block.exercises, *block.core)
    ]
    names.extend(_kb_exercise_headings(root))
    # Alias targets are canonical corrected forms and must be members too,
    # otherwise folding a corpus typo would map onto a name that fails W1.
    names.extend(_ALIAS_MAP.values())
    return ExerciseVocabulary(frozenset(_canonical(normalize_name(name)) for name in names))


def validate_gym_blocks(
    blocks: Iterable[GymBlock], *, vocabulary: ExerciseVocabulary | None = None
) -> GymValidationReport:
    """Validate gym blocks and return the report of errors and warnings.

    Errors (structural defects): E1 ``no_sets``, E2 ``reps_out_of_range``,
    E3 ``too_many_sets``, E4 ``blank_exercise_name``,
    E5 ``duplicate_exercise_name``, E6 ``non_positive_rest``.

    Warnings (advisory): W1 ``unknown_exercise_name``,
    W2 ``no_intensity_anchor``, W3 ``empty_block``.

    W1 is skipped for blank names (E4 already covers them) and W2 is skipped
    for exercises with no sets at all (E1 already covers them, and "no set
    declares intensity" is vacuous there).
    """
    if vocabulary is None:
        vocabulary = ExerciseVocabulary.default()
    errors: list[Finding] = []
    warnings: list[Finding] = []

    for block in blocks:
        block_name = (
            block.name.value if isinstance(block.name, GymBlockName) else str(block.name)
        )
        exercises = [*block.activation, *block.exercises, *block.core]

        if not exercises and not block.prose_items:
            warnings.append(
                Finding(
                    "empty_block",
                    Severity.WARNING,
                    f"block {block_name!r} has no activation, exercises, core exercises "
                    "or prose items",
                    block=block_name,
                )
            )

        seen_names: set[str] = set()
        for exercise in exercises:
            name = exercise.name
            blank = not name.strip()
            normalized = normalize_name(name)

            if blank:
                errors.append(
                    Finding(
                        "blank_exercise_name",
                        Severity.ERROR,
                        "exercise name is blank or whitespace-only",
                        block=block_name,
                        exercise=name,
                    )
                )
            elif normalized in seen_names:
                errors.append(
                    Finding(
                        "duplicate_exercise_name",
                        Severity.ERROR,
                        f"exercise {name!r} repeats a normalized name already used "
                        "in this block",
                        block=block_name,
                        exercise=name,
                    )
                )
            seen_names.add(normalized)

            if not exercise.sets:
                errors.append(
                    Finding(
                        "no_sets",
                        Severity.ERROR,
                        f"exercise {name!r} declares no sets",
                        block=block_name,
                        exercise=name,
                    )
                )
            else:
                for set_index, gym_set in enumerate(exercise.sets, start=1):
                    for field_name, value in (
                        ("reps", gym_set.reps),
                        ("reps_max", gym_set.reps_max),
                    ):
                        if value is not None and not 1 <= value <= MAX_REPS:
                            errors.append(
                                Finding(
                                    "reps_out_of_range",
                                    Severity.ERROR,
                                    f"exercise {name!r} set {set_index} has "
                                    f"{field_name}={value}, outside 1..{MAX_REPS}",
                                    block=block_name,
                                    exercise=name,
                                )
                            )
                if len(exercise.sets) > MAX_SETS:
                    errors.append(
                        Finding(
                            "too_many_sets",
                            Severity.ERROR,
                            f"exercise {name!r} declares {len(exercise.sets)} sets, above "
                            f"the sanity ceiling of {MAX_SETS}",
                            block=block_name,
                            exercise=name,
                        )
                    )
                if all(s.rir is None for s in exercise.sets) and all(
                    s.load is None for s in exercise.sets
                ):
                    warnings.append(
                        Finding(
                            "no_intensity_anchor",
                            Severity.WARNING,
                            f"exercise {name!r} declares neither RIR nor load on any set",
                            block=block_name,
                            exercise=name,
                        )
                    )

            if exercise.rest_s is not None and exercise.rest_s <= 0:
                errors.append(
                    Finding(
                        "non_positive_rest",
                        Severity.ERROR,
                        f"exercise {name!r} declares rest {exercise.rest_s}s, which must "
                        "be positive",
                        block=block_name,
                        exercise=name,
                    )
                )

            if not blank and not vocabulary.contains(name):
                warnings.append(
                    Finding(
                        "unknown_exercise_name",
                        Severity.WARNING,
                        f"exercise name {name!r} is not in the known vocabulary",
                        block=block_name,
                        exercise=name,
                    )
                )

    return GymValidationReport(errors=errors, warnings=warnings)
