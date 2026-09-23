"""Shared pytest fixtures for the CycloAI backend test suite.

Currently hosts the database test-residue cleanup: the database integration
modules create fixture users (``alice@example.com``, ``bob@example.com``,
``profile-*@example.com``, ...) through the ``users`` table and rely on the
``handle_new_user`` trigger for their profiles, but nothing removed those rows
when the suite ended. The shared session-scoped fixture below sweeps exactly
those rows once before and once after the full run, so a complete ``pytest``
session leaves no test user behind and residue from earlier runs is cleaned
on the next one.

Narrowness: only rows matching the known fixture emails (exact addresses, or
the fixed ``prefix-`` patterns the modules generate with a random suffix) are
deleted — never a broad delete. The cascade does the rest: ``profiles.id``,
``conversations.user_id`` and ``messages.conversation_id``/``user_id`` all
reference ``users(id) on delete cascade`` (initial Alembic revision), so
deleting the ``users`` rows removes the profile, conversations and messages
without a single extra DELETE statement.

Safety: when ``DATABASE_URL`` is unset the fixture does nothing (the database
integration modules skip themselves in that mode too); when the database is
unreachable the sweep is skipped with a printed warning instead of failing
the suite; and the disposable-database guard (same rule the integration
modules enforce before dropping schemas) refuses to touch a target whose name
does not look disposable.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL")

#: Every fixture email the database integration modules insert verbatim.
TEST_USER_EMAILS: tuple[str, ...] = (
    "alice@example.com",  # test_repositories_integration.py
    "bob@example.com",  # test_repositories_integration.py
    "trigger-test@example.com",  # test_db_integration.py
    "register-trigger@example.com",  # test_auth_service_integration.py
    "policy@example.com",  # test_auth_service_integration.py (never inserted)
    "policy-taken@example.com",  # test_auth_service_integration.py
    "auth-happy@example.com",  # test_auth_service_integration.py
    "auth-enum@example.com",  # test_auth_service_integration.py
    "auth-corrupt@example.com",  # test_auth_service_integration.py
    "auth-noleak@example.com",  # test_auth_service_integration.py
    "auth-rollback@example.com",  # test_auth_service_integration.py
    "athlete@example.com",  # test_api_auth.py (monkeypatched, defensive)
)

#: The random-suffix forms: fixed local-part prefix + ``@example.com``.
TEST_USER_EMAIL_PATTERNS: tuple[str, ...] = (
    "delete-me-%@example.com",  # test_account_integration.py
    "profile-%@example.com",  # test_api_profile_integration.py
    "owner-%@example.com",  # test_conversations_integration.py
    "outsider-%@example.com",  # test_conversations_integration.py
)

_COUNT_TABLES: tuple[str, ...] = ("users", "profiles", "conversations", "messages")

_DELETE_SQL = text(
    "delete from users "
    "where lower(email) = any(:emails) or lower(email) like any(:patterns)"
)


def _looks_disposable(url: str) -> bool:
    """Same disposable-database rule the integration modules enforce: only
    targets whose name contains ``test`` or ``dev`` (or the explicit
    ``CYCLOAI_DESTRUCTIVE_DB_TESTS=1`` opt-in) may be touched."""
    name = urlparse(url).path.lstrip("/").lower()
    return (
        "test" in name
        or "dev" in name
        or os.environ.get("CYCLOAI_DESTRUCTIVE_DB_TESTS") == "1"
    )


def _sweep_test_users(url: str, phase: str) -> None:
    """Delete the known test users, then report the four residue counts."""

    async def _run() -> tuple[int, dict[str, int]]:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                deleted = (
                    await conn.execute(
                        _DELETE_SQL,
                        {
                            "emails": list(TEST_USER_EMAILS),
                            "patterns": list(TEST_USER_EMAIL_PATTERNS),
                        },
                    )
                ).rowcount
                counts = {
                    table: (
                        await conn.execute(text(f"select count(*) from {table}"))
                    ).scalar_one()
                    for table in _COUNT_TABLES
                }
            return deleted, counts
        finally:
            await engine.dispose()

    try:
        deleted, counts = asyncio.run(_run())
    except Exception as error:  # database absent/unreachable: never fail the suite
        print(f"[db-test-cleanup] {phase}: sweep skipped ({error})")
        return
    print(
        f"[db-test-cleanup] {phase}: deleted={deleted} test users; "
        f"remaining counts: "
        + ", ".join(f"{table}={count}" for table, count in counts.items())
    )


@pytest.fixture(scope="session", autouse=True)
def db_test_user_cleanup():
    """Sweep test-user residue before and after the full pytest session.

    The pre-run sweep also removes residue left by earlier sessions, so the
    printed BEFORE/AFTER counts demonstrate a full run returns the tables to
    zero. With no ``DATABASE_URL`` the fixture is a no-op, matching the
    module-level guards that skip the database integration tests.
    """
    if DATABASE_URL is None:
        yield
        return
    if not _looks_disposable(DATABASE_URL):
        print(
            "[db-test-cleanup] skipped: DATABASE_URL does not look disposable; "
            "test-user rows are left untouched"
        )
        yield
        return
    _sweep_test_users(DATABASE_URL, phase="BEFORE full run")
    yield
    _sweep_test_users(DATABASE_URL, phase="AFTER full run")
