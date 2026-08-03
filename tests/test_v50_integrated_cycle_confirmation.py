from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from darwin_v50.integrated_cycle_calibration import (
    IntegratedCalibrationReport,
    bootstrap_integrated_calibration_metrics,
    evaluate_integrated_calibration_world,
    integrated_calibration_criteria,
)
from darwin_v50.integrated_cycle_confirmation import (
    INTEGRATED_CONFIRMATION_FINAL_SEEDS,
    INTEGRATED_CONFIRMATION_TEST_SEEDS,
    IntegratedCycleConfirmationReport,
    record_integrated_cycle_confirmation,
    run_integrated_cycle_confirmation,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError


class IntegratedCycleConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engineering_world = evaluate_integrated_calibration_world(
            INTEGRATED_CONFIRMATION_TEST_SEEDS[0]
        )
        cls.synthetic_seeds = tuple(range(60000, 60064))
        cls.synthetic_report = IntegratedCalibrationReport(
            seeds=cls.synthetic_seeds,
            worlds=tuple(
                replace(cls.engineering_world, seed=seed)
                for seed in cls.synthetic_seeds
            ),
        )

    def _confirmation(
        self,
        report: IntegratedCalibrationReport,
    ) -> IntegratedCycleConfirmationReport:
        metrics = bootstrap_integrated_calibration_metrics(
            report,
            seed=60700,
            samples=100,
        )
        return IntegratedCycleConfirmationReport(
            final_seeds=report.seeds,
            bootstrap_seed=60700,
            bootstrap_samples=100,
            report=report,
            metrics=metrics,
            criteria=integrated_calibration_criteria(report, metrics),
        )

    def test_confirmation_reuses_calibration_conjunction_exactly(self) -> None:
        confirmation = self._confirmation(self.synthetic_report)
        self.assertTrue(confirmation.passes_regression_criteria)
        record = confirmation.to_dict()
        self.assertEqual(record["decision"], "passed_locally")
        self.assertTrue(record["h50_l16_registered"])
        self.assertEqual(record["world_count"], 64)
        self.assertEqual(record["task_count"], 1536)
        self.assertEqual(len(record["criteria"]), 17)

    def test_any_failed_criterion_refutes_and_kernel_does_not_promote(self) -> None:
        damaged_world = replace(
            self.engineering_world,
            seed=self.synthetic_seeds[0],
            environment_replay_exact_rate=0.0,
        )
        damaged_report = IntegratedCalibrationReport(
            seeds=self.synthetic_seeds,
            worlds=(damaged_world,) + self.synthetic_report.worlds[1:],
        )
        confirmation = self._confirmation(damaged_report)
        self.assertFalse(confirmation.passes_regression_criteria)
        self.assertEqual(confirmation.to_dict()["decision"], "refuted")
        self.assertFalse(confirmation.to_dict()["h50_l16_registered"])
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "confirmation.db"
            with DarwinKernelV50.open(database) as kernel:
                observation = record_integrated_cycle_confirmation(
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
            database = Path(directory) / "confirmation.db"
            with DarwinKernelV50.open(database) as kernel:
                observation = record_integrated_cycle_confirmation(
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
            set(INTEGRATED_CONFIRMATION_TEST_SEEDS).isdisjoint(
                INTEGRATED_CONFIRMATION_FINAL_SEEDS
            )
        )
        with self.assertRaises(ValidationError):
            run_integrated_cycle_confirmation(final_seeds=())
        with self.assertRaises(ValidationError):
            run_integrated_cycle_confirmation(
                final_seeds=INTEGRATED_CONFIRMATION_TEST_SEEDS
            )


if __name__ == "__main__":
    unittest.main()
