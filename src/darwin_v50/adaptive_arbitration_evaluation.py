"""Held-out benchmark for Darwin H50-L8 adaptive memory arbitration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from itertools import product
import json
import math
from statistics import fmean
from typing import Any, Iterable, Sequence

from .adaptive_arbitration_lab import (
    ARBITRATION_BIN_COUNT,
    AdaptiveMemoryArbitrator,
    AgeBinnedExpertWeights,
    ArbitrationBernoulliStream,
    ArbitrationSchedule,
    TOTAL_ARBITRATION_OBSERVATIONS,
)
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .temporal_lab import (
    BinaryStreamObservation,
    FixedWindowBernoulliForecaster,
)


ARBITRATION_DEVELOPMENT_SEEDS = tuple(range(12000, 12024))
ARBITRATION_FINAL_SEEDS = tuple(range(12100, 12180))
ARBITRATION_FIXED_WINDOWS = (16, 32, 64, 128)
ARBITRATION_LEARNING_RATES = (2.0, 8.0, 32.0)
ARBITRATION_LOSS_DISCOUNTS = (0.95, 0.99, 1.0)
ARBITRATION_RECOVERY_WINDOW = 128
LOCAL_ARBITRATION_EVALUATOR = (
    "darwin_v50.adaptive_arbitration_lab.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class ArbitrationFixedCandidateScore:
    window_size: int
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_size": self.window_size,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class ArbitrationCandidateScore:
    learning_rate: float
    loss_discount: float
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "learning_rate": self.learning_rate,
            "loss_discount": self.loss_discount,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class ArbitrationDevelopmentSelection:
    seeds: tuple[int, ...]
    fixed_scores: tuple[ArbitrationFixedCandidateScore, ...]
    candidate_scores: tuple[ArbitrationCandidateScore, ...]
    selected_fixed_window: int
    selected_learning_rate: float
    selected_loss_discount: float

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_fixed_window": self.selected_fixed_window,
            "selected_learning_rate": self.selected_learning_rate,
            "selected_loss_discount": self.selected_loss_discount,
        }
        if include_scores:
            result["fixed_scores"] = [
                item.to_dict() for item in self.fixed_scores
            ]
            result["candidate_scores"] = [
                item.to_dict() for item in self.candidate_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class ArbitrationExpertRecord:
    index: int
    outcome: bool
    base_probability: float
    fixed_mix_probability: float
    memory_probability: float | None
    active_age: int | None


@dataclass(frozen=True, slots=True)
class ArbitrationForecastRecord:
    index: int
    outcome: bool
    fixed_window_probability: float
    base_probability: float
    fixed_mix_probability: float
    adaptive_probability: float
    memory_probability: float | None
    memory_weight: float
    age_bin: int | None


@dataclass(frozen=True, slots=True)
class ArbitrationWorldResult:
    seed: int
    family: str
    phase_start_indices: tuple[int, int, int, int, int, int, int]
    fixed_total_brier: float
    base_total_brier: float
    fixed_mix_total_brier: float
    adaptive_total_brier: float
    recurrence_count: int
    fixed_recurrence_loss_sum: float
    base_recurrence_loss_sum: float
    fixed_mix_recurrence_loss_sum: float
    adaptive_recurrence_loss_sum: float
    novelty_count: int
    base_novelty_loss_sum: float
    adaptive_novelty_loss_sum: float
    active_count: int
    base_active_loss_sum: float
    memory_active_loss_sum: float
    adaptive_active_loss_sum: float
    oracle_active_loss_sum: float
    recurrence_boundary_count: int
    correctly_retrieved_recurrence_count: int
    retrieval_event_count: int
    correct_retrieval_event_count: int
    memory_weight_sums: tuple[float, float, float, float, float]
    memory_weight_counts: tuple[int, int, int, int, int]
    archive_retained: bool
    snapshot_round_trip_exact: bool
    prototype_count: int
    transition_count: int

    @property
    def total_improvement_vs_fixed(self) -> float:
        return self.fixed_total_brier - self.adaptive_total_brier

    def to_dict(self) -> dict[str, Any]:
        result = {
            "seed": self.seed,
            "family": self.family,
            "phase_start_indices": list(self.phase_start_indices),
            "fixed_total_brier": self.fixed_total_brier,
            "base_total_brier": self.base_total_brier,
            "fixed_mix_total_brier": self.fixed_mix_total_brier,
            "adaptive_total_brier": self.adaptive_total_brier,
            "total_improvement_vs_fixed": self.total_improvement_vs_fixed,
            "recurrence_count": self.recurrence_count,
            "novelty_count": self.novelty_count,
            "active_count": self.active_count,
            "recurrence_boundary_count": self.recurrence_boundary_count,
            "correctly_retrieved_recurrence_count": (
                self.correctly_retrieved_recurrence_count
            ),
            "retrieval_event_count": self.retrieval_event_count,
            "correct_retrieval_event_count": (
                self.correct_retrieval_event_count
            ),
            "memory_weight_sums": list(self.memory_weight_sums),
            "memory_weight_counts": list(self.memory_weight_counts),
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": self.snapshot_round_trip_exact,
            "prototype_count": self.prototype_count,
            "transition_count": self.transition_count,
        }
        for prefix, total, count in (
            ("fixed_recurrence", self.fixed_recurrence_loss_sum, self.recurrence_count),
            ("base_recurrence", self.base_recurrence_loss_sum, self.recurrence_count),
            (
                "fixed_mix_recurrence",
                self.fixed_mix_recurrence_loss_sum,
                self.recurrence_count,
            ),
            (
                "adaptive_recurrence",
                self.adaptive_recurrence_loss_sum,
                self.recurrence_count,
            ),
            ("base_novelty", self.base_novelty_loss_sum, self.novelty_count),
            (
                "adaptive_novelty",
                self.adaptive_novelty_loss_sum,
                self.novelty_count,
            ),
            ("base_active", self.base_active_loss_sum, self.active_count),
            ("memory_active", self.memory_active_loss_sum, self.active_count),
            (
                "adaptive_active",
                self.adaptive_active_loss_sum,
                self.active_count,
            ),
            ("oracle_active", self.oracle_active_loss_sum, self.active_count),
        ):
            result[f"{prefix}_brier"] = total / count if count else None
        return result


@dataclass(frozen=True, slots=True)
class ArbitrationSuiteReport:
    development: ArbitrationDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[ArbitrationWorldResult, ...]
    final_world_count: int
    family_counts: dict[str, int]
    unique_schedule_count: int
    fixed_total_brier: float
    base_total_brier: float
    fixed_mix_total_brier: float
    adaptive_total_brier: float
    total_improvement_vs_fixed: float
    world_win_rate_vs_fixed: float
    total_improvement_vs_base: float
    recurrence_improvement_vs_base: float
    recurrence_improvement_vs_fixed_mix: float
    exact_recurrence_improvement_vs_base: float
    shifted_recurrence_degradation_vs_base: float
    novelty_degradation_vs_base: float
    active_regret_vs_best_fixed_expert: float
    active_gap_vs_step_oracle: float
    correct_recurrence_retrieval_coverage: float
    retrieval_precision: float
    mean_memory_weights_by_age_bin: tuple[float, float, float, float, float]
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    mean_prototype_count: float
    mean_transition_count: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_total_improvement_vs_fixed: float = 0.002,
        minimum_world_win_rate_vs_fixed: float = 0.65,
        minimum_total_improvement_vs_base: float = 0.0,
        minimum_recurrence_improvement_vs_base: float = 0.0005,
        minimum_recurrence_improvement_vs_fixed_mix: float = 0.001,
        minimum_exact_recurrence_improvement_vs_base: float = 0.0005,
        maximum_shifted_recurrence_degradation_vs_base: float = 0.001,
        maximum_novelty_degradation_vs_base: float = 0.001,
        maximum_active_regret_vs_best_fixed_expert: float = 0.005,
        minimum_correct_recurrence_retrieval_coverage: float = 0.80,
        minimum_retrieval_precision: float = 0.90,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
    ) -> bool:
        return (
            self.total_improvement_vs_fixed
            >= minimum_total_improvement_vs_fixed
            and self.world_win_rate_vs_fixed
            >= minimum_world_win_rate_vs_fixed
            and self.total_improvement_vs_base
            >= minimum_total_improvement_vs_base
            and self.recurrence_improvement_vs_base
            >= minimum_recurrence_improvement_vs_base
            and self.recurrence_improvement_vs_fixed_mix
            >= minimum_recurrence_improvement_vs_fixed_mix
            and self.exact_recurrence_improvement_vs_base
            >= minimum_exact_recurrence_improvement_vs_base
            and self.shifted_recurrence_degradation_vs_base
            <= maximum_shifted_recurrence_degradation_vs_base
            and self.novelty_degradation_vs_base
            <= maximum_novelty_degradation_vs_base
            and self.active_regret_vs_best_fixed_expert
            <= maximum_active_regret_vs_best_fixed_expert
            and self.correct_recurrence_retrieval_coverage
            >= minimum_correct_recurrence_retrieval_coverage
            and self.retrieval_precision >= minimum_retrieval_precision
            and self.archive_retention_rate >= minimum_archive_retention_rate
            and self.snapshot_round_trip_rate
            >= minimum_snapshot_round_trip_rate
        )

    def to_dict(
        self,
        *,
        include_development_scores: bool = True,
        include_worlds: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "development": self.development.to_dict(
                include_scores=include_development_scores
            ),
            "final_seeds": list(self.final_seeds),
            "final_world_count": self.final_world_count,
            "family_counts": self.family_counts,
            "unique_schedule_count": self.unique_schedule_count,
            "fixed_total_brier": self.fixed_total_brier,
            "base_total_brier": self.base_total_brier,
            "fixed_mix_total_brier": self.fixed_mix_total_brier,
            "adaptive_total_brier": self.adaptive_total_brier,
            "total_improvement_vs_fixed": self.total_improvement_vs_fixed,
            "world_win_rate_vs_fixed": self.world_win_rate_vs_fixed,
            "total_improvement_vs_base": self.total_improvement_vs_base,
            "recurrence_improvement_vs_base": (
                self.recurrence_improvement_vs_base
            ),
            "recurrence_improvement_vs_fixed_mix": (
                self.recurrence_improvement_vs_fixed_mix
            ),
            "exact_recurrence_improvement_vs_base": (
                self.exact_recurrence_improvement_vs_base
            ),
            "shifted_recurrence_degradation_vs_base": (
                self.shifted_recurrence_degradation_vs_base
            ),
            "novelty_degradation_vs_base": (
                self.novelty_degradation_vs_base
            ),
            "active_regret_vs_best_fixed_expert": (
                self.active_regret_vs_best_fixed_expert
            ),
            "active_gap_vs_step_oracle": self.active_gap_vs_step_oracle,
            "correct_recurrence_retrieval_coverage": (
                self.correct_recurrence_retrieval_coverage
            ),
            "retrieval_precision": self.retrieval_precision,
            "mean_memory_weights_by_age_bin": list(
                self.mean_memory_weights_by_age_bin
            ),
            "archive_retention_rate": self.archive_retention_rate,
            "snapshot_round_trip_rate": self.snapshot_round_trip_rate,
            "mean_prototype_count": self.mean_prototype_count,
            "mean_transition_count": self.mean_transition_count,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
            "passes_regression_criteria": self.passes_regression_criteria(),
        }
        if include_worlds:
            result["worlds"] = [item.to_dict() for item in self.worlds]
        return result


def _normalize_seeds(
    seeds: Iterable[int],
    *,
    field: str,
) -> tuple[int, ...]:
    result = tuple(seeds)
    if (
        not result
        or any(
            isinstance(seed, bool) or not isinstance(seed, int)
            for seed in result
        )
        or len(set(result)) != len(result)
    ):
        raise ValidationError(f"{field} seeds must be unique integers")
    return result


def _validate_grid(
    values: Sequence[int] | Sequence[float],
    *,
    field: str,
    integer: bool,
    probability: bool = False,
) -> tuple[int, ...] | tuple[float, ...]:
    result = tuple(values)
    if (
        not result
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
    ):
        raise ValidationError(
            f"{field} candidates must be unique and increasing"
        )
    for value in result:
        if isinstance(value, bool) or not isinstance(
            value,
            int if integer else (int, float),
        ):
            raise ValidationError(f"{field} candidate type is invalid")
        if integer and value < 2:
            raise ValidationError(f"{field} candidates must be at least two")
        if not integer and (
            not math.isfinite(value)
            or value <= 0.0
            or (probability and value > 1.0)
        ):
            raise ValidationError(f"{field} candidate value is invalid")
    return result


def _expert_trace(seed: int) -> tuple[ArbitrationExpertRecord, ...]:
    stream = ArbitrationBernoulliStream(seed)
    model = AdaptiveMemoryArbitrator(
        learning_rate=2.0,
        loss_discount=1.0,
    )
    records: list[ArbitrationExpertRecord] = []
    for index in range(1, TOTAL_ARBITRATION_OBSERVATIONS + 1):
        forecast = model.predict()
        observation = stream.next_observation()
        records.append(
            ArbitrationExpertRecord(
                index=index,
                outcome=observation.outcome,
                base_probability=forecast.base_probability,
                fixed_mix_probability=forecast.fixed_mix_probability,
                memory_probability=forecast.memory_probability,
                active_age=forecast.active_age,
            )
        )
        model.observe(observation)
    return tuple(records)


def _adaptive_probabilities(
    records: Sequence[ArbitrationExpertRecord],
    *,
    learning_rate: float,
    loss_discount: float,
) -> tuple[float, ...]:
    weights = AgeBinnedExpertWeights(
        learning_rate=learning_rate,
        loss_discount=loss_discount,
    )
    probabilities: list[float] = []
    for record in records:
        if record.memory_probability is None:
            probability = record.base_probability
        else:
            if record.active_age is None:
                raise ValidationError("active trace lacks age")
            decision = weights.predict(
                base_probability=record.base_probability,
                memory_probability=record.memory_probability,
                active_age=record.active_age,
            )
            probability = decision.probability
            weights.observe(decision, record.outcome)
        probabilities.append(probability)
    return tuple(probabilities)


def _mean_brier(
    probabilities: Sequence[float],
    outcomes: Sequence[bool],
) -> float:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValidationError("Brier inputs must be non-empty and aligned")
    return fmean(
        (probability - float(outcome)) ** 2
        for probability, outcome in zip(
            probabilities,
            outcomes,
            strict=True,
        )
    )


def _fixed_probabilities(
    observations: Sequence[BinaryStreamObservation],
    window_size: int,
) -> tuple[float, ...]:
    model = FixedWindowBernoulliForecaster(window_size)
    probabilities: list[float] = []
    for observation in observations:
        probabilities.append(model.predict().probability)
        model.observe(observation)
    return tuple(probabilities)


def select_arbitration_configuration(
    seeds: Iterable[int] = ARBITRATION_DEVELOPMENT_SEEDS,
    *,
    fixed_window_candidates: Sequence[int] = ARBITRATION_FIXED_WINDOWS,
    learning_rate_candidates: Sequence[float] = (
        ARBITRATION_LEARNING_RATES
    ),
    loss_discount_candidates: Sequence[float] = (
        ARBITRATION_LOSS_DISCOUNTS
    ),
) -> ArbitrationDevelopmentSelection:
    normalized = _normalize_seeds(seeds, field="development")
    windows = _validate_grid(
        fixed_window_candidates,
        field="fixed-window",
        integer=True,
    )
    learning_rates = _validate_grid(
        learning_rate_candidates,
        field="learning-rate",
        integer=False,
    )
    discounts = _validate_grid(
        loss_discount_candidates,
        field="loss-discount",
        integer=False,
        probability=True,
    )
    traces = tuple(_expert_trace(seed) for seed in normalized)
    observations = tuple(
        tuple(
            BinaryStreamObservation(item.index, item.outcome)
            for item in trace
        )
        for trace in traces
    )
    outcomes = tuple(
        tuple(item.outcome for item in trace) for trace in traces
    )
    fixed_scores = tuple(
        ArbitrationFixedCandidateScore(
            window_size=int(window),
            mean_total_brier=fmean(
                _mean_brier(
                    _fixed_probabilities(items, int(window)),
                    outcome_items,
                )
                for items, outcome_items in zip(
                    observations,
                    outcomes,
                    strict=True,
                )
            ),
        )
        for window in windows
    )
    candidate_scores = tuple(
        ArbitrationCandidateScore(
            learning_rate=float(learning_rate),
            loss_discount=float(discount),
            mean_total_brier=fmean(
                _mean_brier(
                    _adaptive_probabilities(
                        trace,
                        learning_rate=float(learning_rate),
                        loss_discount=float(discount),
                    ),
                    outcome_items,
                )
                for trace, outcome_items in zip(
                    traces,
                    outcomes,
                    strict=True,
                )
            ),
        )
        for learning_rate, discount in product(
            learning_rates,
            discounts,
        )
    )
    selected_fixed = min(
        fixed_scores,
        key=lambda item: (item.mean_total_brier, item.window_size),
    )
    selected_candidate = min(
        candidate_scores,
        key=lambda item: (
            item.mean_total_brier,
            item.learning_rate,
            item.loss_discount,
        ),
    )
    return ArbitrationDevelopmentSelection(
        seeds=normalized,
        fixed_scores=fixed_scores,
        candidate_scores=candidate_scores,
        selected_fixed_window=selected_fixed.window_size,
        selected_learning_rate=selected_candidate.learning_rate,
        selected_loss_discount=selected_candidate.loss_discount,
    )


def _loss_sum(
    records: Sequence[ArbitrationForecastRecord],
    probability_field: str,
    indices: Sequence[int],
) -> float:
    return sum(
        (
            getattr(records[index - 1], probability_field)
            - float(records[index - 1].outcome)
        )
        ** 2
        for index in indices
    )


def _event_is_correct(
    event: Any,
    schedule: ArbitrationSchedule,
) -> bool:
    return (
        event.retrieved_probability is not None
        and abs(
            event.retrieved_probability
            - schedule.probability_at(event.decision_index)
        )
        <= 0.15
    )


def run_arbitration_world(
    seed: int,
    *,
    selected_fixed_window: int,
    selected_learning_rate: float,
    selected_loss_discount: float,
) -> ArbitrationWorldResult:
    stream = ArbitrationBernoulliStream(seed)
    schedule = stream.schedule
    fixed = FixedWindowBernoulliForecaster(selected_fixed_window)
    adaptive = AdaptiveMemoryArbitrator(
        learning_rate=selected_learning_rate,
        loss_discount=selected_loss_discount,
    )
    records: list[ArbitrationForecastRecord] = []
    observations: list[BinaryStreamObservation] = []
    weight_sums = [0.0] * ARBITRATION_BIN_COUNT
    weight_counts = [0] * ARBITRATION_BIN_COUNT
    for index in range(1, TOTAL_ARBITRATION_OBSERVATIONS + 1):
        fixed_probability = fixed.predict().probability
        forecast = adaptive.predict()
        observation = stream.next_observation()
        records.append(
            ArbitrationForecastRecord(
                index=index,
                outcome=observation.outcome,
                fixed_window_probability=fixed_probability,
                base_probability=forecast.base_probability,
                fixed_mix_probability=forecast.fixed_mix_probability,
                adaptive_probability=forecast.probability,
                memory_probability=forecast.memory_probability,
                memory_weight=forecast.memory_weight,
                age_bin=forecast.age_bin,
            )
        )
        if forecast.age_bin is not None:
            weight_sums[forecast.age_bin] += forecast.memory_weight
            weight_counts[forecast.age_bin] += 1
        fixed.observe(observation)
        adaptive.observe(observation)
        observations.append(observation)

    all_indices = tuple(range(1, TOTAL_ARBITRATION_OBSERVATIONS + 1))
    recurrence_indices = tuple(
        index
        for boundary in schedule.recurrence_indices
        for index in range(
            boundary,
            min(
                boundary + ARBITRATION_RECOVERY_WINDOW,
                TOTAL_ARBITRATION_OBSERVATIONS + 1,
            ),
        )
    )
    novelty_indices = tuple(
        index
        for boundary in schedule.novelty_indices
        for index in range(
            boundary,
            min(
                boundary + ARBITRATION_RECOVERY_WINDOW,
                TOTAL_ARBITRATION_OBSERVATIONS + 1,
            ),
        )
    )
    active_indices = tuple(
        item.index for item in records if item.memory_probability is not None
    )
    transitions = adaptive.transitions
    recurrence_events = tuple(
        tuple(
            event
            for event in transitions
            if boundary
            <= event.decision_index
            < boundary + ARBITRATION_RECOVERY_WINDOW
        )
        for boundary in schedule.recurrence_indices
    )
    retrieved_events = tuple(
        event
        for event in transitions
        if event.retrieved_prototype_id is not None
    )
    snapshot = adaptive.to_snapshot()
    restored = AdaptiveMemoryArbitrator.from_snapshot(snapshot)
    snapshot_exact = (
        restored.to_snapshot() == snapshot
        and restored.predict() == adaptive.predict()
        and restored.archive == adaptive.archive
        and restored.prototypes == adaptive.prototypes
        and restored.transitions == adaptive.transitions
    )
    fixed_total_loss = _loss_sum(
        records,
        "fixed_window_probability",
        all_indices,
    )
    base_total_loss = _loss_sum(records, "base_probability", all_indices)
    fixed_mix_total_loss = _loss_sum(
        records,
        "fixed_mix_probability",
        all_indices,
    )
    adaptive_total_loss = _loss_sum(
        records,
        "adaptive_probability",
        all_indices,
    )
    base_active_loss = _loss_sum(
        records,
        "base_probability",
        active_indices,
    )
    adaptive_active_loss = _loss_sum(
        records,
        "adaptive_probability",
        active_indices,
    )
    memory_active_loss = sum(
        (
            (records[index - 1].memory_probability or 0.0)
            - float(records[index - 1].outcome)
        )
        ** 2
        for index in active_indices
    )
    oracle_active_loss = sum(
        min(
            (
                records[index - 1].base_probability
                - float(records[index - 1].outcome)
            )
            ** 2,
            (
                (records[index - 1].memory_probability or 0.0)
                - float(records[index - 1].outcome)
            )
            ** 2,
        )
        for index in active_indices
    )
    return ArbitrationWorldResult(
        seed=seed,
        family=schedule.family,
        phase_start_indices=schedule.phase_start_indices,
        fixed_total_brier=fixed_total_loss / len(all_indices),
        base_total_brier=base_total_loss / len(all_indices),
        fixed_mix_total_brier=fixed_mix_total_loss / len(all_indices),
        adaptive_total_brier=adaptive_total_loss / len(all_indices),
        recurrence_count=len(recurrence_indices),
        fixed_recurrence_loss_sum=_loss_sum(
            records,
            "fixed_window_probability",
            recurrence_indices,
        ),
        base_recurrence_loss_sum=_loss_sum(
            records,
            "base_probability",
            recurrence_indices,
        ),
        fixed_mix_recurrence_loss_sum=_loss_sum(
            records,
            "fixed_mix_probability",
            recurrence_indices,
        ),
        adaptive_recurrence_loss_sum=_loss_sum(
            records,
            "adaptive_probability",
            recurrence_indices,
        ),
        novelty_count=len(novelty_indices),
        base_novelty_loss_sum=_loss_sum(
            records,
            "base_probability",
            novelty_indices,
        ),
        adaptive_novelty_loss_sum=_loss_sum(
            records,
            "adaptive_probability",
            novelty_indices,
        ),
        active_count=len(active_indices),
        base_active_loss_sum=base_active_loss,
        memory_active_loss_sum=memory_active_loss,
        adaptive_active_loss_sum=adaptive_active_loss,
        oracle_active_loss_sum=oracle_active_loss,
        recurrence_boundary_count=len(schedule.recurrence_indices),
        correctly_retrieved_recurrence_count=sum(
            any(_event_is_correct(event, schedule) for event in events)
            for events in recurrence_events
        ),
        retrieval_event_count=len(retrieved_events),
        correct_retrieval_event_count=sum(
            _event_is_correct(event, schedule)
            for event in retrieved_events
        ),
        memory_weight_sums=tuple(weight_sums),  # type: ignore[arg-type]
        memory_weight_counts=tuple(weight_counts),  # type: ignore[arg-type]
        archive_retained=(
            adaptive.archive == tuple(observations)
            and len(adaptive.archive) == TOTAL_ARBITRATION_OBSERVATIONS
        ),
        snapshot_round_trip_exact=snapshot_exact,
        prototype_count=len(adaptive.prototypes),
        transition_count=len(adaptive.transitions),
    )


def _pooled_brier(
    worlds: Sequence[ArbitrationWorldResult],
    *,
    loss_field: str,
    count_field: str,
) -> float:
    count = sum(getattr(world, count_field) for world in worlds)
    if count < 1:
        raise ValidationError("pooled region cannot be empty")
    return sum(getattr(world, loss_field) for world in worlds) / count


def run_arbitration_suite(
    *,
    development_seeds: Iterable[int] = ARBITRATION_DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = ARBITRATION_FINAL_SEEDS,
    fixed_window_candidates: Sequence[int] = ARBITRATION_FIXED_WINDOWS,
    learning_rate_candidates: Sequence[float] = (
        ARBITRATION_LEARNING_RATES
    ),
    loss_discount_candidates: Sequence[float] = (
        ARBITRATION_LOSS_DISCOUNTS
    ),
) -> ArbitrationSuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds,
        field="development",
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("development and final seeds must be disjoint")
    development = select_arbitration_configuration(
        development_seed_tuple,
        fixed_window_candidates=fixed_window_candidates,
        learning_rate_candidates=learning_rate_candidates,
        loss_discount_candidates=loss_discount_candidates,
    )
    worlds = tuple(
        run_arbitration_world(
            seed,
            selected_fixed_window=development.selected_fixed_window,
            selected_learning_rate=development.selected_learning_rate,
            selected_loss_discount=development.selected_loss_discount,
        )
        for seed in final_seed_tuple
    )
    fixed_total = fmean(item.fixed_total_brier for item in worlds)
    base_total = fmean(item.base_total_brier for item in worlds)
    fixed_mix_total = fmean(item.fixed_mix_total_brier for item in worlds)
    adaptive_total = fmean(item.adaptive_total_brier for item in worlds)
    fixed_recurrence = _pooled_brier(
        worlds,
        loss_field="fixed_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    base_recurrence = _pooled_brier(
        worlds,
        loss_field="base_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    fixed_mix_recurrence = _pooled_brier(
        worlds,
        loss_field="fixed_mix_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    adaptive_recurrence = _pooled_brier(
        worlds,
        loss_field="adaptive_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    exact_worlds = tuple(
        item for item in worlds if item.family == "exact_recurrence"
    )
    shifted_worlds = tuple(
        item for item in worlds if item.family == "shifted_recurrence"
    )
    novelty_worlds = tuple(item for item in worlds if item.novelty_count)
    exact_base = _pooled_brier(
        exact_worlds,
        loss_field="base_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    exact_adaptive = _pooled_brier(
        exact_worlds,
        loss_field="adaptive_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    shifted_base = _pooled_brier(
        shifted_worlds,
        loss_field="base_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    shifted_adaptive = _pooled_brier(
        shifted_worlds,
        loss_field="adaptive_recurrence_loss_sum",
        count_field="recurrence_count",
    )
    novelty_base = _pooled_brier(
        novelty_worlds,
        loss_field="base_novelty_loss_sum",
        count_field="novelty_count",
    )
    novelty_adaptive = _pooled_brier(
        novelty_worlds,
        loss_field="adaptive_novelty_loss_sum",
        count_field="novelty_count",
    )
    base_active = _pooled_brier(
        worlds,
        loss_field="base_active_loss_sum",
        count_field="active_count",
    )
    memory_active = _pooled_brier(
        worlds,
        loss_field="memory_active_loss_sum",
        count_field="active_count",
    )
    adaptive_active = _pooled_brier(
        worlds,
        loss_field="adaptive_active_loss_sum",
        count_field="active_count",
    )
    oracle_active = _pooled_brier(
        worlds,
        loss_field="oracle_active_loss_sum",
        count_field="active_count",
    )
    recurrence_boundary_count = sum(
        item.recurrence_boundary_count for item in worlds
    )
    retrieval_event_count = sum(
        item.retrieval_event_count for item in worlds
    )
    weight_sums = tuple(
        sum(item.memory_weight_sums[index] for item in worlds)
        for index in range(ARBITRATION_BIN_COUNT)
    )
    weight_counts = tuple(
        sum(item.memory_weight_counts[index] for item in worlds)
        for index in range(ARBITRATION_BIN_COUNT)
    )
    schedule_signatures = {
        (
            item.family,
            item.phase_start_indices,
            ArbitrationSchedule.from_seed(item.seed).probabilities,
        )
        for item in worlds
    }
    family_counts = {
        family: sum(item.family == family for item in worlds)
        for family in (
            "exact_recurrence",
            "shifted_recurrence",
            "returning_novelty",
            "late_novelty",
        )
    }
    return ArbitrationSuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        family_counts=family_counts,
        unique_schedule_count=len(schedule_signatures),
        fixed_total_brier=fixed_total,
        base_total_brier=base_total,
        fixed_mix_total_brier=fixed_mix_total,
        adaptive_total_brier=adaptive_total,
        total_improvement_vs_fixed=fixed_total - adaptive_total,
        world_win_rate_vs_fixed=(
            sum(
                item.adaptive_total_brier < item.fixed_total_brier
                for item in worlds
            )
            / len(worlds)
        ),
        total_improvement_vs_base=base_total - adaptive_total,
        recurrence_improvement_vs_base=(
            base_recurrence - adaptive_recurrence
        ),
        recurrence_improvement_vs_fixed_mix=(
            fixed_mix_recurrence - adaptive_recurrence
        ),
        exact_recurrence_improvement_vs_base=(
            exact_base - exact_adaptive
        ),
        shifted_recurrence_degradation_vs_base=(
            shifted_adaptive - shifted_base
        ),
        novelty_degradation_vs_base=novelty_adaptive - novelty_base,
        active_regret_vs_best_fixed_expert=(
            adaptive_active - min(base_active, memory_active)
        ),
        active_gap_vs_step_oracle=adaptive_active - oracle_active,
        correct_recurrence_retrieval_coverage=(
            sum(
                item.correctly_retrieved_recurrence_count
                for item in worlds
            )
            / recurrence_boundary_count
        ),
        retrieval_precision=(
            sum(item.correct_retrieval_event_count for item in worlds)
            / retrieval_event_count
            if retrieval_event_count
            else 0.0
        ),
        mean_memory_weights_by_age_bin=tuple(
            weight_sums[index] / weight_counts[index]
            if weight_counts[index]
            else 0.0
            for index in range(ARBITRATION_BIN_COUNT)
        ),  # type: ignore[arg-type]
        archive_retention_rate=fmean(
            float(item.archive_retained) for item in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(item.snapshot_round_trip_exact) for item in worlds
        ),
        mean_prototype_count=fmean(
            item.prototype_count for item in worlds
        ),
        mean_transition_count=fmean(
            item.transition_count for item in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Eta and discount are selected only on seeds 12000-12023. "
            "Final metrics use disjoint seeds 12100-12179, four balanced "
            "families, and forecasts emitted before every outcome."
        ),
        limitations=(
            "The worlds remain synthetic, univariate, and Bernoulli.",
            "Expert definitions, age bins, priors, and candidate grid are human-defined.",
            "The run-length posterior is the same pruned H50-L6 approximation.",
            "The repository and detector are frozen from the refuted H50-L7 mechanism.",
            "Online weight adaptation within a world is not general metacognition.",
            "The per-step oracle is diagnostic and not causally executable.",
            "Snapshots are structurally validated but not cryptographically authenticated.",
            "The local evaluator does not provide independent E3 evidence.",
            "Success does not imply language, consciousness, personhood, emotion, or general intelligence.",
        ),
    )


def record_arbitration_result(
    kernel: DarwinKernelV50,
    report: ArbitrationSuiteReport,
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"arbitration-lab:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Adaptive expert arbitration improves recurrent memory use"
        ),
        evidence_source=LOCAL_ARBITRATION_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-adaptive-memory-arbitration",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_fixed_window": (
                report.development.selected_fixed_window
            ),
            "selected_learning_rate": (
                report.development.selected_learning_rate
            ),
            "selected_loss_discount": (
                report.development.selected_loss_discount
            ),
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_ARBITRATION_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": all_criteria_satisfied,
            "total_improvement_vs_fixed": (
                report.total_improvement_vs_fixed
            ),
            "world_win_rate_vs_fixed": report.world_win_rate_vs_fixed,
            "total_improvement_vs_base": report.total_improvement_vs_base,
            "recurrence_improvement_vs_base": (
                report.recurrence_improvement_vs_base
            ),
            "recurrence_improvement_vs_fixed_mix": (
                report.recurrence_improvement_vs_fixed_mix
            ),
            "exact_recurrence_improvement_vs_base": (
                report.exact_recurrence_improvement_vs_base
            ),
            "shifted_recurrence_degradation_vs_base": (
                report.shifted_recurrence_degradation_vs_base
            ),
            "novelty_degradation_vs_base": (
                report.novelty_degradation_vs_base
            ),
            "active_regret_vs_best_fixed_expert": (
                report.active_regret_vs_best_fixed_expert
            ),
            "correct_recurrence_retrieval_coverage": (
                report.correct_recurrence_retrieval_coverage
            ),
            "retrieval_precision": report.retrieval_precision,
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
        },
    )


def report_with_arbitration_metrics(
    report: ArbitrationSuiteReport,
    **changes: Any,
) -> ArbitrationSuiteReport:
    return replace(report, **changes)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Darwin H50-L8 adaptive memory arbitration benchmark."
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=ARBITRATION_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=ARBITRATION_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    args = parser.parse_args(argv)
    report = run_arbitration_suite(
        development_seeds=args.development_seeds,
        final_seeds=args.final_seeds,
    )
    print(
        json.dumps(
            report.to_dict(
                include_development_scores=args.development_scores,
                include_worlds=args.details,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
