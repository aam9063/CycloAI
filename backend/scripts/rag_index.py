"""CLI entry point for RAG indexing (offline, developer-run tooling).

Port of ``scripts/rag-index.ts`` main() (read-only reference).

Run from ``backend/``::

    uv run python scripts/rag_index.py           # resume: skips indexed files
    uv run python scripts/rag_index.py --force   # re-embed everything

Requires ``GOOGLE_GENERATIVE_AI_API_KEY`` (process environment or
``backend/.env``) and ``DATABASE_URL`` pointing at a disposable database.
The key is read through the settings layer, never hardcoded, never printed.

Exit codes: 0 success, 1 configuration/missing-content error or at least one
failed file, 130 on Ctrl-C.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_KB_DIR = REPO_ROOT / "knowledge-base"


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Index every knowledge-base/*.md file into knowledge_embeddings "
            "(gemini-embedding-001, 768 dims, RETRIEVAL_DOCUMENT)."
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-embed everything, replacing each file's existing rows",
    )
    parser.add_argument(
        "--knowledge-base",
        type=Path,
        default=DEFAULT_KB_DIR,
        help=f"knowledge base directory (default: {DEFAULT_KB_DIR})",
    )
    args = parser.parse_args()

    # Imported lazily so --help stays free of any dependency side effects.
    from cycloai.rag.embeddings import GeminiEmbedder
    from cycloai.rag.ingest import run_index

    if not args.knowledge_base.is_dir():
        print(
            f"Error: el directorio knowledge-base no existe en {args.knowledge_base}\n"
            "Los archivos de contenido deben ser creados antes de ejecutar este script.",
            file=sys.stderr,
        )
        return 1

    try:
        embedder: GeminiEmbedder = GeminiEmbedder()
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        summary = await run_index(
            args.knowledge_base,
            embedder,
            force=args.force,
        )
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 1 if summary.failed_files > 0 else 0


def main() -> None:
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
