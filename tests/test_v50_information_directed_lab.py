from __future__ import annotations

import json
import math
import random
import unittest

import darwin_v50.information_directed_evaluation as evaluation
from darwin_v50.information_directed_lab import (
    IDS_OUTCOMES,
    InformationDirectedAgent,
    _action_information_gain,
    _candidate_mixture_probabilities,
    _outcome_probability,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.learned_context_lab import (
    CONTEXT_ACTIONS,
    LearnedContextWorld,
    all_contexts,
)
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.online_posterior_lab import ProbabilityTableModel
from darwin_v50.store import SQLiteEventStore


IDS_TEST_DEVELOPMENT_SEEDS = (25020,)
IDS_TEST_FINAL_SEEDS = (25120, 25121, 25122, 25123)


def _model(
    *,
    amber_reward: float,
    violet_reward: float,
    amber_transition: float = 0.5,
    violet_transition: float = 0.5,
) -> ProbabilityTableModel:
    return ProbabilityTableModel(
        order=1,
        probabilities={
            (context, action): (
                amber_transition if action == "amber" else violet_transition,
                amber_reward if action == "amber" else violet_reward,
            )
            for context in all_contexts(1)
            for action in CONTEXT_ACTIONS
        },
    )


class InformationDirectedMathTests(unittest.TestCase):
    def test_sampled_outcome_distribution_is_complete(self) -> None:
        model = _model(
            amber_reward=0.8,
            violet_reward=0.2,
            amber_transition=0.7,
        )
        history = (False, True, False, True, False)
        probabilities = tuple(
            _outcome_probability(model, history, "amber", outcome)
            for outcome in IDS_OUTCOMES
        )
        self.assertTrue(all(0.0 <= value <= 1.0 for value in probabilities))
        self.assertAlmostEqual(sum(probabilities), 1.0)

    def test_mutual_information_is_zero_for_a_certain_optimal_action(self) -> None:
        models = (
            _model(amber_reward=0.8, violet_reward=0.2),
            _model(amber_reward=0.7, violet_reward=0.3),
        )
        history = (False, True, False, True, False)
        gain = _action_information_gain(
            models, ("amber", "amber"), history, "amber"
        )
        self.assertAlmostEqual(gain, 0.0)

    def test_mutual_information_detects_action_target_evidence(self) -> None:
        models = (
            _model(
                amber_reward=0.9,
                violet_reward=0.1,
                amber_transition=0.9,
            ),
            _model(
                amber_reward=0.1,
                violet_reward=0.9,
                amber_transition=0.1,
            ),
        )
        history = (False, True, False, True, False)
        gain = _action_information_gain(
            models, ("amber", "violet"), history, "amber"
        )
        self.assertGreater(gain, 0.0)
        self.assertLessEqual(gain, math.log(2.0))

    def test_two_action_stationary_mixture_is_considered(self) -> None:
        candidates = _candidate_mixture_probabilities(
            amber_regret=0.1,
            violet_regret=0.4,
            amber_gain=0.02,
            violet_gain=0.30,
        )
        self.assertEqual(candidates[0], 0.0)
        self.assertEqual(candidates[-1], 1.0)
        self.assertTrue(any(0.0 < value < 1.0 for value in candidates))

    def test_analytic_candidates_match_a_dense_mixture_grid(self) -> None:
        rng = random.Random(25003)
        for _ in range(250):
            amber_regret = rng.random()
            violet_regret = rng.random()
            amber_gain = rng.random()
            violet_gain = rng.random()
            candidates = _candidate_mixture_probabilities(
                amber_regret,
                violet_regret,
                amber_gain,
                violet_gain,
            )

            def score(probability: float) -> float:
                regret = (
                    probability * amber_regret
                    + (1.0 - probability) * violet_regret
                )
                gain = (
                    probability * amber_gain
                    + (1.0 - probability) * violet_gain
                )
                return regret * regret / gain

            analytic = min(score(value) for value in candidates)
            dense = min(score(index / 10_000) for index in range(10_001))
            self.assertLessEqual(analytic, dense + 1e-12)


class InformationDirectedAgentTests(unittest.TestCase):
    def test_agent_updates_only_after_the_chosen_outcome(self) -> None:
        seed = 25000
        episode = evaluation.make_online_schedule(seed)[0]
        world = LearnedContextWorld(seed)
        world.reset(
            initial_history=episode.initial_history,
            max_steps=32,
            episode_seed=episode.episode_seed,
        )
        agent = InformationDirectedAgent(
            world_id=world.world_id,
            model_seed=75000,
            action_seed=85000,
            block_length=4,
        )
        agent.begin_episode(
            episode_index=1, initial_history=episode.initial_history
        )
        decision = agent.action()
        self.assertEqual(len(agent.model.archive.items), 0)
        self.assertEqual(agent.pending_decision, decision)
        step = world.step(decision.action)
        agent.observe(
            next_observation=step.observation.observation,
            reward=step.reward,
        )
        self.assertEqual(len(agent.model.archive.items), 1)
        self.assertIsNone(agent.pending_decision)
        self.assertEqual(
            set(agent.model.archive.items[0].to_dict()),
            agent.model.archive.items[0].FIELDS,
        )

    def test_snapshot_preserves_pending_and_future_decisions(self) -> None:
        seed = 25001
        episode = evaluation.make_online_schedule(seed)[0]
        world = LearnedContextWorld(seed)
        world.reset(
            initial_history=episode.initial_history,
            max_steps=32,
            episode_seed=episode.episode_seed,
        )
        agent = InformationDirectedAgent(
            world_id=world.world_id,
            model_seed=75001,
            action_seed=85001,
            block_length=8,
        )
        agent.begin_episode(
            episode_index=1, initial_history=episode.initial_history
        )
        pending = agent.action()
        snapshot = agent.to_snapshot()
        restored = InformationDirectedAgent.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.pending_decision, pending)
        step = world.step(pending.action)
        agent.observe(
            next_observation=step.observation.observation,
            reward=step.reward,
        )
        restored.observe(
            next_observation=step.observation.observation,
            reward=step.reward,
        )
        self.assertEqual(restored.to_snapshot(), agent.to_snapshot())
        self.assertEqual(restored.action(), agent.action())

    def test_snapshot_rejects_causal_and_diagnostic_tampering(self) -> None:
        seed = 25002
        episode = evaluation.make_online_schedule(seed)[0]
        world = LearnedContextWorld(seed)
        world.reset(
            initial_history=episode.initial_history,
            max_steps=32,
            episode_seed=episode.episode_seed,
        )
        agent = InformationDirectedAgent(
            world_id=world.world_id,
            model_seed=75002,
            action_seed=85002,
            block_length=4,
        )
        agent.begin_episode(
            episode_index=1, initial_history=episode.initial_history
        )
        agent.action()
        snapshot = agent.to_snapshot()
        bad_diagnostic = json.loads(snapshot)
        bad_diagnostic["pending_decision"]["information_gain"] += 0.1
        with self.assertRaises(ValidationError):
            InformationDirectedAgent.from_snapshot(json.dumps(bad_diagnostic))

        step = world.step(agent.pending_decision.action)  # type: ignore[union-attr]
        agent.observe(
            next_observation=step.observation.observation,
            reward=step.reward,
        )
        observed = json.loads(agent.to_snapshot())
        observed["model"]["archive"][0]["unchosen_reward"] = True
        with self.assertRaises(ValidationError):
            InformationDirectedAgent.from_snapshot(json.dumps(observed))

    def test_invalid_boolean_and_non_divisor_configuration_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            InformationDirectedAgent(
                world_id="world",
                model_seed=True,  # type: ignore[arg-type]
                action_seed=1,
                block_length=4,
            )
        with self.assertRaises(ValidationError):
            InformationDirectedAgent(
                world_id="world",
                model_seed=1,
                action_seed=2,
                block_length=3,
            )


class InformationDirectedEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = evaluation.run_ids_suite(
            development_seeds=IDS_TEST_DEVELOPMENT_SEEDS,
            final_seeds=IDS_TEST_FINAL_SEEDS,
            candidates=(4,),
        )

    def test_small_suite_is_disjoint_causal_and_persistent(self) -> None:
        self.assertEqual(self.report.final_world_count, 4)
        self.assertFalse(
            set(self.report.development.seeds) & set(self.report.final_seeds)
        )
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)
        self.assertEqual(self.report.causal_field_rate, 1.0)
        self.assertIn("25020-25020", self.report.held_out_definition)
        self.assertIn("25120-25123", self.report.held_out_definition)

    def test_development_selection_is_deterministic(self) -> None:
        first = evaluation.select_ids_block_length(
            seeds=(25030,), candidates=(4, 8)
        )
        second = evaluation.select_ids_block_length(
            seeds=(25030,), candidates=(4, 8)
        )
        self.assertEqual(first, second)
        self.assertIn(first.selected_block_length, (4, 8))

    def test_seed_overlap_and_invalid_grid_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation.run_ids_suite(
                development_seeds=(25040,),
                final_seeds=(25040,),
                candidates=(4,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_ids_block_length(
                seeds=(25041,), candidates=(4, 4)
            )
        with self.assertRaises(ValidationError):
            evaluation.select_ids_block_length(
                seeds=(25041,), candidates=(3,)
            )

    def test_registered_criteria_are_strictly_conjunctive(self) -> None:
        passing = evaluation.report_with_ids_metrics(
            self.report,
            candidate_oracle_total_reward_ratio=0.80,
            candidate_oracle_final_quarter_reward_ratio=0.90,
            improvement_vs_certainty_equivalent=0.005,
            improvement_vs_posterior_sampling=0.010,
            improvement_vs_epsilon_greedy=0.005,
            improvement_vs_random=0.050,
            simultaneous_baseline_world_win_rate=0.60,
            exact_order_recovery_rate=0.70,
            mean_true_order_posterior_mass=0.65,
            transition_probability_error=0.08,
            reward_probability_error=0.08,
            finite_diagnostic_rate=1.0,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
            causal_field_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            evaluation.report_with_ids_metrics(
                passing,
                improvement_vs_posterior_sampling=0.010 - 1e-12,
            ).passes_regression_criteria()
        )

    def test_kernel_cannot_promote_a_failed_conjunction(self) -> None:
        failing = evaluation.report_with_ids_metrics(
            self.report, improvement_vs_random=-1.0
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = evaluation.record_ids_result(kernel, failing)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
