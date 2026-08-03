"""Pre-registered H50-L17 online-alignment confirmation evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable

from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .online_alignment_calibration import (
    ONLINE_ALIGNMENT_CALIBRATION_SEEDS,
    ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS,
    OnlineAlignmentCalibrationInterval,
    OnlineAlignmentCalibrationReport,
    _normalize_seeds,
    bootstrap_online_alignment_calibration_metrics,
    online_alignment_calibration_criteria,
)
from .online_alignment_evaluation import (
    ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS,
    ONLINE_ALIGNMENT_ROTATIONS,
    ONLINE_ALIGNMENT_SEGMENTS,
    ONLINE_ALIGNMENT_TEST_SEEDS,
    evaluate_online_alignment_world,
)


ONLINE_ALIGNMENT_CONFIRMATION_TEST_SEEDS = tuple(range(43900, 43904))
ONLINE_ALIGNMENT_CONFIRMATION_FINAL_SEEDS = tuple(range(44000, 44064))
ONLINE_ALIGNMENT_CONFIRMATION_BOOTSTRAP_SEED = 44700
ONLINE_ALIGNMENT_CONFIRMATION_BOOTSTRAP_SAMPLES = 10_000
LOCAL_ONLINE_ALIGNMENT_CONFIRMATION_EVALUATOR = (
    "darwin_v50.online_alignment_confirmation.local_evaluator"
)
ONLINE_ALIGNMENT_CLAIM = (
    "deterministic online action-alignment inference with a frozen "
    "transition prior"
)


def _normalize_final_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    normalized = _normalize_seeds(seeds)
    excluded = set(
        ONLINE_ALIGNMENT_TEST_SEEDS
        + ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS
        + ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS
        + ONLINE_ALIGNMENT_CALIBRATION_SEEDS
        + ONLINE_ALIGNMENT_CONFIRMATION_TEST_SEEDS
    )
    if excluded.intersection(normalized):
        raise ValidationError(
            "online-alignment confirmation seeds overlap an earlier partition"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class OnlineAlignmentConfirmationReport:
    final_seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_samples: int
    report: OnlineAlignmentCalibrationReport
    metrics: dict[str, OnlineAlignmentCalibrationInterval]
    criteria: dict[str, bool]

    def __post_init__(self) -> None:
        if _normalize_final_seeds(self.final_seeds) != self.final_seeds:
            raise ValidationError(
                "online-alignment confirmation seeds are not canonical"
            )
        if self.report.seeds != self.final_seeds:
            raise ValidationError(
                "online-alignment confirmation report seed binding disagrees"
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
                "online-alignment confirmation bootstrap is invalid"
            )
        expected = online_alignment_calibration_criteria(
            self.report,
            self.metrics,
        )
        if self.criteria != expected:
            raise ValidationError(
                "online-alignment confirmation criteria disagree"
            )

    @property
    def passes_regression_criteria(self) -> bool:
        return all(self.criteria.values())

    def to_dict(self) -> dict[str, object]:
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
            "experiment": "039",
            "status": "confirmatory-h50-l17",
            "capability_claim": ONLINE_ALIGNMENT_CLAIM,
            "h50_l17_registered": self.passes_regression_criteria,
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
            "segments": list(ONLINE_ALIGNMENT_SEGMENTS),
            "hidden_rotations": list(ONLINE_ALIGNMENT_ROTATIONS),
            "success_rates": {
                policy: self.report.pooled_rate(f"{policy}_success_rate")
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
                    for world in self.report.worlds
                )
                for index, segment in enumerate(ONLINE_ALIGNMENT_SEGMENTS)
            },
            "frozen_segment_success_rates": {
                segment: fmean(
                    world.frozen_segment_success_rates[index]
                    for world in self.report.worlds
                )
                for index, segment in enumerate(ONLINE_ALIGNMENT_SEGMENTS)
            },
            "mean_candidate_steps": fmean(
                world.candidate_mean_steps for world in self.report.worlds
            ),
            "mean_oracle_steps": fmean(
                world.oracle_mean_steps for world in self.report.worlds
            ),
            "mean_boundary_adaptation_delay": fmean(
                world.boundary_adaptation_delay for world in self.report.worlds
            ),
            "integrity": {
                field: self.report.pooled_rate(field)
                for field in integrity_fields
            },
            "metrics": {
                name: interval.to_dict()
                for name, interval in self.metrics.items()
            },
            "criteria": dict(self.criteria),
            "claim_boundary": (
                "external goals and segment schedule, known closed set of "
                "three deterministic rotations, unique observations, frozen "
                "transition prior, and unauthenticated local evaluator"
            ),
        }


def run_online_alignment_confirmation(
    *,
    final_seeds: Iterable[int],
    bootstrap_seed: int = ONLINE_ALIGNMENT_CONFIRMATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = ONLINE_ALIGNMENT_CONFIRMATION_BOOTSTRAP_SAMPLES,
) -> OnlineAlignmentConfirmationReport:
    normalized = _normalize_final_seeds(final_seeds)
    report = OnlineAlignmentCalibrationReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_online_alignment_world(seed) for seed in normalized
        ),
    )
    metrics = bootstrap_online_alignment_calibration_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    criteria = online_alignment_calibration_criteria(report, metrics)
    return OnlineAlignmentConfirmationReport(
        final_seeds=normalized,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
        report=report,
        metrics=metrics,
        criteria=criteria,
    )


def record_online_alignment_confirmation(
    kernel: DarwinKernelV50,
    report: OnlineAlignmentConfirmationReport,
) -> ObservationResult:
    if not isinstance(report, OnlineAlignmentConfirmationReport):
        raise ValidationError(
            "online-alignment confirmation report is invalid"
        )
    goal = kernel.create_goal(
        session_id=(
            f"online-alignment-confirmation:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Confirm deterministic online action-alignment inference with "
            "a frozen transition prior"
        ),
        evidence_source=LOCAL_ONLINE_ALIGNMENT_CONFIRMATION_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-online-alignment-confirmation",
        parameters={
            "final_seeds": list(report.final_seeds),
            "world_count": len(report.report.worlds),
            "task_count": report.report.task_count,
            "segments": list(ONLINE_ALIGNMENT_SEGMENTS),
            "hidden_rotations": list(ONLINE_ALIGNMENT_ROTATIONS),
            "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_ONLINE_ALIGNMENT_CONFIRMATION_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                report.passes_regression_criteria
            ),
            "candidate_success_rate": report.report.pooled_rate(
                "candidate_success_rate"
            ),
            "boundary_adaptation_delay": fmean(
                world.boundary_adaptation_delay
                for world in report.report.worlds
            ),
            "integration_parity_rate": report.report.pooled_rate(
                "integration_parity_rate"
            ),
            "prior_frozen_rate": report.report.pooled_rate(
                "prior_frozen_rate"
            ),
        },
    )
