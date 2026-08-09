from __future__ import annotations

import json
import unittest

from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.regime_memory_evaluation import (
    record_regime_memory_result,
    report_with_regime_memory_metrics,
    run_regime_memory_suite,
)
from darwin_v50.regime_memory_lab import (
    RegimeMemoryBernoulliStream,
    RegimeMemorySchedule,
    RegimeRepositoryForecaster,
    TOTAL_REGIME_MEMORY_OBSERVATIONS,
)
from darwin_v50.store import SQLiteEventStore
from darwin_v50.temporal_lab import BinaryStreamObservation


def observations_from_runs(
    *runs: tuple[bool, int],
) -> tuple[BinaryStreamObservation, ...]:
    outcomes = tuple(
        outcome
        for outcome, count in runs
        for _ in range(count)
    )
    return tuple(
        BinaryStreamObservation(index=index, outcome=outcome)
        for index, outcome in enumerate(outcomes, start=1)
    )


class RegimeMemoryScheduleTests(unittest.TestCase):
    def test_schedule_is_deterministic_balanced_and_complete(self) -> None:
        recurring = RegimeMemorySchedule.from_seed(11000)
        novelty = RegimeMemorySchedule.from_seed(11001)
        self.assertEqual(recurring, RegimeMemorySchedule.from_seed(11000))
        self.assertEqual(recurring.family, "recurring")
        self.assertEqual(novelty.family, "novelty")
        self.assertEqual(sum(recurring.durations), 3000)
        self.assertEqual(
            recurring.labels,
            ("A", "B", "A", "B", "A"),
        )
        self.assertEqual(
            novelty.labels,
            ("A", "B", "A", "C", "B"),
        )
        self.assertEqual(len(recurring.recurrence_indices), 3)
        self.assertEqual(len(novelty.recurrence_indices), 2)
        self.assertEqual(len(novelty.novelty_indices), 1)

    def test_stream_hides_schedule_from_observations(self) -> None:
        stream = RegimeMemoryBernoulliStream(11002)
        observations = tuple(
            stream.next_observation()
            for _ in range(TOTAL_REGIME_MEMORY_OBSERVATIONS)
        )
        self.assertEqual(
            tuple(item.index for item in observations),
            tuple(range(1, 3001)),
        )
        self.assertTrue(
            all(isinstance(item.outcome, bool) for item in observations)
        )


class RegimeRepositoryForecasterTests(unittest.TestCase):
    def test_recurring_regime_is_retrieved_after_clean_confirmation(self) -> None:
        model = RegimeRepositoryForecaster(
            detector_window_size=32,
            false_alarm_delta=0.05,
            match_tolerance=0.15,
        )
        observations = observations_from_runs(
            (True, 256),
            (False, 256),
            (True, 256),
        )
        for observation in observations:
            model.predict()
            model.observe(observation)
        retrieved = tuple(
            item
            for item in model.transitions
            if item.retrieved_prototype_id is not None
        )
        self.assertTrue(retrieved)
        self.assertTrue(any(item.recent_mean > 0.90 for item in retrieved))
        self.assertTrue(
            all(
                item.decision_index - item.detection_index == 32
                for item in model.transitions
            )
        )

    def test_novel_regime_causes_abstention_not_retrieval(self) -> None:
        model = RegimeRepositoryForecaster(
            detector_window_size=32,
            false_alarm_delta=0.05,
            match_tolerance=0.15,
        )
        outcomes = (
            (True,) * 256
            + (False,) * 256
            + (True,) * 256
            + tuple(index % 2 == 0 for index in range(256))
        )
        for index, outcome in enumerate(outcomes, start=1):
            model.observe(
                BinaryStreamObservation(index=index, outcome=outcome)
            )
        self.assertTrue(model.transitions[-1].abstained)
        self.assertIsNone(model.transitions[-1].retrieved_prototype_id)
        self.assertAlmostEqual(model.transitions[-1].recent_mean, 0.5)

    def test_disabled_retrieval_is_exact_base_ablation(self) -> None:
        full = RegimeRepositoryForecaster(
            detector_window_size=32,
            false_alarm_delta=0.05,
            match_tolerance=0.15,
        )
        ablated = RegimeRepositoryForecaster(
            detector_window_size=32,
            false_alarm_delta=0.05,
            match_tolerance=0.15,
            retrieval_enabled=False,
        )
        observations = observations_from_runs(
            (True, 256),
            (False, 256),
            (True, 256),
        )
        full_differs_after_retrieval = False
        for observation in observations:
            full_forecast = full.predict()
            ablated_forecast = ablated.predict()
            self.assertEqual(
                full_forecast.base_probability,
                ablated_forecast.base_probability,
            )
            self.assertEqual(
                ablated_forecast.probability,
                ablated_forecast.base_probability,
            )
            full_differs_after_retrieval |= (
                full_forecast.probability
                != full_forecast.base_probability
            )
            full.observe(observation)
            ablated.observe(observation)
        self.assertTrue(full_differs_after_retrieval)

    def test_archive_is_complete_while_working_memory_is_bounded(self) -> None:
        stream = RegimeMemoryBernoulliStream(11003)
        model = RegimeRepositoryForecaster(maximum_working_memory=512)
        for _ in range(TOTAL_REGIME_MEMORY_OBSERVATIONS):
            model.observe(stream.next_observation())
        self.assertEqual(len(model.archive), 3000)
        self.assertLessEqual(len(model.working_memory), 512)

    def test_snapshot_round_trip_preserves_future_behavior(self) -> None:
        observations = observations_from_runs(
            (True, 256),
            (False, 256),
            (True, 192),
        )
        original = RegimeRepositoryForecaster(
            detector_window_size=32,
            false_alarm_delta=0.05,
            match_tolerance=0.15,
        )
        for observation in observations:
            original.observe(observation)
        snapshot = original.to_snapshot()
        restored = RegimeRepositoryForecaster.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.predict(), original.predict())
        for offset, outcome in enumerate(
            (False, True, True, False),
            start=len(observations) + 1,
        ):
            observation = BinaryStreamObservation(offset, outcome)
            self.assertEqual(restored.predict(), original.predict())
            restored.observe(observation)
            original.observe(observation)
        self.assertEqual(restored.to_snapshot(), original.to_snapshot())

    def test_snapshot_rejects_derived_state_tampering(self) -> None:
        model = RegimeRepositoryForecaster(
            detector_window_size=32,
            false_alarm_delta=0.05,
        )
        for observation in observations_from_runs(
            (True, 256),
            (False, 128),
        ):
            model.observe(observation)
        parsed = json.loads(model.to_snapshot())
        parsed["prototypes"][0]["successes"] += 1
        with self.assertRaises(ValidationError):
            RegimeRepositoryForecaster.from_snapshot(
                json.dumps(parsed)
            )

    def test_observations_must_be_strictly_causal_and_contiguous(self) -> None:
        model = RegimeRepositoryForecaster()
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(2, True))


class RegimeMemoryEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_regime_memory_suite(
            development_seeds=(11100, 11101),
            final_seeds=(11200, 11201),
            fixed_window_candidates=(32,),
            detector_window_candidates=(32,),
            false_alarm_delta_candidates=(0.05,),
            match_tolerance_candidates=(0.15,),
        )

    def test_small_suite_keeps_selection_and_final_disjoint(self) -> None:
        self.assertEqual(self.report.final_world_count, 2)
        self.assertEqual(self.report.recurring_world_count, 1)
        self.assertEqual(self.report.novelty_world_count, 1)
        self.assertFalse(
            set(self.report.development.seeds)
            & set(self.report.final_seeds)
        )
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)

    def test_final_seed_overlap_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            run_regime_memory_suite(
                development_seeds=(11300,),
                final_seeds=(11300,),
                fixed_window_candidates=(32,),
                detector_window_candidates=(32,),
                false_alarm_delta_candidates=(0.05,),
                match_tolerance_candidates=(0.15,),
            )

    def test_regression_decision_is_a_conjunction(self) -> None:
        passing = report_with_regime_memory_metrics(
            self.report,
            total_improvement_vs_fixed=0.003,
            world_win_rate_vs_fixed=0.70,
            recurrence_improvement_vs_ablation=0.002,
            recurrence_improvement_vs_fixed=0.003,
            correct_recurrence_retrieval_coverage=0.90,
            retrieval_precision=0.95,
            novelty_abstention_coverage=0.80,
            novelty_false_retrieval_rate=0.05,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            report_with_regime_memory_metrics(
                passing,
                retrieval_precision=0.89,
            ).passes_regression_criteria()
        )

    def test_kernel_records_failed_conjunction_without_promotion(self) -> None:
        failing = report_with_regime_memory_metrics(
            self.report,
            total_improvement_vs_fixed=-1.0,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = record_regime_memory_result(kernel, failing)
        self.assertEqual(
            result.goal.status,
            GoalStatus.WAITING_OBSERVATION,
        )
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
