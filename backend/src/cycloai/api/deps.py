"""Request-scoped dependencies for the CycloAI API.

This module owns the **authentication seam**,
:func:`get_current_athlete`: it resolves the caller's identity and nothing
else. The identity comes ONLY from the session cookie, verified by the
``cycloai.auth.security`` core (JWT, HS256, pinned algorithm). Nothing in the
request body, the query string or the headers may influence it.

Session-cookie contract
-----------------------

The signed session token is delivered in the cookie named
:data:`AUTH_COOKIE_NAME` with:

* ``httponly`` — never readable from JavaScript;
* ``SameSite=Lax`` — sent on top-level navigations, not cross-site posts;
* ``path=/`` — valid across the whole API;
* an explicit ``max_age`` equal to the access-token lifetime
  (:data:`~cycloai.auth.security.ACCESS_TOKEN_TTL`);
* ``Secure`` enabled exactly when ``CYCLOAI_ENV`` is ``production``
  (case-insensitive) — see :func:`auth_cookie_secure`. Every other value
  (unset, ``development``, ``local``, ``test``) leaves ``Secure`` off so the
  cookie works over plain HTTP locally.

Everything here remains deliberately lazy: constructing a model client or an
engine happens at request time, never at import time, so the app can be
imported and built in tests with no database URL and no API key configured.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Final

from fastapi import HTTPException, Request, Response, status

from cycloai.auth.security import ACCESS_TOKEN_TTL, verify_token
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
    "AUTH_COOKIE_MAX_AGE_SECONDS",
    "AUTH_COOKIE_NAME",
    "UNAUTHENTICATED_DETAIL",
    "auth_cookie_secure",
    "clear_auth_cookie",
    "get_current_athlete",
    "get_model_client",
    "get_retrieve",
    "get_session",
    "set_auth_cookie",
]

# Re-exported so routes depend on this module for every request-scoped
# collaborator; the implementation lives in cycloai.db.engine and connects
# lazily on first use (never at import time).
from cycloai.db.engine import get_session as get_session  # noqa: E402

logger = logging.getLogger("cycloai.api")

# ---------------------------------------------------------------------------
# Session cookie
# ---------------------------------------------------------------------------

#: The (single) name of the session cookie. Both the seam that READS it and
#: the routes that SET/CLEAR it must use this constant — never a repeated
#: string literal.
AUTH_COOKIE_NAME: Final[str] = "cycloai_session"

#: Explicit cookie lifetime, matching the access-token lifetime exactly: the
#: cookie and the token inside it expire together.
AUTH_COOKIE_MAX_AGE_SECONDS: Final[int] = int(ACCESS_TOKEN_TTL.total_seconds())

#: Values of ``CYCLOAI_ENV`` for which the cookie is marked ``Secure``.
_PRODUCTION_ENVS: Final[frozenset[str]] = frozenset({"production"})

#: One generic unauthenticated message for every rejected credential state.
#: Missing, malformed, expired and wrongly-signed tokens all look the same to
#: the caller: a distinct message per failure mode would only help attackers.
UNAUTHENTICATED_DETAIL: Final[str] = "Authentication required."


def auth_cookie_secure() -> bool:
    """Whether the session cookie must carry the ``Secure`` attribute.

    ``Secure`` is enabled exactly when the environment is production, read
    from the same ``CYCLOAI_ENV`` flag the codebase already uses, compared
    case-insensitively on the stripped value.
    """
    env = os.environ.get("CYCLOAI_ENV", "").strip().lower()
    return env in _PRODUCTION_ENVS


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the session cookie (httponly, Lax, path=/, explicit max_age)."""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
        secure=auth_cookie_secure(),
    )


def clear_auth_cookie(response: Response) -> None:
    """Expire the session cookie with the same attributes it was set with."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=auth_cookie_secure(),
    )


# ---------------------------------------------------------------------------
# The authentication seam
# ---------------------------------------------------------------------------


async def get_current_athlete(request: Request) -> uuid.UUID:
    """Resolve the identity of the authenticated athlete for this request.

    The identity comes ONLY from the session token carried in the
    :data:`AUTH_COOKIE_NAME` cookie, verified through the auth core
    (:func:`cycloai.auth.security.verify_token`). Nothing in the request
    body, the query string or the headers may influence the result: the
    request object is used solely to read the cookie, and no other request
    data is ever consulted.

    Failure mapping: a missing, malformed, expired or otherwise unverifiable
    token is an UNAUTHENTICATED request, not a server error. The auth core
    deliberately returns ``None`` instead of raising for every verification
    failure, and this dependency respects that: ``None`` — and only an
    absent/failed verification — maps to a generic ``401`` response. No
    exception ever escapes as a ``500`` for a bad credential, and every
    failure mode returns the same generic detail so failure modes cannot be
    enumerated.
    """
    token = request.cookies.get(AUTH_COOKIE_NAME)
    identity = verify_token(token) if token else None
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHENTICATED_DETAIL,
        )
    return identity


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
