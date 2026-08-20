"""Source-learned priors and compatibility gating for transfer development.

The learner consumes chosen-action summaries from source tasks.  It never
receives hidden family or target parameters.  This module is development
infrastructure and does not register H50-L14.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
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
from .models import ValidationError, canonical_json


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


def permuted_transfer_prior(
    prior: TransferPrior, *, offset: int = 1
) -> TransferPrior:
    """Causal control that preserves priors but breaks their cell alignment."""

    if not isinstance(prior, TransferPrior):
        raise ValidationError("permuted prior is invalid")
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or not 1 <= offset < len(prior.cells)
    ):
        raise ValidationError("prior permutation offset is invalid")
    return TransferPrior(
        provenance=f"permuted:{offset}:{prior.provenance}",
        cells=tuple(
            TransferCellPrior(
                context=context,
                action=action,
                transition=prior.cells[
                    (index + offset) % len(prior.cells)
                ].transition,
                reward=prior.cells[
                    (index + offset) % len(prior.cells)
                ].reward,
            )
            for index, (context, action) in enumerate(transfer_cell_keys())
        ),
    )


def _strict_json(raw: str) -> object:
    if not isinstance(raw, str):
        raise ValidationError("snapshot must be text")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError("snapshot contains a duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValidationError(f"snapshot contains {value}")
            ),
        )
    except ValidationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValidationError("snapshot is not strict JSON") from error


def _prior_to_dict(prior: TransferPrior) -> dict[str, object]:
    return {
        "provenance": prior.provenance,
        "cells": [
            {
                "context": list(cell.context),
                "action": cell.action,
                "transition": {
                    "alpha": cell.transition.alpha,
                    "beta": cell.transition.beta,
                },
                "reward": {
                    "alpha": cell.reward.alpha,
                    "beta": cell.reward.beta,
                },
            }
            for cell in prior.cells
        ],
    }


def _prior_digest(prior: TransferPrior) -> str:
    return hashlib.sha256(
        canonical_json(_prior_to_dict(prior)).encode("utf-8")
    ).hexdigest()


def _beta_prior_from_dict(raw: object, field: str) -> BetaPrior:
    if not isinstance(raw, dict) or set(raw) != {"alpha", "beta"}:
        raise ValidationError(f"snapshot {field} prior is invalid")
    return BetaPrior(
        alpha=raw.get("alpha"),  # type: ignore[arg-type]
        beta=raw.get("beta"),  # type: ignore[arg-type]
    )


def _prior_from_dict(raw: object) -> TransferPrior:
    if not isinstance(raw, dict) or set(raw) != {"provenance", "cells"}:
        raise ValidationError("snapshot source prior is invalid")
    rows = raw.get("cells")
    if not isinstance(rows, list):
        raise ValidationError("snapshot prior cells must be a list")
    cells: list[TransferCellPrior] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "context",
            "action",
            "transition",
            "reward",
        }:
            raise ValidationError("snapshot prior cell is invalid")
        context = row.get("context")
        if not isinstance(context, list):
            raise ValidationError("snapshot prior context is invalid")
        cells.append(
            TransferCellPrior(
                context=tuple(context),  # type: ignore[arg-type]
                action=row.get("action"),  # type: ignore[arg-type]
                transition=_beta_prior_from_dict(
                    row.get("transition"), "transition"
                ),
                reward=_beta_prior_from_dict(row.get("reward"), "reward"),
            )
        )
    return TransferPrior(
        provenance=raw.get("provenance"),  # type: ignore[arg-type]
        cells=tuple(cells),
    )


def _observation_to_dict(
    observation: TransferObservation,
) -> dict[str, object]:
    return {
        "world_id": observation.world_id,
        "index": observation.index,
        "context": list(observation.context),
        "action": observation.action,
        "next_observation": observation.next_observation,
        "reward": observation.reward,
    }


def _observation_from_dict(raw: object) -> TransferObservation:
    if not isinstance(raw, dict) or set(raw) != {
        "world_id",
        "index",
        "context",
        "action",
        "next_observation",
        "reward",
    }:
        raise ValidationError("snapshot observation is invalid")
    context = raw.get("context")
    if not isinstance(context, list):
        raise ValidationError("snapshot observation context is invalid")
    return TransferObservation(
        world_id=raw.get("world_id"),  # type: ignore[arg-type]
        index=raw.get("index"),  # type: ignore[arg-type]
        context=tuple(context),  # type: ignore[arg-type]
        action=raw.get("action"),  # type: ignore[arg-type]
        next_observation=raw.get("next_observation"),  # type: ignore[arg-type]
        reward=raw.get("reward"),  # type: ignore[arg-type]
    )


class GatedTransferModel:
    """Bayesian mixture of a source-learned model and scratch learning."""

    SNAPSHOT_SCHEMA = 1
    REWARD_ONLY_SNAPSHOT_SCHEMA = 2
    COMPATIBILITY_FEEDBACK_MODES = (
        "transition_and_reward",
        "reward_only",
    )

    def __init__(
        self,
        *,
        world_id: str,
        source_prior: TransferPrior,
        initial_source_weight: float,
        compatibility_feedback: str = "transition_and_reward",
    ) -> None:
        if (
            isinstance(initial_source_weight, bool)
            or not isinstance(initial_source_weight, (int, float))
            or not math.isfinite(initial_source_weight)
            or not 0.0 < initial_source_weight < 1.0
        ):
            raise ValidationError("initial source weight must be within (0, 1)")
        if compatibility_feedback not in self.COMPATIBILITY_FEEDBACK_MODES:
            raise ValidationError("compatibility feedback mode is invalid")
        self.world_id = world_id
        self.source_prior = source_prior
        self.source_prior_digest = _prior_digest(source_prior)
        self.initial_source_weight = float(initial_source_weight)
        self.compatibility_feedback = compatibility_feedback
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

    def _combine(
        self,
        source: TransferForecast,
        scratch: TransferForecast,
    ) -> TransferForecast:
        weight = self.source_weight
        return TransferForecast(
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

    def peek(
        self, context: ContextState, action: str
    ) -> TransferForecast:
        if self._pending is not None:
            raise ValidationError("pending gated forecast must be observed")
        return self._combine(
            self._source.peek(context, action),
            self._scratch.peek(context, action),
        )

    def forecast(
        self, context: ContextState, action: str
    ) -> TransferForecast:
        if self._pending is not None:
            raise ValidationError("pending gated forecast must be observed")
        source = self._source.forecast(context, action)
        scratch = self._scratch.forecast(context, action)
        combined = self._combine(source, scratch)
        self._pending = (combined, source, scratch)
        return combined

    def _log_likelihood(
        self,
        forecast: TransferForecast,
        observation: TransferObservation,
    ) -> float:
        result = 0.0
        channels = (
            ((forecast.reward_probability, observation.reward),)
            if self.compatibility_feedback == "reward_only"
            else (
                (
                    forecast.transition_probability,
                    observation.next_observation,
                ),
                (forecast.reward_probability, observation.reward),
            )
        )
        for probability, outcome in channels:
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

    def _snapshot_dict(self) -> dict[str, object]:
        configuration: dict[str, object] = {
            "world_id": self.world_id,
            "initial_source_weight": self.initial_source_weight,
            "source_prior": _prior_to_dict(self.source_prior),
            "source_prior_digest": self.source_prior_digest,
        }
        schema = self.SNAPSHOT_SCHEMA
        if self.compatibility_feedback == "reward_only":
            schema = self.REWARD_ONLY_SNAPSHOT_SCHEMA
            configuration["compatibility_feedback"] = (
                self.compatibility_feedback
            )
        return {
            "schema": schema,
            "configuration": configuration,
            "archive": [
                _observation_to_dict(item) for item in self.archive
            ],
            "derived": {
                "source_weight": self.source_weight,
                "weight_history": list(self.weight_history),
            },
        }

    def to_snapshot(self) -> str:
        if self._pending is not None:
            raise ValidationError("cannot snapshot a pending gated forecast")
        return canonical_json(self._snapshot_dict())

    @classmethod
    def from_snapshot(cls, raw: str) -> "GatedTransferModel":
        parsed = _strict_json(raw)
        schema = parsed.get("schema") if isinstance(parsed, dict) else None
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema",
            "configuration",
            "archive",
            "derived",
        } or schema not in (
            cls.SNAPSHOT_SCHEMA,
            cls.REWARD_ONLY_SNAPSHOT_SCHEMA,
        ):
            raise ValidationError("unsupported gated transfer snapshot")
        configuration = parsed.get("configuration")
        expected_configuration = {
            "world_id",
            "initial_source_weight",
            "source_prior",
            "source_prior_digest",
        }
        if schema == cls.REWARD_ONLY_SNAPSHOT_SCHEMA:
            expected_configuration.add("compatibility_feedback")
        if (
            not isinstance(configuration, dict)
            or set(configuration) != expected_configuration
        ):
            raise ValidationError("gated snapshot configuration is invalid")
        compatibility_feedback = configuration.get(
            "compatibility_feedback",
            "transition_and_reward",
        )
        if (
            schema == cls.REWARD_ONLY_SNAPSHOT_SCHEMA
            and compatibility_feedback != "reward_only"
        ):
            raise ValidationError("gated snapshot feedback mode is invalid")
        source_prior = _prior_from_dict(configuration.get("source_prior"))
        if configuration.get("source_prior_digest") != _prior_digest(
            source_prior
        ):
            raise ValidationError("gated snapshot prior digest disagrees")
        model = cls(
            world_id=configuration.get("world_id"),  # type: ignore[arg-type]
            source_prior=source_prior,
            initial_source_weight=configuration.get(
                "initial_source_weight"
            ),  # type: ignore[arg-type]
            compatibility_feedback=compatibility_feedback,  # type: ignore[arg-type]
        )
        archive = parsed.get("archive")
        if not isinstance(archive, list):
            raise ValidationError("gated snapshot archive must be a list")
        for row in archive:
            observation = _observation_from_dict(row)
            model.forecast(observation.context, observation.action)
            model.observe(observation)
        try:
            if canonical_json(parsed) != canonical_json(model._snapshot_dict()):
                raise ValidationError(
                    "gated snapshot does not match causal replay"
                )
        except (TypeError, ValueError) as error:
            raise ValidationError("gated snapshot is not finite") from error
        return model


class CellwiseGatedTransferModel:
    """Independent compatibility odds per aligned context-action cell."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        world_id: str,
        source_prior: TransferPrior,
        initial_source_weight: float,
        scratch_fallback: bool,
    ) -> None:
        if (
            isinstance(initial_source_weight, bool)
            or not isinstance(initial_source_weight, (int, float))
            or not math.isfinite(initial_source_weight)
            or not 0.0 < initial_source_weight < 1.0
        ):
            raise ValidationError("initial source weight must be within (0, 1)")
        if not isinstance(scratch_fallback, bool):
            raise ValidationError("scratch fallback flag is invalid")
        self.world_id = world_id
        self.source_prior = source_prior
        self.source_prior_digest = _prior_digest(source_prior)
        self.initial_source_weight = float(initial_source_weight)
        self.scratch_fallback = scratch_fallback
        self._source = PrequentialTransferModel(
            world_id=world_id,
            prior=source_prior,
        )
        self._scratch = PrequentialTransferModel(
            world_id=world_id,
            prior=TransferPrior.scratch(),
        )
        self._log_weights = {
            key: (
                math.log(self.initial_source_weight),
                math.log(1.0 - self.initial_source_weight),
            )
            for key in transfer_cell_keys()
        }
        self._pending: tuple[
            TransferForecast,
            TransferForecast,
            TransferForecast,
        ] | None = None

    @property
    def archive(self) -> tuple[TransferObservation, ...]:
        if self._source.archive != self._scratch.archive:
            raise ValidationError("cellwise gated model archives disagree")
        return self._source.archive

    def posterior_source_weight(
        self,
        context: ContextState,
        action: str,
    ) -> float:
        key = (context, action)
        if key not in self._log_weights:
            raise ValidationError("cellwise gate key is invalid")
        log_source, log_scratch = self._log_weights[key]
        maximum = max(log_source, log_scratch)
        source = math.exp(log_source - maximum)
        scratch = math.exp(log_scratch - maximum)
        return source / (source + scratch)

    def effective_source_weight(
        self,
        context: ContextState,
        action: str,
    ) -> float:
        posterior = self.posterior_source_weight(context, action)
        if self.scratch_fallback and posterior < self.initial_source_weight:
            return 0.0
        return posterior

    @property
    def posterior_source_weights(self) -> tuple[float, ...]:
        return tuple(
            self.posterior_source_weight(context, action)
            for context, action in transfer_cell_keys()
        )

    @property
    def effective_source_weights(self) -> tuple[float, ...]:
        return tuple(
            self.effective_source_weight(context, action)
            for context, action in transfer_cell_keys()
        )

    @property
    def fallback_cell_rate(self) -> float:
        return sum(
            weight == 0.0 for weight in self.effective_source_weights
        ) / len(transfer_cell_keys())

    def _combine(
        self,
        source: TransferForecast,
        scratch: TransferForecast,
    ) -> TransferForecast:
        weight = self.effective_source_weight(source.context, source.action)
        return TransferForecast(
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

    def peek(
        self,
        context: ContextState,
        action: str,
    ) -> TransferForecast:
        if self._pending is not None:
            raise ValidationError("pending cellwise forecast must be observed")
        return self._combine(
            self._source.peek(context, action),
            self._scratch.peek(context, action),
        )

    def forecast(
        self,
        context: ContextState,
        action: str,
    ) -> TransferForecast:
        if self._pending is not None:
            raise ValidationError("pending cellwise forecast must be observed")
        source = self._source.forecast(context, action)
        scratch = self._scratch.forecast(context, action)
        combined = self._combine(source, scratch)
        self._pending = (combined, source, scratch)
        return combined

    @staticmethod
    def _log_likelihood(
        forecast: TransferForecast,
        observation: TransferObservation,
    ) -> float:
        return sum(
            math.log(probability if outcome else 1.0 - probability)
            for probability, outcome in (
                (
                    forecast.transition_probability,
                    observation.next_observation,
                ),
                (forecast.reward_probability, observation.reward),
            )
        )

    def observe(self, observation: TransferObservation) -> None:
        if self._pending is None:
            raise ValidationError("cellwise observation has no forecast")
        combined, source, scratch = self._pending
        if (
            not isinstance(observation, TransferObservation)
            or observation.world_id != combined.world_id
            or observation.index != combined.index
            or observation.context != combined.context
            or observation.action != combined.action
        ):
            raise ValidationError(
                "cellwise observation does not match forecast"
            )
        key = (observation.context, observation.action)
        log_source, log_scratch = self._log_weights[key]
        self._log_weights[key] = (
            log_source + self._log_likelihood(source, observation),
            log_scratch + self._log_likelihood(scratch, observation),
        )
        self._source.observe(observation)
        self._scratch.observe(observation)
        self._pending = None

    def _weight_rows(self) -> list[dict[str, object]]:
        return [
            {
                "context": list(context),
                "action": action,
                "posterior_source_weight": self.posterior_source_weight(
                    context,
                    action,
                ),
                "effective_source_weight": self.effective_source_weight(
                    context,
                    action,
                ),
            }
            for context, action in transfer_cell_keys()
        ]

    def _snapshot_dict(self) -> dict[str, object]:
        return {
            "schema": self.SNAPSHOT_SCHEMA,
            "configuration": {
                "world_id": self.world_id,
                "initial_source_weight": self.initial_source_weight,
                "scratch_fallback": self.scratch_fallback,
                "source_prior": _prior_to_dict(self.source_prior),
                "source_prior_digest": self.source_prior_digest,
            },
            "archive": [
                _observation_to_dict(item) for item in self.archive
            ],
            "derived": {
                "weights": self._weight_rows(),
                "fallback_cell_rate": self.fallback_cell_rate,
            },
        }

    def to_snapshot(self) -> str:
        if self._pending is not None:
            raise ValidationError(
                "cannot snapshot a pending cellwise forecast"
            )
        return canonical_json(self._snapshot_dict())

    @classmethod
    def from_snapshot(cls, raw: str) -> "CellwiseGatedTransferModel":
        parsed = _strict_json(raw)
        if (
            not isinstance(parsed, dict)
            or set(parsed) != {
                "schema",
                "configuration",
                "archive",
                "derived",
            }
            or parsed.get("schema") != cls.SNAPSHOT_SCHEMA
        ):
            raise ValidationError("unsupported cellwise gate snapshot")
        configuration = parsed.get("configuration")
        if not isinstance(configuration, dict) or set(configuration) != {
            "world_id",
            "initial_source_weight",
            "scratch_fallback",
            "source_prior",
            "source_prior_digest",
        }:
            raise ValidationError(
                "cellwise snapshot configuration is invalid"
            )
        source_prior = _prior_from_dict(configuration.get("source_prior"))
        if configuration.get("source_prior_digest") != _prior_digest(
            source_prior
        ):
            raise ValidationError("cellwise snapshot prior digest disagrees")
        model = cls(
            world_id=configuration.get("world_id"),  # type: ignore[arg-type]
            source_prior=source_prior,
            initial_source_weight=configuration.get(
                "initial_source_weight"
            ),  # type: ignore[arg-type]
            scratch_fallback=configuration.get(  # type: ignore[arg-type]
                "scratch_fallback"
            ),
        )
        archive = parsed.get("archive")
        if not isinstance(archive, list):
            raise ValidationError("cellwise snapshot archive must be a list")
        for row in archive:
            observation = _observation_from_dict(row)
            model.forecast(observation.context, observation.action)
            model.observe(observation)
        try:
            if canonical_json(parsed) != canonical_json(model._snapshot_dict()):
                raise ValidationError(
                    "cellwise snapshot does not match causal replay"
                )
        except (TypeError, ValueError) as error:
            raise ValidationError("cellwise snapshot is not finite") from error
        return model
