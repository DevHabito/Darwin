"""Pre-registered H50-L15 confirmatory evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .cross_world_transfer_control_evaluation import ControlMetricInterval
from .cross_world_transfer_control_learning_calibration import (
    _validate_integrity,
    transfer_control_learning_calibration_criteria,
)
from .cross_world_transfer_control_learning_evaluation import (
    bootstrap_transfer_control_learning_metrics,
    run_transfer_control_learning_development,
)
from .cross_world_transfer_lab import require_disjoint_seed_sets
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)


TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS = tuple(range(34900, 34904))
TRANSFER_CONTROL_LEARNING_FINAL_SEEDS = tuple(range(35000, 35128))
TRANSFER_CONTROL_LEARNING_FINAL_BOOTSTRAP_SEED = 35700
TRANSFER_CONTROL_LEARNING_FINAL_BOOTSTRAP_SAMPLES = 10_000
LOCAL_CONTEXTUAL_TRANSFER_EVALUATOR = (
    "darwin_v50.cross_world_transfer_control_learning_confirmation.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class TransferControlLearningConfirmationReport:
    final_seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_samples: int
    metrics: dict[str, ControlMetricInterval]
    criteria: dict[str, bool]
    integrity: dict[str, float]
    source_interactions: int
    target_interactions: int
    feedback_boundary: str

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(final=self.final_seeds)["final"]
        if normalized != self.final_seeds:
            raise ValidationError("contextual confirmation seeds are not canonical")
        if len(self.criteria) != 21 or any(
            not isinstance(value, bool) for value in self.criteria.values()
        ):
            raise ValidationError("contextual confirmation criteria are invalid")
        normalized_integrity = _validate_integrity(self.integrity)
        expected = transfer_control_learning_calibration_criteria(
            self.metrics,
            integrity=normalized_integrity,
            source_interactions=self.source_interactions,
            target_interactions=self.target_interactions,
        )
        if self.criteria != expected:
            raise ValidationError("contextual confirmation criteria disagree")
        if not isinstance(self.feedback_boundary, str) or not self.feedback_boundary:
            raise ValidationError("contextual confirmation boundary is invalid")

    @property
    def passes_regression_criteria(self) -> bool:
        return all(self.criteria.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "confirmatory-h50-l15",
            "capability_claim": (
                "known-alignment contextual decisions with auxiliary "
                "transition feedback in a synthetic tabular family"
            ),
            "claim_limits_negative_transfer_but_does_not_eliminate_it": True,
            "h50_l15_registered": True,
            "decision": (
                "passed_locally"
                if self.passes_regression_criteria
                else "refuted"
            ),
            "evidence_level": "E1_LOCAL_AUTOMATED_EVALUATOR",
            "final_seeds": list(self.final_seeds),
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "source_interactions": self.source_interactions,
            "target_interactions": self.target_interactions,
            "source_to_target_cost_ratio": (
                self.source_interactions / self.target_interactions
            ),
            "feedback_boundary": self.feedback_boundary,
            "metrics": {
                key: value.to_dict() for key, value in self.metrics.items()
            },
            "criteria": dict(self.criteria),
            "integrity": dict(self.integrity),
        }


def run_transfer_control_learning_confirmation(
    *,
    final_seeds: Iterable[int],
    bootstrap_seed: int = TRANSFER_CONTROL_LEARNING_FINAL_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CONTROL_LEARNING_FINAL_BOOTSTRAP_SAMPLES,
) -> TransferControlLearningConfirmationReport:
    normalized = require_disjoint_seed_sets(final=final_seeds)["final"]
    report = run_transfer_control_learning_development(seeds=normalized)
    metrics = bootstrap_transfer_control_learning_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    summary = report.to_summary_dict()
    integrity = _validate_integrity(summary["integrity"])
    criteria = transfer_control_learning_calibration_criteria(
        metrics,
        integrity=integrity,
        source_interactions=report.source_interactions,
        target_interactions=report.target_interactions,
    )
    return TransferControlLearningConfirmationReport(
        final_seeds=normalized,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        metrics=metrics,
        criteria=criteria,
        integrity=integrity,
        source_interactions=report.source_interactions,
        target_interactions=report.target_interactions,
        feedback_boundary=summary["feedback_boundary"],
    )


def record_transfer_control_learning_confirmation(
    kernel: DarwinKernelV50,
    report: TransferControlLearningConfirmationReport,
) -> ObservationResult:
    if not isinstance(report, TransferControlLearningConfirmationReport):
        raise ValidationError("contextual confirmation report is invalid")
    goal = kernel.create_goal(
        session_id=(
            f"contextual-transfer:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "A source-learned prior improves related contextual decisions "
            "and the gate bounds declared mismatch losses"
        ),
        evidence_source=LOCAL_CONTEXTUAL_TRANSFER_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-known-alignment-contextual-transfer",
        parameters={
            "final_seeds": list(report.final_seeds),
            "source_interactions": report.source_interactions,
            "target_interactions": report.target_interactions,
            "feedback_boundary": report.feedback_boundary,
            "evidence_level": "E1_LOCAL_AUTOMATED_EVALUATOR",
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_CONTEXTUAL_TRANSFER_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                report.passes_regression_criteria
            ),
            "related_reward_improvement_low": report.metrics[
                "related_candidate_reward_improvement"
            ].low,
            "related_minus_shuffled_reward_low": report.metrics[
                "related_candidate_minus_shuffled_reward"
            ].low,
            "unrelated_reward_improvement_low": report.metrics[
                "unrelated_candidate_reward_improvement"
            ].low,
            "adversarial_reward_improvement_low": report.metrics[
                "adversarial_candidate_reward_improvement"
            ].low,
            "causal_archive_rate": report.integrity[
                "causal_archive_rate"
            ],
            "candidate_snapshot_rate": report.integrity[
                "candidate_snapshot_rate"
            ],
        },
    )
