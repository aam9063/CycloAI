"""Integration tests for the P2 PostgreSQL schema (Alembic + pgvector).

These tests need a real PostgreSQL with pgvector (see ``docker-compose.yml``
at the repository root). The WHOLE module is skipped when ``DATABASE_URL`` is
not set, so a plain ``uv run pytest`` never requires Docker.

Note: the ``migrated_db`` fixture resets the target database to a clean state
(drops and recreates the ``public`` and ``extensions`` schemas) so the initial
Alembic revision is proven to apply from scratch on every run. Point
``DATABASE_URL`` at a disposable development database only.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import alembic.command
import alembic.config
import alembic.script
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("DATABASE_URL")


def _assert_disposable_database(url: str) -> None:
    """Refuse to run destructive tests against a database that is not disposable.

    The ``migrated_db`` fixture drops the ``public`` and ``extensions`` schemas
    outright, so pointing ``DATABASE_URL`` at anything but a throwaway database
    destroys real data. A warning in a docstring is not a guard, so this fails
    closed at import time: the suite errors loudly instead of wiping a database
    somebody aimed here by accident.

    A database name containing ``test`` or ``dev`` is accepted as disposable.
    Any other target needs the explicit ``CYCLOAI_DESTRUCTIVE_DB_TESTS=1`` opt-in.
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

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "users": {"id", "email", "password_hash", "display_name", "avatar_url", "created_at"},
    "profiles": {
        "id",
        "created_at",
        "updated_at",
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
    },
    "conversations": {"id", "user_id", "created_at", "updated_at", "title", "summary"},
    "messages": {
        "id",
        "conversation_id",
        "user_id",
        "role",
        "content",
        "created_at",
        "metadata",
    },
    "knowledge_embeddings": {"id", "content", "embedding", "metadata", "fts", "created_at"},
    "waitlist": {"id", "email", "source", "created_at"},
}


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
    yield {"engine": engine, "head": _alembic_config()}
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
def engine(migrated_db):
    return migrated_db["engine"]


async def _fetch_one(engine, sql: str, params: dict[str, Any] | None = None) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), params or {})
        return result.mappings().one_or_none()


async def test_migration_reaches_head(migrated_db):
    cfg = migrated_db["head"]
    script = alembic.script.ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    row = await _fetch_one(migrated_db["engine"], "select version_num from alembic_version")
    assert row["version_num"] == head


async def test_vector_extension_in_extensions_schema_not_public(engine):
    row = await _fetch_one(
        engine,
        """
        select n.nspname as schema_name
        from pg_extension e
        join pg_namespace n on n.oid = e.extnamespace
        where e.extname = 'vector'
        """,
    )
    assert row is not None, "vector extension is not installed"
    assert row["schema_name"] == "extensions"


async def test_all_six_tables_have_expected_columns(engine):
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    select table_name, column_name
                    from information_schema.columns
                    where table_schema = 'public'
                    """
                )
            )
        ).fetchall()
    actual: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        actual.setdefault(table_name, set()).add(column_name)

    for table, expected in EXPECTED_COLUMNS.items():
        assert table in actual, f"table {table} does not exist"
        assert actual[table] == expected, (
            f"table {table}: missing={expected - actual[table]}, "
            f"unexpected={actual[table] - expected}"
        )


async def test_search_knowledge_signature(engine):
    row = await _fetch_one(
        engine,
        """
        select pg_get_function_identity_arguments(p.oid) as args, p.prokind
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'search_knowledge'
        """,
    )
    assert row is not None, "public.search_knowledge does not exist"
    # asyncpg returns char("char") values as bytes.
    prokind = row["prokind"].decode() if isinstance(row["prokind"], bytes) else row["prokind"]
    assert prokind == "f"
    # pg_get_function_identity_arguments never carries the typmod,
    # so the base type name is the expected form.
    assert "query_embedding extensions.vector" in row["args"]
    assert "query_text text" in row["args"]
    assert "match_count integer" in row["args"]


async def test_spanish_text_search_configuration(engine):
    async with engine.connect() as conn:
        config_count = (
            await conn.execute(
                text("select count(*) from pg_ts_config where cfgname = 'spanish'")
            )
        ).scalar_one()
        assert config_count >= 1
        # Exercise it end to end: the inflected form must match its own stem,
        # which only the Spanish configuration guarantees.
        match = await conn.execute(
            text(
                "select to_tsquery('spanish', 'corriendo') "
                "@@ to_tsvector('spanish', 'corriendo por las montañas')"
            )
        )
        assert match.scalar_one() is True


async def test_handle_new_user_trigger_creates_profile(engine):
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                insert into users (email, password_hash, display_name, avatar_url)
                values ('trigger-test@example.com', 'hash', 'Trigger Tester',
                        'https://example.com/a.png')
                returning id
                """
            )
        )
        user_id = result.scalar_one()
        profile = (
            await conn.execute(
                text("select * from profiles where id = :id"), {"id": user_id}
            )
        ).mappings().one()
        assert profile["display_name"] == "Trigger Tester"
        assert profile["avatar_url"] == "https://example.com/a.png"
        assert profile["onboarding_completed"] is False
        # Transaction rolls back: no test residue stays in the database.


async def test_waitlist_check_rejects_bad_email_and_oversized_source(engine):
    async with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text("insert into waitlist (email) values ('not-an-email')")
            )
    async with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "insert into waitlist (email, source) values ('dev@example.com', :src)"
                ),
                {"src": "x" * 51},
            )
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into waitlist (email, source) values ('dev@example.com', 'landing')")
        )


async def test_waitlist_email_unique_is_case_insensitive(engine):
    async with engine.begin() as conn:
        await conn.execute(text("insert into waitlist (email) values ('A@B.com')"))
    async with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(text("insert into waitlist (email) values ('a@b.com')"))
