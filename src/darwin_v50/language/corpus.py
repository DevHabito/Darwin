"""Versioned labelled cases for Darwin language-boundary development."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..models import ValidationError, canonical_json, require_text
from .schema import ObservedEntity, ReportedSignal


LANGUAGE_CORPUS_V1_DEVELOPMENT = "darwin-language-corpus-v1-development"
LANGUAGE_CORPUS_V1_FAMILY_SIZE = 20


class LanguageCorpusFamily(StrEnum):
    SIMPLE_INTENT = "simple_intent"
    EXPERIENCE_PREFERENCE = "experience_preference"
    AMBIGUITY = "ambiguity"
    CONTRADICTION = "contradiction"
    BOUNDARY_ATTACK = "boundary_attack"


def _text(value: object, field: str, *, maximum: int = 20_000) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    normalized = require_text(value, field)
    if len(normalized) > maximum:
        raise ValidationError(f"{field} exceeds {maximum} characters")
    return normalized


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field, maximum=500)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ValidationError(f"{field} fields do not match the corpus v1 schema")


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list")
    return value


@dataclass(frozen=True, slots=True)
class ExpectedLanguageObservation:
    accepted_intents: tuple[str, ...]
    entities: tuple[ObservedEntity, ...]
    signals: tuple[ReportedSignal, ...]
    temporal_reference: str | None
    explicit_preference: str | None
    should_abstain: bool

    def __post_init__(self) -> None:
        if not isinstance(self.accepted_intents, tuple) or not self.accepted_intents:
            raise ValidationError("accepted_intents must be a non-empty tuple")
        normalized_intents = tuple(
            _text(intent, "accepted intent", maximum=80)
            for intent in self.accepted_intents
        )
        if len(set(normalized_intents)) != len(normalized_intents):
            raise ValidationError("accepted intents must be unique")
        if not isinstance(self.entities, tuple) or any(
            not isinstance(entity, ObservedEntity) for entity in self.entities
        ):
            raise ValidationError("expected entities are invalid")
        entity_pairs = [(entity.kind, entity.value) for entity in self.entities]
        if len(set(entity_pairs)) != len(entity_pairs):
            raise ValidationError("expected entities must be unique")
        if not isinstance(self.signals, tuple) or any(
            not isinstance(signal, ReportedSignal) for signal in self.signals
        ):
            raise ValidationError("expected signals are invalid")
        signal_names = [signal.name for signal in self.signals]
        if len(set(signal_names)) != len(signal_names):
            raise ValidationError("expected signal names must be unique")
        _optional_text(self.temporal_reference, "expected temporal reference")
        _optional_text(self.explicit_preference, "expected explicit preference")
        if not isinstance(self.should_abstain, bool):
            raise ValidationError("expected abstention flag must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "intents": list(self.accepted_intents),
            "entities": [
                [entity.kind, entity.value] for entity in self.entities
            ],
            "signals": [[signal.name, signal.value] for signal in self.signals],
            "temporal": self.temporal_reference,
            "preference": self.explicit_preference,
            "abstain": self.should_abstain,
        }


@dataclass(frozen=True, slots=True)
class LanguageCorpusCase:
    case_id: str
    version: str
    family: LanguageCorpusFamily
    locale: str
    text: str
    recent_turns: tuple[str, ...]
    expected: ExpectedLanguageObservation

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id", maximum=80)
        if self.version != LANGUAGE_CORPUS_V1_DEVELOPMENT:
            raise ValidationError("unsupported language corpus version")
        if not isinstance(self.family, LanguageCorpusFamily):
            raise ValidationError("language corpus family is invalid")
        _text(self.locale, "locale", maximum=32)
        _text(self.text, "text")
        if not isinstance(self.recent_turns, tuple) or len(self.recent_turns) > 64:
            raise ValidationError("recent_turns must be a bounded tuple")
        for turn in self.recent_turns:
            _text(turn, "recent turn", maximum=2_000)
        if not isinstance(self.expected, ExpectedLanguageObservation):
            raise ValidationError("expected observation is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "version": self.version,
            "family": self.family.value,
            "locale": self.locale,
            "text": self.text,
            "context": list(self.recent_turns),
            **self.expected.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class LanguageCorpus:
    version: str
    cases: tuple[LanguageCorpusCase, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.version != LANGUAGE_CORPUS_V1_DEVELOPMENT:
            raise ValidationError("unsupported language corpus version")
        if not isinstance(self.cases, tuple) or not self.cases:
            raise ValidationError("language corpus must contain cases")
        if any(case.version != self.version for case in self.cases):
            raise ValidationError("language corpus mixes versions")
        ids = [case.case_id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValidationError("language corpus case ids must be unique")
        request_keys = [
            (case.locale, case.text, case.recent_turns) for case in self.cases
        ]
        if len(set(request_keys)) != len(request_keys):
            raise ValidationError("language corpus requests must be unique")
        expected_digest = language_corpus_digest(self.cases)
        if self.digest != expected_digest:
            raise ValidationError("language corpus digest does not match its cases")

    @property
    def family_counts(self) -> dict[str, int]:
        counts = Counter(case.family.value for case in self.cases)
        return dict(sorted(counts.items()))


def language_corpus_digest(cases: Iterable[LanguageCorpusCase]) -> str:
    payload = [case.to_dict() for case in cases]
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _parse_pair_list(
    raw: object,
    field: str,
    *,
    numeric_second: bool,
) -> tuple[tuple[str, object], ...]:
    pairs: list[tuple[str, object]] = []
    for index, item in enumerate(_list(raw, field)):
        if not isinstance(item, list) or len(item) != 2:
            raise ValidationError(f"{field}[{index}] must be a two-item list")
        first = _text(item[0], f"{field}[{index}][0]", maximum=80)
        second = item[1]
        if numeric_second:
            if isinstance(second, bool) or not isinstance(second, (int, float)):
                raise ValidationError(f"{field}[{index}][1] must be numeric")
            second = float(second)
        else:
            second = _text(second, f"{field}[{index}][1]", maximum=500)
        pairs.append((first, second))
    return tuple(pairs)


def language_corpus_case_from_dict(raw: Mapping[str, Any]) -> LanguageCorpusCase:
    _exact_keys(
        raw,
        {
            "id",
            "version",
            "family",
            "locale",
            "text",
            "context",
            "intents",
            "entities",
            "signals",
            "temporal",
            "preference",
            "abstain",
        },
        "language corpus case",
    )
    try:
        family = LanguageCorpusFamily(str(raw["family"]))
    except ValueError as exc:
        raise ValidationError("unknown language corpus family") from exc
    intents = tuple(
        _text(item, "intent", maximum=80) for item in _list(raw["intents"], "intents")
    )
    entity_pairs = _parse_pair_list(
        raw["entities"],
        "entities",
        numeric_second=False,
    )
    signal_pairs = _parse_pair_list(
        raw["signals"],
        "signals",
        numeric_second=True,
    )
    context = tuple(
        _text(item, "context item", maximum=2_000)
        for item in _list(raw["context"], "context")
    )
    if not isinstance(raw["abstain"], bool):
        raise ValidationError("abstain must be boolean")
    return LanguageCorpusCase(
        case_id=_text(raw["id"], "id", maximum=80),
        version=_text(raw["version"], "version", maximum=80),
        family=family,
        locale=_text(raw["locale"], "locale", maximum=32),
        text=_text(raw["text"], "text"),
        recent_turns=context,
        expected=ExpectedLanguageObservation(
            accepted_intents=intents,
            entities=tuple(
                ObservedEntity(kind=kind, value=str(value))
                for kind, value in entity_pairs
            ),
            signals=tuple(
                ReportedSignal(name=name, value=float(value))
                for name, value in signal_pairs
            ),
            temporal_reference=_optional_text(raw["temporal"], "temporal"),
            explicit_preference=_optional_text(raw["preference"], "preference"),
            should_abstain=raw["abstain"],
        ),
    )


def load_language_corpus(path: str | Path) -> LanguageCorpus:
    source = Path(path)
    cases: list[LanguageCorpusCase] = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read language corpus: {source}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line, object_pairs_hook=_strict_object)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValidationError(
                f"invalid language corpus JSON on line {line_number}"
            ) from exc
        if not isinstance(raw, dict):
            raise ValidationError(
                f"language corpus line {line_number} must be an object"
            )
        try:
            cases.append(language_corpus_case_from_dict(raw))
        except ValidationError as exc:
            raise ValidationError(
                f"invalid language corpus case on line {line_number}: {exc}"
            ) from exc
    normalized = tuple(cases)
    return LanguageCorpus(
        version=LANGUAGE_CORPUS_V1_DEVELOPMENT,
        cases=normalized,
        digest=language_corpus_digest(normalized),
    )


def require_balanced_v1_development_corpus(corpus: LanguageCorpus) -> None:
    expected = {
        family.value: LANGUAGE_CORPUS_V1_FAMILY_SIZE
        for family in LanguageCorpusFamily
    }
    if corpus.family_counts != expected:
        raise ValidationError(
            "language corpus v1 must contain exactly 20 cases per family"
        )
