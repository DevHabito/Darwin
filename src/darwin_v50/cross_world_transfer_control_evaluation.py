"""Oracle sensitivity benchmark for cross-world contextual decisions.

This evaluator asks whether the existing synthetic family can expose reward
benefits and negative transfer when a policy is initialized with an exact
family prior.  The oracle is evaluator-only.  No learned transfer capability
is claimed or registered here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import fmean
from typing import Iterable, Protocol

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
    TransferForecast,
    TransferObservation,
    TransferPrior,
    TRANSFER_CONTEXT_ORDER,
    TransferWorldSpecification,
    require_disjoint_seed_sets,
)
from .cross_world_transfer_learning_evaluation import (
    target_family_for_condition,
)
from .learned_context_lab import (
    CONTEXT_ACTIONS,
    ContextState,
    all_contexts,
)
from .models import ValidationError


TRANSFER_CONTROL_TEST_SEEDS = tuple(range(30200, 30208))
TRANSFER_CONTROL_VALIDATION_SEEDS = tuple(range(30300, 30332))
TRANSFER_CONTROL_CONTEXT_CYCLES = 8
TRANSFER_CONTROL_EPSILON = 0.10
TRANSFER_CONTROL_BOOTSTRAP_SEED = 30900
TRANSFER_CONTROL_BOOTSTRAP_SAMPLES = 5_000
TRANSFER_CONTROL_SCHEDULE_XOR_MASK = 0x5D02A
TRANSFER_CONTROL_POLICY_XOR_MASK = 0x6A31C


class _DecisionModel(Protocol):
    @property
    def archive(self) -> tuple[TransferObservation, ...]: ...

    def peek(
        self, context: ContextState, action: str
    ) -> TransferForecast: ...

    def forecast(
        self, context: ContextState, action: str
    ) -> TransferForecast: ...

    def observe(self, observation: TransferObservation) -> None: ...


def balanced_transfer_context_schedule(
    *, cycles: int, seed: int
) -> tuple[ContextState, ...]:
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1:
        raise ValidationError("context schedule cycles must be positive")
    normalized_seed = require_disjoint_seed_sets(schedule=(seed,))[
        "schedule"
    ][0]
    rng = random.Random(normalized_seed)
    contexts = all_contexts(TRANSFER_CONTEXT_ORDER)
    result: list[ContextState] = []
    for _ in range(cycles):
        cycle = list(contexts)
        rng.shuffle(cycle)
        result.extend(cycle)
    return tuple(result)


def _validate_epsilon(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValidationError("control epsilon must be within [0, 1]")
    return float(value)


def _choose_action(
    model: _DecisionModel,
    context: ContextState,
    *,
    rng: random.Random,
    epsilon: float,
) -> str:
    explore = rng.random() < epsilon
    if explore:
        return rng.choice(CONTEXT_ACTIONS)
    forecasts = tuple(model.peek(context, action) for action in CONTEXT_ACTIONS)
    best = max(item.reward_probability for item in forecasts)
    return next(
        item.action for item in forecasts if item.reward_probability == best
    )


@dataclass(frozen=True, slots=True)
class ContextualPolicyScore:
    cumulative_reward: int
    pseudo_regret: float
    family_preferred_action_rate: float
    causal_archive_valid: bool
    public_identity_valid: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.cumulative_reward, bool)
            or not isinstance(self.cumulative_reward, int)
            or self.cumulative_reward < 0
        ):
            raise ValidationError("cumulative reward is invalid")
        for value in (self.pseudo_regret, self.family_preferred_action_rate):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValidationError("contextual policy metric is invalid")
        if self.family_preferred_action_rate > 1.0:
            raise ValidationError("preferred action rate exceeds one")
        if not isinstance(self.causal_archive_valid, bool):
            raise ValidationError("causal archive flag is invalid")
        if not isinstance(self.public_identity_valid, bool):
            raise ValidationError("public identity flag is invalid")


@dataclass(frozen=True, slots=True)
class TransferControlWorldScore:
    seed: int
    condition: str
    scratch: ContextualPolicyScore
    oracle: ContextualPolicyScore

    def __post_init__(self) -> None:
        require_disjoint_seed_sets(world=(self.seed,))
        if self.condition not in TRANSFER_CONDITIONS:
            raise ValidationError("control condition is invalid")

    @property
    def reward_improvement(self) -> float:
        return float(
            self.oracle.cumulative_reward - self.scratch.cumulative_reward
        )

    @property
    def pseudo_regret_reduction(self) -> float:
        return self.scratch.pseudo_regret - self.oracle.pseudo_regret

    @property
    def preferred_action_rate_improvement(self) -> float:
        return (
            self.oracle.family_preferred_action_rate
            - self.scratch.family_preferred_action_rate
        )


@dataclass(frozen=True, slots=True)
class TransferControlSensitivityReport:
    seeds: tuple[int, ...]
    epsilon: float
    context_cycles: int
    worlds: tuple[TransferControlWorldScore, ...]

    def __post_init__(self) -> None:
        normalized = require_disjoint_seed_sets(validation=self.seeds)[
            "validation"
        ]
        if normalized != self.seeds:
            raise ValidationError("control seeds are not canonical")
        _validate_epsilon(self.epsilon)
        if self.context_cycles < 1:
            raise ValidationError("control context cycles are invalid")
        expected = len(self.seeds)
        if any(
            sum(item.condition == condition for item in self.worlds)
            != expected
            for condition in TRANSFER_CONDITIONS
        ):
            raise ValidationError("control conditions are unbalanced")

    def _condition_rows(
        self, condition: str
    ) -> tuple[TransferControlWorldScore, ...]:
        if condition not in TRANSFER_CONDITIONS:
            raise ValidationError("control condition is invalid")
        return tuple(
            item for item in self.worlds if item.condition == condition
        )

    def mean_metric(self, condition: str, metric: str) -> float:
        if metric not in (
            "reward_improvement",
            "pseudo_regret_reduction",
            "preferred_action_rate_improvement",
        ):
            raise ValidationError("control metric is invalid")
        return fmean(
            getattr(item, metric) for item in self._condition_rows(condition)
        )

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "status": "benchmark-development-only",
            "capability_claim": False,
            "h50_l15_registered": False,
            "seeds": list(self.seeds),
            "epsilon": self.epsilon,
            "context_cycles": self.context_cycles,
            "interactions_per_target": self.context_cycles * 8,
            "oracle_improvement": {
                condition: {
                    metric: self.mean_metric(condition, metric)
                    for metric in (
                        "reward_improvement",
                        "pseudo_regret_reduction",
                        "preferred_action_rate_improvement",
                    )
                }
                for condition in TRANSFER_CONDITIONS
            },
            "integrity": {
                "causal_archive_rate": fmean(
                    float(score.causal_archive_valid)
                    for item in self.worlds
                    for score in (item.scratch, item.oracle)
                ),
                "public_identity_rate": fmean(
                    float(score.public_identity_valid)
                    for item in self.worlds
                    for score in (item.scratch, item.oracle)
                ),
            },
        }


@dataclass(frozen=True, slots=True)
class ControlMetricInterval:
    mean: float
    low: float
    high: float

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (self.mean, self.low, self.high)
        ):
            raise ValidationError("control interval is invalid")
        if not self.low <= self.mean <= self.high:
            raise ValidationError("control interval ordering is invalid")

    def to_dict(self) -> dict[str, float]:
        return {"mean": self.mean, "low": self.low, "high": self.high}


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_transfer_control_metrics(
    report: TransferControlSensitivityReport,
    *,
    seed: int = TRANSFER_CONTROL_BOOTSTRAP_SEED,
    samples: int = TRANSFER_CONTROL_BOOTSTRAP_SAMPLES,
) -> dict[str, ControlMetricInterval]:
    if not isinstance(report, TransferControlSensitivityReport):
        raise ValidationError("control report is invalid")
    normalized_seed = require_disjoint_seed_sets(bootstrap=(seed,))[
        "bootstrap"
    ][0]
    if (
        isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("control bootstrap samples must be positive")
    rng = random.Random(normalized_seed)
    metrics: dict[str, ControlMetricInterval] = {}
    for condition in TRANSFER_CONDITIONS:
        rows = report._condition_rows(condition)
        value_sets = {
            "reward_improvement": tuple(
                item.reward_improvement for item in rows
            ),
            "pseudo_regret_reduction": tuple(
                item.pseudo_regret_reduction for item in rows
            ),
            "preferred_action_rate_improvement": tuple(
                item.preferred_action_rate_improvement for item in rows
            ),
        }
        if condition == "related":
            value_sets["simultaneous_win_rate"] = tuple(
                float(
                    item.reward_improvement > 0.0
                    and item.pseudo_regret_reduction > 0.0
                )
                for item in rows
            )
        for name, values in value_sets.items():
            bootstrap_means = [
                fmean(rng.choice(values) for _ in values)
                for _ in range(samples)
            ]
            metrics[f"{condition}_{name}"] = ControlMetricInterval(
                mean=fmean(values),
                low=_quantile(bootstrap_means, 0.025),
                high=_quantile(bootstrap_means, 0.975),
            )
    return metrics


def transfer_control_sensitivity_criteria(
    metrics: dict[str, ControlMetricInterval],
    *,
    causal_archive_rate: float,
    public_identity_rate: float,
) -> dict[str, bool]:
    required = {
        f"{condition}_{name}"
        for condition in TRANSFER_CONDITIONS
        for name in (
            "reward_improvement",
            "pseudo_regret_reduction",
            "preferred_action_rate_improvement",
        )
    } | {"related_simultaneous_win_rate"}
    if set(metrics) != required:
        raise ValidationError("control metric set is incomplete")
    for value in (causal_archive_rate, public_identity_rate):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
        ):
            raise ValidationError("control integrity rate is invalid")
    return {
        "related_reward_low_at_least_1": (
            metrics["related_reward_improvement"].low >= 1.0
        ),
        "related_regret_reduction_low_at_least_0_75": (
            metrics["related_pseudo_regret_reduction"].low >= 0.75
        ),
        "related_preferred_rate_low_at_least_0_05": (
            metrics["related_preferred_action_rate_improvement"].low
            >= 0.05
        ),
        "related_simultaneous_win_low_at_least_0_75": (
            metrics["related_simultaneous_win_rate"].low >= 0.75
        ),
        "unrelated_reward_high_at_most_0": (
            metrics["unrelated_reward_improvement"].high <= 0.0
        ),
        "unrelated_regret_reduction_high_at_most_0": (
            metrics["unrelated_pseudo_regret_reduction"].high <= 0.0
        ),
        "adversarial_reward_high_at_most_minus_2": (
            metrics["adversarial_reward_improvement"].high <= -2.0
        ),
        "adversarial_regret_reduction_high_at_most_minus_5": (
            metrics["adversarial_pseudo_regret_reduction"].high <= -5.0
        ),
        "causal_archive_rate_equals_1": causal_archive_rate == 1.0,
        "public_identity_rate_equals_1": public_identity_rate == 1.0,
    }


def transfer_control_validation_record(
    report: TransferControlSensitivityReport,
    *,
    bootstrap_seed: int = TRANSFER_CONTROL_BOOTSTRAP_SEED,
    bootstrap_samples: int = TRANSFER_CONTROL_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    metrics = bootstrap_transfer_control_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    base = report.to_summary_dict()
    integrity = base["integrity"]
    if not isinstance(integrity, dict):
        raise ValidationError("control integrity summary is invalid")
    criteria = transfer_control_sensitivity_criteria(
        metrics,
        causal_archive_rate=integrity["causal_archive_rate"],
        public_identity_rate=integrity["public_identity_rate"],
    )
    return {
        "status": "control-benchmark-sensitivity",
        "capability_claim": False,
        "h50_l15_registered": False,
        "seeds": list(report.seeds),
        "epsilon": report.epsilon,
        "context_cycles": report.context_cycles,
        "interactions_per_target": report.context_cycles * 8,
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_samples": bootstrap_samples,
        "metrics": {
            key: value.to_dict() for key, value in metrics.items()
        },
        "integrity": integrity,
        "criteria": criteria,
        "decision": (
            "passed_benchmark_sensitivity"
            if all(criteria.values())
            else "refuted_benchmark"
        ),
    }


def _score_policy(
    *,
    model: _DecisionModel,
    task: AlignedTransferTask,
    contexts: tuple[ContextState, ...],
    family: TransferFamilySpecification,
    specification: TransferWorldSpecification,
    policy_seed: int,
    epsilon: float,
) -> ContextualPolicyScore:
    rng = random.Random(policy_seed)
    reward = 0
    pseudo_regret = 0.0
    preferred_total = 0
    preferred_chosen = 0
    chosen_actions: list[str] = []
    for context in contexts:
        action = _choose_action(
            model,
            context,
            rng=rng,
            epsilon=epsilon,
        )
        model.forecast(context, action)
        observation = task.act(context, action)
        model.observe(observation)
        chosen_actions.append(action)
        reward += int(observation.reward)
        chosen_probability = specification.cell(
            context, action
        ).reward_probability
        pseudo_regret += max(
            specification.cell(context, candidate).reward_probability
            for candidate in CONTEXT_ACTIONS
        ) - chosen_probability
        family_means = {
            candidate: family.cell(context, candidate).reward_mean
            for candidate in CONTEXT_ACTIONS
        }
        if len(set(family_means.values())) > 1:
            preferred_total += 1
            preferred_chosen += int(
                action == max(family_means, key=family_means.__getitem__)
            )
    archive = model.archive
    public_world_id = task.world_id
    return ContextualPolicyScore(
        cumulative_reward=reward,
        pseudo_regret=pseudo_regret,
        family_preferred_action_rate=(
            preferred_chosen / preferred_total
            if preferred_total
            else 0.0
        ),
        causal_archive_valid=(
            len(archive) == len(contexts)
            and tuple(item.index for item in archive)
            == tuple(range(len(contexts)))
            and tuple(item.context for item in archive) == contexts
            and tuple(item.action for item in archive)
            == tuple(chosen_actions)
        ),
        public_identity_valid=(
            all(item.world_id == public_world_id for item in archive)
            and str(family.seed) not in public_world_id
            and str(specification.world_seed) not in public_world_id
        ),
    )


def evaluate_transfer_control_world(
    *,
    seed: int,
    condition: str,
    epsilon: float = TRANSFER_CONTROL_EPSILON,
    context_cycles: int = TRANSFER_CONTROL_CONTEXT_CYCLES,
) -> TransferControlWorldScore:
    normalized_seed = require_disjoint_seed_sets(world=(seed,))["world"][0]
    normalized_epsilon = _validate_epsilon(epsilon)
    source_family = TransferFamilySpecification.from_seed(
        normalized_seed ^ SOURCE_FAMILY_XOR_MASK
    )
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
        cycles=context_cycles,
        seed=normalized_seed ^ TRANSFER_CONTROL_SCHEDULE_XOR_MASK,
    )
    scores: dict[str, ContextualPolicyScore] = {}
    for name, prior in (
        ("scratch", TransferPrior.scratch()),
        ("oracle", TransferPrior.oracle(source_family)),
    ):
        public_world_id = f"control-target:{name}"
        scores[name] = _score_policy(
            model=PrequentialTransferModel(
                world_id=public_world_id,
                prior=prior,
            ),
            task=AlignedTransferTask(
                specification,
                outcome_seed=normalized_seed ^ OUTCOME_XOR_MASK,
                public_world_id=public_world_id,
            ),
            contexts=contexts,
            family=target_family,
            specification=specification,
            policy_seed=(
                normalized_seed ^ TRANSFER_CONTROL_POLICY_XOR_MASK
            ),
            epsilon=normalized_epsilon,
        )
    return TransferControlWorldScore(
        seed=normalized_seed,
        condition=condition,
        scratch=scores["scratch"],
        oracle=scores["oracle"],
    )


def run_transfer_control_sensitivity(
    *,
    seeds: Iterable[int],
    epsilon: float = TRANSFER_CONTROL_EPSILON,
    context_cycles: int = TRANSFER_CONTROL_CONTEXT_CYCLES,
) -> TransferControlSensitivityReport:
    normalized = require_disjoint_seed_sets(validation=seeds)["validation"]
    worlds = tuple(
        evaluate_transfer_control_world(
            seed=seed,
            condition=condition,
            epsilon=epsilon,
            context_cycles=context_cycles,
        )
        for seed in normalized
        for condition in TRANSFER_CONDITIONS
    )
    return TransferControlSensitivityReport(
        seeds=normalized,
        epsilon=_validate_epsilon(epsilon),
        context_cycles=context_cycles,
        worlds=worlds,
    )
