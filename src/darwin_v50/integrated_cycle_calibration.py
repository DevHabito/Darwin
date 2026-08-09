"""Independent durability calibration for the integrated planning cycle."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import random
from statistics import fmean
import tempfile
from typing import Iterable

from .integrated_cycle_durability import IntegratedRecoveryBundle
from .integrated_cycle_evaluation import (
    INTEGRATED_CYCLE_EVIDENCE_SOURCE,
    INTEGRATED_CYCLE_EXPLORATION_BUDGET,
    _expected_event_kinds,
    _run_random_policy,
)
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
    PredictiveHistoryModel,
    PredictivePlanningWorld,
    PredictiveWorldSpecification,
)


INTEGRATED_CALIBRATION_TEST_SEEDS = tuple(range(39900, 39904))
INTEGRATED_CALIBRATION_SEEDS = tuple(range(40000, 40064))
INTEGRATED_CALIBRATION_BOOTSTRAP_SEED = 40700
INTEGRATED_CALIBRATION_BOOTSTRAP_SAMPLES = 5_000
INTEGRATED_RESTART_MODES = (
    "after_observation_1",
    "after_observation_2",
    "after_observation_3",
    "pending_before_dispatch_2",
)


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
            "integrated calibration seeds must be unique increasing integers"
        )
    return result


def _restart_step(mode: str) -> int | None:
    if mode not in INTEGRATED_RESTART_MODES:
        raise ValidationError("integrated restart mode is invalid")
    if mode.startswith("after_observation_"):
        return int(mode[-1])
    return None


@dataclass(frozen=True, slots=True)
class DurableIntegratedEpisodeResult:
    restart_mode: str
    success: bool
    steps: int
    actions: tuple[str, ...]
    prediction_match_rate: float
    model_frozen: bool
    recovery_executed: bool
    checkpoint_exact: bool
    kernel_restart_exact: bool
    environment_replay_exact: bool
    pending_decision_preserved: bool
    kernel_cycle_binding_exact: bool
    kernel_lineage_valid: bool
    action_observation_correlation_valid: bool
    no_premature_success: bool

    def __post_init__(self) -> None:
        if self.restart_mode not in INTEGRATED_RESTART_MODES:
            raise ValidationError("durable episode restart mode is invalid")
        if (
            not isinstance(self.success, bool)
            or isinstance(self.steps, bool)
            or not isinstance(self.steps, int)
            or self.steps < 1
            or self.steps != len(self.actions)
        ):
            raise ValidationError("durable episode outcome is invalid")
        if (
            isinstance(self.prediction_match_rate, bool)
            or not isinstance(self.prediction_match_rate, (int, float))
            or not math.isfinite(self.prediction_match_rate)
            or not 0.0 <= self.prediction_match_rate <= 1.0
        ):
            raise ValidationError("durable prediction rate is invalid")
        if any(
            not isinstance(value, bool)
            for value in (
                self.model_frozen,
                self.recovery_executed,
                self.checkpoint_exact,
                self.kernel_restart_exact,
                self.environment_replay_exact,
                self.pending_decision_preserved,
                self.kernel_cycle_binding_exact,
                self.kernel_lineage_valid,
                self.action_observation_correlation_valid,
                self.no_premature_success,
            )
        ):
            raise ValidationError("durable integrity flag is invalid")


def _capture_reopen_restore(
    *,
    kernel: DarwinKernelV50,
    database: Path,
    cycle: IntegratedPlanningCycle,
    world_seed: int,
    task: PredictivePlanningTask,
) -> tuple[DarwinKernelV50, IntegratedPlanningCycle, PredictivePlanningWorld, bool, bool, bool, bool]:
    goal = kernel.get_goal(cycle.goal_id)
    snapshot = IntegratedRecoveryBundle.capture(
        cycle=cycle,
        goal=goal,
        events=kernel.goal_events(goal.goal_id),
        world_seed=world_seed,
        task=task,
    )
    pending = cycle.pending_decision
    persisted_goal = goal
    kernel.close()
    reopened = DarwinKernelV50.open(database)
    restored = IntegratedRecoveryBundle.restore(snapshot, kernel=reopened)
    kernel_exact = reopened.get_goal(goal.goal_id) == persisted_goal
    binding_exact = (
        restored.cycle.goal_id == restored.goal.goal_id
        and restored.cycle.session_id == restored.goal.session_id
        and restored.cycle.evidence_source == restored.goal.evidence_source
    )
    pending_exact = restored.cycle.pending_decision == pending
    return (
        reopened,
        restored.cycle,
        restored.world,
        restored.checkpoint_exact,
        kernel_exact,
        restored.environment_replay_exact,
        binding_exact and pending_exact,
    )


def _run_durable_episode(
    *,
    seed: int,
    task: PredictivePlanningTask,
    model_snapshot: str,
    restart_mode: str,
) -> DurableIntegratedEpisodeResult:
    after_observation = _restart_step(restart_mode)
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "durable-integrated-cycle.db"
        kernel = DarwinKernelV50.open(database)
        try:
            goal = kernel.create_goal(
                session_id=f"integrated-calibration:{seed}:{restart_mode}",
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
            restarted = False
            checkpoint_exact = True
            kernel_exact = True
            environment_exact = True
            binding_exact = True
            pending_exact = True
            observations_accepted = True
            for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
                decision = cycle.choose_action()
                if (
                    restart_mode == "pending_before_dispatch_2"
                    and not restarted
                    and decision.step_index == 1
                ):
                    expected_pending = decision
                    (
                        kernel,
                        cycle,
                        world,
                        restored_checkpoint,
                        restored_kernel,
                        restored_environment,
                        restored_binding,
                    ) = _capture_reopen_restore(
                        kernel=kernel,
                        database=database,
                        cycle=cycle,
                        world_seed=seed,
                        task=task,
                    )
                    checkpoint_exact &= restored_checkpoint
                    kernel_exact &= restored_kernel
                    environment_exact &= restored_environment
                    binding_exact &= restored_binding
                    pending_exact &= cycle.pending_decision == expected_pending
                    decision = cycle.choose_action()
                    restarted = True
                    goal = kernel.get_goal(goal.goal_id)
                goal = kernel.dispatch_action(
                    goal.goal_id,
                    action_name="predictive-history-step",
                    parameters={
                        "action": decision.action,
                        "step_index": decision.step_index,
                        "current_history": list(decision.current_history),
                        "goal_history": list(decision.goal_history),
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
                    after_observation is not None
                    and not restarted
                    and cycle.step_index == after_observation
                ):
                    (
                        kernel,
                        cycle,
                        world,
                        restored_checkpoint,
                        restored_kernel,
                        restored_environment,
                        restored_binding,
                    ) = _capture_reopen_restore(
                        kernel=kernel,
                        database=database,
                        cycle=cycle,
                        world_seed=seed,
                        task=task,
                    )
                    checkpoint_exact &= restored_checkpoint
                    kernel_exact &= restored_kernel
                    environment_exact &= restored_environment
                    binding_exact &= restored_binding
                    pending_exact &= cycle.pending_decision is None
                    restarted = True
                    goal = kernel.get_goal(goal.goal_id)
                goal = kernel.continue_goal(goal.goal_id)

            events = kernel.goal_events(goal.goal_id)
            actions = cycle.action_history
            success = goal.status is GoalStatus.SUCCEEDED
            kinds = tuple(event.kind for event in events)
            linear = all(
                event.parent_event_id == previous.event_id
                for previous, event in zip(events, events[1:])
            )
            dispatches = tuple(
                event for event in events if event.kind == "action.dispatched"
            )
            observations = tuple(
                event for event in events if event.kind == "observation.recorded"
            )
            correlation = (
                observations_accepted
                and len(dispatches) == len(actions) == len(observations)
                and all(
                    dispatch.action_id == observation.action_id
                    and dispatch.payload.get("parameters", {}).get("action")
                    == action
                    for dispatch, observation, action in zip(
                        dispatches,
                        observations,
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
                    or observations[-1].payload.get("metrics", {}).get(
                        "goal_reached"
                    )
                    == 1
                )
            )
            return DurableIntegratedEpisodeResult(
                restart_mode=restart_mode,
                success=success,
                steps=len(actions),
                actions=actions,
                prediction_match_rate=fmean(
                    float(value) for value in cycle.prediction_matches
                ),
                model_frozen=cycle.model_frozen,
                recovery_executed=restarted,
                checkpoint_exact=checkpoint_exact and restarted,
                kernel_restart_exact=kernel_exact and restarted,
                environment_replay_exact=environment_exact and restarted,
                pending_decision_preserved=pending_exact and restarted,
                kernel_cycle_binding_exact=binding_exact and restarted,
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


def _run_policy_trace(
    *,
    seed: int,
    task: PredictivePlanningTask,
    model_snapshot: str,
    action_rotation: int,
) -> tuple[bool, tuple[str, ...]]:
    cycle = IntegratedPlanningCycle(
        model=PredictiveHistoryModel.from_snapshot(model_snapshot),
        session_id="integrated-calibration:comparison",
        goal_id="goal:comparison",
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
            break
    return cycle.goal_reached, cycle.action_history


@dataclass(frozen=True, slots=True)
class IntegratedCalibrationWorldResult:
    seed: int
    task_count: int
    restart_mode_counts: tuple[int, ...]
    restart_mode_success_rates: tuple[float, ...]
    candidate_success_rate: float
    uninterrupted_success_rate: float
    rotated_success_rate: float
    random_success_rate: float
    oracle_success_rate: float
    restart_action_exact_rate: float
    prediction_match_rate: float
    model_frozen_rate: float
    recovery_executed_rate: float
    checkpoint_exact_rate: float
    kernel_restart_exact_rate: float
    environment_replay_exact_rate: float
    pending_decision_preserved_rate: float
    kernel_cycle_binding_exact_rate: float
    kernel_lineage_rate: float
    action_observation_correlation_rate: float
    no_premature_success_rate: float
    mean_candidate_steps: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or self.seed < 0
            or isinstance(self.task_count, bool)
            or not isinstance(self.task_count, int)
            or self.task_count < 1
        ):
            raise ValidationError("integrated calibration world is invalid")
        if (
            len(self.restart_mode_counts) != len(INTEGRATED_RESTART_MODES)
            or sum(self.restart_mode_counts) != self.task_count
            or len(self.restart_mode_success_rates)
            != len(INTEGRATED_RESTART_MODES)
        ):
            raise ValidationError("integrated restart balance is invalid")
        rates = (
            self.restart_mode_success_rates
            + (
                self.candidate_success_rate,
                self.uninterrupted_success_rate,
                self.rotated_success_rate,
                self.random_success_rate,
                self.oracle_success_rate,
                self.restart_action_exact_rate,
                self.prediction_match_rate,
                self.model_frozen_rate,
                self.recovery_executed_rate,
                self.checkpoint_exact_rate,
                self.kernel_restart_exact_rate,
                self.environment_replay_exact_rate,
                self.pending_decision_preserved_rate,
                self.kernel_cycle_binding_exact_rate,
                self.kernel_lineage_rate,
                self.action_observation_correlation_rate,
                self.no_premature_success_rate,
            )
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in rates
        ):
            raise ValidationError("integrated calibration rate is invalid")
        if (
            isinstance(self.mean_candidate_steps, bool)
            or not isinstance(self.mean_candidate_steps, (int, float))
            or not math.isfinite(self.mean_candidate_steps)
            or self.mean_candidate_steps < 1.0
        ):
            raise ValidationError("integrated calibration steps are invalid")


def evaluate_integrated_calibration_world(
    seed: int,
) -> IntegratedCalibrationWorldResult:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError("integrated calibration world seed is invalid")
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
    candidate: list[DurableIntegratedEpisodeResult] = []
    uninterrupted: list[bool] = []
    uninterrupted_actions: list[tuple[str, ...]] = []
    rotated: list[bool] = []
    random_results: list[bool] = []
    oracle: list[bool] = []
    for task_index, task in enumerate(tasks):
        mode = INTEGRATED_RESTART_MODES[
            task_index % len(INTEGRATED_RESTART_MODES)
        ]
        candidate.append(
            _run_durable_episode(
                seed=seed,
                task=task,
                model_snapshot=model_snapshot,
                restart_mode=mode,
            )
        )
        continuous_success, continuous_actions = _run_policy_trace(
            seed=seed,
            task=task,
            model_snapshot=model_snapshot,
            action_rotation=0,
        )
        uninterrupted.append(continuous_success)
        uninterrupted_actions.append(continuous_actions)
        rotated_success, _ = _run_policy_trace(
            seed=seed,
            task=task,
            model_snapshot=model_snapshot,
            action_rotation=1,
        )
        rotated.append(rotated_success)
        random_results.append(
            _run_random_policy(
                seed=seed,
                task=task,
                task_index=task_index + 1,
            )
        )
        oracle.append(
            specification.shortest_plan(task.start, task.goal)
            == task.oracle_actions
        )

    def rate(values: Iterable[bool]) -> float:
        rows = tuple(values)
        return fmean(float(value) for value in rows)

    integrity_fields = {
        "model_frozen_rate": "model_frozen",
        "recovery_executed_rate": "recovery_executed",
        "checkpoint_exact_rate": "checkpoint_exact",
        "kernel_restart_exact_rate": "kernel_restart_exact",
        "environment_replay_exact_rate": "environment_replay_exact",
        "pending_decision_preserved_rate": "pending_decision_preserved",
        "kernel_cycle_binding_exact_rate": "kernel_cycle_binding_exact",
        "kernel_lineage_rate": "kernel_lineage_valid",
        "action_observation_correlation_rate": (
            "action_observation_correlation_valid"
        ),
        "no_premature_success_rate": "no_premature_success",
    }
    mode_rows = {
        mode: tuple(item for item in candidate if item.restart_mode == mode)
        for mode in INTEGRATED_RESTART_MODES
    }
    return IntegratedCalibrationWorldResult(
        seed=seed,
        task_count=len(tasks),
        restart_mode_counts=tuple(
            len(mode_rows[mode]) for mode in INTEGRATED_RESTART_MODES
        ),
        restart_mode_success_rates=tuple(
            rate(item.success for item in mode_rows[mode])
            for mode in INTEGRATED_RESTART_MODES
        ),
        candidate_success_rate=rate(item.success for item in candidate),
        uninterrupted_success_rate=rate(uninterrupted),
        rotated_success_rate=rate(rotated),
        random_success_rate=rate(random_results),
        oracle_success_rate=rate(oracle),
        restart_action_exact_rate=rate(
            item.actions == actions and item.success == success
            for item, actions, success in zip(
                candidate,
                uninterrupted_actions,
                uninterrupted,
                strict=True,
            )
        ),
        prediction_match_rate=fmean(
            item.prediction_match_rate for item in candidate
        ),
        **{
            output: rate(getattr(item, source) for item in candidate)
            for output, source in integrity_fields.items()
        },
        mean_candidate_steps=fmean(item.steps for item in candidate),
    )


@dataclass(frozen=True, slots=True)
class IntegratedCalibrationReport:
    seeds: tuple[int, ...]
    worlds: tuple[IntegratedCalibrationWorldResult, ...]

    def __post_init__(self) -> None:
        if _normalize_seeds(self.seeds) != self.seeds:
            raise ValidationError("integrated calibration seeds are not canonical")
        if tuple(world.seed for world in self.worlds) != self.seeds:
            raise ValidationError("integrated calibration worlds are unbalanced")

    @property
    def task_count(self) -> int:
        return sum(world.task_count for world in self.worlds)

    def pooled_rate(self, field: str) -> float:
        allowed = {
            name
            for name in IntegratedCalibrationWorldResult.__dataclass_fields__
            if name.endswith("_rate")
        }
        if field not in allowed:
            raise ValidationError("integrated calibration field is invalid")
        return sum(
            getattr(world, field) * world.task_count for world in self.worlds
        ) / self.task_count


@dataclass(frozen=True, slots=True)
class IntegratedCalibrationInterval:
    mean: float
    low: float
    high: float

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (self.mean, self.low, self.high)
        ) or not self.low <= self.mean <= self.high:
            raise ValidationError("integrated calibration interval is invalid")

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


def bootstrap_integrated_calibration_metrics(
    report: IntegratedCalibrationReport,
    *,
    seed: int = INTEGRATED_CALIBRATION_BOOTSTRAP_SEED,
    samples: int = INTEGRATED_CALIBRATION_BOOTSTRAP_SAMPLES,
) -> dict[str, IntegratedCalibrationInterval]:
    if not isinstance(report, IntegratedCalibrationReport):
        raise ValidationError("integrated calibration report is invalid")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
        or isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("integrated calibration bootstrap is invalid")
    value_sets = {
        "candidate_success_rate": tuple(
            world.candidate_success_rate for world in report.worlds
        ),
        "candidate_minus_rotated_success_rate": tuple(
            world.candidate_success_rate - world.rotated_success_rate
            for world in report.worlds
        ),
        "candidate_minus_random_success_rate": tuple(
            world.candidate_success_rate - world.random_success_rate
            for world in report.worlds
        ),
        "candidate_minus_uninterrupted_success_rate": tuple(
            world.candidate_success_rate - world.uninterrupted_success_rate
            for world in report.worlds
        ),
        "restart_action_exact_rate": tuple(
            world.restart_action_exact_rate for world in report.worlds
        ),
    }
    rng = random.Random(seed)
    result: dict[str, IntegratedCalibrationInterval] = {}
    for name, values in value_sets.items():
        means = [
            fmean(rng.choice(values) for _ in values)
            for _ in range(samples)
        ]
        result[name] = IntegratedCalibrationInterval(
            mean=fmean(values),
            low=_quantile(means, 0.025),
            high=_quantile(means, 0.975),
        )
    return result


def integrated_calibration_criteria(
    report: IntegratedCalibrationReport,
    intervals: dict[str, IntegratedCalibrationInterval],
) -> dict[str, bool]:
    required = {
        "candidate_success_rate",
        "candidate_minus_rotated_success_rate",
        "candidate_minus_random_success_rate",
        "candidate_minus_uninterrupted_success_rate",
        "restart_action_exact_rate",
    }
    if set(intervals) != required:
        raise ValidationError("integrated calibration metrics are incomplete")
    integrity_fields = (
        "prediction_match_rate",
        "model_frozen_rate",
        "recovery_executed_rate",
        "checkpoint_exact_rate",
        "kernel_restart_exact_rate",
        "environment_replay_exact_rate",
        "pending_decision_preserved_rate",
        "kernel_cycle_binding_exact_rate",
        "kernel_lineage_rate",
        "action_observation_correlation_rate",
        "no_premature_success_rate",
    )
    mode_success = [
        world.restart_mode_success_rates[index]
        for world in report.worlds
        for index in range(len(INTEGRATED_RESTART_MODES))
    ]
    return {
        "candidate_success_equals_1": (
            report.pooled_rate("candidate_success_rate") == 1.0
        ),
        "candidate_success_interval_low_equals_1": (
            intervals["candidate_success_rate"].low == 1.0
        ),
        "every_restart_mode_success_equals_1": all(
            value == 1.0 for value in mode_success
        ),
        "uninterrupted_success_equals_1": (
            report.pooled_rate("uninterrupted_success_rate") == 1.0
        ),
        "oracle_success_equals_1": (
            report.pooled_rate("oracle_success_rate") == 1.0
        ),
        "rotated_gap_interval_low_at_least_0_95": (
            intervals["candidate_minus_rotated_success_rate"].low >= 0.95
        ),
        "random_gap_interval_low_at_least_0_90": (
            intervals["candidate_minus_random_success_rate"].low >= 0.90
        ),
        "restart_action_exact_equals_1": (
            report.pooled_rate("restart_action_exact_rate") == 1.0
        ),
        "restart_action_interval_low_equals_1": (
            intervals["restart_action_exact_rate"].low == 1.0
        ),
        "candidate_matches_uninterrupted": (
            intervals["candidate_minus_uninterrupted_success_rate"].low
            == intervals["candidate_minus_uninterrupted_success_rate"].high
            == 0.0
        ),
        "all_integrity_rates_equal_1": all(
            report.pooled_rate(field) == 1.0 for field in integrity_fields
        ),
        "mean_candidate_steps_equal_4": (
            fmean(world.mean_candidate_steps for world in report.worlds) == 4.0
        ),
        "restart_modes_balanced_6_each_per_world": all(
            world.restart_mode_counts == (6, 6, 6, 6)
            for world in report.worlds
        ),
        "world_count_equals_64": len(report.worlds) == 64,
        "task_count_equals_1536": report.task_count == 1_536,
        "exploration_budget_equals_486": (
            INTEGRATED_CYCLE_EXPLORATION_BUDGET == 486
        ),
        "target_step_budget_equals_6": (
            PREDICTIVE_MAX_EVALUATION_STEPS == 6
        ),
    }


def run_integrated_calibration(
    *,
    seeds: Iterable[int],
    bootstrap_seed: int = INTEGRATED_CALIBRATION_BOOTSTRAP_SEED,
    bootstrap_samples: int = INTEGRATED_CALIBRATION_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    normalized = _normalize_seeds(seeds)
    report = IntegratedCalibrationReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_integrated_calibration_world(seed)
            for seed in normalized
        ),
    )
    intervals = bootstrap_integrated_calibration_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    criteria = integrated_calibration_criteria(report, intervals)
    success_rates = {
        name: report.pooled_rate(f"{name}_success_rate")
        for name in ("candidate", "uninterrupted", "rotated", "random", "oracle")
    }
    integrity_fields = (
        "restart_action_exact_rate",
        "prediction_match_rate",
        "model_frozen_rate",
        "recovery_executed_rate",
        "checkpoint_exact_rate",
        "kernel_restart_exact_rate",
        "environment_replay_exact_rate",
        "pending_decision_preserved_rate",
        "kernel_cycle_binding_exact_rate",
        "kernel_lineage_rate",
        "action_observation_correlation_rate",
        "no_premature_success_rate",
    )
    eligible = all(criteria.values())
    return {
        "experiment": "035",
        "status": "calibration-only",
        "capability_claim": False,
        "h50_l16_registered": False,
        "eligible_for_h50_l16_preregistration": eligible,
        "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
        "seeds": list(normalized),
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_samples": bootstrap_samples,
        "world_count": len(report.worlds),
        "task_count": report.task_count,
        "tasks_per_world": PREDICTIVE_TASKS_PER_WORLD,
        "restart_modes": list(INTEGRATED_RESTART_MODES),
        "restart_mode_counts_per_world": [6, 6, 6, 6],
        "exploration_interactions_per_world": (
            INTEGRATED_CYCLE_EXPLORATION_BUDGET
        ),
        "maximum_target_steps": PREDICTIVE_MAX_EVALUATION_STEPS,
        "persistence_boundary": (
            "kernel reopened from SQLite, agent restored from causal replay, "
            "and deterministic evaluator environment reconstructed by action "
            "replay; no authenticated external process checkpoint"
        ),
        "success_rates": success_rates,
        "restart_mode_success_rates": {
            mode: fmean(
                world.restart_mode_success_rates[index]
                for world in report.worlds
            )
            for index, mode in enumerate(INTEGRATED_RESTART_MODES)
        },
        "integrity": {
            field: report.pooled_rate(field) for field in integrity_fields
        },
        "mean_candidate_steps": fmean(
            world.mean_candidate_steps for world in report.worlds
        ),
        "metrics": {
            name: interval.to_dict() for name, interval in intervals.items()
        },
        "criteria": criteria,
        "decision": (
            "eligible_for_confirmatory_preregistration"
            if eligible
            else "calibration_failed"
        ),
    }
