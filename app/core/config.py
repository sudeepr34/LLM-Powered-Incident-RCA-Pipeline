from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal environments

    def load_dotenv() -> bool:
        return False


load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime config. Fields use ``default_factory`` so env vars are read on
    each construction (plain defaults freeze at class definition time).
    """

    log_level: str = field(default_factory=lambda: _env("RCA_LOG_LEVEL", "INFO"))
    default_source: str = field(default_factory=lambda: _env("RCA_DEFAULT_SOURCE", "unknown"))

    # Alert correlation
    correlation_window_seconds: int = field(
        default_factory=lambda: _env_int("RCA_CORRELATION_WINDOW_SECONDS", 900)
    )

    # LLM summarisation
    enable_llm: bool = field(default_factory=lambda: _env_bool("RCA_ENABLE_LLM", False))
    llm_provider: str = field(default_factory=lambda: _env("RCA_LLM_PROVIDER", "offline"))
    llm_model: str | None = field(default_factory=lambda: _env("RCA_LLM_MODEL"))
    llm_api_key: str | None = field(default_factory=lambda: _env("RCA_LLM_API_KEY"))
    llm_base_url: str | None = field(default_factory=lambda: _env("RCA_LLM_BASE_URL"))
    llm_timeout_seconds: float = field(
        default_factory=lambda: _env_float("RCA_LLM_TIMEOUT_SECONDS", 20.0)
    )
    llm_max_retries: int = field(default_factory=lambda: _env_int("RCA_LLM_MAX_RETRIES", 2))
    llm_temperature: float = field(default_factory=lambda: _env_float("RCA_LLM_TEMPERATURE", 0.2))
    llm_max_tokens: int = field(default_factory=lambda: _env_int("RCA_LLM_MAX_TOKENS", 600))
    llm_redact: bool = field(default_factory=lambda: _env_bool("RCA_LLM_REDACT", True))

    # Storage
    db_password: str | None = field(default_factory=lambda: _env("RCA_DB_PASSWORD"))
    database_url: str | None = field(default_factory=lambda: _env("RCA_DATABASE_URL"))


def get_settings() -> Settings:
    return Settings()
