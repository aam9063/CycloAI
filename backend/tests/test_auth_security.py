"""Tests for the P5a cryptographic auth core: hashing and session tokens.

No database, no network: this slice is the cryptographic core only, kept
free of FastAPI so it is unit-testable on its own.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from argon2.exceptions import InvalidHashError

from cycloai import auth
from cycloai.auth import security

USER_ID = uuid.UUID("6f1a2b3c-4d5e-4f60-8a71-9b2c3d4e5f60")
# String form for hand-built JWT payloads: PyJWT cannot JSON-serialize a
# uuid.UUID, and these payloads deliberately bypass create_token.
USER_ID_STR = str(USER_ID)
# 64 bytes: at/above the RFC 7518 minimum for every HMAC-SHA variant, so the
# HS512 confusion test triggers no InsecureKeyLengthWarning and the rejected
# algorithm is the only variable under test.
SECRET = (
    "test-secret-that-is-long-enough-for-hs256-signing-and-64-bytes"
    "-in-total-length"
)


@pytest.fixture(autouse=True)
def _isolated_secret(monkeypatch: pytest.MonkeyPatch):
    """Run every test against a known secret, with a cold settings cache.

    The settings cache is cleared before AND after so one test's secret can
    never leak into another, and the real backend/.env (if any) is bypassed
    via the environment for everything except the explicit .env-path test.
    """
    monkeypatch.setenv("JWT_SECRET", SECRET)
    security.get_settings.cache_clear()
    yield
    security.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_is_salted_same_password_different_hashes(self):
        first = auth.hash_password("correct horse battery staple")
        second = auth.hash_password("correct horse battery staple")
        assert first != second

    def test_verification_accepts_right_password(self):
        stored = auth.hash_password("correct horse battery staple")
        assert auth.verify_password(stored, "correct horse battery staple") is True

    def test_wrong_password_returns_false_without_raising(self):
        stored = auth.hash_password("correct horse battery staple")
        assert auth.verify_password(stored, "wrong password") is False

    def test_corrupted_stored_hash_returns_false_without_raising(self):
        stored = auth.hash_password("correct horse battery staple")
        for corrupted in (
            "",  # empty
            "not-a-hash-at-all",
            stored[:-4] + "zzzz",  # truncated/garbled valid-looking hash
            "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$invalidbase64!!",  # malformed
        ):
            # Must not raise InvalidHashError or anything else.
            assert auth.verify_password(corrupted, "correct horse battery staple") is False

    def test_argon2id_hashes_rejected_by_raw_verify_still_false(self):
        # Sanity: the library itself raises on a malformed hash; our wrapper
        # is what converts that into a safe False.
        with pytest.raises(InvalidHashError):
            security._hasher.verify("garbage", "anything")

    def test_empty_password_rejected_at_hashing_boundary(self):
        with pytest.raises(auth.PasswordValidationError):
            auth.hash_password("")

    def test_absurdly_long_password_rejected_at_hashing_boundary(self):
        with pytest.raises(auth.PasswordValidationError):
            auth.hash_password("x" * (security.MAX_PASSWORD_LENGTH + 1))


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding, exactly as JWT segments are."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _forged_payload(claims: dict) -> str:
    return _b64url(json.dumps(claims).encode())


class TestSessionTokens:
    def test_round_trip_returns_equal_uuid_of_uuid_type(self):
        # The assertion whose absence let a str/UUID boundary mismatch
        # through: the returned value must EQUAL the input uuid.UUID (not
        # merely be string-equal) and must BE a uuid.UUID.
        token = auth.create_token(USER_ID)
        verified = auth.verify_token(token)
        assert verified == USER_ID
        assert type(verified) is uuid.UUID

    def test_create_token_accepts_uuid_and_verify_returns_uuid(self):
        assert isinstance(USER_ID, uuid.UUID)  # the input really is a UUID
        verified = auth.verify_token(auth.create_token(USER_ID))
        assert isinstance(verified, uuid.UUID)
        # String form is also accepted at the create boundary.
        assert (
            auth.verify_token(auth.create_token(USER_ID_STR)) == USER_ID
        )

    def test_sub_not_a_uuid_returns_none_without_raising(self):
        # Valid signature, but a subject that is not a valid identity is not
        # an identity: rejected as unauthenticated, never raised.
        token = jwt.encode(
            {
                "sub": "not-a-uuid",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "typ": security.ACCESS_TOKEN_TYPE,
            },
            SECRET,
            algorithm="HS256",
        )
        assert auth.verify_token(token) is None

    def test_empty_sub_returns_none(self):
        token = jwt.encode(
            {
                "sub": "",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "typ": security.ACCESS_TOKEN_TYPE,
            },
            SECRET,
            algorithm="HS256",
        )
        assert auth.verify_token(token) is None

    def test_missing_sub_returns_none(self):
        token = jwt.encode(
            {
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "typ": security.ACCESS_TOKEN_TYPE,
            },
            SECRET,
            algorithm="HS256",
        )
        assert auth.verify_token(token) is None

    def test_expired_token_returns_none(self):
        now = datetime.now(UTC)
        payload = {
            "sub": USER_ID_STR,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "typ": security.ACCESS_TOKEN_TYPE,
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        assert auth.verify_token(token) is None

    def test_token_signed_with_different_secret_returns_none(self):
        token = jwt.encode(
            {
                "sub": USER_ID_STR,
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "typ": security.ACCESS_TOKEN_TYPE,
            },
            "a-completely-different-secret-value-used-to-sign",
            algorithm="HS256",
        )
        assert auth.verify_token(token) is None

    def test_tampered_payload_returns_none(self):
        token = auth.create_token(USER_ID)
        header, _payload, signature = token.split(".")
        # Forge a payload claiming a different user, keeping the original
        # (now-invalid) signature.
        forged_payload = _forged_payload(
            {"sub": "00000000-0000-0000-0000-000000000000", "typ": "access"}
        )
        assert auth.verify_token(f"{header}.{forged_payload}.{signature}") is None

    def test_malformed_token_returns_none(self):
        for bad in ("", "not.a.token", "a.b.c", auth.create_token(USER_ID) + "x"):
            assert auth.verify_token(bad) is None

    def test_algorithm_confusion_header_claiming_different_alg_is_rejected(self):
        # The classic algorithm-confusion attempt: a token whose header
        # declares "none" (unsigned) must be rejected even though our
        # verifier holds an HMAC secret.
        unsigned = jwt.encode(
            {
                "sub": USER_ID_STR,
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "typ": security.ACCESS_TOKEN_TYPE,
            },
            key="",
            algorithm="none",
        )
        assert auth.verify_token(unsigned) is None

        # The subtler variant: the same secret, but the header claims a
        # different (still-HMAC) algorithm, with a signature that is VALID
        # for that claimed algorithm. A verifier that trusted the header
        # would accept this; our pinned algorithms=["HS256"] must not.
        now = datetime.now(UTC)
        payload = {
            "sub": USER_ID_STR,
            "iat": now,
            "exp": now + timedelta(hours=1),
            "typ": security.ACCESS_TOKEN_TYPE,
        }
        hs512 = jwt.encode(payload, SECRET, algorithm="HS512")
        header = jwt.get_unverified_header(hs512)
        assert header["alg"] == "HS512"  # the confusion is real in the token
        assert auth.verify_token(hs512) is None

    def test_missing_secret_raises_clear_error_instead_of_fallback(self, monkeypatch, tmp_path):
        # Isolate from the environment AND from any real backend/.env.
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setattr(security, "_ENV_FILE", tmp_path / "absent.env")
        security.get_settings.cache_clear()
        with pytest.raises(auth.AuthConfigError) as excinfo:
            auth.create_token(USER_ID)
        assert "JWT_SECRET" in str(excinfo.value)

    def test_too_short_secret_is_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JWT_SECRET", "too-short")
        monkeypatch.setattr(security, "_ENV_FILE", tmp_path / "absent.env")
        security.get_settings.cache_clear()
        with pytest.raises(auth.AuthConfigError) as excinfo:
            auth.create_token(USER_ID)
        assert "too short" in str(excinfo.value)
        security.get_settings.cache_clear()

    def test_token_purpose_claim_keeps_refresh_from_working_as_access(self):
        refresh = auth.create_token(USER_ID, token_type="refresh")
        assert auth.verify_token(refresh) is None
        assert auth.verify_token(refresh, expected_type="refresh") == USER_ID


# ---------------------------------------------------------------------------
# Settings loading
# ---------------------------------------------------------------------------


def test_env_file_path_is_absolute_and_cwd_independent():
    # The module-anchored .env resolution must never depend on the working
    # directory: a relative path made the same command behave differently
    # depending on where it was launched (fixed twice already; do not regress).
    env_file = auth.get_env_file()
    assert env_file.is_absolute()
    assert env_file.name == ".env"
    assert env_file.parent.name == "backend"


def test_settings_load_from_environment_without_cwd_dependence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # a different working directory must not matter
    assert auth.get_settings().jwt_secret == SECRET
