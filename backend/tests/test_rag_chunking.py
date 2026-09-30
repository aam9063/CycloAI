"""Unit tests for the RAG ingestion pipeline's PURE parts — no database.

Covers the pure chunking/front-matter module (``cycloai.rag.chunking``), the
quota-backoff helpers (``cycloai.rag.embeddings``, exercised with fake
embedders and a fake sleep so nothing ever touches Google's API), and the
chunk counts over the real ``knowledge-base/`` corpus (computed without any
embedding call).

The database-dependent integration tests live in
``test_rag_ingest_integration.py`` and skip without ``DATABASE_URL``.
"""

from __future__ import annotations

import importlib.util
import io
import math
from pathlib import Path

import pytest

from cycloai.rag.chunking import (
    MAX_CHUNK_WORDS,
    OVERLAP_WORDS,
    WINDOW_STEP_WORDS,
    build_chunk_metadata,
    chunk_markdown,
    parse_document,
)
from cycloai.rag.embeddings import (
    DEFAULT_RETRY_DELAY_MS,
    MAX_EMBED_ATTEMPTS,
    embed_with_backoff,
    is_quota_error,
    parse_retry_delay_ms,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_BASE_DIR = REPO_ROOT / "knowledge-base"


def _words(n: int, prefix: str = "w") -> str:
    """n distinct words ``prefix000 prefix001 ...`` so window boundaries are exact."""
    return " ".join(f"{prefix}{i:03d}" for i in range(n))


# ---------------------------------------------------------------------------
# Window arithmetic (400/50 sliding window)
# ---------------------------------------------------------------------------


class TestWindowArithmetic:
    def test_constants_match_the_ported_pipeline(self):
        assert MAX_CHUNK_WORDS == 400
        assert OVERLAP_WORDS == 50
        assert WINDOW_STEP_WORDS == MAX_CHUNK_WORDS - OVERLAP_WORDS

    def test_section_within_limit_is_one_chunk(self):
        body = f"## Head\n{_words(400)}"
        assert chunk_markdown(body) == [body.strip()]

    def test_exactly_one_word_over_limit_produces_two_chunks(self):
        body = f"## Head\n{_words(401)}"
        chunks = chunk_markdown(body)
        assert len(chunks) == 2
        # First window: words 0..399. Second: 350..400 (51 words).
        assert chunks[0].split("\n", 1)[1].split() == [f"w{i:03d}" for i in range(400)]
        assert chunks[1].split("\n", 1)[1].split() == [f"w{i:03d}" for i in range(350, 401)]

    def test_sliding_window_sizes_and_overlap_are_exact(self):
        # 950 body words -> windows starting at 0, 350, 700: sizes 400/400/250.
        body = f"## Head\n{_words(950)}"
        chunks = chunk_markdown(body)
        assert len(chunks) == 3
        bodies = [chunk.split("\n", 1)[1].split() for chunk in chunks]
        assert len(bodies[0]) == 400
        assert len(bodies[1]) == 400
        assert len(bodies[2]) == 250
        # Overlap: the OVERLAP_WORDS words before each step are shared.
        assert bodies[0][-OVERLAP_WORDS:] == bodies[1][:OVERLAP_WORDS]
        assert bodies[0][-1] == "w399"
        assert bodies[1][0] == "w350"
        assert bodies[1][-1] == "w749"
        assert bodies[2][0] == "w700"
        assert bodies[2][-1] == "w949"

    def test_short_trailing_window_is_kept(self):
        # 425 words -> windows 0..399 and 350..424 (75 words), nothing dropped.
        body = f"## Head\n{_words(425)}"
        chunks = chunk_markdown(body)
        assert len(chunks) == 2
        assert chunks[1].split("\n", 1)[1].split()[-1] == "w424"


# ---------------------------------------------------------------------------
# Heading retention
# ---------------------------------------------------------------------------


class TestHeadingRetention:
    def test_heading_stays_inside_every_window(self):
        body = f"## Umbral de lactato\n{_words(950)}"
        chunks = chunk_markdown(body)
        assert len(chunks) == 3
        for chunk in chunks:
            assert chunk.startswith("## Umbral de lactato\n")

    def test_small_section_is_verbatim_including_heading(self):
        body = "## Zona 2\nTexto corto de la seccion."
        assert chunk_markdown(body) == [body]

    def test_multiple_sections_each_keep_their_own_heading(self):
        body = f"## Una\n{_words(30)}\n\n## Dos\n{_words(950, prefix='v')}"
        chunks = chunk_markdown(body)
        assert len(chunks) == 4  # 1 small section + 3 windows
        assert chunks[0].startswith("## Una")
        assert all(chunk.startswith("## Dos\n") for chunk in chunks[1:])


# ---------------------------------------------------------------------------
# Documents without ## headings
# ---------------------------------------------------------------------------


class TestDocumentsWithoutHeadings:
    def test_no_headings_short_body_is_single_chunk(self):
        body = _words(100)
        assert chunk_markdown(body) == [body]

    def test_no_headings_oversized_body_still_produces_chunks(self):
        chunks = chunk_markdown(_words(950))
        assert len(chunks) == 3
        assert all(not chunk.startswith("##") for chunk in chunks)
        assert chunks[0].split()[0] == "w000"
        assert chunks[2].split()[-1] == "w949"

    def test_empty_body_produces_no_chunks(self):
        assert chunk_markdown("") == []
        assert chunk_markdown("   \n  ") == []


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------


class TestFrontMatter:
    def test_title_category_and_keywords_are_read(self):
        raw = (
            "---\n"
            "title: Zonas por pulso\n"
            "category: training\n"
            "keywords: [pulso, LTHR, umbral]\n"
            "---\n"
            "\n"
            "## Seccion\nCuerpo del documento.\n"
        )
        doc = parse_document(raw, fallback_title="ignored")
        assert doc.title == "Zonas por pulso"
        assert doc.category == "training"
        assert doc.keywords == ["pulso", "LTHR", "umbral"]
        assert doc.content.strip() == "## Seccion\nCuerpo del documento.".strip()

    def test_missing_category_falls_back_to_path_segment(self):
        raw = "---\ntitle: Algo\ntags: [x]\n---\n\n## S\nCuerpo.\n"
        doc = parse_document(raw, fallback_title="ignored", fallback_category="gym")
        assert doc.category == "gym"

    def test_missing_title_falls_back_to_filename_stem(self):
        raw = "---\nkeywords: [a]\n---\n\n## S\nCuerpo.\n"
        doc = parse_document(raw, fallback_title="zonas-entrenamiento-pulso")
        assert doc.title == "zonas-entrenamiento-pulso"

    def test_missing_keywords_default_to_empty_list(self):
        raw = "---\ntitle: Algo\n---\n\nCuerpo.\n"
        doc = parse_document(raw, fallback_title="x")
        assert doc.keywords == []

    def test_utf8_bom_is_stripped_before_parsing(self):
        raw = "﻿---\ntitle: Con BOM\ncategory: nutrition\n---\n\n## S\nCuerpo.\n"
        doc = parse_document(raw, fallback_title="x")
        assert doc.title == "Con BOM"
        assert doc.category == "nutrition"

    def test_file_without_front_matter_uses_fallbacks(self):
        doc = parse_document("## S\nCuerpo.\n", fallback_title="sin-fm")
        assert doc.title == "sin-fm"
        assert doc.category is None
        assert doc.keywords == []


# ---------------------------------------------------------------------------
# Metadata shape
# ---------------------------------------------------------------------------


class TestMetadataShape:
    def test_metadata_has_exactly_the_six_documented_keys(self):
        meta = build_chunk_metadata(
            category="training",
            source_file="training/zonas-entrenamiento-pulso.md",
            title="Zonas por pulso",
            chunk_index=2,
            total_chunks=6,
            keywords=["pulso", "LTHR"],
        )
        assert meta == {
            "category": "training",
            "source_file": "training/zonas-entrenamiento-pulso.md",
            "title": "Zonas por pulso",
            "chunk_index": 2,
            "total_chunks": 6,
            "keywords": ["pulso", "LTHR"],
        }
        assert set(meta) == {
            "category",
            "source_file",
            "title",
            "chunk_index",
            "total_chunks",
            "keywords",
        }

    def test_source_file_uses_forward_slashes(self):
        meta = build_chunk_metadata(
            category="gym",
            source_file="gym/core-estabilizacion-ciclista.md",
            title="t",
            chunk_index=0,
            total_chunks=1,
            keywords=[],
        )
        assert "\\" not in meta["source_file"]
        assert "/" in meta["source_file"]

    def test_keywords_are_copied_not_aliased(self):
        keywords = ["pulso"]
        meta = build_chunk_metadata(
            category="c",
            source_file="f.md",
            title="t",
            chunk_index=0,
            total_chunks=1,
            keywords=keywords,
        )
        keywords.append("extra")
        assert meta["keywords"] == ["pulso"]


# ---------------------------------------------------------------------------
# Real corpus chunk counts (no embedding API involved)
# ---------------------------------------------------------------------------

# Expected chunk counts over the CURRENT knowledge-base/ corpus, computed
# with this same chunker (parse_document + chunk_markdown, zero API calls).
# The corpus is 24 documents; these numbers lock it: when a document is added
# or edited, recompute and update EXPECTED_CORPUS_CHUNKS.
EXPECTED_CORPUS_CHUNKS: dict[str, int] = {
    "gym/core-estabilizacion-ciclista.md": 9,
    "gym/ejercicios-fuerza-ciclismo.md": 8,
    "gym/movilidad-flexibilidad-ciclista.md": 7,
    "gym/periodizacion-gimnasio-ciclista.md": 7,
    "nutrition/hidratacion-calor-altitud.md": 7,
    "nutrition/macros-ciclismo-por-volumen.md": 7,
    "nutrition/nutricion-intra-entrenamiento.md": 7,
    "nutrition/perdida-peso-sin-perder-rendimiento.md": 6,
    "nutrition/recuperacion-post-entrenamiento.md": 7,
    "nutrition/suplementacion-evidencia-ciclismo.md": 7,
    "physiology/adaptaciones-entrenamiento-aerobico.md": 8,
    "physiology/altitud-calor-adaptaciones.md": 9,
    "physiology/ftp-vo2max-relacion.md": 8,
    "physiology/hrv-monitorizacion.md": 8,
    "physiology/sobreentrenamiento-sintomas.md": 7,
    "training/modelo-pmc-carga-entrenamiento.md": 8,
    "training/plan-base-aerobica-16-semanas.md": 7,
    "training/plan-build-threshold-8-semanas.md": 9,
    "training/plan-peak-gran-fondo-4-semanas.md": 8,
    "training/principios-periodizacion-ciclismo.md": 7,
    "training/recuperacion-activa-protocolos.md": 8,
    "training/sesiones-tipo-z2-z4-z5-vo2max.md": 8,
    "training/zonas-entrenamiento-potencia.md": 7,
    "training/zonas-entrenamiento-pulso.md": 6,
}


class TestRealCorpusChunkCounts:
    def test_corpus_document_count_matches_expectation(self):
        files = sorted(
            p for p in KNOWLEDGE_BASE_DIR.rglob("*")
            if p.is_file() and p.name.endswith(".md")
        )
        assert len(files) == len(EXPECTED_CORPUS_CHUNKS) == 24

    def test_corpus_produces_the_expected_chunk_counts(self):
        counts = {
            path.relative_to(KNOWLEDGE_BASE_DIR).as_posix(): len(
                chunk_markdown(parse_document(path.read_text(encoding="utf-8"),
                                             fallback_title=path.stem).content)
            )
            for path in sorted(
                p for p in KNOWLEDGE_BASE_DIR.rglob("*")
                if p.is_file() and p.name.endswith(".md")
            )
        }
        assert counts == EXPECTED_CORPUS_CHUNKS
        assert sum(counts.values()) == 180


# ---------------------------------------------------------------------------
# Quota handling (fake embedder + fake sleep: no Google API, no real waiting)
# ---------------------------------------------------------------------------


class TestQuotaHandling:
    def test_parse_retry_delay_reads_googles_suggestion(self):
        # 31.66s -> ceil(31660ms) + 1000ms safety = 32660ms, as in the original.
        assert parse_retry_delay_ms("Resource exhausted, please retry in 31.66s") == 32660
        assert parse_retry_delay_ms("Please RETRY IN 0.5 s.") == 1500

    def test_parse_retry_delay_default_without_suggestion(self):
        assert parse_retry_delay_ms("quota exceeded") == DEFAULT_RETRY_DELAY_MS == 45_000

    def test_quota_shape_detection(self):
        for message in (
            "429 Too Many Requests",
            "Resource has been exhausted (resource_exhausted)",
            "Quota exceeded for the project",
            "Rate limit reached",
        ):
            assert is_quota_error(message), message
        assert not is_quota_error("invalid api key")
        assert not is_quota_error("connection reset by peer")

    @pytest.mark.asyncio
    async def test_retries_on_quota_error_and_succeeds(self):
        waits: list[float] = []
        attempts = {"n": 0}

        async def flaky(texts: list[str]) -> list[list[float]]:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError(
                    "429 Resource has been exhausted (e.g. check quota), "
                    "please retry in 31.66s"
                )
            return [[0.0] * 768 for _ in texts]

        async def fake_sleep(seconds: float) -> None:
            waits.append(seconds)

        result = await embed_with_backoff(flaky, ["a"], sleep=fake_sleep, log=lambda *_: None)
        assert attempts["n"] == 3
        assert len(result) == 1
        # Two waits, each Google's suggestion + 1s safety margin.
        assert waits == [32.66, 32.66]

    @pytest.mark.asyncio
    async def test_non_quota_error_fails_immediately(self):
        attempts = {"n": 0}

        async def broken(texts: list[str]) -> list[list[float]]:
            attempts["n"] += 1
            raise ValueError("invalid api key")

        with pytest.raises(ValueError, match="invalid api key"):
            await embed_with_backoff(broken, ["a"], sleep=lambda _s: None, log=lambda *_: None)
        assert attempts["n"] == 1

    @pytest.mark.asyncio
    async def test_gives_up_after_bounded_attempts(self):
        attempts = {"n": 0}
        waits: list[float] = []

        async def always_quotas(texts: list[str]) -> list[list[float]]:
            attempts["n"] += 1
            raise RuntimeError("quota exhausted")

        async def fake_sleep(seconds: float) -> None:
            waits.append(seconds)

        with pytest.raises(RuntimeError, match="quota exhausted"):
            await embed_with_backoff(
                always_quotas, ["a"], sleep=fake_sleep, log=lambda *_: None
            )
        assert attempts["n"] == MAX_EMBED_ATTEMPTS == 5
        assert len(waits) == MAX_EMBED_ATTEMPTS - 1
        assert all(math.isclose(w, 45.0) for w in waits)


# ---------------------------------------------------------------------------
# CLI console encoding (regression: UnicodeEncodeError on Windows cp1252 runs)
# ---------------------------------------------------------------------------


def _load_rag_index_module():
    """Load ``backend/scripts/rag_index.py`` by path (scripts/ is not a package)."""
    script = REPO_ROOT / "backend" / "scripts" / "rag_index.py"
    spec = importlib.util.spec_from_file_location("rag_index_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingStream:
    """Minimal stand-in for sys.stdout that records reconfigure() calls."""

    def __init__(self):
        self.reconfigure_kwargs: list[dict] = []

    def reconfigure(self, **kwargs):
        self.reconfigure_kwargs.append(kwargs)


class TestCliConsoleEncoding:
    """The documented indexing command prints status icons (✓, →, ✗), em
    dashes and Spanish text. On a Windows run whose output codec cannot
    represent them (legacy codepage, e.g. on a piped run), the default
    strict codec raised UnicodeEncodeError AFTER the work was done — the
    file was embedded and committed, then the run died reporting it. The
    fix lives at the CLI entry point: printing is the CLI's concern, and
    the library module stays console-agnostic."""

    def test_entry_point_configures_its_streams(self):
        rag_index = _load_rag_index_module()
        out, err = _RecordingStream(), _RecordingStream()
        rag_index.configure_console_streams(out, err)
        assert out.reconfigure_kwargs == [{"encoding": "utf-8", "errors": "replace"}]
        assert err.reconfigure_kwargs == [{"encoding": "utf-8", "errors": "replace"}]

    def test_entry_point_defaults_to_the_real_std_streams(self):
        rag_index = _load_rag_index_module()
        # Must run against the real sys.stdout/sys.stderr without raising,
        # whatever object the interpreter or the test runner substituted.
        rag_index.configure_console_streams()

    def test_entry_point_tolerates_streams_without_reconfigure(self):
        rag_index = _load_rag_index_module()
        rag_index.configure_console_streams(object(), object())  # must not raise

    def test_configured_stream_no_longer_aborts_on_the_historical_payload(self):
        rag_index = _load_rag_index_module()
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
        rag_index.configure_console_streams(stream)
        # The exact kind of line that crashed the run, accents included.
        stream.write("  ✓ training/zonas-pulso.md — 6 chunk(s) — Ángulos\n")
        stream.flush()
        emitted = buffer.getvalue().decode("utf-8")
        assert "Ángulos" in emitted  # the Spanish text survives
        assert "✓" in emitted  # ...and the icon is emitted too, not dropped
