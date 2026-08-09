"""Development evaluator for the minimum integrated cognitive cycle.

The evaluator composes the causal kernel, frozen H50-L10 learned model,
replanning controller, replay-checked checkpoint, and deterministic predictive
world.  It remains a synthetic E1 development harness and cannot register an
integrated capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import random
from statistics import fmean
import tempfile
from typing import Iterable

from .integrated_cycle_lab import IntegratedPlanningCycle
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    GoalStatus,
    ValidationError,
)
from .predictive_planning_evaluation import (
    PREDICTIVE_MAX_EVALUATION_STEPS,
    PREDICTIVE_TASKS_PER_WORLD,
    PredictivePlanningTask,
    make_predictive_tasks,
    run_predictive_exploration,
)
from .predictive_planning_lab import (
    PLANNING_ACTIONS,
    PredictiveHistoryModel,
    PredictivePlanningWorld,
    PredictiveWorldSpecification,
    next_history,
)


INTEGRATED_CYCLE_TEST_SEEDS = tuple(range(38900, 38904))
INTEGRATED_CYCLE_DEVELOPMENT_SEEDS = tuple(range(39000, 39032))
INTEGRATED_CYCLE_BOOTSTRAP_SEED = 39700
INTEGRATED_CYCLE_BOOTSTRAP_SAMPLES = 2_000
INTEGRATED_CYCLE_EXPLORATION_BUDGET = 486
INTEGRATED_CYCLE_RESTART_AFTER_STEPS = 2
INTEGRATED_CYCLE_EVIDENCE_SOURCE = "integrated-cycle:local-evaluator"


def _normalize_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    result = tuple(seeds)
    if (
        not result
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
        or any(
            isinstance(seed, bool)
            or not isinstance(seed, int)
            or seed < 0
            for seed in result
        )
    ):
        raise ValidationError(
            "integrated-cycle seeds must be unique increasing integers"
        )
    return result


@dataclass(frozen=True, slots=True)
class IntegratedEpisodeResult:
    success: bool
    steps: int
    actions: tuple[str, ...]
    prediction_match_rate: float
    model_frozen: bool
    checkpoint_replay_exact: bool
    kernel_restart_exact: bool
    kernel_lineage_valid: bool
    action_observation_correlation_valid: bool
    no_premature_success: bool

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise ValidationError("integrated episode success is invalid")
        if (
            isinstance(self.steps, bool)
            or not isinstance(self.steps, int)
            or self.steps < 1
            or self.steps != len(self.actions)
        ):
            raise ValidationError("integrated episode steps are invalid")
        if any(action not in PLANNING_ACTIONS for action in self.actions):
            raise ValidationError("integrated episode action is invalid")
        if (
            isinstance(self.prediction_match_rate, bool)
            or not isinstance(self.prediction_match_rate, (int, float))
            or not math.isfinite(self.prediction_match_rate)
            or not 0.0 <= self.prediction_match_rate <= 1.0
        ):
            raise ValidationError(
                "integrated prediction-match rate is invalid"
            )
        if any(
            not isinstance(value, bool)
            for value in (
                self.model_frozen,
                self.checkpoint_replay_exact,
                self.kernel_restart_exact,
                self.kernel_lineage_valid,
                self.action_observation_correlation_valid,
                self.no_premature_success,
            )
        ):
            raise ValidationError("integrated integrity flag is invalid")


@dataclass(frozen=True, slots=True)
class IntegratedWorldResult:
    seed: int
    task_count: int
    candidate_success_rate: float
    uninterrupted_success_rate: float
    rotated_success_rate: float
    random_success_rate: float
    oracle_success_rate: float
    restart_action_exact_rate: float
    prediction_match_rate: float
    model_frozen_rate: float
    checkpoint_replay_rate: float
    kernel_restart_rate: float
    kernel_lineage_rate: float
    action_observation_correlation_rate: float
    no_premature_success_rate: float
    mean_candidate_steps: float

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("integrated world seed is invalid")
        if (
            isinstance(self.task_count, bool)
            or not isinstance(self.task_count, int)
            or self.task_count < 1
        ):
            raise ValidationError("integrated world task count is invalid")
        for value in (
            self.candidate_success_rate,
            self.uninterrupted_success_rate,
            self.rotated_success_rate,
            self.random_success_rate,
            self.oracle_success_rate,
            self.restart_action_exact_rate,
            self.prediction_match_rate,
            self.model_frozen_rate,
            self.checkpoint_replay_rate,
            self.kernel_restart_rate,
            self.kernel_lineage_rate,
            self.action_observation_correlation_rate,
            self.no_premature_success_rate,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError("integrated world rate is invalid")
        if (
            isinstance(self.mean_candidate_steps, bool)
            or not isinstance(self.mean_candidate_steps, (int, float))
            or not math.isfinite(self.mean_candidate_steps)
            or self.mean_candidate_steps < 1.0
        ):
            raise ValidationError("integrated mean steps are invalid")


@dataclass(frozen=True, slots=True)
class IntegratedCycleDevelopmentReport:
    seeds: tuple[int, ...]
    worlds: tuple[IntegratedWorldResult, ...]

    def __post_init__(self) -> None:
        if _normalize_seeds(self.seeds) != self.seeds:
            raise ValidationError("integrated report seeds are not canonical")
        if tuple(item.seed for item in self.worlds) != self.seeds:
            raise ValidationError("integrated report worlds are unbalanced")

    @property
    def task_count(self) -> int:
        return sum(item.task_count for item in self.worlds)

    def pooled_rate(self, field: str) -> float:
        if field not in {
            "candidate_success_rate",
            "uninterrupted_success_rate",
            "rotated_success_rate",
            "random_success_rate",
            "oracle_success_rate",
            "restart_action_exact_rate",
            "prediction_match_rate",
            "model_frozen_rate",
            "checkpoint_replay_rate",
            "kernel_restart_rate",
            "kernel_lineage_rate",
            "action_observation_correlation_rate",
            "no_premature_success_rate",
        }:
            raise ValidationError("integrated report field is invalid")
        return sum(
            getattr(item, field) * item.task_count for item in self.worlds
        ) / self.task_count

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "experiment": "034",
            "status": "development-only",
            "capability_claim": False,
            "h50_l16_registered": False,
            "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
            "seeds": list(self.seeds),
            "world_count": len(self.worlds),
            "task_count": self.task_count,
            "exploration_interactions_per_world": (
                INTEGRATED_CYCLE_EXPLORATION_BUDGET
            ),
            "tasks_per_world": PREDICTIVE_TASKS_PER_WORLD,
            "maximum_target_steps": PREDICTIVE_MAX_EVALUATION_STEPS,
            "restart_after_steps": INTEGRATED_CYCLE_RESTART_AFTER_STEPS,
            "persistence_boundary": (
                "kernel reopened from SQLite and agent restored from a causal "
                "checkpoint; evaluator-owned environment remains in memory"
            ),
            "success_rates": {
                policy: self.pooled_rate(f"{policy}_success_rate")
                for policy in (
                    "candidate",
                    "uninterrupted",
                    "rotated",
                    "random",
                    "oracle",
                )
            },
            "candidate_improvement": {
                "versus_rotated": self.pooled_rate(
                    "candidate_success_rate"
                )
                - self.pooled_rate("rotated_success_rate"),
                "versus_random": self.pooled_rate(
                    "candidate_success_rate"
                )
                - self.pooled_rate("random_success_rate"),
                "versus_uninterrupted": self.pooled_rate(
                    "candidate_success_rate"
                )
                - self.pooled_rate("uninterrupted_success_rate"),
            },
            "integrity": {
                field: self.pooled_rate(field)
                for field in (
                    "restart_action_exact_rate",
                    "prediction_match_rate",
                    "model_frozen_rate",
                    "checkpoint_replay_rate",
                    "kernel_restart_rate",
                    "kernel_lineage_rate",
                    "action_observation_correlation_rate",
                    "no_premature_success_rate",
                )
            },
            "mean_candidate_steps": fmean(
                item.mean_candidate_steps for item in self.worlds
            ),
        }


def _snapshot_digest(cycle: IntegratedPlanningCycle) -> str:
    return hashlib.sha256(cycle.to_snapshot().encode("utf-8")).hexdigest()


def _expected_event_kinds(*, steps: int, success: bool) -> tuple[str, ...]:
    result = ["goal.created", "goal.started"]
    for index in range(steps):
        result.extend(("action.dispatched", "observation.recorded"))
        final_success = success and index == steps - 1
        result.append(
            "goal.succeeded"
            if final_success
            else "goal.condition_unsatisfied"
        )
        if not final_success and index < steps - 1:
            result.append("goal.continued")
    return tuple(result)


def _run_integrated_episode(
    *,
    seed: int,
    task: PredictivePlanningTask,
    model_snapshot: str,
    restart: bool,
) -> IntegratedEpisodeResult:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "integrated-cycle.db"
        kernel = DarwinKernelV50.open(database)
        try:
            goal = kernel.create_goal(
                session_id=f"integrated-cycle:{seed}:{int(restart)}",
                description="Reach the externally supplied history state",
                evidence_source=INTEGRATED_CYCLE_EVIDENCE_SOURCE,
                condition=ComparisonCondition(
                    "goal_reached",
                    ComparisonOperator.EQUAL,
                    1,
                ),
            )
            goal = kernel.start_goal(goal.goal_id)
            cycle = IntegratedPlanningCycle(
                model=PredictiveHistoryModel.from_snapshot(model_snapshot),
                session_id=goal.session_id,
                goal_id=goal.goal_id,
                evidence_source=goal.evidence_source,
                initial_history=task.start,
                goal_history=task.goal,
                max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
            )
            world = PredictivePlanningWorld(seed)
            world.reset(
                start=task.start,
                goal=task.goal,
                max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
            )
            checkpoint_exact = True
            kernel_restart_exact = True
            observations_accepted = True
            restarted = False
            for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
                decision = cycle.choose_action()
                checkpoint_digest = _snapshot_digest(cycle)
                goal = kernel.dispatch_action(
                    goal.goal_id,
                    action_name="predictive-history-step",
                    parameters={
                        "action": decision.action,
                        "step_index": decision.step_index,
                        "current_history": list(decision.current_history),
                        "goal_history": list(decision.goal_history),
                        "checkpoint_digest": checkpoint_digest,
                    },
                )
                step = world.step(decision.action)
                observed = cycle.observe(
                    action=decision.action,
                    next_cue=step.observation.cue,
                )
                recorded = kernel.record_observation(
                    goal.goal_id,
                    action_id=goal.expected_action_id or "",
                    source=INTEGRATED_CYCLE_EVIDENCE_SOURCE,
                    metrics={
                        "goal_reached": int(observed.goal_reached),
                        "observed_cue": observed.observed_cue,
                        "step_index": observed.step_index,
                        "prediction_matched": observed.prediction_matched,
                    },
                )
                observations_accepted &= recorded.accepted
                goal = recorded.goal
                if observed.goal_reached:
                    break
                if cycle.step_index >= PREDICTIVE_MAX_EVALUATION_STEPS:
                    break
                if (
                    restart
                    and not restarted
                    and cycle.step_index
                    == INTEGRATED_CYCLE_RESTART_AFTER_STEPS
                ):
                    checkpoint = cycle.to_snapshot()
                    persisted_goal = kernel.get_goal(goal.goal_id)
                    kernel.close()
                    kernel = DarwinKernelV50.open(database)
                    restored = IntegratedPlanningCycle.from_snapshot(checkpoint)
                    checkpoint_exact &= restored.to_snapshot() == checkpoint
                    kernel_restart_exact &= (
                        kernel.get_goal(goal.goal_id) == persisted_goal
                        and restored.goal_id == persisted_goal.goal_id
                        and restored.session_id == persisted_goal.session_id
                    )
                    cycle = restored
                    goal = persisted_goal
                    restarted = True
                goal = kernel.continue_goal(goal.goal_id)
            events = kernel.goal_events(goal.goal_id)
            success = goal.status is GoalStatus.SUCCEEDED
            actions = cycle.action_history
            kinds = tuple(event.kind for event in events)
            linear = all(
                event.parent_event_id == previous.event_id
                for previous, event in zip(events, events[1:])
            )
            dispatches = tuple(
                event for event in events if event.kind == "action.dispatched"
            )
            recorded_events = tuple(
                event
                for event in events
                if event.kind == "observation.recorded"
            )
            correlation = (
                observations_accepted
                and len(dispatches) == len(actions) == len(recorded_events)
                and all(
                    dispatch.action_id == observation.action_id
                    and dispatch.payload.get("parameters", {}).get("action")
                    == action
                    for dispatch, observation, action in zip(
                        dispatches,
                        recorded_events,
                        actions,
                        strict=True,
                    )
                )
            )
            successes = tuple(
                event for event in events if event.kind == "goal.succeeded"
            )
            no_premature = (
                len(successes) == int(success)
                and all(
                    event.payload.get("satisfied") is True
                    for event in successes
                )
                and (
                    not success
                    or recorded_events[-1].payload.get("metrics", {}).get(
                        "goal_reached"
                    )
                    == 1
                )
            )
            return IntegratedEpisodeResult(
                success=success,
                steps=len(actions),
                actions=actions,
                prediction_match_rate=fmean(
                    float(value) for value in cycle.prediction_matches
                ),
                model_frozen=cycle.model_frozen,
                checkpoint_replay_exact=(
                    checkpoint_exact and (not restart or restarted)
                ),
                kernel_restart_exact=(
                    kernel_restart_exact and (not restart or restarted)
                ),
                kernel_lineage_valid=(
                    linear
                    and kinds
                    == _expected_event_kinds(
                        steps=len(actions),
                        success=success,
                    )
                ),
                action_observation_correlation_valid=correlation,
                no_premature_success=no_premature,
            )
        finally:
            if not kernel.store.closed:
                kernel.close()


def _run_cycle_policy(
    *,
    seed: int,
    task: PredictivePlanningTask,
    model_snapshot: str,
    action_rotation: int,
) -> bool:
    cycle = IntegratedPlanningCycle(
        model=PredictiveHistoryModel.from_snapshot(model_snapshot),
        session_id="integrated-cycle:ablation",
        goal_id="goal:ablation",
        evidence_source=INTEGRATED_CYCLE_EVIDENCE_SOURCE,
        initial_history=task.start,
        goal_history=task.goal,
        max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
        action_rotation=action_rotation,
    )
    world = PredictivePlanningWorld(seed)
    world.reset(
        start=task.start,
        goal=task.goal,
        max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
    )
    for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
        decision = cycle.choose_action()
        step = world.step(decision.action)
        cycle.observe(
            action=decision.action,
            next_cue=step.observation.cue,
        )
        if cycle.goal_reached:
            return True
    return False


def _run_random_policy(
    *,
    seed: int,
    task: PredictivePlanningTask,
    task_index: int,
) -> bool:
    rng = random.Random(seed ^ (task_index * 0x9E37) ^ 0x1C7A)
    world = PredictivePlanningWorld(seed)
    observation = world.reset(
        start=task.start,
        goal=task.goal,
        max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
    )
    history = task.start
    for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
        step = world.step(rng.choice(PLANNING_ACTIONS))
        history = next_history(history, step.observation.cue)
        if step.observation.terminated:
            return history == task.goal
        if step.observation.truncated:
            break
    return False


def evaluate_integrated_world(seed: int) -> IntegratedWorldResult:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError("integrated world seed is invalid")
    explorer, exploration_world = run_predictive_exploration(
        seed,
        budget=INTEGRATED_CYCLE_EXPLORATION_BUDGET,
    )
    model_snapshot = explorer.model.to_snapshot()
    specification: PredictiveWorldSpecification = (
        exploration_world.specification
    )
    tasks = make_predictive_tasks(
        specification,
        count=PREDICTIVE_TASKS_PER_WORLD,
    )
    candidate: list[IntegratedEpisodeResult] = []
    uninterrupted: list[IntegratedEpisodeResult] = []
    rotated: list[bool] = []
    random_results: list[bool] = []
    oracle: list[bool] = []
    for task_index, task in enumerate(tasks, start=1):
        restarted = _run_integrated_episode(
            seed=seed,
            task=task,
            model_snapshot=model_snapshot,
            restart=True,
        )
        continuous = _run_integrated_episode(
            seed=seed,
            task=task,
            model_snapshot=model_snapshot,
            restart=False,
        )
        candidate.append(restarted)
        uninterrupted.append(continuous)
        rotated.append(
            _run_cycle_policy(
                seed=seed,
                task=task,
                model_snapshot=model_snapshot,
                action_rotation=1,
            )
        )
        random_results.append(
            _run_random_policy(
                seed=seed,
                task=task,
                task_index=task_index,
            )
        )
        oracle.append(
            specification.shortest_plan(task.start, task.goal)
            == task.oracle_actions
        )

    def rate(values: Iterable[bool]) -> float:
        rows = tuple(values)
        return fmean(float(value) for value in rows)

    return IntegratedWorldResult(
        seed=seed,
        task_count=len(tasks),
        candidate_success_rate=rate(item.success for item in candidate),
        uninterrupted_success_rate=rate(
            item.success for item in uninterrupted
        ),
        rotated_success_rate=rate(rotated),
        random_success_rate=rate(random_results),
        oracle_success_rate=rate(oracle),
        restart_action_exact_rate=rate(
            left.actions == right.actions and left.success == right.success
            for left, right in zip(candidate, uninterrupted, strict=True)
        ),
        prediction_match_rate=fmean(
            item.prediction_match_rate for item in candidate
        ),
        model_frozen_rate=rate(item.model_frozen for item in candidate),
        checkpoint_replay_rate=rate(
            item.checkpoint_replay_exact for item in candidate
        ),
        kernel_restart_rate=rate(
            item.kernel_restart_exact for item in candidate
        ),
        kernel_lineage_rate=rate(
            item.kernel_lineage_valid for item in candidate
        ),
        action_observation_correlation_rate=rate(
            item.action_observation_correlation_valid for item in candidate
        ),
        no_premature_success_rate=rate(
            item.no_premature_success for item in candidate
        ),
        mean_candidate_steps=fmean(item.steps for item in candidate),
    )


def run_integrated_cycle_development(
    *,
    seeds: Iterable[int],
) -> IntegratedCycleDevelopmentReport:
    normalized = _normalize_seeds(seeds)
    return IntegratedCycleDevelopmentReport(
        seeds=normalized,
        worlds=tuple(evaluate_integrated_world(seed) for seed in normalized),
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


def bootstrap_integrated_cycle_metrics(
    report: IntegratedCycleDevelopmentReport,
    *,
    seed: int = INTEGRATED_CYCLE_BOOTSTRAP_SEED,
    samples: int = INTEGRATED_CYCLE_BOOTSTRAP_SAMPLES,
) -> dict[str, dict[str, float]]:
    if not isinstance(report, IntegratedCycleDevelopmentReport):
        raise ValidationError("integrated development report is invalid")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
        or isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("integrated bootstrap configuration is invalid")
    rng = random.Random(seed)
    value_sets = {
        "candidate_success_rate": tuple(
            item.candidate_success_rate for item in report.worlds
        ),
        "candidate_minus_rotated_success_rate": tuple(
            item.candidate_success_rate - item.rotated_success_rate
            for item in report.worlds
        ),
        "candidate_minus_random_success_rate": tuple(
            item.candidate_success_rate - item.random_success_rate
            for item in report.worlds
        ),
        "candidate_minus_uninterrupted_success_rate": tuple(
            item.candidate_success_rate - item.uninterrupted_success_rate
            for item in report.worlds
        ),
        "restart_action_exact_rate": tuple(
            item.restart_action_exact_rate for item in report.worlds
        ),
    }
    result: dict[str, dict[str, float]] = {}
    for name, values in value_sets.items():
        means = [
            fmean(rng.choice(values) for _ in values)
            for _ in range(samples)
        ]
        result[name] = {
            "mean": fmean(values),
            "low": _quantile(means, 0.025),
            "high": _quantile(means, 0.975),
        }
    return result


def integrated_cycle_development_record(
    report: IntegratedCycleDevelopmentReport,
    *,
    bootstrap_seed: int = INTEGRATED_CYCLE_BOOTSTRAP_SEED,
    bootstrap_samples: int = INTEGRATED_CYCLE_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    result = report.to_summary_dict()
    result["bootstrap_seed"] = bootstrap_seed
    result["bootstrap_samples"] = bootstrap_samples
    result["development_intervals"] = bootstrap_integrated_cycle_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    return result
