"""Pre-registered H50-L16 integrated-cycle confirmation evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable

from .integrated_cycle_calibration import (
    INTEGRATED_CALIBRATION_SEEDS,
    INTEGRATED_CALIBRATION_TEST_SEEDS,
    INTEGRATED_RESTART_MODES,
    IntegratedCalibrationInterval,
    IntegratedCalibrationReport,
    _normalize_seeds,
    bootstrap_integrated_calibration_metrics,
    evaluate_integrated_calibration_world,
    integrated_calibration_criteria,
)
from .integrated_cycle_evaluation import (
    INTEGRATED_CYCLE_DEVELOPMENT_SEEDS,
    INTEGRATED_CYCLE_TEST_SEEDS,
)
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)


INTEGRATED_CONFIRMATION_TEST_SEEDS = tuple(range(40900, 40904))
INTEGRATED_CONFIRMATION_FINAL_SEEDS = tuple(range(41000, 41064))
INTEGRATED_CONFIRMATION_BOOTSTRAP_SEED = 41700
INTEGRATED_CONFIRMATION_BOOTSTRAP_SAMPLES = 10_000
LOCAL_INTEGRATED_CONFIRMATION_EVALUATOR = (
    "darwin_v50.integrated_cycle_confirmation.local_evaluator"
)
INTEGRATED_CYCLE_CLAIM = (
    "deterministic externally-goaled integrated planning with local "
    "replay-based recovery"
)


def _normalize_final_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    normalized = _normalize_seeds(seeds)
    excluded = set(
        INTEGRATED_CYCLE_TEST_SEEDS
        + INTEGRATED_CYCLE_DEVELOPMENT_SEEDS
        + INTEGRATED_CALIBRATION_TEST_SEEDS
        + INTEGRATED_CALIBRATION_SEEDS
        + INTEGRATED_CONFIRMATION_TEST_SEEDS
    )
    if excluded.intersection(normalized):
        raise ValidationError(
            "integrated confirmation seeds overlap an earlier partition"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class IntegratedCycleConfirmationReport:
    final_seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_samples: int
    report: IntegratedCalibrationReport
    metrics: dict[str, IntegratedCalibrationInterval]
    criteria: dict[str, bool]

    def __post_init__(self) -> None:
        if _normalize_final_seeds(self.final_seeds) != self.final_seeds:
            raise ValidationError(
                "integrated confirmation seeds are not canonical"
            )
        if self.report.seeds != self.final_seeds:
            raise ValidationError(
                "integrated confirmation report seed binding disagrees"
            )
        if (
            isinstance(self.bootstrap_seed, bool)
            or not isinstance(self.bootstrap_seed, int)
            or self.bootstrap_seed < 0
            or isinstance(self.bootstrap_samples, bool)
            or not isinstance(self.bootstrap_samples, int)
            or self.bootstrap_samples < 1
        ):
            raise ValidationError(
                "integrated confirmation bootstrap is invalid"
            )
        expected = integrated_calibration_criteria(
            self.report,
            self.metrics,
        )
        if self.criteria != expected:
            raise ValidationError(
                "integrated confirmation criteria disagree"
            )

    @property
    def passes_regression_criteria(self) -> bool:
        return all(self.criteria.values())

    def to_dict(self) -> dict[str, object]:
        integrity_fields = (
            "restart_action_exact_rate",
            "prediction_match_rate",
            "model_frozen_rate",
            "recovery_executed_rate",
            "checkpoint_exact_rate",
            "kernel_restart_exact_rate",
            "environment_replay_exact_rate",
            "pending_decision_preserved_rate",
            "kernel_cycle_binding_exact_rate",
            "kernel_lineage_rate",
            "action_observation_correlation_rate",
            "no_premature_success_rate",
        )
        return {
            "experiment": "036",
            "status": "confirmatory-h50-l16",
            "capability_claim": INTEGRATED_CYCLE_CLAIM,
            "h50_l16_registered": self.passes_regression_criteria,
            "decision": (
                "passed_locally"
                if self.passes_regression_criteria
                else "refuted"
            ),
            "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
            "final_seeds": list(self.final_seeds),
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "world_count": len(self.report.worlds),
            "task_count": self.report.task_count,
            "restart_modes": list(INTEGRATED_RESTART_MODES),
            "success_rates": {
                name: self.report.pooled_rate(f"{name}_success_rate")
                for name in (
                    "candidate",
                    "uninterrupted",
                    "rotated",
                    "random",
                    "oracle",
                )
            },
            "restart_mode_success_rates": {
                mode: fmean(
                    world.restart_mode_success_rates[index]
                    for world in self.report.worlds
                )
                for index, mode in enumerate(INTEGRATED_RESTART_MODES)
            },
            "integrity": {
                field: self.report.pooled_rate(field)
                for field in integrity_fields
            },
            "mean_candidate_steps": fmean(
                world.mean_candidate_steps for world in self.report.worlds
            ),
            "metrics": {
                name: interval.to_dict()
                for name, interval in self.metrics.items()
            },
            "criteria": dict(self.criteria),
            "claim_boundary": (
                "external goals, frozen learned model, deterministic symbolic "
                "world, local SQLite kernel, and evaluator-known environment "
                "reconstruction by replay"
            ),
        }


def run_integrated_cycle_confirmation(
    *,
    final_seeds: Iterable[int],
    bootstrap_seed: int = INTEGRATED_CONFIRMATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = INTEGRATED_CONFIRMATION_BOOTSTRAP_SAMPLES,
) -> IntegratedCycleConfirmationReport:
    normalized = _normalize_final_seeds(final_seeds)
    report = IntegratedCalibrationReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_integrated_calibration_world(seed)
            for seed in normalized
        ),
    )
    metrics = bootstrap_integrated_calibration_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    criteria = integrated_calibration_criteria(report, metrics)
    return IntegratedCycleConfirmationReport(
        final_seeds=normalized,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        report=report,
        metrics=metrics,
        criteria=criteria,
    )


def record_integrated_cycle_confirmation(
    kernel: DarwinKernelV50,
    report: IntegratedCycleConfirmationReport,
) -> ObservationResult:
    if not isinstance(report, IntegratedCycleConfirmationReport):
        raise ValidationError("integrated confirmation report is invalid")
    goal = kernel.create_goal(
        session_id=(
            f"integrated-confirmation:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Confirm deterministic externally-goaled integrated planning "
            "with local replay-based recovery"
        ),
        evidence_source=LOCAL_INTEGRATED_CONFIRMATION_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-integrated-cycle-confirmation",
        parameters={
            "final_seeds": list(report.final_seeds),
            "world_count": len(report.report.worlds),
            "task_count": report.report.task_count,
            "restart_modes": list(INTEGRATED_RESTART_MODES),
            "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_INTEGRATED_CONFIRMATION_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                report.passes_regression_criteria
            ),
            "candidate_success_rate": report.report.pooled_rate(
                "candidate_success_rate"
            ),
            "restart_action_exact_rate": report.report.pooled_rate(
                "restart_action_exact_rate"
            ),
            "environment_replay_exact_rate": report.report.pooled_rate(
                "environment_replay_exact_rate"
            ),
            "kernel_lineage_rate": report.report.pooled_rate(
                "kernel_lineage_rate"
            ),
        },
    )
