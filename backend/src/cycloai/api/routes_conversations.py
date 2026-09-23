"""The conversation and message persistence endpoints.

This is the slice that replaces the deleted Supabase chat-history path: an
athlete's conversations and messages now live in our own PostgreSQL, behind
the ownership-enforcing repositories in :mod:`cycloai.db.repositories`.

Outcome mapping is deliberately narrow and honest:

* **unauthenticated** → ``401`` from the auth seam (one generic detail);
* **list / read / append success** → ``200`` (``201`` for creates) with the
  caller's own data only;
* **conversation missing OR foreign** → ``404`` with ONE generic detail.
  The repository collapses "does not exist" and "not yours" into the same
  ``None`` on purpose: a distinct error for a foreign id would confirm that
  the conversation exists, which is a leak. This module never re-splits them.

Ownership: the identity comes ONLY from the verified session token. The
caller id is bound onto the session with :func:`bind_session_user` before
any repository access, so the fail-closed ownership guard runs on every
request. Nothing in the body or the path may select the owner: a ``user_id``
or ``id`` smuggled into a body can never influence attribution — the
repository stamps the message's ``user_id`` from the bound caller itself.

Message rules (client bugs are rejected at the boundary, never stored):

* ``role`` must be exactly ``'user'`` or ``'assistant'`` — the same domain
  the ``messages.role`` CHECK constraint enforces, so a bad role is a clear
  ``422`` instead of a later ``IntegrityError``;
* ``content`` must be non-empty — an empty message is a client bug;
* ``metadata`` is optional JSON, bounded in serialized size and nesting
  depth so an arbitrarily large or deeply nested object cannot become a
  denial-of-service vector (a ``422`` names the limit that was exceeded).

Title behaviour is ported from the original client (``truncateTitle`` in
``lib/chat/text.ts``): truncation to 60 characters happens on a word
boundary when one exists far enough into the string, exactly as the old
app normalised titles, so titles created here look the same as the ones the
frontend used to create.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.api.deps import get_current_athlete, get_session
from cycloai.db.repositories import (
    ConversationRepository,
    MessageRepository,
    bind_session_user,
)

__all__ = ["router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(prefix="/conversations", tags=["conversations"])

#: The roles the ``messages.role`` CHECK constraint allows — the exact same
#: domain, validated here so a bad role is a clear ``422`` at the boundary.
ALLOWED_ROLES: Final[tuple[str, ...]] = ("user", "assistant")

#: Title truncation length, ported unchanged from the original client.
_TITLE_MAX_LENGTH: Final[int] = 60

#: Maximum serialized size of a message's ``metadata`` JSON. Real chat
#: metadata (token counts, model names, timestamps) is orders of magnitude
#: below this; a hostile payload cannot bloat a row or the JSONB indexes.
_METADATA_MAX_BYTES: Final[int] = 8 * 1024

#: Maximum nesting depth of a message's ``metadata`` JSON. Deeply nested
#: structures cost parse time on every read; real metadata is flat.
_METADATA_MAX_DEPTH: Final[int] = 8

#: Maximum stored message content length. Chat messages are prose, not
#: documents; this bounds a single row's size against an abusive client.
_CONTENT_MAX_LENGTH: Final[int] = 100_000

#: One generic detail for BOTH a nonexistent and a foreign conversation.
#: Keeping these identical is the security property — a distinct status or
#: message for a foreign id would confirm that the conversation exists.
_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."


def get_conversation_repository() -> ConversationRepository:
    """Provide the conversation repository (a seam so tests can substitute it)."""
    return ConversationRepository()


def get_message_repository() -> MessageRepository:
    """Provide the message repository (a seam so tests can substitute it)."""
    return MessageRepository()


CallerDep = Annotated[uuid.UUID, Depends(get_current_athlete)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ConversationRepoDep = Annotated[
    ConversationRepository, Depends(get_conversation_repository)
]
MessageRepoDep = Annotated[MessageRepository, Depends(get_message_repository)]


def truncate_title(text: str, max_chars: int = _TITLE_MAX_LENGTH) -> str:
    """Normalise a title exactly like the original client's ``truncateTitle``.

    Ported from ``lib/chat/text.ts`` (Next.js app)::

        export function truncateTitle(s: string, max: number): string {
          const trimmed = s.trim();
          if (trimmed.length <= max) return trimmed;
          const slice = trimmed.slice(0, max);
          const lastSpace = slice.lastIndexOf(' ');
          return lastSpace > max * 0.6 ? slice.slice(0, lastSpace) : slice;
        }

    Truncate at ``max`` characters on a word boundary when a space exists
    far enough into the slice (past 60% of ``max``); otherwise hard-cut.
    Whitespace is trimmed first, and a short-enough title is returned as-is.
    """
    trimmed = text.strip()
    if len(trimmed) <= max_chars:
        return trimmed
    slice_ = trimmed[:max_chars]
    last_space = slice_.rfind(" ")
    if last_space > max_chars * 0.6:
        return slice_[:last_space]
    return slice_


def _json_depth(value: object) -> int:
    """Nesting depth of a parsed-JSON-shaped value (scalars are depth 0)."""
    if isinstance(value, dict):
        return 1 + max((_json_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_json_depth(v) for v in value), default=0)
    return 0


class ConversationOut(BaseModel):
    """The caller's own conversation: exactly the ``conversations`` columns."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: Any
    updated_at: Any
    title: str | None
    summary: str | None


class MessageOut(BaseModel):
    """One stored message: exactly the ``messages`` columns.

    Built explicitly rather than via ``from_attributes`` because the ORM
    exposes the JSONB column as ``metadata_`` (``metadata`` itself is the
    SQLAlchemy declarative registry), so an implicit mapping would silently
    pick up the wrong attribute.
    """

    id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    content: str
    created_at: Any
    metadata: dict[str, Any] | None


class ConversationCreate(BaseModel):
    """The body of ``POST /conversations``.

    ``extra="forbid"`` turns a typo or a smuggled field into a clear ``422``
    at the boundary. The one deliberate exception is ``id``: it is ACCEPTED
    and IGNORED — identity comes only from the verified token, so an id in
    the body can never select which owner is written (the repository stamps
    ``user_id`` from the bound caller itself).
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    # Accepted but never applied: excluded so no body value can influence
    # ownership. Identity is token-only.
    id: uuid.UUID | None = Field(default=None, exclude=True)


class MessageCreate(BaseModel):
    """The body of ``POST /conversations/{id}/messages``.

    ``role`` is pinned to the schema CHECK's exact domain, ``content`` must
    be non-empty, and ``metadata`` is validated for serialized size and
    nesting depth before it can reach storage. There is NO ``user_id`` field:
    attribution is decided by the repository from the bound caller, so no
    body value can put a message on somebody else's identity.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=_CONTENT_MAX_LENGTH)
    metadata: dict[str, Any] | None = None
    # Accepted but never applied: excluded so no body value can influence
    # ownership. Identity is token-only.
    id: uuid.UUID | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _bound_metadata(self) -> MessageCreate:
        """Reject an unbounded ``metadata`` payload clearly, before storage.

        Two bounds, each checked with its own named message: total serialized
        size (:data:`_METADATA_MAX_BYTES`) and nesting depth
        (:data:`_METADATA_MAX_DEPTH`). A payload that is not JSON-serialisable
        at all is also refused here rather than failing later at the database.
        """
        if self.metadata is None:
            return self
        try:
            encoded = json.dumps(self.metadata, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ValueError(
                "metadata must be JSON-serialisable."
            ) from None
        size = len(encoded.encode("utf-8"))
        if size > _METADATA_MAX_BYTES:
            raise ValueError(
                "metadata is too large: "
                f"{size} bytes serialized exceeds the {_METADATA_MAX_BYTES}-byte limit."
            )
        depth = _json_depth(self.metadata)
        if depth > _METADATA_MAX_DEPTH:
            raise ValueError(
                "metadata is nested too deeply: depth "
                f"{depth} exceeds the {_METADATA_MAX_DEPTH}-level limit."
            )
        return self


def _conversation_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_CONVERSATION_NOT_FOUND_DETAIL,
    )


def _message_out(message: Any) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        metadata=message.metadata_,
    )


@router.get(
    "",
    response_model=list[ConversationOut],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
    },
    summary="List the authenticated athlete's own conversations, most recently active first.",
)
async def list_conversations(
    caller_id: CallerDep,
    session: SessionDep,
    repo: ConversationRepoDep,
) -> list[ConversationOut]:
    """List the caller's own conversations ordered by ``updated_at`` desc.

    The owner filter is part of the repository query itself, so a foreign
    user's conversations are structurally absent from the result — the
    ``conversations_user_updated`` index supports exactly this ordering.
    """
    bind_session_user(session, caller_id)
    conversations = await repo.list_conversations(session, caller_id)
    return [ConversationOut.model_validate(c) for c in conversations]


@router.post(
    "",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
    },
    summary="Create a conversation owned by the authenticated athlete.",
)
async def create_conversation(
    body: ConversationCreate,
    caller_id: CallerDep,
    session: SessionDep,
    repo: ConversationRepoDep,
) -> ConversationOut:
    """Create a conversation for the caller, normalising the title.

    The title is truncated exactly as the original client did
    (:func:`truncate_title`), and the owning ``user_id`` is stamped by the
    repository from the bound caller — never from the body.
    """
    bind_session_user(session, caller_id)
    title = truncate_title(body.title) if body.title is not None else None
    conversation = await repo.create_conversation(
        session, caller_id, title=title
    )
    if conversation is None:
        # Unreachable right after a successful bind: kept fail-closed so a
        # future guard change can never turn into an unintended success.
        logger.warning("conversation creation refused by ownership guard")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    # Transaction ownership: the shared session dependency
    # (``cycloai.db.engine.get_session``) now commits at the request boundary,
    # so this explicit commit is redundant in production. It is kept ONLY
    # because ``test_conversations_integration.py`` overrides ``get_session``
    # with a bare, non-committing session factory: remove the route-level
    # commits and those tests fail (the writes roll back when the overridden
    # session closes). When that override is removed in favour of the real
    # dependency, delete these commits too so the boundary is the single
    # transaction owner.
    await session.commit()
    return ConversationOut.model_validate(conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "The conversation does not exist, or it belongs to another "
                "athlete. The two cases are deliberately indistinguishable."
            )
        },
    },
    summary="Return the authenticated athlete's own conversation.",
)
async def read_conversation(
    conversation_id: uuid.UUID,
    caller_id: CallerDep,
    session: SessionDep,
    repo: ConversationRepoDep,
) -> ConversationOut:
    """Read one of the caller's conversations through the ownership guard.

    A missing id and a foreign id both collapse into the repository's
    ``None`` and therefore into the SAME ``404`` — never a ``403``, which
    would confirm that somebody else's conversation exists.
    """
    bind_session_user(session, caller_id)
    conversation = await repo.get_conversation(session, caller_id, conversation_id)
    if conversation is None:
        raise _conversation_not_found()
    return ConversationOut.model_validate(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageOut],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "The conversation does not exist, or it belongs to another "
                "athlete. The two cases are deliberately indistinguishable."
            )
        },
    },
    summary="List the messages of the caller's own conversation, oldest first.",
)
async def list_messages(
    conversation_id: uuid.UUID,
    caller_id: CallerDep,
    session: SessionDep,
    repo: MessageRepoDep,
) -> list[MessageOut]:
    """List a conversation's messages in creation order, oldest first.

    Visibility is decided by the repository: an invisible conversation
    (missing or foreign) yields ``None`` and maps to the same generic
    ``404`` as reading the conversation itself.
    """
    bind_session_user(session, caller_id)
    messages = await repo.list_messages(session, caller_id, conversation_id)
    if messages is None:
        raise _conversation_not_found()
    return [_message_out(m) for m in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "The conversation does not exist, or it belongs to another "
                "athlete. The two cases are deliberately indistinguishable, "
                "and nothing is written in either case."
            )
        },
    },
    summary="Append a message to the caller's own conversation.",
)
async def append_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    caller_id: CallerDep,
    session: SessionDep,
    message_repo: MessageRepoDep,
    conversation_repo: ConversationRepoDep,
) -> MessageOut:
    """Append a message and bump the conversation's ``updated_at``.

    The repository requires the conversation to be visible to the caller
    before it writes anything, so appending to somebody else's conversation
    is refused exactly like a nonexistent one — and it never writes a row
    whose ``user_id`` differs from the caller's, because attribution comes
    from the bound caller, not from the request. On success the
    conversation's ``updated_at`` is bumped through the repository's update
    operation so the list order reflects real activity.
    """
    bind_session_user(session, caller_id)
    message = await message_repo.append_message(
        session,
        caller_id,
        conversation_id,
        role=body.role,
        content=body.content,
        metadata=body.metadata,
    )
    if message is None:
        raise _conversation_not_found()
    await conversation_repo.update_conversation(session, caller_id, conversation_id)
    # Same story as ``create_conversation``: redundant under the request
    # boundary, load-bearing only for the session-overriding integration
    # tests. Kept until those tests go through the real dependency.
    await session.commit()
    return _message_out(message)
