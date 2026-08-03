from __future__ import annotations

import unittest

from darwin_v50.models import ValidationError
from darwin_v50.online_alignment_evaluation import (
    ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS,
    ONLINE_ALIGNMENT_TEST_SEEDS,
    OnlineAlignmentDevelopmentReport,
    bootstrap_online_alignment_metrics,
    evaluate_online_alignment_world,
    online_alignment_development_record,
    run_online_alignment_development,
)


class OnlineAlignmentEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = evaluate_online_alignment_world(
            ONLINE_ALIGNMENT_TEST_SEEDS[0]
        )
        cls.report = OnlineAlignmentDevelopmentReport(
            seeds=(cls.world.seed,),
            worlds=(cls.world,),
        )

    def test_engineering_world_separates_online_policy_from_controls(self) -> None:
        self.assertEqual(self.world.task_count, 24)
        self.assertEqual(self.world.candidate_success_rate, 1.0)
        self.assertEqual(self.world.oracle_success_rate, 1.0)
        self.assertEqual(self.world.frozen_success_rate, 0.5)
        self.assertEqual(self.world.cumulative_success_rate, 0.5)
        self.assertEqual(self.world.shuffled_success_rate, 0.0)
        self.assertLess(self.world.random_success_rate, 0.1)
        self.assertEqual(
            self.world.candidate_segment_success_rates,
            (1.0, 1.0, 1.0, 1.0),
        )
        self.assertEqual(
            self.world.frozen_segment_success_rates,
            (1.0, 0.0, 1.0, 0.0),
        )
        self.assertEqual(self.world.candidate_mean_steps, 4.125)
        self.assertEqual(self.world.oracle_mean_steps, 4.0)
        self.assertEqual(self.world.boundary_adaptation_delay, 1.0)

    def test_integrated_candidate_causal_checks_are_exact(self) -> None:
        for value in (
            self.world.integration_parity_rate,
            self.world.alignment_identification_rate,
            self.world.post_observation_alignment_rate,
            self.world.tracker_snapshot_rate,
            self.world.kernel_lineage_rate,
            self.world.action_observation_correlation_rate,
            self.world.no_premature_success_rate,
            self.world.archive_retention_rate,
            self.world.prior_frozen_rate,
        ):
            self.assertEqual(value, 1.0)

    def test_development_record_is_deterministic_and_non_capability(self) -> None:
        first = online_alignment_development_record(
            self.report,
            bootstrap_seed=42701,
            bootstrap_samples=50,
        )
        second = online_alignment_development_record(
            self.report,
            bootstrap_seed=42701,
            bootstrap_samples=50,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "development-only")
        self.assertFalse(first["capability_claim"])
        self.assertFalse(first["h50_l17_registered"])
        self.assertEqual(
            first["development_intervals"],
            bootstrap_online_alignment_metrics(
                self.report,
                seed=42701,
                samples=50,
            ),
        )

    def test_seed_partitions_and_invalid_inputs_fail_closed(self) -> None:
        self.assertTrue(
            set(ONLINE_ALIGNMENT_TEST_SEEDS).isdisjoint(
                ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS
            )
        )
        with self.assertRaises(ValidationError):
            run_online_alignment_development(seeds=())
        with self.assertRaises(ValidationError):
            run_online_alignment_development(seeds=(2, 1))
        with self.assertRaises(ValidationError):
            bootstrap_online_alignment_metrics(self.report, samples=0)


if __name__ == "__main__":
    unittest.main()
