"""Fresh replication of the refuted contextual decision benchmark.

The policy, task family, horizon, and thresholds remain unchanged.  This
version increases the validation cohort and uses a Wilson interval for the
binary simultaneous-win rate.  It cannot retroactively change Experiment 025.
"""

from __future__ import annotations

import math
from typing import Iterable

from .cross_world_transfer_control_evaluation import (
    TRANSFER_CONTROL_CONTEXT_CYCLES,
    TRANSFER_CONTROL_EPSILON,
    ContextualPolicyScore,
    ControlMetricInterval,
    TransferControlSensitivityReport,
    bootstrap_transfer_control_metrics,
    run_transfer_control_sensitivity,
    transfer_control_sensitivity_criteria,
)
from .cross_world_transfer_lab import require_disjoint_seed_sets
from .models import ValidationError


TRANSFER_CONTROL_REPLICATION_TEST_SEEDS = tuple(range(31800, 31804))
TRANSFER_CONTROL_REPLICATION_VALIDATION_SEEDS = tuple(range(32000, 32128))
TRANSFER_CONTROL_REPLICATION_BOOTSTRAP_SEED = 32700
TRANSFER_CONTROL_REPLICATION_BOOTSTRAP_SAMPLES = 5_000
WILSON_95_Z = 1.959963984540054


def wilson_rate_interval(*, successes: int, total: int) -> ControlMetricInterval:
    if (
        isinstance(successes, bool)
        or not isinstance(successes, int)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 1
        or not 0 <= successes <= total
    ):
        raise ValidationError("Wilson rate inputs are invalid")
    proportion = successes / total
    z_squared = WILSON_95_Z**2
    denominator = 1.0 + z_squared / total
    center = (proportion + z_squared / (2.0 * total)) / denominator
    radius = (
        WILSON_95_Z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z_squared / (4.0 * total**2)
        )
        / denominator
    )
    return ControlMetricInterval(
        mean=proportion,
        low=max(0.0, center - radius),
        high=min(1.0, center + radius),
    )


def _integrity_rate(
    report: TransferControlSensitivityReport,
    field: str,
) -> float:
    if field not in ("causal_archive_valid", "public_identity_valid"):
        raise ValidationError("replication integrity field is invalid")
    scores: tuple[ContextualPolicyScore, ...] = tuple(
        score
        for world in report.worlds
        for score in (world.scratch, world.oracle)
    )
    return sum(float(getattr(score, field)) for score in scores) / len(scores)


def transfer_control_replication_record(
    report: TransferControlSensitivityReport,
    *,
    bootstrap_seed: int = TRANSFER_CONTROL_REPLICATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CONTROL_REPLICATION_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    if not isinstance(report, TransferControlSensitivityReport):
        raise ValidationError("replication report is invalid")
    metrics = bootstrap_transfer_control_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    related = tuple(
        item for item in report.worlds if item.condition == "related"
    )
    simultaneous_successes = sum(
        item.reward_improvement > 0.0
        and item.pseudo_regret_reduction > 0.0
        for item in related
    )
    metrics["related_simultaneous_win_rate"] = wilson_rate_interval(
        successes=simultaneous_successes,
        total=len(related),
    )
    causal_archive_rate = _integrity_rate(
        report, "causal_archive_valid"
    )
    public_identity_rate = _integrity_rate(
        report, "public_identity_valid"
    )
    criteria = transfer_control_sensitivity_criteria(
        metrics,
        causal_archive_rate=causal_archive_rate,
        public_identity_rate=public_identity_rate,
    )
    return {
        "status": "control-benchmark-replication-v2",
        "capability_claim": False,
        "can_reverse_experiment_025": False,
        "h50_l15_registered": False,
        "seeds": list(report.seeds),
        "epsilon": report.epsilon,
        "context_cycles": report.context_cycles,
        "interactions_per_target": report.context_cycles * 8,
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_samples": bootstrap_samples,
        "interval_methods": {
            "continuous_means": "paired_percentile_bootstrap_over_worlds",
            "related_simultaneous_win_rate": "wilson_score_95_percent",
        },
        "metrics": {
            key: value.to_dict() for key, value in metrics.items()
        },
        "integrity": {
            "causal_archive_rate": causal_archive_rate,
            "public_identity_rate": public_identity_rate,
        },
        "criteria": criteria,
        "decision": (
            "passed_benchmark_sensitivity"
            if all(criteria.values())
            else "refuted_benchmark_replication"
        ),
    }


def run_transfer_control_replication(
    *, seeds: Iterable[int]
) -> dict[str, object]:
    normalized = require_disjoint_seed_sets(replication=seeds)[
        "replication"
    ]
    report = run_transfer_control_sensitivity(
        seeds=normalized,
        epsilon=TRANSFER_CONTROL_EPSILON,
        context_cycles=TRANSFER_CONTROL_CONTEXT_CYCLES,
    )
    return transfer_control_replication_record(report)
