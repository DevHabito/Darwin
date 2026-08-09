"""Held-out multiscale concept-drift benchmark for Darwin H50-L5."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from itertools import product
import json
import math
from statistics import fmean
from typing import Any, Iterable, Sequence

from .drift_lab import (
    DEFAULT_EXPERT_WINDOWS,
    FixedShareMemoryForecaster,
    MultiphaseBernoulliStream,
    _fixed_share_weights_after_outcome,
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
    StationaryBernoulliForecaster,
)


DEVELOPMENT_SEEDS = tuple(range(8400, 8420))
FINAL_SEEDS = tuple(range(8500, 8540))
ETA_CANDIDATES = (0.5, 1.0, 2.0, 4.0, 8.0)
SHARE_RATE_CANDIDATES = (0.001, 0.005, 0.01, 0.05)
LOCAL_DRIFT_EVALUATOR = "darwin_v50.drift_lab.local_evaluator"


@dataclass(frozen=True, slots=True)
class FixedWindowCandidateScore:
    window_size: int
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_size": self.window_size,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class MultiscaleCandidateScore:
    eta: float
    share_rate: float
    mean_total_brier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "eta": self.eta,
            "share_rate": self.share_rate,
            "mean_total_brier": self.mean_total_brier,
        }


@dataclass(frozen=True, slots=True)
class DevelopmentSelection:
    seeds: tuple[int, ...]
    fixed_window_scores: tuple[FixedWindowCandidateScore, ...]
    multiscale_scores: tuple[MultiscaleCandidateScore, ...]
    selected_fixed_window: int
    selected_eta: float
    selected_share_rate: float

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_fixed_window": self.selected_fixed_window,
            "selected_eta": self.selected_eta,
            "selected_share_rate": self.selected_share_rate,
        }
        if include_scores:
            result["fixed_window_scores"] = [
                score.to_dict() for score in self.fixed_window_scores
            ]
            result["multiscale_scores"] = [
                score.to_dict() for score in self.multiscale_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class DriftForecastRecord:
    index: int
    outcome: bool
    stationary_probability: float
    fixed_window_probability: float
    multiscale_probability: float
    dominant_expert: str


@dataclass(frozen=True, slots=True)
class MultiscaleWorldResult:
    seed: int
    stationary_total_brier: float
    fixed_window_total_brier: float
    multiscale_total_brier: float
    fixed_window_abrupt_recovery_brier: float
    multiscale_abrupt_recovery_brier: float
    fixed_window_recurrence_brier: float
    multiscale_recurrence_brier: float
    fixed_window_gradual_brier: float
    multiscale_gradual_brier: float
    distinct_dominant_experts: int
    dominant_expert_switches: int
    archive_retained: bool
    snapshot_round_trip_exact: bool

    @property
    def total_improvement_vs_fixed(self) -> float:
        return self.fixed_window_total_brier - self.multiscale_total_brier

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "stationary_total_brier": self.stationary_total_brier,
            "fixed_window_total_brier": self.fixed_window_total_brier,
            "multiscale_total_brier": self.multiscale_total_brier,
            "total_improvement_vs_fixed": self.total_improvement_vs_fixed,
            "fixed_window_abrupt_recovery_brier": (
                self.fixed_window_abrupt_recovery_brier
            ),
            "multiscale_abrupt_recovery_brier": (
                self.multiscale_abrupt_recovery_brier
            ),
            "fixed_window_recurrence_brier": (
                self.fixed_window_recurrence_brier
            ),
            "multiscale_recurrence_brier": (
                self.multiscale_recurrence_brier
            ),
            "fixed_window_gradual_brier": self.fixed_window_gradual_brier,
            "multiscale_gradual_brier": self.multiscale_gradual_brier,
            "distinct_dominant_experts": self.distinct_dominant_experts,
            "dominant_expert_switches": self.dominant_expert_switches,
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": self.snapshot_round_trip_exact,
        }


@dataclass(frozen=True, slots=True)
class MultiscaleSuiteReport:
    development: DevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[MultiscaleWorldResult, ...]
    final_world_count: int
    stationary_total_brier: float
    fixed_window_total_brier: float
    multiscale_total_brier: float
    total_brier_improvement_vs_fixed: float
    total_brier_improvement_vs_stationary: float
    world_win_rate_vs_fixed: float
    recurrence_brier_improvement_vs_fixed: float
    gradual_brier_degradation_vs_fixed: float
    abrupt_recovery_brier_degradation_vs_fixed: float
    mean_distinct_dominant_experts: float
    mean_dominant_expert_switches: float
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
        minimum_recurrence_improvement_vs_fixed: float = 0.0,
        maximum_gradual_degradation_vs_fixed: float = 0.005,
        maximum_abrupt_recovery_degradation_vs_fixed: float = 0.01,
        minimum_total_improvement_vs_stationary: float = 0.05,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
    ) -> bool:
        return (
            self.total_brier_improvement_vs_fixed
            >= minimum_total_improvement_vs_fixed
            and self.world_win_rate_vs_fixed
            >= minimum_world_win_rate_vs_fixed
            and self.recurrence_brier_improvement_vs_fixed
            >= minimum_recurrence_improvement_vs_fixed
            and self.gradual_brier_degradation_vs_fixed
            <= maximum_gradual_degradation_vs_fixed
            and self.abrupt_recovery_brier_degradation_vs_fixed
            <= maximum_abrupt_recovery_degradation_vs_fixed
            and self.total_brier_improvement_vs_stationary
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
            "stationary_total_brier": self.stationary_total_brier,
            "fixed_window_total_brier": self.fixed_window_total_brier,
            "multiscale_total_brier": self.multiscale_total_brier,
            "total_brier_improvement_vs_fixed": (
                self.total_brier_improvement_vs_fixed
            ),
            "total_brier_improvement_vs_stationary": (
                self.total_brier_improvement_vs_stationary
            ),
            "world_win_rate_vs_fixed": self.world_win_rate_vs_fixed,
            "recurrence_brier_improvement_vs_fixed": (
                self.recurrence_brier_improvement_vs_fixed
            ),
            "gradual_brier_degradation_vs_fixed": (
                self.gradual_brier_degradation_vs_fixed
            ),
            "abrupt_recovery_brier_degradation_vs_fixed": (
                self.abrupt_recovery_brier_degradation_vs_fixed
            ),
            "mean_distinct_dominant_experts": (
                self.mean_distinct_dominant_experts
            ),
            "mean_dominant_expert_switches": (
                self.mean_dominant_expert_switches
            ),
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
        raise ValidationError(f"{field} must contain integer seeds")
    if len(set(normalized)) != len(normalized):
        raise ValidationError(f"{field} seeds must be unique")
    return normalized


def _observations_for_seed(seed: int) -> tuple[BinaryStreamObservation, ...]:
    stream = MultiphaseBernoulliStream(seed)
    return tuple(
        stream.next_observation()
        for _ in range(MultiphaseBernoulliStream.TOTAL_OBSERVATIONS)
    )


def select_development_configuration(
    seeds: Iterable[int] = DEVELOPMENT_SEEDS,
    *,
    fixed_window_candidates: Sequence[int] = DEFAULT_EXPERT_WINDOWS,
    eta_candidates: Sequence[float] = ETA_CANDIDATES,
    share_rate_candidates: Sequence[float] = SHARE_RATE_CANDIDATES,
) -> DevelopmentSelection:
    normalized_seeds = _normalize_seeds(seeds, field="development")
    windows = tuple(fixed_window_candidates)
    etas = tuple(eta_candidates)
    share_rates = tuple(share_rate_candidates)
    if not windows or any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 2
        for value in windows
    ):
        raise ValidationError(
            "fixed-window candidates must be integers of at least two"
        )
    if (
        len(set(windows)) != len(windows)
        or tuple(sorted(windows)) != windows
    ):
        raise ValidationError(
            "fixed-window candidates must be unique and increasing"
        )
    if not etas or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
        for value in etas
    ):
        raise ValidationError(
            "eta candidates must be finite and positive"
        )
    if len(set(etas)) != len(etas):
        raise ValidationError(
            "eta candidates must be unique"
        )
    if not share_rates or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < value < 1.0
        for value in share_rates
    ):
        raise ValidationError(
            "share-rate candidates must be within (0, 1)"
        )
    if len(set(share_rates)) != len(share_rates):
        raise ValidationError("share-rate candidates must be unique")
    traces: list[
        tuple[
            tuple[tuple[float, ...], bool],
            ...,
        ]
    ] = []
    for seed in normalized_seeds:
        expert_source = FixedShareMemoryForecaster(
            window_sizes=windows,
            eta=1.0,
            share_rate=0.01,
        )
        trace: list[tuple[tuple[float, ...], bool]] = []
        for observation in _observations_for_seed(seed):
            forecast = expert_source.predict()
            trace.append(
                (
                    forecast.expert_probabilities,
                    observation.outcome,
                )
            )
            expert_source.observe(observation)
        traces.append(tuple(trace))
    fixed_scores: list[FixedWindowCandidateScore] = []
    for window_index, window_size in enumerate(windows, start=1):
        world_scores = tuple(
            fmean(
                (
                    probabilities[window_index] - float(outcome)
                )
                ** 2
                for probabilities, outcome in trace
            )
            for trace in traces
        )
        fixed_scores.append(
            FixedWindowCandidateScore(
                window_size=window_size,
                mean_total_brier=fmean(world_scores),
            )
        )
    multiscale_scores: list[MultiscaleCandidateScore] = []
    for eta, share_rate in product(etas, share_rates):
        candidate_world_scores: list[float] = []
        for trace in traces:
            expert_count = 1 + len(windows)
            weights = tuple(
                1.0 / expert_count for _ in range(expert_count)
            )
            losses: list[float] = []
            for probabilities, outcome in trace:
                probability = sum(
                    weight * expert_probability
                    for weight, expert_probability in zip(
                        weights,
                        probabilities,
                        strict=True,
                    )
                )
                losses.append((probability - float(outcome)) ** 2)
                weights = _fixed_share_weights_after_outcome(
                    weights,
                    probabilities,
                    outcome,
                    eta=float(eta),
                    share_rate=float(share_rate),
                )
            candidate_world_scores.append(fmean(losses))
        multiscale_scores.append(
            MultiscaleCandidateScore(
                eta=float(eta),
                share_rate=float(share_rate),
                mean_total_brier=fmean(candidate_world_scores),
            )
        )
    selected_fixed = min(
        fixed_scores,
        key=lambda score: (score.mean_total_brier, score.window_size),
    )
    selected_multiscale = min(
        multiscale_scores,
        key=lambda score: (
            score.mean_total_brier,
            score.eta,
            score.share_rate,
        ),
    )
    return DevelopmentSelection(
        seeds=normalized_seeds,
        fixed_window_scores=tuple(fixed_scores),
        multiscale_scores=tuple(multiscale_scores),
        selected_fixed_window=selected_fixed.window_size,
        selected_eta=selected_multiscale.eta,
        selected_share_rate=selected_multiscale.share_rate,
    )


def _brier_for_indices(
    records: Sequence[DriftForecastRecord],
    probability_field: str,
    indices: Sequence[int],
) -> float:
    selected = tuple(records[index - 1] for index in indices)
    values = tuple(
        (
            getattr(record, probability_field)
            - float(record.outcome)
        )
        ** 2
        for record in selected
    )
    if not values:
        raise ValidationError("Brier region cannot be empty")
    return fmean(values)


def run_multiscale_world(
    seed: int,
    *,
    selected_fixed_window: int,
    selected_eta: float,
    selected_share_rate: float,
    expert_windows: Sequence[int] = DEFAULT_EXPERT_WINDOWS,
) -> MultiscaleWorldResult:
    stream = MultiphaseBernoulliStream(seed)
    stationary = StationaryBernoulliForecaster()
    fixed = FixedWindowBernoulliForecaster(selected_fixed_window)
    multiscale = FixedShareMemoryForecaster(
        window_sizes=expert_windows,
        eta=selected_eta,
        share_rate=selected_share_rate,
    )
    records: list[DriftForecastRecord] = []
    observations: list[BinaryStreamObservation] = []
    for _ in range(MultiphaseBernoulliStream.TOTAL_OBSERVATIONS):
        stationary_forecast = stationary.predict()
        fixed_forecast = fixed.predict()
        multiscale_forecast = multiscale.predict()
        observation = stream.next_observation()
        records.append(
            DriftForecastRecord(
                index=observation.index,
                outcome=observation.outcome,
                stationary_probability=stationary_forecast.probability,
                fixed_window_probability=fixed_forecast.probability,
                multiscale_probability=multiscale_forecast.probability,
                dominant_expert=multiscale_forecast.dominant_expert,
            )
        )
        stationary.observe(observation)
        fixed.observe(observation)
        multiscale.observe(observation)
        observations.append(observation)

    all_indices = tuple(range(1, 3001))
    abrupt_indices = tuple(range(601, 729)) + tuple(range(1201, 1329))
    recurrence_indices = tuple(range(1201, 1801))
    gradual_indices = tuple(range(1801, 2401))
    dominant = tuple(record.dominant_expert for record in records)
    snapshot = multiscale.to_snapshot()
    restored = FixedShareMemoryForecaster.from_snapshot(snapshot)
    snapshot_exact = (
        restored.to_snapshot() == snapshot
        and restored.predict() == multiscale.predict()
        and restored.archive == multiscale.archive
        and restored.weights == multiscale.weights
    )
    return MultiscaleWorldResult(
        seed=seed,
        stationary_total_brier=_brier_for_indices(
            records,
            "stationary_probability",
            all_indices,
        ),
        fixed_window_total_brier=_brier_for_indices(
            records,
            "fixed_window_probability",
            all_indices,
        ),
        multiscale_total_brier=_brier_for_indices(
            records,
            "multiscale_probability",
            all_indices,
        ),
        fixed_window_abrupt_recovery_brier=_brier_for_indices(
            records,
            "fixed_window_probability",
            abrupt_indices,
        ),
        multiscale_abrupt_recovery_brier=_brier_for_indices(
            records,
            "multiscale_probability",
            abrupt_indices,
        ),
        fixed_window_recurrence_brier=_brier_for_indices(
            records,
            "fixed_window_probability",
            recurrence_indices,
        ),
        multiscale_recurrence_brier=_brier_for_indices(
            records,
            "multiscale_probability",
            recurrence_indices,
        ),
        fixed_window_gradual_brier=_brier_for_indices(
            records,
            "fixed_window_probability",
            gradual_indices,
        ),
        multiscale_gradual_brier=_brier_for_indices(
            records,
            "multiscale_probability",
            gradual_indices,
        ),
        distinct_dominant_experts=len(set(dominant)),
        dominant_expert_switches=sum(
            left != right
            for left, right in zip(
                dominant[:-1],
                dominant[1:],
                strict=True,
            )
        ),
        archive_retained=(
            multiscale.archive == tuple(observations)
            and len(multiscale.archive)
            == MultiphaseBernoulliStream.TOTAL_OBSERVATIONS
        ),
        snapshot_round_trip_exact=snapshot_exact,
    )


def run_multiscale_suite(
    *,
    development_seeds: Iterable[int] = DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = FINAL_SEEDS,
    fixed_window_candidates: Sequence[int] = DEFAULT_EXPERT_WINDOWS,
    eta_candidates: Sequence[float] = ETA_CANDIDATES,
    share_rate_candidates: Sequence[float] = SHARE_RATE_CANDIDATES,
) -> MultiscaleSuiteReport:
    normalized_development = _normalize_seeds(
        development_seeds,
        field="development",
    )
    normalized_final = _normalize_seeds(final_seeds, field="final")
    if set(normalized_development) & set(normalized_final):
        raise ValidationError(
            "development and final seeds must be disjoint"
        )
    development = select_development_configuration(
        normalized_development,
        fixed_window_candidates=fixed_window_candidates,
        eta_candidates=eta_candidates,
        share_rate_candidates=share_rate_candidates,
    )
    worlds = tuple(
        run_multiscale_world(
            seed,
            selected_fixed_window=development.selected_fixed_window,
            selected_eta=development.selected_eta,
            selected_share_rate=development.selected_share_rate,
            expert_windows=tuple(fixed_window_candidates),
        )
        for seed in normalized_final
    )
    stationary_total = fmean(
        world.stationary_total_brier for world in worlds
    )
    fixed_total = fmean(
        world.fixed_window_total_brier for world in worlds
    )
    multiscale_total = fmean(
        world.multiscale_total_brier for world in worlds
    )
    fixed_recurrence = fmean(
        world.fixed_window_recurrence_brier for world in worlds
    )
    multiscale_recurrence = fmean(
        world.multiscale_recurrence_brier for world in worlds
    )
    fixed_gradual = fmean(
        world.fixed_window_gradual_brier for world in worlds
    )
    multiscale_gradual = fmean(
        world.multiscale_gradual_brier for world in worlds
    )
    fixed_abrupt = fmean(
        world.fixed_window_abrupt_recovery_brier for world in worlds
    )
    multiscale_abrupt = fmean(
        world.multiscale_abrupt_recovery_brier for world in worlds
    )
    return MultiscaleSuiteReport(
        development=development,
        final_seeds=normalized_final,
        worlds=worlds,
        final_world_count=len(worlds),
        stationary_total_brier=stationary_total,
        fixed_window_total_brier=fixed_total,
        multiscale_total_brier=multiscale_total,
        total_brier_improvement_vs_fixed=fixed_total - multiscale_total,
        total_brier_improvement_vs_stationary=(
            stationary_total - multiscale_total
        ),
        world_win_rate_vs_fixed=(
            sum(
                world.multiscale_total_brier
                < world.fixed_window_total_brier
                for world in worlds
            )
            / len(worlds)
        ),
        recurrence_brier_improvement_vs_fixed=(
            fixed_recurrence - multiscale_recurrence
        ),
        gradual_brier_degradation_vs_fixed=(
            multiscale_gradual - fixed_gradual
        ),
        abrupt_recovery_brier_degradation_vs_fixed=(
            multiscale_abrupt - fixed_abrupt
        ),
        mean_distinct_dominant_experts=fmean(
            world.distinct_dominant_experts for world in worlds
        ),
        mean_dominant_expert_switches=fmean(
            world.dominant_expert_switches for world in worlds
        ),
        archive_retention_rate=fmean(
            float(world.archive_retained) for world in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(world.snapshot_round_trip_exact) for world in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Hyperparameters and the fixed-window baseline are selected only "
            "on development seeds 8400-8419. Final metrics use disjoint seeds "
            "8500-8539, with every forecast recorded before its outcome."
        ),
        limitations=(
            "The stream is synthetic, univariate, Bernoulli, and has fixed phase boundaries.",
            "The probability schedule is identical across seeds.",
            "Expert windows and the hyperparameter grid are human-defined.",
            "The aggregate does not explicitly identify or name latent regimes.",
            "A recurring probability is not evidence of autobiographical recall.",
            "The snapshot is structurally validated but not cryptographically authenticated.",
            "The evaluator is local and does not provide independent E3 evidence.",
            "Success does not imply consciousness, general intelligence, emotion, or personhood.",
        ),
    )


def record_multiscale_result(
    kernel: DarwinKernelV50,
    report: MultiscaleSuiteReport,
    *,
    minimum_total_improvement_vs_fixed: float = 0.002,
) -> ObservationResult:
    if (
        isinstance(minimum_total_improvement_vs_fixed, bool)
        or not isinstance(
            minimum_total_improvement_vs_fixed,
            (int, float),
        )
        or not math.isfinite(minimum_total_improvement_vs_fixed)
    ):
        raise ValidationError(
            "minimum_total_improvement_vs_fixed must be finite"
        )
    all_criteria_satisfied = report.passes_regression_criteria(
        minimum_total_improvement_vs_fixed=(
            minimum_total_improvement_vs_fixed
        )
    )
    goal = kernel.create_goal(
        session_id=(
            f"drift-lab:{report.final_seeds[0]}:{report.final_seeds[-1]}"
        ),
        description=(
            "Online multiscale memory beats a development-selected fixed window"
        ),
        evidence_source=LOCAL_DRIFT_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-multiscale-concept-drift",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_fixed_window": (
                report.development.selected_fixed_window
            ),
            "selected_eta": report.development.selected_eta,
            "selected_share_rate": (
                report.development.selected_share_rate
            ),
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_DRIFT_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": all_criteria_satisfied,
            "total_brier_improvement_vs_fixed": (
                report.total_brier_improvement_vs_fixed
            ),
            "world_win_rate_vs_fixed": report.world_win_rate_vs_fixed,
            "recurrence_brier_improvement_vs_fixed": (
                report.recurrence_brier_improvement_vs_fixed
            ),
            "gradual_brier_degradation_vs_fixed": (
                report.gradual_brier_degradation_vs_fixed
            ),
            "abrupt_recovery_brier_degradation_vs_fixed": (
                report.abrupt_recovery_brier_degradation_vs_fixed
            ),
            "total_brier_improvement_vs_stationary": (
                report.total_brier_improvement_vs_stationary
            ),
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": (
                report.snapshot_round_trip_rate
            ),
        },
    )


def report_with_total_improvement(
    report: MultiscaleSuiteReport,
    value: float,
) -> MultiscaleSuiteReport:
    return replace(report, total_brier_improvement_vs_fixed=value)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Darwin H50-L5 held-out multiscale drift benchmark."
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument(
        "--development-scores",
        action="store_true",
    )
    args = parser.parse_args(argv)
    report = run_multiscale_suite(
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
