"""Causal online action-alignment adaptation for H50-L17 development.

The transition prior remains frozen.  A separate tracker infers which of three
registered action rotations currently explains chosen-action observations.
This is a narrow hidden-mode update, not general online world-model learning.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .integrated_cycle_lab import IntegratedCycleDecision
from .models import ValidationError, canonical_json, parse_json, require_text
from .predictive_planning_lab import (
    PLANNING_ACTIONS,
    HistoryState,
    PredictiveHistoryModel,
    PredictiveHistoryPlanner,
    next_history,
    validate_history,
)


ALIGNMENT_ROTATIONS = tuple(range(len(PLANNING_ACTIONS)))
ALIGNMENT_POLICIES = ("latest", "cumulative", "frozen")


def _model_digest(model: PredictiveHistoryModel) -> str:
    return hashlib.sha256(model.to_snapshot().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AlignmentExperience:
    sequence: int
    episode_index: int
    step_index: int
    history: HistoryState
    action: str
    next_cue: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
            or isinstance(self.episode_index, bool)
            or not isinstance(self.episode_index, int)
            or self.episode_index < 1
            or isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValidationError("alignment experience index is invalid")
        validate_history(self.history, "alignment experience history")
        if self.action not in PLANNING_ACTIONS:
            raise ValidationError("alignment experience action is invalid")
        next_history(self.history, self.next_cue)

    @property
    def observed_history(self) -> HistoryState:
        return next_history(self.history, self.next_cue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "episode_index": self.episode_index,
            "step_index": self.step_index,
            "history": list(self.history),
            "action": self.action,
            "next_cue": self.next_cue,
        }


@dataclass(frozen=True, slots=True)
class AlignmentUpdate:
    sequence: int
    compatible_rotation: int
    recorded_rotation: int
    rotation_before: int
    rotation_after: int
    prediction_matched: bool
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "compatible_rotation": self.compatible_rotation,
            "recorded_rotation": self.recorded_rotation,
            "rotation_before": self.rotation_before,
            "rotation_after": self.rotation_after,
            "prediction_matched": self.prediction_matched,
            "changed": self.changed,
        }


class OnlineActionAlignmentTracker:
    """Replay-checked hidden action-rotation tracker."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        prior_model: PredictiveHistoryModel,
        policy: str = "latest",
        initial_rotation: int = 0,
        evidence_shift: int = 0,
    ) -> None:
        if not isinstance(prior_model, PredictiveHistoryModel):
            raise ValidationError("alignment prior model is invalid")
        if policy not in ALIGNMENT_POLICIES:
            raise ValidationError("alignment policy is invalid")
        if initial_rotation not in ALIGNMENT_ROTATIONS:
            raise ValidationError("initial alignment rotation is invalid")
        if evidence_shift not in ALIGNMENT_ROTATIONS:
            raise ValidationError("alignment evidence shift is invalid")
        self.prior_model = prior_model
        self.policy = policy
        self.initial_rotation = initial_rotation
        self.evidence_shift = evidence_shift
        self._prior_snapshot = prior_model.to_snapshot()
        self._prior_digest = _model_digest(prior_model)
        self._archive: list[AlignmentExperience] = []
        self._updates: list[AlignmentUpdate] = []
        self._counts = [0 for _ in ALIGNMENT_ROTATIONS]
        self._current_rotation = initial_rotation

    @property
    def archive(self) -> tuple[AlignmentExperience, ...]:
        return tuple(self._archive)

    @property
    def updates(self) -> tuple[AlignmentUpdate, ...]:
        return tuple(self._updates)

    @property
    def current_rotation(self) -> int:
        return self._current_rotation

    @property
    def counts(self) -> tuple[int, ...]:
        return tuple(self._counts)

    @property
    def prior_digest(self) -> str:
        return self._prior_digest

    @property
    def prior_frozen(self) -> bool:
        return self.prior_model.to_snapshot() == self._prior_snapshot

    def _validate_continuity(self, experience: AlignmentExperience) -> None:
        if experience.sequence != len(self._archive) + 1:
            raise ValidationError(
                "alignment experience must be contiguous and unreplayed"
            )
        if not self._archive:
            if experience.episode_index != 1 or experience.step_index != 0:
                raise ValidationError(
                    "alignment archive must start at episode one step zero"
                )
            return
        previous = self._archive[-1]
        if experience.episode_index == previous.episode_index:
            if (
                experience.step_index != previous.step_index + 1
                or experience.history != previous.observed_history
            ):
                raise ValidationError(
                    "alignment within-episode trace is discontinuous"
                )
            return
        if (
            experience.episode_index != previous.episode_index + 1
            or experience.step_index != 0
        ):
            raise ValidationError(
                "alignment episode transition is discontinuous"
            )

    def _compatible_rotation(
        self,
        experience: AlignmentExperience,
    ) -> int:
        compatible: list[int] = []
        executed_index = PLANNING_ACTIONS.index(experience.action)
        for rotation in ALIGNMENT_ROTATIONS:
            queried_action = PLANNING_ACTIONS[
                (executed_index + rotation) % len(PLANNING_ACTIONS)
            ]
            prediction = self.prior_model.predict(
                experience.history,
                queried_action,
            )
            if (
                prediction is not None
                and prediction.next_history == experience.observed_history
            ):
                compatible.append(rotation)
        if len(compatible) != 1:
            raise ValidationError(
                "alignment observation does not identify exactly one mode"
            )
        return compatible[0]

    def observe(self, experience: AlignmentExperience) -> AlignmentUpdate:
        if not isinstance(experience, AlignmentExperience):
            raise ValidationError("alignment experience is invalid")
        if not self.prior_frozen:
            raise ValidationError("alignment prior changed during adaptation")
        self._validate_continuity(experience)
        compatible = self._compatible_rotation(experience)
        recorded = (
            compatible + self.evidence_shift
        ) % len(ALIGNMENT_ROTATIONS)
        before = self.current_rotation
        self._counts[recorded] += 1
        if self.policy == "latest":
            after = recorded
        elif self.policy == "cumulative":
            after = min(
                ALIGNMENT_ROTATIONS,
                key=lambda rotation: (-self._counts[rotation], rotation),
            )
        else:
            after = self.initial_rotation
        update = AlignmentUpdate(
            sequence=experience.sequence,
            compatible_rotation=compatible,
            recorded_rotation=recorded,
            rotation_before=before,
            rotation_after=after,
            prediction_matched=before == compatible,
            changed=before != after,
        )
        self._archive.append(experience)
        self._updates.append(update)
        self._current_rotation = after
        return update

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "configuration": {
                    "policy": self.policy,
                    "initial_rotation": self.initial_rotation,
                    "evidence_shift": self.evidence_shift,
                    "prior_digest": self.prior_digest,
                },
                "archive": [item.to_dict() for item in self.archive],
                "updates": [item.to_dict() for item in self.updates],
                "derived": {
                    "current_rotation": self.current_rotation,
                    "counts": list(self.counts),
                    "prior_frozen": self.prior_frozen,
                },
            }
        )

    @classmethod
    def from_snapshot(
        cls,
        raw: str,
        *,
        prior_model: PredictiveHistoryModel,
    ) -> "OnlineActionAlignmentTracker":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema",
            "configuration",
            "archive",
            "updates",
            "derived",
        } or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported alignment snapshot")
        configuration = parsed.get("configuration")
        archive = parsed.get("archive")
        updates = parsed.get("updates")
        if not isinstance(configuration, dict) or set(configuration) != {
            "policy",
            "initial_rotation",
            "evidence_shift",
            "prior_digest",
        }:
            raise ValidationError("alignment snapshot configuration is invalid")
        if configuration.get("prior_digest") != _model_digest(prior_model):
            raise ValidationError("alignment prior digest disagrees")
        if not isinstance(archive, list) or not isinstance(updates, list):
            raise ValidationError("alignment snapshot trace is invalid")
        tracker = cls(
            prior_model=prior_model,
            policy=configuration.get("policy"),  # type: ignore[arg-type]
            initial_rotation=configuration.get(  # type: ignore[arg-type]
                "initial_rotation"
            ),
            evidence_shift=configuration.get(  # type: ignore[arg-type]
                "evidence_shift"
            ),
        )
        if len(archive) != len(updates):
            raise ValidationError("alignment snapshot trace is unbalanced")
        for raw_experience, raw_update in zip(archive, updates, strict=True):
            if not isinstance(raw_experience, dict):
                raise ValidationError("alignment snapshot experience is invalid")
            history = raw_experience.get("history")
            if not isinstance(history, list):
                raise ValidationError("alignment snapshot history is invalid")
            experience = AlignmentExperience(
                sequence=raw_experience.get("sequence"),  # type: ignore[arg-type]
                episode_index=raw_experience.get(  # type: ignore[arg-type]
                    "episode_index"
                ),
                step_index=raw_experience.get("step_index"),  # type: ignore[arg-type]
                history=tuple(history),  # type: ignore[arg-type]
                action=raw_experience.get("action"),  # type: ignore[arg-type]
                next_cue=raw_experience.get("next_cue"),  # type: ignore[arg-type]
            )
            update = tracker.observe(experience)
            if not isinstance(raw_update, dict) or update.to_dict() != raw_update:
                raise ValidationError("alignment snapshot update disagrees")
        if canonical_json(parsed) != tracker.to_snapshot():
            raise ValidationError(
                "alignment snapshot does not match causal replay"
            )
        return tracker


@dataclass(frozen=True, slots=True)
class OnlineCycleObservation:
    step_index: int
    action: str
    observed_cue: int
    observed_history: HistoryState
    goal_reached: bool
    alignment_update: AlignmentUpdate


class OnlineAdaptivePlanningCycle:
    """One goal-bound planning cycle with post-observation alignment updates."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        prior_model: PredictiveHistoryModel,
        tracker: OnlineActionAlignmentTracker,
        session_id: str,
        goal_id: str,
        evidence_source: str,
        episode_index: int,
        initial_history: HistoryState,
        goal_history: HistoryState,
        max_steps: int,
    ) -> None:
        if not isinstance(prior_model, PredictiveHistoryModel):
            raise ValidationError("online cycle prior model is invalid")
        if not isinstance(tracker, OnlineActionAlignmentTracker):
            raise ValidationError("online cycle tracker is invalid")
        if tracker.prior_digest != _model_digest(prior_model):
            raise ValidationError("online cycle prior binding disagrees")
        if (
            isinstance(episode_index, bool)
            or not isinstance(episode_index, int)
            or episode_index < 1
            or episode_index != len({item.episode_index for item in tracker.archive}) + 1
        ):
            raise ValidationError("online cycle episode index is invalid")
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or max_steps < 1
        ):
            raise ValidationError("online cycle max steps is invalid")
        self.prior_model = prior_model
        self.tracker = tracker
        self.session_id = require_text(session_id, "session_id")
        self.goal_id = require_text(goal_id, "goal_id")
        self.evidence_source = require_text(evidence_source, "evidence_source")
        self.episode_index = episode_index
        self.initial_history = validate_history(
            initial_history,
            "initial_history",
        )
        self.goal_history = validate_history(goal_history, "goal_history")
        if self.initial_history == self.goal_history:
            raise ValidationError("online cycle goal must differ from start")
        self.max_steps = max_steps
        self._prior_snapshot = prior_model.to_snapshot()
        self._starting_tracker_snapshot = tracker.to_snapshot()
        self._expected_tracker_snapshot = tracker.to_snapshot()
        self._current_history = self.initial_history
        self._actions: list[str] = []
        self._observed_cues: list[int] = []
        self._updates: list[AlignmentUpdate] = []
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
    def updates(self) -> tuple[AlignmentUpdate, ...]:
        return tuple(self._updates)

    @property
    def step_index(self) -> int:
        return len(self._actions)

    @property
    def goal_reached(self) -> bool:
        return self.current_history == self.goal_history

    @property
    def pending_decision(self) -> IntegratedCycleDecision | None:
        return self._pending

    @property
    def prior_frozen(self) -> bool:
        return self.prior_model.to_snapshot() == self._prior_snapshot

    def _require_unmodified_tracker(self) -> None:
        if self.tracker.to_snapshot() != self._expected_tracker_snapshot:
            raise ValidationError("online cycle tracker changed externally")

    def choose_action(self) -> IntegratedCycleDecision:
        self._require_unmodified_tracker()
        if self._pending is not None:
            return self._pending
        if self.goal_reached:
            raise ValidationError("online cycle goal is already reached")
        if self.step_index >= self.max_steps:
            raise ValidationError("online cycle step budget is exhausted")
        if not self.prior_frozen:
            raise ValidationError("online cycle prior changed during control")
        plan = PredictiveHistoryPlanner(
            self.prior_model,
            max_depth=self.max_steps,
            action_rotation=self.tracker.current_rotation,
        ).plan(self.current_history, self.goal_history)
        if not plan.found or not plan.actions:
            raise ValidationError("online cycle has no aligned plan")
        self._pending = IntegratedCycleDecision(
            step_index=self.step_index,
            current_history=self.current_history,
            goal_history=self.goal_history,
            action=plan.actions[0],
            planned_actions=plan.actions,
            predicted_histories=plan.predicted_histories,
        )
        return self._pending

    def observe(self, *, action: str, next_cue: int) -> OnlineCycleObservation:
        self._require_unmodified_tracker()
        if self._pending is None:
            raise ValidationError("online observation has no decision")
        if action != self._pending.action:
            raise ValidationError("online observation action mismatch")
        observed_history = next_history(self.current_history, next_cue)
        update = self.tracker.observe(
            AlignmentExperience(
                sequence=len(self.tracker.archive) + 1,
                episode_index=self.episode_index,
                step_index=self.step_index,
                history=self.current_history,
                action=action,
                next_cue=next_cue,
            )
        )
        step_index = self.step_index
        self._actions.append(action)
        self._observed_cues.append(next_cue)
        self._updates.append(update)
        self._current_history = observed_history
        self._pending = None
        self._expected_tracker_snapshot = self.tracker.to_snapshot()
        if not self.prior_frozen:
            raise ValidationError("online cycle prior changed during control")
        return OnlineCycleObservation(
            step_index=step_index,
            action=action,
            observed_cue=next_cue,
            observed_history=observed_history,
            goal_reached=self.goal_reached,
            alignment_update=update,
        )

    def to_snapshot(self) -> str:
        self._require_unmodified_tracker()
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "binding": {
                    "session_id": self.session_id,
                    "goal_id": self.goal_id,
                    "evidence_source": self.evidence_source,
                    "episode_index": self.episode_index,
                },
                "configuration": {
                    "initial_history": list(self.initial_history),
                    "goal_history": list(self.goal_history),
                    "max_steps": self.max_steps,
                    "prior_model_snapshot": self._prior_snapshot,
                    "starting_tracker_snapshot": (
                        self._starting_tracker_snapshot
                    ),
                },
                "history": {
                    "actions": list(self.action_history),
                    "observed_cues": list(self.observed_cues),
                    "updates": [item.to_dict() for item in self.updates],
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
                    "prior_frozen": self.prior_frozen,
                    "current_rotation": self.tracker.current_rotation,
                },
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "OnlineAdaptivePlanningCycle":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema",
            "binding",
            "configuration",
            "history",
            "pending_decision",
            "derived",
        } or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported online-cycle snapshot")
        binding = parsed.get("binding")
        configuration = parsed.get("configuration")
        history = parsed.get("history")
        if not isinstance(binding, dict) or set(binding) != {
            "session_id",
            "goal_id",
            "evidence_source",
            "episode_index",
        }:
            raise ValidationError("online snapshot binding is invalid")
        if not isinstance(configuration, dict) or set(configuration) != {
            "initial_history",
            "goal_history",
            "max_steps",
            "prior_model_snapshot",
            "starting_tracker_snapshot",
        }:
            raise ValidationError("online snapshot configuration is invalid")
        if not isinstance(history, dict) or set(history) != {
            "actions",
            "observed_cues",
            "updates",
        }:
            raise ValidationError("online snapshot history is invalid")
        prior_snapshot = configuration.get("prior_model_snapshot")
        tracker_snapshot = configuration.get("starting_tracker_snapshot")
        if not isinstance(prior_snapshot, str) or not isinstance(
            tracker_snapshot,
            str,
        ):
            raise ValidationError("online snapshot model state is invalid")
        prior = PredictiveHistoryModel.from_snapshot(prior_snapshot)
        tracker = OnlineActionAlignmentTracker.from_snapshot(
            tracker_snapshot,
            prior_model=prior,
        )
        initial = configuration.get("initial_history")
        target = configuration.get("goal_history")
        if not isinstance(initial, list) or not isinstance(target, list):
            raise ValidationError("online snapshot task is invalid")
        cycle = cls(
            prior_model=prior,
            tracker=tracker,
            session_id=binding.get("session_id"),  # type: ignore[arg-type]
            goal_id=binding.get("goal_id"),  # type: ignore[arg-type]
            evidence_source=binding.get("evidence_source"),  # type: ignore[arg-type]
            episode_index=binding.get("episode_index"),  # type: ignore[arg-type]
            initial_history=tuple(initial),  # type: ignore[arg-type]
            goal_history=tuple(target),  # type: ignore[arg-type]
            max_steps=configuration.get("max_steps"),  # type: ignore[arg-type]
        )
        actions = history.get("actions")
        cues = history.get("observed_cues")
        updates = history.get("updates")
        if (
            not isinstance(actions, list)
            or not isinstance(cues, list)
            or not isinstance(updates, list)
            or not len(actions) == len(cues) == len(updates)
        ):
            raise ValidationError("online snapshot trace is invalid")
        for action, cue, raw_update in zip(
            actions,
            cues,
            updates,
            strict=True,
        ):
            decision = cycle.choose_action()
            if decision.action != action:
                raise ValidationError("online snapshot action is not causal")
            observation = cycle.observe(action=action, next_cue=cue)
            if (
                not isinstance(raw_update, dict)
                or observation.alignment_update.to_dict() != raw_update
            ):
                raise ValidationError("online snapshot update disagrees")
        pending = parsed.get("pending_decision")
        if pending is not None:
            if not isinstance(pending, dict):
                raise ValidationError("online pending decision is invalid")
            if cycle.choose_action().to_dict() != pending:
                raise ValidationError("online pending decision does not replay")
        if canonical_json(parsed) != cycle.to_snapshot():
            raise ValidationError(
                "online snapshot does not match causal replay"
            )
        return cycle
