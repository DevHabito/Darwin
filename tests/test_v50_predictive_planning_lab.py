from __future__ import annotations

import json
import unittest

import darwin_v50.predictive_planning_evaluation as evaluation
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.predictive_planning_lab import (
    ALL_HISTORY_STATES,
    CUE_VALUES,
    PLANNING_ACTIONS,
    PREDICTIVE_PAIR_COUNT,
    PREDICTIVE_STATE_COUNT,
    HistoryFrontierExplorer,
    PredictiveHistoryModel,
    PredictiveHistoryPlanner,
    PredictivePlanningStep,
    PredictivePlanningWorld,
    PredictiveTransitionExperience,
    PredictiveWorldSpecification,
    next_history,
)
from darwin_v50.store import SQLiteEventStore


class PredictiveWorldTests(unittest.TestCase):
    def test_world_is_deterministic_complete_and_action_controllable(
        self,
    ) -> None:
        specification = PredictiveWorldSpecification.from_seed(18400)
        self.assertEqual(
            specification,
            PredictiveWorldSpecification.from_seed(18400),
        )
        self.assertEqual(len(specification.rules), PREDICTIVE_STATE_COUNT)
        self.assertEqual(
            tuple(rule.history for rule in specification.rules),
            ALL_HISTORY_STATES,
        )
        self.assertTrue(
            all(
                tuple(sorted(rule.next_cues)) == CUE_VALUES
                for rule in specification.rules
            )
        )
        for history in ALL_HISTORY_STATES:
            self.assertEqual(
                {
                    specification.transition(history, action)[-1]
                    for action in PLANNING_ACTIONS
                },
                set(CUE_VALUES),
            )

    def test_instantaneous_cue_aliases_twenty_seven_states(self) -> None:
        for cue in CUE_VALUES:
            self.assertEqual(
                sum(history[-1] == cue for history in ALL_HISTORY_STATES),
                27,
            )

    def test_policy_observation_exposes_priming_then_one_cue_only(
        self,
    ) -> None:
        world = PredictivePlanningWorld(18401)
        task = evaluation.make_predictive_tasks(
            world.specification,
            count=1,
        )[0]
        initial = world.reset(
            start=task.start,
            goal=task.goal,
            max_steps=6,
        )
        self.assertEqual(initial.priming_history, task.start)
        result = world.step(task.oracle_actions[0])
        self.assertIsNone(result.observation.priming_history)
        self.assertEqual(
            set(PredictivePlanningStep.__dataclass_fields__),
            {"observation", "action", "reward"},
        )

    def test_reserved_tasks_are_unique_deterministic_and_four_steps(
        self,
    ) -> None:
        specification = PredictiveWorldSpecification.from_seed(18402)
        tasks = evaluation.make_predictive_tasks(specification)
        self.assertEqual(tasks, evaluation.make_predictive_tasks(specification))
        self.assertEqual(len(tasks), 24)
        self.assertEqual(
            len({(item.start, item.goal) for item in tasks}),
            24,
        )
        self.assertTrue(
            all(
                len(item.oracle_actions) == 4
                and specification.shortest_plan(item.start, item.goal)
                == item.oracle_actions
                for item in tasks
            )
        )

    def test_invalid_history_and_boolean_reward_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            next_history((0, 0, 0, 3), 0)  # type: ignore[arg-type]
        world = PredictivePlanningWorld(18403)
        observation = world.reset(
            start=world.specification.exploration_start,
            goal=None,
            max_steps=1,
        )
        with self.assertRaises(ValidationError):
            PredictivePlanningStep(
                observation=observation,
                action="amber",
                reward=False,  # type: ignore[arg-type]
            )


class PredictiveModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.explorer, cls.world = evaluation.run_predictive_exploration(
            18410,
            budget=486,
        )
        cls.model = cls.explorer.model

    def test_explorer_requires_chosen_action_and_archives_one_outcome(
        self,
    ) -> None:
        world = PredictivePlanningWorld(18411)
        observation = world.reset(
            start=world.specification.exploration_start,
            goal=None,
            max_steps=2,
        )
        explorer = HistoryFrontierExplorer()
        self.assertIsNotNone(observation.priming_history)
        explorer.start(observation.priming_history)  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            explorer.observe(
                next_cue=0,
                world_id=world.world_id,
                trace_id="test-trace",
            )
        action = explorer.choose_action()
        step = world.step(action)
        experience = explorer.observe(
            next_cue=step.observation.cue,
            world_id=world.world_id,
            trace_id="test-trace",
        )
        self.assertEqual(experience.action, action)
        self.assertEqual(len(explorer.model.archive), 1)
        self.assertEqual(
            set(
                json.loads(explorer.model.to_snapshot())["archive"][0]
            ),
            {
                "world_id",
                "trace_id",
                "sequence",
                "history",
                "action",
                "next_cue",
            },
        )

    def test_model_rejects_replay_discontinuity_and_trace_mixing(
        self,
    ) -> None:
        model = PredictiveHistoryModel()
        first = PredictiveTransitionExperience(
            world_id="world",
            trace_id="trace",
            sequence=1,
            history=(0, 0, 0, 0),
            action="amber",
            next_cue=1,
        )
        model.observe(first)
        with self.assertRaises(ValidationError):
            model.observe(first)
        with self.assertRaises(ValidationError):
            model.observe(
                PredictiveTransitionExperience(
                    world_id="world",
                    trace_id="trace",
                    sequence=2,
                    history=(2, 2, 2, 2),
                    action="amber",
                    next_cue=0,
                )
            )
        with self.assertRaises(ValidationError):
            model.observe(
                PredictiveTransitionExperience(
                    world_id="world",
                    trace_id="other-trace",
                    sequence=2,
                    history=first.next_history,
                    action="amber",
                    next_cue=0,
                )
            )

    def test_frontier_exploration_covers_and_predicts_every_pair(
        self,
    ) -> None:
        self.assertEqual(
            self.model.known_transition_pair_count,
            PREDICTIVE_PAIR_COUNT,
        )
        self.assertEqual(self.model.experience_count, 486)
        for history in ALL_HISTORY_STATES:
            for action in PLANNING_ACTIONS:
                prediction = self.model.predict(history, action)
                self.assertIsNotNone(prediction)
                self.assertEqual(
                    prediction.next_history,  # type: ignore[union-attr]
                    self.world.specification.transition(history, action),
                )

    def test_planner_composes_exact_four_step_paths(self) -> None:
        planner = PredictiveHistoryPlanner(self.model)
        tasks = evaluation.make_predictive_tasks(
            self.world.specification,
            count=8,
        )
        for task in tasks:
            plan = planner.plan(task.start, task.goal)
            self.assertTrue(plan.found)
            self.assertEqual(len(plan.actions), 4)
            self.assertEqual(plan.predicted_histories[-1], task.goal)

    def test_snapshot_preserves_pending_action_and_rejects_tampering(
        self,
    ) -> None:
        pending = self.explorer.choose_action()
        snapshot = self.explorer.to_snapshot()
        restored = HistoryFrontierExplorer.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.choose_action(), pending)

        count_tamper = json.loads(snapshot)
        count_tamper["model"]["counts"][0]["next_counts"][0]["count"] += 1
        with self.assertRaises(ValidationError):
            HistoryFrontierExplorer.from_snapshot(
                json.dumps(count_tamper)
            )

        state_tamper = json.loads(snapshot)
        state_tamper["current_history"] = [2, 2, 2, 2]
        with self.assertRaises(ValidationError):
            HistoryFrontierExplorer.from_snapshot(
                json.dumps(state_tamper)
            )

    def test_action_rotation_changes_the_model_used_for_planning(
        self,
    ) -> None:
        task = evaluation.make_predictive_tasks(
            self.world.specification,
            count=1,
        )[0]
        correct = PredictiveHistoryPlanner(self.model).plan(
            task.start,
            task.goal,
        )
        rotated = PredictiveHistoryPlanner(
            self.model,
            action_rotation=1,
        ).plan(task.start, task.goal)
        self.assertTrue(correct.found)
        self.assertTrue(rotated.found)
        self.assertNotEqual(correct.actions, rotated.actions)


class PredictiveEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = evaluation.run_predictive_suite(
            development_seeds=(18420, 18421, 18422, 18423),
            final_seeds=(18520, 18521, 18522, 18523),
            budget_candidates=(486,),
        )

    def test_small_suite_is_disjoint_unique_causal_and_persistent(
        self,
    ) -> None:
        self.assertEqual(self.report.final_world_count, 4)
        self.assertEqual(self.report.unique_world_count, 4)
        self.assertEqual(self.report.task_count, 96)
        self.assertFalse(
            set(self.report.development.seeds)
            & set(self.report.final_seeds)
        )
        self.assertEqual(self.report.mean_coverage, 1.0)
        self.assertEqual(self.report.known_transition_accuracy, 1.0)
        self.assertEqual(self.report.candidate_success_rate, 1.0)
        self.assertGreater(
            self.report.candidate_success_rate,
            self.report.reactive_success_rate,
        )
        self.assertGreater(
            self.report.candidate_success_rate,
            self.report.myopic_success_rate,
        )
        self.assertGreater(
            self.report.candidate_success_rate,
            self.report.permuted_action_success_rate,
        )
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)
        self.assertEqual(self.report.frozen_model_rate, 1.0)
        self.assertIn("18420-18423", self.report.held_out_definition)
        self.assertIn("18520-18523", self.report.held_out_definition)

    def test_seed_overlap_and_invalid_budget_grid_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            evaluation.run_predictive_suite(
                development_seeds=(18600,),
                final_seeds=(18600,),
                budget_candidates=(486,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_predictive_budget(
                seeds=(18601,),
                budget_candidates=(486, 486),
            )

    def test_regression_criteria_are_conjunctive(self) -> None:
        passing = evaluation.report_with_predictive_metrics(
            self.report,
            mean_coverage=0.90,
            known_transition_accuracy=1.0,
            candidate_success_rate=0.90,
            improvement_vs_reactive=0.50,
            improvement_vs_myopic=0.35,
            improvement_vs_permuted_action=0.40,
            improvement_vs_random=0.50,
            simultaneous_ablation_world_win_rate=0.90,
            mean_candidate_excess_steps_vs_oracle=0.25,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
            frozen_model_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            evaluation.report_with_predictive_metrics(
                passing,
                improvement_vs_myopic=0.35 - 1e-12,
            ).passes_regression_criteria()
        )

    def test_kernel_does_not_promote_a_failed_conjunction(self) -> None:
        failing = evaluation.report_with_predictive_metrics(
            self.report,
            improvement_vs_reactive=-1.0,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = evaluation.record_predictive_result(kernel, failing)
        self.assertEqual(
            result.goal.status,
            GoalStatus.WAITING_OBSERVATION,
        )
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
