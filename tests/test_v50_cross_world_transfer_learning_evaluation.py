from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_learning_evaluation import (
    TRANSFER_DEVELOPMENT_CONFIGURATIONS,
    TRANSFER_LEARNING_TEST_SEEDS,
    TransferDevelopmentConfiguration,
    evaluate_development_configuration,
    evaluate_learning_world,
    run_transfer_learning_development,
)
from darwin_v50.models import ValidationError


class TransferLearningDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.small_configuration = TransferDevelopmentConfiguration(
            source_tasks=4,
            source_cycles=4,
            initial_source_weight=0.5,
        )

    def test_world_scoring_is_deterministic_and_reports_source_cost(self) -> None:
        first = evaluate_learning_world(
            seed=27420,
            condition="related",
            configuration=self.small_configuration,
        )
        repeated = evaluate_learning_world(
            seed=27420,
            condition="related",
            configuration=self.small_configuration,
        )
        self.assertEqual(first, repeated)
        self.assertEqual(self.small_configuration.source_interactions, 256)
        self.assertTrue(math_is_finite(first.shuffled.log_loss))

    def test_configuration_report_balances_all_conditions(self) -> None:
        report = evaluate_development_configuration(
            seeds=TRANSFER_LEARNING_TEST_SEEDS[:2],
            configuration=self.small_configuration,
        )
        self.assertEqual(len(report.worlds), 6)
        self.assertTrue(math_is_finite(report.robust_score))

    def test_full_grid_selection_is_deterministic_on_one_test_seed(self) -> None:
        first = run_transfer_learning_development(
            seeds=TRANSFER_LEARNING_TEST_SEEDS[:1]
        )
        repeated = run_transfer_learning_development(
            seeds=TRANSFER_LEARNING_TEST_SEEDS[:1]
        )
        self.assertEqual(first, repeated)
        self.assertEqual(len(first.configurations), 18)
        self.assertIn(first.selected, TRANSFER_DEVELOPMENT_CONFIGURATIONS)
        payload = first.to_summary_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["h50_l14_registered"])

    def test_invalid_grid_value_and_condition_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            TransferDevelopmentConfiguration(
                source_tasks=32,
                source_cycles=4,
                initial_source_weight=0.5,
            )
        with self.assertRaises(ValidationError):
            evaluate_learning_world(
                seed=27421,
                condition="unknown",
                configuration=self.small_configuration,
            )


def math_is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


if __name__ == "__main__":
    unittest.main()
