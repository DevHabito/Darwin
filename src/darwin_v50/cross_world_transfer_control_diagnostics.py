"""Fresh-seed diagnostics for the refuted contextual decision benchmark."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import fmean
from typing import Callable, Iterable

from .cross_world_transfer_control_evaluation import (
    ControlMetricInterval,
    TransferControlWorldScore,
    evaluate_transfer_control_world,
)
from .cross_world_transfer_lab import require_disjoint_seed_sets
from .models import ValidationError


TRANSFER_CONTROL_AUDIT_SEEDS = tuple(range(31000, 31128))
TRANSFER_CONTROL_AUDIT_TEST_SEEDS = tuple(range(31150, 31154))
TRANSFER_CONTROL_AUDIT_BOOTSTRAP_SEED = 31700
TRANSFER_CONTROL_AUDIT_BOOTSTRAP_SAMPLES = 5_000


_AUDIT_METRICS: dict[
    str, Callable[[TransferControlWorldScore], float]
] = {
    "reward_improvement": lambda item: item.reward_improvement,
    "expected_reward_improvement": (
        lambda item: item.pseudo_regret_reduction
    ),
    "reward_minus_expected": (
        lambda item: item.reward_improvement
        - item.pseudo_regret_reduction
    ),
    "realized_reward_win_rate": (
        lambda item: float(item.reward_improvement > 0.0)
    ),
    "expected_reward_win_rate": (
        lambda item: float(item.pseudo_regret_reduction > 0.0)
    ),
    "simultaneous_win_rate": (
        lambda item: float(
            item.reward_improvement > 0.0
            and item.pseudo_regret_reduction > 0.0
        )
    ),
    "expected_win_realized_nonwin_rate": (
        lambda item: float(
            item.pseudo_regret_reduction > 0.0
            and item.reward_improvement <= 0.0
        )
    ),
    "expected_nonwin_realized_win_rate": (
        lambda item: float(
            item.pseudo_regret_reduction <= 0.0
            and item.reward_improvement > 0.0
        )
    ),
}


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


@dataclass(frozen=True, slots=True)
class TransferControlFailureAudit:
    seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_samples: int
    metrics: dict[str, ControlMetricInterval]
    causal_archive_rate: float
    public_identity_rate: float

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(audit=self.seeds)["audit"]
        if normalized != self.seeds:
            raise ValidationError("control audit seeds are not canonical")
        if set(self.metrics) != set(_AUDIT_METRICS):
            raise ValidationError("control audit metric set is incomplete")
        for value in (self.causal_archive_rate, self.public_identity_rate):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError("control audit integrity is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "diagnostic-only",
            "capability_claim": False,
            "can_promote_experiment_025": False,
            "h50_l15_registered": False,
            "seeds": list(self.seeds),
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "metrics": {
                key: value.to_dict() for key, value in self.metrics.items()
            },
            "integrity": {
                "causal_archive_rate": self.causal_archive_rate,
                "public_identity_rate": self.public_identity_rate,
            },
        }


def run_transfer_control_failure_audit(
    *,
    seeds: Iterable[int],
    bootstrap_seed: int = TRANSFER_CONTROL_AUDIT_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CONTROL_AUDIT_BOOTSTRAP_SAMPLES,
) -> TransferControlFailureAudit:
    normalized = require_disjoint_seed_sets(audit=seeds)["audit"]
    normalized_bootstrap_seed = require_disjoint_seed_sets(
        bootstrap=(bootstrap_seed,)
    )["bootstrap"][0]
    if (
        isinstance(bootstrap_samples, bool)
        or not isinstance(bootstrap_samples, int)
        or bootstrap_samples < 1
    ):
        raise ValidationError("control audit bootstrap samples are invalid")
    worlds = tuple(
        evaluate_transfer_control_world(seed=seed, condition="related")
        for seed in normalized
    )
    rng = random.Random(normalized_bootstrap_seed)
    intervals: dict[str, ControlMetricInterval] = {}
    for name, getter in _AUDIT_METRICS.items():
        values = tuple(getter(item) for item in worlds)
        bootstrap_means = [
            fmean(rng.choice(values) for _ in values)
            for _ in range(bootstrap_samples)
        ]
        intervals[name] = ControlMetricInterval(
            mean=fmean(values),
            low=_quantile(bootstrap_means, 0.025),
            high=_quantile(bootstrap_means, 0.975),
        )
    return TransferControlFailureAudit(
        seeds=normalized,
        bootstrap_seed=normalized_bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        metrics=intervals,
        causal_archive_rate=fmean(
            float(score.causal_archive_valid)
            for item in worlds
            for score in (item.scratch, item.oracle)
        ),
        public_identity_rate=fmean(
            float(score.public_identity_valid)
            for item in worlds
            for score in (item.scratch, item.oracle)
        ),
    )
