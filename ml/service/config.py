from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ML inference service configuration, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ml_service_host: str = "0.0.0.0"
    ml_service_port: int = 8001

    artifacts_dir: str = "artifacts"
    model_name: str = "baseline"
    model_version: str = "1.0"
    schedule_plan_path: str = "data/raw/validate/schedule_plan.csv"

    log_level: str = "INFO"


settings = Settings()
