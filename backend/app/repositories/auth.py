"""PostgreSQL persistence for dispatcher accounts."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the small backend-owned database schema."""


class AuthUser(Base):
    """Dispatcher account stored in PostgreSQL."""

    __tablename__ = "auth_users"

    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="dispatcher")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AuthRepository:
    """Read and bootstrap authentication accounts in PostgreSQL."""

    def __init__(self, database_url: str, connect_timeout_s: float) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"timeout": connect_timeout_s},
        )
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def initialize(self) -> None:
        """Create backend-owned tables if they do not exist."""
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def create_initial_user(
        self,
        username: str,
        password_hash: str,
        role: str = "dispatcher",
    ) -> bool:
        """Insert a bootstrap account only when its username is absent."""
        async with self._sessions() as session:
            existing = await session.get(AuthUser, username)
            if existing is not None:
                return False
            session.add(AuthUser(username=username, password_hash=password_hash, role=role))
            await session.commit()
            return True

    async def get_active_user(self, username: str) -> AuthUser | None:
        """Return an enabled user by exact username."""
        async with self._sessions() as session:
            result = await session.execute(
                select(AuthUser).where(
                    AuthUser.username == username,
                    AuthUser.is_active.is_(True),
                )
            )
            return result.scalar_one_or_none()

    async def close(self) -> None:
        """Release all pooled database connections."""
        await self._engine.dispose()
