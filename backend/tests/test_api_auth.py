"""API tests for the P5b auth endpoints and the REPLACED auth seam.

No database and no network: the service functions are faked at the route
module boundary (``routes_auth.register_user`` / ``routes_auth.authenticate_user``)
and every request-scoped dependency is overridden or driven through a locally
attached probe route.

The seam contract under test: :func:`cycloai.api.deps.get_current_athlete`
resolves the caller's identity ONLY from the verified session cookie. Nothing
in the request body, the query string or the headers may influence it — the
body-smuggling probe test asserts that directly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from cycloai.api import routes_auth
from cycloai.api.app import create_app
from cycloai.api.deps import (
    AUTH_COOKIE_NAME,
    get_current_athlete,
    get_session,
)
from cycloai.auth.security import (
    ACCESS_TOKEN_TTL,
    PasswordValidationError,
    create_token,
    get_settings,
)
from cycloai.auth.service import EmailAlreadyRegisteredError, UserIdentity

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

#: A test-only signing secret (>= MIN_SECRET_LENGTH). The autouse fixture
#: injects it into the environment and clears the settings cache so the auth
#: core never reads a developer's real ``backend/.env`` secret here.
TEST_JWT_SECRET = "test-secret-0123456789abcdef0123456789abcdef"
OTHER_JWT_SECRET = "other-secret-0123456789abcdef0123456789abcde"

REGISTERED_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
SEAM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b5")
SMUGGLED_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
assert SMUGGLED_ID != SEAM_ID and SMUGGLED_ID != REGISTERED_ID


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Pin the JWT secret for every test and clear the cached settings."""
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.delenv("CYCLOAI_ENV", raising=False)  # non-production by default
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class ProbeBody(BaseModel):
    """A body that SMUGGLES an identity, to prove the seam ignores it."""

    user_id: str | None = None


def make_app() -> FastAPI:
    """Build the app plus a probe route that exposes the seam's identity."""
    app = create_app()

    @app.post("/_probe/me")
    async def probe(
        body: ProbeBody,
        athlete_id: uuid.UUID = Depends(get_current_athlete),
    ) -> dict[str, str]:
        return {"athlete_id": str(athlete_id)}

    return app


async def fake_session() -> AsyncIterator[object]:
    """A sentinel session: the faked service never touches it."""
    yield object()


def install_session_override(app: FastAPI) -> None:
    app.dependency_overrides[get_session] = fake_session


def fake_register(
    monkeypatch: pytest.MonkeyPatch, outcome: UserIdentity | Exception
) -> list[dict[str, str]]:
    """Replace the service's ``register_user`` in the route module namespace."""
    calls: list[dict[str, str]] = []

    async def _register(session: Any, *, email: str, password: str) -> UserIdentity:
        calls.append({"email": email, "password": password})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(routes_auth, "register_user", _register)
    return calls


def fake_authenticate(
    monkeypatch: pytest.MonkeyPatch,
    outcome: UserIdentity | None,
    *,
    only_email: str | None = None,
) -> list[dict[str, str]]:
    """Replace the service's ``authenticate_user`` in the route module.

    With ``only_email``, only that email authenticates — any other email
    fails, mirroring the service's indistinguishable ``None`` outcome.
    """
    calls: list[dict[str, str]] = []

    async def _authenticate(session: Any, *, email: str, password: str) -> UserIdentity | None:
        calls.append({"email": email, "password": password})
        if only_email is not None and email != only_email:
            return None
        return outcome

    monkeypatch.setattr(routes_auth, "authenticate_user", _authenticate)
    return calls


def capture_tokens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every session token the routes issue, to assert it never leaks."""
    issued: list[str] = []
    original = routes_auth.create_token

    def _create(user_id: Any, **kwargs: Any) -> str:
        token = original(user_id, **kwargs)
        issued.append(token)
        return token

    monkeypatch.setattr(routes_auth, "create_token", _create)
    return issued


def register_body() -> dict[str, str]:
    return {"email": "Athlete@Example.com", "password": "correct-horse-battery"}


def set_cookie_headers(response: Any) -> list[str]:
    return response.headers.get_list("set-cookie")


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


def test_register_success_sets_session_cookie_with_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_register(monkeypatch, UserIdentity(id=REGISTERED_ID, email="athlete@example.com"))
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    response = client.post("/auth/register", json=register_body())

    assert response.status_code == 201, response.text
    assert response.json() == {"id": str(REGISTERED_ID), "email": "athlete@example.com"}
    cookies = set_cookie_headers(response)
    assert len(cookies) == 1, "register must set exactly one session cookie"
    raw = cookies[0]
    assert f"{AUTH_COOKIE_NAME}=" in raw
    lowered = raw.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert f"max-age={int(ACCESS_TOKEN_TTL.total_seconds())}" in lowered
    assert "secure" not in lowered, "Secure must be OFF outside production"


def test_register_production_sets_secure_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_register(monkeypatch, UserIdentity(id=REGISTERED_ID, email="athlete@example.com"))
    monkeypatch.setenv("CYCLOAI_ENV", "production")
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    response = client.post("/auth/register", json=register_body())

    assert response.status_code == 201
    raw = set_cookie_headers(response)[0].lower()
    assert "secure" in raw, "Secure must be ON in production"
    assert "httponly" in raw and "samesite=lax" in raw


def test_duplicate_email_is_409_and_sets_no_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_register(
        monkeypatch, EmailAlreadyRegisteredError("athlete@example.com")
    )
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    response = client.post("/auth/register", json=register_body())

    assert response.status_code == 409
    assert set_cookie_headers(response) == [], "a failed registration must not log in"
    assert response.json()["detail"]


def test_password_policy_failure_is_distinct_from_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_register(monkeypatch, PasswordValidationError("Password length must be at least 1."))
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    response = client.post("/auth/register", json=register_body())

    assert response.status_code == 400
    assert response.status_code != 409, "policy failure must never read as 'email taken'"
    assert set_cookie_headers(response) == []
    assert response.json()["detail"]


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_unknown_email_and_wrong_password_are_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP layer must NOT undo the service's anti-enumeration design:
    any failure maps to one indistinguishable 401 shape."""
    calls = fake_authenticate(monkeypatch, None)
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    unknown_email = client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "whatever-1"}
    )
    wrong_password = client.post(
        "/auth/login", json={"email": "athlete@example.com", "password": "totally-wrong"}
    )

    assert len(calls) == 2
    assert unknown_email.status_code == wrong_password.status_code == 401
    assert unknown_email.content == wrong_password.content


def test_login_success_sets_session_cookie_and_no_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_authenticate(
        monkeypatch, UserIdentity(id=REGISTERED_ID, email="athlete@example.com")
    )
    issued = capture_tokens(monkeypatch)
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    response = client.post(
        "/auth/login", json={"email": "athlete@example.com", "password": "s3cret-value"}
    )

    assert response.status_code == 200
    assert response.json() == {"id": str(REGISTERED_ID), "email": "athlete@example.com"}
    assert len(issued) == 1
    # The token is delivered ONLY as a cookie — never in the body.
    assert issued[0] not in response.text
    assert "s3cret-value" not in response.text
    assert "password_hash" not in response.text
    raw = set_cookie_headers(response)[0].lower()
    assert "httponly" in raw and "samesite=lax" in raw and "path=/" in raw


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout_clears_the_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    app = make_app()
    install_session_override(app)
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "some-session-token")

    response = client.post("/auth/logout")

    assert response.status_code == 200
    cookies = set_cookie_headers(response)
    assert cookies, "logout must send a clearing Set-Cookie"
    raw = cookies[0].lower()
    assert f"{AUTH_COOKIE_NAME}=" in raw
    assert 'max-age=0' in raw or 'expires=thu, 01 jan 1970' in raw


# ---------------------------------------------------------------------------
# Secret hygiene across all responses
# ---------------------------------------------------------------------------


def test_no_response_body_ever_carries_password_hash_or_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_register(monkeypatch, UserIdentity(id=REGISTERED_ID, email="athlete@example.com"))
    fake_authenticate(
        monkeypatch,
        UserIdentity(id=REGISTERED_ID, email="athlete@example.com"),
        only_email="athlete@example.com",
    )
    issued = capture_tokens(monkeypatch)
    app = make_app()
    install_session_override(app)
    client = TestClient(app)

    responses = [
        client.post("/auth/register", json=register_body()),
        client.post("/auth/login", json={"email": "athlete@example.com", "password": "pw-secret"}),
        client.post("/auth/login", json={"email": "ghost@example.com", "password": "pw-secret"}),
        client.post("/auth/register", json={"email": "x@y.com", "password": "z"}),
        client.post("/auth/logout"),
    ]

    assert [r.status_code for r in responses] == [201, 200, 401, 201, 200]
    assert len(issued) == 3  # register + successful login + second register
    for response in responses:
        text = response.text
        assert "pw-secret" not in text
        assert "password_hash" not in text
        assert "argon2" not in text.lower()
        for token in issued:
            assert token not in text


# ---------------------------------------------------------------------------
# The replaced seam: get_current_athlete
# ---------------------------------------------------------------------------


def test_seam_rejects_missing_cookie_with_401_never_500() -> None:
    app = make_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/_probe/me", json={})

    assert response.status_code == 401, response.text


def test_seam_rejects_garbage_cookie_with_401_never_500() -> None:
    app = make_app()
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(AUTH_COOKIE_NAME, "not-a-jwt-at-all")

    response = client.post("/_probe/me", json={})

    assert response.status_code == 401, response.text


def test_seam_rejects_token_signed_with_wrong_secret_with_401_never_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", OTHER_JWT_SECRET)
    get_settings.cache_clear()
    foreign_token = create_token(SEAM_ID)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    get_settings.cache_clear()

    app = make_app()
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(AUTH_COOKIE_NAME, foreign_token)

    response = client.post("/_probe/me", json={})

    assert response.status_code == 401, response.text


def test_seam_rejects_expired_token_with_401_never_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    expired = jwt.encode(
        {
            "sub": str(SEAM_ID),
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "typ": "access",
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    app = make_app()
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(AUTH_COOKIE_NAME, expired)

    response = client.post("/_probe/me", json={})

    assert response.status_code == 401, response.text


def test_seam_identity_comes_from_token_never_from_body() -> None:
    """THE seam property: the identity is the verified token's subject, and a
    ``user_id`` smuggled in the body is ignored completely."""
    token = create_token(SEAM_ID)
    app = make_app()
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, token)

    response = client.post("/_probe/me", json={"user_id": str(SMUGGLED_ID)})

    assert response.status_code == 200
    assert response.json()["athlete_id"] == str(SEAM_ID)
    assert response.json()["athlete_id"] != str(SMUGGLED_ID)


# ---------------------------------------------------------------------------
# OpenAPI surface
# ---------------------------------------------------------------------------


def test_auth_routes_are_documented_in_openapi() -> None:
    app = make_app()
    schema = app.openapi()

    for path in ("/auth/register", "/auth/login", "/auth/logout"):
        assert path in schema["paths"], path
        assert "post" in schema["paths"][path]
