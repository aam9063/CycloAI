"""Integration tests for the profile/onboarding persistence API.

These tests need a real PostgreSQL (see ``docker-compose.yml`` at the
repository root). The WHOLE module is skipped when ``DATABASE_URL`` is not
set, with the same disposable-database guard as ``test_db_integration.py``
(the ``migrated_db`` fixture drops the ``public`` and ``extensions``
schemas, so point ``DATABASE_URL`` at a throwaway database only).

Unlike every other API test module, these tests deliberately do NOT
override ``get_session``: they go through the REAL session dependency and
the REAL database, because the defect they guard against is invisible
otherwise. A request whose transaction is never committed still returns
``200`` with correct-looking bodies — every assertion the route can make
about its own ORM objects passes while NOTHING reaches storage. The
assertions therefore read back through a SEPARATE connection in a fresh
transaction, so they cannot be satisfied by the same transaction that
wrote the row.

What this proves beyond the unit tests: ``PATCH /profile`` and
``POST /onboarding/complete`` actually PERSIST (``training_system``,
``lthr_bpm``, ``ftp_estimated``, ``onboarding_completed`` — exactly the
values the generator needs to derive an absolute target), and a request
that mutates and then fails leaves no partial write behind.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

import cycloai.db.engine as engine_module
from cycloai.api.app import create_app
from cycloai.api.deps import get_current_athlete
from cycloai.api.routes_profile import get_profile_repository
from cycloai.db.repositories import ProfileRepository
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


async def _read_user_email(engine, user_id: uuid.UUID) -> str | None:
    """Read the account email in a FRESH transaction on a SEPARATE connection.

    Same anti-tautology rule as the profile row read: the expected value is
    taken from storage, never from the response being asserted.
    """
    async with engine.connect() as conn:
        row = await conn.execute(
            text("select email from users where id = :id"), {"id": user_id}
        )
    return row.scalar_one_or_none()


async def _read_profile_row(engine, user_id: uuid.UUID) -> dict:
    """Read the raw profile row in a FRESH transaction on a SEPARATE connection.

    This is the anti-tautology detail: the assertion cannot be satisfied by
    the same session (or even the same transaction) that performed the
    write, so a route that never commits fails here no matter what its
    response body says.
    """
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "select display_name, weekly_hours, training_system, lthr_bpm, "
                    "ftp_estimated, onboarding_completed "
                    "from profiles where id = :id"
                ),
                {"id": user_id},
            )
        ).mappings().one()
    return dict(row)


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _real_session_environment():
    """Point the app's REAL ``get_session`` at the migrated disposable DB.

    The engine/sessionmaker are process-wide lazily-created globals; reset
    them so the first request builds an engine from ``DATABASE_URL`` (the
    migrated database), not from whatever ambient settings a previous test
    left behind. The env var is set explicitly so ``backend/.env`` cannot
    silently redirect the app at a different database.
    """
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = DATABASE_URL
    previous_engine = engine_module._engine
    previous_sessionmaker = engine_module._sessionmaker
    engine_module._engine = None
    engine_module._sessionmaker = None
    yield
    app_engine = engine_module._engine
    engine_module._engine = previous_engine
    engine_module._sessionmaker = previous_sessionmaker
    os.environ["DATABASE_URL"] = previous_url
    if app_engine is not None:
        await app_engine.dispose()


def _real_client_for(user_id: uuid.UUID) -> httpx.AsyncClient:
    """An API client authenticated as ``user_id`` using the REAL session dep."""

    def build() -> httpx.AsyncClient:
        app = create_app()
        app.dependency_overrides[get_current_athlete] = lambda: user_id
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return build()


def _failing_client_for(user_id: uuid.UUID) -> httpx.AsyncClient:
    """Like :func:`_real_client_for`, but the profile repository raises AFTER
    the real write, to exercise the rollback half of the request boundary."""

    def build() -> httpx.AsyncClient:
        app = create_app()
        app.dependency_overrides[get_current_athlete] = lambda: user_id
        real_repo = ProfileRepository()

        class _ExplodingAfterWrite:
            async def update_profile(self, session, caller_id, **updates):
                await real_repo.update_profile(session, caller_id, **updates)
                raise RuntimeError("simulated failure after the write")

        app.dependency_overrides[get_profile_repository] = _ExplodingAfterWrite
        # Deliver the 500 instead of propagating the exception into the test.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return build()


@pytest_asyncio.fixture(loop_scope="module")
async def profile_user(migrated_db):
    """One fresh user in a freshly migrated schema."""
    engine = migrated_db["engine"]
    user = await _create_user(engine, f"profile-{uuid.uuid4().hex[:12]}@example.com")
    return {"engine": engine, "user": user}


async def test_profile_response_returns_the_registered_email(profile_user):
    """The email in the response is the one the user registered with.

    The expected value is read back from ``users`` in a fresh transaction on
    a separate connection, so the assertion cannot be satisfied by the
    response itself. Both endpoints must return it so the response shape
    stays consistent for the profile page.
    """
    engine, user = profile_user["engine"], profile_user["user"]
    stored_email = await _read_user_email(engine, user)
    assert stored_email  # the fixture registered a real user with an email

    async with _real_client_for(user) as client:
        read = await client.get("/profile")
        assert read.status_code == 200
        updated = await client.patch("/profile", json={"display_name": "Email Check"})
        assert updated.status_code == 200

    assert read.json()["email"] == stored_email
    assert updated.json()["email"] == stored_email


async def test_patch_profile_persists_in_a_fresh_session(profile_user):
    engine, user = profile_user["engine"], profile_user["user"]

    async with _real_client_for(user) as client:
        response = await client.patch(
            "/profile",
            json={"display_name": "Persisted Athlete", "weekly_hours": 7.5},
        )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Persisted Athlete"

    # The response above is the route's own ORM object and proves nothing:
    # the value must still be there for a reader in a brand-new transaction.
    stored = await _read_profile_row(engine, user)
    assert stored["display_name"] == "Persisted Athlete"
    assert stored["weekly_hours"] == 7.5


async def test_onboarding_complete_sets_flag_in_the_database(profile_user):
    engine, user = profile_user["engine"], profile_user["user"]

    async with _real_client_for(user) as client:
        declared = await client.patch(
            "/profile",
            json={"training_system": "heart_rate", "lthr_bpm": 170},
        )
        assert declared.status_code == 200
        completed = await client.post("/onboarding/complete")
    assert completed.status_code == 200
    assert completed.json()["onboarding_completed"] is True

    stored = await _read_profile_row(engine, user)
    assert stored["onboarding_completed"] is True


async def test_threshold_fields_survive_the_round_trip(profile_user):
    engine, user = profile_user["engine"], profile_user["user"]

    async with _real_client_for(user) as client:
        declared = await client.patch(
            "/profile",
            json={"training_system": "power", "ftp_estimated": 250},
        )
        assert declared.status_code == 200
        completed = await client.post("/onboarding/complete")
    assert completed.status_code == 200

    stored = await _read_profile_row(engine, user)
    assert stored["training_system"] == "power"
    assert stored["ftp_estimated"] == 250
    assert stored["onboarding_completed"] is True


async def test_failed_request_after_a_write_leaves_no_partial_write(profile_user):
    engine, user = profile_user["engine"], profile_user["user"]

    async with _failing_client_for(user) as client:
        response = await client.patch(
            "/profile",
            json={"display_name": "Must Not Persist"},
        )
    assert response.status_code == 500

    # The write happened, then the request failed: the request boundary must
    # roll the whole thing back, leaving the trigger-created row untouched.
    stored = await _read_profile_row(engine, user)
    assert stored["display_name"] is None
    assert stored["onboarding_completed"] is False
