from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_control_evaluation import (
    ControlMetricInterval,
)
from darwin_v50.cross_world_transfer_feedback_audit import (
    FEEDBACK_AUDIT_SEEDS,
    FEEDBACK_AUDIT_TEST_SEEDS,
    bootstrap_feedback_audit_metrics,
    evaluate_feedback_audit_world,
    feedback_audit_criteria,
    feedback_audit_record,
    run_feedback_audit,
)
from darwin_v50.cross_world_transfer_reward_only_evaluation import (
    REWARD_ONLY_CONTROL_DEVELOPMENT_SEEDS,
    REWARD_ONLY_CONTROL_TEST_SEEDS,
)
from darwin_v50.models import ValidationError


class CompatibilityFeedbackAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_feedback_audit(seeds=FEEDBACK_AUDIT_TEST_SEEDS)

    def test_report_is_deterministic_and_diagnostic_only(self) -> None:
        repeated = run_feedback_audit(seeds=FEEDBACK_AUDIT_TEST_SEEDS)
        self.assertEqual(self.report, repeated)
        payload = self.report.to_summary_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertEqual(payload["baseline_h50_l15_status"], "passed_locally")
        self.assertEqual(
            payload["experiment_031_status"],
            "not_eligible_for_calibration",
        )
        self.assertIn("only compatibility feedback mode differs", payload[
            "paired_boundary"
        ])

    def test_cost_pairing_and_integrity_are_explicit(self) -> None:
        payload = self.report.to_summary_dict()
        self.assertEqual(payload["source_interactions"], 2048)
        self.assertEqual(payload["target_interactions"], 64)
        self.assertEqual(payload["source_to_target_cost_ratio"], 32.0)
        self.assertTrue(
            all(value == 1.0 for value in payload["integrity"].values())
        )

    def test_fixed_archive_detects_test_only_mismatch_signal(self) -> None:
        adversarial = self.report.condition_rows("adversarial")
        self.assertGreater(
            sum(item.fixed_archive_weight_delta for item in adversarial),
            0.0,
        )

    def test_record_is_deterministic_and_has_frozen_conjunction(self) -> None:
        first = feedback_audit_record(
            self.report,
            bootstrap_seed=36980,
            bootstrap_samples=200,
        )
        second = feedback_audit_record(
            self.report,
            bootstrap_seed=36980,
            bootstrap_samples=200,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first["audit_intervals"]), 21)
        self.assertEqual(len(first["frozen_audit_criteria"]), 15)
        self.assertFalse(first["capability_claim"])

    def test_failed_interval_cannot_support_clean_audit_conclusion(self) -> None:
        intervals = bootstrap_feedback_audit_metrics(
            self.report,
            seed=36981,
            samples=100,
        )
        intervals["adversarial_dual_minus_reward_only_reward"] = (
            ControlMetricInterval(mean=-1.0, low=-2.0, high=0.0)
        )
        criteria = feedback_audit_criteria(self.report, intervals)
        self.assertFalse(
            criteria["adversarial_reward_benefit_low_above_zero"]
        )
        self.assertFalse(all(criteria.values()))

    def test_audit_seeds_are_fresh(self) -> None:
        prior = set(REWARD_ONLY_CONTROL_TEST_SEEDS) | set(
            REWARD_ONLY_CONTROL_DEVELOPMENT_SEEDS
        )
        self.assertTrue(set(FEEDBACK_AUDIT_TEST_SEEDS).isdisjoint(prior))
        self.assertTrue(
            set(FEEDBACK_AUDIT_SEEDS).isdisjoint(
                prior | set(FEEDBACK_AUDIT_TEST_SEEDS)
            )
        )

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_feedback_audit_world(seed=36990, condition="unknown")
        with self.assertRaises(ValidationError):
            bootstrap_feedback_audit_metrics(self.report, samples=0)
        with self.assertRaises(ValidationError):
            feedback_audit_criteria(self.report, {})


if __name__ == "__main__":
    unittest.main()
