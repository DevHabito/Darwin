from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from statistics import fmean
import tempfile
import unittest

from darwin_v50.drift_evaluation import (
    record_multiscale_result,
    report_with_total_improvement,
    run_multiscale_suite,
    select_development_configuration,
)
from darwin_v50.drift_lab import (
    FixedShareMemoryForecaster,
    MultiphaseBernoulliStream,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.temporal_lab import BinaryStreamObservation
from darwin_v50.temporal_lab import FixedWindowBernoulliForecaster


class MultiphaseStreamTests(unittest.TestCase):
    def test_probability_schedule_has_registered_boundaries(self) -> None:
        probability = MultiphaseBernoulliStream.probability_at

        self.assertEqual(probability(1), 0.85)
        self.assertEqual(probability(600), 0.85)
        self.assertEqual(probability(601), 0.15)
        self.assertEqual(probability(1200), 0.15)
        self.assertEqual(probability(1201), 0.85)
        self.assertEqual(probability(1800), 0.85)
        self.assertEqual(probability(1801), 0.85)
        self.assertAlmostEqual(probability(2400), 0.15)
        self.assertEqual(probability(2401), 0.15)
        self.assertEqual(probability(3000), 0.15)
        with self.assertRaises(ValidationError):
            probability(0)
        with self.assertRaises(ValidationError):
            probability(3001)

    def test_stream_is_deterministic_and_exhaustible(self) -> None:
        first = MultiphaseBernoulliStream(8700)
        second = MultiphaseBernoulliStream(8700)
        first_observations = tuple(
            first.next_observation() for _ in range(3000)
        )
        second_observations = tuple(
            second.next_observation() for _ in range(3000)
        )

        self.assertEqual(first_observations, second_observations)
        self.assertEqual(first_observations[0].index, 1)
        self.assertEqual(first_observations[-1].index, 3000)
        with self.assertRaises(StopIteration):
            first.next_observation()


class FixedShareMemoryTests(unittest.TestCase):
    @staticmethod
    def _sequence() -> tuple[BinaryStreamObservation, ...]:
        return tuple(
            BinaryStreamObservation(index, index <= 120)
            for index in range(1, 241)
        )

    def test_weights_are_normalized_and_change_only_after_outcome(self) -> None:
        model = FixedShareMemoryForecaster(
            window_sizes=(8, 16, 32),
            eta=4.0,
            share_rate=0.01,
        )
        before = model.predict()
        observation = BinaryStreamObservation(1, True)
        model.observe(observation)
        after = model.predict()

        self.assertEqual(before.probability, 0.5)
        self.assertEqual(len(before.expert_weights), 4)
        self.assertAlmostEqual(sum(after.expert_weights), 1.0)
        self.assertEqual(model.archive, (observation,))
        self.assertTrue(
            all(weight > 0.0 for weight in after.expert_weights)
        )

    def test_snapshot_round_trip_preserves_future_behavior(self) -> None:
        sequence = self._sequence()
        original = FixedShareMemoryForecaster(
            window_sizes=(8, 16, 32),
            eta=4.0,
            share_rate=0.01,
        )
        for observation in sequence[:150]:
            original.observe(observation)
        restored = FixedShareMemoryForecaster.from_snapshot(
            original.to_snapshot()
        )

        self.assertEqual(restored.to_snapshot(), original.to_snapshot())
        for observation in sequence[150:]:
            self.assertEqual(restored.predict(), original.predict())
            restored.observe(observation)
            original.observe(observation)
        self.assertEqual(restored.to_snapshot(), original.to_snapshot())

    def test_snapshot_rejects_weights_inconsistent_with_archive(self) -> None:
        model = FixedShareMemoryForecaster(
            window_sizes=(8, 16),
            eta=2.0,
            share_rate=0.01,
        )
        for observation in self._sequence()[:50]:
            model.observe(observation)
        parsed = json.loads(model.to_snapshot())
        parsed["weights"][0] += 0.01
        parsed["weights"][1] -= 0.01

        with self.assertRaises(ValidationError):
            FixedShareMemoryForecaster.from_snapshot(json.dumps(parsed))

    def test_replay_skip_and_invalid_configuration_fail_closed(self) -> None:
        model = FixedShareMemoryForecaster(window_sizes=(8, 16))
        model.observe(BinaryStreamObservation(1, True))
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(1, False))
        with self.assertRaises(ValidationError):
            FixedShareMemoryForecaster(window_sizes=(16, 8))
        with self.assertRaises(ValidationError):
            FixedShareMemoryForecaster(window_sizes=(8, 8))
        with self.assertRaises(ValidationError):
            FixedShareMemoryForecaster(eta=float("nan"))
        with self.assertRaises(ValidationError):
            FixedShareMemoryForecaster(share_rate=0.0)


class MultiscaleEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_multiscale_suite(
            development_seeds=(8800, 8801),
            final_seeds=(8900, 8901),
            fixed_window_candidates=(32, 64),
            eta_candidates=(1.0, 4.0),
            share_rate_candidates=(0.005, 0.01),
        )

    def test_selection_uses_only_development_worlds(self) -> None:
        selection = select_development_configuration(
            seeds=(8800, 8801),
            fixed_window_candidates=(32, 64),
            eta_candidates=(1.0, 4.0),
            share_rate_candidates=(0.005, 0.01),
        )

        self.assertEqual(selection.seeds, (8800, 8801))
        self.assertIn(selection.selected_fixed_window, (32, 64))
        self.assertIn(selection.selected_eta, (1.0, 4.0))
        self.assertIn(selection.selected_share_rate, (0.005, 0.01))
        self.assertNotIn(8900, selection.seeds)

    def test_optimized_selection_matches_forecaster_execution(self) -> None:
        seed = 8803
        selection = select_development_configuration(
            seeds=(seed,),
            fixed_window_candidates=(32, 64),
            eta_candidates=(2.0,),
            share_rate_candidates=(0.005,),
        )
        stream = MultiphaseBernoulliStream(seed)
        observations = tuple(
            stream.next_observation() for _ in range(3000)
        )

        def score(model) -> float:
            losses: list[float] = []
            for observation in observations:
                probability = model.predict().probability
                losses.append(
                    (probability - float(observation.outcome)) ** 2
                )
                model.observe(observation)
            return fmean(losses)

        multiscale_score = score(
            FixedShareMemoryForecaster(
                window_sizes=(32, 64),
                eta=2.0,
                share_rate=0.005,
            )
        )
        fixed_scores = {
            window: score(FixedWindowBernoulliForecaster(window))
            for window in (32, 64)
        }

        self.assertAlmostEqual(
            selection.multiscale_scores[0].mean_total_brier,
            multiscale_score,
            places=15,
        )
        for candidate in selection.fixed_window_scores:
            self.assertAlmostEqual(
                candidate.mean_total_brier,
                fixed_scores[candidate.window_size],
                places=15,
            )

    def test_final_worlds_are_prequential_persistent_and_disjoint(self) -> None:
        report = self.report

        self.assertEqual(report.final_seeds, (8900, 8901))
        self.assertEqual(report.final_world_count, 2)
        self.assertEqual(report.archive_retention_rate, 1.0)
        self.assertEqual(report.snapshot_round_trip_rate, 1.0)
        self.assertTrue(
            set(report.development.seeds).isdisjoint(report.final_seeds)
        )
        self.assertIn("before its outcome", report.held_out_definition)

    def test_suite_is_deterministic(self) -> None:
        arguments = {
            "development_seeds": (8802,),
            "final_seeds": (8902,),
            "fixed_window_candidates": (32, 64),
            "eta_candidates": (1.0,),
            "share_rate_candidates": (0.01,),
        }
        first = run_multiscale_suite(**arguments)
        second = run_multiscale_suite(**arguments)

        self.assertEqual(
            first.to_dict(include_worlds=True),
            second.to_dict(include_worlds=True),
        )

    def test_seed_leakage_and_duplicate_grids_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            run_multiscale_suite(
                development_seeds=(9000,),
                final_seeds=(9000,),
                fixed_window_candidates=(32,),
                eta_candidates=(1.0,),
                share_rate_candidates=(0.01,),
            )
        with self.assertRaises(ValidationError):
            select_development_configuration(
                seeds=(9001,),
                fixed_window_candidates=(32, 32),
                eta_candidates=(1.0,),
                share_rate_candidates=(0.01,),
            )
        with self.assertRaises(ValidationError):
            select_development_configuration(
                seeds=(9001,),
                fixed_window_candidates=(64, 32),
                eta_candidates=(1.0,),
                share_rate_candidates=(0.01,),
            )
        with self.assertRaises(ValidationError):
            select_development_configuration(
                seeds=(9001,),
                fixed_window_candidates=(32,),
                eta_candidates=(float("nan"),),
                share_rate_candidates=(0.01,),
            )

    def test_registered_criteria_are_not_relaxed_by_the_evaluator(self) -> None:
        passing = replace(
            self.report,
            total_brier_improvement_vs_fixed=0.002,
            world_win_rate_vs_fixed=0.65,
            recurrence_brier_improvement_vs_fixed=0.0,
            gradual_brier_degradation_vs_fixed=0.005,
            abrupt_recovery_brier_degradation_vs_fixed=0.01,
            total_brier_improvement_vs_stationary=0.05,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        failing = replace(passing, total_brier_improvement_vs_fixed=0.0019)

        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(failing.passes_regression_criteria())

    def test_kernel_records_local_result_without_authentication(self) -> None:
        passing = replace(
            self.report,
            total_brier_improvement_vs_fixed=0.01,
            world_win_rate_vs_fixed=1.0,
            recurrence_brier_improvement_vs_fixed=0.01,
            gradual_brier_degradation_vs_fixed=0.0,
            abrupt_recovery_brier_degradation_vs_fixed=0.0,
            total_brier_improvement_vs_stationary=0.10,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "multiscale.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_multiscale_result(kernel, passing)
                observation = next(
                    event
                    for event in kernel.goal_events(result.goal.goal_id)
                    if event.kind == "observation.recorded"
                )

        self.assertTrue(result.accepted)
        self.assertTrue(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertFalse(observation.payload["authenticated"])

    def test_failed_fixed_window_advantage_cannot_create_success(self) -> None:
        failed = report_with_total_improvement(self.report, -0.01)
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "failed-multiscale.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_multiscale_result(kernel, failed)
                success_events = kernel.store.count_events(
                    goal_id=result.goal.goal_id,
                    kind="goal.succeeded",
                )

        self.assertTrue(result.accepted)
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(success_events, 0)

    def test_passing_primary_metric_cannot_hide_another_failed_criterion(
        self,
    ) -> None:
        failed = replace(
            self.report,
            total_brier_improvement_vs_fixed=0.01,
            world_win_rate_vs_fixed=0.1,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "failed-conjunction.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_multiscale_result(kernel, failed)
                success_events = kernel.store.count_events(
                    goal_id=result.goal.goal_id,
                    kind="goal.succeeded",
                )

        self.assertTrue(result.accepted)
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(success_events, 0)


if __name__ == "__main__":
    unittest.main()
