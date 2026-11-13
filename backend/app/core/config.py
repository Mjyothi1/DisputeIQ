"""Application settings, loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed application settings. No secrets are hardcoded; all come from the environment."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: str = "http://localhost:5173"
    # Prototype reviewer auth: "name=key,name2=key2" (keys >= 8 chars). Empty = writes refused.
    reviewer_accounts: str = ""
    # Signs customer-portal session tokens. Recommended in production; if empty a key is derived
    # from REVIEWER_ACCOUNTS (see app/core/security.py). Never commit a real value.
    auth_secret: str = ""
    # Demo-only password for the six demo customers' portal logins (seeded with
    # BOOTSTRAP_DEMO_CUSTOMERS). Empty = no demo customer logins are created.
    demo_customer_password: str = ""
    max_request_bytes: int = Field(default=64_000, gt=0)

    database_url: str = "postgresql+psycopg://disputeiq:disputeiq@localhost:5432/disputeiq"

    # Primary: Google Gemini Flash (free tier). "mock" is an explicit offline fallback only.
    llm_provider: Literal["gemini", "anthropic", "openai", "mock"] = "gemini"
    llm_model: str = ""  # optional override; for Gemini prefer GEMINI_MODEL
    gemini_api_key: str = ""
    # Single source of truth for the default model. Override with GEMINI_MODEL. The name is NOT
    # verified against Google's live model list by this repo; confirm it with `python -m
    # app.agent.cli ping` (or the provider test) before a demo.
    gemini_model: str = "gemini-3.8-flash"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_max_retries: int = Field(default=3, ge=0)
    llm_timeout_s: float = Field(default=60, gt=0)
    usd_inr: float = Field(default=88.0, gt=0)

    # "hash" = dependency-free deterministic feature hashing (also the fallback for "local").
    embedding_provider: Literal["local", "openai", "hash"] = "hash"
    embedding_model: str = ""
    embedding_dim: int = Field(default=384, gt=0)

    # Fill an EMPTY database with the synthetic demo dataset on startup (never touches existing data).
    bootstrap_demo_data: bool = False
    # Opt-in, additive: add the six isolated demo customers (data_gen/demo_customers.py) on startup.
    # Matched by name, so it is idempotent and never edits or deletes existing rows. Turn it off
    # again after the first successful run.
    bootstrap_demo_customers: bool = False

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @field_validator("gemini_api_key", "anthropic_api_key", "openai_api_key", mode="before")
    @classmethod
    def _strip_secrets(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @property
    def resolved_database_url(self) -> str:
        """DATABASE_URL with a relative SQLite path pinned to the backend folder.

        ``sqlite:///./disputeiq.db`` used to resolve against whatever folder the command ran in, so
        starting the server from a different folder silently opened a new, empty database.
        """
        url = self.database_url
        # Render/Supabase hand out postgres:// or postgresql:// URLs; we ship the psycopg 3 driver.
        for scheme in ("postgres://", "postgresql://"):
            if url.startswith(scheme):
                return "postgresql+psycopg://" + url[len(scheme) :]
        prefix = "sqlite:///"
        if url.startswith(prefix) and not url.startswith("sqlite:////"):
            rel = url[len(prefix):]
            if rel and rel != ":memory:" and not Path(rel).is_absolute():
                return prefix + str((BACKEND_DIR / rel).resolve())
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
