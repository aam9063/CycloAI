"""API tests for ``DELETE /account`` (no database).

The auth dependency and the session are overridden, and the deletion seam
(``routes_account.delete_account_row``) is faked at the route-module
boundary, mirroring how ``test_api_auth.py`` fakes the auth service. These
tests pin the API contract:

* an authenticated request deletes the CALLER'S OWN account — the identity
  acted on is the one from the verified token, never from the body;
* an unauthenticated request is ``401`` (from the REAL auth seam, no
  override) and deletes nothing;
* a ``user_id`` smuggled in the body cannot influence WHICH account is
  deleted — the endpoint has no path/body/query target selector at all;
* the response clears the session cookie, asserted on the ACTUAL
  ``Set-Cookie`` header, not on a helper's return value;
* deleting an already-deleted account is a decided ``404`` (consistent with
  the other endpoints' treatment of absent rows), never a ``500``, and it
  clears the cookie too;
* no other endpoint in the application gained a delete path — ``DELETE
  /account`` is self-service only, and there is no administrative sibling.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cycloai.api import routes_account
from cycloai.api.app import create_app
from cycloai.api.deps import (
    AUTH_COOKIE_NAME,
    UNAUTHENTICATED_DETAIL,
    get_current_athlete,
    get_session,
)

CALLER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
SMUGGLED_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
assert SMUGGLED_ID != CALLER_ID


# ---------------------------------------------------------------------------
# Fakes and app builder
# ---------------------------------------------------------------------------


def fake_delete(
    monkeypatch: pytest.MonkeyPatch, outcome: bool
) -> list[uuid.UUID]:
    """Replace the route module's deletion seam; record the ids targeted."""
    calls: list[uuid.UUID] = []

    async def _delete(session: Any, user_id: uuid.UUID) -> bool:
        calls.append(user_id)
        return outcome

    monkeypatch.setattr(routes_account, "delete_account_row", _delete)
    return calls


class FakeSession(SimpleNamespace):
    """A minimal session stand-in: the faked seam never touches storage."""

    async def commit(self) -> None:
        return None


async def fake_session() -> Any:
    yield FakeSession(info={})


def make_app(*, authenticated_as: uuid.UUID | None) -> FastAPI:
    """Build the app, overriding the auth dependency only when requested.

    With ``authenticated_as=None`` the REAL auth seam stays in place, so the
    unauthenticated path is exercised honestly (no cookie → 401).
    """
    app = create_app()
    if authenticated_as is not None:
        app.dependency_overrides[get_current_athlete] = lambda: authenticated_as
    app.dependency_overrides[get_session] = fake_session
    return app


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_authenticated_delete_targets_the_token_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_delete(monkeypatch, outcome=True)
    app = make_app(authenticated_as=CALLER_ID)
    client = TestClient(app)

    response = client.delete("/account")

    assert response.status_code == 200, response.text
    assert response.json() == {"detail": "Account deleted."}
    assert calls == [CALLER_ID], "exactly the caller's own account, once"


def test_body_cannot_influence_which_account_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smuggling a foreign ``user_id`` in the body changes nothing: the
    identity comes only from the verified token."""
    calls = fake_delete(monkeypatch, outcome=True)
    app = make_app(authenticated_as=CALLER_ID)
    client = TestClient(app)

    response = client.request(
        "DELETE", "/account", json={"user_id": str(SMUGGLED_ID), "id": str(SMUGGLED_ID)}
    )

    assert response.status_code == 200, response.text
    assert calls == [CALLER_ID]
    assert SMUGGLED_ID not in calls


def test_unauthenticated_request_is_401_and_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_delete(monkeypatch, outcome=True)
    # NO auth override: the real seam runs, and no cookie is presented.
    app = make_app(authenticated_as=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.delete("/account")

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == UNAUTHENTICATED_DETAIL
    assert calls == [], "an unauthenticated request must delete nothing"


# ---------------------------------------------------------------------------
# Session-cookie clearing, asserted on the actual Set-Cookie header
# ---------------------------------------------------------------------------


def test_success_clears_the_session_cookie_on_the_real_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_delete(monkeypatch, outcome=True)
    app = make_app(authenticated_as=CALLER_ID)
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "token-for-an-account-about-to-vanish")

    response = client.delete("/account")

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert cookies, "the deletion response must send a clearing Set-Cookie"
    raw = cookies[0].lower()
    assert f"{AUTH_COOKIE_NAME}=" in raw
    assert "max-age=0" in raw or "expires=thu, 01 jan 1970" in raw
    assert "httponly" in raw and "samesite=lax" in raw and "path=/" in raw


def test_already_deleted_is_404_with_cookie_cleared_never_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_delete(monkeypatch, outcome=False)
    app = make_app(authenticated_as=CALLER_ID)
    client = TestClient(app)

    response = client.delete("/account")

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Account not found."}
    cookies = response.headers.get_list("set-cookie")
    assert cookies, "the 404 must ALSO clear the stale session cookie"
    raw = cookies[0].lower()
    assert f"{AUTH_COOKIE_NAME}=" in raw
    assert "max-age=0" in raw or "expires=thu, 01 jan 1970" in raw


# ---------------------------------------------------------------------------
# OpenAPI surface: no other endpoint gained a delete path
# ---------------------------------------------------------------------------


def test_delete_account_is_the_only_delete_path() -> None:
    app = create_app()
    schema = app.openapi()

    assert "delete" in schema["paths"]["/account"], "/account must expose DELETE"
    for path, operations in schema["paths"].items():
        if path != "/account":
            assert "delete" not in operations, (
                f"{path} gained a delete path; only the self-service "
                "DELETE /account may exist"
            )
