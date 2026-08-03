from __future__ import annotations

import json
import unittest

from darwin_v50.models import ValidationError
from darwin_v50.online_alignment_lab import (
    AlignmentExperience,
    OnlineActionAlignmentTracker,
    OnlineAdaptivePlanningCycle,
)
from darwin_v50.predictive_planning_evaluation import (
    make_predictive_tasks,
    run_predictive_exploration,
)
from darwin_v50.predictive_planning_lab import (
    PLANNING_ACTIONS,
    PredictiveHistoryModel,
    PredictivePlanningWorld,
)


class OnlineAlignmentLabTests(unittest.TestCase):
    SEED = 41800

    @classmethod
    def setUpClass(cls) -> None:
        explorer, world = run_predictive_exploration(cls.SEED, budget=486)
        cls.model_snapshot = explorer.model.to_snapshot()
        cls.specification = world.specification
        cls.task = make_predictive_tasks(cls.specification, count=1)[0]

    def _model(self) -> PredictiveHistoryModel:
        return PredictiveHistoryModel.from_snapshot(self.model_snapshot)

    def _experience(
        self,
        *,
        history: tuple[int, int, int, int],
        action: str,
        rotation: int,
        sequence: int,
        episode_index: int,
        step_index: int,
    ) -> AlignmentExperience:
        mapped = PLANNING_ACTIONS[
            (PLANNING_ACTIONS.index(action) + rotation)
            % len(PLANNING_ACTIONS)
        ]
        cue = self.specification.transition(history, mapped)[-1]
        return AlignmentExperience(
            sequence=sequence,
            episode_index=episode_index,
            step_index=step_index,
            history=history,
            action=action,
            next_cue=cue,
        )

    def test_latest_tracker_identifies_hidden_rotation_after_observation(self) -> None:
        tracker = OnlineActionAlignmentTracker(prior_model=self._model())
        experience = self._experience(
            history=self.task.start,
            action="amber",
            rotation=1,
            sequence=1,
            episode_index=1,
            step_index=0,
        )
        update = tracker.observe(experience)
        self.assertEqual(update.rotation_before, 0)
        self.assertEqual(update.compatible_rotation, 1)
        self.assertEqual(update.rotation_after, 1)
        self.assertTrue(update.changed)
        self.assertFalse(update.prediction_matched)
        self.assertTrue(tracker.prior_frozen)

    def test_frozen_cumulative_and_shifted_controls_are_distinct(self) -> None:
        frozen = OnlineActionAlignmentTracker(
            prior_model=self._model(),
            policy="frozen",
        )
        shifted = OnlineActionAlignmentTracker(
            prior_model=self._model(),
            evidence_shift=1,
        )
        for tracker in (frozen, shifted):
            update = tracker.observe(
                self._experience(
                    history=self.task.start,
                    action="amber",
                    rotation=1,
                    sequence=1,
                    episode_index=1,
                    step_index=0,
                )
            )
            self.assertEqual(update.compatible_rotation, 1)
        self.assertEqual(frozen.current_rotation, 0)
        self.assertEqual(shifted.current_rotation, 2)

        cumulative = OnlineActionAlignmentTracker(
            prior_model=self._model(),
            policy="cumulative",
        )
        history = self.task.start
        for index in range(4):
            experience = self._experience(
                history=history,
                action="amber",
                rotation=0,
                sequence=index + 1,
                episode_index=1,
                step_index=index,
            )
            cumulative.observe(experience)
            history = experience.observed_history
        shifted_experience = self._experience(
            history=history,
            action="amber",
            rotation=1,
            sequence=5,
            episode_index=1,
            step_index=4,
        )
        cumulative.observe(shifted_experience)
        self.assertEqual(cumulative.current_rotation, 0)

    def test_adaptive_cycle_recovers_from_one_wrong_action(self) -> None:
        model = self._model()
        tracker = OnlineActionAlignmentTracker(prior_model=model)
        cycle = OnlineAdaptivePlanningCycle(
            prior_model=model,
            tracker=tracker,
            session_id="session:online-test",
            goal_id="goal:online-test",
            evidence_source="online-test:evaluator",
            episode_index=1,
            initial_history=self.task.start,
            goal_history=self.task.goal,
            max_steps=6,
        )
        world = PredictivePlanningWorld(self.SEED)
        world.reset(start=self.task.start, goal=self.task.goal, max_steps=6)
        while not cycle.goal_reached:
            decision = cycle.choose_action()
            mapped = PLANNING_ACTIONS[
                (PLANNING_ACTIONS.index(decision.action) + 1)
                % len(PLANNING_ACTIONS)
            ]
            step = world.step(mapped)
            cycle.observe(
                action=decision.action,
                next_cue=step.observation.cue,
            )
        self.assertEqual(cycle.step_index, 5)
        self.assertEqual(cycle.updates[0].rotation_after, 1)
        self.assertTrue(cycle.goal_reached)
        self.assertTrue(cycle.prior_frozen)

    def test_cycle_and_tracker_snapshots_replay_exactly(self) -> None:
        model = self._model()
        tracker = OnlineActionAlignmentTracker(prior_model=model)
        cycle = OnlineAdaptivePlanningCycle(
            prior_model=model,
            tracker=tracker,
            session_id="session:online-snapshot",
            goal_id="goal:online-snapshot",
            evidence_source="online-test:evaluator",
            episode_index=1,
            initial_history=self.task.start,
            goal_history=self.task.goal,
            max_steps=6,
        )
        world = PredictivePlanningWorld(self.SEED)
        world.reset(start=self.task.start, goal=self.task.goal, max_steps=6)
        decision = cycle.choose_action()
        mapped = PLANNING_ACTIONS[
            (PLANNING_ACTIONS.index(decision.action) + 1)
            % len(PLANNING_ACTIONS)
        ]
        step = world.step(mapped)
        cycle.observe(action=decision.action, next_cue=step.observation.cue)
        cycle.choose_action()
        snapshot = cycle.to_snapshot()
        restored = OnlineAdaptivePlanningCycle.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(
            restored.tracker.to_snapshot(),
            cycle.tracker.to_snapshot(),
        )

        payload = json.loads(snapshot)
        payload["derived"]["current_rotation"] = 2
        with self.assertRaises(ValidationError):
            OnlineAdaptivePlanningCycle.from_snapshot(json.dumps(payload))

    def test_external_tracker_or_prior_mutation_fails_closed(self) -> None:
        model = self._model()
        tracker = OnlineActionAlignmentTracker(prior_model=model)
        cycle = OnlineAdaptivePlanningCycle(
            prior_model=model,
            tracker=tracker,
            session_id="session:online-mutation",
            goal_id="goal:online-mutation",
            evidence_source="online-test:evaluator",
            episode_index=1,
            initial_history=self.task.start,
            goal_history=self.task.goal,
            max_steps=6,
        )
        tracker.observe(
            self._experience(
                history=self.task.start,
                action="amber",
                rotation=0,
                sequence=1,
                episode_index=1,
                step_index=0,
            )
        )
        with self.assertRaises(ValidationError):
            cycle.choose_action()


if __name__ == "__main__":
    unittest.main()
