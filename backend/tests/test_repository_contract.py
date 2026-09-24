"""Structural guard for repository ownership (runs WITHOUT a database).

Why this exists: the schema port off Supabase dropped Row Level Security, so
authorization lives entirely in the application layer — concretely, in
``cycloai.db.repositories``. The invariant that keeps users isolated is that
**every public function touching user-owned data (profiles, conversations,
messages) declares a required ``user_id`` parameter and filters by it**.

A filter can be forgotten silently; a missing parameter cannot. This module
introspects the repository module and fails loudly when the invariant is
violated, so an unscoped accessor can never land quietly. A docstring is not
a guard; this is.

This module must NEVER require ``DATABASE_URL``: it imports pure Python and
asserts on structure and on caller-binding semantics only, the latter through
stub sessions (``session.info`` is a plain dict on a real AsyncSession, so the
binding decision is decidable without touching SQL). If it ever fails to find
the repository classes or their methods it must fail, not skip — a
silently-skipped guard is worse than none.
"""

from __future__ import annotations

import inspect
import uuid

import pytest

from cycloai.db import repositories

# The repository classes that guard user-owned data. All three must exist;
# if one is renamed or removed this guard fails instead of silently
# protecting nothing.
REPOSITORY_CLASSES = ("ProfileRepository", "ConversationRepository", "MessageRepository")

# Name fragments that mark a function as touching user-owned data. Any public
# callable whose name contains one of these MUST declare a required user_id.
OWNED_DATA_WORDS = ("profile", "conversation", "message")

# Names that suggest an ownerless fetch, forbidden regardless of signature.
# Each has an ownership-scoped replacement (see repositories.py).
FORBIDDEN_UNSCOPED_NAMES = frozenset(
    {
        "get_conversation",
        "get_conversation_by_id",
        "fetch_conversation",
        "find_conversation",
        "get_message",
        "get_message_by_id",
        "fetch_message",
        "find_message",
        "get_profile",
        "get_profile_by_id",
        "fetch_profile",
        "find_profile",
    }
)


def _public_functions_of_class(cls: type) -> dict[str, object]:
    """Public callables defined on the class itself (not inherited)."""
    return {
        name: attr
        for name, attr in vars(cls).items()
        if not name.startswith("_") and callable(attr)
    }


def _iter_owned_callables() -> list[tuple[str, inspect.Signature]]:
    """Every public callable in the repository layer that touches owned data.

    Covers both repository-class methods and module-level public functions.
    Fails the suite (never skips) if the expected classes or any owned-data
    function are missing: a guard that finds nothing to guard is broken.
    """
    found: list[tuple[str, inspect.Signature]] = []

    for class_name in REPOSITORY_CLASSES:
        cls = getattr(repositories, class_name, None)
        assert cls is not None, (
            f"cycloai.db.repositories no longer defines {class_name}. The "
            "ownership guard protects user data through this class; update "
            "REPOSITORY_CLASSES only if ownership genuinely moved elsewhere."
        )
        methods = _public_functions_of_class(cls)
        assert methods, (
            f"{class_name} has no public methods: the ownership guard has "
            "nothing to protect. This is a structural failure, not a skip."
        )
        for method_name, method in methods.items():
            found.append((f"{class_name}.{method_name}", inspect.signature(method)))

    for name, attr in vars(repositories).items():
        if name.startswith("_") or not callable(attr) or inspect.isclass(attr):
            continue
        found.append((name, inspect.signature(attr)))

    return found


def _owned_data_name(qualname: str) -> bool:
    lowered = qualname.lower()
    return any(word in lowered for word in OWNED_DATA_WORDS)


def _has_required_user_id(signature: inspect.Signature) -> bool:
    param = signature.parameters.get("user_id")
    return (
        param is not None
        and param.default is inspect.Parameter.empty
        and param.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    )


def test_every_owned_data_function_declares_required_user_id() -> None:
    """No user-owned accessor may exist without a required user_id parameter.

    This is the load-bearing assertion: if somebody adds an unscoped accessor
    (e.g. ``get_conversation(session, conversation_id)``), it fails here and
    cannot land quietly.
    """
    callables_ = _iter_owned_callables()
    assert callables_, "repository module exposes no public callables to guard"

    violations: list[str] = []
    for qualname, signature in callables_:
        if not _owned_data_name(qualname):
            continue
        param = signature.parameters.get("user_id")
        if param is None:
            violations.append(f"{qualname}: no user_id parameter at all")
        elif param.default is not inspect.Parameter.empty:
            violations.append(f"{qualname}: user_id has a default (callers may omit it)")
        elif param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            violations.append(f"{qualname}: user_id is a *args/**kwargs catch-all")

    assert not violations, (
        "Repository functions touching user-owned data must declare a "
        "required user_id parameter (RLS was dropped with the Supabase port; "
        "this layer is the only authorization left):\n  "
        + "\n  ".join(violations)
    )


def test_no_public_function_is_named_like_an_unscoped_fetch() -> None:
    """Ownerless-sounding accessors are forbidden unless explicitly scoped.

    The canonical violation the parent spec names is ``get_conversation``
    with no owner parameter. A scoped variant (required ``user_id``, filtered
    query) is legitimate and is what ``repositories.py`` ships; the ban
    fires only when one of these names also lacks a required ``user_id`` —
    exactly the "id-only lookup" shape this layer must never offer.
    """
    offenders: list[str] = []
    for qualname, signature in _iter_owned_callables():
        leaf_name = qualname.split(".")[-1]
        unscoped = not _has_required_user_id(signature)
        if unscoped and (
            leaf_name in FORBIDDEN_UNSCOPED_NAMES
            or _owned_data_name(leaf_name)
            and leaf_name.startswith(("get_by_id", "fetch_by_id", "find_by_id"))
        ):
            offenders.append(qualname)

    assert not offenders, (
        "These functions are named like an ownerless fetch and lack a "
        "required user_id — a cross-user read is a data leak once RLS is "
        f"gone: {offenders}. Every accessor for user-owned data must take "
        "user_id and filter by it."
    )


def test_owned_functions_operate_through_a_session() -> None:
    """Owned-data functions must take a session (no hidden ambient connections)."""
    offenders = [
        qualname
        for qualname, signature in _iter_owned_callables()
        if _owned_data_name(qualname) and "session" not in signature.parameters
    ]
    assert not offenders, (
        f"These functions bypass the session (and thus transaction and "
        f"caller-binding discipline): {offenders}"
    )


def test_bind_session_user_exists_as_the_caller_binding_point() -> None:
    """The defense-in-depth binding point must exist and require a user_id.

    Repositories refuse a user_id that mismatches the session-bound caller;
    that mechanism only works if the app layer has something to bind with.
    """
    func = getattr(repositories, "bind_session_user", None)
    assert func is not None, (
        "cycloai.db.repositories must expose bind_session_user: without it "
        "the session-bound caller check (defense in depth on top of the "
        "user_id filters) cannot be enforced by request paths."
    )
    param = inspect.signature(func).parameters.get("user_id")
    assert param is not None and param.default is inspect.Parameter.empty, (
        "bind_session_user must require user_id explicitly"
    )


def test_unbound_session_error_is_a_dedicated_loud_failure() -> None:
    """An unbound session must raise a dedicated error, not collapse to None.

    A forgotten bind silently disables the whole ownership check, so the
    failure must be loud and nameable. It must NOT be a "not found" style
    outcome either: hiding a wiring bug from the developer is how it survives
    to production.
    """
    error = getattr(repositories, "UnboundSessionError", None)
    assert error is not None, (
        "cycloai.db.repositories must define UnboundSessionError: an unbound "
        "session is a wiring bug (the ownership check would be silently "
        "disabled) and must be raised loudly, never tolerated silently."
    )
    assert inspect.isclass(error) and issubclass(error, Exception)


def test_bind_internal_session_is_the_explicit_greppable_escape_hatch() -> None:
    """Cross-user access needs a named, greppable entry point.

    Trusted internal code (migrations, ingestion, cross-user test fixtures)
    must be able to bind explicitly; the sentinel binding must be a visible,
    searchable act rather than a silent default.
    """
    func = getattr(repositories, "bind_internal_session", None)
    assert func is not None, (
        "cycloai.db.repositories must expose bind_internal_session: trusted "
        "internal code needs one explicit, greppable binding entry point, so "
        "cross-user permissiveness is never the silent default."
    )
    assert list(inspect.signature(func).parameters) == ["session"], (
        "bind_internal_session must take only the session (no user_id: it "
        "binds internal code, not an identity)"
    )


# ---------------------------------------------------------------------------
# Behavioural guard: the caller check must FAIL CLOSED (no database needed).
#
# ``session.info`` is a plain mutable mapping on a real AsyncSession, and the
# binding decision must be decidable before any query runs, so a stub carrying
# only ``info`` exercises the real guard code path. A permissive default here
# would mean any request path that forgets to bind silently disables the
# entire ownership check — the exact bug class this layer exists to catch.
# ---------------------------------------------------------------------------


class _StubSession:
    """Minimal AsyncSession stand-in: only what the guard itself touches.

    Deliberately has NO query surface (``scalars``/``execute``): if a
    repository call ever got past the guard on a session it should have
    refused, these tests would fail loudly with AttributeError instead of
    passing silently.
    """

    def __init__(self) -> None:
        self.info: dict[str, object] = {}


class _NoRows:
    """Query result that behaves like "no matching row" (``first()`` → None)."""

    def first(self) -> None:
        return None


class _EmptySession(_StubSession):
    """Stub whose queries never return a row: the "does not exist" path."""

    async def scalars(self, *_args: object, **_kwargs: object) -> _NoRows:
        return _NoRows()


class TestUnboundSessionFailsClosed:
    """An unbound session is a wiring error, and must fail LOUD."""

    async def test_every_repository_call_raises_on_an_unbound_session(self) -> None:
        # _StubSession has no query surface at all: if any call got past the
        # guard, the test would fail with AttributeError, not pass.
        profile_repo = repositories.ProfileRepository()
        conv_repo = repositories.ConversationRepository()
        msg_repo = repositories.MessageRepository()
        user_id = uuid.uuid4()
        conversation_id = uuid.uuid4()
        calls = [
            profile_repo.get_profile(_StubSession(), user_id),
            profile_repo.update_profile(_StubSession(), user_id, display_name="x"),
            conv_repo.create_conversation(_StubSession(), user_id),
            conv_repo.list_conversations(_StubSession(), user_id),
            conv_repo.get_conversation(_StubSession(), user_id, conversation_id),
            conv_repo.update_conversation(
                _StubSession(), user_id, conversation_id, title="x"
            ),
            msg_repo.append_message(
                _StubSession(), user_id, conversation_id, role="user", content="x"
            ),
            msg_repo.list_messages(_StubSession(), user_id, conversation_id),
        ]
        for call in calls:
            with pytest.raises(
                repositories.UnboundSessionError,
                match="not bound",
            ):
                await call

    async def test_read_and_write_are_both_blocked_for_one_caller(self) -> None:
        # A single session, first used for a read and then for a write: both
        # must raise — silence on either path would be a silent leak.
        session = _StubSession()
        with pytest.raises(repositories.UnboundSessionError):
            await repositories.ProfileRepository().get_profile(session, uuid.uuid4())
        with pytest.raises(repositories.UnboundSessionError):
            await repositories.ConversationRepository().create_conversation(
                session, uuid.uuid4()
            )


class TestBindingIsMonotonic:
    async def test_binding_the_same_user_twice_is_a_no_op(self) -> None:
        session = _StubSession()
        user_id = uuid.uuid4()
        repositories.bind_session_user(session, user_id)
        repositories.bind_session_user(session, user_id)  # must not raise
        assert repositories._caller_matches(session, user_id) is True

    async def test_rebinding_to_a_different_user_is_refused(self) -> None:
        session = _StubSession()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        repositories.bind_session_user(session, user_a)
        with pytest.raises(ValueError, match="already bound"):
            repositories.bind_session_user(session, user_b)
        # The original binding must survive the refused re-bind.
        assert repositories._caller_matches(session, user_a) is True
        assert repositories._caller_matches(session, user_b) is False


class TestInternalEscapeHatch:
    async def test_internally_bound_session_is_accepted(self) -> None:
        session = _EmptySession()
        repositories.bind_internal_session(session)
        # Accepted for ANY user id — and the call proceeds into the query
        # layer (the stub's ``None`` row), not blocked by the guard.
        assert repositories._caller_matches(session, uuid.uuid4()) is True
        assert (
            await repositories.ProfileRepository().get_profile(session, uuid.uuid4())
            is None
        )

    async def test_internal_binding_of_an_already_bound_session_is_refused(self) -> None:
        session = _StubSession()
        repositories.bind_session_user(session, uuid.uuid4())
        with pytest.raises(ValueError, match="already bound"):
            repositories.bind_internal_session(session)

    async def test_rebinding_over_an_internal_binding_is_refused(self) -> None:
        session = _StubSession()
        repositories.bind_internal_session(session)
        with pytest.raises(ValueError, match="already bound"):
            repositories.bind_session_user(session, uuid.uuid4())


class TestForeignAccessStaysQuiet:
    async def test_mismatch_is_indistinguishable_from_not_found(self) -> None:
        """A refusal for user B's id must be OBSERVABLY identical to not-found.

        Both calls run against the same "no row" stub: one is refused by the
        guard (foreign id), one reaches the query and finds nothing. The
        observable result must be the same ``None`` — not a distinct error
        that would confirm the id exists.
        """
        session = _EmptySession()
        user_a = uuid.uuid4()
        repositories.bind_session_user(session, user_a)
        repo = repositories.ProfileRepository()

        # Foreign id: refused by the guard → None, with no exception.
        foreign = await repo.get_profile(session, uuid.uuid4())
        assert foreign is None

        # The same call over an internally bound session (guard passes) on a
        # non-existent id: the query finds nothing → also None.
        internal = _EmptySession()
        repositories.bind_internal_session(internal)
        missing = await repo.get_profile(internal, uuid.uuid4())
        assert foreign is None and missing is None

    async def test_foreign_list_refusal_is_the_documented_empty_result(self) -> None:
        session = _StubSession()
        repositories.bind_session_user(session, uuid.uuid4())
        # A foreign conversation's messages are structurally absent: None,
        # exactly as the docstring promises for an invisible conversation.
        assert (
            await repositories.MessageRepository().list_messages(
                session, uuid.uuid4(), uuid.uuid4()
            )
            is None
        )

    async def test_foreign_read_and_write_are_both_blocked(self) -> None:
        session = _StubSession()
        repositories.bind_session_user(session, uuid.uuid4())
        repo = repositories.ProfileRepository()

        assert await repo.get_profile(session, uuid.uuid4()) is None
        assert (
            await repo.update_profile(session, uuid.uuid4(), display_name="hijacked")
            is None
        )
