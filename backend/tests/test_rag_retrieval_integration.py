"""Integration tests for the RAG retrieval half — needs PostgreSQL + pgvector.

The WHOLE module is skipped when ``DATABASE_URL`` is not set, with the same
disposable-database guard ``test_db_integration.py`` uses. The schema is
brought up with ``alembic upgrade head`` (idempotent, non-destructive).

Isolation: everything runs inside ONE transaction on ONE connection that is
rolled back at the end of the module. The fixture first deletes every
``knowledge_embeddings`` row *inside that transaction*, so the tests see a
fully controlled corpus while the target database (which may be the
long-lived ``cycloai_dev``) is left byte-for-byte unchanged on disk.

The corpus uses hand-crafted 768-dim vectors built from two basis
directions, so cosine similarity against the fixed query vector is designed,
not random:

- Doc A: cosine ~0.994 vs query — vector rank 1; FTS matches 2 of the 3
  query terms, so under ``websearch_to_tsquery``'s AND semantics it does not
  qualify for the FTS leg at all.
- Doc B: cosine ~0.814 — vector rank 3; the ONLY doc containing all 3 query
  terms, so FTS rank 1.
- Doc D: cosine ~0.842 — vector rank 2, FTS matches nothing.
- Doc C: cosine 0.0 — BELOW the 0.65 threshold (never in the vector leg);
  the FTS-rescue proof uses the single-term query "ftp".

The hand-off proof: an embedding written through the P3a insert path is read
back through the ORM as the pgvector TEXT STRING and parsed intact with
:func:`cycloai.rag.retrieval.parse_pgvector_text` — no codec is registered.
"""

from __future__ import annotations

import asyncio

import alembic.command
import alembic.config
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine

from cycloai.db.models import KnowledgeEmbedding
from cycloai.rag.chunking import ParsedDocument
from cycloai.rag.ingest import insert_chunks
from cycloai.rag.retrieval import parse_pgvector_text, retrieve_chunks
from cycloai.rag.search import search_knowledge_base
from test_db_integration import BACKEND_DIR, DATABASE_URL, _assert_disposable_database

pytestmark = [
    pytest.mark.skipif(
        DATABASE_URL is None,
        reason="DATABASE_URL not set: database integration tests need a running PostgreSQL",
    ),
    # One event loop per module: the module-scoped engine/connection must not
    # be shared across per-test loops (asyncpg connections are loop-bound).
    pytest.mark.asyncio(loop_scope="module"),
]

if DATABASE_URL is not None:
    _assert_disposable_database(DATABASE_URL)


def _mixture(primary: float, secondary: float) -> list[float]:
    """768-dim vector on the e0/e1 plane; cosine vs e0 is designed, not random."""
    vector = [0.0] * 768
    vector[0] = primary
    vector[1] = secondary
    return vector


QUERY_VECTOR = _mixture(1.0, 0.0)
VEC_A = _mixture(0.9, 0.1)  # cos ~0.994: vector rank 1
VEC_B = _mixture(0.7, 0.5)  # cos ~0.814: vector rank 3
VEC_D = _mixture(0.78, 0.5)  # cos ~0.842: vector rank 2
VEC_C = _mixture(0.0, 1.0)  # cos 0.0: below the 0.65 threshold — FTS-only

DOC_A = ParsedDocument(
    title="Doc A",
    category="training",
    keywords=[],
    content="Plan de entrenamiento para subir el umbral.",  # matches 2 query terms
)
DOC_B = ParsedDocument(
    title="Doc B",
    category="training",
    keywords=[],
    content="El entrenamiento de ftp y el umbral funcional.",  # matches all 3 -> fts rank 1
)
DOC_C = ParsedDocument(
    title="Doc C",
    category="training",
    keywords=[],
    content="El ftp es potencia sostenida.",  # matches 1 query term -> fts rank 3
)
DOC_D = ParsedDocument(
    title="Doc D",
    category="training",
    keywords=[],
    content="La nutricion ayuda a la recuperacion muscular.",  # matches nothing
)

CORPUS: dict[str, tuple[ParsedDocument, list[float]]] = {
    "retrieval/doc-a.md": (DOC_A, VEC_A),
    "retrieval/doc-b.md": (DOC_B, VEC_B),
    "retrieval/doc-c.md": (DOC_C, VEC_C),
    "retrieval/doc-d.md": (DOC_D, VEC_D),
}


class _FakeQueryEmbedder:
    """Returns the designed query vector for every text; records calls."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = list(vector) if vector is not None else QUERY_VECTOR
        self.calls: list[str] = []

    async def __call__(self, text_value: str) -> list[float]:
        self.calls.append(text_value)
        return list(self.vector)


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
async def isolated_conn(migrated_db) -> AsyncConnection:
    """One connection holding an open transaction over an EMPTIED table.

    The delete happens inside the transaction and the whole module rolls
    back, so pre-existing rows (P3a corpus, anything long-lived) survive on
    disk while these tests see exactly the synthetic corpus.
    """
    del migrated_db
    engine = create_async_engine(DATABASE_URL)
    conn = await engine.connect()
    trans = await conn.begin()
    await conn.execute(text("delete from knowledge_embeddings"))
    try:
        yield conn
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def empty_corpus_result(isolated_conn) -> str:
    """Run the entry point against the emptied table BEFORE the corpus lands."""
    return await search_knowledge_base(
        "entrenamiento de umbral",
        embed=_FakeQueryEmbedder(),
        db=isolated_conn,
    )


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def corpus(isolated_conn, empty_corpus_result) -> AsyncConnection:
    """Insert the synthetic corpus (fixture ordering: empty-table search ran first)."""
    del empty_corpus_result
    for source_file, (doc, vector) in CORPUS.items():
        await insert_chunks(
            isolated_conn,
            doc=doc,
            category=doc.category or "unknown",
            source_file=source_file,
            chunk_texts=[doc.content],
            embeddings=[vector],
        )
    return isolated_conn


# RRF k=60 expectations for the hybrid query "entrenamiento ftp umbral".
# websearch_to_tsquery('spanish', ...) ANDs bare terms, so only Doc B (which
# contains all three lexemes) enters the FTS leg — rank 1. Vector leg (cosine
# > 0.65): A rank 1, D rank 2, B rank 3; Doc C (cosine 0) never enters it.
#   B: 1/(60+1) + 1/(60+3)   — worst vector rank, best FTS rank
#   A: 1/(60+1)              — vector only
#   D: 1/(60+2)              — vector only
# B beats the vector-leg leader precisely because the FUSED score decides.
EXPECTED_FUSED = {
    DOC_B.content: 1 / 61 + 1 / 63,
    DOC_A.content: 1 / 61,
    DOC_D.content: 1 / 62,
}
EXPECTED_ORDER = [DOC_B.content, DOC_A.content, DOC_D.content]


async def test_empty_corpus_returns_empty_without_raising(empty_corpus_result):
    assert empty_corpus_result == ""


async def test_hybrid_query_returns_chunks_in_fused_rrf_order(corpus):
    rows = await retrieve_chunks(
        corpus, _FakeQueryEmbedder(), "entrenamiento ftp umbral", match_count=4
    )
    # B (fts rank 1, worst vector rank) > A (vector rank 1 alone) > D
    # (vector rank 2 alone): the fused RRF score decides, not either leg.
    assert [row.content for row in rows] == EXPECTED_ORDER
    for row in rows:
        assert row.score == pytest.approx(EXPECTED_FUSED[row.content], rel=1e-9)
    # Doc C matches no leg for this query (AND semantics + cosine 0).
    assert DOC_C.content not in [row.content for row in rows]


async def test_term_below_cosine_threshold_surfaces_via_fts(corpus):
    """The 0.65-threshold-on-one-leg design: an FTS-only chunk is still findable."""
    rows = await retrieve_chunks(corpus, _FakeQueryEmbedder(), "ftp", match_count=4)
    by_content = {row.content: row for row in rows}
    # Doc C sits at cosine 0.0 — it can NEVER enter the vector leg — yet the
    # FTS leg surfaces it. Its score is purely an FTS RRF term: 1/(60+rank)
    # for a rank in [1, 2] (B matches "ftp" too; both ranks are admissible).
    assert DOC_C.content in by_content
    assert by_content[DOC_C.content].score in (
        pytest.approx(1 / 61, rel=1e-9),
        pytest.approx(1 / 62, rel=1e-9),
    )


async def test_search_knowledge_base_formats_real_rpc_rows(corpus):
    formatted = await search_knowledge_base(
        "entrenamiento ftp umbral", embed=_FakeQueryEmbedder(), db=corpus
    )
    assert formatted.startswith("[Conocimiento 1 — Doc B]\n")
    assert "\n\n---\n\n[Conocimiento 2 — Doc A]\n" in formatted


async def test_embedding_round_trips_through_orm_as_pgvector_text(corpus):
    """The codec decision, proven: the ORM read is a text string; parse it in place."""
    row_id = (
        await corpus.execute(
            text(
                "select id from knowledge_embeddings "
                "where metadata->>'source_file' = 'retrieval/doc-a.md'"
            )
        )
    ).scalar_one()

    # Participates in the module transaction: sees the uncommitted corpus.
    async with AsyncSession(corpus, expire_on_commit=False) as session:
        stored = await session.get(KnowledgeEmbedding, row_id)

    assert stored is not None
    assert stored.content == DOC_A.content
    # asyncpg has no pgvector codec: the ORM hands back pgvector's text form.
    assert isinstance(stored.embedding, str)
    assert stored.embedding.startswith("[") and stored.embedding.endswith("]")
    parsed = parse_pgvector_text(stored.embedding)
    assert len(parsed) == 768
    assert all(
        abs(got - want) < 1e-6 for got, want in zip(parsed, VEC_A, strict=True)
    )
