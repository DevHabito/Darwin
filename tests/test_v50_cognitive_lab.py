from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from darwin_v50.cognitive_evaluation import (
    record_active_exploration_result,
    record_suite_result,
    report_with_delta,
    run_active_exploration_suite,
    run_active_exploration_world_benchmark,
    run_cognitive_suite,
    run_world_benchmark,
)
from darwin_v50.cognitive_lab import (
    ActiveTransitionExplorer,
    ModelBasedPlanner,
    OpaqueGraphWorld,
    TabularTransitionModel,
    collect_controlled_transition_census,
    make_benchmark_world,
    snapshot_digest,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError


class OpaqueGraphWorldTests(unittest.TestCase):
    def test_transition_has_local_causal_lineage_and_real_state_change(self) -> None:
        world = OpaqueGraphWorld(
            world_id="world:test",
            transitions={
                "a": {"amber": "b", "cyan": "a", "violet": "b"},
                "b": {"amber": "a", "cyan": "b", "violet": "a"},
            },
        )
        initial = world.reset(start="a", goal="b", max_steps=3)
        first = world.step("cyan")
        result = world.step("amber")

        self.assertEqual(initial.state, "a")
        self.assertEqual(first.observation.state, "a")
        self.assertFalse(first.observation.terminated)
        self.assertEqual(result.observation.state, "b")
        self.assertTrue(result.observation.terminated)
        self.assertEqual(result.experience.state, "a")
        self.assertEqual(result.experience.next_state, "b")
        self.assertIsNone(first.experience.parent_transition_id)
        self.assertEqual(
            result.experience.parent_transition_id,
            first.experience.transition_id,
        )
        self.assertEqual(
            result.experience.transition_id,
            f"{initial.episode_id}:transition:0002",
        )
        with self.assertRaises(RuntimeError):
            world.step("amber")

    def test_invalid_world_and_invalid_actions_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            OpaqueGraphWorld(
                world_id="broken",
                transitions={
                    "a": {"amber": "outside", "cyan": "a", "violet": "a"},
                    "b": {"amber": "a", "cyan": "b", "violet": "a"},
                },
            )
        world = make_benchmark_world(5001)
        world.reset(start=world.states[0], goal=world.states[1], max_steps=1)
        with self.assertRaises(ValidationError):
            world.step("shell")


class TransitionModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = make_benchmark_world(5002)
        self.model = TabularTransitionModel()
        self.experiences = collect_controlled_transition_census(
            self.world, self.model
        )

    def test_census_learns_only_observed_transitions_and_rejects_replay(self) -> None:
        expected = len(self.world.states) * len(self.world.action_space)
        self.assertEqual(len(self.experiences), expected)
        self.assertEqual(self.model.experience_count, expected)
        first = self.experiences[0]
        prediction = self.model.predict(first.state, first.action)
        self.assertIsNotNone(prediction)
        assert prediction is not None
        self.assertEqual(prediction.next_state, first.next_state)
        self.assertEqual(prediction.probability, 1.0)
        self.assertFalse(self.model.observe(first))
        self.assertEqual(self.model.experience_count, expected)
        with self.assertRaises(ValidationError):
            self.model.observe(replace(first, next_state="conflicting-state"))

    def test_model_refuses_to_mix_world_identities(self) -> None:
        other_world = make_benchmark_world(9002)
        other_model = TabularTransitionModel()
        other_experience = collect_controlled_transition_census(
            other_world, other_model
        )[0]
        with self.assertRaises(ValidationError):
            self.model.observe(other_experience)

    def test_snapshot_round_trip_preserves_learned_model(self) -> None:
        snapshot = self.model.to_snapshot()
        restored = TabularTransitionModel.from_snapshot(snapshot)

        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(snapshot_digest(restored), snapshot_digest(self.model))
        for experience in self.experiences:
            self.assertEqual(
                restored.predict(experience.state, experience.action),
                self.model.predict(experience.state, experience.action),
            )

    def test_malformed_snapshot_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            TabularTransitionModel.from_snapshot('{"schema": 999}')
        with self.assertRaises(ValidationError):
            TabularTransitionModel.from_snapshot(
                '{"schema":1,"experiences":[{"transition_id":"x"}]}'
            )

    def test_planner_abstains_without_a_model_and_composes_with_one(self) -> None:
        empty_plan = ModelBasedPlanner(TabularTransitionModel()).plan(
            self.world.states[0],
            self.world.states[4],
        )
        learned_plan = ModelBasedPlanner(self.model).plan(
            self.world.states[0],
            self.world.states[4],
        )

        self.assertFalse(empty_plan.found)
        self.assertEqual(empty_plan.reason, "model_empty")
        self.assertTrue(learned_plan.found)
        self.assertGreater(len(learned_plan.actions), 0)
        self.assertEqual(learned_plan.predicted_states[0], self.world.states[0])
        self.assertEqual(learned_plan.predicted_states[-1], self.world.states[4])

    def test_active_explorer_builds_a_monotonic_learning_curve(self) -> None:
        world = make_benchmark_world(5003)
        model = TabularTransitionModel()
        trace = ActiveTransitionExplorer(
            model,
            world.action_space,
        ).explore(
            world,
            start=world.states[0],
            budget=30,
        )

        self.assertEqual(trace.steps, 30)
        self.assertEqual(len(trace.pair_count_curve), 30)
        self.assertEqual(trace.pair_count_curve[-1], trace.unique_transition_pairs)
        self.assertTrue(
            all(
                before <= after
                for before, after in zip(
                    trace.pair_count_curve[:-1],
                    trace.pair_count_curve[1:],
                    strict=True,
                )
            )
        )
        self.assertGreaterEqual(trace.unique_transition_pairs, 26)
        self.assertEqual(trace.discovered_states, len(world.states))


class CognitiveBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_cognitive_suite(range(5010, 5015), task_limit=24)

    def test_reserved_task_benchmark_beats_baselines(self) -> None:
        report = self.report
        self.assertEqual(report.world_count, 5)
        self.assertEqual(report.evaluation_episode_count, 120)
        self.assertEqual(report.model_based_success_rate, 1.0)
        self.assertEqual(report.untrained_success_rate, 0.0)
        self.assertLess(report.random_success_rate, 0.50)
        self.assertGreater(report.success_rate_delta, 0.50)
        self.assertEqual(report.known_transition_accuracy, 1.0)
        self.assertTrue(report.passes_regression_criteria())
        self.assertIn("state-action transition pairs were not held out", report.held_out_definition)
        self.assertEqual(report.evidence_level, "E1_LOCAL_AUTOMATED_EVALUATOR")

    def test_benchmark_is_deterministic(self) -> None:
        first = run_world_benchmark(5021, task_limit=18)
        second = run_world_benchmark(5021, task_limit=18)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_causal_kernel_records_true_result_without_upgrading_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "cognitive-lab.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_suite_result(kernel, self.report)
                events = kernel.goal_events(result.goal.goal_id)

        self.assertTrue(result.accepted)
        self.assertTrue(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertEqual(
            [event.kind for event in events],
            [
                "goal.created",
                "goal.started",
                "action.dispatched",
                "observation.recorded",
                "goal.succeeded",
            ],
        )
        observation = next(
            event for event in events if event.kind == "observation.recorded"
        )
        self.assertFalse(observation.payload["authenticated"])

    def test_causal_kernel_does_not_turn_failed_delta_into_success(self) -> None:
        failed_report = report_with_delta(
            self.report,
            model_success_rate=0.40,
            random_success_rate=0.35,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "failed-cognitive-lab.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_suite_result(kernel, failed_report)
                success_events = kernel.store.count_events(
                    goal_id=result.goal.goal_id,
                    kind="goal.succeeded",
                )

        self.assertTrue(result.accepted)
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(success_events, 0)

    def test_report_criteria_fail_if_result_is_not_better_than_baseline(self) -> None:
        non_improving = replace(
            self.report,
            model_based_success_rate=0.50,
            random_success_rate=0.50,
            success_rate_delta=0.0,
        )
        self.assertFalse(non_improving.passes_regression_criteria())


class ActiveExplorationBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_active_exploration_suite(
            range(5010, 5015),
            budget=30,
            task_limit=24,
        )

    def test_active_exploration_beats_equal_budget_random_exploration(self) -> None:
        report = self.report
        self.assertEqual(report.world_count, 5)
        self.assertEqual(report.budget_per_world, 30)
        self.assertGreaterEqual(report.active_coverage, 0.95)
        self.assertGreater(report.coverage_delta, 0.20)
        self.assertGreaterEqual(report.active_task_success_rate, 0.95)
        self.assertGreater(report.task_success_delta, 0.20)
        self.assertTrue(report.passes_regression_criteria())
        self.assertEqual(report.evidence_level, "E1_LOCAL_AUTOMATED_EVALUATOR")

    def test_active_exploration_benchmark_is_deterministic(self) -> None:
        first = run_active_exploration_world_benchmark(
            5040,
            budget=30,
            task_limit=18,
        )
        second = run_active_exploration_world_benchmark(
            5040,
            budget=30,
            task_limit=18,
        )
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_active_exploration_result_uses_causal_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "active-exploration.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_active_exploration_result(kernel, self.report)
                observation = next(
                    event
                    for event in kernel.goal_events(result.goal.goal_id)
                    if event.kind == "observation.recorded"
                )

        self.assertTrue(result.accepted)
        self.assertTrue(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertFalse(observation.payload["authenticated"])

    def test_active_exploration_failed_delta_cannot_succeed(self) -> None:
        failed = replace(
            self.report,
            active_task_success_rate=0.50,
            random_exploration_task_success_rate=0.45,
            task_success_delta=0.05,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "failed-active.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_active_exploration_result(kernel, failed)
                success_events = kernel.store.count_events(
                    goal_id=result.goal.goal_id,
                    kind="goal.succeeded",
                )

        self.assertTrue(result.accepted)
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(success_events, 0)


if __name__ == "__main__":
    unittest.main()
