"""Development evaluator for cellwise compatibility and safe fallback.

The candidate localizes source-versus-scratch compatibility to each aligned
context-action cell.  If a cell's posterior source weight falls below its
initial prior weight, that cell forecasts from scratch until its posterior
recovers.  This module is development-only and has no capability decision.
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
    CellwiseGatedTransferModel,
    GatedTransferModel,
    collect_source_family_evidence,
    learn_transfer_prior,
    permuted_transfer_prior,
)
from .cross_world_transfer_learning_evaluation import (
    TRANSFER_SOURCE_BASE_XOR_MASK,
    target_family_for_condition,
)
from .models import ValidationError


LOCAL_GATE_TEST_SEEDS = tuple(range(37900, 37904))
LOCAL_GATE_DEVELOPMENT_SEEDS = tuple(range(38000, 38032))
LOCAL_GATE_BOOTSTRAP_SEED = 38700
LOCAL_GATE_BOOTSTRAP_SAMPLES = 2_000
LOCAL_GATE_POLICIES = (
    "scratch",
    "global",
    "cellwise",
    "candidate",
    "ungated",
    "shuffled",
    "oracle",
)


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
class LocalGateWorldScore:
    seed: int
    condition: str
    scratch: ContextualPolicyScore
    global_: ContextualPolicyScore
    cellwise: ContextualPolicyScore
    candidate: ContextualPolicyScore
    ungated: ContextualPolicyScore
    shuffled: ContextualPolicyScore
    oracle: ContextualPolicyScore
    global_final_source_weight: float
    cellwise_mean_posterior_weight: float
    candidate_mean_posterior_weight: float
    candidate_mean_effective_weight: float
    candidate_fallback_cell_rate: float
    candidate_snapshot_valid: bool
    cellwise_snapshot_valid: bool
    global_snapshot_valid: bool
    shuffled_snapshot_valid: bool
    source_interactions: int

    def __post_init__(self) -> None:
        require_disjoint_seed_sets(world=(self.seed,))
        if self.condition not in TRANSFER_CONDITIONS:
            raise ValidationError("local-gate condition is invalid")
        for field, value in (
            ("global source weight", self.global_final_source_weight),
            (
                "cellwise posterior weight",
                self.cellwise_mean_posterior_weight,
            ),
            (
                "candidate posterior weight",
                self.candidate_mean_posterior_weight,
            ),
            (
                "candidate effective weight",
                self.candidate_mean_effective_weight,
            ),
            (
                "candidate fallback cell rate",
                self.candidate_fallback_cell_rate,
            ),
        ):
            _validate_probability(value, field)
        if any(
            not isinstance(value, bool)
            for value in (
                self.candidate_snapshot_valid,
                self.cellwise_snapshot_valid,
                self.global_snapshot_valid,
                self.shuffled_snapshot_valid,
            )
        ):
            raise ValidationError("local-gate snapshot flag is invalid")
        if (
            isinstance(self.source_interactions, bool)
            or not isinstance(self.source_interactions, int)
            or self.source_interactions < 1
        ):
            raise ValidationError("local-gate source cost is invalid")

    def policy_score(self, policy: str) -> ContextualPolicyScore:
        if policy not in LOCAL_GATE_POLICIES:
            raise ValidationError("local-gate policy is invalid")
        return self.global_ if policy == "global" else getattr(self, policy)

    def improvement(self, policy: str, metric: str) -> float:
        score = self.policy_score(policy)
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
        raise ValidationError("local-gate metric is invalid")

    def candidate_minus_policy(self, policy: str, metric: str) -> float:
        if policy not in ("global", "cellwise", "ungated", "shuffled"):
            raise ValidationError("local-gate control policy is invalid")
        other = self.policy_score(policy)
        if metric == "reward":
            return float(
                self.candidate.cumulative_reward - other.cumulative_reward
            )
        if metric == "pseudo_regret":
            return other.pseudo_regret - self.candidate.pseudo_regret
        raise ValidationError("local-gate control metric is invalid")


@dataclass(frozen=True, slots=True)
class LocalGateDevelopmentReport:
    seeds: tuple[int, ...]
    worlds: tuple[LocalGateWorldScore, ...]

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(development=self.seeds)[
            "development"
        ]
        if normalized != self.seeds:
            raise ValidationError("local-gate seeds are not canonical")
        if any(
            sum(item.condition == condition for item in self.worlds)
            != len(self.seeds)
            for condition in TRANSFER_CONDITIONS
        ):
            raise ValidationError("local-gate worlds are unbalanced")

    def condition_rows(
        self,
        condition: str,
    ) -> tuple[LocalGateWorldScore, ...]:
        if condition not in TRANSFER_CONDITIONS:
            raise ValidationError("local-gate condition is invalid")
        return tuple(
            item for item in self.worlds if item.condition == condition
        )

    @property
    def source_interactions(self) -> int:
        return self.worlds[0].source_interactions

    @property
    def target_interactions(self) -> int:
        return TRANSFER_CONTROL_CONTEXT_CYCLES * 8

    def mean_improvement(
        self,
        condition: str,
        policy: str,
        metric: str,
    ) -> float:
        return fmean(
            item.improvement(policy, metric)
            for item in self.condition_rows(condition)
        )

    def mean_candidate_control_delta(
        self,
        condition: str,
        policy: str,
        metric: str,
    ) -> float:
        return fmean(
            item.candidate_minus_policy(policy, metric)
            for item in self.condition_rows(condition)
        )

    def integrity_rates(self) -> dict[str, float]:
        scores = tuple(
            score
            for item in self.worlds
            for score in (
                item.scratch,
                item.global_,
                item.cellwise,
                item.candidate,
                item.ungated,
                item.shuffled,
                item.oracle,
            )
        )
        return {
            "causal_archive_rate": fmean(
                float(score.causal_archive_valid) for score in scores
            ),
            "public_identity_rate": fmean(
                float(score.public_identity_valid) for score in scores
            ),
            "candidate_snapshot_rate": fmean(
                float(item.candidate_snapshot_valid)
                for item in self.worlds
            ),
            "cellwise_snapshot_rate": fmean(
                float(item.cellwise_snapshot_valid)
                for item in self.worlds
            ),
            "global_snapshot_rate": fmean(
                float(item.global_snapshot_valid) for item in self.worlds
            ),
            "shuffled_snapshot_rate": fmean(
                float(item.shuffled_snapshot_valid)
                for item in self.worlds
            ),
        }

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "experiment": "033",
            "status": "development-only",
            "capability_claim": False,
            "new_hypothesis_registered": False,
            "seeds": list(self.seeds),
            "source_interactions": self.source_interactions,
            "target_interactions": self.target_interactions,
            "source_to_target_cost_ratio": (
                self.source_interactions / self.target_interactions
            ),
            "epsilon": TRANSFER_CONTROL_EPSILON,
            "candidate_boundary": (
                "independent transition-and-reward compatibility odds per "
                "context-action cell; source influence becomes zero when a "
                "cell posterior falls below its initial source weight"
            ),
            "mean_improvement_over_scratch": {
                condition: {
                    policy: {
                        metric: self.mean_improvement(
                            condition,
                            policy,
                            metric,
                        )
                        for metric in (
                            "reward",
                            "pseudo_regret",
                            "preferred_action_rate",
                        )
                    }
                    for policy in LOCAL_GATE_POLICIES[1:]
                }
                for condition in TRANSFER_CONDITIONS
            },
            "candidate_minus_controls": {
                condition: {
                    policy: {
                        metric: self.mean_candidate_control_delta(
                            condition,
                            policy,
                            metric,
                        )
                        for metric in ("reward", "pseudo_regret")
                    }
                    for policy in (
                        "global",
                        "cellwise",
                        "ungated",
                        "shuffled",
                    )
                }
                for condition in TRANSFER_CONDITIONS
            },
            "candidate_weight_state": {
                condition: {
                    "mean_posterior_source_weight": fmean(
                        item.candidate_mean_posterior_weight
                        for item in self.condition_rows(condition)
                    ),
                    "mean_effective_source_weight": fmean(
                        item.candidate_mean_effective_weight
                        for item in self.condition_rows(condition)
                    ),
                    "fallback_cell_rate": fmean(
                        item.candidate_fallback_cell_rate
                        for item in self.condition_rows(condition)
                    ),
                }
                for condition in TRANSFER_CONDITIONS
            },
            "integrity": self.integrity_rates(),
        }


def evaluate_local_gate_world(
    *,
    seed: int,
    condition: str,
) -> LocalGateWorldScore:
    normalized_seed = require_disjoint_seed_sets(world=(seed,))["world"][0]
    if condition not in TRANSFER_CONDITIONS:
        raise ValidationError("local-gate condition is invalid")
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
            world_id="local-gate:scratch",
            prior=TransferPrior.scratch(),
        ),
        "global": GatedTransferModel(
            world_id="local-gate:global",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
        ),
        "cellwise": CellwiseGatedTransferModel(
            world_id="local-gate:cellwise",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
            scratch_fallback=False,
        ),
        "candidate": CellwiseGatedTransferModel(
            world_id="local-gate:candidate",
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
            scratch_fallback=True,
        ),
        "ungated": PrequentialTransferModel(
            world_id="local-gate:ungated",
            prior=learned_prior,
        ),
        "shuffled": CellwiseGatedTransferModel(
            world_id="local-gate:shuffled",
            source_prior=shuffled_prior,
            initial_source_weight=configuration.initial_source_weight,
            scratch_fallback=True,
        ),
        "oracle": PrequentialTransferModel(
            world_id="local-gate:oracle",
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
    global_model = models["global"]
    cellwise_model = models["cellwise"]
    candidate_model = models["candidate"]
    shuffled_model = models["shuffled"]
    if not isinstance(global_model, GatedTransferModel):
        raise ValidationError("global local-gate control is invalid")
    if not isinstance(cellwise_model, CellwiseGatedTransferModel):
        raise ValidationError("cellwise local-gate control is invalid")
    if not isinstance(candidate_model, CellwiseGatedTransferModel):
        raise ValidationError("local-gate candidate is invalid")
    if not isinstance(shuffled_model, CellwiseGatedTransferModel):
        raise ValidationError("shuffled local-gate control is invalid")
    global_snapshot = global_model.to_snapshot()
    cellwise_snapshot = cellwise_model.to_snapshot()
    candidate_snapshot = candidate_model.to_snapshot()
    shuffled_snapshot = shuffled_model.to_snapshot()
    return LocalGateWorldScore(
        seed=normalized_seed,
        condition=condition,
        scratch=scores["scratch"],
        global_=scores["global"],
        cellwise=scores["cellwise"],
        candidate=scores["candidate"],
        ungated=scores["ungated"],
        shuffled=scores["shuffled"],
        oracle=scores["oracle"],
        global_final_source_weight=global_model.source_weight,
        cellwise_mean_posterior_weight=fmean(
            cellwise_model.posterior_source_weights
        ),
        candidate_mean_posterior_weight=fmean(
            candidate_model.posterior_source_weights
        ),
        candidate_mean_effective_weight=fmean(
            candidate_model.effective_source_weights
        ),
        candidate_fallback_cell_rate=candidate_model.fallback_cell_rate,
        candidate_snapshot_valid=(
            CellwiseGatedTransferModel.from_snapshot(
                candidate_snapshot
            ).to_snapshot()
            == candidate_snapshot
        ),
        cellwise_snapshot_valid=(
            CellwiseGatedTransferModel.from_snapshot(
                cellwise_snapshot
            ).to_snapshot()
            == cellwise_snapshot
        ),
        global_snapshot_valid=(
            GatedTransferModel.from_snapshot(global_snapshot).to_snapshot()
            == global_snapshot
        ),
        shuffled_snapshot_valid=(
            CellwiseGatedTransferModel.from_snapshot(
                shuffled_snapshot
            ).to_snapshot()
            == shuffled_snapshot
        ),
        source_interactions=configuration.source_interactions,
    )


def run_local_gate_development(
    *,
    seeds: Iterable[int],
) -> LocalGateDevelopmentReport:
    normalized = require_disjoint_seed_sets(development=seeds)["development"]
    return LocalGateDevelopmentReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_local_gate_world(
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


def bootstrap_local_gate_metrics(
    report: LocalGateDevelopmentReport,
    *,
    seed: int = LOCAL_GATE_BOOTSTRAP_SEED,
    samples: int = LOCAL_GATE_BOOTSTRAP_SAMPLES,
) -> dict[str, ControlMetricInterval]:
    if not isinstance(report, LocalGateDevelopmentReport):
        raise ValidationError("local-gate report is invalid")
    normalized_seed = require_disjoint_seed_sets(bootstrap=(seed,))[
        "bootstrap"
    ][0]
    if (
        isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("local-gate bootstrap is invalid")
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
            **{
                f"candidate_minus_{policy}_{metric}": tuple(
                    item.candidate_minus_policy(policy, metric)
                    for item in rows
                )
                for policy in (
                    "global",
                    "cellwise",
                    "ungated",
                    "shuffled",
                )
                for metric in ("reward", "pseudo_regret")
            },
            "candidate_mean_posterior_weight": tuple(
                item.candidate_mean_posterior_weight for item in rows
            ),
            "candidate_mean_effective_weight": tuple(
                item.candidate_mean_effective_weight for item in rows
            ),
            "candidate_fallback_cell_rate": tuple(
                item.candidate_fallback_cell_rate for item in rows
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
            intervals["related_candidate_simultaneous_win_rate"] = (
                wilson_rate_interval(
                    successes=simultaneous,
                    total=len(rows),
                )
            )
    return intervals


def local_gate_development_record(
    report: LocalGateDevelopmentReport,
    *,
    bootstrap_seed: int = LOCAL_GATE_BOOTSTRAP_SEED,
    bootstrap_samples: int = LOCAL_GATE_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    intervals = bootstrap_local_gate_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    result = report.to_summary_dict()
    result["bootstrap_seed"] = bootstrap_seed
    result["bootstrap_samples"] = bootstrap_samples
    result["development_intervals"] = {
        name: interval.to_dict() for name, interval in intervals.items()
    }
    return result
