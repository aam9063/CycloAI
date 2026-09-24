"""RAG ingestion pipeline: walk, chunk, embed, upsert, report.

Port of the indexing loop in ``scripts/rag-index.ts`` (read-only reference).

Importing this module performs no I/O and requires no database connection and
no API key: only :func:`run_index` (the run path) opens an engine/session, and
the embedder is always injected as an async callable, so the whole pipeline is
testable with a fake embedder against a disposable database.

Per-chunk metadata shape: ``{category, source_file, title, chunk_index,
total_chunks, keywords}`` with ``source_file`` relative to ``knowledge-base/``
and using forward slashes — the idempotency filter and the retrieval half
query this key.

The ``vector`` bind-processor problem: the ``Vector`` user-defined type in
``cycloai.db.models`` has no bind processor, so binding a Python list (or even
a ready string) through the ORM reaches asyncpg unadapted and fails at
execution time. The pipeline solves it explicitly: embeddings are serialized
into pgvector's text format (``[0.1,0.2,...]``) and inserted with an explicit
SQL cast, ``cast(:embedding as extensions.vector)``, via a text() statement —
never through the ORM column. The round-trip test in
``backend/tests/test_rag_ingest_integration.py`` proves a written embedding
reads back intact through both SQL and the ORM.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from cycloai.db.engine import create_engine
from cycloai.db.models import KnowledgeEmbedding
from cycloai.db.settings import Settings
from cycloai.rag.chunking import (
    ParsedDocument,
    build_chunk_metadata,
    chunk_markdown,
    parse_document,
)
from cycloai.rag.embeddings import (
    EMBED_DIMENSIONS,
    MAX_EMBED_ATTEMPTS,
    EmbedFn,
    embed_with_backoff,
)

# Free tier counts each embedded chunk as one request against a ~100/min
# window; ~700ms per embedded chunk keeps a file run under it.
PACE_SECONDS_PER_CHUNK = 0.7

STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"

_INSERT_CHUNK_SQL = text(
    "insert into knowledge_embeddings (content, embedding, metadata) "
    "values (:content, cast(:embedding as extensions.vector), cast(:metadata as jsonb))"
)


@dataclass(frozen=True)
class FileResult:
    """Outcome of indexing one markdown file."""

    file: str
    chunks: int
    status: str
    error: str | None = None


@dataclass
class RunSummary:
    """Aggregate of one ``run_index`` pass over the corpus."""

    results: list[FileResult] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def embedded_files(self) -> list[FileResult]:
        return [result for result in self.results if result.status == STATUS_OK]

    @property
    def embedded_chunks(self) -> int:
        return sum(result.chunks for result in self.embedded_files)

    @property
    def skipped_files(self) -> int:
        return sum(1 for result in self.results if result.status == STATUS_SKIPPED)

    @property
    def failed_files(self) -> int:
        return sum(1 for result in self.results if result.status == STATUS_FAILED)


def walk_markdown_files(root: Path) -> list[Path]:
    """Recursively collect ``*.md`` files under ``root``, deterministically sorted."""
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*") if path.is_file() and path.name.endswith(".md")
    )


def relative_source_file(kb_dir: Path, path: Path) -> str:
    """Path relative to ``knowledge-base/`` with forward slashes, always."""
    return path.relative_to(kb_dir).as_posix()


def embedding_literal(values: list[float]) -> str:
    """Serialize an embedding as pgvector's text format, dimension-checked.

    This is the explicit solve for the missing bind processor on the
    ``Vector`` type (see module docstring): the string is bound as text and
    cast in SQL, so no ORM bind processing is needed.
    """
    if len(values) != EMBED_DIMENSIONS:
        raise ValueError(
            f"embedding dimension mismatch: got {len(values)}, expected "
            f"{EMBED_DIMENSIONS} (extensions.vector({EMBED_DIMENSIONS}) column)"
        )
    return json.dumps(values)


async def count_existing_chunks(session, source_file: str) -> int:
    """Number of rows already indexed for ``source_file`` (idempotency check)."""
    stmt = (
        select(func.count())
        .select_from(KnowledgeEmbedding)
        .where(KnowledgeEmbedding.metadata_["source_file"].as_string() == source_file)
    )
    return (await session.execute(stmt)).scalar_one()


async def delete_chunks_for_source(session, source_file: str) -> None:
    """Delete every row indexed for ``source_file`` (used by forced reindexing)."""
    stmt = delete(KnowledgeEmbedding).where(
        KnowledgeEmbedding.metadata_["source_file"].as_string() == source_file
    )
    await session.execute(stmt)


async def insert_chunks(
    session,
    *,
    doc: ParsedDocument,
    category: str,
    source_file: str,
    chunk_texts: list[str],
    embeddings: list[list[float]],
) -> None:
    """Insert one metadata-complete row per chunk, embedding cast via SQL."""
    rows = [
        {
            "content": content,
            "embedding": embedding_literal(vector),
            "metadata": json.dumps(
                build_chunk_metadata(
                    category=category,
                    source_file=source_file,
                    title=doc.title,
                    chunk_index=idx,
                    total_chunks=len(chunk_texts),
                    keywords=doc.keywords,
                )
            ),
        }
        for idx, (content, vector) in enumerate(
            zip(chunk_texts, embeddings, strict=True)
        )
    ]
    await session.execute(_INSERT_CHUNK_SQL, rows)


async def index_file(
    session,
    path: Path,
    kb_dir: Path,
    embedder: EmbedFn,
    *,
    force: bool = False,
    max_attempts: int = MAX_EMBED_ATTEMPTS,
    backoff_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    backoff_log: Callable[[str], None] = print,
) -> FileResult:
    """Index a single markdown file: skip, chunk, embed, replace, report."""
    source_file = relative_source_file(kb_dir, path)

    # Resume mode: skip files that already have chunks in the DB (saves quota
    # on re-runs after partial failures). --force re-embeds everything.
    if not force:
        existing = await count_existing_chunks(session, source_file)
        if existing > 0:
            return FileResult(source_file, existing, STATUS_SKIPPED)

    try:
        raw = path.read_text(encoding="utf-8")
        doc = parse_document(raw, fallback_title=path.stem)
    except (OSError, ValueError) as err:
        # ValueError covers YAML front-matter parse failures.
        return FileResult(source_file, 0, STATUS_FAILED, f"read/parse error: {err}")

    chunk_texts = chunk_markdown(doc.content)
    if not chunk_texts:
        return FileResult(source_file, 0, STATUS_FAILED, "no chunks produced (file may be empty)")

    try:
        embeddings = await embed_with_backoff(
            embedder,
            chunk_texts,
            max_attempts=max_attempts,
            sleep=backoff_sleep,
            log=backoff_log,
        )
    except Exception as err:  # noqa: BLE001 - the embedder's failure text is reported per file
        return FileResult(source_file, 0, STATUS_FAILED, f"embed error: {err}")

    # Idempotent write: delete the file's existing rows, then insert fresh.
    # Brief delete+insert window is acceptable for offline reindexing.
    try:
        await delete_chunks_for_source(session, source_file)
        category = doc.category or source_file.split("/")[0] or "unknown"
        await insert_chunks(
            session,
            doc=doc,
            category=category,
            source_file=source_file,
            chunk_texts=chunk_texts,
            embeddings=embeddings,
        )
        await session.commit()
    except Exception as err:  # noqa: BLE001 - database failures are reported per file
        await session.rollback()
        return FileResult(source_file, 0, STATUS_FAILED, f"database error: {err}")

    return FileResult(source_file, len(chunk_texts), STATUS_OK)


async def run_index(
    kb_dir: Path,
    embedder: EmbedFn,
    *,
    database_url: str | None = None,
    force: bool = False,
    pace_seconds: float = PACE_SECONDS_PER_CHUNK,
    max_attempts: int = MAX_EMBED_ATTEMPTS,
    log: Callable[[str], None] = print,
) -> RunSummary:
    """Run the full pipeline over ``kb_dir``. Only here is a database opened.

    ``pace_seconds`` defaults to ~700ms per embedded chunk (free-tier window);
    tests pass 0 to skip pacing entirely.
    """
    files = walk_markdown_files(kb_dir)
    if not files:
        raise FileNotFoundError(f"no .md files found under {kb_dir}")

    if database_url is None:
        database_url = Settings().database_url
    engine: AsyncEngine = create_engine(Settings(database_url=database_url))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    force_note = "--force: re-embeds everything" if force else "resume: skips already-indexed files"
    log(f"\nIndexing {len(files)} file(s) from {kb_dir} ({force_note})\n")

    summary = RunSummary()
    try:
        async with sessionmaker() as session:
            for path in files:
                result = await index_file(
                    session,
                    path,
                    kb_dir,
                    embedder,
                    force=force,
                    max_attempts=max_attempts,
                    backoff_sleep=asyncio.sleep,
                    backoff_log=log,
                )
                summary.results.append(result)

                icon = {STATUS_OK: "✓", STATUS_SKIPPED: "→"}.get(result.status, "✗")
                if result.status == STATUS_OK:
                    detail = f"{result.chunks} chunk(s)"
                elif result.status == STATUS_SKIPPED:
                    detail = f"already indexed ({result.chunks} chunk(s)) — skipped"
                else:
                    detail = f"FAILED: {result.error or 'unknown error'}"
                log(f"  {icon} {result.file} — {detail}")

                # Pace embedding throughput between files (free-tier window).
                if result.status == STATUS_OK and pace_seconds > 0:
                    await asyncio.sleep(result.chunks * pace_seconds)
    finally:
        await engine.dispose()

    log("\n----------------------------------------")
    log(f"Archivos procesados : {summary.total_files}")
    log(
        f"Embebidos ahora     : {len(summary.embedded_files)} "
        f"({summary.embedded_chunks} chunks)"
    )
    log(f"Omitidos (ya en DB) : {summary.skipped_files}")
    log(f"Fallos              : {summary.failed_files}")
    log("----------------------------------------\n")

    return summary
