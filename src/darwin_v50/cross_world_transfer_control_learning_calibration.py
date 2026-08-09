"""Frozen calibration for source-learned contextual decisions."""

from __future__ import annotations

import math
from typing import Iterable

from .cross_world_transfer_control_evaluation import ControlMetricInterval
from .cross_world_transfer_control_learning_evaluation import (
    TRANSFER_CONTROL_LEARNING_POLICIES,
    bootstrap_transfer_control_learning_metrics,
    run_transfer_control_learning_development,
)
from .cross_world_transfer_lab import require_disjoint_seed_sets
from .models import ValidationError


TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS = tuple(range(33900, 33904))
TRANSFER_CONTROL_LEARNING_CALIBRATION_SEEDS = tuple(range(34000, 34064))
TRANSFER_CONTROL_LEARNING_CALIBRATION_BOOTSTRAP_SEED = 34700
TRANSFER_CONTROL_LEARNING_CALIBRATION_BOOTSTRAP_SAMPLES = 5_000


def _validate_integrity(raw: object) -> dict[str, float]:
    required = {
        "causal_archive_rate",
        "public_identity_rate",
        "candidate_snapshot_rate",
        "shuffled_snapshot_rate",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValidationError("control-learning integrity is invalid")
    result: dict[str, float] = {}
    for key, value in raw.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
        ):
            raise ValidationError("control-learning integrity rate is invalid")
        result[key] = float(value)
    return result


def transfer_control_learning_calibration_criteria(
    metrics: dict[str, ControlMetricInterval],
    *,
    integrity: dict[str, float],
    source_interactions: int,
    target_interactions: int,
) -> dict[str, bool]:
    required_metrics = {
        f"{condition}_{name}"
        for condition in ("related", "unrelated", "adversarial")
        for name in (
            "candidate_reward_improvement",
            "candidate_pseudo_regret_reduction",
            "candidate_preferred_action_rate_improvement",
            "candidate_minus_shuffled_reward",
            "candidate_minus_shuffled_pseudo_regret",
            "candidate_minus_ungated_reward",
            "candidate_minus_ungated_pseudo_regret",
            "candidate_final_source_weight",
        )
    } | {"related_candidate_simultaneous_win_rate"}
    if set(metrics) != required_metrics:
        raise ValidationError("control-learning calibration metrics are incomplete")
    normalized_integrity = _validate_integrity(integrity)
    return {
        "related_reward_low_at_least_1": (
            metrics["related_candidate_reward_improvement"].low >= 1.0
        ),
        "related_regret_low_at_least_0_75": (
            metrics["related_candidate_pseudo_regret_reduction"].low
            >= 0.75
        ),
        "related_preferred_rate_low_at_least_0_05": (
            metrics[
                "related_candidate_preferred_action_rate_improvement"
            ].low
            >= 0.05
        ),
        "related_minus_shuffled_reward_low_at_least_1": (
            metrics["related_candidate_minus_shuffled_reward"].low >= 1.0
        ),
        "related_minus_shuffled_regret_low_at_least_1": (
            metrics[
                "related_candidate_minus_shuffled_pseudo_regret"
            ].low
            >= 1.0
        ),
        "related_simultaneous_wilson_low_at_least_0_65": (
            metrics["related_candidate_simultaneous_win_rate"].low >= 0.65
        ),
        "unrelated_reward_low_at_least_minus_1": (
            metrics["unrelated_candidate_reward_improvement"].low >= -1.0
        ),
        "unrelated_regret_low_at_least_minus_1": (
            metrics["unrelated_candidate_pseudo_regret_reduction"].low
            >= -1.0
        ),
        "adversarial_reward_low_at_least_minus_2": (
            metrics["adversarial_candidate_reward_improvement"].low >= -2.0
        ),
        "adversarial_regret_low_at_least_minus_1_5": (
            metrics["adversarial_candidate_pseudo_regret_reduction"].low
            >= -1.5
        ),
        "unrelated_gate_reward_benefit_low_at_least_2": (
            metrics["unrelated_candidate_minus_ungated_reward"].low >= 2.0
        ),
        "adversarial_gate_reward_benefit_low_at_least_8": (
            metrics["adversarial_candidate_minus_ungated_reward"].low >= 8.0
        ),
        "related_source_weight_low_at_least_0_95": (
            metrics["related_candidate_final_source_weight"].low >= 0.95
        ),
        "unrelated_source_weight_high_at_most_0_10": (
            metrics["unrelated_candidate_final_source_weight"].high <= 0.10
        ),
        "adversarial_source_weight_high_at_most_0_01": (
            metrics["adversarial_candidate_final_source_weight"].high <= 0.01
        ),
        "causal_archive_rate_equals_1": (
            normalized_integrity["causal_archive_rate"] == 1.0
        ),
        "public_identity_rate_equals_1": (
            normalized_integrity["public_identity_rate"] == 1.0
        ),
        "candidate_snapshot_rate_equals_1": (
            normalized_integrity["candidate_snapshot_rate"] == 1.0
        ),
        "shuffled_snapshot_rate_equals_1": (
            normalized_integrity["shuffled_snapshot_rate"] == 1.0
        ),
        "source_interactions_equal_2048": source_interactions == 2048,
        "target_interactions_equal_64": target_interactions == 64,
    }


def run_transfer_control_learning_calibration(
    *,
    seeds: Iterable[int],
    bootstrap_seed: int = TRANSFER_CONTROL_LEARNING_CALIBRATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = (
        TRANSFER_CONTROL_LEARNING_CALIBRATION_BOOTSTRAP_SAMPLES
    ),
) -> dict[str, object]:
    normalized = require_disjoint_seed_sets(calibration=seeds)["calibration"]
    report = run_transfer_control_learning_development(seeds=normalized)
    metrics = bootstrap_transfer_control_learning_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    summary = report.to_summary_dict()
    integrity = _validate_integrity(summary["integrity"])
    source_interactions = report.source_interactions
    target_interactions = report.target_interactions
    criteria = transfer_control_learning_calibration_criteria(
        metrics,
        integrity=integrity,
        source_interactions=source_interactions,
        target_interactions=target_interactions,
    )
    return {
        "status": "calibration-only",
        "capability_claim": False,
        "h50_l15_registered": False,
        "eligible_for_h50_l15_preregistration": all(criteria.values()),
        "seeds": list(normalized),
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_samples": bootstrap_samples,
        "source_interactions": source_interactions,
        "target_interactions": target_interactions,
        "source_to_target_cost_ratio": (
            source_interactions / target_interactions
        ),
        "epsilon": summary["epsilon"],
        "feedback_boundary": summary["feedback_boundary"],
        "metrics": {
            key: value.to_dict() for key, value in metrics.items()
        },
        "criteria": criteria,
        "integrity": integrity,
        "comparison_policies": list(TRANSFER_CONTROL_LEARNING_POLICIES),
        "decision": (
            "eligible_for_confirmatory_preregistration"
            if all(criteria.values())
            else "calibration_failed"
        ),
    }
