"""Smoke tests for the Streamlit app, without network calls."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rag_app.config import get_settings

APP_PATH = Path(__file__).parents[2] / "src" / "rag_app" / "app.py"


def test_app_renders_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    app = AppTest.from_file(str(APP_PATH)).run()

    assert not app.exception
    assert [title.value for title in app.title] == ["Chatbot"]


def test_app_shows_config_error_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_API_KEY", "")

    app = AppTest.from_file(str(APP_PATH)).run()

    assert not app.exception
    assert any("Configuratie" in error.value for error in app.error)
