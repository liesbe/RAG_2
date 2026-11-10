"""Application settings loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the phase 1 chatbot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gemini-3.8-flash"

    llm_max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_connect_timeout_seconds: float = Field(default=10.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def _validate_api_key(self) -> Self:
        value = self.llm_api_key.get_secret_value().strip()
        if not value or value == "your-key-here":
            raise ValueError("LLM_API_KEY ontbreekt of is nog de placeholder uit .env.example")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
