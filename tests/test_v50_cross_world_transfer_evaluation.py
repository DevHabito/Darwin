from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_evaluation import (
    TRANSFER_TEST_BOOTSTRAP_SEED,
    TRANSFER_TEST_SEEDS,
    evaluate_transfer_world,
    paired_bootstrap_interval,
    run_transfer_benchmark,
)
from darwin_v50.models import ValidationError


class TransferSensitivityEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_benchmark(
            seeds=TRANSFER_TEST_SEEDS,
            bootstrap_seed=TRANSFER_TEST_BOOTSTRAP_SEED,
            bootstrap_samples=200,
        )

    def test_evaluator_is_deterministic(self) -> None:
        repeated = run_transfer_benchmark(
            seeds=TRANSFER_TEST_SEEDS,
            bootstrap_seed=TRANSFER_TEST_BOOTSTRAP_SEED,
            bootstrap_samples=200,
        )
        self.assertEqual(self.report, repeated)

    def test_oracle_signal_has_registered_direction_on_test_seeds(self) -> None:
        self.assertGreater(
            self.report.condition("related").log_loss_improvement.mean,
            0.0,
        )
        self.assertLess(
            self.report.condition("adversarial").log_loss_improvement.mean,
            0.0,
        )

    def test_report_is_explicitly_not_a_capability_claim(self) -> None:
        payload = self.report.to_dict()
        self.assertEqual(payload["status"], "benchmark-sensitivity-only")
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["h50_l14_registered"])

    def test_same_outcomes_score_scratch_and_transfer(self) -> None:
        score = evaluate_transfer_world(seed=27220, condition="related")
        self.assertEqual(score.interactions, 64)
        self.assertGreaterEqual(score.scratch_log_loss, 0.0)
        self.assertGreaterEqual(score.transfer_log_loss, 0.0)

    def test_invalid_condition_and_bootstrap_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_transfer_world(seed=27221, condition="hidden-answer")
        with self.assertRaises(ValidationError):
            paired_bootstrap_interval((0.1, 0.2), seed=1, samples=99)


if __name__ == "__main__":
    unittest.main()
