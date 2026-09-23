"""Integration tests for ``DELETE /account`` against a real PostgreSQL.

These tests need a real database (see ``docker-compose.yml`` at the
repository root). The WHOLE module is skipped when ``DATABASE_URL`` is not
set, with the same disposable-database guard as
``test_conversations_integration.py`` (the ``migrated_db`` fixture drops the
``public`` and ``extensions`` schemas, so point ``DATABASE_URL`` at a
throwaway database only).

What this proves beyond the unit tests: the ``ON DELETE CASCADE`` FKs the
endpoint RELIES on (``profiles.id``, ``conversations.user_id``,
``messages.user_id`` — P2 initial schema) actually remove the profile, the
conversations and the messages when the ``users`` row is deleted. Every
assertion after the deletion is a FRESH read against the database, not a
leftover object from the request. Deleting an already-deleted account is
the decided ``404`` — never a ``500`` — and also clears the cookie.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from cycloai.api.app import create_app
from cycloai.api.deps import AUTH_COOKIE_NAME, get_current_athlete, get_session
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


async def _count(engine, sql: str, params: dict) -> int:
    """Run one fresh scalar count query on its own connection."""
    async with engine.begin() as conn:
        result = await conn.execute(text(sql), params)
        return int(result.scalar_one())


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


async def _counts(engine, user_id: uuid.UUID) -> dict[str, int]:
    """Fresh counts of the four row kinds the cascade must remove."""
    return {
        "users": await _count(
            engine, "select count(*) from users where id = :u", {"u": user_id}
        ),
        "profiles": await _count(
            engine, "select count(*) from profiles where id = :u", {"u": user_id}
        ),
        "conversations": await _count(
            engine,
            "select count(*) from conversations where user_id = :u",
            {"u": user_id},
        ),
        "messages": await _count(
            engine,
            "select count(*) from messages where user_id = :u",
            {"u": user_id},
        ),
    }


@pytest_asyncio.fixture(loop_scope="module")
async def athlete(migrated_db):
    """One fresh user in a freshly migrated schema (profile via the trigger)."""
    engine = migrated_db["engine"]
    suffix = uuid.uuid4().hex[:12]
    user_id = await _create_user(engine, f"delete-me-{suffix}@example.com")
    return {"engine": engine, "user_id": user_id}


async def test_delete_account_cascades_all_owned_rows(athlete):
    engine, user_id = athlete["engine"], athlete["user_id"]

    client = _client_for(engine, user_id)
    async with client as c:
        # Build real data through the REAL endpoints first.
        created = await c.post("/conversations", json={"title": "FTP blocks"})
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]

        first = await c.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "user", "content": "hello coach"},
        )
        assert first.status_code == 201, first.text
        second = await c.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "assistant", "content": "hello athlete"},
        )
        assert second.status_code == 201, second.text

        # Fresh reads BEFORE deletion: everything the cascade must remove
        # actually exists — the trigger made the profile, the endpoints
        # made the conversation and the messages.
        before = await _counts(engine, user_id)
        assert before == {
            "users": 1,
            "profiles": 1,
            "conversations": 1,
            "messages": 2,
        }, before

        # Delete the caller's own account.
        response = await c.delete("/account")
        assert response.status_code == 200, response.text
        assert response.json() == {"detail": "Account deleted."}
        cookies = response.headers.get_list("set-cookie")
        assert cookies, "the deletion response must send a clearing Set-Cookie"
        assert AUTH_COOKIE_NAME in cookies[0]

    # Fresh reads AFTER deletion: ALL FOUR row kinds are gone — this is the
    # proof that the schema's ON DELETE CASCADE did the work, not assumption.
    after = await _counts(engine, user_id)
    assert after == {
        "users": 0,
        "profiles": 0,
        "conversations": 0,
        "messages": 0,
    }, after


async def test_deleting_an_already_deleted_account_is_404_never_500(athlete):
    engine, user_id = athlete["engine"], athlete["user_id"]

    client = _client_for(engine, user_id)
    async with client as c:
        first = await c.delete("/account")
        assert first.status_code == 200, first.text

        again = await c.delete("/account")
        assert again.status_code == 404, again.text
        assert again.json() == {"detail": "Account not found."}
        cookies = again.headers.get_list("set-cookie")
        assert cookies, "the 404 must ALSO clear the stale session cookie"
        assert AUTH_COOKIE_NAME in cookies[0]
