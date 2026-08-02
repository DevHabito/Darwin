"""Small, falsifiable learning components for the Darwin v50 laboratory.

The classes in this module do not implement general intelligence or
consciousness.  They isolate one narrower claim: an agent can learn transition
dynamics from environment observations and use only that learned model to
compose a plan for a previously unseen start-goal task.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import heapq
import json
import math
import random
from typing import Any, Mapping, Protocol, Sequence

from .models import ValidationError, canonical_json, parse_json, require_text


DEFAULT_ACTIONS = ("amber", "cyan", "violet")


@dataclass(frozen=True, slots=True)
class LabObservation:
    """Observable state exposed to a policy."""

    world_id: str
    episode_id: str
    state: str
    goal: str
    step_index: int
    terminated: bool
    truncated: bool


@dataclass(frozen=True, slots=True)
class TransitionExperience:
    """One causal state-action-state observation from the environment."""

    transition_id: str
    parent_transition_id: str | None
    world_id: str
    episode_id: str
    sequence: int
    state: str
    action: str
    next_state: str
    reward: float
    terminated: bool
    truncated: bool
    source: str

    def __post_init__(self) -> None:
        require_text(self.transition_id, "transition_id")
        require_text(self.world_id, "world_id")
        require_text(self.episode_id, "episode_id")
        require_text(self.state, "state")
        require_text(self.action, "action")
        require_text(self.next_state, "next_state")
        require_text(self.source, "source")
        if self.parent_transition_id is not None:
            require_text(self.parent_transition_id, "parent_transition_id")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ValidationError("sequence must be positive")
        if (
            isinstance(self.reward, bool)
            or not isinstance(self.reward, (int, float))
            or not math.isfinite(self.reward)
        ):
            raise ValidationError("reward must be finite")
        if not isinstance(self.terminated, bool) or not isinstance(
            self.truncated, bool
        ):
            raise ValidationError("terminal flags must be booleans")
        if self.terminated and self.truncated:
            raise ValidationError("a transition cannot be terminated and truncated")


@dataclass(frozen=True, slots=True)
class LabStep:
    observation: LabObservation
    experience: TransitionExperience


class CausalEnvironment(Protocol):
    """Minimal digital embodiment boundary used by the learning lab."""

    @property
    def states(self) -> tuple[str, ...]: ...

    @property
    def action_space(self) -> tuple[str, ...]: ...

    def reset(self, *, start: str, goal: str, max_steps: int) -> LabObservation: ...

    def observe(self) -> LabObservation: ...

    def available_actions(self) -> tuple[str, ...]: ...

    def step(self, action: str) -> LabStep: ...


class OpaqueGraphWorld:
    """Deterministic graph whose transition table is hidden from policies.

    State and action labels are intentionally opaque.  The benchmark harness
    may inspect the state list to choose controlled probes, but planners only
    receive observations and a learned ``TabularTransitionModel``.
    """

    def __init__(
        self,
        *,
        world_id: str,
        transitions: Mapping[str, Mapping[str, str]],
        action_space: Sequence[str] = DEFAULT_ACTIONS,
    ) -> None:
        self.world_id = require_text(world_id, "world_id")
        actions = tuple(require_text(action, "action") for action in action_space)
        if not actions or len(set(actions)) != len(actions):
            raise ValidationError("action_space must contain unique actions")
        states = tuple(sorted(require_text(state, "state") for state in transitions))
        if len(states) < 2:
            raise ValidationError("world must contain at least two states")
        state_set = frozenset(states)
        normalized: dict[str, dict[str, str]] = {}
        for state in states:
            row = transitions[state]
            if frozenset(row) != frozenset(actions):
                raise ValidationError(
                    f"state {state!r} must define exactly the action space"
                )
            normalized[state] = {}
            for action in actions:
                target = require_text(row[action], "next_state")
                if target not in state_set:
                    raise ValidationError(
                        f"transition target {target!r} is not a world state"
                    )
                normalized[state][action] = target
        self._states = states
        self._actions = actions
        self.__transitions = normalized
        self._episode_counter = 0
        self._episode_id = ""
        self._state = ""
        self._goal = ""
        self._step_index = 0
        self._max_steps = 0
        self._terminated = False
        self._truncated = False
        self._last_transition_id: str | None = None

    @property
    def states(self) -> tuple[str, ...]:
        return self._states

    @property
    def action_space(self) -> tuple[str, ...]:
        return self._actions

    def reset(self, *, start: str, goal: str, max_steps: int) -> LabObservation:
        if start not in self._states:
            raise ValidationError("unknown start state")
        if goal not in self._states:
            raise ValidationError("unknown goal state")
        if start == goal:
            raise ValidationError("start and goal must differ")
        return self._reset(start=start, goal=goal, max_steps=max_steps)

    def reset_exploration(
        self,
        *,
        start: str,
        max_steps: int,
    ) -> LabObservation:
        """Start a budgeted episode with no rewarding terminal goal."""

        if start not in self._states:
            raise ValidationError("unknown start state")
        return self._reset(start=start, goal="", max_steps=max_steps)

    def _reset(
        self,
        *,
        start: str,
        goal: str,
        max_steps: int,
    ) -> LabObservation:
        if max_steps < 1:
            raise ValidationError("max_steps must be positive")
        self._episode_counter += 1
        self._episode_id = f"{self.world_id}:episode:{self._episode_counter:06d}"
        self._state = start
        self._goal = goal
        self._step_index = 0
        self._max_steps = max_steps
        self._terminated = False
        self._truncated = False
        self._last_transition_id = None
        return self.observe()

    def _require_active(self) -> None:
        if not self._episode_id:
            raise RuntimeError("environment has not been reset")
        if self._terminated or self._truncated:
            raise RuntimeError("episode is already complete")

    def observe(self) -> LabObservation:
        if not self._episode_id:
            raise RuntimeError("environment has not been reset")
        return LabObservation(
            world_id=self.world_id,
            episode_id=self._episode_id,
            state=self._state,
            goal=self._goal,
            step_index=self._step_index,
            terminated=self._terminated,
            truncated=self._truncated,
        )

    def available_actions(self) -> tuple[str, ...]:
        self._require_active()
        return self._actions

    def step(self, action: str) -> LabStep:
        self._require_active()
        if action not in self._actions:
            raise ValidationError("action is not available")
        previous = self._state
        self._state = self.__transitions[previous][action]
        self._step_index += 1
        self._terminated = bool(self._goal) and self._state == self._goal
        self._truncated = (
            not self._terminated and self._step_index >= self._max_steps
        )
        transition_id = (
            f"{self._episode_id}:transition:{self._step_index:04d}"
        )
        experience = TransitionExperience(
            transition_id=transition_id,
            parent_transition_id=self._last_transition_id,
            world_id=self.world_id,
            episode_id=self._episode_id,
            sequence=self._step_index,
            state=previous,
            action=action,
            next_state=self._state,
            reward=1.0 if self._terminated else -0.01,
            terminated=self._terminated,
            truncated=self._truncated,
            source=f"opaque_graph_world:{self.world_id}",
        )
        self._last_transition_id = transition_id
        return LabStep(self.observe(), experience)

    def evaluator_shortest_path_length(self, start: str, goal: str) -> int:
        """Return the true shortest length for task construction only.

        Policies are not given this method or the transition table.  Keeping
        the evaluator oracle separate prevents task selection from depending on
        whether the model under test happened to learn a path.
        """

        if start not in self._states or goal not in self._states:
            raise ValidationError("oracle query references an unknown state")
        if start == goal:
            return 0
        frontier = deque([(start, 0)])
        visited = {start}
        while frontier:
            state, depth = frontier.popleft()
            for action in self._actions:
                target = self.__transitions[state][action]
                if target == goal:
                    return depth + 1
                if target not in visited:
                    visited.add(target)
                    frontier.append((target, depth + 1))
        raise RuntimeError("goal is unreachable in benchmark world")


def make_benchmark_world(
    seed: int,
    *,
    state_count: int = 9,
) -> OpaqueGraphWorld:
    """Build a reproducible strongly connected world with opaque labels."""

    if state_count < 7:
        raise ValidationError("state_count must be at least seven")
    rng = random.Random(seed)
    raw_labels = [f"{rng.getrandbits(48):012x}" for _ in range(state_count)]
    if len(set(raw_labels)) != state_count:
        raise RuntimeError("unexpected state label collision")
    labels = tuple(f"node-{value}" for value in raw_labels)
    transitions: dict[str, dict[str, str]] = {}
    for index, state in enumerate(labels):
        targets = [
            labels[(index + 1) % state_count],
            labels[(index - 1) % state_count],
            labels[(index + 3) % state_count],
        ]
        actions = list(DEFAULT_ACTIONS)
        rng.shuffle(actions)
        transitions[state] = dict(zip(actions, targets, strict=True))
    return OpaqueGraphWorld(
        world_id=f"opaque-graph-{seed}",
        transitions=transitions,
    )


@dataclass(frozen=True, slots=True)
class TransitionPrediction:
    state: str
    action: str
    next_state: str
    probability: float
    evidence_count: int
    distribution: tuple[tuple[str, float], ...]


class TabularTransitionModel:
    """Empirical transition model learned only from experiences."""

    SNAPSHOT_SCHEMA = 1

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        self._world_ids: set[str] = set()
        self._experiences: dict[str, TransitionExperience] = {}

    @property
    def experience_count(self) -> int:
        return len(self._experiences)

    @property
    def world_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._world_ids))

    @property
    def known_transition_pair_count(self) -> int:
        return len(self._counts)

    @property
    def known_states(self) -> tuple[str, ...]:
        states = {state for state, _action in self._counts}
        for counts in self._counts.values():
            states.update(counts)
        return tuple(sorted(states))

    def observe(self, experience: TransitionExperience) -> bool:
        """Learn one transition, returning false for an exact replay."""

        existing = self._experiences.get(experience.transition_id)
        if existing is not None:
            if existing != experience:
                raise ValidationError(
                    "transition identifier replayed with different content"
                )
            return False
        if self._world_ids and experience.world_id not in self._world_ids:
            raise ValidationError(
                "one transition model cannot mix distinct world identities"
            )
        self._experiences[experience.transition_id] = experience
        self._world_ids.add(experience.world_id)
        self._counts[(experience.state, experience.action)][
            experience.next_state
        ] += 1
        return True

    def actions_for(self, state: str) -> tuple[str, ...]:
        return tuple(
            sorted(action for known_state, action in self._counts if known_state == state)
        )

    def evidence_count_for(self, state: str, action: str) -> int:
        return sum(self._counts.get((state, action), {}).values())

    def predict(self, state: str, action: str) -> TransitionPrediction | None:
        counts = self._counts.get((state, action))
        if not counts:
            return None
        total = sum(counts.values())
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        next_state, best_count = ordered[0]
        distribution = tuple(
            (target, count / total) for target, count in sorted(counts.items())
        )
        return TransitionPrediction(
            state=state,
            action=action,
            next_state=next_state,
            probability=best_count / total,
            evidence_count=total,
            distribution=distribution,
        )

    def to_snapshot(self) -> str:
        rows = [
            {
                "transition_id": experience.transition_id,
                "parent_transition_id": experience.parent_transition_id,
                "world_id": experience.world_id,
                "episode_id": experience.episode_id,
                "sequence": experience.sequence,
                "state": experience.state,
                "action": experience.action,
                "next_state": experience.next_state,
                "reward": experience.reward,
                "terminated": experience.terminated,
                "truncated": experience.truncated,
                "source": experience.source,
            }
            for experience in sorted(
                self._experiences.values(),
                key=lambda item: item.transition_id,
            )
        ]
        payload = {
            "schema": self.SNAPSHOT_SCHEMA,
            "experiences": rows,
        }
        return canonical_json(payload)

    @classmethod
    def from_snapshot(cls, raw: str) -> "TabularTransitionModel":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported transition model snapshot")
        experiences = parsed.get("experiences")
        if not isinstance(experiences, list):
            raise ValidationError("invalid transition model snapshot")
        model = cls()
        for row in experiences:
            if not isinstance(row, dict):
                raise ValidationError("invalid experience row")
            try:
                experience = TransitionExperience(
                    transition_id=row["transition_id"],
                    parent_transition_id=row["parent_transition_id"],
                    world_id=row["world_id"],
                    episode_id=row["episode_id"],
                    sequence=row["sequence"],
                    state=row["state"],
                    action=row["action"],
                    next_state=row["next_state"],
                    reward=row["reward"],
                    terminated=row["terminated"],
                    truncated=row["truncated"],
                    source=row["source"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"experience snapshot missing field: {error.args[0]}"
                ) from error
            model.observe(experience)
        return model


@dataclass(frozen=True, slots=True)
class ModelPlan:
    found: bool
    start: str
    goal: str
    actions: tuple[str, ...]
    predicted_states: tuple[str, ...]
    cost: float
    expanded_states: int
    reason: str


class ModelBasedPlanner:
    """Uniform-cost search over predictions, never over the real environment."""

    def __init__(
        self,
        model: TabularTransitionModel,
        *,
        uncertainty_penalty: float = 1.0,
        max_depth: int = 32,
    ) -> None:
        if uncertainty_penalty < 0 or not math.isfinite(uncertainty_penalty):
            raise ValidationError("uncertainty_penalty must be finite and non-negative")
        if max_depth < 1:
            raise ValidationError("max_depth must be positive")
        self.model = model
        self.uncertainty_penalty = uncertainty_penalty
        self.max_depth = max_depth

    def plan(self, start: str, goal: str) -> ModelPlan:
        require_text(start, "start")
        require_text(goal, "goal")
        if start == goal:
            return ModelPlan(
                True, start, goal, (), (start,), 0.0, 0, "already_at_goal"
            )
        frontier: list[
            tuple[float, int, str, tuple[str, ...], tuple[str, ...]]
        ] = [(0.0, 0, start, (), (start,))]
        best_cost = {start: 0.0}
        expanded = 0
        while frontier:
            cost, depth, state, actions, states = heapq.heappop(frontier)
            if cost > best_cost.get(state, math.inf):
                continue
            if state == goal:
                return ModelPlan(
                    True, start, goal, actions, states, cost, expanded, "model_path"
                )
            if depth >= self.max_depth:
                continue
            expanded += 1
            for action in self.model.actions_for(state):
                prediction = self.model.predict(state, action)
                if prediction is None:
                    continue
                step_cost = 1.0 + self.uncertainty_penalty * (
                    1.0 - prediction.probability
                )
                candidate_cost = cost + step_cost
                if candidate_cost >= best_cost.get(
                    prediction.next_state, math.inf
                ):
                    continue
                best_cost[prediction.next_state] = candidate_cost
                heapq.heappush(
                    frontier,
                    (
                        candidate_cost,
                        depth + 1,
                        prediction.next_state,
                        actions + (action,),
                        states + (prediction.next_state,),
                    ),
                )
        reason = (
            "model_empty"
            if self.model.experience_count == 0
            else "no_known_path"
        )
        return ModelPlan(
            False, start, goal, (), (start,), math.inf, expanded, reason
        )


@dataclass(frozen=True, slots=True)
class ExplorationTrace:
    policy: str
    world_id: str
    budget: int
    steps: int
    unique_transition_pairs: int
    discovered_states: int
    pair_count_curve: tuple[int, ...]
    trajectory: tuple[str, ...]
    actions: tuple[str, ...]


class ActiveTransitionExplorer:
    """Choose observations using only the current learned model.

    The policy tries unobserved actions in its current state, navigates through
    known transitions toward discovered states with unobserved actions, and
    falls back to the least-sampled local action.  It never reads the world's
    transition table or complete state list.
    """

    def __init__(
        self,
        model: TabularTransitionModel,
        action_space: Sequence[str],
    ) -> None:
        actions = tuple(
            sorted(require_text(action, "action") for action in action_space)
        )
        if not actions or len(set(actions)) != len(actions):
            raise ValidationError("action_space must contain unique actions")
        self.model = model
        self.action_space = actions

    def choose_action(self, state: str) -> str:
        observed_here = frozenset(self.model.actions_for(state))
        unobserved_here = [
            action for action in self.action_space if action not in observed_here
        ]
        if unobserved_here:
            return unobserved_here[0]

        candidates: list[tuple[int, str, str]] = []
        planner = ModelBasedPlanner(self.model)
        for frontier in self.model.known_states:
            if len(self.model.actions_for(frontier)) >= len(self.action_space):
                continue
            plan = planner.plan(state, frontier)
            if plan.found and plan.actions:
                candidates.append((len(plan.actions), frontier, plan.actions[0]))
        if candidates:
            return min(candidates)[2]

        return min(
            self.action_space,
            key=lambda action: (
                self.model.evidence_count_for(state, action),
                action,
            ),
        )

    def explore(
        self,
        environment: OpaqueGraphWorld,
        *,
        start: str,
        budget: int,
    ) -> ExplorationTrace:
        if budget < 1:
            raise ValidationError("exploration budget must be positive")
        observation = environment.reset_exploration(
            start=start,
            max_steps=budget,
        )
        trajectory = [observation.state]
        actions: list[str] = []
        curve: list[int] = []
        while not observation.truncated:
            action = self.choose_action(observation.state)
            result = environment.step(action)
            self.model.observe(result.experience)
            observation = result.observation
            trajectory.append(observation.state)
            actions.append(action)
            curve.append(self.model.known_transition_pair_count)
        return ExplorationTrace(
            policy="active_frontier",
            world_id=environment.world_id,
            budget=budget,
            steps=len(actions),
            unique_transition_pairs=self.model.known_transition_pair_count,
            discovered_states=len(self.model.known_states),
            pair_count_curve=tuple(curve),
            trajectory=tuple(trajectory),
            actions=tuple(actions),
        )


def collect_controlled_transition_census(
    environment: CausalEnvironment,
    model: TabularTransitionModel,
) -> tuple[TransitionExperience, ...]:
    """Observe each state-action pair once under an explicit lab protocol.

    This is exhaustive system identification, not autonomous exploration.  The
    benchmark reserves start-goal tasks, not transition pairs.
    """

    experiences: list[TransitionExperience] = []
    states = environment.states
    for state_index, state in enumerate(states):
        goal = states[(state_index + 1) % len(states)]
        for action in environment.action_space:
            environment.reset(start=state, goal=goal, max_steps=1)
            result = environment.step(action)
            model.observe(result.experience)
            experiences.append(result.experience)
    return tuple(experiences)


def snapshot_digest(model: TabularTransitionModel) -> str:
    """Stable non-cryptographic diagnostic label for tests and reports."""

    # This is intentionally not an authorization or integrity primitive.
    raw = model.to_snapshot().encode("utf-8")
    value = 1469598103934665603
    for byte in raw:
        value ^= byte
        value = (value * 1099511628211) & ((1 << 64) - 1)
    return f"fnv1a64:{value:016x}"


def snapshot_as_mapping(model: TabularTransitionModel) -> Mapping[str, Any]:
    """Return a defensive decoded view for diagnostics."""

    parsed = json.loads(model.to_snapshot())
    if not isinstance(parsed, dict):
        raise RuntimeError("canonical snapshot was not an object")
    return parsed
