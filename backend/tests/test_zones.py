"""Tests for the closed corpus zone model and label mapping (T3)."""

import pytest

from cycloai.domain.zones import (
    ZONES,
    AmbiguousZoneLabelError,
    UnknownZoneCodeError,
    ZoneCode,
    ZoneError,
    ZoneLabelMismatchError,
    zone_from_label,
)

CORPUS_CODES = ["Z1", "Z2", "Z3", "Z4", "Z5A", "Z5B", "Z5C"]

# (%FTP lower, %FTP upper) taken from knowledge-base/training/zonas-entrenamiento-potencia.md.
# Z5A/Z5B/Z5C are corpus sub-zones the KB document does not define bounds for.
EXPECTED_PCT_FTP_BOUNDS = {
    ZoneCode.Z1: (None, 55.0),
    ZoneCode.Z2: (56.0, 75.0),
    ZoneCode.Z3: (76.0, 90.0),
    ZoneCode.Z4: (91.0, 105.0),
    ZoneCode.Z5A: (None, None),
    ZoneCode.Z5B: (None, None),
    ZoneCode.Z5C: (None, None),
}


def test_zone_vocabulary_is_the_closed_corpus_set() -> None:
    assert set(ZONES) == set(ZoneCode)
    assert [code.value for code in ZoneCode] == CORPUS_CODES


@pytest.mark.parametrize("code", CORPUS_CODES)
def test_pct_ftp_bounds_match_the_knowledge_base_or_are_absent(code: str) -> None:
    spec = ZONES[ZoneCode(code)]
    expected_lower, expected_upper = EXPECTED_PCT_FTP_BOUNDS[ZoneCode(code)]
    assert spec.pct_ftp_lower == expected_lower
    assert spec.pct_ftp_upper == expected_upper


def test_corpus_sub_zones_have_no_invented_bounds() -> None:
    """The KB document does not define Z5A/Z5B/Z5C; bounds must stay absent, not guessed."""
    for code in (ZoneCode.Z5A, ZoneCode.Z5B, ZoneCode.Z5C):
        assert ZONES[code].pct_ftp_lower is None
        assert ZONES[code].pct_ftp_upper is None


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
def test_mapping_is_keyed_on_the_code_token(label: str, expected: ZoneCode) -> None:
    assert zone_from_label(label) is expected


def test_descriptors_are_distinct_strings_not_a_collision() -> None:
    """`Aerobic` (Z2) and `Aerobic Capacity` (Z5B) are different measured strings;
    the earlier `Zone 5B: Aerobic` reading was a first-space truncation artifact."""
    assert zone_from_label("Zone 2: Aerobic") is ZoneCode.Z2
    assert zone_from_label("Zone 5B: Aerobic Capacity") is ZoneCode.Z5B
    assert ZoneCode.Z2 is not ZoneCode.Z5B


def test_mapping_is_whitespace_and_case_tolerant() -> None:
    assert zone_from_label("  zone 5b:   Aerobic Capacity  ") is ZoneCode.Z5B


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Recovery", ZoneCode.Z1),
        ("Aerobic", ZoneCode.Z2),
        ("Tempo", ZoneCode.Z3),
        ("SubThreshold", ZoneCode.Z4),
        ("SuperThreshold", ZoneCode.Z5A),
        ("Aerobic Capacity", ZoneCode.Z5B),
        ("Anaerobic Capacity", ZoneCode.Z5C),
    ],
)
def test_bare_descriptor_resolves_to_its_code(label: str, expected: ZoneCode) -> None:
    assert zone_from_label(label) is expected


def test_ambiguous_zone_label_error_is_kept_defensively() -> None:
    """No measured label is ambiguous today, so nothing raises this; it stays as
    the defensive contract for future descriptors."""
    assert issubclass(AmbiguousZoneLabelError, ZoneError)


@pytest.mark.parametrize(
    "label",
    ["Zone 3: Recovery", "Zone 1: Aerobic", "Zone 5A: Anaerobic", "Zone 2: Capacity"],
)
def test_mismatched_code_descriptor_pair_is_rejected(label: str) -> None:
    with pytest.raises(ZoneLabelMismatchError):
        zone_from_label(label)


@pytest.mark.parametrize("label", ["Zone 5D: SuperThreshold", "Zone 9: Recovery", "Zone 12: Tempo"])
def test_unknown_code_token_raises(label: str) -> None:
    with pytest.raises(UnknownZoneCodeError):
        zone_from_label(label)


@pytest.mark.parametrize(
    "label",
    ["Sweetspot", "", "   ", "A TOPE", "NO TIENES QUE LLEGAR A ESTE PULSO"],
)
def test_unknown_label_raises_dedicated_exception(label: str) -> None:
    with pytest.raises(ZoneError):
        zone_from_label(label)
