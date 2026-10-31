"""Settings read from environment variables or a local .env file (never committed)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None

    extract_model: str = "claude-opus-5-5"
    extract_effort: str = "medium"
    max_attempts: int = 3

    elevenlabs_model: str = "eleven_flash_v2_5"
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"

    output_dir: Path = Path("out")
    webhook_secret: SecretStr | None = None
    log_level: str = "INFO"


class MissingKeyError(RuntimeError):
    """Raised when a feature needs an API key that is not configured."""


def require(secret: SecretStr | None, name: str) -> str:
    if secret is None or not secret.get_secret_value():
        raise MissingKeyError(f"{name} is not set. Add it to your .env file (see .env.example).")
    return secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
