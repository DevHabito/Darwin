"""Blockwise Monte Carlo information-directed control for Darwin H50-L13.

The implementation is a finite-sample tabular approximation.  It does not
inherit published IDS regret bounds and does not implement general intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Sequence

from .learned_context_lab import (
    CONTEXT_ACTIONS,
    FullHistory,
    append_observation,
    validate_full_history,
)
from .models import ValidationError, canonical_json, parse_json, require_text
from .online_posterior_lab import (
    ONLINE_ENVIRONMENT_EPISODE_LENGTH,
    FiniteHorizonContextPlanner,
    OnlineBayesianModel,
    OnlineExperience,
    ProbabilityTableModel,
    _random_state_from_dict,
    _random_state_to_dict,
)


IDS_POSTERIOR_SAMPLE_COUNT = 16
IDS_EPSILON = 1e-15
IDS_OUTCOMES = (
    (False, False),
    (False, True),
    (True, False),
    (True, True),
)


def _validate_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    return require_text(value, field)


def _validate_integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"{field} must be an integer at least {minimum}")
    return value


def _validate_probability(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValidationError(f"{field} must be a finite probability")
    return float(value)


def _validate_non_negative(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or float(value) < 0.0
    ):
        raise ValidationError(f"{field} must be finite and non-negative")
    return float(value)


def _validate_action(value: object) -> str:
    if not isinstance(value, str) or value not in CONTEXT_ACTIONS:
        raise ValidationError("information-directed action is invalid")
    return value


@dataclass(frozen=True, slots=True)
class InformationDirectedDecision:
    """One pre-outcome action and its finite-sample IDS diagnostics."""

    action: str
    amber_probability: float
    expected_regret: float
    information_gain: float
    information_ratio: float | None
    amber_expected_regret: float
    violet_expected_regret: float
    amber_information_gain: float
    violet_information_gain: float

    FIELDS = frozenset(
        {
            "action",
            "amber_probability",
            "expected_regret",
            "information_gain",
            "information_ratio",
            "amber_expected_regret",
            "violet_expected_regret",
            "amber_information_gain",
            "violet_information_gain",
        }
    )

    def __post_init__(self) -> None:
        _validate_action(self.action)
        probability = _validate_probability(
            self.amber_probability, "amber probability"
        )
        for name in (
            "expected_regret",
            "information_gain",
            "amber_expected_regret",
            "violet_expected_regret",
            "amber_information_gain",
            "violet_information_gain",
        ):
            _validate_non_negative(getattr(self, name), name)
        if self.information_ratio is not None:
            _validate_non_negative(self.information_ratio, "information ratio")
        if probability == 1.0 and self.action != "amber":
            raise ValidationError("deterministic amber mixture chose violet")
        if probability == 0.0 and self.action != "violet":
            raise ValidationError("deterministic violet mixture chose amber")

    @property
    def finite_diagnostic(self) -> bool:
        return self.information_ratio is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "amber_probability": self.amber_probability,
            "expected_regret": self.expected_regret,
            "information_gain": self.information_gain,
            "information_ratio": self.information_ratio,
            "amber_expected_regret": self.amber_expected_regret,
            "violet_expected_regret": self.violet_expected_regret,
            "amber_information_gain": self.amber_information_gain,
            "violet_information_gain": self.violet_information_gain,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "InformationDirectedDecision":
        if not isinstance(raw, dict) or set(raw) != cls.FIELDS:
            raise ValidationError("information-directed decision fields are invalid")
        ratio = raw.get("information_ratio")
        if ratio is not None and (
            isinstance(ratio, bool) or not isinstance(ratio, (int, float))
        ):
            raise ValidationError("information ratio must be numeric or null")
        return cls(
            action=raw.get("action"),  # type: ignore[arg-type]
            amber_probability=raw.get("amber_probability"),  # type: ignore[arg-type]
            expected_regret=raw.get("expected_regret"),  # type: ignore[arg-type]
            information_gain=raw.get("information_gain"),  # type: ignore[arg-type]
            information_ratio=(None if ratio is None else float(ratio)),
            amber_expected_regret=raw.get(  # type: ignore[arg-type]
                "amber_expected_regret"
            ),
            violet_expected_regret=raw.get(  # type: ignore[arg-type]
                "violet_expected_regret"
            ),
            amber_information_gain=raw.get(  # type: ignore[arg-type]
                "amber_information_gain"
            ),
            violet_information_gain=raw.get(  # type: ignore[arg-type]
                "violet_information_gain"
            ),
        )


@dataclass(frozen=True, slots=True)
class _MixtureStatistics:
    amber_probability: float
    expected_regret: float
    information_gain: float
    information_ratio: float | None
    amber_expected_regret: float
    violet_expected_regret: float
    amber_information_gain: float
    violet_information_gain: float


def _outcome_probability(
    model: ProbabilityTableModel,
    history: FullHistory,
    action: str,
    outcome: tuple[bool, bool],
) -> float:
    context = model.context_for_history(history)
    transition = model.transition_probability(context, action)
    reward = model.reward_probability(context, action)
    next_observation, rewarded = outcome
    transition_factor = transition if next_observation else 1.0 - transition
    reward_factor = reward if rewarded else 1.0 - reward
    probability = transition_factor * reward_factor
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValidationError("sampled outcome probability is invalid")
    return probability


def _action_information_gain(
    models: Sequence[ProbabilityTableModel],
    optimal_actions: Sequence[str],
    history: FullHistory,
    action: str,
) -> float:
    if not models or len(models) != len(optimal_actions):
        raise ValidationError("IDS ensemble is incomplete")
    sample_count = len(models)
    joint = {
        (optimal, outcome): 0.0
        for optimal in CONTEXT_ACTIONS
        for outcome in IDS_OUTCOMES
    }
    optimal_mass = {
        optimal: sum(value == optimal for value in optimal_actions) / sample_count
        for optimal in CONTEXT_ACTIONS
    }
    for model, optimal in zip(models, optimal_actions, strict=True):
        for outcome in IDS_OUTCOMES:
            joint[(optimal, outcome)] += (
                _outcome_probability(model, history, action, outcome)
                / sample_count
            )
    outcome_mass = {
        outcome: sum(joint[(optimal, outcome)] for optimal in CONTEXT_ACTIONS)
        for outcome in IDS_OUTCOMES
    }
    information_gain = 0.0
    for optimal in CONTEXT_ACTIONS:
        for outcome in IDS_OUTCOMES:
            probability = joint[(optimal, outcome)]
            denominator = optimal_mass[optimal] * outcome_mass[outcome]
            if probability > 0.0:
                if denominator <= 0.0:
                    raise ValidationError("IDS mutual information is undefined")
                information_gain += probability * math.log(
                    probability / denominator
                )
    if information_gain < -1e-12 or not math.isfinite(information_gain):
        raise ValidationError("IDS mutual information is invalid")
    return max(0.0, information_gain)


def _candidate_mixture_probabilities(
    amber_regret: float,
    violet_regret: float,
    amber_gain: float,
    violet_gain: float,
) -> tuple[float, ...]:
    values = {0.0, 1.0}
    regret_slope = amber_regret - violet_regret
    gain_slope = amber_gain - violet_gain
    if abs(regret_slope) > IDS_EPSILON:
        zero_regret = -violet_regret / regret_slope
        if 0.0 <= zero_regret <= 1.0:
            values.add(min(1.0, max(0.0, zero_regret)))
    if (
        abs(regret_slope) > IDS_EPSILON
        and abs(gain_slope) > IDS_EPSILON
    ):
        stationary = (
            gain_slope * violet_regret
            - 2.0 * regret_slope * violet_gain
        ) / (regret_slope * gain_slope)
        if 0.0 <= stationary <= 1.0:
            values.add(min(1.0, max(0.0, stationary)))
    return tuple(sorted(values))


def _mixture_statistics(
    models: Sequence[ProbabilityTableModel],
    planners: Sequence[FiniteHorizonContextPlanner],
    history: FullHistory,
    *,
    remaining: int,
) -> _MixtureStatistics:
    validate_full_history(history)
    if (
        not models
        or len(models) != len(planners)
        or any(planner.model != model for model, planner in zip(models, planners))
    ):
        raise ValidationError("IDS models and planners disagree")
    q_values = {
        action: [] for action in CONTEXT_ACTIONS
    }
    optimal_actions: list[str] = []
    for model, planner in zip(models, planners, strict=True):
        context = model.context_for_history(history)
        model_q = {
            action: planner.q_value(context, action, remaining=remaining)
            for action in CONTEXT_ACTIONS
        }
        for action in CONTEXT_ACTIONS:
            q_values[action].append(model_q[action])
        optimal_actions.append(
            max(
                CONTEXT_ACTIONS,
                key=lambda action: (
                    model_q[action],
                    -CONTEXT_ACTIONS.index(action),
                ),
            )
        )
    regrets = {
        action: sum(
            max(q_values[other][index] for other in CONTEXT_ACTIONS)
            - q_values[action][index]
            for index in range(len(models))
        )
        / len(models)
        for action in CONTEXT_ACTIONS
    }
    gains = {
        action: _action_information_gain(
            models, optimal_actions, history, action
        )
        for action in CONTEXT_ACTIONS
    }
    amber_regret = regrets["amber"]
    violet_regret = regrets["violet"]
    amber_gain = gains["amber"]
    violet_gain = gains["violet"]

    def values(probability: float) -> tuple[float, float, float]:
        regret = (
            probability * amber_regret
            + (1.0 - probability) * violet_regret
        )
        gain = (
            probability * amber_gain
            + (1.0 - probability) * violet_gain
        )
        if gain <= IDS_EPSILON:
            score = 0.0 if regret <= IDS_EPSILON else math.inf
        else:
            score = regret * regret / gain
        return regret, gain, score

    candidates = _candidate_mixture_probabilities(
        amber_regret, violet_regret, amber_gain, violet_gain
    )
    selected = min(
        candidates,
        key=lambda probability: (
            values(probability)[2],
            values(probability)[0],
            -probability,
        ),
    )
    regret, gain, score = values(selected)
    return _MixtureStatistics(
        amber_probability=selected,
        expected_regret=max(0.0, regret),
        information_gain=max(0.0, gain),
        information_ratio=(score if math.isfinite(score) else None),
        amber_expected_regret=max(0.0, amber_regret),
        violet_expected_regret=max(0.0, violet_regret),
        amber_information_gain=max(0.0, amber_gain),
        violet_information_gain=max(0.0, violet_gain),
    )


class InformationDirectedAgent:
    """Causal blockwise Monte Carlo IDS agent with exact snapshots."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        world_id: str,
        model_seed: int,
        action_seed: int,
        block_length: int,
        sample_count: int = IDS_POSTERIOR_SAMPLE_COUNT,
    ) -> None:
        self.world_id = _validate_text(world_id, "world id")
        self.model_seed = _validate_integer(model_seed, "model seed")
        self.action_seed = _validate_integer(action_seed, "action seed")
        self.block_length = _validate_integer(
            block_length, "block length", minimum=1
        )
        self.sample_count = _validate_integer(
            sample_count, "sample count", minimum=1
        )
        if ONLINE_ENVIRONMENT_EPISODE_LENGTH % self.block_length != 0:
            raise ValidationError(
                "IDS block length must divide the environment episode"
            )
        self.model = OnlineBayesianModel(world_id=self.world_id)
        self._model_rng = random.Random(self.model_seed)
        self._action_rng = random.Random(self.action_seed)
        self._episode_index = 0
        self._step_index = 0
        self._history: FullHistory | None = None
        self._block_remaining = 0
        self._models: tuple[ProbabilityTableModel, ...] = ()
        self._planners: tuple[FiniteHorizonContextPlanner, ...] = ()
        self._pending_decision: InformationDirectedDecision | None = None

    @property
    def current_history(self) -> FullHistory:
        if self._history is None:
            raise RuntimeError("IDS environment episode has not started")
        return self._history

    @property
    def block_remaining(self) -> int:
        return self._block_remaining

    @property
    def pending_decision(self) -> InformationDirectedDecision | None:
        return self._pending_decision

    def begin_episode(
        self, *, episode_index: int, initial_history: FullHistory
    ) -> None:
        validate_full_history(initial_history, "IDS initial history")
        validated_index = _validate_integer(
            episode_index, "episode index", minimum=1
        )
        if self._pending_decision is not None:
            raise ValidationError("cannot reset IDS with a pending action")
        if self._episode_index == 0:
            if validated_index != 1 or self.model.archive.items:
                raise ValidationError("IDS run must begin at episode one")
        elif (
            self._step_index != ONLINE_ENVIRONMENT_EPISODE_LENGTH
            or validated_index != self._episode_index + 1
            or self._block_remaining != 0
        ):
            raise ValidationError("IDS episode reset is discontinuous")
        self._episode_index = validated_index
        self._step_index = 0
        self._history = initial_history

    def _start_block(self) -> None:
        self._models = tuple(
            self.model.sampled_model(self._model_rng)
            for _ in range(self.sample_count)
        )
        self._planners = tuple(
            FiniteHorizonContextPlanner(model, horizon=self.block_length)
            for model in self._models
        )
        self._block_remaining = self.block_length

    def _statistics(self) -> _MixtureStatistics:
        if self._history is None or self._block_remaining < 1:
            raise RuntimeError("IDS planning state is unavailable")
        return _mixture_statistics(
            self._models,
            self._planners,
            self._history,
            remaining=self._block_remaining,
        )

    def action(self) -> InformationDirectedDecision:
        if self._history is None or self._episode_index < 1:
            raise RuntimeError("IDS environment episode has not started")
        if self._step_index >= ONLINE_ENVIRONMENT_EPISODE_LENGTH:
            raise RuntimeError("IDS environment episode is complete")
        if self._pending_decision is not None:
            raise ValidationError("IDS pending action has not been observed")
        if self._block_remaining == 0:
            self._start_block()
        statistics = self._statistics()
        action = (
            "amber"
            if self._action_rng.random() < statistics.amber_probability
            else "violet"
        )
        self._pending_decision = InformationDirectedDecision(
            action=action,
            amber_probability=statistics.amber_probability,
            expected_regret=statistics.expected_regret,
            information_gain=statistics.information_gain,
            information_ratio=statistics.information_ratio,
            amber_expected_regret=statistics.amber_expected_regret,
            violet_expected_regret=statistics.violet_expected_regret,
            amber_information_gain=statistics.amber_information_gain,
            violet_information_gain=statistics.violet_information_gain,
        )
        return self._pending_decision

    def observe(self, *, next_observation: bool, reward: bool) -> float:
        if self._history is None or self._pending_decision is None:
            raise ValidationError("IDS observation has no pending action")
        if not isinstance(next_observation, bool) or not isinstance(reward, bool):
            raise ValidationError("IDS outcomes must be boolean")
        experience = OnlineExperience(
            world_id=self.world_id,
            sequence=len(self.model.archive.items) + 1,
            episode_index=self._episode_index,
            step_index=self._step_index,
            history=self._history,
            action=self._pending_decision.action,
            next_observation=next_observation,
            reward=reward,
        )
        information_gain = self.model.update(experience)
        self._history = append_observation(self._history, next_observation)
        self._step_index += 1
        self._block_remaining -= 1
        self._pending_decision = None
        if self._block_remaining == 0:
            self._models = ()
            self._planners = ()
        return information_gain

    def _validate_current_state(self) -> None:
        if self._history is None or self._episode_index < 1:
            raise ValidationError("IDS snapshot needs an active episode")
        if not 0 <= self._step_index <= ONLINE_ENVIRONMENT_EPISODE_LENGTH:
            raise ValidationError("IDS snapshot step index is invalid")
        archive = self.model.archive.items
        if not archive:
            if self._episode_index != 1 or self._step_index != 0:
                raise ValidationError("empty IDS archive state is inconsistent")
        else:
            last = archive[-1]
            if self._episode_index == last.episode_index:
                if (
                    self._step_index != last.step_index + 1
                    or self._history != last.next_history
                ):
                    raise ValidationError("IDS snapshot history disagrees")
            elif self._episode_index == last.episode_index + 1:
                if (
                    last.step_index != ONLINE_ENVIRONMENT_EPISODE_LENGTH - 1
                    or self._step_index != 0
                ):
                    raise ValidationError("IDS snapshot reset disagrees")
            else:
                raise ValidationError("IDS snapshot episode is discontinuous")
        observed = len(archive)
        remainder = observed % self.block_length
        expected_remaining = (
            self.block_length if remainder == 0 else self.block_length - remainder
        )
        if self._pending_decision is None and remainder == 0:
            expected_remaining = 0
        if self._block_remaining != expected_remaining:
            raise ValidationError("IDS planning-block clock is inconsistent")
        if self._block_remaining == 0:
            if self._models or self._planners or self._pending_decision is not None:
                raise ValidationError("inactive IDS block retained planning state")
        elif (
            len(self._models) != self.sample_count
            or len(self._planners) != self.sample_count
        ):
            raise ValidationError("active IDS block has an incomplete ensemble")

    def to_snapshot(self) -> str:
        self._validate_current_state()
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "world_id": self.world_id,
                "model_seed": self.model_seed,
                "action_seed": self.action_seed,
                "block_length": self.block_length,
                "sample_count": self.sample_count,
                "model": self.model.to_dict(),
                "model_rng_state": _random_state_to_dict(
                    self._model_rng.getstate()
                ),
                "action_rng_state": _random_state_to_dict(
                    self._action_rng.getstate()
                ),
                "episode_index": self._episode_index,
                "step_index": self._step_index,
                "history": list(self.current_history),
                "block_remaining": self._block_remaining,
                "ensemble": [model.to_dict() for model in self._models],
                "pending_decision": (
                    None
                    if self._pending_decision is None
                    else self._pending_decision.to_dict()
                ),
            }
        )

    @classmethod
    def from_snapshot(cls, payload: str) -> "InformationDirectedAgent":
        raw = parse_json(payload)
        fields = {
            "schema",
            "world_id",
            "model_seed",
            "action_seed",
            "block_length",
            "sample_count",
            "model",
            "model_rng_state",
            "action_rng_state",
            "episode_index",
            "step_index",
            "history",
            "block_remaining",
            "ensemble",
            "pending_decision",
        }
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValidationError("IDS snapshot fields are invalid")
        if raw.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("IDS snapshot schema is invalid")
        agent = cls(
            world_id=raw.get("world_id"),  # type: ignore[arg-type]
            model_seed=raw.get("model_seed"),  # type: ignore[arg-type]
            action_seed=raw.get("action_seed"),  # type: ignore[arg-type]
            block_length=raw.get("block_length"),  # type: ignore[arg-type]
            sample_count=raw.get("sample_count"),  # type: ignore[arg-type]
        )
        agent.model = OnlineBayesianModel.from_dict(raw.get("model"))
        if agent.model.world_id != agent.world_id:
            raise ValidationError("IDS snapshot model belongs to another world")
        agent._model_rng.setstate(  # type: ignore[arg-type]
            _random_state_from_dict(raw.get("model_rng_state"))
        )
        agent._action_rng.setstate(  # type: ignore[arg-type]
            _random_state_from_dict(raw.get("action_rng_state"))
        )
        agent._episode_index = _validate_integer(
            raw.get("episode_index"), "episode index", minimum=1
        )
        agent._step_index = _validate_integer(
            raw.get("step_index"), "step index"
        )
        history = raw.get("history")
        if not isinstance(history, list):
            raise ValidationError("IDS snapshot history must be a list")
        agent._history = validate_full_history(
            tuple(history), "IDS snapshot history"
        )
        agent._block_remaining = _validate_integer(
            raw.get("block_remaining"), "block remaining"
        )
        ensemble = raw.get("ensemble")
        if not isinstance(ensemble, list):
            raise ValidationError("IDS snapshot ensemble must be a list")
        agent._models = tuple(
            ProbabilityTableModel.from_dict(item) for item in ensemble
        )
        agent._planners = tuple(
            FiniteHorizonContextPlanner(model, horizon=agent.block_length)
            for model in agent._models
        )
        pending = raw.get("pending_decision")
        agent._pending_decision = (
            None
            if pending is None
            else InformationDirectedDecision.from_dict(pending)
        )
        agent._validate_current_state()
        if agent._pending_decision is not None:
            expected = agent._statistics()
            pending_decision = agent._pending_decision
            expected_values = (
                expected.amber_probability,
                expected.expected_regret,
                expected.information_gain,
                expected.information_ratio,
                expected.amber_expected_regret,
                expected.violet_expected_regret,
                expected.amber_information_gain,
                expected.violet_information_gain,
            )
            observed_values = (
                pending_decision.amber_probability,
                pending_decision.expected_regret,
                pending_decision.information_gain,
                pending_decision.information_ratio,
                pending_decision.amber_expected_regret,
                pending_decision.violet_expected_regret,
                pending_decision.amber_information_gain,
                pending_decision.violet_information_gain,
            )
            if expected_values != observed_values:
                raise ValidationError("IDS pending diagnostics disagree")
        if canonical_json(raw) != agent.to_snapshot():
            raise ValidationError("IDS snapshot is not canonical")
        return agent
