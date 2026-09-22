"""Canonical Pydantic v2 domain schema for training plans (feature doc section 3.2).

Structural invariants enforced here (feature doc section 3.1):

- I1: a step target carries a zone code and optional free-text intent; the schema
  offers no field for absolute bpm or watts and forbids unknown extras.
- I2: zone codes are the closed corpus set defined in ``cycloai.domain.zones``.
- I5: ``total_duration_s`` and ``estimated_tss`` are computed fields derived from
  the structure; they are not caller-supplied inputs.
- I6: ``prescriptive: false`` is a first-class shape for free-text sessions: a zone
  cap plus a duration, with no fabricated interval blocks.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from cycloai.domain.zones import ZoneCode

__all__ = [
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
    "SecondsDuration",
    "StepDuration",
    "StepRole",
    "TrainingPlan",
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
    """Step target: a closed-set zone code plus optional free-text intent (I1).

    Intent annotations observed in the corpus (``APRIETA``, ``A TOPE``, ``NO TIENES
    QUE LLEGAR A ESTE PULSO``) are coach intents, not zones; they live here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["zone"] = "zone"
    zone: ZoneCode
    intent: str | None = None


class CyclingStep(BaseModel):
    """One step of a cycling session: duration, role and a zone target (I1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration: StepDuration
    role: StepRole
    target: ZoneTarget


class CyclingBlock(BaseModel):
    """A group of steps repeated ``repeat_count`` times (corpus ``Repetir N veces``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: StepRole
    steps: Annotated[list[CyclingStep], Field(min_length=1)]
    repeat_count: int = Field(default=1, gt=0)


# TSS per hour midpoints quoted from knowledge-base/training/zonas-entrenamiento-potencia.md:
#   Z1 15-25, Z2 40-60, Z3 65-80, Z4 80-95, Z5 95-120.
# The corpus sub-zones Z5A/Z5B/Z5C refine Coggan Z5, whose midpoint (107.5) is used
# as a documented proxy; the KB document quantifies no TSS/h beyond these bands.
_TSS_PER_HOUR_MIDPOINT: dict[ZoneCode, float] = {
    ZoneCode.Z1: 20.0,
    ZoneCode.Z2: 50.0,
    ZoneCode.Z3: 72.5,
    ZoneCode.Z4: 87.5,
    ZoneCode.Z5A: 107.5,
    ZoneCode.Z5B: 107.5,
    ZoneCode.Z5C: 107.5,
}


class CyclingWorkout(BaseModel):
    """A cycling session, either prescriptive (structured blocks) or free text (I6)."""

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
    sources: Annotated[list[str], Field(min_length=1)]

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
        """Derived TSS estimate from zone durations (I5); 0.0 for free-text sessions."""
        zone_seconds: dict[ZoneCode, int] = {}
        for block in self.blocks:
            for step in block.steps:
                code = step.target.zone
                step_seconds = step.duration.total_seconds * block.repeat_count
                zone_seconds[code] = zone_seconds.get(code, 0) + step_seconds
        raw = sum(
            seconds / 3600 * _TSS_PER_HOUR_MIDPOINT[code] for code, seconds in zone_seconds.items()
        )
        return round(raw, 1)


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
    """One set: reps plus optional RIR, load and tempo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reps: int = Field(gt=0)
    rir: Annotated[int | None, Field(ge=0)] = None
    load: GymLoad | None = None
    tempo: str | None = None


class GymExercise(BaseModel):
    """An exercise with its sets and optional rest."""

    model_config = ConfigDict(extra="forbid")

    name: str
    sets: Annotated[list[GymSet], Field(min_length=1)]
    rest_s: Annotated[int | None, Field(gt=0)] = None


class GymBlockName(StrEnum):
    """Closed corpus vocabulary for gym block names (``docs/gym.txt``)."""

    LOWER_BODY = "TREN INFERIOR"
    UPPER_BODY = "TREN SUPERIOR"
    CORE = "CORE"


class GymBlock(BaseModel):
    """A gym session block: activation, main exercises and core work."""

    model_config = ConfigDict(extra="forbid")

    name: GymBlockName
    activation: list[GymExercise] = []
    exercises: list[GymExercise] = []
    core: list[GymExercise] = []


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
