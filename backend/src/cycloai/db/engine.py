"""Async SQLAlchemy engine and session factories.

Nothing connects at import time: the engine and sessionmaker are created
lazily on first use, so importing this module never requires a database.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cycloai.db.settings import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create a fresh engine from explicit settings (or the ambient ones)."""
    if settings is None:
        settings = Settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first use."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one transaction per request (unit of work).

    The request boundary — not the individual route — owns the transaction:
    when the request completes successfully the session is committed, and
    when anything raises the session is rolled back and the exception is
    re-raised. This is deliberate: the alternative (committing inside each
    mutating route) fails silently the moment a route author forgets — the
    route returns ``200`` and the data vanishes on close, with the failure
    surfacing far from its cause. A route author cannot forget a boundary
    they never have to write.

    Note for other writers of sessions: code that creates its own session
    outside a request (or overrides this dependency, as some integration
    tests do) owns its own commit.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
