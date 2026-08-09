"""Registered evaluator for Darwin H50-L12 online Bayesian control."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import random
from statistics import fmean
from typing import Any, Iterable, Sequence

from .kernel import DarwinKernelV50
from .learned_context_lab import (
    CONTEXT_ACTIONS,
    MAX_CONTEXT_ORDER,
    FullHistory,
    LearnedContextWorld,
    LearnedContextWorldSpecification,
    append_observation,
    validate_full_history,
)
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .online_posterior_lab import (
    ONLINE_ENVIRONMENT_EPISODE_LENGTH,
    FiniteHorizonContextPlanner,
    OnlineBayesianModel,
    OnlineExperience,
    OnlinePosteriorAgent,
    ProbabilityTableModel,
    true_probability_model,
)


ONLINE_POSTERIOR_DEVELOPMENT_SEEDS = tuple(range(22000, 22032))
ONLINE_POSTERIOR_FINAL_SEEDS = tuple(range(22100, 22200))
ONLINE_RESAMPLING_LENGTH_CANDIDATES = (8, 16, 32, 64)
ONLINE_EPISODE_COUNT = 40
ONLINE_INTERACTION_COUNT = (
    ONLINE_EPISODE_COUNT * ONLINE_ENVIRONMENT_EPISODE_LENGTH
)
ONLINE_FINAL_QUARTER_COUNT = 320
ONLINE_EXPLORE_THEN_COMMIT_STEPS = 512
ONLINE_EPSILON = 0.10

ONLINE_SCHEDULE_XOR_MASK = 0x12D67
ONLINE_CANDIDATE_POLICY_XOR_MASK = 0xA110C
ONLINE_FIXED_ORDER_POLICY_XOR_MASK = 0xF15E5
ONLINE_EPSILON_ACTION_XOR_MASK = 0xE0510
ONLINE_COMMIT_ACTION_XOR_MASK = 0xC0517
ONLINE_RANDOM_ACTION_XOR_MASK = 0xA4D0B

LOCAL_ONLINE_POSTERIOR_EVALUATOR = (
    "darwin_v50.online_posterior_evaluation.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class OnlineEpisode:
    initial_history: FullHistory
    episode_seed: int

    def __post_init__(self) -> None:
        validate_full_history(self.initial_history, "online initial history")
        if (
            isinstance(self.episode_seed, bool)
            or not isinstance(self.episode_seed, int)
            or self.episode_seed < 0
        ):
            raise ValidationError("online episode seed must be non-negative")


@dataclass(frozen=True, slots=True)
class OnlineDevelopmentScore:
    resampling_length: int
    mean_reward: float
    mean_combined_model_error: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "resampling_length": self.resampling_length,
            "mean_reward": self.mean_reward,
            "mean_combined_model_error": self.mean_combined_model_error,
        }


@dataclass(frozen=True, slots=True)
class OnlineDevelopmentSelection:
    seeds: tuple[int, ...]
    candidate_scores: tuple[OnlineDevelopmentScore, ...]
    selected_resampling_length: int

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_resampling_length": self.selected_resampling_length,
        }
        if include_scores:
            result["candidate_scores"] = [
                score.to_dict() for score in self.candidate_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class OnlineWorldResult:
    seed: int
    true_order: int
    map_order: int
    order_correct: bool
    true_order_posterior_mass: float
    transition_probability_error: float
    reward_probability_error: float
    candidate_mean_reward: float
    candidate_final_quarter_reward: float
    certainty_equivalent_mean_reward: float
    epsilon_greedy_mean_reward: float
    explore_then_commit_mean_reward: float
    fixed_order_five_mean_reward: float
    random_mean_reward: float
    oracle_mean_reward: float
    oracle_final_quarter_reward: float
    bayesian_regret: float
    mean_information_gain_per_episode: float
    simultaneous_baseline_win: bool
    archive_retained: bool
    snapshot_round_trip_exact: bool
    causal_field_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class OnlineSuiteReport:
    development: OnlineDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[OnlineWorldResult, ...]
    final_world_count: int
    unique_world_count: int
    true_order_counts: dict[int, int]
    map_order_counts: dict[int, int]
    order_confusion: dict[str, int]
    candidate_mean_reward: float
    candidate_final_quarter_reward: float
    certainty_equivalent_mean_reward: float
    epsilon_greedy_mean_reward: float
    explore_then_commit_mean_reward: float
    fixed_order_five_mean_reward: float
    random_mean_reward: float
    oracle_mean_reward: float
    oracle_final_quarter_reward: float
    candidate_oracle_total_reward_ratio: float
    candidate_oracle_final_quarter_reward_ratio: float
    improvement_vs_certainty_equivalent: float
    improvement_vs_epsilon_greedy: float
    improvement_vs_explore_then_commit: float
    improvement_vs_fixed_order_five: float
    improvement_vs_random: float
    simultaneous_baseline_world_win_rate: float
    exact_order_recovery_rate: float
    mean_true_order_posterior_mass: float
    transition_probability_error: float
    reward_probability_error: float
    mean_bayesian_regret: float
    mean_information_gain_per_episode: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    causal_field_rate: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_total_oracle_ratio: float = 0.75,
        minimum_final_quarter_oracle_ratio: float = 0.85,
        minimum_improvement_vs_certainty: float = 0.010,
        minimum_improvement_vs_epsilon: float = 0.005,
        minimum_improvement_vs_commit: float = 0.015,
        minimum_improvement_vs_fixed_order: float = 0.010,
        minimum_improvement_vs_random: float = 0.050,
        minimum_simultaneous_win_rate: float = 0.60,
        minimum_order_recovery: float = 0.70,
        minimum_true_order_mass: float = 0.65,
        maximum_transition_error: float = 0.08,
        maximum_reward_error: float = 0.08,
        minimum_archive_rate: float = 1.0,
        minimum_snapshot_rate: float = 1.0,
        minimum_causal_field_rate: float = 1.0,
    ) -> bool:
        return (
            self.candidate_oracle_total_reward_ratio
            >= minimum_total_oracle_ratio
            and self.candidate_oracle_final_quarter_reward_ratio
            >= minimum_final_quarter_oracle_ratio
            and self.improvement_vs_certainty_equivalent
            >= minimum_improvement_vs_certainty
            and self.improvement_vs_epsilon_greedy
            >= minimum_improvement_vs_epsilon
            and self.improvement_vs_explore_then_commit
            >= minimum_improvement_vs_commit
            and self.improvement_vs_fixed_order_five
            >= minimum_improvement_vs_fixed_order
            and self.improvement_vs_random >= minimum_improvement_vs_random
            and self.simultaneous_baseline_world_win_rate
            >= minimum_simultaneous_win_rate
            and self.exact_order_recovery_rate >= minimum_order_recovery
            and self.mean_true_order_posterior_mass
            >= minimum_true_order_mass
            and self.transition_probability_error <= maximum_transition_error
            and self.reward_probability_error <= maximum_reward_error
            and self.archive_retention_rate >= minimum_archive_rate
            and self.snapshot_round_trip_rate >= minimum_snapshot_rate
            and self.causal_field_rate >= minimum_causal_field_rate
        )

    def to_dict(
        self,
        *,
        include_development_scores: bool = True,
        include_worlds: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
            if field not in {"development", "worlds", "limitations"}
        }
        result["development"] = self.development.to_dict(
            include_scores=include_development_scores
        )
        result["final_seeds"] = list(self.final_seeds)
        result["limitations"] = list(self.limitations)
        result["passes_regression_criteria"] = (
            self.passes_regression_criteria()
        )
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


@dataclass(slots=True)
class _PolicyRun:
    rewards: tuple[bool, ...]
    model: OnlineBayesianModel | None = None
    archive_retained: bool = False
    snapshot_round_trip_exact: bool = False
    causal_field_complete: bool = False

    @property
    def mean_reward(self) -> float:
        return fmean(float(value) for value in self.rewards)

    @property
    def final_quarter_reward(self) -> float:
        return fmean(
            float(value)
            for value in self.rewards[-ONLINE_FINAL_QUARTER_COUNT:]
        )


def _normalize_seeds(
    seeds: Iterable[int], *, field: str
) -> tuple[int, ...]:
    result = tuple(seeds)
    if (
        not result
        or len(set(result)) != len(result)
        or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in result)
    ):
        raise ValidationError(f"{field} seeds must be unique integers")
    return result


def _normalize_lengths(lengths: Sequence[int]) -> tuple[int, ...]:
    result = tuple(lengths)
    if (
        not result
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
        or any(
            isinstance(length, bool)
            or not isinstance(length, int)
            or length < 1
            for length in result
        )
    ):
        raise ValidationError(
            "resampling lengths must be unique increasing integers"
        )
    return result


def make_online_schedule(seed: int) -> tuple[OnlineEpisode, ...]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValidationError("online world seed must be an integer")
    rng = random.Random(seed ^ ONLINE_SCHEDULE_XOR_MASK)
    return tuple(
        OnlineEpisode(
            initial_history=tuple(
                bool(rng.getrandbits(1))
                for _ in range(MAX_CONTEXT_ORDER)
            ),  # type: ignore[arg-type]
            episode_seed=rng.getrandbits(63),
        )
        for _ in range(ONLINE_EPISODE_COUNT)
    )


def _assert_world_history(
    world: LearnedContextWorld, history: FullHistory
) -> None:
    if world.current_history_for_evaluator != history:
        raise RuntimeError("online observed history diverged from evaluator")


def _run_posterior_policy(
    seed: int,
    schedule: Sequence[OnlineEpisode],
    *,
    resampling_length: int,
    policy_seed_mask: int,
    fixed_order: int | None = None,
    check_snapshot: bool = False,
) -> _PolicyRun:
    world = LearnedContextWorld(seed)
    agent = OnlinePosteriorAgent(
        world_id=world.world_id,
        policy_seed=seed ^ policy_seed_mask,
        resampling_length=resampling_length,
        fixed_order=fixed_order,
    )
    rewards: list[bool] = []
    midpoint_snapshot_exact = not check_snapshot
    midpoint_archive_retained = not check_snapshot
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
            if check_snapshot and len(rewards) == ONLINE_INTERACTION_COUNT // 2:
                snapshot = agent.to_snapshot()
                restored = OnlinePosteriorAgent.from_snapshot(snapshot)
                restored_initial_exact = restored.to_snapshot() == snapshot
                midpoint_archive_retained = (
                    restored.model.archive.items == agent.model.archive.items
                    and len(restored.model.archive.items)
                    == ONLINE_INTERACTION_COUNT // 2
                )
                original_action = agent.action()
                restored_action = restored.action()
                midpoint_snapshot_exact = (
                    restored_initial_exact and original_action == restored_action
                )
                action = original_action
            else:
                action = agent.action()
            step = world.step(action)
            agent.observe(
                next_observation=step.observation.observation,
                reward=step.reward,
            )
            rewards.append(step.reward)
            _assert_world_history(world, agent.current_history)
    if check_snapshot:
        final_snapshot = agent.to_snapshot()
        final_restored = OnlinePosteriorAgent.from_snapshot(final_snapshot)
        snapshot_exact = (
            midpoint_snapshot_exact
            and final_restored.to_snapshot() == final_snapshot
            and final_restored.model.archive.items == agent.model.archive.items
        )
        archive_retained = (
            midpoint_archive_retained
            and len(agent.model.archive.items) == ONLINE_INTERACTION_COUNT
            and final_restored.model.archive.items == agent.model.archive.items
        )
    else:
        snapshot_exact = False
        archive_retained = (
            len(agent.model.archive.items) == ONLINE_INTERACTION_COUNT
        )
    causal_fields = all(
        set(item.to_dict()) == OnlineExperience.FIELDS
        for item in agent.model.archive.items
    )
    return _PolicyRun(
        rewards=tuple(rewards),
        model=agent.model,
        archive_retained=archive_retained,
        snapshot_round_trip_exact=snapshot_exact,
        causal_field_complete=causal_fields,
    )


class _MeanController:
    def __init__(
        self,
        *,
        world_id: str,
        resampling_length: int,
        epsilon: float = 0.0,
        action_seed: int | None = None,
    ) -> None:
        self.model = OnlineBayesianModel(world_id=world_id)
        self.resampling_length = resampling_length
        self.epsilon = epsilon
        self._rng = random.Random(action_seed) if action_seed is not None else None
        self._planner: FiniteHorizonContextPlanner | None = None
        self._remaining = 0

    def action(self, history: FullHistory) -> str:
        if self._remaining == 0:
            self._planner = FiniteHorizonContextPlanner(
                self.model.mean_model(), horizon=self.resampling_length
            )
            self._remaining = self.resampling_length
        if self._planner is None:
            raise RuntimeError("mean controller planner is unavailable")
        planned = self._planner.action(history, remaining=self._remaining)
        if (
            self._rng is not None
            and self._rng.random() < self.epsilon
        ):
            return self._rng.choice(CONTEXT_ACTIONS)
        return planned

    def observe(self, experience: OnlineExperience) -> None:
        self.model.update(experience)
        self._remaining -= 1


def _run_mean_policy(
    seed: int,
    schedule: Sequence[OnlineEpisode],
    *,
    resampling_length: int,
    epsilon: float = 0.0,
) -> _PolicyRun:
    world = LearnedContextWorld(seed)
    controller = _MeanController(
        world_id=world.world_id,
        resampling_length=resampling_length,
        epsilon=epsilon,
        action_seed=(seed ^ ONLINE_EPSILON_ACTION_XOR_MASK),
    )
    rewards: list[bool] = []
    for episode_index, episode in enumerate(schedule, start=1):
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        history = episode.initial_history
        for step_index in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            action = controller.action(history)
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
            controller.observe(experience)
            history = experience.next_history
            rewards.append(step.reward)
            _assert_world_history(world, history)
    return _PolicyRun(rewards=tuple(rewards), model=controller.model)


def _run_explore_then_commit(
    seed: int,
    schedule: Sequence[OnlineEpisode],
    *,
    resampling_length: int,
) -> _PolicyRun:
    world = LearnedContextWorld(seed)
    model = OnlineBayesianModel(world_id=world.world_id)
    rng = random.Random(seed ^ ONLINE_COMMIT_ACTION_XOR_MASK)
    frozen_model: ProbabilityTableModel | None = None
    planner: FiniteHorizonContextPlanner | None = None
    remaining = 0
    rewards: list[bool] = []
    for episode_index, episode in enumerate(schedule, start=1):
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        history = episode.initial_history
        for step_index in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            sequence = len(rewards) + 1
            if sequence <= ONLINE_EXPLORE_THEN_COMMIT_STEPS:
                action = rng.choice(CONTEXT_ACTIONS)
            else:
                if frozen_model is None:
                    frozen_model = model.mean_model()
                if remaining == 0:
                    planner = FiniteHorizonContextPlanner(
                        frozen_model, horizon=resampling_length
                    )
                    remaining = resampling_length
                if planner is None:
                    raise RuntimeError("commit planner is unavailable")
                action = planner.action(history, remaining=remaining)
            step = world.step(action)
            experience = OnlineExperience(
                world_id=world.world_id,
                sequence=sequence,
                episode_index=episode_index,
                step_index=step_index,
                history=history,
                action=action,
                next_observation=step.observation.observation,
                reward=step.reward,
            )
            if sequence <= ONLINE_EXPLORE_THEN_COMMIT_STEPS:
                model.update(experience)
                if sequence == ONLINE_EXPLORE_THEN_COMMIT_STEPS:
                    frozen_model = model.mean_model()
            else:
                remaining -= 1
            history = experience.next_history
            rewards.append(step.reward)
            _assert_world_history(world, history)
    return _PolicyRun(rewards=tuple(rewards), model=model)


def _run_random_policy(
    seed: int, schedule: Sequence[OnlineEpisode]
) -> _PolicyRun:
    world = LearnedContextWorld(seed)
    rng = random.Random(seed ^ ONLINE_RANDOM_ACTION_XOR_MASK)
    rewards: list[bool] = []
    for episode in schedule:
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        for _ in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            rewards.append(world.step(rng.choice(CONTEXT_ACTIONS)).reward)
    return _PolicyRun(rewards=tuple(rewards))


def _run_oracle_policy(
    seed: int,
    schedule: Sequence[OnlineEpisode],
    *,
    resampling_length: int,
) -> _PolicyRun:
    world = LearnedContextWorld(seed)
    model = true_probability_model(world.specification)
    planner = FiniteHorizonContextPlanner(
        model, horizon=resampling_length
    )
    remaining = 0
    rewards: list[bool] = []
    for episode in schedule:
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        history = episode.initial_history
        for _ in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            if remaining == 0:
                remaining = resampling_length
            action = planner.action(history, remaining=remaining)
            step = world.step(action)
            history = append_observation(
                history, step.observation.observation
            )
            rewards.append(step.reward)
            remaining -= 1
            _assert_world_history(world, history)
    return _PolicyRun(rewards=tuple(rewards))


def _world_signature(seed: int) -> tuple[object, ...]:
    specification = LearnedContextWorldSpecification.from_seed(seed)
    return (
        specification.true_order,
        tuple(rule.preferred_next_bits for rule in specification.dynamics),
        tuple(
            (target.context, target.rewarded_action)
            for target in specification.reward_contexts
        ),
    )


def select_online_resampling_length(
    seeds: Iterable[int] = ONLINE_POSTERIOR_DEVELOPMENT_SEEDS,
    *,
    candidates: Sequence[int] = ONLINE_RESAMPLING_LENGTH_CANDIDATES,
) -> OnlineDevelopmentSelection:
    normalized_seeds = _normalize_seeds(seeds, field="development")
    lengths = _normalize_lengths(candidates)
    rewards = {length: [] for length in lengths}
    errors = {length: [] for length in lengths}
    for seed in normalized_seeds:
        schedule = make_online_schedule(seed)
        specification = LearnedContextWorldSpecification.from_seed(seed)
        for length in lengths:
            run = _run_posterior_policy(
                seed,
                schedule,
                resampling_length=length,
                policy_seed_mask=ONLINE_CANDIDATE_POLICY_XOR_MASK,
            )
            if run.model is None:
                raise RuntimeError("candidate model is missing")
            transition_error, reward_error = run.model.probability_errors(
                specification
            )
            rewards[length].append(run.mean_reward)
            errors[length].append(transition_error + reward_error)
    scores = tuple(
        OnlineDevelopmentScore(
            resampling_length=length,
            mean_reward=fmean(rewards[length]),
            mean_combined_model_error=fmean(errors[length]),
        )
        for length in lengths
    )
    selected = min(
        scores,
        key=lambda score: (
            -score.mean_reward,
            score.mean_combined_model_error,
            score.resampling_length,
        ),
    )
    return OnlineDevelopmentSelection(
        seeds=normalized_seeds,
        candidate_scores=scores,
        selected_resampling_length=selected.resampling_length,
    )


def run_online_world(
    seed: int, *, selected_resampling_length: int
) -> OnlineWorldResult:
    schedule = make_online_schedule(seed)
    candidate = _run_posterior_policy(
        seed,
        schedule,
        resampling_length=selected_resampling_length,
        policy_seed_mask=ONLINE_CANDIDATE_POLICY_XOR_MASK,
        check_snapshot=True,
    )
    certainty = _run_mean_policy(
        seed,
        schedule,
        resampling_length=selected_resampling_length,
    )
    epsilon = _run_mean_policy(
        seed,
        schedule,
        resampling_length=selected_resampling_length,
        epsilon=ONLINE_EPSILON,
    )
    commit = _run_explore_then_commit(
        seed,
        schedule,
        resampling_length=selected_resampling_length,
    )
    fixed_order = _run_posterior_policy(
        seed,
        schedule,
        resampling_length=selected_resampling_length,
        policy_seed_mask=ONLINE_FIXED_ORDER_POLICY_XOR_MASK,
        fixed_order=5,
    )
    random_run = _run_random_policy(seed, schedule)
    oracle = _run_oracle_policy(
        seed,
        schedule,
        resampling_length=selected_resampling_length,
    )
    if candidate.model is None:
        raise RuntimeError("candidate model is missing")
    specification = LearnedContextWorldSpecification.from_seed(seed)
    posterior = candidate.model.order_posterior()
    transition_error, reward_error = candidate.model.probability_errors(
        specification
    )
    gains = candidate.model.information_gains
    if len(gains) != ONLINE_INTERACTION_COUNT:
        raise RuntimeError("candidate information-gain trace is incomplete")
    episode_gain = fmean(
        sum(
            gains[
                index * ONLINE_ENVIRONMENT_EPISODE_LENGTH:
                (index + 1) * ONLINE_ENVIRONMENT_EPISODE_LENGTH
            ]
        )
        for index in range(ONLINE_EPISODE_COUNT)
    )
    candidate_total = sum(candidate.rewards)
    oracle_total = sum(oracle.rewards)
    return OnlineWorldResult(
        seed=seed,
        true_order=specification.true_order,
        map_order=candidate.model.map_order,
        order_correct=(candidate.model.map_order == specification.true_order),
        true_order_posterior_mass=posterior[specification.true_order],
        transition_probability_error=transition_error,
        reward_probability_error=reward_error,
        candidate_mean_reward=candidate.mean_reward,
        candidate_final_quarter_reward=candidate.final_quarter_reward,
        certainty_equivalent_mean_reward=certainty.mean_reward,
        epsilon_greedy_mean_reward=epsilon.mean_reward,
        explore_then_commit_mean_reward=commit.mean_reward,
        fixed_order_five_mean_reward=fixed_order.mean_reward,
        random_mean_reward=random_run.mean_reward,
        oracle_mean_reward=oracle.mean_reward,
        oracle_final_quarter_reward=oracle.final_quarter_reward,
        bayesian_regret=float(oracle_total - candidate_total),
        mean_information_gain_per_episode=episode_gain,
        simultaneous_baseline_win=(
            candidate_total > sum(certainty.rewards)
            and candidate_total > sum(epsilon.rewards)
            and candidate_total > sum(commit.rewards)
            and candidate_total > sum(fixed_order.rewards)
        ),
        archive_retained=candidate.archive_retained,
        snapshot_round_trip_exact=candidate.snapshot_round_trip_exact,
        causal_field_complete=candidate.causal_field_complete,
    )


def run_online_suite(
    *,
    development_seeds: Iterable[int] = ONLINE_POSTERIOR_DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = ONLINE_POSTERIOR_FINAL_SEEDS,
    candidates: Sequence[int] = ONLINE_RESAMPLING_LENGTH_CANDIDATES,
) -> OnlineSuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds, field="development"
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("development and final seeds must be disjoint")
    development = select_online_resampling_length(
        development_seed_tuple, candidates=candidates
    )
    worlds = tuple(
        run_online_world(
            seed,
            selected_resampling_length=(
                development.selected_resampling_length
            ),
        )
        for seed in final_seed_tuple
    )
    means = {
        field: fmean(getattr(world, field) for world in worlds)
        for field in (
            "candidate_mean_reward",
            "candidate_final_quarter_reward",
            "certainty_equivalent_mean_reward",
            "epsilon_greedy_mean_reward",
            "explore_then_commit_mean_reward",
            "fixed_order_five_mean_reward",
            "random_mean_reward",
            "oracle_mean_reward",
            "oracle_final_quarter_reward",
        )
    }
    candidate_mean = means["candidate_mean_reward"]
    candidate_final = means["candidate_final_quarter_reward"]
    oracle_mean = means["oracle_mean_reward"]
    oracle_final = means["oracle_final_quarter_reward"]
    true_counts = {
        order: sum(world.true_order == order for world in worlds)
        for order in (2, 3, 4, 5)
    }
    map_counts = {
        order: sum(world.map_order == order for world in worlds)
        for order in (1, 2, 3, 4, 5)
    }
    confusion = {
        f"{true_order}->{map_order}": sum(
            world.true_order == true_order and world.map_order == map_order
            for world in worlds
        )
        for true_order in (2, 3, 4, 5)
        for map_order in (1, 2, 3, 4, 5)
        if any(
            world.true_order == true_order and world.map_order == map_order
            for world in worlds
        )
    }
    return OnlineSuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        unique_world_count=len({_world_signature(seed) for seed in final_seed_tuple}),
        true_order_counts=true_counts,
        map_order_counts=map_counts,
        order_confusion=confusion,
        candidate_mean_reward=candidate_mean,
        candidate_final_quarter_reward=candidate_final,
        certainty_equivalent_mean_reward=means[
            "certainty_equivalent_mean_reward"
        ],
        epsilon_greedy_mean_reward=means["epsilon_greedy_mean_reward"],
        explore_then_commit_mean_reward=means[
            "explore_then_commit_mean_reward"
        ],
        fixed_order_five_mean_reward=means["fixed_order_five_mean_reward"],
        random_mean_reward=means["random_mean_reward"],
        oracle_mean_reward=oracle_mean,
        oracle_final_quarter_reward=oracle_final,
        candidate_oracle_total_reward_ratio=(
            candidate_mean / oracle_mean if oracle_mean > 0.0 else 0.0
        ),
        candidate_oracle_final_quarter_reward_ratio=(
            candidate_final / oracle_final if oracle_final > 0.0 else 0.0
        ),
        improvement_vs_certainty_equivalent=(
            candidate_mean - means["certainty_equivalent_mean_reward"]
        ),
        improvement_vs_epsilon_greedy=(
            candidate_mean - means["epsilon_greedy_mean_reward"]
        ),
        improvement_vs_explore_then_commit=(
            candidate_mean - means["explore_then_commit_mean_reward"]
        ),
        improvement_vs_fixed_order_five=(
            candidate_mean - means["fixed_order_five_mean_reward"]
        ),
        improvement_vs_random=(candidate_mean - means["random_mean_reward"]),
        simultaneous_baseline_world_win_rate=fmean(
            float(world.simultaneous_baseline_win) for world in worlds
        ),
        exact_order_recovery_rate=fmean(
            float(world.order_correct) for world in worlds
        ),
        mean_true_order_posterior_mass=fmean(
            world.true_order_posterior_mass for world in worlds
        ),
        transition_probability_error=fmean(
            world.transition_probability_error for world in worlds
        ),
        reward_probability_error=fmean(
            world.reward_probability_error for world in worlds
        ),
        mean_bayesian_regret=fmean(world.bayesian_regret for world in worlds),
        mean_information_gain_per_episode=fmean(
            world.mean_information_gain_per_episode for world in worlds
        ),
        archive_retention_rate=fmean(
            float(world.archive_retained) for world in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(world.snapshot_round_trip_exact) for world in worlds
        ),
        causal_field_rate=fmean(
            float(world.causal_field_complete) for world in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Resampling length is selected only on development seeds "
            f"{development_seed_tuple[0]}-{development_seed_tuple[-1]}. "
            "Final metrics use disjoint supplied seeds "
            f"{final_seed_tuple[0]}-{final_seed_tuple[-1]}, 40 paired "
            "32-action episodes per world, chosen-action feedback, separate "
            "policy streams, and precomputed action-indexed exogenous draws."
        ),
        limitations=(
            "The environment is synthetic, stationary, binary, and tabular.",
            "Candidate context orders one through five are supplied by the experiment design.",
            "Transition and reward outcomes are modeled as conditionally independent.",
            "The exact planner is practical only because the state and action spaces are tiny.",
            "No learned state transfers between worlds.",
            "The oracle comparison does not make the benchmark a proof of a PSRL regret bound.",
            "Snapshots are structurally replayed but not cryptographically authenticated.",
            "The local evaluator cannot provide independent E3 evidence.",
            "Success would not imply perception, language grounding, consciousness, personhood, AGI, or a Diana-like brain.",
        ),
    )


def record_online_result(
    kernel: DarwinKernelV50, report: OnlineSuiteReport
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"online-posterior:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description="Online posterior sampling reduces registered regret",
        evidence_source=LOCAL_ONLINE_POSTERIOR_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-online-posterior-sampling-control",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_resampling_length": (
                report.development.selected_resampling_length
            ),
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_ONLINE_POSTERIOR_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": all_criteria_satisfied,
            "candidate_oracle_total_reward_ratio": (
                report.candidate_oracle_total_reward_ratio
            ),
            "candidate_oracle_final_quarter_reward_ratio": (
                report.candidate_oracle_final_quarter_reward_ratio
            ),
            "improvement_vs_certainty_equivalent": (
                report.improvement_vs_certainty_equivalent
            ),
            "improvement_vs_epsilon_greedy": (
                report.improvement_vs_epsilon_greedy
            ),
            "improvement_vs_explore_then_commit": (
                report.improvement_vs_explore_then_commit
            ),
            "improvement_vs_fixed_order_five": (
                report.improvement_vs_fixed_order_five
            ),
            "improvement_vs_random": report.improvement_vs_random,
            "simultaneous_baseline_world_win_rate": (
                report.simultaneous_baseline_world_win_rate
            ),
            "exact_order_recovery_rate": report.exact_order_recovery_rate,
            "mean_true_order_posterior_mass": (
                report.mean_true_order_posterior_mass
            ),
            "transition_probability_error": (
                report.transition_probability_error
            ),
            "reward_probability_error": report.reward_probability_error,
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
            "causal_field_rate": report.causal_field_rate,
        },
    )


def report_with_online_metrics(
    report: OnlineSuiteReport, **changes: Any
) -> OnlineSuiteReport:
    return replace(report, **changes)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Darwin H50-L12 online posterior-sampling benchmark."
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=ONLINE_POSTERIOR_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=ONLINE_POSTERIOR_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args(argv)
    if args.development_only:
        selection = select_online_resampling_length(args.development_seeds)
        print(json.dumps(selection.to_dict(), indent=2, sort_keys=True))
        return 0
    report = run_online_suite(
        development_seeds=args.development_seeds,
        final_seeds=args.final_seeds,
    )
    print(
        json.dumps(
            report.to_dict(
                include_development_scores=args.development_scores,
                include_worlds=args.details,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
