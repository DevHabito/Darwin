"""Prequential change-detection benchmark for Darwin H50-L4."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
from statistics import fmean, median
from typing import Any, Iterable, Sequence

from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .temporal_lab import (
    AdaptiveBernoulliForecaster,
    BinaryForecast,
    BinaryStreamObservation,
    FixedWindowBernoulliForecaster,
    RegimeShiftBernoulliStream,
    StationaryBernoulliForecaster,
    beta_bernoulli_forecast,
)


LOCAL_TEMPORAL_EVALUATOR = "darwin_v50.temporal_lab.local_evaluator"


@dataclass(frozen=True, slots=True)
class PrequentialForecastRecord:
    index: int
    outcome: bool
    stationary_probability: float
    adaptive_probability: float
    fixed_window_probability: float
    oracle_probability: float


@dataclass(frozen=True, slots=True)
class TemporalWorldResult:
    seed: int
    change_index: int
    total_observations: int
    detection_indices: tuple[int, ...]
    false_alarm_count: int
    detected_change: bool
    detection_delay: int | None
    stationary_pre_brier: float
    adaptive_pre_brier: float
    fixed_window_pre_brier: float
    oracle_pre_brier: float
    stationary_post_brier: float
    adaptive_post_brier: float
    fixed_window_post_brier: float
    oracle_post_brier: float
    stationary_total_brier: float
    adaptive_total_brier: float
    fixed_window_total_brier: float
    oracle_total_brier: float
    archive_retained: bool
    final_working_memory_size: int
    snapshot_round_trip_exact: bool

    @property
    def post_brier_improvement(self) -> float:
        return self.stationary_post_brier - self.adaptive_post_brier

    @property
    def total_brier_improvement(self) -> float:
        return self.stationary_total_brier - self.adaptive_total_brier

    @property
    def pre_brier_degradation(self) -> float:
        return self.adaptive_pre_brier - self.stationary_pre_brier

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "change_index": self.change_index,
            "total_observations": self.total_observations,
            "detection_indices": list(self.detection_indices),
            "false_alarm_count": self.false_alarm_count,
            "detected_change": self.detected_change,
            "detection_delay": self.detection_delay,
            "stationary_pre_brier": self.stationary_pre_brier,
            "adaptive_pre_brier": self.adaptive_pre_brier,
            "fixed_window_pre_brier": self.fixed_window_pre_brier,
            "oracle_pre_brier": self.oracle_pre_brier,
            "stationary_post_brier": self.stationary_post_brier,
            "adaptive_post_brier": self.adaptive_post_brier,
            "fixed_window_post_brier": self.fixed_window_post_brier,
            "oracle_post_brier": self.oracle_post_brier,
            "stationary_total_brier": self.stationary_total_brier,
            "adaptive_total_brier": self.adaptive_total_brier,
            "fixed_window_total_brier": self.fixed_window_total_brier,
            "oracle_total_brier": self.oracle_total_brier,
            "post_brier_improvement": self.post_brier_improvement,
            "total_brier_improvement": self.total_brier_improvement,
            "pre_brier_degradation": self.pre_brier_degradation,
            "archive_retained": self.archive_retained,
            "final_working_memory_size": self.final_working_memory_size,
            "snapshot_round_trip_exact": self.snapshot_round_trip_exact,
        }


@dataclass(frozen=True, slots=True)
class TemporalSuiteReport:
    seeds: tuple[int, ...]
    worlds: tuple[TemporalWorldResult, ...]
    world_count: int
    change_index: int
    total_observations_per_world: int
    detection_rate: float
    worlds_with_false_alarm: int
    false_alarm_world_rate: float
    mean_detection_delay: float
    median_detection_delay: float
    maximum_detection_delay: int
    stationary_pre_brier: float
    adaptive_pre_brier: float
    fixed_window_pre_brier: float
    stationary_post_brier: float
    adaptive_post_brier: float
    fixed_window_post_brier: float
    oracle_post_brier: float
    stationary_total_brier: float
    adaptive_total_brier: float
    fixed_window_total_brier: float
    oracle_total_brier: float
    post_change_brier_improvement: float
    total_brier_improvement: float
    pre_change_brier_degradation: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    mean_final_working_memory_fraction: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_detection_rate: float = 0.95,
        maximum_false_alarm_world_rate: float = 0.05,
        maximum_detection_delay: int = 128,
        minimum_post_brier_improvement: float = 0.10,
        minimum_total_brier_improvement: float = 0.04,
        maximum_pre_brier_degradation: float = 0.01,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
    ) -> bool:
        return (
            self.detection_rate >= minimum_detection_rate
            and self.false_alarm_world_rate <= maximum_false_alarm_world_rate
            and self.maximum_detection_delay <= maximum_detection_delay
            and self.post_change_brier_improvement
            >= minimum_post_brier_improvement
            and self.total_brier_improvement
            >= minimum_total_brier_improvement
            and self.pre_change_brier_degradation
            <= maximum_pre_brier_degradation
            and self.archive_retention_rate >= minimum_archive_retention_rate
            and self.snapshot_round_trip_rate
            >= minimum_snapshot_round_trip_rate
        )

    def to_dict(self, *, include_worlds: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "world_count": self.world_count,
            "change_index": self.change_index,
            "total_observations_per_world": self.total_observations_per_world,
            "detection_rate": self.detection_rate,
            "worlds_with_false_alarm": self.worlds_with_false_alarm,
            "false_alarm_world_rate": self.false_alarm_world_rate,
            "mean_detection_delay": self.mean_detection_delay,
            "median_detection_delay": self.median_detection_delay,
            "maximum_detection_delay": self.maximum_detection_delay,
            "stationary_pre_brier": self.stationary_pre_brier,
            "adaptive_pre_brier": self.adaptive_pre_brier,
            "fixed_window_pre_brier": self.fixed_window_pre_brier,
            "stationary_post_brier": self.stationary_post_brier,
            "adaptive_post_brier": self.adaptive_post_brier,
            "fixed_window_post_brier": self.fixed_window_post_brier,
            "oracle_post_brier": self.oracle_post_brier,
            "stationary_total_brier": self.stationary_total_brier,
            "adaptive_total_brier": self.adaptive_total_brier,
            "fixed_window_total_brier": self.fixed_window_total_brier,
            "oracle_total_brier": self.oracle_total_brier,
            "post_change_brier_improvement": (
                self.post_change_brier_improvement
            ),
            "total_brier_improvement": self.total_brier_improvement,
            "pre_change_brier_degradation": self.pre_change_brier_degradation,
            "archive_retention_rate": self.archive_retention_rate,
            "snapshot_round_trip_rate": self.snapshot_round_trip_rate,
            "mean_final_working_memory_fraction": (
                self.mean_final_working_memory_fraction
            ),
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
        }
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


def brier_score(
    records: Sequence[PrequentialForecastRecord],
    probability_field: str,
) -> float:
    if not records:
        raise ValidationError("Brier score requires records")
    values: list[float] = []
    for record in records:
        probability = getattr(record, probability_field)
        if not 0.0 <= probability <= 1.0:
            raise ValidationError("forecast probability must be within [0, 1]")
        values.append((probability - float(record.outcome)) ** 2)
    return fmean(values)


def run_temporal_world(
    seed: int,
    *,
    change_index: int = 1001,
    total_observations: int = 2000,
    detector_window_size: int = 64,
    false_alarm_delta: float = 1e-6,
    maximum_working_memory: int = 512,
) -> TemporalWorldResult:
    stream = RegimeShiftBernoulliStream(
        seed,
        change_index=change_index,
        total_observations=total_observations,
    )
    stationary = StationaryBernoulliForecaster()
    fixed = FixedWindowBernoulliForecaster(detector_window_size)
    adaptive = AdaptiveBernoulliForecaster(
        detector_window_size=detector_window_size,
        false_alarm_delta=false_alarm_delta,
        maximum_working_memory=maximum_working_memory,
    )
    oracle_memory: list[BinaryStreamObservation] = []
    records: list[PrequentialForecastRecord] = []
    all_observations: list[BinaryStreamObservation] = []

    for index in range(1, total_observations + 1):
        stationary_forecast = stationary.predict()
        adaptive_forecast = adaptive.predict()
        fixed_forecast = fixed.predict()
        if index == change_index:
            oracle_memory.clear()
        oracle_forecast: BinaryForecast = beta_bernoulli_forecast(oracle_memory)

        observation = stream.next_observation()
        records.append(
            PrequentialForecastRecord(
                index=index,
                outcome=observation.outcome,
                stationary_probability=stationary_forecast.probability,
                adaptive_probability=adaptive_forecast.probability,
                fixed_window_probability=fixed_forecast.probability,
                oracle_probability=oracle_forecast.probability,
            )
        )
        stationary.observe(observation)
        adaptive.observe(observation)
        fixed.observe(observation)
        oracle_memory.append(observation)
        all_observations.append(observation)

    pre = tuple(record for record in records if record.index < change_index)
    post = tuple(record for record in records if record.index >= change_index)
    detections = adaptive.detections
    false_alarms = tuple(
        event for event in detections if event.detection_index < change_index
    )
    valid_detections = tuple(
        event for event in detections if event.detection_index >= change_index
    )
    first_valid = valid_detections[0] if valid_detections else None
    restored = AdaptiveBernoulliForecaster.from_snapshot(adaptive.to_snapshot())
    snapshot_exact = (
        restored.to_snapshot() == adaptive.to_snapshot()
        and restored.predict() == adaptive.predict()
        and restored.archive == adaptive.archive
        and restored.working_memory == adaptive.working_memory
        and restored.detections == adaptive.detections
    )
    return TemporalWorldResult(
        seed=seed,
        change_index=change_index,
        total_observations=total_observations,
        detection_indices=tuple(
            event.detection_index for event in detections
        ),
        false_alarm_count=len(false_alarms),
        detected_change=first_valid is not None,
        detection_delay=(
            first_valid.detection_index - change_index + 1
            if first_valid is not None
            else None
        ),
        stationary_pre_brier=brier_score(pre, "stationary_probability"),
        adaptive_pre_brier=brier_score(pre, "adaptive_probability"),
        fixed_window_pre_brier=brier_score(
            pre, "fixed_window_probability"
        ),
        oracle_pre_brier=brier_score(pre, "oracle_probability"),
        stationary_post_brier=brier_score(post, "stationary_probability"),
        adaptive_post_brier=brier_score(post, "adaptive_probability"),
        fixed_window_post_brier=brier_score(
            post, "fixed_window_probability"
        ),
        oracle_post_brier=brier_score(post, "oracle_probability"),
        stationary_total_brier=brier_score(
            records, "stationary_probability"
        ),
        adaptive_total_brier=brier_score(records, "adaptive_probability"),
        fixed_window_total_brier=brier_score(
            records, "fixed_window_probability"
        ),
        oracle_total_brier=brier_score(records, "oracle_probability"),
        archive_retained=(
            adaptive.archive == tuple(all_observations)
            and len(adaptive.archive) == total_observations
        ),
        final_working_memory_size=len(adaptive.working_memory),
        snapshot_round_trip_exact=snapshot_exact,
    )


def run_temporal_suite(
    seeds: Iterable[int] = range(8100, 8120),
    *,
    change_index: int = 1001,
    total_observations: int = 2000,
    detector_window_size: int = 64,
    false_alarm_delta: float = 1e-6,
    maximum_working_memory: int = 512,
) -> TemporalSuiteReport:
    normalized_seeds = tuple(int(seed) for seed in seeds)
    if not normalized_seeds:
        raise ValidationError("at least one temporal seed is required")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValidationError("temporal seeds must be unique")
    worlds = tuple(
        run_temporal_world(
            seed,
            change_index=change_index,
            total_observations=total_observations,
            detector_window_size=detector_window_size,
            false_alarm_delta=false_alarm_delta,
            maximum_working_memory=maximum_working_memory,
        )
        for seed in normalized_seeds
    )
    detected = tuple(
        world for world in worlds if world.detection_delay is not None
    )
    if not detected:
        delays = (total_observations,)
    else:
        delays = tuple(
            world.detection_delay
            for world in detected
            if world.detection_delay is not None
        )
    stationary_pre = fmean(world.stationary_pre_brier for world in worlds)
    adaptive_pre = fmean(world.adaptive_pre_brier for world in worlds)
    stationary_post = fmean(world.stationary_post_brier for world in worlds)
    adaptive_post = fmean(world.adaptive_post_brier for world in worlds)
    stationary_total = fmean(
        world.stationary_total_brier for world in worlds
    )
    adaptive_total = fmean(world.adaptive_total_brier for world in worlds)
    worlds_with_false_alarm = sum(
        world.false_alarm_count > 0 for world in worlds
    )
    return TemporalSuiteReport(
        seeds=normalized_seeds,
        worlds=worlds,
        world_count=len(worlds),
        change_index=change_index,
        total_observations_per_world=total_observations,
        detection_rate=len(detected) / len(worlds),
        worlds_with_false_alarm=worlds_with_false_alarm,
        false_alarm_world_rate=worlds_with_false_alarm / len(worlds),
        mean_detection_delay=fmean(delays),
        median_detection_delay=float(median(delays)),
        maximum_detection_delay=max(delays),
        stationary_pre_brier=stationary_pre,
        adaptive_pre_brier=adaptive_pre,
        fixed_window_pre_brier=fmean(
            world.fixed_window_pre_brier for world in worlds
        ),
        stationary_post_brier=stationary_post,
        adaptive_post_brier=adaptive_post,
        fixed_window_post_brier=fmean(
            world.fixed_window_post_brier for world in worlds
        ),
        oracle_post_brier=fmean(world.oracle_post_brier for world in worlds),
        stationary_total_brier=stationary_total,
        adaptive_total_brier=adaptive_total,
        fixed_window_total_brier=fmean(
            world.fixed_window_total_brier for world in worlds
        ),
        oracle_total_brier=fmean(world.oracle_total_brier for world in worlds),
        post_change_brier_improvement=stationary_post - adaptive_post,
        total_brier_improvement=stationary_total - adaptive_total,
        pre_change_brier_degradation=adaptive_pre - stationary_pre,
        archive_retention_rate=fmean(
            float(world.archive_retained) for world in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(world.snapshot_round_trip_exact) for world in worlds
        ),
        mean_final_working_memory_fraction=fmean(
            world.final_working_memory_size / world.total_observations
            for world in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Each seed defines one prequential stream. Forecasts are recorded "
            "before outcomes; no outcome is replayed into an earlier forecast."
        ),
        limitations=(
            "The shift is single, abrupt, binary, and large.",
            "The detector window and false-alarm parameter are fixed by the experiment.",
            "The adaptive model is not a full ADWIN or CUSUM implementation.",
            "The oracle baseline is told the true change boundary.",
            "The immutable archive is retained in memory, not external durable storage.",
            "The evaluator is local and is not independent E3 evidence.",
            "Success does not imply consciousness, general intelligence, emotion, or personhood.",
        ),
    )


def record_temporal_result(
    kernel: DarwinKernelV50,
    report: TemporalSuiteReport,
    *,
    minimum_post_brier_improvement: float = 0.10,
) -> ObservationResult:
    if not math.isfinite(minimum_post_brier_improvement):
        raise ValidationError("minimum_post_brier_improvement must be finite")
    goal = kernel.create_goal(
        session_id=f"temporal-lab:{report.seeds[0]}:{report.seeds[-1]}",
        description=(
            "Adaptive temporal memory improves post-change probability forecasts"
        ),
        evidence_source=LOCAL_TEMPORAL_EVALUATOR,
        condition=ComparisonCondition(
            "post_change_brier_improvement",
            ComparisonOperator.GREATER_THAN_OR_EQUAL,
            minimum_post_brier_improvement,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-prequential-regime-change-adaptation",
        parameters={
            "seeds": list(report.seeds),
            "change_index": report.change_index,
            "total_observations_per_world": (
                report.total_observations_per_world
            ),
            "world_count": report.world_count,
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_TEMPORAL_EVALUATOR,
        metrics={
            "detection_rate": report.detection_rate,
            "false_alarm_world_rate": report.false_alarm_world_rate,
            "maximum_detection_delay": report.maximum_detection_delay,
            "stationary_post_brier": report.stationary_post_brier,
            "adaptive_post_brier": report.adaptive_post_brier,
            "post_change_brier_improvement": (
                report.post_change_brier_improvement
            ),
            "total_brier_improvement": report.total_brier_improvement,
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
        },
    )


def report_with_post_improvement(
    report: TemporalSuiteReport,
    value: float,
) -> TemporalSuiteReport:
    return replace(report, post_change_brier_improvement=value)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Darwin H50-L4 temporal adaptation benchmark."
    )
    parser.add_argument(
        "--seeds",
        type=_parse_seeds,
        default=tuple(range(8100, 8120)),
    )
    parser.add_argument("--change-index", type=int, default=1001)
    parser.add_argument("--total-observations", type=int, default=2000)
    parser.add_argument("--detector-window", type=int, default=64)
    parser.add_argument("--false-alarm-delta", type=float, default=1e-6)
    parser.add_argument("--maximum-working-memory", type=int, default=512)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    report = run_temporal_suite(
        args.seeds,
        change_index=args.change_index,
        total_observations=args.total_observations,
        detector_window_size=args.detector_window,
        false_alarm_delta=args.false_alarm_delta,
        maximum_working_memory=args.maximum_working_memory,
    )
    print(
        json.dumps(
            report.to_dict(include_worlds=args.details),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
