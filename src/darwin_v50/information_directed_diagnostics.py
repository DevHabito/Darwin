"""Pre-registered failure audit for Darwin H50-L13."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import random
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from .information_directed_evaluation import (
    IDS_ACTION_XOR_MASK,
    IDS_MODEL_XOR_MASK,
)
from .information_directed_lab import (
    IDS_POSTERIOR_SAMPLE_COUNT,
    InformationDirectedAgent,
)
from .learned_context_lab import CONTEXT_ACTIONS, LearnedContextWorld
from .models import ValidationError
from .online_posterior_evaluation import (
    ONLINE_INTERACTION_COUNT,
    OnlineEpisode,
    _run_mean_policy,
    make_online_schedule,
)
from .online_posterior_lab import (
    ONLINE_ENVIRONMENT_EPISODE_LENGTH,
    FiniteHorizonContextPlanner,
    OnlineExperience,
)


IDS_FAILURE_AUDIT_SEEDS = tuple(range(25200, 25232))
IDS_FAILURE_AUDIT_BLOCK_LENGTH = 16
IDS_FAILURE_AUDIT_QUARTER_LENGTH = 320
IDS_FAILURE_AUDIT_BOOTSTRAP_RESAMPLES = 10_000
IDS_FAILURE_AUDIT_BOOTSTRAP_SEED = 0xA19D19


_METRIC_NAMES = (
    "candidate_reward",
    "certainty_equivalent_reward",
    "candidate_minus_certainty_reward",
    "total_disagreement_rate",
    "staleness_channel_disagreement_rate",
    "ensemble_channel_disagreement_rate",
    "mixture_channel_disagreement_rate",
    "mixture_minus_ensemble_disagreement_rate",
    "mixture_minus_staleness_disagreement_rate",
    "ensemble_minus_staleness_disagreement_rate",
    "selected_non_greedy_probability",
    "realized_non_greedy_rate",
    "non_degenerate_mixture_rate",
    "mean_mixture_entropy",
    "mean_current_map_q_opportunity_cost",
    "conditional_current_map_q_opportunity_cost",
    "mean_action_information_gain",
    "mean_information_ratio",
    "mean_order_posterior_entropy",
)


def _validate_seed(seed: object) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValidationError("IDS audit seed must be an integer")
    return seed


def _normalize_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    normalized = tuple(_validate_seed(seed) for seed in seeds)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValidationError("IDS audit seeds must be non-empty and unique")
    return normalized


def _mean(values: Sequence[float]) -> float:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValidationError("IDS audit values must be finite and non-empty")
    return fmean(values)


def _entropy(probabilities: Mapping[int, float]) -> float:
    if (
        not probabilities
        or any(
            not math.isfinite(value) or value < 0.0
            for value in probabilities.values()
        )
        or not math.isclose(
            sum(probabilities.values()), 1.0, rel_tol=0.0, abs_tol=1e-12
        )
    ):
        raise ValidationError("IDS audit posterior is invalid")
    return -sum(
        probability * math.log(probability)
        for probability in probabilities.values()
        if probability > 0.0
    )


def _binary_entropy(probability: float) -> float:
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValidationError("IDS audit mixture probability is invalid")
    return -sum(
        value * math.log(value)
        for value in (probability, 1.0 - probability)
        if value > 0.0
    )


@dataclass(frozen=True, slots=True)
class MetricEstimate:
    mean: float
    lower_95: float
    upper_95: float

    def __post_init__(self) -> None:
        if (
            any(
                not math.isfinite(value)
                for value in (self.mean, self.lower_95, self.upper_95)
            )
            or self.lower_95 > self.mean
            or self.mean > self.upper_95
        ):
            raise ValidationError("IDS audit estimate is invalid")

    def to_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "lower_95": self.lower_95,
            "upper_95": self.upper_95,
        }


@dataclass(frozen=True, slots=True)
class IDSFailureAuditWorld:
    seed: int
    full_run: dict[str, float]
    quarters: tuple[dict[str, float], ...]
    trace_length: int
    causal_archive_complete: bool

    def __post_init__(self) -> None:
        _validate_seed(self.seed)
        if self.trace_length != ONLINE_INTERACTION_COUNT:
            raise ValidationError("IDS audit trace is incomplete")
        if len(self.quarters) != 4:
            raise ValidationError("IDS audit requires four quarters")
        for metrics in (self.full_run, *self.quarters):
            if set(metrics) != set(_METRIC_NAMES):
                raise ValidationError("IDS audit metric set is incomplete")
            if any(not math.isfinite(value) for value in metrics.values()):
                raise ValidationError("IDS audit metric is non-finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "full_run": dict(self.full_run),
            "quarters": [dict(quarter) for quarter in self.quarters],
            "trace_length": self.trace_length,
            "causal_archive_complete": self.causal_archive_complete,
        }


@dataclass(frozen=True, slots=True)
class IDSFailureAuditReport:
    seeds: tuple[int, ...]
    block_length: int
    sample_count: int
    bootstrap_resamples: int
    bootstrap_seed: int
    full_run: dict[str, MetricEstimate]
    quarters: tuple[dict[str, MetricEstimate], ...]
    worlds: tuple[IDSFailureAuditWorld, ...]
    reward_deficit_replication: str
    model_implied_decision_cost: str
    dominant_disagreement_channel: str
    causal_archive_rate: float
    evidence_level: str = "E1_LOCAL_DIAGNOSTIC"

    def to_dict(self, *, include_worlds: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "experiment": "H50-L13 failure audit",
            "seeds": list(self.seeds),
            "block_length": self.block_length,
            "sample_count": self.sample_count,
            "bootstrap_resamples": self.bootstrap_resamples,
            "bootstrap_seed": self.bootstrap_seed,
            "full_run": {
                name: estimate.to_dict()
                for name, estimate in self.full_run.items()
            },
            "quarters": [
                {
                    name: estimate.to_dict()
                    for name, estimate in quarter.items()
                }
                for quarter in self.quarters
            ],
            "interpretation": {
                "reward_deficit_replication": self.reward_deficit_replication,
                "model_implied_decision_cost": (
                    self.model_implied_decision_cost
                ),
                "dominant_disagreement_channel": (
                    self.dominant_disagreement_channel
                ),
            },
            "causal_archive_rate": self.causal_archive_rate,
            "evidence_level": self.evidence_level,
            "limitations": [
                "This is a diagnostic follow-up, not a confirmatory experiment.",
                "The Q opportunity cost is model-implied, not counterfactual reward.",
                "The three channels are sequential and are not additive "
                "causal effects.",
                "The environment is synthetic, stationary, binary, and tabular.",
                "The result cannot establish consciousness, personhood, AGI, "
                "or a Diana-like mind.",
            ],
        }
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


@dataclass(frozen=True, slots=True)
class _AuditTrace:
    rewards: tuple[float, ...]
    total_disagreement: tuple[float, ...]
    staleness_channel: tuple[float, ...]
    ensemble_channel: tuple[float, ...]
    mixture_channel: tuple[float, ...]
    selected_non_greedy_probability: tuple[float, ...]
    non_degenerate_mixture: tuple[float, ...]
    mixture_entropy: tuple[float, ...]
    opportunity_cost: tuple[float, ...]
    action_information_gain: tuple[float, ...]
    information_ratio: tuple[float, ...]
    order_entropy: tuple[float, ...]
    causal_archive_complete: bool


def _run_candidate_trace(
    seed: int, schedule: Sequence[OnlineEpisode]
) -> _AuditTrace:
    world = LearnedContextWorld(seed)
    agent = InformationDirectedAgent(
        world_id=world.world_id,
        model_seed=seed ^ IDS_MODEL_XOR_MASK,
        action_seed=seed ^ IDS_ACTION_XOR_MASK,
        block_length=IDS_FAILURE_AUDIT_BLOCK_LENGTH,
        sample_count=IDS_POSTERIOR_SAMPLE_COUNT,
    )
    rewards: list[float] = []
    total_disagreement: list[float] = []
    staleness_channel: list[float] = []
    ensemble_channel: list[float] = []
    mixture_channel: list[float] = []
    non_greedy_probability: list[float] = []
    non_degenerate_mixture: list[float] = []
    mixture_entropy: list[float] = []
    opportunity_cost: list[float] = []
    information_gain: list[float] = []
    information_ratio: list[float] = []
    order_entropy: list[float] = []
    block_mean_planner: FiniteHorizonContextPlanner | None = None

    for episode_index, episode in enumerate(schedule, start=1):
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        agent.begin_episode(
            episode_index=episode_index,
            initial_history=episode.initial_history,
        )
        for _ in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            starts_block = agent.block_remaining == 0
            posterior_before = agent.model.order_posterior()
            decision = agent.action()
            if starts_block:
                block_mean_planner = FiniteHorizonContextPlanner(
                    agent.model.mean_model(),
                    horizon=IDS_FAILURE_AUDIT_BLOCK_LENGTH,
                )
            if block_mean_planner is None:
                raise RuntimeError("IDS audit block-mean planner is unavailable")
            if decision.information_ratio is None:
                raise RuntimeError("IDS audit encountered a non-finite ratio")

            history = agent.current_history
            remaining = agent.block_remaining
            current_mean_planner = FiniteHorizonContextPlanner(
                agent.model.mean_model(),
                horizon=IDS_FAILURE_AUDIT_BLOCK_LENGTH,
            )
            block_action = block_mean_planner.action(
                history, remaining=remaining
            )
            current_action = current_mean_planner.action(
                history, remaining=remaining
            )
            ensemble_action = min(
                CONTEXT_ACTIONS,
                key=lambda action: (
                    decision.amber_expected_regret
                    if action == "amber"
                    else decision.violet_expected_regret,
                    CONTEXT_ACTIONS.index(action),
                ),
            )
            current_context = current_mean_planner.model.context_for_history(
                history
            )
            q_gap = current_mean_planner.q_value(
                current_context, current_action, remaining=remaining
            ) - current_mean_planner.q_value(
                current_context, decision.action, remaining=remaining
            )
            if q_gap < -1e-12 or not math.isfinite(q_gap):
                raise RuntimeError("IDS audit opportunity cost is invalid")
            q_gap = max(0.0, q_gap)
            probability = decision.amber_probability
            probability_non_greedy = (
                1.0 - probability
                if ensemble_action == "amber"
                else probability
            )

            total_disagreement.append(float(decision.action != current_action))
            staleness_channel.append(float(block_action != current_action))
            ensemble_channel.append(float(ensemble_action != block_action))
            mixture_channel.append(float(decision.action != ensemble_action))
            non_greedy_probability.append(probability_non_greedy)
            non_degenerate_mixture.append(float(0.0 < probability < 1.0))
            mixture_entropy.append(_binary_entropy(probability))
            opportunity_cost.append(q_gap)
            information_gain.append(decision.information_gain)
            information_ratio.append(decision.information_ratio)
            order_entropy.append(_entropy(posterior_before))

            step = world.step(decision.action)
            agent.observe(
                next_observation=step.observation.observation,
                reward=step.reward,
            )
            rewards.append(float(step.reward))
            if world.current_history_for_evaluator != agent.current_history:
                raise RuntimeError("IDS audit history diverged from evaluator")

    traces = (
        rewards,
        total_disagreement,
        staleness_channel,
        ensemble_channel,
        mixture_channel,
        non_greedy_probability,
        non_degenerate_mixture,
        mixture_entropy,
        opportunity_cost,
        information_gain,
        information_ratio,
        order_entropy,
    )
    if {len(values) for values in traces} != {ONLINE_INTERACTION_COUNT}:
        raise RuntimeError("IDS audit trace is incomplete")
    causal_complete = all(
        set(experience.to_dict()) == OnlineExperience.FIELDS
        for experience in agent.model.archive.items
    ) and len(agent.model.archive.items) == ONLINE_INTERACTION_COUNT
    return _AuditTrace(
        rewards=tuple(rewards),
        total_disagreement=tuple(total_disagreement),
        staleness_channel=tuple(staleness_channel),
        ensemble_channel=tuple(ensemble_channel),
        mixture_channel=tuple(mixture_channel),
        selected_non_greedy_probability=tuple(non_greedy_probability),
        non_degenerate_mixture=tuple(non_degenerate_mixture),
        mixture_entropy=tuple(mixture_entropy),
        opportunity_cost=tuple(opportunity_cost),
        action_information_gain=tuple(information_gain),
        information_ratio=tuple(information_ratio),
        order_entropy=tuple(order_entropy),
        causal_archive_complete=causal_complete,
    )


def _summarize_slice(
    trace: _AuditTrace,
    certainty_rewards: Sequence[float],
    start: int,
    stop: int,
) -> dict[str, float]:
    if not 0 <= start < stop <= ONLINE_INTERACTION_COUNT:
        raise ValidationError("IDS audit summary slice is invalid")
    candidate_reward = _mean(trace.rewards[start:stop])
    certainty_reward = _mean(certainty_rewards[start:stop])
    total = _mean(trace.total_disagreement[start:stop])
    staleness = _mean(trace.staleness_channel[start:stop])
    ensemble = _mean(trace.ensemble_channel[start:stop])
    mixture = _mean(trace.mixture_channel[start:stop])
    costs = trace.opportunity_cost[start:stop]
    disagreement_costs = tuple(
        cost
        for cost, disagrees in zip(
            costs,
            trace.total_disagreement[start:stop],
            strict=True,
        )
        if disagrees == 1.0
    )
    return {
        "candidate_reward": candidate_reward,
        "certainty_equivalent_reward": certainty_reward,
        "candidate_minus_certainty_reward": (
            candidate_reward - certainty_reward
        ),
        "total_disagreement_rate": total,
        "staleness_channel_disagreement_rate": staleness,
        "ensemble_channel_disagreement_rate": ensemble,
        "mixture_channel_disagreement_rate": mixture,
        "mixture_minus_ensemble_disagreement_rate": mixture - ensemble,
        "mixture_minus_staleness_disagreement_rate": mixture - staleness,
        "ensemble_minus_staleness_disagreement_rate": ensemble - staleness,
        "selected_non_greedy_probability": _mean(
            trace.selected_non_greedy_probability[start:stop]
        ),
        "realized_non_greedy_rate": mixture,
        "non_degenerate_mixture_rate": _mean(
            trace.non_degenerate_mixture[start:stop]
        ),
        "mean_mixture_entropy": _mean(trace.mixture_entropy[start:stop]),
        "mean_current_map_q_opportunity_cost": _mean(costs),
        "conditional_current_map_q_opportunity_cost": (
            _mean(disagreement_costs) if disagreement_costs else 0.0
        ),
        "mean_action_information_gain": _mean(
            trace.action_information_gain[start:stop]
        ),
        "mean_information_ratio": _mean(
            trace.information_ratio[start:stop]
        ),
        "mean_order_posterior_entropy": _mean(
            trace.order_entropy[start:stop]
        ),
    }


def run_ids_failure_audit_world(seed: int) -> IDSFailureAuditWorld:
    normalized_seed = _validate_seed(seed)
    schedule = make_online_schedule(normalized_seed)
    candidate = _run_candidate_trace(normalized_seed, schedule)
    certainty = _run_mean_policy(
        normalized_seed,
        schedule,
        resampling_length=IDS_FAILURE_AUDIT_BLOCK_LENGTH,
    )
    certainty_rewards = tuple(float(value) for value in certainty.rewards)
    quarters = tuple(
        _summarize_slice(
            candidate,
            certainty_rewards,
            index * IDS_FAILURE_AUDIT_QUARTER_LENGTH,
            (index + 1) * IDS_FAILURE_AUDIT_QUARTER_LENGTH,
        )
        for index in range(4)
    )
    return IDSFailureAuditWorld(
        seed=normalized_seed,
        full_run=_summarize_slice(
            candidate, certainty_rewards, 0, ONLINE_INTERACTION_COUNT
        ),
        quarters=quarters,
        trace_length=len(candidate.rewards),
        causal_archive_complete=candidate.causal_archive_complete,
    )


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if (
        not sorted_values
        or not 0.0 <= probability <= 1.0
        or any(not math.isfinite(value) for value in sorted_values)
        or tuple(sorted_values) != tuple(sorted(sorted_values))
    ):
        raise ValidationError("IDS audit quantile input is invalid")
    position = probability * (len(sorted_values) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    fraction = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - fraction)
        + sorted_values[upper_index] * fraction
    )


def _bootstrap_estimate(
    values: Sequence[float], *, resamples: int
) -> MetricEstimate:
    if (
        not values
        or any(not math.isfinite(value) for value in values)
        or isinstance(resamples, bool)
        or not isinstance(resamples, int)
        or resamples < 1
    ):
        raise ValidationError("IDS audit bootstrap configuration is invalid")
    rng = random.Random(IDS_FAILURE_AUDIT_BOOTSTRAP_SEED)
    count = len(values)
    bootstrap_means = sorted(
        fmean(values[rng.randrange(count)] for _ in range(count))
        for _ in range(resamples)
    )
    return MetricEstimate(
        mean=fmean(values),
        lower_95=_quantile(bootstrap_means, 0.025),
        upper_95=_quantile(bootstrap_means, 0.975),
    )


def _aggregate_metrics(
    worlds: Sequence[IDSFailureAuditWorld],
    *,
    quarter_index: int | None,
    bootstrap_resamples: int,
) -> dict[str, MetricEstimate]:
    if not worlds:
        raise ValidationError("IDS audit needs at least one world")
    if quarter_index is not None and not 0 <= quarter_index < 4:
        raise ValidationError("IDS audit quarter index is invalid")
    return {
        name: _bootstrap_estimate(
            tuple(
                (
                    world.full_run
                    if quarter_index is None
                    else world.quarters[quarter_index]
                )[name]
                for world in worlds
            ),
            resamples=bootstrap_resamples,
        )
        for name in _METRIC_NAMES
    }


def run_ids_failure_audit(
    seeds: Iterable[int] = IDS_FAILURE_AUDIT_SEEDS,
    *,
    bootstrap_resamples: int = IDS_FAILURE_AUDIT_BOOTSTRAP_RESAMPLES,
) -> IDSFailureAuditReport:
    normalized_seeds = _normalize_seeds(seeds)
    if (
        isinstance(bootstrap_resamples, bool)
        or not isinstance(bootstrap_resamples, int)
        or bootstrap_resamples < 1
    ):
        raise ValidationError("IDS audit bootstrap resamples must be positive")
    worlds = tuple(
        run_ids_failure_audit_world(seed) for seed in normalized_seeds
    )
    full_run = _aggregate_metrics(
        worlds,
        quarter_index=None,
        bootstrap_resamples=bootstrap_resamples,
    )
    quarters = tuple(
        _aggregate_metrics(
            worlds,
            quarter_index=index,
            bootstrap_resamples=bootstrap_resamples,
        )
        for index in range(4)
    )
    reward_interval = full_run["candidate_minus_certainty_reward"]
    cost_interval = full_run["mean_current_map_q_opportunity_cost"]
    mixture_ensemble = full_run[
        "mixture_minus_ensemble_disagreement_rate"
    ]
    mixture_staleness = full_run[
        "mixture_minus_staleness_disagreement_rate"
    ]
    ensemble_staleness = full_run[
        "ensemble_minus_staleness_disagreement_rate"
    ]
    if (
        mixture_ensemble.lower_95 > 0.0
        and mixture_staleness.lower_95 > 0.0
    ):
        dominant = "mixture"
    elif (
        mixture_ensemble.upper_95 < 0.0
        and ensemble_staleness.lower_95 > 0.0
    ):
        dominant = "ensemble"
    elif (
        mixture_staleness.upper_95 < 0.0
        and ensemble_staleness.upper_95 < 0.0
    ):
        dominant = "staleness"
    else:
        dominant = "unresolved"
    return IDSFailureAuditReport(
        seeds=normalized_seeds,
        block_length=IDS_FAILURE_AUDIT_BLOCK_LENGTH,
        sample_count=IDS_POSTERIOR_SAMPLE_COUNT,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=IDS_FAILURE_AUDIT_BOOTSTRAP_SEED,
        full_run=full_run,
        quarters=quarters,
        worlds=worlds,
        reward_deficit_replication=(
            "replicated"
            if reward_interval.upper_95 < 0.0
            else "not_resolved"
        ),
        model_implied_decision_cost=(
            "resolved_above_zero"
            if cost_interval.lower_95 > 0.0
            else "not_resolved"
        ),
        dominant_disagreement_channel=dominant,
        causal_archive_rate=fmean(
            float(world.causal_archive_complete) for world in worlds
        ),
    )


def _parse_seeds(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(
            int(part.strip()) for part in raw.split(",") if part.strip()
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "IDS audit seeds must be integers"
        ) from error
    if not values:
        raise argparse.ArgumentTypeError("provide at least one IDS audit seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the pre-registered H50-L13 failure audit."
    )
    parser.add_argument(
        "--seeds", type=_parse_seeds, default=IDS_FAILURE_AUDIT_SEEDS
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=IDS_FAILURE_AUDIT_BOOTSTRAP_RESAMPLES,
    )
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    report = run_ids_failure_audit(
        args.seeds, bootstrap_resamples=args.bootstrap_resamples
    )
    print(
        json.dumps(
            report.to_dict(include_worlds=args.details),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
