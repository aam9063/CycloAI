"""Cryptographic core for CycloAI authentication.

This module owns two responsibilities and nothing else:

1. Password hashing with Argon2 (salted, constant-time verification).
2. Session token (JWT) issuance and verification.

Deliberately free of FastAPI/HTTP concerns: no request objects, no cookies,
no endpoints. Those belong to the next slice.

Error contract (important):

- ``verify_password`` NEVER raises on a wrong password or a corrupted stored
  hash; it returns ``False``. A corrupted stored hash must not become a 500.
- ``verify_token`` NEVER raises on any verification failure (expired,
  tampered, wrong signature, malformed, wrong algorithm); it returns
  ``None``. A token that cannot be verified is not an error condition, it is
  an unauthenticated request.
- Configuration problems (missing or too-short ``JWT_SECRET``) DO raise at
  startup: a silently forgeable session secret is worse than a loud failure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AuthConfigError(RuntimeError):
    """Raised when the auth configuration is missing or invalid.

    This is deliberately loud: there is NO insecure default secret, because a
    development default that works would silently reach production as a
    forgeable session. Failing at startup names the variable to set.
    """


class PasswordValidationError(ValueError):
    """Raised when a password cannot be hashed because it violates policy."""


# ---------------------------------------------------------------------------
# Settings (module-anchored .env path — do NOT use a relative env_file)
# ---------------------------------------------------------------------------

# The env file is resolved from THIS module's location, not from the process
# working directory, exactly like ``db/settings.py``. A relative ``.env``
# silently means ``backend/.env`` when you happen to run from ``backend/``
# and the repository-root ``.env`` when you run from the root, so the same
# command behaved differently depending on where it was launched and
# reported "not configured" for a variable that existed.
# backend/src/cycloai/auth/security.py -> parents[3] == backend/
_ENV_FILE: Final[Path] = Path(__file__).resolve().parents[3] / ".env"


def get_env_file() -> Path:
    """Return the resolved, absolute ``.env`` path used for auth settings."""
    return _ENV_FILE


class AuthSettings(BaseSettings):
    """Auth settings: environment first, then the module-anchored ``.env``.

    ``jwt_secret`` is Optional so that a MISSING secret surfaces as our own
    :class:`AuthConfigError` (which names the variable and how to fix it)
    instead of an opaque pydantic validation error.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str | None = None


# Minimum secret length: 32 bytes (256 bits). Rationale: tokens are signed
# with HMAC-SHA-256 (HS256), and RFC 7518 section 3.2 requires the key to be
# at least as long as the hash output (256 bits) for that algorithm. Anything
# shorter weakens the effective key space below the signature strength.
MIN_SECRET_LENGTH: Final[int] = 32


@lru_cache(maxsize=1)
def get_settings() -> AuthSettings:
    """Load auth settings once (tests may ``cache_clear`` between cases).

    Raises AuthConfigError when JWT_SECRET is absent or too short. There is
    deliberately no insecure default: a development fallback that works
    would silently reach production as a forgeable session.
    """
    settings = AuthSettings(_env_file=_ENV_FILE)  # type: ignore[call-arg]
    if not settings.jwt_secret:
        raise AuthConfigError(
            "JWT_SECRET is not set. Set the JWT_SECRET environment variable "
            f"or add JWT_SECRET=<random secret> to {_ENV_FILE}. There is "
            "deliberately no insecure default: a development fallback that "
            "works would silently reach production as a forgeable session."
        )
    if len(settings.jwt_secret) < MIN_SECRET_LENGTH:
        raise AuthConfigError(
            f"JWT_SECRET is too short: got {len(settings.jwt_secret)} "
            f"characters, minimum is {MIN_SECRET_LENGTH} (256 bits, matching "
            "the HS256 signature strength). Generate one with: "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`"
        )
    return settings


# ---------------------------------------------------------------------------
# Password hashing (Argon2)
# ---------------------------------------------------------------------------

# Passwords we are willing to hash. Argon2 pre-hashes long inputs, so there
# is no cryptographic length limit, but an unbounded password is a cheap
# denial-of-service vector, so we cap it.
MIN_PASSWORD_LENGTH: Final[int] = 1
MAX_PASSWORD_LENGTH: Final[int] = 1024

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id.

    Raises PasswordValidationError for an empty or absurdly long password.
    """
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise PasswordValidationError(
            f"Password length must be between {MIN_PASSWORD_LENGTH} and "
            f"{MAX_PASSWORD_LENGTH} characters; got {len(password)}."
        )
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify a password against a stored Argon2 hash.

    Constant-time comparison (provided by the Argon2 library). Never raises:
    a wrong password, a malformed hash, or a corrupted stored hash all return
    ``False`` — a bad stored value must not become a 500.
    """
    try:
        return _hasher.verify(stored_hash, password)
    except (InvalidHashError, VerificationError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Session tokens (JWT)
# ---------------------------------------------------------------------------

# The signing algorithm is PINNED here and passed explicitly to both encode
# and decode. ``jwt.decode(..., algorithms=["HS256"])`` means PyJWT rejects
# any token whose header claims a different algorithm (e.g. "none" or an RSA
# algorithm), which prevents algorithm-confusion attacks where an attacker
# crafts a header to make the verifier skip signature checking or interpret
# the symmetric secret as something else entirely.
ALGORITHM: Final[str] = "HS256"

# Token purpose claim. Present so that future refresh tokens (with
# token_type="refresh") cannot be replayed as access tokens: verification
# rejects a token whose purpose does not match what the caller expects.
ACCESS_TOKEN_TYPE: Final[str] = "access"

# Access-token lifetime. Short-lived on purpose; refresh tokens belong to a
# later slice and would use a different, longer lifetime.
ACCESS_TOKEN_TTL: Final[timedelta] = timedelta(hours=1)


def create_token(
    user_id: str | uuid.UUID, *, token_type: str = ACCESS_TOKEN_TYPE
) -> str:
    """Create a signed JWT for the given user identity.

    ``user_id`` may be a :class:`uuid.UUID` or its canonical string form; it
    is stored in the ``sub`` claim. Carries: ``sub`` (subject = user id),
    ``exp`` (expiry), ``iat`` (issued at) and ``typ`` (token purpose, so
    refresh tokens can never be used as access tokens).
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
        "typ": token_type,
    }
    return jwt.encode(
        payload, get_settings().jwt_secret, algorithm=ALGORITHM
    )


def verify_token(
    token: str, *, expected_type: str = ACCESS_TOKEN_TYPE
) -> uuid.UUID | None:
    """Verify a session token and return the user identity it carries.

    Returns a :class:`uuid.UUID` when the token is valid, otherwise ``None``.
    The identity is parsed from the ``sub`` claim here, at the boundary, so
    no caller can ever receive a bare string and silently compare it against
    a UUID (``UUID == str`` is ``False``, which would fail closed and deny a
    legitimate owner as "not found").

    IMPORTANT: a token that cannot be verified is not an error condition, it
    is an unauthenticated request. This function NEVER raises: an expired
    token, a tampered payload, a wrong signature, a malformed token, a token
    declaring a different algorithm, or a token whose ``sub`` subject is
    absent, empty, or not a valid UUID all return ``None``. An unparseable
    subject is rejected as unauthenticated rather than surfaced as an error:
    a subject that is not a valid identity is not a valid identity.

    The accepted algorithm is pinned (``algorithms=[ALGORITHM]``) rather than
    trusted from the token header, so a forged header cannot select another
    algorithm. A token whose ``typ`` purpose claim does not match
    ``expected_type`` is also rejected, so a future refresh token cannot be
    replayed as an access token.
    """
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        return None
    try:
        return uuid.UUID(sub)
    except (ValueError, AttributeError, TypeError):
        return None
