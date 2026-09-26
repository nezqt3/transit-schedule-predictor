"""API schemas for dispatcher authentication."""

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Bearer token returned after successful authentication."""

    access_token: str = Field(..., description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="OAuth2 token type")
    expires_in: int = Field(..., description="Token lifetime in seconds")


class CurrentUser(BaseModel):
    """Authenticated dispatcher identity exposed to API clients."""

    username: str = Field(..., description="Dispatcher login")
    role: str = Field(default="dispatcher", description="Application role")
