"""Plan-level validator: weekly load progression, recovery cadence and TSB gating.

Every threshold in this module comes from the project's own knowledge base or
from the system prompt's behaviour rules. None is invented here, and each is
named at its definition so a reader can check it against the source.

Load metric
-----------
The load metric is DECLARED by the caller and never assumed. TSS is derived from
POWER, while the training corpus prescribes by HEART RATE, so treating TSS as
the universal load would silently mis-measure half the corpus. The knowledge base
itself states the progression rule as "la carga total semanal (medida en TSS o en
horas)", so both ``"hours"`` and ``"tss"`` are supported and a plan is only ever
compared against itself in one metric.

There is deliberately no heart-rate-to-power conversion anywhere in this module:
the relationship is individual and drifts with fitness, fatigue, heat and
duration, so a conversion factor would be fabricated precision.

TSS coverage is reported, not fixed
-----------------------------------
When ``load_metric="tss"`` and the plan contains prescriptions that TSS cannot
represent (heart rate or perceived exertion), the validator emits a warning
naming the count. It does not convert and it does not guess. A later task will
enforce this properly once a zone reference carries its training system.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from .workout import CyclingWorkout, PlanWeek, TrainingPlan, ZoneTarget

__all__ = [
    "HIGH_INTENSITY_PREFIXES",
    "PROGRESSION_LIMIT_PCT",
    "RECOVERY_DROP_MAX_PCT",
    "RECOVERY_DROP_MIN_PCT",
    "RECOVERY_WINDOW_WEEKS",
    "TSB_DEBT_THRESHOLD",
    "TSB_FRESH_THRESHOLD",
    "TSB_RECOVERY_THRESHOLD",
    "AthleteLoadState",
    "LoadMetric",
    "NotEvaluated",
    "PlanFinding",
    "PlanValidationReport",
    "Severity",
    "validate_training_plan",
]

LoadMetric = Literal["hours", "tss"]

#: Weekly load may not rise more than this over the previous week.
#: Source: knowledge-base/training/principios-periodizacion-ciclismo.md —
#: "la carga total semanal (medida en TSS o en horas) no debe aumentar más de un
#: 10% de una semana a la siguiente".
PROGRESSION_LIMIT_PCT = 10.0

#: The habitual pattern is 3:1, with the recovery week dropping volume by 30-50%.
#: Source: same document — "El patrón de carga más habitual es 3:1 ... una semana
#: de recuperación en la que el volumen se reduce entre un 30 y un 50%".
RECOVERY_WINDOW_WEEKS = 4
RECOVERY_DROP_MIN_PCT = 30.0
RECOVERY_DROP_MAX_PCT = 50.0

#: TSB below this must prioritise recovery, and the model must warn explicitly
#: before proposing intensity (system prompt, rules 2 and 3).
TSB_RECOVERY_THRESHOLD = -20.0
#: TSB above this with a high CTL means the athlete is fresh and tolerates
#: quality work, so it must NOT be reported as a problem.
TSB_FRESH_THRESHOLD = 15.0
#: Sustained TSB below this accumulates fatigue debt that the usual 3:1 pattern
#: does not resolve. Source: knowledge-base/training/plan-base-aerobica-16-semanas.md
#: — "Si el TSB cae y permanece por debajo de -25 durante más de dos semanas
#: seguidas, se acumula una deuda de fatiga".
TSB_DEBT_THRESHOLD = -25.0

#: Zone-code prefixes that count as high intensity. Both vocabularies are covered
#: without needing to know which system the plan uses: Coggan's Z5/Z6/Z7, and the
#: corpus's Z5A/Z5B/Z5C. A zone reference will carry its system in a later task,
#: at which point this approximation can be replaced by a system-aware check.
HIGH_INTENSITY_PREFIXES = ("Z5", "Z6", "Z7")

_RELATIVE_TOLERANCE = 1e-9


class Severity(StrEnum):
    """Severity of a validation finding."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class PlanFinding:
    """One validation finding: stable machine code, severity, message, location."""

    code: str
    severity: Severity
    message: str
    week: int | None = None


@dataclass(frozen=True, slots=True)
class NotEvaluated:
    """A rule that was NOT evaluated, with the reason, so silence is never a pass."""

    code: str
    reason: str


@dataclass(frozen=True, slots=True)
class AthleteLoadState:
    """The athlete's current training-load metrics.

    Supplied by the caller; never derived and never invented. A plan validated
    without one has its TSB rules reported as not evaluated rather than passed.
    """

    ctl: float
    atl: float
    tsb: float


@dataclass(frozen=True, slots=True)
class PlanValidationReport:
    """Result of validating a training plan."""

    errors: list[PlanFinding] = field(default_factory=list)
    warnings: list[PlanFinding] = field(default_factory=list)
    not_evaluated: list[NotEvaluated] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there are no structural errors; warnings do not block."""
        return not self.errors

    @property
    def is_valid(self) -> bool:
        """Alias of :attr:`ok`."""
        return not self.errors


def weekly_load(week: PlanWeek, load_metric: LoadMetric) -> float:
    """Weekly load in the declared metric, never converted between metrics."""
    if load_metric == "hours":
        return week.total_duration_s / 3600.0
    return week.total_estimated_tss


def _zone_code_of(target: object) -> str | None:
    """Return the zone code of a step target, or None for RPE and free text."""
    if isinstance(target, ZoneTarget):
        code = target.zone
        return code.value if hasattr(code, "value") else str(code)
    return None


def _is_high_intensity(week: PlanWeek) -> bool:
    """True when the week prescribes any step in a top zone."""
    for workout in week.workouts:
        if not isinstance(workout, CyclingWorkout):
            continue
        for block in workout.blocks or []:
            for step in block.steps:
                code = _zone_code_of(step.target)
                if code is not None and code.startswith(HIGH_INTENSITY_PREFIXES):
                    return True
    return False


def validate_training_plan(
    plan: TrainingPlan,
    *,
    load_metric: LoadMetric = "hours",
    athlete_state: AthleteLoadState | None = None,
    non_power_prescriptions: int = 0,
) -> PlanValidationReport:
    """Validate a training plan's load progression, recovery cadence and TSB gating.

    Args:
        plan: the plan to validate.
        load_metric: ``"hours"`` (always derivable) or ``"tss"`` (power-derived).
            The plan is only ever compared against itself in this one metric.
        athlete_state: the athlete's current load metrics. When omitted, the TSB
            rules are recorded in ``not_evaluated`` instead of passing silently.
        non_power_prescriptions: how many prescriptions in the plan are expressed
            as heart rate or perceived exertion, which TSS cannot represent. Only
            meaningful together with ``load_metric="tss"``.
    """
    report = PlanValidationReport()
    weeks: Sequence[PlanWeek] = plan.weeks

    # R5 — defense in depth: the model already enforces a non-empty week list.
    if not str(plan.id).strip():
        report.errors.append(
            PlanFinding(
                code="blank_plan_id",
                severity=Severity.ERROR,
                message="The plan has a blank id.",
            )
        )
    if not weeks:
        report.errors.append(
            PlanFinding(
                code="empty_plan",
                severity=Severity.ERROR,
                message="The plan has no weeks.",
            )
        )
        return report

    loads = [weekly_load(week, load_metric) for week in weeks]

    # R1 — weekly load progression, at most +10% over the previous week.
    for index in range(1, len(loads)):
        previous, current = loads[index - 1], loads[index]
        if previous <= 0:
            continue
        ceiling = previous * (1 + PROGRESSION_LIMIT_PCT / 100) + previous * _RELATIVE_TOLERANCE
        if current > ceiling:
            increase = (current - previous) / previous * 100
            report.warnings.append(
                PlanFinding(
                    code="weekly_load_progression",
                    severity=Severity.WARNING,
                    message=(
                        f"Week {weeks[index].number} raises load by {increase:.1f}% over the "
                        f"previous week, above the {PROGRESSION_LIMIT_PCT:g}% limit."
                    ),
                    week=weeks[index].number,
                )
            )

    # R2 — recovery cadence. A recovery week is inferred from the load drop
    # itself, using the same 30-50% band the knowledge base defines: a week is a
    # recovery week when its load falls at least 30% below the previous week, so
    # "below 30%" is not a shallow recovery week, it is not a recovery week at all.
    recovery_flags: list[bool] = [False] * len(loads)
    for index in range(1, len(loads)):
        previous, current = loads[index - 1], loads[index]
        if previous <= 0:
            continue
        drop_pct = (previous - current) / previous * 100
        if drop_pct >= RECOVERY_DROP_MIN_PCT:
            recovery_flags[index] = True
            if drop_pct > RECOVERY_DROP_MAX_PCT:
                report.warnings.append(
                    PlanFinding(
                        code="recovery_unload_too_deep",
                        severity=Severity.WARNING,
                        message=(
                            f"Week {weeks[index].number} unloads {drop_pct:.1f}% below the "
                            f"previous week, deeper than the "
                            f"{RECOVERY_DROP_MIN_PCT:g}-{RECOVERY_DROP_MAX_PCT:g}% band."
                        ),
                        week=weeks[index].number,
                    )
                )

    for start in range(len(loads) - RECOVERY_WINDOW_WEEKS + 1):
        window = recovery_flags[start + 1 : start + RECOVERY_WINDOW_WEEKS]
        if not any(window):
            report.warnings.append(
                PlanFinding(
                    code="recovery_week_cadence",
                    severity=Severity.WARNING,
                    message=(
                        f"Weeks {weeks[start].number}-"
                        f"{weeks[start + RECOVERY_WINDOW_WEEKS - 1].number} contain no recovery "
                        f"week; the habitual pattern is 3:1."
                    ),
                    week=weeks[start].number,
                )
            )

    # R3 — TSB gating, only when the athlete's state is supplied.
    if athlete_state is None:
        for code in ("tsb_recovery_priority", "tsb_fatigue_debt", "tsb_fresh_tolerance"):
            report.not_evaluated.append(
                NotEvaluated(
                    code=code,
                    reason=(
                        "No athlete load state was supplied; the metrics are entered manually, "
                        "so nothing is assumed about them."
                    ),
                )
            )
    else:
        tsb = athlete_state.tsb
        if tsb < TSB_RECOVERY_THRESHOLD and _is_high_intensity(weeks[0]):
            report.warnings.append(
                PlanFinding(
                    code="tsb_recovery_priority",
                    severity=Severity.WARNING,
                    message=(
                        f"TSB is {tsb:.1f}, below {TSB_RECOVERY_THRESHOLD:g}; the first week "
                        f"still prescribes high intensity. Recovery must be prioritised and "
                        f"intensity warned about explicitly before it is proposed."
                    ),
                    week=weeks[0].number,
                )
            )
        if tsb < TSB_DEBT_THRESHOLD:
            report.warnings.append(
                PlanFinding(
                    code="tsb_fatigue_debt",
                    severity=Severity.WARNING,
                    message=(
                        f"TSB is {tsb:.1f}, below {TSB_DEBT_THRESHOLD:g}; sustained below that "
                        f"level for more than two consecutive weeks it accumulates fatigue debt "
                        f"the 3:1 pattern does not resolve. Only one state was supplied, so "
                        f"continuity was not checked."
                    ),
                    week=weeks[0].number,
                )
            )
            report.not_evaluated.append(
                NotEvaluated(
                    code="tsb_debt_sustained",
                    reason=(
                        "The sustained-debt variant needs one load state per week, and only a "
                        "single current state was supplied; a per-week history arrives with the "
                        "metrics feature."
                    ),
                )
            )
        # TSB above TSB_FRESH_THRESHOLD is deliberately NOT a finding: a fresh
        # athlete with a high CTL tolerates quality work.

    # R4 — TSS cannot represent heart-rate or perceived-exertion prescriptions.
    if load_metric == "tss" and non_power_prescriptions > 0:
        report.warnings.append(
            PlanFinding(
                code="load_metric_mismatch",
                severity=Severity.WARNING,
                message=(
                    f"{non_power_prescriptions} prescription(s) in this plan are expressed as "
                    f"heart rate or perceived exertion, which TSS cannot represent because TSS "
                    f"is derived from power. The load figures for this plan are incomplete."
                ),
            )
        )

    return report
