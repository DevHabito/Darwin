"""Held-out variable-schedule benchmark for Darwin H50-L6."""

from __future__ import annotations

import argparse
from collections import deque
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
from .run_length_lab import (
    PrunedBayesianRunLengthForecaster,
    TOTAL_VARIABLE_OBSERVATIONS,
    VariableRegimeBernoulliStream,
    VariableRegimeSchedule,
)
from .temporal_lab import (
    BinaryStreamObservation,
    FixedWindowBernoulliForecaster,
)


RUN_LENGTH_DEVELOPMENT_SEEDS = tuple(range(9300, 9320))
RUN_LENGTH_FINAL_SEEDS = tuple(range(9400, 9460))
RUN_LENGTH_FIXED_WINDOWS = (16, 32, 64, 128, 256)
EXPECTED_DURATION_CANDIDATES = (200, 400, 800)
MAXIMUM_HYPOTHESES_CANDIDATES = (16, 32, 64)
LOCAL_RUN_LENGTH_EVALUATOR = (
    "darwin_v50.run_length_lab.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class RunLengthFixedCandidateScore:
    window_size: int
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_size": self.window_size,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class RunLengthCandidateScore:
    expected_duration: int
    maximum_hypotheses: int
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_duration": self.expected_duration,
            "maximum_hypotheses": self.maximum_hypotheses,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class RunLengthDevelopmentSelection:
    seeds: tuple[int, ...]
    fixed_scores: tuple[RunLengthFixedCandidateScore, ...]
    run_length_scores: tuple[RunLengthCandidateScore, ...]
    selected_fixed_window: int
    selected_expected_duration: int
    selected_maximum_hypotheses: int

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_fixed_window": self.selected_fixed_window,
            "selected_expected_duration": self.selected_expected_duration,
            "selected_maximum_hypotheses": (
                self.selected_maximum_hypotheses
            ),
        }
        if include_scores:
            result["fixed_scores"] = [
                score.to_dict() for score in self.fixed_scores
            ]
            result["run_length_scores"] = [
                score.to_dict() for score in self.run_length_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class RunLengthForecastRecord:
    index: int
    outcome: bool
    stationary_probability: float
    fixed_probability: float
    run_length_probability: float


@dataclass(frozen=True, slots=True)
class RunLengthWorldResult:
    seed: int
    first_abrupt_index: int
    recurrence_index: int
    gradual_start_index: int
    gradual_end_index: int
    first_probability: float
    opposite_probability: float
    stationary_total_brier: float
    fixed_total_brier: float
    run_length_total_brier: float
    fixed_abrupt_brier: float
    run_length_abrupt_brier: float
    fixed_recurrence_brier: float
    run_length_recurrence_brier: float
    fixed_gradual_brier: float
    run_length_gradual_brier: float
    mean_hypothesis_count: float
    maximum_change_probability: float
    archive_retained: bool
    snapshot_round_trip_exact: bool

    @property
    def total_improvement_vs_fixed(self) -> float:
        return self.fixed_total_brier - self.run_length_total_brier

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "first_abrupt_index": self.first_abrupt_index,
            "recurrence_index": self.recurrence_index,
            "gradual_start_index": self.gradual_start_index,
            "gradual_end_index": self.gradual_end_index,
            "first_probability": self.first_probability,
            "opposite_probability": self.opposite_probability,
            "stationary_total_brier": self.stationary_total_brier,
            "fixed_total_brier": self.fixed_total_brier,
            "run_length_total_brier": self.run_length_total_brier,
            "total_improvement_vs_fixed": self.total_improvement_vs_fixed,
            "fixed_abrupt_brier": self.fixed_abrupt_brier,
            "run_length_abrupt_brier": self.run_length_abrupt_brier,
            "fixed_recurrence_brier": self.fixed_recurrence_brier,
            "run_length_recurrence_brier": self.run_length_recurrence_brier,
            "fixed_gradual_brier": self.fixed_gradual_brier,
            "run_length_gradual_brier": self.run_length_gradual_brier,
            "mean_hypothesis_count": self.mean_hypothesis_count,
            "maximum_change_probability": self.maximum_change_probability,
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": self.snapshot_round_trip_exact,
        }


@dataclass(frozen=True, slots=True)
class RunLengthSuiteReport:
    development: RunLengthDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[RunLengthWorldResult, ...]
    final_world_count: int
    unique_schedule_count: int
    stationary_total_brier: float
    fixed_total_brier: float
    run_length_total_brier: float
    total_improvement_vs_fixed: float
    total_improvement_vs_stationary: float
    world_win_rate_vs_fixed: float
    abrupt_improvement_vs_fixed: float
    recurrence_improvement_vs_fixed: float
    gradual_degradation_vs_fixed: float
    mean_hypothesis_count: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_total_improvement_vs_fixed: float = 0.002,
        minimum_world_win_rate_vs_fixed: float = 0.65,
        minimum_abrupt_improvement_vs_fixed: float = 0.0,
        minimum_recurrence_improvement_vs_fixed: float = 0.0,
        maximum_gradual_degradation_vs_fixed: float = 0.003,
        minimum_total_improvement_vs_stationary: float = 0.05,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
    ) -> bool:
        return (
            self.total_improvement_vs_fixed
            >= minimum_total_improvement_vs_fixed
            and self.world_win_rate_vs_fixed
            >= minimum_world_win_rate_vs_fixed
            and self.abrupt_improvement_vs_fixed
            >= minimum_abrupt_improvement_vs_fixed
            and self.recurrence_improvement_vs_fixed
            >= minimum_recurrence_improvement_vs_fixed
            and self.gradual_degradation_vs_fixed
            <= maximum_gradual_degradation_vs_fixed
            and self.total_improvement_vs_stationary
            >= minimum_total_improvement_vs_stationary
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
            "unique_schedule_count": self.unique_schedule_count,
            "stationary_total_brier": self.stationary_total_brier,
            "fixed_total_brier": self.fixed_total_brier,
            "run_length_total_brier": self.run_length_total_brier,
            "total_improvement_vs_fixed": (
                self.total_improvement_vs_fixed
            ),
            "total_improvement_vs_stationary": (
                self.total_improvement_vs_stationary
            ),
            "world_win_rate_vs_fixed": self.world_win_rate_vs_fixed,
            "abrupt_improvement_vs_fixed": (
                self.abrupt_improvement_vs_fixed
            ),
            "recurrence_improvement_vs_fixed": (
                self.recurrence_improvement_vs_fixed
            ),
            "gradual_degradation_vs_fixed": (
                self.gradual_degradation_vs_fixed
            ),
            "mean_hypothesis_count": self.mean_hypothesis_count,
            "archive_retention_rate": self.archive_retention_rate,
            "snapshot_round_trip_rate": self.snapshot_round_trip_rate,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
            "passes_regression_criteria": self.passes_regression_criteria(),
        }
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


def _normalize_seeds(
    seeds: Iterable[int],
    *,
    field: str,
) -> tuple[int, ...]:
    normalized = tuple(seeds)
    if not normalized:
        raise ValidationError(f"{field} requires at least one seed")
    if any(
        isinstance(seed, bool) or not isinstance(seed, int)
        for seed in normalized
    ):
        raise ValidationError(f"{field} seeds must be integers")
    if len(set(normalized)) != len(normalized):
        raise ValidationError(f"{field} seeds must be unique")
    return normalized


def _observations(seed: int) -> tuple[BinaryStreamObservation, ...]:
    stream = VariableRegimeBernoulliStream(seed)
    return tuple(
        stream.next_observation()
        for _ in range(TOTAL_VARIABLE_OBSERVATIONS)
    )


def _fixed_window_scores(
    observations: Sequence[BinaryStreamObservation],
    windows: Sequence[int],
) -> tuple[float, ...]:
    buffers = tuple(deque(maxlen=window) for window in windows)
    successes = [0 for _ in windows]
    losses = [[] for _ in windows]
    for observation in observations:
        for index, buffer in enumerate(buffers):
            probability = (1 + successes[index]) / (2 + len(buffer))
            losses[index].append(
                (probability - float(observation.outcome)) ** 2
            )
            if len(buffer) == buffer.maxlen and buffer[0]:
                successes[index] -= 1
            buffer.append(observation.outcome)
            successes[index] += int(observation.outcome)
    return tuple(fmean(values) for values in losses)


def _run_length_score(
    observations: Sequence[BinaryStreamObservation],
    *,
    expected_duration: int,
    maximum_hypotheses: int,
) -> float:
    model = PrunedBayesianRunLengthForecaster(
        expected_duration=expected_duration,
        maximum_hypotheses=maximum_hypotheses,
    )
    losses: list[float] = []
    for observation in observations:
        probability = model.predict_probability()
        losses.append((probability - float(observation.outcome)) ** 2)
        model._update_posterior(observation.outcome)
    return fmean(losses)


def select_run_length_configuration(
    seeds: Iterable[int] = RUN_LENGTH_DEVELOPMENT_SEEDS,
    *,
    fixed_window_candidates: Sequence[int] = RUN_LENGTH_FIXED_WINDOWS,
    expected_duration_candidates: Sequence[int] = (
        EXPECTED_DURATION_CANDIDATES
    ),
    maximum_hypotheses_candidates: Sequence[int] = (
        MAXIMUM_HYPOTHESES_CANDIDATES
    ),
) -> RunLengthDevelopmentSelection:
    normalized_seeds = _normalize_seeds(seeds, field="development")
    windows = tuple(fixed_window_candidates)
    durations = tuple(expected_duration_candidates)
    hypothesis_limits = tuple(maximum_hypotheses_candidates)
    for name, values in (
        ("fixed-window", windows),
        ("expected-duration", durations),
        ("hypothesis-limit", hypothesis_limits),
    ):
        if (
            not values
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 2
                for value in values
            )
            or len(set(values)) != len(values)
            or tuple(sorted(values)) != values
        ):
            raise ValidationError(
                f"{name} candidates must be unique increasing integers"
            )
    observations_by_seed = tuple(
        _observations(seed) for seed in normalized_seeds
    )
    fixed_by_seed = tuple(
        _fixed_window_scores(observations, windows)
        for observations in observations_by_seed
    )
    fixed_scores = tuple(
        RunLengthFixedCandidateScore(
            window_size=window,
            mean_total_brier=fmean(
                scores[index] for scores in fixed_by_seed
            ),
        )
        for index, window in enumerate(windows)
    )
    run_length_scores = tuple(
        RunLengthCandidateScore(
            expected_duration=duration,
            maximum_hypotheses=limit,
            mean_total_brier=fmean(
                _run_length_score(
                    observations,
                    expected_duration=duration,
                    maximum_hypotheses=limit,
                )
                for observations in observations_by_seed
            ),
        )
        for duration, limit in product(durations, hypothesis_limits)
    )
    selected_fixed = min(
        fixed_scores,
        key=lambda score: (score.mean_total_brier, score.window_size),
    )
    selected_run_length = min(
        run_length_scores,
        key=lambda score: (
            score.mean_total_brier,
            score.expected_duration,
            score.maximum_hypotheses,
        ),
    )
    return RunLengthDevelopmentSelection(
        seeds=normalized_seeds,
        fixed_scores=fixed_scores,
        run_length_scores=run_length_scores,
        selected_fixed_window=selected_fixed.window_size,
        selected_expected_duration=(
            selected_run_length.expected_duration
        ),
        selected_maximum_hypotheses=(
            selected_run_length.maximum_hypotheses
        ),
    )


def _region_brier(
    records: Sequence[RunLengthForecastRecord],
    probability_field: str,
    indices: Sequence[int],
) -> float:
    values = tuple(
        (
            getattr(records[index - 1], probability_field)
            - float(records[index - 1].outcome)
        )
        ** 2
        for index in indices
    )
    if not values:
        raise ValidationError("Brier region cannot be empty")
    return fmean(values)


def run_run_length_world(
    seed: int,
    *,
    selected_fixed_window: int,
    selected_expected_duration: int,
    selected_maximum_hypotheses: int,
) -> RunLengthWorldResult:
    stream = VariableRegimeBernoulliStream(seed)
    schedule = stream.schedule
    fixed = FixedWindowBernoulliForecaster(selected_fixed_window)
    model = PrunedBayesianRunLengthForecaster(
        expected_duration=selected_expected_duration,
        maximum_hypotheses=selected_maximum_hypotheses,
    )
    records: list[RunLengthForecastRecord] = []
    observations: list[BinaryStreamObservation] = []
    stationary_successes = 0
    hypothesis_counts: list[int] = []
    change_probabilities: list[float] = []
    for index in range(1, TOTAL_VARIABLE_OBSERVATIONS + 1):
        stationary_probability = (1 + stationary_successes) / (1 + index)
        fixed_probability = fixed.predict().probability
        run_length_probability = model.predict_probability()
        observation = stream.next_observation()
        records.append(
            RunLengthForecastRecord(
                index=index,
                outcome=observation.outcome,
                stationary_probability=stationary_probability,
                fixed_probability=fixed_probability,
                run_length_probability=run_length_probability,
            )
        )
        fixed.observe(observation)
        model.observe(observation)
        stationary_successes += int(observation.outcome)
        observations.append(observation)
        hypothesis_counts.append(model.hypothesis_count)
        change_probabilities.append(model.last_change_probability)

    all_indices = tuple(range(1, TOTAL_VARIABLE_OBSERVATIONS + 1))
    abrupt_indices = tuple(
        range(
            schedule.first_abrupt_index,
            schedule.first_abrupt_index + 128,
        )
    ) + tuple(
        range(
            schedule.recurrence_index,
            schedule.recurrence_index + 128,
        )
    )
    recurrence_indices = tuple(
        range(schedule.recurrence_index, schedule.gradual_start_index)
    )
    gradual_indices = tuple(
        range(
            schedule.gradual_start_index,
            schedule.gradual_end_index + 1,
        )
    )
    snapshot = model.to_snapshot()
    restored = PrunedBayesianRunLengthForecaster.from_snapshot(snapshot)
    snapshot_exact = (
        restored.to_snapshot() == snapshot
        and restored.predict() == model.predict()
        and restored.archive == model.archive
        and restored.hypotheses == model.hypotheses
    )
    return RunLengthWorldResult(
        seed=seed,
        first_abrupt_index=schedule.first_abrupt_index,
        recurrence_index=schedule.recurrence_index,
        gradual_start_index=schedule.gradual_start_index,
        gradual_end_index=schedule.gradual_end_index,
        first_probability=schedule.first_probability,
        opposite_probability=schedule.opposite_probability,
        stationary_total_brier=_region_brier(
            records,
            "stationary_probability",
            all_indices,
        ),
        fixed_total_brier=_region_brier(
            records,
            "fixed_probability",
            all_indices,
        ),
        run_length_total_brier=_region_brier(
            records,
            "run_length_probability",
            all_indices,
        ),
        fixed_abrupt_brier=_region_brier(
            records,
            "fixed_probability",
            abrupt_indices,
        ),
        run_length_abrupt_brier=_region_brier(
            records,
            "run_length_probability",
            abrupt_indices,
        ),
        fixed_recurrence_brier=_region_brier(
            records,
            "fixed_probability",
            recurrence_indices,
        ),
        run_length_recurrence_brier=_region_brier(
            records,
            "run_length_probability",
            recurrence_indices,
        ),
        fixed_gradual_brier=_region_brier(
            records,
            "fixed_probability",
            gradual_indices,
        ),
        run_length_gradual_brier=_region_brier(
            records,
            "run_length_probability",
            gradual_indices,
        ),
        mean_hypothesis_count=fmean(hypothesis_counts),
        maximum_change_probability=max(change_probabilities),
        archive_retained=(
            model.archive == tuple(observations)
            and len(model.archive) == TOTAL_VARIABLE_OBSERVATIONS
        ),
        snapshot_round_trip_exact=snapshot_exact,
    )


def run_run_length_suite(
    *,
    development_seeds: Iterable[int] = RUN_LENGTH_DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = RUN_LENGTH_FINAL_SEEDS,
    fixed_window_candidates: Sequence[int] = RUN_LENGTH_FIXED_WINDOWS,
    expected_duration_candidates: Sequence[int] = (
        EXPECTED_DURATION_CANDIDATES
    ),
    maximum_hypotheses_candidates: Sequence[int] = (
        MAXIMUM_HYPOTHESES_CANDIDATES
    ),
) -> RunLengthSuiteReport:
    normalized_development = _normalize_seeds(
        development_seeds,
        field="development",
    )
    normalized_final = _normalize_seeds(final_seeds, field="final")
    if set(normalized_development) & set(normalized_final):
        raise ValidationError(
            "development and final seeds must be disjoint"
        )
    development = select_run_length_configuration(
        normalized_development,
        fixed_window_candidates=fixed_window_candidates,
        expected_duration_candidates=expected_duration_candidates,
        maximum_hypotheses_candidates=maximum_hypotheses_candidates,
    )
    worlds = tuple(
        run_run_length_world(
            seed,
            selected_fixed_window=development.selected_fixed_window,
            selected_expected_duration=(
                development.selected_expected_duration
            ),
            selected_maximum_hypotheses=(
                development.selected_maximum_hypotheses
            ),
        )
        for seed in normalized_final
    )
    stationary_total = fmean(
        world.stationary_total_brier for world in worlds
    )
    fixed_total = fmean(world.fixed_total_brier for world in worlds)
    run_length_total = fmean(
        world.run_length_total_brier for world in worlds
    )
    fixed_abrupt = fmean(world.fixed_abrupt_brier for world in worlds)
    run_length_abrupt = fmean(
        world.run_length_abrupt_brier for world in worlds
    )
    fixed_recurrence = fmean(
        world.fixed_recurrence_brier for world in worlds
    )
    run_length_recurrence = fmean(
        world.run_length_recurrence_brier for world in worlds
    )
    fixed_gradual = fmean(world.fixed_gradual_brier for world in worlds)
    run_length_gradual = fmean(
        world.run_length_gradual_brier for world in worlds
    )
    schedule_signatures = {
        (
            world.first_abrupt_index,
            world.recurrence_index,
            world.gradual_start_index,
            world.gradual_end_index,
            world.first_probability,
            world.opposite_probability,
        )
        for world in worlds
    }
    return RunLengthSuiteReport(
        development=development,
        final_seeds=normalized_final,
        worlds=worlds,
        final_world_count=len(worlds),
        unique_schedule_count=len(schedule_signatures),
        stationary_total_brier=stationary_total,
        fixed_total_brier=fixed_total,
        run_length_total_brier=run_length_total,
        total_improvement_vs_fixed=fixed_total - run_length_total,
        total_improvement_vs_stationary=(
            stationary_total - run_length_total
        ),
        world_win_rate_vs_fixed=(
            sum(
                world.run_length_total_brier < world.fixed_total_brier
                for world in worlds
            )
            / len(worlds)
        ),
        abrupt_improvement_vs_fixed=(
            fixed_abrupt - run_length_abrupt
        ),
        recurrence_improvement_vs_fixed=(
            fixed_recurrence - run_length_recurrence
        ),
        gradual_degradation_vs_fixed=(
            run_length_gradual - fixed_gradual
        ),
        mean_hypothesis_count=fmean(
            world.mean_hypothesis_count for world in worlds
        ),
        archive_retention_rate=fmean(
            float(world.archive_retained) for world in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(world.snapshot_round_trip_exact) for world in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Configurations are selected only on seeds 9300-9319. Final "
            "metrics use disjoint seeds 9400-9459 and variable hidden "
            "schedules. Every forecast precedes its outcome."
        ),
        limitations=(
            "The model is a pruned approximation, not exact BOCPD.",
            "All streams remain synthetic, univariate, and Bernoulli.",
            "Every world follows the same high-level phase order.",
            "The schedule ranges and candidate grid are human-defined.",
            "The model does not explicitly retrieve a named prior regime.",
            "The snapshot is structurally validated but not cryptographically authenticated.",
            "The evaluator is local and does not provide independent E3 evidence.",
            "Success does not imply consciousness, general intelligence, emotion, or personhood.",
        ),
    )


def record_run_length_result(
    kernel: DarwinKernelV50,
    report: RunLengthSuiteReport,
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"run-length-lab:{report.final_seeds[0]}:{report.final_seeds[-1]}"
        ),
        description=(
            "Pruned Bayesian run-length memory beats a selected fixed window"
        ),
        evidence_source=LOCAL_RUN_LENGTH_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-variable-schedule-run-length-memory",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_fixed_window": (
                report.development.selected_fixed_window
            ),
            "selected_expected_duration": (
                report.development.selected_expected_duration
            ),
            "selected_maximum_hypotheses": (
                report.development.selected_maximum_hypotheses
            ),
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_RUN_LENGTH_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": all_criteria_satisfied,
            "total_improvement_vs_fixed": (
                report.total_improvement_vs_fixed
            ),
            "world_win_rate_vs_fixed": report.world_win_rate_vs_fixed,
            "abrupt_improvement_vs_fixed": (
                report.abrupt_improvement_vs_fixed
            ),
            "recurrence_improvement_vs_fixed": (
                report.recurrence_improvement_vs_fixed
            ),
            "gradual_degradation_vs_fixed": (
                report.gradual_degradation_vs_fixed
            ),
            "total_improvement_vs_stationary": (
                report.total_improvement_vs_stationary
            ),
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": (
                report.snapshot_round_trip_rate
            ),
        },
    )


def report_with_run_length_metrics(
    report: RunLengthSuiteReport,
    **changes: Any,
) -> RunLengthSuiteReport:
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
        description="Run Darwin H50-L6 variable-schedule benchmark."
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=RUN_LENGTH_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=RUN_LENGTH_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    args = parser.parse_args(argv)
    report = run_run_length_suite(
        development_seeds=args.development_seeds,
        final_seeds=args.final_seeds,
    )
    print(
        json.dumps(
            report.to_dict(
                include_development_scores=args.development_scores,
                include_worlds=args.details,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
