from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_learning_calibration import (
    TRANSFER_CONTROL_LEARNING_CALIBRATION_SEEDS,
    TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS,
    run_transfer_control_learning_calibration,
    transfer_control_learning_calibration_criteria,
)
from darwin_v50.cross_world_transfer_control_learning_evaluation import (
    TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS,
    TRANSFER_CONTROL_LEARNING_TEST_SEEDS,
)
from darwin_v50.models import ValidationError


class TransferControlLearningCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = run_transfer_control_learning_calibration(
            seeds=TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS,
            bootstrap_seed=33950,
            bootstrap_samples=200,
        )

    def test_record_is_deterministic_and_not_a_claim(self) -> None:
        repeated = run_transfer_control_learning_calibration(
            seeds=TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS,
            bootstrap_seed=33950,
            bootstrap_samples=200,
        )
        self.assertEqual(self.record, repeated)
        self.assertFalse(self.record["capability_claim"])
        self.assertFalse(self.record["h50_l15_registered"])
        self.assertEqual(len(self.record["criteria"]), 21)

    def test_cost_feedback_and_integrity_are_explicit(self) -> None:
        self.assertEqual(self.record["source_interactions"], 2048)
        self.assertEqual(self.record["target_interactions"], 64)
        self.assertEqual(self.record["source_to_target_cost_ratio"], 32.0)
        self.assertIn("transition and reward", self.record["feedback_boundary"])
        self.assertTrue(
            all(value == 1.0 for value in self.record["integrity"].values())
        )

    def test_calibration_seeds_are_fresh(self) -> None:
        prior = set(TRANSFER_CONTROL_LEARNING_TEST_SEEDS) | set(
            TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS).isdisjoint(
                prior
            )
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_LEARNING_CALIBRATION_SEEDS).isdisjoint(
                prior | set(TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS)
            )
        )

    def test_incomplete_metrics_and_invalid_bootstrap_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            run_transfer_control_learning_calibration(
                seeds=TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS,
                bootstrap_samples=0,
            )
        metrics = dict(self.record["metrics"])
        metrics.pop(next(iter(metrics)))
        with self.assertRaises(ValidationError):
            transfer_control_learning_calibration_criteria(
                metrics,
                integrity=self.record["integrity"],
                source_interactions=2048,
                target_interactions=64,
            )


if __name__ == "__main__":
    unittest.main()
