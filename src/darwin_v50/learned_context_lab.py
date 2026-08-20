"""Learned context order, reward model, and planning for Darwin H50-L11.

This is a small tabular laboratory.  It does not implement a general context
tree, latent representation learning, general intelligence, or consciousness.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
import random
from typing import Any, Iterable, Protocol, Sequence, TypeAlias

from .models import ValidationError, canonical_json, parse_json, require_text


CONTEXT_ACTIONS = ("amber", "violet")
MAX_CONTEXT_ORDER = 5
CONTEXT_ORDER_CANDIDATES = (1, 2, 3, 4, 5)
TRUE_CONTEXT_ORDERS = (2, 3, 4, 5)
CONTEXT_STRUCTURE_XOR_MASK = 0xB41C7
CONTEXT_TRANSITION_XOR_MASK = 0x71A35
CONTEXT_REWARD_XOR_MASK = 0xC4E21
TRANSITION_FIDELITY = 0.85
TARGET_REWARD_PROBABILITY = 0.75
TARGET_OTHER_ACTION_PROBABILITY = 0.10
BACKGROUND_REWARD_PROBABILITY = 0.02
CONTEXT_DISCOUNT = 0.95

FullHistory: TypeAlias = tuple[bool, bool, bool, bool, bool]
ContextState: TypeAlias = tuple[bool, ...]


def _validate_order(value: object, field: str = "order") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in CONTEXT_ORDER_CANDIDATES
    ):
        raise ValidationError(f"{field} is invalid")
    return value


def _validate_probability(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < value < 1.0
    ):
        raise ValidationError(f"{field} must be within (0, 1)")
    return float(value)


def validate_full_history(
    value: object,
    field: str = "history",
) -> FullHistory:
    if (
        not isinstance(value, tuple)
        or len(value) != MAX_CONTEXT_ORDER
        or any(not isinstance(bit, bool) for bit in value)
    ):
        raise ValidationError(
            f"{field} must contain five boolean observations"
        )
    return value  # type: ignore[return-value]


def validate_context(
    value: object,
    *,
    order: int,
    field: str = "context",
) -> ContextState:
    if (
        isinstance(order, bool)
        or not isinstance(order, int)
        or order not in CONTEXT_ORDER_CANDIDATES
    ):
        raise ValidationError("context order is invalid")
    if (
        not isinstance(value, tuple)
        or len(value) != order
        or any(not isinstance(bit, bool) for bit in value)
    ):
        raise ValidationError(
            f"{field} must contain {order} boolean observations"
        )
    return value


def history_suffix(
    history: FullHistory,
    order: int,
) -> ContextState:
    validate_full_history(history)
    _validate_order(order, "context order")
    return history[-order:]


def append_observation(
    history: FullHistory,
    observation: bool,
) -> FullHistory:
    validate_full_history(history)
    if not isinstance(observation, bool):
        raise ValidationError("next observation must be boolean")
    return history[1:] + (observation,)


def all_contexts(order: int) -> tuple[ContextState, ...]:
    _validate_order(order, "context order")
    return tuple(product((False, True), repeat=order))


def _action_index(action: str) -> int:
    if action not in CONTEXT_ACTIONS:
        raise ValidationError("unknown context action")
    return CONTEXT_ACTIONS.index(action)


@dataclass(frozen=True, slots=True)
class ContextDynamicsRule:
    context: ContextState
    preferred_next_bits: tuple[bool, bool]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, tuple)
            or not 1 <= len(self.context) <= MAX_CONTEXT_ORDER
            or any(not isinstance(bit, bool) for bit in self.context)
        ):
            raise ValidationError("dynamics context is invalid")
        if (
            not isinstance(self.preferred_next_bits, tuple)
            or len(self.preferred_next_bits) != len(CONTEXT_ACTIONS)
            or any(
                not isinstance(bit, bool)
                for bit in self.preferred_next_bits
            )
            or self.preferred_next_bits[0]
            == self.preferred_next_bits[1]
        ):
            raise ValidationError(
                "actions must prefer complementary next bits"
            )

    def transition_probability(self, action: str) -> float:
        preferred = self.preferred_next_bits[_action_index(action)]
        return (
            TRANSITION_FIDELITY
            if preferred
            else 1.0 - TRANSITION_FIDELITY
        )


@dataclass(frozen=True, slots=True)
class RewardContext:
    context: ContextState
    rewarded_action: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, tuple)
            or not 1 <= len(self.context) <= MAX_CONTEXT_ORDER
            or any(not isinstance(bit, bool) for bit in self.context)
        ):
            raise ValidationError("reward context is invalid")
        _action_index(self.rewarded_action)


@dataclass(frozen=True, slots=True)
class LearnedContextWorldSpecification:
    seed: int
    true_order: int
    dynamics: tuple[ContextDynamicsRule, ...]
    reward_contexts: tuple[RewardContext, RewardContext]

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("context world seed must be an integer")
        expected_order = TRUE_CONTEXT_ORDERS[self.seed % 4]
        if self.true_order != expected_order:
            raise ValidationError("true order does not match seed family")
        expected_contexts = all_contexts(self.true_order)
        if (
            not isinstance(self.dynamics, tuple)
            or tuple(item.context for item in self.dynamics)
            != expected_contexts
        ):
            raise ValidationError(
                "dynamics must cover every ordered true context"
            )
        if (
            not isinstance(self.reward_contexts, tuple)
            or len(self.reward_contexts) != 2
            or len(
                {item.context for item in self.reward_contexts}
            )
            != 2
            or any(
                len(item.context) != self.true_order
                for item in self.reward_contexts
            )
        ):
            raise ValidationError(
                "world must contain two distinct reward contexts"
            )

    @classmethod
    def from_seed(
        cls,
        seed: int,
    ) -> "LearnedContextWorldSpecification":
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("context world seed must be an integer")
        true_order = TRUE_CONTEXT_ORDERS[seed % 4]
        rng = random.Random(seed ^ CONTEXT_STRUCTURE_XOR_MASK)
        contexts = all_contexts(true_order)
        dynamics = tuple(
            ContextDynamicsRule(
                context=context,
                preferred_next_bits=(
                    preferred := bool(rng.getrandbits(1)),
                    not preferred,
                ),
            )
            for context in contexts
        )
        target_contexts = tuple(rng.sample(list(contexts), 2))
        reward_contexts = tuple(
            RewardContext(
                context=context,
                rewarded_action=rng.choice(CONTEXT_ACTIONS),
            )
            for context in target_contexts
        )
        return cls(
            seed=seed,
            true_order=true_order,
            dynamics=dynamics,
            reward_contexts=reward_contexts,  # type: ignore[arg-type]
        )

    def _context(self, history: FullHistory) -> ContextState:
        return history_suffix(history, self.true_order)

    def dynamics_rule(
        self,
        history: FullHistory,
    ) -> ContextDynamicsRule:
        context = self._context(history)
        index = sum(
            int(bit) << (self.true_order - position - 1)
            for position, bit in enumerate(context)
        )
        return self.dynamics[index]

    def transition_probability(
        self,
        history: FullHistory,
        action: str,
    ) -> float:
        return self.dynamics_rule(history).transition_probability(action)

    def reward_probability(
        self,
        history: FullHistory,
        action: str,
    ) -> float:
        _action_index(action)
        context = self._context(history)
        for target in self.reward_contexts:
            if target.context == context:
                return (
                    TARGET_REWARD_PROBABILITY
                    if action == target.rewarded_action
                    else TARGET_OTHER_ACTION_PROBABILITY
                )
        return BACKGROUND_REWARD_PROBABILITY


@dataclass(frozen=True, slots=True)
class LearnedContextObservation:
    world_id: str
    episode_id: str
    observation: bool
    step_index: int
    truncated: bool
    priming_history: FullHistory | None

    def __post_init__(self) -> None:
        require_text(self.world_id, "world_id")
        require_text(self.episode_id, "episode_id")
        if not isinstance(self.observation, bool):
            raise ValidationError("context observation must be boolean")
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
            or not isinstance(self.truncated, bool)
        ):
            raise ValidationError("context observation state is invalid")
        if self.priming_history is not None:
            validate_full_history(
                self.priming_history,
                "priming_history",
            )
            if (
                self.step_index != 0
                or self.priming_history[-1] != self.observation
            ):
                raise ValidationError(
                    "priming history is inconsistent"
                )
        elif self.step_index == 0:
            raise ValidationError(
                "initial observation requires priming history"
            )
        if self.step_index == 0 and self.truncated:
            raise ValidationError(
                "initial observation cannot be truncated"
            )


@dataclass(frozen=True, slots=True)
class LearnedContextStep:
    observation: LearnedContextObservation
    action: str
    reward: bool

    def __post_init__(self) -> None:
        _action_index(self.action)
        if not isinstance(self.reward, bool):
            raise ValidationError("observed reward must be boolean")


class LearnedContextWorld:
    """Stochastic process revealing one chosen transition and reward."""

    def __init__(self, seed: int) -> None:
        self.specification = LearnedContextWorldSpecification.from_seed(
            seed
        )
        self.world_id = f"learned-context-{seed}"
        self._episode_counter = 0
        self._episode_id = ""
        self._history: FullHistory | None = None
        self._step_index = 0
        self._max_steps = 0
        self._transition_uniforms: tuple[
            tuple[float, float], ...
        ] = ()
        self._reward_uniforms: tuple[tuple[float, float], ...] = ()
        self._truncated = False

    @property
    def current_history_for_evaluator(self) -> FullHistory:
        if self._history is None:
            raise RuntimeError("context world has not been reset")
        return self._history

    def reset(
        self,
        *,
        initial_history: FullHistory,
        max_steps: int,
        episode_seed: int,
    ) -> LearnedContextObservation:
        validate_full_history(initial_history, "initial_history")
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or max_steps < 1
            or isinstance(episode_seed, bool)
            or not isinstance(episode_seed, int)
        ):
            raise ValidationError("episode configuration is invalid")
        transition_rng = random.Random(
            episode_seed ^ CONTEXT_TRANSITION_XOR_MASK
        )
        reward_rng = random.Random(
            episode_seed ^ CONTEXT_REWARD_XOR_MASK
        )
        self._transition_uniforms = tuple(
            tuple(
                transition_rng.random() for _ in CONTEXT_ACTIONS
            )
            for _ in range(max_steps)
        )  # type: ignore[assignment]
        self._reward_uniforms = tuple(
            tuple(reward_rng.random() for _ in CONTEXT_ACTIONS)
            for _ in range(max_steps)
        )  # type: ignore[assignment]
        self._episode_counter += 1
        self._episode_id = (
            f"{self.world_id}:episode:{self._episode_counter:06d}"
        )
        self._history = initial_history
        self._step_index = 0
        self._max_steps = max_steps
        self._truncated = False
        return self._observation(priming=True)

    def _observation(self, *, priming: bool) -> LearnedContextObservation:
        if self._history is None:
            raise RuntimeError("context world has not been reset")
        return LearnedContextObservation(
            world_id=self.world_id,
            episode_id=self._episode_id,
            observation=self._history[-1],
            step_index=self._step_index,
            truncated=self._truncated,
            priming_history=self._history if priming else None,
        )

    def step(self, action: str) -> LearnedContextStep:
        action_index = _action_index(action)
        if self._history is None:
            raise RuntimeError("context world has not been reset")
        if self._truncated:
            raise RuntimeError("context episode is complete")
        transition_probability = (
            self.specification.transition_probability(
                self._history,
                action,
            )
        )
        reward_probability = self.specification.reward_probability(
            self._history,
            action,
        )
        next_observation = (
            self._transition_uniforms[self._step_index][action_index]
            < transition_probability
        )
        reward = (
            self._reward_uniforms[self._step_index][action_index]
            < reward_probability
        )
        self._history = append_observation(
            self._history,
            next_observation,
        )
        self._step_index += 1
        self._truncated = self._step_index >= self._max_steps
        return LearnedContextStep(
            observation=self._observation(priming=False),
            action=action,
            reward=reward,
        )


@dataclass(frozen=True, slots=True)
class LearnedContextExperience:
    world_id: str
    trace_id: str
    sequence: int
    history: FullHistory
    action: str
    next_observation: bool
    reward: bool

    def __post_init__(self) -> None:
        require_text(self.world_id, "world_id")
        require_text(self.trace_id, "trace_id")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ValidationError("context sequence must be positive")
        validate_full_history(self.history)
        _action_index(self.action)
        if (
            not isinstance(self.next_observation, bool)
            or not isinstance(self.reward, bool)
        ):
            raise ValidationError(
                "next observation and reward must be boolean"
            )

    @property
    def next_history(self) -> FullHistory:
        return append_observation(
            self.history,
            self.next_observation,
        )


class CausalContextArchive:
    """Immutable-facing continuous trace of chosen feedback."""

    SNAPSHOT_SCHEMA = 1

    def __init__(self) -> None:
        self._items: list[LearnedContextExperience] = []

    @property
    def items(self) -> tuple[LearnedContextExperience, ...]:
        return tuple(self._items)

    def observe(self, experience: LearnedContextExperience) -> None:
        if experience.sequence != len(self._items) + 1:
            raise ValidationError(
                "context sequence must be contiguous and unreplayed"
            )
        if self._items:
            previous = self._items[-1]
            if experience.history != previous.next_history:
                raise ValidationError("context history is discontinuous")
            if (
                experience.world_id != previous.world_id
                or experience.trace_id != previous.trace_id
            ):
                raise ValidationError(
                    "one context archive cannot mix traces or worlds"
                )
        self._items.append(experience)

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "items": [
                    {
                        "world_id": item.world_id,
                        "trace_id": item.trace_id,
                        "sequence": item.sequence,
                        "history": list(item.history),
                        "action": item.action,
                        "next_observation": item.next_observation,
                        "reward": item.reward,
                    }
                    for item in self._items
                ],
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "CausalContextArchive":
        parsed = parse_json(raw)
        if (
            not isinstance(parsed, dict)
            or parsed.get("schema") != cls.SNAPSHOT_SCHEMA
        ):
            raise ValidationError("unsupported context archive snapshot")
        rows = parsed.get("items")
        if not isinstance(rows, list):
            raise ValidationError("context archive items must be a list")
        archive = cls()
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid context archive item")
            try:
                raw_history = row["history"]
                if not isinstance(raw_history, list):
                    raise ValidationError(
                        "archive history must be a list"
                    )
                archive.observe(
                    LearnedContextExperience(
                        world_id=row["world_id"],
                        trace_id=row["trace_id"],
                        sequence=row["sequence"],
                        history=tuple(raw_history),  # type: ignore[arg-type]
                        action=row["action"],
                        next_observation=row["next_observation"],
                        reward=row["reward"],
                    )
                )
            except KeyError as error:
                raise ValidationError(
                    f"context archive missing field: {error.args[0]}"
                ) from error
        if canonical_json(parsed) != archive.to_snapshot():
            raise ValidationError(
                "context archive does not match causal replay"
            )
        return archive


@dataclass(frozen=True, slots=True)
class ContextOutcomeCounts:
    transition_successes: int
    transition_failures: int
    reward_successes: int
    reward_failures: int

    def __post_init__(self) -> None:
        for value in (
            self.transition_successes,
            self.transition_failures,
            self.reward_successes,
            self.reward_failures,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValidationError("context counts are invalid")
        if (
            self.transition_successes + self.transition_failures
            != self.reward_successes + self.reward_failures
        ):
            raise ValidationError(
                "transition and reward evidence counts must agree"
            )

    @property
    def evidence_count(self) -> int:
        return self.transition_successes + self.transition_failures

    @property
    def transition_probability(self) -> float:
        return (
            1.0 + self.transition_successes
        ) / (2.0 + self.evidence_count)

    @property
    def reward_probability(self) -> float:
        return (
            1.0 + self.reward_successes
        ) / (2.0 + self.evidence_count)


@dataclass(frozen=True, slots=True)
class ContextOrderScore:
    order: int
    validation_log_loss: float

    def __post_init__(self) -> None:
        _validate_order(self.order, "order score")
        if (
            isinstance(self.validation_log_loss, bool)
            or not isinstance(self.validation_log_loss, (int, float))
            or not math.isfinite(self.validation_log_loss)
            or self.validation_log_loss < 0.0
        ):
            raise ValidationError("validation log loss is invalid")


def _fit_counts(
    experiences: Iterable[LearnedContextExperience],
    *,
    order: int,
) -> dict[tuple[ContextState, str], ContextOutcomeCounts]:
    _validate_order(order, "context order")
    mutable: dict[tuple[ContextState, str], list[int]] = {}
    for item in experiences:
        key = (history_suffix(item.history, order), item.action)
        counts = mutable.setdefault(key, [0, 0, 0, 0])
        counts[0 if item.next_observation else 1] += 1
        counts[2 if item.reward else 3] += 1
    return {
        key: ContextOutcomeCounts(*values)
        for key, values in mutable.items()
    }


def _probabilities_from_counts(
    counts: dict[tuple[ContextState, str], ContextOutcomeCounts],
    context: ContextState,
    action: str,
) -> tuple[float, float]:
    item = counts.get((context, action))
    if item is None:
        return 0.5, 0.5
    return item.transition_probability, item.reward_probability


def _binary_log_loss(probability: float, outcome: bool) -> float:
    bounded = min(max(probability, 1e-12), 1.0 - 1e-12)
    return -math.log(bounded if outcome else 1.0 - bounded)


class LearnedContextModel:
    """Selected fixed-order transition and reward model."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        archive: tuple[LearnedContextExperience, ...],
        selected_order: int,
        order_scores: tuple[ContextOrderScore, ...],
        fixed_order: int | None,
        counts: dict[
            tuple[ContextState, str],
            ContextOutcomeCounts,
        ],
    ) -> None:
        if not archive:
            raise ValidationError("learned context model needs experience")
        _validate_order(selected_order, "selected context order")
        if fixed_order is not None:
            _validate_order(fixed_order, "fixed context order")
            if fixed_order != selected_order:
                raise ValidationError("fixed and selected orders disagree")
        if fixed_order is None and (
            len(order_scores) != len(CONTEXT_ORDER_CANDIDATES)
            or tuple(item.order for item in order_scores)
            != CONTEXT_ORDER_CANDIDATES
        ):
            raise ValidationError("selected model requires all order scores")
        if fixed_order is not None and order_scores:
            raise ValidationError("fixed model cannot contain order scores")
        self._archive = archive
        self.selected_order = selected_order
        self.order_scores = order_scores
        self.fixed_order = fixed_order
        self._counts = dict(counts)

    @classmethod
    def fit(
        cls,
        archive: Sequence[LearnedContextExperience],
        *,
        fixed_order: int | None = None,
    ) -> "LearnedContextModel":
        items = tuple(archive)
        if len(items) < 10:
            raise ValidationError(
                "context model needs at least ten experiences"
            )
        replay = CausalContextArchive()
        for item in items:
            replay.observe(item)
        if fixed_order is not None:
            _validate_order(fixed_order, "fixed context order")
            selected_order = fixed_order
            scores: tuple[ContextOrderScore, ...] = ()
        else:
            split = int(len(items) * 0.70)
            if not 1 <= split < len(items):
                raise ValidationError("context validation split is invalid")
            training = items[:split]
            validation = items[split:]
            mutable_scores: list[ContextOrderScore] = []
            for order in CONTEXT_ORDER_CANDIDATES:
                training_counts = _fit_counts(training, order=order)
                total_loss = 0.0
                for item in validation:
                    context = history_suffix(item.history, order)
                    transition_p, reward_p = (
                        _probabilities_from_counts(
                            training_counts,
                            context,
                            item.action,
                        )
                    )
                    total_loss += _binary_log_loss(
                        transition_p,
                        item.next_observation,
                    )
                    total_loss += _binary_log_loss(
                        reward_p,
                        item.reward,
                    )
                mutable_scores.append(
                    ContextOrderScore(
                        order=order,
                        validation_log_loss=(
                            total_loss / (2 * len(validation))
                        ),
                    )
                )
            scores = tuple(mutable_scores)
            selected_order = min(
                scores,
                key=lambda item: (
                    item.validation_log_loss,
                    item.order,
                ),
            ).order
        counts = _fit_counts(items, order=selected_order)
        return cls(
            archive=items,
            selected_order=selected_order,
            order_scores=scores,
            fixed_order=fixed_order,
            counts=counts,
        )

    @property
    def archive(self) -> tuple[LearnedContextExperience, ...]:
        return self._archive

    @property
    def contexts(self) -> tuple[ContextState, ...]:
        return all_contexts(self.selected_order)

    def counts_for(
        self,
        context: ContextState,
        action: str,
    ) -> ContextOutcomeCounts | None:
        validate_context(
            context,
            order=self.selected_order,
        )
        _action_index(action)
        return self._counts.get((context, action))

    def transition_probability(
        self,
        context: ContextState,
        action: str,
    ) -> float:
        counts = self.counts_for(context, action)
        return (
            counts.transition_probability
            if counts is not None
            else 0.5
        )

    def reward_probability(
        self,
        context: ContextState,
        action: str,
    ) -> float:
        counts = self.counts_for(context, action)
        return counts.reward_probability if counts is not None else 0.5

    def context_for_history(
        self,
        history: FullHistory,
    ) -> ContextState:
        return history_suffix(history, self.selected_order)

    def _count_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for context, action in sorted(
            self._counts,
            key=lambda item: (
                item[0],
                CONTEXT_ACTIONS.index(item[1]),
            ),
        ):
            item = self._counts[(context, action)]
            rows.append(
                {
                    "context": list(context),
                    "action": action,
                    "transition_successes": item.transition_successes,
                    "transition_failures": item.transition_failures,
                    "reward_successes": item.reward_successes,
                    "reward_failures": item.reward_failures,
                }
            )
        return rows

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "fixed_order": self.fixed_order,
                "selected_order": self.selected_order,
                "order_scores": [
                    {
                        "order": item.order,
                        "validation_log_loss": (
                            item.validation_log_loss
                        ),
                    }
                    for item in self.order_scores
                ],
                "archive": [
                    {
                        "world_id": item.world_id,
                        "trace_id": item.trace_id,
                        "sequence": item.sequence,
                        "history": list(item.history),
                        "action": item.action,
                        "next_observation": item.next_observation,
                        "reward": item.reward,
                    }
                    for item in self._archive
                ],
                "counts": self._count_rows(),
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "LearnedContextModel":
        parsed = parse_json(raw)
        if (
            not isinstance(parsed, dict)
            or parsed.get("schema") != cls.SNAPSHOT_SCHEMA
        ):
            raise ValidationError(
                "unsupported learned-context snapshot"
            )
        archive_rows = parsed.get("archive")
        if not isinstance(archive_rows, list):
            raise ValidationError("learned context archive is invalid")
        archive = CausalContextArchive()
        for row in archive_rows:
            if not isinstance(row, dict):
                raise ValidationError(
                    "invalid learned context experience"
                )
            try:
                raw_history = row["history"]
                if not isinstance(raw_history, list):
                    raise ValidationError(
                        "learned context history must be a list"
                    )
                archive.observe(
                    LearnedContextExperience(
                        world_id=row["world_id"],
                        trace_id=row["trace_id"],
                        sequence=row["sequence"],
                        history=tuple(raw_history),  # type: ignore[arg-type]
                        action=row["action"],
                        next_observation=row["next_observation"],
                        reward=row["reward"],
                    )
                )
            except KeyError as error:
                raise ValidationError(
                    f"learned context snapshot missing: {error.args[0]}"
                ) from error
        fixed_order = parsed.get("fixed_order")
        model = cls.fit(
            archive.items,
            fixed_order=fixed_order,
        )
        if canonical_json(parsed) != model.to_snapshot():
            raise ValidationError(
                "learned context snapshot does not match replay"
            )
        return model


class ContextPlanningModel(Protocol):
    selected_order: int

    @property
    def contexts(self) -> tuple[ContextState, ...]: ...

    def transition_probability(
        self,
        context: ContextState,
        action: str,
    ) -> float: ...

    def reward_probability(
        self,
        context: ContextState,
        action: str,
    ) -> float: ...

    def context_for_history(
        self,
        history: FullHistory,
    ) -> ContextState: ...


class TrueContextPlanningModel:
    """Evaluator-only adapter around registered world probabilities."""

    def __init__(
        self,
        specification: LearnedContextWorldSpecification,
    ) -> None:
        self.specification = specification
        self.selected_order = specification.true_order

    @property
    def contexts(self) -> tuple[ContextState, ...]:
        return all_contexts(self.selected_order)

    def _history_for_context(
        self,
        context: ContextState,
    ) -> FullHistory:
        validate_context(
            context,
            order=self.selected_order,
        )
        prefix = (False,) * (MAX_CONTEXT_ORDER - self.selected_order)
        return prefix + context  # type: ignore[return-value]

    def transition_probability(
        self,
        context: ContextState,
        action: str,
    ) -> float:
        return self.specification.transition_probability(
            self._history_for_context(context),
            action,
        )

    def reward_probability(
        self,
        context: ContextState,
        action: str,
    ) -> float:
        return self.specification.reward_probability(
            self._history_for_context(context),
            action,
        )

    def context_for_history(
        self,
        history: FullHistory,
    ) -> ContextState:
        return history_suffix(history, self.selected_order)


class ContextValuePlanner:
    """Discounted value iteration over learned context dynamics."""

    def __init__(
        self,
        model: ContextPlanningModel,
        *,
        discount: float = CONTEXT_DISCOUNT,
        tolerance: float = 1e-10,
        maximum_iterations: int = 1000,
        reward_rotation: int = 0,
    ) -> None:
        if (
            isinstance(discount, bool)
            or not isinstance(discount, (int, float))
            or not math.isfinite(discount)
            or not 0.0 < discount < 1.0
            or isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance)
            or tolerance <= 0.0
            or isinstance(maximum_iterations, bool)
            or not isinstance(maximum_iterations, int)
            or maximum_iterations < 1
            or isinstance(reward_rotation, bool)
            or not isinstance(reward_rotation, int)
            or reward_rotation < 0
        ):
            raise ValidationError("value planner configuration is invalid")
        self.model = model
        self.discount = float(discount)
        self.tolerance = float(tolerance)
        self.maximum_iterations = maximum_iterations
        self.reward_rotation = reward_rotation
        self._values, self._q_values, self.iterations = self._solve()

    @staticmethod
    def _shift_context(
        context: ContextState,
        next_observation: bool,
    ) -> ContextState:
        return context[1:] + (next_observation,)

    def _rotated_reward_context(
        self,
        context: ContextState,
    ) -> ContextState:
        if self.reward_rotation == 0:
            return context
        contexts = self.model.contexts
        index = contexts.index(context)
        return contexts[
            (index + self.reward_rotation) % len(contexts)
        ]

    def _solve(
        self,
    ) -> tuple[
        dict[ContextState, float],
        dict[tuple[ContextState, str], float],
        int,
    ]:
        values = {context: 0.0 for context in self.model.contexts}
        q_values: dict[tuple[ContextState, str], float] = {}
        for iteration in range(1, self.maximum_iterations + 1):
            updated: dict[ContextState, float] = {}
            next_q: dict[tuple[ContextState, str], float] = {}
            for context in self.model.contexts:
                reward_context = self._rotated_reward_context(context)
                for action in CONTEXT_ACTIONS:
                    transition_p = self.model.transition_probability(
                        context,
                        action,
                    )
                    reward_p = self.model.reward_probability(
                        reward_context,
                        action,
                    )
                    false_context = self._shift_context(
                        context,
                        False,
                    )
                    true_context = self._shift_context(
                        context,
                        True,
                    )
                    next_q[(context, action)] = (
                        reward_p
                        + self.discount
                        * (
                            (1.0 - transition_p)
                            * values[false_context]
                            + transition_p * values[true_context]
                        )
                    )
                updated[context] = max(
                    next_q[(context, action)]
                    for action in CONTEXT_ACTIONS
                )
            difference = max(
                abs(updated[context] - values[context])
                for context in self.model.contexts
            )
            values = updated
            q_values = next_q
            if difference <= self.tolerance:
                return values, q_values, iteration
        raise ValidationError("value iteration did not converge")

    def action(self, history: FullHistory) -> str:
        context = self.model.context_for_history(history)
        return max(
            CONTEXT_ACTIONS,
            key=lambda action: (
                self._q_values[(context, action)],
                -CONTEXT_ACTIONS.index(action),
            ),
        )

    def q_value(self, context: ContextState, action: str) -> float:
        validate_context(
            context,
            order=self.model.selected_order,
        )
        _action_index(action)
        return self._q_values[(context, action)]
