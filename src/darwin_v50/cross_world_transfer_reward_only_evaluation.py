"""Development evaluator for reward-only compatibility transfer.

This evaluator changes one part of the H50-L15 candidate: the compatibility
gate updates its source weight from chosen-action rewards only.  Transition
outcomes remain in the common observation schema and causal archive, but they
cannot affect the gate weight or reward forecasts.  This module is
development-only and contains no capability decision rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable

from .cross_world_transfer_calibration import TRANSFER_SELECTED_CONFIGURATION
from .cross_world_transfer_control_evaluation import (
    TRANSFER_CONTROL_CONTEXT_CYCLES,
    TRANSFER_CONTROL_EPSILON,
    TRANSFER_CONTROL_POLICY_XOR_MASK,
    TRANSFER_CONTROL_SCHEDULE_XOR_MASK,
    ContextualPolicyScore,
    balanced_transfer_context_schedule,
    score_contextual_policy,
)
from .cross_world_transfer_control_learning_evaluation import (
    TransferControlLearningDevelopmentReport,
    TransferControlLearningWorldScore,
    bootstrap_transfer_control_learning_metrics,
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
    transfer_cell_keys,
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


REWARD_ONLY_CONTROL_TEST_SEEDS = tuple(range(35900, 35904))
REWARD_ONLY_CONTROL_DEVELOPMENT_SEEDS = tuple(range(36000, 36032))
REWARD_ONLY_CONTROL_BOOTSTRAP_SEED = 36700
REWARD_ONLY_CONTROL_BOOTSTRAP_SAMPLES = 2_000


@dataclass(frozen=True, slots=True)
class RewardOnlyTransferWorldScore(TransferControlLearningWorldScore):
    candidate_transition_blindness_valid: bool
    shuffled_transition_blindness_valid: bool

    def __post_init__(self) -> None:
        super(RewardOnlyTransferWorldScore, self).__post_init__()
        if not isinstance(self.candidate_transition_blindness_valid, bool):
            raise ValidationError(
                "candidate transition-blindness flag is invalid"
            )
        if not isinstance(self.shuffled_transition_blindness_valid, bool):
            raise ValidationError(
                "shuffled transition-blindness flag is invalid"
            )


@dataclass(frozen=True, slots=True)
class RewardOnlyTransferDevelopmentReport(
    TransferControlLearningDevelopmentReport
):
    def __post_init__(self) -> None:
        super(RewardOnlyTransferDevelopmentReport, self).__post_init__()
        if any(
            not isinstance(item, RewardOnlyTransferWorldScore)
            for item in self.worlds
        ):
            raise ValidationError("reward-only world score is invalid")

    def to_summary_dict(self) -> dict[str, object]:
        result = super(
            RewardOnlyTransferDevelopmentReport,
            self,
        ).to_summary_dict()
        result["experiment"] = "031"
        result["status"] = "development-only"
        result["capability_claim"] = False
        result["next_hypothesis_registered"] = False
        result.pop("h50_l15_registered", None)
        result["baseline_h50_l15_status"] = "passed_locally"
        result["feedback_boundary"] = (
            "action ranking and compatibility-weight updates use only "
            "chosen-action rewards; transition outcomes remain archived but "
            "are causally excluded from weights and reward forecasts"
        )
        integrity = result["integrity"]
        if not isinstance(integrity, dict):
            raise ValidationError("reward-only integrity summary is invalid")
        integrity["candidate_transition_blindness_rate"] = fmean(
            float(item.candidate_transition_blindness_valid)
            for item in self.worlds
        )
        integrity["shuffled_transition_blindness_rate"] = fmean(
            float(item.shuffled_transition_blindness_valid)
            for item in self.worlds
        )
        return result


def reward_only_transition_blindness_check(
    *,
    source_prior: TransferPrior,
    initial_source_weight: float,
    archive: tuple[TransferObservation, ...],
) -> bool:
    """Replay rewards under opposite transitions and compare reward state."""

    if not archive:
        raise ValidationError("transition-blindness archive is empty")
    world_id = archive[0].world_id
    observed = GatedTransferModel(
        world_id=world_id,
        source_prior=source_prior,
        initial_source_weight=initial_source_weight,
        compatibility_feedback="reward_only",
    )
    flipped = GatedTransferModel(
        world_id=world_id,
        source_prior=source_prior,
        initial_source_weight=initial_source_weight,
        compatibility_feedback="reward_only",
    )
    for item in archive:
        if item.world_id != world_id:
            return False
        for context, action in transfer_cell_keys():
            if (
                observed.peek(context, action).reward_probability
                != flipped.peek(context, action).reward_probability
            ):
                return False
        observed.forecast(item.context, item.action)
        flipped.forecast(item.context, item.action)
        observed.observe(item)
        flipped.observe(
            TransferObservation(
                world_id=item.world_id,
                index=item.index,
                context=item.context,
                action=item.action,
                next_observation=not item.next_observation,
                reward=item.reward,
            )
        )
        if (
            observed.source_weight != flipped.source_weight
            or observed.weight_history != flipped.weight_history
        ):
            return False
    return all(
        observed.peek(context, action).reward_probability
        == flipped.peek(context, action).reward_probability
        for context, action in transfer_cell_keys()
    )


def evaluate_reward_only_transfer_world(
    *, seed: int, condition: str
) -> RewardOnlyTransferWorldScore:
    normalized_seed = require_disjoint_seed_sets(world=(seed,))["world"][0]
    if condition not in TRANSFER_CONDITIONS:
        raise ValidationError("reward-only condition is invalid")
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
            world_id="reward-only:scratch",
            prior=TransferPrior.scratch(),
        ),
        "candidate": GatedTransferModel(
            world_id="reward-only:candidate",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
            compatibility_feedback="reward_only",
        ),
        "ungated": PrequentialTransferModel(
            world_id="reward-only:ungated",
            prior=learned_prior,
        ),
        "shuffled": GatedTransferModel(
            world_id="reward-only:shuffled",
            source_prior=shuffled_prior,
            initial_source_weight=configuration.initial_source_weight,
            compatibility_feedback="reward_only",
        ),
        "pooled": PrequentialTransferModel(
            world_id="reward-only:pooled",
            prior=pooled_source_prior(source_evidence),
        ),
        "oracle": PrequentialTransferModel(
            world_id="reward-only:oracle",
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
        raise ValidationError("reward-only candidate type is invalid")
    if not isinstance(shuffled, GatedTransferModel):
        raise ValidationError("reward-only shuffled type is invalid")
    candidate_snapshot = candidate.to_snapshot()
    shuffled_snapshot = shuffled.to_snapshot()
    return RewardOnlyTransferWorldScore(
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
        candidate_transition_blindness_valid=(
            reward_only_transition_blindness_check(
                source_prior=learned_prior,
                initial_source_weight=configuration.initial_source_weight,
                archive=candidate.archive,
            )
        ),
        shuffled_transition_blindness_valid=(
            reward_only_transition_blindness_check(
                source_prior=shuffled_prior,
                initial_source_weight=configuration.initial_source_weight,
                archive=shuffled.archive,
            )
        ),
    )


def run_reward_only_transfer_development(
    *, seeds: Iterable[int]
) -> RewardOnlyTransferDevelopmentReport:
    normalized = require_disjoint_seed_sets(development=seeds)["development"]
    worlds = tuple(
        evaluate_reward_only_transfer_world(
            seed=seed,
            condition=condition,
        )
        for seed in normalized
        for condition in TRANSFER_CONDITIONS
    )
    return RewardOnlyTransferDevelopmentReport(
        seeds=normalized,
        worlds=worlds,
    )


def reward_only_transfer_development_record(
    report: RewardOnlyTransferDevelopmentReport,
    *,
    bootstrap_seed: int = REWARD_ONLY_CONTROL_BOOTSTRAP_SEED,
    bootstrap_samples: int = REWARD_ONLY_CONTROL_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    if not isinstance(report, RewardOnlyTransferDevelopmentReport):
        raise ValidationError("reward-only development report is invalid")
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
