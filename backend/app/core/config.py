"""Application settings, loaded from environment variables / .env."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings. No secrets are hardcoded; all come from the environment."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg://disputeiq:disputeiq@localhost:5432/disputeiq"

    # Primary: Google Gemini Flash (free tier). "mock" is an explicit offline fallback only.
    llm_provider: Literal["gemini", "anthropic", "openai", "mock"] = "gemini"
    llm_model: str = ""  # optional override; for Gemini prefer GEMINI_MODEL
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"  # free-tier Flash; override via GEMINI_MODEL
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_max_retries: int = Field(default=3, ge=0)
    llm_timeout_s: float = Field(default=60, gt=0)
    usd_inr: float = Field(default=88.0, gt=0)

    # "hash" = dependency-free deterministic feature hashing (also the fallback for "local").
    embedding_provider: Literal["local", "openai", "hash"] = "hash"
    embedding_model: str = ""
    embedding_dim: int = Field(default=384, gt=0)

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @field_validator("gemini_api_key", "anthropic_api_key", "openai_api_key", mode="before")
    @classmethod
    def _strip_secrets(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
