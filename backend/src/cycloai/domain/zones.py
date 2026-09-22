"""Closed training-zone vocabulary and corpus label mapping.

The zone codes are the closed set observed in the cycling corpus
(``docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt``): Z1, Z2, Z3, Z4, Z5A, Z5B, Z5C.
It is a subset refinement of the Coggan model documented in
``knowledge-base/training/zonas-entrenamiento-potencia.md``, whose %FTP bounds are:

    Zona 1 - Recuperación activa: menos del 55% FTP.
    Zona 2 - Resistencia aeróbica: 56-75% FTP.
    Zona 3 - Tempo o resistencia muscular: 76-90% FTP.
    Zona 4 - Umbral lactato / sweet spot superior: 91-105% FTP.
    Zona 5 - VO2max: 106-120% FTP.

The KB document does NOT define Z5A/Z5B/Z5C sub-zone bounds; they are deliberately
left absent instead of being guessed (feature doc invariant I2 and decision D7).

The corpus label text is NOT unique: ``Zone 2: Aerobic`` and ``Zone 5B: Aerobic``
share the descriptor ``Aerobic``. Mapping is therefore keyed on the parsed zone
code token and the descriptor is only validated against it, never used as a key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ZoneCode(StrEnum):
    """Closed corpus zone vocabulary (subset refinement of the Coggan Z1-Z7 model)."""

    Z1 = "Z1"
    Z2 = "Z2"
    Z3 = "Z3"
    Z4 = "Z4"
    Z5A = "Z5A"
    Z5B = "Z5B"
    Z5C = "Z5C"


class ZoneError(ValueError):
    """Base class for zone vocabulary errors."""


class UnknownZoneCodeError(ZoneError):
    """Raised when a corpus zone label carries no known zone code token."""


class AmbiguousZoneLabelError(ZoneError):
    """Raised when a bare descriptor maps to more than one zone code."""


class ZoneLabelMismatchError(ZoneError):
    """Raised when a code/descriptor pair is not one of the corpus-observed pairs."""


@dataclass(frozen=True, slots=True)
class ZoneSpec:
    """A zone of the closed corpus vocabulary with its KB-derived %FTP bounds."""

    code: ZoneCode
    descriptor: str
    pct_ftp_lower: float | None
    pct_ftp_upper: float | None


# %FTP bounds quoted from knowledge-base/training/zonas-entrenamiento-potencia.md
# ("Las 7 zonas Coggan: rangos y objetivos fisiológicos"). Z1 has no lower bound
# ("menos del 55% FTP"); Z5A/Z5B/Z5C are not defined by the KB document, so their
# bounds stay absent rather than invented.
ZONES: dict[ZoneCode, ZoneSpec] = {
    ZoneCode.Z1: ZoneSpec(ZoneCode.Z1, "Recovery", None, 55.0),
    ZoneCode.Z2: ZoneSpec(ZoneCode.Z2, "Aerobic", 56.0, 75.0),
    ZoneCode.Z3: ZoneSpec(ZoneCode.Z3, "Tempo", 76.0, 90.0),
    ZoneCode.Z4: ZoneSpec(ZoneCode.Z4, "SubThreshold", 91.0, 105.0),
    ZoneCode.Z5A: ZoneSpec(ZoneCode.Z5A, "SuperThreshold", None, None),
    ZoneCode.Z5B: ZoneSpec(ZoneCode.Z5B, "Aerobic", None, None),
    ZoneCode.Z5C: ZoneSpec(ZoneCode.Z5C, "Anaerobic", None, None),
}

# Corpus-observed code/descriptor pairs. The descriptor is a display label only.
_KNOWN_PAIRS: dict[str, ZoneCode] = {
    "1:recovery": ZoneCode.Z1,
    "2:aerobic": ZoneCode.Z2,
    "3:tempo": ZoneCode.Z3,
    "4:subthreshold": ZoneCode.Z4,
    "5a:superthreshold": ZoneCode.Z5A,
    "5b:aerobic": ZoneCode.Z5B,
    "5c:anaerobic": ZoneCode.Z5C,
}

_CODE_TOKENS: dict[str, ZoneCode] = {
    "1": ZoneCode.Z1,
    "2": ZoneCode.Z2,
    "3": ZoneCode.Z3,
    "4": ZoneCode.Z4,
    "5A": ZoneCode.Z5A,
    "5B": ZoneCode.Z5B,
    "5C": ZoneCode.Z5C,
}

# Bare-descriptor form: only unambiguous descriptors can be resolved without a code.
_UNAMBIGUOUS_DESCRIPTORS: dict[str, ZoneCode] = {
    "recovery": ZoneCode.Z1,
    "tempo": ZoneCode.Z3,
    "subthreshold": ZoneCode.Z4,
    "superthreshold": ZoneCode.Z5A,
    "anaerobic": ZoneCode.Z5C,
}

_ZONE_LABEL_RE = re.compile(r"^Zone\s*([0-9][A-C]?)\s*:\s*(.+)$", re.IGNORECASE)


def zone_from_label(label: str) -> ZoneCode:
    """Map a corpus zone label onto the closed zone vocabulary.

    Accepts the corpus form ``Zone 1: Recovery`` (keyed on the code token ``1``) and
    the bare unambiguous descriptor ``Recovery``. A bare descriptor shared by several
    codes (``Aerobic``: Z2 and Z5B) is ambiguous and rejected. Unmapped or unknown
    labels raise a dedicated :class:`ZoneError` subclass; nothing is guessed.
    """
    text = " ".join(label.split())
    if not text:
        raise UnknownZoneCodeError("Zone label is empty")

    match = _ZONE_LABEL_RE.match(text)
    if match is not None:
        token = match.group(1).upper()
        zone = _CODE_TOKENS.get(token)
        if zone is None:
            raise UnknownZoneCodeError(f"Unknown corpus zone code token: {token!r} in {label!r}")
        descriptor = " ".join(match.group(2).split()).casefold()
        known = _KNOWN_PAIRS.get(f"{token.casefold()}:{descriptor}")
        if known is not zone:
            raise ZoneLabelMismatchError(
                f"Corpus label {label!r}: code {token!r} is not paired "
                f"with descriptor {descriptor!r}"
            )
        return zone

    zone = _UNAMBIGUOUS_DESCRIPTORS.get(text.casefold())
    if zone is None:
        if text.casefold() in {"aerobic"}:
            raise AmbiguousZoneLabelError(
                f"Ambiguous bare zone label {label!r}: matches Z2 and Z5B; "
                "use the 'Zone N: ...' form"
            )
        raise UnknownZoneCodeError(f"Unknown corpus zone label: {label!r}")
    return zone
