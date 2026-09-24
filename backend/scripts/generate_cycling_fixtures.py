"""Deterministically regenerate the cycling corpus fixtures.

Usage (from ``backend/``): ``uv run python scripts/generate_cycling_fixtures.py``

Reads the measured corpus (``docs/EJEMPLO DE ENTRENAMIENTO PARA CICLISMO.txt``),
parses it with :func:`cycloai.domain.cycling_corpus.parse_cycling_corpus_file` and
writes one JSON fixture per workout into ``tests/fixtures/cycling/``. The output
is deterministic: running it twice with an unchanged corpus produces
byte-identical files (no timestamps, sorted keys, stable naming, trailing
newline, ``ensure_ascii=False`` for the corpus accents).
"""

from __future__ import annotations

import json
from pathlib import Path

from cycloai.domain.cycling_corpus import (
    CORPUS_FILENAME,
    ParsedWorkout,
    parse_cycling_corpus_file,
    parsed_workout_to_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "docs" / CORPUS_FILENAME
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "cycling"


def fixture_name(index: int, parsed: ParsedWorkout) -> str:
    if parsed.label is not None:
        return f"{index:02d}-{parsed.label.lower()}.json"
    return f"{index:02d}-unlabelled.json"


def main() -> None:
    corpus = parse_cycling_corpus_file(CORPUS_PATH)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for index, parsed in enumerate(corpus.workouts, start=1):
        payload = (
            json.dumps(
                parsed_workout_to_dict(parsed),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        path = FIXTURE_DIR / fixture_name(index, parsed)
        path.write_text(payload, encoding="utf-8", newline="\n")
    print(f"wrote {len(corpus.workouts)} fixtures to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
