"""Paired failure audit for compatibility-feedback channels.

The audit compares the H50-L15 transition-and-reward gate with the Experiment
031 reward-only gate on identical fresh synthetic worlds.  It is diagnostic:
it cannot register or promote a capability hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import fmean
from typing import Iterable

from .cross_world_transfer_calibration import TRANSFER_SELECTED_CONFIGURATION
from .cross_world_transfer_control_evaluation import (
    TRANSFER_CONTROL_CONTEXT_CYCLES,
    TRANSFER_CONTROL_EPSILON,
    TRANSFER_CONTROL_POLICY_XOR_MASK,
    TRANSFER_CONTROL_SCHEDULE_XOR_MASK,
    ContextualPolicyScore,
    ControlMetricInterval,
    balanced_transfer_context_schedule,
    score_contextual_policy,
)
from .cross_world_transfer_evaluation import (
    OUTCOME_XOR_MASK,
    SOURCE_FAMILY_XOR_MASK,
    TRANSFER_CONDITIONS,
    WORLD_XOR_MASK,
)
from .cross_world_transfer_lab import (
    AlignedTransferTask,
    PrequentialTransferModel,
    TransferFamilySpecification,
    TransferObservation,
    TransferPrior,
    TransferWorldSpecification,
    require_disjoint_seed_sets,
)
from .cross_world_transfer_learning import (
    GatedTransferModel,
    collect_source_family_evidence,
    learn_transfer_prior,
)
from .cross_world_transfer_learning_evaluation import (
    TRANSFER_SOURCE_BASE_XOR_MASK,
    target_family_for_condition,
)
from .models import ValidationError


FEEDBACK_AUDIT_TEST_SEEDS = tuple(range(36900, 36904))
FEEDBACK_AUDIT_SEEDS = tuple(range(37000, 37064))
FEEDBACK_AUDIT_BOOTSTRAP_SEED = 37700
FEEDBACK_AUDIT_BOOTSTRAP_SAMPLES = 5_000
FEEDBACK_AUDIT_RELATED_COST_TOLERANCE = -0.5


def _validate_probability(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValidationError(f"{field} is invalid")
    return float(value)


@dataclass(frozen=True, slots=True)
class FeedbackAuditWorldScore:
    seed: int
    condition: str
    scratch: ContextualPolicyScore
    dual_channel: ContextualPolicyScore
    reward_only: ContextualPolicyScore
    dual_channel_final_source_weight: float
    reward_only_final_source_weight: float
    fixed_archive_dual_channel_weight: float
    fixed_archive_reward_only_weight: float
    dual_channel_snapshot_valid: bool
    reward_only_snapshot_valid: bool
    reward_only_replay_valid: bool
    source_interactions: int

    def __post_init__(self) -> None:
        require_disjoint_seed_sets(world=(self.seed,))
        if self.condition not in TRANSFER_CONDITIONS:
            raise ValidationError("feedback-audit condition is invalid")
        for field, value in (
            (
                "dual-channel final source weight",
                self.dual_channel_final_source_weight,
            ),
            (
                "reward-only final source weight",
                self.reward_only_final_source_weight,
            ),
            (
                "fixed-archive dual-channel weight",
                self.fixed_archive_dual_channel_weight,
            ),
            (
                "fixed-archive reward-only weight",
                self.fixed_archive_reward_only_weight,
            ),
        ):
            _validate_probability(value, field)
        if any(
            not isinstance(value, bool)
            for value in (
                self.dual_channel_snapshot_valid,
                self.reward_only_snapshot_valid,
                self.reward_only_replay_valid,
            )
        ):
            raise ValidationError("feedback-audit integrity flag is invalid")
        if (
            isinstance(self.source_interactions, bool)
            or not isinstance(self.source_interactions, int)
            or self.source_interactions < 1
        ):
            raise ValidationError("feedback-audit source cost is invalid")

    def dual_minus_reward_only(self, metric: str) -> float:
        if metric == "reward":
            return float(
                self.dual_channel.cumulative_reward
                - self.reward_only.cumulative_reward
            )
        if metric == "pseudo_regret":
            return (
                self.reward_only.pseudo_regret
                - self.dual_channel.pseudo_regret
            )
        if metric == "preferred_action_rate":
            return (
                self.dual_channel.family_preferred_action_rate
                - self.reward_only.family_preferred_action_rate
            )
        raise ValidationError("feedback-audit metric is invalid")

    def reward_improvement_over_scratch(self, policy: str) -> float:
        if policy not in ("dual_channel", "reward_only"):
            raise ValidationError("feedback-audit policy is invalid")
        return float(
            getattr(self, policy).cumulative_reward
            - self.scratch.cumulative_reward
        )

    @property
    def behavioral_weight_delta(self) -> float:
        return (
            self.reward_only_final_source_weight
            - self.dual_channel_final_source_weight
        )

    @property
    def fixed_archive_weight_delta(self) -> float:
        return (
            self.fixed_archive_reward_only_weight
            - self.fixed_archive_dual_channel_weight
        )


@dataclass(frozen=True, slots=True)
class FeedbackAuditReport:
    seeds: tuple[int, ...]
    worlds: tuple[FeedbackAuditWorldScore, ...]

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(audit=self.seeds)["audit"]
        if normalized != self.seeds:
            raise ValidationError("feedback-audit seeds are not canonical")
        if any(
            sum(item.condition == condition for item in self.worlds)
            != len(self.seeds)
            for condition in TRANSFER_CONDITIONS
        ):
            raise ValidationError("feedback-audit worlds are unbalanced")

    def condition_rows(
        self, condition: str
    ) -> tuple[FeedbackAuditWorldScore, ...]:
        if condition not in TRANSFER_CONDITIONS:
            raise ValidationError("feedback-audit condition is invalid")
        return tuple(
            item for item in self.worlds if item.condition == condition
        )

    @property
    def source_interactions(self) -> int:
        return self.worlds[0].source_interactions

    @property
    def target_interactions(self) -> int:
        return TRANSFER_CONTROL_CONTEXT_CYCLES * 8

    def integrity_rates(self) -> dict[str, float]:
        scores = tuple(
            score
            for item in self.worlds
            for score in (
                item.scratch,
                item.dual_channel,
                item.reward_only,
            )
        )
        return {
            "causal_archive_rate": fmean(
                float(score.causal_archive_valid) for score in scores
            ),
            "public_identity_rate": fmean(
                float(score.public_identity_valid) for score in scores
            ),
            "dual_channel_snapshot_rate": fmean(
                float(item.dual_channel_snapshot_valid)
                for item in self.worlds
            ),
            "reward_only_snapshot_rate": fmean(
                float(item.reward_only_snapshot_valid)
                for item in self.worlds
            ),
            "reward_only_replay_rate": fmean(
                float(item.reward_only_replay_valid)
                for item in self.worlds
            ),
        }

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "experiment": "032",
            "status": "registered-failure-audit",
            "capability_claim": False,
            "baseline_h50_l15_status": "passed_locally",
            "experiment_031_status": "not_eligible_for_calibration",
            "seeds": list(self.seeds),
            "source_interactions": self.source_interactions,
            "target_interactions": self.target_interactions,
            "source_to_target_cost_ratio": (
                self.source_interactions / self.target_interactions
            ),
            "epsilon": TRANSFER_CONTROL_EPSILON,
            "paired_boundary": (
                "identical source family, learned prior, target world, context "
                "schedule, action-randomness stream, and outcome-randomness "
                "stream; only compatibility feedback mode differs"
            ),
            "integrity": self.integrity_rates(),
            "mean_dual_minus_reward_only": {
                condition: {
                    metric: fmean(
                        item.dual_minus_reward_only(metric)
                        for item in self.condition_rows(condition)
                    )
                    for metric in (
                        "reward",
                        "pseudo_regret",
                        "preferred_action_rate",
                    )
                }
                for condition in TRANSFER_CONDITIONS
            },
            "mean_reward_improvement_over_scratch": {
                condition: {
                    policy: fmean(
                        item.reward_improvement_over_scratch(policy)
                        for item in self.condition_rows(condition)
                    )
                    for policy in ("dual_channel", "reward_only")
                }
                for condition in TRANSFER_CONDITIONS
            },
            "mean_source_weight_delta": {
                condition: {
                    "behavioral_reward_only_minus_dual": fmean(
                        item.behavioral_weight_delta
                        for item in self.condition_rows(condition)
                    ),
                    "fixed_archive_reward_only_minus_dual": fmean(
                        item.fixed_archive_weight_delta
                        for item in self.condition_rows(condition)
                    ),
                }
                for condition in TRANSFER_CONDITIONS
            },
        }


def _replay_gate_weight(
    *,
    source_prior: TransferPrior,
    initial_source_weight: float,
    archive: tuple[TransferObservation, ...],
    compatibility_feedback: str,
) -> tuple[float, tuple[TransferObservation, ...]]:
    if not archive:
        raise ValidationError("feedback-audit replay archive is empty")
    model = GatedTransferModel(
        world_id=archive[0].world_id,
        source_prior=source_prior,
        initial_source_weight=initial_source_weight,
        compatibility_feedback=compatibility_feedback,
    )
    for item in archive:
        model.forecast(item.context, item.action)
        model.observe(item)
    return model.source_weight, model.archive


def evaluate_feedback_audit_world(
    *, seed: int, condition: str
) -> FeedbackAuditWorldScore:
    normalized_seed = require_disjoint_seed_sets(world=(seed,))["world"][0]
    if condition not in TRANSFER_CONDITIONS:
        raise ValidationError("feedback-audit condition is invalid")
    source_family = TransferFamilySpecification.from_seed(
        normalized_seed ^ SOURCE_FAMILY_XOR_MASK
    )
    configuration = TRANSFER_SELECTED_CONFIGURATION
    source_evidence = collect_source_family_evidence(
        source_family,
        base_seed=normalized_seed ^ TRANSFER_SOURCE_BASE_XOR_MASK,
        task_count=configuration.source_tasks,
        cycles=configuration.source_cycles,
    )
    learned_prior = learn_transfer_prior(source_evidence)
    target_family = target_family_for_condition(
        source=source_family,
        seed=normalized_seed,
        condition=condition,
    )
    specification = TransferWorldSpecification.from_family(
        target_family,
        world_seed=normalized_seed ^ WORLD_XOR_MASK,
    )
    contexts = balanced_transfer_context_schedule(
        cycles=TRANSFER_CONTROL_CONTEXT_CYCLES,
        seed=normalized_seed ^ TRANSFER_CONTROL_SCHEDULE_XOR_MASK,
    )
    models = {
        "scratch": PrequentialTransferModel(
            world_id="feedback-audit:scratch",
            prior=TransferPrior.scratch(),
        ),
        "dual_channel": GatedTransferModel(
            world_id="feedback-audit:dual-channel",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
        ),
        "reward_only": GatedTransferModel(
            world_id="feedback-audit:reward-only",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
            compatibility_feedback="reward_only",
        ),
    }
    scores: dict[str, ContextualPolicyScore] = {}
    for name, model in models.items():
        scores[name] = score_contextual_policy(
            model=model,
            task=AlignedTransferTask(
                specification,
                outcome_seed=normalized_seed ^ OUTCOME_XOR_MASK,
                public_world_id=model.world_id,
            ),
            contexts=contexts,
            family=target_family,
            specification=specification,
            policy_seed=(
                normalized_seed ^ TRANSFER_CONTROL_POLICY_XOR_MASK
            ),
            epsilon=TRANSFER_CONTROL_EPSILON,
        )
    dual_channel = models["dual_channel"]
    reward_only = models["reward_only"]
    if not isinstance(dual_channel, GatedTransferModel):
        raise ValidationError("dual-channel audit model is invalid")
    if not isinstance(reward_only, GatedTransferModel):
        raise ValidationError("reward-only audit model is invalid")
    dual_snapshot = dual_channel.to_snapshot()
    reward_snapshot = reward_only.to_snapshot()
    fixed_dual_weight, fixed_dual_archive = _replay_gate_weight(
        source_prior=learned_prior,
        initial_source_weight=configuration.initial_source_weight,
        archive=reward_only.archive,
        compatibility_feedback="transition_and_reward",
    )
    fixed_reward_weight, fixed_reward_archive = _replay_gate_weight(
        source_prior=learned_prior,
        initial_source_weight=configuration.initial_source_weight,
        archive=reward_only.archive,
        compatibility_feedback="reward_only",
    )
    return FeedbackAuditWorldScore(
        seed=normalized_seed,
        condition=condition,
        scratch=scores["scratch"],
        dual_channel=scores["dual_channel"],
        reward_only=scores["reward_only"],
        dual_channel_final_source_weight=dual_channel.source_weight,
        reward_only_final_source_weight=reward_only.source_weight,
        fixed_archive_dual_channel_weight=fixed_dual_weight,
        fixed_archive_reward_only_weight=fixed_reward_weight,
        dual_channel_snapshot_valid=(
            GatedTransferModel.from_snapshot(dual_snapshot).to_snapshot()
            == dual_snapshot
        ),
        reward_only_snapshot_valid=(
            GatedTransferModel.from_snapshot(reward_snapshot).to_snapshot()
            == reward_snapshot
        ),
        reward_only_replay_valid=(
            fixed_reward_weight == reward_only.source_weight
            and fixed_reward_archive == reward_only.archive
            and fixed_dual_archive == reward_only.archive
        ),
        source_interactions=configuration.source_interactions,
    )


def run_feedback_audit(*, seeds: Iterable[int]) -> FeedbackAuditReport:
    normalized = require_disjoint_seed_sets(audit=seeds)["audit"]
    return FeedbackAuditReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_feedback_audit_world(
                seed=seed,
                condition=condition,
            )
            for seed in normalized
            for condition in TRANSFER_CONDITIONS
        ),
    )


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_feedback_audit_metrics(
    report: FeedbackAuditReport,
    *,
    seed: int = FEEDBACK_AUDIT_BOOTSTRAP_SEED,
    samples: int = FEEDBACK_AUDIT_BOOTSTRAP_SAMPLES,
) -> dict[str, ControlMetricInterval]:
    if not isinstance(report, FeedbackAuditReport):
        raise ValidationError("feedback-audit report is invalid")
    normalized_seed = require_disjoint_seed_sets(bootstrap=(seed,))[
        "bootstrap"
    ][0]
    if (
        isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("feedback-audit bootstrap is invalid")
    rng = random.Random(normalized_seed)
    intervals: dict[str, ControlMetricInterval] = {}
    for condition in TRANSFER_CONDITIONS:
        rows = report.condition_rows(condition)
        value_sets = {
            "dual_minus_reward_only_reward": tuple(
                item.dual_minus_reward_only("reward") for item in rows
            ),
            "dual_minus_reward_only_pseudo_regret": tuple(
                item.dual_minus_reward_only("pseudo_regret")
                for item in rows
            ),
            "dual_minus_reward_only_preferred_action_rate": tuple(
                item.dual_minus_reward_only("preferred_action_rate")
                for item in rows
            ),
            "behavioral_reward_only_minus_dual_weight": tuple(
                item.behavioral_weight_delta for item in rows
            ),
            "fixed_archive_reward_only_minus_dual_weight": tuple(
                item.fixed_archive_weight_delta for item in rows
            ),
            "dual_channel_reward_improvement_over_scratch": tuple(
                item.reward_improvement_over_scratch("dual_channel")
                for item in rows
            ),
            "reward_only_reward_improvement_over_scratch": tuple(
                item.reward_improvement_over_scratch("reward_only")
                for item in rows
            ),
        }
        for name, values in value_sets.items():
            bootstrap_means = [
                fmean(rng.choice(values) for _ in values)
                for _ in range(samples)
            ]
            intervals[f"{condition}_{name}"] = ControlMetricInterval(
                mean=fmean(values),
                low=_quantile(bootstrap_means, 0.025),
                high=_quantile(bootstrap_means, 0.975),
            )
    return intervals


def feedback_audit_criteria(
    report: FeedbackAuditReport,
    intervals: dict[str, ControlMetricInterval],
) -> dict[str, bool]:
    if not isinstance(report, FeedbackAuditReport):
        raise ValidationError("feedback-audit report is invalid")
    required = {
        f"{condition}_{metric}"
        for condition in TRANSFER_CONDITIONS
        for metric in (
            "dual_minus_reward_only_reward",
            "dual_minus_reward_only_pseudo_regret",
            "fixed_archive_reward_only_minus_dual_weight",
        )
    }
    if not required.issubset(intervals):
        raise ValidationError("feedback-audit intervals are incomplete")
    integrity = report.integrity_rates()
    return {
        "unrelated_reward_benefit_low_above_zero": intervals[
            "unrelated_dual_minus_reward_only_reward"
        ].low
        > 0.0,
        "unrelated_regret_benefit_low_above_zero": intervals[
            "unrelated_dual_minus_reward_only_pseudo_regret"
        ].low
        > 0.0,
        "adversarial_reward_benefit_low_above_zero": intervals[
            "adversarial_dual_minus_reward_only_reward"
        ].low
        > 0.0,
        "adversarial_regret_benefit_low_above_zero": intervals[
            "adversarial_dual_minus_reward_only_pseudo_regret"
        ].low
        > 0.0,
        "related_reward_cost_low_at_least_minus_point_five": intervals[
            "related_dual_minus_reward_only_reward"
        ].low
        >= FEEDBACK_AUDIT_RELATED_COST_TOLERANCE,
        "related_regret_cost_low_at_least_minus_point_five": intervals[
            "related_dual_minus_reward_only_pseudo_regret"
        ].low
        >= FEEDBACK_AUDIT_RELATED_COST_TOLERANCE,
        "unrelated_fixed_archive_weight_delta_low_above_zero": intervals[
            "unrelated_fixed_archive_reward_only_minus_dual_weight"
        ].low
        > 0.0,
        "adversarial_fixed_archive_weight_delta_low_above_zero": intervals[
            "adversarial_fixed_archive_reward_only_minus_dual_weight"
        ].low
        > 0.0,
        **{
            f"{name}_equals_one": value == 1.0
            for name, value in integrity.items()
        },
        "source_interactions_equal_2048": report.source_interactions == 2048,
        "target_interactions_equal_64": report.target_interactions == 64,
    }


def feedback_audit_record(
    report: FeedbackAuditReport,
    *,
    bootstrap_seed: int = FEEDBACK_AUDIT_BOOTSTRAP_SEED,
    bootstrap_samples: int = FEEDBACK_AUDIT_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    intervals = bootstrap_feedback_audit_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    criteria = feedback_audit_criteria(report, intervals)
    result = report.to_summary_dict()
    result["bootstrap_seed"] = bootstrap_seed
    result["bootstrap_samples"] = bootstrap_samples
    result["audit_intervals"] = {
        name: interval.to_dict() for name, interval in intervals.items()
    }
    result["frozen_audit_criteria"] = criteria
    result["all_audit_criteria_pass"] = all(criteria.values())
    result["audit_decision"] = (
        "transition_feedback_benefit_supported"
        if result["all_audit_criteria_pass"]
        else "clean_transition_feedback_benefit_not_supported"
    )
    return result
