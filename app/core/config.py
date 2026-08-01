from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal environments
    def load_dotenv() -> bool:
        return False

load_dotenv()


@dataclass(frozen=True)
class Settings:
    log_level: str = os.getenv("RCA_LOG_LEVEL", "INFO")
    default_source: str = os.getenv("RCA_DEFAULT_SOURCE", "unknown")
    enable_llm: bool = os.getenv("RCA_ENABLE_LLM", "false").lower() == "true"
    llm_provider: str = os.getenv("RCA_LLM_PROVIDER", "mock")
    llm_model: str | None = os.getenv("RCA_LLM_MODEL")
    llm_api_key: str | None = os.getenv("RCA_LLM_API_KEY")
    db_password: str | None = os.getenv("RCA_DB_PASSWORD")
    database_url: str | None = os.getenv("RCA_DATABASE_URL")


def get_settings() -> Settings:
    return Settings()
