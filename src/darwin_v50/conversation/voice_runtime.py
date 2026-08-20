"""Wake-gated voice control for the maintained conversational runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Protocol
import unicodedata

from ..models import DarwinV50Error, ValidationError, require_text
from .runtime import AuthorityMutationCounts, ConversationTurnResult


WAKE_WORDS = frozenset({"darwin", "darvim", "darvin", "dauin"})
_DIRECT_SLEEP_COMMANDS = frozenset(
    {
        "boa noite",
        "descansa",
        "descansar",
        "dorme",
        "dormir",
        "durma",
        "mimi",
        "mimir",
    }
)


class VoiceHostError(DarwinV50Error):
    """Base error for the maintained voice host."""


class VoiceHostState(StrEnum):
    SLEEPING = "sleeping"
    AWAKE = "awake"
    CLOSED = "closed"


class VoiceActionKind(StrEnum):
    IGNORED = "ignored"
    AWAKENED = "awakened"
    SLEPT = "slept"
    MODEL_REPLY = "model_reply"
    FAILED_CLOSED = "failed_closed"


class VoiceConversationRuntime(Protocol):
    def turn(self, text: str) -> ConversationTurnResult:
        """Run one isolated conversational turn."""

    def close(self) -> None:
        """Erase temporary context and close the runtime."""


@dataclass(frozen=True, slots=True)
class VoiceAction:
    kind: VoiceActionKind
    state: VoiceHostState
    captured_text: str
    model_input: str | None = None
    expression_text: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceHostSnapshot:
    state: VoiceHostState
    accepted_model_turns: int
    failed_model_turns: int
    persistent_transcript_enabled: bool
    scripted_reply_enabled: bool
    authority_mutations: AuthorityMutationCounts


def normalize_voice_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def contains_wake_word(text: str) -> bool:
    return bool(set(normalize_voice_text(text).split()) & WAKE_WORDS)


def command_after_wake_word(text: str) -> str:
    pieces = text.strip().split()
    for index, piece in enumerate(pieces):
        normalized = normalize_voice_text(piece)
        if normalized in WAKE_WORDS:
            return " ".join(pieces[index + 1 :]).strip()
    return text.strip()


def is_sleep_command(text: str) -> bool:
    normalized = normalize_voice_text(text)
    if normalized in _DIRECT_SLEEP_COMMANDS:
        return True
    if normalized.startswith(
        (
            "boa noite darwin",
            "esta na hora de dormir",
            "esta na hora de mimir",
            "hora de dormir",
            "hora de mimir",
            "ta na hora de dormir",
            "ta na hora de mimir",
        )
    ):
        return True
    words = normalized.split()
    return (
        len(words) <= 5
        and bool(set(words) & {"descansa", "dorme", "dormir", "durma", "mimir"})
        and bool(set(words) & {"agora", "pode", "vai", "voce"})
    )


class DarwinVoiceController:
    """Routes wake-gated speech to v50 without a scripted dialogue path."""

    def __init__(
        self,
        runtime: VoiceConversationRuntime,
        *,
        minimum_confidence: float = 0.25,
    ) -> None:
        if not callable(getattr(runtime, "turn", None)) or not callable(
            getattr(runtime, "close", None)
        ):
            raise ValidationError("voice host requires a conversation runtime")
        if isinstance(minimum_confidence, bool) or not isinstance(
            minimum_confidence,
            (int, float),
        ):
            raise ValidationError("voice confidence threshold must be numeric")
        threshold = float(minimum_confidence)
        if not 0.0 <= threshold <= 1.0:
            raise ValidationError("voice confidence threshold must be from 0 to 1")
        self._runtime = runtime
        self._minimum_confidence = threshold
        self._state = VoiceHostState.SLEEPING
        self._accepted_model_turns = 0
        self._failed_model_turns = 0

    @property
    def state(self) -> VoiceHostState:
        return self._state

    def snapshot(self) -> VoiceHostSnapshot:
        return VoiceHostSnapshot(
            state=self._state,
            accepted_model_turns=self._accepted_model_turns,
            failed_model_turns=self._failed_model_turns,
            persistent_transcript_enabled=False,
            scripted_reply_enabled=False,
            authority_mutations=AuthorityMutationCounts(),
        )

    def handle(self, text: str, *, confidence: float) -> VoiceAction:
        captured = require_text(text, "recognized speech")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValidationError("recognized speech confidence must be numeric")
        measured_confidence = float(confidence)
        if not 0.0 <= measured_confidence <= 1.0:
            raise ValidationError("recognized speech confidence must be from 0 to 1")
        if self._state is VoiceHostState.CLOSED:
            raise VoiceHostError("voice_host_closed")
        if measured_confidence < self._minimum_confidence:
            return VoiceAction(VoiceActionKind.IGNORED, self._state, captured)

        if self._state is VoiceHostState.SLEEPING:
            if not contains_wake_word(captured):
                return VoiceAction(VoiceActionKind.IGNORED, self._state, captured)
            command = command_after_wake_word(captured)
            if command and is_sleep_command(command):
                return VoiceAction(VoiceActionKind.IGNORED, self._state, captured)
            self._state = VoiceHostState.AWAKE
            if not command:
                return VoiceAction(VoiceActionKind.AWAKENED, self._state, captured)
            return self._model_turn(captured, command)

        if is_sleep_command(captured):
            self._state = VoiceHostState.SLEEPING
            return VoiceAction(VoiceActionKind.SLEPT, self._state, captured)

        model_input = (
            command_after_wake_word(captured)
            if contains_wake_word(captured)
            else captured
        )
        if not model_input:
            return VoiceAction(VoiceActionKind.AWAKENED, self._state, captured)
        return self._model_turn(captured, model_input)

    def _model_turn(self, captured: str, model_input: str) -> VoiceAction:
        try:
            result = self._runtime.turn(model_input)
            if result.authority_mutations != AuthorityMutationCounts():
                raise VoiceHostError("voice_turn_authority_mutation_detected")
            expression = require_text(
                result.expression.text,
                "voice model expression",
            )
        except Exception as exc:
            self._failed_model_turns += 1
            return VoiceAction(
                VoiceActionKind.FAILED_CLOSED,
                self._state,
                captured,
                model_input=model_input,
                error_code=f"voice_model_turn_failed:{type(exc).__name__}",
            )
        self._accepted_model_turns += 1
        return VoiceAction(
            VoiceActionKind.MODEL_REPLY,
            self._state,
            captured,
            model_input=model_input,
            expression_text=expression,
        )

    def sleep(self) -> VoiceAction:
        if self._state is VoiceHostState.CLOSED:
            raise VoiceHostError("voice_host_closed")
        self._state = VoiceHostState.SLEEPING
        return VoiceAction(VoiceActionKind.SLEPT, self._state, "")

    def close(self) -> None:
        if self._state is VoiceHostState.CLOSED:
            return
        self._runtime.close()
        self._state = VoiceHostState.CLOSED
