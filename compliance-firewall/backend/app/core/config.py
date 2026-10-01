"""Application settings, loaded from environment variables and the backend `.env` file."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required, no defaults: these must come from `.env` (or the environment). Startup fails if missing.
    groq_api_key: SecretStr
    groq_model: str = Field(min_length=1)
    database_url: str = Field(min_length=1)
    check_timeout_s: float = Field(default=8.0, gt=0, le=60)
    # Browser origins allowed by CORS (only Expo *web* needs this; native apps ignore CORS).
    # "*" is only honoured when DEBUG=true.
    cors_origins: str = ""
    debug: bool = False
    log_level: str = "INFO"
    # AI governance
    ai_enabled: bool = True  # kill switch: false = no LLM calls; answers that need AI fail closed
    ai_max_calls_per_minute: int = Field(default=25, ge=1, le=1000)  # stay under Groq free tier
    # AI security. Admin token: X-Admin-Token for rule edits, reviews and suite runs.
    # API token: X-API-Key for checks, chat, audit reads and the governance report.
    # Empty = those endpoints only work when DEBUG=true (fail closed).
    admin_token: SecretStr = SecretStr("")
    api_token: SecretStr = SecretStr("")
    # Per-client (IP) request limit on endpoints that can trigger AI calls.
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    # Privacy: redact personal data (emails, phones, cards, CNIC) before it is stored in the audit log.
    audit_redact_pii: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins if self.debug else [o for o in origins if o != "*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
