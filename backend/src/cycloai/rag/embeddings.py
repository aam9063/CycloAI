"""Gemini embedding adapter for the RAG ingestion pipeline.

The pipeline never depends on Google's client directly: it depends on the
async :data:`EmbedFn` callable (``list[str] -> list[list[float]]``). Tests
inject a fake embedder and no Google API is touched; only a live run goes
through :class:`GeminiEmbedder`.

Dimension lock-in: ``gemini-embedding-001`` is queried with
``output_dimensionality=768`` because ``knowledge_embeddings.embedding`` is
``extensions.vector(768)`` (see ``backend/alembic/versions/
1a2b3c4d5e6f_p2_initial_schema.py``). A dimension mismatch is a PostgreSQL
runtime error at insert time, so the dimension is a constant here and the
pipeline re-checks it before writing a row.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EMBED_MODEL = "gemini-embedding-001"
# LOCK-IN: must match extensions.vector(768) in the initial schema migration
# and the vector(768) column. Any mismatch is a runtime error at insert time.
EMBED_DIMENSIONS = 768
EMBED_TASK_TYPE = "RETRIEVAL_DOCUMENT"

# Quota handling (mirrors embedWithBackoff in scripts/rag-index.ts): on
# quota/rate-limit shaped errors wait for the delay Google suggests, else a
# sensible default for a per-minute quota window, and retry up to
# MAX_EMBED_ATTEMPTS total tries. Any other error fails the file.
DEFAULT_RETRY_DELAY_MS = 45_000
MAX_EMBED_ATTEMPTS = 5

_RETRY_DELAY_PATTERN = re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE)

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]

# The env file is resolved from THIS module's location, not from the process
# working directory. A relative ``.env`` silently means ``backend/.env`` when
# you happen to run from ``backend/`` and the repository-root ``.env`` when you
# run from the root, so the same command behaved differently depending on
# where it was launched. Mirrors ``cycloai.db.settings``.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class EmbedderSettings(BaseSettings):
    """API-key resolution mirroring ``cycloai.db.settings`` conventions.

    Reads the process environment first, then ``backend/.env``; the env-file
    path is resolved from this module's location, so key resolution no longer
    depends on the process working directory. The key is never hardcoded and
    never printed. (``cycloai.db.settings.Settings`` currently owns database
    connectivity only and is not extendable from this module, so the Gemini
    key lives here with the same env var name the TypeScript original used.)
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = Field(default="", validation_alias="GOOGLE_GENERATIVE_AI_API_KEY")

    # Generation model, consumed by ``cycloai.generator.client`` so both the
    # key and the model name resolve from the same settings/env-file source.
    generation_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias="GEMINI_GENERATION_MODEL",
    )


def parse_retry_delay_ms(message: str) -> int:
    """Extract Google's suggested retry delay ("please retry in 31.66s").

    Returns the delay in milliseconds with a +1s safety margin, or
    ``DEFAULT_RETRY_DELAY_MS`` when the message carries no suggestion.
    """
    match = _RETRY_DELAY_PATTERN.search(message)
    if match:
        return math.ceil(float(match.group(1)) * 1000) + 1000  # +1s safety
    return DEFAULT_RETRY_DELAY_MS


def is_quota_error(message: str) -> bool:
    """True only for quota/rate-limit shaped errors; anything else fails the file."""
    lower = message.lower()
    return any(
        marker in lower
        for marker in ("quota", "429", "rate limit", "resource_exhausted")
    )


async def embed_with_backoff(
    embed: EmbedFn,
    texts: list[str],
    *,
    max_attempts: int = MAX_EMBED_ATTEMPTS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    log: Callable[[str], None] = print,
) -> list[list[float]]:
    """Embed a batch, retrying patiently on quota errors.

    Non-quota errors raise immediately (the caller marks the file failed).
    Quota errors wait for Google's suggested delay (or the default) and
    retry, up to ``max_attempts`` total tries.
    """
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            return await embed(texts)
        except Exception as err:  # noqa: BLE001 - any error text is inspected, then re-raised
            last_error = str(err)
            if not is_quota_error(last_error) or attempt == max_attempts:
                raise
            wait_ms = parse_retry_delay_ms(last_error)
            log(
                f"    · cuota alcanzada — esperando {round(wait_ms / 1000)}s "
                f"antes de reintentar ({attempt}/{max_attempts - 1})"
            )
            await sleep(wait_ms / 1000)
    raise RuntimeError(last_error)


class GeminiEmbedder:
    """Real embedder (gemini-embedding-001, 768 dims, RETRIEVAL_DOCUMENT).

    Implements :data:`EmbedFn`. Only a live run constructs this; tests inject
    fakes, which is why the client is created eagerly here and never at
    import time.
    """

    def __init__(self, api_key: str | None = None) -> None:
        resolved = api_key if api_key is not None else EmbedderSettings().google_api_key
        if not resolved:
            raise RuntimeError(
                "GOOGLE_GENERATIVE_AI_API_KEY is not configured (process environment or "
                "backend/.env). Export it before running the indexer; it is never "
                "hardcoded and never printed."
            )
        self.api_key = resolved
        self._client = genai.Client(api_key=resolved)

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunk texts as RETRIEVAL_DOCUMENT vectors."""
        response = await self._client.aio.models.embed_content(
            model=EMBED_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBED_DIMENSIONS,
                task_type=EMBED_TASK_TYPE,
            ),
        )
        if not response.embeddings:
            raise RuntimeError("Gemini returned no embeddings for the batch")
        return [list(item.values or []) for item in response.embeddings]
