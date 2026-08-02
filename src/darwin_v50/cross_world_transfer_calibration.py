"""Independent calibration for the frozen source-learned transfer candidate.

Calibration determines whether a confirmatory H50-L14 registration is
scientifically eligible.  It is not itself a capability experiment.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import fmean
from typing import Callable, Iterable

from .cross_world_transfer_evaluation import TRANSFER_CONDITIONS
from .cross_world_transfer_learning_evaluation import (
    TransferDevelopmentConfiguration,
    TransferLearningWorldScore,
    evaluate_learning_world,
)
from .cross_world_transfer_lab import require_disjoint_seed_sets
from .models import ValidationError


TRANSFER_CALIBRATION_SEEDS = tuple(range(27500, 27532))
TRANSFER_CALIBRATION_TEST_SEEDS = tuple(range(27600, 27608))
TRANSFER_CALIBRATION_BOOTSTRAP_SEED = 28000
TRANSFER_CALIBRATION_BOOTSTRAP_SAMPLES = 5_000
TRANSFER_SELECTED_CONFIGURATION = TransferDevelopmentConfiguration(
    source_tasks=16,
    source_cycles=8,
    initial_source_weight=0.5,
)

MINIMUM_RELATED_IMPROVEMENT = 0.12
MINIMUM_RELATED_VS_SHUFFLED = 0.10
MINIMUM_ORACLE_GAP_CLOSURE = 0.80
MINIMUM_INCOMPATIBLE_IMPROVEMENT = -0.01
MINIMUM_RELATED_SOURCE_WEIGHT = 0.95
MAXIMUM_UNRELATED_SOURCE_WEIGHT = 0.20
MAXIMUM_ADVERSARIAL_SOURCE_WEIGHT = 0.05
MINIMUM_SIMULTANEOUS_WIN_RATE = 0.75


@dataclass(frozen=True, slots=True)
class CalibrationInterval:
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
            raise ValidationError("calibration interval is invalid")

    def to_dict(self) -> dict[str, float]:
        return {"mean": self.mean, "low": self.low, "high": self.high}


@dataclass(frozen=True, slots=True)
class TransferCalibrationReport:
    seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_samples: int
    metrics: dict[str, CalibrationInterval]
    criteria: dict[str, bool]

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(calibration=self.seeds)[
            "calibration"
        ]
        if normalized != self.seeds:
            raise ValidationError("calibration seeds are not canonical")
        if set(self.metrics) != {
            "related_gated_improvement",
            "related_candidate_minus_shuffled",
            "related_oracle_gap_closure",
            "unrelated_gated_improvement",
            "adversarial_gated_improvement",
            "related_final_source_weight",
            "unrelated_final_source_weight",
            "adversarial_final_source_weight",
            "related_simultaneous_win_rate",
        }:
            raise ValidationError("calibration metrics are incomplete")
        if len(self.criteria) != 9 or any(
            not isinstance(value, bool) for value in self.criteria.values()
        ):
            raise ValidationError("calibration criteria are invalid")

    @property
    def eligible_for_h50_l14_registration(self) -> bool:
        return all(self.criteria.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "calibration-only",
            "capability_claim": False,
            "h50_l14_registered": False,
            "eligible_for_h50_l14_registration": (
                self.eligible_for_h50_l14_registration
            ),
            "seeds": list(self.seeds),
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "selected_configuration": (
                TRANSFER_SELECTED_CONFIGURATION.to_dict()
            ),
            "metrics": {
                key: value.to_dict() for key, value in self.metrics.items()
            },
            "criteria": dict(self.criteria),
        }


def _metric_functions() -> dict[
    str, Callable[[dict[str, tuple[TransferLearningWorldScore, ...]]], float]
]:
    def improvement(
        rows: dict[str, tuple[TransferLearningWorldScore, ...]],
        condition: str,
    ) -> float:
        return fmean(
            item.log_loss_improvement("gated") for item in rows[condition]
        )

    return {
        "related_gated_improvement": lambda rows: improvement(
            rows, "related"
        ),
        "related_candidate_minus_shuffled": lambda rows: fmean(
            item.log_loss_improvement("gated")
            - item.log_loss_improvement("shuffled")
            for item in rows["related"]
        ),
        "related_oracle_gap_closure": lambda rows: improvement(
            rows, "related"
        )
        / fmean(
            item.log_loss_improvement("oracle")
            for item in rows["related"]
        ),
        "unrelated_gated_improvement": lambda rows: improvement(
            rows, "unrelated"
        ),
        "adversarial_gated_improvement": lambda rows: improvement(
            rows, "adversarial"
        ),
        "related_final_source_weight": lambda rows: fmean(
            item.final_source_weight for item in rows["related"]
        ),
        "unrelated_final_source_weight": lambda rows: fmean(
            item.final_source_weight for item in rows["unrelated"]
        ),
        "adversarial_final_source_weight": lambda rows: fmean(
            item.final_source_weight for item in rows["adversarial"]
        ),
        "related_simultaneous_win_rate": lambda rows: fmean(
            item.log_loss_improvement("gated") > 0.0
            and item.log_loss_improvement("gated")
            > item.log_loss_improvement("shuffled")
            for item in rows["related"]
        ),
    }


def _rows_by_condition(
    worlds: Iterable[TransferLearningWorldScore],
) -> dict[str, tuple[TransferLearningWorldScore, ...]]:
    items = tuple(worlds)
    result = {
        condition: tuple(
            item for item in items if item.condition == condition
        )
        for condition in TRANSFER_CONDITIONS
    }
    lengths = {len(rows) for rows in result.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) < 1:
        raise ValidationError("calibration conditions are unbalanced")
    return result


def _bootstrap_intervals(
    rows: dict[str, tuple[TransferLearningWorldScore, ...]],
    *,
    seed: int,
    samples: int,
) -> dict[str, CalibrationInterval]:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError("calibration bootstrap seed is invalid")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 100:
        raise ValidationError("calibration bootstrap samples are invalid")
    count = len(rows["related"])
    functions = _metric_functions()
    points = {name: function(rows) for name, function in functions.items()}
    draws = {name: [] for name in functions}
    rng = random.Random(seed)
    for _ in range(samples):
        indices = [rng.randrange(count) for _ in range(count)]
        sampled = {
            condition: tuple(condition_rows[index] for index in indices)
            for condition, condition_rows in rows.items()
        }
        for name, function in functions.items():
            value = function(sampled)
            if not math.isfinite(value):
                raise ValidationError("calibration bootstrap is non-finite")
            draws[name].append(value)
    result: dict[str, CalibrationInterval] = {}
    for name, values in draws.items():
        ordered = sorted(values)
        low = min(points[name], ordered[int(0.025 * samples)])
        high = max(
            points[name],
            ordered[min(samples - 1, int(0.975 * samples))],
        )
        result[name] = CalibrationInterval(
            mean=points[name], low=low, high=high
        )
    return result


def run_transfer_calibration(
    *,
    seeds: Iterable[int],
    bootstrap_seed: int = TRANSFER_CALIBRATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CALIBRATION_BOOTSTRAP_SAMPLES,
) -> TransferCalibrationReport:
    normalized = require_disjoint_seed_sets(calibration=seeds)["calibration"]
    worlds = tuple(
        evaluate_learning_world(
            seed=seed,
            condition=condition,
            configuration=TRANSFER_SELECTED_CONFIGURATION,
        )
        for seed in normalized
        for condition in TRANSFER_CONDITIONS
    )
    metrics = _bootstrap_intervals(
        _rows_by_condition(worlds),
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    criteria = {
        "related_improvement_low_at_least_0_12": (
            metrics["related_gated_improvement"].low
            >= MINIMUM_RELATED_IMPROVEMENT
        ),
        "related_vs_shuffled_low_at_least_0_10": (
            metrics["related_candidate_minus_shuffled"].low
            >= MINIMUM_RELATED_VS_SHUFFLED
        ),
        "oracle_gap_closure_low_at_least_0_80": (
            metrics["related_oracle_gap_closure"].low
            >= MINIMUM_ORACLE_GAP_CLOSURE
        ),
        "unrelated_improvement_low_at_least_minus_0_01": (
            metrics["unrelated_gated_improvement"].low
            >= MINIMUM_INCOMPATIBLE_IMPROVEMENT
        ),
        "adversarial_improvement_low_at_least_minus_0_01": (
            metrics["adversarial_gated_improvement"].low
            >= MINIMUM_INCOMPATIBLE_IMPROVEMENT
        ),
        "related_source_weight_low_at_least_0_95": (
            metrics["related_final_source_weight"].low
            >= MINIMUM_RELATED_SOURCE_WEIGHT
        ),
        "unrelated_source_weight_high_at_most_0_20": (
            metrics["unrelated_final_source_weight"].high
            <= MAXIMUM_UNRELATED_SOURCE_WEIGHT
        ),
        "adversarial_source_weight_high_at_most_0_05": (
            metrics["adversarial_final_source_weight"].high
            <= MAXIMUM_ADVERSARIAL_SOURCE_WEIGHT
        ),
        "related_simultaneous_win_rate_low_at_least_0_75": (
            metrics["related_simultaneous_win_rate"].low
            >= MINIMUM_SIMULTANEOUS_WIN_RATE
        ),
    }
    return TransferCalibrationReport(
        seeds=normalized,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        metrics=metrics,
        criteria=criteria,
    )
