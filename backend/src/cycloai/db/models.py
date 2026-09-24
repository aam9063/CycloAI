"""SQLAlchemy 2.0 declarative models for the P2 CycloAI schema.

Authoritative source of truth: ``backend/alembic/versions/1a2b3c4d5e6f_p2_initial_schema.py``.
The models below mirror that migration column by column (types, nullability,
defaults, checks). Schema *changes* are made in Alembic migrations first and
then reflected here; these models are never used to create tables
(``Base.metadata.create_all`` is not part of the workflow, and Alembic's
``env.py`` keeps ``target_metadata = None`` so autogenerate stays disabled).

Two columns need custom types because they come from the ``extensions``
schema / server-side generation and no third-party driver library is
installed:

- ``knowledge_embeddings.embedding`` uses pgvector's ``vector`` type,
  relocated to the ``extensions`` schema by revision 007. Modelled as a
  :class:`Vector` user-defined type whose col spec is schema-qualified.
- ``knowledge_embeddings.fts`` is a ``tsvector generated always as
  to_tsvector('spanish', content) stored`` column. Modelled as
  :class:`TSVector` with a ``Computed`` marker so SQLAlchemy excludes it
  from INSERT/UPDATE statements (the server owns the value).

Importing this module performs no I/O and requires no database: everything
is plain declarative metadata built at import time.

Note on ``metadata``: the ``messages.metadata`` and
``knowledge_embeddings.metadata`` JSONB columns clash with SQLAlchemy's
reserved ``DeclarativeBase.metadata`` attribute name, so the mapped
attributes are named ``metadata_`` while mapping to the real column name
``metadata`` in the database.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType


class Base(DeclarativeBase):
    """Shared declarative base for all CycloAI ORM models."""


class Vector(UserDefinedType):
    """pgvector's ``vector`` column type, schema-qualified into ``extensions``.

    The extension is relocated out of ``public`` by the migration (006 + 007),
    so the col spec must be fully qualified: ``extensions.vector(N)``.
    ``cache_ok`` is safe: the only state is the immutable dimension.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: Any) -> str:
        return f"extensions.vector({self.dim})"


class TSVector(UserDefinedType):
    """PostgreSQL ``tsvector`` column type (no third-party driver installed)."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "tsvector"


class User(Base):
    """``users`` — first-party replacement for Supabase's ``auth.users``."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Profile(Base):
    """``profiles`` — one row per user, created by the ``handle_new_user`` trigger."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "training_system in ('power', 'heart_rate')",
            name="profiles_training_system_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    strava_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    strava_connected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    strava_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_hours: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    gym_days_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injuries: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_power_meter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    target_event: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    training_system: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'heart_rate'")
    )
    lthr_bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ftp_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctl: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    atl: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    tsb: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    weekly_volume_km: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    weekly_volume_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    avg_days_per_week: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    """``conversations`` — chat threads, strictly owned by one user."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Message(Base):
    """``messages`` — chat turns, denormalised with their owner's ``user_id``."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="messages_role_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # ``metadata`` is reserved by DeclarativeBase, hence the trailing underscore.
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)


class KnowledgeEmbedding(Base):
    """``knowledge_embeddings`` — shared RAG content (no per-user ownership).

    ``fts`` is generated by the server; SQLAlchemy's ``Computed`` marker keeps
    it read-only (excluded from INSERT/UPDATE) while still mapping the column
    for SELECTs.
    """

    __tablename__ = "knowledge_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(768), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    fts: Mapped[Any] = mapped_column(
        TSVector,
        Computed("to_tsvector('spanish', content)", persisted=True),
        nullable=False,
    )
    # The migration declares ``created_at timestamptz default now()`` with no
    # NOT NULL: mirrored exactly, so it stays nullable here too.
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )


class Waitlist(Base):
    """``waitlist`` — insert-only landing-page signups (no per-user ownership)."""

    __tablename__ = "waitlist"
    __table_args__ = (
        CheckConstraint(
            "char_length(email) between 3 and 320 "
            "and position('@' in email) > 1 "
            "and position('.' in split_part(email, '@', 2)) > 0 "
            "and (source is null or char_length(source) <= 50)",
            name="waitlist_email_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mirrors the migration exactly: nullable with a default.
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )


# --- Index fidelity -----------------------------------------------------------
#
# Plain indexes are mirrored here so the ORM metadata stays an honest picture
# of the schema. The pgvector-specific HNSW / GIN indexes are deliberately
# NOT modelled: rendering their opclasses and access methods through the ORM
# risks generating subtly wrong DDL, and Alembic owns all schema creation.
# They live (correctly) in the 1a2b3c4d5e6f migration only.

Index("users_email_unique", func.lower(User.__table__.c.email), unique=True)
Index(
    "conversations_user_updated",
    Conversation.__table__.c.user_id,
    Conversation.__table__.c.updated_at.desc(),
)
Index("messages_conversation", Message.__table__.c.conversation_id, Message.__table__.c.created_at)
Index("waitlist_email_unique", func.lower(Waitlist.__table__.c.email), unique=True)
