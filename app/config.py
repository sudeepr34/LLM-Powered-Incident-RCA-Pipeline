from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    log_level: str = os.getenv("RCA_LOG_LEVEL", "INFO")
    default_source: str = os.getenv("RCA_DEFAULT_SOURCE", "unknown")
    enable_llm: bool = os.getenv("RCA_ENABLE_LLM", "false").lower() == "true"
    llm_provider: str = os.getenv("RCA_LLM_PROVIDER", "mock")
    llm_model: str | None = os.getenv("RCA_LLM_MODEL")


def get_settings() -> Settings:
    return Settings()
