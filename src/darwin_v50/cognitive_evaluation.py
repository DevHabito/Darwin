"""Deterministic evaluation harness for the Darwin v50.1 learning lab.

The evaluator is deliberately local and therefore not independent evidence.
Its purpose is regression testing and falsification of a narrow engineering
hypothesis, not certification of cognition.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
import random
from statistics import fmean
from typing import Any, Iterable, Sequence

from .cognitive_lab import (
    ActiveTransitionExplorer,
    CausalEnvironment,
    ExplorationTrace,
    ModelBasedPlanner,
    OpaqueGraphWorld,
    TabularTransitionModel,
    collect_controlled_transition_census,
    make_benchmark_world,
    snapshot_digest,
)
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)


LOCAL_EVALUATOR_SOURCE = "darwin_v50.cognitive_lab.local_evaluator"


@dataclass(frozen=True, slots=True)
class EvaluationTask:
    task_id: str
    start: str
    goal: str
    max_steps: int
    oracle_path_length: int


@dataclass(frozen=True, slots=True)
class EpisodeEvaluation:
    task_id: str
    policy: str
    success: bool
    steps: int
    replans: int
    prediction_count: int
    prediction_errors: int
    stopped_reason: str
    trajectory: tuple[str, ...]
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicySummary:
    policy: str
    episodes: int
    successes: int
    success_rate: float
    mean_steps: float
    prediction_accuracy: float | None

    @classmethod
    def from_episodes(
        cls,
        policy: str,
        episodes: Sequence[EpisodeEvaluation],
    ) -> "PolicySummary":
        if not episodes:
            raise ValidationError("policy summary requires at least one episode")
        successes = sum(episode.success for episode in episodes)
        prediction_count = sum(episode.prediction_count for episode in episodes)
        prediction_errors = sum(episode.prediction_errors for episode in episodes)
        accuracy = (
            1.0 - prediction_errors / prediction_count
            if prediction_count
            else None
        )
        return cls(
            policy=policy,
            episodes=len(episodes),
            successes=successes,
            success_rate=successes / len(episodes),
            mean_steps=fmean(episode.steps for episode in episodes),
            prediction_accuracy=accuracy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "episodes": self.episodes,
            "successes": self.successes,
            "success_rate": self.success_rate,
            "mean_steps": self.mean_steps,
            "prediction_accuracy": self.prediction_accuracy,
        }


@dataclass(frozen=True, slots=True)
class WorldBenchmark:
    seed: int
    world_id: str
    training_transition_count: int
    model_snapshot_digest: str
    reserved_task_count: int
    known_transition_accuracy: float
    model_based: PolicySummary
    random_policy: PolicySummary
    untrained_ablation: PolicySummary

    @property
    def success_rate_delta(self) -> float:
        return self.model_based.success_rate - self.random_policy.success_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "world_id": self.world_id,
            "training_transition_count": self.training_transition_count,
            "model_snapshot_digest": self.model_snapshot_digest,
            "reserved_task_count": self.reserved_task_count,
            "known_transition_accuracy": self.known_transition_accuracy,
            "model_based": self.model_based.to_dict(),
            "random_policy": self.random_policy.to_dict(),
            "untrained_ablation": self.untrained_ablation.to_dict(),
            "success_rate_delta": self.success_rate_delta,
        }


@dataclass(frozen=True, slots=True)
class CognitiveSuiteReport:
    seeds: tuple[int, ...]
    worlds: tuple[WorldBenchmark, ...]
    world_count: int
    evaluation_episode_count: int
    training_transition_count: int
    model_based_success_rate: float
    random_success_rate: float
    untrained_success_rate: float
    known_transition_accuracy: float
    success_rate_delta: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_model_success: float = 0.95,
        minimum_delta: float = 0.20,
        minimum_known_transition_accuracy: float = 1.0,
    ) -> bool:
        return (
            self.model_based_success_rate >= minimum_model_success
            and self.success_rate_delta >= minimum_delta
            and self.known_transition_accuracy
            >= minimum_known_transition_accuracy
            and self.untrained_success_rate == 0.0
        )

    def to_dict(self, *, include_worlds: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "world_count": self.world_count,
            "evaluation_episode_count": self.evaluation_episode_count,
            "training_transition_count": self.training_transition_count,
            "model_based_success_rate": self.model_based_success_rate,
            "random_success_rate": self.random_success_rate,
            "untrained_success_rate": self.untrained_success_rate,
            "known_transition_accuracy": self.known_transition_accuracy,
            "success_rate_delta": self.success_rate_delta,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
        }
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


@dataclass(frozen=True, slots=True)
class ActiveExplorationWorldBenchmark:
    seed: int
    world_id: str
    budget: int
    possible_transition_pairs: int
    active_trace: ExplorationTrace
    random_trace: ExplorationTrace
    active_model: PolicySummary
    random_exploration_model: PolicySummary

    @property
    def active_coverage(self) -> float:
        return (
            self.active_trace.unique_transition_pairs
            / self.possible_transition_pairs
        )

    @property
    def random_coverage(self) -> float:
        return (
            self.random_trace.unique_transition_pairs
            / self.possible_transition_pairs
        )

    @property
    def coverage_delta(self) -> float:
        return self.active_coverage - self.random_coverage

    @property
    def task_success_delta(self) -> float:
        return (
            self.active_model.success_rate
            - self.random_exploration_model.success_rate
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "world_id": self.world_id,
            "budget": self.budget,
            "possible_transition_pairs": self.possible_transition_pairs,
            "active_unique_transition_pairs": (
                self.active_trace.unique_transition_pairs
            ),
            "random_unique_transition_pairs": (
                self.random_trace.unique_transition_pairs
            ),
            "active_discovered_states": self.active_trace.discovered_states,
            "random_discovered_states": self.random_trace.discovered_states,
            "active_coverage": self.active_coverage,
            "random_coverage": self.random_coverage,
            "coverage_delta": self.coverage_delta,
            "active_model": self.active_model.to_dict(),
            "random_exploration_model": (
                self.random_exploration_model.to_dict()
            ),
            "task_success_delta": self.task_success_delta,
        }


@dataclass(frozen=True, slots=True)
class ActiveExplorationSuiteReport:
    seeds: tuple[int, ...]
    worlds: tuple[ActiveExplorationWorldBenchmark, ...]
    world_count: int
    budget_per_world: int
    training_step_count: int
    evaluation_episode_count_per_policy: int
    active_coverage: float
    random_coverage: float
    coverage_delta: float
    active_task_success_rate: float
    random_exploration_task_success_rate: float
    task_success_delta: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_active_coverage: float = 0.95,
        minimum_coverage_delta: float = 0.20,
        minimum_active_task_success: float = 0.95,
        minimum_task_success_delta: float = 0.20,
    ) -> bool:
        return (
            self.active_coverage >= minimum_active_coverage
            and self.coverage_delta >= minimum_coverage_delta
            and self.active_task_success_rate >= minimum_active_task_success
            and self.task_success_delta >= minimum_task_success_delta
        )

    def to_dict(self, *, include_worlds: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "world_count": self.world_count,
            "budget_per_world": self.budget_per_world,
            "training_step_count": self.training_step_count,
            "evaluation_episode_count_per_policy": (
                self.evaluation_episode_count_per_policy
            ),
            "active_coverage": self.active_coverage,
            "random_coverage": self.random_coverage,
            "coverage_delta": self.coverage_delta,
            "active_task_success_rate": self.active_task_success_rate,
            "random_exploration_task_success_rate": (
                self.random_exploration_task_success_rate
            ),
            "task_success_delta": self.task_success_delta,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
        }
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


def _reserved_tasks(
    environment: OpaqueGraphWorld,
    *,
    seed: int,
    task_limit: int,
) -> tuple[EvaluationTask, ...]:
    """Select tasks not used as start-goal pairs during transition probes."""

    if task_limit < 1:
        raise ValidationError("task_limit must be positive")
    states = environment.states
    probe_pairs = {
        (state, states[(index + 1) % len(states)])
        for index, state in enumerate(states)
    }
    candidates: list[EvaluationTask] = []
    for start in states:
        for goal in states:
            if start == goal or (start, goal) in probe_pairs:
                continue
            path_length = environment.evaluator_shortest_path_length(start, goal)
            if path_length < 2:
                continue
            candidates.append(
                EvaluationTask(
                    task_id=f"task:{start}:{goal}",
                    start=start,
                    goal=goal,
                    max_steps=path_length,
                    oracle_path_length=path_length,
                )
            )
    rng = random.Random(seed ^ 0xD45A_501)
    rng.shuffle(candidates)
    selected = tuple(candidates[:task_limit])
    if len(selected) < task_limit:
        raise RuntimeError(
            f"world produced only {len(selected)} eligible reserved tasks"
        )
    return selected


def run_model_based_episode(
    environment: CausalEnvironment,
    model: TabularTransitionModel,
    task: EvaluationTask,
    *,
    policy_name: str = "learned_model_planner",
) -> EpisodeEvaluation:
    observation = environment.reset(
        start=task.start,
        goal=task.goal,
        max_steps=task.max_steps,
    )
    trajectory = [observation.state]
    actions: list[str] = []
    replans = 0
    prediction_count = 0
    prediction_errors = 0
    stopped_reason = "step_budget_exhausted"
    while not observation.terminated and not observation.truncated:
        plan = ModelBasedPlanner(model, max_depth=task.max_steps).plan(
            observation.state,
            observation.goal,
        )
        replans += 1
        if not plan.found or not plan.actions:
            stopped_reason = plan.reason
            break
        action = plan.actions[0]
        prediction = model.predict(observation.state, action)
        if prediction is None:
            stopped_reason = "missing_transition_prediction"
            break
        prediction_count += 1
        result = environment.step(action)
        if prediction.next_state != result.observation.state:
            prediction_errors += 1
        observation = result.observation
        trajectory.append(observation.state)
        actions.append(action)
        if observation.terminated:
            stopped_reason = "goal_reached"
        elif observation.truncated:
            stopped_reason = "step_budget_exhausted"
    return EpisodeEvaluation(
        task_id=task.task_id,
        policy=policy_name,
        success=observation.terminated,
        steps=len(actions),
        replans=replans,
        prediction_count=prediction_count,
        prediction_errors=prediction_errors,
        stopped_reason=stopped_reason,
        trajectory=tuple(trajectory),
        actions=tuple(actions),
    )


def run_random_episode(
    environment: CausalEnvironment,
    task: EvaluationTask,
    *,
    seed: int,
) -> EpisodeEvaluation:
    rng = random.Random(seed)
    observation = environment.reset(
        start=task.start,
        goal=task.goal,
        max_steps=task.max_steps,
    )
    trajectory = [observation.state]
    actions: list[str] = []
    while not observation.terminated and not observation.truncated:
        action = rng.choice(environment.available_actions())
        result = environment.step(action)
        observation = result.observation
        trajectory.append(observation.state)
        actions.append(action)
    return EpisodeEvaluation(
        task_id=task.task_id,
        policy="seeded_random",
        success=observation.terminated,
        steps=len(actions),
        replans=0,
        prediction_count=0,
        prediction_errors=0,
        stopped_reason=(
            "goal_reached" if observation.terminated else "step_budget_exhausted"
        ),
        trajectory=tuple(trajectory),
        actions=tuple(actions),
    )


def run_random_transition_exploration(
    environment: OpaqueGraphWorld,
    model: TabularTransitionModel,
    *,
    start: str,
    budget: int,
    seed: int,
) -> ExplorationTrace:
    if budget < 1:
        raise ValidationError("exploration budget must be positive")
    rng = random.Random(seed)
    observation = environment.reset_exploration(
        start=start,
        max_steps=budget,
    )
    trajectory = [observation.state]
    actions: list[str] = []
    curve: list[int] = []
    while not observation.truncated:
        action = rng.choice(environment.available_actions())
        result = environment.step(action)
        model.observe(result.experience)
        observation = result.observation
        trajectory.append(observation.state)
        actions.append(action)
        curve.append(model.known_transition_pair_count)
    return ExplorationTrace(
        policy="seeded_random_exploration",
        world_id=environment.world_id,
        budget=budget,
        steps=len(actions),
        unique_transition_pairs=model.known_transition_pair_count,
        discovered_states=len(model.known_states),
        pair_count_curve=tuple(curve),
        trajectory=tuple(trajectory),
        actions=tuple(actions),
    )


def evaluate_known_transition_accuracy(
    environment: CausalEnvironment,
    model: TabularTransitionModel,
) -> float:
    """Evaluate fresh outcomes for trained state-action pairs.

    These are repeated transition pairs, not held-out dynamics.  The more
    conservative name prevents this metric from being misreported as
    generalization.
    """

    correct = 0
    total = 0
    states = environment.states
    for state_index, state in enumerate(states):
        goal = states[(state_index + 1) % len(states)]
        for action in environment.action_space:
            prediction = model.predict(state, action)
            if prediction is None:
                total += 1
                continue
            environment.reset(start=state, goal=goal, max_steps=1)
            actual = environment.step(action).experience.next_state
            total += 1
            correct += prediction.next_state == actual
    if total == 0:
        raise RuntimeError("transition accuracy has no cases")
    return correct / total


def run_world_benchmark(
    seed: int,
    *,
    task_limit: int = 24,
) -> WorldBenchmark:
    environment = make_benchmark_world(seed)
    model = TabularTransitionModel()
    experiences = collect_controlled_transition_census(environment, model)
    snapshot = model.to_snapshot()
    reloaded_model = TabularTransitionModel.from_snapshot(snapshot)
    tasks = _reserved_tasks(
        environment,
        seed=seed,
        task_limit=task_limit,
    )
    model_episodes = tuple(
        run_model_based_episode(environment, reloaded_model, task)
        for task in tasks
    )
    random_episodes = tuple(
        run_random_episode(
            environment,
            task,
            seed=(seed * 10_000) + index,
        )
        for index, task in enumerate(tasks)
    )
    untrained_model = TabularTransitionModel()
    untrained_episodes = tuple(
        run_model_based_episode(
            environment,
            untrained_model,
            task,
            policy_name="untrained_model_ablation",
        )
        for task in tasks
    )
    return WorldBenchmark(
        seed=seed,
        world_id=environment.world_id,
        training_transition_count=len(experiences),
        model_snapshot_digest=snapshot_digest(reloaded_model),
        reserved_task_count=len(tasks),
        known_transition_accuracy=evaluate_known_transition_accuracy(
            environment, reloaded_model
        ),
        model_based=PolicySummary.from_episodes(
            "learned_model_planner", model_episodes
        ),
        random_policy=PolicySummary.from_episodes(
            "seeded_random", random_episodes
        ),
        untrained_ablation=PolicySummary.from_episodes(
            "untrained_model_ablation", untrained_episodes
        ),
    )


def run_active_exploration_world_benchmark(
    seed: int,
    *,
    budget: int = 30,
    task_limit: int = 24,
) -> ActiveExplorationWorldBenchmark:
    active_training_world = make_benchmark_world(seed)
    active_model = TabularTransitionModel()
    active_trace = ActiveTransitionExplorer(
        active_model,
        active_training_world.action_space,
    ).explore(
        active_training_world,
        start=active_training_world.states[0],
        budget=budget,
    )

    random_training_world = make_benchmark_world(seed)
    random_model = TabularTransitionModel()
    random_trace = run_random_transition_exploration(
        random_training_world,
        random_model,
        start=random_training_world.states[0],
        budget=budget,
        seed=seed ^ 0xA11CE,
    )

    # Reload both snapshots so evaluation depends on persisted learned state,
    # not object identity or hidden references to training environments.
    active_model = TabularTransitionModel.from_snapshot(
        active_model.to_snapshot()
    )
    random_model = TabularTransitionModel.from_snapshot(
        random_model.to_snapshot()
    )
    evaluator_world = make_benchmark_world(seed)
    tasks = _reserved_tasks(
        evaluator_world,
        seed=seed,
        task_limit=task_limit,
    )
    active_evaluation_world = make_benchmark_world(seed)
    random_evaluation_world = make_benchmark_world(seed)
    active_episodes = tuple(
        run_model_based_episode(
            active_evaluation_world,
            active_model,
            task,
            policy_name="active_exploration_model",
        )
        for task in tasks
    )
    random_episodes = tuple(
        run_model_based_episode(
            random_evaluation_world,
            random_model,
            task,
            policy_name="random_exploration_model",
        )
        for task in tasks
    )
    return ActiveExplorationWorldBenchmark(
        seed=seed,
        world_id=evaluator_world.world_id,
        budget=budget,
        possible_transition_pairs=(
            len(evaluator_world.states) * len(evaluator_world.action_space)
        ),
        active_trace=active_trace,
        random_trace=random_trace,
        active_model=PolicySummary.from_episodes(
            "active_exploration_model", active_episodes
        ),
        random_exploration_model=PolicySummary.from_episodes(
            "random_exploration_model", random_episodes
        ),
    )


def run_active_exploration_suite(
    seeds: Iterable[int] = range(5010, 5030),
    *,
    budget: int = 30,
    task_limit: int = 24,
) -> ActiveExplorationSuiteReport:
    normalized_seeds = tuple(int(seed) for seed in seeds)
    if not normalized_seeds:
        raise ValidationError("at least one seed is required")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValidationError("seeds must be unique")
    worlds = tuple(
        run_active_exploration_world_benchmark(
            seed,
            budget=budget,
            task_limit=task_limit,
        )
        for seed in normalized_seeds
    )
    episodes = sum(
        world.active_model.episodes for world in worlds
    )
    active_successes = sum(
        world.active_model.successes for world in worlds
    )
    random_successes = sum(
        world.random_exploration_model.successes for world in worlds
    )
    active_coverage = fmean(world.active_coverage for world in worlds)
    random_coverage = fmean(world.random_coverage for world in worlds)
    active_success_rate = active_successes / episodes
    random_success_rate = random_successes / episodes
    return ActiveExplorationSuiteReport(
        seeds=normalized_seeds,
        worlds=worlds,
        world_count=len(worlds),
        budget_per_world=budget,
        training_step_count=budget * len(worlds) * 2,
        evaluation_episode_count_per_policy=episodes,
        active_coverage=active_coverage,
        random_coverage=random_coverage,
        coverage_delta=active_coverage - random_coverage,
        active_task_success_rate=active_success_rate,
        random_exploration_task_success_rate=random_success_rate,
        task_success_delta=active_success_rate - random_success_rate,
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "No evaluation start-goal task was presented during transition "
            "collection; both policies explored without goal labels. "
            "State-action dynamics were not held out."
        ),
        limitations=(
            "The active exploration rule is hand-authored rather than learned.",
            "The action vocabulary and common start state are supplied by the harness.",
            "The environment is deterministic, finite, symbolic, and fully observable.",
            "Evaluation recombines observed same-world dynamics; it does not test cross-world transfer.",
            "The evaluator is local and is not independent E3 evidence.",
            "Success does not imply consciousness, general intelligence, emotion, or personhood.",
        ),
    )


def run_cognitive_suite(
    seeds: Iterable[int] = range(5010, 5030),
    *,
    task_limit: int = 24,
) -> CognitiveSuiteReport:
    normalized_seeds = tuple(int(seed) for seed in seeds)
    if not normalized_seeds:
        raise ValidationError("at least one seed is required")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValidationError("seeds must be unique")
    worlds = tuple(
        run_world_benchmark(seed, task_limit=task_limit)
        for seed in normalized_seeds
    )
    episodes = sum(world.reserved_task_count for world in worlds)
    model_successes = sum(world.model_based.successes for world in worlds)
    random_successes = sum(world.random_policy.successes for world in worlds)
    untrained_successes = sum(
        world.untrained_ablation.successes for world in worlds
    )
    model_rate = model_successes / episodes
    random_rate = random_successes / episodes
    untrained_rate = untrained_successes / episodes
    return CognitiveSuiteReport(
        seeds=normalized_seeds,
        worlds=worlds,
        world_count=len(worlds),
        evaluation_episode_count=episodes,
        training_transition_count=sum(
            world.training_transition_count for world in worlds
        ),
        model_based_success_rate=model_rate,
        random_success_rate=random_rate,
        untrained_success_rate=untrained_rate,
        known_transition_accuracy=fmean(
            world.known_transition_accuracy for world in worlds
        ),
        success_rate_delta=model_rate - random_rate,
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Start-goal task pairs were excluded from controlled transition "
            "probes; state-action transition pairs were not held out."
        ),
        limitations=(
            "The transition census is exhaustive and is not autonomous exploration.",
            "The environment is deterministic, finite, symbolic, and fully observable.",
            "The model recombines learned transitions but does not generalize to unseen dynamics.",
            "The evaluator is authored and executed in the same codebase, so it is not independent E3 evidence.",
            "Success does not imply consciousness, general intelligence, emotion, or personhood.",
        ),
    )


def record_suite_result(
    kernel: DarwinKernelV50,
    report: CognitiveSuiteReport,
    *,
    minimum_delta: float = 0.20,
) -> ObservationResult:
    """Record a local benchmark result through the v50 causal goal protocol."""

    if not math.isfinite(minimum_delta):
        raise ValidationError("minimum_delta must be finite")
    goal = kernel.create_goal(
        session_id=f"cognitive-lab:{report.seeds[0]}:{report.seeds[-1]}",
        description="Model-based policy exceeds the seeded-random baseline",
        evidence_source=LOCAL_EVALUATOR_SOURCE,
        condition=ComparisonCondition(
            "success_rate_delta",
            ComparisonOperator.GREATER_THAN_OR_EQUAL,
            minimum_delta,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-opaque-graph-task-recombination",
        parameters={
            "seeds": list(report.seeds),
            "world_count": report.world_count,
            "evaluation_episode_count": report.evaluation_episode_count,
            "held_out_definition": report.held_out_definition,
            "evidence_level": report.evidence_level,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_EVALUATOR_SOURCE,
        metrics={
            "model_based_success_rate": report.model_based_success_rate,
            "random_success_rate": report.random_success_rate,
            "untrained_success_rate": report.untrained_success_rate,
            "known_transition_accuracy": report.known_transition_accuracy,
            "success_rate_delta": report.success_rate_delta,
            "evaluation_episode_count": report.evaluation_episode_count,
        },
    )


def record_active_exploration_result(
    kernel: DarwinKernelV50,
    report: ActiveExplorationSuiteReport,
    *,
    minimum_task_delta: float = 0.20,
) -> ObservationResult:
    """Record H50-L2 as a local, unauthenticated benchmark observation."""

    if not math.isfinite(minimum_task_delta):
        raise ValidationError("minimum_task_delta must be finite")
    goal = kernel.create_goal(
        session_id=f"active-exploration:{report.seeds[0]}:{report.seeds[-1]}",
        description=(
            "Active transition selection improves held-out task success "
            "over random transition selection"
        ),
        evidence_source=LOCAL_EVALUATOR_SOURCE,
        condition=ComparisonCondition(
            "task_success_delta",
            ComparisonOperator.GREATER_THAN_OR_EQUAL,
            minimum_task_delta,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-budgeted-active-transition-exploration",
        parameters={
            "seeds": list(report.seeds),
            "world_count": report.world_count,
            "budget_per_world": report.budget_per_world,
            "evaluation_episode_count_per_policy": (
                report.evaluation_episode_count_per_policy
            ),
            "held_out_definition": report.held_out_definition,
            "evidence_level": report.evidence_level,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_EVALUATOR_SOURCE,
        metrics={
            "active_coverage": report.active_coverage,
            "random_coverage": report.random_coverage,
            "coverage_delta": report.coverage_delta,
            "active_task_success_rate": report.active_task_success_rate,
            "random_exploration_task_success_rate": (
                report.random_exploration_task_success_rate
            ),
            "task_success_delta": report.task_success_delta,
            "evaluation_episode_count_per_policy": (
                report.evaluation_episode_count_per_policy
            ),
        },
    )


def report_with_delta(
    report: CognitiveSuiteReport,
    *,
    model_success_rate: float,
    random_success_rate: float,
) -> CognitiveSuiteReport:
    """Create a diagnostic report variant used to test false-success handling."""

    if not 0.0 <= model_success_rate <= 1.0:
        raise ValidationError("model_success_rate must be within [0, 1]")
    if not 0.0 <= random_success_rate <= 1.0:
        raise ValidationError("random_success_rate must be within [0, 1]")
    return replace(
        report,
        model_based_success_rate=model_success_rate,
        random_success_rate=random_success_rate,
        success_rate_delta=model_success_rate - random_success_rate,
    )


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the narrow Darwin v50.1 cognitive learning benchmark."
    )
    parser.add_argument(
        "--seeds",
        type=_parse_seeds,
        default=tuple(range(5010, 5030)),
        help="comma-separated deterministic seeds",
    )
    parser.add_argument("--tasks-per-world", type=int, default=24)
    parser.add_argument(
        "--active-exploration",
        action="store_true",
        help="run H50-L2 budgeted exploration instead of the census benchmark",
    )
    parser.add_argument("--exploration-budget", type=int, default=30)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    if args.active_exploration:
        report: CognitiveSuiteReport | ActiveExplorationSuiteReport = (
            run_active_exploration_suite(
                args.seeds,
                budget=args.exploration_budget,
                task_limit=args.tasks_per_world,
            )
        )
    else:
        report = run_cognitive_suite(
            args.seeds,
            task_limit=args.tasks_per_world,
        )
    print(
        json.dumps(
            report.to_dict(include_worlds=args.details),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
