"""Tests for the profile and onboarding endpoints (P5c).

No database: the auth dependency, the session dependency and the repository
are overridden. The endpoints are exercised through the real app wiring so
the routing, the status mapping and the response models are what get tested.

Contract under test:

- ``GET  /profile``             — the caller's own profile, resolved ONLY
  from the verified token;
- ``PATCH /profile``            — partial update through the repository; a
  disallowed field is a clear 4xx, never a 500;
- ``POST /onboarding/complete`` — marks onboarding complete only when the
  product-required fields are present, and the refusal NAMES the missing
  field(s).

The response deliberately includes the caller's own account ``email``: it is
read through the owner-scoped repository method, so it can only ever be the
token identity's email. Nothing else from ``users`` (``password_hash``, ...)
may appear.

Ownership: every request must bind the caller derived from the token onto
the session (``bind_session_user``) before touching the repository, and no
body field may select which profile is read or written. An id smuggled into
a body is REJECTED like any other unknown field (``extra="forbid"``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cycloai.api import routes_profile
from cycloai.api.app import create_app
from cycloai.api.deps import get_current_athlete, get_session

CALLER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()

#: The exact field set ``ProfileOut`` may expose. Everything on ``profiles``
#: is athlete-owned and legitimately visible; the account ``email`` is the
#: caller's own, read through the owner-scoped repository method. Nothing
#: else from ``users`` (``password_hash``, ...) may appear.
EXPECTED_PROFILE_KEYS = {
    "id",
    "email",
    "created_at",
    "updated_at",
    "display_name",
    "avatar_url",
    "strava_id",
    "strava_connected",
    "strava_connected_at",
    "objective",
    "weekly_hours",
    "gym_days_per_week",
    "injuries",
    "has_power_meter",
    "target_event",
    "target_event_date",
    "onboarding_completed",
    "training_system",
    "lthr_bpm",
    "ftp_estimated",
    "ctl",
    "atl",
    "tsb",
    "weekly_volume_km",
    "weekly_volume_hours",
    "avg_days_per_week",
    "last_sync_at",
}


# ---------------------------------------------------------------------------
# Fakes: profile row, session, repository
# ---------------------------------------------------------------------------


@dataclass
class FakeProfile:
    """Attribute-compatible stand-in for the ``Profile`` ORM row."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime(2025, 1, 1, tzinfo=UTC)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime(2025, 1, 2, tzinfo=UTC)
    )
    display_name: str | None = "Athlete"
    avatar_url: str | None = None
    strava_id: int | None = None
    strava_connected: bool = False
    strava_connected_at: datetime | None = None
    objective: str | None = None
    weekly_hours: float | None = None
    gym_days_per_week: int | None = None
    injuries: str | None = None
    has_power_meter: bool = False
    target_event: str | None = None
    target_event_date: date | None = None
    onboarding_completed: bool = False
    training_system: str = "heart_rate"
    lthr_bpm: int | None = 170
    ftp_estimated: int | None = None
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None
    weekly_volume_km: float | None = None
    weekly_volume_hours: float | None = None
    avg_days_per_week: float | None = None
    last_sync_at: datetime | None = None


class FakeSession:
    """Just enough session for ``bind_session_user`` (writes ``info``)."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}


class FakeProfileRepository:
    """Records which ``user_id`` each call acted on; never lets it drift.

    ``update_profile`` mirrors the repository's contract: it applies the
    given keyword fields onto the stored profile. The API boundary must
    already have rejected anything outside the client-facing payload, so a
    ``ValueError`` path is exercised at the unit level by the repository's
    own tests, not here.

    ``get_email`` mirrors the owner-scoped read: it returns the email of
    exactly the ``user_id`` it was called with, so an assertion that the
    response email equals this caller's email proves the email came from the
    token identity's account and nobody else's.
    """

    def __init__(self, profile: FakeProfile | None = None) -> None:
        self.profile = profile if profile is not None else FakeProfile(id=CALLER_ID)
        self.calls: list[tuple[str, uuid.UUID]] = []
        self.updates: list[dict[str, Any]] = []

    async def get_profile(self, session: Any, user_id: uuid.UUID) -> FakeProfile | None:
        self.calls.append(("get", user_id))
        return self.profile

    async def get_email(self, session: Any, user_id: uuid.UUID) -> str:
        self.calls.append(("email", user_id))
        return f"user-{user_id}@example.com"

    async def update_profile(
        self, session: Any, user_id: uuid.UUID, **fields: Any
    ) -> FakeProfile | None:
        self.calls.append(("update", user_id))
        self.updates.append(fields)
        for name, value in fields.items():
            setattr(self.profile, name, value)
        return self.profile


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    repo: FakeProfileRepository,
    *,
    authenticated: bool = True,
) -> TestClient:
    """Build the real app with the DB-facing dependencies overridden.

    ``bind_session_user`` is spied on (not removed): the test asserts it was
    called with the TOKEN identity, so the ownership guard stays in the path.
    """
    app: FastAPI = create_app()
    fake_session = FakeSession()

    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[routes_profile.get_profile_repository] = lambda: repo
    if authenticated:
        app.dependency_overrides[get_current_athlete] = lambda: CALLER_ID

    bound: list[uuid.UUID] = []
    monkeypatch.setattr(
        routes_profile, "bind_session_user", lambda session, user_id: bound.append(user_id)
    )
    app.state.bound_callers = bound

    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------


def test_get_profile_returns_callers_own_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeProfileRepository()
    client = make_client(monkeypatch, repo)

    response = client.get("/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(CALLER_ID)
    assert body["training_system"] == "heart_rate"
    # The email is the caller's own account email: the fake derives it from
    # the user_id it was called with, so a match proves the token identity's
    # account was read and no other.
    assert body["email"] == f"user-{CALLER_ID}@example.com"
    # The profile acted on is the one from the token, asserted directly.
    assert repo.calls == [("get", CALLER_ID), ("email", CALLER_ID)]
    # The ownership guard ran with the token identity before the read.
    assert client.app.state.bound_callers == [CALLER_ID]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# PATCH /profile
# ---------------------------------------------------------------------------


def test_patch_applies_allowed_field(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeProfileRepository()
    client = make_client(monkeypatch, repo)

    response = client.patch("/profile", json={"display_name": "Racer"})

    assert response.status_code == 200
    assert response.json()["display_name"] == "Racer"
    # Same shape as GET: the response still carries the caller's own email.
    assert response.json()["email"] == f"user-{CALLER_ID}@example.com"
    assert repo.updates == [{"display_name": "Racer"}]
    assert repo.calls == [("update", CALLER_ID), ("email", CALLER_ID)]
    # The ownership guard ran with the token identity before the write.
    assert client.app.state.bound_callers == [CALLER_ID]  # type: ignore[attr-defined]


def test_patch_rejects_disallowed_field_with_clear_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smuggled or protected fields are a 422 at the boundary, never a 500."""
    repo = FakeProfileRepository()
    client = make_client(monkeypatch, repo)

    for payload in ({"onboarding_completed": True}, {"password_hash": "x"}):
        response = client.patch("/profile", json=payload)
        assert response.status_code == 422, payload
        assert repo.updates == []


def test_patch_rejects_unknown_training_system(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeProfileRepository()
    client = make_client(monkeypatch, repo)

    response = client.patch("/profile", json={"training_system": "watts"})

    assert response.status_code == 422
    assert "training_system" in response.text
    assert repo.updates == []


def test_patch_rejects_id_field_in_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """An id smuggled into the body is REJECTED like any other unknown field:
    a client must never see a silent 200 that ignored what it sent."""
    repo = FakeProfileRepository(profile=FakeProfile(id=CALLER_ID))
    client = make_client(monkeypatch, repo)

    response = client.patch(
        "/profile", json={"id": str(OTHER_ID), "display_name": "Racer"}
    )

    assert response.status_code == 422
    assert "id" in response.text
    # Nothing was read or written: the request never reached the repository.
    assert repo.calls == []
    assert repo.updates == []


def test_patch_acts_only_on_token_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """The security property behind the old ignore rule, asserted on a request
    that smuggles nothing: the profile acted on is the one from the TOKEN."""
    repo = FakeProfileRepository(profile=FakeProfile(id=CALLER_ID))
    client = make_client(monkeypatch, repo)

    response = client.patch("/profile", json={"display_name": "Racer"})

    assert response.status_code == 200
    assert response.json()["id"] == str(CALLER_ID)
    assert repo.calls == [("update", CALLER_ID), ("email", CALLER_ID)]
    assert repo.updates == [{"display_name": "Racer"}]
    # The ownership guard ran with the token identity before the write.
    assert client.app.state.bound_callers == [CALLER_ID]  # type: ignore[attr-defined]


def test_unauthenticated_requests_are_401(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeProfileRepository()
    client = make_client(monkeypatch, repo, authenticated=False)

    assert client.get("/profile").status_code == 401
    assert client.patch("/profile", json={"display_name": "x"}).status_code == 401
    assert client.post("/onboarding/complete").status_code == 401
    assert repo.calls == []


# ---------------------------------------------------------------------------
# POST /onboarding/complete
# ---------------------------------------------------------------------------


def test_onboarding_completes_when_required_fields_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeProfileRepository(
        profile=FakeProfile(id=CALLER_ID, training_system="heart_rate", lthr_bpm=170)
    )
    client = make_client(monkeypatch, repo)

    response = client.post("/onboarding/complete")

    assert response.status_code == 200
    assert response.json()["onboarding_completed"] is True
    assert repo.updates == [{"onboarding_completed": True}]
    assert repo.calls[0] == ("get", CALLER_ID)


def test_onboarding_power_athlete_without_ftp_is_refused_and_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeProfileRepository(
        profile=FakeProfile(
            id=CALLER_ID, training_system="power", ftp_estimated=None, lthr_bpm=170
        )
    )
    client = make_client(monkeypatch, repo)

    response = client.post("/onboarding/complete")

    assert response.status_code == 422
    assert "ftp_estimated" in response.text
    assert repo.updates == []


def test_onboarding_heart_rate_athlete_without_lthr_is_refused_and_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeProfileRepository(
        profile=FakeProfile(
            id=CALLER_ID, training_system="heart_rate", lthr_bpm=None, ftp_estimated=250
        )
    )
    client = make_client(monkeypatch, repo)

    response = client.post("/onboarding/complete")

    assert response.status_code == 422
    assert "lthr_bpm" in response.text
    assert repo.updates == []


def test_onboarding_refuses_unknown_training_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeProfileRepository(
        profile=replace(FakeProfile(id=CALLER_ID), training_system="swim")
    )
    client = make_client(monkeypatch, repo)

    response = client.post("/onboarding/complete")

    assert response.status_code == 422
    assert "training_system" in response.text
    assert repo.updates == []


def test_onboarding_on_missing_profile_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeProfileRepository()
    repo.profile = None
    client = make_client(monkeypatch, repo)

    response = client.post("/onboarding/complete")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# No leakage from users
# ---------------------------------------------------------------------------


def test_response_exposes_only_profile_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact key set is asserted so an accidental new field is caught.

    ``email`` IS part of the contract now — but only as the caller's OWN
    account email, read through the owner-scoped repository method. Nothing
    else from ``users`` may appear.
    """
    repo = FakeProfileRepository()
    client = make_client(monkeypatch, repo)

    get_body = client.get("/profile").json()
    patch_body = client.patch("/profile", json={"display_name": "Racer"}).json()
    onboard_body = client.post("/onboarding/complete").json()

    for body in (get_body, patch_body, onboard_body):
        assert set(body) == EXPECTED_PROFILE_KEYS
        assert "password_hash" not in body
        # The email is present and is the token identity's own, never another
        # account's and never a second field smuggled from ``users``.
        assert body["email"] == f"user-{CALLER_ID}@example.com"
