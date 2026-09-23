"""Canonical Pydantic v2 domain schema for training plans (feature doc section 3.2).

Structural invariants enforced here (feature doc section 3.1):

- I1: a step target carries no absolute physiological magnitude such as bpm or
  watts; it is either a zone code plus optional free-text intent, or a 1-10 RPE.
  RPE is a perceived-exertion scale, not an athlete-specific absolute value, so it
  does not violate I1. The schema forbids unknown extras, so no bpm/watts field
  can be smuggled in.
- I2: zone targets carry a (system, code) pair from the closed vocabularies
  defined in ``cycloai.domain.zones``; the two training systems (power/%FTP
  and heart-rate/%LTHR) are not interchangeable and a code alone is never
  enough.
- I5: ``total_duration_s`` and ``estimated_tss`` are computed fields derived from
  the structure; they are not caller-supplied inputs.
- I6: ``prescriptive: false`` is a first-class shape for free-text sessions: a zone
  cap plus a duration, with no fabricated interval blocks.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from cycloai.domain.zones import ZONES, TrainingSystem, ZoneCode

__all__ = [
    "CadenceTarget",
    "ClockDuration",
    "CyclingBlock",
    "CyclingStep",
    "CyclingWorkout",
    "GymBlock",
    "GymBlockName",
    "GymExercise",
    "GymLoad",
    "GymLoadAbsoluteKg",
    "GymLoadPctOneRm",
    "GymSet",
    "MinutesDuration",
    "PlanWeek",
    "RpeTarget",
    "SecondsDuration",
    "StepDuration",
    "StepRole",
    "StepTarget",
    "TrainingPlan",
    "TrainingSystem",
    "ZoneCode",
    "ZoneTarget",
]


class StepRole(StrEnum):
    """Role of a step or block within a cycling session."""

    WARMUP = "warmup"
    ACTIVE = "active"
    RECOVERY = "recovery"
    COOLDOWN = "cooldown"
    WORK = "work"
    REST = "rest"


# --- Cycling: durations ---------------------------------------------------------------


class MinutesDuration(BaseModel):
    """Corpus form ``N min @ ...``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["minutes"] = "minutes"
    minutes: int = Field(gt=0)

    @computed_field
    @property
    def total_seconds(self) -> int:
        return self.minutes * 60


class SecondsDuration(BaseModel):
    """Corpus form ``N sec @ ...``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["seconds"] = "seconds"
    seconds: int = Field(gt=0)

    @computed_field
    @property
    def total_seconds(self) -> int:
        return self.seconds


class ClockDuration(BaseModel):
    """Corpus form ``mm:ss @ ...`` (e.g. ``36:20``); the original form is preserved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["clock"] = "clock"
    clock: Annotated[str, Field(pattern=r"^\d{1,3}:[0-5]\d$")]

    @computed_field
    @property
    def total_seconds(self) -> int:
        minutes, seconds = self.clock.split(":")
        return int(minutes) * 60 + int(seconds)


StepDuration = Annotated[
    MinutesDuration | SecondsDuration | ClockDuration,
    Field(discriminator="kind"),
]


# --- Cycling: steps, blocks, workouts ---------------------------------------------------


class ZoneTarget(BaseModel):
    """Zone step target: a (system, code) pair plus optional free-text intent (I1).

    ``system`` is REQUIRED with no default: a zone belongs to one training
    system (power/%FTP or heart-rate/%LTHR), the same code means different
    bounds in each, and hiding that choice behind a default would silently
    re-create the flat-vocabulary conflation. The (system, code) pair must
    exist in ``cycloai.domain.zones.ZONES``: power-only codes (``Z5``-``Z7``)
    and heart-rate-only codes (``Z5A``-``Z5C``) are rejected outside their own
    system.

    Intent annotations observed in the corpus (``APRIETA``, ``A TOPE``, ``NO TIENES
    QUE LLEGAR A ESTE PULSO``) are coach intents, not zones; they live here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["zone"] = "zone"
    system: TrainingSystem
    zone: ZoneCode
    intent: str | None = None

    @model_validator(mode="after")
    def _enforce_system_code_pair(self) -> ZoneTarget:
        if (self.system, self.zone) not in ZONES:
            raise ValueError(
                f"zone {self.zone.value} does not exist in the {self.system.value} "
                f"training system"
            )
        return self


class RpeTarget(BaseModel):
    """RPE step target: a 1-10 perceived-exertion value (corpus ``@ N RPE``).

    RPE does not violate invariant I1: I1 forbids absolute physiological
    magnitudes that depend on the individual athlete (heart rate in bpm, power in
    watts). RPE is a bounded subjective scale (1-10), not an athlete-specific
    absolute value, so it stays prescriptive without smuggling in physiology.

    Corpus facts: every ``@ N RPE`` step carries NO zone label, and every
    ``@ N bpm`` step carries one; the two forms are mutually exclusive.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rpe"] = "rpe"
    rpe: Annotated[float, Field(ge=1, le=10)]


StepTarget = Annotated[
    ZoneTarget | RpeTarget,
    Field(discriminator="kind"),
]
"""Discriminated union of step targets: exactly one of zone or RPE per step.

A step with an RPE target carries no zone, and a zone target carries no RPE:
``extra="forbid"`` on both sides makes the opposite field a validation error.
"""


class CadenceTarget(BaseModel):
    """Optional cadence window on a cycling step (corpus ``N-N rpm`` and ``Nrpm``).

    The two corpus cadence forms map faithfully onto one explicit model:
    ``85-95 rpm`` -> ``min_rpm=85, max_rpm=95``, and a single ``90 rpm`` ->
    ``min_rpm=max_rpm=90`` (use :meth:`from_single`); the degenerate window
    keeps the single form without two loose integer fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_rpm: int = Field(ge=1)
    max_rpm: int = Field(ge=1)

    @classmethod
    def from_single(cls, rpm: int) -> CadenceTarget:
        """Map the corpus single-value form ``Nrpm`` onto ``min == max``."""
        return cls(min_rpm=rpm, max_rpm=rpm)

    @model_validator(mode="after")
    def _enforce_order(self) -> CadenceTarget:
        if self.min_rpm > self.max_rpm:
            raise ValueError("cadence min_rpm must not exceed max_rpm")
        return self


class CyclingStep(BaseModel):
    """One cycling step: duration, role, exactly one target, optional cadence.

    The target is either a :class:`ZoneTarget` (corpus ``@ N bpm`` plus a zone
    label) or an :class:`RpeTarget` (corpus ``@ N RPE``, never with a zone label).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration: StepDuration
    role: StepRole
    target: StepTarget
    cadence: CadenceTarget | None = None


class CyclingBlock(BaseModel):
    """A group of steps repeated ``repeat_count`` times (corpus ``Repetir N veces``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: StepRole
    steps: Annotated[list[CyclingStep], Field(min_length=1)]
    repeat_count: int = Field(default=1, gt=0)


# TSS per hour midpoints quoted from knowledge-base/training/zonas-entrenamiento-potencia.md:
#   Z1 15-25, Z2 40-60, Z3 65-80, Z4 80-95, Z5 95-120 ("pero los intervalos
#   rara vez duran 1 hora entera").
# These values come from the POWER document and apply to POWER zone targets
# ONLY: TSS is defined off power (IF = NP/FTP), and the heart-rate document
# (zonas-entrenamiento-pulso.md) quantifies no TSS/h at all, so heart-rate
# targets must never be multiplied by these numbers.
# Z6 and Z7 are deliberately ABSENT: the same document states for zone 6
# "TSS difícil de estimar con precisión en esta zona" and for zone 7 "No se
# cuantifica de manera adecuada con TSS o IF", so no honest midpoint exists;
# a POWER target in Z6 or Z7 is NOT COVERED by TSS (it is counted by
# tss_uncovered_target_count) and is never multiplied by an invented figure.
# The heart-rate-only sub-zone codes Z5A/Z5B/Z5C are likewise absent: they
# belong to the heart-rate vocabulary, not to this power-model table.
_TSS_PER_HOUR_MIDPOINT: dict[ZoneCode, float] = {
    ZoneCode.Z1: 20.0,
    ZoneCode.Z2: 50.0,
    ZoneCode.Z3: 72.5,
    ZoneCode.Z4: 87.5,
    ZoneCode.Z5: 107.5,
}


class CyclingWorkout(BaseModel):
    """A cycling session, either prescriptive (structured blocks) or free text (I6).

    ``sources`` is required but MAY be empty: a model enforces what is ALWAYS
    true, while a requirement that depends on context belongs in the validator
    that has the context. "sources must be non-empty" is only true when there
    was knowledge to cite, and that depends on the retrieval, which the domain
    model cannot see. Keeping it strict here forced callers to choose between
    failing every knowledge-less generation and fabricating a placeholder
    citation — and fabricating one violates the very invariant the field exists
    to serve. The type is still ``list[str]`` so a non-string element is
    rejected here regardless of context.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    sport: Literal["cycling"] = "cycling"
    objective: str
    prescriptive: bool = True
    zone_cap: ZoneCode | None = None
    freeform_duration_s: Annotated[int | None, Field(gt=0)] = None
    blocks: list[CyclingBlock] = []
    notes: str | None = None
    sources: list[str]

    @model_validator(mode="after")
    def _enforce_workout_shape(self) -> CyclingWorkout:
        if self.prescriptive:
            if not self.blocks:
                raise ValueError("prescriptive workout requires at least one block")
            if self.zone_cap is not None:
                raise ValueError("zone_cap is only valid for non-prescriptive (free-text) workouts")
            if self.freeform_duration_s is not None:
                raise ValueError(
                    "freeform_duration_s is only valid for non-prescriptive (free-text) workouts"
                )
        else:
            if self.blocks:
                raise ValueError(
                    "non-prescriptive (free-text) workouts must not carry fabricated blocks"
                )
            if self.zone_cap is None:
                raise ValueError("non-prescriptive (free-text) workout requires zone_cap")
            if self.freeform_duration_s is None:
                raise ValueError(
                    "non-prescriptive (free-text) workout requires freeform_duration_s"
                )
        return self

    @computed_field
    @property
    def total_duration_s(self) -> int:
        """Derived total duration in seconds (I5)."""
        if not self.prescriptive:
            duration = self.freeform_duration_s
            return duration if duration is not None else 0
        return sum(
            block.repeat_count * sum(step.duration.total_seconds for step in block.steps)
            for block in self.blocks
        )

    @computed_field
    @property
    def estimated_tss(self) -> float:
        """Derived TSS estimate from POWER zone durations only (I5).

        TSS is defined off power (IF = NP/FTP), and the TSS/hour midpoints
        below are quoted from the power knowledge-base document, so ONLY steps
        whose target is a POWER ``ZoneTarget`` with a documented midpoint
        (``Z1``-``Z5``). Heart-rate steps, RPE steps and POWER steps in ``Z6``
        or ``Z7`` contribute nothing: the heart-rate knowledge base quantifies
        no TSS/h, and the power document states TSS cannot be quantified for
        its zones 6 and 7, so no honest substitution exists for any of them.
        The omissions are reported by
        :attr:`tss_uncovered_target_count` instead of being hidden, so a 0.0
        can never be mistaken for "no work was prescribed". 0.0 for free-text
        sessions (I6), which carry no steps at all.
        """
        zone_seconds: dict[ZoneCode, int] = {}
        for block in self.blocks:
            for step in block.steps:
                target = step.target
                if (
                    not isinstance(target, ZoneTarget)
                    or target.system is not TrainingSystem.POWER
                ):
                    continue
                code = target.zone
                step_seconds = step.duration.total_seconds * block.repeat_count
                zone_seconds[code] = zone_seconds.get(code, 0) + step_seconds
        raw = 0.0
        for code, seconds in zone_seconds.items():
            midpoint = _TSS_PER_HOUR_MIDPOINT.get(code)
            if midpoint is None:
                # POWER Z6/Z7: the knowledge base quantifies no TSS/h for
                # these zones, so they are uncovered, never estimated.
                continue
            raw += seconds / 3600 * midpoint
        return round(raw, 1)

    @computed_field
    @property
    def tss_uncovered_target_count(self) -> int:
        """Derived count of step targets that TSS cannot represent (I5).

        Every heart-rate zone step, every RPE step and every POWER step in
        ``Z6`` or ``Z7`` is a real prescription with no honest TSS figure
        (TSS is anchored on power, the heart-rate knowledge base quantifies no
        TSS/h, and the power document states TSS cannot quantify its zones 6
        and 7), so this reports how many such
        targets the plan carries — heart-rate, RPE and power Z6/Z7 alike,
        counted per step
        instance (a block repeated N times contributes N per step, matching
        how ``estimated_tss`` aggregates durations). Free-text sessions carry
        no steps and therefore report 0.
        """
        count = 0
        for block in self.blocks:
            for step in block.steps:
                target = step.target
                if (
                    isinstance(target, ZoneTarget)
                    and target.system is TrainingSystem.POWER
                    and target.zone in _TSS_PER_HOUR_MIDPOINT
                ):
                    continue
                # Heart-rate, RPE, and POWER Z6/Z7 (TSS cannot quantify those
                # two zones per the power knowledge base) are all uncovered.
                count += block.repeat_count
        return count


# --- Gym shapes -------------------------------------------------------------------------


class GymLoadPctOneRm(BaseModel):
    """Load expressed as a percentage of one-rep max."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["pct_1rm"] = "pct_1rm"
    pct: float = Field(gt=0)


class GymLoadAbsoluteKg(BaseModel):
    """Load expressed as an absolute weight in kilograms."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["absolute_kg"] = "absolute_kg"
    kg: float = Field(gt=0)


GymLoad = Annotated[GymLoadPctOneRm | GymLoadAbsoluteKg, Field(discriminator="kind")]


class GymSet(BaseModel):
    """One set: reps plus optional RIR, load, tempo and unit.

    Corpus rep forms (``docs/gym.txt``): a plain count (``3X12``), a per-set
    range (``4x25-30``, ``3x8/10`` -> ``reps`` is the lower bound and
    ``reps_max`` the upper bound), and an explicit descending per-set ramp
    (``5x20-15-15-10-10``), which is one :class:`GymSet` per element of
    ``GymExercise.sets`` (the leading number is the list length). The corpus
    also counts a non-rep unit once (``10 PASOS A CADA DIRECCIÓN``); that is
    carried by ``unit`` rather than coerced into a fabricated rep meaning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reps: int = Field(gt=0)
    reps_max: Annotated[int | None, Field(gt=0)] = None
    unit: Literal["reps", "steps"] = "reps"
    rir: Annotated[int | None, Field(ge=0)] = None
    load: GymLoad | None = None
    tempo: str | None = None

    @model_validator(mode="after")
    def _enforce_rep_range(self) -> GymSet:
        if self.reps_max is not None and self.reps_max < self.reps:
            raise ValueError("reps_max must not be lower than reps")
        return self


class GymExercise(BaseModel):
    """An exercise with its sets, optional rest and optional verbatim note.

    ``rest_s`` is expressed in seconds (corpus ``1´ 30´´ REC`` -> 90). ``note``
    carries the author's free prose verbatim (``(la primera de calentamiento)``);
    tempo and similar remarks stay prose because the corpus never structures
    them, so no structured tempo field is modelled.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    sets: Annotated[list[GymSet], Field(min_length=1)]
    rest_s: Annotated[int | None, Field(gt=0)] = None
    note: str | None = None


class GymBlockName(StrEnum):
    """Closed corpus vocabulary for gym block names (``docs/gym.txt``)."""

    LOWER_BODY = "TREN INFERIOR"
    UPPER_BODY = "TREN SUPERIOR"
    CORE = "CORE"

    @classmethod
    def from_header(cls, header: str) -> GymBlockName:
        """Map the three corpus header forms (``- TREN INFERIOR:``, ``CORE:``)
        onto the block identity; the leading dash and trailing colon are
        formatting and carry no identity, so all three forms survive."""
        text = header.strip()
        if text.startswith("-"):
            text = text[1:].strip()
        if text.endswith(":"):
            text = text[:-1].strip()
        return cls(text)


class GymBlock(BaseModel):
    """A gym session block: activation, main exercises, core work and prose lines.

    The ``ACTIVACIÓN:`` sub-header is already covered by the ``activation``
    list, so no extra section type is modelled. ``prose_items`` carries
    first-class freeform lines verbatim (the whole hand-written CORE block,
    ``SIN CALENTAMIENTO.``, the warm-up line) with no fabricated structure.
    """

    model_config = ConfigDict(extra="forbid")

    name: GymBlockName
    activation: list[GymExercise] = []
    exercises: list[GymExercise] = []
    core: list[GymExercise] = []
    prose_items: list[str] = []


# --- Plan level --------------------------------------------------------------------------


class PlanWeek(BaseModel):
    """One training week: its workouts plus derived weekly load metrics (I5)."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(gt=0)
    workouts: list[CyclingWorkout | GymBlock] = []

    @computed_field
    @property
    def total_duration_s(self) -> int:
        """Derived weekly duration; gym blocks carry no duration and contribute 0."""
        return sum(
            workout.total_duration_s
            for workout in self.workouts
            if isinstance(workout, CyclingWorkout)
        )

    @computed_field
    @property
    def total_estimated_tss(self) -> float:
        """Derived weekly TSS estimate from cycling workouts."""
        return round(
            sum(
                workout.estimated_tss
                for workout in self.workouts
                if isinstance(workout, CyclingWorkout)
            ),
            1,
        )


class TrainingPlan(BaseModel):
    """A multi-week training plan (feature doc section 3.2)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    weeks: Annotated[list[PlanWeek], Field(min_length=1)]
