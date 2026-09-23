"""Integration tests for the authentication service (register + authenticate).

These tests need a real PostgreSQL with pgvector (same requirements as
``test_db_integration.py``). The WHOLE module is skipped when ``DATABASE_URL``
is not set, so a plain ``uv run pytest`` never requires Docker. The same
disposable-database guard is enforced: the module fixture resets the target
database and re-applies the Alembic head, so point ``DATABASE_URL`` at a
disposable development database only.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import alembic.command
import alembic.config
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from cycloai.auth.security import PasswordValidationError
from cycloai.auth.service import (
    EmailAlreadyRegisteredError,
    UserIdentity,
    authenticate_user,
    register_user,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("DATABASE_URL")


def _assert_disposable_database(url: str) -> None:
    """Refuse to run destructive tests against a database that is not disposable.

    Mirrors the guard in ``test_db_integration.py``: this module's fixture drops
    the ``public`` and ``extensions`` schemas, so only a throwaway database
    (name containing ``test`` or ``dev``) or an explicit
    ``CYCLOAI_DESTRUCTIVE_DB_TESTS=1`` opt-in is accepted.
    """
    name = urlparse(url).path.lstrip("/").lower()
    if "test" in name or "dev" in name:
        return
    if os.environ.get("CYCLOAI_DESTRUCTIVE_DB_TESTS") == "1":
        return
    raise RuntimeError(
        f"Refusing to run destructive database tests against {name or 'an unnamed'} database: "
        "the auth fixture drops the public and extensions schemas. Point DATABASE_URL "
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
    """Reset the database and apply the migration from scratch.

    Same convention as ``test_db_integration.py`` so this module proves the
    auth service against a from-scratch schema on every run.
    """
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
def engine(migrated_db):
    return migrated_db["engine"]


@pytest_asyncio.fixture(loop_scope="module")
async def session_factory(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="module")
async def cleanup_users(engine):
    """Track emails created by a test and delete the users afterwards.

    ``profiles`` rows go with them via the ``on delete cascade`` FK.
    """
    created: list[str] = []
    yield created
    if created:
        async with engine.begin() as conn:
            await conn.execute(
                text("delete from users where lower(email) = any(:emails)"),
                {"emails": created},
            )


def _track(cleanup_users, *emails: str) -> None:
    cleanup_users.extend(e.lower() for e in emails)


async def test_register_user_creates_user_and_trigger_creates_profile(
    session_factory, cleanup_users
):
    email = "register-trigger@example.com"
    password = "correct horse battery staple"
    _track(cleanup_users, email)
    async with session_factory() as session:
        identity = await register_user(session, email=email, password=password)
        await session.commit()

    assert isinstance(identity, UserIdentity)
    assert identity.email == email.lower()

    async with session_factory() as session:
        user = (
            await session.execute(
                text(
                    "select id, email, password_hash from users "
                    "where lower(email) = :email"
                ),
                {"email": email},
            )
        ).mappings().one()
        # The service stored a hash, never the plaintext.
        assert user["password_hash"] != password
        assert user["password_hash"].startswith("$argon2")
        assert str(identity.id) == str(user["id"])

        # The profile row comes ONLY from the handle_new_user trigger: the
        # service must not insert one itself. If this ever fails, every new
        # user silently has no profile.
        profile = (
            await session.execute(
                text("select * from profiles where id = :id"), {"id": user["id"]}
            )
        ).mappings().one()
        assert profile["display_name"] is None
        assert profile["onboarding_completed"] is False


async def test_register_duplicate_email_in_different_case_is_rejected(
    session_factory, cleanup_users
):
    email = "Duplicate@Case-Test.com"
    _track(cleanup_users, email)
    async with session_factory() as session:
        await register_user(session, email=email, password="first-password")
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(EmailAlreadyRegisteredError):
            await register_user(
                session, email=email.lower(), password="other-password"
            )

    async with session_factory() as session:
        count = (
            await session.execute(
                text("select count(*) from users where lower(email) = :email"),
                {"email": email.lower()},
            )
        ).scalar_one()
        assert count == 1, "case variant must not become a second account"


async def test_password_policy_error_is_distinct_from_duplicate(
    session_factory, cleanup_users
):
    # An empty password must surface as the password-policy error, and a
    # duplicate must surface as the duplicate error: the two are different
    # exception types the HTTP layer can map to 422/400 and 409 respectively.
    async with session_factory() as session:
        with pytest.raises(PasswordValidationError):
            await register_user(session, email="policy@example.com", password="")
        await session.rollback()
    async with session_factory() as session:
        count = (
            await session.execute(
                text("select count(*) from users where email = 'policy@example.com'")
            )
        ).scalar_one()
        assert count == 0

    existing = "policy-taken@example.com"
    _track(cleanup_users, existing)
    async with session_factory() as session:
        await register_user(session, email=existing, password="real-password")
        await session.commit()
        with pytest.raises(EmailAlreadyRegisteredError) as exc_info:
            await register_user(session, email=existing, password="also-valid-password")
        # The duplicate outcome is NOT the password-policy outcome: different
        # exception types map to different HTTP statuses (409 vs 4xx).
        assert not isinstance(exc_info.value, PasswordValidationError)


async def test_authenticate_with_correct_password_returns_identity(
    session_factory, cleanup_users
):
    email = "auth-happy@example.com"
    password = "super-secret-password-42"
    _track(cleanup_users, email)
    async with session_factory() as session:
        registered = await register_user(session, email=email, password=password)
        await session.commit()

    async with session_factory() as session:
        identity = await authenticate_user(session, email=email.upper(), password=password)
        assert identity is not None
        assert str(identity.id) == str(registered.id)
        assert identity.email == email.lower()


async def test_wrong_password_and_unknown_email_are_indistinguishable(
    session_factory, cleanup_users
):
    """Wrong password vs unknown email: SAME observable outcome.

    This is the anti-enumeration contract: the caller must not be able to
    distinguish "email does not exist" from "password is wrong" in any way.
    """
    email = "auth-enum@example.com"
    password = "the-real-password"
    _track(cleanup_users, email)
    async with session_factory() as session:
        await register_user(session, email=email, password=password)
        await session.commit()

    async with session_factory() as session:
        wrong_password = await authenticate_user(
            session, email=email, password="not-the-password"
        )
        unknown_email = await authenticate_user(
            session, email="nobody-here@example.com", password=password
        )
    # Assert the equivalence DIRECTLY, not merely that both are falsy.
    assert wrong_password == unknown_email
    assert wrong_password is None


async def test_corrupted_hash_fails_authentication_without_raising(
    session_factory, cleanup_users
):
    email = "auth-corrupt@example.com"
    password = "never-checked-anyway"
    _track(cleanup_users, email)
    async with session_factory() as session:
        identity = await register_user(session, email=email, password=password)
        await session.commit()

    # Corrupt the stored hash directly in the database, then authenticate:
    # must return None, not raise.
    async with session_factory() as session:
        await session.execute(
            text("update users set password_hash = :h where id = :id"),
            {"h": "corrupted-not-an-argon2-hash", "id": str(identity.id)},
        )
        await session.commit()

    async with session_factory() as session:
        result = await authenticate_user(session, email=email, password=password)
    assert result is None


async def test_no_plaintext_password_anywhere_in_users_rows(
    session_factory, cleanup_users
):
    email = "auth-noleak@example.com"
    password = "plaintext-must-not-be-stored-77"
    _track(cleanup_users, email)
    async with session_factory() as session:
        await register_user(session, email=email, password=password)
        await session.commit()

        rows = (
            await session.execute(text("select email, password_hash from users"))
        ).fetchall()
        assert rows, "expected at least one user row"
        for row in rows:
            assert password not in (row[0] or "")
            assert password != row[1]
            assert row[1].startswith("$argon2")


async def test_duplicate_email_does_not_leak_password_and_rolls_back(
    session_factory, cleanup_users
):
    """A failed duplicate insert leaves no partial user and no password traces."""
    email = "auth-rollback@example.com"
    _track(cleanup_users, email)
    async with session_factory() as session:
        await register_user(session, email=email, password="original-password")
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(EmailAlreadyRegisteredError) as exc_info:
            await register_user(
                session, email=email, password="second-attempt-password"
            )
        # The error names the email, never the password.
        assert "second-attempt-password" not in str(exc_info.value)

    async with session_factory() as session:
        count = (
            await session.execute(
                text("select count(*) from users where lower(email) = :email"),
                {"email": email},
            )
        ).scalar_one()
        assert count == 1
