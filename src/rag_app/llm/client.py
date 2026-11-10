"""OpenAI-compatible LLM client with user-friendly error mapping."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterator

import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    Stream,
)
from openai.types.chat import ChatCompletionChunk

from rag_app.config import Settings
from rag_app.llm.prompts import build_messages

logger = logging.getLogger(__name__)
_INITIAL_RETRY_DELAY_SECONDS = 0.5
_MAX_RETRY_DELAY_SECONDS = 8.0


class LLMError(RuntimeError):
    """Error that can be shown to the user without leaking internals."""


def _retry_after_seconds(exc: APIStatusError) -> int | None:
    raw = exc.response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return None


def _retry_delay_seconds(exc: APIStatusError, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return float(retry_after)
    delay = min(_INITIAL_RETRY_DELAY_SECONDS * (2**attempt), _MAX_RETRY_DELAY_SECONDS)
    return delay * (1 - 0.25 * random.random())


def map_error(exc: Exception, timeout_seconds: float) -> LLMError | None:
    """Translate provider exceptions into user-facing errors, or return None."""
    if isinstance(exc, RateLimitError):
        retry_after = _retry_after_seconds(exc)
        if retry_after is not None:
            return LLMError(f"Limiet bereikt. Probeer het over ±{retry_after} seconden opnieuw.")
        return LLMError("Limiet bereikt. Probeer het later opnieuw.")
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return LLMError("API-key ongeldig of geen toegang. Controleer `.env`.")
    if isinstance(exc, APITimeoutError):
        return LLMError(f"Geen antwoord binnen {timeout_seconds:.0f} seconden. Probeer opnieuw.")
    if isinstance(exc, APIConnectionError):
        return LLMError("Kon de provider niet bereiken. Controleer je internetverbinding.")
    if isinstance(exc, InternalServerError):
        return LLMError("De provider heeft een storing. Probeer het later opnieuw.")
    if isinstance(exc, APIStatusError):
        return LLMError(
            f"De provider gaf een fout (status {exc.status_code}). Probeer het later opnieuw."
        )
    return None


class LLMClient:
    """Thin wrapper around the OpenAI SDK for a single-turn chat endpoint."""

    def __init__(self, settings: Settings, *, client: OpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=httpx2.Timeout(
                settings.llm_timeout_seconds,
                connect=settings.llm_connect_timeout_seconds,
            ),
            max_retries=0,
        )

    def _create_stream(self, user_message: str) -> Stream[ChatCompletionChunk]:
        for attempt in range(self._settings.llm_max_retries + 1):
            try:
                return self._client.chat.completions.create(
                    model=self._settings.llm_model,
                    messages=build_messages(user_message),
                    temperature=self._settings.llm_temperature,
                    max_tokens=self._settings.llm_max_output_tokens,
                    stream=True,
                )
            except APIStatusError as exc:
                retryable = exc.status_code == 429 or exc.status_code >= 500
                if not retryable or attempt >= self._settings.llm_max_retries:
                    raise
                logger.warning("Retrying LLM request after HTTP status %s", exc.status_code)
                time.sleep(_retry_delay_seconds(exc, attempt))
        raise RuntimeError("LLM request attempts were exhausted without a response")

    def stream_reply(self, user_message: str) -> Iterator[str]:
        """Yield the assistant reply as text fragments."""
        try:
            for chunk in self._create_stream(user_message):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            mapped = map_error(exc, self._settings.llm_timeout_seconds)
            if mapped is None:
                logger.error("Unexpected LLM error: %s", type(exc).__name__)
                raise
            logger.warning("LLM request failed: %s", type(exc).__name__)
            raise mapped from exc
