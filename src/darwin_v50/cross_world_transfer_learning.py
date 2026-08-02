"""Source-learned priors and compatibility gating for transfer development.

The learner consumes chosen-action summaries from source tasks.  It never
receives hidden family or target parameters.  This module is development
infrastructure and does not register H50-L14.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .cross_world_transfer_lab import (
    AlignedTransferTask,
    BetaPrior,
    PrequentialTransferModel,
    TransferCellPrior,
    TransferFamilySpecification,
    TransferForecast,
    TransferObservation,
    TransferPrior,
    TransferWorldSpecification,
    balanced_transfer_schedule,
    transfer_cell_keys,
)
from .learned_context_lab import ContextState
from .models import ValidationError


SOURCE_CONCENTRATION_CANDIDATES = (
    1.0,
    2.0,
    4.0,
    8.0,
    12.0,
    18.0,
    24.0,
    32.0,
    48.0,
    64.0,
)
SOURCE_WORLD_XOR_MASK = 0x6A12F
SOURCE_OUTCOME_XOR_MASK = 0x31D87
SOURCE_SCHEDULE_XOR_MASK = 0x574CB
SOURCE_INDEX_MULTIPLIER = 0x9E3779B1


def _validate_non_negative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class SourceCellEvidence:
    context: ContextState
    action: str
    transition_successes: int
    reward_successes: int
    trials: int

    def __post_init__(self) -> None:
        if (self.context, self.action) not in transfer_cell_keys():
            raise ValidationError("source cell key is invalid")
        for field, value in (
            ("transition successes", self.transition_successes),
            ("reward successes", self.reward_successes),
            ("trials", self.trials),
        ):
            _validate_non_negative_integer(value, field)
        if self.trials < 1:
            raise ValidationError("source cell must contain evidence")
        if (
            self.transition_successes > self.trials
            or self.reward_successes > self.trials
        ):
            raise ValidationError("source successes exceed trials")


@dataclass(frozen=True, slots=True)
class SourceTaskEvidence:
    world_id: str
    cells: tuple[SourceCellEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.world_id, str) or not self.world_id:
            raise ValidationError("source world id is invalid")
        if not isinstance(self.cells, tuple) or tuple(
            (item.context, item.action) for item in self.cells
        ) != transfer_cell_keys():
            raise ValidationError("source task cells are not canonical")

    @property
    def interactions(self) -> int:
        return sum(item.trials for item in self.cells)


def collect_source_task_evidence(
    family: TransferFamilySpecification,
    *,
    base_seed: int,
    task_index: int,
    cycles: int,
) -> SourceTaskEvidence:
    if not isinstance(family, TransferFamilySpecification):
        raise ValidationError("source family is invalid")
    validated_seed = _validate_non_negative_integer(base_seed, "source seed")
    validated_index = _validate_non_negative_integer(
        task_index, "source task index"
    )
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1:
        raise ValidationError("source cycles must be positive")
    stream = validated_index * SOURCE_INDEX_MULTIPLIER
    specification = TransferWorldSpecification.from_family(
        family,
        world_seed=validated_seed ^ SOURCE_WORLD_XOR_MASK ^ stream,
    )
    task = AlignedTransferTask(
        specification,
        outcome_seed=validated_seed ^ SOURCE_OUTCOME_XOR_MASK ^ stream,
        public_world_id=f"source-task:{validated_index}",
    )
    mutable = {key: [0, 0, 0] for key in transfer_cell_keys()}
    schedule = balanced_transfer_schedule(
        cycles=cycles,
        seed=validated_seed ^ SOURCE_SCHEDULE_XOR_MASK ^ stream,
    )
    for context, action in schedule:
        observation = task.act(context, action)
        counts = mutable[(context, action)]
        counts[0] += int(observation.next_observation)
        counts[1] += int(observation.reward)
        counts[2] += 1
    return SourceTaskEvidence(
        world_id=task.world_id,
        cells=tuple(
            SourceCellEvidence(
                context=context,
                action=action,
                transition_successes=mutable[(context, action)][0],
                reward_successes=mutable[(context, action)][1],
                trials=mutable[(context, action)][2],
            )
            for context, action in transfer_cell_keys()
        ),
    )


def collect_source_family_evidence(
    family: TransferFamilySpecification,
    *,
    base_seed: int,
    task_count: int,
    cycles: int,
) -> tuple[SourceTaskEvidence, ...]:
    if (
        isinstance(task_count, bool)
        or not isinstance(task_count, int)
        or task_count < 2
    ):
        raise ValidationError("source task count must be at least two")
    tasks = tuple(
        collect_source_task_evidence(
            family,
            base_seed=base_seed,
            task_index=index,
            cycles=cycles,
        )
        for index in range(task_count)
    )
    if len({item.world_id for item in tasks}) != len(tasks):
        raise ValidationError("source task identities must be unique")
    return tasks


def _beta_binomial_log_probability(
    *, successes: int, trials: int, mean: float, concentration: float
) -> float:
    alpha = mean * concentration
    beta = (1.0 - mean) * concentration
    return (
        math.lgamma(trials + 1)
        - math.lgamma(successes + 1)
        - math.lgamma(trials - successes + 1)
        + math.lgamma(successes + alpha)
        + math.lgamma(trials - successes + beta)
        - math.lgamma(trials + alpha + beta)
        + math.lgamma(alpha + beta)
        - math.lgamma(alpha)
        - math.lgamma(beta)
    )


def _fit_beta_prior(
    successes_and_trials: Iterable[tuple[int, int]],
) -> BetaPrior:
    observations = tuple(successes_and_trials)
    if len(observations) < 2:
        raise ValidationError("Beta-Binomial fit needs at least two tasks")
    total_successes = 0
    total_trials = 0
    for successes, trials in observations:
        _validate_non_negative_integer(successes, "fit successes")
        _validate_non_negative_integer(trials, "fit trials")
        if trials < 1 or successes > trials:
            raise ValidationError("Beta-Binomial observation is invalid")
        total_successes += successes
        total_trials += trials
    mean = (total_successes + 0.5) / (total_trials + 1.0)
    concentration = max(
        SOURCE_CONCENTRATION_CANDIDATES,
        key=lambda candidate: (
            sum(
                _beta_binomial_log_probability(
                    successes=successes,
                    trials=trials,
                    mean=mean,
                    concentration=candidate,
                )
                for successes, trials in observations
            ),
            -candidate,
        ),
    )
    return BetaPrior(
        alpha=mean * concentration,
        beta=(1.0 - mean) * concentration,
    )


def learn_transfer_prior(
    tasks: Iterable[SourceTaskEvidence],
) -> TransferPrior:
    evidence = tuple(tasks)
    if len(evidence) < 2:
        raise ValidationError("transfer prior needs at least two source tasks")
    if len({item.world_id for item in evidence}) != len(evidence):
        raise ValidationError("source task evidence cannot be replayed")
    cells: list[TransferCellPrior] = []
    for cell_index, (context, action) in enumerate(transfer_cell_keys()):
        rows = tuple(item.cells[cell_index] for item in evidence)
        if any(
            (item.context, item.action) != (context, action) for item in rows
        ):
            raise ValidationError("source task alignment is inconsistent")
        cells.append(
            TransferCellPrior(
                context=context,
                action=action,
                transition=_fit_beta_prior(
                    (item.transition_successes, item.trials)
                    for item in rows
                ),
                reward=_fit_beta_prior(
                    (item.reward_successes, item.trials) for item in rows
                ),
            )
        )
    source_interactions = sum(item.interactions for item in evidence)
    return TransferPrior(
        provenance=(
            f"learned-beta-binomial:tasks={len(evidence)}:"
            f"interactions={source_interactions}"
        ),
        cells=tuple(cells),
    )


def pooled_source_prior(
    tasks: Iterable[SourceTaskEvidence],
) -> TransferPrior:
    """Naive control that treats all source outcomes as one target task."""

    evidence = tuple(tasks)
    if len(evidence) < 2:
        raise ValidationError("pooled prior needs at least two source tasks")
    if len({item.world_id for item in evidence}) != len(evidence):
        raise ValidationError("pooled source evidence cannot be replayed")
    cells: list[TransferCellPrior] = []
    for cell_index, (context, action) in enumerate(transfer_cell_keys()):
        rows = tuple(item.cells[cell_index] for item in evidence)
        total_trials = sum(item.trials for item in rows)
        transition_successes = sum(
            item.transition_successes for item in rows
        )
        reward_successes = sum(item.reward_successes for item in rows)
        cells.append(
            TransferCellPrior(
                context=context,
                action=action,
                transition=BetaPrior(
                    1.0 + transition_successes,
                    1.0 + total_trials - transition_successes,
                ),
                reward=BetaPrior(
                    1.0 + reward_successes,
                    1.0 + total_trials - reward_successes,
                ),
            )
        )
    return TransferPrior(
        provenance=f"naive-pooled-source:tasks={len(evidence)}",
        cells=tuple(cells),
    )


class GatedTransferModel:
    """Bayesian mixture of a source-learned model and scratch learning."""

    def __init__(
        self,
        *,
        world_id: str,
        source_prior: TransferPrior,
        initial_source_weight: float,
    ) -> None:
        if (
            isinstance(initial_source_weight, bool)
            or not isinstance(initial_source_weight, (int, float))
            or not math.isfinite(initial_source_weight)
            or not 0.0 < initial_source_weight < 1.0
        ):
            raise ValidationError("initial source weight must be within (0, 1)")
        self.world_id = world_id
        self.source_prior = source_prior
        self.initial_source_weight = float(initial_source_weight)
        self._log_source_weight = math.log(self.initial_source_weight)
        self._log_scratch_weight = math.log(1.0 - self.initial_source_weight)
        self._source = PrequentialTransferModel(
            world_id=world_id,
            prior=source_prior,
        )
        self._scratch = PrequentialTransferModel(
            world_id=world_id,
            prior=TransferPrior.scratch(),
        )
        self._pending: tuple[
            TransferForecast, TransferForecast, TransferForecast
        ] | None = None
        self._weight_history: list[float] = []

    @property
    def source_weight(self) -> float:
        maximum = max(self._log_source_weight, self._log_scratch_weight)
        source = math.exp(self._log_source_weight - maximum)
        scratch = math.exp(self._log_scratch_weight - maximum)
        return source / (source + scratch)

    @property
    def weight_history(self) -> tuple[float, ...]:
        return tuple(self._weight_history)

    @property
    def archive(self) -> tuple[TransferObservation, ...]:
        if self._source.archive != self._scratch.archive:
            raise ValidationError("gated model archives disagree")
        return self._source.archive

    def forecast(
        self, context: ContextState, action: str
    ) -> TransferForecast:
        if self._pending is not None:
            raise ValidationError("pending gated forecast must be observed")
        source = self._source.forecast(context, action)
        scratch = self._scratch.forecast(context, action)
        weight = self.source_weight
        combined = TransferForecast(
            world_id=self.world_id,
            index=source.index,
            context=source.context,
            action=source.action,
            transition_probability=(
                weight * source.transition_probability
                + (1.0 - weight) * scratch.transition_probability
            ),
            reward_probability=(
                weight * source.reward_probability
                + (1.0 - weight) * scratch.reward_probability
            ),
        )
        self._pending = (combined, source, scratch)
        return combined

    @staticmethod
    def _log_likelihood(
        forecast: TransferForecast,
        observation: TransferObservation,
    ) -> float:
        result = 0.0
        for probability, outcome in (
            (forecast.transition_probability, observation.next_observation),
            (forecast.reward_probability, observation.reward),
        ):
            result += math.log(
                probability if outcome else 1.0 - probability
            )
        return result

    def observe(self, observation: TransferObservation) -> None:
        if self._pending is None:
            raise ValidationError("gated observation has no forecast")
        combined, source, scratch = self._pending
        if (
            not isinstance(observation, TransferObservation)
            or observation.world_id != combined.world_id
            or observation.index != combined.index
            or observation.context != combined.context
            or observation.action != combined.action
        ):
            raise ValidationError("gated observation does not match forecast")
        self._log_source_weight += self._log_likelihood(source, observation)
        self._log_scratch_weight += self._log_likelihood(scratch, observation)
        self._source.observe(observation)
        self._scratch.observe(observation)
        self._pending = None
        self._weight_history.append(self.source_weight)
