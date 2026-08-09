from __future__ import annotations

import json
import math
import unittest

import darwin_v50.learned_context_evaluation as evaluation
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.learned_context_lab import (
    CONTEXT_ACTIONS,
    MAX_CONTEXT_ORDER,
    CausalContextArchive,
    ContextOrderScore,
    ContextValuePlanner,
    LearnedContextExperience,
    LearnedContextModel,
    LearnedContextObservation,
    LearnedContextStep,
    LearnedContextWorld,
    LearnedContextWorldSpecification,
    append_observation,
)
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.store import SQLiteEventStore


EXTERNAL_DEVELOPMENT_SEEDS = (20020, 20021)
EXTERNAL_FINAL_SEEDS = (20120, 20121, 20122, 20123)


class LearnedContextWorldTests(unittest.TestCase):
    def test_specification_is_deterministic_complete_and_hidden(self) -> None:
        specification = LearnedContextWorldSpecification.from_seed(20000)
        self.assertEqual(
            specification,
            LearnedContextWorldSpecification.from_seed(20000),
        )
        self.assertEqual(specification.true_order, 2)
        self.assertEqual(
            len(specification.dynamics),
            2**specification.true_order,
        )
        self.assertEqual(len(specification.reward_contexts), 2)
        self.assertTrue(
            all(
                set(rule.preferred_next_bits) == {False, True}
                for rule in specification.dynamics
            )
        )
        world = LearnedContextWorld(20000)
        observation = world.reset(
            initial_history=(False, True, False, True, False),
            max_steps=1,
            episode_seed=80000,
        )
        self.assertEqual(
            set(LearnedContextObservation.__dataclass_fields__),
            {
                "world_id",
                "episode_id",
                "observation",
                "step_index",
                "truncated",
                "priming_history",
            },
        )
        self.assertFalse(
            {
                "true_order",
                "dynamics",
                "reward_contexts",
                "transition_probability",
                "reward_probability",
            }
            & set(LearnedContextObservation.__dataclass_fields__)
        )
        self.assertIsNotNone(observation.priming_history)

    def test_potential_outcomes_are_paired_and_only_choice_is_returned(
        self,
    ) -> None:
        initial = (False, False, True, True, False)
        first = LearnedContextWorld(20001)
        second = LearnedContextWorld(20001)
        first.reset(
            initial_history=initial,
            max_steps=3,
            episode_seed=80001,
        )
        second.reset(
            initial_history=initial,
            max_steps=3,
            episode_seed=80001,
        )
        first_step = first.step("amber")
        second_step = second.step("amber")
        self.assertEqual(first_step, second_step)
        self.assertEqual(
            set(LearnedContextStep.__dataclass_fields__),
            {"observation", "action", "reward"},
        )
        self.assertEqual(first_step.action, "amber")
        self.assertIsNone(first_step.observation.priming_history)

    def test_invalid_boolean_numeric_fields_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation.LearnedContextEpisode(
                initial_history=(False,) * MAX_CONTEXT_ORDER,
                episode_seed=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValidationError):
            ContextOrderScore(
                order=2,
                validation_log_loss=True,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValidationError):
            LearnedContextWorld(True)  # type: ignore[arg-type]


class LearnedContextModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive, cls.world = evaluation.collect_learned_context_trace(
            20010,
            budget=768,
        )
        cls.model = LearnedContextModel.fit(cls.archive.items)

    def test_archive_is_contiguous_chosen_feedback_only(self) -> None:
        self.assertEqual(len(self.archive.items), 768)
        self.assertEqual(
            set(LearnedContextExperience.__dataclass_fields__),
            {
                "world_id",
                "trace_id",
                "sequence",
                "history",
                "action",
                "next_observation",
                "reward",
            },
        )
        first = self.archive.items[0]
        self.assertIn(first.action, CONTEXT_ACTIONS)
        self.assertEqual(
            self.archive.items[1].history,
            first.next_history,
        )

        invalid = CausalContextArchive()
        invalid.observe(first)
        with self.assertRaises(ValidationError):
            invalid.observe(first)
        with self.assertRaises(ValidationError):
            invalid.observe(
                LearnedContextExperience(
                    world_id=first.world_id,
                    trace_id=first.trace_id,
                    sequence=2,
                    history=(False,) * MAX_CONTEXT_ORDER,
                    action="amber",
                    next_observation=False,
                    reward=False,
                )
            )

    def test_selection_uses_lowest_validation_loss(self) -> None:
        expected = min(
            self.model.order_scores,
            key=lambda item: (item.validation_log_loss, item.order),
        )
        self.assertEqual(self.model.selected_order, expected.order)
        self.assertEqual(
            tuple(item.order for item in self.model.order_scores),
            (1, 2, 3, 4, 5),
        )
        self.assertTrue(
            all(
                math.isfinite(item.validation_log_loss)
                for item in self.model.order_scores
            )
        )

    def test_snapshot_replays_archive_and_rejects_tampering(self) -> None:
        snapshot = self.model.to_snapshot()
        restored = LearnedContextModel.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.archive, self.model.archive)

        tampered = json.loads(snapshot)
        tampered["counts"][0]["reward_successes"] += 1
        with self.assertRaises(ValidationError):
            LearnedContextModel.from_snapshot(json.dumps(tampered))

        invalid_order = json.loads(snapshot)
        invalid_order["fixed_order"] = True
        with self.assertRaises(ValidationError):
            LearnedContextModel.from_snapshot(json.dumps(invalid_order))

    def test_planner_is_deterministic_and_model_remains_frozen(self) -> None:
        snapshot = self.model.to_snapshot()
        first = ContextValuePlanner(self.model)
        second = ContextValuePlanner(self.model)
        histories = (
            self.archive.items[0].history,
            self.archive.items[-1].next_history,
        )
        self.assertEqual(
            tuple(first.action(history) for history in histories),
            tuple(second.action(history) for history in histories),
        )
        self.assertLessEqual(first.iterations, 1000)
        self.assertEqual(self.model.to_snapshot(), snapshot)

    def test_probability_errors_use_unseen_evaluator_truth_only(self) -> None:
        transition_error, reward_error = evaluation.model_probability_errors(
            self.model,
            self.world.specification,
        )
        self.assertGreaterEqual(transition_error, 0.0)
        self.assertLessEqual(transition_error, 1.0)
        self.assertGreaterEqual(reward_error, 0.0)
        self.assertLessEqual(reward_error, 1.0)
        self.assertNotIn(
            "specification",
            json.loads(self.model.to_snapshot()),
        )


class LearnedContextEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = evaluation.run_learned_context_suite(
            development_seeds=EXTERNAL_DEVELOPMENT_SEEDS,
            final_seeds=EXTERNAL_FINAL_SEEDS,
            budget_candidates=(384,),
        )

    def test_small_suite_is_disjoint_paired_causal_and_persistent(
        self,
    ) -> None:
        self.assertEqual(self.report.final_world_count, 4)
        self.assertEqual(self.report.unique_world_count, 4)
        self.assertFalse(
            set(self.report.development.seeds)
            & set(self.report.final_seeds)
        )
        self.assertEqual(
            set(self.report.true_order_counts),
            {2, 3, 4, 5},
        )
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)
        self.assertEqual(self.report.frozen_model_rate, 1.0)
        self.assertIn("20020-20021", self.report.held_out_definition)
        self.assertIn("20120-20123", self.report.held_out_definition)

    def test_exact_order_five_equivalence_is_not_counted_as_a_loss(
        self,
    ) -> None:
        world = evaluation.run_learned_context_world(
            20703,
            selected_budget=384,
        )
        self.assertEqual((world.true_order, world.selected_order), (5, 5))
        self.assertEqual(
            world.candidate_return,
            world.maximum_depth_return,
        )
        self.assertGreater(
            world.candidate_return,
            world.reactive_return,
        )
        self.assertGreater(world.candidate_return, world.myopic_return)
        self.assertGreater(
            world.candidate_return,
            world.rotated_reward_return,
        )
        self.assertTrue(world.simultaneous_ablation_win)

    def test_seed_overlap_and_invalid_budget_grid_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation.run_learned_context_suite(
                development_seeds=(20200,),
                final_seeds=(20200,),
                budget_candidates=(384,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_learned_context_budget(
                seeds=(20201,),
                budget_candidates=(384, 384),
            )

    def test_regression_criteria_are_strictly_conjunctive(self) -> None:
        passing = evaluation.report_with_learned_context_metrics(
            self.report,
            exact_order_recovery_rate=0.70,
            transition_probability_error=0.08,
            reward_probability_error=0.08,
            candidate_oracle_return_ratio=0.80,
            improvement_vs_reactive=0.25,
            improvement_vs_maximum_depth=0.10,
            improvement_vs_myopic=0.20,
            improvement_vs_rotated_reward=0.25,
            improvement_vs_random=0.40,
            simultaneous_ablation_world_win_rate=0.70,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
            frozen_model_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            evaluation.report_with_learned_context_metrics(
                passing,
                improvement_vs_maximum_depth=0.10 - 1e-12,
            ).passes_regression_criteria()
        )

    def test_kernel_does_not_promote_a_failed_conjunction(self) -> None:
        failing = evaluation.report_with_learned_context_metrics(
            self.report,
            improvement_vs_reactive=-1.0,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = evaluation.record_learned_context_result(kernel, failing)
        self.assertEqual(
            result.goal.status,
            GoalStatus.WAITING_OBSERVATION,
        )
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
