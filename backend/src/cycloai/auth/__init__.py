"""CycloAI authentication.

P5a (this slice) owns the cryptographic core (password hashing and
session-token issuance/verification) and the database-backed service (user
registration and authentication), importable without FastAPI. The HTTP
endpoints, cookie handling and the replacement of the development auth seam
arrive in the next slice.
"""

from cycloai.auth.security import (
    ACCESS_TOKEN_TTL,
    ACCESS_TOKEN_TYPE,
    ALGORITHM,
    AuthConfigError,
    AuthSettings,
    PasswordValidationError,
    create_token,
    get_env_file,
    get_settings,
    hash_password,
    verify_password,
    verify_token,
)
from cycloai.auth.service import (
    EmailAlreadyRegisteredError,
    UserIdentity,
    authenticate_user,
    register_user,
)

__all__ = [
    "ACCESS_TOKEN_TTL",
    "ACCESS_TOKEN_TYPE",
    "ALGORITHM",
    "AuthConfigError",
    "AuthSettings",
    "PasswordValidationError",
    "create_token",
    "get_env_file",
    "get_settings",
    "hash_password",
    "verify_password",
    "verify_token",
    "EmailAlreadyRegisteredError",
    "UserIdentity",
    "authenticate_user",
    "register_user",
]
