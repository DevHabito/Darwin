"""Finite observable-history planning components for Darwin H50-L10.

This module implements a small deterministic controlled process.  It does not
implement a general predictive-state representation, a neural world model,
general intelligence, or consciousness.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from itertools import product
import math
import random
from typing import Any, Sequence, TypeAlias

from .models import ValidationError, canonical_json, parse_json, require_text


HISTORY_LENGTH = 4
CUE_VALUES = (0, 1, 2)
PLANNING_ACTIONS = ("amber", "cyan", "violet")
PREDICTIVE_STATE_COUNT = len(CUE_VALUES) ** HISTORY_LENGTH
PREDICTIVE_PAIR_COUNT = PREDICTIVE_STATE_COUNT * len(PLANNING_ACTIONS)
PREDICTIVE_STRUCTURE_XOR_MASK = 0xA17E5

HistoryState: TypeAlias = tuple[int, int, int, int]


def _validate_cue(value: object, field: str = "cue") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in CUE_VALUES
    ):
        raise ValidationError(f"{field} must be one of {CUE_VALUES}")
    return value


def validate_history(
    value: object,
    field: str = "history",
) -> HistoryState:
    if (
        not isinstance(value, tuple)
        or len(value) != HISTORY_LENGTH
    ):
        raise ValidationError(
            f"{field} must contain exactly {HISTORY_LENGTH} cues"
        )
    for index, cue in enumerate(value):
        _validate_cue(cue, f"{field}[{index}]")
    return value  # type: ignore[return-value]


def next_history(history: HistoryState, next_cue: int) -> HistoryState:
    validate_history(history)
    _validate_cue(next_cue, "next_cue")
    return history[1:] + (next_cue,)


def history_hamming_distance(
    left: HistoryState,
    right: HistoryState,
) -> int:
    validate_history(left, "left_history")
    validate_history(right, "right_history")
    return sum(a != b for a, b in zip(left, right, strict=True))


ALL_HISTORY_STATES: tuple[HistoryState, ...] = tuple(
    product(CUE_VALUES, repeat=HISTORY_LENGTH)  # type: ignore[arg-type]
)


@dataclass(frozen=True, slots=True)
class HistoryTransitionRule:
    history: HistoryState
    next_cues: tuple[int, int, int]

    def __post_init__(self) -> None:
        validate_history(self.history)
        if (
            not isinstance(self.next_cues, tuple)
            or len(self.next_cues) != len(PLANNING_ACTIONS)
        ):
            raise ValidationError("next_cues must match the action space")
        for index, cue in enumerate(self.next_cues):
            _validate_cue(cue, f"next_cues[{index}]")
        if tuple(sorted(self.next_cues)) != CUE_VALUES:
            raise ValidationError(
                "each history must permute all possible next cues"
            )

    def next_cue_for(self, action: str) -> int:
        if action not in PLANNING_ACTIONS:
            raise ValidationError("unknown planning action")
        return self.next_cues[PLANNING_ACTIONS.index(action)]


@dataclass(frozen=True, slots=True)
class PredictiveWorldSpecification:
    seed: int
    rules: tuple[HistoryTransitionRule, ...]
    exploration_start: HistoryState

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("predictive world seed must be an integer")
        if (
            not isinstance(self.rules, tuple)
            or len(self.rules) != PREDICTIVE_STATE_COUNT
            or tuple(rule.history for rule in self.rules)
            != ALL_HISTORY_STATES
        ):
            raise ValidationError(
                "predictive rules must cover every ordered history"
            )
        validate_history(self.exploration_start, "exploration_start")

    @classmethod
    def from_seed(cls, seed: int) -> "PredictiveWorldSpecification":
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("predictive world seed must be an integer")
        rng = random.Random(seed ^ PREDICTIVE_STRUCTURE_XOR_MASK)
        rules: list[HistoryTransitionRule] = []
        for history in ALL_HISTORY_STATES:
            cues = list(CUE_VALUES)
            rng.shuffle(cues)
            rules.append(
                HistoryTransitionRule(
                    history=history,
                    next_cues=tuple(cues),  # type: ignore[arg-type]
                )
            )
        return cls(
            seed=seed,
            rules=tuple(rules),
            exploration_start=rng.choice(ALL_HISTORY_STATES),
        )

    def rule(self, history: HistoryState) -> HistoryTransitionRule:
        validate_history(history)
        index = (
            history[0] * len(CUE_VALUES) ** 3
            + history[1] * len(CUE_VALUES) ** 2
            + history[2] * len(CUE_VALUES)
            + history[3]
        )
        return self.rules[index]

    def transition(
        self,
        history: HistoryState,
        action: str,
    ) -> HistoryState:
        cue = self.rule(history).next_cue_for(action)
        return next_history(history, cue)

    def shortest_plan(
        self,
        start: HistoryState,
        goal: HistoryState,
    ) -> tuple[str, ...]:
        validate_history(start, "start")
        validate_history(goal, "goal")
        if start == goal:
            return ()
        frontier: deque[tuple[HistoryState, tuple[str, ...]]] = deque(
            [(start, ())]
        )
        visited = {start}
        while frontier:
            state, actions = frontier.popleft()
            for action in PLANNING_ACTIONS:
                target = self.transition(state, action)
                candidate = actions + (action,)
                if target == goal:
                    return candidate
                if target not in visited:
                    visited.add(target)
                    frontier.append((target, candidate))
        raise RuntimeError("registered predictive world is not connected")


@dataclass(frozen=True, slots=True)
class PredictivePlanningObservation:
    world_id: str
    episode_id: str
    cue: int
    goal_history: HistoryState | None
    step_index: int
    terminated: bool
    truncated: bool
    priming_history: HistoryState | None

    def __post_init__(self) -> None:
        require_text(self.world_id, "world_id")
        require_text(self.episode_id, "episode_id")
        _validate_cue(self.cue)
        if self.goal_history is not None:
            validate_history(self.goal_history, "goal_history")
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValidationError("planning step index is invalid")
        if (
            not isinstance(self.terminated, bool)
            or not isinstance(self.truncated, bool)
            or self.terminated and self.truncated
        ):
            raise ValidationError("planning terminal flags are invalid")
        if self.priming_history is not None:
            validate_history(self.priming_history, "priming_history")
            if (
                self.step_index != 0
                or self.priming_history[-1] != self.cue
            ):
                raise ValidationError(
                    "priming history is inconsistent with observation"
                )
        elif self.step_index == 0:
            raise ValidationError(
                "initial observation must contain priming history"
            )
        if self.step_index == 0 and (
            self.terminated or self.truncated
        ):
            raise ValidationError(
                "initial observation cannot already be complete"
            )


@dataclass(frozen=True, slots=True)
class PredictivePlanningStep:
    observation: PredictivePlanningObservation
    action: str
    reward: float

    def __post_init__(self) -> None:
        if self.action not in PLANNING_ACTIONS:
            raise ValidationError("planning step action is invalid")
        if (
            isinstance(self.reward, bool)
            or not isinstance(self.reward, (int, float))
            or not math.isfinite(self.reward)
            or self.reward not in {0.0, 1.0}
        ):
            raise ValidationError("planning reward must be zero or one")
        if (self.reward == 1.0) != self.observation.terminated:
            raise ValidationError(
                "positive reward must exactly match goal termination"
            )


class PredictivePlanningWorld:
    """Hidden order-four process exposing one cue after each action."""

    def __init__(self, seed: int) -> None:
        self.specification = PredictiveWorldSpecification.from_seed(seed)
        self.world_id = f"predictive-history-{seed}"
        self._episode_counter = 0
        self._episode_id = ""
        self._history: HistoryState | None = None
        self._goal: HistoryState | None = None
        self._step_index = 0
        self._max_steps = 0
        self._terminated = False
        self._truncated = False

    @property
    def current_history_for_evaluator(self) -> HistoryState:
        if self._history is None:
            raise RuntimeError("predictive world has not been reset")
        return self._history

    def reset(
        self,
        *,
        start: HistoryState,
        goal: HistoryState | None,
        max_steps: int,
    ) -> PredictivePlanningObservation:
        validate_history(start, "start")
        if goal is not None:
            validate_history(goal, "goal")
            if start == goal:
                raise ValidationError("start and goal must differ")
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or max_steps < 1
        ):
            raise ValidationError("max_steps must be positive")
        self._episode_counter += 1
        self._episode_id = (
            f"{self.world_id}:episode:{self._episode_counter:06d}"
        )
        self._history = start
        self._goal = goal
        self._step_index = 0
        self._max_steps = max_steps
        self._terminated = False
        self._truncated = False
        return self._observation(priming=True)

    def _require_active(self) -> HistoryState:
        if self._history is None:
            raise RuntimeError("predictive world has not been reset")
        if self._terminated or self._truncated:
            raise RuntimeError("predictive episode is already complete")
        return self._history

    def _observation(
        self,
        *,
        priming: bool,
    ) -> PredictivePlanningObservation:
        if self._history is None:
            raise RuntimeError("predictive world has not been reset")
        return PredictivePlanningObservation(
            world_id=self.world_id,
            episode_id=self._episode_id,
            cue=self._history[-1],
            goal_history=self._goal,
            step_index=self._step_index,
            terminated=self._terminated,
            truncated=self._truncated,
            priming_history=self._history if priming else None,
        )

    def step(self, action: str) -> PredictivePlanningStep:
        history = self._require_active()
        if action not in PLANNING_ACTIONS:
            raise ValidationError("action is not available")
        self._history = self.specification.transition(history, action)
        self._step_index += 1
        self._terminated = (
            self._goal is not None and self._history == self._goal
        )
        self._truncated = (
            not self._terminated and self._step_index >= self._max_steps
        )
        reward = 1.0 if self._terminated else 0.0
        return PredictivePlanningStep(
            observation=self._observation(priming=False),
            action=action,
            reward=reward,
        )


@dataclass(frozen=True, slots=True)
class PredictiveTransitionExperience:
    world_id: str
    trace_id: str
    sequence: int
    history: HistoryState
    action: str
    next_cue: int

    def __post_init__(self) -> None:
        require_text(self.world_id, "world_id")
        require_text(self.trace_id, "trace_id")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ValidationError("experience sequence must be positive")
        validate_history(self.history)
        if self.action not in PLANNING_ACTIONS:
            raise ValidationError("experience action is invalid")
        _validate_cue(self.next_cue, "next_cue")

    @property
    def next_history(self) -> HistoryState:
        return next_history(self.history, self.next_cue)


@dataclass(frozen=True, slots=True)
class PredictiveTransitionPrediction:
    history: HistoryState
    action: str
    next_history: HistoryState
    probability: float
    evidence_count: int
    distribution: tuple[tuple[HistoryState, float], ...]


class PredictiveHistoryModel:
    """Action-conditioned empirical model over observable histories."""

    SNAPSHOT_SCHEMA = 1

    def __init__(self) -> None:
        self._archive: list[PredictiveTransitionExperience] = []
        self._counts: dict[
            tuple[HistoryState, str],
            Counter[HistoryState],
        ] = defaultdict(Counter)
        self._world_id: str | None = None
        self._trace_id: str | None = None

    @property
    def archive(self) -> tuple[PredictiveTransitionExperience, ...]:
        return tuple(self._archive)

    @property
    def experience_count(self) -> int:
        return len(self._archive)

    @property
    def known_transition_pair_count(self) -> int:
        return len(self._counts)

    @property
    def world_id(self) -> str | None:
        return self._world_id

    @property
    def trace_id(self) -> str | None:
        return self._trace_id

    @property
    def current_history(self) -> HistoryState | None:
        if not self._archive:
            return None
        return self._archive[-1].next_history

    @property
    def known_states(self) -> tuple[HistoryState, ...]:
        states = {history for history, _action in self._counts}
        for counts in self._counts.values():
            states.update(counts)
        return tuple(sorted(states))

    def observe(self, experience: PredictiveTransitionExperience) -> None:
        if experience.sequence != len(self._archive) + 1:
            raise ValidationError(
                "experience sequence must be contiguous and unreplayed"
            )
        if self._archive:
            previous = self._archive[-1]
            if experience.history != previous.next_history:
                raise ValidationError(
                    "experience history is discontinuous"
                )
            if (
                experience.world_id != self._world_id
                or experience.trace_id != self._trace_id
            ):
                raise ValidationError(
                    "one predictive model cannot mix traces or worlds"
                )
        else:
            self._world_id = experience.world_id
            self._trace_id = experience.trace_id
        self._archive.append(experience)
        self._counts[(experience.history, experience.action)][
            experience.next_history
        ] += 1

    def evidence_count_for(
        self,
        history: HistoryState,
        action: str,
    ) -> int:
        validate_history(history)
        if action not in PLANNING_ACTIONS:
            raise ValidationError("unknown planning action")
        return sum(self._counts.get((history, action), {}).values())

    def actions_for(self, history: HistoryState) -> tuple[str, ...]:
        validate_history(history)
        return tuple(
            action
            for action in PLANNING_ACTIONS
            if (history, action) in self._counts
        )

    def predict(
        self,
        history: HistoryState,
        action: str,
    ) -> PredictiveTransitionPrediction | None:
        validate_history(history)
        if action not in PLANNING_ACTIONS:
            raise ValidationError("unknown planning action")
        counts = self._counts.get((history, action))
        if not counts:
            return None
        total = sum(counts.values())
        ordered = sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        target, best_count = ordered[0]
        return PredictiveTransitionPrediction(
            history=history,
            action=action,
            next_history=target,
            probability=best_count / total,
            evidence_count=total,
            distribution=tuple(
                (state, count / total)
                for state, count in sorted(counts.items())
            ),
        )

    def _count_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for history, action in sorted(
            self._counts,
            key=lambda item: (item[0], PLANNING_ACTIONS.index(item[1])),
        ):
            rows.append(
                {
                    "history": list(history),
                    "action": action,
                    "next_counts": [
                        {
                            "history": list(target),
                            "count": count,
                        }
                        for target, count in sorted(
                            self._counts[(history, action)].items()
                        )
                    ],
                }
            )
        return rows

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "archive": [
                    {
                        "world_id": item.world_id,
                        "trace_id": item.trace_id,
                        "sequence": item.sequence,
                        "history": list(item.history),
                        "action": item.action,
                        "next_cue": item.next_cue,
                    }
                    for item in self._archive
                ],
                "counts": self._count_rows(),
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "PredictiveHistoryModel":
        parsed = parse_json(raw)
        if (
            not isinstance(parsed, dict)
            or parsed.get("schema") != cls.SNAPSHOT_SCHEMA
        ):
            raise ValidationError("unsupported predictive-model snapshot")
        archive = parsed.get("archive")
        if not isinstance(archive, list):
            raise ValidationError("predictive archive must be a list")
        model = cls()
        for row in archive:
            if not isinstance(row, dict):
                raise ValidationError("invalid predictive experience")
            try:
                raw_history = row["history"]
                if not isinstance(raw_history, list):
                    raise ValidationError(
                        "experience history must be a list"
                    )
                experience = PredictiveTransitionExperience(
                    world_id=row["world_id"],
                    trace_id=row["trace_id"],
                    sequence=row["sequence"],
                    history=tuple(raw_history),  # type: ignore[arg-type]
                    action=row["action"],
                    next_cue=row["next_cue"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"predictive experience missing field: {error.args[0]}"
                ) from error
            model.observe(experience)
        if canonical_json(parsed) != model.to_snapshot():
            raise ValidationError(
                "predictive snapshot does not match replayed archive"
            )
        return model


@dataclass(frozen=True, slots=True)
class PredictiveHistoryPlan:
    found: bool
    start: HistoryState
    goal: HistoryState
    actions: tuple[str, ...]
    predicted_histories: tuple[HistoryState, ...]
    expanded_states: int
    reason: str


class PredictiveHistoryPlanner:
    """Breadth-first planning over learned modal history transitions."""

    def __init__(
        self,
        model: PredictiveHistoryModel,
        *,
        max_depth: int = 8,
        action_rotation: int = 0,
    ) -> None:
        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, int)
            or max_depth < 1
        ):
            raise ValidationError("max_depth must be positive")
        if (
            isinstance(action_rotation, bool)
            or not isinstance(action_rotation, int)
            or not 0 <= action_rotation < len(PLANNING_ACTIONS)
        ):
            raise ValidationError("action_rotation is invalid")
        self.model = model
        self.max_depth = max_depth
        self.action_rotation = action_rotation

    def _prediction_for_executed_action(
        self,
        history: HistoryState,
        action: str,
    ) -> PredictiveTransitionPrediction | None:
        index = PLANNING_ACTIONS.index(action)
        queried_action = PLANNING_ACTIONS[
            (index + self.action_rotation) % len(PLANNING_ACTIONS)
        ]
        return self.model.predict(history, queried_action)

    def plan(
        self,
        start: HistoryState,
        goal: HistoryState,
    ) -> PredictiveHistoryPlan:
        validate_history(start, "start")
        validate_history(goal, "goal")
        if start == goal:
            return PredictiveHistoryPlan(
                True,
                start,
                goal,
                (),
                (start,),
                0,
                "already_at_goal",
            )
        frontier: deque[
            tuple[
                HistoryState,
                tuple[str, ...],
                tuple[HistoryState, ...],
            ]
        ] = deque([(start, (), (start,))])
        visited = {start}
        expanded = 0
        while frontier:
            state, actions, histories = frontier.popleft()
            if len(actions) >= self.max_depth:
                continue
            expanded += 1
            for action in PLANNING_ACTIONS:
                prediction = self._prediction_for_executed_action(
                    state,
                    action,
                )
                if prediction is None:
                    continue
                target = prediction.next_history
                candidate_actions = actions + (action,)
                candidate_histories = histories + (target,)
                if target == goal:
                    return PredictiveHistoryPlan(
                        True,
                        start,
                        goal,
                        candidate_actions,
                        candidate_histories,
                        expanded,
                        "model_path",
                    )
                if target not in visited:
                    visited.add(target)
                    frontier.append(
                        (
                            target,
                            candidate_actions,
                            candidate_histories,
                        )
                    )
        return PredictiveHistoryPlan(
            False,
            start,
            goal,
            (),
            (start,),
            expanded,
            (
                "model_empty"
                if self.model.experience_count == 0
                else "no_known_path"
            ),
        )


class HistoryFrontierExplorer:
    """Selects actions from observable history and the learned model only."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        model: PredictiveHistoryModel | None = None,
    ) -> None:
        self.model = model or PredictiveHistoryModel()
        self._current_history: HistoryState | None = (
            self.model.current_history
        )
        self._pending_action: str | None = None

    @property
    def current_history(self) -> HistoryState | None:
        return self._current_history

    @property
    def pending_action(self) -> str | None:
        return self._pending_action

    def start(self, priming_history: HistoryState) -> None:
        validate_history(priming_history, "priming_history")
        if self._current_history is not None or self.model.experience_count:
            raise ValidationError("explorer has already started")
        self._current_history = priming_history

    def _path_to_frontier(
        self,
        start: HistoryState,
    ) -> tuple[str, ...] | None:
        frontier: deque[tuple[HistoryState, tuple[str, ...]]] = deque(
            [(start, ())]
        )
        visited = {start}
        while frontier:
            state, path = frontier.popleft()
            if state != start and any(
                self.model.evidence_count_for(state, action) == 0
                for action in PLANNING_ACTIONS
            ):
                return path
            for action in PLANNING_ACTIONS:
                prediction = self.model.predict(state, action)
                if (
                    prediction is not None
                    and prediction.next_history not in visited
                ):
                    visited.add(prediction.next_history)
                    frontier.append(
                        (
                            prediction.next_history,
                            path + (action,),
                        )
                    )
        return None

    def choose_action(self) -> str:
        if self._current_history is None:
            raise ValidationError("explorer must be started")
        if self._pending_action is not None:
            return self._pending_action
        unseen = tuple(
            action
            for action in PLANNING_ACTIONS
            if self.model.evidence_count_for(
                self._current_history,
                action,
            )
            == 0
        )
        if unseen:
            action = unseen[0]
        elif (
            self.model.known_transition_pair_count
            == PREDICTIVE_PAIR_COUNT
        ):
            action = min(
                PLANNING_ACTIONS,
                key=lambda item: (
                    self.model.evidence_count_for(
                        self._current_history,
                        item,
                    ),
                    PLANNING_ACTIONS.index(item),
                ),
            )
        else:
            path = self._path_to_frontier(self._current_history)
            if path:
                action = path[0]
            else:
                action = min(
                    PLANNING_ACTIONS,
                    key=lambda item: (
                        self.model.evidence_count_for(
                            self._current_history,
                            item,
                        ),
                        PLANNING_ACTIONS.index(item),
                    ),
                )
        self._pending_action = action
        return action

    def observe(
        self,
        *,
        next_cue: int,
        world_id: str,
        trace_id: str,
    ) -> PredictiveTransitionExperience:
        if self._current_history is None or self._pending_action is None:
            raise ValidationError("chosen action must precede observation")
        experience = PredictiveTransitionExperience(
            world_id=world_id,
            trace_id=trace_id,
            sequence=self.model.experience_count + 1,
            history=self._current_history,
            action=self._pending_action,
            next_cue=next_cue,
        )
        self.model.observe(experience)
        self._current_history = experience.next_history
        self._pending_action = None
        return experience

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "model": parse_json(self.model.to_snapshot()),
                "current_history": (
                    list(self._current_history)
                    if self._current_history is not None
                    else None
                ),
                "pending_action": self._pending_action,
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "HistoryFrontierExplorer":
        parsed = parse_json(raw)
        if (
            not isinstance(parsed, dict)
            or parsed.get("schema") != cls.SNAPSHOT_SCHEMA
        ):
            raise ValidationError("unsupported explorer snapshot")
        model_raw = parsed.get("model")
        if not isinstance(model_raw, dict):
            raise ValidationError("explorer model snapshot is invalid")
        model = PredictiveHistoryModel.from_snapshot(
            canonical_json(model_raw)
        )
        explorer = cls(model)
        current_raw = parsed.get("current_history")
        if current_raw is None:
            if model.experience_count:
                raise ValidationError(
                    "trained explorer must have current history"
                )
            explorer._current_history = None
        else:
            if not isinstance(current_raw, list):
                raise ValidationError(
                    "explorer current history must be a list"
                )
            current = validate_history(
                tuple(current_raw),
                "current_history",
            )
            if (
                model.current_history is not None
                and current != model.current_history
            ):
                raise ValidationError(
                    "explorer history does not match model archive"
                )
            explorer._current_history = current
        pending = parsed.get("pending_action")
        if pending is not None:
            if pending not in PLANNING_ACTIONS:
                raise ValidationError("pending explorer action is invalid")
            if explorer.choose_action() != pending:
                raise ValidationError(
                    "pending explorer action does not match policy"
                )
        if canonical_json(parsed) != explorer.to_snapshot():
            raise ValidationError(
                "explorer snapshot does not match causal replay"
            )
        return explorer
