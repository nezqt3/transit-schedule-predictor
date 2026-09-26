import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend runtime configuration, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    ml_service_url: str = "http://ml:8001"
    ml_request_timeout_s: float = 5.0

    ndtp_host: str = "0.0.0.0"
    ndtp_port: int = 9201

    runtime_schedule_path: str = "data/raw/validate/schedule_plan.csv"
    runtime_traffic_path: str = "data/raw/validate/traffic.csv"
    replay_schedule_path: str = "data/raw/test/schedule.csv"
    replay_traffic_path: str = "data/raw/test/traffic.csv"
    replay_labels_path: str = "data/raw/labels/labels_test.csv"
    dataset_replay_url: str | None = None

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "transport"
    postgres_user: str = "transport"
    postgres_password: str = "transport"

    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def load_settings() -> Settings:
    """Load settings, tolerating a missing .env file."""
    env_file = os.getenv("ENV_FILE", ".env")
    if os.path.exists(env_file):
        return Settings(_env_file=env_file)
    return Settings()


settings = load_settings()
