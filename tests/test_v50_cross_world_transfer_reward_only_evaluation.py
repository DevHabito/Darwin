from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_learning_confirmation import (
    TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS,
    TRANSFER_CONTROL_LEARNING_FINAL_SEEDS,
)
from darwin_v50.cross_world_transfer_control_learning_evaluation import (
    TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS,
    TRANSFER_CONTROL_LEARNING_TEST_SEEDS,
)
from darwin_v50.cross_world_transfer_reward_only_evaluation import (
    REWARD_ONLY_CONTROL_DEVELOPMENT_SEEDS,
    REWARD_ONLY_CONTROL_TEST_SEEDS,
    evaluate_reward_only_transfer_world,
    reward_only_transfer_development_record,
    run_reward_only_transfer_development,
)
from darwin_v50.models import ValidationError


class RewardOnlyTransferDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_reward_only_transfer_development(
            seeds=REWARD_ONLY_CONTROL_TEST_SEEDS
        )

    def test_report_is_deterministic_and_not_a_capability_claim(self) -> None:
        repeated = run_reward_only_transfer_development(
            seeds=REWARD_ONLY_CONTROL_TEST_SEEDS
        )
        self.assertEqual(self.report, repeated)
        payload = self.report.to_summary_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["next_hypothesis_registered"])
        self.assertNotIn("h50_l15_registered", payload)
        self.assertEqual(
            payload["baseline_h50_l15_status"],
            "passed_locally",
        )
        self.assertIn(
            "only chosen-action rewards",
            payload["feedback_boundary"],
        )
        self.assertIn("causally excluded", payload["feedback_boundary"])

    def test_cost_and_all_integrity_checks_are_explicit(self) -> None:
        payload = self.report.to_summary_dict()
        self.assertEqual(payload["source_interactions"], 2048)
        self.assertEqual(payload["target_interactions"], 64)
        self.assertEqual(payload["source_to_target_cost_ratio"], 32.0)
        self.assertTrue(
            all(value == 1.0 for value in payload["integrity"].values())
        )

    def test_development_record_is_deterministic_and_complete(self) -> None:
        first = reward_only_transfer_development_record(
            self.report,
            bootstrap_seed=35980,
            bootstrap_samples=200,
        )
        second = reward_only_transfer_development_record(
            self.report,
            bootstrap_seed=35980,
            bootstrap_samples=200,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first["development_intervals"]), 25)
        self.assertIn(
            "related_candidate_simultaneous_win_rate",
            first["development_intervals"],
        )

    def test_candidate_has_test_only_related_decision_signal(self) -> None:
        self.assertGreater(
            self.report.mean_improvement(
                "related",
                "candidate",
                "pseudo_regret",
            ),
            0.0,
        )
        self.assertGreater(
            self.report.mean_candidate_control_delta(
                "related",
                "pseudo_regret",
            ),
            0.0,
        )

    def test_development_seeds_are_fresh(self) -> None:
        prior = (
            set(TRANSFER_CONTROL_LEARNING_TEST_SEEDS)
            | set(TRANSFER_CONTROL_LEARNING_DEVELOPMENT_SEEDS)
            | set(TRANSFER_CONTROL_LEARNING_CONFIRMATION_TEST_SEEDS)
            | set(TRANSFER_CONTROL_LEARNING_FINAL_SEEDS)
        )
        self.assertTrue(set(REWARD_ONLY_CONTROL_TEST_SEEDS).isdisjoint(prior))
        self.assertTrue(
            set(REWARD_ONLY_CONTROL_DEVELOPMENT_SEEDS).isdisjoint(
                prior | set(REWARD_ONLY_CONTROL_TEST_SEEDS)
            )
        )

    def test_unknown_condition_and_wrong_report_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_reward_only_transfer_world(
                seed=35990,
                condition="unknown",
            )
        with self.assertRaises(ValidationError):
            reward_only_transfer_development_record(  # type: ignore[arg-type]
                object()
            )


if __name__ == "__main__":
    unittest.main()
