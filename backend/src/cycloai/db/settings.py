"""Application settings for the CycloAI backend.

Auth secrets (JWT signing keys, cookie options, OAuth client ids, ...) arrive
with the auth work (P5), not here: this module owns database connectivity only.

The URL uses the asyncpg driver form:

    postgresql+asyncpg://user:password@host:port/dbname

Values are read from the process environment first, then from ``backend/.env``.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
