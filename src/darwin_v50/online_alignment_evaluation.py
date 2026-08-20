"""Development benchmark for online latent action-alignment adaptation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import random
from statistics import fmean
import tempfile
from typing import Iterable

from .integrated_cycle_evaluation import _expected_event_kinds
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    GoalStatus,
    ValidationError,
)
from .online_alignment_lab import (
    AlignmentExperience,
    OnlineActionAlignmentTracker,
    OnlineAdaptivePlanningCycle,
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
    PredictiveHistoryPlanner,
    PredictivePlanningWorld,
)


ONLINE_ALIGNMENT_TEST_SEEDS = tuple(range(41900, 41904))
ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS = tuple(range(42000, 42032))
ONLINE_ALIGNMENT_BOOTSTRAP_SEED = 42700
ONLINE_ALIGNMENT_BOOTSTRAP_SAMPLES = 2_000
ONLINE_ALIGNMENT_EXPLORATION_BUDGET = 486
ONLINE_ALIGNMENT_EVIDENCE_SOURCE = "online-alignment:local-evaluator"
ONLINE_ALIGNMENT_SEGMENTS = (
    "base",
    "shifted",
    "recurrent",
    "novel",
)
ONLINE_ALIGNMENT_ROTATIONS = (0, 1, 0, 2)
ONLINE_ALIGNMENT_TASKS_PER_SEGMENT = 6


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
            "online-alignment seeds must be unique increasing integers"
        )
    return result


def _task_rotation(task_index: int) -> int:
    if (
        isinstance(task_index, bool)
        or not isinstance(task_index, int)
        or not 0 <= task_index < PREDICTIVE_TASKS_PER_WORLD
    ):
        raise ValidationError("online-alignment task index is invalid")
    return ONLINE_ALIGNMENT_ROTATIONS[
        task_index // ONLINE_ALIGNMENT_TASKS_PER_SEGMENT
    ]


def _mapped_action(action: str, rotation: int) -> str:
    if action not in PLANNING_ACTIONS or rotation not in (0, 1, 2):
        raise ValidationError("online-alignment action mapping is invalid")
    return PLANNING_ACTIONS[
        (PLANNING_ACTIONS.index(action) + rotation) % len(PLANNING_ACTIONS)
    ]


@dataclass(frozen=True, slots=True)
class OnlinePolicyScheduleResult:
    successes: tuple[bool, ...]
    steps: tuple[int, ...]
    actions: tuple[tuple[str, ...], ...]
    final_rotation: int
    archive_count: int
    prior_frozen: bool

    def __post_init__(self) -> None:
        if not (
            len(self.successes)
            == len(self.steps)
            == len(self.actions)
            == PREDICTIVE_TASKS_PER_WORLD
        ):
            raise ValidationError("online policy schedule is unbalanced")
        if any(
            isinstance(step, bool)
            or not isinstance(step, int)
            or not 1 <= step <= PREDICTIVE_MAX_EVALUATION_STEPS
            or step != len(actions)
            for step, actions in zip(self.steps, self.actions, strict=True)
        ):
            raise ValidationError("online policy schedule step is invalid")
        if self.final_rotation not in (0, 1, 2):
            raise ValidationError("online policy final rotation is invalid")
        if (
            isinstance(self.archive_count, bool)
            or not isinstance(self.archive_count, int)
            or self.archive_count != sum(self.steps)
            or not isinstance(self.prior_frozen, bool)
        ):
            raise ValidationError("online policy archive is invalid")

    @property
    def success_rate(self) -> float:
        return fmean(float(value) for value in self.successes)

    @property
    def mean_steps(self) -> float:
        return fmean(self.steps)

    def segment_success_rate(self, segment_index: int) -> float:
        start = segment_index * ONLINE_ALIGNMENT_TASKS_PER_SEGMENT
        end = start + ONLINE_ALIGNMENT_TASKS_PER_SEGMENT
        return fmean(float(value) for value in self.successes[start:end])


def _run_tracker_schedule(
    *,
    seed: int,
    tasks: tuple[PredictivePlanningTask, ...],
    model_snapshot: str,
    policy: str,
    evidence_shift: int = 0,
) -> OnlinePolicyScheduleResult:
    model = PredictiveHistoryModel.from_snapshot(model_snapshot)
    tracker = OnlineActionAlignmentTracker(
        prior_model=model,
        policy=policy,
        evidence_shift=evidence_shift,
    )
    successes: list[bool] = []
    step_counts: list[int] = []
    action_rows: list[tuple[str, ...]] = []
    for task_index, task in enumerate(tasks):
        rotation = _task_rotation(task_index)
        world = PredictivePlanningWorld(seed)
        world.reset(
            start=task.start,
            goal=task.goal,
            max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
        )
        history = task.start
        actions: list[str] = []
        for step_index in range(PREDICTIVE_MAX_EVALUATION_STEPS):
            plan = PredictiveHistoryPlanner(
                model,
                max_depth=PREDICTIVE_MAX_EVALUATION_STEPS,
                action_rotation=tracker.current_rotation,
            ).plan(history, task.goal)
            if not plan.found or not plan.actions:
                raise ValidationError("online control has no aligned plan")
            action = plan.actions[0]
            step = world.step(_mapped_action(action, rotation))
            tracker.observe(
                AlignmentExperience(
                    sequence=len(tracker.archive) + 1,
                    episode_index=task_index + 1,
                    step_index=step_index,
                    history=history,
                    action=action,
                    next_cue=step.observation.cue,
                )
            )
            actions.append(action)
            history = world.current_history_for_evaluator
            if history == task.goal:
                break
        successes.append(history == task.goal)
        step_counts.append(len(actions))
        action_rows.append(tuple(actions))
    return OnlinePolicyScheduleResult(
        successes=tuple(successes),
        steps=tuple(step_counts),
        actions=tuple(action_rows),
        final_rotation=tracker.current_rotation,
        archive_count=len(tracker.archive),
        prior_frozen=tracker.prior_frozen,
    )


def _run_oracle_schedule(
    *,
    seed: int,
    tasks: tuple[PredictivePlanningTask, ...],
    model_snapshot: str,
) -> OnlinePolicyScheduleResult:
    model = PredictiveHistoryModel.from_snapshot(model_snapshot)
    successes: list[bool] = []
    step_counts: list[int] = []
    action_rows: list[tuple[str, ...]] = []
    for task_index, task in enumerate(tasks):
        rotation = _task_rotation(task_index)
        world = PredictivePlanningWorld(seed)
        world.reset(
            start=task.start,
            goal=task.goal,
            max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
        )
        history = task.start
        actions: list[str] = []
        for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
            plan = PredictiveHistoryPlanner(
                model,
                max_depth=PREDICTIVE_MAX_EVALUATION_STEPS,
                action_rotation=rotation,
            ).plan(history, task.goal)
            if not plan.found or not plan.actions:
                raise ValidationError("online oracle has no plan")
            action = plan.actions[0]
            step = world.step(_mapped_action(action, rotation))
            actions.append(action)
            history = world.current_history_for_evaluator
            if history == task.goal:
                break
        successes.append(history == task.goal)
        step_counts.append(len(actions))
        action_rows.append(tuple(actions))
    return OnlinePolicyScheduleResult(
        successes=tuple(successes),
        steps=tuple(step_counts),
        actions=tuple(action_rows),
        final_rotation=ONLINE_ALIGNMENT_ROTATIONS[-1],
        archive_count=sum(step_counts),
        prior_frozen=model.to_snapshot() == model_snapshot,
    )


def _run_random_schedule(
    *,
    seed: int,
    tasks: tuple[PredictivePlanningTask, ...],
    model_snapshot: str,
) -> OnlinePolicyScheduleResult:
    rng = random.Random(seed ^ 0x17A11)
    successes: list[bool] = []
    step_counts: list[int] = []
    action_rows: list[tuple[str, ...]] = []
    for task_index, task in enumerate(tasks):
        rotation = _task_rotation(task_index)
        world = PredictivePlanningWorld(seed)
        world.reset(
            start=task.start,
            goal=task.goal,
            max_steps=PREDICTIVE_MAX_EVALUATION_STEPS,
        )
        actions: list[str] = []
        for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
            action = rng.choice(PLANNING_ACTIONS)
            world.step(_mapped_action(action, rotation))
            actions.append(action)
            if world.current_history_for_evaluator == task.goal:
                break
        successes.append(world.current_history_for_evaluator == task.goal)
        step_counts.append(len(actions))
        action_rows.append(tuple(actions))
    model = PredictiveHistoryModel.from_snapshot(model_snapshot)
    return OnlinePolicyScheduleResult(
        successes=tuple(successes),
        steps=tuple(step_counts),
        actions=tuple(action_rows),
        final_rotation=0,
        archive_count=sum(step_counts),
        prior_frozen=model.to_snapshot() == model_snapshot,
    )


@dataclass(frozen=True, slots=True)
class IntegratedOnlineScheduleResult:
    policy: OnlinePolicyScheduleResult
    boundary_adaptation_delays: tuple[int, ...]
    alignment_identification_rate: float
    post_observation_alignment_rate: float
    tracker_snapshot_rate: float
    kernel_lineage_rate: float
    action_observation_correlation_rate: float
    no_premature_success_rate: float
    archive_retention_rate: float
    prior_frozen_rate: float

    def __post_init__(self) -> None:
        if (
            len(self.boundary_adaptation_delays) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                for value in self.boundary_adaptation_delays
            )
        ):
            raise ValidationError("online adaptation delay is invalid")
        for value in (
            self.alignment_identification_rate,
            self.post_observation_alignment_rate,
            self.tracker_snapshot_rate,
            self.kernel_lineage_rate,
            self.action_observation_correlation_rate,
            self.no_premature_success_rate,
            self.archive_retention_rate,
            self.prior_frozen_rate,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError("online integrity rate is invalid")


def _run_integrated_candidate(
    *,
    seed: int,
    tasks: tuple[PredictivePlanningTask, ...],
    model_snapshot: str,
) -> IntegratedOnlineScheduleResult:
    model = PredictiveHistoryModel.from_snapshot(model_snapshot)
    tracker = OnlineActionAlignmentTracker(prior_model=model)
    successes: list[bool] = []
    step_counts: list[int] = []
    action_rows: list[tuple[str, ...]] = []
    identification: list[bool] = []
    post_alignment: list[bool] = []
    snapshot_exact: list[bool] = []
    lineage_valid: list[bool] = []
    correlation_valid: list[bool] = []
    no_premature_rows: list[bool] = []
    prior_frozen_rows: list[bool] = []
    boundary_delays: list[int] = []
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "online-alignment.db"
        with DarwinKernelV50.open(database) as kernel:
            for task_index, task in enumerate(tasks):
                rotation = _task_rotation(task_index)
                goal = kernel.create_goal(
                    session_id=f"online-alignment:{seed}:{task_index + 1}",
                    description="Reach the supplied history under hidden alignment",
                    evidence_source=ONLINE_ALIGNMENT_EVIDENCE_SOURCE,
                    condition=ComparisonCondition(
                        "goal_reached",
                        ComparisonOperator.EQUAL,
                        1,
                    ),
                )
                goal = kernel.start_goal(goal.goal_id)
                cycle = OnlineAdaptivePlanningCycle(
                    prior_model=model,
                    tracker=tracker,
                    session_id=goal.session_id,
                    goal_id=goal.goal_id,
                    evidence_source=goal.evidence_source,
                    episode_index=task_index + 1,
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
                decisions: list[str] = []
                task_updates = []
                observations_accepted = True
                boundary_delay: int | None = None
                for _ in range(PREDICTIVE_MAX_EVALUATION_STEPS):
                    decision_rotation = tracker.current_rotation
                    decision = cycle.choose_action()
                    decisions.append(decision.action)
                    goal = kernel.dispatch_action(
                        goal.goal_id,
                        action_name="online-aligned-history-step",
                        parameters={
                            "action": decision.action,
                            "step_index": decision.step_index,
                            "alignment_at_decision": decision_rotation,
                        },
                    )
                    step = world.step(
                        _mapped_action(decision.action, rotation)
                    )
                    observed = cycle.observe(
                        action=decision.action,
                        next_cue=step.observation.cue,
                    )
                    task_updates.append(observed.alignment_update)
                    identification.append(
                        observed.alignment_update.compatible_rotation
                        == rotation
                    )
                    post_alignment.append(
                        observed.alignment_update.rotation_after == rotation
                    )
                    if (
                        boundary_delay is None
                        and observed.alignment_update.rotation_after == rotation
                    ):
                        boundary_delay = observed.step_index + 1
                    recorded = kernel.record_observation(
                        goal.goal_id,
                        action_id=goal.expected_action_id or "",
                        source=ONLINE_ALIGNMENT_EVIDENCE_SOURCE,
                        metrics={
                            "goal_reached": int(observed.goal_reached),
                            "observed_cue": observed.observed_cue,
                            "compatible_rotation": (
                                observed.alignment_update.compatible_rotation
                            ),
                            "rotation_after": (
                                observed.alignment_update.rotation_after
                            ),
                        },
                    )
                    observations_accepted &= recorded.accepted
                    goal = recorded.goal
                    if observed.goal_reached:
                        break
                    if cycle.step_index >= PREDICTIVE_MAX_EVALUATION_STEPS:
                        break
                    goal = kernel.continue_goal(goal.goal_id)
                if task_index in (6, 12, 18):
                    if boundary_delay is None:
                        raise ValidationError(
                            "online candidate did not adapt at a boundary"
                        )
                    boundary_delays.append(boundary_delay)
                events = kernel.goal_events(goal.goal_id)
                kinds = tuple(event.kind for event in events)
                linear = all(
                    event.parent_event_id == previous.event_id
                    for previous, event in zip(events, events[1:])
                )
                dispatches = tuple(
                    event
                    for event in events
                    if event.kind == "action.dispatched"
                )
                observations = tuple(
                    event
                    for event in events
                    if event.kind == "observation.recorded"
                )
                correlation_valid.append(
                    observations_accepted
                    and len(dispatches)
                    == len(observations)
                    == len(decisions)
                    and all(
                        dispatch.action_id == observation.action_id
                        and dispatch.payload.get("parameters", {}).get(
                            "action"
                        )
                        == action
                        for dispatch, observation, action in zip(
                            dispatches,
                            observations,
                            decisions,
                            strict=True,
                        )
                    )
                )
                success = goal.status is GoalStatus.SUCCEEDED
                lineage_valid.append(
                    linear
                    and kinds
                    == _expected_event_kinds(
                        steps=cycle.step_index,
                        success=success,
                    )
                )
                success_events = tuple(
                    event for event in events if event.kind == "goal.succeeded"
                )
                no_premature_rows.append(
                    len(success_events) == int(success)
                    and (
                        not success
                        or observations[-1].payload.get("metrics", {}).get(
                            "goal_reached"
                        )
                        == 1
                    )
                )
                successes.append(success)
                step_counts.append(cycle.step_index)
                action_rows.append(cycle.action_history)
                prior_frozen_rows.append(cycle.prior_frozen)
                tracker = cycle.tracker
                if (task_index + 1) % ONLINE_ALIGNMENT_TASKS_PER_SEGMENT == 0:
                    snapshot = tracker.to_snapshot()
                    restored = OnlineActionAlignmentTracker.from_snapshot(
                        snapshot,
                        prior_model=model,
                    )
                    snapshot_exact.append(restored.to_snapshot() == snapshot)
                    tracker = restored
    policy = OnlinePolicyScheduleResult(
        successes=tuple(successes),
        steps=tuple(step_counts),
        actions=tuple(action_rows),
        final_rotation=tracker.current_rotation,
        archive_count=len(tracker.archive),
        prior_frozen=tracker.prior_frozen,
    )
    total_actions = sum(step_counts)
    return IntegratedOnlineScheduleResult(
        policy=policy,
        boundary_adaptation_delays=tuple(boundary_delays),
        alignment_identification_rate=fmean(
            float(value) for value in identification
        ),
        post_observation_alignment_rate=fmean(
            float(value) for value in post_alignment
        ),
        tracker_snapshot_rate=fmean(float(value) for value in snapshot_exact),
        kernel_lineage_rate=fmean(float(value) for value in lineage_valid),
        action_observation_correlation_rate=fmean(
            float(value) for value in correlation_valid
        ),
        no_premature_success_rate=fmean(
            float(value) for value in no_premature_rows
        ),
        archive_retention_rate=len(tracker.archive) / total_actions,
        prior_frozen_rate=fmean(float(value) for value in prior_frozen_rows),
    )


@dataclass(frozen=True, slots=True)
class OnlineAlignmentWorldResult:
    seed: int
    task_count: int
    candidate_success_rate: float
    frozen_success_rate: float
    cumulative_success_rate: float
    shuffled_success_rate: float
    random_success_rate: float
    oracle_success_rate: float
    candidate_segment_success_rates: tuple[float, ...]
    frozen_segment_success_rates: tuple[float, ...]
    candidate_mean_steps: float
    oracle_mean_steps: float
    boundary_adaptation_delay: float
    integration_parity_rate: float
    alignment_identification_rate: float
    post_observation_alignment_rate: float
    tracker_snapshot_rate: float
    kernel_lineage_rate: float
    action_observation_correlation_rate: float
    no_premature_success_rate: float
    archive_retention_rate: float
    prior_frozen_rate: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or self.seed < 0
            or self.task_count != PREDICTIVE_TASKS_PER_WORLD
            or len(self.candidate_segment_success_rates)
            != len(ONLINE_ALIGNMENT_SEGMENTS)
            or len(self.frozen_segment_success_rates)
            != len(ONLINE_ALIGNMENT_SEGMENTS)
        ):
            raise ValidationError("online-alignment world is invalid")
        rates = (
            self.candidate_segment_success_rates
            + self.frozen_segment_success_rates
            + (
                self.candidate_success_rate,
                self.frozen_success_rate,
                self.cumulative_success_rate,
                self.shuffled_success_rate,
                self.random_success_rate,
                self.oracle_success_rate,
                self.integration_parity_rate,
                self.alignment_identification_rate,
                self.post_observation_alignment_rate,
                self.tracker_snapshot_rate,
                self.kernel_lineage_rate,
                self.action_observation_correlation_rate,
                self.no_premature_success_rate,
                self.archive_retention_rate,
                self.prior_frozen_rate,
            )
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in rates
        ):
            raise ValidationError("online-alignment rate is invalid")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0.0
            for value in (
                self.candidate_mean_steps,
                self.oracle_mean_steps,
                self.boundary_adaptation_delay,
            )
        ):
            raise ValidationError("online-alignment cost is invalid")


def evaluate_online_alignment_world(seed: int) -> OnlineAlignmentWorldResult:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError("online-alignment world seed is invalid")
    explorer, exploration_world = run_predictive_exploration(
        seed,
        budget=ONLINE_ALIGNMENT_EXPLORATION_BUDGET,
    )
    model_snapshot = explorer.model.to_snapshot()
    tasks = make_predictive_tasks(
        exploration_world.specification,
        count=PREDICTIVE_TASKS_PER_WORLD,
    )
    candidate = _run_integrated_candidate(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
    )
    pure_candidate = _run_tracker_schedule(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
        policy="latest",
    )
    frozen = _run_tracker_schedule(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
        policy="frozen",
    )
    cumulative = _run_tracker_schedule(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
        policy="cumulative",
    )
    shuffled = _run_tracker_schedule(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
        policy="latest",
        evidence_shift=1,
    )
    oracle = _run_oracle_schedule(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
    )
    random_result = _run_random_schedule(
        seed=seed,
        tasks=tasks,
        model_snapshot=model_snapshot,
    )
    return OnlineAlignmentWorldResult(
        seed=seed,
        task_count=len(tasks),
        candidate_success_rate=candidate.policy.success_rate,
        frozen_success_rate=frozen.success_rate,
        cumulative_success_rate=cumulative.success_rate,
        shuffled_success_rate=shuffled.success_rate,
        random_success_rate=random_result.success_rate,
        oracle_success_rate=oracle.success_rate,
        candidate_segment_success_rates=tuple(
            candidate.policy.segment_success_rate(index)
            for index in range(len(ONLINE_ALIGNMENT_SEGMENTS))
        ),
        frozen_segment_success_rates=tuple(
            frozen.segment_success_rate(index)
            for index in range(len(ONLINE_ALIGNMENT_SEGMENTS))
        ),
        candidate_mean_steps=candidate.policy.mean_steps,
        oracle_mean_steps=oracle.mean_steps,
        boundary_adaptation_delay=fmean(
            candidate.boundary_adaptation_delays
        ),
        integration_parity_rate=fmean(
            float(
                left_success == right_success
                and left_actions == right_actions
            )
            for left_success, right_success, left_actions, right_actions in zip(
                candidate.policy.successes,
                pure_candidate.successes,
                candidate.policy.actions,
                pure_candidate.actions,
                strict=True,
            )
        ),
        alignment_identification_rate=(
            candidate.alignment_identification_rate
        ),
        post_observation_alignment_rate=(
            candidate.post_observation_alignment_rate
        ),
        tracker_snapshot_rate=candidate.tracker_snapshot_rate,
        kernel_lineage_rate=candidate.kernel_lineage_rate,
        action_observation_correlation_rate=(
            candidate.action_observation_correlation_rate
        ),
        no_premature_success_rate=candidate.no_premature_success_rate,
        archive_retention_rate=candidate.archive_retention_rate,
        prior_frozen_rate=candidate.prior_frozen_rate,
    )


@dataclass(frozen=True, slots=True)
class OnlineAlignmentDevelopmentReport:
    seeds: tuple[int, ...]
    worlds: tuple[OnlineAlignmentWorldResult, ...]

    def __post_init__(self) -> None:
        if _normalize_seeds(self.seeds) != self.seeds:
            raise ValidationError("online development seeds are not canonical")
        if tuple(world.seed for world in self.worlds) != self.seeds:
            raise ValidationError("online development worlds are unbalanced")

    @property
    def task_count(self) -> int:
        return sum(world.task_count for world in self.worlds)

    def pooled_rate(self, field: str) -> float:
        if field not in {
            name
            for name in OnlineAlignmentWorldResult.__dataclass_fields__
            if name.endswith("_rate")
        }:
            raise ValidationError("online development rate field is invalid")
        return sum(
            getattr(world, field) * world.task_count for world in self.worlds
        ) / self.task_count

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "experiment": "037",
            "status": "development-only",
            "capability_claim": False,
            "h50_l17_registered": False,
            "evidence_level": "E1_LOCAL_UNAUTHENTICATED_EVALUATOR",
            "seeds": list(self.seeds),
            "world_count": len(self.worlds),
            "task_count": self.task_count,
            "segments": list(ONLINE_ALIGNMENT_SEGMENTS),
            "hidden_rotations": list(ONLINE_ALIGNMENT_ROTATIONS),
            "tasks_per_segment": ONLINE_ALIGNMENT_TASKS_PER_SEGMENT,
            "exploration_interactions_per_world": (
                ONLINE_ALIGNMENT_EXPLORATION_BUDGET
            ),
            "maximum_target_steps": PREDICTIVE_MAX_EVALUATION_STEPS,
            "success_rates": {
                policy: self.pooled_rate(f"{policy}_success_rate")
                for policy in (
                    "candidate",
                    "frozen",
                    "cumulative",
                    "shuffled",
                    "random",
                    "oracle",
                )
            },
            "candidate_segment_success_rates": {
                segment: fmean(
                    world.candidate_segment_success_rates[index]
                    for world in self.worlds
                )
                for index, segment in enumerate(ONLINE_ALIGNMENT_SEGMENTS)
            },
            "frozen_segment_success_rates": {
                segment: fmean(
                    world.frozen_segment_success_rates[index]
                    for world in self.worlds
                )
                for index, segment in enumerate(ONLINE_ALIGNMENT_SEGMENTS)
            },
            "mean_candidate_steps": fmean(
                world.candidate_mean_steps for world in self.worlds
            ),
            "mean_oracle_steps": fmean(
                world.oracle_mean_steps for world in self.worlds
            ),
            "mean_boundary_adaptation_delay": fmean(
                world.boundary_adaptation_delay for world in self.worlds
            ),
            "integrity": {
                field: self.pooled_rate(field)
                for field in (
                    "integration_parity_rate",
                    "alignment_identification_rate",
                    "post_observation_alignment_rate",
                    "tracker_snapshot_rate",
                    "kernel_lineage_rate",
                    "action_observation_correlation_rate",
                    "no_premature_success_rate",
                    "archive_retention_rate",
                    "prior_frozen_rate",
                )
            },
            "interpretation_boundary": (
                "online inference over a registered three-value action "
                "alignment; the transition prior remains frozen"
            ),
        }


def run_online_alignment_development(
    *,
    seeds: Iterable[int],
) -> OnlineAlignmentDevelopmentReport:
    normalized = _normalize_seeds(seeds)
    return OnlineAlignmentDevelopmentReport(
        seeds=normalized,
        worlds=tuple(
            evaluate_online_alignment_world(seed) for seed in normalized
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


def bootstrap_online_alignment_metrics(
    report: OnlineAlignmentDevelopmentReport,
    *,
    seed: int = ONLINE_ALIGNMENT_BOOTSTRAP_SEED,
    samples: int = ONLINE_ALIGNMENT_BOOTSTRAP_SAMPLES,
) -> dict[str, dict[str, float]]:
    if not isinstance(report, OnlineAlignmentDevelopmentReport):
        raise ValidationError("online development report is invalid")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
        or isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 1
    ):
        raise ValidationError("online development bootstrap is invalid")
    value_sets = {
        "candidate_success_rate": tuple(
            world.candidate_success_rate for world in report.worlds
        ),
        "candidate_minus_frozen_success_rate": tuple(
            world.candidate_success_rate - world.frozen_success_rate
            for world in report.worlds
        ),
        "candidate_minus_cumulative_success_rate": tuple(
            world.candidate_success_rate - world.cumulative_success_rate
            for world in report.worlds
        ),
        "candidate_minus_shuffled_success_rate": tuple(
            world.candidate_success_rate - world.shuffled_success_rate
            for world in report.worlds
        ),
        "candidate_minus_oracle_success_rate": tuple(
            world.candidate_success_rate - world.oracle_success_rate
            for world in report.worlds
        ),
        "recurrent_candidate_minus_frozen_success_rate": tuple(
            world.candidate_segment_success_rates[2]
            - world.frozen_segment_success_rates[2]
            for world in report.worlds
        ),
        "boundary_adaptation_delay": tuple(
            world.boundary_adaptation_delay for world in report.worlds
        ),
    }
    rng = random.Random(seed)
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


def online_alignment_development_record(
    report: OnlineAlignmentDevelopmentReport,
    *,
    bootstrap_seed: int = ONLINE_ALIGNMENT_BOOTSTRAP_SEED,
    bootstrap_samples: int = ONLINE_ALIGNMENT_BOOTSTRAP_SAMPLES,
) -> dict[str, object]:
    result = report.to_summary_dict()
    result["bootstrap_seed"] = bootstrap_seed
    result["bootstrap_samples"] = bootstrap_samples
    result["development_intervals"] = bootstrap_online_alignment_metrics(
        report,
        seed=bootstrap_seed,
        samples=bootstrap_samples,
    )
    return result
