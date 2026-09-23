"""Tests for the two training-zone systems and their label mapping (T9).

The two systems (power/%FTP and heart-rate/%LTHR) are separate vocabularies
that share overlapping code names: a bare ``Z2`` means a power band in one and
a heart-rate band in the other. A zone is always identified by a
``ZoneRef(system, code)``; every test here guards that separation.
"""

import pytest

from cycloai.domain.zones import (
    HEART_RATE_ZONES,
    POWER_ZONES,
    ZONES,
    AmbiguousZoneLabelError,
    AthleteThresholds,
    MissingThresholdError,
    TrainingSystem,
    UnknownZoneCodeError,
    ZoneCode,
    ZoneError,
    ZoneLabelMismatchError,
    ZoneRef,
    ZonesForUnknownSystemError,
    resolve_target,
    zone_from_label,
    zones_for,
)

POWER = TrainingSystem.POWER
HEART_RATE = TrainingSystem.HEART_RATE

# Bounds quoted from the two knowledge-base documents.
EXPECTED_POWER_BOUNDS = {
    ZoneCode.Z1: (None, 55.0),
    ZoneCode.Z2: (56.0, 75.0),
    ZoneCode.Z3: (76.0, 90.0),
    ZoneCode.Z4: (91.0, 105.0),
    ZoneCode.Z5: (106.0, 120.0),
    ZoneCode.Z6: (121.0, 150.0),
    ZoneCode.Z7: (150.0, None),
}
EXPECTED_HEART_RATE_BOUNDS = {
    ZoneCode.Z1: (None, 81.0),
    ZoneCode.Z2: (81.0, 89.0),
    ZoneCode.Z3: (90.0, 93.0),
    ZoneCode.Z4: (94.0, 99.0),
    ZoneCode.Z5A: (100.0, 102.0),
    ZoneCode.Z5B: (103.0, 106.0),
    ZoneCode.Z5C: (106.0, None),
}


# --- The two closed tables -----------------------------------------------------


def test_each_system_table_has_exactly_seven_entries() -> None:
    assert len(POWER_ZONES) == 7
    assert len(HEART_RATE_ZONES) == 7
    assert set(POWER_ZONES) == {ZoneCode.Z1, ZoneCode.Z2, ZoneCode.Z3, ZoneCode.Z4,
                                ZoneCode.Z5, ZoneCode.Z6, ZoneCode.Z7}
    assert set(HEART_RATE_ZONES) == {ZoneCode.Z1, ZoneCode.Z2, ZoneCode.Z3, ZoneCode.Z4,
                                     ZoneCode.Z5A, ZoneCode.Z5B, ZoneCode.Z5C}


def test_union_vocabulary_is_the_closed_ten_code_set() -> None:
    assert [code.value for code in ZoneCode] == [
        "Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7", "Z5A", "Z5B", "Z5C",
    ]


@pytest.mark.parametrize(
    ("system", "expected_bounds"),
    [
        (POWER, EXPECTED_POWER_BOUNDS),
        (HEART_RATE, EXPECTED_HEART_RATE_BOUNDS),
    ],
)
def test_every_zone_exists_with_the_exact_quoted_bounds(
    system: TrainingSystem, expected_bounds: dict
) -> None:
    for code, (lower, upper) in expected_bounds.items():
        spec = zones_for(system)[code]
        assert spec.system is system
        assert spec.code is code
        assert spec.pct_lower == lower, f"{system.value} {code.value} lower bound"
        assert spec.pct_upper == upper, f"{system.value} {code.value} upper bound"
        assert ZONES[(system, code)] is spec


def test_threshold_metric_is_pct_ftp_for_power_and_pct_lthr_for_heart_rate() -> None:
    assert all(spec.threshold_metric == "pct_ftp" for spec in POWER_ZONES.values())
    assert all(spec.threshold_metric == "pct_lthr" for spec in HEART_RATE_ZONES.values())
    assert all(spec.ref == ZoneRef(spec.system, spec.code) for spec in ZONES.values())


def test_zones_for_returns_one_table_per_system_and_rejects_unknown_systems() -> None:
    assert zones_for("power") is POWER_ZONES
    assert zones_for("heart_rate") is HEART_RATE_ZONES
    with pytest.raises(ZonesForUnknownSystemError):
        zones_for("swim")


def test_shared_codes_have_DIFFERENT_bounds_in_the_two_systems() -> None:
    """The conflation can never return: Z1-Z4 exist in both systems and every
    one of them carries different bounds per system."""
    for code in (ZoneCode.Z1, ZoneCode.Z2, ZoneCode.Z3, ZoneCode.Z4):
        power = POWER_ZONES[code]
        heart = HEART_RATE_ZONES[code]
        assert (power.pct_lower, power.pct_upper) != (heart.pct_lower, heart.pct_upper), code


# --- Label mapping is keyed on the code token, per system ----------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Zone 1: Recovery", ZoneCode.Z1),
        ("Zone 2: Aerobic", ZoneCode.Z2),
        ("Zone 3: Tempo", ZoneCode.Z3),
        ("Zone 4: SubThreshold", ZoneCode.Z4),
        ("Zone 5A: SuperThreshold", ZoneCode.Z5A),
        ("Zone 5B: Aerobic Capacity", ZoneCode.Z5B),
        ("Zone 5C: Anaerobic Capacity", ZoneCode.Z5C),
    ],
)
def test_corpus_labels_default_to_the_heart_rate_system(label: str, expected: ZoneCode) -> None:
    ref = zone_from_label(label)
    assert ref.system is HEART_RATE
    assert ref.code is expected


def test_mapping_is_whitespace_and_case_tolerant() -> None:
    assert zone_from_label("  zone 5b:   Aerobic Capacity  ") == ZoneRef(HEART_RATE, ZoneCode.Z5B)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Zone 1: Recuperación activa", ZoneCode.Z1),
        ("Zone 2: Resistencia aeróbica", ZoneCode.Z2),
        ("Zone 5: VO2max", ZoneCode.Z5),
        ("Zone 7: Potencia neuromuscular", ZoneCode.Z7),
        ("Recuperación activa", ZoneCode.Z1),
        ("VO2max", ZoneCode.Z5),
    ],
)
def test_power_labels_resolve_in_the_power_system(label: str, expected: ZoneCode) -> None:
    assert zone_from_label(label, system=POWER) == ZoneRef(POWER, expected)


def test_power_only_code_is_rejected_for_the_heart_rate_system() -> None:
    with pytest.raises(UnknownZoneCodeError):
        zone_from_label("Zone 6: Capacidad anaeróbica", system=HEART_RATE)


def test_heart_rate_only_code_is_rejected_for_the_power_system() -> None:
    with pytest.raises(UnknownZoneCodeError):
        zone_from_label("Zone 5A: SuperThreshold", system=POWER)


def test_descriptors_are_distinct_strings_not_a_collision() -> None:
    """`Aerobic` (Z2) and `Aerobic Capacity` (Z5B) are different measured strings;
    the earlier `Zone 5B: Aerobic` reading was a first-space truncation artifact."""
    assert zone_from_label("Zone 2: Aerobic") == ZoneRef(HEART_RATE, ZoneCode.Z2)
    assert zone_from_label("Zone 5B: Aerobic Capacity") == ZoneRef(HEART_RATE, ZoneCode.Z5B)


@pytest.mark.parametrize(
    "label", ["Zone 3: Recovery", "Zone 1: Aerobic", "Zone 5A: Anaerobic", "Zone 2: Capacity"]
)
def test_mismatched_code_descriptor_pair_is_rejected(label: str) -> None:
    with pytest.raises(ZoneLabelMismatchError):
        zone_from_label(label)


def test_power_system_rejects_a_descriptor_from_the_heart_rate_table() -> None:
    """A non-default system validates against its OWN descriptors, not the corpus's."""
    with pytest.raises(ZoneLabelMismatchError):
        zone_from_label("Zone 2: Aerobic", system=POWER)


@pytest.mark.parametrize("label", ["Zone 5D: SuperThreshold", "Zone 9: Recovery", "Zone 12: Tempo"])
def test_unknown_code_token_raises(label: str) -> None:
    with pytest.raises(UnknownZoneCodeError):
        zone_from_label(label)


@pytest.mark.parametrize(
    "label", ["Sweetspot", "", "   ", "A TOPE", "NO TIENES QUE LLEGAR A ESTE PULSO"]
)
def test_unknown_label_raises_dedicated_exception(label: str) -> None:
    with pytest.raises(ZoneError):
        zone_from_label(label)


def test_ambiguous_zone_label_error_is_kept_defensively() -> None:
    """No measured label is ambiguous today, so nothing raises this; it stays as
    the defensive contract for future descriptors."""
    assert issubclass(AmbiguousZoneLabelError, ZoneError)


# --- AthleteThresholds require the declared system's threshold -----------------


def test_power_athlete_requires_ftp() -> None:
    with pytest.raises(MissingThresholdError):
        AthleteThresholds(system=POWER)


def test_heart_rate_athlete_requires_lthr() -> None:
    with pytest.raises(MissingThresholdError):
        AthleteThresholds(system=HEART_RATE)


def test_non_positive_thresholds_are_refused() -> None:
    with pytest.raises(MissingThresholdError):
        AthleteThresholds(system=POWER, ftp_watts=0)
    with pytest.raises(MissingThresholdError):
        AthleteThresholds(system=HEART_RATE, lthr_bpm=-140)


def test_declared_thresholds_are_accepted() -> None:
    power = AthleteThresholds(system=POWER, ftp_watts=250.0)
    heart = AthleteThresholds(system=HEART_RATE, lthr_bpm=170.0)
    assert power.ftp_watts == 250.0
    assert heart.lthr_bpm == 170.0


# --- resolve_target derives from the athlete's own threshold only --------------


def test_heart_rate_zone_with_heart_rate_athlete_yields_bpm_bands() -> None:
    ref = zone_from_label("Zone 2: Aerobic")  # heart-rate Z2: 81-89 %LTHR
    target = resolve_target(ref, AthleteThresholds(system=HEART_RATE, lthr_bpm=170.0))
    assert target.system is HEART_RATE
    assert target.code is ZoneCode.Z2
    assert target.unit == "bpm"
    assert target.lower == pytest.approx(137.7)
    assert target.upper == pytest.approx(151.3)


def test_power_zone_with_power_athlete_yields_watts_bands() -> None:
    ref = zone_from_label("Zone 2: Resistencia aeróbica", system=POWER)  # 56-75 %FTP
    target = resolve_target(ref, AthleteThresholds(system=POWER, ftp_watts=200.0))
    assert target.system is POWER
    assert target.code is ZoneCode.Z2
    assert target.unit == "watts"
    assert target.lower == pytest.approx(112.0)
    assert target.upper == pytest.approx(150.0)


@pytest.mark.parametrize(
    ("ref", "thresholds"),
    [
        # heart-rate zone, power athlete
        (
            ZoneRef(HEART_RATE, ZoneCode.Z2),
            AthleteThresholds(system=POWER, ftp_watts=250.0),
        ),
        # power zone, heart-rate athlete
        (
            ZoneRef(POWER, ZoneCode.Z2),
            AthleteThresholds(system=HEART_RATE, lthr_bpm=170.0),
        ),
    ],
)
def test_system_mismatch_raises_and_names_the_missing_conversion(
    ref: ZoneRef, thresholds: AthleteThresholds
) -> None:
    with pytest.raises(MissingThresholdError, match="no conversion exists"):
        resolve_target(ref, thresholds)


def test_resolve_target_requires_matching_systems_which_makes_conversion_impossible() -> None:
    """There is deliberately NO conversion helper anywhere: the only way to get
    an absolute range out of a zone reference is through an athlete whose
    declared system matches the reference's system. That property is what makes
    a heart-rate-to-power conversion impossible in this module."""
    import cycloai.domain.zones as zones_module

    public_names = [name for name in dir(zones_module) if not name.startswith("_")]
    assert not any("convert" in name.lower() for name in public_names)
    with pytest.raises(MissingThresholdError):
        resolve_target(ZoneRef(HEART_RATE, ZoneCode.Z3), AthleteThresholds(system=POWER))


def test_resolve_target_rejects_a_pair_absent_from_the_tables() -> None:
    with pytest.raises(UnknownZoneCodeError):
        resolve_target(
            ZoneRef(HEART_RATE, ZoneCode.Z6),
            AthleteThresholds(system=HEART_RATE, lthr_bpm=170.0),
        )


# --- Open-ended bands describe themselves without inventing a bound ------------


def test_open_low_end_describes_itself_as_below() -> None:
    # Power Z1 and heart-rate Z1 have no lower bound ("menos del 55% FTP").
    target = resolve_target(
        ZoneRef(POWER, ZoneCode.Z1), AthleteThresholds(system=POWER, ftp_watts=200.0)
    )
    assert target.lower is None
    assert target.upper == pytest.approx(110.0)
    assert "below 110 watts" in target.describe()


def test_open_high_end_describes_itself_as_above() -> None:
    # Power Z7 ("más del 150% FTP") and heart-rate Z5C ("más de 106%") have no
    # upper bound.
    z7 = resolve_target(
        ZoneRef(POWER, ZoneCode.Z7), AthleteThresholds(system=POWER, ftp_watts=200.0)
    )
    assert z7.upper is None
    assert z7.lower == pytest.approx(300.0)
    assert "above 300 watts" in z7.describe()

    z5c = resolve_target(
        ZoneRef(HEART_RATE, ZoneCode.Z5C), AthleteThresholds(system=HEART_RATE, lthr_bpm=170.0)
    )
    assert z5c.upper is None
    assert "above 180.2 bpm" in z5c.describe()


def test_closed_band_describes_its_range() -> None:
    target = resolve_target(
        ZoneRef(HEART_RATE, ZoneCode.Z4), AthleteThresholds(system=HEART_RATE, lthr_bpm=170.0)
    )
    assert target.describe() == "Z4: 159.8-168.3 bpm"
