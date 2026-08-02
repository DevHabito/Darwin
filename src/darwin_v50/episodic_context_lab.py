"""Partially observed episodic action memory for Darwin H50-L9."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import random
from typing import Any, Sequence

from .models import ValidationError, canonical_json, parse_json


EPISODE_COUNT = 18
STEPS_PER_EPISODE = 24
ACTION_COUNT = 3
CUE_COUNT = 4
EPISODIC_SCHEDULE_XOR_MASK = 0xC0917
EPISODIC_TRACE_XOR_MASK = 0x51A7D

CONTEXT_LABELS = ("A", "B", "C", "D", "E")
EVEN_PARITY_CODES = (
    (False, False, False, False),
    (False, False, True, True),
    (False, True, False, True),
    (False, True, True, False),
    (True, False, False, True),
    (True, False, True, False),
    (True, True, False, False),
    (True, True, True, True),
)
EPISODIC_FAMILIES = (
    "exact_recurrence",
    "cue_drift",
    "reward_drift",
    "novelty",
)
EPISODE_LABELS = {
    "exact_recurrence": tuple("ABCABCACBABCABCACB"),
    "cue_drift": tuple("ABCABCACBABCABCACB"),
    "reward_drift": tuple("ABCABCACBABCABCACB"),
    "novelty": tuple("ABCADBECDAEBCDEABC"),
}


def _validate_probability(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < value < 1.0
    ):
        raise ValidationError(f"{field} must be within (0, 1)")
    return float(value)


def forced_action(episode_index: int, step_index: int) -> int | None:
    if (
        isinstance(episode_index, bool)
        or not isinstance(episode_index, int)
        or episode_index < 1
        or isinstance(step_index, bool)
        or not isinstance(step_index, int)
        or not 1 <= step_index <= STEPS_PER_EPISODE
    ):
        raise ValidationError("episode and step indices are invalid")
    if step_index <= ACTION_COUNT:
        return step_index - 1
    if step_index in {10, 20}:
        return (episode_index + step_index // 10) % ACTION_COUNT
    return None


@dataclass(frozen=True, slots=True)
class ContextDefinition:
    label: str
    code: tuple[bool, bool, bool, bool]
    base_reward_probabilities: tuple[float, float, float]

    def __post_init__(self) -> None:
        if self.label not in CONTEXT_LABELS:
            raise ValidationError("context label is invalid")
        if self.code not in EVEN_PARITY_CODES:
            raise ValidationError("context code is invalid")
        if (
            not isinstance(self.base_reward_probabilities, tuple)
            or len(self.base_reward_probabilities) != ACTION_COUNT
        ):
            raise ValidationError("context rewards are invalid")
        for index, value in enumerate(self.base_reward_probabilities):
            _validate_probability(value, f"reward[{index}]")
        if sorted(self.base_reward_probabilities) != [0.15, 0.5, 0.85]:
            raise ValidationError("context rewards must permute registered levels")

    @property
    def cue_probabilities(self) -> tuple[float, float, float, float]:
        return tuple(0.9 if bit else 0.1 for bit in self.code)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class EpisodicWorldSpecification:
    seed: int
    family: str
    contexts: tuple[
        ContextDefinition,
        ContextDefinition,
        ContextDefinition,
        ContextDefinition,
        ContextDefinition,
    ]
    episode_labels: tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
    ]

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("world seed must be an integer")
        if self.family != EPISODIC_FAMILIES[self.seed % 4]:
            raise ValidationError("world family does not match seed")
        if self.episode_labels != EPISODE_LABELS[self.family]:
            raise ValidationError("episode labels do not match family")
        if tuple(item.label for item in self.contexts) != CONTEXT_LABELS:
            raise ValidationError("world contexts must be ordered A through E")
        codes = tuple(item.code for item in self.contexts)
        if len(set(codes)) != len(codes):
            raise ValidationError("context codes must be unique")
        if any(
            sum(left != right for left, right in zip(a, b, strict=True)) < 2
            for index, a in enumerate(codes)
            for b in codes[index + 1 :]
        ):
            raise ValidationError("context codes must be separated")

    @classmethod
    def from_seed(cls, seed: int) -> "EpisodicWorldSpecification":
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("world seed must be an integer")
        rng = random.Random(seed ^ EPISODIC_SCHEDULE_XOR_MASK)
        codes = list(EVEN_PARITY_CODES)
        rng.shuffle(codes)
        contexts: list[ContextDefinition] = []
        for label, code in zip(CONTEXT_LABELS, codes[:5], strict=True):
            rewards = [0.85, 0.50, 0.15]
            rng.shuffle(rewards)
            contexts.append(
                ContextDefinition(
                    label=label,
                    code=code,
                    base_reward_probabilities=tuple(rewards),  # type: ignore[arg-type]
                )
            )
        family = EPISODIC_FAMILIES[seed % 4]
        return cls(
            seed=seed,
            family=family,
            contexts=tuple(contexts),  # type: ignore[arg-type]
            episode_labels=EPISODE_LABELS[family],
        )

    def context(self, label: str) -> ContextDefinition:
        if label not in CONTEXT_LABELS:
            raise ValidationError("unknown context label")
        return self.contexts[CONTEXT_LABELS.index(label)]

    @property
    def recurrence_episode_indices(self) -> tuple[int, ...]:
        seen: set[str] = set()
        result: list[int] = []
        for index, label in enumerate(self.episode_labels, start=1):
            if label in seen:
                result.append(index)
            seen.add(label)
        return tuple(result)

    @property
    def novelty_episode_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, label in enumerate(self.episode_labels, start=1)
            if label in {"D", "E"}
            and label not in self.episode_labels[: index - 1]
        )


@dataclass(frozen=True, slots=True)
class EpisodicStep:
    episode_index: int
    step_index: int
    context_label: str
    cues: tuple[bool, bool, bool, bool]
    potential_outcomes: tuple[bool, bool, bool]
    reward_probabilities: tuple[float, float, float]

    def __post_init__(self) -> None:
        if (
            isinstance(self.episode_index, bool)
            or not isinstance(self.episode_index, int)
            or not 1 <= self.episode_index <= EPISODE_COUNT
            or isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or not 1 <= self.step_index <= STEPS_PER_EPISODE
        ):
            raise ValidationError("episodic step index is invalid")
        if self.context_label not in CONTEXT_LABELS:
            raise ValidationError("episodic context label is invalid")
        if (
            not isinstance(self.cues, tuple)
            or len(self.cues) != CUE_COUNT
            or any(not isinstance(value, bool) for value in self.cues)
        ):
            raise ValidationError("episodic cues must be four booleans")
        if (
            not isinstance(self.potential_outcomes, tuple)
            or len(self.potential_outcomes) != ACTION_COUNT
            or any(
                not isinstance(value, bool)
                for value in self.potential_outcomes
            )
        ):
            raise ValidationError("potential outcomes must be three booleans")
        if (
            not isinstance(self.reward_probabilities, tuple)
            or len(self.reward_probabilities) != ACTION_COUNT
        ):
            raise ValidationError(
                "reward probabilities must contain three values"
            )
        for index, value in enumerate(self.reward_probabilities):
            _validate_probability(value, f"reward_probability[{index}]")


class EpisodicContextWorld:
    """Precomputed paired world; policies reveal only their chosen outcome."""

    def __init__(self, seed: int) -> None:
        self.specification = EpisodicWorldSpecification.from_seed(seed)
        rng = random.Random(seed ^ EPISODIC_TRACE_XOR_MASK)
        occurrence_counts = {label: 0 for label in CONTEXT_LABELS}
        steps: list[EpisodicStep] = []
        for episode_index, label in enumerate(
            self.specification.episode_labels,
            start=1,
        ):
            context = self.specification.context(label)
            occurrence = occurrence_counts[label]
            occurrence_counts[label] += 1
            fidelity = 0.9
            if self.specification.family == "cue_drift" and occurrence > 0:
                fidelity = 0.85 if occurrence == 1 else 0.80
            rewards = context.base_reward_probabilities
            if (
                self.specification.family == "reward_drift"
                and occurrence > 0
            ):
                offsets = tuple(
                    rng.choice((-0.05, 0.0, 0.05))
                    for _ in range(ACTION_COUNT)
                )
                rewards = tuple(
                    value + offset
                    for value, offset in zip(
                        rewards,
                        offsets,
                        strict=True,
                    )
                )  # type: ignore[assignment]
            for step_index in range(1, STEPS_PER_EPISODE + 1):
                cues = tuple(
                    (
                        rng.random() < fidelity
                        if bit
                        else rng.random() >= fidelity
                    )
                    for bit in context.code
                )
                outcomes = tuple(
                    rng.random() < probability
                    for probability in rewards
                )
                steps.append(
                    EpisodicStep(
                        episode_index=episode_index,
                        step_index=step_index,
                        context_label=label,
                        cues=cues,  # type: ignore[arg-type]
                        potential_outcomes=outcomes,  # type: ignore[arg-type]
                        reward_probabilities=rewards,
                    )
                )
        self._steps = tuple(steps)

    @property
    def steps(self) -> tuple[EpisodicStep, ...]:
        return self._steps

    def episode_steps(self, episode_index: int) -> tuple[EpisodicStep, ...]:
        if (
            isinstance(episode_index, bool)
            or not isinstance(episode_index, int)
            or not 1 <= episode_index <= EPISODE_COUNT
        ):
            raise ValidationError("episode index is invalid")
        start = (episode_index - 1) * STEPS_PER_EPISODE
        return self._steps[start : start + STEPS_PER_EPISODE]


@dataclass(frozen=True, slots=True)
class EpisodicInteraction:
    episode_index: int
    step_index: int
    cues: tuple[bool, bool, bool, bool]
    action: int
    outcome: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.episode_index, bool)
            or not isinstance(self.episode_index, int)
            or self.episode_index < 1
            or isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or not 1 <= self.step_index <= STEPS_PER_EPISODE
            or not isinstance(self.cues, tuple)
            or len(self.cues) != CUE_COUNT
            or any(not isinstance(value, bool) for value in self.cues)
        ):
            raise ValidationError("interaction indices or cues are invalid")
        if (
            isinstance(self.action, bool)
            or not isinstance(self.action, int)
            or not 0 <= self.action < ACTION_COUNT
        ):
            raise ValidationError("interaction action is invalid")
        if not isinstance(self.outcome, bool):
            raise ValidationError("interaction outcome must be boolean")


@dataclass(frozen=True, slots=True)
class EpisodicPrototype:
    prototype_id: int
    cue_successes: tuple[int, int, int, int]
    cue_count: int
    action_successes: tuple[int, int, int]
    action_failures: tuple[int, int, int]
    consolidations: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.prototype_id, bool)
            or not isinstance(self.prototype_id, int)
            or self.prototype_id < 1
            or isinstance(self.cue_count, bool)
            or not isinstance(self.cue_count, int)
            or self.cue_count < 1
            or isinstance(self.consolidations, bool)
            or not isinstance(self.consolidations, int)
            or self.consolidations < 1
        ):
            raise ValidationError("prototype scalar state is invalid")
        if (
            len(self.cue_successes) != CUE_COUNT
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= self.cue_count
                for value in self.cue_successes
            )
        ):
            raise ValidationError("prototype cue counts are invalid")
        for field, values in (
            ("action_successes", self.action_successes),
            ("action_failures", self.action_failures),
        ):
            if (
                len(values) != ACTION_COUNT
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    for value in values
                )
            ):
                raise ValidationError(f"prototype {field} are invalid")
        if (
            sum(self.action_successes) + sum(self.action_failures)
            != self.cue_count
        ):
            raise ValidationError(
                "prototype action counts must match its cue count"
            )

    @property
    def cue_means(self) -> tuple[float, float, float, float]:
        return tuple(
            value / self.cue_count for value in self.cue_successes
        )  # type: ignore[return-value]

    def action_probability(self, action: int) -> float:
        return (
            1.0 + self.action_successes[action]
        ) / (
            2.0
            + self.action_successes[action]
            + self.action_failures[action]
        )


@dataclass(frozen=True, slots=True)
class EpisodeRetrievalDecision:
    episode_index: int
    step_index: int
    retrieved_prototype_id: int | None
    distance: float | None
    current_cue_means: tuple[float, float, float, float]
    prototype_cue_means: tuple[float, float, float, float] | None
    abstained: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.episode_index, bool)
            or not isinstance(self.episode_index, int)
            or self.episode_index < 1
            or isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or not 1 <= self.step_index <= STEPS_PER_EPISODE
            or not isinstance(self.abstained, bool)
        ):
            raise ValidationError("retrieval indices or state are invalid")
        if (
            not isinstance(self.current_cue_means, tuple)
            or len(self.current_cue_means) != CUE_COUNT
        ):
            raise ValidationError("current cue means are invalid")
        for value in self.current_cue_means:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError("current cue mean is invalid")
        if self.retrieved_prototype_id is None:
            if (
                self.distance is not None
                or self.prototype_cue_means is not None
                or not self.abstained
            ):
                raise ValidationError("abstention state is inconsistent")
        else:
            if (
                isinstance(self.retrieved_prototype_id, bool)
                or not isinstance(self.retrieved_prototype_id, int)
                or self.retrieved_prototype_id < 1
                or isinstance(self.distance, bool)
                or not isinstance(self.distance, (int, float))
                or not math.isfinite(self.distance)
                or self.distance < 0.0
                or self.prototype_cue_means is None
                or self.abstained
            ):
                raise ValidationError("retrieval state is inconsistent")
            if (
                not isinstance(self.prototype_cue_means, tuple)
                or len(self.prototype_cue_means) != CUE_COUNT
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0.0 <= value <= 1.0
                    for value in self.prototype_cue_means
                )
            ):
                raise ValidationError("prototype cue means are invalid")


class EpisodicActionMemory:
    """Prototype retrieval plus action values observed in past episodes."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        minimum_cues: int = 6,
        match_tolerance: float = 0.24,
        memory_enabled: bool = True,
    ) -> None:
        if (
            isinstance(minimum_cues, bool)
            or not isinstance(minimum_cues, int)
            or not 1 <= minimum_cues <= STEPS_PER_EPISODE
        ):
            raise ValidationError("minimum_cues is invalid")
        if (
            isinstance(match_tolerance, bool)
            or not isinstance(match_tolerance, (int, float))
            or not math.isfinite(match_tolerance)
            or not 0.0 < match_tolerance < 1.0
        ):
            raise ValidationError("match_tolerance must be within (0, 1)")
        if not isinstance(memory_enabled, bool):
            raise ValidationError("memory_enabled must be boolean")
        self.minimum_cues = minimum_cues
        self.match_tolerance = float(match_tolerance)
        self.memory_enabled = memory_enabled
        self._archive: list[EpisodicInteraction] = []
        self._prototypes: list[EpisodicPrototype] = []
        self._retrieval_decisions: list[EpisodeRetrievalDecision] = []
        self._current_episode: int | None = None
        self._next_step = 1
        self._cue_successes = [0] * CUE_COUNT
        self._cue_count = 0
        self._action_successes = [0] * ACTION_COUNT
        self._action_failures = [0] * ACTION_COUNT
        self._active_prototype_id: int | None = None
        self._pending_cues: tuple[bool, bool, bool, bool] | None = None
        self._pending_action: int | None = None

    @property
    def archive(self) -> tuple[EpisodicInteraction, ...]:
        return tuple(self._archive)

    @property
    def prototypes(self) -> tuple[EpisodicPrototype, ...]:
        return tuple(self._prototypes)

    @property
    def retrieval_decisions(self) -> tuple[EpisodeRetrievalDecision, ...]:
        return tuple(self._retrieval_decisions)

    @property
    def current_episode(self) -> int | None:
        return self._current_episode

    @property
    def next_step(self) -> int:
        return self._next_step

    @property
    def active_prototype_id(self) -> int | None:
        return self._active_prototype_id

    def begin_episode(self, episode_index: int) -> None:
        if (
            isinstance(episode_index, bool)
            or not isinstance(episode_index, int)
            or episode_index < 1
        ):
            raise ValidationError("episode index must be a positive integer")
        expected = (
            1
            if not self._archive
            else self._archive[-1].episode_index
            + int(self._archive[-1].step_index == STEPS_PER_EPISODE)
        )
        if self._current_episode is not None:
            raise ValidationError("an episode is already open")
        if episode_index != expected:
            raise ValidationError(
                f"expected episode index {expected}, got {episode_index}"
            )
        self._current_episode = episode_index
        self._next_step = 1
        self._cue_successes = [0] * CUE_COUNT
        self._cue_count = 0
        self._action_successes = [0] * ACTION_COUNT
        self._action_failures = [0] * ACTION_COUNT
        self._active_prototype_id = None
        self._pending_cues = None
        self._pending_action = None

    def _current_cue_means(self) -> tuple[float, float, float, float]:
        if self._cue_count < 1:
            raise ValidationError("cue means require evidence")
        return tuple(
            value / self._cue_count for value in self._cue_successes
        )  # type: ignore[return-value]

    @staticmethod
    def _distance(
        left: Sequence[float],
        right: Sequence[float],
    ) -> float:
        return sum(
            abs(a - b) for a, b in zip(left, right, strict=True)
        ) / CUE_COUNT

    def _nearest_prototype(
        self,
        cue_means: Sequence[float],
    ) -> tuple[EpisodicPrototype | None, float | None]:
        if not self._prototypes:
            return None, None
        prototype = min(
            self._prototypes,
            key=lambda item: (
                self._distance(cue_means, item.cue_means),
                item.prototype_id,
            ),
        )
        distance = self._distance(cue_means, prototype.cue_means)
        if distance > self.match_tolerance:
            return None, None
        return prototype, distance

    def observe_cues(self, cues: tuple[bool, bool, bool, bool]) -> None:
        if self._current_episode is None:
            raise ValidationError("begin_episode must precede cues")
        if self._next_step > STEPS_PER_EPISODE:
            raise ValidationError("episode has no remaining steps")
        if self._pending_cues is not None or self._pending_action is not None:
            raise ValidationError("previous step is incomplete")
        if (
            not isinstance(cues, tuple)
            or len(cues) != CUE_COUNT
            or any(not isinstance(value, bool) for value in cues)
        ):
            raise ValidationError("cues must be four booleans")
        self._pending_cues = cues
        self._cue_count += 1
        for index, value in enumerate(cues):
            self._cue_successes[index] += int(value)
        if (
            self.memory_enabled
            and self._cue_count == self.minimum_cues
        ):
            means = self._current_cue_means()
            prototype, distance = self._nearest_prototype(means)
            self._active_prototype_id = (
                prototype.prototype_id if prototype is not None else None
            )
            self._retrieval_decisions.append(
                EpisodeRetrievalDecision(
                    episode_index=self._current_episode,
                    step_index=self._next_step,
                    retrieved_prototype_id=(
                        prototype.prototype_id
                        if prototype is not None
                        else None
                    ),
                    distance=distance,
                    current_cue_means=means,
                    prototype_cue_means=(
                        prototype.cue_means
                        if prototype is not None
                        else None
                    ),
                    abstained=prototype is None,
                )
            )

    def _action_probability(self, action: int) -> float:
        successes = self._action_successes[action]
        failures = self._action_failures[action]
        if self._active_prototype_id is not None and self.memory_enabled:
            prototype = self._prototypes[self._active_prototype_id - 1]
            successes += prototype.action_successes[action]
            failures += prototype.action_failures[action]
        return (1.0 + successes) / (2.0 + successes + failures)

    def action_probabilities(self) -> tuple[float, float, float]:
        return tuple(
            self._action_probability(action)
            for action in range(ACTION_COUNT)
        )  # type: ignore[return-value]

    def choose_action(self) -> int:
        if self._current_episode is None or self._pending_cues is None:
            raise ValidationError("cues must precede action")
        if self._pending_action is not None:
            return self._pending_action
        forced = forced_action(self._current_episode, self._next_step)
        if forced is not None:
            action = forced
        else:
            probabilities = self.action_probabilities()
            action = max(
                range(ACTION_COUNT),
                key=lambda index: (probabilities[index], -index),
            )
        self._pending_action = action
        return action

    def observe_outcome(self, action: int, outcome: bool) -> None:
        if (
            self._current_episode is None
            or self._pending_cues is None
            or self._pending_action is None
        ):
            raise ValidationError("action must precede outcome")
        if action != self._pending_action:
            raise ValidationError("outcome action does not match decision")
        if not isinstance(outcome, bool):
            raise ValidationError("outcome must be boolean")
        self._archive.append(
            EpisodicInteraction(
                episode_index=self._current_episode,
                step_index=self._next_step,
                cues=self._pending_cues,
                action=action,
                outcome=outcome,
            )
        )
        self._action_successes[action] += int(outcome)
        self._action_failures[action] += int(not outcome)
        self._next_step += 1
        self._pending_cues = None
        self._pending_action = None

    def _consolidate_episode(self) -> None:
        means = self._current_cue_means()
        prototype, _ = self._nearest_prototype(means)
        if prototype is None:
            self._prototypes.append(
                EpisodicPrototype(
                    prototype_id=len(self._prototypes) + 1,
                    cue_successes=tuple(self._cue_successes),  # type: ignore[arg-type]
                    cue_count=self._cue_count,
                    action_successes=tuple(self._action_successes),  # type: ignore[arg-type]
                    action_failures=tuple(self._action_failures),  # type: ignore[arg-type]
                    consolidations=1,
                )
            )
            return
        updated = replace(
            prototype,
            cue_successes=tuple(
                left + right
                for left, right in zip(
                    prototype.cue_successes,
                    self._cue_successes,
                    strict=True,
                )
            ),  # type: ignore[arg-type]
            cue_count=prototype.cue_count + self._cue_count,
            action_successes=tuple(
                left + right
                for left, right in zip(
                    prototype.action_successes,
                    self._action_successes,
                    strict=True,
                )
            ),  # type: ignore[arg-type]
            action_failures=tuple(
                left + right
                for left, right in zip(
                    prototype.action_failures,
                    self._action_failures,
                    strict=True,
                )
            ),  # type: ignore[arg-type]
            consolidations=prototype.consolidations + 1,
        )
        self._prototypes[prototype.prototype_id - 1] = updated

    def end_episode(self) -> None:
        if self._current_episode is None:
            raise ValidationError("no episode is open")
        if (
            self._next_step != STEPS_PER_EPISODE + 1
            or self._pending_cues is not None
            or self._pending_action is not None
        ):
            raise ValidationError("episode is incomplete")
        if self.memory_enabled:
            self._consolidate_episode()
        self._current_episode = None
        self._next_step = 1
        self._active_prototype_id = None

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "minimum_cues": self.minimum_cues,
                "match_tolerance": self.match_tolerance,
                "memory_enabled": self.memory_enabled,
                "archive": [
                    {
                        "episode_index": item.episode_index,
                        "step_index": item.step_index,
                        "cues": list(item.cues),
                        "action": item.action,
                        "outcome": item.outcome,
                    }
                    for item in self._archive
                ],
                "prototypes": [
                    {
                        "prototype_id": item.prototype_id,
                        "cue_successes": list(item.cue_successes),
                        "cue_count": item.cue_count,
                        "action_successes": list(item.action_successes),
                        "action_failures": list(item.action_failures),
                        "consolidations": item.consolidations,
                    }
                    for item in self._prototypes
                ],
                "retrieval_decisions": [
                    {
                        "episode_index": item.episode_index,
                        "step_index": item.step_index,
                        "retrieved_prototype_id": (
                            item.retrieved_prototype_id
                        ),
                        "distance": item.distance,
                        "current_cue_means": list(item.current_cue_means),
                        "prototype_cue_means": (
                            list(item.prototype_cue_means)
                            if item.prototype_cue_means is not None
                            else None
                        ),
                        "abstained": item.abstained,
                    }
                    for item in self._retrieval_decisions
                ],
                "current_episode": self._current_episode,
                "next_step": self._next_step,
                "cue_successes": list(self._cue_successes),
                "cue_count": self._cue_count,
                "action_successes": list(self._action_successes),
                "action_failures": list(self._action_failures),
                "active_prototype_id": self._active_prototype_id,
                "pending_cues": (
                    list(self._pending_cues)
                    if self._pending_cues is not None
                    else None
                ),
                "pending_action": self._pending_action,
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "EpisodicActionMemory":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported episodic-memory snapshot")
        try:
            model = cls(
                minimum_cues=parsed["minimum_cues"],
                match_tolerance=parsed["match_tolerance"],
                memory_enabled=parsed["memory_enabled"],
            )
            archive_rows = parsed["archive"]
            stored_current_episode = parsed["current_episode"]
            pending_cues = parsed["pending_cues"]
            pending_action = parsed["pending_action"]
        except KeyError as error:
            raise ValidationError(
                f"episodic snapshot missing field: {error.args[0]}"
            ) from error
        if not isinstance(archive_rows, list):
            raise ValidationError("episodic archive must be a list")
        for row in archive_rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid episodic interaction")
            try:
                episode_index = row["episode_index"]
                step_index = row["step_index"]
                cues_raw = row["cues"]
                action = row["action"]
                outcome = row["outcome"]
            except KeyError as error:
                raise ValidationError(
                    f"interaction missing field: {error.args[0]}"
                ) from error
            if not isinstance(cues_raw, list):
                raise ValidationError("interaction cues must be a list")
            if model.current_episode is None:
                model.begin_episode(episode_index)
            if model.current_episode != episode_index:
                raise ValidationError("archive episode order is invalid")
            if model.next_step != step_index:
                raise ValidationError("archive step order is invalid")
            model.observe_cues(tuple(cues_raw))  # type: ignore[arg-type]
            predicted_action = model.choose_action()
            if predicted_action != action:
                raise ValidationError(
                    "archived action does not match causal replay"
                )
            model.observe_outcome(action, outcome)
            if step_index == STEPS_PER_EPISODE:
                model.end_episode()
        if stored_current_episode is not None:
            if model.current_episode is None:
                model.begin_episode(stored_current_episode)
            elif model.current_episode != stored_current_episode:
                raise ValidationError("stored open episode is inconsistent")
        elif model.current_episode is not None:
            raise ValidationError("archive ends with an unclosed episode")
        if pending_cues is not None:
            if not isinstance(pending_cues, list):
                raise ValidationError("pending cues must be a list")
            model.observe_cues(tuple(pending_cues))  # type: ignore[arg-type]
        if pending_action is not None:
            if model.choose_action() != pending_action:
                raise ValidationError("pending action does not match replay")
        if canonical_json(parsed) != model.to_snapshot():
            raise ValidationError(
                "episodic snapshot does not match replayed archive"
            )
        return model
