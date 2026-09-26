"""DI-зависимости API.

Единственный источник экземпляров сервисов: telemetry-стор живёт в
app.state, NDTP-сервер пишет в него, API читает.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.security import decode_access_token
from app.schemas.auth import CurrentUser
from app.services.auth import AuthService
from app.services.telemetry import TelemetryService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_telemetry_service(request: Request) -> TelemetryService:
    """Return the telemetry registry owned by the FastAPI application."""
    return request.app.state.telemetry


def get_auth_service(request: Request) -> AuthService:
    """Return database-backed auth or report temporary storage unavailability."""
    if not getattr(request.app.state, "auth_available", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication storage is unavailable",
        )
    return request.app.state.auth_service


async def get_current_user(
    request: Request,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    """Resolve a dispatcher from a Bearer header or HttpOnly session cookie."""
    token = bearer_token or request.cookies.get(settings.auth_cookie_name)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    identity = decode_access_token(token)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username, token_role = identity
    user = await auth_service.get_current_user(username)
    if user is None or user.role != token_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="account is disabled or no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
