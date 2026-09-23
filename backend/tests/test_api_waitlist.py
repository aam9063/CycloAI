"""API tests for the anonymous waitlist endpoint — NO database.

The session dependency is overridden with a fake that records what the route
added and raises, on demand, the exact database integrity error the real
PostgreSQL constraint would raise. That is how the tests prove the endpoint
LEANES ON THE DATABASE CONSTRAINT instead of reimplementing the shape rules in
Python: a malformed email and an oversized ``source`` still reach the INSERT
(the fake records the row) and the 4xx comes from the fake's raised
constraint violation — if Python had its own copy of the rules, the route
would refuse before ever touching the session.

Contract under test:

* a valid signup is accepted with ``202``;
* a malformed email / oversized ``source`` → ``422`` PRODUCED BY the database
  constraint violation, not by any client-side rule;
* a duplicate email (unique index on ``lower(email)``) → the SAME ``202``
  acknowledgement, by explicit product decision: a repeat signup is
  idempotent and indistinguishable from a first signup;
* the endpoint works with NO authentication at all — no cookie, no session;
* the response body exposes nothing beyond the acknowledgement.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from cycloai.api import routes_waitlist
from cycloai.api.app import create_app
from cycloai.api.deps import get_session

VALID_EMAIL = "rider@example.com"
ACK_BODY = {"detail": routes_waitlist.WAITLIST_ACK_DETAIL}


class FakeSession:
    """Stand-in for ``AsyncSession``: records adds, raises on commit on demand."""

    def __init__(self, commit_error: Exception | None = None) -> None:
        self.added: list[Any] = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.commit_error = commit_error

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollback_calls += 1


def db_integrity_error(constraint_name: str) -> IntegrityError:
    """Build the ``IntegrityError`` the real driver would raise for a constraint.

    The cause carries ``constraint_name`` the same way psycopg's diagnostics
    do, so the route's constraint-name mapping is exercised, not bypassed.
    """
    cause = Exception(f'new row violates check constraint "{constraint_name}"')
    cause.constraint_name = constraint_name  # type: ignore[attr-defined]
    return IntegrityError("INSERT INTO waitlist ...", {}, cause)


def make_client(fake: FakeSession) -> TestClient:
    """Build the real app with ONLY the session dependency overridden."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: fake
    return TestClient(app, raise_server_exceptions=False)


def test_valid_signup_is_accepted() -> None:
    fake = FakeSession()
    response = make_client(fake).post(
        "/waitlist",
        json={"email": VALID_EMAIL, "source": "landing"},
    )
    assert response.status_code == 202
    assert response.json() == ACK_BODY
    assert fake.commit_calls == 1
    (row,) = fake.added
    assert row.email == VALID_EMAIL
    assert row.source == "landing"


def test_malformed_email_rejection_comes_from_the_database_constraint() -> None:
    # "not-an-email" violates waitlist_email_shape in PostgreSQL. The fake
    # raises exactly that constraint violation on commit — the route must
    # have ATTEMPTED THE INSERT (no client-side rule refused first) and must
    # map the raised violation to a clear 422.
    fake = FakeSession(commit_error=db_integrity_error("waitlist_email_shape"))
    response = make_client(fake).post(
        "/waitlist", json={"email": "not-an-email"}
    )
    assert response.status_code == 422
    assert "waitlist" in response.json()["detail"].lower()
    assert fake.commit_calls == 1, "the route must reach the INSERT, not pre-validate"
    assert fake.rollback_calls == 1, (
        "the failed session must be rolled back before the boundary commit"
    )
    (row,) = fake.added
    assert row.email == "not-an-email"


def test_oversized_source_rejected_clearly() -> None:
    # source > 50 chars violates waitlist_email_shape — a clear client error,
    # never a 500, and still produced by the database, not a Python rule.
    fake = FakeSession(commit_error=db_integrity_error("waitlist_email_shape"))
    response = make_client(fake).post(
        "/waitlist",
        json={"email": VALID_EMAIL, "source": "x" * 51},
    )
    assert response.status_code == 422
    assert "source" in response.json()["detail"] or "waitlist" in response.json()["detail"]
    assert fake.commit_calls == 1


def test_duplicate_email_returns_the_same_acknowledgement() -> None:
    # Product decision under test: a repeat signup is idempotent — same 202,
    # same body, no signal that the address was already present.
    fake = FakeSession(commit_error=db_integrity_error("waitlist_email_unique"))
    response = make_client(fake).post(
        "/waitlist", json={"email": VALID_EMAIL.upper()}
    )
    assert response.status_code == 202
    assert response.json() == ACK_BODY
    assert fake.rollback_calls == 1, "a duplicate must also leave the session reusable"


def test_works_with_no_authentication_at_all() -> None:
    # No cookie, no session, no auth header: the landing page visitor path.
    # Forgetting this would make the landing page silently stop collecting
    # signups once it stops using the direct database insert.
    fake = FakeSession()
    response = make_client(fake).post("/waitlist", json={"email": VALID_EMAIL})
    assert response.status_code == 202
    assert response.json() == ACK_BODY


def test_response_exposes_nothing_beyond_the_acknowledgement() -> None:
    fake = FakeSession()
    response = make_client(fake).post(
        "/waitlist", json={"email": VALID_EMAIL, "source": "landing"}
    )
    body = response.json()
    assert set(body) == {"detail"}
    assert VALID_EMAIL not in response.text  # never echoes the submitted email
    assert "id" not in body and "created_at" not in body


def test_unattributable_integrity_error_is_a_generic_500() -> None:
    # Triangulation: an integrity error that is NEITHER the shape constraint
    # NOR the unique index must not be silently reinterpreted as one of them.
    fake = FakeSession(commit_error=db_integrity_error("some_other_constraint"))
    response = make_client(fake).post("/waitlist", json={"email": VALID_EMAIL})
    assert response.status_code == 500
    assert response.json() == {"detail": "The request could not be completed."}


def test_missing_email_is_a_request_validation_error() -> None:
    # Pydantic's presence check only — no shape rules live client-side.
    fake = FakeSession()
    response = make_client(fake).post("/waitlist", json={"source": "landing"})
    assert response.status_code == 422
    assert fake.commit_calls == 0
    assert fake.added == []


@pytest.mark.parametrize("payload", [{"email": ""}, {"email": "a@b"}])
def test_degenerate_emails_still_go_to_the_database(payload: dict[str, Any]) -> None:
    # Even degenerate values are NOT screened client-side: the constraint is
    # the authority for them too.
    fake = FakeSession(commit_error=db_integrity_error("waitlist_email_shape"))
    response = make_client(fake).post("/waitlist", json=payload)
    assert response.status_code == 422
    assert fake.commit_calls == 1
