"""The chat context endpoint: everything the frontend needs to run ONE turn.

``POST /chat/context`` answers, in a single authenticated call:

* the assembled **system prompt** — built by the ported chat prompt builder
  (:func:`cycloai.chat.prompt.build_system_prompt`) from the authenticated
  athlete's REAL profile and the retrieved knowledge-base context;
* the **conversation id** to use — the supplied one (owner-checked) or a
  freshly created conversation titled from the first message exactly the way
  ``POST /conversations`` does (:func:`truncate_title`);
* whether **knowledge was actually used**, so the client can tell "nothing
  relevant was retrieved" apart from "retrieval failed" (both render the
  same prompt: without the knowledge block).

Architecture boundary (deliberate, documented): the chat's BUSINESS LOGIC
lives in the backend — the prompt, retrieval and persistence are all here —
while the STREAMING TRANSPORT stays in the frontend, which calls the model
and streams to the browser as it does today, because the client consumes the
AI SDK's stream protocol and moving the transport would mean reimplementing
abort, error propagation and mid-stream rate-limit detection alongside a
client rework, for no user-visible gain. This is additive later: a backend
streaming endpoint can be introduced without moving anything built here.

Retrieval is ADDITIVE: an empty result or a failing retrieval never fails
the request — the prompt is built without the knowledge block, exactly what
the builder expects (it omits the section cleanly).

Persistence boundary: this endpoint persists NOTHING about the turn's
messages. The conversation row itself is created here when the client had
none (so the reply has a home), but the USER's message and the ASSISTANT's
reply are both written by the client through the existing message endpoint
(``POST /conversations/{id}/messages`` — role ``user`` before streaming,
role ``assistant`` after), as it already does. A message is therefore never
lost HERE: this endpoint never receives ownership of one.

Ownership: the identity comes ONLY from the verified session token, bound
onto the session with :func:`bind_session_user` before any storage access.
The profile read and the conversation read/create both go through the
ownership-enforcing repositories. A conversation belonging to somebody else
is refused EXACTLY like a nonexistent one — the same ``404`` detail constant
as :mod:`cycloai.api.routes_conversations`, never a ``403``, which would
confirm the conversation exists. Nothing in the request body selects whose
profile is loaded: a smuggled ``id`` field is accepted and ignored, the same
contract the conversation endpoints apply.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.api.deps import get_current_athlete, get_retrieve, get_session
from cycloai.api.routes_conversations import (
    _CONVERSATION_NOT_FOUND_DETAIL,
    truncate_title,
)
from cycloai.chat.prompt import ChatAthlete, build_system_prompt
from cycloai.db.repositories import (
    ConversationRepository,
    ProfileRepository,
    bind_session_user,
)
from cycloai.domain.zones import AthleteThresholds, TrainingSystem
from cycloai.generator.generate import RetrieveFn

__all__ = ["router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(prefix="/chat", tags=["chat"])

#: Maximum message length, the same bound the message endpoint enforces on
#: stored content: the context call receives exactly the text that will be
#: persisted there, so it must accept exactly what that endpoint accepts.
_MESSAGE_MAX_LENGTH: Final[int] = 100_000

# ``_CONVERSATION_NOT_FOUND_DETAIL`` is imported — not re-declared — so the
# two endpoints CANNOT drift apart: a foreign and a nonexistent conversation
# collapse into this one detail.


def get_profile_repository() -> ProfileRepository:
    """Provide the profile repository (a seam so tests can substitute it)."""
    return ProfileRepository()


def get_conversation_repository() -> ConversationRepository:
    """Provide the conversation repository (a seam so tests can substitute it)."""
    return ConversationRepository()


CallerDep = Annotated[uuid.UUID, Depends(get_current_athlete)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ProfileRepoDep = Annotated[ProfileRepository, Depends(get_profile_repository)]
ConversationRepoDep = Annotated[
    ConversationRepository, Depends(get_conversation_repository)
]
RetrieveDep = Annotated[RetrieveFn, Depends(get_retrieve)]


class ChatContextCreate(BaseModel):
    """The body of ``POST /chat/context``.

    ``extra="forbid"`` turns a typo into a clear ``422`` at the boundary.
    The one deliberate exception is ``id``: it is ACCEPTED and IGNORED —
    identity comes only from the verified token, so no body value can
    influence which profile is loaded or which owner is written.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=_MESSAGE_MAX_LENGTH)
    conversation_id: uuid.UUID | None = None
    # Accepted but never applied: excluded so no body value can influence
    # ownership. Identity is token-only.
    id: uuid.UUID | None = Field(default=None, exclude=True)


class ChatContextOut(BaseModel):
    """One chat turn's context: the prompt, the conversation, and the flag.

    Deliberately minimal: the athlete's raw profile row and anything from
    ``users`` beyond what the prompt legitimately needs (already rendered
    INTO the prompt text) never appear here.
    """

    conversation_id: uuid.UUID
    system_prompt: str
    knowledge_used: bool


def _as_float(value: Any) -> float | None:
    """Numeric columns arrive as ``Decimal``; the builder takes ``float``."""
    if value is None:
        return None
    return float(value) if isinstance(value, Decimal) else float(value)


def _thresholds_from_profile(profile: Any) -> AthleteThresholds | None:
    """The athlete's DECLARED threshold, in their own system, or ``None``.

    The ``training_system`` column has a storage default, but a default is
    not a declaration: a threshold exists only when the DECLARED system's
    metric is present and positive. A new profile (``lthr_bpm`` null until
    onboarding completes) therefore maps to ``None`` and the prompt says so
    honestly — the endpoint passes the absence through rather than refusing
    the request, because an athlete who has not finished onboarding can
    still be in the chat asking for help. An unrecognised ``training_system``
    value also yields ``None``: rendering a threshold for an unknown system
    would fabricate one.
    """
    system = getattr(profile, "training_system", None)
    if system == TrainingSystem.POWER:
        ftp = profile.ftp_estimated
        if ftp is None or ftp <= 0:
            return None
        return AthleteThresholds(
            system=TrainingSystem.POWER, ftp_watts=float(ftp)
        )
    if system == TrainingSystem.HEART_RATE:
        lthr = profile.lthr_bpm
        if lthr is None or lthr <= 0:
            return None
        return AthleteThresholds(
            system=TrainingSystem.HEART_RATE, lthr_bpm=float(lthr)
        )
    return None


def _athlete_from_profile(profile: Any) -> ChatAthlete:
    """Map the caller's OWN profile row onto the prompt builder's input.

    Only the columns the prompt consumes are carried over: identifiers,
    credentials and account fields have no path into this value object.
    """
    last_sync_at: date | None = profile.last_sync_at
    if isinstance(last_sync_at, datetime):
        last_sync_at = last_sync_at.date()
    return ChatAthlete(
        thresholds=_thresholds_from_profile(profile),
        objective=profile.objective,
        weekly_hours=_as_float(profile.weekly_hours),
        gym_days_per_week=profile.gym_days_per_week,
        injuries=profile.injuries,
        has_power_meter=profile.has_power_meter,
        target_event=profile.target_event,
        target_event_date=profile.target_event_date,
        strava_connected=bool(profile.strava_connected),
        last_sync_at=last_sync_at,
        ctl=_as_float(profile.ctl),
        atl=_as_float(profile.atl),
        tsb=_as_float(profile.tsb),
        weekly_volume_km=_as_float(profile.weekly_volume_km),
        weekly_volume_hours=_as_float(profile.weekly_volume_hours),
        avg_days_per_week=_as_float(profile.avg_days_per_week),
    )


async def _retrieve_knowledge_text(
    retrieve: RetrieveFn | None, query: str
) -> str:
    """Retrieved knowledge as display text, or ``""`` on any failure.

    Retrieval is ADDITIVE and must never fail the request: the generator
    pipeline's degradation contract
    (:func:`cycloai.generator.generate.generate_workout`) applies here too —
    an exception is logged and the turn continues without knowledge. ``""``
    is the no-knowledge value; the builder omits the section cleanly and
    ``knowledge_used`` reports ``False`` so the client can distinguish "no
    knowledge was relevant" from a successful retrieval.
    """
    if retrieve is None or not query.strip():
        return ""
    try:
        result = await retrieve(query)
    except Exception as err:  # noqa: BLE001 - retrieval NEVER fails the request
        logger.warning(
            "chat knowledge retrieval failed, continuing without it: %s", err
        )
        return ""
    text = result if isinstance(result, str) else result.text
    return text or ""


@router.post(
    "/context",
    response_model=ChatContextOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "The conversation does not exist, or it belongs to another "
                "athlete. The two cases are deliberately indistinguishable."
            )
        },
    },
    summary=(
        "Return one chat turn's context: the system prompt, the conversation "
        "id (created when absent) and whether knowledge was used."
    ),
)
async def chat_context(
    body: ChatContextCreate,
    caller_id: CallerDep,
    session: SessionDep,
    profile_repo: ProfileRepoDep,
    conversation_repo: ConversationRepoDep,
    retrieve: RetrieveDep,
) -> ChatContextOut:
    """Assemble one chat turn's context for the authenticated athlete.

    Nothing about the turn's MESSAGES is persisted here (see the module
    docstring for where the user and assistant messages are written); the
    only write is the conversation row created when the client supplied
    none, titled from the first message the way ``POST /conversations``
    does. The profile is loaded for the TOKEN's identity only, and a
    foreign conversation id is refused exactly like a nonexistent one.
    """
    bind_session_user(session, caller_id)

    if body.conversation_id is not None:
        conversation = await conversation_repo.get_conversation(
            session, caller_id, body.conversation_id
        )
        if conversation is None:
            # Same detail for missing AND foreign: re-splitting them would
            # leak that somebody else's conversation exists.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_CONVERSATION_NOT_FOUND_DETAIL,
            )
    else:
        conversation = await conversation_repo.create_conversation(
            session, caller_id, title=truncate_title(body.message)
        )
        if conversation is None:
            # Unreachable right after a successful bind: kept fail-closed so
            # a future guard change can never turn into an unintended
            # success (same contract as ``create_conversation``).
            logger.warning("conversation creation refused by ownership guard")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        # Transaction ownership: the shared session dependency
        # (``cycloai.db.engine.get_session``) commits at the request boundary.
        # Kept ONLY because the integration tests override ``get_session``
        # with a bare, non-committing session factory — same story as the
        # conversation endpoints; delete with those when they change.
        await session.commit()

    # The profile is the CALLER's, always: nothing in the body selects it.
    profile = await profile_repo.get_profile(session, caller_id)
    athlete = (
        _athlete_from_profile(profile) if profile is not None else ChatAthlete()
    )

    knowledge_text = await _retrieve_knowledge_text(retrieve, body.message)
    knowledge_used = bool(knowledge_text.strip())
    system_prompt = build_system_prompt(
        athlete, knowledge=knowledge_text if knowledge_used else None
    )

    return ChatContextOut(
        conversation_id=conversation.id,
        system_prompt=system_prompt,
        knowledge_used=knowledge_used,
    )
