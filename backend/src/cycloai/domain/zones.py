"""Closed training-zone vocabularies for the two training systems.

There are TWO training systems in this repository, and they are NOT
interchangeable:

- **Power** (Coggan model): bounds expressed in %FTP, quoted from
  ``knowledge-base/training/zonas-entrenamiento-potencia.md``.
- **Heart rate** (Friel LTHR model): bounds expressed in %LTHR, quoted from
  ``knowledge-base/training/zonas-entrenamiento-pulso.md``.

The zone CODES overlap (Z1-Z4 exist in both) but a bare code means different
things per system: a power ``Z2`` is 56-75% FTP while a heart-rate ``Z2`` is
81-89% LTHR. A zone is therefore always identified by a :class:`ZoneRef`
(system AND code), never by a code alone. The earlier flat vocabulary mixed
codes from the heart-rate-anchored cycling corpus with bounds from the
power-anchored Coggan document; that conflation is a bug this module refuses
to reproduce.

**There is deliberately NO heart-rate-to-power conversion anywhere in this
module.** The relationship between the two anchors is individual (it depends
on the athlete's physiology), and it drifts with fitness, fatigue, heat and
effort duration; in short efforts the heart rate even lags too much to be
meaningful. A fixed conversion factor would be fabricated precision
(``zonas-entrenamiento-pulso.md`` states this explicitly). The system
prescribes in the model the athlete declared and never translates:
:meth:`resolve_target` raises :class:`MissingThresholdError` when the systems
disagree instead of converting.

Measured cycling-corpus labels (complete text, with observed frequencies) —
the corpus is HEART-RATE anchored, so its labels resolve in the heart-rate
system by default:

    Zone 1: Recovery             (140)
    Zone 2: Aerobic              (73)
    Zone 3: Tempo                (32)
    Zone 4: SubThreshold         (20)
    Zone 5A: SuperThreshold      (24)
    Zone 5B: Aerobic Capacity    (24)
    Zone 5C: Anaerobic Capacity  (16)

There is no duplicate label: ``Aerobic`` (Z2) and ``Aerobic Capacity`` (Z5B)
are different strings and no measured label is genuinely ambiguous. An earlier
measurement truncated each label at the first space (rendering ``Zone 5B:
Aerobic Capacity`` as ``Zone 5B: Aerobic``), which invented a false collision
with Z2 and seeded wrong descriptors into this module; mapping now uses the
full label text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class TrainingSystem(StrEnum):
    """The two closed training-zone systems, each anchored on its own threshold."""

    POWER = "power"
    HEART_RATE = "heart_rate"


class ZoneCode(StrEnum):
    """Union of both systems' zone vocabularies.

    ``Z1``-``Z4`` exist in BOTH systems with different bounds; ``Z5``/``Z6``/
    ``Z7`` are power-only (Coggan); ``Z5A``/``Z5B``/``Z5C`` are heart-rate-only
    (Friel sub-zones). A code alone is never enough: pair it with a
    :class:`TrainingSystem`.
    """

    Z1 = "Z1"
    Z2 = "Z2"
    Z3 = "Z3"
    Z4 = "Z4"
    Z5 = "Z5"
    Z6 = "Z6"
    Z7 = "Z7"
    Z5A = "Z5A"
    Z5B = "Z5B"
    Z5C = "Z5C"


class ZoneError(ValueError):
    """Base class for zone vocabulary errors."""


class UnknownZoneCodeError(ZoneError):
    """Raised when a zone label carries no code token known to the given system."""


class AmbiguousZoneLabelError(ZoneError):
    """Raised when a bare descriptor maps to more than one zone code.

    Defensive: every measured corpus descriptor is unambiguous today, and each
    system's table has unique descriptors, so nothing currently raises this;
    it remains the contract for future labels.
    """


class ZoneLabelMismatchError(ZoneError):
    """Raised when a code/descriptor pair is not one of the observed pairs."""


class MissingThresholdError(ZoneError):
    """Raised when a declared system's threshold is absent, or the systems of a
    zone reference and an athlete disagree.

    Deliberately NOT a conversion error: the two systems are not
    interchangeable and no conversion exists, so a system mismatch is reported
    as a missing-compatible-threshold condition instead of being translated.
    """


class ZonesForUnknownSystemError(ZoneError):
    """Raised when a value is not a known :class:`TrainingSystem`."""


@dataclass(frozen=True, slots=True)
class ZoneRef:
    """A zone identified by system AND code, never by a code alone."""

    system: TrainingSystem
    code: ZoneCode


@dataclass(frozen=True, slots=True)
class ZoneSpec:
    """One zone of one training system with its KB-quoted threshold bounds.

    ``pct_lower``/``pct_upper`` are percentages of the system's threshold
    metric (:attr:`threshold_metric`); ``None`` marks an open end that the
    source document does not bound.
    """

    system: TrainingSystem
    code: ZoneCode
    descriptor: str
    pct_lower: float | None
    pct_upper: float | None

    @property
    def threshold_metric(self) -> str:
        """The threshold metric the percentages are expressed against."""
        if self.system is TrainingSystem.POWER:
            return "pct_ftp"
        return "pct_lthr"

    @property
    def ref(self) -> ZoneRef:
        return ZoneRef(self.system, self.code)


# %FTP bounds quoted from knowledge-base/training/zonas-entrenamiento-potencia.md
# ("Las 7 zonas Coggan: rangos y objetivos fisiológicos"): Z1 "menos del 55% FTP"
# (no lower bound), Z2 56-75, Z3 76-90, Z4 91-105, Z5 106-120, Z6 121-150,
# Z7 "más del 150% FTP" (no upper bound). Descriptors are the document's own
# zone names.
POWER_ZONES: dict[ZoneCode, ZoneSpec] = {
    ZoneCode.Z1: ZoneSpec(TrainingSystem.POWER, ZoneCode.Z1, "Recuperación activa", None, 55.0),
    ZoneCode.Z2: ZoneSpec(TrainingSystem.POWER, ZoneCode.Z2, "Resistencia aeróbica", 56.0, 75.0),
    ZoneCode.Z3: ZoneSpec(
        TrainingSystem.POWER, ZoneCode.Z3, "Tempo o resistencia muscular", 76.0, 90.0
    ),
    ZoneCode.Z4: ZoneSpec(
        TrainingSystem.POWER, ZoneCode.Z4, "Umbral lactato / sweet spot superior", 91.0, 105.0
    ),
    ZoneCode.Z5: ZoneSpec(TrainingSystem.POWER, ZoneCode.Z5, "VO2max", 106.0, 120.0),
    ZoneCode.Z6: ZoneSpec(TrainingSystem.POWER, ZoneCode.Z6, "Capacidad anaeróbica", 121.0, 150.0),
    ZoneCode.Z7: ZoneSpec(TrainingSystem.POWER, ZoneCode.Z7, "Potencia neuromuscular", 150.0, None),
}

# %LTHR bounds quoted from knowledge-base/training/zonas-entrenamiento-pulso.md
# ("Las siete bandas de pulso (modelo de Friel)"): Z1 "menos de 81%" (no lower
# bound), Z2 81-89, Z3 90-93, Z4 94-99, Z5a 100-102, Z5b 103-106,
# Z5c "más de 106%" (no upper bound). Descriptors are the corpus-observed
# English names the pulse document lists for this project's corpus.
HEART_RATE_ZONES: dict[ZoneCode, ZoneSpec] = {
    ZoneCode.Z1: ZoneSpec(TrainingSystem.HEART_RATE, ZoneCode.Z1, "Recovery", None, 81.0),
    ZoneCode.Z2: ZoneSpec(TrainingSystem.HEART_RATE, ZoneCode.Z2, "Aerobic", 81.0, 89.0),
    ZoneCode.Z3: ZoneSpec(TrainingSystem.HEART_RATE, ZoneCode.Z3, "Tempo", 90.0, 93.0),
    ZoneCode.Z4: ZoneSpec(TrainingSystem.HEART_RATE, ZoneCode.Z4, "SubThreshold", 94.0, 99.0),
    ZoneCode.Z5A: ZoneSpec(TrainingSystem.HEART_RATE, ZoneCode.Z5A, "SuperThreshold", 100.0, 102.0),
    ZoneCode.Z5B: ZoneSpec(
        TrainingSystem.HEART_RATE, ZoneCode.Z5B, "Aerobic Capacity", 103.0, 106.0
    ),
    ZoneCode.Z5C: ZoneSpec(
        TrainingSystem.HEART_RATE, ZoneCode.Z5C, "Anaerobic Capacity", 106.0, None
    ),
}

_SYSTEM_TABLES: dict[TrainingSystem, dict[ZoneCode, ZoneSpec]] = {
    TrainingSystem.POWER: POWER_ZONES,
    TrainingSystem.HEART_RATE: HEART_RATE_ZONES,
}

#: Every zone of both systems, keyed by (system, code). A bare code is NOT a
#: key: ``Z2`` exists in both systems with different bounds.
ZONES: dict[tuple[TrainingSystem, ZoneCode], ZoneSpec] = {
    (system, code): spec
    for system, table in _SYSTEM_TABLES.items()
    for code, spec in table.items()
}

_ZONE_LABEL_RE = re.compile(r"^Zone\s*([0-9][A-C]?)\s*:\s*(.+)$", re.IGNORECASE)


def zones_for(system: TrainingSystem | str) -> dict[ZoneCode, ZoneSpec]:
    """Return the zone table of one training system.

    Raises :class:`ZonesForUnknownSystemError` for anything that is not a
    known :class:`TrainingSystem`.
    """
    try:
        key = TrainingSystem(system)
    except ValueError:
        raise ZonesForUnknownSystemError(f"Unknown training system: {system!r}") from None
    return _SYSTEM_TABLES[key]


def zone_from_label(
    label: str, *, system: TrainingSystem | str = TrainingSystem.HEART_RATE
) -> ZoneRef:
    """Map a zone label onto the vocabulary of one training system.

    Accepts the labelled form ``Zone 1: Recovery`` (keyed on the CODE TOKEN,
    with the descriptor validated against the system's own table) and the bare
    descriptor form. The default system is HEART_RATE because every measured
    corpus label is heart rate and the cycling corpus is the only labelled
    corpus in the repository; callers handling another system must pass it
    explicitly. A code/descriptor pair that is not one of the system's pairs
    is rejected. A code that does not exist in the given system (power-only
    ``Z6`` for heart rate, heart-rate-only ``Z5A`` for power) raises
    :class:`UnknownZoneCodeError`; nothing is guessed.

    :class:`AmbiguousZoneLabelError` stays defined for defensive use; no
    measured corpus label raises it today.
    """
    try:
        key = TrainingSystem(system)
    except ValueError:
        raise ZonesForUnknownSystemError(f"Unknown training system: {system!r}") from None
    table = zones_for(key)
    tokens = {code.value[1:]: code for code in table}
    descriptors = {spec.descriptor.casefold(): spec.code for spec in table.values()}

    text = " ".join(label.split())
    if not text:
        raise UnknownZoneCodeError("Zone label is empty")

    match = _ZONE_LABEL_RE.match(text)
    if match is not None:
        token = match.group(1).upper()
        zone = tokens.get(token)
        if zone is None:
            raise UnknownZoneCodeError(
                f"Unknown {key.value} zone code token: {token!r} in {label!r}"
            )
        descriptor = " ".join(match.group(2).split()).casefold()
        if descriptors.get(descriptor) is not zone:
            raise ZoneLabelMismatchError(
                f"{key.value} label {label!r}: code {token!r} is not paired "
                f"with descriptor {descriptor!r}"
            )
        return ZoneRef(key, zone)

    zone = descriptors.get(text.casefold())
    if zone is None:
        raise UnknownZoneCodeError(f"Unknown {key.value} zone label: {label!r}")
    return ZoneRef(key, zone)


@dataclass(frozen=True, slots=True)
class AthleteThresholds:
    """The threshold an athlete declared for ONE training system.

    The threshold of the declared system is REQUIRED and must be positive:
    a power athlete without FTP and a heart-rate athlete without LTHR are both
    refused at construction, because prescribing in a system without its
    anchor would be fabrication.
    """

    system: TrainingSystem
    ftp_watts: float | None = None
    lthr_bpm: float | None = None

    def __post_init__(self) -> None:
        if self.system is TrainingSystem.POWER:
            if self.ftp_watts is None or self.ftp_watts <= 0:
                raise MissingThresholdError(
                    "a power athlete requires a positive FTP in watts"
                )
        elif self.system is TrainingSystem.HEART_RATE:
            if self.lthr_bpm is None or self.lthr_bpm <= 0:
                raise MissingThresholdError(
                    "a heart-rate athlete requires a positive LTHR in bpm"
                )
        else:
            raise ZonesForUnknownSystemError(f"Unknown training system: {self.system!r}")


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """An absolute target range derived from the athlete's own threshold.

    ``lower``/``upper`` are absolute values in ``unit``; ``None`` marks an
    open end that the source zone leaves unbounded (:meth:`describe` states
    open ends rather than guessing them).
    """

    system: TrainingSystem
    code: ZoneCode
    lower: float | None
    upper: float | None
    unit: str

    def describe(self) -> str:
        if self.lower is None or self.upper is None:
            if self.lower is None and self.upper is None:
                return f"{self.code.value}: unbounded (no bound defined by the source document)"
            if self.lower is None:
                return f"{self.code.value}: below {self.upper:g} {self.unit}"
            return f"{self.code.value}: above {self.lower:g} {self.unit}"
        return f"{self.code.value}: {self.lower:g}-{self.upper:g} {self.unit}"


def resolve_target(ref: ZoneRef, thresholds: AthleteThresholds) -> ResolvedTarget:
    """Derive an absolute range from the athlete's own threshold only.

    The reference's system must match the athlete's declared system: the two
    training systems are not interchangeable and NO conversion exists between
    them (the relationship is individual and drifts with fitness, fatigue,
    heat and duration), so a mismatch raises :class:`MissingThresholdError`
    instead of being translated.
    """
    if ref.system is not thresholds.system:
        raise MissingThresholdError(
            f"zone {ref.code.value} belongs to the {ref.system.value} system but the "
            f"athlete declared the {thresholds.system.value} system: the two systems "
            f"are not interchangeable and no conversion exists between them"
        )
    spec = ZONES.get((ref.system, ref.code))
    if spec is None:
        raise UnknownZoneCodeError(
            f"Zone {ref.code.value} does not exist in the {ref.system.value} system"
        )
    if ref.system is TrainingSystem.POWER:
        value, unit = thresholds.ftp_watts, "watts"
    else:
        value, unit = thresholds.lthr_bpm, "bpm"
    if value is None or value <= 0:
        raise MissingThresholdError(
            f"a {ref.system.value} athlete requires a positive "
            f"{'FTP in watts' if ref.system is TrainingSystem.POWER else 'LTHR in bpm'}"
        )
    lower = None if spec.pct_lower is None else spec.pct_lower / 100 * value
    upper = None if spec.pct_upper is None else spec.pct_upper / 100 * value
    return ResolvedTarget(ref.system, ref.code, lower, upper, unit)
