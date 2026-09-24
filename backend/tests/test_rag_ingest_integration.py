"""Integration tests for the RAG ingestion pipeline — needs PostgreSQL + pgvector.

The WHOLE module is skipped when ``DATABASE_URL`` is not set, with the same
disposable-database guard ``test_db_integration.py`` uses (a database name
containing ``test``/``dev``, or the ``CYCLOAI_DESTRUCTIVE_DB_TESTS=1``
opt-in). The schema is brought up with ``alembic upgrade head``, which is
idempotent and non-destructive: it never drops anything.

Everything runs against a small synthetic corpus with a FAKE embedder, so no
Google API key or quota is involved: real rows are written to and read back
from ``knowledge_embeddings``, a second run skips what is already indexed,
and ``--force`` reindexes without duplicating rows.

The embedding round-trip test exists because the ``Vector`` user-defined type
has no bind processor: the pipeline inserts embeddings as pgvector text
literals with an explicit SQL cast (``cast(:embedding as extensions.vector)``),
and this module proves a written embedding reads back intact through both raw
SQL and the ORM.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import alembic.command
import alembic.config
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from cycloai.db.models import KnowledgeEmbedding
from cycloai.rag.chunking import parse_document
from cycloai.rag.ingest import (
    STATUS_OK,
    STATUS_SKIPPED,
    insert_chunks,
    run_index,
)
from test_db_integration import BACKEND_DIR, DATABASE_URL, _assert_disposable_database

pytestmark = [
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="DATABASE_URL not set: database integration tests need a running PostgreSQL",
    ),
    # One event loop per module: the module-scoped engine must not be shared
    # across per-test loops (asyncpg connections are loop-bound).
    pytest.mark.asyncio(loop_scope="module"),
]

if DATABASE_URL is not None:
    _assert_disposable_database(DATABASE_URL)

CORPUS_SOURCE_FILES = (
    "training/doc-a.md",
    "misc/doc-b.md",
    "misc/doc-c.md",
)

DOC_A_BODY = (
    "## Zona 2 base\n"
    "Sesiones largas y suaves para construir la base aerobica del ciclista "
    "con competencias de fondo en la temporada."
)
DOC_B_SECTION_1 = "## Umbral\nBloques de 2x20 minutos al umbral funcional de lactato."
DOC_B_SECTION_2 = "## VO2max\nSeries de 3 a 5 minutos por encima de 110 por ciento del FTP."
DOC_C_INTRO = "No front matter at all."

# Sorted walk order (misc/ < training/): doc-b 2 chunks, doc-c 2, doc-a 1.
EXPECTED_CHUNKS_PER_FILE = {"misc/doc-b.md": 2, "misc/doc-c.md": 2, "training/doc-a.md": 1}


def _deterministic_vector(text_value: str) -> list[float]:
    """768-dim vector derived from the text; stable across runs and processes."""
    seed = sum(text_value.encode("utf-8"))
    return [((seed + i) % 100) / 100 for i in range(768)]


class FakeEmbedder:
    """Stands in for GeminiEmbedder: records batches, returns stable vectors."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_deterministic_vector(value) for value in texts]


def _alembic_config() -> alembic.config.Config:
    cfg = alembic.config.Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def migrated_db():
    """Ensure the schema exists (idempotent upgrade; never drops anything)."""
    await asyncio.to_thread(alembic.command.upgrade, _alembic_config(), "head")
    return _alembic_config()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def clean_corpus_rows(migrated_db):
    """Remove any rows left by earlier runs of this suite for the corpus files.

    The synthetic corpus keeps stable source_file values across pytest
    sessions, while ``cycloai_dev`` is long-lived: without this, a rerun
    would see resume mode skip everything before the first run ever happens.
    """
    del migrated_db
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            for source_file in CORPUS_SOURCE_FILES:
                await conn.execute(
                    text(
                        "delete from knowledge_embeddings "
                        "where metadata->>'source_file' = :source_file"
                    ),
                    {"source_file": source_file},
                )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory) -> Path:
    """A small knowledge-base-shaped corpus: three files, four chunks total."""
    root = tmp_path_factory.mktemp("kb")
    training = root / "training"
    misc = root / "misc"
    training.mkdir()
    misc.mkdir()
    (training / "doc-a.md").write_text(
        "---\n"
        "title: Doc A\n"
        "keywords: [base, aerobica]\n"
        "---\n"  # no category: pipeline must derive it from the path segment
        f"\n{DOC_A_BODY}\n",
        encoding="utf-8",
    )
    (misc / "doc-b.md").write_text(
        "---\n"
        "title: Doc B\n"
        "category: nutrition\n"  # front matter must win over the path ("misc")
        "keywords: [umbral, vo2max]\n"
        "---\n"
        f"\n{DOC_B_SECTION_1}\n\n{DOC_B_SECTION_2}\n",
        encoding="utf-8",
    )
    (misc / "doc-c.md").write_text(
        f"{DOC_C_INTRO}\n\n{DOC_B_SECTION_1}\n",
        encoding="utf-8",
    )
    return root


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def first_run(clean_corpus_rows, corpus_dir) -> dict[str, Any]:
    """Run the pipeline once over the corpus; shared state for the module."""
    embedder = FakeEmbedder()
    summary = await run_index(
        corpus_dir,
        embedder,
        database_url=DATABASE_URL,
        pace_seconds=0,  # tests skip the free-tier pacing sleep entirely
    )
    return {"summary": summary, "embedder": embedder, "corpus_dir": corpus_dir}


async def _count_rows(engine: AsyncEngine, source_file: str) -> int:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "select count(*) from knowledge_embeddings "
                    "where metadata->>'source_file' = :source_file"
                ),
                {"source_file": source_file},
            )
        ).scalar_one()


async def test_first_run_embeds_every_file(first_run):
    summary = first_run["summary"]
    assert summary.total_files == 3
    assert [result.status for result in summary.results] == [STATUS_OK] * 3
    # doc-b: 2 ## sections; doc-c: intro line + one ## section; doc-a: 1 chunk.
    assert [result.chunks for result in summary.results] == [2, 2, 1]
    assert summary.embedded_chunks == 5
    # One batched embed call per file, sized to its chunk count.
    assert [len(call) for call in first_run["embedder"].calls] == [2, 2, 1]


async def test_chunk_rows_carry_the_documented_metadata(first_run):
    del first_run  # ensures the module-scoped run happened before row assertions
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "select content, metadata from knowledge_embeddings "
                        "where metadata->>'source_file' = 'misc/doc-b.md' "
                        "order by metadata->>'chunk_index'"
                    )
                )
            ).fetchall()
    finally:
        await engine.dispose()

    assert len(rows) == 2
    assert rows[0][1] == {
        "category": "nutrition",  # front matter wins over the path segment
        "source_file": "misc/doc-b.md",  # forward slashes, relative to knowledge-base/
        "title": "Doc B",
        "chunk_index": 0,
        "total_chunks": 2,
        "keywords": ["umbral", "vo2max"],
    }
    assert rows[1][1]["chunk_index"] == 1
    assert rows[1][1]["total_chunks"] == 2
    assert rows[0][0].startswith("## Umbral\n")
    assert rows[1][0].startswith("## VO2max\n")


async def test_derived_category_from_path_segment_when_front_matter_lacks_it(first_run):
    del first_run
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            category = (
                await conn.execute(
                    text(
                        "select metadata->>'category' from knowledge_embeddings "
                        "where metadata->>'source_file' = 'training/doc-a.md'"
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    assert category == "training"


async def test_embedding_round_trips_through_database(first_run):
    """The bind-processor proof: write through the pipeline, read back via SQL + ORM."""
    del first_run
    expected = _deterministic_vector(DOC_A_BODY)
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            # Raw SQL read: pgvector stores single precision, so compare with
            # a float32 tolerance rather than exact equality.
            raw = (
                await conn.execute(
                    text(
                        "select embedding::text from knowledge_embeddings "
                        "where metadata->>'source_file' = 'training/doc-a.md'"
                    )
                )
            ).scalar_one()
        assert raw.startswith("[") and raw.endswith("]")
        stored = [float(value) for value in raw[1:-1].split(",")]
        assert len(stored) == 768
        assert all(
            abs(got - want) < 1e-6 for got, want in zip(stored, expected, strict=True)
        )

        async with engine.connect() as conn:
            row_id = (
                (
                    await conn.execute(
                        text(
                            "select id from knowledge_embeddings "
                            "where metadata->>'source_file' = 'training/doc-a.md'"
                        )
                    )
                )
                .scalars()
                .one()
            )

        # And through the ORM itself, as the retrieval half will read it.
        # Note: asyncpg has no codec for vector, so the ORM read returns the
        # pgvector text form; parse it and compare against the same vector.
        from sqlalchemy.ext.asyncio import async_sessionmaker

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            row = await session.get(KnowledgeEmbedding, row_id)
        assert row.content == DOC_A_BODY
        raw_orm = row.embedding
        assert isinstance(raw_orm, str) and len(raw_orm) > 700
        stored_orm = [float(value) for value in raw_orm[1:-1].split(",")]
        assert len(stored_orm) == 768
        assert all(
            abs(got - want) < 1e-6 for got, want in zip(stored_orm, expected, strict=True)
        )
    finally:
        await engine.dispose()


async def test_insert_chunks_rejects_wrong_dimension(first_run):
    del first_run
    engine = create_async_engine(DATABASE_URL)
    doc = parse_document("---\ntitle: x\n---\n\n## s\nbody\n", fallback_title="x")
    try:
        async with engine.begin() as conn:
            with pytest.raises(ValueError, match="dimension mismatch"):
                await insert_chunks(
                    conn,
                    doc=doc,
                    category="c",
                    source_file="dimension-guard-test.md",
                    chunk_texts=["## s\nbody"],
                    embeddings=[[0.0] * 3],
                )
    finally:
        await engine.dispose()


async def test_second_run_skips_everything_already_indexed(first_run, migrated_db):
    del migrated_db
    engine = create_async_engine(DATABASE_URL)
    try:
        before = {
            source_file: await _count_rows(engine, source_file)
            for source_file in CORPUS_SOURCE_FILES
        }
        embedder = FakeEmbedder()  # a fresh embedder: nothing may call the API again
        summary = await run_index(
            first_run["corpus_dir"],
            embedder,
            database_url=DATABASE_URL,
            pace_seconds=0,
        )
        after = {
            source_file: await _count_rows(engine, source_file)
            for source_file in CORPUS_SOURCE_FILES
        }
    finally:
        await engine.dispose()

    assert [result.status for result in summary.results] == [STATUS_SKIPPED] * 3
    assert embedder.calls == []  # resume mode spends zero embedding quota
    assert [result.chunks for result in summary.results] == [2, 2, 1]
    assert after == before == dict(EXPECTED_CHUNKS_PER_FILE)


async def test_force_reindex_replaces_rows_without_duplicates(first_run, migrated_db):
    del migrated_db
    engine = create_async_engine(DATABASE_URL)
    try:
        before = {
            source_file: await _count_rows(engine, source_file)
            for source_file in CORPUS_SOURCE_FILES
        }
        embedder = FakeEmbedder()
        summary = await run_index(
            first_run["corpus_dir"],
            embedder,
            database_url=DATABASE_URL,
            force=True,
            pace_seconds=0,
        )
        after = {
            source_file: await _count_rows(engine, source_file)
            for source_file in CORPUS_SOURCE_FILES
        }
        # Values must be identical, proving delete+insert (not append).
        async with engine.connect() as conn:
            stored = (
                await conn.execute(
                    text(
                        "select metadata->>'source_file', metadata->>'chunk_index', "
                        "embedding::text from knowledge_embeddings "
                        "order by metadata->>'source_file', metadata->>'chunk_index'"
                    )
                )
            ).fetchall()
    finally:
        await engine.dispose()

    assert [result.status for result in summary.results] == [STATUS_OK] * 3
    assert after == before  # same row counts: replaced, not duplicated

    chunk_bodies = {
        ("misc/doc-b.md", "0"): DOC_B_SECTION_1,
        ("misc/doc-b.md", "1"): DOC_B_SECTION_2,
        ("misc/doc-c.md", "0"): DOC_B_SECTION_1,
        ("training/doc-a.md", "0"): DOC_A_BODY,
    }
    chunk_counts = dict(EXPECTED_CHUNKS_PER_FILE)
    assert [(row[0], row[1]) for row in stored] == [
        (source_file, str(index))
        for source_file in ("misc/doc-b.md", "misc/doc-c.md", "training/doc-a.md")
        for index in range(chunk_counts[source_file])
    ]
    chunk_bodies = {
        ("misc/doc-b.md", "0"): DOC_B_SECTION_1,
        ("misc/doc-b.md", "1"): DOC_B_SECTION_2,
        ("misc/doc-c.md", "0"): DOC_C_INTRO,
        ("misc/doc-c.md", "1"): DOC_B_SECTION_1,
        ("training/doc-a.md", "0"): DOC_A_BODY,
    }
    for source_file, chunk_index, embedding_text in stored:
        expected = _deterministic_vector(chunk_bodies[(source_file, chunk_index)])
        got = [float(value) for value in embedding_text[1:-1].split(",")]
        assert all(
            abs(g - w) < 1e-6 for g, w in zip(got, expected, strict=True)
        ), (source_file, chunk_index)


async def test_embed_failure_fails_that_file_and_keeps_others(corpus_dir, clean_corpus_rows):
    del clean_corpus_rows
    # A copy under its own directory name: the relative source_file values
    # ("failing/...") are unique, so resume mode cannot skip them and the
    # embed failure path actually executes for every file.
    failing_dir = corpus_dir.parent / "kb-failing" / "failing"
    failing_dir.mkdir(parents=True, exist_ok=True)
    for path in corpus_dir.rglob("*.md"):
        (failing_dir / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    class BrokenEmbedder(FakeEmbedder):
        async def __call__(self, texts: list[str]) -> list[list[float]]:
            raise ValueError("invalid api key")

    summary = await run_index(
        failing_dir,
        BrokenEmbedder(),
        database_url=DATABASE_URL,
        pace_seconds=0,
    )
    assert summary.failed_files == 3
    assert all(result.error is not None for result in summary.results)
    assert "invalid api key" in summary.results[0].error  # non-quota error surfaces verbatim
