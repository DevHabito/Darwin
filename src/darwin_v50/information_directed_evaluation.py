"""Registered evaluator for Darwin H50-L13 information-directed control."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
from statistics import fmean
from typing import Any, Iterable, Sequence

from .information_directed_lab import (
    IDS_POSTERIOR_SAMPLE_COUNT,
    InformationDirectedAgent,
    InformationDirectedDecision,
)
from .kernel import DarwinKernelV50
from .learned_context_lab import (
    LearnedContextWorld,
    LearnedContextWorldSpecification,
)
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)
from .online_posterior_evaluation import (
    ONLINE_EPSILON,
    ONLINE_FINAL_QUARTER_COUNT,
    ONLINE_INTERACTION_COUNT,
    OnlineEpisode,
    _run_mean_policy,
    _run_oracle_policy,
    _run_posterior_policy,
    _run_random_policy,
    _world_signature,
    make_online_schedule,
)
from .online_posterior_lab import (
    ONLINE_ENVIRONMENT_EPISODE_LENGTH,
    OnlineExperience,
)


IDS_DEVELOPMENT_SEEDS = tuple(range(24000, 24032))
IDS_FINAL_SEEDS = tuple(range(24100, 24200))
IDS_BLOCK_LENGTH_CANDIDATES = (4, 8, 16)
IDS_MODEL_XOR_MASK = 0x1D5A11
IDS_ACTION_XOR_MASK = 0x1D5AC7
IDS_POSTERIOR_BASELINE_XOR_MASK = 0x1D5B45

LOCAL_INFORMATION_DIRECTED_EVALUATOR = (
    "darwin_v50.information_directed_evaluation.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class IDSDevelopmentScore:
    block_length: int
    mean_reward: float
    mean_combined_model_error: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_length": self.block_length,
            "mean_reward": self.mean_reward,
            "mean_combined_model_error": self.mean_combined_model_error,
        }


@dataclass(frozen=True, slots=True)
class IDSDevelopmentSelection:
    seeds: tuple[int, ...]
    candidate_scores: tuple[IDSDevelopmentScore, ...]
    selected_block_length: int

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_block_length": self.selected_block_length,
        }
        if include_scores:
            result["candidate_scores"] = [
                score.to_dict() for score in self.candidate_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class IDSWorldResult:
    seed: int
    true_order: int
    map_order: int
    order_correct: bool
    true_order_posterior_mass: float
    transition_probability_error: float
    reward_probability_error: float
    candidate_mean_reward: float
    candidate_final_quarter_reward: float
    certainty_equivalent_mean_reward: float
    posterior_sampling_mean_reward: float
    epsilon_greedy_mean_reward: float
    random_mean_reward: float
    oracle_mean_reward: float
    oracle_final_quarter_reward: float
    bayesian_regret: float
    mean_action_information_gain: float
    mean_information_ratio: float | None
    finite_diagnostic_rate: float
    simultaneous_baseline_win: bool
    archive_retained: bool
    snapshot_round_trip_exact: bool
    causal_field_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field) for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class IDSSuiteReport:
    development: IDSDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[IDSWorldResult, ...]
    final_world_count: int
    unique_world_count: int
    true_order_counts: dict[int, int]
    map_order_counts: dict[int, int]
    order_confusion: dict[str, int]
    candidate_mean_reward: float
    candidate_final_quarter_reward: float
    certainty_equivalent_mean_reward: float
    posterior_sampling_mean_reward: float
    epsilon_greedy_mean_reward: float
    random_mean_reward: float
    oracle_mean_reward: float
    oracle_final_quarter_reward: float
    candidate_oracle_total_reward_ratio: float
    candidate_oracle_final_quarter_reward_ratio: float
    improvement_vs_certainty_equivalent: float
    improvement_vs_posterior_sampling: float
    improvement_vs_epsilon_greedy: float
    improvement_vs_random: float
    simultaneous_baseline_world_win_rate: float
    exact_order_recovery_rate: float
    mean_true_order_posterior_mass: float
    transition_probability_error: float
    reward_probability_error: float
    mean_bayesian_regret: float
    mean_action_information_gain: float
    mean_information_ratio: float | None
    finite_diagnostic_rate: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    causal_field_rate: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_total_oracle_ratio: float = 0.80,
        minimum_final_quarter_oracle_ratio: float = 0.90,
        minimum_improvement_vs_certainty: float = 0.005,
        minimum_improvement_vs_posterior: float = 0.010,
        minimum_improvement_vs_epsilon: float = 0.005,
        minimum_improvement_vs_random: float = 0.050,
        minimum_simultaneous_win_rate: float = 0.60,
        minimum_order_recovery: float = 0.70,
        minimum_true_order_mass: float = 0.65,
        maximum_transition_error: float = 0.08,
        maximum_reward_error: float = 0.08,
        minimum_finite_diagnostic_rate: float = 1.0,
        minimum_archive_rate: float = 1.0,
        minimum_snapshot_rate: float = 1.0,
        minimum_causal_field_rate: float = 1.0,
    ) -> bool:
        return (
            self.candidate_oracle_total_reward_ratio
            >= minimum_total_oracle_ratio
            and self.candidate_oracle_final_quarter_reward_ratio
            >= minimum_final_quarter_oracle_ratio
            and self.improvement_vs_certainty_equivalent
            >= minimum_improvement_vs_certainty
            and self.improvement_vs_posterior_sampling
            >= minimum_improvement_vs_posterior
            and self.improvement_vs_epsilon_greedy
            >= minimum_improvement_vs_epsilon
            and self.improvement_vs_random >= minimum_improvement_vs_random
            and self.simultaneous_baseline_world_win_rate
            >= minimum_simultaneous_win_rate
            and self.exact_order_recovery_rate >= minimum_order_recovery
            and self.mean_true_order_posterior_mass
            >= minimum_true_order_mass
            and self.transition_probability_error <= maximum_transition_error
            and self.reward_probability_error <= maximum_reward_error
            and self.finite_diagnostic_rate
            >= minimum_finite_diagnostic_rate
            and self.archive_retention_rate >= minimum_archive_rate
            and self.snapshot_round_trip_rate >= minimum_snapshot_rate
            and self.causal_field_rate >= minimum_causal_field_rate
        )

    def to_dict(
        self,
        *,
        include_development_scores: bool = True,
        include_worlds: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
            if field not in {"development", "worlds", "limitations"}
        }
        result["experiment"] = "H50-L13"
        result["development"] = self.development.to_dict(
            include_scores=include_development_scores
        )
        result["final_seeds"] = list(self.final_seeds)
        result["limitations"] = list(self.limitations)
        result["passes_regression_criteria"] = (
            self.passes_regression_criteria()
        )
        if include_worlds:
            result["worlds"] = [world.to_dict() for world in self.worlds]
        return result


@dataclass(slots=True)
class _IDSRun:
    rewards: tuple[bool, ...]
    decisions: tuple[InformationDirectedDecision, ...]
    agent: InformationDirectedAgent
    archive_retained: bool
    snapshot_round_trip_exact: bool
    causal_field_complete: bool

    @property
    def mean_reward(self) -> float:
        return fmean(float(value) for value in self.rewards)

    @property
    def final_quarter_reward(self) -> float:
        return fmean(
            float(value)
            for value in self.rewards[-ONLINE_FINAL_QUARTER_COUNT:]
        )


def _normalize_seeds(seeds: Iterable[int], *, field: str) -> tuple[int, ...]:
    normalized = tuple(seeds)
    if (
        not normalized
        or len(set(normalized)) != len(normalized)
        or any(
            isinstance(seed, bool) or not isinstance(seed, int)
            for seed in normalized
        )
    ):
        raise ValidationError(f"{field} seeds must be unique integers")
    return normalized


def _normalize_lengths(lengths: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(lengths)
    if (
        not normalized
        or len(set(normalized)) != len(normalized)
        or tuple(sorted(normalized)) != normalized
        or any(
            isinstance(length, bool)
            or not isinstance(length, int)
            or length < 1
            or ONLINE_ENVIRONMENT_EPISODE_LENGTH % length != 0
            for length in normalized
        )
    ):
        raise ValidationError(
            "IDS block lengths must be unique increasing episode divisors"
        )
    return normalized


def _run_information_directed_policy(
    seed: int,
    schedule: Sequence[OnlineEpisode],
    *,
    block_length: int,
    check_snapshot: bool = False,
) -> _IDSRun:
    world = LearnedContextWorld(seed)
    agent = InformationDirectedAgent(
        world_id=world.world_id,
        model_seed=seed ^ IDS_MODEL_XOR_MASK,
        action_seed=seed ^ IDS_ACTION_XOR_MASK,
        block_length=block_length,
        sample_count=IDS_POSTERIOR_SAMPLE_COUNT,
    )
    rewards: list[bool] = []
    decisions: list[InformationDirectedDecision] = []
    midpoint_exact = not check_snapshot
    midpoint_archive = not check_snapshot
    for episode_index, episode in enumerate(schedule, start=1):
        world.reset(
            initial_history=episode.initial_history,
            max_steps=ONLINE_ENVIRONMENT_EPISODE_LENGTH,
            episode_seed=episode.episode_seed,
        )
        agent.begin_episode(
            episode_index=episode_index,
            initial_history=episode.initial_history,
        )
        for _ in range(ONLINE_ENVIRONMENT_EPISODE_LENGTH):
            if check_snapshot and len(rewards) == ONLINE_INTERACTION_COUNT // 2:
                snapshot = agent.to_snapshot()
                restored = InformationDirectedAgent.from_snapshot(snapshot)
                initial_exact = restored.to_snapshot() == snapshot
                midpoint_archive = (
                    restored.model.archive.items == agent.model.archive.items
                    and len(restored.model.archive.items)
                    == ONLINE_INTERACTION_COUNT // 2
                )
                decision = agent.action()
                restored_decision = restored.action()
                midpoint_exact = initial_exact and decision == restored_decision
            else:
                decision = agent.action()
            step = world.step(decision.action)
            agent.observe(
                next_observation=step.observation.observation,
                reward=step.reward,
            )
            rewards.append(step.reward)
            decisions.append(decision)
            if world.current_history_for_evaluator != agent.current_history:
                raise RuntimeError("IDS history diverged from evaluator")
    if check_snapshot:
        final_snapshot = agent.to_snapshot()
        final_restored = InformationDirectedAgent.from_snapshot(final_snapshot)
        snapshot_exact = (
            midpoint_exact
            and final_restored.to_snapshot() == final_snapshot
            and final_restored.model.archive.items == agent.model.archive.items
        )
        archive_retained = (
            midpoint_archive
            and len(agent.model.archive.items) == ONLINE_INTERACTION_COUNT
            and final_restored.model.archive.items == agent.model.archive.items
        )
    else:
        snapshot_exact = False
        archive_retained = (
            len(agent.model.archive.items) == ONLINE_INTERACTION_COUNT
        )
    causal_fields = all(
        set(item.to_dict()) == OnlineExperience.FIELDS
        for item in agent.model.archive.items
    )
    if (
        len(rewards) != ONLINE_INTERACTION_COUNT
        or len(decisions) != ONLINE_INTERACTION_COUNT
    ):
        raise RuntimeError("IDS online trace is incomplete")
    return _IDSRun(
        rewards=tuple(rewards),
        decisions=tuple(decisions),
        agent=agent,
        archive_retained=archive_retained,
        snapshot_round_trip_exact=snapshot_exact,
        causal_field_complete=causal_fields,
    )


def select_ids_block_length(
    seeds: Iterable[int] = IDS_DEVELOPMENT_SEEDS,
    *,
    candidates: Sequence[int] = IDS_BLOCK_LENGTH_CANDIDATES,
) -> IDSDevelopmentSelection:
    normalized_seeds = _normalize_seeds(seeds, field="development")
    normalized_lengths = _normalize_lengths(candidates)
    rewards = {length: [] for length in normalized_lengths}
    errors = {length: [] for length in normalized_lengths}
    for seed in normalized_seeds:
        schedule = make_online_schedule(seed)
        specification = LearnedContextWorldSpecification.from_seed(seed)
        for length in normalized_lengths:
            run = _run_information_directed_policy(
                seed, schedule, block_length=length
            )
            transition_error, reward_error = run.agent.model.probability_errors(
                specification
            )
            rewards[length].append(run.mean_reward)
            errors[length].append(transition_error + reward_error)
    scores = tuple(
        IDSDevelopmentScore(
            block_length=length,
            mean_reward=fmean(rewards[length]),
            mean_combined_model_error=fmean(errors[length]),
        )
        for length in normalized_lengths
    )
    selected = min(
        scores,
        key=lambda score: (
            -score.mean_reward,
            score.mean_combined_model_error,
            score.block_length,
        ),
    )
    return IDSDevelopmentSelection(
        seeds=normalized_seeds,
        candidate_scores=scores,
        selected_block_length=selected.block_length,
    )


def run_ids_world(seed: int, *, selected_block_length: int) -> IDSWorldResult:
    schedule = make_online_schedule(seed)
    candidate = _run_information_directed_policy(
        seed,
        schedule,
        block_length=selected_block_length,
        check_snapshot=True,
    )
    certainty = _run_mean_policy(
        seed, schedule, resampling_length=selected_block_length
    )
    posterior = _run_posterior_policy(
        seed,
        schedule,
        resampling_length=selected_block_length,
        policy_seed_mask=IDS_POSTERIOR_BASELINE_XOR_MASK,
    )
    epsilon = _run_mean_policy(
        seed,
        schedule,
        resampling_length=selected_block_length,
        epsilon=ONLINE_EPSILON,
    )
    random_run = _run_random_policy(seed, schedule)
    oracle = _run_oracle_policy(
        seed, schedule, resampling_length=selected_block_length
    )
    specification = LearnedContextWorldSpecification.from_seed(seed)
    model = candidate.agent.model
    order_posterior = model.order_posterior()
    transition_error, reward_error = model.probability_errors(specification)
    finite_ratios = tuple(
        decision.information_ratio
        for decision in candidate.decisions
        if decision.information_ratio is not None
    )
    candidate_total = sum(candidate.rewards)
    return IDSWorldResult(
        seed=seed,
        true_order=specification.true_order,
        map_order=model.map_order,
        order_correct=(model.map_order == specification.true_order),
        true_order_posterior_mass=order_posterior[specification.true_order],
        transition_probability_error=transition_error,
        reward_probability_error=reward_error,
        candidate_mean_reward=candidate.mean_reward,
        candidate_final_quarter_reward=candidate.final_quarter_reward,
        certainty_equivalent_mean_reward=certainty.mean_reward,
        posterior_sampling_mean_reward=posterior.mean_reward,
        epsilon_greedy_mean_reward=epsilon.mean_reward,
        random_mean_reward=random_run.mean_reward,
        oracle_mean_reward=oracle.mean_reward,
        oracle_final_quarter_reward=oracle.final_quarter_reward,
        bayesian_regret=float(sum(oracle.rewards) - candidate_total),
        mean_action_information_gain=fmean(
            decision.information_gain for decision in candidate.decisions
        ),
        mean_information_ratio=(
            fmean(finite_ratios) if finite_ratios else None
        ),
        finite_diagnostic_rate=(
            len(finite_ratios) / len(candidate.decisions)
        ),
        simultaneous_baseline_win=(
            candidate_total > sum(certainty.rewards)
            and candidate_total > sum(posterior.rewards)
            and candidate_total > sum(epsilon.rewards)
        ),
        archive_retained=candidate.archive_retained,
        snapshot_round_trip_exact=candidate.snapshot_round_trip_exact,
        causal_field_complete=candidate.causal_field_complete,
    )


def run_ids_suite(
    *,
    development_seeds: Iterable[int] = IDS_DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = IDS_FINAL_SEEDS,
    candidates: Sequence[int] = IDS_BLOCK_LENGTH_CANDIDATES,
) -> IDSSuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds, field="development"
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("IDS development and final seeds must be disjoint")
    development = select_ids_block_length(
        development_seed_tuple, candidates=candidates
    )
    worlds = tuple(
        run_ids_world(
            seed,
            selected_block_length=development.selected_block_length,
        )
        for seed in final_seed_tuple
    )
    mean_fields = (
        "candidate_mean_reward",
        "candidate_final_quarter_reward",
        "certainty_equivalent_mean_reward",
        "posterior_sampling_mean_reward",
        "epsilon_greedy_mean_reward",
        "random_mean_reward",
        "oracle_mean_reward",
        "oracle_final_quarter_reward",
    )
    means = {
        field: fmean(getattr(world, field) for world in worlds)
        for field in mean_fields
    }
    candidate_mean = means["candidate_mean_reward"]
    candidate_final = means["candidate_final_quarter_reward"]
    oracle_mean = means["oracle_mean_reward"]
    oracle_final = means["oracle_final_quarter_reward"]
    finite_world_ratios = tuple(
        world.mean_information_ratio
        for world in worlds
        if world.mean_information_ratio is not None
    )
    return IDSSuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        unique_world_count=len(
            {_world_signature(seed) for seed in final_seed_tuple}
        ),
        true_order_counts={
            order: sum(world.true_order == order for world in worlds)
            for order in (2, 3, 4, 5)
        },
        map_order_counts={
            order: sum(world.map_order == order for world in worlds)
            for order in (1, 2, 3, 4, 5)
        },
        order_confusion={
            f"{true_order}->{map_order}": sum(
                world.true_order == true_order and world.map_order == map_order
                for world in worlds
            )
            for true_order in (2, 3, 4, 5)
            for map_order in (1, 2, 3, 4, 5)
            if any(
                world.true_order == true_order and world.map_order == map_order
                for world in worlds
            )
        },
        candidate_mean_reward=candidate_mean,
        candidate_final_quarter_reward=candidate_final,
        certainty_equivalent_mean_reward=means[
            "certainty_equivalent_mean_reward"
        ],
        posterior_sampling_mean_reward=means[
            "posterior_sampling_mean_reward"
        ],
        epsilon_greedy_mean_reward=means["epsilon_greedy_mean_reward"],
        random_mean_reward=means["random_mean_reward"],
        oracle_mean_reward=oracle_mean,
        oracle_final_quarter_reward=oracle_final,
        candidate_oracle_total_reward_ratio=(
            candidate_mean / oracle_mean if oracle_mean > 0.0 else 0.0
        ),
        candidate_oracle_final_quarter_reward_ratio=(
            candidate_final / oracle_final if oracle_final > 0.0 else 0.0
        ),
        improvement_vs_certainty_equivalent=(
            candidate_mean - means["certainty_equivalent_mean_reward"]
        ),
        improvement_vs_posterior_sampling=(
            candidate_mean - means["posterior_sampling_mean_reward"]
        ),
        improvement_vs_epsilon_greedy=(
            candidate_mean - means["epsilon_greedy_mean_reward"]
        ),
        improvement_vs_random=(candidate_mean - means["random_mean_reward"]),
        simultaneous_baseline_world_win_rate=fmean(
            float(world.simultaneous_baseline_win) for world in worlds
        ),
        exact_order_recovery_rate=fmean(
            float(world.order_correct) for world in worlds
        ),
        mean_true_order_posterior_mass=fmean(
            world.true_order_posterior_mass for world in worlds
        ),
        transition_probability_error=fmean(
            world.transition_probability_error for world in worlds
        ),
        reward_probability_error=fmean(
            world.reward_probability_error for world in worlds
        ),
        mean_bayesian_regret=fmean(world.bayesian_regret for world in worlds),
        mean_action_information_gain=fmean(
            world.mean_action_information_gain for world in worlds
        ),
        mean_information_ratio=(
            fmean(finite_world_ratios) if finite_world_ratios else None
        ),
        finite_diagnostic_rate=fmean(
            world.finite_diagnostic_rate for world in worlds
        ),
        archive_retention_rate=fmean(
            float(world.archive_retained) for world in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(world.snapshot_round_trip_exact) for world in worlds
        ),
        causal_field_rate=fmean(
            float(world.causal_field_complete) for world in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Block length is selected only on development seeds "
            f"{development_seed_tuple[0]}-{development_seed_tuple[-1]}. "
            "Final metrics use disjoint supplied seeds "
            f"{final_seed_tuple[0]}-{final_seed_tuple[-1]}, 40 paired "
            "32-action episodes, chosen-action feedback, separate model, "
            "action, and exogenous streams, and 16 posterior models per block."
        ),
        limitations=(
            "The candidate is a finite-sample blockwise approximation, not exact IDS.",
            "Published IDS or RL regret bounds do not transfer to this evaluator.",
            "The environment is synthetic, stationary, binary, and tabular.",
            "Candidate context orders one through five are supplied by the design.",
            "Transition and reward outcomes are modeled as conditionally independent.",
            "No learned state transfers between worlds.",
            "The local evaluator cannot provide independent E3 evidence.",
            "Success would not imply consciousness, personhood, AGI, or a "
            "Diana-like mind.",
        ),
    )


def record_ids_result(
    kernel: DarwinKernelV50, report: IDSSuiteReport
) -> ObservationResult:
    goal = kernel.create_goal(
        session_id=f"ids:{report.final_seeds[0]}:{report.final_seeds[-1]}",
        description="Information-directed control reduces registered regret",
        evidence_source=LOCAL_INFORMATION_DIRECTED_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-information-directed-control",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_block_length": report.development.selected_block_length,
            "posterior_sample_count": IDS_POSTERIOR_SAMPLE_COUNT,
            "evidence_level": report.evidence_level,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_INFORMATION_DIRECTED_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": (
                report.passes_regression_criteria()
            ),
            "candidate_oracle_total_reward_ratio": (
                report.candidate_oracle_total_reward_ratio
            ),
            "candidate_oracle_final_quarter_reward_ratio": (
                report.candidate_oracle_final_quarter_reward_ratio
            ),
            "improvement_vs_certainty_equivalent": (
                report.improvement_vs_certainty_equivalent
            ),
            "improvement_vs_posterior_sampling": (
                report.improvement_vs_posterior_sampling
            ),
            "improvement_vs_epsilon_greedy": (
                report.improvement_vs_epsilon_greedy
            ),
            "improvement_vs_random": report.improvement_vs_random,
            "simultaneous_baseline_world_win_rate": (
                report.simultaneous_baseline_world_win_rate
            ),
            "exact_order_recovery_rate": report.exact_order_recovery_rate,
            "mean_true_order_posterior_mass": (
                report.mean_true_order_posterior_mass
            ),
            "transition_probability_error": (
                report.transition_probability_error
            ),
            "reward_probability_error": report.reward_probability_error,
            "finite_diagnostic_rate": report.finite_diagnostic_rate,
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
            "causal_field_rate": report.causal_field_rate,
        },
    )


def report_with_ids_metrics(
    report: IDSSuiteReport, **changes: Any
) -> IDSSuiteReport:
    return replace(report, **changes)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(
            int(part.strip()) for part in raw.split(",") if part.strip()
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError("IDS seeds must be integers") from error
    if not values:
        raise argparse.ArgumentTypeError("provide at least one IDS seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the pre-registered Darwin H50-L13 benchmark."
    )
    parser.add_argument(
        "--development-seeds", type=_parse_seeds, default=IDS_DEVELOPMENT_SEEDS
    )
    parser.add_argument(
        "--final-seeds", type=_parse_seeds, default=IDS_FINAL_SEEDS
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args(argv)
    if args.development_only:
        selection = select_ids_block_length(args.development_seeds)
        print(json.dumps(selection.to_dict(), indent=2, sort_keys=True))
        return 0
    report = run_ids_suite(
        development_seeds=args.development_seeds,
        final_seeds=args.final_seeds,
    )
    print(
        json.dumps(
            report.to_dict(
                include_development_scores=args.development_scores,
                include_worlds=args.details,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passes_regression_criteria() else 1


if __name__ == "__main__":
    raise SystemExit(main())
