from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Replay emulator configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="REPLAY_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 18081
    data_root: Path = Path("/data")
    ndtp_target_host: str = "backend"
    ndtp_target_port: int = 9201
    connect_timeout_s: float = 5.0
    reconnect_delay_s: float = 1.0
    handshake_delay_s: float = 0.2


settings = Settings()

