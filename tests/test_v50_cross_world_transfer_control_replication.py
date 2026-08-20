from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_diagnostics import (
    TRANSFER_CONTROL_AUDIT_SEEDS,
    TRANSFER_CONTROL_AUDIT_TEST_SEEDS,
)
from darwin_v50.cross_world_transfer_control_evaluation import (
    TRANSFER_CONTROL_TEST_SEEDS,
    TRANSFER_CONTROL_VALIDATION_SEEDS,
)
from darwin_v50.cross_world_transfer_control_replication import (
    TRANSFER_CONTROL_REPLICATION_TEST_SEEDS,
    TRANSFER_CONTROL_REPLICATION_VALIDATION_SEEDS,
    run_transfer_control_replication,
    wilson_rate_interval,
)
from darwin_v50.models import ValidationError


class TransferControlReplicationTests(unittest.TestCase):
    def test_wilson_interval_does_not_collapse_for_eight_successes(self) -> None:
        interval = wilson_rate_interval(successes=8, total=8)
        self.assertEqual(interval.mean, 1.0)
        self.assertLess(interval.low, 1.0)
        self.assertEqual(interval.high, 1.0)

    def test_wilson_inputs_fail_closed(self) -> None:
        for successes, total in ((-1, 8), (9, 8), (0, 0), (True, 8)):
            with self.assertRaises(ValidationError):
                wilson_rate_interval(successes=successes, total=total)

    def test_replication_record_is_deterministic_and_not_a_claim(self) -> None:
        first = run_transfer_control_replication(
            seeds=TRANSFER_CONTROL_REPLICATION_TEST_SEEDS
        )
        second = run_transfer_control_replication(
            seeds=TRANSFER_CONTROL_REPLICATION_TEST_SEEDS
        )
        self.assertEqual(first, second)
        self.assertFalse(first["capability_claim"])
        self.assertFalse(first["can_reverse_experiment_025"])
        self.assertFalse(first["h50_l15_registered"])
        self.assertEqual(len(first["criteria"]), 10)
        self.assertEqual(
            first["interval_methods"]["related_simultaneous_win_rate"],
            "wilson_score_95_percent",
        )

    def test_replication_seeds_are_fresh(self) -> None:
        prior = (
            set(TRANSFER_CONTROL_TEST_SEEDS)
            | set(TRANSFER_CONTROL_VALIDATION_SEEDS)
            | set(TRANSFER_CONTROL_AUDIT_SEEDS)
            | set(TRANSFER_CONTROL_AUDIT_TEST_SEEDS)
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_REPLICATION_TEST_SEEDS).isdisjoint(prior)
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_REPLICATION_VALIDATION_SEEDS).isdisjoint(
                prior | set(TRANSFER_CONTROL_REPLICATION_TEST_SEEDS)
            )
        )


if __name__ == "__main__":
    unittest.main()
