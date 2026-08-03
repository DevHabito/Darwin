from __future__ import annotations

import unittest

from darwin_v50.integrated_cycle_evaluation import (
    INTEGRATED_CYCLE_DEVELOPMENT_SEEDS,
    INTEGRATED_CYCLE_TEST_SEEDS,
    IntegratedCycleDevelopmentReport,
    bootstrap_integrated_cycle_metrics,
    evaluate_integrated_world,
    integrated_cycle_development_record,
    run_integrated_cycle_development,
)
from darwin_v50.models import ValidationError


class IntegratedCycleEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = evaluate_integrated_world(
            INTEGRATED_CYCLE_TEST_SEEDS[0]
        )
        cls.report = IntegratedCycleDevelopmentReport(
            seeds=(cls.world.seed,),
            worlds=(cls.world,),
        )

    def test_engineering_world_is_sensitive_to_policy_ablation(self) -> None:
        self.assertEqual(self.world.task_count, 24)
        self.assertEqual(self.world.candidate_success_rate, 1.0)
        self.assertEqual(self.world.uninterrupted_success_rate, 1.0)
        self.assertEqual(self.world.oracle_success_rate, 1.0)
        self.assertLess(
            self.world.rotated_success_rate,
            self.world.candidate_success_rate,
        )
        self.assertLess(
            self.world.random_success_rate,
            self.world.candidate_success_rate,
        )
        self.assertEqual(self.world.mean_candidate_steps, 4.0)

    def test_restart_and_kernel_integrity_checks_are_exact(self) -> None:
        for value in (
            self.world.restart_action_exact_rate,
            self.world.prediction_match_rate,
            self.world.model_frozen_rate,
            self.world.checkpoint_replay_rate,
            self.world.kernel_restart_rate,
            self.world.kernel_lineage_rate,
            self.world.action_observation_correlation_rate,
            self.world.no_premature_success_rate,
        ):
            self.assertEqual(value, 1.0)

    def test_development_record_is_explicitly_non_capability(self) -> None:
        record = integrated_cycle_development_record(
            self.report,
            bootstrap_seed=39701,
            bootstrap_samples=50,
        )
        self.assertEqual(record["status"], "development-only")
        self.assertFalse(record["capability_claim"])
        self.assertFalse(record["h50_l16_registered"])
        self.assertEqual(record["world_count"], 1)
        self.assertEqual(record["task_count"], 24)
        self.assertIn("environment remains in memory", record["persistence_boundary"])
        self.assertEqual(
            bootstrap_integrated_cycle_metrics(
                self.report,
                seed=39701,
                samples=50,
            ),
            record["development_intervals"],
        )

    def test_seed_partitions_are_disjoint_and_invalid_inputs_fail(self) -> None:
        self.assertTrue(
            set(INTEGRATED_CYCLE_TEST_SEEDS).isdisjoint(
                INTEGRATED_CYCLE_DEVELOPMENT_SEEDS
            )
        )
        with self.assertRaises(ValidationError):
            run_integrated_cycle_development(seeds=())
        with self.assertRaises(ValidationError):
            run_integrated_cycle_development(seeds=(2, 1))
        with self.assertRaises(ValidationError):
            bootstrap_integrated_cycle_metrics(self.report, samples=0)


if __name__ == "__main__":
    unittest.main()
