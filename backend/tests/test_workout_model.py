"""Tests for the canonical Pydantic domain schema (T2), including invariants I1, I2, I5, I6."""

import pytest
from pydantic import ValidationError

from cycloai.domain.workout import (
    CadenceTarget,
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
    RpeTarget,
    SecondsDuration,
    StepRole,
    TrainingPlan,
    TrainingSystem,
    ZoneTarget,
)

CORPUS_SOURCES = ["docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt"]


def make_step(zone: str = "Z2", **overrides) -> CyclingStep:
    payload = {
        "role": StepRole.ACTIVE,
        "duration": {"kind": "minutes", "minutes": 15},
        "target": {"kind": "zone", "system": "heart_rate", "zone": zone},
    }
    payload.update(overrides)
    return CyclingStep.model_validate(payload)


def _power_step(zone: str, minutes: int = 15, role: StepRole = StepRole.ACTIVE) -> CyclingStep:
    """A POWER-system zone step, for tests that exercise the TSS arithmetic."""
    return CyclingStep(
        role=role,
        duration={"kind": "minutes", "minutes": minutes},
        target={"kind": "zone", "system": "power", "zone": zone},
    )


def make_block(
    steps: list[CyclingStep],
    repeat_count: int = 1,
    role: StepRole = StepRole.ACTIVE,
) -> CyclingBlock:
    return CyclingBlock(role=role, steps=steps, repeat_count=repeat_count)


def make_prescriptive_workout(system: str = "heart_rate", **overrides) -> CyclingWorkout:
    """A corpus-shaped prescriptive workout.

    ``system`` defaults to ``heart_rate`` because every corpus target is a
    heart-rate zone; tests that exercise the power-derived TSS arithmetic pass
    ``system="power"`` to get the same shape with POWER targets.
    """

    def zone_target(zone: str) -> dict:
        return {"kind": "zone", "system": system, "zone": zone}

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
                        target=zone_target("Z1"),
                    )
                ],
                role=StepRole.WARMUP,
            ),
            make_block(
                [
                    CyclingStep(
                        role=StepRole.ACTIVE,
                        duration={"kind": "minutes", "minutes": 15},
                        target=zone_target("Z2"),
                    ),
                    CyclingStep(
                        role=StepRole.RECOVERY,
                        duration={"kind": "minutes", "minutes": 5},
                        target=zone_target("Z1"),
                    ),
                ],
                repeat_count=3,
            ),
            make_block(
                [
                    CyclingStep(
                        role=StepRole.COOLDOWN,
                        duration={"kind": "minutes", "minutes": 40},
                        target=zone_target("Z1"),
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
        make_step(target={"kind": "zone", "system": "heart_rate", "zone": "Z2", "bpm": 127})


def test_i1_target_rejects_smuggled_watts() -> None:
    with pytest.raises(ValidationError):
        ZoneTarget(system="heart_rate", zone="Z2", watts=250)


def test_i1_step_rejects_undecorated_absolute_fields() -> None:
    with pytest.raises(ValidationError):
        make_step(bpm=67)
    with pytest.raises(ValidationError):
        make_step(watts=200)


# --- Invariant I2: closed zone vocabularies, identified by (system, code) ---


@pytest.mark.parametrize("zone", ["Z8", "Z0", "z2", "zone 2", "A TOPE"])
def test_i2_zone_codes_outside_the_closed_set_are_rejected(zone: str) -> None:
    with pytest.raises(ValidationError):
        ZoneTarget(system=TrainingSystem.HEART_RATE, zone=zone)


def test_i2_valid_corpus_codes_are_accepted_in_the_heart_rate_system() -> None:
    for zone in ("Z1", "Z2", "Z3", "Z4", "Z5A", "Z5B", "Z5C"):
        target = ZoneTarget(system=TrainingSystem.HEART_RATE, zone=zone)
        assert target.zone.value == zone
        assert target.system is TrainingSystem.HEART_RATE


def test_i2_power_vocabulary_is_accepted_in_the_power_system() -> None:
    for zone in ("Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"):
        target = ZoneTarget(system=TrainingSystem.POWER, zone=zone)
        assert target.zone.value == zone
        assert target.system is TrainingSystem.POWER


def test_i2_power_only_code_is_rejected_in_the_heart_rate_system() -> None:
    with pytest.raises(ValidationError):
        ZoneTarget(system=TrainingSystem.HEART_RATE, zone="Z6")


def test_i2_heart_rate_only_code_is_rejected_in_the_power_system() -> None:
    with pytest.raises(ValidationError):
        ZoneTarget(system=TrainingSystem.POWER, zone="Z5A")


def test_i2_zone_target_requires_the_system_field_without_a_default() -> None:
    """The system is REQUIRED: a bare code is never enough, and a default would
    silently re-create the flat-vocabulary conflation."""
    with pytest.raises(ValidationError):
        ZoneTarget(zone="Z2")


# --- RPE targets (corpus `@ N RPE`, never carrying a zone label) ---


@pytest.mark.parametrize("rpe", [1, 5, 8, 10, 6.5])
def test_rpe_target_accepts_values_within_1_to_10(rpe: float) -> None:
    assert RpeTarget(rpe=rpe).rpe == rpe


@pytest.mark.parametrize("rpe", [-1, 0, 0.5, 10.5, 11])
def test_rpe_target_rejects_values_outside_1_to_10(rpe: float) -> None:
    with pytest.raises(ValidationError):
        RpeTarget(rpe=rpe)


def test_step_can_target_rpe_instead_of_a_zone() -> None:
    step = make_step(target={"kind": "rpe", "rpe": 8})
    assert isinstance(step.target, RpeTarget)
    assert step.target.rpe == 8
    assert not hasattr(step.target, "zone")


def test_step_cannot_carry_both_a_zone_and_an_rpe() -> None:
    with pytest.raises(ValidationError):
        make_step(target={"kind": "rpe", "rpe": 8, "zone": "Z2"})
    with pytest.raises(ValidationError):
        make_step(target={"kind": "zone", "system": "heart_rate", "zone": "Z2", "rpe": 8})


def test_rpe_target_rejects_smuggled_bpm() -> None:
    """RPE is not a loophole around I1: no absolute magnitude may ride along."""
    with pytest.raises(ValidationError):
        RpeTarget(rpe=8, bpm=127)


# --- Optional cadence (corpus `N-N rpm` and `Nrpm`) ---


def test_cadence_window_captures_the_range_form() -> None:
    step = make_step(cadence={"min_rpm": 85, "max_rpm": 95})
    assert step.cadence == CadenceTarget(min_rpm=85, max_rpm=95)


def test_single_value_cadence_maps_onto_min_equals_max() -> None:
    cadence = CadenceTarget.from_single(90)
    assert cadence.min_rpm == cadence.max_rpm == 90


def test_cadence_is_optional_and_defaults_to_none() -> None:
    assert make_step().cadence is None


def test_cadence_window_rejects_min_above_max() -> None:
    with pytest.raises(ValidationError):
        CadenceTarget(min_rpm=95, max_rpm=85)


def test_cadence_rejects_non_positive_rpm() -> None:
    with pytest.raises(ValidationError):
        CadenceTarget(min_rpm=0, max_rpm=90)


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
    # This fixture is corpus-faithful: every target is a HEART-RATE zone. TSS is
    # anchored on power (IF = NP/FTP) and the heart-rate knowledge base
    # (zonas-entrenamiento-pulso.md) quantifies no TSS/h at all, so there is no
    # honest per-zone load for these steps. The old expectation of 65.8 here
    # encoded the defect: it multiplied heart-rate durations by TSS/h midpoints
    # quoted from the POWER document, silently treating a heart-rate
    # prescription as a power prescription. TSS is therefore 0.0, and the
    # omission is reported by the uncovered count instead of being hidden.
    assert workout.estimated_tss == 0.0
    # 1 warm-up + 3 x 2 main + 1 cool-down = 8 heart-rate step instances.
    assert workout.tss_uncovered_target_count == 8


def test_i5_power_workout_tss_still_uses_the_power_midpoints() -> None:
    workout = make_prescriptive_workout(
        system="power",
        blocks=[
            make_block(
                [
                    _power_step("Z2", minutes=60),
                    _power_step("Z4", minutes=30),
                ]
            )
        ],
    )
    # Hand arithmetic from the power-document midpoints (Z2 50, Z4 87.5 TSS/h):
    # 60 min at Z2 -> (3600/3600) * 50.0 = 50.0; 30 min at Z4 ->
    # (1800/3600) * 87.5 = 43.75; raw total = 93.75, rounded to the field's
    # 1-decimal precision -> 93.8.
    assert workout.estimated_tss == pytest.approx(93.8)
    assert workout.tss_uncovered_target_count == 0


def test_i5_mixed_workout_tss_covers_only_the_power_steps() -> None:
    workout = make_prescriptive_workout(
        blocks=[
            make_block(
                [
                    make_step("Z2"),  # heart-rate target: duration, never TSS
                    _power_step("Z3", minutes=60),
                ],
                repeat_count=2,
            )
        ]
    )
    # Only the POWER Z3 instances feed TSS: 2 x (3600/3600) * 72.5 = 145.0.
    assert workout.estimated_tss == pytest.approx(145.0)
    # Only the 2 heart-rate instances are uncovered; power ones are covered.
    assert workout.tss_uncovered_target_count == 2


def test_i5_power_z5_uses_the_documented_107_5_midpoint() -> None:
    workout = make_prescriptive_workout(
        system="power",
        blocks=[make_block([_power_step("Z5", minutes=36)])],
    )
    # Hand arithmetic from the power document ("Zona 5 ... TSS por hora: 95-120",
    # midpoint 107.5): 36 min = 2160 s -> (2160/3600) * 107.5 = 0.6 * 107.5
    # = 64.5.
    assert workout.estimated_tss == pytest.approx(64.5)
    assert workout.tss_uncovered_target_count == 0


def test_i5_power_z6_and_z7_are_not_covered_by_tss() -> None:
    """The power document states TSS cannot quantify its zones 6 and 7
    ("TSS difícil de estimar con precisión en esta zona" for Z6, "No se
    cuantifica de manera adecuada con TSS o IF" for Z7), so a POWER target in
    either zone must contribute 0 to the estimate and be counted as uncovered
    instead of raising or being multiplied by an invented figure."""
    workout = make_prescriptive_workout(
        system="power",
        blocks=[
            make_block([_power_step("Z6", minutes=2)]),
            make_block([_power_step("Z7", minutes=1)]),
        ],
    )
    assert workout.estimated_tss == 0.0
    assert workout.tss_uncovered_target_count == 2


def test_i5_power_z6_does_not_raise_alongside_a_covered_zone() -> None:
    workout = make_prescriptive_workout(
        system="power",
        blocks=[make_block([_power_step("Z5", minutes=36), _power_step("Z6", minutes=5)])],
    )
    # Only the Z5 instances feed TSS: (2160/3600) * 107.5 = 64.5; the Z6
    # instance is uncovered, not estimated and not a crash.
    assert workout.estimated_tss == pytest.approx(64.5)
    assert workout.tss_uncovered_target_count == 1


def test_i5_derived_metrics_are_serialised() -> None:
    # A POWER workout, the only kind that carries any TSS: the derived metrics
    # must survive serialisation, including the coverage count.
    data = make_prescriptive_workout(system="power").model_dump()
    assert data["total_duration_s"] == 7800
    # (5100/3600)*20 + (2700/3600)*50 = 28.33... + 37.5 = 65.8.
    assert data["estimated_tss"] == pytest.approx(65.8)
    assert data["tss_uncovered_target_count"] == 0


def test_i5_repeat_count_multiplies_step_durations() -> None:
    steps = [
        make_step("Z2"),
        make_step("Z1", role=StepRole.RECOVERY, duration={"kind": "minutes", "minutes": 5}),
    ]
    repeated = make_prescriptive_workout(blocks=[make_block(steps, repeat_count=3)])
    expanded = make_prescriptive_workout(blocks=[make_block(steps) for _ in range(3)])
    assert repeated.total_duration_s == expanded.total_duration_s == 3 * 1200


def test_i5_rpe_steps_count_duration_but_not_tss() -> None:
    workout = make_prescriptive_workout(
        blocks=[
            make_block(
                [
                    make_step(target={"kind": "rpe", "rpe": 8}),
                    _power_step("Z1", minutes=5),
                ],
                repeat_count=3,
            )
        ]
    )
    # 3 x (15 + 5) min = 3600 s of total duration...
    assert workout.total_duration_s == 3600
    # ...but only the POWER Z1 steps feed the TSS estimate: (900/3600)*20 = 5.0.
    assert workout.estimated_tss == pytest.approx(5.0)
    # The 3 RPE step instances are prescriptions TSS cannot represent.
    assert workout.tss_uncovered_target_count == 3


def test_i5_rpe_steps_are_reported_as_not_covered_by_tss() -> None:
    """Design decision: an RPE prescription is also outside TSS's power anchor,
    so it counts as uncovered. The field exists so a 0.0 estimate can never be
    read as "no work was prescribed", and an RPE step prescribes real work
    that TSS cannot represent — the same population plan_rules'
    load_metric_mismatch warning counts ("heart rate or perceived exertion")."""
    workout = make_prescriptive_workout(
        blocks=[make_block([make_step(target={"kind": "rpe", "rpe": 8})])]
    )
    assert workout.estimated_tss == 0.0
    assert workout.tss_uncovered_target_count == 1


def test_i6_free_text_session_reports_no_uncovered_targets() -> None:
    """Free-text sessions carry no steps (I6): there is nothing to count, so
    their behaviour is unchanged."""
    workout = make_free_text_workout()
    assert workout.estimated_tss == 0.0
    assert workout.tss_uncovered_target_count == 0


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
    step = make_step(
        "Z5B",
        target={"kind": "zone", "system": "heart_rate", "zone": "Z5B", "intent": "A TOPE"},
    )
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


# --- Gym corpus extensions: rep ramps, ranges, prose, units, identity ---


def test_gym_set_rep_ramp_is_an_explicit_per_set_list() -> None:
    """``5x20-15-15-10-10``: the leading 5 is the set count and each element
    carries its own reps, so a descending ramp needs no invented structure."""
    exercise = GymExercise(name="Prensa", sets=[GymSet(reps=reps) for reps in (20, 15, 15, 10, 10)])
    assert [s.reps for s in exercise.sets] == [20, 15, 15, 10, 10]
    assert len(exercise.sets) == 5


def test_gym_set_rep_range_keeps_both_bounds() -> None:
    """``4x25-30`` and ``3x8/10``: a set spans a range, which a single reps
    integer cannot represent."""
    ranged = GymSet(reps=25, reps_max=30)
    alternative = GymSet(reps=8, reps_max=10)
    assert (ranged.reps, ranged.reps_max) == (25, 30)
    assert (alternative.reps, alternative.reps_max) == (8, 10)


def test_gym_set_rejects_a_range_with_max_below_min() -> None:
    """Negative case: the corpus never writes a descending range like
    ``4x30-25`` — only per-set ramps descend, and those are modelled as one
    ``GymSet`` per element, never as an inverted range."""
    with pytest.raises(ValidationError):
        GymSet(reps=30, reps_max=25)


@pytest.mark.parametrize("rir", [None, 4, 5])
def test_gym_set_rir_is_optional(rir: int | None) -> None:
    """RIR appears on only 3 of ~19 corpus exercises; it must never be required."""
    assert GymSet(reps=12, rir=rir).rir == rir


def test_gym_exercise_rest_is_expressed_in_seconds() -> None:
    """Spanish rest notation maps onto seconds: ``1´ 30´´ REC`` -> 90,
    ``30´´ REC`` -> 30."""
    assert GymExercise(name="Prensa", rest_s=90, sets=[GymSet(reps=12)]).rest_s == 90
    assert GymExercise(name="Abducciones", rest_s=30, sets=[GymSet(reps=15)]).rest_s == 30


def test_gym_exercise_note_is_preserved_verbatim() -> None:
    """Author prose stays a verbatim string; no structured tempo field exists."""
    note = "(LAS DOS PRIMERAS A RITMO NORMAL, LAS DOS ÚLTIMAS BAJAS DENTO (4 SEG))"
    exercise = GymExercise(name="Press banca", note=note, sets=[GymSet(reps=12)])
    assert exercise.note == note


def test_gym_set_supports_non_reps_units() -> None:
    """``CAMINATA LATERAL CON BANDA ELÁSTICA: 10 PASOS A CADA DIRECCIÓN.``
    counts steps; the unit is modelled, not coerced into a rep meaning."""
    exercise = GymExercise(
        name="Caminito lateral con banda elástica",
        sets=[GymSet(reps=10, unit="steps")],
    )
    assert exercise.sets[0].unit == "steps"
    assert exercise.sets[0].reps == 10
    # The unit vocabulary is closed to what the corpus provides.
    with pytest.raises(ValidationError):
        GymSet(reps=10, unit="meters")


def test_gym_block_carries_freeform_prose_items_verbatim() -> None:
    """The CORE block is hand-written prose with no sets; each line is kept
    verbatim, with no fabricated exercise or set structure."""
    prose = [
        "PLANCHA FRONTAL 2 APOYOS (codo y pie contrario) 15” cada lado",
        "PUENTE DE PIERNAS FITBALL A UNA PIERNA 10 reps/pierna",
        "SIN CALENTAMIENTO.",
    ]
    block = GymBlock(name=GymBlockName.CORE, prose_items=prose)
    assert block.prose_items == prose
    assert block.prose_items[0] == "PLANCHA FRONTAL 2 APOYOS (codo y pie contrario) 15” cada lado"


def test_gym_block_identity_survives_all_three_header_forms() -> None:
    """Two headers carry a leading dash, one does not; all three collapse onto
    the same closed block identity."""
    for header, expected in (
        ("- TREN INFERIOR:", GymBlockName.LOWER_BODY),
        ("- TREN SUPERIOR:", GymBlockName.UPPER_BODY),
        ("CORE:", GymBlockName.CORE),
    ):
        assert GymBlockName.from_header(header) is expected
        assert GymBlock(name=GymBlockName.from_header(header)).name is expected


def test_gym_activation_subheader_is_covered_by_the_activation_list() -> None:
    """``ACTIVACIÓN:`` groups three exercises; the existing ``activation`` list
    already marks that section, so no additional section type is modelled."""
    activation = [GymExercise(name=f"Activación {i}", sets=[GymSet(reps=12)]) for i in range(3)]
    block = GymBlock(name=GymBlockName.LOWER_BODY, activation=activation)
    assert len(block.activation) == 3


# --- Plan level ---


def test_plan_week_derives_weekly_load_metrics() -> None:
    free_text = make_free_text_workout()
    core_block = GymBlock(name=GymBlockName.CORE)
    # The prescriptive workout uses POWER targets: it is the only kind that
    # carries a TSS estimate at all, and the weekly figure must keep working.
    week = PlanWeek(
        number=1,
        workouts=[make_prescriptive_workout(system="power"), free_text, core_block],
    )
    assert week.total_duration_s == 7800 + 7200
    assert week.total_estimated_tss == pytest.approx(65.8)


def test_plan_requires_at_least_one_week() -> None:
    with pytest.raises(ValidationError):
        TrainingPlan(id="plan-1", weeks=[])
