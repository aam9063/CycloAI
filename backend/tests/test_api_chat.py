"""Tests for the chat context endpoint (``POST /chat/context``).

No database: the auth dependency, the session, the repositories and the
retrieval callable are all overridden. The endpoint must be verified against
its contract, not against storage:

* the prompt is built from the TOKEN's identity's profile — a smuggled body
  ``id`` is accepted and ignored;
* a foreign conversation id is refused EXACTLY like a nonexistent one
  (asserted directly: identical status, identical detail);
* a threshold-less athlete still gets the honest no-threshold prompt;
* retrieval is additive: a failure or an empty result never fails the
  request and never leaves a knowledge block in the prompt;
* the response carries the prompt, the conversation id and the
  knowledge-used flag — and nothing else about the athlete.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from cycloai.api.app import create_app
from cycloai.api.deps import get_current_athlete, get_retrieve, get_session
from cycloai.api.routes_chat import (
    get_conversation_repository,
    get_profile_repository,
)
from cycloai.generator.generate import EMPTY_KNOWLEDGE
from cycloai.rag.retrieval import RetrievedKnowledge

CALLER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
SMUGGLED_ID = uuid.uuid4()
NOW = datetime(2026, 1, 15, 12, 0, 0)

#: The detail BOTH a foreign and a nonexistent conversation must produce.
NOT_FOUND_DETAIL = "Conversation not found."


class FakeSession:
    """Bare async session stand-in: ``info`` for the caller bind, ``commit``."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeProfileRepo:
    """Records which user id the profile was read for."""

    def __init__(self, profile: Any) -> None:
        self.profile = profile
        self.read_for: list[uuid.UUID] = []

    async def get_profile(self, session: Any, user_id: uuid.UUID) -> Any:
        self.read_for.append(user_id)
        return self.profile


class FakeConversationRepo:
    """Ownership-enforcing conversation repository stand-in.

    ``rows`` maps conversation id -> ``(owner_id, row)``; a read for another
    user or an unknown id collapses to ``None``, exactly like the real
    repository's deliberate indistinguishability.
    """

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, tuple[uuid.UUID, Any]] = {}
        self.created: list[Any] = []

    def add(self, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> Any:
        row = SimpleNamespace(
            id=conversation_id,
            user_id=owner_id,
            title="existing",
            summary=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.rows[conversation_id] = (owner_id, row)
        return row

    async def get_conversation(
        self, session: Any, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Any:
        entry = self.rows.get(conversation_id)
        if entry is None or entry[0] != user_id:
            return None
        return entry[1]

    async def create_conversation(
        self,
        session: Any,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        summary: str | None = None,
    ) -> Any:
        row = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            summary=summary,
            created_at=NOW,
            updated_at=NOW,
        )
        self.rows[row.id] = (user_id, row)
        self.created.append(row)
        return row


def make_profile(**overrides: Any) -> Any:
    """A profile row with the columns the prompt builder consumes."""
    base: dict[str, Any] = {
        "id": CALLER_ID,
        "strava_connected": True,
        "objective": "gran_fondo",
        "weekly_hours": Decimal("10.0"),
        "gym_days_per_week": 3,
        "injuries": None,
        "has_power_meter": False,
        "target_event": "Gran Fondo Nacional",
        "target_event_date": date(2026, 5, 1),
        "onboarding_completed": True,
        "training_system": "heart_rate",
        "lthr_bpm": 170,
        "ftp_estimated": None,
        "ctl": None,
        "atl": None,
        "tsb": None,
        "weekly_volume_km": None,
        "weekly_volume_hours": None,
        "avg_days_per_week": None,
        "last_sync_at": datetime(2026, 1, 10, 8, 30),
        # Values that must NEVER reach the response:
        "display_name": "SECRET-NAME",
        "email": "secret@example.com",
        "password_hash": "SECRET-HASH",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def _knowledge_ok(query: str) -> RetrievedKnowledge:
    return RetrievedKnowledge(
        text="Hidratación: 500-750 ml/h en clima templado.",
        citation_ids=frozenset({"kb/nutrition/hidratacion.md#1"}),
    )


async def _knowledge_empty(query: str) -> RetrievedKnowledge:
    return EMPTY_KNOWLEDGE


async def _knowledge_broken(query: str) -> RetrievedKnowledge:
    raise RuntimeError("retrieval backend down")


@pytest.fixture
def harness():
    """Build the app with overridable fakes; return (client, fakes)."""

    def _make(
        *,
        profile: Any | None = None,
        retrieve: Any = _knowledge_empty,
        authenticated: bool = True,
    ) -> tuple[TestClient, SimpleNamespace]:
        app = create_app()
        session = FakeSession()
        profile_repo = FakeProfileRepo(profile)
        conversation_repo = FakeConversationRepo()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_profile_repository] = lambda: profile_repo
        app.dependency_overrides[get_conversation_repository] = (
            lambda: conversation_repo
        )
        app.dependency_overrides[get_retrieve] = lambda: retrieve
        if authenticated:
            app.dependency_overrides[get_current_athlete] = lambda: CALLER_ID
        client = TestClient(app)
        fakes = SimpleNamespace(
            session=session,
            profile_repo=profile_repo,
            conversation_repo=conversation_repo,
        )
        return client, fakes

    return _make


class TestChatContextEndpoint:
    def test_authenticated_call_returns_prompt_conversation_id_and_flag(
        self, harness
    ) -> None:
        client, fakes = harness(profile=make_profile(), retrieve=_knowledge_ok)
        response = client.post(
            "/chat/context",
            json={"message": "Como mejoro mi FTP?"},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert set(body) == {"conversation_id", "system_prompt", "knowledge_used"}
        assert body["knowledge_used"] is True
        assert "BASE DE CONOCIMIENTO" in body["system_prompt"]
        # The conversation was created (none was supplied) with the title
        # derived from the first message, the way the existing endpoint does.
        assert len(fakes.conversation_repo.created) == 1
        created = fakes.conversation_repo.created[0]
        assert str(created.id) == body["conversation_id"]
        assert created.title == "Como mejoro mi FTP?"

    def test_new_conversation_title_is_truncated_like_the_existing_behaviour(
        self, harness
    ) -> None:
        client, fakes = harness(profile=make_profile())
        long_message = "palabra " * 30
        response = client.post(
            "/chat/context", json={"message": long_message.strip()}
        )
        assert response.status_code == status.HTTP_200_OK
        created = fakes.conversation_repo.created[0]
        assert len(created.title) <= 60

    def test_foreign_conversation_id_refused_like_nonexistent(self, harness) -> None:
        client, fakes = harness(profile=make_profile())
        foreign_id = uuid.uuid4()
        nonexistent_id = uuid.uuid4()
        # The foreign conversation EXISTS but belongs to another user.
        fakes.conversation_repo.add(foreign_id, OTHER_USER_ID)

        foreign = client.post(
            "/chat/context",
            json={"message": "hola", "conversation_id": str(foreign_id)},
        )
        nonexistent = client.post(
            "/chat/context",
            json={"message": "hola", "conversation_id": str(nonexistent_id)},
        )

        # Asserted DIRECTLY: identical status AND identical detail. The
        # backend collapses both cases and this endpoint must not re-split
        # them, because a distinction would confirm the conversation exists.
        assert foreign.status_code == status.HTTP_404_NOT_FOUND
        assert nonexistent.status_code == status.HTTP_404_NOT_FOUND
        assert foreign.json() == nonexistent.json()
        assert foreign.json() == {"detail": NOT_FOUND_DETAIL}
        assert fakes.conversation_repo.created == []

    def test_existing_own_conversation_is_reused(self, harness) -> None:
        client, fakes = harness(profile=make_profile())
        own_id = uuid.uuid4()
        fakes.conversation_repo.add(own_id, CALLER_ID)
        response = client.post(
            "/chat/context",
            json={"message": "hola", "conversation_id": str(own_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["conversation_id"] == str(own_id)
        assert fakes.conversation_repo.created == []

    def test_athlete_without_threshold_gets_honest_no_threshold_prompt(
        self, harness
    ) -> None:
        # Onboarding not finished: the declared system's threshold is absent.
        client, _ = harness(
            profile=make_profile(lthr_bpm=None, onboarding_completed=False)
        )
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_200_OK
        prompt = response.json()["system_prompt"]
        assert "SIN UMBRAL DECLARADO" in prompt
        # The honesty is explicit, not left to the model to decide.
        assert "NO des objetivos absolutos" in prompt
        assert "LTHR declarado" not in prompt
        assert "FTP declarado" not in prompt

    def test_power_athlete_prompt_declares_ftp_in_watts(self, harness) -> None:
        client, _ = harness(
            profile=make_profile(
                training_system="power", ftp_estimated=250, lthr_bpm=None
            )
        )
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_200_OK
        prompt = response.json()["system_prompt"]
        assert "FTP declarado: 250 vatios" in prompt
        assert "LTHR declarado" not in prompt

    def test_retrieval_failure_does_not_fail_request(self, harness) -> None:
        client, _ = harness(profile=make_profile(), retrieve=_knowledge_broken)
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["knowledge_used"] is False
        assert "BASE DE CONOCIMIENTO" not in body["system_prompt"]

    def test_empty_retrieval_yields_no_knowledge_block(self, harness) -> None:
        client, _ = harness(profile=make_profile(), retrieve=_knowledge_empty)
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["knowledge_used"] is False
        assert "BASE DE CONOCIMIENTO" not in body["system_prompt"]

    def test_unauthenticated_call_is_401(self, harness) -> None:
        # No auth override and no cookie: the real auth seam runs.
        client, _ = harness(profile=make_profile(), authenticated=False)
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Authentication required."}

    def test_profile_loaded_is_token_identity_smuggled_id_ignored(
        self, harness
    ) -> None:
        client, fakes = harness(profile=make_profile())
        response = client.post(
            "/chat/context",
            json={"message": "hola", "id": str(SMUGGLED_ID)},
        )
        assert response.status_code == status.HTTP_200_OK
        # The profile was read for the TOKEN's identity, never for the body id.
        assert fakes.profile_repo.read_for == [CALLER_ID]
        # The conversation is created for the bound caller, and the smuggled
        # id did not become the conversation id.
        created = fakes.conversation_repo.created[0]
        assert created.user_id == CALLER_ID
        assert created.id != SMUGGLED_ID
        assert response.json()["conversation_id"] == str(created.id)

    def test_response_leaks_nothing_from_users_beyond_prompt_needs(
        self, harness
    ) -> None:
        client, _ = harness(profile=make_profile(), retrieve=_knowledge_ok)
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_200_OK
        raw = response.text
        assert "SECRET-NAME" not in raw
        assert "SECRET-HASH" not in raw
        assert "secret@example.com" not in raw
        body = response.json()
        assert set(body) == {"conversation_id", "system_prompt", "knowledge_used"}

    def test_nothing_is_written_for_the_messages_themselves(self, harness) -> None:
        """The turn's messages are NOT persisted here: no message repository
        is even wired into this endpoint, and the conversation write is only
        the create-when-missing."""
        client, fakes = harness(profile=make_profile())
        response = client.post("/chat/context", json={"message": "hola"})
        assert response.status_code == status.HTTP_200_OK
        # Only the conversation creation happened; no message rows exist in
        # this endpoint's reach at all.
        assert len(fakes.conversation_repo.created) == 1
