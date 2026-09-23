"""RAG ingestion pipeline (P3a): chunking, embeddings, upsert into
``knowledge_embeddings``.

Public entry points:

- :func:`cycloai.rag.chunking.chunk_markdown` — pure chunking, no I/O.
- :class:`cycloai.rag.embeddings.GeminiEmbedder` — the real embedder, behind
  the :data:`cycloai.rag.embeddings.EmbedFn` callable interface.
- :func:`cycloai.rag.ingest.run_index` — the full walk/chunk/embed/upsert
  pass; the only place a database connection is opened.

The retrieval half is deliberately not part of this package yet.
"""

from cycloai.rag.chunking import (
    ParsedDocument,
    build_chunk_metadata,
    chunk_markdown,
    parse_document,
)
from cycloai.rag.embeddings import EmbedFn, GeminiEmbedder
from cycloai.rag.ingest import FileResult, RunSummary, index_file, run_index

__all__ = [
    "EmbedFn",
    "FileResult",
    "GeminiEmbedder",
    "ParsedDocument",
    "RunSummary",
    "build_chunk_metadata",
    "chunk_markdown",
    "index_file",
    "parse_document",
    "run_index",
]
