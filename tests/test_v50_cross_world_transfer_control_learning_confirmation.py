from __future__ import annotations

from dataclasses import replace
import unittest

from darwin_v50.cross_world_transfer_control_learning_calibration import (
    TRANSFER_CONTROL_LEARNING_CALIBRATION_SEEDS,
    TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS,
)
from darwin_v50.cross_world_transfer_control_learning_confirmation import (
    TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS,
    TRANSFER_CONTROL_LEARNING_FINAL_SEEDS,
    record_transfer_control_learning_confirmation,
    run_transfer_control_learning_confirmation,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.store import SQLiteEventStore


class TransferControlLearningConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_control_learning_confirmation(
            final_seeds=TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS,
            bootstrap_seed=34950,
            bootstrap_samples=200,
        )

    def test_report_is_deterministic_and_names_the_narrow_claim(self) -> None:
        repeated = run_transfer_control_learning_confirmation(
            final_seeds=TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS,
            bootstrap_seed=34950,
            bootstrap_samples=200,
        )
        self.assertEqual(self.report, repeated)
        payload = self.report.to_dict()
        self.assertIn("known-alignment", payload["capability_claim"])
        self.assertIn("auxiliary transition", payload["capability_claim"])
        self.assertTrue(
            payload["claim_limits_negative_transfer_but_does_not_eliminate_it"]
        )
        self.assertTrue(payload["h50_l15_registered"])

    def test_kernel_cannot_promote_a_failed_conjunction(self) -> None:
        criteria = dict(self.report.criteria)
        criteria["causal_archive_rate_equals_1"] = False
        integrity = dict(self.report.integrity)
        integrity["causal_archive_rate"] = 0.0
        failing = replace(
            self.report,
            criteria=criteria,
            integrity=integrity,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = record_transfer_control_learning_confirmation(kernel, failing)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertFalse(result.condition_satisfied)

    def test_derived_criteria_disagreement_is_rejected(self) -> None:
        criteria = dict(self.report.criteria)
        key = next(iter(criteria))
        criteria[key] = not criteria[key]
        with self.assertRaises(ValidationError):
            replace(self.report, criteria=criteria)

    def test_final_seeds_are_fresh(self) -> None:
        prior = set(TRANSFER_CONTROL_LEARNING_CALIBRATION_TEST_SEEDS) | set(
            TRANSFER_CONTROL_LEARNING_CALIBRATION_SEEDS
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS).isdisjoint(
                prior
            )
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_LEARNING_FINAL_SEEDS).isdisjoint(
                prior
                | set(TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS)
            )
        )


if __name__ == "__main__":
    unittest.main()
