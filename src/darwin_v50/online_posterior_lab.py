"""Online posterior-sampling control for Darwin H50-L12.

The module implements a deliberately small tabular Bayesian controller.  It
does not implement general reinforcement learning, neural representation
learning, consciousness, or a Diana-like mind.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Mapping, Sequence

from .learned_context_lab import (
    CONTEXT_ACTIONS,
    CONTEXT_ORDER_CANDIDATES,
    MAX_CONTEXT_ORDER,
    ContextState,
    FullHistory,
    LearnedContextWorldSpecification,
    all_contexts,
    append_observation,
    history_suffix,
    validate_context,
    validate_full_history,
)
from .models import ValidationError, canonical_json, parse_json, require_text


ONLINE_ENVIRONMENT_EPISODE_LENGTH = 32
ONLINE_PRIOR_ALPHA = 1.0
ONLINE_PRIOR_BETA = 1.0


def _validate_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    return require_text(value, field)


def _validate_action(action: object) -> str:
    if not isinstance(action, str) or action not in CONTEXT_ACTIONS:
        raise ValidationError("unknown online action")
    return action


def _validate_order(order: object, field: str = "order") -> int:
    if (
        isinstance(order, bool)
        or not isinstance(order, int)
        or order not in CONTEXT_ORDER_CANDIDATES
    ):
        raise ValidationError(f"{field} is invalid")
    return order


def _validate_probability(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < float(value) < 1.0
    ):
        raise ValidationError(f"{field} must be finite and within (0, 1)")
    return float(value)


def _validate_non_negative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class OnlineExperience:
    """One chosen action and its two observed binary consequences."""

    world_id: str
    sequence: int
    episode_index: int
    step_index: int
    history: FullHistory
    action: str
    next_observation: bool
    reward: bool

    FIELDS = frozenset(
        {
            "world_id",
            "sequence",
            "episode_index",
            "step_index",
            "history",
            "action",
            "next_observation",
            "reward",
        }
    )

    def __post_init__(self) -> None:
        _validate_text(self.world_id, "world_id")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
            or isinstance(self.episode_index, bool)
            or not isinstance(self.episode_index, int)
            or self.episode_index < 1
            or isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or not 0 <= self.step_index < ONLINE_ENVIRONMENT_EPISODE_LENGTH
        ):
            raise ValidationError("online experience index is invalid")
        validate_full_history(self.history)
        _validate_action(self.action)
        if (
            not isinstance(self.next_observation, bool)
            or not isinstance(self.reward, bool)
        ):
            raise ValidationError("online outcomes must be boolean")

    @property
    def next_history(self) -> FullHistory:
        return append_observation(self.history, self.next_observation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "sequence": self.sequence,
            "episode_index": self.episode_index,
            "step_index": self.step_index,
            "history": list(self.history),
            "action": self.action,
            "next_observation": self.next_observation,
            "reward": self.reward,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "OnlineExperience":
        if not isinstance(raw, dict) or set(raw) != cls.FIELDS:
            raise ValidationError(
                "online experience fields are invalid or counterfactual"
            )
        history = raw.get("history")
        if not isinstance(history, list):
            raise ValidationError("online history must be a list")
        return cls(
            world_id=raw.get("world_id"),  # type: ignore[arg-type]
            sequence=raw.get("sequence"),  # type: ignore[arg-type]
            episode_index=raw.get("episode_index"),  # type: ignore[arg-type]
            step_index=raw.get("step_index"),  # type: ignore[arg-type]
            history=tuple(history),  # type: ignore[arg-type]
            action=raw.get("action"),  # type: ignore[arg-type]
            next_observation=raw.get("next_observation"),  # type: ignore[arg-type]
            reward=raw.get("reward"),  # type: ignore[arg-type]
        )


class OnlineCausalArchive:
    """Chosen-action archive with explicit environment episode boundaries."""

    def __init__(self) -> None:
        self._items: list[OnlineExperience] = []

    @property
    def items(self) -> tuple[OnlineExperience, ...]:
        return tuple(self._items)

    def observe(self, experience: OnlineExperience) -> None:
        if experience.sequence != len(self._items) + 1:
            raise ValidationError("online sequence must be contiguous")
        if not self._items:
            if experience.episode_index != 1 or experience.step_index != 0:
                raise ValidationError("online archive must start at episode one")
        else:
            previous = self._items[-1]
            if experience.world_id != previous.world_id:
                raise ValidationError("online archive cannot mix worlds")
            if experience.episode_index == previous.episode_index:
                if (
                    experience.step_index != previous.step_index + 1
                    or experience.history != previous.next_history
                ):
                    raise ValidationError("online history is discontinuous")
            elif experience.episode_index == previous.episode_index + 1:
                if (
                    previous.step_index
                    != ONLINE_ENVIRONMENT_EPISODE_LENGTH - 1
                    or experience.step_index != 0
                ):
                    raise ValidationError("online episode boundary is invalid")
            else:
                raise ValidationError("online episode index is discontinuous")
        self._items.append(experience)


@dataclass(frozen=True, slots=True)
class BetaCounts:
    successes: int = 0
    failures: int = 0

    def __post_init__(self) -> None:
        _validate_non_negative_integer(self.successes, "successes")
        _validate_non_negative_integer(self.failures, "failures")

    @property
    def alpha(self) -> float:
        return ONLINE_PRIOR_ALPHA + self.successes

    @property
    def beta(self) -> float:
        return ONLINE_PRIOR_BETA + self.failures

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def probability_of(self, outcome: bool) -> float:
        if not isinstance(outcome, bool):
            raise ValidationError("posterior outcome must be boolean")
        return self.mean if outcome else 1.0 - self.mean

    def updated(self, outcome: bool) -> "BetaCounts":
        if not isinstance(outcome, bool):
            raise ValidationError("posterior outcome must be boolean")
        return BetaCounts(
            successes=self.successes + int(outcome),
            failures=self.failures + int(not outcome),
        )


@dataclass(frozen=True, slots=True)
class OutcomeCounts:
    transition: BetaCounts
    reward: BetaCounts


class ProbabilityTableModel:
    """A complete fixed-order transition and reward probability table."""

    def __init__(
        self,
        *,
        order: int,
        probabilities: Mapping[
            tuple[ContextState, str], tuple[float, float]
        ],
    ) -> None:
        self.selected_order = _validate_order(order, "planning order")
        expected = {
            (context, action)
            for context in all_contexts(self.selected_order)
            for action in CONTEXT_ACTIONS
        }
        if set(probabilities) != expected:
            raise ValidationError("planning table does not cover every state")
        self._probabilities = {
            key: (
                _validate_probability(value[0], "transition probability"),
                _validate_probability(value[1], "reward probability"),
            )
            for key, value in probabilities.items()
        }

    @property
    def contexts(self) -> tuple[ContextState, ...]:
        return all_contexts(self.selected_order)

    def transition_probability(
        self, context: ContextState, action: str
    ) -> float:
        validate_context(context, order=self.selected_order)
        _validate_action(action)
        return self._probabilities[(context, action)][0]

    def reward_probability(
        self, context: ContextState, action: str
    ) -> float:
        validate_context(context, order=self.selected_order)
        _validate_action(action)
        return self._probabilities[(context, action)][1]

    def context_for_history(self, history: FullHistory) -> ContextState:
        return history_suffix(history, self.selected_order)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.selected_order,
            "rows": [
                {
                    "context": list(context),
                    "action": action,
                    "transition_probability": self._probabilities[
                        (context, action)
                    ][0],
                    "reward_probability": self._probabilities[
                        (context, action)
                    ][1],
                }
                for context in self.contexts
                for action in CONTEXT_ACTIONS
            ],
        }

    @classmethod
    def from_dict(cls, raw: object) -> "ProbabilityTableModel":
        if not isinstance(raw, dict) or set(raw) != {"order", "rows"}:
            raise ValidationError("sampled model fields are invalid")
        order = _validate_order(raw.get("order"), "sampled order")
        rows = raw.get("rows")
        if not isinstance(rows, list):
            raise ValidationError("sampled model rows must be a list")
        probabilities: dict[
            tuple[ContextState, str], tuple[float, float]
        ] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "context",
                "action",
                "transition_probability",
                "reward_probability",
            }:
                raise ValidationError("sampled model row is invalid")
            context_raw = row.get("context")
            if not isinstance(context_raw, list):
                raise ValidationError("sampled context must be a list")
            context = validate_context(
                tuple(context_raw), order=order, field="sampled context"
            )
            action = _validate_action(row.get("action"))
            key = (context, action)
            if key in probabilities:
                raise ValidationError("sampled model row is duplicated")
            probabilities[key] = (
                _validate_probability(
                    row.get("transition_probability"),
                    "sampled transition probability",
                ),
                _validate_probability(
                    row.get("reward_probability"),
                    "sampled reward probability",
                ),
            )
        model = cls(order=order, probabilities=probabilities)
        if canonical_json(raw) != canonical_json(model.to_dict()):
            raise ValidationError("sampled model is not canonical")
        return model


class FiniteHorizonContextPlanner:
    """Exact undiscounted dynamic program for a fixed tabular model."""

    def __init__(self, model: ProbabilityTableModel, *, horizon: int) -> None:
        if (
            isinstance(horizon, bool)
            or not isinstance(horizon, int)
            or horizon < 1
        ):
            raise ValidationError("planning horizon must be positive")
        self.model = model
        self.horizon = horizon
        self._q_values = self._solve()

    @staticmethod
    def _next_context(
        context: ContextState, next_observation: bool
    ) -> ContextState:
        return context[1:] + (next_observation,)

    def _solve(self) -> dict[tuple[int, ContextState, str], float]:
        previous = {context: 0.0 for context in self.model.contexts}
        q_values: dict[tuple[int, ContextState, str], float] = {}
        for remaining in range(1, self.horizon + 1):
            current: dict[ContextState, float] = {}
            for context in self.model.contexts:
                for action in CONTEXT_ACTIONS:
                    transition_p = self.model.transition_probability(
                        context, action
                    )
                    reward_p = self.model.reward_probability(context, action)
                    false_context = self._next_context(context, False)
                    true_context = self._next_context(context, True)
                    q_values[(remaining, context, action)] = (
                        reward_p
                        + (1.0 - transition_p) * previous[false_context]
                        + transition_p * previous[true_context]
                    )
                current[context] = max(
                    q_values[(remaining, context, action)]
                    for action in CONTEXT_ACTIONS
                )
            previous = current
        return q_values

    def action(self, history: FullHistory, *, remaining: int) -> str:
        validate_full_history(history)
        if (
            isinstance(remaining, bool)
            or not isinstance(remaining, int)
            or not 1 <= remaining <= self.horizon
        ):
            raise ValidationError("planning time-to-go is invalid")
        context = self.model.context_for_history(history)
        return max(
            CONTEXT_ACTIONS,
            key=lambda action: (
                self._q_values[(remaining, context, action)],
                -CONTEXT_ACTIONS.index(action),
            ),
        )

    def q_value(
        self, context: ContextState, action: str, *, remaining: int
    ) -> float:
        validate_context(context, order=self.model.selected_order)
        _validate_action(action)
        if not 1 <= remaining <= self.horizon:
            raise ValidationError("planning time-to-go is invalid")
        return self._q_values[(remaining, context, action)]


class OnlineBayesianModel:
    """Five exact Beta-Bernoulli models with prequential order evidence."""

    def __init__(self, *, world_id: str) -> None:
        self.world_id = _validate_text(world_id, "world_id")
        self.archive = OnlineCausalArchive()
        self._counts: dict[
            int, dict[tuple[ContextState, str], OutcomeCounts]
        ] = {
            order: {
                (context, action): OutcomeCounts(BetaCounts(), BetaCounts())
                for context in all_contexts(order)
                for action in CONTEXT_ACTIONS
            }
            for order in CONTEXT_ORDER_CANDIDATES
        }
        self._log_evidence = {
            order: 0.0 for order in CONTEXT_ORDER_CANDIDATES
        }
        self._information_gains: list[float] = []

    @property
    def log_evidence(self) -> dict[int, float]:
        return dict(self._log_evidence)

    @property
    def information_gains(self) -> tuple[float, ...]:
        return tuple(self._information_gains)

    def counts_for(
        self, order: int, context: ContextState, action: str
    ) -> OutcomeCounts:
        validated_order = _validate_order(order)
        validate_context(context, order=validated_order)
        _validate_action(action)
        return self._counts[validated_order][(context, action)]

    def _log_order_posterior(self) -> dict[int, float]:
        if any(not math.isfinite(value) for value in self._log_evidence.values()):
            raise ValidationError("order evidence must be finite")
        maximum = max(self._log_evidence.values())
        shifted_sum = sum(
            math.exp(value - maximum)
            for value in self._log_evidence.values()
        )
        if not math.isfinite(shifted_sum) or shifted_sum <= 0.0:
            raise ValidationError("order posterior cannot be normalized")
        log_normalizer = maximum + math.log(shifted_sum)
        return {
            order: value - log_normalizer
            for order, value in self._log_evidence.items()
        }

    def order_posterior(self) -> dict[int, float]:
        log_posterior = self._log_order_posterior()
        posterior = {
            order: math.exp(value)
            for order, value in log_posterior.items()
        }
        if not math.isclose(
            sum(posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValidationError("order posterior does not normalize")
        return posterior

    @property
    def map_order(self) -> int:
        return max(
            CONTEXT_ORDER_CANDIDATES,
            key=lambda order: (self._log_evidence[order], -order),
        )

    def update(self, experience: OnlineExperience) -> float:
        if experience.world_id != self.world_id:
            raise ValidationError("online observation belongs to another world")
        old_log_posterior = self._log_order_posterior()
        self.archive.observe(experience)
        for order in CONTEXT_ORDER_CANDIDATES:
            context = history_suffix(experience.history, order)
            key = (context, experience.action)
            counts = self._counts[order][key]
            transition_predictive = counts.transition.probability_of(
                experience.next_observation
            )
            reward_predictive = counts.reward.probability_of(experience.reward)
            self._log_evidence[order] += math.log(
                transition_predictive
            ) + math.log(reward_predictive)
            self._counts[order][key] = OutcomeCounts(
                transition=counts.transition.updated(
                    experience.next_observation
                ),
                reward=counts.reward.updated(experience.reward),
            )
        new_log_posterior = self._log_order_posterior()
        information_gain = sum(
            math.exp(new_log_posterior[order])
            * (
                new_log_posterior[order]
                - old_log_posterior[order]
            )
            for order in CONTEXT_ORDER_CANDIDATES
        )
        if information_gain < -1e-12 or not math.isfinite(information_gain):
            raise ValidationError("order information gain is invalid")
        information_gain = max(0.0, information_gain)
        self._information_gains.append(information_gain)
        return information_gain

    def mean_model(self, *, order: int | None = None) -> ProbabilityTableModel:
        selected = self.map_order if order is None else _validate_order(order)
        return ProbabilityTableModel(
            order=selected,
            probabilities={
                (context, action): (
                    self._counts[selected][(context, action)].transition.mean,
                    self._counts[selected][(context, action)].reward.mean,
                )
                for context in all_contexts(selected)
                for action in CONTEXT_ACTIONS
            },
        )

    def sample_order(self, rng: random.Random) -> int:
        posterior = self.order_posterior()
        draw = rng.random()
        cumulative = 0.0
        for order in CONTEXT_ORDER_CANDIDATES:
            cumulative += posterior[order]
            if draw < cumulative:
                return order
        return CONTEXT_ORDER_CANDIDATES[-1]

    def sampled_model(
        self, rng: random.Random, *, fixed_order: int | None = None
    ) -> ProbabilityTableModel:
        selected = (
            self.sample_order(rng)
            if fixed_order is None
            else _validate_order(fixed_order, "fixed sampled order")
        )
        return ProbabilityTableModel(
            order=selected,
            probabilities={
                (context, action): (
                    rng.betavariate(
                        self._counts[selected][
                            (context, action)
                        ].transition.alpha,
                        self._counts[selected][
                            (context, action)
                        ].transition.beta,
                    ),
                    rng.betavariate(
                        self._counts[selected][(context, action)].reward.alpha,
                        self._counts[selected][(context, action)].reward.beta,
                    ),
                )
                for context in all_contexts(selected)
                for action in CONTEXT_ACTIONS
            },
        )

    def probability_errors(
        self, specification: LearnedContextWorldSpecification
    ) -> tuple[float, float]:
        model = self.mean_model()
        transition_errors: list[float] = []
        reward_errors: list[float] = []
        for integer in range(1 << MAX_CONTEXT_ORDER):
            history: FullHistory = tuple(
                bool(integer & (1 << (MAX_CONTEXT_ORDER - index - 1)))
                for index in range(MAX_CONTEXT_ORDER)
            )  # type: ignore[assignment]
            context = model.context_for_history(history)
            for action in CONTEXT_ACTIONS:
                transition_errors.append(
                    abs(
                        model.transition_probability(context, action)
                        - specification.transition_probability(history, action)
                    )
                )
                reward_errors.append(
                    abs(
                        model.reward_probability(context, action)
                        - specification.reward_probability(history, action)
                    )
                )
        return (
            sum(transition_errors) / len(transition_errors),
            sum(reward_errors) / len(reward_errors),
        )

    def _count_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "order": order,
                "context": list(context),
                "action": action,
                "transition_successes": (
                    self._counts[order][(context, action)].transition.successes
                ),
                "transition_failures": (
                    self._counts[order][(context, action)].transition.failures
                ),
                "reward_successes": (
                    self._counts[order][(context, action)].reward.successes
                ),
                "reward_failures": (
                    self._counts[order][(context, action)].reward.failures
                ),
            }
            for order in CONTEXT_ORDER_CANDIDATES
            for context in all_contexts(order)
            for action in CONTEXT_ACTIONS
        ]

    def to_dict(self) -> dict[str, Any]:
        posterior = self.order_posterior()
        return {
            "world_id": self.world_id,
            "archive": [item.to_dict() for item in self.archive.items],
            "order_models": self._count_rows(),
            "log_evidence": [
                {"order": order, "value": self._log_evidence[order]}
                for order in CONTEXT_ORDER_CANDIDATES
            ],
            "order_posterior": [
                {"order": order, "value": posterior[order]}
                for order in CONTEXT_ORDER_CANDIDATES
            ],
        }

    @classmethod
    def from_dict(cls, raw: object) -> "OnlineBayesianModel":
        if not isinstance(raw, dict) or set(raw) != {
            "world_id",
            "archive",
            "order_models",
            "log_evidence",
            "order_posterior",
        }:
            raise ValidationError("online Bayesian model fields are invalid")
        world_id = raw.get("world_id")
        model = cls(world_id=world_id)  # type: ignore[arg-type]
        archive_rows = raw.get("archive")
        if not isinstance(archive_rows, list):
            raise ValidationError("online archive must be a list")
        for row in archive_rows:
            model.update(OnlineExperience.from_dict(row))
        try:
            if canonical_json(raw) != canonical_json(model.to_dict()):
                raise ValidationError(
                    "online Bayesian model does not match causal replay"
                )
        except (TypeError, ValueError) as error:
            raise ValidationError("online Bayesian model is not finite") from error
        return model


def _random_state_to_dict(state: object) -> dict[str, Any]:
    if (
        not isinstance(state, tuple)
        or len(state) != 3
        or not isinstance(state[0], int)
        or not isinstance(state[1], tuple)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in state[1])
        or (
            state[2] is not None
            and (
                isinstance(state[2], bool)
                or not isinstance(state[2], (int, float))
                or not math.isfinite(state[2])
            )
        )
    ):
        raise ValidationError("policy random state is invalid")
    return {
        "version": state[0],
        "internal_state": list(state[1]),
        "gauss_next": state[2],
    }


def _random_state_from_dict(raw: object) -> tuple[object, ...]:
    if not isinstance(raw, dict) or set(raw) != {
        "version",
        "internal_state",
        "gauss_next",
    }:
        raise ValidationError("policy random state fields are invalid")
    version = raw.get("version")
    internal = raw.get("internal_state")
    gauss_next = raw.get("gauss_next")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or not isinstance(internal, list)
        or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in internal
        )
        or (
            gauss_next is not None
            and (
                isinstance(gauss_next, bool)
                or not isinstance(gauss_next, (int, float))
                or not math.isfinite(gauss_next)
            )
        )
    ):
        raise ValidationError("policy random state is invalid")
    state: tuple[object, ...] = (version, tuple(internal), gauss_next)
    probe = random.Random()
    try:
        probe.setstate(state)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValidationError("policy random state cannot be restored") from error
    return state


class OnlinePosteriorAgent:
    """Posterior-sampling agent with replay-checked exact snapshots."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        world_id: str,
        policy_seed: int,
        resampling_length: int,
        fixed_order: int | None = None,
    ) -> None:
        _validate_text(world_id, "world_id")
        if isinstance(policy_seed, bool) or not isinstance(policy_seed, int):
            raise ValidationError("policy seed must be an integer")
        if (
            isinstance(resampling_length, bool)
            or not isinstance(resampling_length, int)
            or resampling_length < 1
        ):
            raise ValidationError("resampling length must be positive")
        if fixed_order is not None:
            fixed_order = _validate_order(fixed_order, "agent fixed order")
        self.world_id = world_id
        self.policy_seed = policy_seed
        self.resampling_length = resampling_length
        self.fixed_order = fixed_order
        self.model = OnlineBayesianModel(world_id=world_id)
        self._rng = random.Random(policy_seed)
        self._episode_index = 0
        self._step_index = 0
        self._history: FullHistory | None = None
        self._block_remaining = 0
        self._sampled_model: ProbabilityTableModel | None = None
        self._planner: FiniteHorizonContextPlanner | None = None
        self._pending_action: str | None = None

    @property
    def episode_index(self) -> int:
        return self._episode_index

    @property
    def step_index(self) -> int:
        return self._step_index

    @property
    def current_history(self) -> FullHistory:
        if self._history is None:
            raise RuntimeError("online episode has not started")
        return self._history

    @property
    def block_remaining(self) -> int:
        return self._block_remaining

    @property
    def sampled_order(self) -> int | None:
        return (
            self._sampled_model.selected_order
            if self._sampled_model is not None
            else None
        )

    def begin_episode(
        self, *, episode_index: int, initial_history: FullHistory
    ) -> None:
        validate_full_history(initial_history, "online initial history")
        if (
            isinstance(episode_index, bool)
            or not isinstance(episode_index, int)
            or episode_index < 1
        ):
            raise ValidationError("online episode index is invalid")
        if self._pending_action is not None:
            raise ValidationError("cannot reset with a pending action")
        if self._episode_index == 0:
            if episode_index != 1 or self.model.archive.items:
                raise ValidationError("online run must begin at episode one")
        elif (
            self._step_index != ONLINE_ENVIRONMENT_EPISODE_LENGTH
            or episode_index != self._episode_index + 1
        ):
            raise ValidationError("online episode reset is discontinuous")
        self._episode_index = episode_index
        self._step_index = 0
        self._history = initial_history

    def action(self) -> str:
        if self._history is None or self._episode_index < 1:
            raise RuntimeError("online episode has not started")
        if self._step_index >= ONLINE_ENVIRONMENT_EPISODE_LENGTH:
            raise RuntimeError("online environment episode is complete")
        if self._pending_action is not None:
            raise ValidationError("pending action has not been observed")
        if self._block_remaining == 0:
            self._sampled_model = self.model.sampled_model(
                self._rng, fixed_order=self.fixed_order
            )
            self._planner = FiniteHorizonContextPlanner(
                self._sampled_model, horizon=self.resampling_length
            )
            self._block_remaining = self.resampling_length
        if self._sampled_model is None or self._planner is None:
            raise RuntimeError("online planning state is incomplete")
        self._pending_action = self._planner.action(
            self._history, remaining=self._block_remaining
        )
        return self._pending_action

    def observe(self, *, next_observation: bool, reward: bool) -> float:
        if self._history is None or self._pending_action is None:
            raise ValidationError("online observation has no pending action")
        if not isinstance(next_observation, bool) or not isinstance(reward, bool):
            raise ValidationError("online outcomes must be boolean")
        experience = OnlineExperience(
            world_id=self.world_id,
            sequence=len(self.model.archive.items) + 1,
            episode_index=self._episode_index,
            step_index=self._step_index,
            history=self._history,
            action=self._pending_action,
            next_observation=next_observation,
            reward=reward,
        )
        information_gain = self.model.update(experience)
        self._history = experience.next_history
        self._step_index += 1
        self._block_remaining -= 1
        self._pending_action = None
        if self._block_remaining == 0:
            self._sampled_model = None
            self._planner = None
        return information_gain

    def _validate_current_state(self) -> None:
        if self._history is None or self._episode_index < 1:
            raise ValidationError("snapshot needs an active episode")
        if not 0 <= self._step_index <= ONLINE_ENVIRONMENT_EPISODE_LENGTH:
            raise ValidationError("snapshot step index is invalid")
        items = self.model.archive.items
        if not items:
            if self._episode_index != 1 or self._step_index != 0:
                raise ValidationError("empty archive state is inconsistent")
            return
        last = items[-1]
        if self._episode_index == last.episode_index:
            if (
                self._step_index != last.step_index + 1
                or self._history != last.next_history
            ):
                raise ValidationError("snapshot current history disagrees")
        elif self._episode_index == last.episode_index + 1:
            if (
                last.step_index != ONLINE_ENVIRONMENT_EPISODE_LENGTH - 1
                or self._step_index != 0
            ):
                raise ValidationError("snapshot episode reset disagrees")
        else:
            raise ValidationError("snapshot episode state is discontinuous")

    def to_snapshot(self) -> str:
        if self._pending_action is not None:
            raise ValidationError("cannot snapshot a pending action")
        self._validate_current_state()
        expected_remaining = (
            0
            if len(self.model.archive.items) % self.resampling_length == 0
            else self.resampling_length
            - len(self.model.archive.items) % self.resampling_length
        )
        if self._block_remaining != expected_remaining:
            raise ValidationError("planning block clock is inconsistent")
        if (self._sampled_model is None) != (self._block_remaining == 0):
            raise ValidationError("sampled model and block clock disagree")
        if not 0 <= self._block_remaining <= self.resampling_length:
            raise ValidationError("planning block clock is out of range")
        if (
            self.fixed_order is not None
            and self._sampled_model is not None
            and self._sampled_model.selected_order != self.fixed_order
        ):
            raise ValidationError("fixed-order sampled model is inconsistent")
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "configuration": {
                    "world_id": self.world_id,
                    "policy_seed": self.policy_seed,
                    "resampling_length": self.resampling_length,
                    "fixed_order": self.fixed_order,
                },
                "model": self.model.to_dict(),
                "episode_state": {
                    "episode_index": self._episode_index,
                    "step_index": self._step_index,
                    "history": list(self.current_history),
                },
                "planning_state": {
                    "block_remaining": self._block_remaining,
                    "sampled_model": (
                        self._sampled_model.to_dict()
                        if self._sampled_model is not None
                        else None
                    ),
                },
                "policy_rng_state": _random_state_to_dict(
                    self._rng.getstate()
                ),
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "OnlinePosteriorAgent":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema",
            "configuration",
            "model",
            "episode_state",
            "planning_state",
            "policy_rng_state",
        } or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported online agent snapshot")
        configuration = parsed.get("configuration")
        if not isinstance(configuration, dict) or set(configuration) != {
            "world_id",
            "policy_seed",
            "resampling_length",
            "fixed_order",
        }:
            raise ValidationError("online configuration is invalid")
        agent = cls(
            world_id=configuration.get("world_id"),  # type: ignore[arg-type]
            policy_seed=configuration.get("policy_seed"),  # type: ignore[arg-type]
            resampling_length=configuration.get("resampling_length"),  # type: ignore[arg-type]
            fixed_order=configuration.get("fixed_order"),  # type: ignore[arg-type]
        )
        agent.model = OnlineBayesianModel.from_dict(parsed.get("model"))
        if agent.model.world_id != agent.world_id:
            raise ValidationError("snapshot model and agent worlds disagree")
        episode_state = parsed.get("episode_state")
        if not isinstance(episode_state, dict) or set(episode_state) != {
            "episode_index",
            "step_index",
            "history",
        }:
            raise ValidationError("online episode snapshot is invalid")
        history = episode_state.get("history")
        if not isinstance(history, list):
            raise ValidationError("online snapshot history must be a list")
        agent._episode_index = _validate_non_negative_integer(
            episode_state.get("episode_index"), "snapshot episode index"
        )
        if agent._episode_index < 1:
            raise ValidationError("snapshot episode index must be positive")
        agent._step_index = _validate_non_negative_integer(
            episode_state.get("step_index"), "snapshot step index"
        )
        agent._history = validate_full_history(
            tuple(history), "online snapshot history"
        )
        planning_state = parsed.get("planning_state")
        if not isinstance(planning_state, dict) or set(planning_state) != {
            "block_remaining",
            "sampled_model",
        }:
            raise ValidationError("online planning snapshot is invalid")
        agent._block_remaining = _validate_non_negative_integer(
            planning_state.get("block_remaining"), "block remaining"
        )
        sampled_raw = planning_state.get("sampled_model")
        if sampled_raw is not None:
            agent._sampled_model = ProbabilityTableModel.from_dict(sampled_raw)
            agent._planner = FiniteHorizonContextPlanner(
                agent._sampled_model, horizon=agent.resampling_length
            )
        agent._rng.setstate(  # type: ignore[arg-type]
            _random_state_from_dict(parsed.get("policy_rng_state"))
        )
        agent._validate_current_state()
        try:
            if canonical_json(parsed) != agent.to_snapshot():
                raise ValidationError(
                    "online snapshot does not match replayed state"
                )
        except (TypeError, ValueError) as error:
            raise ValidationError("online snapshot is not finite") from error
        return agent


def true_probability_model(
    specification: LearnedContextWorldSpecification,
) -> ProbabilityTableModel:
    """Evaluator-only complete table for the paired oracle."""

    order = specification.true_order
    probabilities: dict[
        tuple[ContextState, str], tuple[float, float]
    ] = {}
    prefix = (False,) * (MAX_CONTEXT_ORDER - order)
    for context in all_contexts(order):
        history: FullHistory = prefix + context  # type: ignore[assignment]
        for action in CONTEXT_ACTIONS:
            probabilities[(context, action)] = (
                specification.transition_probability(history, action),
                specification.reward_probability(history, action),
            )
    return ProbabilityTableModel(order=order, probabilities=probabilities)
