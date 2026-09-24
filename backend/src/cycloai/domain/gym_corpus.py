"""Parser for the hand-written gym corpus (``docs/gym.txt``).

The gym corpus is not an export. It is prose written by a coach, with structure
only where the author felt like it, so this parser is deliberately tolerant and
never invents structure:

* The corpus title is line 1.
* Block headers appear in three forms (``- TREN INFERIOR:``, ``- TREN SUPERIOR:``,
  ``CORE:``) and are resolved through :meth:`GymBlockName.from_header`.
* ``ACTIVACIÓN:`` is a section inside a block, not a new block. Because the file
  marks no explicit end, the activation group is closed by the first blank line
  after it opens. That is the only rule this file supports, and it is recorded
  here rather than hidden in the code.
* ``--`` lines are separators and carry no structure.
* Anything that is not a block header, a section header, a rest line or an
  exercise line is a PROSE ITEM, preserved verbatim on its block. The whole CORE
  block is prose, and it stays prose: no exercise is fabricated from it.

Exercise detection is by evidence, not by position: a line is an exercise only
when it carries a set pattern (``3X12``, ``5x20-15-15-10-10``, ``3x8/10``) or a
step count (``10 PASOS``). Everything else is prose. That single discriminator
is what keeps ``3 planchas de 1 minuto.`` and ``3 planchas de 30´´`` out of the
exercise list.

Set notation
------------
The leading number is the set count. Three shapes occur, and the rules below
cover every form in the corpus:

* ``4x14`` -> four sets of 14.
* slash tail (``3x8/10``, ``3x10/12``) -> a rep RANGE: the set count is kept and
  every set carries ``reps`` (lower) and ``reps_max`` (upper).
* hyphen tail -> per-set RAMP (``5x20-15-15-10-10`` = 20, 15, 15, 10, 10), with
  one :class:`GymSet` per element. A hyphen tail of exactly two numbers whose
  declared count is not 2 is instead a RANGE (``4x25-30`` -> four sets of 25-30),
  because a two-set ramp is never written and four sets of 25-30 is what the
  author means. This decision is a judgment call and is asserted in the tests.
* ``5x12-12-10-10`` declares five sets but lists four. The listed ramp is the
  authoritative per-set prescription, so four sets are emitted and the leading
  count is treated as the author's slip. The parser does not "fix" the number
  and does not fail, and the test pins that behaviour.

Rest notation is Spanish: ``´`` is minutes and ``´´`` is seconds, so
``1´ 30´´ REC`` is 90 seconds and ``2´ DE REC`` is 120. ``RIR`` appears on only
three exercises, once inside a parenthetical the author never closed, so it is
always optional and its absence is normal. Author remarks are preserved verbatim
in ``GymExercise.note`` with only the ``RIR`` fragment and surrounding
punctuation removed; no structured tempo field is invented, because the corpus
never structures tempo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .workout import GymBlock, GymBlockName, GymExercise, GymSet

__all__ = [
    "CORPUS_FILENAME",
    "GymCorpusParseError",
    "ParsedGymCorpus",
    "UnparsedLine",
    "parse_gym_corpus",
    "parse_gym_corpus_file",
]

#: Name of the corpus file, resolved by callers against the repository root.
CORPUS_FILENAME = "gym.txt"


class GymCorpusParseError(ValueError):
    """Raised when a line matches a structural token but cannot be assigned."""


@dataclass(frozen=True, slots=True)
class UnparsedLine:
    """A non-blank line that belonged to no block, kept with its source number."""

    line_number: int
    text: str


@dataclass
class ParsedGymCorpus:
    """Result of parsing the gym corpus."""

    title: str | None = None
    blocks: list[GymBlock] = field(default_factory=list)
    unparsed: list[UnparsedLine] = field(default_factory=list)


TITLE_RE = re.compile(r"^EJEMPLO ENTRENAMIENTO GYM PARA CICLISMO\s*:\s*$", re.IGNORECASE)
SEPARATOR = "--"
BLOCK_HEADER_RE = re.compile(
    r"^-?\s*(TREN INFERIOR|TREN SUPERIOR|CORE)\s*:\s*$",
    re.IGNORECASE,
)
SECTION_HEADER_RE = re.compile(r"^ACTIVACI[OÓ]N\s*:\s*$", re.IGNORECASE)
# `´` minutes, `´´` or `”`/`"` seconds, optional "DE", required REC.
REST_RE = re.compile(
    r"^(?:(?P<minutes>\d+)\s*[´']\s*)?(?:(?P<seconds>\d+)\s*(?:[´']{2}|[”\"])\s*)?"
    r"(?:DE\s+)?REC\.?$",
    re.IGNORECASE,
)
SET_RE = re.compile(r"(?P<count>\d+)\s*[xX]\s*(?P<tail>\d+(?:\s*[-/]\s*\d+)*)")
STEPS_RE = re.compile(r"^(?P<count>\d+)\s+PASOS\b", re.IGNORECASE)
RIR_RE = re.compile(r"RIR\s*(?P<rir>\d+)", re.IGNORECASE)
ARROW = "-->"


def _build_sets(count: int, tail: str, rir: int | None) -> list[GymSet]:
    """Expand a corpus set token into one :class:`GymSet` per prescribed set."""
    if "/" in tail:
        lower, _, upper = (part.strip() for part in tail.partition("/"))
        return [
            GymSet(reps=int(lower), reps_max=int(upper), rir=rir) for _ in range(count)
        ]

    parts = [int(part.strip()) for part in tail.split("-")]
    if len(parts) == 1:
        return [GymSet(reps=parts[0], rir=rir) for _ in range(count)]
    if len(parts) == 2 and count != 2:
        return [
            GymSet(reps=parts[0], reps_max=parts[1], rir=rir) for _ in range(count)
        ]
    return [GymSet(reps=part, rir=rir) for part in parts]


def _clean_note(text: str) -> str | None:
    """Strip the RIR fragment and separator punctuation, keep the rest verbatim."""
    cleaned = RIR_RE.sub(" ", text)
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .,;:")
    if not cleaned:
        return None
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def _try_exercise(line: str) -> GymExercise | None:
    """Return an exercise when the line carries set or step evidence, else None."""
    name: str | None = None
    body = line

    if ARROW in line:
        head, _, rest = line.partition(ARROW)
        name, body = head.strip().lstrip("-").strip(), rest
    elif ":" in line:
        head, _, rest = line.partition(":")
        name, body = head.strip().lstrip("-").strip(), rest

    rir_match = RIR_RE.search(body)
    rir = int(rir_match.group("rir")) if rir_match else None

    sets_match = SET_RE.search(body)
    if sets_match is not None:
        sets = _build_sets(int(sets_match.group("count")), sets_match.group("tail"), rir)
        if name is None:
            # Reps-first form: "3x25 crunch abdomen" carries no name prefix.
            name = body[sets_match.end() :].strip(" .,:;-")
            note = None
        else:
            note = _clean_note(body[: sets_match.start()] + " " + body[sets_match.end() :])
        return GymExercise(name=name, sets=sets, note=note)

    steps_match = STEPS_RE.match(body.strip()) if name is not None else None
    if steps_match is not None:
        note = _clean_note(body.strip()[steps_match.end() :])
        return GymExercise(
            name=name,
            sets=[GymSet(reps=int(steps_match.group("count")), unit="steps", rir=rir)],
            note=note,
        )

    return None


def parse_gym_corpus(text: str) -> ParsedGymCorpus:
    """Parse the gym corpus text into blocks, with prose preserved verbatim."""
    result = ParsedGymCorpus()
    current: GymBlock | None = None
    in_activation = False
    last_exercise: GymExercise | None = None

    for line_number, raw in enumerate(text.split("\n"), start=1):
        line = raw.strip()

        if not line:
            # The activation group is closed by the first blank line after it.
            if in_activation and current is not None and current.activation:
                in_activation = False
            continue

        if line == SEPARATOR:
            if in_activation:
                in_activation = False
            continue

        if result.title is None and TITLE_RE.match(line):
            result.title = line
            continue

        if BLOCK_HEADER_RE.match(line):
            current = GymBlock(name=GymBlockName.from_header(line))
            result.blocks.append(current)
            in_activation = False
            last_exercise = None
            continue

        if SECTION_HEADER_RE.match(line):
            in_activation = True
            last_exercise = None
            continue

        if REST_RE.match(line):
            if last_exercise is None or current is None:
                raise GymCorpusParseError(
                    f"line {line_number}: rest line has no preceding exercise: {line!r}"
                )
            match = REST_RE.match(line)
            assert match is not None  # narrowed by the guard above
            minutes = int(match.group("minutes") or 0)
            seconds = int(match.group("seconds") or 0)
            if minutes == 0 and seconds == 0:
                raise GymCorpusParseError(
                    f"line {line_number}: rest line declares no duration: {line!r}"
                )
            last_exercise.rest_s = minutes * 60 + seconds
            continue

        exercise = _try_exercise(line)
        if exercise is not None and current is not None:
            if in_activation:
                current.activation.append(exercise)
            else:
                current.exercises.append(exercise)
            last_exercise = exercise
            continue

        if current is not None:
            current.prose_items.append(line)
            continue

        result.unparsed.append(UnparsedLine(line_number, line))

    return result


def parse_gym_corpus_file(path: str | Path) -> ParsedGymCorpus:
    """Parse the corpus from a path, decoded strictly as UTF-8.

    There is deliberately no fallback codec: a corpus that is not UTF-8 must
    fail loudly rather than decode into mojibake that would be parsed as data.
    """
    return parse_gym_corpus(Path(path).read_text(encoding="utf-8"))
