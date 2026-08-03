from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_feedback_audit import (
    FEEDBACK_AUDIT_SEEDS,
    FEEDBACK_AUDIT_TEST_SEEDS,
)
from darwin_v50.cross_world_transfer_local_gate_evaluation import (
    LOCAL_GATE_DEVELOPMENT_SEEDS,
    LOCAL_GATE_TEST_SEEDS,
    bootstrap_local_gate_metrics,
    evaluate_local_gate_world,
    local_gate_development_record,
    run_local_gate_development,
)
from darwin_v50.models import ValidationError


class LocalGateDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_local_gate_development(seeds=LOCAL_GATE_TEST_SEEDS)

    def test_report_is_deterministic_and_development_only(self) -> None:
        repeated = run_local_gate_development(seeds=LOCAL_GATE_TEST_SEEDS)
        self.assertEqual(self.report, repeated)
        payload = self.report.to_summary_dict()
        self.assertFalse(payload["capability_claim"])
        self.assertFalse(payload["new_hypothesis_registered"])
        self.assertIn("per context-action cell", payload["candidate_boundary"])
        self.assertIn("becomes zero", payload["candidate_boundary"])

    def test_cost_and_integrity_are_explicit(self) -> None:
        payload = self.report.to_summary_dict()
        self.assertEqual(payload["source_interactions"], 2048)
        self.assertEqual(payload["target_interactions"], 64)
        self.assertEqual(payload["source_to_target_cost_ratio"], 32.0)
        self.assertTrue(
            all(value == 1.0 for value in payload["integrity"].values())
        )

    def test_fallback_is_active_on_implementation_worlds(self) -> None:
        self.assertGreater(
            sum(item.candidate_fallback_cell_rate for item in self.report.worlds),
            0.0,
        )

    def test_development_record_is_deterministic_and_complete(self) -> None:
        first = local_gate_development_record(
            self.report,
            bootstrap_seed=37980,
            bootstrap_samples=200,
        )
        second = local_gate_development_record(
            self.report,
            bootstrap_seed=37980,
            bootstrap_samples=200,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first["development_intervals"]), 43)
        self.assertIn(
            "related_candidate_simultaneous_win_rate",
            first["development_intervals"],
        )

    def test_development_seeds_are_fresh(self) -> None:
        prior = set(FEEDBACK_AUDIT_TEST_SEEDS) | set(FEEDBACK_AUDIT_SEEDS)
        self.assertTrue(set(LOCAL_GATE_TEST_SEEDS).isdisjoint(prior))
        self.assertTrue(
            set(LOCAL_GATE_DEVELOPMENT_SEEDS).isdisjoint(
                prior | set(LOCAL_GATE_TEST_SEEDS)
            )
        )

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_local_gate_world(seed=37990, condition="unknown")
        with self.assertRaises(ValidationError):
            bootstrap_local_gate_metrics(self.report, samples=0)
        with self.assertRaises(ValidationError):
            self.report.mean_improvement(
                "related",
                "candidate",
                "unknown",
            )
        with self.assertRaises(ValidationError):
            self.report.mean_candidate_control_delta(
                "related",
                "oracle",
                "reward",
            )


if __name__ == "__main__":
    unittest.main()
