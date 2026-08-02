"""Held-out benchmark for Darwin H50-L9 episodic contextual action memory."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from itertools import product
import json
import math
from statistics import fmean
from typing import Any, Iterable, Sequence

from .episodic_context_lab import (
    ACTION_COUNT,
    CONTEXT_LABELS,
    EPISODE_COUNT,
    STEPS_PER_EPISODE,
    EpisodicActionMemory,
    EpisodicContextWorld,
    EpisodicStep,
    EpisodicWorldSpecification,
    EpisodeRetrievalDecision,
    forced_action,
)
from .kernel import DarwinKernelV50
from .models import (
    ComparisonCondition,
    ComparisonOperator,
    ObservationResult,
    ValidationError,
)


EPISODIC_DEVELOPMENT_SEEDS = tuple(range(14000, 14032))
EPISODIC_FINAL_SEEDS = tuple(range(14100, 14200))
EPISODIC_MINIMUM_CUE_CANDIDATES = (4, 6, 8)
EPISODIC_TOLERANCE_CANDIDATES = (0.18, 0.24, 0.30)
EPISODIC_EARLY_STEPS = 12
LOCAL_EPISODIC_EVALUATOR = (
    "darwin_v50.episodic_context_lab.local_evaluator"
)


@dataclass(frozen=True, slots=True)
class EpisodicCandidateScore:
    minimum_cues: int
    match_tolerance: float
    mean_total_reward: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_cues": self.minimum_cues,
            "match_tolerance": self.match_tolerance,
            "mean_total_reward": self.mean_total_reward,
        }


@dataclass(frozen=True, slots=True)
class EpisodicDevelopmentSelection:
    seeds: tuple[int, ...]
    candidate_scores: tuple[EpisodicCandidateScore, ...]
    selected_minimum_cues: int
    selected_match_tolerance: float

    def to_dict(self, *, include_scores: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seeds": list(self.seeds),
            "selected_minimum_cues": self.selected_minimum_cues,
            "selected_match_tolerance": self.selected_match_tolerance,
        }
        if include_scores:
            result["candidate_scores"] = [
                item.to_dict() for item in self.candidate_scores
            ]
        return result


@dataclass(frozen=True, slots=True)
class EpisodicPolicyStep:
    episode_index: int
    step_index: int
    context_label: str
    action: int
    reward: bool


@dataclass(frozen=True, slots=True)
class EpisodicWorldResult:
    seed: int
    family: str
    local_total_reward: float
    global_total_reward: float
    candidate_total_reward: float
    oracle_total_reward: float
    recurrence_count: int
    local_recurrence_reward_sum: int
    candidate_recurrence_reward_sum: int
    novelty_count: int
    local_novelty_reward_sum: int
    candidate_novelty_reward_sum: int
    recurrence_episode_count: int
    correctly_retrieved_recurrence_count: int
    retrieval_decision_count: int
    correct_retrieval_decision_count: int
    novelty_episode_count: int
    novelty_abstention_count: int
    novelty_false_retrieval_count: int
    archive_retained: bool
    snapshot_round_trip_exact: bool
    prototype_count: int

    @property
    def total_improvement_vs_local(self) -> float:
        return self.candidate_total_reward - self.local_total_reward

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "family": self.family,
            "local_total_reward": self.local_total_reward,
            "global_total_reward": self.global_total_reward,
            "candidate_total_reward": self.candidate_total_reward,
            "oracle_total_reward": self.oracle_total_reward,
            "total_improvement_vs_local": self.total_improvement_vs_local,
            "local_recurrence_reward": (
                self.local_recurrence_reward_sum / self.recurrence_count
            ),
            "candidate_recurrence_reward": (
                self.candidate_recurrence_reward_sum
                / self.recurrence_count
            ),
            "local_novelty_reward": (
                self.local_novelty_reward_sum / self.novelty_count
                if self.novelty_count
                else None
            ),
            "candidate_novelty_reward": (
                self.candidate_novelty_reward_sum / self.novelty_count
                if self.novelty_count
                else None
            ),
            "recurrence_episode_count": self.recurrence_episode_count,
            "correctly_retrieved_recurrence_count": (
                self.correctly_retrieved_recurrence_count
            ),
            "retrieval_decision_count": self.retrieval_decision_count,
            "correct_retrieval_decision_count": (
                self.correct_retrieval_decision_count
            ),
            "novelty_episode_count": self.novelty_episode_count,
            "novelty_abstention_count": self.novelty_abstention_count,
            "novelty_false_retrieval_count": (
                self.novelty_false_retrieval_count
            ),
            "archive_retained": self.archive_retained,
            "snapshot_round_trip_exact": self.snapshot_round_trip_exact,
            "prototype_count": self.prototype_count,
        }


@dataclass(frozen=True, slots=True)
class EpisodicSuiteReport:
    development: EpisodicDevelopmentSelection
    final_seeds: tuple[int, ...]
    worlds: tuple[EpisodicWorldResult, ...]
    final_world_count: int
    family_counts: dict[str, int]
    unique_world_count: int
    local_total_reward: float
    global_total_reward: float
    candidate_total_reward: float
    oracle_total_reward: float
    total_improvement_vs_local: float
    world_win_rate_vs_local: float
    total_improvement_vs_global: float
    recurrence_improvement_vs_local: float
    exact_recurrence_improvement_vs_local: float
    cue_drift_improvement_vs_local: float
    reward_drift_improvement_vs_local: float
    novelty_degradation_vs_local: float
    gap_to_oracle: float
    correct_recurrence_retrieval_coverage: float
    retrieval_precision: float
    novelty_abstention_coverage: float
    novelty_false_retrieval_rate: float
    archive_retention_rate: float
    snapshot_round_trip_rate: float
    mean_prototype_count: float
    evidence_level: str
    held_out_definition: str
    limitations: tuple[str, ...]

    def passes_regression_criteria(
        self,
        *,
        minimum_total_improvement_vs_local: float = 0.04,
        minimum_world_win_rate_vs_local: float = 0.75,
        minimum_total_improvement_vs_global: float = 0.05,
        minimum_recurrence_improvement_vs_local: float = 0.06,
        minimum_exact_recurrence_improvement_vs_local: float = 0.08,
        minimum_cue_drift_improvement_vs_local: float = 0.05,
        minimum_reward_drift_improvement_vs_local: float = 0.05,
        maximum_novelty_degradation_vs_local: float = 0.02,
        maximum_gap_to_oracle: float = 0.15,
        minimum_correct_recurrence_retrieval_coverage: float = 0.85,
        minimum_retrieval_precision: float = 0.90,
        minimum_novelty_abstention_coverage: float = 0.80,
        maximum_novelty_false_retrieval_rate: float = 0.10,
        minimum_archive_retention_rate: float = 1.0,
        minimum_snapshot_round_trip_rate: float = 1.0,
    ) -> bool:
        return (
            self.total_improvement_vs_local
            >= minimum_total_improvement_vs_local
            and self.world_win_rate_vs_local
            >= minimum_world_win_rate_vs_local
            and self.total_improvement_vs_global
            >= minimum_total_improvement_vs_global
            and self.recurrence_improvement_vs_local
            >= minimum_recurrence_improvement_vs_local
            and self.exact_recurrence_improvement_vs_local
            >= minimum_exact_recurrence_improvement_vs_local
            and self.cue_drift_improvement_vs_local
            >= minimum_cue_drift_improvement_vs_local
            and self.reward_drift_improvement_vs_local
            >= minimum_reward_drift_improvement_vs_local
            and self.novelty_degradation_vs_local
            <= maximum_novelty_degradation_vs_local
            and self.gap_to_oracle <= maximum_gap_to_oracle
            and self.correct_recurrence_retrieval_coverage
            >= minimum_correct_recurrence_retrieval_coverage
            and self.retrieval_precision >= minimum_retrieval_precision
            and self.novelty_abstention_coverage
            >= minimum_novelty_abstention_coverage
            and self.novelty_false_retrieval_rate
            <= maximum_novelty_false_retrieval_rate
            and self.archive_retention_rate >= minimum_archive_retention_rate
            and self.snapshot_round_trip_rate
            >= minimum_snapshot_round_trip_rate
        )

    def to_dict(
        self,
        *,
        include_development_scores: bool = True,
        include_worlds: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "development": self.development.to_dict(
                include_scores=include_development_scores
            ),
            "final_seeds": list(self.final_seeds),
            "final_world_count": self.final_world_count,
            "family_counts": self.family_counts,
            "unique_world_count": self.unique_world_count,
            "local_total_reward": self.local_total_reward,
            "global_total_reward": self.global_total_reward,
            "candidate_total_reward": self.candidate_total_reward,
            "oracle_total_reward": self.oracle_total_reward,
            "total_improvement_vs_local": self.total_improvement_vs_local,
            "world_win_rate_vs_local": self.world_win_rate_vs_local,
            "total_improvement_vs_global": (
                self.total_improvement_vs_global
            ),
            "recurrence_improvement_vs_local": (
                self.recurrence_improvement_vs_local
            ),
            "exact_recurrence_improvement_vs_local": (
                self.exact_recurrence_improvement_vs_local
            ),
            "cue_drift_improvement_vs_local": (
                self.cue_drift_improvement_vs_local
            ),
            "reward_drift_improvement_vs_local": (
                self.reward_drift_improvement_vs_local
            ),
            "novelty_degradation_vs_local": (
                self.novelty_degradation_vs_local
            ),
            "gap_to_oracle": self.gap_to_oracle,
            "correct_recurrence_retrieval_coverage": (
                self.correct_recurrence_retrieval_coverage
            ),
            "retrieval_precision": self.retrieval_precision,
            "novelty_abstention_coverage": (
                self.novelty_abstention_coverage
            ),
            "novelty_false_retrieval_rate": (
                self.novelty_false_retrieval_rate
            ),
            "archive_retention_rate": self.archive_retention_rate,
            "snapshot_round_trip_rate": self.snapshot_round_trip_rate,
            "mean_prototype_count": self.mean_prototype_count,
            "evidence_level": self.evidence_level,
            "held_out_definition": self.held_out_definition,
            "limitations": list(self.limitations),
            "passes_regression_criteria": self.passes_regression_criteria(),
        }
        if include_worlds:
            result["worlds"] = [item.to_dict() for item in self.worlds]
        return result


def _normalize_seeds(
    seeds: Iterable[int],
    *,
    field: str,
) -> tuple[int, ...]:
    result = tuple(seeds)
    if (
        not result
        or any(
            isinstance(seed, bool) or not isinstance(seed, int)
            for seed in result
        )
        or len(set(result)) != len(result)
    ):
        raise ValidationError(f"{field} seeds must be unique integers")
    return result


def _prototype_context_label(
    cue_means: Sequence[float],
    specification: EpisodicWorldSpecification,
) -> str:
    return min(
        CONTEXT_LABELS,
        key=lambda label: (
            sum(
                abs(left - right)
                for left, right in zip(
                    cue_means,
                    specification.context(label).cue_probabilities,
                    strict=True,
                )
            )
            / len(cue_means),
            label,
        ),
    )


def _retrieval_is_correct(
    decision: EpisodeRetrievalDecision,
    specification: EpisodicWorldSpecification,
) -> bool:
    if decision.prototype_cue_means is None:
        return False
    current_label = specification.episode_labels[
        decision.episode_index - 1
    ]
    return (
        _prototype_context_label(
            decision.prototype_cue_means,
            specification,
        )
        == current_label
    )


def _run_memory_policy(
    world: EpisodicContextWorld,
    *,
    minimum_cues: int,
    match_tolerance: float,
    memory_enabled: bool,
) -> tuple[
    tuple[EpisodicPolicyStep, ...],
    EpisodicActionMemory,
]:
    model = EpisodicActionMemory(
        minimum_cues=minimum_cues,
        match_tolerance=match_tolerance,
        memory_enabled=memory_enabled,
    )
    records: list[EpisodicPolicyStep] = []
    for episode_index in range(1, EPISODE_COUNT + 1):
        model.begin_episode(episode_index)
        for step in world.episode_steps(episode_index):
            model.observe_cues(step.cues)
            action = model.choose_action()
            outcome = step.potential_outcomes[action]
            model.observe_outcome(action, outcome)
            records.append(
                EpisodicPolicyStep(
                    episode_index=episode_index,
                    step_index=step.step_index,
                    context_label=step.context_label,
                    action=action,
                    reward=outcome,
                )
            )
        model.end_episode()
    return tuple(records), model


def _run_global_policy(
    world: EpisodicContextWorld,
) -> tuple[EpisodicPolicyStep, ...]:
    successes = [0] * ACTION_COUNT
    failures = [0] * ACTION_COUNT
    records: list[EpisodicPolicyStep] = []
    for step in world.steps:
        forced = forced_action(step.episode_index, step.step_index)
        if forced is not None:
            action = forced
        else:
            probabilities = tuple(
                (1 + successes[index])
                / (2 + successes[index] + failures[index])
                for index in range(ACTION_COUNT)
            )
            action = max(
                range(ACTION_COUNT),
                key=lambda index: (probabilities[index], -index),
            )
        outcome = step.potential_outcomes[action]
        successes[action] += int(outcome)
        failures[action] += int(not outcome)
        records.append(
            EpisodicPolicyStep(
                episode_index=step.episode_index,
                step_index=step.step_index,
                context_label=step.context_label,
                action=action,
                reward=outcome,
            )
        )
    return tuple(records)


def _run_oracle_policy(
    world: EpisodicContextWorld,
) -> tuple[EpisodicPolicyStep, ...]:
    records: list[EpisodicPolicyStep] = []
    for step in world.steps:
        forced = forced_action(step.episode_index, step.step_index)
        action = (
            forced
            if forced is not None
            else max(
                range(ACTION_COUNT),
                key=lambda index: (
                    step.reward_probabilities[index],
                    -index,
                ),
            )
        )
        records.append(
            EpisodicPolicyStep(
                episode_index=step.episode_index,
                step_index=step.step_index,
                context_label=step.context_label,
                action=action,
                reward=step.potential_outcomes[action],
            )
        )
    return tuple(records)


def _reward_rate(records: Sequence[EpisodicPolicyStep]) -> float:
    if not records:
        raise ValidationError("reward region cannot be empty")
    return fmean(float(item.reward) for item in records)


def _candidate_total_reward(
    seed: int,
    *,
    minimum_cues: int,
    match_tolerance: float,
) -> float:
    records, _ = _run_memory_policy(
        EpisodicContextWorld(seed),
        minimum_cues=minimum_cues,
        match_tolerance=match_tolerance,
        memory_enabled=True,
    )
    return _reward_rate(records)


def _validate_candidates(
    values: Sequence[int] | Sequence[float],
    *,
    field: str,
    integer: bool,
) -> tuple[int, ...] | tuple[float, ...]:
    result = tuple(values)
    if (
        not result
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
    ):
        raise ValidationError(
            f"{field} candidates must be unique and increasing"
        )
    for value in result:
        if isinstance(value, bool) or not isinstance(
            value,
            int if integer else (int, float),
        ):
            raise ValidationError(f"{field} candidate type is invalid")
        if integer and not 1 <= value <= STEPS_PER_EPISODE:
            raise ValidationError(f"{field} candidate value is invalid")
        if not integer and (
            not math.isfinite(value) or not 0.0 < value < 1.0
        ):
            raise ValidationError(f"{field} candidate value is invalid")
    return result


def select_episodic_configuration(
    seeds: Iterable[int] = EPISODIC_DEVELOPMENT_SEEDS,
    *,
    minimum_cue_candidates: Sequence[int] = (
        EPISODIC_MINIMUM_CUE_CANDIDATES
    ),
    tolerance_candidates: Sequence[float] = (
        EPISODIC_TOLERANCE_CANDIDATES
    ),
) -> EpisodicDevelopmentSelection:
    normalized = _normalize_seeds(seeds, field="development")
    minimum_cues = _validate_candidates(
        minimum_cue_candidates,
        field="minimum-cue",
        integer=True,
    )
    tolerances = _validate_candidates(
        tolerance_candidates,
        field="tolerance",
        integer=False,
    )
    scores = tuple(
        EpisodicCandidateScore(
            minimum_cues=int(cue_count),
            match_tolerance=float(tolerance),
            mean_total_reward=fmean(
                _candidate_total_reward(
                    seed,
                    minimum_cues=int(cue_count),
                    match_tolerance=float(tolerance),
                )
                for seed in normalized
            ),
        )
        for cue_count, tolerance in product(minimum_cues, tolerances)
    )
    selected = min(
        scores,
        key=lambda item: (
            -item.mean_total_reward,
            -item.minimum_cues,
            item.match_tolerance,
        ),
    )
    return EpisodicDevelopmentSelection(
        seeds=normalized,
        candidate_scores=scores,
        selected_minimum_cues=selected.minimum_cues,
        selected_match_tolerance=selected.match_tolerance,
    )


def _filter_region(
    records: Sequence[EpisodicPolicyStep],
    episode_indices: set[int],
) -> tuple[EpisodicPolicyStep, ...]:
    return tuple(
        item
        for item in records
        if item.episode_index in episode_indices
        and item.step_index <= EPISODIC_EARLY_STEPS
    )


def run_episodic_world(
    seed: int,
    *,
    selected_minimum_cues: int,
    selected_match_tolerance: float,
) -> EpisodicWorldResult:
    world = EpisodicContextWorld(seed)
    specification = world.specification
    local_records, _ = _run_memory_policy(
        world,
        minimum_cues=selected_minimum_cues,
        match_tolerance=selected_match_tolerance,
        memory_enabled=False,
    )
    candidate_records, candidate = _run_memory_policy(
        world,
        minimum_cues=selected_minimum_cues,
        match_tolerance=selected_match_tolerance,
        memory_enabled=True,
    )
    global_records = _run_global_policy(world)
    oracle_records = _run_oracle_policy(world)
    recurrence_episodes = set(specification.recurrence_episode_indices)
    novelty_episodes = set(specification.novelty_episode_indices)
    local_recurrence = _filter_region(
        local_records,
        recurrence_episodes,
    )
    candidate_recurrence = _filter_region(
        candidate_records,
        recurrence_episodes,
    )
    local_novelty = _filter_region(local_records, novelty_episodes)
    candidate_novelty = _filter_region(
        candidate_records,
        novelty_episodes,
    )
    decisions = candidate.retrieval_decisions
    recurrence_decisions = tuple(
        item
        for item in decisions
        if item.episode_index in recurrence_episodes
        and item.step_index <= EPISODIC_EARLY_STEPS
    )
    retrieved_decisions = tuple(
        item
        for item in decisions
        if item.retrieved_prototype_id is not None
    )
    novelty_decisions = tuple(
        item
        for item in decisions
        if item.episode_index in novelty_episodes
    )
    expected_archive = candidate.archive
    snapshot = candidate.to_snapshot()
    restored = EpisodicActionMemory.from_snapshot(snapshot)
    archive_retained = (
        len(expected_archive) == EPISODE_COUNT * STEPS_PER_EPISODE
        and restored.archive == expected_archive
    )
    snapshot_exact = (
        restored.to_snapshot() == snapshot
        and restored.archive == expected_archive
        and restored.prototypes == candidate.prototypes
        and restored.retrieval_decisions
        == candidate.retrieval_decisions
    )
    candidate.begin_episode(EPISODE_COUNT + 1)
    restored.begin_episode(EPISODE_COUNT + 1)
    probe_cues = (False, True, False, True)
    candidate.observe_cues(probe_cues)
    restored.observe_cues(probe_cues)
    snapshot_exact &= (
        candidate.choose_action() == restored.choose_action()
        and candidate.to_snapshot() == restored.to_snapshot()
    )
    return EpisodicWorldResult(
        seed=seed,
        family=specification.family,
        local_total_reward=_reward_rate(local_records),
        global_total_reward=_reward_rate(global_records),
        candidate_total_reward=_reward_rate(candidate_records),
        oracle_total_reward=_reward_rate(oracle_records),
        recurrence_count=len(local_recurrence),
        local_recurrence_reward_sum=sum(
            item.reward for item in local_recurrence
        ),
        candidate_recurrence_reward_sum=sum(
            item.reward for item in candidate_recurrence
        ),
        novelty_count=len(local_novelty),
        local_novelty_reward_sum=sum(item.reward for item in local_novelty),
        candidate_novelty_reward_sum=sum(
            item.reward for item in candidate_novelty
        ),
        recurrence_episode_count=len(recurrence_episodes),
        correctly_retrieved_recurrence_count=sum(
            _retrieval_is_correct(item, specification)
            for item in recurrence_decisions
        ),
        retrieval_decision_count=len(retrieved_decisions),
        correct_retrieval_decision_count=sum(
            _retrieval_is_correct(item, specification)
            for item in retrieved_decisions
        ),
        novelty_episode_count=len(novelty_episodes),
        novelty_abstention_count=sum(
            item.abstained for item in novelty_decisions
        ),
        novelty_false_retrieval_count=sum(
            item.retrieved_prototype_id is not None
            for item in novelty_decisions
        ),
        archive_retained=archive_retained,
        snapshot_round_trip_exact=snapshot_exact,
        prototype_count=len(restored.prototypes),
    )


def _pooled_reward(
    worlds: Sequence[EpisodicWorldResult],
    *,
    sum_field: str,
    count_field: str,
) -> float:
    count = sum(getattr(item, count_field) for item in worlds)
    if count < 1:
        raise ValidationError("pooled reward region cannot be empty")
    return sum(getattr(item, sum_field) for item in worlds) / count


def run_episodic_suite(
    *,
    development_seeds: Iterable[int] = EPISODIC_DEVELOPMENT_SEEDS,
    final_seeds: Iterable[int] = EPISODIC_FINAL_SEEDS,
    minimum_cue_candidates: Sequence[int] = (
        EPISODIC_MINIMUM_CUE_CANDIDATES
    ),
    tolerance_candidates: Sequence[float] = (
        EPISODIC_TOLERANCE_CANDIDATES
    ),
) -> EpisodicSuiteReport:
    development_seed_tuple = _normalize_seeds(
        development_seeds,
        field="development",
    )
    final_seed_tuple = _normalize_seeds(final_seeds, field="final")
    if set(development_seed_tuple) & set(final_seed_tuple):
        raise ValidationError("development and final seeds must be disjoint")
    development = select_episodic_configuration(
        development_seed_tuple,
        minimum_cue_candidates=minimum_cue_candidates,
        tolerance_candidates=tolerance_candidates,
    )
    worlds = tuple(
        run_episodic_world(
            seed,
            selected_minimum_cues=development.selected_minimum_cues,
            selected_match_tolerance=(
                development.selected_match_tolerance
            ),
        )
        for seed in final_seed_tuple
    )
    local_total = fmean(item.local_total_reward for item in worlds)
    global_total = fmean(item.global_total_reward for item in worlds)
    candidate_total = fmean(
        item.candidate_total_reward for item in worlds
    )
    oracle_total = fmean(item.oracle_total_reward for item in worlds)
    local_recurrence = _pooled_reward(
        worlds,
        sum_field="local_recurrence_reward_sum",
        count_field="recurrence_count",
    )
    candidate_recurrence = _pooled_reward(
        worlds,
        sum_field="candidate_recurrence_reward_sum",
        count_field="recurrence_count",
    )
    exact_worlds = tuple(
        item for item in worlds if item.family == "exact_recurrence"
    )
    cue_drift_worlds = tuple(
        item for item in worlds if item.family == "cue_drift"
    )
    reward_drift_worlds = tuple(
        item for item in worlds if item.family == "reward_drift"
    )

    def recurrence_improvement(
        selected_worlds: Sequence[EpisodicWorldResult],
    ) -> float:
        return _pooled_reward(
            selected_worlds,
            sum_field="candidate_recurrence_reward_sum",
            count_field="recurrence_count",
        ) - _pooled_reward(
            selected_worlds,
            sum_field="local_recurrence_reward_sum",
            count_field="recurrence_count",
        )

    novelty_worlds = tuple(item for item in worlds if item.novelty_count)
    local_novelty = _pooled_reward(
        novelty_worlds,
        sum_field="local_novelty_reward_sum",
        count_field="novelty_count",
    )
    candidate_novelty = _pooled_reward(
        novelty_worlds,
        sum_field="candidate_novelty_reward_sum",
        count_field="novelty_count",
    )
    recurrence_episode_count = sum(
        item.recurrence_episode_count for item in worlds
    )
    retrieval_count = sum(
        item.retrieval_decision_count for item in worlds
    )
    novelty_episode_count = sum(
        item.novelty_episode_count for item in worlds
    )
    family_counts = {
        family: sum(item.family == family for item in worlds)
        for family in (
            "exact_recurrence",
            "cue_drift",
            "reward_drift",
            "novelty",
        )
    }
    world_signatures = {
        (
            item.family,
            tuple(
                (
                    context.code,
                    context.base_reward_probabilities,
                )
                for context in EpisodicWorldSpecification.from_seed(
                    item.seed
                ).contexts
            ),
        )
        for item in worlds
    }
    return EpisodicSuiteReport(
        development=development,
        final_seeds=final_seed_tuple,
        worlds=worlds,
        final_world_count=len(worlds),
        family_counts=family_counts,
        unique_world_count=len(world_signatures),
        local_total_reward=local_total,
        global_total_reward=global_total,
        candidate_total_reward=candidate_total,
        oracle_total_reward=oracle_total,
        total_improvement_vs_local=candidate_total - local_total,
        world_win_rate_vs_local=(
            sum(
                item.candidate_total_reward > item.local_total_reward
                for item in worlds
            )
            / len(worlds)
        ),
        total_improvement_vs_global=candidate_total - global_total,
        recurrence_improvement_vs_local=(
            candidate_recurrence - local_recurrence
        ),
        exact_recurrence_improvement_vs_local=recurrence_improvement(
            exact_worlds
        ),
        cue_drift_improvement_vs_local=recurrence_improvement(
            cue_drift_worlds
        ),
        reward_drift_improvement_vs_local=recurrence_improvement(
            reward_drift_worlds
        ),
        novelty_degradation_vs_local=local_novelty - candidate_novelty,
        gap_to_oracle=oracle_total - candidate_total,
        correct_recurrence_retrieval_coverage=(
            sum(
                item.correctly_retrieved_recurrence_count
                for item in worlds
            )
            / recurrence_episode_count
        ),
        retrieval_precision=(
            sum(item.correct_retrieval_decision_count for item in worlds)
            / retrieval_count
            if retrieval_count
            else 0.0
        ),
        novelty_abstention_coverage=(
            sum(item.novelty_abstention_count for item in worlds)
            / novelty_episode_count
        ),
        novelty_false_retrieval_rate=(
            sum(
                item.novelty_false_retrieval_count for item in worlds
            )
            / novelty_episode_count
        ),
        archive_retention_rate=fmean(
            float(item.archive_retained) for item in worlds
        ),
        snapshot_round_trip_rate=fmean(
            float(item.snapshot_round_trip_exact) for item in worlds
        ),
        mean_prototype_count=fmean(
            item.prototype_count for item in worlds
        ),
        evidence_level="E1_LOCAL_AUTOMATED_EVALUATOR",
        held_out_definition=(
            "Minimum cues and tolerance are selected only on seeds "
            f"{development_seed_tuple[0]}-{development_seed_tuple[-1]}. "
            "Final metrics use the disjoint supplied final seeds "
            f"{final_seed_tuple[0]}-{final_seed_tuple[-1]}, paired "
            "potential outcomes, seed-defined families, and bandit "
            "feedback limited to the chosen action."
        ),
        limitations=(
            "The environment is synthetic, small, and tabular.",
            "Context codes, schedules, forced exploration, and reward levels are human-defined.",
            "The candidate clusters cue means with a fixed L1 threshold.",
            "The evaluator sees counterfactual outcomes only to pair policies and score the oracle.",
            "The agent receives only the reward of its chosen action.",
            "The task has immediate rewards and is a contextual bandit, not long-horizon planning.",
            "Snapshots are structurally validated but not cryptographically authenticated.",
            "The local evaluator does not provide independent E3 evidence.",
            "Success does not imply consciousness, language, personhood, emotion, or general intelligence.",
        ),
    )


def record_episodic_result(
    kernel: DarwinKernelV50,
    report: EpisodicSuiteReport,
) -> ObservationResult:
    all_criteria_satisfied = report.passes_regression_criteria()
    goal = kernel.create_goal(
        session_id=(
            f"episodic-context-lab:{report.final_seeds[0]}:"
            f"{report.final_seeds[-1]}"
        ),
        description=(
            "Episodic contextual action memory improves paired bandit reward"
        ),
        evidence_source=LOCAL_EPISODIC_EVALUATOR,
        condition=ComparisonCondition(
            "all_regression_criteria_satisfied",
            ComparisonOperator.EQUAL,
            True,
        ),
    )
    goal = kernel.start_goal(goal.goal_id)
    goal = kernel.dispatch_action(
        goal.goal_id,
        action_name="evaluate-held-out-episodic-context-action-memory",
        parameters={
            "development_seeds": list(report.development.seeds),
            "final_seeds": list(report.final_seeds),
            "selected_minimum_cues": (
                report.development.selected_minimum_cues
            ),
            "selected_match_tolerance": (
                report.development.selected_match_tolerance
            ),
            "evidence_level": report.evidence_level,
            "held_out_definition": report.held_out_definition,
        },
    )
    return kernel.record_observation(
        goal.goal_id,
        action_id=goal.expected_action_id or "",
        source=LOCAL_EPISODIC_EVALUATOR,
        metrics={
            "all_regression_criteria_satisfied": all_criteria_satisfied,
            "total_improvement_vs_local": (
                report.total_improvement_vs_local
            ),
            "world_win_rate_vs_local": report.world_win_rate_vs_local,
            "total_improvement_vs_global": (
                report.total_improvement_vs_global
            ),
            "recurrence_improvement_vs_local": (
                report.recurrence_improvement_vs_local
            ),
            "exact_recurrence_improvement_vs_local": (
                report.exact_recurrence_improvement_vs_local
            ),
            "cue_drift_improvement_vs_local": (
                report.cue_drift_improvement_vs_local
            ),
            "reward_drift_improvement_vs_local": (
                report.reward_drift_improvement_vs_local
            ),
            "novelty_degradation_vs_local": (
                report.novelty_degradation_vs_local
            ),
            "gap_to_oracle": report.gap_to_oracle,
            "correct_recurrence_retrieval_coverage": (
                report.correct_recurrence_retrieval_coverage
            ),
            "retrieval_precision": report.retrieval_precision,
            "novelty_abstention_coverage": (
                report.novelty_abstention_coverage
            ),
            "novelty_false_retrieval_rate": (
                report.novelty_false_retrieval_rate
            ),
            "archive_retention_rate": report.archive_retention_rate,
            "snapshot_round_trip_rate": report.snapshot_round_trip_rate,
        },
    )


def report_with_episodic_metrics(
    report: EpisodicSuiteReport,
    **changes: Any,
) -> EpisodicSuiteReport:
    return replace(report, **changes)


def _parse_seeds(raw: str) -> tuple[int, ...]:
    values = tuple(
        int(part.strip()) for part in raw.split(",") if part.strip()
    )
    if not values:
        raise argparse.ArgumentTypeError("provide at least one integer seed")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Darwin H50-L9 episodic contextual action benchmark."
    )
    parser.add_argument(
        "--development-seeds",
        type=_parse_seeds,
        default=EPISODIC_DEVELOPMENT_SEEDS,
    )
    parser.add_argument(
        "--final-seeds",
        type=_parse_seeds,
        default=EPISODIC_FINAL_SEEDS,
    )
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--development-scores", action="store_true")
    args = parser.parse_args(argv)
    report = run_episodic_suite(
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
