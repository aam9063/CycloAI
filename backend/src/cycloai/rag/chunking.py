"""Pure markdown chunking and front-matter parsing for RAG ingestion.

No I/O happens here: everything is a pure text-to-text (or text-to-data)
transformation so the whole module is testable without a database, a
filesystem, or the Google API.

Port of the chunker in ``scripts/rag-index.ts`` (the TypeScript original is a
read-only reference):

- Split the body on newlines that precede a ``##`` heading, so every section
  starts at its own heading.
- A section of at most ``MAX_CHUNK_WORDS`` words becomes exactly one chunk.
- A larger section becomes a sliding window of ``MAX_CHUNK_WORDS`` words with
  ``OVERLAP_WORDS`` words of overlap (step ``WINDOW_STEP_WORDS``).
- The ``##`` heading stays inside every chunk so it carries its own title.

Deliberate divergence from the TypeScript original: there, only the FIRST
window of an oversized section contained the heading words; subsequent
windows silently lost them. The load-bearing behaviour here is that every
chunk carries its section title, so the heading line is re-attached to each
window (windows are computed over the section body words only, keeping the
400/50 arithmetic exact).

Front matter (``title``, ``category``, ``keywords``) is parsed with
``python-frontmatter`` (the ``gray-matter`` equivalent). A leading UTF-8 BOM
is stripped first: at least one corpus file carries one and YAML parsing
would otherwise fail to detect the opening ``---``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import frontmatter

MAX_CHUNK_WORDS = 400
OVERLAP_WORDS = 50
WINDOW_STEP_WORDS = MAX_CHUNK_WORDS - OVERLAP_WORDS  # 350

# Split on newlines that precede a ## heading (keeps the ## at the start of
# each section), mirroring the TypeScript `body.split(/\n(?=## )/)`.
_SECTION_SPLIT = re.compile(r"\n(?=## )")
# The heading line is the first line of a section when it starts with "## ".
_HEADING_LINE = re.compile(r"^(## [^\n]*)(\n|$)")


@dataclass(frozen=True)
class ParsedDocument:
    """Front matter plus body of one knowledge-base markdown file."""

    title: str
    category: str | None
    keywords: list[str]
    content: str


def parse_document(
    raw: str,
    fallback_title: str,
    fallback_category: str | None = None,
) -> ParsedDocument:
    """Parse YAML front matter, falling back per field.

    ``title`` falls back to ``fallback_title`` (the filename stem in the
    pipeline), ``category`` to ``fallback_category`` (the first path segment
    under ``knowledge-base/``), and ``keywords`` to an empty list.
    """
    post = frontmatter.loads(raw.lstrip("\ufeff"))
    metadata = post.metadata
    return ParsedDocument(
        title=metadata.get("title") or fallback_title,
        category=metadata.get("category") or fallback_category,
        keywords=[str(keyword) for keyword in (metadata.get("keywords") or [])],
        content=post.content,
    )


def chunk_markdown(body: str) -> list[str]:
    """Split a markdown body (front matter already stripped) into chunks.

    Each ``##`` section with at most ``MAX_CHUNK_WORDS`` words becomes one
    chunk; a larger section becomes a sliding window of ``MAX_CHUNK_WORDS``
    words with ``OVERLAP_WORDS`` words of overlap, with the heading line
    re-attached to every window. A document with no ``##`` headings is one
    section and still produces chunks.
    """
    chunks: list[str] = []
    for section in _SECTION_SPLIT.split(body):
        trimmed = section.strip()
        if not trimmed:
            continue

        match = _HEADING_LINE.match(trimmed)
        heading = match.group(1) if match else ""
        section_body = trimmed[match.end():] if match else trimmed
        words = section_body.split()

        if len(words) <= MAX_CHUNK_WORDS:
            # Small section: the chunk is the section verbatim (heading included).
            chunks.append(trimmed)
            continue

        # Sliding window over the body words; every window is re-titled with
        # the heading so each chunk carries its own section title.
        start = 0
        while True:
            end = min(start + MAX_CHUNK_WORDS, len(words))
            window_text = " ".join(words[start:end])
            chunks.append(f"{heading}\n{window_text}" if heading else window_text)
            if end == len(words):
                break
            start += WINDOW_STEP_WORDS

    return chunks


def build_chunk_metadata(
    *,
    category: str,
    source_file: str,
    title: str,
    chunk_index: int,
    total_chunks: int,
    keywords: list[str],
) -> dict[str, Any]:
    """Metadata written verbatim into the ``knowledge_embeddings.metadata`` JSONB.

    ``source_file`` must be relative to ``knowledge-base/`` and use forward
    slashes (the shape the retrieval half and the idempotency filter rely on).
    """
    return {
        "category": category,
        "source_file": source_file,
        "title": title,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "keywords": list(keywords),
    }
