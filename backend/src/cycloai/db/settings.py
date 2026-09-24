"""Application settings for the CycloAI backend.

Auth secrets (JWT signing keys, cookie options, OAuth client ids, ...) arrive
with the auth work (P5), not here: this module owns database connectivity only.

The URL uses the asyncpg driver form:

    postgresql+asyncpg://user:password@host:port/dbname

Values are read from the process environment first, then from ``backend/.env``.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The env file is resolved from THIS module's location, not from the process
# working directory. A relative ``.env`` silently means ``backend/.env`` when you
# happen to run from ``backend/`` and the repository-root ``.env`` when you run
# from the root, so the same command behaved differently depending on where it
# was launched and reported "not configured" for a variable that existed.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
