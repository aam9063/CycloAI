"""Parser for the measured cycling training corpus grammar.

Corpus: ``docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt`` (1727 lines).

Measured grammar facts (authoritative; do not re-derive):

* A line that strips to exactly ``--`` is a workout separator (25 of them).
* Line 1 is the corpus title (``EJEMPLO DE ENTRENAMIENTO PARA CICLISMO:``).
* 29 workouts total: 5 labelled (``E1``, ``E3`` and ``E5`` are interval
  workouts with 7 bpm steps each; ``E2`` and ``E4`` are free text) plus 24
  unlabelled sections that have no header and start with a ``Warm up`` role
  line. ``E2`` carries one line of Spanish prose as its body; ``E4`` has NO
  body at all (its free text lives in the header line itself, e.g.
  ``E4:SALIDA LIBRE: ...``), so its ``free_text`` is ``None`` and its
  ``name`` carries the description.
* Two of the unlabelled sections are RPE-ONLY workouts: 16 steps each whose
  targets are ``@ N RPE`` with no zone label. They are structured workouts,
  NOT free text.
* 361 steps: 329 carry ``@ N bpm`` plus a zone label, 32 carry ``@ N RPE``
  with no zone label. The raw bpm magnitude is deliberately NOT carried into
  the domain model (invariant I1 forbids absolute physiological magnitudes);
  a bpm step is represented by a :class:`ZoneTarget`.
* 319 role lines (``Warm up``, ``Active``, ``Recovery``, ``Cool down``),
  run-length encoded: a role line applies to every following step until the
  next role line, so 42 steps inherit the previous role. A step with no role
  available at all is an error.
* Zone labels resolve ONLY through
  :func:`cycloai.domain.zones.zone_from_label`; never match on label text.
  Complete set: ``Zone 1: Recovery``, ``Zone 2: Aerobic``, ``Zone 3: Tempo``,
  ``Zone 4: SubThreshold``, ``Zone 5A: SuperThreshold``,
  ``Zone 5B: Aerobic Capacity``, ``Zone 5C: Anaerobic Capacity``.
* Duration forms before the target: ``N min``, ``N sec`` and ``N:N`` clock
  form (for example ``36:20``). The clock form is preserved verbatim, never
  normalised (``ClockDuration.clock`` keeps the original string).
* 49 cadence lines, always standalone lines, in two forms: ``N-N rpm`` (35)
  and ``Nrpm`` (14, mapped through :meth:`CadenceTarget.from_single`).
  Cadence belongs to the step it annotates.
* 80 repeat markers ``Repetir N veces`` (N in 1..6), captured structurally.

ASSUMPTION (unresolved): the exporter emits repeated groups textually more
than once AND places the ``Repetir N veces`` marker after them, so it is
unclear whether the marker closes a repeated group or states a repetition
count. This parser captures the marker structurally (count plus the index of
the step it follows, in flattened parse order) and does NOT expand,
deduplicate or interpret it; every parsed block keeps ``repeat_count = 1``.
This interpretation is explicitly NOT settled.

Intent annotations (``APRIETA``, ``A TOPE``, ...) are coach intents, not
zones: they are matched case-insensitively against the six measured strings
and attached to the step they annotate (the step whose zone line they
follow). Zone steps store them in ``ZoneTarget.intent`` (joined with
``" | "`` when a step carries more than one); RPE steps have no intent field
in the domain model, so intents live in
``ParsedWorkout.step_intents`` (aligned with the flattened step order) for
every step. Line classification is tolerant to zone labels appearing either
before or after their step's target line.

Free-text workouts (``E2``, ``E4``) carry no steps and no zone cap in the
corpus, so they cannot satisfy the ``CyclingWorkout`` free-text invariants
(I6 requires a zone cap plus a duration that the corpus does not state);
their ``workout`` field is therefore ``None`` and the prose body is captured
in ``free_text``. Every non-empty line must classify; anything that fits no
grammar class is recorded in ``ParsedCorpus.unparsed`` with its 1-based line
number instead of being dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from cycloai.domain.workout import (
    CadenceTarget,
    ClockDuration,
    CyclingBlock,
    CyclingStep,
    CyclingWorkout,
    MinutesDuration,
    RpeTarget,
    SecondsDuration,
    StepDuration,
    StepRole,
    StepTarget,
    ZoneTarget,
)
from cycloai.domain.zones import ZoneCode, zone_from_label

__all__ = [
    "CORPUS_FILENAME",
    "CyclingCorpusParseError",
    "ParsedCorpus",
    "ParsedWorkout",
    "RepeatMarker",
    "UnparsedLine",
    "parse_cycling_corpus",
    "parse_cycling_corpus_file",
    "parsed_workout_to_dict",
]


class CyclingCorpusParseError(ValueError):
    """Raised when the corpus violates the measured grammar."""


# --- Grammar constants (measured) -------------------------------------------

SEPARATOR = "--"
CORPUS_FILENAME = "EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt"
CORPUS_SOURCE = f"docs/{CORPUS_FILENAME}"

HEADER_RE = re.compile(r"^E(?P<number>\d+):(?P<name>.*)$")
TARGET_RE = re.compile(r"^(?P<duration>.+?) @ (?P<value>\d+) (?P<kind>bpm|RPE)$")
REPEAT_RE = re.compile(r"^Repetir (?P<count>\d+) veces$")
CADENCE_RANGE_RE = re.compile(r"^(?P<low>\d+)-(?P<high>\d+) rpm$")
CADENCE_SINGLE_RE = re.compile(r"^(?P<value>\d+)rpm$")

DURATION_MIN_RE = re.compile(r"^(?P<value>\d+) min$")
DURATION_SEC_RE = re.compile(r"^(?P<value>\d+) sec$")
DURATION_CLOCK_RE = re.compile(r"^(?P<minutes>\d{1,3}):(?P<seconds>[0-5]\d)$")

CORPUS_ROLES: dict[str, StepRole] = {
    "Warm up": StepRole.WARMUP,
    "Active": StepRole.ACTIVE,
    "Recovery": StepRole.RECOVERY,
    "Cool down": StepRole.COOLDOWN,
}

# Matched case-insensitively (the corpus mixes e.g. ``A TOPE`` / ``a tope``).
INTENT_LINES: frozenset[str] = frozenset(
    {
        "aprieta",
        "a tope",
        "aceleración",
        "no tienes que llegar a este pulso",
        "no pasa nada si no llegas al pulso marcado",
    }
)

INTENT_SEPARATOR = " | "


# --- Public data model -------------------------------------------------------


@dataclass(frozen=True)
class UnparsedLine:
    """A non-empty corpus line that fits no known grammar class."""

    line_number: int
    text: str


@dataclass(frozen=True)
class RepeatMarker:
    """A structurally captured ``Repetir N veces`` marker (semantics unresolved)."""

    count: int
    after_step_index: int | None


@dataclass(frozen=True)
class ParsedWorkout:
    label: str | None
    name: str | None
    workout: CyclingWorkout | None
    free_text: str | None
    repeat_markers: tuple[RepeatMarker, ...]
    inherited_role_steps: int
    step_intents: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class ParsedCorpus:
    title: str | None
    workouts: list[ParsedWorkout]
    unparsed: list[UnparsedLine]


# --- Internal parsing state --------------------------------------------------


@dataclass
class _StepData:
    role: StepRole
    duration: StepDuration
    kind: str  # "bpm" | "RPE"
    value: int
    zone: ZoneCode | None = None
    cadence: CadenceTarget | None = None
    intents: list[str] = field(default_factory=list)


@dataclass
class _WorkoutData:
    label: str | None
    name: str | None
    steps: list[_StepData] = field(default_factory=list)
    prose: list[tuple[int, str]] = field(default_factory=list)
    repeat_markers: list[RepeatMarker] = field(default_factory=list)
    inherited_role_steps: int = 0


def _parse_duration(raw: str) -> StepDuration | None:
    text = raw.strip()
    if match := DURATION_MIN_RE.match(text):
        return MinutesDuration(minutes=int(match["value"]))
    if match := DURATION_SEC_RE.match(text):
        return SecondsDuration(seconds=int(match["value"]))
    if match := DURATION_CLOCK_RE.match(text):
        return ClockDuration(clock=text)
    return None


def _parse_cadence(line: str) -> CadenceTarget | None:
    if match := CADENCE_RANGE_RE.match(line):
        return CadenceTarget(min_rpm=int(match["low"]), max_rpm=int(match["high"]))
    if match := CADENCE_SINGLE_RE.match(line):
        return CadenceTarget.from_single(int(match["value"]))
    return None


def _build_step(step: _StepData) -> CyclingStep:
    if step.kind == "RPE":
        target: StepTarget = RpeTarget(rpe=step.value)
    else:
        if step.zone is None:
            raise CyclingCorpusParseError(
                f"bpm step without a zone label (role={step.role}, "
                f"duration={step.duration})"
            )
        intent = INTENT_SEPARATOR.join(step.intents) if step.intents else None
        target = ZoneTarget(zone=step.zone, intent=intent)
    return CyclingStep(
        duration=step.duration, role=step.role, target=target, cadence=step.cadence
    )


def _build_workout(data: _WorkoutData, index: int) -> CyclingWorkout:
    blocks: list[CyclingBlock] = []
    for step_data in data.steps:
        step = _build_step(step_data)
        if not blocks or blocks[-1].role != step_data.role:
            blocks.append(CyclingBlock(role=step_data.role, steps=[step]))
        else:
            blocks[-1].steps.append(step)
    if data.label is not None:
        workout_id = f"cycling-{data.label.lower()}"
        name = data.name or data.label
    else:
        workout_id = f"cycling-unlabelled-{index:02d}"
        name = ""
    return CyclingWorkout(
        id=workout_id,
        name=name,
        objective="",
        sources=[CORPUS_SOURCE],
        blocks=blocks,
    )


def _finalize(
    data: _WorkoutData | None, index: int, unparsed: list[UnparsedLine]
) -> ParsedWorkout | None:
    if data is None:
        return None
    if not data.steps and not data.prose:
        # A labelled workout with no body at all (e.g. E4: the free text lives
        # in its header) is kept as an empty free-text workout; only a truly
        # contentless unlabelled section is dropped.
        if data.label is None:
            return None
        free_text = None
        workout = None
        return ParsedWorkout(
            label=data.label,
            name=data.name,
            workout=workout,
            free_text=free_text,
            repeat_markers=(),
            inherited_role_steps=0,
            step_intents=(),
        )
    if data.steps:
        # Prose lines interleaved with structured steps classify as unparsed,
        # never silently dropped.
        unparsed.extend(UnparsedLine(line_number=n, text=t) for n, t in data.prose)
        free_text = None
    else:
        free_text = "\n".join(text for _, text in data.prose) or None
    workout = _build_workout(data, index) if data.steps else None
    return ParsedWorkout(
        label=data.label,
        name=data.name,
        workout=workout,
        free_text=free_text,
        repeat_markers=tuple(data.repeat_markers),
        inherited_role_steps=data.inherited_role_steps,
        step_intents=tuple(tuple(step.intents) for step in data.steps),
    )


# --- Core parser -------------------------------------------------------------


def parse_cycling_corpus(text: str) -> ParsedCorpus:
    """Parse the full cycling corpus text into a :class:`ParsedCorpus`."""
    title: str | None = None
    workouts: list[ParsedWorkout] = []
    unparsed: list[UnparsedLine] = []

    current: _WorkoutData | None = None
    role: StepRole | None = None
    role_fresh = False  # True right after a role line, before the next step
    pending_zone: ZoneCode | None = None
    pending_zone_line: int | None = None
    pending_intents: list[str] = []
    pending_cadence: CadenceTarget | None = None
    pending_cadence_line: int | None = None

    def reset_step_scope() -> None:
        nonlocal role, role_fresh
        nonlocal pending_zone, pending_zone_line
        nonlocal pending_intents
        nonlocal pending_cadence, pending_cadence_line
        if pending_zone is not None:
            raise CyclingCorpusParseError(
                f"unassigned zone label from line {pending_zone_line} "
                f"cannot belong to any step"
            )
        role = None
        role_fresh = False
        pending_zone = None
        pending_zone_line = None
        pending_intents = []
        pending_cadence = None
        pending_cadence_line = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line == SEPARATOR:
            if parsed := _finalize(current, len(workouts) + 1, unparsed):
                workouts.append(parsed)
            current = None
            reset_step_scope()
            continue

        if match := HEADER_RE.match(line):
            if parsed := _finalize(current, len(workouts) + 1, unparsed):
                workouts.append(parsed)
            name = match["name"].strip()
            current = _WorkoutData(label=f"E{match['number']}", name=name or None)
            reset_step_scope()
            continue

        if line in CORPUS_ROLES:
            # Unlabelled sections have no header: the role line opens them.
            if current is None:
                current = _WorkoutData(label=None, name=None)
            role = CORPUS_ROLES[line]
            role_fresh = True
            continue

        if match := REPEAT_RE.match(line):
            if current is None:
                raise CyclingCorpusParseError(
                    f"line {line_number}: repeat marker outside any workout"
                )
            count = int(match["count"])
            if not 1 <= count <= 6:
                raise CyclingCorpusParseError(
                    f"line {line_number}: repeat count {count} outside 1..6"
                )
            after = len(current.steps) - 1 if current.steps else None
            current.repeat_markers.append(
                RepeatMarker(count=count, after_step_index=after)
            )
            continue

        if match := TARGET_RE.match(line):
            if current is None:
                raise CyclingCorpusParseError(
                    f"line {line_number}: target line outside any workout"
                )
            duration = _parse_duration(match["duration"])
            if duration is None:
                unparsed.append(UnparsedLine(line_number=line_number, text=line))
                continue
            if role is None:
                raise CyclingCorpusParseError(
                    f"line {line_number}: step has no role available "
                    f"(no role line seen for this workout yet)"
                )
            step = _StepData(
                role=role,
                duration=duration,
                kind=match["kind"],
                value=int(match["value"]),
            )
            if pending_zone is not None:
                if match["kind"] != "bpm":
                    raise CyclingCorpusParseError(
                        f"line {line_number}: RPE target cannot carry the "
                        f"pending zone label from line {pending_zone_line}"
                    )
                step.zone = pending_zone
                pending_zone = None
                pending_zone_line = None
            step.intents.extend(pending_intents)
            pending_intents = []
            if pending_cadence is not None:
                step.cadence = pending_cadence
                pending_cadence = None
            if not role_fresh:
                current.inherited_role_steps += 1
            role_fresh = False
            current.steps.append(step)
            continue

        # Zone labels resolve only through zone_from_label.
        try:
            zone = zone_from_label(line)
        except ValueError:
            zone = None
        if zone is not None:
            if current is None:
                raise CyclingCorpusParseError(
                    f"line {line_number}: zone label outside any workout "
                    f"cannot belong to any step"
                )
            last = current.steps[-1] if current.steps else None
            if (
                last is not None
                and last.kind == "bpm"
                and last.zone is None
                and pending_zone is None
            ):
                last.zone = zone
            elif pending_zone is not None:
                raise CyclingCorpusParseError(
                    f"line {line_number}: second consecutive zone label; "
                    f"the one from line {pending_zone_line} is still unassigned"
                )
            else:
                pending_zone = zone
                pending_zone_line = line_number
            continue

        if cadence := _parse_cadence(line):
            if current is None:
                unparsed.append(UnparsedLine(line_number=line_number, text=line))
                continue
            last = current.steps[-1] if current.steps else None
            if last is not None and last.cadence is None and pending_zone is None:
                last.cadence = cadence
            elif pending_cadence is not None:
                raise CyclingCorpusParseError(
                    f"line {line_number}: second consecutive unassigned "
                    f"cadence line; the one from line {pending_cadence_line} "
                    f"is still unassigned"
                )
            else:
                pending_cadence = cadence
                pending_cadence_line = line_number
            continue

        if line.casefold() in INTENT_LINES:
            if current is None:
                unparsed.append(UnparsedLine(line_number=line_number, text=line))
                continue
            last = current.steps[-1] if current.steps else None
            if last is not None and pending_zone is None:
                last.intents.append(line)
            else:
                pending_intents.append(line)
            continue

        # Corpus title: the first content line that fits no structural class.
        if title is None and not workouts and current is None:
            title = line
            continue

        # Free-text prose body: only valid for a workout with no steps yet.
        if not current.steps:
            current.prose.append((line_number, line))
            continue

        unparsed.append(UnparsedLine(line_number=line_number, text=line))

    if pending_zone is not None:
        raise CyclingCorpusParseError(
            f"unassigned zone label from line {pending_zone_line} "
            f"cannot belong to any step"
        )
    if parsed := _finalize(current, len(workouts) + 1, unparsed):
        workouts.append(parsed)

    return ParsedCorpus(title=title, workouts=workouts, unparsed=unparsed)


def parse_cycling_corpus_file(path: str | Path) -> ParsedCorpus:
    """Parse the cycling corpus from a file path (strict UTF-8, no fallback).

    A corpus file that is not valid UTF-8 raises :class:`UnicodeDecodeError`
    instead of being silently decoded into mojibake.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_cycling_corpus(text)


# --- Serialization (shared by the fixture generator and the tests) -----------


def _duration_to_dict(duration: StepDuration) -> dict:
    if isinstance(duration, MinutesDuration):
        return {
            "kind": "minutes",
            "minutes": duration.minutes,
            "raw": f"{duration.minutes} min",
        }
    if isinstance(duration, SecondsDuration):
        return {
            "kind": "seconds",
            "seconds": duration.seconds,
            "raw": f"{duration.seconds} sec",
        }
    return {"kind": "clock", "clock": duration.clock, "raw": duration.clock}


def _target_to_dict(target: StepTarget) -> dict:
    if isinstance(target, RpeTarget):
        return {"kind": "rpe", "rpe": target.rpe, "zone": None}
    return {"kind": "zone", "zone": str(target.zone), "intent": target.intent}


def _cadence_to_dict(cadence: CadenceTarget | None) -> dict | None:
    if cadence is None:
        return None
    return {"min_rpm": cadence.min_rpm, "max_rpm": cadence.max_rpm}


def parsed_workout_to_dict(parsed: ParsedWorkout) -> dict:
    """Deterministic JSON-ready dict for one parsed workout."""
    steps: list[CyclingStep] = []
    if parsed.workout is not None:
        steps = [step for block in parsed.workout.blocks for step in block.steps]
    if len(parsed.step_intents) != len(steps):
        raise CyclingCorpusParseError(
            "step_intents out of alignment with flattened steps"
        )
    serialized_steps = []
    for step, intents in zip(steps, parsed.step_intents, strict=True):
        serialized_steps.append(
            {
                "role": str(step.role),
                "duration": _duration_to_dict(step.duration),
                "target": _target_to_dict(step.target),
                "cadence": _cadence_to_dict(step.cadence),
                "intents": list(intents),
            }
        )
    return {
        "label": parsed.label,
        "name": parsed.name,
        "free_text": parsed.free_text,
        "repeat_markers": [
            {"count": marker.count, "after_step_index": marker.after_step_index}
            for marker in parsed.repeat_markers
        ],
        "steps": serialized_steps,
    }
