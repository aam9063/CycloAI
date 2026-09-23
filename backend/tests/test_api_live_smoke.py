"""LIVE end-to-end smoke test: the workout-generation prompt meets a real model.

OPT-IN — this module is SKIPPED unless the explicit environment flag
``CYCLOAI_LIVE_SMOKE=1`` is set AND ``DATABASE_URL`` is configured, so a plain
``uv run pytest`` never spends API quota. When enabled it runs exactly ONCE:

1. Two tiny synthetic knowledge rows are indexed through the REAL ingestion
   path (``cycloai.rag.ingest.index_file`` with the real ``GeminiEmbedder``)
   so retrieval has something real to return. They are tagged and deletable.
2. The REAL ``POST /generate`` endpoint is called ONCE through the app's
   ``TestClient`` with the REAL model client and REAL retrieval wiring — no
   fakes anywhere on this path.
3. Evidence is PRINTED (status, workout, zone codes, cited sources, prose
   length, findings) rather than asserted, because the point of this run is
   to observe what the model actually does.

Run it exactly once with:

    cd backend
    DATABASE_URL="postgresql://..." CYCLOAI_LIVE_SMOKE=1 \
        uv run pytest tests/test_api_live_smoke.py -s

The synthetic rows are cleaned up in a ``finally`` block, whether the run
succeeds or fails. The API key and the database password are never printed.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

LIVE_FLAG = "CYCLOAI_LIVE_SMOKE"


def _live_requested() -> bool:
    """True only with the explicit opt-in flag AND a resolvable database URL.

    The flag MUST come from the process environment (deliberate, unmistakable
    opt-in). The database URL may come from the environment or from
    ``backend/.env`` through ``Settings`` — the same resolution the
    application itself uses — never from anywhere else. Import-safe: no
    connection is opened here.
    """
    if os.environ.get(LIVE_FLAG) != "1":
        return False
    if os.environ.get("DATABASE_URL"):
        return True
    from cycloai.db.settings import Settings  # noqa: PLC0415 — import-safe

    try:
        return bool(Settings().database_url)
    except Exception:  # noqa: BLE001 — skip loudly rather than crash collection
        return False


pytestmark = pytest.mark.skipif(
    not _live_requested(),
    reason=(
        "opt-in live smoke test: set CYCLOAI_LIVE_SMOKE=1 and a resolvable "
        "DATABASE_URL (environment or backend/.env) to spend real API quota; "
        "a plain run must skip"
    ),
)

# Synthetic knowledge files, tagged by name. ``index_file`` derives
# ``metadata.source_file`` from the filename, which is the exact citable
# identifier the prompt shows the model — and the exact key cleanup deletes.
_SOURCE_FILES = (
    "zz-live-smoke-synthetic-endurance.md",
    "zz-live-smoke-synthetic-recovery.md",
)

_DOCS: dict[str, str] = {
    _SOURCE_FILES[0]: (
        "---\n"
        'title: "LIVE-SMOKE synthetic: resistencia base en zona 2"\n'
        "category: training\n"
        "keywords: [resistencia, zona 2, endurance, cadencia]\n"
        "---\n"
        "\n"
        "## Resistencia base en zona 2\n"
        "\n"
        "La salida de resistencia base se realiza en zona 2 del sistema "
        "declarado por el atleta, a ritmo conversacional y con cadencia alta "
        "alrededor de 90 rpm. La duración típica es de 60 a 120 minutos sobre "
        "terreno llano. Nunca se prescriben magnitudes absolutas: la "
        "intensidad se ancla siempre en el sistema declarado del atleta.\n"
    ),
    _SOURCE_FILES[1]: (
        "---\n"
        'title: "LIVE-SMOKE synthetic: recuperación activa"\n'
        "category: training\n"
        "keywords: [recuperación, regeneración, zona 1, spinning]\n"
        "---\n"
        "\n"
        "## Recuperación activa\n"
        "\n"
        "La sesión de recuperación es muy corta, de 20 a 40 minutos, en la "
        "zona más suave del sistema declarado, con spinning fácil y sin "
        "intensidad. Su único objetivo es regenerar. Queda prohibido "
        "prescribir latidos por minuto o vatios absolutos.\n"
    ),
}

_REQUEST_BODY = {
    "objective": (
        "Salida de resistencia base en zona 2 de 60 minutos, terreno llano, "
        "ritmo conversacional"
    ),
    "thresholds": {"system": "heart_rate", "lthr_bpm": 150},
    "weekly_hours": 8,
    "has_power_meter": False,
}


async def _seed_synthetic_rows(kb_dir: Path) -> None:
    """Index the synthetic docs through the REAL ingestion path.

    Uses the real embedder and the real database; leftover rows from an
    interrupted earlier run are cleared first so the run starts clean.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from cycloai.db.engine import create_engine
    from cycloai.db.settings import Settings
    from cycloai.rag.embeddings import GeminiEmbedder
    from cycloai.rag.ingest import delete_chunks_for_source, index_file

    engine = create_engine(Settings())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    embedder = GeminiEmbedder()
    try:
        async with sessionmaker() as session:
            for name in _SOURCE_FILES:
                await delete_chunks_for_source(session, name)
                await session.commit()
                result = await index_file(
                    session, kb_dir / name, kb_dir, embedder, force=True
                )
                print(f"[seed] {name}: status={result.status} chunks={result.chunks}")
                if result.status != "ok":
                    raise RuntimeError(
                        f"seeding {name} failed: {result.error or 'unknown error'}"
                    )
    finally:
        await engine.dispose()


async def _delete_synthetic_rows_and_confirm() -> None:
    """Delete every synthetic row and CONFIRM the deletion is complete."""
    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from cycloai.db.engine import create_engine
    from cycloai.db.settings import Settings
    from cycloai.rag.ingest import delete_chunks_for_source

    engine = create_engine(Settings())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            for name in _SOURCE_FILES:
                await delete_chunks_for_source(session, name)
            await session.commit()
            for name in _SOURCE_FILES:
                remaining = (
                    await session.execute(
                        select(func.count())
                        .select_from(text("knowledge_embeddings"))
                        .where(
                            text("metadata->>'source_file' = :name"),
                        ),
                        {"name": name},
                    )
                ).scalar_one()
                print(f"[cleanup] rows remaining for {name}: {remaining}")
    finally:
        await engine.dispose()


def _collect_zone_evidence(workout: dict) -> tuple[list[str], set[str]]:
    """Flatten every step target into readable (kind, system, zone/rpe) rows."""
    rows: list[str] = []
    systems: set[str] = set()
    for block in workout.get("blocks") or []:
        for step in block.get("steps") or []:
            target = step.get("target") or {}
            kind = target.get("kind")
            if kind == "zone":
                systems.add(str(target.get("system")))
                rows.append(f"zone {target.get('system')}:{target.get('zone')}")
            else:
                rows.append(f"target kind={kind} payload={target}")
    return rows, systems


def _markdown_indicator_report(prose: str) -> str:
    """Coarse scan of the prose for plain-text-rule violations."""
    markers = {
        "heading '#'": prose.count("#"),
        "bold/italic '*'": prose.count("*"),
        "backtick '`'": prose.count("`"),
        "bullet '- '": sum(1 for line in prose.splitlines() if line.lstrip().startswith("- ")),
        "numbered list": sum(
            1 for line in prose.splitlines() if line[:3].rstrip(".").isdigit() and ". " in line[:4]
        ),
    }
    return ", ".join(f"{label}={count}" for label, count in markers.items())


def test_live_workout_generation_once(tmp_path: Path) -> None:
    """ONE real end-to-end run. Prints evidence; a 4xx/5xx outcome is data."""
    kb_dir = tmp_path
    for name, content in _DOCS.items():
        (kb_dir / name).write_text(content, encoding="utf-8")

    try:
        # 1. Seed through the real ingestion path (real embedder, real DB).
        asyncio.run(_seed_synthetic_rows(kb_dir))

        # 2. ONE real call through the real app wiring.
        from fastapi.testclient import TestClient

        from cycloai.api.app import create_app

        with TestClient(create_app()) as client:
            response = client.post("/generate", json=_REQUEST_BODY)

        # 3. Evidence, not pass/fail.
        print("\n=== LIVE SMOKE EVIDENCE ===")
        print(f"HTTP status: {response.status_code}")
        body = response.json()
        if response.status_code == 200:
            workout = body.get("workout") or {}
            print(f"workout produced: {bool(workout)}")
            zone_rows, zone_systems = _collect_zone_evidence(workout)
            print(f"zone/target choices: {zone_rows}")
            print(f"zone systems used: {sorted(zone_systems)}")
            print(f"sources cited: {workout.get('sources')}")
            print(f"knowledge_used: {body.get('knowledge_used')}")
            prose = body.get("prose") or ""
            print(f"prose length: {len(prose)} chars")
            print(f"prose markdown indicators: {_markdown_indicator_report(prose)}")
            print("--- prose verbatim ---")
            print(prose or "(empty)")
            print("--- end prose ---")
            findings: list[dict] = []
            attempts = None
        elif response.status_code == 422:
            findings = body.get("findings") or []
            attempts = body.get("attempts")
            print(f"gate REJECTED the model output; attempts: {attempts}")
            print("findings (verbatim):")
            for finding in findings:
                print(
                    f"  - source={finding.get('source')} code={finding.get('code')} "
                    f"severity={finding.get('severity')}: {finding.get('message')}"
                )
            print("workout produced: False")
            print("sources cited: (none — no workout)")
            print("prose length: 0 (no prose)")
        else:
            print(f"UNEXPECTED status; body (first 2000 chars): {response.text[:2000]!r}")
            print(f"findings: none available at status {response.status_code}")

        # Only a decisive outcome counts as a completed live run.
        assert response.status_code in (200, 422), (
            f"live run did not reach a decisive outcome: "
            f"status={response.status_code} body={response.text[:2000]!r}"
        )
        _ = findings, attempts
    finally:
        # 4. Cleanup, then confirm — on success AND on failure.
        asyncio.run(_delete_synthetic_rows_and_confirm())
