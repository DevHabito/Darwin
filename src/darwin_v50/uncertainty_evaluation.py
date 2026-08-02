"""Held-out calibration and information-action evaluation for H50-L3."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
from statistics import fmean
from typing import Any, Iterable, Sequence

from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .uncertainty_lab import (
    ALL_CONTEXTS,
    CHOICE_ACTIONS,
    INITIAL_CONTEXTS,
    INSPECT,
    REVEALED_CONTEXTS,
    BetaBernoulliOutcomeModel,
    HiddenSignalObservation,
    HiddenSignalWorld,
    OutcomeExperience,
    SelectiveInformationPolicy,
    outcome_experience,
)


LOCAL_UNCERTAINTY_EVALUATOR = (
    "darwin_v50.uncertainty_lab.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    context: str
    action: str
    predicted_probability: float
    success: bool


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    records: int
    brier_score: float
    uninformative_brier_score: float
    brier_improvement: float
    expected_calibration_error: float
    maximum_calibration_error: float
    bin_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "brier_score": self.brier_score,
            "uninformative_brier_score": self.uninformative_brier_score,
            "brier_improvement": self.brier_improvement,
            "expected_calibration_error": self.expected_calibration_error,
            "maximum_calibration_error": self.maximum_calibration_error,
            "bin_count": self.bin_count,
        }


@dataclass(frozen=True, slots=True)
class PolicyEpisode:
    policy: str
    success: bool
    inspected: bool
    utility: float
    initial_context: str
    decision_context: str
    chosen_action: str
    forecast_probability: float


@dataclass(frozen=True, slots=True)
class InformationPolicyMetrics:
    policy: str
    episodes: int
    successes: int
    inspections: int
    success_rate: float
    inspection_rate: float
    mean_utility: float
    forecast_brier_score: float

    @classmethod
    def from_episodes(
        cls,
        policy: str,
        episodes: Sequence[PolicyEpisode],
    ) -> "InformationPolicyMetrics":
        if not episodes:
            raise ValidationError("policy metrics require episodes")
        return cls(
            policy=policy,
            episodes=len(episodes),
            successes=sum(episode.success for episode in episodes),
            inspections=sum(episode.inspected for episode in episodes),
            success_rate=fmean(float(episode.success) for episode in episodes),
            inspection_rate=fmean(
                float(episode.inspected) for episode in episodes
            ),
            mean_utility=fmean(episode.utility for episode in episodes),
            forecast_brier_score=fmean(
                (
                    episode.forecast_probability - float(episode.success)
                )
                ** 2
                for episode in episodes
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "episodes": self.episodes,
            "successes": self.successes,
            "inspections": self.inspections,
            "success_rate": self.success_rate,
            "inspection_rate": self.inspection_rate,
            "mean_utility": self.mean_utility,
            "forecast_brier_score": self.forecast_brier_score,
        }


@dataclass(frozen=True, slots=True)
class UncertaintySuiteReport:
    training_seed: int
    evaluation_seeds: tuple[int, ...]
    training_samples_per_context_action: int
    training_experience_count: int
    calibration_samples_per_context_action: int
    calibration: CalibrationMetrics
    policy_episodes_per_seed: int
    selective: InformationPolicyMetrics
    never_inspect: InformationPolicyMetrics
    always_inspect: InformationPolicyMetrics
    selective_utility_delta_vs_never: float
    selective_utility_delta_vs_always: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    @property
    def minimum_utility_advantage(self) -> float:
        return min(
            self.selective_utility_delta_vs_never,
            self.selective_utility_delta_vs_always,
        )

    def passes_regression_criteria(
        self,
        *,
        maximum_brier_score: float = 0.18,
        minimum_brier_improvement: float = 0.07,
        maximum_expected_calibration_error: float = 0.04,
        minimum_selective_inspection_rate: float = 0.35,
        maximum_selective_inspection_rate: float = 0.65,
        minimum_utility_delta_vs_never: float = 0.05,
        minimum_utility_delta_vs_always: float = 0.02,
    ) -> bool:
        return (
            self.calibration.brier_score <= maximum_brier_score
            and self.calibration.brier_improvement
            >= minimum_brier_improvement
            and self.calibration.expected_calibration_error
            <= maximum_expected_calibration_error
            and minimum_selective_inspection_rate
            <= self.selective.inspection_rate
            <= maximum_selective_inspection_rate
            and self.selective_utility_delta_vs_never
            >= minimum_utility_delta_vs_never
            and self.selective_utility_delta_vs_always
            >= minimum_utility_delta_vs_always
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_seed": self.training_seed,
            "evaluation_seeds": list(self.evaluation_seeds),
            "training_samples_per_context_action": (
                self.training_samples_per_context_action
            ),
            "training_experience_count": self.training_experience_count,
            "calibration_samples_per_context_action": (
                self.calibration_samples_per_context_action
            ),
            "calibration": self.calibration.to_dict(),
            "policy_episodes_per_seed": self.policy_episodes_per_seed,
            "selective": self.selective.to_dict(),
            "never_inspect": self.never_inspect.to_dict(),
            "always_inspect": self.always_inspect.to_dict(),
            "selective_utility_delta_vs_never": (
                self.selective_utility_delta_vs_never
            ),
            "selective_utility_delta_vs_always": (
                self.selective_utility_delta_vs_always
            ),
            "minimum_utility_advantage": self.minimum_utility_advantage,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
        }


def _least_sampled_action(
    counts: dict[tuple[str, str], int],
    context: str,
) -> str:
    return min(
        CHOICE_ACTIONS,
        key=lambda action: (counts.get((context, action), 0), action),
    )


def _record_training_outcome(
    model: BetaBernoulliOutcomeModel,
    counts: dict[tuple[str, str], int],
    observation: HiddenSignalObservation,
    world: HiddenSignalWorld,
) -> None:
    action = _least_sampled_action(counts, observation.context)
    result = world.step(action)
    if result.success is None:
        raise RuntimeError("terminal choice did not produce an outcome")
    model.observe(
        outcome_experience(
            observation=observation,
            action=action,
            success=result.success,
        )
    )
    counts[(observation.context, action)] = (
        counts.get((observation.context, action), 0) + 1
    )


def train_balanced_outcome_model(
    *,
    seed: int,
    samples_per_context_action: int = 250,
) -> BetaBernoulliOutcomeModel:
    if samples_per_context_action < 1:
        raise ValidationError("training sample target must be positive")
    world = HiddenSignalWorld(seed)
    model = BetaBernoulliOutcomeModel()
    counts: dict[tuple[str, str], int] = {}

    target_initial = len(INITIAL_CONTEXTS) * len(CHOICE_ACTIONS)
    attempts = 0
    maximum_attempts = samples_per_context_action * target_initial * 100
    while sum(
        counts.get((context, action), 0) >= samples_per_context_action
        for context in INITIAL_CONTEXTS
        for action in CHOICE_ACTIONS
    ) < target_initial:
        attempts += 1
        if attempts > maximum_attempts:
            raise RuntimeError("initial-context training collection exhausted")
        observation = world.reset()
        if all(
            counts.get((observation.context, action), 0)
            >= samples_per_context_action
            for action in CHOICE_ACTIONS
        ):
            continue
        _record_training_outcome(model, counts, observation, world)

    target_revealed = len(REVEALED_CONTEXTS) * len(CHOICE_ACTIONS)
    attempts = 0
    maximum_attempts = samples_per_context_action * target_revealed * 100
    while sum(
        counts.get((context, action), 0) >= samples_per_context_action
        for context in REVEALED_CONTEXTS
        for action in CHOICE_ACTIONS
    ) < target_revealed:
        attempts += 1
        if attempts > maximum_attempts:
            raise RuntimeError("revealed-context training collection exhausted")
        observation = world.reset()
        revealed = world.step(INSPECT).observation
        if all(
            counts.get((revealed.context, action), 0)
            >= samples_per_context_action
            for action in CHOICE_ACTIONS
        ):
            continue
        _record_training_outcome(model, counts, revealed, world)

    expected = len(ALL_CONTEXTS) * len(CHOICE_ACTIONS) * samples_per_context_action
    if model.experience_count != expected:
        raise RuntimeError("balanced training count mismatch")
    return model


def _record_forecast_case(
    records: list[ForecastRecord],
    counts: dict[tuple[str, str], int],
    model: BetaBernoulliOutcomeModel,
    observation: HiddenSignalObservation,
    world: HiddenSignalWorld,
) -> None:
    action = _least_sampled_action(counts, observation.context)
    forecast = model.predict(observation.context, action)
    result = world.step(action)
    if result.success is None:
        raise RuntimeError("forecast case did not produce an outcome")
    records.append(
        ForecastRecord(
            context=observation.context,
            action=action,
            predicted_probability=forecast.success_probability,
            success=result.success,
        )
    )
    counts[(observation.context, action)] = (
        counts.get((observation.context, action), 0) + 1
    )


def collect_balanced_forecast_records(
    model: BetaBernoulliOutcomeModel,
    *,
    seed: int,
    samples_per_context_action: int = 500,
) -> tuple[ForecastRecord, ...]:
    if samples_per_context_action < 1:
        raise ValidationError("calibration sample target must be positive")
    world = HiddenSignalWorld(seed)
    records: list[ForecastRecord] = []
    counts: dict[tuple[str, str], int] = {}

    target_initial = len(INITIAL_CONTEXTS) * len(CHOICE_ACTIONS)
    attempts = 0
    maximum_attempts = samples_per_context_action * target_initial * 100
    while sum(
        counts.get((context, action), 0) >= samples_per_context_action
        for context in INITIAL_CONTEXTS
        for action in CHOICE_ACTIONS
    ) < target_initial:
        attempts += 1
        if attempts > maximum_attempts:
            raise RuntimeError("initial-context calibration collection exhausted")
        observation = world.reset()
        if all(
            counts.get((observation.context, action), 0)
            >= samples_per_context_action
            for action in CHOICE_ACTIONS
        ):
            continue
        _record_forecast_case(records, counts, model, observation, world)

    target_revealed = len(REVEALED_CONTEXTS) * len(CHOICE_ACTIONS)
    attempts = 0
    maximum_attempts = samples_per_context_action * target_revealed * 100
    while sum(
        counts.get((context, action), 0) >= samples_per_context_action
        for context in REVEALED_CONTEXTS
        for action in CHOICE_ACTIONS
    ) < target_revealed:
        attempts += 1
        if attempts > maximum_attempts:
            raise RuntimeError("revealed-context calibration collection exhausted")
        world.reset()
        observation = world.step(INSPECT).observation
        if all(
            counts.get((observation.context, action), 0)
            >= samples_per_context_action
            for action in CHOICE_ACTIONS
        ):
            continue
        _record_forecast_case(records, counts, model, observation, world)

    expected = len(ALL_CONTEXTS) * len(CHOICE_ACTIONS) * samples_per_context_action
    if len(records) != expected:
        raise RuntimeError("balanced calibration count mismatch")
    return tuple(records)


def calibration_metrics(
    records: Sequence[ForecastRecord],
    *,
    bin_count: int = 10,
) -> CalibrationMetrics:
    if not records:
        raise ValidationError("calibration requires forecast records")
    if bin_count < 2:
        raise ValidationError("bin_count must be at least two")
    brier = fmean(
        (record.predicted_probability - float(record.success)) ** 2
        for record in records
    )
    bins: list[list[ForecastRecord]] = [[] for _ in range(bin_count)]
    for record in records:
        if not 0.0 <= record.predicted_probability <= 1.0:
            raise ValidationError("forecast probability must be within [0, 1]")
        index = min(int(record.predicted_probability * bin_count), bin_count - 1)
        bins[index].append(record)
    weighted_error = 0.0
    maximum_error = 0.0
    for bucket in bins:
        if not bucket:
            continue
        predicted = fmean(record.predicted_probability for record in bucket)
        observed = fmean(float(record.success) for record in bucket)
        gap = abs(predicted - observed)
        weighted_error += len(bucket) / len(records) * gap
        maximum_error = max(maximum_error, gap)
    uninformative = 0.25
    return CalibrationMetrics(
        records=len(records),
        brier_score=brier,
        uninformative_brier_score=uninformative,
        brier_improvement=uninformative - brier,
        expected_calibration_error=weighted_error,
        maximum_calibration_error=maximum_error,
        bin_count=bin_count,
    )


def run_information_episode(
    world: HiddenSignalWorld,
    model: BetaBernoulliOutcomeModel,
    *,
    policy: str,
    actionability_threshold: float = 0.75,
    minimum_evidence: int = 50,
) -> PolicyEpisode:
    observation = world.reset()
    initial_context = observation.context
    inspected = False
    information_cost = 0.0

    if policy == "selective":
        controller = SelectiveInformationPolicy(
            model,
            actionability_threshold=actionability_threshold,
            minimum_evidence=minimum_evidence,
        )
        decision = controller.decide(observation)
        if decision.action == INSPECT:
            inspect_result = world.step(INSPECT)
            inspected = True
            information_cost += inspect_result.information_cost
            observation = inspect_result.observation
            decision = controller.decide(observation)
        action = decision.action
        forecast = decision.forecast
    elif policy == "never_inspect":
        forecast = model.best_choice(observation.context)
        action = forecast.action
    elif policy == "always_inspect":
        inspect_result = world.step(INSPECT)
        inspected = True
        information_cost += inspect_result.information_cost
        observation = inspect_result.observation
        forecast = model.best_choice(observation.context)
        action = forecast.action
    else:
        raise ValidationError("unknown information policy")

    decision_context = observation.context
    result = world.step(action)
    if result.success is None:
        raise RuntimeError("policy choice did not terminate")
    return PolicyEpisode(
        policy=policy,
        success=result.success,
        inspected=inspected,
        utility=float(result.success) - information_cost,
        initial_context=initial_context,
        decision_context=decision_context,
        chosen_action=action,
        forecast_probability=forecast.success_probability,
    )


def evaluate_information_policies(
    model: BetaBernoulliOutcomeModel,
    *,
    seeds: Iterable[int],
    episodes_per_seed: int = 500,
) -> tuple[
    InformationPolicyMetrics,
    InformationPolicyMetrics,
    InformationPolicyMetrics,
]:
    normalized_seeds = tuple(int(seed) for seed in seeds)
    if not normalized_seeds:
        raise ValidationError("at least one policy evaluation seed is required")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValidationError("policy evaluation seeds must be unique")
    if episodes_per_seed < 1:
        raise ValidationError("episodes_per_seed must be positive")
    by_policy: dict[str, list[PolicyEpisode]] = {
        "selective": [],
        "never_inspect": [],
        "always_inspect": [],
    }
    for seed in normalized_seeds:
        worlds = {
            policy: HiddenSignalWorld(seed)
            for policy in by_policy
        }
        for _ in range(episodes_per_seed):
            for policy, world in worlds.items():
                by_policy[policy].append(
                    run_information_episode(
                        world,
                        model,
                        policy=policy,
                    )
                )
    return (
        InformationPolicyMetrics.from_episodes(
            "selective", by_policy["selective"]
        ),
        InformationPolicyMetrics.from_episodes(
            "never_inspect", by_policy["never_inspect"]
        ),
        InformationPolicyMetrics.from_episodes(
            "always_inspect", by_policy["always_inspect"]
        ),
    )


def run_uncertainty_suite(
    *,
    training_seed: int = 7300,
    calibration_seed: int = 7400,
    evaluation_seeds: Iterable[int] = range(7500, 7520),
    training_samples_per_context_action: int = 250,
    calibration_samples_per_context_action: int = 500,
    policy_episodes_per_seed: int = 500,
) -> UncertaintySuiteReport:
    normalized_seeds = tuple(int(seed) for seed in evaluation_seeds)
    if not normalized_seeds:
        raise ValidationError("at least one evaluation seed is required")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValidationError("evaluation seeds must be unique")
    if training_seed == calibration_seed or training_seed in normalized_seeds:
        raise ValidationError("training seed must be held out from evaluation")
    if calibration_seed in normalized_seeds:
        raise ValidationError("calibration and policy seeds must be distinct")
    model = train_balanced_outcome_model(
        seed=training_seed,
        samples_per_context_action=training_samples_per_context_action,
    )
    model = BetaBernoulliOutcomeModel.from_snapshot(model.to_snapshot())
    records = collect_balanced_forecast_records(
        model,
        seed=calibration_seed,
        samples_per_context_action=calibration_samples_per_context_action,
    )
    calibration = calibration_metrics(records)
    selective, never, always = evaluate_information_policies(
        model,
        seeds=normalized_seeds,
        episodes_per_seed=policy_episodes_per_seed,
    )
    return UncertaintySuiteReport(
        training_seed=training_seed,
        evaluation_seeds=normalized_seeds,
        training_samples_per_context_action=(
            training_samples_per_context_action
        ),
        training_experience_count=model.experience_count,
        calibration_samples_per_context_action=(
            calibration_samples_per_context_action
        ),
        calibration=calibration,
        policy_episodes_per_seed=policy_episodes_per_seed,
        selective=selective,
        never_inspect=never,
        always_inspect=always,
        selective_utility_delta_vs_never=(
            selective.mean_utility - never.mean_utility
        ),
        selective_utility_delta_vs_always=(
            selective.mean_utility - always.mean_utility
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Training, calibration, and policy evaluation use disjoint RNG "
            "seeds. Calibration outcomes are not used to update the model."
        ),
        limitations=(
            "The hidden-state structure and inspect action semantics are hand-authored.",
            "Training collection is balanced and controlled, not autonomous.",
            "The policy threshold is fixed rather than learned.",
            "The environment has only two hidden states and known action vocabulary.",
            "ECE depends on the pre-registered ten-bin partition.",
            "The evaluator is local and is not independent E3 evidence.",
            "Success does not imply consciousness, general intelligence, emotion, or personhood.",
        ),
    )


def record_uncertainty_result(
    kernel: DarwinKernelV50,
    report: UncertaintySuiteReport,
    *,
    minimum_utility_advantage: float = 0.02,
) -> ObservationResult:
    if not math.isfinite(minimum_utility_advantage):
        raise ValidationError("minimum_utility_advantage must be finite")
    goal = kernel.create_goal(
        session_id=(
            f"uncertainty-lab:{report.training_seed}:"
            f"{report.evaluation_seeds[0]}:{report.evaluation_seeds[-1]}"
        ),
        description=(
            "Selective information use exceeds both fixed information policies"
        ),
        evidence_source=LOCAL_UNCERTAINTY_EVALUATOR,
        condition=ComparisonCondition(
            "minimum_utility_advantage",
            ComparisonOperator.GREATER_THAN_OR_EQUAL,
            minimum_utility_advantage,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-probabilistic-information-policy",
        parameters={
            "training_seed": report.training_seed,
            "evaluation_seeds": list(report.evaluation_seeds),
            "calibration_records": report.calibration.records,
            "policy_episodes_per_seed": report.policy_episodes_per_seed,
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_UNCERTAINTY_EVALUATOR,
        metrics={
            "brier_score": report.calibration.brier_score,
            "expected_calibration_error": (
                report.calibration.expected_calibration_error
            ),
            "selective_inspection_rate": report.selective.inspection_rate,
            "selective_mean_utility": report.selective.mean_utility,
            "never_inspect_mean_utility": report.never_inspect.mean_utility,
            "always_inspect_mean_utility": report.always_inspect.mean_utility,
            "selective_utility_delta_vs_never": (
                report.selective_utility_delta_vs_never
            ),
            "selective_utility_delta_vs_always": (
                report.selective_utility_delta_vs_always
            ),
            "minimum_utility_advantage": report.minimum_utility_advantage,
        },
    )


def report_with_utility_advantages(
    report: UncertaintySuiteReport,
    *,
    delta_vs_never: float,
    delta_vs_always: float,
) -> UncertaintySuiteReport:
    return replace(
        report,
        selective_utility_delta_vs_never=delta_vs_never,
        selective_utility_delta_vs_always=delta_vs_always,
    )


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Darwin H50-L3 uncertainty calibration benchmark."
    )
    parser.add_argument("--training-seed", type=int, default=7300)
    parser.add_argument("--calibration-seed", type=int, default=7400)
    parser.add_argument(
        "--evaluation-seeds",
        type=_parse_seeds,
        default=tuple(range(7500, 7520)),
    )
    parser.add_argument(
        "--training-samples-per-pair",
        type=int,
        default=250,
    )
    parser.add_argument(
        "--calibration-samples-per-pair",
        type=int,
        default=500,
    )
    parser.add_argument("--policy-episodes-per-seed", type=int, default=500)
    args = parser.parse_args(argv)
    report = run_uncertainty_suite(
        training_seed=args.training_seed,
        calibration_seed=args.calibration_seed,
        evaluation_seeds=args.evaluation_seeds,
        training_samples_per_context_action=args.training_samples_per_pair,
        calibration_samples_per_context_action=(
            args.calibration_samples_per_pair
        ),
        policy_episodes_per_seed=args.policy_episodes_per_seed,
    )
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
