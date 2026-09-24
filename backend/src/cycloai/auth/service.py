"""User registration and authentication service for CycloAI.

This module owns the two database-backed auth operations the HTTP layer will
sit on top of: creating a user and verifying a login. Like
``cycloai.auth.security`` it is deliberately free of FastAPI/HTTP concerns —
no request objects, no cookies, no endpoints. Those belong to the next slice;
this module never imports FastAPI.

Outcomes (the typed contract the HTTP layer maps to responses):

- ``register_user`` returns a :class:`UserIdentity` on success and raises
  :class:`EmailAlreadyRegisteredError` when the email is already taken (the
  HTTP layer maps that to 409). Password-policy violations surface as
  ``auth.security.PasswordValidationError`` — a DIFFERENT exception from the
  duplicate-email one, so a 4xx "bad password" can never be confused with a
  409 "email taken". Policy errors are raised before any database write.
- ``authenticate_user`` returns a :class:`UserIdentity` on success and
  ``None`` on ANY failure. Read the docstring of ``authenticate_user`` for
  the anti-enumeration contract: a wrong password and an unknown email are
  indistinguishable BY DESIGN.

Deliberately NOT here (later work, not forgotten):

- Token issuance belongs to ``auth.security.create_token`` and stays at the
  HTTP layer; this service returns the identity, not a session.
- Token revocation, ``jti`` tracking and refresh tokens are explicitly later
  work; nothing in this module pretends to support them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.auth.security import hash_password, verify_password

# Postgres SQLSTATE for a unique-index violation. The ``users`` table has
# exactly one integrity constraint relevant to a registration insert: the
# case-insensitive unique index ``users_email_unique`` on ``lower(email)``.
# Any unique violation on that insert IS a duplicate email; anything else
# (should be impossible) propagates unchanged instead of being mislabeled.
_UNIQUE_VIOLATION_SQLSTATE = "23505"


class EmailAlreadyRegisteredError(Exception):
    """The email already has an account (case-insensitively).

    Raised instead of letting ``IntegrityError`` escape: a raw database
    exception is not an API. Carries only the email — never the password.
    """

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(
            f"An account with email {email!r} already exists "
            "(case-insensitive match)."
        )


@dataclass(frozen=True)
class UserIdentity:
    """The authenticated/registered identity, safe to hand to the HTTP layer."""

    id: uuid.UUID
    email: str


def _normalize_email(email: str) -> str:
    """Lowercase the email so lookups match the ``lower(email)`` unique index.

    Storage is normalized (lowercased) and lookups compare lowercased values,
    so ``A@B.com`` and ``a@b.com`` are the SAME account, enforced by the
    database even if a future write path forgets to normalize.
    """
    return email.lower()


# A decoy Argon2 hash used purely to equalize the timing of the
# "unknown email" path with the "known email, verifying" path. It is the hash
# of a fixed decoy string, deliberately not a secret and not any user's
# password; it is never compared against user input as truth.
_DECOY_HASH = hash_password("decoy-timing-equalizer-not-a-real-password")


async def register_user(
    session: AsyncSession, *, email: str, password: str
) -> UserIdentity:
    """Create a user account and return its identity.

    The password is hashed with the existing auth core
    (``auth.security.hash_password``, Argon2id) and only the hash is stored:
    no plaintext password is ever written or logged, including in error
    messages. Password-policy violations raise
    ``auth.security.PasswordValidationError`` before any database write, and
    are a distinct outcome from a duplicate email.

    Raises:
        EmailAlreadyRegisteredError: an account with this email already
            exists (case-insensitive), including inside a concurrent race —
            the unique index is the source of truth, so the duplicate check
            is the INSERT itself, never a pre-select.
        auth.security.PasswordValidationError: the password violates policy
            (empty or over-long).
    """
    # Hash BEFORE touching the database: a policy violation must not leave
    # partial work and must not be conflatable with a duplicate email.
    password_hash = hash_password(password)
    normalized = _normalize_email(email)

    try:
        result = await session.execute(
            text(
                """
                insert into users (email, password_hash)
                values (:email, :password_hash)
                returning id, email
                """
            ),
            {"email": normalized, "password_hash": password_hash},
        )
    except IntegrityError as exc:
        await session.rollback()
        orig = exc.orig
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate != _UNIQUE_VIOLATION_SQLSTATE:
            raise  # Not an email collision: do not mislabel other failures.
        raise EmailAlreadyRegisteredError(normalized) from exc

    row = result.mappings().one()
    # The profile row is created by the handle_new_user trigger (P2 schema).
    # This service must NOT insert a profile itself; if the trigger stops
    # firing, the integration tests assert the profile exists and will fail.
    await session.commit()
    return UserIdentity(id=row["id"], email=row["email"])


async def authenticate_user(
    session: AsyncSession, *, email: str, password: str
) -> UserIdentity | None:
    """Verify credentials and return the identity, or ``None`` on failure.

    ANTI-ENUMERATION CONTRACT: a wrong password and an unknown email return
    the SAME outcome — ``None`` — with no distinguishing detail, because a
    helpful distinct error ("email not found" vs "wrong password") would let
    the caller enumerate which emails have accounts. This is deliberate; do
    not "improve" it into two different errors. The unknown-email path also
    runs a decoy constant-time hash verification so its timing matches the
    known-email path.

    A corrupted stored hash fails authentication as ``None``: the verifier
    (``auth.security.verify_password``) already returns ``False`` for a
    malformed hash, so this module never pre-checks the hash shape and never
    catches around it — a corrupted value is an authentication failure, not
    a 500.

    Token issuance (``auth.security.create_token``) stays at the HTTP layer.
    Token revocation and ``jti`` tracking are deliberately later work; they
    are not stubbed or implied here.
    """
    normalized = _normalize_email(email)
    row = (
        await session.execute(
            text(
                """
                select id, email, password_hash
                from users
                where lower(email) = lower(:email)
                """
            ),
            {"email": normalized},
        )
    ).mappings().one_or_none()

    if row is None:
        # Unknown email: burn the same verification cost against a decoy hash
        # so response timing cannot distinguish this from a wrong password.
        verify_password(_DECOY_HASH, password)
        return None

    if not verify_password(row["password_hash"], password):
        return None

    return UserIdentity(id=row["id"], email=row["email"])
