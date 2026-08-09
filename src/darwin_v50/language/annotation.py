"""Blind human-annotation contracts for the Darwin language boundary.

This module prepares and checks annotation evidence.  It deliberately has no
model adapter, adjudication rule, or path that promotes annotations to gold
labels.  Human independence remains an external fact that code cannot prove.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from itertools import combinations
import hashlib
import json
from pathlib import Path
import random
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from ..models import ValidationError, canonical_json, require_text
from .corpus import LanguageCorpus, LanguageCorpusFamily
from .schema import ObservedEntity


LANGUAGE_CALIBRATION_CANDIDATES_V1 = (
    "darwin-language-calibration-candidates-v1"
)
LANGUAGE_ANNOTATION_V1 = "darwin-language-annotation-v1"
LANGUAGE_BLIND_PACKET_V1 = "darwin-language-blind-packet-v1"
LANGUAGE_CALIBRATION_FAMILY_SIZE = 30

LANGUAGE_INTENT_LABELS_V1 = frozenset(
    {
        "ambiguous_acceptance",
        "ambiguous_affect",
        "ambiguous_commitment",
        "ambiguous_intent",
        "ambiguous_preference",
        "ambiguous_reference",
        "assert_core_state_change",
        "continue_activity",
        "decline_activity",
        "express_indifference",
        "farewell",
        "greet",
        "request_activity",
        "request_alternative",
        "request_boundary_bypass",
        "request_conversation",
        "request_core_state_change",
        "request_explanation",
        "request_information",
        "request_item",
        "request_presence",
        "request_repetition",
        "request_silence",
        "revise_experience_report",
        "revise_preference_report",
        "revise_state_report",
        "share_experience",
        "share_state",
        "state_preference",
        "stop_activity",
        "uncertain_preference",
    }
)
LANGUAGE_ENTITY_KINDS_V1 = frozenset(
    {
        "activity",
        "artist",
        "claimed_authority",
        "content",
        "item",
        "option",
        "organization",
        "person",
        "place",
        "preference_scope",
        "proposed_fact",
        "requested_duration",
        "requested_format",
        "requested_operation",
        "requested_value",
        "target_state",
        "time_reference",
        "topic",
    }
)
LANGUAGE_SIGNAL_NAMES_V1 = frozenset(
    {
        "boredom",
        "current_willingness",
        "energy",
        "enjoyment",
        "fatigue",
        "frustration",
        "relief",
        "sadness",
    }
)


class SignalIntensity(IntEnum):
    NONE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3
    VERY_HIGH = 4

    @property
    def normalized_value(self) -> float:
        return float(self) / 4.0

    @classmethod
    def from_label(cls, value: object) -> SignalIntensity:
        if not isinstance(value, str):
            raise ValidationError("signal intensity must be a category")
        try:
            return {
                "none": cls.NONE,
                "low": cls.LOW,
                "moderate": cls.MODERATE,
                "high": cls.HIGH,
                "very_high": cls.VERY_HIGH,
            }[value]
        except KeyError as exc:
            raise ValidationError("unknown signal intensity category") from exc

    @property
    def label(self) -> str:
        return {
            self.NONE: "none",
            self.LOW: "low",
            self.MODERATE: "moderate",
            self.HIGH: "high",
            self.VERY_HIGH: "very_high",
        }[self]


class AnnotationStatus(StrEnum):
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"
    UNDERSPECIFIED = "underspecified"
    CONTEXT_DEPENDENT = "context_dependent"


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


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ValidationError(f"{field} fields do not match its v1 schema")


@dataclass(frozen=True, slots=True)
class AnnotationCandidate:
    case_id: str
    version: str
    family: LanguageCorpusFamily
    locale: str
    text: str
    recent_turns: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id", maximum=80)
        if self.version != LANGUAGE_CALIBRATION_CANDIDATES_V1:
            raise ValidationError("unsupported annotation candidate version")
        if not isinstance(self.family, LanguageCorpusFamily):
            raise ValidationError("annotation candidate family is invalid")
        _text(self.locale, "locale", maximum=32)
        _text(self.text, "text")
        if not isinstance(self.recent_turns, tuple) or len(self.recent_turns) > 64:
            raise ValidationError("recent_turns must be a bounded tuple")
        for turn in self.recent_turns:
            _text(turn, "recent turn", maximum=2_000)

    def to_source_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "version": self.version,
            "family": self.family.value,
            "locale": self.locale,
            "text": self.text,
            "context": list(self.recent_turns),
        }

    def to_blind_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "locale": self.locale,
            "text": self.text,
            "context": list(self.recent_turns),
        }


@dataclass(frozen=True, slots=True)
class AnnotationCandidateSet:
    version: str
    cases: tuple[AnnotationCandidate, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.version != LANGUAGE_CALIBRATION_CANDIDATES_V1:
            raise ValidationError("unsupported annotation candidate-set version")
        if not isinstance(self.cases, tuple) or not self.cases:
            raise ValidationError("annotation candidate set must contain cases")
        if any(case.version != self.version for case in self.cases):
            raise ValidationError("annotation candidate set mixes versions")
        ids = [case.case_id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValidationError("annotation candidate ids must be unique")
        request_keys = [
            (case.locale, case.text, case.recent_turns) for case in self.cases
        ]
        if len(set(request_keys)) != len(request_keys):
            raise ValidationError("annotation candidate requests must be unique")
        if self.digest != annotation_candidate_digest(self.cases):
            raise ValidationError("annotation candidate digest is invalid")

    @property
    def family_counts(self) -> dict[str, int]:
        counts = Counter(case.family.value for case in self.cases)
        return dict(sorted(counts.items()))


def annotation_candidate_digest(cases: Iterable[AnnotationCandidate]) -> str:
    payload = [case.to_source_dict() for case in cases]
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def annotation_candidate_from_dict(raw: Mapping[str, Any]) -> AnnotationCandidate:
    _exact_keys(
        raw,
        {"id", "version", "family", "locale", "text", "context"},
        "annotation candidate",
    )
    try:
        family = LanguageCorpusFamily(str(raw["family"]))
    except ValueError as exc:
        raise ValidationError("unknown annotation candidate family") from exc
    context = tuple(
        _text(item, "context item", maximum=2_000)
        for item in _list(raw["context"], "context")
    )
    return AnnotationCandidate(
        case_id=_text(raw["id"], "id", maximum=80),
        version=_text(raw["version"], "version", maximum=80),
        family=family,
        locale=_text(raw["locale"], "locale", maximum=32),
        text=_text(raw["text"], "text"),
        recent_turns=context,
    )


def load_annotation_candidates(path: str | Path) -> AnnotationCandidateSet:
    source = Path(path)
    cases: list[AnnotationCandidate] = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read annotation candidates: {source}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line, object_pairs_hook=_strict_object)
            if not isinstance(raw, dict):
                raise ValidationError("candidate line must be an object")
            cases.append(annotation_candidate_from_dict(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValidationError(
                f"invalid annotation candidate on line {line_number}: {exc}"
            ) from exc
    normalized = tuple(cases)
    return AnnotationCandidateSet(
        version=LANGUAGE_CALIBRATION_CANDIDATES_V1,
        cases=normalized,
        digest=annotation_candidate_digest(normalized),
    )


def require_balanced_calibration_candidates(
    candidates: AnnotationCandidateSet,
) -> None:
    expected = {
        family.value: LANGUAGE_CALIBRATION_FAMILY_SIZE
        for family in LanguageCorpusFamily
    }
    if candidates.family_counts != expected:
        raise ValidationError(
            "calibration candidates v1 must contain exactly 30 cases per family"
        )


def require_disjoint_from_development(
    candidates: AnnotationCandidateSet,
    development: LanguageCorpus,
) -> None:
    development_requests = {
        (case.locale, case.text, case.recent_turns) for case in development.cases
    }
    overlap = [
        case.case_id
        for case in candidates.cases
        if (case.locale, case.text, case.recent_turns) in development_requests
    ]
    if overlap:
        raise ValidationError(
            "calibration candidates overlap development requests: "
            + ", ".join(overlap)
        )


@dataclass(frozen=True, slots=True)
class BlindAnnotationPacket:
    packet_id: str
    candidate_digest: str
    cases: tuple[AnnotationCandidate, ...]

    def __post_init__(self) -> None:
        _text(self.packet_id, "packet_id", maximum=80)
        _text(self.candidate_digest, "candidate_digest", maximum=64)
        if not isinstance(self.cases, tuple) or not self.cases:
            raise ValidationError("blind annotation packet must contain cases")

    def jsonl(self) -> str:
        rows = []
        for case in self.cases:
            rows.append(
                canonical_json(
                    {
                        "schema": LANGUAGE_BLIND_PACKET_V1,
                        "packet_id": self.packet_id,
                        "candidate_digest": self.candidate_digest,
                        **case.to_blind_dict(),
                    }
                )
            )
        return "\n".join(rows) + "\n"


def build_blind_annotation_packet(
    candidates: AnnotationCandidateSet,
    *,
    packet_id: str,
    seed: int,
) -> BlindAnnotationPacket:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValidationError("packet seed must be an integer")
    ordered = list(candidates.cases)
    random.Random(seed).shuffle(ordered)
    return BlindAnnotationPacket(
        packet_id=packet_id,
        candidate_digest=candidates.digest,
        cases=tuple(ordered),
    )


@dataclass(frozen=True, slots=True)
class AnnotatedSignal:
    name: str
    intensity: SignalIntensity

    def __post_init__(self) -> None:
        _text(self.name, "signal name", maximum=80)
        if not isinstance(self.intensity, SignalIntensity):
            raise ValidationError("signal intensity is invalid")

    def to_list(self) -> list[str]:
        return [self.name, self.intensity.label]


@dataclass(frozen=True, slots=True)
class LanguageAnnotation:
    candidate_digest: str
    case_id: str
    annotator_id: str
    intent_labels: tuple[str, ...]
    entities: tuple[ObservedEntity, ...]
    signals: tuple[AnnotatedSignal, ...]
    temporal_reference: str | None
    explicit_preference: str | None
    should_abstain: bool
    annotation_status: AnnotationStatus

    def __post_init__(self) -> None:
        _text(self.candidate_digest, "candidate_digest", maximum=64)
        _text(self.case_id, "case_id", maximum=80)
        _text(self.annotator_id, "annotator_id", maximum=80)
        if not isinstance(self.intent_labels, tuple) or not self.intent_labels:
            raise ValidationError("intent_labels must be a non-empty tuple")
        if len(self.intent_labels) > 3:
            raise ValidationError("intent_labels cannot contain more than three labels")
        intents = tuple(
            _text(intent, "intent label", maximum=80)
            for intent in self.intent_labels
        )
        if len(set(intents)) != len(intents):
            raise ValidationError("intent labels must be unique")
        unknown_intents = set(intents) - LANGUAGE_INTENT_LABELS_V1
        if unknown_intents:
            raise ValidationError("annotation contains an unknown intent label")
        if not isinstance(self.entities, tuple) or any(
            not isinstance(entity, ObservedEntity) for entity in self.entities
        ):
            raise ValidationError("annotation entities are invalid")
        entity_pairs = [(entity.kind, entity.value) for entity in self.entities]
        if len(set(entity_pairs)) != len(entity_pairs):
            raise ValidationError("annotation entities must be unique")
        if any(entity.kind not in LANGUAGE_ENTITY_KINDS_V1 for entity in self.entities):
            raise ValidationError("annotation contains an unknown entity kind")
        if not isinstance(self.signals, tuple) or any(
            not isinstance(signal, AnnotatedSignal) for signal in self.signals
        ):
            raise ValidationError("annotation signals are invalid")
        signal_names = [signal.name for signal in self.signals]
        if len(set(signal_names)) != len(signal_names):
            raise ValidationError("annotation signal names must be unique")
        if set(signal_names) != LANGUAGE_SIGNAL_NAMES_V1:
            raise ValidationError(
                "annotation must classify every signal in the v1 inventory"
            )
        _optional_text(self.temporal_reference, "temporal reference")
        _optional_text(self.explicit_preference, "explicit preference")
        if not isinstance(self.should_abstain, bool):
            raise ValidationError("annotation abstention flag must be boolean")
        if not isinstance(self.annotation_status, AnnotationStatus):
            raise ValidationError("annotation status is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LANGUAGE_ANNOTATION_V1,
            "candidate_digest": self.candidate_digest,
            "case_id": self.case_id,
            "annotator_id": self.annotator_id,
            "intents": list(self.intent_labels),
            "entities": [[entity.kind, entity.value] for entity in self.entities],
            "signals": [signal.to_list() for signal in self.signals],
            "temporal": self.temporal_reference,
            "preference": self.explicit_preference,
            "abstain": self.should_abstain,
            "status": self.annotation_status.value,
        }


def _pair_list(value: object, field: str) -> list[tuple[object, object]]:
    result: list[tuple[object, object]] = []
    for index, item in enumerate(_list(value, field)):
        if not isinstance(item, list) or len(item) != 2:
            raise ValidationError(f"{field}[{index}] must be a two-item list")
        result.append((item[0], item[1]))
    return result


def language_annotation_from_dict(raw: Mapping[str, Any]) -> LanguageAnnotation:
    _exact_keys(
        raw,
        {
            "schema",
            "candidate_digest",
            "case_id",
            "annotator_id",
            "intents",
            "entities",
            "signals",
            "temporal",
            "preference",
            "abstain",
            "status",
        },
        "language annotation",
    )
    if raw["schema"] != LANGUAGE_ANNOTATION_V1:
        raise ValidationError("unsupported language annotation schema")
    if not isinstance(raw["abstain"], bool):
        raise ValidationError("abstain must be boolean")
    try:
        status = AnnotationStatus(str(raw["status"]))
    except ValueError as exc:
        raise ValidationError("unknown annotation status") from exc
    return LanguageAnnotation(
        candidate_digest=_text(
            raw["candidate_digest"], "candidate_digest", maximum=64
        ),
        case_id=_text(raw["case_id"], "case_id", maximum=80),
        annotator_id=_text(raw["annotator_id"], "annotator_id", maximum=80),
        intent_labels=tuple(
            _text(item, "intent", maximum=80)
            for item in _list(raw["intents"], "intents")
        ),
        entities=tuple(
            ObservedEntity(
                kind=_text(kind, "entity kind", maximum=80),
                value=_text(value, "entity value", maximum=500),
            )
            for kind, value in _pair_list(raw["entities"], "entities")
        ),
        signals=tuple(
            AnnotatedSignal(
                name=_text(name, "signal name", maximum=80),
                intensity=SignalIntensity.from_label(level),
            )
            for name, level in _pair_list(raw["signals"], "signals")
        ),
        temporal_reference=_optional_text(raw["temporal"], "temporal"),
        explicit_preference=_optional_text(raw["preference"], "preference"),
        should_abstain=raw["abstain"],
        annotation_status=status,
    )


def load_language_annotations(path: str | Path) -> tuple[LanguageAnnotation, ...]:
    source = Path(path)
    records: list[LanguageAnnotation] = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read language annotations: {source}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line, object_pairs_hook=_strict_object)
            if not isinstance(raw, dict):
                raise ValidationError("annotation line must be an object")
            records.append(language_annotation_from_dict(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValidationError(
                f"invalid language annotation on line {line_number}: {exc}"
            ) from exc
    return tuple(records)


@dataclass(frozen=True, slots=True)
class AnnotationPanel:
    candidate_digest: str
    case_ids: tuple[str, ...]
    annotator_ids: tuple[str, ...]
    records: tuple[LanguageAnnotation, ...]


def validate_annotation_panel(
    candidates: AnnotationCandidateSet,
    records: Sequence[LanguageAnnotation],
    *,
    minimum_annotators: int = 2,
) -> AnnotationPanel:
    if isinstance(minimum_annotators, bool) or minimum_annotators < 2:
        raise ValidationError("minimum_annotators must be at least two")
    if not records:
        raise ValidationError("annotation panel is empty")
    candidate_ids = {case.case_id for case in candidates.cases}
    keys = [(record.annotator_id, record.case_id) for record in records]
    if len(set(keys)) != len(keys):
        raise ValidationError("annotation panel contains duplicate annotator/case rows")
    if any(record.candidate_digest != candidates.digest for record in records):
        raise ValidationError("annotation panel candidate digest does not match")
    if any(record.case_id not in candidate_ids for record in records):
        raise ValidationError("annotation panel contains an unknown case")
    annotators = tuple(sorted({record.annotator_id for record in records}))
    if len(annotators) < minimum_annotators:
        raise ValidationError(
            f"annotation panel requires at least {minimum_annotators} annotators"
        )
    for annotator in annotators:
        annotated = {
            record.case_id for record in records if record.annotator_id == annotator
        }
        if annotated != candidate_ids:
            raise ValidationError(
                f"annotator {annotator} does not cover the exact candidate set"
            )
    return AnnotationPanel(
        candidate_digest=candidates.digest,
        case_ids=tuple(sorted(candidate_ids)),
        annotator_ids=annotators,
        records=tuple(records),
    )


def _mean_jaccard(left: Sequence[set[Any]], right: Sequence[set[Any]]) -> float:
    scores = []
    for left_set, right_set in zip(left, right, strict=True):
        union = left_set | right_set
        scores.append(1.0 if not union else len(left_set & right_set) / len(union))
    return fmean(scores)


def _nonnull_union_mean_jaccard(
    left: Sequence[set[Any]], right: Sequence[set[Any]]
) -> float | None:
    scores = [
        len(left_set & right_set) / len(left_set | right_set)
        for left_set, right_set in zip(left, right, strict=True)
        if left_set or right_set
    ]
    return fmean(scores) if scores else None


def _exact_agreement(left: Sequence[Any], right: Sequence[Any]) -> float:
    return sum(a == b for a, b in zip(left, right, strict=True)) / len(left)


def _nonnull_union_exact_agreement(
    left: Sequence[Any], right: Sequence[Any]
) -> float | None:
    pairs = [
        (a, b)
        for a, b in zip(left, right, strict=True)
        if a is not None or b is not None
    ]
    if not pairs:
        return None
    return sum(a == b for a, b in pairs) / len(pairs)


def _cohen_kappa(left: Sequence[Any], right: Sequence[Any]) -> float | None:
    if len(left) != len(right) or not left:
        raise ValidationError("kappa inputs must be non-empty and equal length")
    observed = _exact_agreement(left, right)
    left_counts = Counter(left)
    right_counts = Counter(right)
    size = len(left)
    expected = sum(
        (left_counts[label] / size) * (right_counts[label] / size)
        for label in set(left_counts) | set(right_counts)
    )
    if expected == 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def _macro_multilabel_kappa(
    left: Sequence[set[str]], right: Sequence[set[str]]
) -> float | None:
    labels = sorted(set().union(*left, *right))
    kappas = []
    for label in labels:
        value = _cohen_kappa(
            [label in values for values in left],
            [label in values for values in right],
        )
        if value is not None:
            kappas.append(value)
    return fmean(kappas) if kappas else None


def _weighted_signal_kappa(
    left: Sequence[dict[str, SignalIntensity]],
    right: Sequence[dict[str, SignalIntensity]],
) -> float | None:
    pairs: list[tuple[int, int]] = []
    for left_signals, right_signals in zip(left, right, strict=True):
        for name in sorted(set(left_signals) | set(right_signals)):
            pairs.append(
                (
                    int(left_signals.get(name, SignalIntensity.NONE)),
                    int(right_signals.get(name, SignalIntensity.NONE)),
                )
            )
    if not pairs:
        return None
    observed = fmean(((a - b) / 4.0) ** 2 for a, b in pairs)
    left_counts = Counter(a for a, _ in pairs)
    right_counts = Counter(b for _, b in pairs)
    size = len(pairs)
    expected = sum(
        (left_counts[a] / size)
        * (right_counts[b] / size)
        * (((a - b) / 4.0) ** 2)
        for a in range(5)
        for b in range(5)
    )
    if expected == 0.0:
        return None
    return 1.0 - observed / expected


@dataclass(frozen=True, slots=True)
class PairwiseAgreement:
    annotators: tuple[str, str]
    metrics: Mapping[str, float | None]
    disagreement_case_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "annotators": list(self.annotators),
            "metrics": dict(sorted(self.metrics.items())),
            "disagreement_case_ids": list(self.disagreement_case_ids),
        }


@dataclass(frozen=True, slots=True)
class AnnotationAgreementReport:
    candidate_digest: str
    cases: int
    annotators: tuple[str, ...]
    pairwise: tuple[PairwiseAgreement, ...]
    aggregate_pairwise_means: Mapping[str, float | None]
    disagreement_case_ids: tuple[str, ...]
    declares_pass: bool = False
    calibration_corpus_promoted: bool = False

    def __post_init__(self) -> None:
        if self.declares_pass or self.calibration_corpus_promoted:
            raise ValidationError("agreement reporting cannot promote a corpus")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_digest": self.candidate_digest,
            "cases": self.cases,
            "annotators": list(self.annotators),
            "pairwise": [comparison.to_dict() for comparison in self.pairwise],
            "aggregate_pairwise_means": dict(
                sorted(self.aggregate_pairwise_means.items())
            ),
            "disagreement_case_ids": list(self.disagreement_case_ids),
            "declares_pass": self.declares_pass,
            "calibration_corpus_promoted": self.calibration_corpus_promoted,
        }


def _annotation_projection(annotation: LanguageAnnotation) -> tuple[Any, ...]:
    return (
        frozenset(annotation.intent_labels),
        frozenset((entity.kind, entity.value) for entity in annotation.entities),
        frozenset((signal.name, signal.intensity) for signal in annotation.signals),
        annotation.temporal_reference,
        annotation.explicit_preference,
        annotation.should_abstain,
        annotation.annotation_status,
    )


def _pairwise_agreement(
    case_ids: Sequence[str],
    left_id: str,
    right_id: str,
    records: Mapping[tuple[str, str], LanguageAnnotation],
) -> PairwiseAgreement:
    left = [records[(left_id, case_id)] for case_id in case_ids]
    right = [records[(right_id, case_id)] for case_id in case_ids]
    left_intents = [set(record.intent_labels) for record in left]
    right_intents = [set(record.intent_labels) for record in right]
    left_entities = [
        {(entity.kind, entity.value) for entity in record.entities} for record in left
    ]
    right_entities = [
        {(entity.kind, entity.value) for entity in record.entities} for record in right
    ]
    left_signals = [
        {signal.name: signal.intensity for signal in record.signals} for record in left
    ]
    right_signals = [
        {signal.name: signal.intensity for signal in record.signals} for record in right
    ]
    left_active_signals = [
        {
            name
            for name, intensity in values.items()
            if intensity is not SignalIntensity.NONE
        }
        for values in left_signals
    ]
    right_active_signals = [
        {
            name
            for name, intensity in values.items()
            if intensity is not SignalIntensity.NONE
        }
        for values in right_signals
    ]
    left_temporal = [record.temporal_reference for record in left]
    right_temporal = [record.temporal_reference for record in right]
    left_preference = [record.explicit_preference for record in left]
    right_preference = [record.explicit_preference for record in right]
    metrics: dict[str, float | None] = {
        "intent_exact_agreement": _exact_agreement(left_intents, right_intents),
        "intent_mean_jaccard": _mean_jaccard(left_intents, right_intents),
        "intent_macro_binary_cohen_kappa": _macro_multilabel_kappa(
            left_intents, right_intents
        ),
        "entity_exact_agreement": _exact_agreement(left_entities, right_entities),
        "entity_mean_jaccard": _mean_jaccard(left_entities, right_entities),
        "entity_nonempty_union_mean_jaccard": _nonnull_union_mean_jaccard(
            left_entities, right_entities
        ),
        "active_signal_mean_jaccard": _mean_jaccard(
            left_active_signals, right_active_signals
        ),
        "active_signal_nonempty_union_mean_jaccard": _nonnull_union_mean_jaccard(
            left_active_signals, right_active_signals
        ),
        "active_signal_macro_binary_cohen_kappa": _macro_multilabel_kappa(
            left_active_signals, right_active_signals
        ),
        "signal_intensity_quadratic_weighted_kappa": _weighted_signal_kappa(
            left_signals, right_signals
        ),
        "temporal_exact_agreement": _exact_agreement(
            left_temporal,
            right_temporal,
        ),
        "temporal_nonnull_union_exact_agreement": _nonnull_union_exact_agreement(
            left_temporal,
            right_temporal,
        ),
        "preference_exact_agreement": _exact_agreement(
            left_preference,
            right_preference,
        ),
        "preference_nonnull_union_exact_agreement": _nonnull_union_exact_agreement(
            left_preference,
            right_preference,
        ),
        "abstention_exact_agreement": _exact_agreement(
            [record.should_abstain for record in left],
            [record.should_abstain for record in right],
        ),
        "abstention_cohen_kappa": _cohen_kappa(
            [record.should_abstain for record in left],
            [record.should_abstain for record in right],
        ),
        "status_exact_agreement": _exact_agreement(
            [record.annotation_status for record in left],
            [record.annotation_status for record in right],
        ),
        "status_cohen_kappa": _cohen_kappa(
            [record.annotation_status for record in left],
            [record.annotation_status for record in right],
        ),
    }
    disagreements = tuple(
        case_id
        for case_id, left_record, right_record in zip(
            case_ids, left, right, strict=True
        )
        if _annotation_projection(left_record) != _annotation_projection(right_record)
    )
    return PairwiseAgreement(
        annotators=(left_id, right_id),
        metrics=metrics,
        disagreement_case_ids=disagreements,
    )


def measure_annotation_agreement(
    panel: AnnotationPanel,
) -> AnnotationAgreementReport:
    indexed = {
        (record.annotator_id, record.case_id): record for record in panel.records
    }
    pairwise = tuple(
        _pairwise_agreement(panel.case_ids, left, right, indexed)
        for left, right in combinations(panel.annotator_ids, 2)
    )
    metric_names = sorted(pairwise[0].metrics)
    aggregates: dict[str, float | None] = {}
    for name in metric_names:
        values = [comparison.metrics[name] for comparison in pairwise]
        numeric = [value for value in values if value is not None]
        aggregates[name] = fmean(numeric) if numeric else None
    disagreements = tuple(
        sorted(
            {
                case_id
                for comparison in pairwise
                for case_id in comparison.disagreement_case_ids
            }
        )
    )
    return AnnotationAgreementReport(
        candidate_digest=panel.candidate_digest,
        cases=len(panel.case_ids),
        annotators=panel.annotator_ids,
        pairwise=pairwise,
        aggregate_pairwise_means=aggregates,
        disagreement_case_ids=disagreements,
    )
