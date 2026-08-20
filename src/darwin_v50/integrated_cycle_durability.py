"""Replay-checked recovery bundle for the integrated planning cycle.

The bundle joins a cycle checkpoint, one persisted kernel head, and a recipe
for deterministically reconstructing the predictive environment.  Its digest
is an integrity checksum, not an authentication mechanism or trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .integrated_cycle_lab import IntegratedPlanningCycle
from .kernel import DarwinKernelV50
from .models import (
    CausalEvent,
    Goal,
    GoalStatus,
    ValidationError,
    canonical_json,
    parse_json,
)
from .predictive_planning_evaluation import PredictivePlanningTask
from .predictive_planning_lab import PredictivePlanningWorld


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_event_head(goal: Goal, events: list[CausalEvent]) -> None:
    if not events or events[-1].event_id != goal.last_event_id:
        raise ValidationError("recovery kernel event head disagrees")
    if any(
        event.goal_id != goal.goal_id
        or event.session_id != goal.session_id
        for event in events
    ):
        raise ValidationError("recovery kernel lineage binding disagrees")
    if any(
        event.parent_event_id != previous.event_id
        for previous, event in zip(events, events[1:])
    ):
        raise ValidationError("recovery kernel lineage is not linear")


@dataclass(frozen=True, slots=True)
class IntegratedRecoveryResult:
    cycle: IntegratedPlanningCycle
    world: PredictivePlanningWorld
    goal: Goal
    checkpoint_exact: bool
    environment_replay_exact: bool
    pending_decision_preserved: bool


class IntegratedRecoveryBundle:
    """Capture and restore one quiescent cross-component boundary."""

    SNAPSHOT_SCHEMA = 1

    @classmethod
    def capture(
        cls,
        *,
        cycle: IntegratedPlanningCycle,
        goal: Goal,
        events: list[CausalEvent],
        world_seed: int,
        task: PredictivePlanningTask,
    ) -> str:
        if not isinstance(cycle, IntegratedPlanningCycle):
            raise ValidationError("recovery cycle is invalid")
        if not isinstance(goal, Goal):
            raise ValidationError("recovery goal is invalid")
        if not isinstance(task, PredictivePlanningTask):
            raise ValidationError("recovery task is invalid")
        if (
            isinstance(world_seed, bool)
            or not isinstance(world_seed, int)
            or world_seed < 0
        ):
            raise ValidationError("recovery world seed is invalid")
        _validate_event_head(goal, events)
        observed_waiting_boundary = (
            goal.status is GoalStatus.WAITING_OBSERVATION
            and events[-1].kind == "goal.condition_unsatisfied"
            and events[-1].action_id == goal.expected_action_id
        )
        if (
            goal.status.terminal
            or goal.expected_action_id is not None
            and not observed_waiting_boundary
        ):
            raise ValidationError(
                "recovery capture requires a quiescent kernel boundary"
            )
        if (
            cycle.goal_id != goal.goal_id
            or cycle.session_id != goal.session_id
            or cycle.evidence_source != goal.evidence_source
        ):
            raise ValidationError("recovery cycle and goal binding disagree")
        if (
            cycle.initial_history != task.start
            or cycle.goal_history != task.goal
        ):
            raise ValidationError("recovery cycle and task disagree")
        if len(cycle.action_history) != len(cycle.observed_cues):
            raise ValidationError("recovery trace is unbalanced")
        if not cycle.model_frozen:
            raise ValidationError("recovery cycle model is not frozen")
        core: dict[str, Any] = {
            "schema": cls.SNAPSHOT_SCHEMA,
            "cycle_snapshot": cycle.to_snapshot(),
            "kernel": {
                "goal_id": goal.goal_id,
                "session_id": goal.session_id,
                "evidence_source": goal.evidence_source,
                "version": goal.version,
                "status": goal.status.value,
                "last_event_id": goal.last_event_id,
                "expected_action_id": goal.expected_action_id,
            },
            "environment": {
                "seed": world_seed,
                "start": list(task.start),
                "goal": list(task.goal),
                "max_steps": cycle.max_steps,
                "actions": list(cycle.action_history),
                "observed_cues": list(cycle.observed_cues),
            },
        }
        return canonical_json({**core, "checksum": _digest(core)})

    @classmethod
    def restore(
        cls,
        raw: str,
        *,
        kernel: DarwinKernelV50,
    ) -> IntegratedRecoveryResult:
        if not isinstance(kernel, DarwinKernelV50):
            raise ValidationError("recovery kernel is invalid")
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema",
            "cycle_snapshot",
            "kernel",
            "environment",
            "checksum",
        }:
            raise ValidationError("recovery snapshot shape is invalid")
        if parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported recovery snapshot")
        checksum = parsed.get("checksum")
        core = {key: value for key, value in parsed.items() if key != "checksum"}
        if not isinstance(checksum, str) or checksum != _digest(core):
            raise ValidationError("recovery checksum disagrees")

        kernel_state = parsed.get("kernel")
        environment = parsed.get("environment")
        cycle_snapshot = parsed.get("cycle_snapshot")
        if not isinstance(kernel_state, dict) or set(kernel_state) != {
            "goal_id",
            "session_id",
            "evidence_source",
            "version",
            "status",
            "last_event_id",
            "expected_action_id",
        }:
            raise ValidationError("recovery kernel state is invalid")
        if not isinstance(environment, dict) or set(environment) != {
            "seed",
            "start",
            "goal",
            "max_steps",
            "actions",
            "observed_cues",
        }:
            raise ValidationError("recovery environment state is invalid")
        if not isinstance(cycle_snapshot, str):
            raise ValidationError("recovery cycle snapshot is invalid")
        goal_id = kernel_state.get("goal_id")
        if not isinstance(goal_id, str):
            raise ValidationError("recovery goal id is invalid")
        persisted_goal = kernel.get_goal(goal_id)
        actual_kernel_state = {
            "goal_id": persisted_goal.goal_id,
            "session_id": persisted_goal.session_id,
            "evidence_source": persisted_goal.evidence_source,
            "version": persisted_goal.version,
            "status": persisted_goal.status.value,
            "last_event_id": persisted_goal.last_event_id,
            "expected_action_id": persisted_goal.expected_action_id,
        }
        if actual_kernel_state != kernel_state:
            raise ValidationError("recovery persisted kernel state disagrees")
        events = kernel.goal_events(goal_id)
        _validate_event_head(persisted_goal, events)

        cycle = IntegratedPlanningCycle.from_snapshot(cycle_snapshot)
        if (
            cycle.goal_id != persisted_goal.goal_id
            or cycle.session_id != persisted_goal.session_id
            or cycle.evidence_source != persisted_goal.evidence_source
        ):
            raise ValidationError("recovery restored binding disagrees")
        seed = environment.get("seed")
        start = environment.get("start")
        target = environment.get("goal")
        max_steps = environment.get("max_steps")
        actions = environment.get("actions")
        cues = environment.get("observed_cues")
        if (
            isinstance(seed, bool)
            or not isinstance(seed, int)
            or seed < 0
            or not isinstance(start, list)
            or not isinstance(target, list)
            or isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or max_steps < 1
            or not isinstance(actions, list)
            or not isinstance(cues, list)
            or len(actions) != len(cues)
        ):
            raise ValidationError("recovery environment recipe is invalid")
        if (
            tuple(start) != cycle.initial_history
            or tuple(target) != cycle.goal_history
            or max_steps != cycle.max_steps
            or tuple(actions) != cycle.action_history
            or tuple(cues) != cycle.observed_cues
        ):
            raise ValidationError("recovery environment recipe disagrees")

        pending_before = cycle.pending_decision
        world = PredictivePlanningWorld(seed)
        world.reset(
            start=cycle.initial_history,
            goal=cycle.goal_history,
            max_steps=cycle.max_steps,
        )
        replay_exact = True
        for action, expected_cue in zip(actions, cues, strict=True):
            step = world.step(action)
            replay_exact &= step.observation.cue == expected_cue
        replay_exact &= world.current_history_for_evaluator == cycle.current_history
        if not replay_exact:
            raise ValidationError("recovery environment replay disagrees")
        pending_preserved = cycle.pending_decision == pending_before
        if not pending_preserved:
            raise ValidationError("recovery pending decision changed")
        task = PredictivePlanningTask(
            start=cycle.initial_history,
            goal=cycle.goal_history,
            oracle_actions=PredictivePlanningWorld(seed).specification.shortest_plan(
                cycle.initial_history,
                cycle.goal_history,
            ),
        )
        rebuilt = cls.capture(
            cycle=cycle,
            goal=persisted_goal,
            events=events,
            world_seed=seed,
            task=task,
        )
        if rebuilt != canonical_json(parsed):
            raise ValidationError("recovery snapshot does not restore exactly")
        return IntegratedRecoveryResult(
            cycle=cycle,
            world=world,
            goal=persisted_goal,
            checkpoint_exact=True,
            environment_replay_exact=True,
            pending_decision_preserved=pending_preserved,
        )
