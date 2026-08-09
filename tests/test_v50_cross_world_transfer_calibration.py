from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_calibration import (
    TRANSFER_CALIBRATION_TEST_SEEDS,
    run_transfer_calibration,
)
from darwin_v50.models import ValidationError


class TransferCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_calibration(
            seeds=TRANSFER_CALIBRATION_TEST_SEEDS[:2],
            bootstrap_seed=28100,
            bootstrap_samples=200,
        )

    def test_report_is_deterministic_and_not_a_claim(self) -> None:
        repeated = run_transfer_calibration(
            seeds=TRANSFER_CALIBRATION_TEST_SEEDS[:2],
            bootstrap_seed=28100,
            bootstrap_samples=200,
        )
        self.assertEqual(self.report, repeated)
        payload = self.report.to_dict()
        self.assertEqual(payload["status"], "calibration-only")
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["h50_l14_registered"])

    def test_metrics_include_causal_and_robustness_controls(self) -> None:
        self.assertIn(
            "related_candidate_minus_shuffled", self.report.metrics
        )
        self.assertIn(
            "unrelated_gated_improvement", self.report.metrics
        )
        self.assertIn(
            "adversarial_gated_improvement", self.report.metrics
        )
        self.assertEqual(len(self.report.criteria), 9)

    def test_invalid_bootstrap_and_seed_overlap_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            run_transfer_calibration(
                seeds=(27610, 27610),
                bootstrap_seed=1,
                bootstrap_samples=200,
            )
        with self.assertRaises(ValidationError):
            run_transfer_calibration(
                seeds=(27610,),
                bootstrap_seed=1,
                bootstrap_samples=99,
            )


if __name__ == "__main__":
    unittest.main()
