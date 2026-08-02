from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.temporal_evaluation import (
    PrequentialForecastRecord,
    brier_score,
    record_temporal_result,
    report_with_post_improvement,
    run_temporal_suite,
)
from darwin_v50.temporal_lab import (
    AdaptiveBernoulliForecaster,
    BinaryForecast,
    BinaryStreamObservation,
    RegimeShiftBernoulliStream,
    StationaryBernoulliForecaster,
    TwoWindowMeanShiftDetector,
)


class TemporalStreamTests(unittest.TestCase):
    def test_stream_changes_only_at_registered_boundary(self) -> None:
        stream = RegimeShiftBernoulliStream(8001)
        observations = tuple(
            stream.next_observation() for _ in range(2000)
        )

        pre_rate = sum(item.outcome for item in observations[:1000]) / 1000
        post_rate = sum(item.outcome for item in observations[1000:]) / 1000
        self.assertGreater(pre_rate, 0.80)
        self.assertLess(pre_rate, 0.90)
        self.assertGreater(post_rate, 0.10)
        self.assertLess(post_rate, 0.20)
        self.assertEqual(observations[999].index, 1000)
        self.assertEqual(observations[1000].index, 1001)
        with self.assertRaises(StopIteration):
            stream.next_observation()

    def test_forecast_is_made_from_prior_observations_only(self) -> None:
        forecaster = StationaryBernoulliForecaster()
        first = forecaster.predict()
        forecaster.observe(BinaryStreamObservation(1, True))
        second = forecaster.predict()

        self.assertEqual(first, BinaryForecast(0.5, 0, 0, 0))
        self.assertEqual(second, BinaryForecast(2 / 3, 1, 1, 0))
        with self.assertRaises(ValidationError):
            forecaster.observe(BinaryStreamObservation(3, False))

    def test_brier_score_rejects_empty_and_unbounded_forecasts(self) -> None:
        with self.assertRaises(ValidationError):
            brier_score((), "adaptive_probability")
        invalid = PrequentialForecastRecord(
            index=1,
            outcome=True,
            stationary_probability=0.5,
            adaptive_probability=1.1,
            fixed_window_probability=0.5,
            oracle_probability=0.5,
        )
        with self.assertRaises(ValidationError):
            brier_score((invalid,), "adaptive_probability")


class MeanShiftDetectorTests(unittest.TestCase):
    def test_constant_history_does_not_trigger(self) -> None:
        detector = TwoWindowMeanShiftDetector(
            window_size=64,
            false_alarm_delta=1e-6,
        )

        detections = tuple(
            detector.observe(BinaryStreamObservation(index, True))[0]
            for index in range(1, 257)
        )

        self.assertTrue(all(event is None for event in detections))

    def test_maximal_constructed_shift_triggers_at_first_full_window(self) -> None:
        detector = TwoWindowMeanShiftDetector(
            window_size=64,
            false_alarm_delta=1e-6,
        )
        result = None
        recent = ()
        for index in range(1, 129):
            result, recent = detector.observe(
                BinaryStreamObservation(index, index <= 64)
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.detection_index, 128)
        self.assertEqual(result.estimated_boundary_index, 65)
        self.assertEqual(result.earlier_mean, 1.0)
        self.assertEqual(result.recent_mean, 0.0)
        self.assertEqual(tuple(item.index for item in recent), tuple(range(65, 129)))


class AdaptiveTemporalMemoryTests(unittest.TestCase):
    @staticmethod
    def _sequence() -> tuple[BinaryStreamObservation, ...]:
        return tuple(
            BinaryStreamObservation(index, index <= 64)
            for index in range(1, 181)
        )

    def test_detection_resets_working_memory_without_erasing_archive(self) -> None:
        model = AdaptiveBernoulliForecaster()
        detection = None
        for observation in self._sequence()[:128]:
            detection = model.observe(observation)

        self.assertIsNotNone(detection)
        self.assertEqual(len(model.archive), 128)
        self.assertEqual(len(model.working_memory), 64)
        self.assertEqual(model.working_memory[0].index, 65)
        self.assertEqual(model.archive[0].index, 1)

    def test_snapshot_round_trip_preserves_future_behavior(self) -> None:
        sequence = self._sequence()
        original = AdaptiveBernoulliForecaster()
        for observation in sequence[:100]:
            original.observe(observation)
        restored = AdaptiveBernoulliForecaster.from_snapshot(
            original.to_snapshot()
        )

        self.assertEqual(restored.to_snapshot(), original.to_snapshot())
        for observation in sequence[100:]:
            self.assertEqual(restored.predict(), original.predict())
            self.assertEqual(
                restored.observe(observation),
                original.observe(observation),
            )

        self.assertEqual(restored.to_snapshot(), original.to_snapshot())

    def test_snapshot_rejects_non_suffix_working_memory(self) -> None:
        model = AdaptiveBernoulliForecaster()
        for index in range(1, 20):
            model.observe(BinaryStreamObservation(index, bool(index % 2)))
        parsed = json.loads(model.to_snapshot())
        parsed["working_indices"] = parsed["working_indices"][:-1]

        with self.assertRaises(ValidationError):
            AdaptiveBernoulliForecaster.from_snapshot(
                json.dumps(parsed)
            )

    def test_snapshot_rejects_inconsistent_detection(self) -> None:
        model = AdaptiveBernoulliForecaster()
        for observation in self._sequence()[:128]:
            model.observe(observation)
        parsed = json.loads(model.to_snapshot())
        parsed["detections"][0]["absolute_mean_gap"] = 0.5

        with self.assertRaises(ValidationError):
            AdaptiveBernoulliForecaster.from_snapshot(
                json.dumps(parsed)
            )

    def test_archive_indices_cannot_skip_or_replay(self) -> None:
        model = AdaptiveBernoulliForecaster()
        model.observe(BinaryStreamObservation(1, True))
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(1, True))
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(3, False))

    def test_invalid_detector_configuration_is_rejected_cleanly(self) -> None:
        with self.assertRaises(ValidationError):
            AdaptiveBernoulliForecaster(detector_window_size="64")  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            AdaptiveBernoulliForecaster(false_alarm_delta=float("nan"))
        with self.assertRaises(ValidationError):
            AdaptiveBernoulliForecaster(maximum_working_memory=32)


class TemporalSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_temporal_suite()

    def test_registered_temporal_criteria_hold(self) -> None:
        report = self.report
        self.assertEqual(report.world_count, 20)
        self.assertGreaterEqual(report.detection_rate, 0.95)
        self.assertLessEqual(report.false_alarm_world_rate, 0.05)
        self.assertLessEqual(report.maximum_detection_delay, 128)
        self.assertGreaterEqual(report.post_change_brier_improvement, 0.10)
        self.assertGreaterEqual(report.total_brier_improvement, 0.04)
        self.assertLessEqual(report.pre_change_brier_degradation, 0.01)
        self.assertEqual(report.archive_retention_rate, 1.0)
        self.assertEqual(report.snapshot_round_trip_rate, 1.0)
        self.assertTrue(report.passes_regression_criteria())
        self.assertEqual(
            report.evidence_level,
            "E1_LOCAL_AUTOMATED_EVALUATOR",
        )

    def test_fixed_window_baseline_is_reported_even_when_it_is_better(self) -> None:
        report = self.report
        self.assertLess(
            report.fixed_window_post_brier,
            report.adaptive_post_brier,
        )
        self.assertLess(
            report.fixed_window_total_brier,
            report.adaptive_total_brier,
        )

    def test_suite_is_deterministic(self) -> None:
        arguments = {
            "seeds": range(8200, 8203),
            "change_index": 301,
            "total_observations": 600,
            "detector_window_size": 32,
            "false_alarm_delta": 1e-4,
            "maximum_working_memory": 128,
        }
        first = run_temporal_suite(**arguments)
        second = run_temporal_suite(**arguments)
        self.assertEqual(
            first.to_dict(include_worlds=True),
            second.to_dict(include_worlds=True),
        )

    def test_suite_rejects_empty_or_duplicate_seed_sets(self) -> None:
        with self.assertRaises(ValidationError):
            run_temporal_suite(seeds=())
        with self.assertRaises(ValidationError):
            run_temporal_suite(
                seeds=(8300, 8300),
                change_index=20,
                total_observations=40,
                detector_window_size=8,
                maximum_working_memory=8,
            )

    def test_result_is_recorded_as_unauthenticated_local_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "temporal.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_temporal_result(kernel, self.report)
                observation = next(
                    event
                    for event in kernel.goal_events(result.goal.goal_id)
                    if event.kind == "observation.recorded"
                )

        self.assertTrue(result.accepted)
        self.assertTrue(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertFalse(observation.payload["authenticated"])

    def test_failed_improvement_cannot_create_success(self) -> None:
        failed = report_with_post_improvement(self.report, 0.01)
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "failed-temporal.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_temporal_result(kernel, failed)
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
