"""Explicit configuration for the conversational development surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import os
from typing import Mapping

from ..models import ValidationError, require_text


DEFAULT_OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_LOCALE = "pt-BR"


class ConversationBackendKind(StrEnum):
    NONE = "none"
    OPENAI = "openai"
    LOCAL = "local"


def _optional_environment_text(
    environment: Mapping[str, str],
    name: str,
) -> str | None:
    value = environment.get(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class ConversationSettings:
    """Configuration values without any implicit provider or model choice."""

    backend: ConversationBackendKind
    model: str | None
    api_key: str | None = field(default=None, repr=False)
    locale: str = DEFAULT_LOCALE
    request_timeout_seconds: float = 45.0

    def __post_init__(self) -> None:
        if not isinstance(self.backend, ConversationBackendKind):
            raise ValidationError("conversation backend kind is invalid")
        if self.model is not None:
            require_text(self.model, "conversation model")
            if len(self.model) > 200:
                raise ValidationError("conversation model exceeds 200 characters")
        if self.api_key is not None:
            require_text(self.api_key, "OpenAI API key")
        require_text(self.locale, "conversation locale")
        if len(self.locale) > 32:
            raise ValidationError("conversation locale exceeds 32 characters")
        if isinstance(self.request_timeout_seconds, bool) or not isinstance(
            self.request_timeout_seconds,
            (int, float),
        ):
            raise ValidationError("request timeout must be a number")
        timeout = float(self.request_timeout_seconds)
        if not 1.0 <= timeout <= 120.0:
            raise ValidationError("request timeout must be from 1 to 120 seconds")
        object.__setattr__(self, "request_timeout_seconds", timeout)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ConversationSettings":
        source = os.environ if environment is None else environment
        raw_backend = source.get("DARWIN_LLM_BACKEND", "none").strip().lower()
        try:
            backend = ConversationBackendKind(raw_backend)
        except ValueError as exc:
            raise ValidationError(
                "DARWIN_LLM_BACKEND must be none, openai, or local"
            ) from exc

        raw_timeout = _optional_environment_text(
            source,
            "DARWIN_LLM_TIMEOUT_SECONDS",
        )
        try:
            timeout = 45.0 if raw_timeout is None else float(raw_timeout)
        except ValueError as exc:
            raise ValidationError(
                "DARWIN_LLM_TIMEOUT_SECONDS must be numeric"
            ) from exc

        return cls(
            backend=backend,
            model=_optional_environment_text(source, "DARWIN_LLM_MODEL"),
            api_key=_optional_environment_text(source, "OPENAI_API_KEY"),
            locale=source.get("DARWIN_CONVERSATION_LOCALE", DEFAULT_LOCALE).strip(),
            request_timeout_seconds=timeout,
        )
