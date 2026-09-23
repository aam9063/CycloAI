"""Integration tests for the conversation/message persistence API.

These tests need a real PostgreSQL (see ``docker-compose.yml`` at the
repository root). The WHOLE module is skipped when ``DATABASE_URL`` is not
set, with the same disposable-database guard as ``test_db_integration.py``
(the ``migrated_db`` fixture drops the ``public`` and ``extensions``
schemas, so point ``DATABASE_URL`` at a throwaway database only).

What this proves beyond the unit tests: against the REAL schema and the
REAL repositories, one athlete's conversation is invisible to another —
not readable, absent from the list, its messages unreadable, and appending
to it writes nothing — while the owner's own ``updated_at`` moves forward
when a message is appended.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from cycloai.api.app import create_app
from cycloai.api.deps import get_current_athlete, get_session
from test_db_integration import DATABASE_URL
from test_db_integration import migrated_db as _migrated_db_fixture

# Re-expose the shared ``migrated_db`` fixture under its canonical name so
# tests can request it, without shadowing it inside a signature.
migrated_db = _migrated_db_fixture

pytestmark = [
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="DATABASE_URL not set: database integration tests need a running PostgreSQL",
    ),
    # The module-scoped engine's asyncpg connections are loop-bound, so the
    # whole module shares one event loop (same contract as test_db_integration).
    pytest.mark.asyncio(loop_scope="module"),
]


async def _create_user(engine, email: str) -> uuid.UUID:
    """Insert a user row directly; the handle_new_user trigger makes the profile."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "insert into users (email, password_hash) "
                "values (:email, 'not-a-real-hash') returning id"
            ),
            {"email": email},
        )
        return uuid.UUID(str(result.scalar_one()))


def _client_for(engine, user_id: uuid.UUID) -> httpx.AsyncClient:
    """An API client authenticated as ``user_id`` against the real database."""

    def build() -> httpx.AsyncClient:
        app = create_app()
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async def _session():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_current_athlete] = lambda: user_id
        app.dependency_overrides[get_session] = _session
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return build()


@pytest_asyncio.fixture(loop_scope="module")
async def two_users(migrated_db):
    """Two fresh users in a freshly migrated schema."""
    engine = migrated_db["engine"]
    suffix = uuid.uuid4().hex[:12]
    owner = await _create_user(engine, f"owner-{suffix}@example.com")
    outsider = await _create_user(engine, f"outsider-{suffix}@example.com")
    return {"engine": engine, "owner": owner, "outsider": outsider}


async def test_conversation_is_invisible_to_another_user(two_users):
    engine, owner, outsider = (
        two_users["engine"],
        two_users["owner"],
        two_users["outsider"],
    )

    owner_client = _client_for(engine, owner)
    async with owner_client as oc:
        created = await oc.post("/conversations", json={"title": "FTP blocks"})
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        first = await oc.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "user", "content": "hello coach"},
        )
        assert first.status_code == 201
        second = await oc.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "assistant", "content": "hello athlete"},
        )
        assert second.status_code == 201

        # The owner sees their own data, oldest first.
        own_messages = await oc.get(f"/conversations/{conversation_id}/messages")
        assert own_messages.status_code == 200
        assert [m["content"] for m in own_messages.json()] == [
            "hello coach",
            "hello athlete",
        ]

        outsider_client = _client_for(engine, outsider)
        async with outsider_client as xc:
            # Cannot read the conversation: 404, the same body a nonexistent
            # id would produce.
            foreign_read = await xc.get(f"/conversations/{conversation_id}")
            nonexistent = uuid.uuid4()
            missing_read = await xc.get(f"/conversations/{nonexistent}")
            assert foreign_read.status_code == missing_read.status_code == 404
            assert foreign_read.json() == missing_read.json()

            # The list does not contain another user's conversation.
            listing = await xc.get("/conversations")
            assert listing.status_code == 200
            assert listing.json() == []

            # Its messages are unreadable, identically to a nonexistent one.
            foreign_messages = await xc.get(
                f"/conversations/{conversation_id}/messages"
            )
            missing_messages = await xc.get(f"/conversations/{nonexistent}/messages")
            assert foreign_messages.status_code == missing_messages.status_code == 404
            assert foreign_messages.json() == missing_messages.json()

            # Appending to it is refused, and nothing is written.
            intrusions = [
                await xc.post(
                    f"/conversations/{conversation_id}/messages",
                    json={"role": "user", "content": "intrusion"},
                ),
                await xc.post(
                    f"/conversations/{nonexistent}/messages",
                    json={"role": "user", "content": "intrusion"},
                ),
            ]
            for response in intrusions:
                assert response.status_code == 404
                assert response.json() == foreign_read.json()

    # Nothing was stored for the outsider's attempts: the message list is
    # exactly the two messages the owner appended.
    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text(
                    "select count(*) from messages where conversation_id = :cid"
                ),
                {"cid": conversation_id},
            )
        ).scalar_one()
    assert count == 2


async def test_updated_at_moves_when_a_message_is_appended(two_users):
    engine, owner = two_users["engine"], two_users["owner"]

    async with _client_for(engine, owner) as oc:
        created = await oc.post("/conversations", json={"title": "Recovery week"})
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        before = (await oc.get(f"/conversations/{conversation_id}")).json()
        # The default now() has microsecond resolution; give the next
        # transaction its own timestamp.
        await asyncio.sleep(0.05)
        appended = await oc.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "user", "content": "how did my FTP test go?"},
        )
        assert appended.status_code == 201
        after = (await oc.get(f"/conversations/{conversation_id}")).json()

        assert after["updated_at"] > before["updated_at"]
