"""Pre-registered failure audit for Darwin H50-L12.

This module diagnoses how posterior sampling changes decisions in the small
registered tabular benchmark.  It does not implement a replacement controller
or provide confirmatory evidence for a new capability.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import random
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from .learned_context_lab import CONTEXT_ACTIONS, LearnedContextWorld
from .models import ValidationError
from .online_posterior_evaluation import (
    ONLINE_CANDIDATE_POLICY_XOR_MASK,
    ONLINE_EPISODE_COUNT,
    ONLINE_INTERACTION_COUNT,
    OnlineEpisode,
    make_online_schedule,
)
from .online_posterior_lab import (
    ONLINE_ENVIRONMENT_EPISODE_LENGTH,
    FiniteHorizonContextPlanner,
    OnlineBayesianModel,
    OnlineExperience,
    OnlinePosteriorAgent,
)


POSTERIOR_AUDIT_SEEDS = tuple(range(23200, 23232))
POSTERIOR_AUDIT_RESAMPLING_LENGTH = 32
POSTERIOR_AUDIT_QUARTER_LENGTH = 320
POSTERIOR_AUDIT_BOOTSTRAP_RESAMPLES = 10_000
POSTERIOR_AUDIT_BOOTSTRAP_SEED = 0xA17D17


_METRIC_NAMES = (
    "candidate_reward",
    "certainty_equivalent_reward",
    "candidate_minus_certainty_reward",
    "candidate_vs_map_disagreement_rate",
    "order_channel_disagreement_rate",
    "parameter_channel_disagreement_rate",
    "parameter_minus_order_disagreement_rate",
    "sampled_order_map_mismatch_rate",
    "mean_map_q_opportunity_cost",
    "conditional_map_q_opportunity_cost",
    "mean_order_posterior_entropy",
    "mean_order_information_gain",
)


def _validate_seed(seed: object) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValidationError("audit seed must be an integer")
    return seed


def _normalize_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    normalized = tuple(_validate_seed(seed) for seed in seeds)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValidationError("audit seeds must be non-empty and unique")
    return normalized


def _mean(values: Sequence[float]) -> float:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValidationError("audit metric values must be finite and non-empty")
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
        raise ValidationError("order posterior is invalid for audit entropy")
    return -sum(
        probability * math.log(probability)
        for probability in probabilities.values()
        if probability > 0.0
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
            raise ValidationError("audit estimate is invalid")

    def to_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "lower_95": self.lower_95,
            "upper_95": self.upper_95,
        }


@dataclass(frozen=True, slots=True)
class PosteriorAuditWorld:
    seed: int
    full_run: dict[str, float]
    quarters: tuple[dict[str, float], ...]
    trace_length: int
    causal_archive_complete: bool

    def __post_init__(self) -> None:
        _validate_seed(self.seed)
        if self.trace_length != ONLINE_INTERACTION_COUNT:
            raise ValidationError("audit trace length is incomplete")
        if len(self.quarters) != 4:
            raise ValidationError("audit requires exactly four quarters")
        for metrics in (self.full_run, *self.quarters):
            if set(metrics) != set(_METRIC_NAMES):
                raise ValidationError("audit metric set is incomplete")
            if any(not math.isfinite(value) for value in metrics.values()):
                raise ValidationError("audit metrics must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "full_run": dict(self.full_run),
            "quarters": [dict(quarter) for quarter in self.quarters],
            "trace_length": self.trace_length,
            "causal_archive_complete": self.causal_archive_complete,
        }


@dataclass(frozen=True, slots=True)
class PosteriorAuditReport:
    seeds: tuple[int, ...]
    resampling_length: int
    bootstrap_resamples: int
    bootstrap_seed: int
    full_run: dict[str, MetricEstimate]
    quarters: tuple[dict[str, MetricEstimate], ...]
    worlds: tuple[PosteriorAuditWorld, ...]
    reward_deficit_replication: str
    model_implied_sampling_cost: str
    dominant_action_change_channel: str
    causal_archive_rate: float
    evidence_level: str = "E1_LOCAL_DIAGNOSTIC"

    def to_dict(self, *, include_worlds: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "experiment": "H50-L12 failure audit",
            "seeds": list(self.seeds),
            "resampling_length": self.resampling_length,
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
                "model_implied_sampling_cost": self.model_implied_sampling_cost,
                "dominant_action_change_channel": (
                    self.dominant_action_change_channel
                ),
            },
            "causal_archive_rate": self.causal_archive_rate,
            "evidence_level": self.evidence_level,
            "limitations": [
                "This is a diagnostic follow-up, not a confirmatory experiment.",
                "The Q opportunity cost is model-implied, not counterfactual reward.",
                "Order and parameter channels are sequential, not additive causal effects.",
                "The environment is synthetic, stationary, binary, and tabular.",
                "The result cannot establish consciousness, personhood, AGI, or a Diana-like mind.",
            ],
        }
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


@dataclass(frozen=True, slots=True)
class _CandidateTrace:
    rewards: tuple[float, ...]
    candidate_vs_map: tuple[float, ...]
    order_channel: tuple[float, ...]
    parameter_channel: tuple[float, ...]
    sampled_order_map_mismatch: tuple[float, ...]
    opportunity_cost: tuple[float, ...]
    order_entropy: tuple[float, ...]
    information_gain: tuple[float, ...]
    causal_archive_complete: bool


def _assert_world_history(world: LearnedContextWorld, history: object) -> None:
    if world.current_history_for_evaluator != history:
        raise RuntimeError("audit history diverged from evaluator state")


def _run_candidate_trace(
    seed: int, schedule: Sequence[OnlineEpisode]
) -> _CandidateTrace:
    world = LearnedContextWorld(seed)
    agent = OnlinePosteriorAgent(
        world_id=world.world_id,
        policy_seed=seed ^ ONLINE_CANDIDATE_POLICY_XOR_MASK,
        resampling_length=POSTERIOR_AUDIT_RESAMPLING_LENGTH,
    )
    rewards: list[float] = []
    candidate_vs_map: list[float] = []
    order_channel: list[float] = []
    parameter_channel: list[float] = []
    order_mismatch: list[float] = []
    opportunity_cost: list[float] = []
    order_entropy: list[float] = []
    information_gain: list[float] = []
    map_planner: FiniteHorizonContextPlanner | None = None
    sampled_order_mean_planner: FiniteHorizonContextPlanner | None = None
    block_map_order: int | None = None

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
            candidate_action = agent.action()
            if starts_block:
                sampled_order = agent.sampled_order
                if sampled_order is None:
                    raise RuntimeError("candidate did not expose sampled order")
                block_map_order = agent.model.map_order
                map_planner = FiniteHorizonContextPlanner(
                    agent.model.mean_model(order=block_map_order),
                    horizon=POSTERIOR_AUDIT_RESAMPLING_LENGTH,
                )
                sampled_order_mean_planner = FiniteHorizonContextPlanner(
                    agent.model.mean_model(order=sampled_order),
                    horizon=POSTERIOR_AUDIT_RESAMPLING_LENGTH,
                )
            if (
                map_planner is None
                or sampled_order_mean_planner is None
                or block_map_order is None
                or agent.sampled_order is None
            ):
                raise RuntimeError("audit shadow planners are unavailable")

            remaining = agent.block_remaining
            history = agent.current_history
            map_action = map_planner.action(history, remaining=remaining)
            sampled_order_mean_action = sampled_order_mean_planner.action(
                history, remaining=remaining
            )
            map_context = map_planner.model.context_for_history(history)
            q_gap = map_planner.q_value(
                map_context, map_action, remaining=remaining
            ) - map_planner.q_value(
                map_context, candidate_action, remaining=remaining
            )
            if q_gap < -1e-12 or not math.isfinite(q_gap):
                raise RuntimeError("audit opportunity cost is invalid")
            q_gap = max(0.0, q_gap)

            sampled_order = agent.sampled_order
            candidate_vs_map.append(float(candidate_action != map_action))
            order_channel.append(
                float(sampled_order_mean_action != map_action)
            )
            parameter_channel.append(
                float(candidate_action != sampled_order_mean_action)
            )
            order_mismatch.append(float(sampled_order != block_map_order))
            opportunity_cost.append(q_gap)
            order_entropy.append(_entropy(posterior_before))

            step = world.step(candidate_action)
            gain = agent.observe(
                next_observation=step.observation.observation,
                reward=step.reward,
            )
            rewards.append(float(step.reward))
            information_gain.append(gain)
            _assert_world_history(world, agent.current_history)

    trace_lengths = {
        len(values)
        for values in (
            rewards,
            candidate_vs_map,
            order_channel,
            parameter_channel,
            order_mismatch,
            opportunity_cost,
            order_entropy,
            information_gain,
        )
    }
    if trace_lengths != {ONLINE_INTERACTION_COUNT}:
        raise RuntimeError("candidate audit trace is incomplete")
    causal_complete = all(
        set(experience.to_dict()) == OnlineExperience.FIELDS
        for experience in agent.model.archive.items
    ) and len(agent.model.archive.items) == ONLINE_INTERACTION_COUNT
    return _CandidateTrace(
        rewards=tuple(rewards),
        candidate_vs_map=tuple(candidate_vs_map),
        order_channel=tuple(order_channel),
        parameter_channel=tuple(parameter_channel),
        sampled_order_map_mismatch=tuple(order_mismatch),
        opportunity_cost=tuple(opportunity_cost),
        order_entropy=tuple(order_entropy),
        information_gain=tuple(information_gain),
        causal_archive_complete=causal_complete,
    )


def _run_certainty_equivalent(
    seed: int, schedule: Sequence[OnlineEpisode]
) -> tuple[float, ...]:
    world = LearnedContextWorld(seed)
    model = OnlineBayesianModel(world_id=world.world_id)
    planner: FiniteHorizonContextPlanner | None = None
    remaining = 0
    rewards: list[float] = []
    for episode_index, episode in enumerate(schedule, start=1):
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        history = episode.initial_history
        for step_index in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            if remaining == 0:
                planner = FiniteHorizonContextPlanner(
                    model.mean_model(),
                    horizon=POSTERIOR_AUDIT_RESAMPLING_LENGTH,
                )
                remaining = POSTERIOR_AUDIT_RESAMPLING_LENGTH
            if planner is None:
                raise RuntimeError("certainty-equivalent planner is unavailable")
            action = planner.action(history, remaining=remaining)
            step = world.step(action)
            experience = OnlineExperience(
                world_id=world.world_id,
                sequence=len(rewards) + 1,
                episode_index=episode_index,
                step_index=step_index,
                history=history,
                action=action,
                next_observation=step.observation.observation,
                reward=step.reward,
            )
            model.update(experience)
            history = experience.next_history
            remaining -= 1
            rewards.append(float(step.reward))
            _assert_world_history(world, history)
    if len(rewards) != ONLINE_INTERACTION_COUNT:
        raise RuntimeError("certainty-equivalent audit trace is incomplete")
    return tuple(rewards)


def _summarize_slice(
    trace: _CandidateTrace,
    certainty_rewards: Sequence[float],
    start: int,
    stop: int,
) -> dict[str, float]:
    if not 0 <= start < stop <= ONLINE_INTERACTION_COUNT:
        raise ValidationError("audit summary slice is invalid")
    candidate_reward = _mean(trace.rewards[start:stop])
    certainty_reward = _mean(certainty_rewards[start:stop])
    candidate_vs_map = _mean(trace.candidate_vs_map[start:stop])
    order_channel = _mean(trace.order_channel[start:stop])
    parameter_channel = _mean(trace.parameter_channel[start:stop])
    costs = trace.opportunity_cost[start:stop]
    disagreement_costs = tuple(
        cost
        for cost, disagrees in zip(
            costs,
            trace.candidate_vs_map[start:stop],
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
        "candidate_vs_map_disagreement_rate": candidate_vs_map,
        "order_channel_disagreement_rate": order_channel,
        "parameter_channel_disagreement_rate": parameter_channel,
        "parameter_minus_order_disagreement_rate": (
            parameter_channel - order_channel
        ),
        "sampled_order_map_mismatch_rate": _mean(
            trace.sampled_order_map_mismatch[start:stop]
        ),
        "mean_map_q_opportunity_cost": _mean(costs),
        "conditional_map_q_opportunity_cost": (
            _mean(disagreement_costs) if disagreement_costs else 0.0
        ),
        "mean_order_posterior_entropy": _mean(
            trace.order_entropy[start:stop]
        ),
        "mean_order_information_gain": _mean(
            trace.information_gain[start:stop]
        ),
    }


def run_posterior_audit_world(seed: int) -> PosteriorAuditWorld:
    normalized_seed = _validate_seed(seed)
    schedule = make_online_schedule(normalized_seed)
    if len(schedule) != ONLINE_EPISODE_COUNT:
        raise RuntimeError("audit schedule is incomplete")
    candidate = _run_candidate_trace(normalized_seed, schedule)
    certainty = _run_certainty_equivalent(normalized_seed, schedule)
    quarters = tuple(
        _summarize_slice(
            candidate,
            certainty,
            index * POSTERIOR_AUDIT_QUARTER_LENGTH,
            (index + 1) * POSTERIOR_AUDIT_QUARTER_LENGTH,
        )
        for index in range(4)
    )
    return PosteriorAuditWorld(
        seed=normalized_seed,
        full_run=_summarize_slice(
            candidate, certainty, 0, ONLINE_INTERACTION_COUNT
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
        raise ValidationError("bootstrap quantile input is invalid")
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
        raise ValidationError("bootstrap configuration is invalid")
    rng = random.Random(POSTERIOR_AUDIT_BOOTSTRAP_SEED)
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
    worlds: Sequence[PosteriorAuditWorld],
    *,
    quarter_index: int | None,
    bootstrap_resamples: int,
) -> dict[str, MetricEstimate]:
    if not worlds:
        raise ValidationError("audit needs at least one world")
    if quarter_index is not None and not 0 <= quarter_index < 4:
        raise ValidationError("audit quarter index is invalid")
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


def run_posterior_failure_audit(
    seeds: Iterable[int] = POSTERIOR_AUDIT_SEEDS,
    *,
    bootstrap_resamples: int = POSTERIOR_AUDIT_BOOTSTRAP_RESAMPLES,
) -> PosteriorAuditReport:
    normalized_seeds = _normalize_seeds(seeds)
    if (
        isinstance(bootstrap_resamples, bool)
        or not isinstance(bootstrap_resamples, int)
        or bootstrap_resamples < 1
    ):
        raise ValidationError("bootstrap resamples must be positive")
    worlds = tuple(run_posterior_audit_world(seed) for seed in normalized_seeds)
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
    cost_interval = full_run["mean_map_q_opportunity_cost"]
    channel_interval = full_run[
        "parameter_minus_order_disagreement_rate"
    ]
    if channel_interval.lower_95 > 0.0:
        dominant_channel = "parameter"
    elif channel_interval.upper_95 < 0.0:
        dominant_channel = "order"
    else:
        dominant_channel = "unresolved"
    return PosteriorAuditReport(
        seeds=normalized_seeds,
        resampling_length=POSTERIOR_AUDIT_RESAMPLING_LENGTH,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=POSTERIOR_AUDIT_BOOTSTRAP_SEED,
        full_run=full_run,
        quarters=quarters,
        worlds=worlds,
        reward_deficit_replication=(
            "replicated"
            if reward_interval.upper_95 < 0.0
            else "not_resolved"
        ),
        model_implied_sampling_cost=(
            "resolved_above_zero"
            if cost_interval.lower_95 > 0.0
            else "not_resolved"
        ),
        dominant_action_change_channel=dominant_channel,
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
        raise argparse.ArgumentTypeError("audit seeds must be integers") from error
    if not values:
        raise argparse.ArgumentTypeError("provide at least one audit seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the pre-registered H50-L12 failure audit."
    )
    parser.add_argument(
        "--seeds", type=_parse_seeds, default=POSTERIOR_AUDIT_SEEDS
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=POSTERIOR_AUDIT_BOOTSTRAP_RESAMPLES,
    )
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    report = run_posterior_failure_audit(
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
