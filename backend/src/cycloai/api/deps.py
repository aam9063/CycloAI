"""Request-scoped dependencies for the CycloAI API.

This module owns the **authentication seam** between phase P4b (this slice)
and phase P5 (real authentication). Everything here is deliberately lazy:
constructing a model client or an engine happens at request time, never at
import time, so the app can be imported and built in tests with no database
URL and no API key configured.

The production guard
--------------------

The development stub below is guarded by the explicit environment flag
``CYCLOAI_ENV``:

* unset, ``development``, ``local``, ``test`` → the stub is served;
* ``production`` (case-insensitive) → the stub REFUSES to run and raises.

The flag is documented here and in the deployment runbook: setting
``CYCLOAI_ENV=production`` before phase P5 lands must fail loudly, never
silently serve unauthenticated requests.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator

from fastapi import HTTPException, status

from cycloai.db.engine import get_engine
from cycloai.generator.client import GeminiGeneratorClient
from cycloai.generator.generate import EMPTY_KNOWLEDGE, ModelClient, RetrieveFn
from cycloai.rag.retrieval import (
    GeminiQueryEmbedder,
    RetrievedKnowledge,
    render_retrieved_knowledge,
    retrieve_chunks,
)

__all__ = [
    "DEVELOPMENT_STUB_ATHLETE_ID",
    "get_current_athlete",
    "get_model_client",
    "get_retrieve",
    "get_session",
]

# Re-exported so routes depend on this module for every request-scoped
# collaborator; the implementation lives in cycloai.db.engine and connects
# lazily on first use (never at import time).
from cycloai.db.engine import get_session as get_session  # noqa: E402

logger = logging.getLogger("cycloai.api")

#: Values of ``CYCLOAI_ENV`` under which the development stub may be served.
_STUB_ALLOWED_ENVS = frozenset({"", "development", "local", "test"})

#: Fixed identity served by the development stub. It exists ONLY so the
#: request path can exercise the ownership guard (session binding + profile
#: repository) before real authentication exists. It is not a real athlete
#: and must never be trusted as one.
DEVELOPMENT_STUB_ATHLETE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d3")


async def get_current_athlete() -> AsyncIterator[uuid.UUID]:
    """Yield the identity of the authenticated athlete for this request.

    **THIS IS NOT AN AUTHORIZATION MECHANISM.** This dependency is a
    development stub only. It performs no credential check, no token
    validation, and no identity verification of any kind: it returns a fixed
    development identity so the request path can be wired end to end before
    phase P5. Real authentication (P5) replaces exactly this one function —
    and until it does, anyone who can reach the API gets the stub identity.

    Guard: when the environment flag ``CYCLOAI_ENV`` is ``production``, the
    stub refuses to run and raises, so a misconfigured production deployment
    can never silently serve unauthenticated requests.

    Yields:
        A fixed development athlete id (see
        :data:`DEVELOPMENT_STUB_ATHLETE_ID`).

    Raises:
        RuntimeError: if ``CYCLOAI_ENV`` is ``production`` — the stub must
            never serve in production; real authentication (P5) is required.
    """
    env = os.environ.get("CYCLOAI_ENV", "").strip().lower()
    if env not in _STUB_ALLOWED_ENVS:
        raise RuntimeError(
            "CYCLOAI_ENV="
            f"{os.environ.get('CYCLOAI_ENV')!r} refuses the development "
            "authentication stub: real authentication (phase P5) must be "
            "installed before the API may serve in this environment. The "
            "stub performs NO credential verification."
        )
    yield DEVELOPMENT_STUB_ATHLETE_ID


async def get_model_client() -> ModelClient:
    """Provide the pipeline's model callable, built lazily at request time.

    Construction resolves the API key; a missing key is a server
    configuration problem and is reported generically — never with the
    underlying exception text, which could name configuration details.
    """
    try:
        return GeminiGeneratorClient()
    except Exception:  # noqa: BLE001 - never leak config errors to callers
        logger.exception("model client construction failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Workout generation is not available on the server.",
        ) from None


async def get_retrieve() -> RetrieveFn:
    """Provide the pipeline's retrieval callable, wired to citable retrieval.

    The callable returns ONE :class:`~cycloai.rag.retrieval.RetrievedKnowledge`
    built by :func:`cycloai.rag.retrieval.render_retrieved_knowledge` from the
    rows returned by :func:`cycloai.rag.retrieval.retrieve_chunks`, so the
    knowledge displayed to the model and the citation set the gate checks come
    from the SAME retrieval result — the single-source-of-truth property that
    keeps the model from being asked to cite something it was never shown.
    Queries are embedded with :class:`~cycloai.rag.retrieval.GeminiQueryEmbedder`
    (``RETRIEVAL_QUERY`` task type), constructed lazily on first use so a
    missing API key degrades to a retrieval failure instead of an import-time
    or dependency-time error.

    Degradation contract: an empty retrieval result yields the module's own
    :data:`~cycloai.generator.generate.EMPTY_KNOWLEDGE`, and a retrieval
    failure propagates to the pipeline, whose own never-throw guard logs the
    error and continues the generation without knowledge. This callable does
    NOT swallow exceptions itself — doing so would double-wrap the pipeline's
    degradation and hide the failure from its log.
    """

    embedder: GeminiQueryEmbedder | None = None

    async def retrieve(query: str) -> RetrievedKnowledge:
        nonlocal embedder
        if embedder is None:
            embedder = GeminiQueryEmbedder()
        rows = await retrieve_chunks(get_engine(), embedder, query)
        if not rows:
            return EMPTY_KNOWLEDGE
        return render_retrieved_knowledge(rows)

    return retrieve

