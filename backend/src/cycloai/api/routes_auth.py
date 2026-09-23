"""The auth endpoints: ``POST /auth/register``, ``POST /auth/login``,
``POST /auth/logout``.

Outcome mapping is deliberately narrow and honest:

* **register success** → ``201`` with the created identity, and the session
  cookie set (the caller is logged in immediately);
* **duplicate email** → ``409``, mapped from the service's typed
  :class:`~cycloai.auth.service.EmailAlreadyRegisteredError`;
* **password-policy rejection** → ``400``, mapped from
  :class:`~cycloai.auth.security.PasswordValidationError` — a DISTINCT status
  from 409 so "bad password" can never be confused with "email taken";
* **login failure** → ``401`` with ONE generic body. The service already
  makes a wrong password and an unknown email indistinguishable; this layer
  has a single failure code path and must not undo that with a "more
  helpful" message;
* **unexpected failure** → generic ``500``, no exception text.

No response here ever echoes the password, the stored hash or the session
token: the token is delivered ONLY as the httponly session cookie.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from cycloai.api.deps import (
    clear_auth_cookie,
    get_session,
    set_auth_cookie,
)
from cycloai.auth.security import MAX_PASSWORD_LENGTH, PasswordValidationError, create_token
from cycloai.auth.service import EmailAlreadyRegisteredError, authenticate_user, register_user

__all__ = ["router"]

logger = logging.getLogger("cycloai.api")

router = APIRouter(prefix="/auth", tags=["auth"])

#: One generic message for every login failure. A distinct "unknown email"
#: message would let callers enumerate which emails have accounts — the
#: service's anti-enumeration contract extends to this layer verbatim.
_LOGIN_FAILURE_DETAIL = "Invalid email or password."


class EmailPasswordIn(BaseModel):
    """The register/login request body: an email and a password.

    Validation is intentionally light here; the real rules (case-insensitive
    uniqueness, password policy) live in the service, which is the single
    authority for both outcomes.
    """

    email: str = Field(min_length=3, max_length=320)
    # The upper bound mirrors the auth core's policy bound so absurdly long
    # passwords are refused at the boundary before any hashing work is done.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email", "password")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class UserOut(BaseModel):
    """The identity a register/login success returns: id and email only.

    Deliberately NOT the password, the hash, or any token.
    """

    id: uuid.UUID
    email: str


def _unexpected_failure(operation: str) -> HTTPException:
    logger.exception("%s failed unexpectedly", operation)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The request could not be completed.",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "The password violates the password policy.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "An account with this email already exists.",
        },
    },
    summary="Create an account and start an authenticated session.",
)
async def register(
    body: EmailPasswordIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserOut:
    """Create the account through the service, then issue a session.

    The account creation itself is the service's responsibility (hashing,
    normalization, uniqueness). On success the HTTP layer issues the session
    token and delivers it as the session cookie — never in the body.
    """
    try:
        identity = await register_user(session, email=body.email, password=body.password)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    except PasswordValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The password does not meet the password policy.",
        ) from None
    except Exception:  # noqa: BLE001 - never leak storage errors to callers
        raise _unexpected_failure("user registration") from None

    set_auth_cookie(response, create_token(identity.id))
    return UserOut(id=identity.id, email=identity.email)


@router.post(
    "/login",
    response_model=UserOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Invalid email or password (indistinguishable on purpose).",
        },
    },
    summary="Authenticate and start an authenticated session.",
)
async def login(
    body: EmailPasswordIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserOut:
    """Authenticate through the service and issue a session cookie.

    Every failure — unknown email, wrong password, corrupted stored hash —
    flows through the SAME ``identity is None`` check into the SAME generic
    ``401``, exactly mirroring the service's anti-enumeration contract.
    """
    try:
        identity = await authenticate_user(session, email=body.email, password=body.password)
    except Exception:  # noqa: BLE001 - never leak storage errors to callers
        raise _unexpected_failure("login") from None

    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_LOGIN_FAILURE_DETAIL,
        )

    set_auth_cookie(response, create_token(identity.id))
    return UserOut(id=identity.id, email=identity.email)


@router.post(
    "/logout",
    summary="Clear the authenticated session.",
)
async def logout(response: Response) -> dict[str, str]:
    """Clear the session cookie. Idempotent: no session is also a success."""
    clear_auth_cookie(response)
    return {"detail": "Logged out."}
