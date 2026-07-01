"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Observability Watchdog"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://watchdog:watchdog@localhost:5432/watchdog"
    api_v1_prefix: str = "/api/v1"
    llm_provider: str = "template"
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 20


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
