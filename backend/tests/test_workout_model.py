"""Tests for the canonical Pydantic domain schema (T2), including invariants I1, I2, I5, I6."""

import pytest
from pydantic import ValidationError

from cycloai.domain.workout import (
    ClockDuration,
    CyclingBlock,
    CyclingStep,
    CyclingWorkout,
    GymBlock,
    GymBlockName,
    GymExercise,
    GymLoadAbsoluteKg,
    GymLoadPctOneRm,
    GymSet,
    MinutesDuration,
    PlanWeek,
    SecondsDuration,
    StepRole,
    TrainingPlan,
    ZoneTarget,
)

CORPUS_SOURCES = ["docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt"]


def make_step(zone: str = "Z2", **overrides) -> CyclingStep:
    payload = {
        "role": StepRole.ACTIVE,
        "duration": {"kind": "minutes", "minutes": 15},
        "target": {"kind": "zone", "zone": zone},
    }
    payload.update(overrides)
    return CyclingStep.model_validate(payload)


def make_block(
    steps: list[CyclingStep],
    repeat_count: int = 1,
    role: StepRole = StepRole.ACTIVE,
) -> CyclingBlock:
    return CyclingBlock(role=role, steps=steps, repeat_count=repeat_count)


def make_prescriptive_workout(**overrides) -> CyclingWorkout:
    payload = {
        "id": "E1",
        "name": "Base endurance",
        "objective": "Aerobic base",
        "blocks": [
            make_block(
                [
                    CyclingStep(
                        role=StepRole.WARMUP,
                        duration={"kind": "minutes", "minutes": 30},
                        target={"kind": "zone", "zone": "Z1"},
                    )
                ],
                role=StepRole.WARMUP,
            ),
            make_block(
                [
                    make_step("Z2"),
                    CyclingStep(
                        role=StepRole.RECOVERY,
                        duration={"kind": "minutes", "minutes": 5},
                        target={"kind": "zone", "zone": "Z1"},
                    ),
                ],
                repeat_count=3,
            ),
            make_block(
                [
                    CyclingStep(
                        role=StepRole.COOLDOWN,
                        duration={"kind": "minutes", "minutes": 40},
                        target={"kind": "zone", "zone": "Z1"},
                    )
                ],
                role=StepRole.COOLDOWN,
            ),
        ],
        "sources": CORPUS_SOURCES,
    }
    payload.update(overrides)
    return CyclingWorkout.model_validate(payload)


def make_free_text_workout(**overrides) -> CyclingWorkout:
    payload = {
        "id": "E2",
        "name": "Rodaje suave",
        "objective": "Easy spin",
        "prescriptive": False,
        "zone_cap": "Z2",
        "freeform_duration_s": 7200,
        "blocks": [],
        "notes": "SOLO DARSE UN PASEO. NADA DE FORZAR, NO PASAR DE Z2",
        "sources": CORPUS_SOURCES,
    }
    payload.update(overrides)
    return CyclingWorkout.model_validate(payload)


# --- Duration variants (corpus formats must be represented exactly, not normalised) ---


@pytest.mark.parametrize(
    ("variant", "expected_seconds"),
    [
        (MinutesDuration(minutes=30), 1800),
        (SecondsDuration(seconds=40), 40),
        (ClockDuration(clock="36:20"), 2180),
    ],
)
def test_duration_variants_cover_all_corpus_formats(variant, expected_seconds: int) -> None:
    assert variant.total_seconds == expected_seconds


def test_clock_duration_preserves_the_original_form() -> None:
    duration = ClockDuration.model_validate({"kind": "clock", "clock": "36:20"})
    assert duration.clock == "36:20"
    assert duration.model_dump() == {"kind": "clock", "clock": "36:20", "total_seconds": 2180}


@pytest.mark.parametrize("bad", ["36:2", "1:60", "3620", ""])
def test_clock_duration_rejects_invalid_clock_forms(bad: str) -> None:
    with pytest.raises(ValidationError):
        ClockDuration.model_validate({"kind": "clock", "clock": bad})


def test_step_carries_any_duration_variant() -> None:
    for duration in ({"kind": "seconds", "seconds": 40}, {"kind": "clock", "clock": "1:10"}):
        step = make_step(duration=duration)
        assert step.duration.total_seconds > 0


# --- Invariant I1: no absolute physiological targets ---


def test_i1_target_rejects_smuggled_bpm() -> None:
    with pytest.raises(ValidationError):
        make_step(target={"kind": "zone", "zone": "Z2", "bpm": 127})


def test_i1_target_rejects_smuggled_watts() -> None:
    with pytest.raises(ValidationError):
        ZoneTarget(zone="Z2", watts=250)


def test_i1_step_rejects_undecorated_absolute_fields() -> None:
    with pytest.raises(ValidationError):
        make_step(bpm=67)
    with pytest.raises(ValidationError):
        make_step(watts=200)


# --- Invariant I2: closed corpus zone vocabulary ---


@pytest.mark.parametrize("zone", ["Z8", "Z0", "Z5", "z2", "zone 2", "A TOPE"])
def test_i2_zone_codes_outside_the_closed_set_are_rejected(zone: str) -> None:
    with pytest.raises(ValidationError):
        ZoneTarget(zone=zone)


def test_i2_valid_corpus_codes_are_accepted() -> None:
    for zone in ("Z1", "Z2", "Z3", "Z4", "Z5A", "Z5B", "Z5C"):
        assert ZoneTarget(zone=zone).zone.value == zone


# --- Invariant I5: derived metrics are computed, not supplied ---


def test_i5_total_duration_s_cannot_be_supplied() -> None:
    with pytest.raises(ValidationError):
        make_prescriptive_workout(total_duration_s=1)


def test_i5_estimated_tss_cannot_be_supplied() -> None:
    with pytest.raises(ValidationError):
        make_prescriptive_workout(estimated_tss=999.0)


def test_i5_derived_metrics_are_computed_from_structure() -> None:
    workout = make_prescriptive_workout()
    # 30 min warm-up + 3 x (15 + 5) min main + 40 min cool-down = 7800 s.
    assert workout.total_duration_s == 7800
    # TSS/h midpoints: Z1 20, Z2 50 -> (5100/3600)*20 + (2700/3600)*50 = 65.8.
    assert workout.estimated_tss == pytest.approx(65.8)


def test_i5_derived_metrics_are_serialised() -> None:
    data = make_prescriptive_workout().model_dump()
    assert data["total_duration_s"] == 7800
    assert data["estimated_tss"] == pytest.approx(65.8)


def test_i5_repeat_count_multiplies_step_durations() -> None:
    steps = [
        make_step("Z2"),
        make_step("Z1", role=StepRole.RECOVERY, duration={"kind": "minutes", "minutes": 5}),
    ]
    repeated = make_prescriptive_workout(blocks=[make_block(steps, repeat_count=3)])
    expanded = make_prescriptive_workout(blocks=[make_block(steps) for _ in range(3)])
    assert repeated.total_duration_s == expanded.total_duration_s == 3 * 1200


# --- Invariant I6: free-text sessions are a first-class shape ---


def test_i6_free_text_session_is_representable() -> None:
    workout = make_free_text_workout()
    assert workout.total_duration_s == 7200
    assert workout.estimated_tss == 0.0
    assert workout.zone_cap.value == "Z2"
    assert workout.blocks == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"zone_cap": None},  # missing zone cap
        {"freeform_duration_s": None},  # missing duration
        {"blocks": [make_block([make_step()])]},  # fabricated interval structure
        {"prescriptive": True, "zone_cap": "Z2", "freeform_duration_s": 7200},  # cap on prescr.
        {"prescriptive": True, "freeform_duration_s": 600},  # freeform duration on prescriptive
    ],
)
def test_i6_invalid_prescriptive_combinations_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        make_free_text_workout(**overrides)


def test_i6_prescriptive_workout_requires_blocks() -> None:
    with pytest.raises(ValidationError):
        make_prescriptive_workout(blocks=[])


def test_intent_free_text_is_captured_on_the_target_not_the_zone() -> None:
    step = make_step("Z5B", target={"kind": "zone", "zone": "Z5B", "intent": "A TOPE"})
    assert step.target.zone.value == "Z5B"
    assert step.target.intent == "A TOPE"


def test_sport_is_locked_to_cycling() -> None:
    with pytest.raises(ValidationError):
        make_prescriptive_workout(sport="running")


def test_sources_are_required() -> None:
    with pytest.raises(ValidationError):
        make_prescriptive_workout(sources=[])


# --- Gym shapes ---


def test_gym_set_supports_both_load_variants() -> None:
    pct = GymSet(reps=12, rir=5, load={"kind": "pct_1rm", "pct": 70}, tempo="ritmo normal")
    absolute = GymSet(reps=8, rir=2, load={"kind": "absolute_kg", "kg": 60})
    assert isinstance(pct.load, GymLoadPctOneRm)
    assert isinstance(absolute.load, GymLoadAbsoluteKg)


def test_gym_set_rejects_undecorated_load() -> None:
    with pytest.raises(ValidationError):
        GymSet(reps=10, kg=50)


def test_gym_set_rejects_negative_rir() -> None:
    with pytest.raises(ValidationError):
        GymSet(reps=10, rir=-1)


def test_gym_block_captures_activation_exercises_and_core() -> None:
    activation = GymExercise(
        name="Clamshell gluteo",
        sets=[GymSet(reps=12)],
    )
    press = GymExercise(
        name="Prensa",
        rest_s=90,
        sets=[GymSet(reps=reps, rir=5) for reps in (20, 15, 15, 10, 10)],
    )
    plank = GymExercise(name="Plancha", sets=[GymSet(reps=1, tempo="60 s")])
    block = GymBlock(
        name=GymBlockName.LOWER_BODY,
        activation=[activation],
        exercises=[press],
        core=[plank],
    )
    assert block.name is GymBlockName.LOWER_BODY
    assert block.exercises[0].sets == [
        GymSet(reps=20, rir=5),
        GymSet(reps=15, rir=5),
        GymSet(reps=15, rir=5),
        GymSet(reps=10, rir=5),
        GymSet(reps=10, rir=5),
    ]


def test_gym_block_name_is_the_closed_corpus_vocabulary() -> None:
    for name in ("TREN INFERIOR", "TREN SUPERIOR", "CORE"):
        assert GymBlock(name=name).name.value == name
    with pytest.raises(ValidationError):
        GymBlock(name="BRAZOS")


# --- Plan level ---


def test_plan_week_derives_weekly_load_metrics() -> None:
    free_text = make_free_text_workout()
    core_block = GymBlock(name=GymBlockName.CORE)
    week = PlanWeek(number=1, workouts=[make_prescriptive_workout(), free_text, core_block])
    assert week.total_duration_s == 7800 + 7200
    assert week.total_estimated_tss == pytest.approx(65.8)


def test_plan_requires_at_least_one_week() -> None:
    with pytest.raises(ValidationError):
        TrainingPlan(id="plan-1", weeks=[])
