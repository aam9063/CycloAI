"""Pure unit tests for the RAG retrieval half — no database, no API.

Covers the formatting contract ported from ``lib/ai/rag.ts`` (title
fallbacks, whole-chunk truncation with the oversized-first-chunk rule,
separators/numbering), the pgvector text-literal parse, and the never-throw
entry point: an empty query short-circuits before any embedder or database
use, and a failing embedder, a wrong-dimension embedding or a failing
database each yield '' plus a visible log line — never an exception.
"""

from __future__ import annotations

from typing import Any

import pytest

from cycloai.rag.ingest import embedding_literal
from cycloai.rag.retrieval import (
    MAX_RAG_CHARS,
    KnowledgeRow,
    format_chunks,
    parse_pgvector_text,
)
from cycloai.rag.search import search_knowledge_base

_SEPARATOR = "\n\n---\n\n"


def _row(content: str, metadata: dict[str, Any] | None = None, score: float = 0.0):
    return KnowledgeRow(
        id=f"id-{content[:8]}", content=content, metadata=metadata or {}, score=score
    )


def _block(number: int, title: str, content: str) -> str:
    """The exact block shape format_chunks must produce."""
    return f"[Conocimiento {number} — {title}]\n{content}"


# ---------------------------------------------------------------------------
# format_chunks
# ---------------------------------------------------------------------------


def test_format_chunks_empty_rows_returns_empty_string():
    assert format_chunks([]) == ""


def test_format_chunks_renders_title_numbering_and_separator():
    rows = [_row("contenido uno", {"title": "Doc A"}), _row("contenido dos", {"title": "Doc B"})]
    expected = _SEPARATOR.join(
        [_block(1, "Doc A", "contenido uno"), _block(2, "Doc B", "contenido dos")]
    )
    assert format_chunks(rows) == expected


def test_format_chunks_title_falls_back_to_source_file_then_fragment():
    rows = [
        _row("c1", {"source_file": "guias/ftp.md"}),  # no title -> source_file
        _row("c2", {}),  # neither -> Fragmento 2 (row position, 1-based)
        _row("c3", {"title": None, "source_file": None}),  # explicit nulls fall through
        _row("c4", {"title": "Doc D"}),
    ]
    formatted = format_chunks(rows)
    assert _block(1, "guias/ftp.md", "c1") in formatted
    assert _block(2, "Fragmento 2", "c2") in formatted
    assert _block(3, "Fragmento 3", "c3") in formatted
    assert _block(4, "Doc D", "c4") in formatted


def test_format_chunks_truncates_on_whole_chunks_only():
    # Header "[Conocimiento N — t]\n" is 21 chars with a 1-char title.
    header_len = len("[Conocimiento 1 — t]\n")
    # Fill sized so two blocks AND their separator stay under the cap (the
    # original's `used` counter does not count separators either), while a
    # third block would exceed it.
    fill = (MAX_RAG_CHARS - len(_SEPARATOR)) // 2 - header_len
    rows = [
        _row("a" * fill, {"title": "t"}),
        _row("b" * fill, {"title": "t"}),
        _row("c" * fill, {"title": "t"}),
    ]

    formatted = format_chunks(rows)

    # Two whole chunks fit under the cap; the third is dropped entirely.
    assert formatted == _SEPARATOR.join(
        [_block(1, "t", "a" * fill), _block(2, "t", "b" * fill)]
    )
    assert len(formatted) <= MAX_RAG_CHARS
    assert "c" * fill not in formatted


def test_format_chunks_boundary_exactly_at_cap_allows_chunk():
    header_len = len("[Conocimiento 1 — t]\n")
    exact_fill = MAX_RAG_CHARS - header_len  # block length == MAX_RAG_CHARS
    rows = [_row("a" * exact_fill, {"title": "t"}), _row("b" * 10, {"title": "t"})]

    formatted = format_chunks(rows)

    # Strictly-over is the break condition, so == cap is allowed through…
    first_block = _block(1, "t", "a" * exact_fill)
    assert formatted.startswith(first_block)
    # …but the next chunk, which would exceed it, is not appended.
    assert "b" * 10 not in formatted


def test_format_chunks_oversized_first_chunk_allowed_through():
    oversized = _row("a" * (MAX_RAG_CHARS + 1000), {"title": "t"})
    assert format_chunks([oversized]) == _block(1, "t", "a" * (MAX_RAG_CHARS + 1000))


def test_format_chunks_oversized_first_chunk_still_blocks_the_rest():
    rows = [
        _row("a" * (MAX_RAG_CHARS + 1000), {"title": "t"}),
        _row("b" * 10, {"title": "t"}),
    ]
    formatted = format_chunks(rows)
    assert formatted == _block(1, "t", "a" * (MAX_RAG_CHARS + 1000))
    assert "b" * 10 not in formatted


# ---------------------------------------------------------------------------
# parse_pgvector_text — the P3a hand-off decision (parse where you read)
# ---------------------------------------------------------------------------


def test_parse_pgvector_text_round_trips_the_ingest_literal():
    vector = [0.1, -0.25, 3.5, 0.0, 1.0 / 3.0]
    vector += [0.0] * (768 - len(vector))  # embedding_literal is dimension-checked
    assert parse_pgvector_text(embedding_literal(vector)) == pytest.approx(vector)


def test_parse_pgvector_text_rejects_malformed_input():
    with pytest.raises(ValueError, match="pgvector text literal"):
        parse_pgvector_text("0.1,0.2")


# ---------------------------------------------------------------------------
# search_knowledge_base — never-throw contract
# ---------------------------------------------------------------------------


class _RecordingEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, text_value: str) -> list[float]:
        self.calls.append(text_value)
        return [0.0] * 768


class _BrokenEmbedder:
    async def __call__(self, text_value: str) -> list[float]:
        raise RuntimeError("quota exceeded for project")


class _WrongDimensionEmbedder:
    async def __call__(self, text_value: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _ExplodingDb:
    """Any use of the database during a test is a loud failure."""

    def connect(self):
        raise AssertionError("database must not be touched by this path")


class _BrokenDb:
    def connect(self):
        raise RuntimeError("connection refused")


async def test_empty_query_short_circuits_before_any_embedder_or_database_use():
    embedder = _RecordingEmbedder()
    assert await search_knowledge_base("   \t\n  ", embed=embedder, db=_ExplodingDb()) == ""
    assert embedder.calls == []


async def test_none_query_returns_empty_string():
    embedder = _RecordingEmbedder()
    assert await search_knowledge_base(None, embed=embedder, db=_ExplodingDb()) == ""
    assert embedder.calls == []


async def test_failing_embedder_yields_empty_string_and_a_visible_reason():
    logs: list[str] = []
    result = await search_knowledge_base(
        "entrenamiento de umbral",
        embed=_BrokenEmbedder(),
        db=_ExplodingDb(),
        log=logs.append,
    )
    assert result == ""
    assert len(logs) == 1
    assert "quota exceeded for project" in logs[0]
    assert "embed" in logs[0]  # the failing stage is named


async def test_wrong_dimension_embedding_yields_empty_string_and_a_visible_reason():
    logs: list[str] = []
    result = await search_knowledge_base(
        "entrenamiento de umbral",
        embed=_WrongDimensionEmbedder(),
        db=_ExplodingDb(),
        log=logs.append,
    )
    assert result == ""
    assert "dimension mismatch" in logs[0]


async def test_failing_database_yields_empty_string_and_a_visible_reason():
    logs: list[str] = []
    result = await search_knowledge_base(
        "entrenamiento de umbral",
        embed=_RecordingEmbedder(),
        db=_BrokenDb(),
        log=logs.append,
    )
    assert result == ""
    assert len(logs) == 1
    assert "connection refused" in logs[0]
    assert "database" in logs[0]  # the failing stage is named
