"""The profile and onboarding endpoints: ``GET /profile``,
``PATCH /profile`` and ``POST /onboarding/complete``.

This is the slice that makes the generator reachable by a real user: the
athlete's declared training system (``training_system``) and threshold
(``lthr_bpm`` / ``ftp_estimated``) live on the ``profiles`` row, and
``onboarding_completed`` is the product's flag for "this athlete can be
served". Onboarding is what populates and validates them.

Outcome mapping is deliberately narrow and honest:

* **unauthenticated** → ``401`` from the auth seam (one generic detail);
* **profile read/update success** → ``200`` with the caller's own profile;
* **disallowed or unknown field on PATCH** → ``422`` from the request model
  (``extra="forbid"``), with the repository's own ``ValueError`` allowlist
  rejection mapped to ``400`` as defense in depth — never a ``500``;
* **unsupported ``training_system``** → ``422`` naming the field;
* **incoherent onboarding** (a declared system without its matching
  threshold) → ``422`` that NAMES the missing field(s) — a generic failure
  would leave the athlete guessing;
* **no profile row** → ``404`` (every user gets one via trigger, so this is
  an integrity anomaly, not a normal state).

Ownership: the identity comes ONLY from the verified session token. The
caller id is bound onto the session with :func:`bind_session_user` before
any repository access, so the fail-closed ownership guard is exercised on
every request and no query is unscoped. Nothing in the body may select
which profile is read or written. The single field the response takes from
``users`` is the caller's OWN ``email``, read through the owner-scoped
``ProfileRepository.get_email`` (same ``user_id`` parameter, same caller
guard); the rest of the user row — ``password_hash`` included — has no path
into a response.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.api.deps import get_current_athlete, get_session
from cycloai.db.repositories import ProfileRepository, bind_session_user

__all__ = ["router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(tags=["profile"])

#: The two training systems the product supports — the same domain the
#: ``profiles.training_system`` CHECK constraint enforces and the same two
#: branches the generator can derive targets from. Anything else is refused
#: clearly instead of reaching the database as an ``IntegrityError``.
SUPPORTED_TRAINING_SYSTEMS: Final[tuple[str, ...]] = ("power", "heart_rate")

#: One generic message for a missing profile row; the profile is created by
#: the ``handle_new_user`` trigger, so this is an integrity anomaly.
_PROFILE_NOT_FOUND_DETAIL = "Profile not found."


def get_profile_repository() -> ProfileRepository:
    """Provide the profile repository (a seam so tests can substitute it)."""
    return ProfileRepository()


CallerDep = Annotated[uuid.UUID, Depends(get_current_athlete)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ProfileRepoDep = Annotated[ProfileRepository, Depends(get_profile_repository)]


class ProfileOut(BaseModel):
    """The caller's own profile: the ``profiles`` columns plus their email.

    Every field here is athlete-owned and legitimately visible. The model is
    built from the ``Profile`` ORM row's attributes, plus the account
    ``email`` read through the owner-scoped ``ProfileRepository.get_email`` —
    the only field sourced from ``users``, and only ever the token identity's
    own. The explicit field list makes any future drift a visible schema
    change rather than a silent leak: no other ``users`` column
    (``password_hash`` included) has a path into a response.
    """

    id: uuid.UUID
    email: str
    created_at: datetime
    updated_at: datetime
    display_name: str | None
    avatar_url: str | None
    strava_id: int | None
    strava_connected: bool
    strava_connected_at: datetime | None
    objective: str | None
    weekly_hours: float | None
    gym_days_per_week: int | None
    injuries: str | None
    has_power_meter: bool
    target_event: str | None
    target_event_date: date | None
    onboarding_completed: bool
    training_system: str
    lthr_bpm: int | None
    ftp_estimated: int | None
    ctl: float | None
    atl: float | None
    tsb: float | None
    weekly_volume_km: float | None
    weekly_volume_hours: float | None
    avg_days_per_week: float | None
    last_sync_at: datetime | None


class ProfileUpdate(BaseModel):
    """The fields an athlete may edit on their own profile.

    This is the client-facing projection of the repository's internal
    allowlist, narrowed to what a human legitimately sets by hand: identity
    fields, training context, and the declared training system and
    thresholds that onboarding populates. Deliberately NOT exposed:
    ``onboarding_completed`` (it may only be set through
    ``POST /onboarding/complete``, which validates the required fields
    first — a PATCH shortcut would bypass that gate), the Strava sync
    fields (owned by the Strava integration), the CTL/ATL/TSB metrics and
    sync timestamps (owned by the sync pipeline).

    ``extra="forbid"`` turns a typo or a smuggled field into a clear 422 at
    the boundary, instead of relying on the repository's later rejection.
    That includes ``id``: identity comes only from the verified token, so an
    id in the body can never select which profile is written — and since it
    could not be honoured anyway, it is REJECTED like any other unknown
    field rather than accepted and silently ignored. A client that sends
    something that will not be applied sees the same clear rejection as any
    other unknown field, instead of a 200 that hides a no-op.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=2048)
    objective: str | None = Field(default=None, max_length=2000)
    weekly_hours: float | None = Field(default=None, ge=0, le=168)
    gym_days_per_week: int | None = Field(default=None, ge=0, le=7)
    injuries: str | None = Field(default=None, max_length=2000)
    has_power_meter: bool | None = None
    target_event: str | None = Field(default=None, max_length=500)
    target_event_date: date | None = None
    training_system: Literal["power", "heart_rate"] | None = None
    lthr_bpm: int | None = Field(default=None, ge=1, le=400)
    ftp_estimated: int | None = Field(default=None, ge=1, le=1000)


def _missing_profile() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_PROFILE_NOT_FOUND_DETAIL,
    )


async def _caller_email(
    repo: ProfileRepository, session: AsyncSession, caller_id: uuid.UUID
) -> str:
    """Read the caller's own email through the owner-scoped repository.

    ``profiles.id`` references ``users.id`` on delete cascade, so a profile
    without its user row is the same integrity anomaly as a missing profile:
    it collapses into the same ``404`` instead of inventing a value.
    """
    email = await repo.get_email(session, caller_id)
    if email is None:
        raise _missing_profile()
    return email


def _profile_out(profile: Any, email: str) -> ProfileOut:
    """Build the response model: the profile row plus the caller's email.

    Every field is read by name from the ``Profile`` row (``email`` excepted
    — it lives on ``users`` and arrives from the owner-scoped read), then
    VALIDATED through the model. This is deliberately not a blanket
    serialisation: the field list on ``ProfileOut`` is the single authority
    on what may appear in a response, and an unknown attribute on the row is
    simply never read.
    """
    data = {
        name: getattr(profile, name)
        for name in ProfileOut.model_fields
        if name != "email"
    }
    data["email"] = email
    return ProfileOut.model_validate(data)


@router.get(
    "/profile",
    response_model=ProfileOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "The profile row does not exist."},
    },
    summary="Return the authenticated athlete's own profile.",
)
async def read_profile(
    caller_id: CallerDep,
    session: SessionDep,
    repo: ProfileRepoDep,
) -> ProfileOut:
    """Read the caller's own profile through the ownership-enforcing repo.

    The caller id comes only from the verified token and is bound onto the
    session first, so the repository's fail-closed guard runs on this read
    and on the account email read that follows it.
    """
    bind_session_user(session, caller_id)
    profile = await repo.get_profile(session, caller_id)
    if profile is None:
        raise _missing_profile()
    email = await _caller_email(repo, session, caller_id)
    return _profile_out(profile, email)


@router.patch(
    "/profile",
    response_model=ProfileOut,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "A field outside the updatable allowlist was requested.",
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "The profile row does not exist."},
    },
    summary="Update the authenticated athlete's own profile.",
)
async def update_own_profile(
    body: ProfileUpdate,
    caller_id: CallerDep,
    session: SessionDep,
    repo: ProfileRepoDep,
) -> ProfileOut:
    """Apply a partial update to the caller's own profile.

    Only the fields present in the body are sent, and the repository's
    explicit allowlist remains the final authority: its ``ValueError`` for a
    protected or unknown field is mapped to a clear ``400`` here — never a
    ``500``. ``onboarding_completed`` is not part of the client-facing
    payload, so onboarding state can only be earned through the completion
    endpoint's validation.
    """
    bind_session_user(session, caller_id)
    updates = body.model_dump(exclude_unset=True)
    try:
        profile = await repo.update_profile(session, caller_id, **updates)
    except ValueError:
        logger.warning("profile update rejected by repository allowlist")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The request contains fields that cannot be updated.",
        ) from None
    if profile is None:
        raise _missing_profile()
    email = await _caller_email(repo, session, caller_id)
    return _profile_out(profile, email)


@router.post(
    "/onboarding/complete",
    response_model=ProfileOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "The profile row does not exist."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "The profile is missing a required field, or declares an "
                "unsupported training system. The response names what is "
                "missing."
            ),
        },
    },
    summary="Mark onboarding complete after verifying the required fields.",
)
async def complete_onboarding(
    caller_id: CallerDep,
    session: SessionDep,
    repo: ProfileRepoDep,
) -> ProfileOut:
    """Mark the caller's onboarding complete — but only coherently.

    Required set (from the schema and the generator's needs):

    * ``training_system`` — must be one of the two supported systems; the
      generator branches on it to derive targets, and the DB CHECK would
      only surface later as a storage error;
    * ``lthr_bpm`` — required when ``training_system`` is ``heart_rate``;
      without it the generator has no threshold to derive HR zones from;
    * ``ftp_estimated`` — required when ``training_system`` is ``power``;
      without it the generator has no FTP to derive power zones from.

    A profile that declares a system without its matching threshold is an
    incoherent profile the generator cannot serve, so the refusal names the
    missing value(s) instead of failing generically. Only after validation
    does the endpoint set ``onboarding_completed`` through the repository —
    the one path a client can flip that flag, so the gate cannot be bypassed.
    """
    bind_session_user(session, caller_id)
    profile = await repo.get_profile(session, caller_id)
    if profile is None:
        raise _missing_profile()

    training_system = profile.training_system
    if training_system is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Onboarding cannot be completed: missing required field(s): "
                "training_system."
            ),
        )
    if training_system not in SUPPORTED_TRAINING_SYSTEMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Onboarding cannot be completed: training_system must be one "
                f"of {', '.join(SUPPORTED_TRAINING_SYSTEMS)}; got "
                f"{training_system!r}."
            ),
        )

    missing: list[str] = []
    if training_system == "heart_rate" and profile.lthr_bpm is None:
        missing.append("lthr_bpm")
    if training_system == "power" and profile.ftp_estimated is None:
        missing.append("ftp_estimated")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Onboarding cannot be completed: missing required field(s): "
                f"{', '.join(missing)}."
            ),
        )

    updated = await repo.update_profile(session, caller_id, onboarding_completed=True)
    if updated is None:
        raise _missing_profile()
    email = await _caller_email(repo, session, caller_id)
    return _profile_out(updated, email)
