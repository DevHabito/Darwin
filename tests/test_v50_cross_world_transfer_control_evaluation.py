from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_evaluation import (
    TRANSFER_CONTROL_TEST_SEEDS,
    TRANSFER_CONTROL_VALIDATION_SEEDS,
    balanced_transfer_context_schedule,
    bootstrap_transfer_control_metrics,
    evaluate_transfer_control_world,
    run_transfer_control_sensitivity,
    transfer_control_sensitivity_criteria,
    transfer_control_validation_record,
)
from darwin_v50.cross_world_transfer_calibration import (
    TRANSFER_CALIBRATION_SEEDS,
)
from darwin_v50.cross_world_transfer_confirmation import (
    TRANSFER_CONFIRMATION_FINAL_SEEDS,
    TRANSFER_INDEPENDENT_FINAL_SEEDS,
)
from darwin_v50.cross_world_transfer_evaluation import TRANSFER_CONDITIONS
from darwin_v50.learned_context_lab import all_contexts
from darwin_v50.models import ValidationError


class TransferControlScheduleTests(unittest.TestCase):
    def test_each_cycle_contains_every_context_once(self) -> None:
        schedule = balanced_transfer_context_schedule(cycles=3, seed=30290)
        contexts = set(all_contexts(3))
        self.assertEqual(len(schedule), 24)
        for start in range(0, len(schedule), 8):
            self.assertEqual(set(schedule[start : start + 8]), contexts)
        self.assertEqual(
            schedule,
            balanced_transfer_context_schedule(cycles=3, seed=30290),
        )

    def test_invalid_cycles_fail_closed(self) -> None:
        for value in (0, -1, True):
            with self.assertRaises(ValidationError):
                balanced_transfer_context_schedule(cycles=value, seed=30290)

    def test_validation_seeds_are_fresh(self) -> None:
        prior = (
            set(TRANSFER_CONTROL_TEST_SEEDS)
            | set(TRANSFER_CALIBRATION_SEEDS)
            | set(TRANSFER_CONFIRMATION_FINAL_SEEDS)
            | set(TRANSFER_INDEPENDENT_FINAL_SEEDS)
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_VALIDATION_SEEDS).isdisjoint(prior)
        )


class TransferControlSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_control_sensitivity(
            seeds=TRANSFER_CONTROL_TEST_SEEDS[:4]
        )

    def test_report_is_deterministic_and_explicitly_not_a_claim(self) -> None:
        repeated = run_transfer_control_sensitivity(
            seeds=TRANSFER_CONTROL_TEST_SEEDS[:4]
        )
        self.assertEqual(self.report, repeated)
        payload = self.report.to_summary_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["h50_l15_registered"])

    def test_only_chosen_actions_enter_the_causal_archive(self) -> None:
        for world in self.report.worlds:
            self.assertTrue(world.scratch.causal_archive_valid)
            self.assertTrue(world.oracle.causal_archive_valid)
            self.assertTrue(world.scratch.public_identity_valid)
            self.assertTrue(world.oracle.public_identity_valid)

    def test_oracle_signal_has_expected_test_only_direction(self) -> None:
        self.assertGreater(
            self.report.mean_metric(
                "related", "pseudo_regret_reduction"
            ),
            0.0,
        )

    def test_bootstrap_and_conjunctive_record_are_deterministic(self) -> None:
        first = transfer_control_validation_record(
            self.report,
            bootstrap_seed=30291,
            bootstrap_samples=200,
        )
        second = transfer_control_validation_record(
            self.report,
            bootstrap_seed=30291,
            bootstrap_samples=200,
        )
        self.assertEqual(first, second)
        self.assertFalse(first["capability_claim"])
        self.assertEqual(len(first["criteria"]), 10)

    def test_incomplete_metrics_and_invalid_bootstrap_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            bootstrap_transfer_control_metrics(
                self.report,
                samples=0,
            )
        metrics = bootstrap_transfer_control_metrics(
            self.report,
            seed=30292,
            samples=20,
        )
        metrics.pop("related_reward_improvement")
        with self.assertRaises(ValidationError):
            transfer_control_sensitivity_criteria(
                metrics,
                causal_archive_rate=1.0,
                public_identity_rate=1.0,
            )
        self.assertLess(
            self.report.mean_metric(
                "adversarial", "pseudo_regret_reduction"
            ),
            0.0,
        )

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_transfer_control_world(
                seed=30299,
                condition="unknown",
            )
        with self.assertRaises(ValidationError):
            evaluate_transfer_control_world(
                seed=30299,
                condition=TRANSFER_CONDITIONS[0],
                epsilon=float("nan"),
            )
        with self.assertRaises(ValidationError):
            self.report.mean_metric("related", "not-a-metric")


if __name__ == "__main__":
    unittest.main()
