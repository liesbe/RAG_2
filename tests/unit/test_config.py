"""Tests for settings defaults and validation."""

import pytest
from pydantic import ValidationError

from rag_app.config import Settings


def test_settings_use_documented_defaults() -> None:
    settings = Settings(_env_file=None, llm_api_key="test-key")

    assert settings.llm_model == "gemini-3.8-flash"
    assert settings.llm_max_output_tokens == 1024
    assert settings.llm_temperature == 0.7
    assert settings.llm_timeout_seconds == 30.0
    assert settings.llm_connect_timeout_seconds == 10.0
    assert settings.llm_max_retries == 2


def test_settings_require_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_invalid_token_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_api_key="test-key", llm_max_output_tokens=0)


def test_settings_reject_the_example_placeholder_key() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_api_key="your-key-here")
