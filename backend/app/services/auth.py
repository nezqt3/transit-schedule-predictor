"""Authentication business logic independent from FastAPI routes."""

from pwdlib import PasswordHash

from app.repositories.auth import AuthRepository
from app.schemas.auth import CurrentUser

password_hash = PasswordHash.recommended()


class AuthService:
    """Authenticate dispatchers and bootstrap the first database account."""

    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    async def bootstrap(self, username: str, password: str) -> bool:
        """Create the first configured account without overwriting existing data."""
        return await self._repository.create_initial_user(
            username=username,
            password_hash=password_hash.hash(password),
        )

    async def authenticate(self, username: str, password: str) -> CurrentUser | None:
        """Verify credentials against the active PostgreSQL account."""
        user = await self._repository.get_active_user(username)
        if user is None or not password_hash.verify(password, user.password_hash):
            return None
        return CurrentUser(username=user.username, role=user.role)

    async def get_current_user(self, username: str) -> CurrentUser | None:
        """Resolve the current active account for authorization checks."""
        user = await self._repository.get_active_user(username)
        if user is None:
            return None
        return CurrentUser(username=user.username, role=user.role)
