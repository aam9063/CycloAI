"""RAG pipeline (P3a ingestion + P3b retrieval): chunking, embeddings, upsert
into ``knowledge_embeddings``, hybrid retrieval for prompt injection.

Public entry points:

- :func:`cycloai.rag.chunking.chunk_markdown` — pure chunking, no I/O.
- :class:`cycloai.rag.embeddings.GeminiEmbedder` — the real document embedder,
  behind the :data:`cycloai.rag.embeddings.EmbedFn` callable interface.
- :func:`cycloai.rag.ingest.run_index` — the full walk/chunk/embed/upsert
  pass; the only ingestion place a database connection is opened.
- :class:`cycloai.rag.retrieval.GeminiQueryEmbedder` — the real query
  embedder (RETRIEVAL_QUERY), behind :data:`cycloai.rag.retrieval.QueryEmbedFn`.
- :func:`cycloai.rag.search.search_knowledge_base` — the retrieval entry
  point with the never-throw contract: any failure returns '' and is logged.
"""

from cycloai.rag.chunking import (
    ParsedDocument,
    build_chunk_metadata,
    chunk_markdown,
    parse_document,
)
from cycloai.rag.embeddings import EmbedFn, GeminiEmbedder
from cycloai.rag.ingest import FileResult, RunSummary, index_file, run_index
from cycloai.rag.retrieval import (
    KnowledgeRow,
    QueryEmbedFn,
    format_chunks,
    parse_pgvector_text,
    retrieve_chunks,
)
from cycloai.rag.search import search_knowledge_base

__all__ = [
    "EmbedFn",
    "FileResult",
    "GeminiEmbedder",
    "GeminiQueryEmbedder",
    "KnowledgeRow",
    "ParsedDocument",
    "QueryEmbedFn",
    "RunSummary",
    "build_chunk_metadata",
    "chunk_markdown",
    "format_chunks",
    "index_file",
    "parse_document",
    "parse_pgvector_text",
    "retrieve_chunks",
    "run_index",
    "search_knowledge_base",
]
