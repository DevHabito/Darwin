"""Oracle sensitivity evaluation for the cross-world transfer benchmark.

The oracle receives hidden family parameters and is evaluator-only.  A positive
oracle result validates benchmark sensitivity; it is not evidence that Darwin
can learn or transfer a prior.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import random
from statistics import fmean
from typing import Iterable, Sequence

from .cross_world_transfer_lab import (
    AlignedTransferTask,
    PrequentialTransferModel,
    TransferFamilySpecification,
    TransferPrior,
    TransferWorldSpecification,
    balanced_transfer_schedule,
    require_disjoint_seed_sets,
)
from .models import ValidationError


TRANSFER_DEVELOPMENT_SEEDS = tuple(range(27000, 27032))
TRANSFER_VALIDATION_SEEDS = tuple(range(27100, 27132))
TRANSFER_TEST_SEEDS = tuple(range(27200, 27208))
TRANSFER_EARLY_CYCLES = 4
TRANSFER_BOOTSTRAP_SAMPLES = 2_000
TRANSFER_DEVELOPMENT_BOOTSTRAP_SEED = 27800
TRANSFER_VALIDATION_BOOTSTRAP_SEED = 27801
TRANSFER_TEST_BOOTSTRAP_SEED = 27802

SOURCE_FAMILY_XOR_MASK = 0x1A793
UNRELATED_FAMILY_XOR_MASK = 0x62C5D
OPPOSED_FAMILY_XOR_MASK = 0x4E18B
WORLD_XOR_MASK = 0x293F7
OUTCOME_XOR_MASK = 0x7B245
SCHEDULE_XOR_MASK = 0x35D9F

TRANSFER_CONDITIONS = ("related", "unrelated", "adversarial")


def _validate_condition(value: object) -> str:
    if not isinstance(value, str) or value not in TRANSFER_CONDITIONS:
        raise ValidationError("transfer condition is invalid")
    return value


def _binary_log_loss(probability: float, outcome: bool) -> float:
    bounded = min(max(probability, 1e-12), 1.0 - 1e-12)
    return -math.log(bounded if outcome else 1.0 - bounded)


def _binary_brier(probability: float, outcome: bool) -> float:
    return (probability - float(outcome)) ** 2


@dataclass(frozen=True, slots=True)
class TransferWorldScore:
    seed: int
    condition: str
    interactions: int
    scratch_log_loss: float
    transfer_log_loss: float
    scratch_brier: float
    transfer_brier: float

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("score seed is invalid")
        _validate_condition(self.condition)
        if (
            isinstance(self.interactions, bool)
            or not isinstance(self.interactions, int)
            or self.interactions < 1
        ):
            raise ValidationError("score interaction count is invalid")
        for field, value in (
            ("scratch log loss", self.scratch_log_loss),
            ("transfer log loss", self.transfer_log_loss),
            ("scratch Brier", self.scratch_brier),
            ("transfer Brier", self.transfer_brier),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValidationError(f"{field} is invalid")

    @property
    def log_loss_improvement(self) -> float:
        return self.scratch_log_loss - self.transfer_log_loss

    @property
    def brier_improvement(self) -> float:
        return self.scratch_brier - self.transfer_brier

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "condition": self.condition,
            "interactions": self.interactions,
            "scratch_log_loss": self.scratch_log_loss,
            "transfer_log_loss": self.transfer_log_loss,
            "log_loss_improvement": self.log_loss_improvement,
            "scratch_brier": self.scratch_brier,
            "transfer_brier": self.transfer_brier,
            "brier_improvement": self.brier_improvement,
        }


@dataclass(frozen=True, slots=True)
class PairedInterval:
    mean: float
    low: float
    high: float

    def __post_init__(self) -> None:
        for value in (self.mean, self.low, self.high):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValidationError("paired interval is invalid")
        if self.low > self.mean or self.mean > self.high:
            raise ValidationError("paired interval is unordered")

    def to_dict(self) -> dict[str, float]:
        return {"mean": self.mean, "low": self.low, "high": self.high}


@dataclass(frozen=True, slots=True)
class TransferConditionReport:
    condition: str
    worlds: tuple[TransferWorldScore, ...]
    log_loss_improvement: PairedInterval
    brier_improvement: PairedInterval

    def __post_init__(self) -> None:
        _validate_condition(self.condition)
        if not self.worlds or any(
            item.condition != self.condition for item in self.worlds
        ):
            raise ValidationError("condition worlds are invalid")

    @property
    def win_rate(self) -> float:
        return fmean(
            item.log_loss_improvement > 0.0 for item in self.worlds
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "condition": self.condition,
            "world_count": len(self.worlds),
            "log_loss_improvement": self.log_loss_improvement.to_dict(),
            "brier_improvement": self.brier_improvement.to_dict(),
            "log_loss_win_rate": self.win_rate,
            "worlds": [item.to_dict() for item in self.worlds],
        }


@dataclass(frozen=True, slots=True)
class TransferBenchmarkReport:
    seeds: tuple[int, ...]
    cycles: int
    bootstrap_seed: int
    bootstrap_samples: int
    conditions: tuple[TransferConditionReport, ...]

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(report=self.seeds)["report"]
        if normalized != self.seeds:
            raise ValidationError("report seeds are not canonical")
        if (
            isinstance(self.cycles, bool)
            or not isinstance(self.cycles, int)
            or self.cycles < 1
        ):
            raise ValidationError("report cycles are invalid")
        if (
            isinstance(self.bootstrap_seed, bool)
            or not isinstance(self.bootstrap_seed, int)
            or self.bootstrap_seed < 0
        ):
            raise ValidationError("report bootstrap seed is invalid")
        if (
            isinstance(self.bootstrap_samples, bool)
            or not isinstance(self.bootstrap_samples, int)
            or self.bootstrap_samples < 100
        ):
            raise ValidationError("report bootstrap samples are invalid")
        if tuple(item.condition for item in self.conditions) != (
            TRANSFER_CONDITIONS
        ):
            raise ValidationError("report conditions are not canonical")

    def condition(self, name: str) -> TransferConditionReport:
        validated = _validate_condition(name)
        return next(
            item for item in self.conditions if item.condition == validated
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "benchmark-sensitivity-only",
            "capability_claim": False,
            "h50_l14_registered": False,
            "seeds": list(self.seeds),
            "cycles": self.cycles,
            "interactions_per_world": (
                self.conditions[0].worlds[0].interactions
            ),
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "conditions": [item.to_dict() for item in self.conditions],
        }


def _target_family(
    *,
    source: TransferFamilySpecification,
    seed: int,
    condition: str,
) -> TransferFamilySpecification:
    validated = _validate_condition(condition)
    if validated == "related":
        return source
    if validated == "unrelated":
        return TransferFamilySpecification.from_seed(
            seed ^ UNRELATED_FAMILY_XOR_MASK
        )
    return source.opposed(seed=seed ^ OPPOSED_FAMILY_XOR_MASK)


def evaluate_transfer_world(
    *, seed: int, condition: str, cycles: int = TRANSFER_EARLY_CYCLES
) -> TransferWorldScore:
    normalized = require_disjoint_seed_sets(world=(seed,))["world"]
    validated_seed = normalized[0]
    validated_condition = _validate_condition(condition)
    source = TransferFamilySpecification.from_seed(
        validated_seed ^ SOURCE_FAMILY_XOR_MASK
    )
    target_family = _target_family(
        source=source,
        seed=validated_seed,
        condition=validated_condition,
    )
    specification = TransferWorldSpecification.from_family(
        target_family,
        world_seed=validated_seed ^ WORLD_XOR_MASK,
    )
    task = AlignedTransferTask(
        specification,
        outcome_seed=validated_seed ^ OUTCOME_XOR_MASK,
    )
    scratch = PrequentialTransferModel(
        world_id=specification.world_id,
        prior=TransferPrior.scratch(),
    )
    transfer = PrequentialTransferModel(
        world_id=specification.world_id,
        prior=TransferPrior.oracle(source),
    )
    scratch_log_losses: list[float] = []
    transfer_log_losses: list[float] = []
    scratch_briers: list[float] = []
    transfer_briers: list[float] = []
    schedule = balanced_transfer_schedule(
        cycles=cycles,
        seed=validated_seed ^ SCHEDULE_XOR_MASK,
    )
    for context, action in schedule:
        scratch_forecast = scratch.forecast(context, action)
        transfer_forecast = transfer.forecast(context, action)
        observation = task.act(context, action)
        for probability, outcome in (
            (
                scratch_forecast.transition_probability,
                observation.next_observation,
            ),
            (scratch_forecast.reward_probability, observation.reward),
        ):
            scratch_log_losses.append(_binary_log_loss(probability, outcome))
            scratch_briers.append(_binary_brier(probability, outcome))
        for probability, outcome in (
            (
                transfer_forecast.transition_probability,
                observation.next_observation,
            ),
            (transfer_forecast.reward_probability, observation.reward),
        ):
            transfer_log_losses.append(_binary_log_loss(probability, outcome))
            transfer_briers.append(_binary_brier(probability, outcome))
        scratch.observe(observation)
        transfer.observe(observation)
    return TransferWorldScore(
        seed=validated_seed,
        condition=validated_condition,
        interactions=len(schedule),
        scratch_log_loss=fmean(scratch_log_losses),
        transfer_log_loss=fmean(transfer_log_losses),
        scratch_brier=fmean(scratch_briers),
        transfer_brier=fmean(transfer_briers),
    )


def paired_bootstrap_interval(
    values: Sequence[float], *, seed: int, samples: int
) -> PairedInterval:
    items = tuple(float(value) for value in values)
    if not items or any(not math.isfinite(value) for value in items):
        raise ValidationError("bootstrap values are invalid")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError("bootstrap seed is invalid")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 100:
        raise ValidationError("bootstrap sample count is invalid")
    rng = random.Random(seed)
    means = sorted(
        fmean(items[rng.randrange(len(items))] for _ in items)
        for _ in range(samples)
    )
    low_index = int(0.025 * samples)
    high_index = min(samples - 1, int(0.975 * samples))
    mean = fmean(items)
    low = min(mean, means[low_index])
    high = max(mean, means[high_index])
    return PairedInterval(mean=mean, low=low, high=high)


def run_transfer_benchmark(
    *,
    seeds: Iterable[int],
    cycles: int = TRANSFER_EARLY_CYCLES,
    bootstrap_seed: int,
    bootstrap_samples: int = TRANSFER_BOOTSTRAP_SAMPLES,
) -> TransferBenchmarkReport:
    normalized = require_disjoint_seed_sets(evaluation=seeds)["evaluation"]
    reports: list[TransferConditionReport] = []
    for condition_index, condition in enumerate(TRANSFER_CONDITIONS):
        worlds = tuple(
            evaluate_transfer_world(
                seed=seed,
                condition=condition,
                cycles=cycles,
            )
            for seed in normalized
        )
        reports.append(
            TransferConditionReport(
                condition=condition,
                worlds=worlds,
                log_loss_improvement=paired_bootstrap_interval(
                    [item.log_loss_improvement for item in worlds],
                    seed=bootstrap_seed + 2 * condition_index,
                    samples=bootstrap_samples,
                ),
                brier_improvement=paired_bootstrap_interval(
                    [item.brier_improvement for item in worlds],
                    seed=bootstrap_seed + 2 * condition_index + 1,
                    samples=bootstrap_samples,
                ),
            )
        )
    return TransferBenchmarkReport(
        seeds=normalized,
        cycles=cycles,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        conditions=tuple(reports),
    )


def _parse_seeds(raw: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in raw.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("seeds must be integers") from error
    if not result:
        raise argparse.ArgumentTypeError("provide at least one seed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the evaluator-only transfer sensitivity benchmark."
    )
    parser.add_argument("--seeds", type=_parse_seeds, required=True)
    parser.add_argument("--cycles", type=int, default=TRANSFER_EARLY_CYCLES)
    parser.add_argument("--bootstrap-seed", type=int, required=True)
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=TRANSFER_BOOTSTRAP_SAMPLES,
    )
    arguments = parser.parse_args()
    report = run_transfer_benchmark(
        seeds=arguments.seeds,
        cycles=arguments.cycles,
        bootstrap_seed=arguments.bootstrap_seed,
        bootstrap_samples=arguments.bootstrap_samples,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
