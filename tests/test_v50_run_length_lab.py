from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from statistics import fmean
import tempfile
import unittest

from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.run_length_evaluation import (
    record_run_length_result,
    run_run_length_suite,
    select_run_length_configuration,
)
from darwin_v50.run_length_lab import (
    PrunedBayesianRunLengthForecaster,
    RunLengthHypothesis,
    TOTAL_VARIABLE_OBSERVATIONS,
    VariableRegimeBernoulliStream,
    VariableRegimeSchedule,
)
from darwin_v50.temporal_lab import (
    BinaryStreamObservation,
    FixedWindowBernoulliForecaster,
)


class VariableScheduleTests(unittest.TestCase):
    def test_schedule_is_deterministic_bounded_and_recurrent(self) -> None:
        first = VariableRegimeSchedule.from_seed(9600)
        second = VariableRegimeSchedule.from_seed(9600)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first.first_duration, 450)
        self.assertLessEqual(first.first_duration, 600)
        self.assertLess(first.gradual_end_index, TOTAL_VARIABLE_OBSERVATIONS)
        self.assertEqual(
            first.probability_at(first.recurrence_index),
            first.first_probability,
        )
        self.assertAlmostEqual(
            first.probability_at(first.gradual_end_index),
            first.opposite_probability,
        )
        self.assertEqual(
            first.probability_at(first.gradual_end_index + 1),
            first.opposite_probability,
        )

    def test_different_seeds_produce_multiple_hidden_schedules(self) -> None:
        schedules = {
            VariableRegimeSchedule.from_seed(seed)
            for seed in range(9600, 9610)
        }

        self.assertGreaterEqual(len(schedules), 8)

    def test_stream_is_deterministic_and_exhaustible(self) -> None:
        first = VariableRegimeBernoulliStream(9610)
        second = VariableRegimeBernoulliStream(9610)
        first_observations = tuple(
            first.next_observation()
            for _ in range(TOTAL_VARIABLE_OBSERVATIONS)
        )
        second_observations = tuple(
            second.next_observation()
            for _ in range(TOTAL_VARIABLE_OBSERVATIONS)
        )

        self.assertEqual(first_observations, second_observations)
        self.assertEqual(first_observations[0].index, 1)
        self.assertEqual(first_observations[-1].index, 3000)
        with self.assertRaises(StopIteration):
            first.next_observation()


class PrunedRunLengthModelTests(unittest.TestCase):
    @staticmethod
    def _sequence() -> tuple[BinaryStreamObservation, ...]:
        return tuple(
            BinaryStreamObservation(index, index <= 150)
            for index in range(1, 301)
        )

    def test_posterior_is_normalized_bounded_and_prequential(self) -> None:
        model = PrunedBayesianRunLengthForecaster(
            expected_duration=100,
            maximum_hypotheses=16,
        )
        initial = model.predict()
        for observation in self._sequence():
            model.observe(observation)

        final = model.predict()
        self.assertEqual(initial.probability, 0.5)
        self.assertLessEqual(len(model.hypotheses), 16)
        self.assertAlmostEqual(
            sum(item.mass for item in model.hypotheses),
            1.0,
        )
        self.assertLess(final.probability, 0.2)
        self.assertEqual(len(model.archive), 300)

    def test_snapshot_round_trip_preserves_future_behavior(self) -> None:
        sequence = self._sequence()
        original = PrunedBayesianRunLengthForecaster(
            expected_duration=100,
            maximum_hypotheses=16,
        )
        for observation in sequence[:180]:
            original.observe(observation)
        restored = PrunedBayesianRunLengthForecaster.from_snapshot(
            original.to_snapshot()
        )

        self.assertEqual(restored.to_snapshot(), original.to_snapshot())
        for observation in sequence[180:]:
            self.assertEqual(restored.predict(), original.predict())
            restored.observe(observation)
            original.observe(observation)
        self.assertEqual(restored.to_snapshot(), original.to_snapshot())

    def test_snapshot_rejects_posterior_inconsistent_with_archive(self) -> None:
        model = PrunedBayesianRunLengthForecaster(
            expected_duration=100,
            maximum_hypotheses=16,
        )
        for observation in self._sequence()[:80]:
            model.observe(observation)
        parsed = json.loads(model.to_snapshot())
        parsed["hypotheses"][0]["alpha"] += 1.0

        with self.assertRaises(ValidationError):
            PrunedBayesianRunLengthForecaster.from_snapshot(
                json.dumps(parsed)
            )

    def test_invalid_state_and_configuration_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            PrunedBayesianRunLengthForecaster(expected_duration=1)
        with self.assertRaises(ValidationError):
            PrunedBayesianRunLengthForecaster(maximum_hypotheses=1)
        with self.assertRaises(ValidationError):
            RunLengthHypothesis(0, 1.0, 1.0, -0.1)
        model = PrunedBayesianRunLengthForecaster()
        model.observe(BinaryStreamObservation(1, True))
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(1, False))
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(3, False))


class RunLengthEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_run_length_suite(
            development_seeds=(9700, 9701),
            final_seeds=(9800, 9801),
            fixed_window_candidates=(32, 64),
            expected_duration_candidates=(100, 200),
            maximum_hypotheses_candidates=(8, 16),
        )

    def test_selection_and_final_sets_are_disjoint(self) -> None:
        report = self.report

        self.assertTrue(
            set(report.development.seeds).isdisjoint(report.final_seeds)
        )
        self.assertEqual(report.final_world_count, 2)
        self.assertEqual(report.unique_schedule_count, 2)
        self.assertEqual(report.archive_retention_rate, 1.0)
        self.assertEqual(report.snapshot_round_trip_rate, 1.0)
        self.assertIn("precedes its outcome", report.held_out_definition)

    def test_selection_is_deterministic(self) -> None:
        arguments = {
            "seeds": (9702,),
            "fixed_window_candidates": (32, 64),
            "expected_duration_candidates": (100, 200),
            "maximum_hypotheses_candidates": (8, 16),
        }
        first = select_run_length_configuration(**arguments)
        second = select_run_length_configuration(**arguments)

        self.assertEqual(first.to_dict(), second.to_dict())

    def test_optimized_score_matches_public_model_execution(self) -> None:
        seed = 9703
        selection = select_run_length_configuration(
            seeds=(seed,),
            fixed_window_candidates=(32,),
            expected_duration_candidates=(100,),
            maximum_hypotheses_candidates=(8,),
        )
        stream = VariableRegimeBernoulliStream(seed)
        model = PrunedBayesianRunLengthForecaster(
            expected_duration=100,
            maximum_hypotheses=8,
        )
        losses: list[float] = []
        for _ in range(TOTAL_VARIABLE_OBSERVATIONS):
            forecast = model.predict()
            observation = stream.next_observation()
            losses.append(
                (
                    forecast.probability
                    - float(observation.outcome)
                )
                ** 2
            )
            model.observe(observation)

        self.assertAlmostEqual(
            selection.run_length_scores[0].mean_total_brier,
            fmean(losses),
            places=15,
        )
        fixed_stream = VariableRegimeBernoulliStream(seed)
        fixed = FixedWindowBernoulliForecaster(32)
        fixed_losses: list[float] = []
        for _ in range(TOTAL_VARIABLE_OBSERVATIONS):
            probability = fixed.predict().probability
            observation = fixed_stream.next_observation()
            fixed_losses.append(
                (probability - float(observation.outcome)) ** 2
            )
            fixed.observe(observation)
        self.assertAlmostEqual(
            selection.fixed_scores[0].mean_total_brier,
            fmean(fixed_losses),
            places=15,
        )

    def test_seed_leakage_and_invalid_grids_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            run_run_length_suite(
                development_seeds=(9900,),
                final_seeds=(9900,),
                fixed_window_candidates=(32,),
                expected_duration_candidates=(100,),
                maximum_hypotheses_candidates=(8,),
            )
        with self.assertRaises(ValidationError):
            select_run_length_configuration(
                seeds=(9901,),
                fixed_window_candidates=(64, 32),
                expected_duration_candidates=(100,),
                maximum_hypotheses_candidates=(8,),
            )

    def test_registered_criteria_are_conjunctive(self) -> None:
        passing = replace(
            self.report,
            total_improvement_vs_fixed=0.002,
            world_win_rate_vs_fixed=0.65,
            abrupt_improvement_vs_fixed=0.0,
            recurrence_improvement_vs_fixed=0.0,
            gradual_degradation_vs_fixed=0.003,
            total_improvement_vs_stationary=0.05,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        failing = replace(passing, recurrence_improvement_vs_fixed=-1e-9)

        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(failing.passes_regression_criteria())

    def test_kernel_records_only_the_full_conjunction_as_success(self) -> None:
        passing = replace(
            self.report,
            total_improvement_vs_fixed=0.01,
            world_win_rate_vs_fixed=1.0,
            abrupt_improvement_vs_fixed=0.01,
            recurrence_improvement_vs_fixed=0.01,
            gradual_degradation_vs_fixed=0.0,
            total_improvement_vs_stationary=0.10,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        failed = replace(passing, world_win_rate_vs_fixed=0.1)
        with tempfile.TemporaryDirectory() as temporary_directory:
            passing_database = Path(temporary_directory) / "passing.db"
            failed_database = Path(temporary_directory) / "failed.db"
            with DarwinKernelV50.open(passing_database) as kernel:
                passing_result = record_run_length_result(kernel, passing)
                observation = next(
                    event
                    for event in kernel.goal_events(
                        passing_result.goal.goal_id
                    )
                    if event.kind == "observation.recorded"
                )
            with DarwinKernelV50.open(failed_database) as kernel:
                failed_result = record_run_length_result(kernel, failed)
                success_events = kernel.store.count_events(
                    goal_id=failed_result.goal.goal_id,
                    kind="goal.succeeded",
                )

        self.assertEqual(passing_result.goal.status, GoalStatus.SUCCEEDED)
        self.assertFalse(observation.payload["authenticated"])
        self.assertEqual(
            failed_result.goal.status,
            GoalStatus.WAITING_OBSERVATION,
        )
        self.assertEqual(success_events, 0)


if __name__ == "__main__":
    unittest.main()
