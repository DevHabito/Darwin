"""Development evaluator for a source-learned cross-world prior.

This module selects a development configuration only.  It does not contain a
confirmatory decision rule or H50-L14 final seeds.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import fmean
from typing import Iterable, Protocol

from .cross_world_transfer_evaluation import (
    OPPOSED_FAMILY_XOR_MASK,
    OUTCOME_XOR_MASK,
    SCHEDULE_XOR_MASK,
    SOURCE_FAMILY_XOR_MASK,
    TRANSFER_CONDITIONS,
    TRANSFER_EARLY_CYCLES,
    UNRELATED_FAMILY_XOR_MASK,
    WORLD_XOR_MASK,
)
from .cross_world_transfer_lab import (
    AlignedTransferTask,
    PrequentialTransferModel,
    TransferFamilySpecification,
    TransferForecast,
    TransferObservation,
    TransferPrior,
    TransferWorldSpecification,
    balanced_transfer_schedule,
    require_disjoint_seed_sets,
)
from .cross_world_transfer_learning import (
    GatedTransferModel,
    collect_source_family_evidence,
    learn_transfer_prior,
    permuted_transfer_prior,
    pooled_source_prior,
)
from .learned_context_lab import ContextState
from .models import ValidationError


TRANSFER_LEARNING_DEVELOPMENT_SEEDS = tuple(range(27000, 27032))
TRANSFER_LEARNING_TEST_SEEDS = tuple(range(27400, 27408))
TRANSFER_SOURCE_TASK_CANDIDATES = (4, 8, 16)
TRANSFER_SOURCE_CYCLE_CANDIDATES = (4, 8)
TRANSFER_INITIAL_WEIGHT_CANDIDATES = (0.25, 0.5, 0.75)
TRANSFER_SOURCE_BASE_XOR_MASK = 0x48B27


class _PrequentialModel(Protocol):
    def forecast(
        self, context: ContextState, action: str
    ) -> TransferForecast: ...

    def observe(self, observation: TransferObservation) -> None: ...


def _binary_log_loss(probability: float, outcome: bool) -> float:
    bounded = min(max(probability, 1e-12), 1.0 - 1e-12)
    return -math.log(bounded if outcome else 1.0 - bounded)


def _binary_brier(probability: float, outcome: bool) -> float:
    return (probability - float(outcome)) ** 2


@dataclass(frozen=True, slots=True)
class TransferDevelopmentConfiguration:
    source_tasks: int
    source_cycles: int
    initial_source_weight: float

    def __post_init__(self) -> None:
        if self.source_tasks not in TRANSFER_SOURCE_TASK_CANDIDATES:
            raise ValidationError("source task candidate is invalid")
        if self.source_cycles not in TRANSFER_SOURCE_CYCLE_CANDIDATES:
            raise ValidationError("source cycle candidate is invalid")
        if self.initial_source_weight not in (
            TRANSFER_INITIAL_WEIGHT_CANDIDATES
        ):
            raise ValidationError("initial source weight candidate is invalid")

    @property
    def source_interactions(self) -> int:
        return self.source_tasks * self.source_cycles * 16

    def to_dict(self) -> dict[str, object]:
        return {
            "source_tasks": self.source_tasks,
            "source_cycles": self.source_cycles,
            "initial_source_weight": self.initial_source_weight,
            "source_interactions": self.source_interactions,
        }


TRANSFER_DEVELOPMENT_CONFIGURATIONS = tuple(
    TransferDevelopmentConfiguration(
        source_tasks=source_tasks,
        source_cycles=source_cycles,
        initial_source_weight=weight,
    )
    for source_tasks in TRANSFER_SOURCE_TASK_CANDIDATES
    for source_cycles in TRANSFER_SOURCE_CYCLE_CANDIDATES
    for weight in TRANSFER_INITIAL_WEIGHT_CANDIDATES
)


@dataclass(frozen=True, slots=True)
class PredictorScore:
    log_loss: float
    brier: float

    def __post_init__(self) -> None:
        for value in (self.log_loss, self.brier):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValidationError("predictor score is invalid")


@dataclass(frozen=True, slots=True)
class TransferLearningWorldScore:
    seed: int
    condition: str
    scratch: PredictorScore
    learned: PredictorScore
    gated: PredictorScore
    pooled: PredictorScore
    shuffled: PredictorScore
    oracle: PredictorScore
    final_source_weight: float

    def __post_init__(self) -> None:
        if self.condition not in TRANSFER_CONDITIONS:
            raise ValidationError("learning score condition is invalid")
        if (
            isinstance(self.final_source_weight, bool)
            or not isinstance(self.final_source_weight, (int, float))
            or not math.isfinite(self.final_source_weight)
            or not 0.0 <= self.final_source_weight <= 1.0
        ):
            raise ValidationError("final source weight is invalid")

    def log_loss_improvement(self, predictor: str) -> float:
        if predictor not in (
            "learned",
            "gated",
            "pooled",
            "shuffled",
            "oracle",
        ):
            raise ValidationError("predictor name is invalid")
        return self.scratch.log_loss - getattr(self, predictor).log_loss


@dataclass(frozen=True, slots=True)
class DevelopmentConfigurationReport:
    configuration: TransferDevelopmentConfiguration
    worlds: tuple[TransferLearningWorldScore, ...]

    def __post_init__(self) -> None:
        expected = len(TRANSFER_CONDITIONS)
        counts = {
            condition: sum(item.condition == condition for item in self.worlds)
            for condition in TRANSFER_CONDITIONS
        }
        if not self.worlds or any(value != len(self.worlds) // expected for value in counts.values()):
            raise ValidationError("development worlds are unbalanced")

    def mean_improvement(self, condition: str, predictor: str) -> float:
        if condition not in TRANSFER_CONDITIONS:
            raise ValidationError("development condition is invalid")
        selected = tuple(
            item.log_loss_improvement(predictor)
            for item in self.worlds
            if item.condition == condition
        )
        return fmean(selected)

    def mean_final_weight(self, condition: str) -> float:
        if condition not in TRANSFER_CONDITIONS:
            raise ValidationError("development condition is invalid")
        return fmean(
            item.final_source_weight
            for item in self.worlds
            if item.condition == condition
        )

    @property
    def robust_score(self) -> float:
        related = self.mean_improvement("related", "gated")
        unrelated = self.mean_improvement("unrelated", "gated")
        adversarial = self.mean_improvement("adversarial", "gated")
        return related + min(0.0, unrelated) + min(0.0, adversarial)

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration.to_dict(),
            "robust_score": self.robust_score,
            "gated_log_loss_improvement": {
                condition: self.mean_improvement(condition, "gated")
                for condition in TRANSFER_CONDITIONS
            },
            "learned_log_loss_improvement": {
                condition: self.mean_improvement(condition, "learned")
                for condition in TRANSFER_CONDITIONS
            },
            "pooled_log_loss_improvement": {
                condition: self.mean_improvement(condition, "pooled")
                for condition in TRANSFER_CONDITIONS
            },
            "shuffled_log_loss_improvement": {
                condition: self.mean_improvement(condition, "shuffled")
                for condition in TRANSFER_CONDITIONS
            },
            "oracle_log_loss_improvement": {
                condition: self.mean_improvement(condition, "oracle")
                for condition in TRANSFER_CONDITIONS
            },
            "mean_final_source_weight": {
                condition: self.mean_final_weight(condition)
                for condition in TRANSFER_CONDITIONS
            },
        }


@dataclass(frozen=True, slots=True)
class TransferLearningDevelopmentReport:
    seeds: tuple[int, ...]
    configurations: tuple[DevelopmentConfigurationReport, ...]
    selected: TransferDevelopmentConfiguration

    def __post_init__(self) -> None:
        if not self.seeds:
            raise ValidationError("development seeds are empty")
        if tuple(item.configuration for item in self.configurations) != (
            TRANSFER_DEVELOPMENT_CONFIGURATIONS
        ):
            raise ValidationError("development grid is incomplete")
        if self.selected not in TRANSFER_DEVELOPMENT_CONFIGURATIONS:
            raise ValidationError("selected development configuration is invalid")

    def selected_report(self) -> DevelopmentConfigurationReport:
        return next(
            item
            for item in self.configurations
            if item.configuration == self.selected
        )

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "status": "development-only",
            "capability_claim": False,
            "h50_l14_registered": False,
            "seeds": list(self.seeds),
            "selection_rule": (
                "maximize related + min(0, unrelated) + "
                "min(0, adversarial); then related; then lower source cost; "
                "then lower initial weight"
            ),
            "selected": self.selected_report().to_summary_dict(),
            "configuration_count": len(self.configurations),
            "configurations": [
                item.to_summary_dict() for item in self.configurations
            ],
        }


def _target_family(
    *,
    source: TransferFamilySpecification,
    seed: int,
    condition: str,
) -> TransferFamilySpecification:
    if condition == "related":
        return source
    if condition == "unrelated":
        return TransferFamilySpecification.from_seed(
            seed ^ UNRELATED_FAMILY_XOR_MASK
        )
    if condition == "adversarial":
        return source.opposed(seed=seed ^ OPPOSED_FAMILY_XOR_MASK)
    raise ValidationError("target condition is invalid")


def _score_forecast(
    forecast: TransferForecast, observation: TransferObservation
) -> tuple[float, float]:
    log_losses: list[float] = []
    briers: list[float] = []
    for probability, outcome in (
        (forecast.transition_probability, observation.next_observation),
        (forecast.reward_probability, observation.reward),
    ):
        log_losses.append(_binary_log_loss(probability, outcome))
        briers.append(_binary_brier(probability, outcome))
    return fmean(log_losses), fmean(briers)


def evaluate_learning_world(
    *,
    seed: int,
    condition: str,
    configuration: TransferDevelopmentConfiguration,
) -> TransferLearningWorldScore:
    normalized_seed = require_disjoint_seed_sets(world=(seed,))["world"][0]
    source_family = TransferFamilySpecification.from_seed(
        normalized_seed ^ SOURCE_FAMILY_XOR_MASK
    )
    source_evidence = collect_source_family_evidence(
        source_family,
        base_seed=normalized_seed ^ TRANSFER_SOURCE_BASE_XOR_MASK,
        task_count=configuration.source_tasks,
        cycles=configuration.source_cycles,
    )
    learned_prior = learn_transfer_prior(source_evidence)
    pooled_prior = pooled_source_prior(source_evidence)
    target_family = _target_family(
        source=source_family,
        seed=normalized_seed,
        condition=condition,
    )
    specification = TransferWorldSpecification.from_family(
        target_family,
        world_seed=normalized_seed ^ WORLD_XOR_MASK,
    )
    task = AlignedTransferTask(
        specification,
        outcome_seed=normalized_seed ^ OUTCOME_XOR_MASK,
        public_world_id="target-task",
    )
    public_world_id = task.world_id
    models: dict[str, _PrequentialModel] = {
        "scratch": PrequentialTransferModel(
            world_id=public_world_id,
            prior=TransferPrior.scratch(),
        ),
        "learned": PrequentialTransferModel(
            world_id=public_world_id,
            prior=learned_prior,
        ),
        "gated": GatedTransferModel(
            world_id=public_world_id,
            source_prior=learned_prior,
            initial_source_weight=configuration.initial_source_weight,
        ),
        "pooled": PrequentialTransferModel(
            world_id=public_world_id,
            prior=pooled_prior,
        ),
        "shuffled": GatedTransferModel(
            world_id=public_world_id,
            source_prior=permuted_transfer_prior(learned_prior, offset=1),
            initial_source_weight=configuration.initial_source_weight,
        ),
        "oracle": PrequentialTransferModel(
            world_id=public_world_id,
            prior=TransferPrior.oracle(source_family),
        ),
    }
    log_losses = {name: [] for name in models}
    briers = {name: [] for name in models}
    schedule = balanced_transfer_schedule(
        cycles=TRANSFER_EARLY_CYCLES,
        seed=normalized_seed ^ SCHEDULE_XOR_MASK,
    )
    for context, action in schedule:
        forecasts = {
            name: model.forecast(context, action)
            for name, model in models.items()
        }
        observation = task.act(context, action)
        for name, forecast in forecasts.items():
            log_loss, brier = _score_forecast(forecast, observation)
            log_losses[name].append(log_loss)
            briers[name].append(brier)
            models[name].observe(observation)
    gated = models["gated"]
    if not isinstance(gated, GatedTransferModel):
        raise ValidationError("gated model type is invalid")
    scores = {
        name: PredictorScore(
            log_loss=fmean(log_losses[name]),
            brier=fmean(briers[name]),
        )
        for name in models
    }
    return TransferLearningWorldScore(
        seed=normalized_seed,
        condition=condition,
        scratch=scores["scratch"],
        learned=scores["learned"],
        gated=scores["gated"],
        pooled=scores["pooled"],
        shuffled=scores["shuffled"],
        oracle=scores["oracle"],
        final_source_weight=gated.source_weight,
    )


def evaluate_development_configuration(
    *,
    seeds: Iterable[int],
    configuration: TransferDevelopmentConfiguration,
) -> DevelopmentConfigurationReport:
    normalized = require_disjoint_seed_sets(development=seeds)["development"]
    worlds = tuple(
        evaluate_learning_world(
            seed=seed,
            condition=condition,
            configuration=configuration,
        )
        for seed in normalized
        for condition in TRANSFER_CONDITIONS
    )
    return DevelopmentConfigurationReport(
        configuration=configuration,
        worlds=worlds,
    )


def run_transfer_learning_development(
    *, seeds: Iterable[int]
) -> TransferLearningDevelopmentReport:
    normalized = require_disjoint_seed_sets(development=seeds)["development"]
    reports = tuple(
        evaluate_development_configuration(
            seeds=normalized,
            configuration=configuration,
        )
        for configuration in TRANSFER_DEVELOPMENT_CONFIGURATIONS
    )
    selected_report = max(
        reports,
        key=lambda item: (
            item.robust_score,
            item.mean_improvement("related", "gated"),
            -item.configuration.source_interactions,
            -item.configuration.initial_source_weight,
        ),
    )
    return TransferLearningDevelopmentReport(
        seeds=normalized,
        configurations=reports,
        selected=selected_report.configuration,
    )
