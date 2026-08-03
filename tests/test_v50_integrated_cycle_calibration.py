from __future__ import annotations

from dataclasses import replace
import unittest

from darwin_v50.integrated_cycle_calibration import (
    INTEGRATED_CALIBRATION_SEEDS,
    INTEGRATED_CALIBRATION_TEST_SEEDS,
    INTEGRATED_RESTART_MODES,
    IntegratedCalibrationReport,
    bootstrap_integrated_calibration_metrics,
    evaluate_integrated_calibration_world,
    integrated_calibration_criteria,
    run_integrated_calibration,
)
from darwin_v50.models import ValidationError


class IntegratedCycleCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = evaluate_integrated_calibration_world(
            INTEGRATED_CALIBRATION_TEST_SEEDS[0]
        )

    def test_engineering_world_exercises_every_restart_boundary(self) -> None:
        self.assertEqual(self.world.task_count, 24)
        self.assertEqual(self.world.restart_mode_counts, (6, 6, 6, 6))
        self.assertEqual(
            len(self.world.restart_mode_success_rates),
            len(INTEGRATED_RESTART_MODES),
        )
        self.assertTrue(
            all(value == 1.0 for value in self.world.restart_mode_success_rates)
        )
        self.assertEqual(self.world.candidate_success_rate, 1.0)
        self.assertEqual(self.world.uninterrupted_success_rate, 1.0)
        self.assertEqual(self.world.rotated_success_rate, 0.0)
        self.assertLess(self.world.random_success_rate, 0.1)

    def test_every_recovery_and_causal_integrity_rate_is_exact(self) -> None:
        for value in (
            self.world.restart_action_exact_rate,
            self.world.prediction_match_rate,
            self.world.model_frozen_rate,
            self.world.recovery_executed_rate,
            self.world.checkpoint_exact_rate,
            self.world.kernel_restart_exact_rate,
            self.world.environment_replay_exact_rate,
            self.world.pending_decision_preserved_rate,
            self.world.kernel_cycle_binding_exact_rate,
            self.world.kernel_lineage_rate,
            self.world.action_observation_correlation_rate,
            self.world.no_premature_success_rate,
        ):
            self.assertEqual(value, 1.0)

    def test_frozen_criteria_are_conjunctive_and_deterministic(self) -> None:
        seeds = tuple(range(50000, 50064))
        report = IntegratedCalibrationReport(
            seeds=seeds,
            worlds=tuple(
                replace(self.world, seed=seed) for seed in seeds
            ),
        )
        first = bootstrap_integrated_calibration_metrics(
            report,
            seed=50700,
            samples=100,
        )
        second = bootstrap_integrated_calibration_metrics(
            report,
            seed=50700,
            samples=100,
        )
        self.assertEqual(first, second)
        self.assertTrue(all(integrated_calibration_criteria(report, first).values()))

        damaged = replace(
            self.world,
            seed=seeds[0],
            environment_replay_exact_rate=0.0,
        )
        damaged_report = IntegratedCalibrationReport(
            seeds=seeds,
            worlds=(damaged,) + report.worlds[1:],
        )
        self.assertFalse(
            integrated_calibration_criteria(damaged_report, first)[
                "all_integrity_rates_equal_1"
            ]
        )

    def test_seed_partitions_and_invalid_inputs_fail_closed(self) -> None:
        self.assertTrue(
            set(INTEGRATED_CALIBRATION_TEST_SEEDS).isdisjoint(
                INTEGRATED_CALIBRATION_SEEDS
            )
        )
        with self.assertRaises(ValidationError):
            run_integrated_calibration(seeds=())
        with self.assertRaises(ValidationError):
            run_integrated_calibration(seeds=(2, 1))


if __name__ == "__main__":
    unittest.main()
