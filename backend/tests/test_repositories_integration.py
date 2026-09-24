"""Cross-user isolation tests for the repository layer (SKIPPED without a DB).

These tests prove the real security property of ``cycloai.db.repositories``:
with Row Level Security gone from the schema, the repository layer is the
only thing standing between two users' data. They need a real PostgreSQL
with pgvector (see ``docker-compose.yml`` at the repository root). The whole
module is skipped when ``DATABASE_URL`` is not set, so a plain ``uv run
pytest`` never requires Docker.

Same conventions as ``test_db_integration.py``: the ``migrated_db`` fixture
resets the target database to a clean state (drops and recreates the
``public`` and ``extensions`` schemas) so the initial Alembic revision is
proven to apply from scratch on every run. The fail-closed disposable-
database guard refuses to run against anything that does not look
disposable — point ``DATABASE_URL`` at a throwaway database only.

Caller binding: every session used through the repositories is bound first
(``bind_session_user`` for one caller, ``bind_internal_session`` for setup
acting across users). Since the caller guard fails closed, an unbound session
raises ``UnboundSessionError`` instead of quietly skipping the ownership
check — the last test pins that property against a real database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import alembic.command
import alembic.config
import alembic.script
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from cycloai.db.models import Profile
from cycloai.db.repositories import (
    ConversationRepository,
    MessageRepository,
    ProfileRepository,
    UnboundSessionError,
    bind_internal_session,
    bind_session_user,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("DATABASE_URL")


def _assert_disposable_database(url: str) -> None:
    """Refuse destructive tests against a database that is not disposable.

    Same guard as ``test_db_integration.py``: the ``migrated_db`` fixture
    drops the ``public`` and ``extensions`` schemas outright, so this fails
    closed at import time unless the target name contains ``test`` or
    ``dev``, or ``CYCLOAI_DESTRUCTIVE_DB_TESTS=1`` is set explicitly.
    """
    name = urlparse(url).path.lstrip("/").lower()
    if "test" in name or "dev" in name:
        return
    if os.environ.get("CYCLOAI_DESTRUCTIVE_DB_TESTS") == "1":
        return
    raise RuntimeError(
        f"Refusing to run destructive database tests against {name or 'an unnamed'} database: "
        "the migrated_db fixture drops the public and extensions schemas. Point DATABASE_URL "
        "at a disposable database whose name contains 'test' or 'dev', or set "
        "CYCLOAI_DESTRUCTIVE_DB_TESTS=1 if you are certain this target is throwaway."
    )


if DATABASE_URL is not None:
    _assert_disposable_database(DATABASE_URL)

pytestmark = [
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="DATABASE_URL not set: database integration tests need a running PostgreSQL",
    ),
    # One event loop per module: the module-scoped engine must not be shared
    # across per-test loops (asyncpg connections are loop-bound).
    pytest.mark.asyncio(loop_scope="module"),
]


def _alembic_config() -> alembic.config.Config:
    cfg = alembic.config.Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def migrated_db():
    """Reset the database and apply the migration from scratch."""
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("drop schema if exists public cascade"))
        await conn.execute(text("create schema public"))
        await conn.execute(text("drop schema if exists extensions cascade"))
    await engine.dispose()

    cfg = _alembic_config()
    # Alembic's env.py calls asyncio.run(), which would fail inside this
    # already-running pytest event loop; run it in a worker thread instead.
    await asyncio.to_thread(alembic.command.upgrade, cfg, "head")

    engine = create_async_engine(DATABASE_URL)
    yield {"engine": engine}
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
def engine(migrated_db) -> AsyncEngine:
    return migrated_db["engine"]


@pytest_asyncio.fixture(loop_scope="module", scope="module")
def sessionmaker(engine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_user(engine: AsyncEngine, email: str) -> uuid.UUID:
    """Insert a user directly (auth work lands in P5); trigger makes the profile."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                insert into users (email, password_hash, display_name)
                values (:email, 'hash', :display_name)
                returning id
                """
            ),
            {"email": email, "display_name": email.split("@")[0]},
        )
        return result.scalar_one()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def two_users(engine) -> dict[str, uuid.UUID]:
    """Two users; the ``handle_new_user`` trigger has created a profile each."""
    user_a = await _create_user(engine, "alice@example.com")
    user_b = await _create_user(engine, "bob@example.com")
    return {"a": user_a, "b": user_b}


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def conversations(sessionmaker, two_users) -> dict[str, uuid.UUID]:
    """Alice owns a conversation with two messages; Bob owns his own (empty)."""
    async with sessionmaker() as session:
        # Setup acts for BOTH users in one session: the internal binding is
        # the deliberate escape hatch (and asserts it exists for real code).
        bind_internal_session(session)
        alice_conv = await ConversationRepository().create_conversation(
            session, two_users["a"], title="Training plan"
        )
        assert alice_conv is not None
        repo = MessageRepository()
        # Each chat turn is its own transaction in real usage, which also
        # gives each message a distinct now() (transaction-start timestamp).
        first = await repo.append_message(
            session, two_users["a"], alice_conv.id, role="user", content="Hola"
        )
        assert first is not None
        await session.commit()
        second = await repo.append_message(
            session, two_users["a"], alice_conv.id, role="assistant", content="Buenas!"
        )
        assert second is not None
        await session.commit()
        bob_conv = await ConversationRepository().create_conversation(
            session, two_users["b"], title="Bob's thread"
        )
        assert bob_conv is not None
        await session.commit()
    return {"a": alice_conv.id, "b": bob_conv.id}


async def _profile_row(session, user_id: uuid.UUID) -> dict:
    """Every column of a profile row, for byte-identical comparisons."""
    result = await session.execute(select(Profile).where(Profile.id == user_id))
    profile = result.scalar_one()
    return {
        column.key: getattr(profile, column.key)
        for column in Profile.__table__.columns
    }


async def test_trigger_created_a_profile_for_each_user(sessionmaker, two_users):
    async with sessionmaker() as session:
        # This fixture-level setup acts across users (auth work lands in P5,
        # so there is no single caller here); the internal binding is the
        # explicit, greppable escape hatch for exactly that.
        bind_internal_session(session)
        repo = ProfileRepository()
        for user_id in two_users.values():
            profile = await repo.get_profile(session, user_id)
            assert profile is not None, f"missing profile for {user_id}"
            assert profile.display_name is not None
            assert profile.onboarding_completed is False


async def test_unbound_session_cannot_reach_user_data_at_all(
    sessionmaker, two_users, conversations
):
    """The guard fails closed: no binding, no access — loudly.

    A forgotten ``bind_session_user`` used to silently disable the ownership
    check; now every repository call on an unbound session raises
    ``UnboundSessionError`` before any query runs, so nothing can be read or
    written, and nothing is left behind either.
    """
    async with sessionmaker() as session:
        # Deliberately NOT bound: not to Alice, not to Bob, not internal.
        conv_repo = ConversationRepository()
        msg_repo = MessageRepository()
        profile_repo = ProfileRepository()

        with pytest.raises(UnboundSessionError):
            await profile_repo.get_profile(session, two_users["a"])
        with pytest.raises(UnboundSessionError):
            await profile_repo.update_profile(
                session, two_users["a"], display_name="hijacked"
            )
        with pytest.raises(UnboundSessionError):
            await conv_repo.get_conversation(session, two_users["a"], conversations["a"])
        with pytest.raises(UnboundSessionError):
            await conv_repo.list_conversations(session, two_users["a"])
        with pytest.raises(UnboundSessionError):
            await conv_repo.update_conversation(
                session, two_users["a"], conversations["a"], title="hijacked"
            )
        with pytest.raises(UnboundSessionError):
            await conv_repo.create_conversation(session, two_users["a"])
        with pytest.raises(UnboundSessionError):
            await msg_repo.list_messages(session, two_users["a"], conversations["a"])
        with pytest.raises(UnboundSessionError):
            await msg_repo.append_message(
                session, two_users["a"], conversations["a"], role="user", content="x"
            )
        # The session never even reached the database for user data.
        await session.rollback()

    async with sessionmaker() as session:
        # And nothing changed: Alice's thread is intact.
        count = (
            await session.execute(
                text("select count(*) from conversations where user_id = :id"),
                {"id": two_users["a"]},
            )
        ).scalar_one()
        assert count == 1


async def test_user_b_cannot_fetch_list_or_update_user_a_conversation(
    sessionmaker, two_users, conversations
):
    async with sessionmaker() as session:
        bind_session_user(session, two_users["b"])
        conv_repo = ConversationRepository()

        # Fetch: somebody else's conversation and a non-existent one must be
        # indistinguishable — both None.
        missing_id = uuid.uuid4()
        assert (
            await conv_repo.get_conversation(session, two_users["b"], conversations["a"])
            is None
        )
        assert (
            await conv_repo.get_conversation(session, two_users["b"], missing_id) is None
        )

        # List: Alice's conversation must be structurally absent from Bob's list.
        bob_conversations = await conv_repo.list_conversations(session, two_users["b"])
        assert [c.id for c in bob_conversations] == [conversations["b"]]

        # Update: refused, and the refusal must not have written anything —
        # commit whatever happened, then verify in a fresh session.
        before = await conv_repo.get_conversation(
            session, two_users["b"], conversations["b"]
        )
        result = await conv_repo.update_conversation(
            session, two_users["b"], conversations["a"], title="hijacked"
        )
        assert result is None
        await session.commit()

    async with sessionmaker() as session:
        row = (
            await session.execute(
                text("select title from conversations where id = :id"),
                {"id": conversations["a"]},
            )
        ).scalar_one()
        assert row == "Training plan", "Bob's update attempt changed Alice's row"
        # And Bob's own conversation is untouched by the failed attack.
        assert before is not None and before.title == "Bob's thread"


async def test_user_b_cannot_append_to_or_read_user_a_messages(
    sessionmaker, two_users, conversations
):
    async with sessionmaker() as session:
        bind_session_user(session, two_users["b"])
        repo = MessageRepository()

        # Append: refused, indistinguishable from a non-existent conversation.
        assert (
            await repo.append_message(
                session, two_users["b"], conversations["a"], role="user", content="intrusion"
            )
            is None
        )
        assert (
            await repo.append_message(
                session, two_users["b"], uuid.uuid4(), role="user", content="intrusion"
            )
            is None
        )

        # Read: both cases collapse to None.
        assert (
            await repo.list_messages(session, two_users["b"], conversations["a"]) is None
        )
        assert await repo.list_messages(session, two_users["b"], uuid.uuid4()) is None
        await session.commit()

    async with sessionmaker() as session:
        count = (
            await session.execute(
                text("select count(*) from messages where conversation_id = :id"),
                {"id": conversations["a"]},
            )
        ).scalar_one()
        assert count == 2, "Bob's append attempt wrote a message into Alice's thread"


async def test_user_b_update_to_user_a_profile_changes_nothing(
    sessionmaker, two_users
):
    async with sessionmaker() as session:
        before = await _profile_row(session, two_users["a"])
        bind_session_user(session, two_users["b"])
        result = await ProfileRepository().update_profile(
            session, two_users["a"], display_name="hijacked", objective="race"
        )
        assert result is None
        await session.commit()

    async with sessionmaker() as session:
        after = await _profile_row(session, two_users["a"])
        assert after == before, (
            "Bob's update attempt changed Alice's profile row "
            f"(differences: {[(k, before[k], after[k]) for k in before if before[k] != after[k]]})"
        )


async def test_missing_and_foreign_ids_are_indistinguishable(
    sessionmaker, two_users, conversations
):
    """No accessor may confirm that a foreign id exists.

    Bob asks for a conversation id that does not exist and for Alice's real
    one: the observable result must be identical (``None`` / ``None``), for
    reads, updates, message listings and appends alike.
    """
    missing_id = uuid.uuid4()
    async with sessionmaker() as session:
        bind_session_user(session, two_users["b"])
        conv_repo = ConversationRepository()
        msg_repo = MessageRepository()
        profile_repo = ProfileRepository()

        assert (
            await conv_repo.get_conversation(session, two_users["b"], missing_id) is None
        )
        assert (
            await conv_repo.get_conversation(session, two_users["b"], conversations["a"])
            is None
        )
        assert (
            await conv_repo.update_conversation(
                session, two_users["b"], missing_id, title="x"
            )
            is None
        )
        assert (
            await conv_repo.update_conversation(
                session, two_users["b"], conversations["a"], title="x"
            )
            is None
        )
        assert await msg_repo.list_messages(session, two_users["b"], missing_id) is None
        assert (
            await msg_repo.list_messages(session, two_users["b"], conversations["a"])
            is None
        )
        assert (
            await msg_repo.append_message(
                session, two_users["b"], missing_id, role="user", content="x"
            )
            is None
        )
        assert (
            await msg_repo.append_message(
                session, two_users["b"], conversations["a"], role="user", content="x"
            )
            is None
        )
        # Profiles: a non-existent user id and Alice's id look the same to Bob.
        assert await profile_repo.get_profile(session, missing_id) is None
        assert await profile_repo.get_profile(session, two_users["a"]) is None


async def test_user_a_retains_full_access_to_own_data(
    sessionmaker, two_users, conversations
):
    """Isolation must not be implemented by breaking legitimate access."""
    async with sessionmaker() as session:
        bind_session_user(session, two_users["a"])
        conv_repo = ConversationRepository()
        msg_repo = MessageRepository()
        profile_repo = ProfileRepository()

        # Profile: read and update own row.
        profile = await profile_repo.get_profile(session, two_users["a"])
        assert profile is not None
        updated = await profile_repo.update_profile(
            session, two_users["a"], objective="gravel race"
        )
        assert updated is not None and updated.objective == "gravel race"

        # Conversations: get, list and update own thread (title + updated_at).
        own = await conv_repo.get_conversation(session, two_users["a"], conversations["a"])
        assert own is not None and own.title == "Training plan"
        old_updated_at = own.updated_at
        listed = await conv_repo.list_conversations(session, two_users["a"])
        assert [c.id for c in listed] == [conversations["a"]]
        renamed = await conv_repo.update_conversation(
            session, two_users["a"], conversations["a"], title="Nuevo plan"
        )
        assert renamed is not None and renamed.title == "Nuevo plan"
        # own and renamed are the same identity-mapped row; the captured value
        # proves the update actually bumped updated_at server-side.
        assert renamed.updated_at is not None and renamed.updated_at > old_updated_at

        # Messages: read own thread in order and append to it.
        messages = await msg_repo.list_messages(session, two_users["a"], conversations["a"])
        assert messages is not None
        assert [m.content for m in messages] == ["Hola", "Buenas!"]
        appended = await msg_repo.append_message(
            session, two_users["a"], conversations["a"], role="user", content="Gracias"
        )
        assert appended is not None
        messages_after = await msg_repo.list_messages(
            session, two_users["a"], conversations["a"]
        )
        assert messages_after is not None
        assert [m.content for m in messages_after] == ["Hola", "Buenas!", "Gracias"]
        await session.commit()
