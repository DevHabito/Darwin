"""Held-out benchmark for Darwin H50-L7 recurrent-regime retrieval."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from itertools import product
import json
import math
from statistics import fmean
from typing import Any, Iterable, Sequence

from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .regime_memory_lab import (
    RegimeMemoryBernoulliStream,
    RegimeMemorySchedule,
    RegimeMemoryTransition,
    RegimeRepositoryForecaster,
    TOTAL_REGIME_MEMORY_OBSERVATIONS,
)
from .temporal_lab import (
    BinaryStreamObservation,
    FixedWindowBernoulliForecaster,
)


REGIME_MEMORY_DEVELOPMENT_SEEDS = tuple(range(10000, 10020))
REGIME_MEMORY_FINAL_SEEDS = tuple(range(10100, 10160))
REGIME_MEMORY_FIXED_WINDOWS = (16, 32, 64, 128)
REGIME_MEMORY_DETECTOR_WINDOWS = (32, 64)
REGIME_MEMORY_DETECTOR_DELTAS = (0.01, 0.05)
REGIME_MEMORY_MATCH_TOLERANCES = (0.10, 0.15)
RECOVERY_WINDOW_SIZE = 128
LOCAL_REGIME_MEMORY_EVALUATOR = (
    "darwin_v50.regime_memory_lab.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class RegimeMemoryFixedCandidateScore:
    window_size: int
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_size": self.window_size,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class RegimeMemoryCandidateScore:
    detector_window_size: int
    false_alarm_delta: float
    match_tolerance: float
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector_window_size": self.detector_window_size,
            "false_alarm_delta": self.false_alarm_delta,
            "match_tolerance": self.match_tolerance,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class RegimeMemoryDevelopmentSelection:
    seeds: tuple[int, ...]
    fixed_scores: tuple[RegimeMemoryFixedCandidateScore, ...]
    candidate_scores: tuple[RegimeMemoryCandidateScore, ...]
    selected_fixed_window: int
    selected_detector_window_size: int
    selected_false_alarm_delta: float
    selected_match_tolerance: float

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_fixed_window": self.selected_fixed_window,
            "selected_detector_window_size": (
                self.selected_detector_window_size
            ),
            "selected_false_alarm_delta": (
                self.selected_false_alarm_delta
            ),
            "selected_match_tolerance": self.selected_match_tolerance,
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
class RegimeMemoryForecastRecord:
    index: int
    outcome: bool
    fixed_probability: float
    ablation_probability: float
    repository_probability: float


@dataclass(frozen=True, slots=True)
class RegimeMemoryWorldResult:
    seed: int
    family: str
    phase_start_indices: tuple[int, int, int, int, int]
    recurrence_boundary_count: int
    correctly_retrieved_recurrence_count: int
    novelty_boundary_count: int
    abstained_novelty_count: int
    falsely_retrieved_novelty_count: int
    retrieval_event_count: int
    correct_retrieval_event_count: int
    fixed_total_brier: float
    ablation_total_brier: float
    repository_total_brier: float
    fixed_recurrence_brier: float
    ablation_recurrence_brier: float
    repository_recurrence_brier: float
    archive_retained: bool
    snapshot_round_trip_exact: bool
    prototype_count: int
    transition_count: int

    @property
    def total_improvement_vs_fixed(self) -> float:
        return self.fixed_total_brier - self.repository_total_brier

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "family": self.family,
            "phase_start_indices": list(self.phase_start_indices),
            "recurrence_boundary_count": self.recurrence_boundary_count,
            "correctly_retrieved_recurrence_count": (
                self.correctly_retrieved_recurrence_count
            ),
            "novelty_boundary_count": self.novelty_boundary_count,
            "abstained_novelty_count": self.abstained_novelty_count,
            "falsely_retrieved_novelty_count": (
                self.falsely_retrieved_novelty_count
            ),
            "retrieval_event_count": self.retrieval_event_count,
            "correct_retrieval_event_count": (
                self.correct_retrieval_event_count
            ),
            "fixed_total_brier": self.fixed_total_brier,
            "ablation_total_brier": self.ablation_total_brier,
            "repository_total_brier": self.repository_total_brier,
            "total_improvement_vs_fixed": self.total_improvement_vs_fixed,
            "fixed_recurrence_brier": self.fixed_recurrence_brier,
            "ablation_recurrence_brier": self.ablation_recurrence_brier,
            "repository_recurrence_brier": self.repository_recurrence_brier,
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": self.snapshot_round_trip_exact,
            "prototype_count": self.prototype_count,
            "transition_count": self.transition_count,
        }


@dataclass(frozen=True, slots=True)
class RegimeMemorySuiteReport:
    development: RegimeMemoryDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[RegimeMemoryWorldResult, ...]
    final_world_count: int
    recurring_world_count: int
    novelty_world_count: int
    unique_schedule_count: int
    fixed_total_brier: float
    ablation_total_brier: float
    repository_total_brier: float
    total_improvement_vs_fixed: float
    world_win_rate_vs_fixed: float
    recurrence_improvement_vs_ablation: float
    recurrence_improvement_vs_fixed: float
    correct_recurrence_retrieval_coverage: float
    retrieval_precision: float
    novelty_abstention_coverage: float
    novelty_false_retrieval_rate: float
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
        minimum_recurrence_improvement_vs_ablation: float = 0.001,
        minimum_recurrence_improvement_vs_fixed: float = 0.002,
        minimum_correct_recurrence_retrieval_coverage: float = 0.80,
        minimum_retrieval_precision: float = 0.90,
        minimum_novelty_abstention_coverage: float = 0.70,
        maximum_novelty_false_retrieval_rate: float = 0.10,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
    ) -> bool:
        return (
            self.total_improvement_vs_fixed
            >= minimum_total_improvement_vs_fixed
            and self.world_win_rate_vs_fixed
            >= minimum_world_win_rate_vs_fixed
            and self.recurrence_improvement_vs_ablation
            >= minimum_recurrence_improvement_vs_ablation
            and self.recurrence_improvement_vs_fixed
            >= minimum_recurrence_improvement_vs_fixed
            and self.correct_recurrence_retrieval_coverage
            >= minimum_correct_recurrence_retrieval_coverage
            and self.retrieval_precision >= minimum_retrieval_precision
            and self.novelty_abstention_coverage
            >= minimum_novelty_abstention_coverage
            and self.novelty_false_retrieval_rate
            <= maximum_novelty_false_retrieval_rate
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
            "recurring_world_count": self.recurring_world_count,
            "novelty_world_count": self.novelty_world_count,
            "unique_schedule_count": self.unique_schedule_count,
            "fixed_total_brier": self.fixed_total_brier,
            "ablation_total_brier": self.ablation_total_brier,
            "repository_total_brier": self.repository_total_brier,
            "total_improvement_vs_fixed": self.total_improvement_vs_fixed,
            "world_win_rate_vs_fixed": self.world_win_rate_vs_fixed,
            "recurrence_improvement_vs_ablation": (
                self.recurrence_improvement_vs_ablation
            ),
            "recurrence_improvement_vs_fixed": (
                self.recurrence_improvement_vs_fixed
            ),
            "correct_recurrence_retrieval_coverage": (
                self.correct_recurrence_retrieval_coverage
            ),
            "retrieval_precision": self.retrieval_precision,
            "novelty_abstention_coverage": (
                self.novelty_abstention_coverage
            ),
            "novelty_false_retrieval_rate": (
                self.novelty_false_retrieval_rate
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


def _observations(seed: int) -> tuple[BinaryStreamObservation, ...]:
    stream = RegimeMemoryBernoulliStream(seed)
    return tuple(
        stream.next_observation()
        for _ in range(TOTAL_REGIME_MEMORY_OBSERVATIONS)
    )


def _fixed_score(
    observations: Sequence[BinaryStreamObservation],
    window_size: int,
) -> float:
    model = FixedWindowBernoulliForecaster(window_size)
    losses: list[float] = []
    for observation in observations:
        probability = model.predict().probability
        losses.append((probability - float(observation.outcome)) ** 2)
        model.observe(observation)
    return fmean(losses)


def _candidate_score(
    observations: Sequence[BinaryStreamObservation],
    *,
    detector_window_size: int,
    false_alarm_delta: float,
    match_tolerance: float,
) -> float:
    model = RegimeRepositoryForecaster(
        detector_window_size=detector_window_size,
        false_alarm_delta=false_alarm_delta,
        match_tolerance=match_tolerance,
    )
    losses: list[float] = []
    for observation in observations:
        probability = model.predict().probability
        losses.append((probability - float(observation.outcome)) ** 2)
        model.observe(observation)
    return fmean(losses)


def _validate_candidates(
    values: Sequence[int] | Sequence[float],
    *,
    field: str,
    integer: bool,
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
            raise ValidationError(f"{field} candidates have an invalid type")
        if integer:
            if value < 2:
                raise ValidationError(f"{field} candidates must be at least two")
        elif not math.isfinite(value) or not 0.0 < value < 1.0:
            raise ValidationError(
                f"{field} candidates must be finite values within (0, 1)"
            )
    return result


def select_regime_memory_configuration(
    seeds: Iterable[int] = REGIME_MEMORY_DEVELOPMENT_SEEDS,
    *,
    fixed_window_candidates: Sequence[int] = REGIME_MEMORY_FIXED_WINDOWS,
    detector_window_candidates: Sequence[int] = (
        REGIME_MEMORY_DETECTOR_WINDOWS
    ),
    false_alarm_delta_candidates: Sequence[float] = (
        REGIME_MEMORY_DETECTOR_DELTAS
    ),
    match_tolerance_candidates: Sequence[float] = (
        REGIME_MEMORY_MATCH_TOLERANCES
    ),
) -> RegimeMemoryDevelopmentSelection:
    normalized = _normalize_seeds(seeds, field="development")
    windows = _validate_candidates(
        fixed_window_candidates,
        field="fixed-window",
        integer=True,
    )
    detector_windows = _validate_candidates(
        detector_window_candidates,
        field="detector-window",
        integer=True,
    )
    deltas = _validate_candidates(
        false_alarm_delta_candidates,
        field="false-alarm-delta",
        integer=False,
    )
    tolerances = _validate_candidates(
        match_tolerance_candidates,
        field="match-tolerance",
        integer=False,
    )
    observations_by_seed = tuple(_observations(seed) for seed in normalized)
    fixed_scores = tuple(
        RegimeMemoryFixedCandidateScore(
            window_size=int(window),
            mean_total_brier=fmean(
                _fixed_score(observations, int(window))
                for observations in observations_by_seed
            ),
        )
        for window in windows
    )
    candidate_scores = tuple(
        RegimeMemoryCandidateScore(
            detector_window_size=int(window),
            false_alarm_delta=float(delta),
            match_tolerance=float(tolerance),
            mean_total_brier=fmean(
                _candidate_score(
                    observations,
                    detector_window_size=int(window),
                    false_alarm_delta=float(delta),
                    match_tolerance=float(tolerance),
                )
                for observations in observations_by_seed
            ),
        )
        for window, delta, tolerance in product(
            detector_windows,
            deltas,
            tolerances,
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
            item.detector_window_size,
            item.false_alarm_delta,
            item.match_tolerance,
        ),
    )
    return RegimeMemoryDevelopmentSelection(
        seeds=normalized,
        fixed_scores=fixed_scores,
        candidate_scores=candidate_scores,
        selected_fixed_window=selected_fixed.window_size,
        selected_detector_window_size=(
            selected_candidate.detector_window_size
        ),
        selected_false_alarm_delta=(
            selected_candidate.false_alarm_delta
        ),
        selected_match_tolerance=selected_candidate.match_tolerance,
    )


def _region_brier(
    records: Sequence[RegimeMemoryForecastRecord],
    probability_field: str,
    indices: Sequence[int],
) -> float:
    losses = tuple(
        (
            getattr(records[index - 1], probability_field)
            - float(records[index - 1].outcome)
        )
        ** 2
        for index in indices
    )
    if not losses:
        raise ValidationError("Brier region cannot be empty")
    return fmean(losses)


def _events_in_recovery_window(
    transitions: Sequence[RegimeMemoryTransition],
    boundary: int,
) -> tuple[RegimeMemoryTransition, ...]:
    return tuple(
        item
        for item in transitions
        if boundary
        <= item.decision_index
        < boundary + RECOVERY_WINDOW_SIZE
    )


def _retrieval_is_correct(
    event: RegimeMemoryTransition,
    schedule: RegimeMemorySchedule,
    match_tolerance: float,
) -> bool:
    return (
        event.retrieved_probability is not None
        and abs(
            event.retrieved_probability
            - schedule.probability_at(event.decision_index)
        )
        <= match_tolerance
    )


def run_regime_memory_world(
    seed: int,
    *,
    selected_fixed_window: int,
    selected_detector_window_size: int,
    selected_false_alarm_delta: float,
    selected_match_tolerance: float,
) -> RegimeMemoryWorldResult:
    stream = RegimeMemoryBernoulliStream(seed)
    schedule = stream.schedule
    fixed = FixedWindowBernoulliForecaster(selected_fixed_window)
    repository = RegimeRepositoryForecaster(
        detector_window_size=selected_detector_window_size,
        false_alarm_delta=selected_false_alarm_delta,
        match_tolerance=selected_match_tolerance,
    )
    observations: list[BinaryStreamObservation] = []
    records: list[RegimeMemoryForecastRecord] = []
    for index in range(1, TOTAL_REGIME_MEMORY_OBSERVATIONS + 1):
        fixed_probability = fixed.predict().probability
        forecast = repository.predict()
        observation = stream.next_observation()
        records.append(
            RegimeMemoryForecastRecord(
                index=index,
                outcome=observation.outcome,
                fixed_probability=fixed_probability,
                ablation_probability=forecast.base_probability,
                repository_probability=forecast.probability,
            )
        )
        fixed.observe(observation)
        repository.observe(observation)
        observations.append(observation)

    recurrence_indices = tuple(
        index
        for boundary in schedule.recurrence_indices
        for index in range(boundary, boundary + RECOVERY_WINDOW_SIZE)
    )
    all_indices = tuple(range(1, TOTAL_REGIME_MEMORY_OBSERVATIONS + 1))
    recurrence_events = tuple(
        _events_in_recovery_window(repository.transitions, boundary)
        for boundary in schedule.recurrence_indices
    )
    novelty_events = tuple(
        _events_in_recovery_window(repository.transitions, boundary)
        for boundary in schedule.novelty_indices
    )
    retrieved_events = tuple(
        item
        for item in repository.transitions
        if item.retrieved_prototype_id is not None
    )
    correct_recurrence_count = sum(
        any(
            _retrieval_is_correct(item, schedule, selected_match_tolerance)
            for item in events
        )
        for events in recurrence_events
    )
    abstained_novelty_count = sum(
        any(item.abstained for item in events)
        for events in novelty_events
    )
    falsely_retrieved_novelty_count = sum(
        any(item.retrieved_prototype_id is not None for item in events)
        for events in novelty_events
    )
    snapshot = repository.to_snapshot()
    restored = RegimeRepositoryForecaster.from_snapshot(snapshot)
    snapshot_exact = (
        restored.to_snapshot() == snapshot
        and restored.predict() == repository.predict()
        and restored.archive == repository.archive
        and restored.prototypes == repository.prototypes
        and restored.transitions == repository.transitions
    )
    return RegimeMemoryWorldResult(
        seed=seed,
        family=schedule.family,
        phase_start_indices=schedule.phase_start_indices,
        recurrence_boundary_count=len(schedule.recurrence_indices),
        correctly_retrieved_recurrence_count=correct_recurrence_count,
        novelty_boundary_count=len(schedule.novelty_indices),
        abstained_novelty_count=abstained_novelty_count,
        falsely_retrieved_novelty_count=falsely_retrieved_novelty_count,
        retrieval_event_count=len(retrieved_events),
        correct_retrieval_event_count=sum(
            _retrieval_is_correct(
                item,
                schedule,
                selected_match_tolerance,
            )
            for item in retrieved_events
        ),
        fixed_total_brier=_region_brier(
            records,
            "fixed_probability",
            all_indices,
        ),
        ablation_total_brier=_region_brier(
            records,
            "ablation_probability",
            all_indices,
        ),
        repository_total_brier=_region_brier(
            records,
            "repository_probability",
            all_indices,
        ),
        fixed_recurrence_brier=_region_brier(
            records,
            "fixed_probability",
            recurrence_indices,
        ),
        ablation_recurrence_brier=_region_brier(
            records,
            "ablation_probability",
            recurrence_indices,
        ),
        repository_recurrence_brier=_region_brier(
            records,
            "repository_probability",
            recurrence_indices,
        ),
        archive_retained=(
            repository.archive == tuple(observations)
            and len(repository.archive)
            == TOTAL_REGIME_MEMORY_OBSERVATIONS
        ),
        snapshot_round_trip_exact=snapshot_exact,
        prototype_count=len(repository.prototypes),
        transition_count=len(repository.transitions),
    )


def run_regime_memory_suite(
    *,
    development_seeds: Iterable[int] = REGIME_MEMORY_DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = REGIME_MEMORY_FINAL_SEEDS,
    fixed_window_candidates: Sequence[int] = REGIME_MEMORY_FIXED_WINDOWS,
    detector_window_candidates: Sequence[int] = (
        REGIME_MEMORY_DETECTOR_WINDOWS
    ),
    false_alarm_delta_candidates: Sequence[float] = (
        REGIME_MEMORY_DETECTOR_DELTAS
    ),
    match_tolerance_candidates: Sequence[float] = (
        REGIME_MEMORY_MATCH_TOLERANCES
    ),
) -> RegimeMemorySuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds,
        field="development",
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("development and final seeds must be disjoint")
    development = select_regime_memory_configuration(
        development_seed_tuple,
        fixed_window_candidates=fixed_window_candidates,
        detector_window_candidates=detector_window_candidates,
        false_alarm_delta_candidates=false_alarm_delta_candidates,
        match_tolerance_candidates=match_tolerance_candidates,
    )
    worlds = tuple(
        run_regime_memory_world(
            seed,
            selected_fixed_window=development.selected_fixed_window,
            selected_detector_window_size=(
                development.selected_detector_window_size
            ),
            selected_false_alarm_delta=(
                development.selected_false_alarm_delta
            ),
            selected_match_tolerance=(
                development.selected_match_tolerance
            ),
        )
        for seed in final_seed_tuple
    )
    fixed_total = fmean(item.fixed_total_brier for item in worlds)
    ablation_total = fmean(item.ablation_total_brier for item in worlds)
    repository_total = fmean(
        item.repository_total_brier for item in worlds
    )
    fixed_recurrence = fmean(
        item.fixed_recurrence_brier for item in worlds
    )
    ablation_recurrence = fmean(
        item.ablation_recurrence_brier for item in worlds
    )
    repository_recurrence = fmean(
        item.repository_recurrence_brier for item in worlds
    )
    recurrence_count = sum(
        item.recurrence_boundary_count for item in worlds
    )
    novelty_count = sum(item.novelty_boundary_count for item in worlds)
    retrieval_count = sum(item.retrieval_event_count for item in worlds)
    schedule_signatures = {
        (
            item.family,
            item.phase_start_indices,
            RegimeMemorySchedule.from_seed(item.seed).probability_a,
            RegimeMemorySchedule.from_seed(item.seed).probability_b,
            RegimeMemorySchedule.from_seed(item.seed).probability_c,
        )
        for item in worlds
    }
    return RegimeMemorySuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        recurring_world_count=sum(
            item.family == "recurring" for item in worlds
        ),
        novelty_world_count=sum(item.family == "novelty" for item in worlds),
        unique_schedule_count=len(schedule_signatures),
        fixed_total_brier=fixed_total,
        ablation_total_brier=ablation_total,
        repository_total_brier=repository_total,
        total_improvement_vs_fixed=fixed_total - repository_total,
        world_win_rate_vs_fixed=(
            sum(
                item.repository_total_brier < item.fixed_total_brier
                for item in worlds
            )
            / len(worlds)
        ),
        recurrence_improvement_vs_ablation=(
            ablation_recurrence - repository_recurrence
        ),
        recurrence_improvement_vs_fixed=(
            fixed_recurrence - repository_recurrence
        ),
        correct_recurrence_retrieval_coverage=(
            sum(
                item.correctly_retrieved_recurrence_count
                for item in worlds
            )
            / recurrence_count
        ),
        retrieval_precision=(
            sum(item.correct_retrieval_event_count for item in worlds)
            / retrieval_count
            if retrieval_count
            else 0.0
        ),
        novelty_abstention_coverage=(
            sum(item.abstained_novelty_count for item in worlds)
            / novelty_count
            if novelty_count
            else 0.0
        ),
        novelty_false_retrieval_rate=(
            sum(
                item.falsely_retrieved_novelty_count
                for item in worlds
            )
            / novelty_count
            if novelty_count
            else 0.0
        ),
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
            "Configurations are selected only on seeds 10000-10019. Final "
            "metrics use disjoint seeds 10100-10159, balanced recurrent and "
            "novel families, and causal prequential forecasts."
        ),
        limitations=(
            "The streams are synthetic, univariate, and Bernoulli.",
            "Regime identity is reduced to one outcome probability.",
            "The detector, grid, tolerance, and blend weight are human-defined.",
            "The H50-L6 posterior remains a pruned approximation near its selected limit.",
            "The ablation probability is the candidate's identical internal base posterior.",
            "The snapshot is structurally validated but not cryptographically authenticated.",
            "The evaluator is local and does not provide independent E3 evidence.",
            "Success does not imply language, consciousness, personhood, emotion, or general intelligence.",
        ),
    )


def record_regime_memory_result(
    kernel: DarwinKernelV50,
    report: RegimeMemorySuiteReport,
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"regime-memory-lab:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Selective recurrent-regime retrieval beats fixed and ablated baselines"
        ),
        evidence_source=LOCAL_REGIME_MEMORY_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-selective-regime-retrieval",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_fixed_window": (
                report.development.selected_fixed_window
            ),
            "selected_detector_window_size": (
                report.development.selected_detector_window_size
            ),
            "selected_false_alarm_delta": (
                report.development.selected_false_alarm_delta
            ),
            "selected_match_tolerance": (
                report.development.selected_match_tolerance
            ),
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_REGIME_MEMORY_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": all_criteria_satisfied,
            "total_improvement_vs_fixed": (
                report.total_improvement_vs_fixed
            ),
            "world_win_rate_vs_fixed": report.world_win_rate_vs_fixed,
            "recurrence_improvement_vs_ablation": (
                report.recurrence_improvement_vs_ablation
            ),
            "recurrence_improvement_vs_fixed": (
                report.recurrence_improvement_vs_fixed
            ),
            "correct_recurrence_retrieval_coverage": (
                report.correct_recurrence_retrieval_coverage
            ),
            "retrieval_precision": report.retrieval_precision,
            "novelty_abstention_coverage": (
                report.novelty_abstention_coverage
            ),
            "novelty_false_retrieval_rate": (
                report.novelty_false_retrieval_rate
            ),
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
        },
    )


def report_with_regime_memory_metrics(
    report: RegimeMemorySuiteReport,
    **changes: Any,
) -> RegimeMemorySuiteReport:
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
        description="Run Darwin H50-L7 recurrent-regime retrieval benchmark."
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=REGIME_MEMORY_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=REGIME_MEMORY_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    args = parser.parse_args(argv)
    report = run_regime_memory_suite(
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
