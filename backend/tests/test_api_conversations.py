"""Unit tests for the conversations and messages API (no database).

The auth seam and both repository seams are overridden, so these tests run
without PostgreSQL and pin the API contract:

* every endpoint serves only the caller's own data, and the owner acted on
  is the one from the verified token (a body-supplied ``id`` is refused
  with a ``422``);
* unauthenticated requests are ``401`` on every endpoint;
* a FOREIGN conversation and a NONEXISTENT one are indistinguishable —
  same status AND same body, asserted directly, because a distinct error
  would confirm that another user's conversation exists (a leak);
* appending to a foreign conversation is refused on the same terms and
  never stores anything;
* an empty message, an invalid role, and an unbounded ``metadata`` payload
  are rejected clearly at the boundary, before any repository write;
* titles are truncated exactly like the original client's
  ``truncateTitle`` (``lib/chat/text.ts``).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cycloai.api.deps import (
    UNAUTHENTICATED_DETAIL,
    get_current_athlete,
    get_session,
)
from cycloai.api.routes_conversations import (
    _METADATA_MAX_BYTES,
    _METADATA_MAX_DEPTH,
    get_conversation_repository,
    get_message_repository,
)

CALLER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()

NOW = "2025-06-01T12:00:00Z"


# ---------------------------------------------------------------------------
# Fakes: record what the route layer asked the repositories to do, so the
# tests can assert on attribution and on "nothing was written".
# ---------------------------------------------------------------------------


class FakeConversationRepository:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.updated: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.conversations: dict[uuid.UUID, SimpleNamespace] = {}

    def seed(self, owner: uuid.UUID) -> SimpleNamespace:
        conversation = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=owner,
            title="Seeded",
            summary=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.conversations[conversation.id] = conversation
        return conversation

    async def create_conversation(self, session, user_id, *, title=None, summary=None):
        self.created.append({"user_id": user_id, "title": title, "summary": summary})
        conversation = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            summary=summary,
            created_at=NOW,
            updated_at=NOW,
        )
        self.conversations[conversation.id] = conversation
        return conversation

    async def list_conversations(self, session, user_id):
        owned = [c for c in self.conversations.values() if c.user_id == user_id]
        return owned

    async def get_conversation(self, session, user_id, conversation_id):
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            return None  # missing and foreign collapse into the same None
        return conversation

    async def update_conversation(self, session, user_id, conversation_id, **fields):
        conversation = await self.get_conversation(session, user_id, conversation_id)
        if conversation is None:
            return None
        self.updated.append((user_id, conversation_id))
        return conversation


class FakeMessageRepository:
    def __init__(self, conversations: FakeConversationRepository) -> None:
        # Mirror the real contract: a message is only written when the target
        # conversation is visible to the caller, so the fake consults the
        # conversation fake rather than adding its own ownership logic.
        self._conversations = conversations
        self.appended: list[dict] = []
        self.messages: dict[uuid.UUID, list[SimpleNamespace]] = {}

    async def append_message(
        self, session, user_id, conversation_id, *, role, content, metadata=None
    ):
        conversation = self._conversations.conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            self.appended.append(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "content": content,
                    "metadata": metadata,
                    "refused": True,
                }
            )
            return None
        self.appended.append(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "metadata": metadata,
                "refused": False,
            }
        )
        message = SimpleNamespace(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,  # attribution comes from the bound caller only
            role=role,
            content=content,
            created_at=NOW,
            metadata_=metadata,
        )
        self.messages.setdefault(conversation_id, []).append(message)
        return message

    async def list_messages(self, session, user_id, conversation_id):
        # Mirror the real visibility rule: None when the conversation is not
        # the caller's (missing or foreign — indistinguishable).
        if conversation_id not in self.messages:
            return None
        return list(self.messages[conversation_id])


@pytest.fixture()
def fake_repos():
    conversation_repo = FakeConversationRepository()
    return conversation_repo, FakeMessageRepository(conversation_repo)


@pytest.fixture()
def client(fake_repos):
    conversation_repo, message_repo = fake_repos

    def build(authenticated: bool) -> TestClient:
        app = FastAPI()
        from cycloai.api.routes_conversations import router

        app.include_router(router)
        if authenticated:
            app.dependency_overrides[get_current_athlete] = lambda: CALLER_ID
        # The routes bind the caller onto the session before any repository
        # access, and commit after a successful write; a lightweight stand-in
        # satisfies that contract.
        async def _commit() -> None:
            return None

        async def _session():
            yield SimpleNamespace(info={}, commit=_commit)

        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_conversation_repository] = (
            lambda: conversation_repo
        )
        app.dependency_overrides[get_message_repository] = lambda: message_repo
        return TestClient(app)

    return build


# ---------------------------------------------------------------------------
# The caller's own data
# ---------------------------------------------------------------------------


class TestOwnData:
    def test_list_conversations_returns_callers_own_conversations(self, client):
        c = client(authenticated=True)
        response = c.get("/conversations")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_conversation_returns_201_with_callers_data(self, client):
        c = client(authenticated=True)
        response = c.post("/conversations", json={"title": "Zwift hill repeats"})
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "Zwift hill repeats"

    def test_get_conversation_returns_the_callers_own_conversation(
        self, client, fake_repos
    ):
        conversation_repo, _ = fake_repos
        conversation = conversation_repo.seed(CALLER_ID)
        c = client(authenticated=True)
        response = c.get(f"/conversations/{conversation.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(conversation.id)

    def test_list_messages_returns_own_messages_oldest_first(
        self, client, fake_repos
    ):
        conversation_repo, message_repo = fake_repos
        conversation = conversation_repo.seed(CALLER_ID)
        c = client(authenticated=True)
        first = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "first"},
        )
        second = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "assistant", "content": "second"},
        )
        assert first.status_code == 201
        assert second.status_code == 201

        listing = c.get(f"/conversations/{conversation.id}/messages")
        assert listing.status_code == 200
        contents = [m["content"] for m in listing.json()]
        assert contents == ["first", "second"]
        assert [m["role"] for m in listing.json()] == ["user", "assistant"]

    def test_append_message_returns_the_stored_row_with_caller_attribution(
        self, client, fake_repos
    ):
        conversation_repo, _ = fake_repos
        conversation = conversation_repo.seed(CALLER_ID)
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "hi", "metadata": {"tokens": 3}},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["role"] == "user"
        assert body["content"] == "hi"
        assert body["metadata"] == {"tokens": 3}
        assert body["user_id"] == str(CALLER_ID)

    def test_appending_bumps_the_conversation_updated_at(
        self, client, fake_repos
    ):
        conversation_repo, _ = fake_repos
        conversation = conversation_repo.seed(CALLER_ID)
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "bump"},
        )
        assert response.status_code == 201
        # The repository's update operation (which owns the bump) was invoked
        # for this conversation on behalf of the caller.
        assert (CALLER_ID, conversation.id) in conversation_repo.updated


# ---------------------------------------------------------------------------
# Unauthenticated access is 401 everywhere
# ---------------------------------------------------------------------------


class TestUnauthenticated:
    def test_every_endpoint_is_401_without_a_valid_token(self, client):
        c = client(authenticated=False)
        foreign_id = uuid.uuid4()
        cases = [
            ("GET", "/conversations", None),
            ("POST", "/conversations", {"title": "nope"}),
            ("GET", f"/conversations/{foreign_id}", None),
            ("GET", f"/conversations/{foreign_id}/messages", None),
            (
                "POST",
                f"/conversations/{foreign_id}/messages",
                {"role": "user", "content": "nope"},
            ),
        ]
        for method, url, payload in cases:
            response = c.request(method, url, json=payload)
            assert response.status_code == 401, f"{method} {url}"
            assert response.json() == {"detail": UNAUTHENTICATED_DETAIL}, (
                f"{method} {url}"
            )


# ---------------------------------------------------------------------------
# Foreign vs nonexistent: indistinguishable by construction
# ---------------------------------------------------------------------------


class TestForeignIndistinguishableFromMissing:
    """The security property under test: "not yours" must look exactly like
    "does not exist". A distinct status or body for a foreign id would
    confirm that somebody else's conversation exists — a leak."""

    def test_foreign_and_nonexistent_conversation_read_identically(
        self, client, fake_repos
    ):
        conversation_repo, _ = fake_repos
        foreign = conversation_repo.seed(OTHER_ID)
        nonexistent = uuid.uuid4()
        c = client(authenticated=True)

        foreign_response = c.get(f"/conversations/{foreign.id}")
        missing_response = c.get(f"/conversations/{nonexistent}")

        # Asserted directly: same status AND byte-identical body, not merely
        # "both fail".
        assert foreign_response.status_code == missing_response.status_code
        assert foreign_response.status_code == 404
        assert foreign_response.json() == missing_response.json()
        assert foreign_response.json() == {"detail": "Conversation not found."}

    def test_foreign_and_nonexistent_message_listing_identical(
        self, client, fake_repos
    ):
        conversation_repo, _ = fake_repos
        foreign = conversation_repo.seed(OTHER_ID)
        nonexistent = uuid.uuid4()
        c = client(authenticated=True)

        foreign_response = c.get(f"/conversations/{foreign.id}/messages")
        missing_response = c.get(f"/conversations/{nonexistent}/messages")

        assert foreign_response.status_code == missing_response.status_code == 404
        assert foreign_response.json() == missing_response.json()

    def test_appending_to_a_foreign_conversation_is_refused_indistinguishably(
        self, client, fake_repos
    ):
        conversation_repo, message_repo = fake_repos
        foreign = conversation_repo.seed(OTHER_ID)
        nonexistent = uuid.uuid4()
        c = client(authenticated=True)

        foreign_response = c.post(
            f"/conversations/{foreign.id}/messages",
            json={"role": "user", "content": "intrusion"},
        )
        missing_response = c.post(
            f"/conversations/{nonexistent}/messages",
            json={"role": "user", "content": "intrusion"},
        )

        assert foreign_response.status_code == missing_response.status_code == 404
        assert foreign_response.json() == missing_response.json()
        # Nothing was written on either path: every append attempt was
        # refused by the repository's visibility rule.
        assert message_repo.appended
        assert all(attempt["refused"] for attempt in message_repo.appended)

    def test_foreign_conversation_is_absent_from_the_list(self, client, fake_repos):
        conversation_repo, _ = fake_repos
        conversation_repo.seed(OTHER_ID)
        c = client(authenticated=True)
        response = c.get("/conversations")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Boundary validation: client bugs are refused, never stored
# ---------------------------------------------------------------------------


class TestMessageValidation:
    def _own_conversation(self, client, fake_repos):
        conversation_repo, _ = fake_repos
        return conversation_repo.seed(CALLER_ID)

    def test_empty_content_is_rejected(self, client, fake_repos):
        conversation = self._own_conversation(client, fake_repos)
        _, message_repo = fake_repos
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": ""},
        )
        assert response.status_code == 422
        assert message_repo.appended == []

    def test_role_outside_the_schema_check_domain_is_rejected(
        self, client, fake_repos
    ):
        # The messages.role CHECK allows exactly ('user', 'assistant').
        conversation = self._own_conversation(client, fake_repos)
        _, message_repo = fake_repos
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "system", "content": "not a stored role"},
        )
        assert response.status_code == 422
        assert message_repo.appended == []

    def test_both_allowed_roles_are_accepted(self, client, fake_repos):
        conversation = self._own_conversation(client, fake_repos)
        c = client(authenticated=True)
        for role in ("user", "assistant"):
            response = c.post(
                f"/conversations/{conversation.id}/messages",
                json={"role": role, "content": "ok"},
            )
            assert response.status_code == 201, role

    def test_oversized_metadata_is_rejected_clearly_and_not_stored(
        self, client, fake_repos
    ):
        conversation = self._own_conversation(client, fake_repos)
        _, message_repo = fake_repos
        c = client(authenticated=True)
        oversized = {"blob": "x" * (_METADATA_MAX_BYTES + 1)}
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "hi", "metadata": oversized},
        )
        assert response.status_code == 422
        assert "metadata is too large" in response.text
        assert message_repo.appended == []

    def test_deeply_nested_metadata_is_rejected_clearly_and_not_stored(
        self, client, fake_repos
    ):
        conversation = self._own_conversation(client, fake_repos)
        _, message_repo = fake_repos
        c = client(authenticated=True)
        deep: dict = {"leaf": 1}
        for _ in range(_METADATA_MAX_DEPTH + 1):
            deep = {"n": deep}
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "hi", "metadata": deep},
        )
        assert response.status_code == 422
        assert "nested too deeply" in response.text
        assert message_repo.appended == []

    def test_reasonable_metadata_is_accepted(self, client, fake_repos):
        conversation = self._own_conversation(client, fake_repos)
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={
                "role": "assistant",
                "content": "ok",
                "metadata": {"model": "gemini", "tokens": 42, "nested": {"a": [1, 2]}},
            },
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Title normalisation: ported from the original client
# ---------------------------------------------------------------------------


class TestTitleNormalisation:
    def test_long_title_is_truncated_at_60_chars_on_a_word_boundary(
        self, client, fake_repos
    ):
        # Original client behaviour (lib/chat/text.ts, truncateTitle):
        #   const slice = trimmed.slice(0, max);
        #   const lastSpace = slice.lastIndexOf(' ');
        #   return lastSpace > max * 0.6 ? slice.slice(0, lastSpace) : slice;
        # A space past 60% of the 60-char window cuts the title at that
        # space; otherwise the slice is hard-cut.
        conversation_repo, _ = fake_repos
        c = client(authenticated=True)
        long_title = "x" * 50 + " " + "y" * 20  # 71 chars, space at index 50
        response = c.post("/conversations", json={"title": long_title})
        assert response.status_code == 201
        assert response.json()["title"] == "x" * 50

    def test_title_without_a_far_enough_boundary_is_hard_cut(self, fake_repos, client):
        conversation_repo, _ = fake_repos
        c = client(authenticated=True)
        no_boundary = "z" * 70  # no space at all: hard cut at 60
        response = c.post("/conversations", json={"title": no_boundary})
        assert response.status_code == 201
        assert response.json()["title"] == "z" * 60

    def test_short_title_is_kept_as_is(self, client, fake_repos):
        conversation_repo, _ = fake_repos
        c = client(authenticated=True)
        response = c.post("/conversations", json={"title": "  Short ride  "})
        assert response.status_code == 201
        assert response.json()["title"] == "Short ride"


# ---------------------------------------------------------------------------
# Ownership comes only from the token
# ---------------------------------------------------------------------------


class TestOwnershipFromTokenOnly:
    def test_body_id_is_rejected_on_conversation_creation(self, client, fake_repos):
        conversation_repo, _ = fake_repos
        c = client(authenticated=True)
        response = c.post(
            "/conversations",
            json={"title": "smuggled", "id": str(OTHER_ID)},
        )
        assert response.status_code == 422
        # Nothing was written: the request was refused at the boundary.
        assert conversation_repo.created == []

    def test_conversation_creation_acts_on_the_token_identity(
        self, client, fake_repos
    ):
        """No smuggled field at all: the owner acted on is the token's."""
        conversation_repo, _ = fake_repos
        c = client(authenticated=True)
        response = c.post("/conversations", json={"title": "token-owned"})
        assert response.status_code == 201
        # The owner acted on is the one from the token.
        assert conversation_repo.created == [
            {"user_id": CALLER_ID, "title": "token-owned", "summary": None}
        ]

    def test_body_id_is_rejected_on_message_append(self, client, fake_repos):
        conversation_repo, message_repo = fake_repos
        conversation = conversation_repo.seed(CALLER_ID)
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "hi", "id": str(OTHER_ID)},
        )
        assert response.status_code == 422
        assert message_repo.appended == []

    def test_message_append_acts_on_the_token_identity(self, client, fake_repos):
        """No smuggled field at all: the owner acted on is the token's."""
        conversation_repo, message_repo = fake_repos
        conversation = conversation_repo.seed(CALLER_ID)
        c = client(authenticated=True)
        response = c.post(
            f"/conversations/{conversation.id}/messages",
            json={"role": "user", "content": "hi"},
        )
        assert response.status_code == 201
        assert response.json()["user_id"] == str(CALLER_ID)
        assert message_repo.appended[0]["user_id"] == CALLER_ID
