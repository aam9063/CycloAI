"""The account self-deletion endpoint: ``DELETE /account``.

This endpoint replaces the deleted Supabase Edge Function that called
``admin.deleteUser``: deleting one's own account is a user right (and, in
several jurisdictions, an obligation), so the capability must live behind
our own API before the frontend stops talking to Supabase.

Outcome mapping is deliberately narrow and honest:

* **unauthenticated** → ``401`` from the auth seam (one generic detail);
* **success** → ``200`` with a short confirmation, and the session cookie
  CLEARED — leaving a valid cookie pointing at a deleted account is exactly
  the confusing half-logged-in state the auth routes' cookie contract
  forbids;
* **account already gone** → ``404`` ("Account not found."), consistent
  with how every other endpoint treats an absent row, and the cookie is
  cleared there too: a token for a deleted account still verifies (the
  auth core checks signature and expiry, not database liveness), so this
  is the reachable state a client lands in by retrying after success.

Scope, stated as boundaries rather than afterthoughts:

* The identity comes ONLY from the verified session token. There is no
  path parameter, query parameter or body field that can name a target: an
  endpoint that could delete someone else's account would be a
  catastrophe, not a feature. The ``users`` row deleted is always the
  caller's own.
* The deletion relies on the schema's ``ON DELETE CASCADE`` FKs
  (``profiles.id``, ``conversations.user_id``, ``messages.user_id`` —
  P2 initial schema), so removing the ``users`` row removes the profile,
  conversations and messages with it. The schema dependency is PROVEN,
  not assumed: ``test_account_integration.py`` asserts, with fresh reads
  against a real database, that all four row kinds are gone.
* There is deliberately NO administrative "delete another user" path
  here, not even as a hidden parameter. If an admin capability is ever
  needed, it is a separate feature with its own authorization model —
  it must not grow quietly out of a self-service endpoint.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from cycloai.api.deps import clear_auth_cookie, get_current_athlete, get_session
from cycloai.db.models import User
from cycloai.db.repositories import bind_session_user

__all__ = ["delete_account_row", "router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(prefix="/account", tags=["account"])

#: One generic detail for the "already deleted" outcome, in the same voice
#: as the other endpoints' absent-row errors.
_ACCOUNT_NOT_FOUND_DETAIL = "Account not found."

CallerDep = Annotated[uuid.UUID, Depends(get_current_athlete)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def delete_account_row(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Delete the ``users`` row for ``user_id``; ``True`` if a row was removed.

    A module-level seam (like the repositories elsewhere) so tests can
    substitute it without a database. The statement deletes EXACTLY one
    targetable row — ``user_id`` comes from the verified token upstream and
    the ``WHERE`` clause is the only selector — and the surrounding
    ``ON DELETE CASCADE`` FKs take the profile, conversations and messages
    with it (proven by the integration tests, not assumed here).
    """
    result = await session.execute(delete(User).where(User.id == user_id))
    return bool(result.rowcount)


@router.delete(
    "",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "The account has already been deleted. The session cookie is "
                "cleared in this case too: a token for a deleted account "
                "still verifies, so the caller must not be left holding it."
            )
        },
    },
    summary="Delete the authenticated athlete's own account and end the session.",
)
async def delete_account(
    response: Response,
    caller_id: CallerDep,
    session: SessionDep,
) -> Response:
    """Delete the caller's own account and clear the session cookie.

    The caller id comes from :func:`cycloai.api.deps.get_current_athlete`
    (verified token only) and is bound onto the session before any storage
    access, keeping the session contract uniform with every other
    authenticated route. The delete statement itself is filtered by that
    same token-derived id — the request carries no other input that could
    select a target, so the body cannot influence WHICH account is deleted.

    On success the session cookie is cleared with the same attributes the
    auth routes use (:func:`cycloai.api.deps.clear_auth_cookie`). When the
    account is already gone the response is a ``404`` with the cookie ALSO
    cleared — built as a direct :class:`~starlette.responses.JSONResponse`
    because a raised ``HTTPException`` would discard headers set on the
    injected ``Response``.
    """
    bind_session_user(session, caller_id)
    try:
        deleted = await delete_account_row(session, caller_id)
    except Exception:  # noqa: BLE001 - never leak storage errors to callers
        logger.exception("account deletion failed unexpectedly")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The request could not be completed.",
        ) from None

    if not deleted:
        # Already deleted (e.g. a retry after success). Consistent with the
        # other endpoints' treatment of absent rows (404), and still clears
        # the cookie: the token points at an account that no longer exists.
        not_found = JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": _ACCOUNT_NOT_FOUND_DETAIL},
        )
        clear_auth_cookie(not_found)
        return not_found

    # Transaction ownership: the shared session dependency
    # (``cycloai.db.engine.get_session``) commits at the request boundary,
    # so this explicit commit is redundant in production. It is kept ONLY
    # because the integration tests override ``get_session`` with a bare,
    # non-committing session factory (same reason as the conversation
    # routes); remove it when that override goes away.
    await session.commit()

    cleared = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"detail": "Account deleted."},
    )
    clear_auth_cookie(cleared)
    return cleared
