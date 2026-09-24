"""Database package (P2): settings, async engine/session factories, ORM models.

``models`` mirrors the Alembic-managed schema; ``repositories`` is the
authorization boundary for user-owned data (RLS was dropped with the Supabase
port) and fails closed: a session with no bound caller raises
:class:`UnboundSessionError` instead of silently skipping the caller check.
Neither import requires a database connection: the engine
connects lazily on first use.
"""

from cycloai.db.engine import create_engine, get_engine, get_session, get_sessionmaker
from cycloai.db.models import Base
from cycloai.db.repositories import (
    ConversationRepository,
    MessageRepository,
    ProfileRepository,
    UnboundSessionError,
    bind_internal_session,
    bind_session_user,
)
from cycloai.db.settings import Settings

__all__ = [
    "Base",
    "ConversationRepository",
    "MessageRepository",
    "ProfileRepository",
    "Settings",
    "UnboundSessionError",
    "bind_internal_session",
    "bind_session_user",
    "create_engine",
    "get_engine",
    "get_session",
    "get_sessionmaker",
]
