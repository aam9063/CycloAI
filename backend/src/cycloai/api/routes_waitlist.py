"""The pre-launch waitlist endpoint: ``POST /waitlist``.

This route is deliberately ANONYMOUS: the waitlist is filled in by landing-page
visitors who have no account and no session, so there is NO authentication
dependency here and a missing session cookie is never an error.

Validation contract — the DATABASE is the single authority:

The ``waitlist`` table carries the ``waitlist_email_shape`` CHECK constraint
(length bounds, an ``@`` that is not the first character, a dot in the domain
part, and a bounded optional ``source``), translated from the original
Supabase RLS ``WITH CHECK`` precisely so the shape rules live at the data
layer. This endpoint does NOT reimplement those rules in Python — two copies
of one rule drift, and then the API accepts what the database rejects or the
reverse. The request model (:class:`WaitlistIn`) therefore carries no shape
rules at all: the row is inserted as given and the database's verdict is the
only gate.

Outcome mapping:

* **accepted** → ``202`` with a minimal acknowledgement;
* **shape violation** (malformed email, oversized ``source``) → ``422`` with a
  clear message, mapped from the database raising the CHECK constraint —
  never a ``500``;
* **duplicate email** → the SAME ``202`` acknowledgement. The unique index is
  on ``lower(email)``, so the same address in different casing is the same
  row. A pre-launch waitlist has no real enumeration consequence, but a
  double-submit from the landing page must not look like an error to the
  visitor, so a repeat signup is deliberately idempotent and indistinguishable
  from a first signup. This is a product decision, made explicit here.

Response contract: the body NEVER echoes the stored row or anything about the
list — no id, no timestamps, no count, not even the submitted email. The list
is consumed by nobody through this API; there is no read endpoint.

**Known gap — NO rate limiting.** This backend has no rate-limiting
infrastructure, and an in-process limiter in a multi-worker deployment would
give false assurance (each worker gets its own budget), which is worse than a
documented absence. This is a public anonymous endpoint: abuse mitigation
(per-IP throttling) must be provided at the edge (reverse proxy / WAF) before
it is exposed.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.api.deps import get_session
from cycloai.db.models import Waitlist

__all__ = ["WAITLIST_ACK_DETAIL", "router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

#: The one acknowledgement every success returns — fresh signup or duplicate
#: alike, so the response carries no signal about who is already on the list.
WAITLIST_ACK_DETAIL = "You are on the waitlist."

#: The database-side authorities, by constraint name. The route never
#: re-evaluates the rules they encode; it only interprets WHICH constraint
#: rejected the row.
_SHAPE_CONSTRAINT = "waitlist_email_shape"
_UNIQUE_CONSTRAINT = "waitlist_email_unique"


class WaitlistIn(BaseModel):
    """The signup body, with NO shape rules of its own.

    Deliberately no length bounds, no pattern, no trimming: the
    ``waitlist_email_shape`` CHECK constraint in the database is the single
    authority for the email and ``source`` rules, and duplicating them here
    would create a second rule that can drift. An oversized or malformed value
    reaches the database and comes back as a mapped client error.
    """

    email: str
    source: str | None = None


class WaitlistAck(BaseModel):
    """The minimal acknowledgement. Nothing about the row or the list."""

    detail: str


def _constraint_name(exc: IntegrityError) -> str | None:
    """Best-effort read of the violated constraint's name from the driver.

    Covers the two drivers this project may use: psycopg exposes it as
    ``diag.constraint_name``, while asyncpg (the project's actual driver)
    exposes ``constraint_name`` on its own exception, which SQLAlchemy wraps
    — so the ``__cause__`` chain is walked until a name surfaces. ``None``
    means "unattributable", which the caller must treat as unexpected —
    never silently as one of the known constraints.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc.orig if exc.orig is not None else exc]
    while pending:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        diag = getattr(current, "diag", None)
        name = getattr(diag, "constraint_name", None) or getattr(
            current, "constraint_name", None
        )
        if name:
            return str(name)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
    return None


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WaitlistAck,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": (
                "The database's waitlist shape rules rejected the email or "
                "the source value."
            ),
        },
    },
    summary="Join the pre-launch waitlist (anonymous, no session required).",
)
async def join_waitlist(
    body: WaitlistIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WaitlistAck:
    """Insert the signup and let the database decide whether it is valid.

    The row is inserted exactly as submitted; the ``waitlist_email_shape``
    CHECK and the ``lower(email)`` unique index are the only authorities. A
    CHECK violation maps to ``422``, a unique violation to the same ``202``
    acknowledgement (idempotent duplicate), and anything else is an
    unexpected storage failure mapped to a generic ``500``.
    """
    session.add(Waitlist(email=body.email, source=body.source))
    try:
        await session.commit()
    except IntegrityError as exc:
        # The commit is deliberately INSIDE the route: the constraint verdict
        # must be observable here to be mapped. A failed flush leaves the
        # session unable to commit again, so it is rolled back before the
        # request boundary (``get_session``) commits on success — otherwise
        # the cleanup commit would raise ``PendingRollbackError``.
        await session.rollback()
        constraint = _constraint_name(exc)
        if constraint == _UNIQUE_CONSTRAINT:
            # Already on the list (case-insensitively): idempotent success,
            # by explicit product decision — see the module docstring.
            return WaitlistAck(detail=WAITLIST_ACK_DETAIL)
        if constraint == _SHAPE_CONSTRAINT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The email or source does not meet the waitlist "
                    "requirements."
                ),
            ) from None
        logger.exception("waitlist insert failed with an unexpected constraint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The request could not be completed.",
        ) from None
    return WaitlistAck(detail=WAITLIST_ACK_DETAIL)
