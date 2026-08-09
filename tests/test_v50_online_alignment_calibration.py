from __future__ import annotations

from dataclasses import replace
import unittest

from darwin_v50.models import ValidationError
from darwin_v50.online_alignment_calibration import (
    ONLINE_ALIGNMENT_CALIBRATION_SEEDS,
    ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS,
    OnlineAlignmentCalibrationReport,
    bootstrap_online_alignment_calibration_metrics,
    online_alignment_calibration_criteria,
    run_online_alignment_calibration,
)
from darwin_v50.online_alignment_evaluation import (
    ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS,
    ONLINE_ALIGNMENT_TEST_SEEDS,
    evaluate_online_alignment_world,
)


class OnlineAlignmentCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = evaluate_online_alignment_world(
            ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS[0]
        )

    def test_engineering_world_matches_the_frozen_schedule(self) -> None:
        self.assertEqual(self.world.task_count, 24)
        self.assertEqual(self.world.candidate_success_rate, 1.0)
        self.assertEqual(self.world.oracle_success_rate, 1.0)
        self.assertEqual(self.world.frozen_success_rate, 0.5)
        self.assertEqual(self.world.cumulative_success_rate, 0.5)
        self.assertEqual(self.world.shuffled_success_rate, 0.0)
        self.assertEqual(
            self.world.candidate_segment_success_rates,
            (1.0, 1.0, 1.0, 1.0),
        )
        self.assertEqual(
            self.world.frozen_segment_success_rates,
            (1.0, 0.0, 1.0, 0.0),
        )
        self.assertEqual(self.world.boundary_adaptation_delay, 1.0)
        self.assertEqual(self.world.candidate_mean_steps, 4.125)
        self.assertEqual(self.world.oracle_mean_steps, 4.0)

    def test_engineering_world_preserves_every_integrity_rate(self) -> None:
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

    def test_frozen_criteria_are_conjunctive_and_deterministic(self) -> None:
        seeds = tuple(range(53000, 53064))
        report = OnlineAlignmentCalibrationReport(
            seeds=seeds,
            worlds=tuple(
                replace(self.world, seed=seed) for seed in seeds
            ),
        )
        first = bootstrap_online_alignment_calibration_metrics(
            report,
            seed=53700,
            samples=100,
        )
        second = bootstrap_online_alignment_calibration_metrics(
            report,
            seed=53700,
            samples=100,
        )
        self.assertEqual(first, second)
        self.assertTrue(
            all(online_alignment_calibration_criteria(report, first).values())
        )

        damaged = replace(
            self.world,
            seed=seeds[0],
            tracker_snapshot_rate=0.0,
        )
        damaged_report = OnlineAlignmentCalibrationReport(
            seeds=seeds,
            worlds=(damaged,) + report.worlds[1:],
        )
        self.assertFalse(
            online_alignment_calibration_criteria(damaged_report, first)[
                "all_integrity_rates_equal_1"
            ]
        )

    def test_calibration_record_remains_non_capability(self) -> None:
        record = run_online_alignment_calibration(
            seeds=(ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS[0],),
            bootstrap_seed=43701,
            bootstrap_samples=25,
        )
        self.assertEqual(record["status"], "calibration-only")
        self.assertFalse(record["capability_claim"])
        self.assertFalse(record["h50_l17_registered"])
        self.assertFalse(record["eligible_for_h50_l17_preregistration"])

    def test_seed_partitions_and_invalid_inputs_fail_closed(self) -> None:
        excluded = set(ONLINE_ALIGNMENT_TEST_SEEDS) | set(
            ONLINE_ALIGNMENT_DEVELOPMENT_SEEDS
        )
        self.assertTrue(
            excluded.isdisjoint(ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS)
        )
        self.assertTrue(excluded.isdisjoint(ONLINE_ALIGNMENT_CALIBRATION_SEEDS))
        self.assertTrue(
            set(ONLINE_ALIGNMENT_CALIBRATION_TEST_SEEDS).isdisjoint(
                ONLINE_ALIGNMENT_CALIBRATION_SEEDS
            )
        )
        with self.assertRaises(ValidationError):
            run_online_alignment_calibration(seeds=())
        with self.assertRaises(ValidationError):
            run_online_alignment_calibration(seeds=(2, 1))
        with self.assertRaises(ValidationError):
            bootstrap_online_alignment_calibration_metrics(
                OnlineAlignmentCalibrationReport(
                    seeds=(self.world.seed,),
                    worlds=(self.world,),
                ),
                samples=0,
            )


if __name__ == "__main__":
    unittest.main()
