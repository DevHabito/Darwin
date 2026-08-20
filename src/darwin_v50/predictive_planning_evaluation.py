"""Held-out benchmark for Darwin H50-L10 predictive-history planning."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import json
import math
import random
from statistics import fmean
from typing import Any, Callable, Iterable, Sequence

from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .predictive_planning_lab import (
    ALL_HISTORY_STATES,
    PLANNING_ACTIONS,
    PREDICTIVE_PAIR_COUNT,
    HistoryFrontierExplorer,
    HistoryState,
    PredictiveHistoryModel,
    PredictiveHistoryPlanner,
    PredictivePlanningWorld,
    PredictiveTransitionExperience,
    PredictiveWorldSpecification,
    history_hamming_distance,
    next_history,
    validate_history,
)


PREDICTIVE_DEVELOPMENT_SEEDS = tuple(range(17000, 17032))
PREDICTIVE_FINAL_SEEDS = tuple(range(17100, 17200))
PREDICTIVE_BUDGET_CANDIDATES = (486, 729, 972)
PREDICTIVE_TASK_XOR_MASK = 0x7A5C9
PREDICTIVE_RANDOM_POLICY_XOR_MASK = 0x4D2B1
PREDICTIVE_TASKS_PER_WORLD = 24
PREDICTIVE_MAX_EVALUATION_STEPS = 6
LOCAL_PREDICTIVE_EVALUATOR = (
    "darwin_v50.predictive_planning_evaluation.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class PredictivePlanningTask:
    start: HistoryState
    goal: HistoryState
    oracle_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_history(self.start, "task_start")
        validate_history(self.goal, "task_goal")
        if self.start == self.goal:
            raise ValidationError("task start and goal must differ")
        if (
            not isinstance(self.oracle_actions, tuple)
            or any(
                action not in PLANNING_ACTIONS
                for action in self.oracle_actions
            )
        ):
            raise ValidationError("task oracle actions are invalid")
        if len(self.oracle_actions) != 4:
            raise ValidationError(
                "registered planning tasks must require four actions"
            )


@dataclass(frozen=True, slots=True)
class PredictiveEpisodeResult:
    success: bool
    steps: int
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PredictiveBudgetScore:
    budget: int
    mean_candidate_success: float
    mean_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "mean_candidate_success": self.mean_candidate_success,
            "mean_coverage": self.mean_coverage,
        }


@dataclass(frozen=True, slots=True)
class PredictiveDevelopmentSelection:
    seeds: tuple[int, ...]
    candidate_scores: tuple[PredictiveBudgetScore, ...]
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
class PredictiveWorldResult:
    seed: int
    task_count: int
    coverage: float
    known_transition_accuracy: float
    candidate_success_rate: float
    reactive_success_rate: float
    myopic_success_rate: float
    permuted_action_success_rate: float
    random_success_rate: float
    oracle_success_rate: float
    simultaneous_ablation_win: bool
    candidate_success_count: int
    candidate_excess_step_sum: int
    archive_retained: bool
    snapshot_round_trip_exact: bool
    model_frozen_during_evaluation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "task_count": self.task_count,
            "coverage": self.coverage,
            "known_transition_accuracy": (
                self.known_transition_accuracy
            ),
            "candidate_success_rate": self.candidate_success_rate,
            "reactive_success_rate": self.reactive_success_rate,
            "myopic_success_rate": self.myopic_success_rate,
            "permuted_action_success_rate": (
                self.permuted_action_success_rate
            ),
            "random_success_rate": self.random_success_rate,
            "oracle_success_rate": self.oracle_success_rate,
            "simultaneous_ablation_win": (
                self.simultaneous_ablation_win
            ),
            "candidate_success_count": self.candidate_success_count,
            "candidate_excess_step_sum": self.candidate_excess_step_sum,
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": (
                self.snapshot_round_trip_exact
            ),
            "model_frozen_during_evaluation": (
                self.model_frozen_during_evaluation
            ),
        }


@dataclass(frozen=True, slots=True)
class PredictiveSuiteReport:
    development: PredictiveDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[PredictiveWorldResult, ...]
    final_world_count: int
    unique_world_count: int
    task_count: int
    mean_coverage: float
    known_transition_accuracy: float
    candidate_success_rate: float
    reactive_success_rate: float
    myopic_success_rate: float
    permuted_action_success_rate: float
    random_success_rate: float
    oracle_success_rate: float
    improvement_vs_reactive: float
    improvement_vs_myopic: float
    improvement_vs_permuted_action: float
    improvement_vs_random: float
    simultaneous_ablation_world_win_rate: float
    mean_candidate_excess_steps_vs_oracle: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    frozen_model_rate: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_coverage: float = 0.90,
        minimum_known_transition_accuracy: float = 1.0,
        minimum_candidate_success_rate: float = 0.90,
        minimum_improvement_vs_reactive: float = 0.50,
        minimum_improvement_vs_myopic: float = 0.35,
        minimum_improvement_vs_permuted_action: float = 0.40,
        minimum_improvement_vs_random: float = 0.50,
        minimum_simultaneous_ablation_world_win_rate: float = 0.90,
        maximum_mean_candidate_excess_steps_vs_oracle: float = 0.25,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
        minimum_frozen_model_rate: float = 1.0,
    ) -> bool:
        return (
            self.mean_coverage >= minimum_coverage
            and self.known_transition_accuracy
            >= minimum_known_transition_accuracy
            and self.candidate_success_rate
            >= minimum_candidate_success_rate
            and self.improvement_vs_reactive
            >= minimum_improvement_vs_reactive
            and self.improvement_vs_myopic
            >= minimum_improvement_vs_myopic
            and self.improvement_vs_permuted_action
            >= minimum_improvement_vs_permuted_action
            and self.improvement_vs_random
            >= minimum_improvement_vs_random
            and self.simultaneous_ablation_world_win_rate
            >= minimum_simultaneous_ablation_world_win_rate
            and self.mean_candidate_excess_steps_vs_oracle
            <= maximum_mean_candidate_excess_steps_vs_oracle
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
            "task_count": self.task_count,
            "mean_coverage": self.mean_coverage,
            "known_transition_accuracy": (
                self.known_transition_accuracy
            ),
            "candidate_success_rate": self.candidate_success_rate,
            "reactive_success_rate": self.reactive_success_rate,
            "myopic_success_rate": self.myopic_success_rate,
            "permuted_action_success_rate": (
                self.permuted_action_success_rate
            ),
            "random_success_rate": self.random_success_rate,
            "oracle_success_rate": self.oracle_success_rate,
            "improvement_vs_reactive": self.improvement_vs_reactive,
            "improvement_vs_myopic": self.improvement_vs_myopic,
            "improvement_vs_permuted_action": (
                self.improvement_vs_permuted_action
            ),
            "improvement_vs_random": self.improvement_vs_random,
            "simultaneous_ablation_world_win_rate": (
                self.simultaneous_ablation_world_win_rate
            ),
            "mean_candidate_excess_steps_vs_oracle": (
                self.mean_candidate_excess_steps_vs_oracle
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
        or any(
            isinstance(seed, bool) or not isinstance(seed, int)
            for seed in result
        )
        or len(set(result)) != len(result)
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
            or value < 1
            for value in result
        )
    ):
        raise ValidationError(
            "budget candidates must be unique increasing integers"
        )
    return result


def make_predictive_tasks(
    specification: PredictiveWorldSpecification,
    *,
    count: int = PREDICTIVE_TASKS_PER_WORLD,
) -> tuple[PredictivePlanningTask, ...]:
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
    ):
        raise ValidationError("task count must be positive")
    rng = random.Random(specification.seed ^ PREDICTIVE_TASK_XOR_MASK)
    tasks: list[PredictivePlanningTask] = []
    seen: set[tuple[HistoryState, HistoryState]] = set()
    attempts = 0
    while len(tasks) < count and attempts < 100_000:
        attempts += 1
        start = rng.choice(ALL_HISTORY_STATES)
        goal = rng.choice(ALL_HISTORY_STATES)
        pair = (start, goal)
        if start == goal or pair in seen:
            continue
        actions = specification.shortest_plan(start, goal)
        if len(actions) != 4:
            continue
        seen.add(pair)
        tasks.append(
            PredictivePlanningTask(
                start=start,
                goal=goal,
                oracle_actions=actions,
            )
        )
    if len(tasks) != count:
        raise RuntimeError("could not construct enough four-step tasks")
    return tuple(tasks)


def _copy_model_prefix(
    archive: Sequence[PredictiveTransitionExperience],
    budget: int,
) -> PredictiveHistoryModel:
    if not 1 <= budget <= len(archive):
        raise ValidationError("model prefix budget is invalid")
    model = PredictiveHistoryModel()
    for experience in archive[:budget]:
        model.observe(experience)
    return model


def run_predictive_exploration(
    seed: int,
    *,
    budget: int,
) -> tuple[HistoryFrontierExplorer, PredictivePlanningWorld]:
    if (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or budget < 1
    ):
        raise ValidationError("exploration budget must be positive")
    world = PredictivePlanningWorld(seed)
    observation = world.reset(
        start=world.specification.exploration_start,
        goal=None,
        max_steps=budget,
    )
    if observation.priming_history is None:
        raise RuntimeError("exploration reset omitted priming history")
    explorer = HistoryFrontierExplorer()
    explorer.start(observation.priming_history)
    trace_id = f"{world.world_id}:exploration:{budget}"
    for _ in range(budget):
        action = explorer.choose_action()
        step = world.step(action)
        explorer.observe(
            next_cue=step.observation.cue,
            world_id=world.world_id,
            trace_id=trace_id,
        )
    return explorer, world


def _run_episode(
    seed: int,
    task: PredictivePlanningTask,
    chooser: Callable[[HistoryState, HistoryState, int], str],
) -> PredictiveEpisodeResult:
    world = PredictivePlanningWorld(seed)
    observation = world.reset(
        start=task.start,
        goal=task.goal,
        max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
    )
    if observation.priming_history is None:
        raise RuntimeError("evaluation reset omitted priming history")
    history = observation.priming_history
    actions: list[str] = []
    for step_index in range(PREDICTIVE_MAX_EVALUATION_STEPS):
        action = chooser(history, task.goal, step_index)
        if action not in PLANNING_ACTIONS:
            raise ValidationError("policy returned an unknown action")
        result = world.step(action)
        actions.append(action)
        history = next_history(history, result.observation.cue)
        if history != world.current_history_for_evaluator:
            raise RuntimeError("observable history diverged from evaluator")
        if result.observation.terminated:
            return PredictiveEpisodeResult(
                success=True,
                steps=len(actions),
                actions=tuple(actions),
            )
        if result.observation.truncated:
            break
    return PredictiveEpisodeResult(
        success=False,
        steps=len(actions),
        actions=tuple(actions),
    )


class _ReactiveCueModel:
    def __init__(
        self,
        archive: Sequence[PredictiveTransitionExperience],
    ) -> None:
        self._counts: dict[
            tuple[int, str],
            Counter[int],
        ] = defaultdict(Counter)
        for item in archive:
            self._counts[(item.history[-1], item.action)][
                item.next_cue
            ] += 1

    def target_probability(
        self,
        cue: int,
        action: str,
        target_cue: int,
    ) -> float:
        counts = self._counts.get((cue, action))
        if not counts:
            return 0.0
        return counts[target_cue] / sum(counts.values())


def _candidate_chooser(
    model: PredictiveHistoryModel,
    *,
    action_rotation: int = 0,
) -> Callable[[HistoryState, HistoryState, int], str]:
    planner = PredictiveHistoryPlanner(
        model,
        max_depth=PREDICTIVE_MAX_EVALUATION_STEPS,
        action_rotation=action_rotation,
    )

    def choose(
        history: HistoryState,
        goal: HistoryState,
        _step_index: int,
    ) -> str:
        plan = planner.plan(history, goal)
        return plan.actions[0] if plan.found and plan.actions else PLANNING_ACTIONS[0]

    return choose


def _myopic_chooser(
    model: PredictiveHistoryModel,
) -> Callable[[HistoryState, HistoryState, int], str]:
    def choose(
        history: HistoryState,
        goal: HistoryState,
        _step_index: int,
    ) -> str:
        predictions = tuple(
            (action, model.predict(history, action))
            for action in PLANNING_ACTIONS
        )
        available = tuple(
            (action, prediction)
            for action, prediction in predictions
            if prediction is not None
        )
        if not available:
            return PLANNING_ACTIONS[0]
        return min(
            available,
            key=lambda item: (
                history_hamming_distance(
                    item[1].next_history,  # type: ignore[union-attr]
                    goal,
                ),
                PLANNING_ACTIONS.index(item[0]),
            ),
        )[0]

    return choose


def _reactive_chooser(
    model: _ReactiveCueModel,
) -> Callable[[HistoryState, HistoryState, int], str]:
    def choose(
        history: HistoryState,
        goal: HistoryState,
        step_index: int,
    ) -> str:
        target = goal[min(step_index, len(goal) - 1)]
        return max(
            PLANNING_ACTIONS,
            key=lambda action: (
                model.target_probability(
                    history[-1],
                    action,
                    target,
                ),
                -PLANNING_ACTIONS.index(action),
            ),
        )

    return choose


def _oracle_chooser(
    specification: PredictiveWorldSpecification,
) -> Callable[[HistoryState, HistoryState, int], str]:
    def choose(
        history: HistoryState,
        goal: HistoryState,
        _step_index: int,
    ) -> str:
        actions = specification.shortest_plan(history, goal)
        return actions[0] if actions else PLANNING_ACTIONS[0]

    return choose


def _random_chooser(
    seed: int,
) -> Callable[[HistoryState, HistoryState, int], str]:
    rng = random.Random(seed ^ PREDICTIVE_RANDOM_POLICY_XOR_MASK)

    def choose(
        _history: HistoryState,
        _goal: HistoryState,
        _step_index: int,
    ) -> str:
        return rng.choice(PLANNING_ACTIONS)

    return choose


def _success_rate(
    results: Sequence[PredictiveEpisodeResult],
) -> float:
    if not results:
        raise ValidationError("episode result set cannot be empty")
    return fmean(float(item.success) for item in results)


def _candidate_success_for_model(
    seed: int,
    model: PredictiveHistoryModel,
    tasks: Sequence[PredictivePlanningTask],
) -> float:
    chooser = _candidate_chooser(model)
    return _success_rate(
        tuple(_run_episode(seed, task, chooser) for task in tasks)
    )


def select_predictive_budget(
    seeds: Iterable[int] = PREDICTIVE_DEVELOPMENT_SEEDS,
    *,
    budget_candidates: Sequence[int] = (
        PREDICTIVE_BUDGET_CANDIDATES
    ),
) -> PredictiveDevelopmentSelection:
    normalized_seeds = _normalize_seeds(seeds, field="development")
    budgets = _normalize_budgets(budget_candidates)
    successes: dict[int, list[float]] = {
        budget: [] for budget in budgets
    }
    coverages: dict[int, list[float]] = {
        budget: [] for budget in budgets
    }
    maximum_budget = max(budgets)
    for seed in normalized_seeds:
        explorer, world = run_predictive_exploration(
            seed,
            budget=maximum_budget,
        )
        tasks = make_predictive_tasks(world.specification)
        archive = explorer.model.archive
        for budget in budgets:
            model = _copy_model_prefix(archive, budget)
            coverages[budget].append(
                model.known_transition_pair_count
                / PREDICTIVE_PAIR_COUNT
            )
            successes[budget].append(
                _candidate_success_for_model(seed, model, tasks)
            )
    scores = tuple(
        PredictiveBudgetScore(
            budget=budget,
            mean_candidate_success=fmean(successes[budget]),
            mean_coverage=fmean(coverages[budget]),
        )
        for budget in budgets
    )
    selected = min(
        scores,
        key=lambda item: (
            -item.mean_candidate_success,
            -item.mean_coverage,
            item.budget,
        ),
    )
    return PredictiveDevelopmentSelection(
        seeds=normalized_seeds,
        candidate_scores=scores,
        selected_budget=selected.budget,
    )


def run_predictive_world(
    seed: int,
    *,
    selected_budget: int,
) -> PredictiveWorldResult:
    explorer, exploration_world = run_predictive_exploration(
        seed,
        budget=selected_budget,
    )
    model = explorer.model
    specification = exploration_world.specification
    tasks = make_predictive_tasks(specification)
    coverage = (
        model.known_transition_pair_count / PREDICTIVE_PAIR_COUNT
    )
    correct = sum(
        prediction is not None
        and prediction.next_history
        == specification.transition(history, action)
        for history in ALL_HISTORY_STATES
        for action in PLANNING_ACTIONS
        for prediction in (model.predict(history, action),)
        if prediction is not None
    )
    accuracy = (
        correct / model.known_transition_pair_count
        if model.known_transition_pair_count
        else 0.0
    )
    expected_archive = model.archive
    model_snapshot = model.to_snapshot()
    explorer_snapshot = explorer.to_snapshot()
    restored = HistoryFrontierExplorer.from_snapshot(explorer_snapshot)
    snapshot_exact = (
        restored.to_snapshot() == explorer_snapshot
        and restored.model.archive == expected_archive
        and restored.choose_action() == explorer.choose_action()
        and restored.to_snapshot() == explorer.to_snapshot()
    )
    archive_retained = (
        len(expected_archive) == selected_budget
        and restored.model.archive == expected_archive
    )

    candidate_chooser = _candidate_chooser(model)
    reactive_chooser = _reactive_chooser(
        _ReactiveCueModel(model.archive)
    )
    myopic_chooser = _myopic_chooser(model)
    permuted_chooser = _candidate_chooser(model, action_rotation=1)
    oracle_chooser = _oracle_chooser(specification)

    candidate_results: list[PredictiveEpisodeResult] = []
    reactive_results: list[PredictiveEpisodeResult] = []
    myopic_results: list[PredictiveEpisodeResult] = []
    permuted_results: list[PredictiveEpisodeResult] = []
    random_results: list[PredictiveEpisodeResult] = []
    oracle_results: list[PredictiveEpisodeResult] = []
    for task_index, task in enumerate(tasks, start=1):
        candidate_results.append(
            _run_episode(seed, task, candidate_chooser)
        )
        reactive_results.append(
            _run_episode(seed, task, reactive_chooser)
        )
        myopic_results.append(
            _run_episode(seed, task, myopic_chooser)
        )
        permuted_results.append(
            _run_episode(seed, task, permuted_chooser)
        )
        random_results.append(
            _run_episode(
                seed,
                task,
                _random_chooser(seed ^ (task_index * 0x9E37)),
            )
        )
        oracle_results.append(
            _run_episode(seed, task, oracle_chooser)
        )

    candidate_rate = _success_rate(candidate_results)
    reactive_rate = _success_rate(reactive_results)
    myopic_rate = _success_rate(myopic_results)
    permuted_rate = _success_rate(permuted_results)
    candidate_successes = tuple(
        item for item in candidate_results if item.success
    )
    return PredictiveWorldResult(
        seed=seed,
        task_count=len(tasks),
        coverage=coverage,
        known_transition_accuracy=accuracy,
        candidate_success_rate=candidate_rate,
        reactive_success_rate=reactive_rate,
        myopic_success_rate=myopic_rate,
        permuted_action_success_rate=permuted_rate,
        random_success_rate=_success_rate(random_results),
        oracle_success_rate=_success_rate(oracle_results),
        simultaneous_ablation_win=(
            candidate_rate > reactive_rate
            and candidate_rate > myopic_rate
            and candidate_rate > permuted_rate
        ),
        candidate_success_count=len(candidate_successes),
        candidate_excess_step_sum=sum(
            item.steps - len(task.oracle_actions)
            for item, task in zip(
                candidate_results,
                tasks,
                strict=True,
            )
            if item.success
        ),
        archive_retained=archive_retained,
        snapshot_round_trip_exact=snapshot_exact,
        model_frozen_during_evaluation=(
            model.to_snapshot() == model_snapshot
        ),
    )


def run_predictive_suite(
    *,
    development_seeds: Iterable[int] = (
        PREDICTIVE_DEVELOPMENT_SEEDS
    ),
    final_seeds: Iterable[int] = PREDICTIVE_FINAL_SEEDS,
    budget_candidates: Sequence[int] = (
        PREDICTIVE_BUDGET_CANDIDATES
    ),
) -> PredictiveSuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds,
        field="development",
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("development and final seeds must be disjoint")
    development = select_predictive_budget(
        development_seed_tuple,
        budget_candidates=budget_candidates,
    )
    worlds = tuple(
        run_predictive_world(
            seed,
            selected_budget=development.selected_budget,
        )
        for seed in final_seed_tuple
    )
    total_tasks = sum(item.task_count for item in worlds)

    def pooled_success(field: str) -> float:
        return sum(
            getattr(item, field) * item.task_count for item in worlds
        ) / total_tasks

    candidate_success = pooled_success("candidate_success_rate")
    reactive_success = pooled_success("reactive_success_rate")
    myopic_success = pooled_success("myopic_success_rate")
    permuted_success = pooled_success(
        "permuted_action_success_rate"
    )
    random_success = pooled_success("random_success_rate")
    oracle_success = pooled_success("oracle_success_rate")
    candidate_success_count = sum(
        item.candidate_success_count for item in worlds
    )
    world_signatures = {
        tuple(rule.next_cues for rule in PredictiveWorldSpecification.from_seed(
            item.seed
        ).rules)
        for item in worlds
    }
    return PredictiveSuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        unique_world_count=len(world_signatures),
        task_count=total_tasks,
        mean_coverage=fmean(item.coverage for item in worlds),
        known_transition_accuracy=(
            sum(
                item.known_transition_accuracy
                * item.coverage
                * PREDICTIVE_PAIR_COUNT
                for item in worlds
            )
            / sum(
                item.coverage * PREDICTIVE_PAIR_COUNT
                for item in worlds
            )
        ),
        candidate_success_rate=candidate_success,
        reactive_success_rate=reactive_success,
        myopic_success_rate=myopic_success,
        permuted_action_success_rate=permuted_success,
        random_success_rate=random_success,
        oracle_success_rate=oracle_success,
        improvement_vs_reactive=candidate_success - reactive_success,
        improvement_vs_myopic=candidate_success - myopic_success,
        improvement_vs_permuted_action=(
            candidate_success - permuted_success
        ),
        improvement_vs_random=candidate_success - random_success,
        simultaneous_ablation_world_win_rate=(
            sum(item.simultaneous_ablation_win for item in worlds)
            / len(worlds)
        ),
        mean_candidate_excess_steps_vs_oracle=(
            sum(item.candidate_excess_step_sum for item in worlds)
            / candidate_success_count
            if candidate_success_count
            else math.inf
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
            "Exploration budget is selected only on development seeds "
            f"{development_seed_tuple[0]}-{development_seed_tuple[-1]}. "
            "Final metrics use disjoint supplied seeds "
            f"{final_seed_tuple[0]}-{final_seed_tuple[-1]}, 24 unique "
            "four-step tasks per world, frozen models, and terminal-only "
            "reward."
        ),
        limitations=(
            "The process is synthetic, deterministic, tabular, and has only 81 states.",
            "A fixed four-cue history is supplied by the experiment design rather than learned.",
            "The initial four-cue orientation sequence is passively observed at reset.",
            "Exploration uses a human-designed frontier policy.",
            "The same within-world transition experience supports all held-out tasks.",
            "There is no transfer of dynamics between worlds.",
            "The goal is an observable four-cue signature supplied by the evaluator.",
            "Rewards are terminal and known through the goal condition; a reward model is not learned.",
            "The implementation is not a full PSR, Dyna, PlaNet, or MuZero system.",
            "Snapshots are structurally replayed but not cryptographically authenticated.",
            "The evaluator is local and cannot provide independent E3 evidence.",
            "Success would not imply language, consciousness, emotion, personhood, AGI, or a Diana-like brain.",
        ),
    )


def record_predictive_result(
    kernel: DarwinKernelV50,
    report: PredictiveSuiteReport,
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"predictive-history-planning:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Observable history plus learned dynamics supports delayed planning"
        ),
        evidence_source=LOCAL_PREDICTIVE_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-predictive-history-planning",
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
        source=LOCAL_PREDICTIVE_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                all_criteria_satisfied
            ),
            "mean_coverage": report.mean_coverage,
            "known_transition_accuracy": (
                report.known_transition_accuracy
            ),
            "candidate_success_rate": report.candidate_success_rate,
            "improvement_vs_reactive": (
                report.improvement_vs_reactive
            ),
            "improvement_vs_myopic": report.improvement_vs_myopic,
            "improvement_vs_permuted_action": (
                report.improvement_vs_permuted_action
            ),
            "improvement_vs_random": report.improvement_vs_random,
            "simultaneous_ablation_world_win_rate": (
                report.simultaneous_ablation_world_win_rate
            ),
            "mean_candidate_excess_steps_vs_oracle": (
                report.mean_candidate_excess_steps_vs_oracle
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


def report_with_predictive_metrics(
    report: PredictiveSuiteReport,
    **changes: Any,
) -> PredictiveSuiteReport:
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
            "Run Darwin H50-L10 predictive-history planning benchmark."
        )
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=PREDICTIVE_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=PREDICTIVE_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    args = parser.parse_args(argv)
    report = run_predictive_suite(
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
