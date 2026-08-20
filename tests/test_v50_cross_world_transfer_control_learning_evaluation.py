from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_learning_evaluation import (
    TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS,
    TRANSFER_CONTROL_LEARNING_TEST_SEEDS,
    bootstrap_transfer_control_learning_metrics,
    evaluate_transfer_control_learning_world,
    run_transfer_control_learning_development,
    transfer_control_learning_development_record,
)
from darwin_v50.cross_world_transfer_control_replication import (
    TRANSFER_CONTROL_REPLICATION_TEST_SEEDS,
    TRANSFER_CONTROL_REPLICATION_VALIDATION_SEEDS,
)
from darwin_v50.models import ValidationError


class TransferControlLearningDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_transfer_control_learning_development(
            seeds=TRANSFER_CONTROL_LEARNING_TEST_SEEDS
        )

    def test_report_is_deterministic_and_not_a_claim(self) -> None:
        repeated = run_transfer_control_learning_development(
            seeds=TRANSFER_CONTROL_LEARNING_TEST_SEEDS
        )
        self.assertEqual(self.report, repeated)
        payload = self.report.to_summary_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["h50_l15_registered"])
        self.assertIn("transition and reward", payload["feedback_boundary"])

    def test_source_cost_and_integrity_are_explicit(self) -> None:
        payload = self.report.to_summary_dict()
        self.assertEqual(payload["source_interactions"], 2048)
        self.assertEqual(payload["target_interactions"], 64)
        self.assertEqual(payload["source_to_target_cost_ratio"], 32.0)
        self.assertTrue(
            all(value == 1.0 for value in payload["integrity"].values())
        )

    def test_development_intervals_are_deterministic_and_complete(self) -> None:
        first = transfer_control_learning_development_record(
            self.report,
            bootstrap_seed=32980,
            bootstrap_samples=200,
        )
        second = transfer_control_learning_development_record(
            self.report,
            bootstrap_seed=32980,
            bootstrap_samples=200,
        )
        self.assertEqual(first, second)
        self.assertIn(
            "related_candidate_simultaneous_win_rate",
            first["development_intervals"],
        )
        self.assertEqual(len(first["development_intervals"]), 25)

    def test_invalid_bootstrap_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            bootstrap_transfer_control_learning_metrics(
                self.report,
                samples=0,
            )

    def test_candidate_has_related_test_only_decision_signal(self) -> None:
        self.assertGreater(
            self.report.mean_improvement(
                "related", "candidate", "pseudo_regret"
            ),
            0.0,
        )
        self.assertGreater(
            self.report.mean_candidate_control_delta(
                "related", "pseudo_regret"
            ),
            0.0,
        )

    def test_development_seeds_are_fresh(self) -> None:
        prior = set(TRANSFER_CONTROL_REPLICATION_TEST_SEEDS) | set(
            TRANSFER_CONTROL_REPLICATION_VALIDATION_SEEDS
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_LEARNING_TEST_SEEDS).isdisjoint(prior)
        )
        self.assertTrue(
            set(TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS).isdisjoint(
                prior | set(TRANSFER_CONTROL_LEARNING_TEST_SEEDS)
            )
        )

    def test_invalid_condition_and_metric_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_transfer_control_learning_world(
                seed=32990,
                condition="unknown",
            )
        with self.assertRaises(ValidationError):
            self.report.mean_improvement(
                "related", "candidate", "unknown"
            )


if __name__ == "__main__":
    unittest.main()
    bootstrap_transfer_control_learning_metrics,
