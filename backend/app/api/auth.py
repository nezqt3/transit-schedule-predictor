"""Authentication endpoints used by Swagger UI and the dashboard."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import get_auth_service, get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.schemas.auth import CurrentUser, TokenResponse
from app.services.auth import AuthService

router = APIRouter()


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Войти в диспетчерскую",
    description="Проверяет логин и пароль и выдаёт JWT Bearer-токен.",
    responses={401: {"description": "Неверный логин или пароль"}},
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Authenticate a dispatcher and persist the JWT in an HttpOnly cookie."""
    user = await auth_service.authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(user.username, user.role)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=expires_in,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/v1",
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Текущий пользователь",
    responses={401: {"description": "Токен отсутствует, повреждён или истёк"}},
)
async def read_current_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Return the identity encoded in the current Bearer token."""
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выйти")
async def logout(response: Response) -> None:
    """Delete the browser session cookie."""
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/v1",
    )
