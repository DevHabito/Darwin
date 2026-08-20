"""Strict data contracts at Darwin's natural-language boundary.

Objects in this module are observations, requests, or renderings.  None of
them is a command to update memory, identity, goals, motivation, or RZS state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..models import ValidationError, require_text


MAX_TEXT_LENGTH = 20_000
MAX_SHORT_TEXT_LENGTH = 500
MAX_ITEMS = 64


class LanguageMode(StrEnum):
    """Whether Darwin is using only local fallbacks or an external model."""

    PURE = "pure"
    MODEL = "model"


class LanguageOperation(StrEnum):
    UNDERSTAND = "understand"
    EXPRESS = "express"
    CONSULT = "consult"


class KnowledgeStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    EXTERNAL_UNVERIFIED = "external_unverified"


def _bounded_text(value: str, field: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    normalized = require_text(value, field)
    if len(normalized) > limit:
        raise ValidationError(f"{field} exceeds {limit} characters")
    return normalized


def _optional_bounded_text(
    value: str | None,
    field: str,
    limit: int = MAX_SHORT_TEXT_LENGTH,
) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, field, limit)


def _probability(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a finite number from 0 to 1")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValidationError(f"{field} must be a finite number from 0 to 1")
    return result


def _bounded_tuple(value: tuple[Any, ...], field: str) -> None:
    if not isinstance(value, tuple):
        raise ValidationError(f"{field} must be an immutable tuple")
    if len(value) > MAX_ITEMS:
        raise ValidationError(f"{field} exceeds {MAX_ITEMS} items")


@dataclass(frozen=True, slots=True)
class UnderstandingRequest:
    """Explicit language-only context made available to a model backend."""

    text: str
    locale: str = "und"
    recent_turns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _bounded_text(self.text, "text")
        _bounded_text(self.locale, "locale", 32)
        _bounded_tuple(self.recent_turns, "recent_turns")
        for index, turn in enumerate(self.recent_turns):
            _bounded_text(turn, f"recent_turns[{index}]", 2_000)

    def to_payload(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "locale": self.locale,
            "recent_turns": list(self.recent_turns),
        }


@dataclass(frozen=True, slots=True)
class ObservedEntity:
    """A model-proposed entity, not an accepted world-model fact."""

    kind: str
    value: str

    def __post_init__(self) -> None:
        _bounded_text(self.kind, "entity kind", 80)
        _bounded_text(self.value, "entity value", MAX_SHORT_TEXT_LENGTH)


@dataclass(frozen=True, slots=True)
class ReportedSignal:
    """A normalized signal attributed to what the person reportedly said."""

    name: str
    value: float

    def __post_init__(self) -> None:
        _bounded_text(self.name, "reported signal name", 80)
        object.__setattr__(
            self,
            "value",
            _probability(self.value, "reported signal value"),
        )


@dataclass(frozen=True, slots=True)
class LanguageObservation:
    """Candidate interpretation that a core-owned evidence gate may evaluate."""

    raw_text: str
    intent: str
    entities: tuple[ObservedEntity, ...]
    reported_signals: tuple[ReportedSignal, ...]
    temporal_reference: str | None
    explicit_preference: str | None
    confidence: float
    source_name: str
    mode: LanguageMode

    def __post_init__(self) -> None:
        _bounded_text(self.raw_text, "raw_text")
        _bounded_text(self.intent, "intent", 80)
        _bounded_tuple(self.entities, "entities")
        if any(not isinstance(entity, ObservedEntity) for entity in self.entities):
            raise ValidationError("entities must contain ObservedEntity values")
        _bounded_tuple(self.reported_signals, "reported_signals")
        if any(
            not isinstance(signal, ReportedSignal)
            for signal in self.reported_signals
        ):
            raise ValidationError(
                "reported_signals must contain ReportedSignal values"
            )
        _optional_bounded_text(self.temporal_reference, "temporal_reference")
        _optional_bounded_text(self.explicit_preference, "explicit_preference")
        object.__setattr__(self, "confidence", _probability(self.confidence, "confidence"))
        _bounded_text(self.source_name, "source_name", 120)
        if not isinstance(self.mode, LanguageMode):
            raise ValidationError("language observation mode is invalid")


@dataclass(frozen=True, slots=True)
class GroundedFact:
    """One core-authored proposition that may be rendered into language."""

    fact_id: str
    statement: str
    required: bool = True

    def __post_init__(self) -> None:
        _bounded_text(self.fact_id, "fact_id", 80)
        _bounded_text(self.statement, "fact statement", 2_000)
        if not isinstance(self.required, bool):
            raise ValidationError("fact required flag must be boolean")


@dataclass(frozen=True, slots=True)
class ExpressionPlan:
    """Core-owned content plus a deterministic pure-mode rendering."""

    speech_act: str
    facts: tuple[GroundedFact, ...]
    fallback_text: str
    style_hints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _bounded_text(self.speech_act, "speech_act", 80)
        if not self.facts:
            raise ValidationError("expression plan requires at least one fact")
        _bounded_tuple(self.facts, "facts")
        if any(not isinstance(fact, GroundedFact) for fact in self.facts):
            raise ValidationError("facts must contain GroundedFact values")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise ValidationError("expression fact ids must be unique")
        _bounded_text(self.fallback_text, "fallback_text", 4_000)
        _bounded_tuple(self.style_hints, "style_hints")
        for index, hint in enumerate(self.style_hints):
            _bounded_text(hint, f"style_hints[{index}]", 120)

    @property
    def required_fact_ids(self) -> frozenset[str]:
        return frozenset(fact.fact_id for fact in self.facts if fact.required)

    @property
    def fact_ids(self) -> frozenset[str]:
        return frozenset(fact.fact_id for fact in self.facts)

    def to_payload(self) -> dict[str, Any]:
        return {
            "speech_act": self.speech_act,
            "facts": [
                {
                    "fact_id": fact.fact_id,
                    "statement": fact.statement,
                    "required": fact.required,
                }
                for fact in self.facts
            ],
            "style_hints": list(self.style_hints),
        }


@dataclass(frozen=True, slots=True)
class LanguageExpression:
    """A rendering of core facts; semantic fidelity is not machine-proven."""

    text: str
    acknowledged_fact_ids: tuple[str, ...]
    source_name: str
    mode: LanguageMode
    semantic_fidelity_verified: bool = False

    def __post_init__(self) -> None:
        _bounded_text(self.text, "expression text", 4_000)
        _bounded_tuple(self.acknowledged_fact_ids, "acknowledged_fact_ids")
        for index, fact_id in enumerate(self.acknowledged_fact_ids):
            _bounded_text(fact_id, f"acknowledged_fact_ids[{index}]", 80)
        if len(set(self.acknowledged_fact_ids)) != len(self.acknowledged_fact_ids):
            raise ValidationError("acknowledged fact ids must be unique")
        _bounded_text(self.source_name, "source_name", 120)
        if not isinstance(self.mode, LanguageMode):
            raise ValidationError("language expression mode is invalid")
        if not isinstance(self.semantic_fidelity_verified, bool):
            raise ValidationError("semantic fidelity flag must be boolean")
        if self.semantic_fidelity_verified:
            raise ValidationError(
                "the v1 language boundary cannot verify semantic fidelity"
            )


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    query: str
    locale: str = "und"

    def __post_init__(self) -> None:
        _bounded_text(self.query, "query", 4_000)
        _bounded_text(self.locale, "locale", 32)

    def to_payload(self) -> dict[str, Any]:
        return {"query": self.query, "locale": self.locale}


@dataclass(frozen=True, slots=True)
class KnowledgeCandidate:
    """External information with provenance, never a direct memory write."""

    available: bool
    content: str | None
    reported_confidence: float
    references: tuple[str, ...]
    source_name: str
    status: KnowledgeStatus

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise ValidationError("knowledge availability must be boolean")
        if self.available:
            _optional_bounded_text(self.content, "knowledge content", 8_000)
            if self.content is None:
                raise ValidationError("available knowledge requires content")
            if self.status is not KnowledgeStatus.EXTERNAL_UNVERIFIED:
                raise ValidationError("available knowledge must remain unverified")
        elif self.content is not None or self.status is not KnowledgeStatus.UNAVAILABLE:
            raise ValidationError("unavailable knowledge cannot contain content")
        object.__setattr__(
            self,
            "reported_confidence",
            _probability(self.reported_confidence, "reported_confidence"),
        )
        _bounded_tuple(self.references, "references")
        for index, reference in enumerate(self.references):
            _bounded_text(reference, f"references[{index}]", 1_000)
        _bounded_text(self.source_name, "source_name", 120)
        if not isinstance(self.status, KnowledgeStatus):
            raise ValidationError("knowledge status is invalid")
