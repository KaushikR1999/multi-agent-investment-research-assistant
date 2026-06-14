from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    log_level: str = "INFO"
    llm_provider: str = "gemini"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_key: str | None = None
    llm_timeout_seconds: float = 60.0
    llm_output_token_limit: int = 4096
    synthesis_max_claims_per_output: int = 6
    synthesis_max_evidence_items: int = 40
    news_api_key: str | None = None
    backend_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
