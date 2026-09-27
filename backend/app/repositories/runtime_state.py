"""PostgreSQL persistence for the latest predictions and incident lifecycle."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.auth import Base
from app.schemas.incident import Incident
from app.schemas.prediction import StoredPrediction


class PredictionRecord(Base):
    __tablename__ = "runtime_predictions"

    tr_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class IncidentRecord(Base):
    __tablename__ = "runtime_incidents"

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tr_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RuntimeStateRepository:
    """Store API models as version-tolerant JSON documents in PostgreSQL."""

    def __init__(self, database_url: str, connect_timeout_s: float) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"timeout": connect_timeout_s},
        )
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def load_predictions(self) -> list[StoredPrediction]:
        async with self._sessions() as session:
            rows = (await session.execute(select(PredictionRecord))).scalars().all()
            return [StoredPrediction.model_validate_json(row.payload) for row in rows]

    async def load_incidents(self) -> list[Incident]:
        async with self._sessions() as session:
            rows = (await session.execute(select(IncidentRecord))).scalars().all()
            return [Incident.model_validate_json(row.payload) for row in rows]

    async def save_prediction(self, prediction: StoredPrediction) -> None:
        async with self._sessions() as session:
            await session.merge(PredictionRecord(
                tr_id=prediction.tr_id,
                prediction_time=prediction.prediction_time,
                payload=prediction.model_dump_json(),
            ))
            await session.commit()

    async def save_incident(self, incident: Incident) -> None:
        async with self._sessions() as session:
            await session.merge(IncidentRecord(
                incident_id=incident.incident_id,
                tr_id=incident.tr_id,
                status=incident.status,
                payload=incident.model_dump_json(),
                updated_at=incident.updated_at,
            ))
            await session.commit()

    async def close(self) -> None:
        await self._engine.dispose()
