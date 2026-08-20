from __future__ import annotations

from dataclasses import replace
import unittest

from darwin_v50.cross_world_transfer_confirmation import (
    TRANSFER_CONFIRMATION_TEST_SEEDS,
    TRANSFER_CONFIRMATION_FINAL_SEEDS,
    TRANSFER_INDEPENDENT_FINAL_SEEDS,
    record_transfer_confirmation,
    run_transfer_confirmation,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus
from darwin_v50.store import SQLiteEventStore


class TransferConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_confirmation(
            final_seeds=TRANSFER_CONFIRMATION_TEST_SEEDS[:2],
            bootstrap_seed=29200,
            bootstrap_samples=200,
        )

    def test_confirmation_is_deterministic_and_integrity_is_complete(self) -> None:
        repeated = run_transfer_confirmation(
            final_seeds=TRANSFER_CONFIRMATION_TEST_SEEDS[:2],
            bootstrap_seed=29200,
            bootstrap_samples=200,
        )
        self.assertEqual(self.report, repeated)
        self.assertEqual(self.report.causal_archive_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)
        self.assertEqual(self.report.public_identity_rate, 1.0)

    def test_kernel_cannot_promote_a_failed_conjunction(self) -> None:
        criteria = dict(self.report.criteria)
        criteria["causal_archive_rate_equals_1"] = False
        failing = replace(self.report, criteria=criteria)
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = record_transfer_confirmation(kernel, failing)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertFalse(result.condition_satisfied)

    def test_machine_record_names_the_narrow_claim(self) -> None:
        payload = self.report.to_dict()
        self.assertEqual(payload["status"], "confirmatory-h50-l14")
        self.assertIn("known-alignment", payload["capability_claim"])
        self.assertTrue(payload["h50_l14_registered"])

    def test_independent_confirmation_seeds_are_fresh(self) -> None:
        self.assertTrue(
            set(TRANSFER_INDEPENDENT_FINAL_SEEDS).isdisjoint(
                TRANSFER_CONFIRMATION_FINAL_SEEDS
            )
        )
        self.assertTrue(
            set(TRANSFER_INDEPENDENT_FINAL_SEEDS).isdisjoint(
                TRANSFER_CONFIRMATION_TEST_SEEDS
            )
        )


if __name__ == "__main__":
    unittest.main()
