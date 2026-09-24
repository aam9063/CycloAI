"""Deterministically regenerate the gym corpus fixtures.

Usage (from ``backend/``): ``uv run python scripts/generate_gym_fixtures.py``

Reads the hand-written corpus (``docs/gym.txt``), parses it with
:func:`cycloai.domain.gym_corpus.parse_gym_corpus_file` and writes one JSON
fixture per block into ``tests/fixtures/gym/``. The output is deterministic:
running it twice with an unchanged corpus produces byte-identical files (no
timestamps, sorted keys, stable naming, trailing newline, ``ensure_ascii=False``
for the corpus accents).
"""

from __future__ import annotations

import json
from pathlib import Path

from cycloai.domain.gym_corpus import (
    CORPUS_FILENAME,
    ParsedGymCorpus,
    parse_gym_corpus_file,
)
from cycloai.domain.workout import GymBlock

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "docs" / CORPUS_FILENAME
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "gym"


def fixture_name(index: int, block: GymBlock) -> str:
    return f"{index:02d}-{block.name.value.lower().replace(' ', '-')}.json"


def block_to_dict(block: GymBlock) -> dict:
    """Serialize a block deterministically (pydantic JSON-compatible dump)."""
    return block.model_dump(mode="json")


def main() -> None:
    corpus: ParsedGymCorpus = parse_gym_corpus_file(CORPUS_PATH)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for index, block in enumerate(corpus.blocks, start=1):
        payload = (
            json.dumps(
                block_to_dict(block),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        path = FIXTURE_DIR / fixture_name(index, block)
        path.write_text(payload, encoding="utf-8", newline="\n")
    print(f"wrote {len(corpus.blocks)} fixtures to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
