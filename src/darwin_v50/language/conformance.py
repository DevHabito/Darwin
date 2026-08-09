"""Development-only metrics for language-observation backends."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..models import ValidationError, canonical_json
from .corpus import (
    LanguageCorpus,
    LanguageCorpusCase,
    LanguageCorpusFamily,
    load_language_corpus,
    require_balanced_v1_development_corpus,
)
from .gateway import (
    DarwinLanguageGateway,
    LanguageAuthorityError,
    LanguageBoundaryError,
)
from .schema import LanguageObservation, UnderstandingRequest


DEFAULT_ABSTENTION_THRESHOLD = 0.5
DEFAULT_SIGNAL_TOLERANCE = 0.15
DEFAULT_CALIBRATION_BINS = 10


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().casefold().split())


def _ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0


@dataclass(frozen=True, slots=True)
class LanguageCaseResult:
    case_id: str
    family: LanguageCorpusFamily
    contract_accepted: bool
    authority_violation: bool
    backend_error: bool
    intent_correct: bool
    entity_true_positive: int
    entity_false_positive: int
    entity_false_negative: int
    signal_true_positive: int
    signal_false_positive: int
    signal_false_negative: int
    signal_absolute_errors: tuple[float, ...]
    temporal_predicted: bool
    temporal_correct: bool
    preference_predicted: bool
    preference_correct: bool
    abstention_correct: bool
    structure_correct: bool
    confidence: float | None


@dataclass(frozen=True, slots=True)
class LanguageFamilyMetrics:
    family: LanguageCorpusFamily
    cases: int
    contract_success_rate: float
    intent_accuracy: float
    exact_structure_accuracy: float
    abstention_accuracy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "cases": self.cases,
            "contract_success_rate": self.contract_success_rate,
            "intent_accuracy": self.intent_accuracy,
            "exact_structure_accuracy": self.exact_structure_accuracy,
            "abstention_accuracy": self.abstention_accuracy,
        }


@dataclass(frozen=True, slots=True)
class LanguageConformanceReport:
    corpus_version: str
    corpus_digest: str
    source_name: str
    mode: str
    cases: int
    accepted_cases: int
    authority_violations: int
    authority_violation_rate: float
    backend_errors: int
    backend_error_rate: float
    contract_success_rate: float
    intent_accuracy: float
    entity_precision: float
    entity_recall: float
    entity_f1: float
    signal_precision: float
    signal_recall: float
    signal_f1: float
    signal_intensity_mae: float | None
    temporal_accuracy: float
    temporal_required_cases: int
    temporal_recall: float
    temporal_false_positive_rate: float
    preference_accuracy: float
    preference_required_cases: int
    preference_recall: float
    preference_false_positive_rate: float
    abstention_accuracy: float
    exact_structure_accuracy: float
    confidence_brier: float | None
    confidence_ece: float | None
    boundary_contract_success_rate: float
    boundary_authority_violation_rate: float
    family_metrics: tuple[LanguageFamilyMetrics, ...]
    semantic_fidelity_tested: bool = False
    core_state_equivalence_tested: bool = False
    evidence_level: str = "development-only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_version": self.corpus_version,
            "corpus_digest": self.corpus_digest,
            "source_name": self.source_name,
            "mode": self.mode,
            "cases": self.cases,
            "accepted_cases": self.accepted_cases,
            "authority_violations": self.authority_violations,
            "authority_violation_rate": self.authority_violation_rate,
            "backend_errors": self.backend_errors,
            "backend_error_rate": self.backend_error_rate,
            "contract_success_rate": self.contract_success_rate,
            "intent_accuracy": self.intent_accuracy,
            "entity_precision": self.entity_precision,
            "entity_recall": self.entity_recall,
            "entity_f1": self.entity_f1,
            "signal_precision": self.signal_precision,
            "signal_recall": self.signal_recall,
            "signal_f1": self.signal_f1,
            "signal_intensity_mae": self.signal_intensity_mae,
            "temporal_accuracy": self.temporal_accuracy,
            "temporal_required_cases": self.temporal_required_cases,
            "temporal_recall": self.temporal_recall,
            "temporal_false_positive_rate": self.temporal_false_positive_rate,
            "preference_accuracy": self.preference_accuracy,
            "preference_required_cases": self.preference_required_cases,
            "preference_recall": self.preference_recall,
            "preference_false_positive_rate": self.preference_false_positive_rate,
            "abstention_accuracy": self.abstention_accuracy,
            "exact_structure_accuracy": self.exact_structure_accuracy,
            "confidence_brier": self.confidence_brier,
            "confidence_ece": self.confidence_ece,
            "boundary_contract_success_rate": self.boundary_contract_success_rate,
            "boundary_authority_violation_rate": (
                self.boundary_authority_violation_rate
            ),
            "family_metrics": [metric.to_dict() for metric in self.family_metrics],
            "semantic_fidelity_tested": self.semantic_fidelity_tested,
            "core_state_equivalence_tested": self.core_state_equivalence_tested,
            "evidence_level": self.evidence_level,
        }


@dataclass(frozen=True, slots=True)
class MetricDelta:
    metric: str
    baseline: float | None
    candidate: float | None
    delta: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "delta": self.delta,
        }


@dataclass(frozen=True, slots=True)
class LanguageConformanceComparison:
    corpus_version: str
    corpus_digest: str
    baseline_source: str
    candidate_source: str
    metrics: tuple[MetricDelta, ...]
    safety_regressed: bool
    declares_winner: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_version": self.corpus_version,
            "corpus_digest": self.corpus_digest,
            "baseline_source": self.baseline_source,
            "candidate_source": self.candidate_source,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "safety_regressed": self.safety_regressed,
            "declares_winner": self.declares_winner,
        }


def _entity_counter(observation: LanguageObservation) -> Counter[tuple[str, str]]:
    return Counter(
        (_normalized(entity.kind) or "", _normalized(entity.value) or "")
        for entity in observation.entities
    )


def _expected_entity_counter(case: LanguageCorpusCase) -> Counter[tuple[str, str]]:
    return Counter(
        (_normalized(entity.kind) or "", _normalized(entity.value) or "")
        for entity in case.expected.entities
    )


def _signal_evaluation(
    case: LanguageCorpusCase,
    observation: LanguageObservation,
    *,
    tolerance: float,
) -> tuple[int, int, int, tuple[float, ...], bool]:
    expected = {
        _normalized(signal.name) or "": signal.value
        for signal in case.expected.signals
    }
    predicted_values: dict[str, list[float]] = {}
    for signal in observation.reported_signals:
        predicted_values.setdefault(_normalized(signal.name) or "", []).append(
            signal.value
        )
    predicted_counter = Counter(
        {
            name: len(values) for name, values in predicted_values.items()
        }
    )
    expected_counter = Counter(expected.keys())
    true_positive = sum((predicted_counter & expected_counter).values())
    false_positive = sum((predicted_counter - expected_counter).values())
    false_negative = sum((expected_counter - predicted_counter).values())
    errors = tuple(
        abs(predicted_values[name][0] - expected[name])
        for name in sorted(expected.keys() & predicted_values.keys())
    )
    exact = (
        predicted_counter == expected_counter
        and all(error <= tolerance for error in errors)
    )
    return true_positive, false_positive, false_negative, errors, exact


def evaluate_language_case(
    gateway: DarwinLanguageGateway,
    case: LanguageCorpusCase,
    *,
    abstention_threshold: float = DEFAULT_ABSTENTION_THRESHOLD,
    signal_tolerance: float = DEFAULT_SIGNAL_TOLERANCE,
) -> LanguageCaseResult:
    if not 0.0 < abstention_threshold < 1.0:
        raise ValidationError("abstention threshold must be between 0 and 1")
    if not 0.0 <= signal_tolerance <= 1.0:
        raise ValidationError("signal tolerance must be between 0 and 1")
    try:
        observation = gateway.understand(
            UnderstandingRequest(
                text=case.text,
                locale=case.locale,
                recent_turns=case.recent_turns,
            )
        )
    except LanguageAuthorityError:
        return _failed_case_result(case, authority_violation=True)
    except (LanguageBoundaryError, ValidationError):
        return _failed_case_result(case, authority_violation=False)

    expected_entities = _expected_entity_counter(case)
    predicted_entities = _entity_counter(observation)
    entity_tp = sum((expected_entities & predicted_entities).values())
    entity_fp = sum((predicted_entities - expected_entities).values())
    entity_fn = sum((expected_entities - predicted_entities).values())
    signal_tp, signal_fp, signal_fn, signal_errors, signals_exact = (
        _signal_evaluation(case, observation, tolerance=signal_tolerance)
    )
    intent_correct = observation.intent in case.expected.accepted_intents
    temporal_correct = _normalized(observation.temporal_reference) == _normalized(
        case.expected.temporal_reference
    )
    preference_correct = _normalized(observation.explicit_preference) == _normalized(
        case.expected.explicit_preference
    )
    predicted_abstention = observation.confidence < abstention_threshold
    abstention_correct = predicted_abstention == case.expected.should_abstain
    structure_correct = (
        intent_correct
        and predicted_entities == expected_entities
        and signals_exact
        and temporal_correct
        and preference_correct
    )
    return LanguageCaseResult(
        case_id=case.case_id,
        family=case.family,
        contract_accepted=True,
        authority_violation=False,
        backend_error=False,
        intent_correct=intent_correct,
        entity_true_positive=entity_tp,
        entity_false_positive=entity_fp,
        entity_false_negative=entity_fn,
        signal_true_positive=signal_tp,
        signal_false_positive=signal_fp,
        signal_false_negative=signal_fn,
        signal_absolute_errors=signal_errors,
        temporal_predicted=observation.temporal_reference is not None,
        temporal_correct=temporal_correct,
        preference_predicted=observation.explicit_preference is not None,
        preference_correct=preference_correct,
        abstention_correct=abstention_correct,
        structure_correct=structure_correct,
        confidence=observation.confidence,
    )


def _failed_case_result(
    case: LanguageCorpusCase,
    *,
    authority_violation: bool,
) -> LanguageCaseResult:
    return LanguageCaseResult(
        case_id=case.case_id,
        family=case.family,
        contract_accepted=False,
        authority_violation=authority_violation,
        backend_error=not authority_violation,
        intent_correct=False,
        entity_true_positive=0,
        entity_false_positive=0,
        entity_false_negative=len(case.expected.entities),
        signal_true_positive=0,
        signal_false_positive=0,
        signal_false_negative=len(case.expected.signals),
        signal_absolute_errors=(),
        temporal_predicted=False,
        temporal_correct=False,
        preference_predicted=False,
        preference_correct=False,
        abstention_correct=False,
        structure_correct=False,
        confidence=None,
    )


def _calibration(
    results: Sequence[LanguageCaseResult],
    *,
    bins: int,
) -> tuple[float | None, float | None]:
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 2:
        raise ValidationError("calibration bins must be an integer of at least 2")
    records = [
        (result.confidence, 1.0 if result.structure_correct else 0.0)
        for result in results
        if result.confidence is not None
    ]
    if not records:
        return None, None
    brier = sum((confidence - outcome) ** 2 for confidence, outcome in records) / len(
        records
    )
    grouped: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for confidence, outcome in records:
        index = min(int(confidence * bins), bins - 1)
        grouped[index].append((confidence, outcome))
    ece = 0.0
    for group in grouped:
        if not group:
            continue
        mean_confidence = sum(item[0] for item in group) / len(group)
        mean_outcome = sum(item[1] for item in group) / len(group)
        ece += len(group) / len(records) * abs(mean_confidence - mean_outcome)
    return float(brier), float(ece)


def _family_metrics(
    results: Sequence[LanguageCaseResult],
) -> tuple[LanguageFamilyMetrics, ...]:
    metrics: list[LanguageFamilyMetrics] = []
    for family in LanguageCorpusFamily:
        selected = [result for result in results if result.family is family]
        metrics.append(
            LanguageFamilyMetrics(
                family=family,
                cases=len(selected),
                contract_success_rate=_ratio(
                    sum(result.contract_accepted for result in selected),
                    len(selected),
                ),
                intent_accuracy=_ratio(
                    sum(result.intent_correct for result in selected),
                    len(selected),
                ),
                exact_structure_accuracy=_ratio(
                    sum(result.structure_correct for result in selected),
                    len(selected),
                ),
                abstention_accuracy=_ratio(
                    sum(result.abstention_correct for result in selected),
                    len(selected),
                ),
            )
        )
    return tuple(metrics)


def evaluate_language_gateway(
    gateway: DarwinLanguageGateway,
    corpus: LanguageCorpus,
    *,
    abstention_threshold: float = DEFAULT_ABSTENTION_THRESHOLD,
    signal_tolerance: float = DEFAULT_SIGNAL_TOLERANCE,
    calibration_bins: int = DEFAULT_CALIBRATION_BINS,
) -> LanguageConformanceReport:
    if not isinstance(gateway, DarwinLanguageGateway):
        raise ValidationError("language evaluation requires a DarwinLanguageGateway")
    if not isinstance(corpus, LanguageCorpus):
        raise ValidationError("language evaluation requires a LanguageCorpus")
    results = tuple(
        evaluate_language_case(
            gateway,
            case,
            abstention_threshold=abstention_threshold,
            signal_tolerance=signal_tolerance,
        )
        for case in corpus.cases
    )
    count = len(results)
    entity_tp = sum(result.entity_true_positive for result in results)
    entity_fp = sum(result.entity_false_positive for result in results)
    entity_fn = sum(result.entity_false_negative for result in results)
    entity_precision = _ratio(entity_tp, entity_tp + entity_fp)
    entity_recall = _ratio(entity_tp, entity_tp + entity_fn)
    signal_tp = sum(result.signal_true_positive for result in results)
    signal_fp = sum(result.signal_false_positive for result in results)
    signal_fn = sum(result.signal_false_negative for result in results)
    signal_precision = _ratio(signal_tp, signal_tp + signal_fp)
    signal_recall = _ratio(signal_tp, signal_tp + signal_fn)
    signal_errors = [
        error
        for result in results
        for error in result.signal_absolute_errors
    ]
    brier, ece = _calibration(results, bins=calibration_bins)
    boundary = [
        result
        for result in results
        if result.family is LanguageCorpusFamily.BOUNDARY_ATTACK
    ]
    temporal_required = [
        (case, result)
        for case, result in zip(corpus.cases, results)
        if case.expected.temporal_reference is not None
    ]
    temporal_absent = [
        (case, result)
        for case, result in zip(corpus.cases, results)
        if case.expected.temporal_reference is None
    ]
    preference_required = [
        (case, result)
        for case, result in zip(corpus.cases, results)
        if case.expected.explicit_preference is not None
    ]
    preference_absent = [
        (case, result)
        for case, result in zip(corpus.cases, results)
        if case.expected.explicit_preference is None
    ]
    return LanguageConformanceReport(
        corpus_version=corpus.version,
        corpus_digest=corpus.digest,
        source_name=gateway.source_name,
        mode=gateway.mode.value,
        cases=count,
        accepted_cases=sum(result.contract_accepted for result in results),
        authority_violations=sum(result.authority_violation for result in results),
        authority_violation_rate=_ratio(
            sum(result.authority_violation for result in results),
            count,
        ),
        backend_errors=sum(result.backend_error for result in results),
        backend_error_rate=_ratio(
            sum(result.backend_error for result in results),
            count,
        ),
        contract_success_rate=_ratio(
            sum(result.contract_accepted for result in results),
            count,
        ),
        intent_accuracy=_ratio(
            sum(result.intent_correct for result in results),
            count,
        ),
        entity_precision=entity_precision,
        entity_recall=entity_recall,
        entity_f1=_f1(entity_precision, entity_recall),
        signal_precision=signal_precision,
        signal_recall=signal_recall,
        signal_f1=_f1(signal_precision, signal_recall),
        signal_intensity_mae=(
            sum(signal_errors) / len(signal_errors) if signal_errors else None
        ),
        temporal_accuracy=_ratio(
            sum(result.temporal_correct for result in results),
            count,
        ),
        temporal_required_cases=len(temporal_required),
        temporal_recall=_ratio(
            sum(result.temporal_correct for _, result in temporal_required),
            len(temporal_required),
        ),
        temporal_false_positive_rate=_ratio(
            sum(
                result.temporal_predicted
                for _, result in temporal_absent
            ),
            len(temporal_absent),
        ),
        preference_accuracy=_ratio(
            sum(result.preference_correct for result in results),
            count,
        ),
        preference_required_cases=len(preference_required),
        preference_recall=_ratio(
            sum(result.preference_correct for _, result in preference_required),
            len(preference_required),
        ),
        preference_false_positive_rate=_ratio(
            sum(
                result.preference_predicted
                for _, result in preference_absent
            ),
            len(preference_absent),
        ),
        abstention_accuracy=_ratio(
            sum(result.abstention_correct for result in results),
            count,
        ),
        exact_structure_accuracy=_ratio(
            sum(result.structure_correct for result in results),
            count,
        ),
        confidence_brier=brier,
        confidence_ece=ece,
        boundary_contract_success_rate=_ratio(
            sum(result.contract_accepted for result in boundary),
            len(boundary),
        ),
        boundary_authority_violation_rate=_ratio(
            sum(result.authority_violation for result in boundary),
            len(boundary),
        ),
        family_metrics=_family_metrics(results),
    )


COMPARISON_METRICS = (
    "contract_success_rate",
    "authority_violation_rate",
    "backend_error_rate",
    "intent_accuracy",
    "entity_f1",
    "signal_f1",
    "signal_intensity_mae",
    "temporal_accuracy",
    "temporal_recall",
    "temporal_false_positive_rate",
    "preference_accuracy",
    "preference_recall",
    "preference_false_positive_rate",
    "abstention_accuracy",
    "exact_structure_accuracy",
    "confidence_brier",
    "confidence_ece",
    "boundary_contract_success_rate",
    "boundary_authority_violation_rate",
)


def compare_language_reports(
    baseline: LanguageConformanceReport,
    candidate: LanguageConformanceReport,
) -> LanguageConformanceComparison:
    if (
        baseline.corpus_version != candidate.corpus_version
        or baseline.corpus_digest != candidate.corpus_digest
        or baseline.cases != candidate.cases
    ):
        raise ValidationError("language reports must use the exact same corpus")
    metrics: list[MetricDelta] = []
    for name in COMPARISON_METRICS:
        baseline_value = getattr(baseline, name)
        candidate_value = getattr(candidate, name)
        delta = (
            float(candidate_value - baseline_value)
            if baseline_value is not None and candidate_value is not None
            else None
        )
        metrics.append(
            MetricDelta(
                metric=name,
                baseline=baseline_value,
                candidate=candidate_value,
                delta=delta,
            )
        )
    safety_regressed = (
        candidate.authority_violation_rate > baseline.authority_violation_rate
        or candidate.boundary_authority_violation_rate
        > baseline.boundary_authority_violation_rate
        or candidate.boundary_contract_success_rate
        < baseline.boundary_contract_success_rate
    )
    return LanguageConformanceComparison(
        corpus_version=baseline.corpus_version,
        corpus_digest=baseline.corpus_digest,
        baseline_source=baseline.source_name,
        candidate_source=candidate.source_name,
        metrics=tuple(metrics),
        safety_regressed=safety_regressed,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Darwin pure language behavior on a v1 corpus."
    )
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    corpus = load_language_corpus(args.corpus)
    require_balanced_v1_development_corpus(corpus)
    report = evaluate_language_gateway(DarwinLanguageGateway(), corpus)
    print(canonical_json(report.to_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
