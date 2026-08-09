"""Tabular task families for a cross-world transfer benchmark.

This module defines benchmark infrastructure, not a transfer capability.  The
family parameters are available to evaluator-only oracle baselines.  A future
candidate must learn its prior from source-task observations.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable

from .learned_context_lab import (
    CONTEXT_ACTIONS,
    ContextState,
    all_contexts,
    validate_context,
)
from .models import ValidationError


TRANSFER_CONTEXT_ORDER = 3
TRANSFER_TRANSITION_HIGH = 0.82
TRANSFER_TRANSITION_LOW = 0.18
TRANSFER_REWARD_HIGH = 0.72
TRANSFER_REWARD_LOW = 0.12
TRANSFER_REWARD_BACKGROUND = 0.04
TRANSFER_REWARDED_CONTEXTS = 3
TRANSFER_TRANSITION_CONCENTRATION = 18.0
TRANSFER_REWARD_CONCENTRATION = 18.0

TRANSFER_FAMILY_XOR_MASK = 0x51A7F
TRANSFER_WORLD_XOR_MASK = 0x2C91D
TRANSFER_OUTCOME_XOR_MASK = 0x73E4B


def _validate_seed(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field} must be a non-negative integer")
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


def _validate_positive(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValidationError(f"{field} must be finite and positive")
    return float(value)


def _validate_action(action: object) -> str:
    if not isinstance(action, str) or action not in CONTEXT_ACTIONS:
        raise ValidationError("transfer action is invalid")
    return action


def transfer_cell_keys() -> tuple[tuple[ContextState, str], ...]:
    return tuple(
        (context, action)
        for context in all_contexts(TRANSFER_CONTEXT_ORDER)
        for action in CONTEXT_ACTIONS
    )


@dataclass(frozen=True, slots=True)
class TransferFamilyCell:
    context: ContextState
    action: str
    transition_mean: float
    reward_mean: float

    def __post_init__(self) -> None:
        validate_context(self.context, order=TRANSFER_CONTEXT_ORDER)
        _validate_action(self.action)
        _validate_probability(self.transition_mean, "transition mean")
        _validate_probability(self.reward_mean, "reward mean")


@dataclass(frozen=True, slots=True)
class TransferFamilySpecification:
    """Hidden family parameters shared probabilistically across tasks."""

    seed: int
    cells: tuple[TransferFamilyCell, ...]
    transition_concentration: float = TRANSFER_TRANSITION_CONCENTRATION
    reward_concentration: float = TRANSFER_REWARD_CONCENTRATION

    def __post_init__(self) -> None:
        _validate_seed(self.seed, "family seed")
        _validate_positive(
            self.transition_concentration,
            "transition concentration",
        )
        _validate_positive(self.reward_concentration, "reward concentration")
        if not isinstance(self.cells, tuple):
            raise ValidationError("family cells must be a tuple")
        observed = tuple((item.context, item.action) for item in self.cells)
        if observed != transfer_cell_keys():
            raise ValidationError(
                "family cells must cover the canonical aligned table"
            )

    @classmethod
    def from_seed(cls, seed: int) -> "TransferFamilySpecification":
        validated_seed = _validate_seed(seed, "family seed")
        rng = random.Random(validated_seed ^ TRANSFER_FAMILY_XOR_MASK)
        contexts = all_contexts(TRANSFER_CONTEXT_ORDER)
        transition_means: dict[tuple[ContextState, str], float] = {}
        for context in contexts:
            amber_high = bool(rng.getrandbits(1))
            transition_means[(context, "amber")] = (
                TRANSFER_TRANSITION_HIGH
                if amber_high
                else TRANSFER_TRANSITION_LOW
            )
            transition_means[(context, "violet")] = (
                TRANSFER_TRANSITION_LOW
                if amber_high
                else TRANSFER_TRANSITION_HIGH
            )

        rewarded_contexts = set(
            rng.sample(list(contexts), TRANSFER_REWARDED_CONTEXTS)
        )
        rewarded_actions = {
            context: rng.choice(CONTEXT_ACTIONS)
            for context in rewarded_contexts
        }
        cells = tuple(
            TransferFamilyCell(
                context=context,
                action=action,
                transition_mean=transition_means[(context, action)],
                reward_mean=(
                    TRANSFER_REWARD_HIGH
                    if context in rewarded_contexts
                    and action == rewarded_actions[context]
                    else (
                        TRANSFER_REWARD_LOW
                        if context in rewarded_contexts
                        else TRANSFER_REWARD_BACKGROUND
                    )
                ),
            )
            for context, action in transfer_cell_keys()
        )
        return cls(seed=validated_seed, cells=cells)

    def cell(
        self, context: ContextState, action: str
    ) -> TransferFamilyCell:
        validate_context(context, order=TRANSFER_CONTEXT_ORDER)
        validated_action = _validate_action(action)
        index = transfer_cell_keys().index((context, validated_action))
        return self.cells[index]

    def opposed(self, *, seed: int) -> "TransferFamilySpecification":
        """Return a same-marginal family with the actionable mapping reversed."""

        validated_seed = _validate_seed(seed, "opposed family seed")
        cells = tuple(
            TransferFamilyCell(
                context=context,
                action=action,
                transition_mean=(
                    TRANSFER_TRANSITION_HIGH
                    + TRANSFER_TRANSITION_LOW
                    - self.cell(context, action).transition_mean
                ),
                reward_mean=self.cell(
                    context,
                    CONTEXT_ACTIONS[1 - CONTEXT_ACTIONS.index(action)],
                ).reward_mean,
            )
            for context, action in transfer_cell_keys()
        )
        return TransferFamilySpecification(
            seed=validated_seed,
            cells=cells,
            transition_concentration=self.transition_concentration,
            reward_concentration=self.reward_concentration,
        )


@dataclass(frozen=True, slots=True)
class TransferWorldCell:
    context: ContextState
    action: str
    transition_probability: float
    reward_probability: float

    def __post_init__(self) -> None:
        validate_context(self.context, order=TRANSFER_CONTEXT_ORDER)
        _validate_action(self.action)
        _validate_probability(
            self.transition_probability,
            "world transition probability",
        )
        _validate_probability(
            self.reward_probability,
            "world reward probability",
        )


@dataclass(frozen=True, slots=True)
class TransferWorldSpecification:
    """One task drawn independently from a hidden family."""

    family_seed: int
    world_seed: int
    cells: tuple[TransferWorldCell, ...]

    def __post_init__(self) -> None:
        _validate_seed(self.family_seed, "world family seed")
        _validate_seed(self.world_seed, "world seed")
        if not isinstance(self.cells, tuple):
            raise ValidationError("world cells must be a tuple")
        observed = tuple((item.context, item.action) for item in self.cells)
        if observed != transfer_cell_keys():
            raise ValidationError(
                "world cells must cover the canonical aligned table"
            )

    @classmethod
    def from_family(
        cls,
        family: TransferFamilySpecification,
        *,
        world_seed: int,
    ) -> "TransferWorldSpecification":
        if not isinstance(family, TransferFamilySpecification):
            raise ValidationError("world family is invalid")
        validated_seed = _validate_seed(world_seed, "world seed")
        rng = random.Random(validated_seed ^ TRANSFER_WORLD_XOR_MASK)
        cells = tuple(
            TransferWorldCell(
                context=cell.context,
                action=cell.action,
                transition_probability=rng.betavariate(
                    cell.transition_mean * family.transition_concentration,
                    (1.0 - cell.transition_mean)
                    * family.transition_concentration,
                ),
                reward_probability=rng.betavariate(
                    cell.reward_mean * family.reward_concentration,
                    (1.0 - cell.reward_mean) * family.reward_concentration,
                ),
            )
            for cell in family.cells
        )
        return cls(
            family_seed=family.seed,
            world_seed=validated_seed,
            cells=cells,
        )

    @property
    def world_id(self) -> str:
        return f"transfer-world:{self.family_seed}:{self.world_seed}"

    def cell(
        self, context: ContextState, action: str
    ) -> TransferWorldCell:
        validate_context(context, order=TRANSFER_CONTEXT_ORDER)
        validated_action = _validate_action(action)
        index = transfer_cell_keys().index((context, validated_action))
        return self.cells[index]


@dataclass(frozen=True, slots=True)
class TransferObservation:
    world_id: str
    index: int
    context: ContextState
    action: str
    next_observation: bool
    reward: bool

    def __post_init__(self) -> None:
        if not isinstance(self.world_id, str) or not self.world_id:
            raise ValidationError("observation world id is invalid")
        if (
            isinstance(self.index, bool)
            or not isinstance(self.index, int)
            or self.index < 0
        ):
            raise ValidationError("observation index is invalid")
        validate_context(self.context, order=TRANSFER_CONTEXT_ORDER)
        _validate_action(self.action)
        if not isinstance(self.next_observation, bool):
            raise ValidationError("next observation must be boolean")
        if not isinstance(self.reward, bool):
            raise ValidationError("reward must be boolean")


class AlignedTransferTask:
    """Evaluator-scheduled task that reveals only chosen-action outcomes."""

    def __init__(
        self,
        specification: TransferWorldSpecification,
        *,
        outcome_seed: int,
        public_world_id: str | None = None,
    ) -> None:
        if not isinstance(specification, TransferWorldSpecification):
            raise ValidationError("transfer world specification is invalid")
        validated_seed = _validate_seed(outcome_seed, "outcome seed")
        if public_world_id is None:
            public_world_id = specification.world_id
        if not isinstance(public_world_id, str) or not public_world_id:
            raise ValidationError("public world id is invalid")
        self.specification = specification
        self.outcome_seed = validated_seed
        self.world_id = public_world_id
        self._rng = random.Random(validated_seed ^ TRANSFER_OUTCOME_XOR_MASK)
        self._index = 0

    def act(
        self, context: ContextState, action: str
    ) -> TransferObservation:
        validate_context(context, order=TRANSFER_CONTEXT_ORDER)
        validated_action = _validate_action(action)
        cell = self.specification.cell(context, validated_action)
        observation = TransferObservation(
            world_id=self.world_id,
            index=self._index,
            context=context,
            action=validated_action,
            next_observation=(
                self._rng.random() < cell.transition_probability
            ),
            reward=self._rng.random() < cell.reward_probability,
        )
        self._index += 1
        return observation


@dataclass(frozen=True, slots=True)
class BetaPrior:
    alpha: float
    beta: float

    def __post_init__(self) -> None:
        _validate_positive(self.alpha, "prior alpha")
        _validate_positive(self.beta, "prior beta")

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)


@dataclass(frozen=True, slots=True)
class TransferCellPrior:
    context: ContextState
    action: str
    transition: BetaPrior
    reward: BetaPrior

    def __post_init__(self) -> None:
        validate_context(self.context, order=TRANSFER_CONTEXT_ORDER)
        _validate_action(self.action)
        if not isinstance(self.transition, BetaPrior):
            raise ValidationError("transition prior is invalid")
        if not isinstance(self.reward, BetaPrior):
            raise ValidationError("reward prior is invalid")


@dataclass(frozen=True, slots=True)
class TransferPrior:
    provenance: str
    cells: tuple[TransferCellPrior, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, str) or not self.provenance:
            raise ValidationError("prior provenance is invalid")
        if not isinstance(self.cells, tuple):
            raise ValidationError("prior cells must be a tuple")
        observed = tuple((item.context, item.action) for item in self.cells)
        if observed != transfer_cell_keys():
            raise ValidationError(
                "prior cells must cover the canonical aligned table"
            )

    @classmethod
    def scratch(cls) -> "TransferPrior":
        return cls(
            provenance="scratch:beta-1-1",
            cells=tuple(
                TransferCellPrior(
                    context=context,
                    action=action,
                    transition=BetaPrior(1.0, 1.0),
                    reward=BetaPrior(1.0, 1.0),
                )
                for context, action in transfer_cell_keys()
            ),
        )

    @classmethod
    def oracle(
        cls, family: TransferFamilySpecification
    ) -> "TransferPrior":
        if not isinstance(family, TransferFamilySpecification):
            raise ValidationError("oracle family is invalid")
        return cls(
            provenance=f"evaluator-oracle-family:{family.seed}",
            cells=tuple(
                TransferCellPrior(
                    context=cell.context,
                    action=cell.action,
                    transition=BetaPrior(
                        cell.transition_mean
                        * family.transition_concentration,
                        (1.0 - cell.transition_mean)
                        * family.transition_concentration,
                    ),
                    reward=BetaPrior(
                        cell.reward_mean * family.reward_concentration,
                        (1.0 - cell.reward_mean)
                        * family.reward_concentration,
                    ),
                )
                for cell in family.cells
            ),
        )

    def cell(
        self, context: ContextState, action: str
    ) -> TransferCellPrior:
        validate_context(context, order=TRANSFER_CONTEXT_ORDER)
        validated_action = _validate_action(action)
        index = transfer_cell_keys().index((context, validated_action))
        return self.cells[index]


@dataclass(frozen=True, slots=True)
class TransferForecast:
    world_id: str
    index: int
    context: ContextState
    action: str
    transition_probability: float
    reward_probability: float

    def __post_init__(self) -> None:
        if not isinstance(self.world_id, str) or not self.world_id:
            raise ValidationError("forecast world id is invalid")
        if (
            isinstance(self.index, bool)
            or not isinstance(self.index, int)
            or self.index < 0
        ):
            raise ValidationError("forecast index is invalid")
        validate_context(self.context, order=TRANSFER_CONTEXT_ORDER)
        _validate_action(self.action)
        _validate_probability(
            self.transition_probability,
            "forecast transition probability",
        )
        _validate_probability(
            self.reward_probability,
            "forecast reward probability",
        )


class PrequentialTransferModel:
    """Prior plus target-only counts with predict-before-observe ordering."""

    def __init__(self, *, world_id: str, prior: TransferPrior) -> None:
        if not isinstance(world_id, str) or not world_id:
            raise ValidationError("model world id is invalid")
        if not isinstance(prior, TransferPrior):
            raise ValidationError("model prior is invalid")
        self.world_id = world_id
        self.prior = prior
        self._counts = {
            key: [0, 0, 0, 0] for key in transfer_cell_keys()
        }
        self._archive: list[TransferObservation] = []
        self._pending: TransferForecast | None = None

    @property
    def archive(self) -> tuple[TransferObservation, ...]:
        return tuple(self._archive)

    @property
    def pending(self) -> TransferForecast | None:
        return self._pending

    def peek(
        self, context: ContextState, action: str
    ) -> TransferForecast:
        if self._pending is not None:
            raise ValidationError("pending transfer forecast must be observed")
        validate_context(context, order=TRANSFER_CONTEXT_ORDER)
        validated_action = _validate_action(action)
        key = (context, validated_action)
        counts = self._counts[key]
        prior = self.prior.cell(context, validated_action)
        return TransferForecast(
            world_id=self.world_id,
            index=len(self._archive),
            context=context,
            action=validated_action,
            transition_probability=(
                prior.transition.alpha + counts[0]
            )
            / (
                prior.transition.alpha
                + prior.transition.beta
                + counts[0]
                + counts[1]
            ),
            reward_probability=(prior.reward.alpha + counts[2])
            / (
                prior.reward.alpha
                + prior.reward.beta
                + counts[2]
                + counts[3]
            ),
        )

    def forecast(
        self, context: ContextState, action: str
    ) -> TransferForecast:
        forecast = self.peek(context, action)
        self._pending = forecast
        return forecast

    def observe(self, observation: TransferObservation) -> None:
        if not isinstance(observation, TransferObservation):
            raise ValidationError("transfer observation is invalid")
        if self._pending is None:
            raise ValidationError("transfer observation has no forecast")
        expected = self._pending
        if (
            observation.world_id != expected.world_id
            or observation.index != expected.index
            or observation.context != expected.context
            or observation.action != expected.action
        ):
            raise ValidationError("transfer observation does not match forecast")
        key = (observation.context, observation.action)
        counts = self._counts[key]
        counts[0 if observation.next_observation else 1] += 1
        counts[2 if observation.reward else 3] += 1
        self._archive.append(observation)
        self._pending = None


def balanced_transfer_schedule(
    *, cycles: int, seed: int
) -> tuple[tuple[ContextState, str], ...]:
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1:
        raise ValidationError("schedule cycles must be positive")
    validated_seed = _validate_seed(seed, "schedule seed")
    rng = random.Random(validated_seed)
    result: list[tuple[ContextState, str]] = []
    keys = list(transfer_cell_keys())
    for _ in range(cycles):
        rng.shuffle(keys)
        result.extend(keys)
    return tuple(result)


def require_disjoint_seed_sets(
    **families: Iterable[int],
) -> dict[str, tuple[int, ...]]:
    normalized: dict[str, tuple[int, ...]] = {}
    seen: dict[int, str] = {}
    for name, values in families.items():
        items = tuple(values)
        if not items or len(set(items)) != len(items):
            raise ValidationError(f"{name} seeds must be non-empty and unique")
        for item in items:
            seed = _validate_seed(item, f"{name} seed")
            if seed in seen:
                raise ValidationError(
                    f"seed overlap between {seen[seed]} and {name}"
                )
            seen[seed] = name
        normalized[name] = items
    return normalized
