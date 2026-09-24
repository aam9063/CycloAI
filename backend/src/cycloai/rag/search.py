"""Public RAG retrieval entry point with never-throw semantics.

Port of ``searchKnowledgeBase`` in ``lib/ai/rag.ts`` (read-only reference).

FAILURE SEMANTICS ARE LOAD-BEARING: the original NEVER throws. Any failure —
embedding error, quota error, RPC error, empty result — returns an empty
string, and the chat continues with the knowledge section simply omitted
(the system prompt owns that omission). A silent retrieval failure is
indistinguishable from "the corpus has nothing relevant", and those two are
very different problems, so every failure is reported through ``log`` with
its stage and reason instead of being swallowed.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from cycloai.db.engine import create_engine
from cycloai.db.settings import Settings
from cycloai.rag.embeddings import EMBED_DIMENSIONS
from cycloai.rag.retrieval import (
    DEFAULT_MATCH_COUNT,
    GeminiQueryEmbedder,
    QueryEmbedFn,
    format_chunks,
    retrieve_chunks,
)


async def search_knowledge_base(
    query_text: str | None,
    *,
    embed: QueryEmbedFn | None = None,
    db: AsyncEngine | AsyncConnection | None = None,
    match_count: int = DEFAULT_MATCH_COUNT,
    log: Callable[[str], None] = print,
) -> str:
    """Retrieve relevant knowledge chunks for a query text, or '' on ANY failure.

    Embeds the query (RETRIEVAL_QUERY, 768 dims), calls the ``search_knowledge``
    RPC (hybrid RRF: vector cosine + FTS) and formats the rows for prompt
    injection via :func:`cycloai.rag.retrieval.format_chunks`.

    Never raises: an empty/whitespace-only query short-circuits before any
    embedder or database use, and every downstream failure is logged with its
    stage (``embed`` / ``database``) and returned as ''.
    """
    trimmed = (query_text or "").strip()
    if not trimmed:
        return ""

    owned_engine: AsyncEngine | None = None
    # Mutable state so the nested embed wrapper can flip the stage.
    state = {"stage": "embed"}
    try:
        embedder = embed if embed is not None else GeminiQueryEmbedder()

        # The embed stage covers the embedder call AND validation of its
        # output; once a valid vector exists, failures belong to the database
        # stage. (retrieve_chunks re-checks dimensions as its own invariant;
        # this duplicate check only attributes the failure to the right stage.)
        async def stage_tracking_embed(text_value: str) -> list[float]:
            vector = await embedder(text_value)
            if len(vector) != EMBED_DIMENSIONS:
                raise ValueError(
                    f"query embedding dimension mismatch: got {len(vector)}, expected "
                    f"{EMBED_DIMENSIONS}"
                )
            state["stage"] = "database"
            return vector

        if db is None:
            # Per-call engine, mirroring the original's per-request client.
            owned_engine = create_engine(Settings())
            db = owned_engine
        rows = await retrieve_chunks(
            db, stage_tracking_embed, trimmed, match_count=match_count
        )
        return format_chunks(rows)
    except Exception as err:  # noqa: BLE001 - the contract is NEVER throw
        log(f"[rag] retrieval failed during {state['stage']}: {err}")
        return ""
    finally:
        if owned_engine is not None:
            await owned_engine.dispose()
