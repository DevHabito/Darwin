from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from darwin_v50.integrated_cycle_durability import IntegratedRecoveryBundle
from darwin_v50.integrated_cycle_lab import IntegratedPlanningCycle
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import (
    ComparisonCondition,
    ComparisonOperator,
    ValidationError,
    canonical_json,
)
from darwin_v50.predictive_planning_evaluation import (
    make_predictive_tasks,
    run_predictive_exploration,
)
from darwin_v50.predictive_planning_lab import (
    PredictiveHistoryModel,
    PredictivePlanningWorld,
)


class IntegratedCycleDurabilityTests(unittest.TestCase):
    SEED = 39800

    @classmethod
    def setUpClass(cls) -> None:
        explorer, world = run_predictive_exploration(cls.SEED, budget=486)
        cls.model_snapshot = explorer.model.to_snapshot()
        cls.task = make_predictive_tasks(world.specification, count=1)[0]

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "durability.db"
        self.kernel = DarwinKernelV50.open(self.database)
        self.goal = self.kernel.create_goal(
            session_id="session:durability-test",
            description="Reach the supplied target",
            evidence_source="durability-test:evaluator",
            condition=ComparisonCondition(
                "goal_reached",
                ComparisonOperator.EQUAL,
                1,
            ),
        )
        self.goal = self.kernel.start_goal(self.goal.goal_id)
        self.cycle = IntegratedPlanningCycle(
            model=PredictiveHistoryModel.from_snapshot(self.model_snapshot),
            session_id=self.goal.session_id,
            goal_id=self.goal.goal_id,
            evidence_source=self.goal.evidence_source,
            initial_history=self.task.start,
            goal_history=self.task.goal,
            max_steps=6,
        )
        self.world = PredictivePlanningWorld(self.SEED)
        self.world.reset(
            start=self.task.start,
            goal=self.task.goal,
            max_steps=6,
        )

    def tearDown(self) -> None:
        if not self.kernel.store.closed:
            self.kernel.close()
        self.directory.cleanup()

    def _complete_one_step(self) -> None:
        decision = self.cycle.choose_action()
        self.goal = self.kernel.dispatch_action(
            self.goal.goal_id,
            action_name="predictive-history-step",
            parameters={"action": decision.action},
        )
        result = self.world.step(decision.action)
        observation = self.cycle.observe(
            action=decision.action,
            next_cue=result.observation.cue,
        )
        recorded = self.kernel.record_observation(
            self.goal.goal_id,
            action_id=self.goal.expected_action_id or "",
            source=self.goal.evidence_source,
            metrics={"goal_reached": int(observation.goal_reached)},
        )
        self.goal = recorded.goal

    def _pending_bundle(self) -> str:
        self._complete_one_step()
        self.goal = self.kernel.continue_goal(self.goal.goal_id)
        self.cycle.choose_action()
        return IntegratedRecoveryBundle.capture(
            cycle=self.cycle,
            goal=self.goal,
            events=self.kernel.goal_events(self.goal.goal_id),
            world_seed=self.SEED,
            task=self.task,
        )

    def test_restores_kernel_cycle_environment_and_pending_action(self) -> None:
        snapshot = self._pending_bundle()
        pending = self.cycle.pending_decision
        expected_history = self.cycle.current_history
        self.kernel.close()
        self.kernel = DarwinKernelV50.open(self.database)
        restored = IntegratedRecoveryBundle.restore(
            snapshot,
            kernel=self.kernel,
        )
        self.assertTrue(restored.checkpoint_exact)
        self.assertTrue(restored.environment_replay_exact)
        self.assertTrue(restored.pending_decision_preserved)
        self.assertEqual(restored.cycle.pending_decision, pending)
        self.assertEqual(
            restored.world.current_history_for_evaluator,
            expected_history,
        )

    def test_capture_rejects_non_quiescent_kernel(self) -> None:
        decision = self.cycle.choose_action()
        self.goal = self.kernel.dispatch_action(
            self.goal.goal_id,
            action_name="predictive-history-step",
            parameters={"action": decision.action},
        )
        with self.assertRaises(ValidationError):
            IntegratedRecoveryBundle.capture(
                cycle=self.cycle,
                goal=self.goal,
                events=self.kernel.goal_events(self.goal.goal_id),
                world_seed=self.SEED,
                task=self.task,
            )

    def test_checksum_and_stale_kernel_state_fail_closed(self) -> None:
        snapshot = self._pending_bundle()
        payload = json.loads(snapshot)
        payload["kernel"]["version"] += 1
        with self.assertRaises(ValidationError):
            IntegratedRecoveryBundle.restore(
                json.dumps(payload),
                kernel=self.kernel,
            )

        self.goal = self.kernel.dispatch_action(
            self.goal.goal_id,
            action_name="predictive-history-step",
            parameters={"action": self.cycle.pending_decision.action},
        )
        with self.assertRaises(ValidationError):
            IntegratedRecoveryBundle.restore(snapshot, kernel=self.kernel)

    def test_recomputed_environment_tampering_fails_causal_replay(self) -> None:
        snapshot = self._pending_bundle()
        payload = json.loads(snapshot)
        original_cue = self.cycle.observed_cues[0]
        action = self.cycle.action_history[0]
        alternate = self.SEED + 1
        while (
            PredictivePlanningWorld(alternate)
            .specification.transition(self.task.start, action)[-1]
            == original_cue
        ):
            alternate += 1
        payload["environment"]["seed"] = alternate
        core = {key: value for key, value in payload.items() if key != "checksum"}
        payload["checksum"] = hashlib.sha256(
            canonical_json(core).encode("utf-8")
        ).hexdigest()
        with self.assertRaises(ValidationError):
            IntegratedRecoveryBundle.restore(
                canonical_json(payload),
                kernel=self.kernel,
            )


if __name__ == "__main__":
    unittest.main()
