from __future__ import annotations

import json
import math
import unittest

import darwin_v50.online_posterior_evaluation as evaluation
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.learned_context_lab import (
    CONTEXT_ACTIONS,
    MAX_CONTEXT_ORDER,
    LearnedContextWorld,
    all_contexts,
)
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.online_posterior_lab import (
    FiniteHorizonContextPlanner,
    OnlineBayesianModel,
    OnlineCausalArchive,
    OnlineExperience,
    OnlinePosteriorAgent,
    ProbabilityTableModel,
)
from darwin_v50.store import SQLiteEventStore


DEBUG_DEVELOPMENT_SEEDS = (23020,)
DEBUG_FINAL_SEEDS = (23120, 23121, 23122, 23123)


def _experience(
    *,
    sequence: int = 1,
    episode_index: int = 1,
    step_index: int = 0,
    history: tuple[bool, bool, bool, bool, bool] = (
        False,
        True,
        False,
        True,
        False,
    ),
    action: str = "amber",
    next_observation: bool = True,
    reward: bool = False,
) -> OnlineExperience:
    return OnlineExperience(
        world_id="learned-context-23000",
        sequence=sequence,
        episode_index=episode_index,
        step_index=step_index,
        history=history,
        action=action,
        next_observation=next_observation,
        reward=reward,
    )


class OnlinePosteriorModelTests(unittest.TestCase):
    def test_prequential_posterior_is_normalized_and_updates_every_order(
        self,
    ) -> None:
        model = OnlineBayesianModel(world_id="learned-context-23000")
        self.assertEqual(model.order_posterior(), {order: 0.2 for order in range(1, 6)})
        information_gain = model.update(_experience())
        self.assertAlmostEqual(information_gain, 0.0)
        self.assertTrue(
            math.isclose(
                sum(model.order_posterior().values()),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )
        self.assertTrue(
            all(
                model.counts_for(
                    order,
                    _experience().history[-order:],
                    "amber",
                ).transition.successes
                == 1
                for order in range(1, 6)
            )
        )
        self.assertTrue(
            all(
                math.isclose(value, -math.log(4.0))
                for value in model.log_evidence.values()
            )
        )

    def test_archive_rejects_skips_discontinuities_and_unknown_actions(
        self,
    ) -> None:
        archive = OnlineCausalArchive()
        first = _experience()
        archive.observe(first)
        with self.assertRaises(ValidationError):
            archive.observe(first)
        with self.assertRaises(ValidationError):
            archive.observe(
                _experience(
                    sequence=2,
                    step_index=1,
                    history=(False,) * MAX_CONTEXT_ORDER,
                )
            )
        with self.assertRaises(ValidationError):
            _experience(action="counterfactual")

    def test_finite_horizon_planner_uses_reward_and_is_deterministic(
        self,
    ) -> None:
        probabilities = {
            (context, action): (
                0.5,
                0.9 if action == "violet" else 0.1,
            )
            for context in all_contexts(1)
            for action in CONTEXT_ACTIONS
        }
        model = ProbabilityTableModel(order=1, probabilities=probabilities)
        planner = FiniteHorizonContextPlanner(model, horizon=4)
        history = (False, True, False, True, False)
        self.assertEqual(planner.action(history, remaining=4), "violet")
        self.assertGreater(
            planner.q_value((False,), "violet", remaining=4),
            planner.q_value((False,), "amber", remaining=4),
        )

    def test_agent_snapshot_crosses_environment_boundary_exactly(self) -> None:
        seed = 23001
        schedule = evaluation.make_online_schedule(seed)
        world = LearnedContextWorld(seed)
        agent = OnlinePosteriorAgent(
            world_id=world.world_id,
            policy_seed=83001,
            resampling_length=64,
        )
        first = schedule[0]
        world.reset(
            initial_history=first.initial_history,
            max_steps=32,
            episode_seed=first.episode_seed,
        )
        agent.begin_episode(episode_index=1, initial_history=first.initial_history)
        for _ in range(32):
            step = world.step(agent.action())
            agent.observe(
                next_observation=step.observation.observation,
                reward=step.reward,
            )
        self.assertEqual(agent.block_remaining, 32)
        second = schedule[1]
        world.reset(
            initial_history=second.initial_history,
            max_steps=32,
            episode_seed=second.episode_seed,
        )
        agent.begin_episode(episode_index=2, initial_history=second.initial_history)
        snapshot = agent.to_snapshot()
        restored = OnlinePosteriorAgent.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.block_remaining, 32)
        self.assertEqual(restored.sampled_order, agent.sampled_order)
        self.assertEqual(restored.action(), agent.action())

    def test_snapshot_replay_rejects_derived_and_causal_tampering(self) -> None:
        seed = 23002
        episode = evaluation.make_online_schedule(seed)[0]
        world = LearnedContextWorld(seed)
        world.reset(
            initial_history=episode.initial_history,
            max_steps=32,
            episode_seed=episode.episode_seed,
        )
        agent = OnlinePosteriorAgent(
            world_id=world.world_id,
            policy_seed=83002,
            resampling_length=8,
        )
        agent.begin_episode(episode_index=1, initial_history=episode.initial_history)
        step = world.step(agent.action())
        agent.observe(
            next_observation=step.observation.observation,
            reward=step.reward,
        )
        snapshot = agent.to_snapshot()

        bad_counts = json.loads(snapshot)
        bad_counts["model"]["order_models"][0]["reward_successes"] += 1
        with self.assertRaises(ValidationError):
            OnlinePosteriorAgent.from_snapshot(json.dumps(bad_counts))

        bad_evidence = json.loads(snapshot)
        bad_evidence["model"]["log_evidence"][0]["value"] += 0.1
        with self.assertRaises(ValidationError):
            OnlinePosteriorAgent.from_snapshot(json.dumps(bad_evidence))

        bad_posterior = json.loads(snapshot)
        bad_posterior["model"]["order_posterior"][0]["value"] = 0.9
        with self.assertRaises(ValidationError):
            OnlinePosteriorAgent.from_snapshot(json.dumps(bad_posterior))

        counterfactual = json.loads(snapshot)
        counterfactual["model"]["archive"][0]["unchosen_reward"] = True
        with self.assertRaises(ValidationError):
            OnlinePosteriorAgent.from_snapshot(json.dumps(counterfactual))

    def test_boolean_numeric_configuration_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            OnlinePosteriorAgent(
                world_id="world",
                policy_seed=True,  # type: ignore[arg-type]
                resampling_length=8,
            )
        with self.assertRaises(ValidationError):
            ProbabilityTableModel(order=True, probabilities={})  # type: ignore[arg-type]


class OnlinePosteriorEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = evaluation.run_online_suite(
            development_seeds=DEBUG_DEVELOPMENT_SEEDS,
            final_seeds=DEBUG_FINAL_SEEDS,
            candidates=(16,),
        )

    def test_schedule_is_deterministic_and_uses_separate_episode_streams(
        self,
    ) -> None:
        schedule = evaluation.make_online_schedule(23010)
        self.assertEqual(schedule, evaluation.make_online_schedule(23010))
        self.assertEqual(len(schedule), 40)
        self.assertEqual(len({item.episode_seed for item in schedule}), 40)

    def test_small_suite_is_disjoint_paired_causal_and_persistent(self) -> None:
        self.assertEqual(self.report.final_world_count, 4)
        self.assertEqual(self.report.unique_world_count, 4)
        self.assertFalse(
            set(self.report.development.seeds) & set(self.report.final_seeds)
        )
        self.assertEqual(self.report.true_order_counts, {2: 1, 3: 1, 4: 1, 5: 1})
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)
        self.assertEqual(self.report.causal_field_rate, 1.0)
        self.assertIn("23020-23020", self.report.held_out_definition)
        self.assertIn("23120-23123", self.report.held_out_definition)

    def test_development_selection_is_deterministic(self) -> None:
        first = evaluation.select_online_resampling_length(
            seeds=(23030, 23031), candidates=(8, 16)
        )
        second = evaluation.select_online_resampling_length(
            seeds=(23030, 23031), candidates=(8, 16)
        )
        self.assertEqual(first, second)
        self.assertIn(first.selected_resampling_length, (8, 16))

    def test_seed_overlap_and_invalid_candidate_grid_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation.run_online_suite(
                development_seeds=(23040,),
                final_seeds=(23040,),
                candidates=(8,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_online_resampling_length(
                seeds=(23041,), candidates=(8, 8)
            )

    def test_regression_criteria_are_strictly_conjunctive(self) -> None:
        passing = evaluation.report_with_online_metrics(
            self.report,
            candidate_oracle_total_reward_ratio=0.75,
            candidate_oracle_final_quarter_reward_ratio=0.85,
            improvement_vs_certainty_equivalent=0.010,
            improvement_vs_epsilon_greedy=0.005,
            improvement_vs_explore_then_commit=0.015,
            improvement_vs_fixed_order_five=0.010,
            improvement_vs_random=0.050,
            simultaneous_baseline_world_win_rate=0.60,
            exact_order_recovery_rate=0.70,
            mean_true_order_posterior_mass=0.65,
            transition_probability_error=0.08,
            reward_probability_error=0.08,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
            causal_field_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            evaluation.report_with_online_metrics(
                passing,
                improvement_vs_epsilon_greedy=0.005 - 1e-12,
            ).passes_regression_criteria()
        )

    def test_kernel_does_not_promote_a_failed_conjunction(self) -> None:
        failing = evaluation.report_with_online_metrics(
            self.report,
            improvement_vs_random=-1.0,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = evaluation.record_online_result(kernel, failing)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
