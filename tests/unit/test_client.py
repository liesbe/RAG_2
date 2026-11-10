"""Tests for the LLM client and its error mapping."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from rag_app.config import Settings
from rag_app.llm.client import LLMClient, LLMError, map_error
from rag_app.llm.prompts import build_messages


def _settings() -> Settings:
    return Settings(_env_file=None, llm_api_key="test-key")


def _response(status: int, headers: dict[str, str] | None = None) -> httpx2.Response:
    return httpx2.Response(
        status_code=status,
        headers=headers,
        request=httpx2.Request("POST", "https://example.test/v1/chat/completions"),
    )


def _chunk(text: str | None, *, with_choice: bool = True) -> SimpleNamespace:
    if not with_choice:
        return SimpleNamespace(choices=[])
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def _mock_client() -> MagicMock:
    return MagicMock(spec=OpenAI)


def test_stream_reply_streams_text_and_sends_only_the_current_question() -> None:
    mock = _mock_client()
    mock.chat.completions.create.return_value = iter(
        [_chunk("Hallo "), _chunk(None), _chunk("wereld"), _chunk(None, with_choice=False)]
    )
    client = LLMClient(_settings(), client=cast(OpenAI, mock))

    assert "".join(client.stream_reply("Hoi")) == "Hallo wereld"

    kwargs = mock.chat.completions.create.call_args.kwargs
    assert kwargs["messages"] == build_messages("Hoi")
    assert len(kwargs["messages"]) == 2
    assert kwargs["model"] == "gemini-3.8-flash"
    assert kwargs["max_tokens"] == 1024
    assert kwargs["temperature"] == 0.7
    assert kwargs["stream"] is True


def test_map_rate_limit_reports_retry_after() -> None:
    exc = RateLimitError(
        "rate limited",
        response=_response(429, {"retry-after": "12"}),
        body=None,
    )

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "12 seconden" in str(mapped)


def test_map_rate_limit_without_retry_after_is_generic() -> None:
    exc = RateLimitError("rate limited", response=_response(429), body=None)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "later" in str(mapped)


def test_map_authentication_error_points_to_env() -> None:
    exc = AuthenticationError("no auth", response=_response(401), body=None)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "API-key" in str(mapped)


def test_map_timeout_uses_configured_seconds() -> None:
    exc = APITimeoutError(_response(200).request)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "30 seconden" in str(mapped)


def test_map_connection_error_mentions_internet() -> None:
    exc = APIConnectionError(request=_response(200).request)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "internetverbinding" in str(mapped)


def test_map_server_error_is_friendly() -> None:
    exc = InternalServerError("boom", response=_response(500), body=None)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "storing" in str(mapped)


def test_map_503_reports_provider_outage() -> None:
    exc = InternalServerError("overloaded", response=_response(503), body=None)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert str(mapped) == "De provider heeft een storing. Probeer het later opnieuw."


def test_map_other_status_error_includes_status_code() -> None:
    exc = APIStatusError("teapot", response=_response(418), body=None)

    mapped = map_error(exc, 30.0)

    assert mapped is not None
    assert "418" in str(mapped)


def test_map_unknown_error_returns_none() -> None:
    assert map_error(ValueError("something else"), 30.0) is None


def test_stream_reply_converts_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rag_app.llm.client.time.sleep", lambda _: None)
    mock = _mock_client()
    mock.chat.completions.create.side_effect = RateLimitError(
        "rate limited",
        response=_response(429, {"retry-after": "5"}),
        body=None,
    )
    client = LLMClient(_settings(), client=cast(OpenAI, mock))

    with pytest.raises(LLMError, match="Limiet bereikt"):
        list(client.stream_reply("Hoi"))
    assert mock.chat.completions.create.call_count == 3


def test_stream_reply_retries_provider_status_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rag_app.llm.client.time.sleep", lambda _: None)
    mock = _mock_client()
    mock.chat.completions.create.side_effect = [
        InternalServerError("temporary failure", response=_response(503), body=None),
        iter([_chunk("Hallo")]),
    ]
    client = LLMClient(_settings(), client=cast(OpenAI, mock))

    assert "".join(client.stream_reply("Hoi")) == "Hallo"
    assert mock.chat.completions.create.call_count == 2


def test_stream_reply_does_not_retry_timeout() -> None:
    mock = _mock_client()
    mock.chat.completions.create.side_effect = APITimeoutError(_response(200).request)
    client = LLMClient(_settings(), client=cast(OpenAI, mock))

    with pytest.raises(LLMError, match="Geen antwoord binnen 30 seconden"):
        list(client.stream_reply("Hoi"))

    assert mock.chat.completions.create.call_count == 1
