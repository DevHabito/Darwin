"""Independent calibration for online latent action-alignment adaptation."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import fmean
from typing import Iterable

from .models import ValidationError
from .online_alignment_evaluation import (
    ONLINE_ALIGNMENT_EXPLORATION_BUDGET,
    ONLINE_ALIGNMENT_ROTATIONS,
    ONLINE_ALIGNMENT_SEGMENTS,
    ONLINE_ALIGNMENT_TASKS_PER_SEGMENT,
    OnlineAlignmentWorldResult,
    evaluate_online_alignment_world,
)
from .predictive_planning_evaluation import (
    PREDICTIVE_MAX_EVALUATION_STEPS,
    PREDICTIVE_TASKS_PER_WORLD,
)


ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS = tuple(range(42900, 42904))
ONLINE_ALIGNMENT_CALIBRATION_SEEDS = tuple(range(43000, 43064))
ONLINE_ALIGNMENT_CALIBRATION_BOOTSTRAP_SEED = 43700
ONLINE_ALIGNMENT_CALIBRATION_BOOTSTRAP_SAMPLES = 5_000


def _normalize_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    result = tuple(seeds)
    if (
        not result
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
        or any(
            isinstance(seed, bool)
            or not isinstance(seed, int)
            or seed < 0
            for seed in result
        )
    ):
        raise ValidationError(
            "online-alignment calibration seeds must be unique increasing "
            "integers"
        )
    return result


@dataclass(frozen=True, slots=True)
class OnlineAlignmentCalibrationReport:
    seeds: tuple[int, ...]
    worlds: tuple[OnlineAlignmentWorldResult, ...]

    def __post_init__(self) -> None:
        if _normalize_seeds(self.seeds) != self.seeds:
            raise ValidationError(
                "online-alignment calibration seeds are not canonical"
            )
        if tuple(world.seed for world in self.worlds) != self.seeds:
            raise ValidationError(
                "online-alignment calibration worlds are unbalanced"
            )

    @property
    def task_count(self) -> int:
        return sum(world.task_count for world in self.worlds)

    def pooled_rate(self, field: str) -> float:
        allowed = {
            name
            for name in OnlineAlignmentWorldResult.__dataclass_fields__
            if name.endswith("_rate")
        }
        if field not in allowed:
            raise ValidationError(
                "online-alignment calibration rate field is invalid"
            )
        return sum(
            getattr(world, field) * world.task_count for world in self.worlds
        ) / self.task_count


@dataclass(frozen=True, slots=True)
class OnlineAlignmentCalibrationInterval:
    mean: float
    low: float
    high: float

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (self.mean, self.low, self.high)
        ) or not self.low <= self.mean <= self.high:
            raise ValidationError(
                "online-alignment calibration interval is invalid"
            )

    def to_dict(self) -> dict[str, float]:
        return {"mean": self.mean, "low": self.low, "high": self.high}


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_online_alignment_calibration_metrics(
    report: OnlineAlignmentCalibrationReport,
    *,
    seed: int = ONLINE_ALIGNMENT_CALIBRATION_BOOTSTRAP_SEED,
    samples: int = ONLINE_ALIGNMENT_CALIBRATION_BOOTSTRAP_SAMPLES,
) -> dict[str, OnlineAlignmentCalibrationInterval]:
    if not isinstance(report, OnlineAlignmentCalibrationReport):
        raise ValidationError(
            "online-alignment calibration report is invalid"
        )
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
        or isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError(
            "online-alignment calibration bootstrap is invalid"
        )
    value_sets = {
        "candidate_success_rate": tuple(
            world.candidate_success_rate for world in report.worlds
        ),
        "candidate_minus_frozen_success_rate": tuple(
            world.candidate_success_rate - world.frozen_success_rate
            for world in report.worlds
        ),
        "candidate_minus_cumulative_success_rate": tuple(
            world.candidate_success_rate - world.cumulative_success_rate
            for world in report.worlds
        ),
        "candidate_minus_shuffled_success_rate": tuple(
            world.candidate_success_rate - world.shuffled_success_rate
            for world in report.worlds
        ),
        "candidate_minus_random_success_rate": tuple(
            world.candidate_success_rate - world.random_success_rate
            for world in report.worlds
        ),
        "candidate_minus_oracle_success_rate": tuple(
            world.candidate_success_rate - world.oracle_success_rate
            for world in report.worlds
        ),
        "recurrent_candidate_minus_frozen_success_rate": tuple(
            world.candidate_segment_success_rates[2]
            - world.frozen_segment_success_rates[2]
            for world in report.worlds
        ),
        "boundary_adaptation_delay": tuple(
            world.boundary_adaptation_delay for world in report.worlds
        ),
        "candidate_step_overhead": tuple(
            world.candidate_mean_steps - world.oracle_mean_steps
            for world in report.worlds
        ),
    }
    rng = random.Random(seed)
    result: dict[str, OnlineAlignmentCalibrationInterval] = {}
    for name, values in value_sets.items():
        means = [
            fmean(rng.choice(values) for _ in values)
            for _ in range(samples)
        ]
        result[name] = OnlineAlignmentCalibrationInterval(
            mean=fmean(values),
            low=_quantile(means, 0.025),
            high=_quantile(means, 0.975),
        )
    return result


def online_alignment_calibration_criteria(
    report: OnlineAlignmentCalibrationReport,
    intervals: dict[str, OnlineAlignmentCalibrationInterval],
) -> dict[str, bool]:
    required = {
        "candidate_success_rate",
        "candidate_minus_frozen_success_rate",
        "candidate_minus_cumulative_success_rate",
        "candidate_minus_shuffled_success_rate",
        "candidate_minus_random_success_rate",
        "candidate_minus_oracle_success_rate",
        "recurrent_candidate_minus_frozen_success_rate",
        "boundary_adaptation_delay",
        "candidate_step_overhead",
    }
    if set(intervals) != required:
        raise ValidationError(
            "online-alignment calibration metrics are incomplete"
        )

    def exact_interval(name: str, value: float) -> bool:
        interval = intervals[name]
        return interval.low == interval.mean == interval.high == value

    integrity_fields = (
        "integration_parity_rate",
        "alignment_identification_rate",
        "post_observation_alignment_rate",
        "tracker_snapshot_rate",
        "kernel_lineage_rate",
        "action_observation_correlation_rate",
        "no_premature_success_rate",
        "archive_retention_rate",
        "prior_frozen_rate",
    )
    return {
        "candidate_success_equals_1": (
            report.pooled_rate("candidate_success_rate") == 1.0
        ),
        "candidate_success_interval_low_equals_1": (
            intervals["candidate_success_rate"].low == 1.0
        ),
        "every_candidate_segment_success_equals_1": all(
            value == 1.0
            for world in report.worlds
            for value in world.candidate_segment_success_rates
        ),
        "oracle_success_equals_1": (
            report.pooled_rate("oracle_success_rate") == 1.0
        ),
        "frozen_success_equals_0_5": (
            report.pooled_rate("frozen_success_rate") == 0.5
        ),
        "frozen_segment_pattern_is_exact": all(
            world.frozen_segment_success_rates == (1.0, 0.0, 1.0, 0.0)
            for world in report.worlds
        ),
        "cumulative_success_equals_0_5": (
            report.pooled_rate("cumulative_success_rate") == 0.5
        ),
        "shuffled_success_equals_0": (
            report.pooled_rate("shuffled_success_rate") == 0.0
        ),
        "candidate_frozen_gap_equals_0_5": exact_interval(
            "candidate_minus_frozen_success_rate", 0.5
        ),
        "candidate_cumulative_gap_equals_0_5": exact_interval(
            "candidate_minus_cumulative_success_rate", 0.5
        ),
        "candidate_shuffled_gap_equals_1": exact_interval(
            "candidate_minus_shuffled_success_rate", 1.0
        ),
        "random_gap_interval_low_at_least_0_90": (
            intervals["candidate_minus_random_success_rate"].low >= 0.90
        ),
        "candidate_matches_oracle_success": exact_interval(
            "candidate_minus_oracle_success_rate", 0.0
        ),
        "recurrent_candidate_matches_frozen": exact_interval(
            "recurrent_candidate_minus_frozen_success_rate", 0.0
        ),
        "boundary_adaptation_delay_equals_1": exact_interval(
            "boundary_adaptation_delay", 1.0
        ),
        "candidate_step_overhead_equals_0_125": exact_interval(
            "candidate_step_overhead", 0.125
        ),
        "all_integrity_rates_equal_1": all(
            report.pooled_rate(field) == 1.0 for field in integrity_fields
        ),
        "world_count_equals_64": len(report.worlds) == 64,
        "task_count_equals_1536": report.task_count == 1_536,
        "schedule_and_budgets_are_frozen": (
            ONLINE_ALIGNMENT_SEGMENTS
            == ("base", "shifted", "recurrent", "novel")
            and ONLINE_ALIGNMENT_ROTATIONS == (0, 1, 0, 2)
            and ONLINE_ALIGNMENT_TASKS_PER_SEGMENT == 6
            and PREDICTIVE_TASKS_PER_WORLD == 24
            and ONLINE_ALIGNMENT_EXPLORATION_BUDGET == 486
            and PREDICTIVE_MAX_EVALUATION_STEPS == 6
        ),
    }


def run_online_alignment_calibration(
    *,
    seeds: Iterable[int],
    bootstrap_seed: int = ONLINE_ALIGNMENT_CALIBRATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = ONLINE_ALIGNMENT_CALIBRATION_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    normalized = _normalize_seeds(seeds)
    report = OnlineAlignmentCalibrationReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_online_alignment_world(seed) for seed in normalized
        ),
    )
    intervals = bootstrap_online_alignment_calibration_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    criteria = online_alignment_calibration_criteria(report, intervals)
    eligible = all(criteria.values())
    integrity_fields = (
        "integration_parity_rate",
        "alignment_identification_rate",
        "post_observation_alignment_rate",
        "tracker_snapshot_rate",
        "kernel_lineage_rate",
        "action_observation_correlation_rate",
        "no_premature_success_rate",
        "archive_retention_rate",
        "prior_frozen_rate",
    )
    return {
        "experiment": "038",
        "status": "calibration-only",
        "capability_claim": False,
        "h50_l17_registered": False,
        "eligible_for_h50_l17_preregistration": eligible,
        "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
        "seeds": list(normalized),
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_samples": bootstrap_samples,
        "world_count": len(report.worlds),
        "task_count": report.task_count,
        "tasks_per_world": PREDICTIVE_TASKS_PER_WORLD,
        "segments": list(ONLINE_ALIGNMENT_SEGMENTS),
        "hidden_rotations": list(ONLINE_ALIGNMENT_ROTATIONS),
        "tasks_per_segment": ONLINE_ALIGNMENT_TASKS_PER_SEGMENT,
        "exploration_interactions_per_world": (
            ONLINE_ALIGNMENT_EXPLORATION_BUDGET
        ),
        "maximum_target_steps": PREDICTIVE_MAX_EVALUATION_STEPS,
        "success_rates": {
            policy: report.pooled_rate(f"{policy}_success_rate")
            for policy in (
                "candidate",
                "frozen",
                "cumulative",
                "shuffled",
                "random",
                "oracle",
            )
        },
        "candidate_segment_success_rates": {
            segment: fmean(
                world.candidate_segment_success_rates[index]
                for world in report.worlds
            )
            for index, segment in enumerate(ONLINE_ALIGNMENT_SEGMENTS)
        },
        "frozen_segment_success_rates": {
            segment: fmean(
                world.frozen_segment_success_rates[index]
                for world in report.worlds
            )
            for index, segment in enumerate(ONLINE_ALIGNMENT_SEGMENTS)
        },
        "mean_candidate_steps": fmean(
            world.candidate_mean_steps for world in report.worlds
        ),
        "mean_oracle_steps": fmean(
            world.oracle_mean_steps for world in report.worlds
        ),
        "mean_boundary_adaptation_delay": fmean(
            world.boundary_adaptation_delay for world in report.worlds
        ),
        "integrity": {
            field: report.pooled_rate(field) for field in integrity_fields
        },
        "metrics": {
            name: interval.to_dict() for name, interval in intervals.items()
        },
        "criteria": criteria,
        "interpretation_boundary": (
            "online inference over a registered deterministic three-value "
            "action alignment; the transition prior remains frozen"
        ),
        "decision": (
            "eligible_for_confirmatory_preregistration"
            if eligible
            else "calibration_failed"
        ),
    }
