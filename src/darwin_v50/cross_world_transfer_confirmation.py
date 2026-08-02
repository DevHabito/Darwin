"""Pre-registered confirmatory evaluator for Darwin H50-L14."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .cross_world_transfer_calibration import (
    CalibrationInterval,
    TRANSFER_SELECTED_CONFIGURATION,
    _bootstrap_intervals,
    _rows_by_condition,
    transfer_calibration_criteria,
)
from .cross_world_transfer_evaluation import TRANSFER_CONDITIONS
from .cross_world_transfer_learning_evaluation import evaluate_learning_world
from .cross_world_transfer_lab import require_disjoint_seed_sets
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)


TRANSFER_CONFIRMATION_FINAL_SEEDS = tuple(range(28500, 28600))
TRANSFER_CONFIRMATION_TEST_SEEDS = tuple(range(28600, 28604))
TRANSFER_CONFIRMATION_BOOTSTRAP_SEED = 29100
TRANSFER_CONFIRMATION_BOOTSTRAP_SAMPLES = 10_000
LOCAL_CROSS_WORLD_TRANSFER_EVALUATOR = (
    "darwin_v50.cross_world_transfer_confirmation.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class TransferConfirmationReport:
    final_seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_samples: int
    metrics: dict[str, CalibrationInterval]
    criteria: dict[str, bool]
    causal_archive_rate: float
    snapshot_round_trip_rate: float
    public_identity_rate: float

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(final=self.final_seeds)["final"]
        if normalized != self.final_seeds:
            raise ValidationError("confirmation seeds are not canonical")
        if len(self.criteria) != 12 or any(
            not isinstance(value, bool) for value in self.criteria.values()
        ):
            raise ValidationError("confirmation criteria are invalid")
        for value in (
            self.causal_archive_rate,
            self.snapshot_round_trip_rate,
            self.public_identity_rate,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError("confirmation integrity rate is invalid")

    @property
    def passes_regression_criteria(self) -> bool:
        return all(self.criteria.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "confirmatory-h50-l14",
            "capability_claim": (
                "known-alignment predictive prior transfer in a synthetic "
                "tabular family"
            ),
            "h50_l14_registered": True,
            "decision": (
                "passed_locally"
                if self.passes_regression_criteria
                else "refuted"
            ),
            "evidence_level": "E1_LOCAL_AUTOMATED_EVALUATOR",
            "final_seeds": list(self.final_seeds),
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "selected_configuration": (
                TRANSFER_SELECTED_CONFIGURATION.to_dict()
            ),
            "metrics": {
                key: value.to_dict() for key, value in self.metrics.items()
            },
            "integrity": {
                "causal_archive_rate": self.causal_archive_rate,
                "snapshot_round_trip_rate": self.snapshot_round_trip_rate,
                "public_identity_rate": self.public_identity_rate,
            },
            "criteria": dict(self.criteria),
        }


def run_transfer_confirmation(
    *,
    final_seeds: Iterable[int],
    bootstrap_seed: int = TRANSFER_CONFIRMATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CONFIRMATION_BOOTSTRAP_SAMPLES,
) -> TransferConfirmationReport:
    normalized = require_disjoint_seed_sets(final=final_seeds)["final"]
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
    causal_archive_rate = sum(
        item.causal_archive_valid for item in worlds
    ) / len(worlds)
    snapshot_round_trip_rate = sum(
        item.snapshot_round_trip_valid for item in worlds
    ) / len(worlds)
    public_identity_rate = sum(
        item.public_identity_valid for item in worlds
    ) / len(worlds)
    criteria = {
        **transfer_calibration_criteria(metrics),
        "causal_archive_rate_equals_1": causal_archive_rate == 1.0,
        "snapshot_round_trip_rate_equals_1": (
            snapshot_round_trip_rate == 1.0
        ),
        "public_identity_rate_equals_1": public_identity_rate == 1.0,
    }
    return TransferConfirmationReport(
        final_seeds=normalized,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        metrics=metrics,
        criteria=criteria,
        causal_archive_rate=causal_archive_rate,
        snapshot_round_trip_rate=snapshot_round_trip_rate,
        public_identity_rate=public_identity_rate,
    )


def record_transfer_confirmation(
    kernel: DarwinKernelV50,
    report: TransferConfirmationReport,
) -> ObservationResult:
    goal = kernel.create_goal(
        session_id=(
            f"cross-world-transfer:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "A source-learned prior improves held-out related prediction "
            "while the gate limits incompatible transfer"
        ),
        evidence_source=LOCAL_CROSS_WORLD_TRANSFER_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-known-alignment-predictive-transfer",
        parameters={
            "final_seeds": list(report.final_seeds),
            "source_tasks": TRANSFER_SELECTED_CONFIGURATION.source_tasks,
            "source_cycles": TRANSFER_SELECTED_CONFIGURATION.source_cycles,
            "initial_source_weight": (
                TRANSFER_SELECTED_CONFIGURATION.initial_source_weight
            ),
            "evidence_level": "E1_LOCAL_AUTOMATED_EVALUATOR",
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_CROSS_WORLD_TRANSFER_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                report.passes_regression_criteria
            ),
            "related_gated_improvement_low": (
                report.metrics["related_gated_improvement"].low
            ),
            "related_candidate_minus_shuffled_low": (
                report.metrics["related_candidate_minus_shuffled"].low
            ),
            "related_oracle_gap_closure_low": (
                report.metrics["related_oracle_gap_closure"].low
            ),
            "unrelated_gated_improvement_low": (
                report.metrics["unrelated_gated_improvement"].low
            ),
            "adversarial_gated_improvement_low": (
                report.metrics["adversarial_gated_improvement"].low
            ),
            "causal_archive_rate": report.causal_archive_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
            "public_identity_rate": report.public_identity_rate,
        },
    )
