"""API tests for ``POST /generate`` (phase P4): no database, no API key.

Every request-scoped dependency is overridden with a fake:

* the **auth seam** (:func:`cycloai.api.deps.get_current_athlete`) is an
  async GENERATOR dependency in production, so the override yields — it
  does not return — a fixed seam identity;
* the **session** is a sentinel object; the profile repository is faked so
  no engine is ever built;
* the **model client** and **retrieval** callables are scripted fakes that
  record every call, which is what lets the malformed-body test prove the
  pipeline never ran.

The security property under test is the P2c fail-closed repository guard's
entry point: the session is bound to the identity from the auth seam and to
NOTHING the request body supplied. That is asserted directly — the body
smuggles a different athlete id and the test captures what
``bind_session_user`` actually received.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cycloai.api import routes_generate
from cycloai.api.app import create_app
from cycloai.api.deps import (
    DEVELOPMENT_STUB_ATHLETE_ID,
    get_current_athlete,
    get_model_client,
    get_retrieve,
    get_session,
)
from cycloai.generator.generate import (
    EMPTY_KNOWLEDGE,
    MAX_ATTEMPTS,
    RetrievedKnowledge,
)

# The identity the auth seam serves. The body's smuggled id MUST differ from
# it, or the binding assertion below would pass for the wrong reason.
SEAM_ATHLETE_ID = DEVELOPMENT_STUB_ATHLETE_ID
SMUGGLED_ATHLETE_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
assert SMUGGLED_ATHLETE_ID != SEAM_ATHLETE_ID

#: A raw payload the REAL gate accepts: warmup/active/cooldown heart-rate
#: zones over the declared LTHR, no sources (empty citation set), valid JSON
#: envelope. Built here, not imported, so these tests exercise the real
#: pipeline exactly as a client would.
VALID_PAYLOAD: dict[str, Any] = {
    "id": "w-1",
    "name": "Base endurance",
    "sport": "cycling",
    "objective": "Build aerobic base",
    "sources": [],
    "blocks": [
        {
            "role": "warmup",
            "steps": [
                {
                    "duration": {"kind": "minutes", "minutes": 10},
                    "role": "warmup",
                    "target": {"kind": "zone", "system": "heart_rate", "zone": "Z1"},
                }
            ],
        },
        {
            "role": "active",
            "steps": [
                {
                    "duration": {"kind": "minutes", "minutes": 40},
                    "role": "active",
                    "target": {"kind": "zone", "system": "heart_rate", "zone": "Z2"},
                }
            ],
        },
        {
            "role": "cooldown",
            "steps": [
                {
                    "duration": {"kind": "minutes", "minutes": 10},
                    "role": "cooldown",
                    "target": {"kind": "zone", "system": "heart_rate", "zone": "Z1"},
                }
            ],
        },
    ],
}

VALID_ENVELOPE = json.dumps({"prose": "Ride easy and steady.", "workout": VALID_PAYLOAD})

#: A payload the REAL gate rejects on the raw layer (no blocks at all), so
#: the retry path and the fail-closed 422 are exercised end to end.
INVALID_ENVELOPE = json.dumps({"prose": "Something.", "workout": {"id": "bad"}})

VALID_BODY: dict[str, Any] = {
    "objective": "Build aerobic base",
    "thresholds": {"system": "heart_rate", "lthr_bpm": 150},
}


class ScriptedModel:
    """A model callable that replays scripted responses and counts calls."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self._responses:
            raise AssertionError("the scripted model was called more times than scripted")
        return self._responses.pop(0)


def make_retrieve(
    knowledge: RetrievedKnowledge | None, *, calls: list[str] | None = None
) -> Any:
    """Build a retrieval callable yielding ONE retrieval result (or raising)."""

    async def retrieve(query: str) -> RetrievedKnowledge:
        if calls is not None:
            calls.append(query)
        if knowledge is None:
            raise RuntimeError("retrieval backend unavailable")
        return knowledge

    return retrieve


def make_client(
    model: ScriptedModel,
    retrieve: Any,
    monkeypatch: Any,
    *,
    body_overrides: dict[str, Any] | None = None,
) -> tuple[TestClient, FastAPI, list[tuple[Any, uuid.UUID]], dict[str, Any]]:
    """Build the app with every request-scoped dependency faked.

    Returns the client, the app, the list of ``(session, identity)``
    tuples that ``bind_session_user`` actually received in call order, and
    the request body the tests should post.
    """
    app = create_app()

    async def fake_seam() -> AsyncIterator[uuid.UUID]:
        # The production seam is an async GENERATOR dependency (it uses
        # yield), so the override must yield too — an override that returns
        # would not exercise the same dependency shape.
        yield SEAM_ATHLETE_ID

    async def fake_session() -> AsyncIterator[object]:
        # A sentinel: binding is captured and the repository is faked, so no
        # database session is ever needed.
        yield object()

    bindings: list[tuple[Any, uuid.UUID]] = []

    def record_binding(session: Any, athlete_id: uuid.UUID) -> None:
        bindings.append((session, athlete_id))

    class FakeProfileRepository:
        async def get_profile(self, session: Any, athlete_id: uuid.UUID) -> None:
            return None

    app.dependency_overrides[get_current_athlete] = fake_seam
    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_model_client] = lambda: model
    app.dependency_overrides[get_retrieve] = lambda: retrieve

    # The route imported these names into its own namespace; patch them THERE
    # or the real repository/binder would run against the sentinel session.
    monkeypatch.setattr(routes_generate, "bind_session_user", record_binding)
    monkeypatch.setattr(routes_generate, "ProfileRepository", FakeProfileRepository)

    request_body = {**VALID_BODY, **body_overrides} if body_overrides else VALID_BODY
    client = TestClient(app)
    return client, app, bindings, request_body


def post_generate(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/generate", json=body)


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_success_returns_workout_prose_knowledge_and_attempts(monkeypatch: Any) -> None:
    model = ScriptedModel(VALID_ENVELOPE)
    retrieve_calls: list[str] = []
    client, _app, _bindings, body = make_client(
        model, make_retrieve(EMPTY_KNOWLEDGE, calls=retrieve_calls), monkeypatch
    )

    response = post_generate(client, body)

    assert response.status_code == 200
    data = response.json()
    assert data["workout"]["name"] == "Base endurance"
    assert data["workout"]["blocks"][1]["steps"][0]["target"]["zone"] == "Z2"
    assert data["prose"] == "Ride easy and steady."
    assert data["knowledge_used"] is False
    assert data["attempts"] == 1
    # The success body carries NOTHING else: no stub identity, no exception
    # text, no credentials — the exact key set is part of the contract.
    assert set(data.keys()) == {"workout", "prose", "knowledge_used", "attempts", "warnings"}
    # The pipeline really ran: retrieval was consulted and degraded to empty.
    assert len(retrieve_calls) == 1
    assert model.call_count == 1


def test_success_knowledge_used_true_when_retrieval_has_citations(monkeypatch: Any) -> None:
    """The knowledge_used flag is not just stuck at False: a retrieval result
    with citable knowledge AND honest citations in the payload reports True."""
    cited_payload = {**VALID_PAYLOAD, "sources": ["docs/base.pdf"]}
    cited_envelope = json.dumps({"prose": "Ride easy.", "workout": cited_payload})
    model = ScriptedModel(cited_envelope)
    knowledge = RetrievedKnowledge(
        text="Base riding guidance.", citation_ids=frozenset({"docs/base.pdf"})
    )
    client, _app, _bindings, body = make_client(model, make_retrieve(knowledge), monkeypatch)

    response = post_generate(client, body)

    assert response.status_code == 200
    assert response.json()["knowledge_used"] is True


def test_success_carries_warnings_but_never_errors(monkeypatch: Any) -> None:
    """Advisory findings ride along on the 200; error findings never do.

    The deep-negative TSB state (ctl 60, atl 90, tsb -35) makes the REAL
    plan-rule validator emit the advisory ``tsb_fatigue_debt`` warning while
    still succeeding — the warning is produced by the gate, not faked.
    """
    model = ScriptedModel(VALID_ENVELOPE)
    client, _app, _bindings, body = make_client(
        model, make_retrieve(EMPTY_KNOWLEDGE), monkeypatch
    )
    body = {**body, "ctl": 60.0, "atl": 90.0, "tsb": -35.0}

    response = post_generate(client, body)

    assert response.status_code == 200
    data = response.json()
    warnings = data["warnings"]
    assert [w["code"] for w in warnings] == ["tsb_fatigue_debt"]
    assert all(w["severity"] == "warning" for w in warnings)
    assert all(w["source"] == "model_rules" for w in warnings)
    # Errors do not appear on a success response: only warnings ride along.
    assert not any(w["severity"] == "error" for w in warnings)


# ---------------------------------------------------------------------------
# Gate exhaustion
# ---------------------------------------------------------------------------


def test_gate_exhaustion_returns_422_with_findings_sources_and_attempts(
    monkeypatch: Any,
) -> None:
    model = ScriptedModel(INVALID_ENVELOPE, INVALID_ENVELOPE)
    client, _app, _bindings, body = make_client(
        model, make_retrieve(EMPTY_KNOWLEDGE), monkeypatch
    )

    response = post_generate(client, body)

    assert response.status_code == 422
    data = response.json()
    # Both the initial attempt AND the one retry ran, then it failed closed.
    assert data["attempts"] == MAX_ATTEMPTS == 2
    assert data["findings"], "a refused generation must say why"
    expected_sources = {"model_response", "raw_payload", "model_rules"}
    for finding in data["findings"]:
        assert set(finding.keys()) == {"source", "code", "severity", "message"}
        assert finding["source"] in expected_sources
        assert finding["severity"] == "error"
    codes = {finding["code"] for finding in data["findings"]}
    assert "retries_exhausted" in codes
    assert "empty_workout" in codes
    assert model.call_count == 2


# ---------------------------------------------------------------------------
# Retrieval degradation
# ---------------------------------------------------------------------------


def test_empty_retrieval_still_succeeds_with_knowledge_used_false(
    monkeypatch: Any,
) -> None:
    model = ScriptedModel(VALID_ENVELOPE)
    client, _app, _bindings, body = make_client(
        model, make_retrieve(EMPTY_KNOWLEDGE), monkeypatch
    )

    response = post_generate(client, body)

    assert response.status_code == 200
    data = response.json()
    assert data["knowledge_used"] is False
    assert data["attempts"] == 1
    assert data["workout"]["name"] == "Base endurance"


def test_failing_retrieval_still_succeeds_with_knowledge_used_false(
    monkeypatch: Any,
) -> None:
    """A retrieval failure NEVER fails generation — the pipeline degrades."""
    model = ScriptedModel(VALID_ENVELOPE)
    client, _app, _bindings, body = make_client(model, make_retrieve(None), monkeypatch)

    response = post_generate(client, body)

    assert response.status_code == 200
    data = response.json()
    assert data["knowledge_used"] is False
    assert data["attempts"] == 1
    assert data["workout"]["name"] == "Base endurance"


# ---------------------------------------------------------------------------
# Validation before the pipeline
# ---------------------------------------------------------------------------


def test_malformed_body_rejected_before_pipeline_runs(monkeypatch: Any) -> None:
    """A body without its required threshold is refused with 422 BEFORE the
    pipeline is reached: the scripted model and retrieval record ZERO calls —
    a status-code-only assertion would not prove the ordering."""
    model = ScriptedModel()
    retrieve_calls: list[str] = []
    client, _app, _bindings, _body = make_client(
        model, make_retrieve(EMPTY_KNOWLEDGE, calls=retrieve_calls), monkeypatch
    )

    response = client.post(
        "/generate", json={"objective": "Build aerobic base"}
    )

    assert response.status_code == 422
    assert model.call_count == 0, "the model must not be called for a malformed body"
    assert retrieve_calls == [], "retrieval must not run for a malformed body"


def test_blank_objective_rejected_before_pipeline_runs(monkeypatch: Any) -> None:
    model = ScriptedModel()
    retrieve_calls: list[str] = []
    client, _app, _bindings, _body = make_client(
        model, make_retrieve(EMPTY_KNOWLEDGE, calls=retrieve_calls), monkeypatch
    )

    response = client.post("/generate", json={**VALID_BODY, "objective": "   "})

    assert response.status_code == 422
    assert model.call_count == 0
    assert retrieve_calls == []


# ---------------------------------------------------------------------------
# Session binding: the auth seam wins, the body never does
# ---------------------------------------------------------------------------


def test_session_is_bound_to_seam_identity_never_to_body_supplied_id(
    monkeypatch: Any,
) -> None:
    """The security property behind the P2c fail-closed repository guard.

    The body smuggles a different athlete id under two plausible keys; the
    test captures what ``bind_session_user`` ACTUALLY received and asserts it
    was the seam identity — a status-code-only assertion cannot see this.
    """
    model = ScriptedModel(VALID_ENVELOPE)
    client, _app, bindings, body = make_client(
        model,
        make_retrieve(EMPTY_KNOWLEDGE),
        monkeypatch,
        body_overrides={
            "user_id": str(SMUGGLED_ATHLETE_ID),
            "athlete_id": str(SMUGGLED_ATHLETE_ID),
        },
    )

    response = post_generate(client, body)

    assert response.status_code == 200
    # THE assertion: the binder received ONLY the seam identity — the body's
    # smuggled id reached neither the binding nor any identity use.
    assert bindings == [(bindings[0][0], SEAM_ATHLETE_ID)]
    assert SMUGGLED_ATHLETE_ID not in [athlete_id for _, athlete_id in bindings]
    assert str(SMUGGLED_ATHLETE_ID) not in response.text
    # And the binding happened before the pipeline ran (the model answered).
    assert model.call_count == 1


# ---------------------------------------------------------------------------
# Import/build safety
# ---------------------------------------------------------------------------


def test_app_import_and_openapi_need_no_database_and_no_key(monkeypatch: Any) -> None:
    """Importing the app module, building the app, and generating the OpenAPI
    document must not require a database URL or an API key.

    ``include_router`` is LAZY on this fastapi version, so ``app.routes``
    does not list the nested route — the OpenAPI document is the honest
    effective-route surface.
    """
    monkeypatch.delenv("CYCLOAI_API_KEY", raising=False)
    monkeypatch.delenv("CYCLOAI_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = create_app()
    schema = app.openapi()

    assert "/generate" in schema["paths"]
    assert "post" in schema["paths"]["/generate"]
    # The success and rejection models are both documented.
    component_names = set(schema["components"]["schemas"])
    assert "GenerationSuccessOut" in component_names
    assert "GenerationRejectedOut" in component_names
