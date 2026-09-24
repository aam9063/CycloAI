"""Repositories for user-owned data: profiles, conversations and messages.

This layer exists to compensate for something the schema port dropped: Row
Level Security. The database used to enforce ``auth.uid()`` policies; it no
longer does. **Authorization lives entirely here.** A single forgotten owner
filter would hand one user another user's data with nothing behind it to
catch the mistake, so the rules below are a security boundary, not a
convenience wrapper:

1. Every public function that touches user-owned data takes ``user_id`` as a
   required parameter and filters by it. ``backend/tests/test_repository_contract.py``
   structurally enforces this so an unscoped accessor cannot land quietly.
2. No public function can return another user's row. "Does not exist" and
   "not yours" are deliberately collapsed into the same outcome (``None``,
   or an empty list): distinguishing them from the outside would itself be a
   leak, because it would confirm that a given id exists.
3. There is deliberately NO "get conversation by id without owner" accessor.

``knowledge_embeddings`` (shared RAG content) and ``waitlist`` (insert-only)
carry no ownership and get no repositories here.

Defense in depth — session-bound caller, and it fails **closed**: because RLS
is gone, the ``user_id`` parameter is only as honest as the layer that supplies
it. Call sites must derive it from verified credentials and bind it onto the
session with :func:`bind_session_user`. The binding guard has exactly three
outcomes:

* **Unbound session** → :class:`UnboundSessionError`. A forgotten bind is a
  wiring bug (the same bug class RLS's removal introduced), so it is raised
  loudly here, never silently tolerated and never disguised as "not found".
* **Bound to a different user** → a foreign access, deliberately collapsed
  into the same "not found" the caller would get for a nonexistent id.
  Distinguishing "not yours" from "does not exist" would itself leak that the
  row exists, so this stays quiet by design.
* **Bound to the same user** (or bound as internal via
  :func:`bind_internal_session`) → the call proceeds under rule 1's filters.

Binding is monotonic: :func:`bind_session_user` refuses to re-bind a session
that is already bound to a different user.

All queries are parameterised SQLAlchemy expressions; no string-built SQL.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.db.models import Conversation, Message, Profile, User

_SESSION_USER_KEY = "cycloai.authenticated_user_id"


# Sentinel stored instead of a user id when *trusted internal code* binds the
# session explicitly (migrations, ingestion, maintenance, cross-user test
# fixtures). A unique object: no user id can ever collide with it.
_INTERNAL_CALLER = object()

_UNBOUND_MESSAGE = (
    "Session is not bound to an authenticated caller: the ownership guard "
    "cannot run. bind_session_user(session, user_id) must be called right "
    "after deriving the caller's id from verified credentials, before any "
    "repository access. Trusted internal code acting across users must call "
    "bind_internal_session(session) explicitly."
)


class UnboundSessionError(RuntimeError):
    """A repository call reached a session with no bound caller.

    This is a wiring error, not a user-level condition: somewhere a request
    path forgot to bind the caller, which would silently disable the entire
    ownership check. It is therefore raised loudly here — never collapsed into
    "not found", because hiding a wiring bug from the developer is how it
    survives to production.
    """


# Columns a caller may set on their own profile. Anything else is rejected
# before it can reach the database, so a typo or a smuggled field (``id``,
# ``updated_at``) cannot turn into an unintended write.
_UPDATABLE_PROFILE_FIELDS: frozenset[str] = frozenset(
    {
        "display_name",
        "avatar_url",
        "strava_id",
        "strava_connected",
        "strava_connected_at",
        "objective",
        "weekly_hours",
        "gym_days_per_week",
        "injuries",
        "has_power_meter",
        "target_event",
        "target_event_date",
        "onboarding_completed",
        "training_system",
        "lthr_bpm",
        "ftp_estimated",
        "ctl",
        "atl",
        "tsb",
        "weekly_volume_km",
        "weekly_volume_hours",
        "avg_days_per_week",
        "last_sync_at",
    }
)


def bind_session_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Record the authenticated caller on ``session`` (defense in depth).

    The application layer calls this once per request, right after deriving
    the caller's id from verified credentials. Every repository function then
    refuses any ``user_id`` argument that does not match the bound caller,
    collapsing the mismatch into "not found" exactly like a foreign read.

    Binding is monotonic: re-binding the *same* user is a harmless no-op, but
    re-binding to a *different* user raises ``ValueError``. Code holding the
    session must not be able to switch identity mid-flight. Trusted internal
    code (migrations, ingestion, maintenance) that genuinely must act across
    users binds explicitly with :func:`bind_internal_session` instead.
    """
    existing = session.info.get(_SESSION_USER_KEY)
    if existing is None:
        session.info[_SESSION_USER_KEY] = user_id
    elif existing == user_id:
        return
    else:
        raise ValueError(
            "Session is already bound to a different caller; refusing to "
            f"re-bind {existing} -> {user_id}. Binding is monotonic: use one "
            "session per authenticated request, or bind_internal_session() "
            "for trusted internal code."
        )


def bind_internal_session(session: AsyncSession) -> None:
    """Bind ``session`` for trusted internal code, explicitly.

    Migrations, ingestion, maintenance jobs and cross-user test fixtures
    legitimately act across users. This entry point binds a distinct internal
    sentinel that the caller guard accepts — permissiveness becomes a
    deliberate, visible, greppable act instead of a silent default.

    Like :func:`bind_session_user`, it refuses to re-bind a session that is
    already bound (to a user or to the internal sentinel); re-binding as
    internal is a no-op.
    """
    existing = session.info.get(_SESSION_USER_KEY)
    if existing is _INTERNAL_CALLER:
        return
    if existing is not None:
        raise ValueError(
            "Session is already bound to a specific caller; refusing to "
            f"re-bind it as internal ({existing} -> internal). Use a fresh "
            "session."
        )
    session.info[_SESSION_USER_KEY] = _INTERNAL_CALLER


def _caller_matches(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Fail-closed caller check for the session's bound caller.

    Three outcomes, chosen so permissiveness can never be the silent default:

    * Nothing is bound → raise :class:`UnboundSessionError`. A forgotten bind
      is a wiring bug; it must be loud, never silently "allowed" and never
      disguised as "not found" (that would smuggle the bug to production).
    * Bound to the internal sentinel → ``True``: trusted internal code set it
      explicitly.
    * Bound to a user → ``True`` only for that same user. Any other ``user_id``
      returns ``False``, which every caller collapses into the same "not
      found" a nonexistent id produces — a distinct error would leak that the
      row exists.
    """
    bound = session.info.get(_SESSION_USER_KEY)
    if bound is None:
        raise UnboundSessionError(_UNBOUND_MESSAGE)
    if bound is _INTERNAL_CALLER:
        return True
    return bound == user_id


class ProfileRepository:
    """Access to the caller's own profile row. Never anyone else's."""

    async def get_email(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> str | None:
        """Return the caller's own account email, or ``None`` if not visible.

        The email lives on ``users``, not ``profiles``, so this is the one
        owner-scoped accessor for it. Like every method here it takes the
        ``user_id`` as a required parameter and filters by it, guarded by the
        same fail-closed caller check: a session bound to another caller gets
        ``None`` (collapsed into "not found", indistinguishable from a
        missing user), so no call path can ever read a different account's
        email. Only the email column is selected — never the full user row —
        so ``password_hash`` has no path out of this method.
        """
        if not _caller_matches(session, user_id):
            return None
        return (
            await session.scalars(select(User.email).where(User.id == user_id))
        ).first()

    async def get_profile(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> Profile | None:
        """Return the caller's profile, or ``None`` if it does not exist."""
        if not _caller_matches(session, user_id):
            return None
        return (
            await session.scalars(select(Profile).where(Profile.id == user_id))
        ).first()

    async def update_profile(
        self, session: AsyncSession, user_id: uuid.UUID, **fields: Any
    ) -> Profile | None:
        """Update the caller's own profile fields; ``None`` if not found.

        Only fields in the explicit allowlist are accepted; anything else
        raises ``ValueError`` rather than silently reaching the database.
        """
        if not _caller_matches(session, user_id):
            return None
        unknown = set(fields) - _UPDATABLE_PROFILE_FIELDS
        if unknown:
            raise ValueError(
                f"Unknown or protected profile fields: {sorted(unknown)}. "
                f"Updatable fields are: {sorted(_UPDATABLE_PROFILE_FIELDS)}"
            )
        profile = (
            await session.scalars(select(Profile).where(Profile.id == user_id))
        ).first()
        if profile is None:
            return None
        for name, value in fields.items():
            setattr(profile, name, value)
        profile.updated_at = func.now()
        await session.flush()
        await session.refresh(profile)
        return profile


class ConversationRepository:
    """Access to the caller's own conversations. Never anyone else's."""

    async def create_conversation(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        summary: str | None = None,
    ) -> Conversation | None:
        """Create a conversation owned by ``user_id``.

        Refused (``None``) if the session is bound to a different caller.
        """
        if not _caller_matches(session, user_id):
            return None
        conversation = Conversation(user_id=user_id, title=title, summary=summary)
        session.add(conversation)
        await session.flush()
        # Fetch the server-generated id/defaults onto the instance.
        await session.refresh(conversation)
        return conversation

    async def list_conversations(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> list[Conversation]:
        """List only the caller's conversations, most recently updated first.

        A foreign user's conversations are structurally absent from this list:
        the owner filter is part of the query itself, not a post-hoc check.
        """
        if not _caller_matches(session, user_id):
            return []
        result = await session.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.all())

    async def get_conversation(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> Conversation | None:
        """Fetch one of the caller's conversations by id.

        Returns ``None`` both when the conversation does not exist and when
        it belongs to somebody else — the two cases are indistinguishable to
        the caller by design. There is deliberately no ownerless variant of
        this accessor.
        """
        if not _caller_matches(session, user_id):
            return None
        return (
            await session.scalars(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
        ).first()

    async def update_conversation(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        title: str | None = None,
        summary: str | None = None,
    ) -> Conversation | None:
        """Update the caller's own conversation; ``None`` if not visible.

        ``title`` / ``summary`` left as ``None`` keep their current value
        (pass explicit values to change or clear them). ``updated_at`` is
        bumped on every successful update. A conversation that does not exist
        or belongs to another user yields ``None`` and changes nothing.
        """
        conversation = await self.get_conversation(session, user_id, conversation_id)
        if conversation is None:
            return None
        if title is not None:
            conversation.title = title
        if summary is not None:
            conversation.summary = summary
        conversation.updated_at = func.now()
        await session.flush()
        await session.refresh(conversation)
        return conversation


class MessageRepository:
    """Access to the messages of conversations the caller owns."""

    async def append_message(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message | None:
        """Append a message to one of the caller's conversations.

        The conversation must exist AND be owned by ``user_id``; otherwise
        ``None`` is returned and nothing is written. The denormalised
        ``user_id`` on the message row is always the caller's, never taken
        from anywhere else.
        """
        if not _caller_matches(session, user_id):
            return None
        conversation = (
            await session.scalars(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
        ).first()
        if conversation is None:
            return None
        message = Message(
            conversation_id=conversation.id,
            user_id=user_id,
            role=role,
            content=content,
            metadata_=metadata,
        )
        session.add(message)
        await session.flush()
        # Fetch the server-generated id/created_at onto the instance.
        await session.refresh(message)
        return message

    async def list_messages(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> list[Message] | None:
        """List a conversation's messages in creation order.

        ``None`` when the conversation is not visible to the caller (missing
        or foreign — indistinguishable, by design). An empty list means the
        caller owns the conversation and it simply has no messages yet.
        """
        if not _caller_matches(session, user_id):
            return None
        conversation = (
            await session.scalars(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
        ).first()
        if conversation is None:
            return None
        result = await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.all())
