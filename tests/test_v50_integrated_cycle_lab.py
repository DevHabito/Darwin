from __future__ import annotations

import json
import unittest

from darwin_v50.integrated_cycle_lab import IntegratedPlanningCycle
from darwin_v50.models import ValidationError
from darwin_v50.predictive_planning_evaluation import (
    make_predictive_tasks,
    run_predictive_exploration,
)
from darwin_v50.predictive_planning_lab import (
    PredictivePlanningWorld,
    PredictiveTransitionExperience,
)


class IntegratedPlanningCycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        explorer, world = run_predictive_exploration(38800, budget=486)
        cls.model_snapshot = explorer.model.to_snapshot()
        cls.task = make_predictive_tasks(world.specification, count=1)[0]

    def _cycle(self) -> IntegratedPlanningCycle:
        from darwin_v50.predictive_planning_lab import PredictiveHistoryModel

        return IntegratedPlanningCycle(
            model=PredictiveHistoryModel.from_snapshot(self.model_snapshot),
            session_id="session:integrated-test",
            goal_id="goal:integrated-test",
            evidence_source="integrated-test:evaluator",
            initial_history=self.task.start,
            goal_history=self.task.goal,
            max_steps=6,
        )

    def test_cycle_replans_from_observation_and_reaches_goal(self) -> None:
        cycle = self._cycle()
        world = PredictivePlanningWorld(38800)
        world.reset(start=self.task.start, goal=self.task.goal, max_steps=6)
        while not cycle.goal_reached:
            decision = cycle.choose_action()
            result = world.step(decision.action)
            observation = cycle.observe(
                action=decision.action,
                next_cue=result.observation.cue,
            )
            self.assertTrue(observation.prediction_matched)
        self.assertTrue(cycle.goal_reached)
        self.assertTrue(cycle.model_frozen)
        self.assertEqual(cycle.action_history, self.task.oracle_actions)

    def test_checkpoint_replays_observed_and_pending_state_exactly(self) -> None:
        cycle = self._cycle()
        world = PredictivePlanningWorld(38800)
        world.reset(start=self.task.start, goal=self.task.goal, max_steps=6)
        first = cycle.choose_action()
        result = world.step(first.action)
        cycle.observe(action=first.action, next_cue=result.observation.cue)
        cycle.choose_action()
        snapshot = cycle.to_snapshot()
        restored = IntegratedPlanningCycle.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.current_history, cycle.current_history)
        self.assertEqual(restored.pending_decision, cycle.pending_decision)
        self.assertEqual(restored.model_digest, cycle.model_digest)

    def test_checkpoint_rejects_derived_action_and_model_tampering(self) -> None:
        cycle = self._cycle()
        cycle.choose_action()
        payload = json.loads(cycle.to_snapshot())
        payload["derived"]["step_index"] = 4
        with self.assertRaises(ValidationError):
            IntegratedPlanningCycle.from_snapshot(json.dumps(payload))

        payload = json.loads(cycle.to_snapshot())
        payload["pending_decision"]["action"] = "not-an-action"
        with self.assertRaises(ValidationError):
            IntegratedPlanningCycle.from_snapshot(json.dumps(payload))

        payload = json.loads(cycle.to_snapshot())
        payload["configuration"]["model_digest"] = "0" * 64
        with self.assertRaises(ValidationError):
            IntegratedPlanningCycle.from_snapshot(json.dumps(payload))

    def test_cycle_rejects_unplanned_or_mismatched_observation(self) -> None:
        cycle = self._cycle()
        with self.assertRaises(ValidationError):
            cycle.observe(action="amber", next_cue=0)
        decision = cycle.choose_action()
        wrong = next(
            action
            for action in ("amber", "cyan", "violet")
            if action != decision.action
        )
        with self.assertRaises(ValidationError):
            cycle.observe(action=wrong, next_cue=0)

    def test_model_mutation_during_control_fails_closed(self) -> None:
        cycle = self._cycle()
        last = cycle.model.archive[-1]
        cycle.model.observe(
            PredictiveTransitionExperience(
                world_id=last.world_id,
                trace_id=last.trace_id,
                sequence=last.sequence + 1,
                history=last.next_history,
                action="amber",
                next_cue=0,
            )
        )
        with self.assertRaises(ValidationError):
            cycle.choose_action()


if __name__ == "__main__":
    unittest.main()
