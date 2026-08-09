"""Development evaluator for source-learned contextual decisions.

The candidate reuses the frozen H50-L14 source estimator and compatibility
gate.  Actions maximize current reward estimates under the fixed contextual
policy from Experiments 025 and 027.  This module is development-only and
cannot register H50-L15.
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
from .cross_world_transfer_control_replication import wilson_rate_interval
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
    TransferPrior,
    TransferWorldSpecification,
    require_disjoint_seed_sets,
)
from .cross_world_transfer_learning import (
    GatedTransferModel,
    collect_source_family_evidence,
    learn_transfer_prior,
    permuted_transfer_prior,
    pooled_source_prior,
)
from .cross_world_transfer_learning_evaluation import (
    TRANSFER_SOURCE_BASE_XOR_MASK,
    target_family_for_condition,
)
from .models import ValidationError


TRANSFER_CONTROL_LEARNING_TEST_SEEDS = tuple(range(32900, 32904))
TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS = tuple(range(33000, 33032))
TRANSFER_CONTROL_LEARNING_BOOTSTRAP_SEED = 33700
TRANSFER_CONTROL_LEARNING_BOOTSTRAP_SAMPLES = 2_000
TRANSFER_CONTROL_LEARNING_POLICIES = (
    "scratch",
    "candidate",
    "ungated",
    "shuffled",
    "pooled",
    "oracle",
)


@dataclass(frozen=True, slots=True)
class TransferControlLearningWorldScore:
    seed: int
    condition: str
    scratch: ContextualPolicyScore
    candidate: ContextualPolicyScore
    ungated: ContextualPolicyScore
    shuffled: ContextualPolicyScore
    pooled: ContextualPolicyScore
    oracle: ContextualPolicyScore
    candidate_final_source_weight: float
    shuffled_final_source_weight: float
    candidate_snapshot_valid: bool
    shuffled_snapshot_valid: bool
    source_interactions: int

    def __post_init__(self) -> None:
        require_disjoint_seed_sets(world=(self.seed,))
        if self.condition not in TRANSFER_CONDITIONS:
            raise ValidationError("control-learning condition is invalid")
        for value in (
            self.candidate_final_source_weight,
            self.shuffled_final_source_weight,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError("control-learning weight is invalid")
        if not isinstance(self.candidate_snapshot_valid, bool):
            raise ValidationError("candidate snapshot flag is invalid")
        if not isinstance(self.shuffled_snapshot_valid, bool):
            raise ValidationError("shuffled snapshot flag is invalid")
        if (
            isinstance(self.source_interactions, bool)
            or not isinstance(self.source_interactions, int)
            or self.source_interactions < 1
        ):
            raise ValidationError("source interaction cost is invalid")

    def policy_score(self, name: str) -> ContextualPolicyScore:
        if name not in TRANSFER_CONTROL_LEARNING_POLICIES:
            raise ValidationError("control-learning policy is invalid")
        return getattr(self, name)

    def improvement(self, name: str, metric: str) -> float:
        score = self.policy_score(name)
        if metric == "reward":
            return float(
                score.cumulative_reward - self.scratch.cumulative_reward
            )
        if metric == "pseudo_regret":
            return self.scratch.pseudo_regret - score.pseudo_regret
        if metric == "preferred_action_rate":
            return (
                score.family_preferred_action_rate
                - self.scratch.family_preferred_action_rate
            )
        raise ValidationError("control-learning metric is invalid")

    def candidate_minus_shuffled(self, metric: str) -> float:
        return self.candidate_minus_policy("shuffled", metric)

    def candidate_minus_policy(self, policy: str, metric: str) -> float:
        other = self.policy_score(policy)
        if metric == "reward":
            return float(
                self.candidate.cumulative_reward
                - other.cumulative_reward
            )
        if metric == "pseudo_regret":
            return other.pseudo_regret - self.candidate.pseudo_regret
        raise ValidationError("candidate control metric is invalid")


@dataclass(frozen=True, slots=True)
class TransferControlLearningDevelopmentReport:
    seeds: tuple[int, ...]
    worlds: tuple[TransferControlLearningWorldScore, ...]

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(development=self.seeds)[
            "development"
        ]
        if normalized != self.seeds:
            raise ValidationError("control-learning seeds are not canonical")
        if any(
            sum(item.condition == condition for item in self.worlds)
            != len(self.seeds)
            for condition in TRANSFER_CONDITIONS
        ):
            raise ValidationError("control-learning worlds are unbalanced")

    def condition_rows(
        self, condition: str
    ) -> tuple[TransferControlLearningWorldScore, ...]:
        if condition not in TRANSFER_CONDITIONS:
            raise ValidationError("control-learning condition is invalid")
        return tuple(
            item for item in self.worlds if item.condition == condition
        )

    def mean_improvement(
        self, condition: str, policy: str, metric: str
    ) -> float:
        return fmean(
            item.improvement(policy, metric)
            for item in self.condition_rows(condition)
        )

    def mean_candidate_control_delta(
        self, condition: str, metric: str, policy: str = "shuffled"
    ) -> float:
        return fmean(
            item.candidate_minus_policy(policy, metric)
            for item in self.condition_rows(condition)
        )

    def mean_weight(self, condition: str, policy: str) -> float:
        if policy not in ("candidate", "shuffled"):
            raise ValidationError("control-learning weight policy is invalid")
        return fmean(
            getattr(item, f"{policy}_final_source_weight")
            for item in self.condition_rows(condition)
        )

    @property
    def source_interactions(self) -> int:
        return self.worlds[0].source_interactions

    @property
    def target_interactions(self) -> int:
        return TRANSFER_CONTROL_CONTEXT_CYCLES * 8

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "status": "development-only",
            "capability_claim": False,
            "h50_l15_registered": False,
            "feedback_boundary": (
                "actions use reward estimates; the frozen compatibility gate "
                "updates from observed transition and reward outcomes"
            ),
            "seeds": list(self.seeds),
            "source_interactions": self.source_interactions,
            "target_interactions": self.target_interactions,
            "source_to_target_cost_ratio": (
                self.source_interactions / self.target_interactions
            ),
            "epsilon": TRANSFER_CONTROL_EPSILON,
            "mean_improvement_over_scratch": {
                condition: {
                    policy: {
                        metric: self.mean_improvement(
                            condition, policy, metric
                        )
                        for metric in (
                            "reward",
                            "pseudo_regret",
                            "preferred_action_rate",
                        )
                    }
                    for policy in TRANSFER_CONTROL_LEARNING_POLICIES[1:]
                }
                for condition in TRANSFER_CONDITIONS
            },
            "candidate_minus_shuffled": {
                condition: {
                    metric: self.mean_candidate_control_delta(
                        condition, metric
                    )
                    for metric in ("reward", "pseudo_regret")
                }
                for condition in TRANSFER_CONDITIONS
            },
            "candidate_minus_ungated": {
                condition: {
                    metric: self.mean_candidate_control_delta(
                        condition, metric, "ungated"
                    )
                    for metric in ("reward", "pseudo_regret")
                }
                for condition in TRANSFER_CONDITIONS
            },
            "mean_final_source_weight": {
                condition: {
                    policy: self.mean_weight(condition, policy)
                    for policy in ("candidate", "shuffled")
                }
                for condition in TRANSFER_CONDITIONS
            },
            "integrity": {
                "causal_archive_rate": fmean(
                    float(score.causal_archive_valid)
                    for item in self.worlds
                    for score in (
                        item.scratch,
                        item.candidate,
                        item.ungated,
                        item.shuffled,
                        item.pooled,
                        item.oracle,
                    )
                ),
                "public_identity_rate": fmean(
                    float(score.public_identity_valid)
                    for item in self.worlds
                    for score in (
                        item.scratch,
                        item.candidate,
                        item.ungated,
                        item.shuffled,
                        item.pooled,
                        item.oracle,
                    )
                ),
                "candidate_snapshot_rate": fmean(
                    float(item.candidate_snapshot_valid)
                    for item in self.worlds
                ),
                "shuffled_snapshot_rate": fmean(
                    float(item.shuffled_snapshot_valid)
                    for item in self.worlds
                ),
            },
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


def bootstrap_transfer_control_learning_metrics(
    report: TransferControlLearningDevelopmentReport,
    *,
    seed: int = TRANSFER_CONTROL_LEARNING_BOOTSTRAP_SEED,
    samples: int = TRANSFER_CONTROL_LEARNING_BOOTSTRAP_SAMPLES,
) -> dict[str, ControlMetricInterval]:
    if not isinstance(report, TransferControlLearningDevelopmentReport):
        raise ValidationError("control-learning report is invalid")
    normalized_seed = require_disjoint_seed_sets(bootstrap=(seed,))[
        "bootstrap"
    ][0]
    if (
        isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("control-learning bootstrap is invalid")
    rng = random.Random(normalized_seed)
    intervals: dict[str, ControlMetricInterval] = {}
    for condition in TRANSFER_CONDITIONS:
        rows = report.condition_rows(condition)
        value_sets = {
            "candidate_reward_improvement": tuple(
                item.improvement("candidate", "reward") for item in rows
            ),
            "candidate_pseudo_regret_reduction": tuple(
                item.improvement("candidate", "pseudo_regret")
                for item in rows
            ),
            "candidate_preferred_action_rate_improvement": tuple(
                item.improvement("candidate", "preferred_action_rate")
                for item in rows
            ),
            "candidate_minus_shuffled_reward": tuple(
                item.candidate_minus_policy("shuffled", "reward")
                for item in rows
            ),
            "candidate_minus_shuffled_pseudo_regret": tuple(
                item.candidate_minus_policy("shuffled", "pseudo_regret")
                for item in rows
            ),
            "candidate_minus_ungated_reward": tuple(
                item.candidate_minus_policy("ungated", "reward")
                for item in rows
            ),
            "candidate_minus_ungated_pseudo_regret": tuple(
                item.candidate_minus_policy("ungated", "pseudo_regret")
                for item in rows
            ),
            "candidate_final_source_weight": tuple(
                item.candidate_final_source_weight for item in rows
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
        if condition == "related":
            simultaneous = sum(
                item.improvement("candidate", "reward") > 0.0
                and item.improvement("candidate", "pseudo_regret") > 0.0
                for item in rows
            )
            intervals[
                "related_candidate_simultaneous_win_rate"
            ] = wilson_rate_interval(
                successes=simultaneous,
                total=len(rows),
            )
    return intervals


def transfer_control_learning_development_record(
    report: TransferControlLearningDevelopmentReport,
    *,
    bootstrap_seed: int = TRANSFER_CONTROL_LEARNING_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CONTROL_LEARNING_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    result = report.to_summary_dict()
    result["bootstrap_seed"] = bootstrap_seed
    result["bootstrap_samples"] = bootstrap_samples
    result["development_intervals"] = {
        key: value.to_dict()
        for key, value in bootstrap_transfer_control_learning_metrics(
            report,
            seed=bootstrap_seed,
            samples=bootstrap_samples,
        ).items()
    }
    return result


def evaluate_transfer_control_learning_world(
    *, seed: int, condition: str
) -> TransferControlLearningWorldScore:
    normalized_seed = require_disjoint_seed_sets(world=(seed,))["world"][0]
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
    shuffled_prior = permuted_transfer_prior(learned_prior, offset=1)
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
            world_id="control-learning:scratch",
            prior=TransferPrior.scratch(),
        ),
        "candidate": GatedTransferModel(
            world_id="control-learning:candidate",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
        ),
        "ungated": PrequentialTransferModel(
            world_id="control-learning:ungated",
            prior=learned_prior,
        ),
        "shuffled": GatedTransferModel(
            world_id="control-learning:shuffled",
            source_prior=shuffled_prior,
            initial_source_weight=configuration.initial_source_weight,
        ),
        "pooled": PrequentialTransferModel(
            world_id="control-learning:pooled",
            prior=pooled_source_prior(source_evidence),
        ),
        "oracle": PrequentialTransferModel(
            world_id="control-learning:oracle",
            prior=TransferPrior.oracle(source_family),
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
    candidate = models["candidate"]
    shuffled = models["shuffled"]
    if not isinstance(candidate, GatedTransferModel):
        raise ValidationError("candidate model type is invalid")
    if not isinstance(shuffled, GatedTransferModel):
        raise ValidationError("shuffled model type is invalid")
    candidate_snapshot = candidate.to_snapshot()
    shuffled_snapshot = shuffled.to_snapshot()
    return TransferControlLearningWorldScore(
        seed=normalized_seed,
        condition=condition,
        scratch=scores["scratch"],
        candidate=scores["candidate"],
        ungated=scores["ungated"],
        shuffled=scores["shuffled"],
        pooled=scores["pooled"],
        oracle=scores["oracle"],
        candidate_final_source_weight=candidate.source_weight,
        shuffled_final_source_weight=shuffled.source_weight,
        candidate_snapshot_valid=(
            GatedTransferModel.from_snapshot(candidate_snapshot).to_snapshot()
            == candidate_snapshot
        ),
        shuffled_snapshot_valid=(
            GatedTransferModel.from_snapshot(shuffled_snapshot).to_snapshot()
            == shuffled_snapshot
        ),
        source_interactions=configuration.source_interactions,
    )


def run_transfer_control_learning_development(
    *, seeds: Iterable[int]
) -> TransferControlLearningDevelopmentReport:
    normalized = require_disjoint_seed_sets(development=seeds)["development"]
    worlds = tuple(
        evaluate_transfer_control_learning_world(
            seed=seed,
            condition=condition,
        )
        for seed in normalized
        for condition in TRANSFER_CONDITIONS
    )
    return TransferControlLearningDevelopmentReport(
        seeds=normalized,
        worlds=worlds,
    )
