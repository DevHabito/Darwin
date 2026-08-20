from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.online_alignment_calibration import (
    OnlineAlignmentCalibrationReport,
    bootstrap_online_alignment_calibration_metrics,
    online_alignment_calibration_criteria,
)
from darwin_v50.online_alignment_confirmation import (
    ONLINE_ALIGNMENT_CONFIRMATION_FINAL_SEEDS,
    ONLINE_ALIGNMENT_CONFIRMATION_TEST_SEEDS,
    OnlineAlignmentConfirmationReport,
    record_online_alignment_confirmation,
    run_online_alignment_confirmation,
)
from darwin_v50.online_alignment_evaluation import (
    evaluate_online_alignment_world,
)


class OnlineAlignmentConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engineering_world = evaluate_online_alignment_world(
            ONLINE_ALIGNMENT_CONFIRMATION_TEST_SEEDS[0]
        )
        cls.synthetic_seeds = tuple(range(70000, 70064))
        cls.synthetic_report = OnlineAlignmentCalibrationReport(
            seeds=cls.synthetic_seeds,
            worlds=tuple(
                replace(cls.engineering_world, seed=seed)
                for seed in cls.synthetic_seeds
            ),
        )

    def _confirmation(
        self,
        report: OnlineAlignmentCalibrationReport,
    ) -> OnlineAlignmentConfirmationReport:
        metrics = bootstrap_online_alignment_calibration_metrics(
            report,
            seed=70700,
            samples=100,
        )
        return OnlineAlignmentConfirmationReport(
            final_seeds=report.seeds,
            bootstrap_seed=70700,
            bootstrap_samples=100,
            report=report,
            metrics=metrics,
            criteria=online_alignment_calibration_criteria(report, metrics),
        )

    def test_confirmation_reuses_calibration_conjunction_exactly(self) -> None:
        confirmation = self._confirmation(self.synthetic_report)
        self.assertTrue(confirmation.passes_regression_criteria)
        record = confirmation.to_dict()
        self.assertEqual(record["decision"], "passed_locally")
        self.assertTrue(record["h50_l17_registered"])
        self.assertEqual(record["world_count"], 64)
        self.assertEqual(record["task_count"], 1536)
        self.assertEqual(len(record["criteria"]), 20)

    def test_any_failed_criterion_refutes_and_kernel_does_not_promote(self) -> None:
        damaged_world = replace(
            self.engineering_world,
            seed=self.synthetic_seeds[0],
            tracker_snapshot_rate=0.0,
        )
        damaged_report = OnlineAlignmentCalibrationReport(
            seeds=self.synthetic_seeds,
            worlds=(damaged_world,) + self.synthetic_report.worlds[1:],
        )
        confirmation = self._confirmation(damaged_report)
        self.assertFalse(confirmation.passes_regression_criteria)
        self.assertEqual(confirmation.to_dict()["decision"], "refuted")
        self.assertFalse(confirmation.to_dict()["h50_l17_registered"])
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "online-alignment-confirmation.db"
            with DarwinKernelV50.open(database) as kernel:
                observation = record_online_alignment_confirmation(
                    kernel,
                    confirmation,
                )
                self.assertFalse(observation.condition_satisfied)
                self.assertEqual(
                    observation.goal.status,
                    GoalStatus.WAITING_OBSERVATION,
                )

    def test_passing_conjunction_is_accepted_by_local_kernel(self) -> None:
        confirmation = self._confirmation(self.synthetic_report)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "online-alignment-confirmation.db"
            with DarwinKernelV50.open(database) as kernel:
                observation = record_online_alignment_confirmation(
                    kernel,
                    confirmation,
                )
                self.assertTrue(observation.condition_satisfied)
                self.assertEqual(
                    observation.goal.status,
                    GoalStatus.SUCCEEDED,
                )

    def test_final_seed_partition_and_invalid_inputs_fail_closed(self) -> None:
        self.assertTrue(
            set(ONLINE_ALIGNMENT_CONFIRMATION_TEST_SEEDS).isdisjoint(
                ONLINE_ALIGNMENT_CONFIRMATION_FINAL_SEEDS
            )
        )
        with self.assertRaises(ValidationError):
            run_online_alignment_confirmation(final_seeds=())
        with self.assertRaises(ValidationError):
            run_online_alignment_confirmation(
                final_seeds=ONLINE_ALIGNMENT_CONFIRMATION_TEST_SEEDS
            )


if __name__ == "__main__":
    unittest.main()
