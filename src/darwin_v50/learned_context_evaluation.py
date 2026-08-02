"""Held-out benchmark for Darwin H50-L11 learned context and reward."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from itertools import product
import json
import random
from statistics import fmean
from typing import Any, Callable, Iterable, Sequence

from .kernel import DarwinKernelV50
from .learned_context_lab import (
    CONTEXT_ACTIONS,
    CONTEXT_DISCOUNT,
    CONTEXT_ORDER_CANDIDATES,
    MAX_CONTEXT_ORDER,
    CausalContextArchive,
    ContextValuePlanner,
    FullHistory,
    LearnedContextExperience,
    LearnedContextModel,
    LearnedContextWorld,
    LearnedContextWorldSpecification,
    TrueContextPlanningModel,
    append_observation,
    validate_full_history,
)
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)


LEARNED_CONTEXT_DEVELOPMENT_SEEDS = tuple(range(19000, 19032))
LEARNED_CONTEXT_FINAL_SEEDS = tuple(range(19100, 19200))
LEARNED_CONTEXT_BUDGET_CANDIDATES = (256, 384, 512)
LEARNED_CONTEXT_DEVELOPMENT_EPISODES = 16
LEARNED_CONTEXT_FINAL_EPISODES = 32
LEARNED_CONTEXT_EVALUATION_HORIZON = 20
LEARNED_CONTEXT_TRAINING_XOR_MASK = 0xD3A19
LEARNED_CONTEXT_ACTION_XOR_MASK = 0xE81F2
LEARNED_CONTEXT_EPISODE_XOR_MASK = 0x119B3
LEARNED_CONTEXT_EVALUATION_XOR_MASK = 0x6C2D7
LEARNED_CONTEXT_RANDOM_POLICY_XOR_MASK = 0xF15A9
LOCAL_LEARNED_CONTEXT_EVALUATOR = (
    "darwin_v50.learned_context_evaluation.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class LearnedContextEpisode:
    initial_history: FullHistory
    episode_seed: int

    def __post_init__(self) -> None:
        validate_full_history(
            self.initial_history,
            "episode initial history",
        )
        if (
            isinstance(self.episode_seed, bool)
            or not isinstance(self.episode_seed, int)
            or self.episode_seed < 0
        ):
            raise ValidationError("episode seed must be non-negative")


@dataclass(frozen=True, slots=True)
class LearnedContextBudgetScore:
    budget: int
    mean_discounted_return: float
    mean_model_error: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "mean_discounted_return": self.mean_discounted_return,
            "mean_model_error": self.mean_model_error,
        }


@dataclass(frozen=True, slots=True)
class LearnedContextDevelopmentSelection:
    seeds: tuple[int, ...]
    candidate_scores: tuple[LearnedContextBudgetScore, ...]
    selected_budget: int

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_budget": self.selected_budget,
        }
        if include_scores:
            result["candidate_scores"] = [
                item.to_dict() for item in self.candidate_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class LearnedContextWorldResult:
    seed: int
    true_order: int
    selected_order: int
    order_correct: bool
    transition_probability_error: float
    reward_probability_error: float
    candidate_return: float
    reactive_return: float
    maximum_depth_return: float
    myopic_return: float
    rotated_reward_return: float
    random_return: float
    oracle_return: float
    simultaneous_ablation_win: bool
    archive_retained: bool
    snapshot_round_trip_exact: bool
    model_frozen_during_evaluation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "true_order": self.true_order,
            "selected_order": self.selected_order,
            "order_correct": self.order_correct,
            "transition_probability_error": (
                self.transition_probability_error
            ),
            "reward_probability_error": self.reward_probability_error,
            "candidate_return": self.candidate_return,
            "reactive_return": self.reactive_return,
            "maximum_depth_return": self.maximum_depth_return,
            "myopic_return": self.myopic_return,
            "rotated_reward_return": self.rotated_reward_return,
            "random_return": self.random_return,
            "oracle_return": self.oracle_return,
            "simultaneous_ablation_win": (
                self.simultaneous_ablation_win
            ),
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": (
                self.snapshot_round_trip_exact
            ),
            "model_frozen_during_evaluation": (
                self.model_frozen_during_evaluation
            ),
        }


@dataclass(frozen=True, slots=True)
class LearnedContextSuiteReport:
    development: LearnedContextDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[LearnedContextWorldResult, ...]
    final_world_count: int
    unique_world_count: int
    true_order_counts: dict[int, int]
    selected_order_counts: dict[int, int]
    order_confusion: dict[str, int]
    exact_order_recovery_rate: float
    transition_probability_error: float
    reward_probability_error: float
    candidate_return: float
    reactive_return: float
    maximum_depth_return: float
    myopic_return: float
    rotated_reward_return: float
    random_return: float
    oracle_return: float
    candidate_oracle_return_ratio: float
    improvement_vs_reactive: float
    improvement_vs_maximum_depth: float
    improvement_vs_myopic: float
    improvement_vs_rotated_reward: float
    improvement_vs_random: float
    simultaneous_ablation_world_win_rate: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    frozen_model_rate: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_exact_order_recovery_rate: float = 0.70,
        maximum_transition_probability_error: float = 0.08,
        maximum_reward_probability_error: float = 0.08,
        minimum_candidate_oracle_return_ratio: float = 0.80,
        minimum_improvement_vs_reactive: float = 0.25,
        minimum_improvement_vs_maximum_depth: float = 0.10,
        minimum_improvement_vs_myopic: float = 0.20,
        minimum_improvement_vs_rotated_reward: float = 0.25,
        minimum_improvement_vs_random: float = 0.40,
        minimum_simultaneous_ablation_world_win_rate: float = 0.70,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
        minimum_frozen_model_rate: float = 1.0,
    ) -> bool:
        return (
            self.exact_order_recovery_rate
            >= minimum_exact_order_recovery_rate
            and self.transition_probability_error
            <= maximum_transition_probability_error
            and self.reward_probability_error
            <= maximum_reward_probability_error
            and self.candidate_oracle_return_ratio
            >= minimum_candidate_oracle_return_ratio
            and self.improvement_vs_reactive
            >= minimum_improvement_vs_reactive
            and self.improvement_vs_maximum_depth
            >= minimum_improvement_vs_maximum_depth
            and self.improvement_vs_myopic
            >= minimum_improvement_vs_myopic
            and self.improvement_vs_rotated_reward
            >= minimum_improvement_vs_rotated_reward
            and self.improvement_vs_random
            >= minimum_improvement_vs_random
            and self.simultaneous_ablation_world_win_rate
            >= minimum_simultaneous_ablation_world_win_rate
            and self.archive_retention_rate
            >= minimum_archive_retention_rate
            and self.snapshot_round_trip_rate
            >= minimum_snapshot_round_trip_rate
            and self.frozen_model_rate >= minimum_frozen_model_rate
        )

    def to_dict(
        self,
        *,
        include_development_scores: bool = True,
        include_worlds: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "development": self.development.to_dict(
                include_scores=include_development_scores
            ),
            "final_seeds": list(self.final_seeds),
            "final_world_count": self.final_world_count,
            "unique_world_count": self.unique_world_count,
            "true_order_counts": self.true_order_counts,
            "selected_order_counts": self.selected_order_counts,
            "order_confusion": self.order_confusion,
            "exact_order_recovery_rate": (
                self.exact_order_recovery_rate
            ),
            "transition_probability_error": (
                self.transition_probability_error
            ),
            "reward_probability_error": (
                self.reward_probability_error
            ),
            "candidate_return": self.candidate_return,
            "reactive_return": self.reactive_return,
            "maximum_depth_return": self.maximum_depth_return,
            "myopic_return": self.myopic_return,
            "rotated_reward_return": self.rotated_reward_return,
            "random_return": self.random_return,
            "oracle_return": self.oracle_return,
            "candidate_oracle_return_ratio": (
                self.candidate_oracle_return_ratio
            ),
            "improvement_vs_reactive": self.improvement_vs_reactive,
            "improvement_vs_maximum_depth": (
                self.improvement_vs_maximum_depth
            ),
            "improvement_vs_myopic": self.improvement_vs_myopic,
            "improvement_vs_rotated_reward": (
                self.improvement_vs_rotated_reward
            ),
            "improvement_vs_random": self.improvement_vs_random,
            "simultaneous_ablation_world_win_rate": (
                self.simultaneous_ablation_world_win_rate
            ),
            "archive_retention_rate": self.archive_retention_rate,
            "snapshot_round_trip_rate": self.snapshot_round_trip_rate,
            "frozen_model_rate": self.frozen_model_rate,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
            "passes_regression_criteria": (
                self.passes_regression_criteria()
            ),
        }
        if include_worlds:
            result["worlds"] = [item.to_dict() for item in self.worlds]
        return result


def _normalize_seeds(
    seeds: Iterable[int],
    *,
    field: str,
) -> tuple[int, ...]:
    result = tuple(seeds)
    if (
        not result
        or len(set(result)) != len(result)
        or any(
            isinstance(seed, bool) or not isinstance(seed, int)
            for seed in result
        )
    ):
        raise ValidationError(f"{field} seeds must be unique integers")
    return result


def _normalize_budgets(
    budgets: Sequence[int],
) -> tuple[int, ...]:
    result = tuple(budgets)
    if (
        not result
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 10
            for value in result
        )
    ):
        raise ValidationError(
            "budget candidates must be unique increasing integers"
        )
    return result


def collect_learned_context_trace(
    seed: int,
    *,
    budget: int,
) -> tuple[CausalContextArchive, LearnedContextWorld]:
    if (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or budget < 10
    ):
        raise ValidationError("context training budget is invalid")
    history_rng = random.Random(
        seed ^ LEARNED_CONTEXT_TRAINING_XOR_MASK
    )
    initial_history: FullHistory = tuple(
        bool(history_rng.getrandbits(1))
        for _ in range(MAX_CONTEXT_ORDER)
    )  # type: ignore[assignment]
    world = LearnedContextWorld(seed)
    world.reset(
        initial_history=initial_history,
        max_steps=budget,
        episode_seed=seed ^ LEARNED_CONTEXT_EPISODE_XOR_MASK,
    )
    action_rng = random.Random(
        seed ^ LEARNED_CONTEXT_ACTION_XOR_MASK
    )
    archive = CausalContextArchive()
    history = initial_history
    trace_id = f"{world.world_id}:training:{budget}"
    for sequence in range(1, budget + 1):
        action = action_rng.choice(CONTEXT_ACTIONS)
        step = world.step(action)
        archive.observe(
            LearnedContextExperience(
                world_id=world.world_id,
                trace_id=trace_id,
                sequence=sequence,
                history=history,
                action=action,
                next_observation=step.observation.observation,
                reward=step.reward,
            )
        )
        history = append_observation(
            history,
            step.observation.observation,
        )
    return archive, world


def _archive_prefix(
    archive: Sequence[LearnedContextExperience],
    budget: int,
) -> tuple[LearnedContextExperience, ...]:
    if not 10 <= budget <= len(archive):
        raise ValidationError("context prefix budget is invalid")
    return tuple(archive[:budget])


def make_learned_context_episodes(
    seed: int,
    *,
    count: int,
) -> tuple[LearnedContextEpisode, ...]:
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
    ):
        raise ValidationError("context episode count must be positive")
    rng = random.Random(seed ^ LEARNED_CONTEXT_EVALUATION_XOR_MASK)
    return tuple(
        LearnedContextEpisode(
            initial_history=tuple(
                bool(rng.getrandbits(1))
                for _ in range(MAX_CONTEXT_ORDER)
            ),  # type: ignore[arg-type]
            episode_seed=rng.getrandbits(63),
        )
        for _ in range(count)
    )


def _run_policy_episode(
    seed: int,
    episode: LearnedContextEpisode,
    chooser: Callable[[FullHistory], str],
) -> float:
    world = LearnedContextWorld(seed)
    world.reset(
        initial_history=episode.initial_history,
        max_steps=LEARNED_CONTEXT_EVALUATION_HORIZON,
        episode_seed=episode.episode_seed,
    )
    history = episode.initial_history
    discounted_return = 0.0
    discount = 1.0
    for _ in range(LEARNED_CONTEXT_EVALUATION_HORIZON):
        action = chooser(history)
        if action not in CONTEXT_ACTIONS:
            raise ValidationError("context policy returned unknown action")
        step = world.step(action)
        discounted_return += discount * float(step.reward)
        discount *= CONTEXT_DISCOUNT
        history = append_observation(
            history,
            step.observation.observation,
        )
        if history != world.current_history_for_evaluator:
            raise RuntimeError(
                "observed context history diverged from evaluator"
            )
    return discounted_return


def _mean_policy_return(
    seed: int,
    episodes: Sequence[LearnedContextEpisode],
    chooser_factory: Callable[
        [int, LearnedContextEpisode],
        Callable[[FullHistory], str],
    ],
) -> float:
    return fmean(
        _run_policy_episode(
            seed,
            episode,
            chooser_factory(index, episode),
        )
        for index, episode in enumerate(episodes, start=1)
    )


def _planner_factory(
    planner: ContextValuePlanner,
) -> Callable[
    [int, LearnedContextEpisode],
    Callable[[FullHistory], str],
]:
    return lambda _index, _episode: planner.action


def _myopic_factory(
    model: LearnedContextModel,
) -> Callable[
    [int, LearnedContextEpisode],
    Callable[[FullHistory], str],
]:
    def factory(
        _index: int,
        _episode: LearnedContextEpisode,
    ) -> Callable[[FullHistory], str]:
        def choose(history: FullHistory) -> str:
            context = model.context_for_history(history)
            return max(
                CONTEXT_ACTIONS,
                key=lambda action: (
                    model.reward_probability(context, action),
                    -CONTEXT_ACTIONS.index(action),
                ),
            )

        return choose

    return factory


def _random_factory(
    seed: int,
) -> Callable[
    [int, LearnedContextEpisode],
    Callable[[FullHistory], str],
]:
    def factory(
        index: int,
        episode: LearnedContextEpisode,
    ) -> Callable[[FullHistory], str]:
        rng = random.Random(
            seed
            ^ episode.episode_seed
            ^ (index * LEARNED_CONTEXT_RANDOM_POLICY_XOR_MASK)
        )
        return lambda _history: rng.choice(CONTEXT_ACTIONS)

    return factory


def model_probability_errors(
    model: LearnedContextModel,
    specification: LearnedContextWorldSpecification,
) -> tuple[float, float]:
    transition_errors: list[float] = []
    reward_errors: list[float] = []
    for raw in product((False, True), repeat=MAX_CONTEXT_ORDER):
        history: FullHistory = raw  # type: ignore[assignment]
        context = model.context_for_history(history)
        for action in CONTEXT_ACTIONS:
            transition_errors.append(
                abs(
                    model.transition_probability(context, action)
                    - specification.transition_probability(
                        history,
                        action,
                    )
                )
            )
            reward_errors.append(
                abs(
                    model.reward_probability(context, action)
                    - specification.reward_probability(
                        history,
                        action,
                    )
                )
            )
    return fmean(transition_errors), fmean(reward_errors)


def select_learned_context_budget(
    seeds: Iterable[int] = LEARNED_CONTEXT_DEVELOPMENT_SEEDS,
    *,
    budget_candidates: Sequence[int] = (
        LEARNED_CONTEXT_BUDGET_CANDIDATES
    ),
) -> LearnedContextDevelopmentSelection:
    normalized_seeds = _normalize_seeds(seeds, field="development")
    budgets = _normalize_budgets(budget_candidates)
    returns: dict[int, list[float]] = {
        budget: [] for budget in budgets
    }
    errors: dict[int, list[float]] = {
        budget: [] for budget in budgets
    }
    maximum_budget = max(budgets)
    for seed in normalized_seeds:
        archive, world = collect_learned_context_trace(
            seed,
            budget=maximum_budget,
        )
        episodes = make_learned_context_episodes(
            seed,
            count=LEARNED_CONTEXT_DEVELOPMENT_EPISODES,
        )
        for budget in budgets:
            model = LearnedContextModel.fit(
                _archive_prefix(archive.items, budget)
            )
            planner = ContextValuePlanner(model)
            returns[budget].append(
                _mean_policy_return(
                    seed,
                    episodes,
                    _planner_factory(planner),
                )
            )
            transition_error, reward_error = model_probability_errors(
                model,
                world.specification,
            )
            errors[budget].append(
                transition_error + reward_error
            )
    scores = tuple(
        LearnedContextBudgetScore(
            budget=budget,
            mean_discounted_return=fmean(returns[budget]),
            mean_model_error=fmean(errors[budget]),
        )
        for budget in budgets
    )
    selected = min(
        scores,
        key=lambda item: (
            -item.mean_discounted_return,
            item.mean_model_error,
            item.budget,
        ),
    )
    return LearnedContextDevelopmentSelection(
        seeds=normalized_seeds,
        candidate_scores=scores,
        selected_budget=selected.budget,
    )


def run_learned_context_world(
    seed: int,
    *,
    selected_budget: int,
) -> LearnedContextWorldResult:
    archive, training_world = collect_learned_context_trace(
        seed,
        budget=selected_budget,
    )
    model = LearnedContextModel.fit(archive.items)
    reactive_model = LearnedContextModel.fit(
        archive.items,
        fixed_order=1,
    )
    maximum_model = LearnedContextModel.fit(
        archive.items,
        fixed_order=5,
    )
    candidate_planner = ContextValuePlanner(model)
    reactive_planner = ContextValuePlanner(reactive_model)
    maximum_planner = ContextValuePlanner(maximum_model)
    rotated_planner = ContextValuePlanner(model, reward_rotation=1)
    oracle_planner = ContextValuePlanner(
        TrueContextPlanningModel(training_world.specification)
    )
    episodes = make_learned_context_episodes(
        seed,
        count=LEARNED_CONTEXT_FINAL_EPISODES,
    )

    expected_archive = model.archive
    snapshot = model.to_snapshot()
    restored = LearnedContextModel.from_snapshot(snapshot)
    probe_history = expected_archive[-1].next_history
    snapshot_exact = (
        restored.to_snapshot() == snapshot
        and restored.archive == expected_archive
        and ContextValuePlanner(restored).action(probe_history)
        == candidate_planner.action(probe_history)
    )
    archive_retained = (
        len(expected_archive) == selected_budget
        and restored.archive == expected_archive
    )

    candidate_return = _mean_policy_return(
        seed,
        episodes,
        _planner_factory(candidate_planner),
    )
    reactive_return = _mean_policy_return(
        seed,
        episodes,
        _planner_factory(reactive_planner),
    )
    maximum_return = _mean_policy_return(
        seed,
        episodes,
        _planner_factory(maximum_planner),
    )
    myopic_return = _mean_policy_return(
        seed,
        episodes,
        _myopic_factory(model),
    )
    rotated_return = _mean_policy_return(
        seed,
        episodes,
        _planner_factory(rotated_planner),
    )
    random_return = _mean_policy_return(
        seed,
        episodes,
        _random_factory(seed),
    )
    oracle_return = _mean_policy_return(
        seed,
        episodes,
        _planner_factory(oracle_planner),
    )
    transition_error, reward_error = model_probability_errors(
        model,
        training_world.specification,
    )
    return LearnedContextWorldResult(
        seed=seed,
        true_order=training_world.specification.true_order,
        selected_order=model.selected_order,
        order_correct=(
            model.selected_order
            == training_world.specification.true_order
        ),
        transition_probability_error=transition_error,
        reward_probability_error=reward_error,
        candidate_return=candidate_return,
        reactive_return=reactive_return,
        maximum_depth_return=maximum_return,
        myopic_return=myopic_return,
        rotated_reward_return=rotated_return,
        random_return=random_return,
        oracle_return=oracle_return,
        simultaneous_ablation_win=(
            candidate_return > reactive_return
            and (
                candidate_return > maximum_return
                or (
                    model.selected_order == MAX_CONTEXT_ORDER
                    and training_world.specification.true_order
                    == MAX_CONTEXT_ORDER
                    and candidate_return >= maximum_return
                )
            )
            and candidate_return > myopic_return
            and candidate_return > rotated_return
        ),
        archive_retained=archive_retained,
        snapshot_round_trip_exact=snapshot_exact,
        model_frozen_during_evaluation=(
            model.to_snapshot() == snapshot
        ),
    )


def run_learned_context_suite(
    *,
    development_seeds: Iterable[int] = (
        LEARNED_CONTEXT_DEVELOPMENT_SEEDS
    ),
    final_seeds: Iterable[int] = LEARNED_CONTEXT_FINAL_SEEDS,
    budget_candidates: Sequence[int] = (
        LEARNED_CONTEXT_BUDGET_CANDIDATES
    ),
) -> LearnedContextSuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds,
        field="development",
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("development and final seeds must be disjoint")
    development = select_learned_context_budget(
        development_seed_tuple,
        budget_candidates=budget_candidates,
    )
    worlds = tuple(
        run_learned_context_world(
            seed,
            selected_budget=development.selected_budget,
        )
        for seed in final_seed_tuple
    )
    candidate_return = fmean(item.candidate_return for item in worlds)
    reactive_return = fmean(item.reactive_return for item in worlds)
    maximum_return = fmean(
        item.maximum_depth_return for item in worlds
    )
    myopic_return = fmean(item.myopic_return for item in worlds)
    rotated_return = fmean(
        item.rotated_reward_return for item in worlds
    )
    random_return = fmean(item.random_return for item in worlds)
    oracle_return = fmean(item.oracle_return for item in worlds)
    true_counts = {
        order: sum(item.true_order == order for item in worlds)
        for order in (2, 3, 4, 5)
    }
    selected_counts = {
        order: sum(item.selected_order == order for item in worlds)
        for order in CONTEXT_ORDER_CANDIDATES
    }
    confusion = {
        f"{true_order}->{selected_order}": sum(
            item.true_order == true_order
            and item.selected_order == selected_order
            for item in worlds
        )
        for true_order in (2, 3, 4, 5)
        for selected_order in CONTEXT_ORDER_CANDIDATES
        if any(
            item.true_order == true_order
            and item.selected_order == selected_order
            for item in worlds
        )
    }
    signatures = {
        (
            tuple(
                item.preferred_next_bits
                for item in LearnedContextWorldSpecification.from_seed(
                    world.seed
                ).dynamics
            ),
            tuple(
                (
                    item.context,
                    item.rewarded_action,
                )
                for item in LearnedContextWorldSpecification.from_seed(
                    world.seed
                ).reward_contexts
            ),
        )
        for world in worlds
    }
    return LearnedContextSuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        unique_world_count=len(signatures),
        true_order_counts=true_counts,
        selected_order_counts=selected_counts,
        order_confusion=confusion,
        exact_order_recovery_rate=fmean(
            float(item.order_correct) for item in worlds
        ),
        transition_probability_error=fmean(
            item.transition_probability_error for item in worlds
        ),
        reward_probability_error=fmean(
            item.reward_probability_error for item in worlds
        ),
        candidate_return=candidate_return,
        reactive_return=reactive_return,
        maximum_depth_return=maximum_return,
        myopic_return=myopic_return,
        rotated_reward_return=rotated_return,
        random_return=random_return,
        oracle_return=oracle_return,
        candidate_oracle_return_ratio=(
            candidate_return / oracle_return
            if oracle_return > 0.0
            else 0.0
        ),
        improvement_vs_reactive=candidate_return - reactive_return,
        improvement_vs_maximum_depth=(
            candidate_return - maximum_return
        ),
        improvement_vs_myopic=candidate_return - myopic_return,
        improvement_vs_rotated_reward=(
            candidate_return - rotated_return
        ),
        improvement_vs_random=candidate_return - random_return,
        simultaneous_ablation_world_win_rate=(
            sum(item.simultaneous_ablation_win for item in worlds)
            / len(worlds)
        ),
        archive_retention_rate=fmean(
            float(item.archive_retained) for item in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(item.snapshot_round_trip_exact) for item in worlds
        ),
        frozen_model_rate=fmean(
            float(item.model_frozen_during_evaluation)
            for item in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Training budget is selected only on development seeds "
            f"{development_seed_tuple[0]}-{development_seed_tuple[-1]}. "
            "Final metrics use disjoint supplied seeds "
            f"{final_seed_tuple[0]}-{final_seed_tuple[-1]}, 32 paired "
            "20-step episodes per world, chosen-action feedback, and "
            "frozen learned models."
        ),
        limitations=(
            "The process is synthetic, binary, tabular, and has maximum order five.",
            "The candidate selects one global suffix order rather than learning a variable context tree.",
            "Candidate orders one through five are supplied by the experiment design.",
            "Training uses a human-defined uniform random exploration policy.",
            "World dynamics and reward locations do not change after training.",
            "There is no transfer of a learned model between worlds.",
            "The reward signal is directly observed and binary.",
            "The learned planner uses exact tabular value iteration.",
            "There is no model-free learned-policy baseline in this experiment.",
            "Snapshots are structurally replayed but not cryptographically authenticated.",
            "The local evaluator cannot provide independent E3 evidence.",
            "Success would not imply perception, language, consciousness, emotion, personhood, AGI, or a Diana-like brain.",
        ),
    )


def record_learned_context_result(
    kernel: DarwinKernelV50,
    report: LearnedContextSuiteReport,
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"learned-context-reward:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Selected context order and learned reward support planning"
        ),
        evidence_source=LOCAL_LEARNED_CONTEXT_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-learned-context-and-reward-planning",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_budget": report.development.selected_budget,
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_LEARNED_CONTEXT_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                all_criteria_satisfied
            ),
            "exact_order_recovery_rate": (
                report.exact_order_recovery_rate
            ),
            "transition_probability_error": (
                report.transition_probability_error
            ),
            "reward_probability_error": (
                report.reward_probability_error
            ),
            "candidate_oracle_return_ratio": (
                report.candidate_oracle_return_ratio
            ),
            "improvement_vs_reactive": (
                report.improvement_vs_reactive
            ),
            "improvement_vs_maximum_depth": (
                report.improvement_vs_maximum_depth
            ),
            "improvement_vs_myopic": report.improvement_vs_myopic,
            "improvement_vs_rotated_reward": (
                report.improvement_vs_rotated_reward
            ),
            "improvement_vs_random": report.improvement_vs_random,
            "simultaneous_ablation_world_win_rate": (
                report.simultaneous_ablation_world_win_rate
            ),
            "archive_retention_rate": (
                report.archive_retention_rate
            ),
            "snapshot_round_trip_rate": (
                report.snapshot_round_trip_rate
            ),
            "frozen_model_rate": report.frozen_model_rate,
        },
    )


def report_with_learned_context_metrics(
    report: LearnedContextSuiteReport,
    **changes: Any,
) -> LearnedContextSuiteReport:
    return replace(report, **changes)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Darwin H50-L11 learned context and reward benchmark."
        )
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=LEARNED_CONTEXT_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=LEARNED_CONTEXT_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    args = parser.parse_args(argv)
    report = run_learned_context_suite(
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
