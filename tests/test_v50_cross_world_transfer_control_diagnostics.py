from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_diagnostics import (
    TRANSFER_CONTROL_AUDIT_SEEDS,
    TRANSFER_CONTROL_AUDIT_TEST_SEEDS,
    run_transfer_control_failure_audit,
)
from darwin_v50.cross_world_transfer_control_evaluation import (
    TRANSFER_CONTROL_TEST_SEEDS,
    TRANSFER_CONTROL_VALIDATION_SEEDS,
)
from darwin_v50.models import ValidationError


class TransferControlFailureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_control_failure_audit(
            seeds=TRANSFER_CONTROL_AUDIT_TEST_SEEDS,
            bootstrap_seed=31160,
            bootstrap_samples=200,
        )

    def test_report_is_deterministic_and_cannot_promote(self) -> None:
        repeated = run_transfer_control_failure_audit(
            seeds=TRANSFER_CONTROL_AUDIT_TEST_SEEDS,
            bootstrap_seed=31160,
            bootstrap_samples=200,
        )
        self.assertEqual(self.report, repeated)
        payload = self.report.to_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["can_promote_experiment_025"])
        self.assertFalse(payload["h50_l15_registered"])

    def test_rates_and_integrity_are_bounded(self) -> None:
        for name in (
            "realized_reward_win_rate",
            "expected_reward_win_rate",
            "simultaneous_win_rate",
            "expected_win_realized_nonwin_rate",
            "expected_nonwin_realized_win_rate",
        ):
            interval = self.report.metrics[name]
            self.assertGreaterEqual(interval.low, 0.0)
            self.assertLessEqual(interval.high, 1.0)
        self.assertEqual(self.report.causal_archive_rate, 1.0)
        self.assertEqual(self.report.public_identity_rate, 1.0)

    def test_audit_seeds_are_fresh(self) -> None:
        prior = set(TRANSFER_CONTROL_TEST_SEEDS) | set(
            TRANSFER_CONTROL_VALIDATION_SEEDS
        )
        self.assertTrue(set(TRANSFER_CONTROL_AUDIT_SEEDS).isdisjoint(prior))
        self.assertTrue(
            set(TRANSFER_CONTROL_AUDIT_TEST_SEEDS).isdisjoint(prior)
        )

    def test_invalid_bootstrap_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            run_transfer_control_failure_audit(
                seeds=TRANSFER_CONTROL_AUDIT_TEST_SEEDS,
                bootstrap_samples=0,
            )


if __name__ == "__main__":
    unittest.main()
