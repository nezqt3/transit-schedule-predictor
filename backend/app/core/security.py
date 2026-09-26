"""JWT creation and validation for the dispatcher API."""

from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError

from app.core.config import settings

TOKEN_ISSUER = "transport-delay-backend"


def create_access_token(username: str, role: str) -> tuple[str, int]:
    """Create a signed access token and return it with its lifetime in seconds."""
    lifetime = timedelta(minutes=settings.auth_token_expire_minutes)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": username,
            "role": role,
            "iat": now,
            "exp": now + lifetime,
            "iss": TOKEN_ISSUER,
        },
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> tuple[str, str] | None:
    """Return username and role or ``None`` for an invalid/expired token."""
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            issuer=TOKEN_ISSUER,
        )
    except InvalidTokenError:
        return None
    subject = payload.get("sub")
    role = payload.get("role")
    if not isinstance(subject, str) or not isinstance(role, str):
        return None
    return subject, role
