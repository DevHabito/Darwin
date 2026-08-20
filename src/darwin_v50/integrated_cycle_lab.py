"""Minimum persistent planning cycle for Darwin integration development.

The cycle binds one externally supplied kernel goal to the frozen H50-L10
history model.  It replans before every action and rebuilds checkpoints by
replaying its own action-observation history.  It is not an autonomous agent,
an online learner, or a general cognitive architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .models import ValidationError, canonical_json, parse_json, require_text
from .predictive_planning_lab import (
    PLANNING_ACTIONS,
    HistoryState,
    PredictiveHistoryModel,
    PredictiveHistoryPlanner,
    next_history,
    validate_history,
)


@dataclass(frozen=True, slots=True)
class IntegratedCycleDecision:
    step_index: int
    current_history: HistoryState
    goal_history: HistoryState
    action: str
    planned_actions: tuple[str, ...]
    predicted_histories: tuple[HistoryState, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValidationError("integrated decision step is invalid")
        validate_history(self.current_history, "decision current history")
        validate_history(self.goal_history, "decision goal history")
        if self.action not in PLANNING_ACTIONS:
            raise ValidationError("integrated decision action is invalid")
        if not self.planned_actions or self.planned_actions[0] != self.action:
            raise ValidationError("integrated decision plan is invalid")
        if any(action not in PLANNING_ACTIONS for action in self.planned_actions):
            raise ValidationError("integrated decision plan action is invalid")
        if (
            not self.predicted_histories
            or self.predicted_histories[0] != self.current_history
            or len(self.predicted_histories) != len(self.planned_actions) + 1
            or self.predicted_histories[-1] != self.goal_history
        ):
            raise ValidationError("integrated predicted path is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "current_history": list(self.current_history),
            "goal_history": list(self.goal_history),
            "action": self.action,
            "planned_actions": list(self.planned_actions),
            "predicted_histories": [
                list(history) for history in self.predicted_histories
            ],
        }


@dataclass(frozen=True, slots=True)
class IntegratedCycleObservation:
    step_index: int
    action: str
    observed_cue: int
    predicted_history: HistoryState
    observed_history: HistoryState
    prediction_matched: bool
    goal_reached: bool


class IntegratedPlanningCycle:
    """Replanning observable-history controller with causal checkpoint replay."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        model: PredictiveHistoryModel,
        session_id: str,
        goal_id: str,
        evidence_source: str,
        initial_history: HistoryState,
        goal_history: HistoryState,
        max_steps: int,
        action_rotation: int = 0,
    ) -> None:
        if not isinstance(model, PredictiveHistoryModel):
            raise ValidationError("integrated cycle model is invalid")
        self.session_id = require_text(session_id, "session_id")
        self.goal_id = require_text(goal_id, "goal_id")
        self.evidence_source = require_text(
            evidence_source,
            "evidence_source",
        )
        self.initial_history = validate_history(
            initial_history,
            "initial_history",
        )
        self.goal_history = validate_history(goal_history, "goal_history")
        if self.initial_history == self.goal_history:
            raise ValidationError("integrated cycle goal must differ from start")
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or max_steps < 1
        ):
            raise ValidationError("integrated cycle max_steps is invalid")
        self.max_steps = max_steps
        self.action_rotation = action_rotation
        self.model = model
        self._model_snapshot = model.to_snapshot()
        self._model_digest = hashlib.sha256(
            self._model_snapshot.encode("utf-8")
        ).hexdigest()
        self._planner = PredictiveHistoryPlanner(
            self.model,
            max_depth=max_steps,
            action_rotation=action_rotation,
        )
        self._current_history = self.initial_history
        self._actions: list[str] = []
        self._observed_cues: list[int] = []
        self._prediction_matches: list[bool] = []
        self._pending: IntegratedCycleDecision | None = None

    @property
    def current_history(self) -> HistoryState:
        return self._current_history

    @property
    def action_history(self) -> tuple[str, ...]:
        return tuple(self._actions)

    @property
    def observed_cues(self) -> tuple[int, ...]:
        return tuple(self._observed_cues)

    @property
    def prediction_matches(self) -> tuple[bool, ...]:
        return tuple(self._prediction_matches)

    @property
    def pending_decision(self) -> IntegratedCycleDecision | None:
        return self._pending

    @property
    def step_index(self) -> int:
        return len(self._actions)

    @property
    def goal_reached(self) -> bool:
        return self.current_history == self.goal_history

    @property
    def model_frozen(self) -> bool:
        return self.model.to_snapshot() == self._model_snapshot

    @property
    def model_digest(self) -> str:
        return self._model_digest

    def choose_action(self) -> IntegratedCycleDecision:
        if self._pending is not None:
            return self._pending
        if self.goal_reached:
            raise ValidationError("integrated cycle goal is already reached")
        if self.step_index >= self.max_steps:
            raise ValidationError("integrated cycle step budget is exhausted")
        if not self.model_frozen:
            raise ValidationError("integrated cycle model changed during control")
        plan = self._planner.plan(self.current_history, self.goal_history)
        if not plan.found or not plan.actions:
            raise ValidationError("integrated cycle has no learned plan")
        self._pending = IntegratedCycleDecision(
            step_index=self.step_index,
            current_history=self.current_history,
            goal_history=self.goal_history,
            action=plan.actions[0],
            planned_actions=plan.actions,
            predicted_histories=plan.predicted_histories,
        )
        return self._pending

    def observe(
        self,
        *,
        action: str,
        next_cue: int,
    ) -> IntegratedCycleObservation:
        if self._pending is None:
            raise ValidationError("integrated observation has no decision")
        if action != self._pending.action:
            raise ValidationError("integrated observation action mismatch")
        observed_history = next_history(self.current_history, next_cue)
        predicted_history = self._pending.predicted_histories[1]
        matched = predicted_history == observed_history
        step_index = self.step_index
        self._actions.append(action)
        self._observed_cues.append(next_cue)
        self._prediction_matches.append(matched)
        self._current_history = observed_history
        self._pending = None
        if not self.model_frozen:
            raise ValidationError("integrated cycle model changed during control")
        return IntegratedCycleObservation(
            step_index=step_index,
            action=action,
            observed_cue=next_cue,
            predicted_history=predicted_history,
            observed_history=observed_history,
            prediction_matched=matched,
            goal_reached=self.goal_reached,
        )

    def _snapshot_dict(self) -> dict[str, Any]:
        return {
            "schema": self.SNAPSHOT_SCHEMA,
            "binding": {
                "session_id": self.session_id,
                "goal_id": self.goal_id,
                "evidence_source": self.evidence_source,
            },
            "configuration": {
                "initial_history": list(self.initial_history),
                "goal_history": list(self.goal_history),
                "max_steps": self.max_steps,
                "action_rotation": self.action_rotation,
                "model_snapshot": self._model_snapshot,
                "model_digest": self.model_digest,
            },
            "history": {
                "actions": list(self.action_history),
                "observed_cues": list(self.observed_cues),
                "prediction_matches": list(self.prediction_matches),
            },
            "pending_decision": (
                self.pending_decision.to_dict()
                if self.pending_decision is not None
                else None
            ),
            "derived": {
                "current_history": list(self.current_history),
                "step_index": self.step_index,
                "goal_reached": self.goal_reached,
                "model_frozen": self.model_frozen,
            },
        }

    def to_snapshot(self) -> str:
        return canonical_json(self._snapshot_dict())

    @staticmethod
    def _history_from_list(raw: object, field: str) -> HistoryState:
        if not isinstance(raw, list):
            raise ValidationError(f"{field} must be a list")
        return validate_history(tuple(raw), field)  # type: ignore[arg-type]

    @classmethod
    def from_snapshot(cls, raw: str) -> "IntegratedPlanningCycle":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema",
            "binding",
            "configuration",
            "history",
            "pending_decision",
            "derived",
        } or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported integrated-cycle snapshot")
        binding = parsed.get("binding")
        configuration = parsed.get("configuration")
        history = parsed.get("history")
        if not isinstance(binding, dict) or set(binding) != {
            "session_id",
            "goal_id",
            "evidence_source",
        }:
            raise ValidationError("integrated snapshot binding is invalid")
        if not isinstance(configuration, dict) or set(configuration) != {
            "initial_history",
            "goal_history",
            "max_steps",
            "action_rotation",
            "model_snapshot",
            "model_digest",
        }:
            raise ValidationError(
                "integrated snapshot configuration is invalid"
            )
        if not isinstance(history, dict) or set(history) != {
            "actions",
            "observed_cues",
            "prediction_matches",
        }:
            raise ValidationError("integrated snapshot history is invalid")
        model_snapshot = configuration.get("model_snapshot")
        if not isinstance(model_snapshot, str):
            raise ValidationError("integrated model snapshot is invalid")
        digest = hashlib.sha256(model_snapshot.encode("utf-8")).hexdigest()
        if configuration.get("model_digest") != digest:
            raise ValidationError("integrated model digest disagrees")
        model = PredictiveHistoryModel.from_snapshot(model_snapshot)
        cycle = cls(
            model=model,
            session_id=binding.get("session_id"),  # type: ignore[arg-type]
            goal_id=binding.get("goal_id"),  # type: ignore[arg-type]
            evidence_source=binding.get(  # type: ignore[arg-type]
                "evidence_source"
            ),
            initial_history=cls._history_from_list(
                configuration.get("initial_history"),
                "snapshot initial history",
            ),
            goal_history=cls._history_from_list(
                configuration.get("goal_history"),
                "snapshot goal history",
            ),
            max_steps=configuration.get("max_steps"),  # type: ignore[arg-type]
            action_rotation=configuration.get(  # type: ignore[arg-type]
                "action_rotation"
            ),
        )
        actions = history.get("actions")
        cues = history.get("observed_cues")
        matches = history.get("prediction_matches")
        if (
            not isinstance(actions, list)
            or not isinstance(cues, list)
            or not isinstance(matches, list)
            or not len(actions) == len(cues) == len(matches)
            or any(not isinstance(value, bool) for value in matches)
        ):
            raise ValidationError("integrated snapshot trace is invalid")
        for action, cue, expected_match in zip(
            actions,
            cues,
            matches,
            strict=True,
        ):
            decision = cycle.choose_action()
            if decision.action != action:
                raise ValidationError(
                    "integrated snapshot action is not policy-causal"
                )
            observation = cycle.observe(action=action, next_cue=cue)
            if observation.prediction_matched != expected_match:
                raise ValidationError(
                    "integrated snapshot prediction trace disagrees"
                )
        pending = parsed.get("pending_decision")
        if pending is not None:
            if not isinstance(pending, dict):
                raise ValidationError("integrated pending decision is invalid")
            if cycle.choose_action().to_dict() != pending:
                raise ValidationError(
                    "integrated pending decision does not replay"
                )
        if canonical_json(parsed) != cycle.to_snapshot():
            raise ValidationError(
                "integrated snapshot does not match causal replay"
            )
        return cycle
