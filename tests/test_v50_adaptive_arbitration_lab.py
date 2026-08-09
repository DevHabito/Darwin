from __future__ import annotations

import json
import unittest

import darwin_v50.adaptive_arbitration_evaluation as evaluation
from darwin_v50.adaptive_arbitration_lab import (
    AdaptiveMemoryArbitrator,
    AgeBinnedExpertWeights,
    ArbitrationBernoulliStream,
    ArbitrationSchedule,
    ExpertWeightDecision,
    TOTAL_ARBITRATION_OBSERVATIONS,
    arbitration_bin_for_age,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.store import SQLiteEventStore
from darwin_v50.temporal_lab import BinaryStreamObservation


class ArbitrationScheduleTests(unittest.TestCase):
    def test_four_families_are_deterministic_balanced_and_complete(self) -> None:
        schedules = tuple(
            ArbitrationSchedule.from_seed(seed)
            for seed in range(13000, 13004)
        )
        self.assertEqual(
            tuple(item.family for item in schedules),
            (
                "exact_recurrence",
                "shifted_recurrence",
                "returning_novelty",
                "late_novelty",
            ),
        )
        for seed, schedule in zip(
            range(13000, 13004),
            schedules,
            strict=True,
        ):
            self.assertEqual(schedule, ArbitrationSchedule.from_seed(seed))
            self.assertEqual(sum(schedule.durations), 4200)
            self.assertEqual(len(schedule.phase_start_indices), 7)
            self.assertGreaterEqual(len(schedule.recurrence_indices), 4)
        self.assertEqual(len(schedules[0].novelty_indices), 0)
        self.assertEqual(len(schedules[2].novelty_indices), 1)
        self.assertEqual(len(schedules[3].novelty_indices), 1)

    def test_shifted_identity_changes_without_crossing_other_identity(self) -> None:
        schedule = ArbitrationSchedule.from_seed(13001)
        a_values = tuple(
            probability
            for label, probability in zip(
                schedule.labels,
                schedule.probabilities,
                strict=True,
            )
            if label == "A"
        )
        self.assertLessEqual(max(a_values) - min(a_values), 0.08 + 1e-12)
        self.assertGreater(len(set(a_values)), 1)
        self.assertTrue(
            all(
                abs(left - right) >= 0.25
                for left, right in zip(
                    schedule.probabilities[:-1],
                    schedule.probabilities[1:],
                    strict=True,
                )
            )
        )

    def test_stream_is_exhaustible_and_contains_only_hidden_outcomes(self) -> None:
        stream = ArbitrationBernoulliStream(13002)
        observations = tuple(
            stream.next_observation()
            for _ in range(TOTAL_ARBITRATION_OBSERVATIONS)
        )
        self.assertEqual(observations[0].index, 1)
        self.assertEqual(observations[-1].index, 4200)
        self.assertTrue(
            all(isinstance(item.outcome, bool) for item in observations)
        )
        with self.assertRaises(StopIteration):
            stream.next_observation()


class ExpertWeightTests(unittest.TestCase):
    def test_weight_changes_only_after_observed_loss(self) -> None:
        weights = AgeBinnedExpertWeights(
            learning_rate=8.0,
            loss_discount=1.0,
        )
        first = weights.predict(
            base_probability=0.8,
            memory_probability=0.2,
            active_age=1,
        )
        repeated = weights.predict(
            base_probability=0.8,
            memory_probability=0.2,
            active_age=1,
        )
        self.assertEqual(first.memory_weight, 0.25)
        self.assertEqual(repeated, first)
        weights.observe(first, False)
        after = weights.predict(
            base_probability=0.8,
            memory_probability=0.2,
            active_age=1,
        )
        self.assertGreater(after.memory_weight, first.memory_weight)

    def test_age_bins_keep_independent_losses(self) -> None:
        weights = AgeBinnedExpertWeights(
            learning_rate=8.0,
            loss_discount=0.99,
        )
        first = weights.predict(
            base_probability=0.8,
            memory_probability=0.2,
            active_age=1,
        )
        weights.observe(first, False)
        self.assertNotEqual(weights.memory_weight(1), 0.25)
        self.assertEqual(weights.memory_weight(17), 0.25)
        self.assertEqual(arbitration_bin_for_age(16), 0)
        self.assertEqual(arbitration_bin_for_age(17), 1)
        self.assertEqual(arbitration_bin_for_age(129), 4)

    def test_extreme_cumulative_loss_is_numerically_bounded(self) -> None:
        weights = AgeBinnedExpertWeights(
            learning_rate=32.0,
            loss_discount=1.0,
        )
        for _ in range(2000):
            decision = weights.predict(
                base_probability=0.99,
                memory_probability=0.01,
                active_age=1,
            )
            weights.observe(decision, False)
        final = weights.predict(
            base_probability=0.99,
            memory_probability=0.01,
            active_age=1,
        )
        self.assertGreaterEqual(final.memory_weight, 0.0)
        self.assertLessEqual(final.memory_weight, 1.0)
        self.assertGreater(final.probability, 0.0)
        self.assertLess(final.probability, 1.0)

    def test_invalid_configuration_and_age_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            AgeBinnedExpertWeights(learning_rate=True)
        with self.assertRaises(ValidationError):
            AgeBinnedExpertWeights(loss_discount=0.0)
        with self.assertRaises(ValidationError):
            arbitration_bin_for_age(0)


class AdaptiveMemoryArbitratorTests(unittest.TestCase):
    def test_sleeping_memory_is_exactly_the_base_and_does_not_update(self) -> None:
        model = AdaptiveMemoryArbitrator()
        for index in range(1, 257):
            forecast = model.predict()
            self.assertIsNone(forecast.memory_probability)
            self.assertEqual(forecast.probability, forecast.base_probability)
            model.observe(BinaryStreamObservation(index, True))
        self.assertEqual(model.base_losses, (0.0,) * 5)
        self.assertEqual(model.memory_losses, (0.0,) * 5)

    def test_predict_must_precede_observe(self) -> None:
        model = AdaptiveMemoryArbitrator()
        with self.assertRaises(ValidationError):
            model.observe(BinaryStreamObservation(1, True))

    def test_snapshot_round_trip_preserves_pending_and_future(self) -> None:
        stream = ArbitrationBernoulliStream(13201)
        original = AdaptiveMemoryArbitrator(
            learning_rate=8.0,
            loss_discount=0.99,
        )
        for _ in range(1800):
            original.predict()
            original.observe(stream.next_observation())
        pending = original.predict()
        snapshot = original.to_snapshot()
        restored = AdaptiveMemoryArbitrator.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.predict(), pending)
        for _ in range(8):
            observation = stream.next_observation()
            self.assertEqual(restored.predict(), original.predict())
            restored.observe(observation)
            original.observe(observation)
        self.assertEqual(restored.to_snapshot(), original.to_snapshot())

    def test_snapshot_rejects_weight_state_tampering(self) -> None:
        model = AdaptiveMemoryArbitrator()
        for index in range(1, 300):
            model.predict()
            model.observe(BinaryStreamObservation(index, index % 3 == 0))
        parsed = json.loads(model.to_snapshot())
        parsed["base_losses"][0] = 10.0
        with self.assertRaises(ValidationError):
            AdaptiveMemoryArbitrator.from_snapshot(json.dumps(parsed))


class ArbitrationEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = evaluation.run_arbitration_suite(
            development_seeds=(13000, 13001, 13002, 13003),
            final_seeds=(13100, 13101, 13102, 13103),
            fixed_window_candidates=(32,),
            learning_rate_candidates=(8.0,),
            loss_discount_candidates=(0.99,),
        )

    def test_optimized_selection_matches_public_model_exactly(self) -> None:
        seed = 13200
        trace = evaluation._expert_trace(seed)
        optimized = evaluation._adaptive_probabilities(
            trace,
            learning_rate=8.0,
            loss_discount=0.99,
        )
        stream = ArbitrationBernoulliStream(seed)
        model = AdaptiveMemoryArbitrator(
            learning_rate=8.0,
            loss_discount=0.99,
        )
        public: list[float] = []
        for _ in range(TOTAL_ARBITRATION_OBSERVATIONS):
            public.append(model.predict().probability)
            model.observe(stream.next_observation())
        self.assertEqual(optimized, tuple(public))

    def test_small_suite_is_balanced_disjoint_and_persistent(self) -> None:
        self.assertEqual(self.report.final_world_count, 4)
        self.assertEqual(
            set(self.report.family_counts.values()),
            {1},
        )
        self.assertFalse(
            set(self.report.development.seeds)
            & set(self.report.final_seeds)
        )
        self.assertEqual(self.report.unique_schedule_count, 4)
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)

    def test_seed_overlap_and_invalid_grid_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation.run_arbitration_suite(
                development_seeds=(13300,),
                final_seeds=(13300,),
                fixed_window_candidates=(32,),
                learning_rate_candidates=(8.0,),
                loss_discount_candidates=(0.99,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_arbitration_configuration(
                seeds=(13301,),
                fixed_window_candidates=(32,),
                learning_rate_candidates=(8.0, 8.0),
                loss_discount_candidates=(0.99,),
            )

    def test_regression_criteria_are_conjunctive(self) -> None:
        passing = evaluation.report_with_arbitration_metrics(
            self.report,
            total_improvement_vs_fixed=0.003,
            world_win_rate_vs_fixed=0.70,
            total_improvement_vs_base=0.001,
            recurrence_improvement_vs_base=0.001,
            recurrence_improvement_vs_fixed_mix=0.002,
            exact_recurrence_improvement_vs_base=0.001,
            shifted_recurrence_degradation_vs_base=0.0005,
            novelty_degradation_vs_base=0.0005,
            active_regret_vs_best_fixed_expert=0.004,
            correct_recurrence_retrieval_coverage=0.90,
            retrieval_precision=0.95,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            evaluation.report_with_arbitration_metrics(
                passing,
                total_improvement_vs_base=-1e-9,
            ).passes_regression_criteria()
        )

    def test_kernel_does_not_promote_a_failed_conjunction(self) -> None:
        failing = evaluation.report_with_arbitration_metrics(
            self.report,
            recurrence_improvement_vs_base=-1.0,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = evaluation.record_arbitration_result(kernel, failing)
        self.assertEqual(
            result.goal.status,
            GoalStatus.WAITING_OBSERVATION,
        )
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
