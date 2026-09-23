"""RAG retrieval half: query embedding, ``search_knowledge`` RPC, chunk formatting.

Port of the retrieval half of ``lib/ai/rag.ts`` (read-only reference). The
ingestion half (``ingest.py``, P3a) writes rows; this half reads them back for
prompt injection.

The embedder is injected as a callable — :data:`QueryEmbedFn`, a single-text
``str -> list[float]`` async callable — exactly as the ingestion half injects
:data:`cycloai.rag.embeddings.EmbedFn`, so retrieval is testable without the
API. Only :class:`GeminiQueryEmbedder` touches Google.

Asymmetric retrieval lock-in: documents are indexed with ``RETRIEVAL_DOCUMENT``
(see ``embeddings.py``), but a QUERY must be embedded with
``RETRIEVAL_QUERY`` — that is the task type the asymmetric-retrieval training
of ``gemini-embedding-001`` expects, and reusing the document task type for
queries degrades similarity quality. Dimensions stay locked at 768 to match
``extensions.vector(768)``.

The pgvector text-string problem (the P3a hand-off): ``asyncpg`` has no codec
for the pgvector type, so an ORM read of ``knowledge_embeddings.embedding``
returns the pgvector TEXT STRING (``"[0.1,0.2,...]"``), not a list. Decision:
parse the string where it is read (:func:`parse_pgvector_text`), and register
no codec. Rationale: the retrieval path never reads the embedding column at
all — the ``search_knowledge`` RPC returns only ``id, content, metadata,
score`` — and the query embedding is BOUND as pgvector's text form with an
explicit SQL cast, the same convention the ingestion insert path established.
A process-global codec could change the type contract P3a's insert path
relies on, for zero benefit here. The round-trip test in
``backend/tests/test_rag_retrieval_integration.py`` proves an ORM-read
embedding is the text string and parses back intact.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from cycloai.rag.embeddings import EMBED_DIMENSIONS, EMBED_MODEL, EmbedderSettings

# Approximate token cap for RAG context injected into the system prompt.
# 6000 chars ~ 1500 tokens at 4 chars/token. Whole-chunk truncation only —
# never mid-chunk. The '## BASE DE CONOCIMIENTO RELEVANTE' header is owned by
# the system prompt; this module returns chunk bodies only (no duplication).
MAX_RAG_CHARS = 6000

# match_count passed to search_knowledge — mirrors the original rpc call.
DEFAULT_MATCH_COUNT = 4

QUERY_TASK_TYPE = "RETRIEVAL_QUERY"

QueryEmbedFn = Callable[[str], Awaitable[list[float]]]

# The RPC is schema-qualified by the pinned search_path inside the function
# (``public, extensions``), but the cast must name the extension schema
# explicitly — same convention as the ingest insert statement.
_SEARCH_KNOWLEDGE_SQL = text(
    "select id, content, metadata, score "
    "from search_knowledge("
    "cast(:query_embedding as extensions.vector), :query_text, :match_count)"
)


@dataclass(frozen=True)
class KnowledgeRow:
    """One row returned by ``search_knowledge`` (fused RRF result).

    ``score`` is the fused RRF score (1/(60+rank) sums), not a raw cosine
    similarity — ordering must respect it rather than either leg alone.
    """

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass(frozen=True)
class RetrievedKnowledge:
    """ONE retrieval result carrying BOTH the display text and the citable ids.

    This object is the deliberate single source of truth for the generator:
    the prompt text is built from ``text`` and the citation set the raw
    payload gate checks is ``citation_ids``, derived from the very same rows
    in the very same pass. A display set that differs from the checked set is
    exactly how the original bug happened — the prompt rendered chunks under
    ``metadata.title`` while the gate checked ``source_file`` values, so the
    model was asked to cite something it was NEVER shown and every honest
    citation was rejected as unretrieved. Passing one of these objects to
    both the prompt builder and the gate makes that drift structurally
    impossible.
    """

    text: str
    citation_ids: frozenset[str]


def parse_pgvector_text(raw: str) -> list[float]:
    """Parse pgvector's text form (``"[0.1,0.2,...]"``) into floats.

    This is the explicit read-site solve for the missing asyncpg codec (see
    the module docstring). Raises ``ValueError`` on anything that is not a
    bracketed comma-separated number list.
    """
    if not (raw.startswith("[") and raw.endswith("]")):
        raise ValueError(f"not a pgvector text literal: {raw[:40]!r}")
    return [float(part) for part in raw[1:-1].split(",")]


def _format_blocks(
    rows: list[KnowledgeRow], *, show_citation: bool
) -> tuple[list[str], list[str]]:
    """Render chunk blocks (and their citable ids) under the whole-chunk cap.

    Per chunk the readable title is ``metadata.title``, falling back to
    ``metadata.source_file`` and then to ``Fragmento N`` (the row's 1-based
    position among the RENDERED blocks). With ``show_citation`` the block
    additionally states the CITABLE identifier on its own line — the exact
    string the generator's gate will accept in ``sources``. The citable
    identifier is ``source_file`` when present, else ``title``, else the same
    synthetic ``Fragmento N`` label: every displayed chunk is citable with a
    string that is shown verbatim, so what the model sees and what the gate
    checks cannot drift apart. Chunks are joined by the caller.

    Truncation is whole-chunk only: once adding the next block would exceed
    :data:`MAX_RAG_CHARS` the loop stops (no mid-chunk splits). The FIRST
    chunk is always allowed through even if it alone exceeds the cap (avoids
    returning empty on an oversized single result). A row dropped by the cap
    contributes neither a block nor a citation id.
    """
    blocks: list[str] = []
    citation_ids: list[str] = []
    used = 0

    for row in rows:
        # `is None` mirrors the original's ?? operator: a present-but-empty
        # title/source_file passes through rather than falling through.
        title = row.metadata.get("title")
        if title is None:
            title = row.metadata.get("source_file")
        if title is None:
            title = f"Fragmento {len(blocks) + 1}"
        position = len(blocks) + 1
        citation_id = row.metadata.get("source_file")
        if citation_id is None:
            citation_id = row.metadata.get("title")
        if citation_id is None:
            citation_id = f"Fragmento {position}"
        citation_id = str(citation_id)

        if show_citation:
            block = (
                f"[Conocimiento {position} — {title}]\n"
                f"fuente citable: {citation_id}\n"
                f"{row.content}"
            )
        else:
            block = f"[Conocimiento {position} — {title}]\n{row.content}"

        # Whole-chunk cap: never split mid-chunk. Allow the FIRST chunk
        # through even if it alone exceeds the cap.
        if blocks and used + len(block) > MAX_RAG_CHARS:
            break

        blocks.append(block)
        citation_ids.append(citation_id)
        used += len(block)

    return blocks, citation_ids


def format_chunks(rows: list[KnowledgeRow]) -> str:
    """Format knowledge rows into a plain-text block for the system prompt.

    Per chunk::

        [Conocimiento N — {title}]
        {content}

    Chunks are joined with ``\\n\\n---\\n\\n``. Truncation and title fallbacks
    are defined by :func:`_format_blocks`. This is the LEGACY chat-path
    renderer: it does NOT show the citable identifier, so it must never feed
    a prompt that asks the model to cite sources — use
    :func:`render_retrieved_knowledge` for that. Returns ``''`` when rows is
    empty.
    """
    blocks, _ = _format_blocks(rows, show_citation=False)
    return "\n\n---\n\n".join(blocks)


def render_retrieved_knowledge(rows: list[KnowledgeRow]) -> RetrievedKnowledge:
    """Render rows into the generator's ONE retrieval result (text + citable ids).

    This is the GENERATOR-path renderer and the only one that may back a
    prompt asking the model to cite sources: the rendered blocks display each
    chunk's citable identifier verbatim (``fuente citable: ...``) and the
    returned :class:`RetrievedKnowledge` carries exactly those identifiers as
    ``citation_ids``. The generator builds the prompt from ``text`` and hands
    ``citation_ids`` to the raw-payload gate, so the displayed set and the
    checked set are the same data by construction — see
    :class:`RetrievedKnowledge` for why that single source of truth is
    deliberate. Returns an empty-text/empty-id object when rows is empty.
    """
    blocks, citation_ids = _format_blocks(rows, show_citation=True)
    return RetrievedKnowledge(
        text="\n\n---\n\n".join(blocks), citation_ids=frozenset(citation_ids)
    )


class GeminiQueryEmbedder:
    """Real query embedder (gemini-embedding-001, 768 dims, RETRIEVAL_QUERY).

    Mirrors :class:`cycloai.rag.embeddings.GeminiEmbedder` (which is READ-ONLY
    P3a code and pins the RETRIEVAL_DOCUMENT task type) but with the query
    task type and a single-text signature matching :data:`QueryEmbedFn`.
    Only a live run constructs this; tests inject fakes, which is why the
    client is created eagerly here and never at import time.
    """

    def __init__(self, api_key: str | None = None) -> None:
        resolved = api_key if api_key is not None else EmbedderSettings().google_api_key
        if not resolved:
            raise RuntimeError(
                "GOOGLE_GENERATIVE_AI_API_KEY is not configured (process environment or "
                "backend/.env); it is never hardcoded and never printed."
            )
        self._client = genai.Client(api_key=resolved)

    async def __call__(self, text_value: str) -> list[float]:
        """Embed one query text as a RETRIEVAL_QUERY vector."""
        response = await self._client.aio.models.embed_content(
            model=EMBED_MODEL,
            contents=text_value,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBED_DIMENSIONS,
                task_type=QUERY_TASK_TYPE,
            ),
        )
        if not response.embeddings:
            raise RuntimeError("Gemini returned no embedding for the query")
        return list(response.embeddings[0].values or [])


async def retrieve_chunks(
    db: AsyncEngine | AsyncConnection,
    embed: QueryEmbedFn,
    query_text: str,
    *,
    match_count: int = DEFAULT_MATCH_COUNT,
) -> list[KnowledgeRow]:
    """Embed the query and run the hybrid ``search_knowledge`` RPC.

    ``db`` accepts an engine (a connection is opened and closed per call,
    mirroring the original's per-request Supabase client) or an open
    :class:`AsyncConnection` (transaction-scoped tests).

    Unlike the original entry point, this function CAN raise: embedding
    failures, dimension mismatches and RPC errors propagate to the caller.
    The never-throw contract lives in
    :func:`cycloai.rag.search.search_knowledge_base`.
    """
    trimmed = query_text.strip()
    if not trimmed:
        return []

    vector = await embed(trimmed)
    if len(vector) != EMBED_DIMENSIONS:
        raise ValueError(
            f"query embedding dimension mismatch: got {len(vector)}, expected "
            f"{EMBED_DIMENSIONS} (extensions.vector({EMBED_DIMENSIONS}))"
        )

    params = {
        # pgvector text form, cast in SQL — same convention as the ingest path.
        "query_embedding": json.dumps(vector),
        "query_text": trimmed,
        "match_count": match_count,
    }
    if isinstance(db, AsyncConnection):
        result = await db.execute(_SEARCH_KNOWLEDGE_SQL, params)
    else:
        async with db.connect() as conn:
            result = await conn.execute(_SEARCH_KNOWLEDGE_SQL, params)
    rows = result.fetchall()

    # asyncpg has no pgvector codec, and the jsonb metadata may arrive as a
    # string (raw text()) or an already-decoded dict (dialect codec).
    return [
        KnowledgeRow(
            id=str(row.id),
            content=row.content,
            metadata=json.loads(row.metadata)
            if isinstance(row.metadata, str)
            else dict(row.metadata or {}),
            score=float(row.score),
        )
        for row in rows
    ]
