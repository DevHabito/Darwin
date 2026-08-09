"""Session-only conversational orchestration outside the frozen E043 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Protocol

from ..language import (
    DarwinLanguageGateway,
    ExpressionPlan,
    GroundedFact,
    LanguageExpression,
    LanguageMode,
    LanguageModelBackend,
    LanguageObservation,
    UnderstandingRequest,
)
from ..models import DarwinV50Error, ValidationError, require_text
from .config import ConversationBackendKind, ConversationSettings
from .openai_responses import JSONTransport, OpenAIResponsesBackend


MAX_SESSION_MESSAGES = 60
MAX_CONTEXT_MESSAGE_LENGTH = 2_000


class ConversationRuntimeError(DarwinV50Error):
    """Base error for the isolated conversational development runtime."""


class ConversationUnavailableError(ConversationRuntimeError):
    """Raised when no explicitly selected backend can answer a turn."""


class ConversationAvailability(StrEnum):
    PURE = "pure"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    CLOSED = "closed"


class ExplicitLocalBackend(LanguageModelBackend, Protocol):
    """A local backend must declare the exact configured model it serves."""

    model: str

    def clear_ephemeral_context(self) -> None:
        """Erase any pending turn data."""


@dataclass(frozen=True, slots=True)
class AuthorityMutationCounts:
    memory_writes: int = 0
    goal_changes: int = 0
    rzs_changes: int = 0
    sigma_changes: int = 0
    identity_changes: int = 0
    world_model_changes: int = 0
    actions_dispatched: int = 0
    actions_executed: int = 0


@dataclass(frozen=True, slots=True)
class ConversationSnapshot:
    requested_backend: ConversationBackendKind
    availability: ConversationAvailability
    language_mode: LanguageMode
    language_source: str
    configured_model: str | None
    unavailable_reason: str | None
    completed_turns: int
    temporary_messages: int
    persistent_history_enabled: bool
    automatic_memory_enabled: bool
    authority_mutations: AuthorityMutationCounts


@dataclass(frozen=True, slots=True)
class ConversationTurnResult:
    observation: LanguageObservation
    plan: ExpressionPlan
    expression: LanguageExpression
    authority_mutations: AuthorityMutationCounts


class ConversationPolicy:
    """Pure policy that keeps model interpretation explicitly provisional."""

    def plan(self, observation: LanguageObservation, *, locale: str) -> ExpressionPlan:
        if not isinstance(observation, LanguageObservation):
            raise ValidationError("conversation policy requires LanguageObservation")
        require_text(locale, "conversation locale")
        return ExpressionPlan(
            speech_act="conversation_reply",
            facts=(
                GroundedFact(
                    fact_id="candidate-status",
                    statement=(
                        "The current language interpretation is an unverified "
                        f"candidate with proposed intent {observation.intent!r}."
                    ),
                ),
                GroundedFact(
                    fact_id="authority-status",
                    statement=(
                        "This turn has not changed persistent memory, goals, "
                        "identity, motivation, RZS, sigma, world-model state, "
                        "or executed an action."
                    ),
                ),
            ),
            fallback_text="The conversational backend is unavailable.",
            style_hints=(
                f"reply naturally in {locale}",
                "do not narrate the protocol unless the user asks",
                "do not claim persistent memory or completed actions",
            ),
        )


def _bounded_context_message(role: str, text: str) -> str:
    prefix = f"{role}:\n"
    available = MAX_CONTEXT_MESSAGE_LENGTH - len(prefix)
    if len(text) <= available:
        return prefix + text
    marker = "\n[truncated from temporary context]"
    return prefix + text[: available - len(marker)] + marker


class ConversationRuntime:
    """Open-ended, non-persistent conversation behind the language gateway."""

    def __init__(
        self,
        *,
        settings: ConversationSettings,
        gateway: DarwinLanguageGateway,
        availability: ConversationAvailability,
        unavailable_reason: str | None,
        backend_controller: object | None,
        policy: ConversationPolicy | None = None,
    ) -> None:
        if not isinstance(settings, ConversationSettings):
            raise ValidationError("conversation settings are invalid")
        if availability is ConversationAvailability.AVAILABLE:
            if gateway.mode is not LanguageMode.MODEL or unavailable_reason is not None:
                raise ValidationError("available conversation runtime is inconsistent")
        elif availability in {
            ConversationAvailability.PURE,
            ConversationAvailability.UNAVAILABLE,
        }:
            if gateway.mode is not LanguageMode.PURE or unavailable_reason is None:
                raise ValidationError("inactive conversation runtime is inconsistent")
        else:
            raise ValidationError("new conversation runtime cannot start closed")
        self._settings = settings
        self._gateway = gateway
        self._availability = availability
        self._unavailable_reason = unavailable_reason
        self._backend_controller = backend_controller
        self._policy = policy or ConversationPolicy()
        self._messages: list[str] = []
        self._completed_turns = 0
        self._lock = RLock()

    @classmethod
    def create(
        cls,
        settings: ConversationSettings,
        *,
        openai_transport: JSONTransport | None = None,
        local_backend: ExplicitLocalBackend | None = None,
    ) -> "ConversationRuntime":
        if not isinstance(settings, ConversationSettings):
            raise ValidationError("conversation settings are invalid")

        if settings.backend is ConversationBackendKind.NONE:
            return cls(
                settings=settings,
                gateway=DarwinLanguageGateway(),
                availability=ConversationAvailability.PURE,
                unavailable_reason="backend_not_requested",
                backend_controller=None,
            )

        if settings.model is None:
            return cls(
                settings=settings,
                gateway=DarwinLanguageGateway(),
                availability=ConversationAvailability.UNAVAILABLE,
                unavailable_reason="model_not_configured",
                backend_controller=None,
            )

        if settings.backend is ConversationBackendKind.OPENAI:
            if settings.api_key is None:
                return cls(
                    settings=settings,
                    gateway=DarwinLanguageGateway(),
                    availability=ConversationAvailability.UNAVAILABLE,
                    unavailable_reason="openai_api_key_not_configured",
                    backend_controller=None,
                )
            backend = OpenAIResponsesBackend(
                model=settings.model,
                api_key=settings.api_key,
                request_timeout_seconds=settings.request_timeout_seconds,
                transport=openai_transport,
            )
            try:
                backend.probe_model()
            except Exception:
                backend.clear_ephemeral_context()
                return cls(
                    settings=settings,
                    gateway=DarwinLanguageGateway(),
                    availability=ConversationAvailability.UNAVAILABLE,
                    unavailable_reason="openai_model_probe_failed",
                    backend_controller=None,
                )
            return cls(
                settings=settings,
                gateway=DarwinLanguageGateway(backend),
                availability=ConversationAvailability.AVAILABLE,
                unavailable_reason=None,
                backend_controller=backend,
            )

        if local_backend is None:
            return cls(
                settings=settings,
                gateway=DarwinLanguageGateway(),
                availability=ConversationAvailability.UNAVAILABLE,
                unavailable_reason="explicit_local_backend_not_supplied",
                backend_controller=None,
            )
        if getattr(local_backend, "model", None) != settings.model:
            return cls(
                settings=settings,
                gateway=DarwinLanguageGateway(),
                availability=ConversationAvailability.UNAVAILABLE,
                unavailable_reason="local_model_mismatch",
                backend_controller=None,
            )
        if not callable(getattr(local_backend, "clear_ephemeral_context", None)):
            return cls(
                settings=settings,
                gateway=DarwinLanguageGateway(),
                availability=ConversationAvailability.UNAVAILABLE,
                unavailable_reason="local_backend_missing_ephemeral_clear",
                backend_controller=None,
            )
        return cls(
            settings=settings,
            gateway=DarwinLanguageGateway(local_backend),
            availability=ConversationAvailability.AVAILABLE,
            unavailable_reason=None,
            backend_controller=local_backend,
        )

    def snapshot(self) -> ConversationSnapshot:
        with self._lock:
            return ConversationSnapshot(
                requested_backend=self._settings.backend,
                availability=self._availability,
                language_mode=self._gateway.mode,
                language_source=self._gateway.source_name,
                configured_model=self._settings.model,
                unavailable_reason=self._unavailable_reason,
                completed_turns=self._completed_turns,
                temporary_messages=len(self._messages),
                persistent_history_enabled=False,
                automatic_memory_enabled=False,
                authority_mutations=AuthorityMutationCounts(),
            )

    def temporary_context(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._messages)

    def turn(self, text: str) -> ConversationTurnResult:
        require_text(text, "conversation text")
        with self._lock:
            if self._availability is ConversationAvailability.CLOSED:
                raise ConversationRuntimeError("conversation_runtime_closed")
            if self._availability is not ConversationAvailability.AVAILABLE:
                raise ConversationUnavailableError(
                    self._unavailable_reason or "conversation_backend_unavailable"
                )
            request = UnderstandingRequest(
                text=text,
                locale=self._settings.locale,
                recent_turns=tuple(self._messages),
            )
            try:
                observation = self._gateway.understand(request)
                plan = self._policy.plan(observation, locale=self._settings.locale)
                expression = self._gateway.express(plan)
            except BaseException:
                self._clear_pending_backend_context()
                raise

            new_messages = [
                _bounded_context_message("user", text),
                _bounded_context_message("darwin", expression.text),
            ]
            self._messages.extend(new_messages)
            if len(self._messages) > MAX_SESSION_MESSAGES:
                del self._messages[: len(self._messages) - MAX_SESSION_MESSAGES]
            self._completed_turns += 1
            return ConversationTurnResult(
                observation=observation,
                plan=plan,
                expression=expression,
                authority_mutations=AuthorityMutationCounts(),
            )

    def _clear_pending_backend_context(self) -> None:
        clear = getattr(self._backend_controller, "clear_ephemeral_context", None)
        if callable(clear):
            clear()

    def close(self) -> None:
        with self._lock:
            if self._availability is ConversationAvailability.CLOSED:
                return
            self._messages.clear()
            self._clear_pending_backend_context()
            self._availability = ConversationAvailability.CLOSED

    def __enter__(self) -> "ConversationRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
