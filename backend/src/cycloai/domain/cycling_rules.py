"""Cycling rule validator for CycloAI generated workouts.

Primary entry point: :func:`validate_cycling_payload`, which validates the RAW
generator payload (a mapping, as produced before parsing into the domain
model). This is deliberate and it is the ONLY genuine enforcement point of
invariant I1 (no absolute physiological targets in generated workouts):

the domain model cannot hold ``bpm``/``watts`` fields (``extra="forbid"`` on
every pydantic model, invariant I1), so an offending value is discarded by
pydantic BEFORE any model-level check could run. A validator inspecting a
:class:`cycloai.domain.workout.CyclingWorkout` can therefore never observe an
I1 violation and a model-level I1 check would be vacuous. The raw payload is
the only place where an absolute magnitude can still be seen and rejected.

:func:`validate_parsed_workout` exists for :class:`ParsedWorkout` values from
``cycloai.domain.cycling_corpus``: only they carry the structurally captured
``Repetir N veces`` markers (the domain model has no field for them), so the
repeat-duration rule can only be evaluated there.

Rules
-----
Errors (structural/invariant defects):

- ``absolute_target_forbidden`` (I1): any mapping in the payload carrying an
  absolute physiological magnitude, detected BY KEY NAME. The rejected keys
  are ``bpm``, ``watts``, ``w``, ``power``, ``hr``, ``heart_rate_bpm``,
  ``vo2`` and ``ftp_watts``. Detection is on keys, never on values, so the
  legitimate system identifier ``"system": "heart_rate"`` is NOT a magnitude
  and never triggers this rule (guarded by an explicit test).
- ``missing_provenance`` (I3): ``sources`` absent, empty, or carrying only
  blank entries.
- ``missing_warmup`` / ``missing_cooldown``: a prescriptive workout whose
  steps include no step (or block) with that role.
- ``unresolvable_zone``: ONLY evaluated when an
  :class:`~cycloai.domain.zones.AthleteThresholds` is supplied. The check is
  delegated to :func:`cycloai.domain.zones.resolve_target`: a zone whose
  system differs from the athlete's declared system raises
  :class:`~cycloai.domain.zones.MissingThresholdError` (there is deliberately
  no conversion) and a code that does not exist in that system raises
  :class:`~cycloai.domain.zones.UnknownZoneCodeError`; both surface as this
  error with the original exception message preserved.
- ``empty_workout``: a prescriptive workout with no blocks or no steps at all.
  When it fires, the warm-up/cool-down role checks are skipped: an empty
  workout trivially has no roles and reporting both would be noise.

Warnings (advisory):

- ``repeat_duration_unreliable``: the parsed workout carries ``Repetir N
  veces`` markers. Measured fact: 24 of the 27 prescriptive corpus workouts
  carry such markers, and their semantics are UNRESOLVED (the exporter both
  repeats groups textually and places the marker, so it is unclear whether it
  closes a repeated group or states a count). The parser captures the markers
  structurally and never expands them, so the parsed ``total_duration_s`` —
  and therefore ``estimated_tss`` — UNDERSTATES those sessions. This
  validator does not expand or interpret the markers either; naming the
  uncertainty is the whole point of the warning.
- ``missing_system``: a zone reference that does not declare its training
  system. A warning, not an error, because the domain model (``ZoneTarget``
  with a required ``system``) would reject the payload anyway; the point of
  the warning is to name the cause clearly at generation time.

Not evaluated
-------------
When ``thresholds`` is omitted, zone resolvability is NOT silently passed: a
finding with code ``unresolvable_zone`` is recorded in the report's
``not_evaluated`` list so consumers can distinguish "checked and fine" from
"never checked".
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from cycloai.domain.cycling_corpus import ParsedWorkout
from cycloai.domain.workout import StepRole, ZoneTarget
from cycloai.domain.zones import (
    AthleteThresholds,
    TrainingSystem,
    ZoneCode,
    ZoneError,
    ZoneRef,
    resolve_target,
)

__all__ = [
    "CyclingValidationReport",
    "Finding",
    "Severity",
    "validate_cycling_payload",
    "validate_parsed_workout",
]


class Severity(StrEnum):
    """Severity of a validation finding."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation finding: stable machine code, severity, message, location.

    ``block_index`` is the 0-based position of the enclosing block in
    ``payload["blocks"]`` (or ``workout.blocks``) and ``step_index`` the
    0-based position of the step within THAT block, so every finding can be
    acted on without re-deriving context. Both are ``None`` for
    workout-level findings.
    """

    code: str
    severity: Severity
    message: str
    block_index: int | None = None
    step_index: int | None = None


@dataclass(frozen=True, slots=True)
class CyclingValidationReport:
    """Result of validating a cycling payload or parsed workout.

    Mirrors the gym validator's shape (``errors``/``warnings`` plus the
    ``ok``/``is_valid`` aliases) and adds ``not_evaluated``: rules that could
    not be evaluated because the required input (athlete thresholds) was not
    supplied. Warnings do not block; only errors make ``ok`` false.
    """

    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    not_evaluated: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there are no errors; warnings and unevaluated rules do not block."""
        return not self.errors

    @property
    def is_valid(self) -> bool:
        """Alias of :attr:`ok`."""
        return not self.errors


#: Keys that mark an ABSOLUTE physiological magnitude on a target object.
#: Detection is by key name only; the values are irrelevant (in particular the
#: legitimate system identifier ``"system": "heart_rate"`` is a VALUE under the
#: ``system`` key, which is not in this set, so it can never false-positive).
_ABSOLUTE_MAGNITUDE_KEYS: frozenset[str] = frozenset(
    {"bpm", "watts", "w", "power", "hr", "heart_rate_bpm", "vo2", "ftp_watts"}
)

_WARMUP = StepRole.WARMUP.value
_COOLDOWN = StepRole.COOLDOWN.value

_NOT_EVALUATED_ZONES = Finding(
    code="unresolvable_zone",
    severity=Severity.WARNING,
    message=(
        "zone resolvability was not evaluated: no athlete thresholds were "
        "supplied, so zone references were neither confirmed nor refuted"
    ),
)


def _magnitude_finding(
    keys: list[str], block_index: int | None, step_index: int | None
) -> Finding:
    quoted = ", ".join(repr(key) for key in keys)
    return Finding(
        code="absolute_target_forbidden",
        severity=Severity.ERROR,
        message=(
            f"invariant I1: mapping carries absolute physiological magnitude "
            f"key(s) {quoted}; a target must carry a zone plus intent or an "
            f"RPE, never a bpm/watt figure"
        ),
        block_index=block_index,
        step_index=step_index,
    )


def _scan_magnitudes(
    node: object,
    key: str | None,
    block_index: int | None,
    step_index: int | None,
    out: list[Finding],
) -> None:
    """Recursively collect every mapping carrying an absolute-magnitude key.

    The whole payload is scanned, not only ``target`` objects: an absolute
    magnitude smuggled anywhere in a generated workout violates I1 just the
    same. An offending mapping is reported once as a whole and its children
    are not re-scanned (they are covered by the report).
    """
    if isinstance(node, Mapping):
        hits = sorted(_ABSOLUTE_MAGNITUDE_KEYS.intersection(node))
        if hits:
            out.append(_magnitude_finding(hits, block_index, step_index))
            return
        for child_key, child in node.items():
            _scan_magnitudes(child, child_key, block_index, step_index, out)
    elif isinstance(node, list):
        if key == "blocks":
            for index, item in enumerate(node):
                _scan_magnitudes(item, key, index, step_index, out)
        elif key == "steps":
            for index, item in enumerate(node):
                _scan_magnitudes(item, key, block_index, index, out)
        else:
            for item in node:
                _scan_magnitudes(item, key, block_index, step_index, out)


def _iter_zone_targets(payload: Mapping) -> Iterator[tuple[int, int, Mapping]]:
    """Yield ``(block_index, step_index, target)`` for every zone reference."""
    blocks = payload.get("blocks")
    if not isinstance(blocks, list):
        return
    for block_index, block in enumerate(blocks):
        if not isinstance(block, Mapping):
            continue
        steps = block.get("steps")
        if not isinstance(steps, list):
            continue
        for step_index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                continue
            target = step.get("target")
            if isinstance(target, Mapping) and "zone" in target:
                yield block_index, step_index, target


def _payload_roles_and_steps(payload: Mapping) -> tuple[set[str], int]:
    """Collect the role values present and the total step count of a payload."""
    roles: set[str] = set()
    step_count = 0
    blocks = payload.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            steps = block.get("steps")
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, Mapping):
                        role = step.get("role")
                        if isinstance(role, str) and role:
                            roles.add(role)
                        step_count += 1
            block_role = block.get("role")
            if isinstance(block_role, str) and block_role:
                roles.add(block_role)
    return roles, step_count


def _payload_structural_errors(payload: Mapping) -> list[Finding]:
    """``empty_workout`` / ``missing_warmup`` / ``missing_cooldown`` checks."""
    errors: list[Finding] = []
    prescriptive = payload.get("prescriptive", True)
    if not prescriptive:
        # Free-text sessions (I6) carry no blocks and no roles by design.
        return errors
    blocks = payload.get("blocks")
    has_blocks = isinstance(blocks, list) and len(blocks) > 0
    roles, step_count = _payload_roles_and_steps(payload)
    if not has_blocks or step_count == 0:
        errors.append(
            Finding(
                code="empty_workout",
                severity=Severity.ERROR,
                message=(
                    "prescriptive workout carries no blocks or no steps at all"
                ),
            )
        )
        return errors
    if _WARMUP not in roles:
        errors.append(
            Finding(
                code="missing_warmup",
                severity=Severity.ERROR,
                message="prescriptive workout has no warm-up role in any step",
            )
        )
    if _COOLDOWN not in roles:
        errors.append(
            Finding(
                code="missing_cooldown",
                severity=Severity.ERROR,
                message="prescriptive workout has no cool-down role in any step",
            )
        )
    return errors


def _provenance_errors(payload: Mapping) -> list[Finding]:
    sources = payload.get("sources")
    ok = isinstance(sources, list) and any(
        isinstance(entry, str) and entry.strip() for entry in sources
    )
    if ok:
        return []
    return [
        Finding(
            code="missing_provenance",
            severity=Severity.ERROR,
            message=(
                "invariant I3: 'sources' is absent, empty or blank; every "
                "workout must cite at least one source"
            ),
        )
    ]


def _zone_errors_and_warnings(
    zone_targets: Iterator[tuple[int, int, Mapping]],
    thresholds: AthleteThresholds | None,
) -> tuple[list[Finding], list[Finding]]:
    errors: list[Finding] = []
    warnings: list[Finding] = []
    for block_index, step_index, target in zone_targets:
        system = target.get("system")
        if not isinstance(system, str) or not system.strip():
            warnings.append(
                Finding(
                    code="missing_system",
                    severity=Severity.WARNING,
                    message=(
                        "zone reference declares no training system; the domain "
                        "model requires one (a bare zone code is ambiguous "
                        "across the power and heart-rate vocabularies) and will "
                        "reject this step"
                    ),
                    block_index=block_index,
                    step_index=step_index,
                )
            )
            continue
        if thresholds is None:
            continue
        try:
            ref = ZoneRef(TrainingSystem(system), ZoneCode(target["zone"]))
            resolve_target(ref, thresholds)
        except (ZoneError, ValueError) as exc:
            # MissingThresholdError / UnknownZoneCodeError come straight from
            # resolve_target (or the ZoneRef vocabulary types); the original
            # message is preserved so the cause is never reimplemented here.
            errors.append(
                Finding(
                    code="unresolvable_zone",
                    severity=Severity.ERROR,
                    message=f"zone reference cannot be resolved for this athlete: {exc}",
                    block_index=block_index,
                    step_index=step_index,
                )
            )
    return errors, warnings


def validate_cycling_payload(
    payload: Mapping, *, thresholds: AthleteThresholds | None = None
) -> CyclingValidationReport:
    """Validate a RAW generator payload (before domain-model parsing).

    This is the ONLY genuine enforcement point of invariant I1: the domain
    model cannot hold ``bpm``/``watts`` fields, so pydantic discards an
    offending value before any model-level check could see it. Here the raw
    mapping is still intact and an absolute magnitude is detectable.

    When ``thresholds`` is omitted, zone resolvability is recorded in
    ``not_evaluated`` instead of passing silently.
    """
    errors: list[Finding] = []
    warnings: list[Finding] = []
    not_evaluated: list[Finding] = []

    _scan_magnitudes(payload, None, None, None, errors)

    errors.extend(_provenance_errors(payload))
    errors.extend(_payload_structural_errors(payload))

    if thresholds is None:
        not_evaluated.append(_NOT_EVALUATED_ZONES)
    zone_errors, zone_warnings = _zone_errors_and_warnings(
        _iter_zone_targets(payload), thresholds
    )
    errors.extend(zone_errors)
    warnings.extend(zone_warnings)

    return CyclingValidationReport(
        errors=errors, warnings=warnings, not_evaluated=not_evaluated
    )


def validate_parsed_workout(
    parsed: ParsedWorkout, *, thresholds: AthleteThresholds | None = None
) -> CyclingValidationReport:
    """Validate a :class:`~cycloai.domain.cycling_corpus.ParsedWorkout`.

    Only this entry point can evaluate ``repeat_duration_unreliable``: the
    structurally captured ``Repetir N veces`` markers exist solely on
    ``ParsedWorkout`` (the domain model has no field for them). The markers
    are NEVER expanded or interpreted here — their semantics are unresolved —
    so the parsed duration and TSS keep understating those sessions and the
    warning is what names that fact.

    Structural role checks run on ``parsed.workout`` when present; free-text
    parsed workouts (``workout is None``) carry nothing structural to check.
    """
    errors: list[Finding] = []
    warnings: list[Finding] = []
    not_evaluated: list[Finding] = []

    workout = parsed.workout
    if workout is not None and workout.prescriptive:
        roles = {block.role.value for block in workout.blocks}
        roles.update(step.role.value for block in workout.blocks for step in block.steps)
        step_count = sum(len(block.steps) for block in workout.blocks)
        if step_count == 0:
            errors.append(
                Finding(
                    code="empty_workout",
                    severity=Severity.ERROR,
                    message=(
                        "prescriptive workout carries no blocks or no steps at all"
                    ),
                )
            )
        else:
            if _WARMUP not in roles:
                errors.append(
                    Finding(
                        code="missing_warmup",
                        severity=Severity.ERROR,
                        message=(
                            "prescriptive workout has no warm-up role in any step"
                        ),
                    )
                )
            if _COOLDOWN not in roles:
                errors.append(
                    Finding(
                        code="missing_cooldown",
                        severity=Severity.ERROR,
                        message=(
                            "prescriptive workout has no cool-down role in any step"
                        ),
                    )
                )
        if thresholds is None:
            not_evaluated.append(_NOT_EVALUATED_ZONES)
        for block_index, block in enumerate(workout.blocks):
            for step_index, step in enumerate(block.steps):
                target = step.target
                if not isinstance(target, ZoneTarget) or thresholds is None:
                    continue
                try:
                    resolve_target(ZoneRef(target.system, target.zone), thresholds)
                except ZoneError as exc:
                    errors.append(
                        Finding(
                            code="unresolvable_zone",
                            severity=Severity.ERROR,
                            message=(
                                f"zone reference cannot be resolved for this "
                                f"athlete: {exc}"
                            ),
                            block_index=block_index,
                            step_index=step_index,
                        )
                    )

    if parsed.repeat_markers:
        warnings.append(
            Finding(
                code="repeat_duration_unreliable",
                severity=Severity.WARNING,
                message=(
                    f"the parsed workout carries {len(parsed.repeat_markers)} "
                    f"'Repetir N veces' markers whose semantics are unresolved "
                    f"(24 of the 27 prescriptive corpus workouts carry such "
                    f"markers); the parser never expands them, so the parsed "
                    f"duration and therefore the estimated TSS understate this "
                    f"session. No expansion or interpretation is attempted."
                ),
            )
        )

    return CyclingValidationReport(
        errors=errors, warnings=warnings, not_evaluated=not_evaluated
    )
