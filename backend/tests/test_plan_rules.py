"""Tests for the plan-level validator (``cycloai.domain.plan_rules``).

Every threshold is exercised AT its boundary in BOTH directions, and every
threshold constant is pinned to its documented value so a silent change fails
the suite:

- weekly load may rise at most +10% over the previous week;
- the habitual cadence is 3:1, with the recovery week dropping volume by
  30-50% (a drop below 30% is NOT a recovery week at all);
- TSB below -20 must prioritise recovery before intensity, TSB above +15 with
  a high CTL is a fresh athlete (never a finding), and sustained TSB below -25
  accumulates fatigue debt (continuity itself is not evaluated from one state).

Load is never converted between metrics: each report uses only the metric the
caller declared ("hours" or "tss"), and a plan is only compared against itself.
"""

from __future__ import annotations

import pytest

from cycloai.domain.plan_rules import (
    PROGRESSION_LIMIT_PCT,
    RECOVERY_DROP_MAX_PCT,
    RECOVERY_DROP_MIN_PCT,
    TSB_DEBT_THRESHOLD,
    TSB_FRESH_THRESHOLD,
    TSB_RECOVERY_THRESHOLD,
    AthleteLoadState,
    PlanValidationReport,
    validate_training_plan,
    weekly_load,
)
from cycloai.domain.workout import (
    CyclingBlock,
    CyclingStep,
    CyclingWorkout,
    MinutesDuration,
    PlanWeek,
    StepRole,
    TrainingPlan,
    TrainingSystem,
    ZoneCode,
    ZoneTarget,
)

HOUR_S = 3600


# --- Builders ----------------------------------------------------------------


def _freeform(seconds: int, name: str = "Salida libre") -> CyclingWorkout:
    """A free-text session: the easiest way to control a week's load in hours."""
    return CyclingWorkout(
        id=f"freeform-{seconds}",
        name=name,
        objective="Base aerobica",
        sources=["test-fixture"],
        prescriptive=False,
        zone_cap=ZoneCode.Z1,
        freeform_duration_s=seconds,
    )


def _z5a_session(minutes: int = 60) -> CyclingWorkout:
    """A prescriptive session with one high-intensity (Z5A) step."""
    step = CyclingStep(
        duration=MinutesDuration(minutes=minutes),
        role=StepRole.ACTIVE,
        target=ZoneTarget(
            system=TrainingSystem.HEART_RATE, zone=ZoneCode.Z5A, intent="A TOPE"
        ),
    )
    return CyclingWorkout(
        id=f"z5a-{minutes}",
        name="Intervalados",
        objective="VO2 max",
        sources=["test-fixture"],
        prescriptive=True,
        blocks=[CyclingBlock(role=StepRole.WORK, steps=[step])],
    )


def _week(number: int, *durations_s: int) -> PlanWeek:
    """A week of free-text sessions, one per duration, controlling load in hours."""
    return PlanWeek(number=number, workouts=[_freeform(seconds) for seconds in durations_s])


def _plan(*weeks: PlanWeek, plan_id: str = "plan-1") -> TrainingPlan:
    return TrainingPlan(id=plan_id, weeks=list(weeks))


def _warning_codes(report: PlanValidationReport) -> list[str]:
    return [finding.code for finding in report.warnings]


def _error_codes(report: PlanValidationReport) -> list[str]:
    return [finding.code for finding in report.errors]


def _not_evaluated_codes(report: PlanValidationReport) -> list[str]:
    return [item.code for item in report.not_evaluated]


# --- Threshold constants are pinned to their documented values ----------------


def test_threshold_constants_match_documented_values() -> None:
    # A silent threshold change must fail the suite, not pass unnoticed.
    assert PROGRESSION_LIMIT_PCT == 10.0
    assert RECOVERY_DROP_MIN_PCT == 30.0
    assert RECOVERY_DROP_MAX_PCT == 50.0
    assert TSB_RECOVERY_THRESHOLD == -20.0
    assert TSB_FRESH_THRESHOLD == 15.0
    assert TSB_DEBT_THRESHOLD == -25.0


# --- R1: weekly load progression, boundary at exactly +10% ---------------------


def test_load_rising_exactly_10_pct_is_not_flagged() -> None:
    # 10 h -> 11 h is exactly the +10% limit: allowed.
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 11 * HOUR_S))
    report = validate_training_plan(plan)
    assert "weekly_load_progression" not in _warning_codes(report)


def test_load_rising_just_over_10_pct_is_flagged() -> None:
    # 10 h -> 11 h + 1 s is one second past the ceiling: flagged.
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 11 * HOUR_S + 1))
    report = validate_training_plan(plan)
    codes = _warning_codes(report)
    assert "weekly_load_progression" in codes
    progression = next(w for w in report.warnings if w.code == "weekly_load_progression")
    assert progression.week == 2


# --- R2: recovery cadence and unload depth ------------------------------------


def test_three_build_weeks_then_exact_50_pct_drop_is_clean() -> None:
    # 10 h -> 10.5 h -> 11 h -> 5.5 h: the recovery drop is exactly the 50%
    # maximum, inside the 30-50% band, and the 3:1 cadence is honoured.
    plan = _plan(
        _week(1, 10 * HOUR_S),
        _week(2, int(10.5 * HOUR_S)),
        _week(3, 11 * HOUR_S),
        _week(4, int(5.5 * HOUR_S)),
    )
    report = validate_training_plan(plan)
    codes = _warning_codes(report)
    assert "recovery_week_cadence" not in codes
    assert "recovery_unload_too_deep" not in codes


def test_four_build_weeks_without_recovery_is_flagged() -> None:
    # +5% every week: no week drops 30%, so the 3:1 pattern is broken.
    plan = _plan(
        _week(1, 10 * HOUR_S),
        _week(2, int(10.5 * HOUR_S)),
        _week(3, int(11.025 * HOUR_S)),
        _week(4, int(11.576 * HOUR_S)),
    )
    report = validate_training_plan(plan)
    cadence = [w for w in report.warnings if w.code == "recovery_week_cadence"]
    assert len(cadence) == 1
    assert cadence[0].week == 1


def test_unload_of_exactly_50_pct_is_not_too_deep() -> None:
    # A single 50% drop is the top of the allowed band: a recovery week, not a
    # warning. (10 h -> 5 h also honours the cadence, so the report is clean.)
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 5 * HOUR_S))
    report = validate_training_plan(plan)
    assert "recovery_unload_too_deep" not in _warning_codes(report)
    assert "recovery_week_cadence" not in _warning_codes(report)


def test_unload_deeper_than_50_pct_is_flagged() -> None:
    # 10 h -> 4.5 h is a 55% drop: past the band's top, so too deep.
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 4.5 * HOUR_S))
    report = validate_training_plan(plan)
    codes = _warning_codes(report)
    assert "recovery_unload_too_deep" in codes
    # It is still a recovery week (>= 30%), so the cadence rule stays silent.
    assert "recovery_week_cadence" not in codes


def test_drop_below_30_pct_is_not_a_recovery_week_at_all() -> None:
    # A 25% drop (10 h -> 7.5 h) is not a shallow recovery week: the 30-50%
    # band defines what a recovery week IS, so it produces neither code, and
    # only the cadence rule can catch the recovery week that never arrives.
    plan = _plan(
        _week(1, 10 * HOUR_S),
        _week(2, 7.5 * HOUR_S),
        _week(3, 7.5 * HOUR_S),
        _week(4, 7.5 * HOUR_S),
    )
    report = validate_training_plan(plan)
    codes = _warning_codes(report)
    assert "recovery_unload_too_deep" not in codes
    assert "recovery_week_cadence" in codes


# --- R3: TSB gating, only when the athlete state is supplied -------------------


def test_without_athlete_state_tsb_rules_are_not_evaluated_not_passed() -> None:
    # Silence must never read as a pass: the TSB rule codes appear in
    # not_evaluated and NONE of them appears as a finding.
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 10.5 * HOUR_S))
    report = validate_training_plan(plan)
    tsb_codes = {"tsb_recovery_priority", "tsb_fatigue_debt", "tsb_fresh_tolerance"}
    assert tsb_codes <= set(_not_evaluated_codes(report))
    assert tsb_codes.isdisjoint(_warning_codes(report))
    assert tsb_codes.isdisjoint(_error_codes(report))


def test_tsb_below_minus_20_with_high_intensity_first_week_is_flagged() -> None:
    plan = _plan(PlanWeek(number=1, workouts=[_z5a_session()]))
    report = validate_training_plan(
        plan, athlete_state=AthleteLoadState(ctl=80, atl=110, tsb=-21)
    )
    assert "tsb_recovery_priority" in _warning_codes(report)


def test_tsb_of_exactly_minus_20_is_not_flagged() -> None:
    # -20 is the threshold itself: only strictly below it prioritises recovery.
    plan = _plan(PlanWeek(number=1, workouts=[_z5a_session()]))
    state = AthleteLoadState(ctl=80, atl=110, tsb=-20.0)
    report = validate_training_plan(plan, athlete_state=state)
    assert "tsb_recovery_priority" not in _warning_codes(report)


def test_tsb_below_minus_20_with_low_intensity_week_is_not_flagged() -> None:
    # Fatigue gates INTENSITY: a low-intensity week is exactly what the
    # threshold asks for, so no TSB finding arises.
    plan = _plan(_week(1, 8 * HOUR_S))
    report = validate_training_plan(plan, athlete_state=AthleteLoadState(ctl=80, atl=110, tsb=-21))
    assert "tsb_recovery_priority" not in _warning_codes(report)


def test_fresh_athlete_with_high_ctl_gets_no_tsb_finding() -> None:
    # TSB above +15 with a high CTL means the athlete tolerates quality work:
    # freshness is deliberately never a finding, even with Z5A in week 1.
    plan = _plan(PlanWeek(number=1, workouts=[_z5a_session()]))
    report = validate_training_plan(plan, athlete_state=AthleteLoadState(ctl=100, atl=70, tsb=16))
    tsb_codes = {"tsb_recovery_priority", "tsb_fatigue_debt", "tsb_fresh_tolerance"}
    assert tsb_codes.isdisjoint(_warning_codes(report))


def test_tsb_below_minus_25_flags_fatigue_debt_and_leaves_continuity_unevaluated() -> None:
    # A single state cannot show that TSB stayed below -25 for two weeks, so
    # the sustained variant is reported as not evaluated, not passed.
    plan = _plan(_week(1, 8 * HOUR_S))
    report = validate_training_plan(
        plan, athlete_state=AthleteLoadState(ctl=80, atl=120, tsb=-26)
    )
    assert "tsb_fatigue_debt" in _warning_codes(report)
    assert "tsb_debt_sustained" in _not_evaluated_codes(report)
    # Low-intensity week: the recovery-priority rule has nothing to say here.
    assert "tsb_recovery_priority" not in _warning_codes(report)


# --- R4: each report uses only the metric the caller declared -------------------


def test_tss_metric_with_non_power_prescriptions_flags_mismatch() -> None:
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 10 * HOUR_S))
    report = validate_training_plan(plan, load_metric="tss", non_power_prescriptions=3)
    assert "load_metric_mismatch" in _warning_codes(report)


def test_hours_metric_never_flags_metric_mismatch() -> None:
    # Hours are always derivable: the non-power count is irrelevant to them.
    plan = _plan(_week(1, 10 * HOUR_S), _week(2, 10 * HOUR_S))
    report = validate_training_plan(plan, load_metric="hours", non_power_prescriptions=3)
    assert "load_metric_mismatch" not in _warning_codes(report)


def test_same_plan_in_hours_and_tss_uses_only_its_own_metric() -> None:
    # The same plan is compared against itself in ONE metric per report: the
    # hours report never carries the tss-only mismatch finding (even with 3
    # non-power prescriptions), and each metric measures its own weekly load.
    # Structured sessions, because free-text sessions carry no TSS estimate.
    plan = _plan(
        PlanWeek(number=1, workouts=[_z5a_session(60)]),
        PlanWeek(number=2, workouts=[_z5a_session(68)]),
    )

    hours_report = validate_training_plan(plan, load_metric="hours", non_power_prescriptions=3)
    tss_report = validate_training_plan(plan, load_metric="tss", non_power_prescriptions=0)

    assert "load_metric_mismatch" not in _warning_codes(hours_report)
    assert "load_metric_mismatch" not in _warning_codes(tss_report)
    # The +10% violation is real in both metrics, each measured on its own load.
    assert "weekly_load_progression" in _warning_codes(hours_report)
    assert "weekly_load_progression" in _warning_codes(tss_report)
    assert weekly_load(plan.weeks[0], "hours") == 1.0
    assert weekly_load(plan.weeks[0], "tss") == pytest.approx(107.5)  # 1 h at the Z5 midpoint
    assert weekly_load(plan.weeks[0], "tss") != weekly_load(plan.weeks[0], "hours")


# --- Structural errors and the clean plan -------------------------------------


def test_blank_plan_id_is_an_error_and_not_ok() -> None:
    report = validate_training_plan(_plan(_week(1, 10 * HOUR_S), plan_id="   "))
    assert "blank_plan_id" in _error_codes(report)
    assert report.ok is False
    assert report.is_valid is False


def test_valid_plan_is_ok() -> None:
    # 10 h -> 10.5 h -> 11 h -> 6 h (a 45% recovery drop): clean on every rule.
    plan = _plan(
        _week(1, 10 * HOUR_S),
        _week(2, int(10.5 * HOUR_S)),
        _week(3, 11 * HOUR_S),
        _week(4, 6 * HOUR_S),
    )
    report = validate_training_plan(
        plan, athlete_state=AthleteLoadState(ctl=80, atl=84, tsb=-5)
    )
    assert report.errors == []
    assert report.warnings == []
    assert report.not_evaluated == []
    assert report.ok is True
    assert report.is_valid is True
