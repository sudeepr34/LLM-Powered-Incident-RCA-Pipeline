from __future__ import annotations

from app.core.config import get_settings


def test_settings_expose_secrets_separately(monkeypatch) -> None:
    monkeypatch.setenv("RCA_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("RCA_LLM_API_KEY", "super-secret-key")
    monkeypatch.setenv("RCA_DB_PASSWORD", "db-secret-pass")

    settings = get_settings()

    assert settings.log_level == "DEBUG"
    assert settings.llm_api_key == "super-secret-key"
    assert settings.db_password == "db-secret-pass"
