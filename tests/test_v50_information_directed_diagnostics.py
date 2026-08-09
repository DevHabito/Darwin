from __future__ import annotations

import math
import unittest

import darwin_v50.information_directed_diagnostics as diagnostics
import darwin_v50.information_directed_evaluation as evaluation
from darwin_v50.models import ValidationError
from darwin_v50.online_posterior_evaluation import make_online_schedule


IDS_AUDIT_TEST_SEEDS = (25310, 25311, 25312, 25313)


class InformationDirectedFailureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = diagnostics.run_ids_failure_audit(
            IDS_AUDIT_TEST_SEEDS,
            bootstrap_resamples=128,
        )

    def test_diagnostic_trace_preserves_the_registered_candidate(self) -> None:
        seed = 25300
        schedule = make_online_schedule(seed)
        traced = diagnostics._run_candidate_trace(seed, schedule)
        registered = evaluation._run_information_directed_policy(
            seed,
            schedule,
            block_length=16,
        )
        self.assertEqual(traced.rewards, registered.rewards)
        self.assertTrue(traced.causal_archive_complete)

    def test_world_trace_has_frozen_metrics_and_exact_quarters(self) -> None:
        world = diagnostics.run_ids_failure_audit_world(25301)
        self.assertEqual(
            world.trace_length, diagnostics.ONLINE_INTERACTION_COUNT
        )
        self.assertEqual(len(world.quarters), 4)
        self.assertEqual(
            set(world.full_run), set(diagnostics._METRIC_NAMES)
        )
        self.assertTrue(world.causal_archive_complete)
        for metrics in (world.full_run, *world.quarters):
            for name in (
                "total_disagreement_rate",
                "staleness_channel_disagreement_rate",
                "ensemble_channel_disagreement_rate",
                "mixture_channel_disagreement_rate",
                "selected_non_greedy_probability",
                "realized_non_greedy_rate",
                "non_degenerate_mixture_rate",
            ):
                self.assertGreaterEqual(metrics[name], 0.0)
                self.assertLessEqual(metrics[name], 1.0)
            self.assertAlmostEqual(
                metrics["realized_non_greedy_rate"],
                metrics["mixture_channel_disagreement_rate"],
            )
            self.assertAlmostEqual(
                metrics["mixture_minus_ensemble_disagreement_rate"],
                metrics["mixture_channel_disagreement_rate"]
                - metrics["ensemble_channel_disagreement_rate"],
            )
            self.assertAlmostEqual(
                metrics["mixture_minus_staleness_disagreement_rate"],
                metrics["mixture_channel_disagreement_rate"]
                - metrics["staleness_channel_disagreement_rate"],
            )
            self.assertAlmostEqual(
                metrics["ensemble_minus_staleness_disagreement_rate"],
                metrics["ensemble_channel_disagreement_rate"]
                - metrics["staleness_channel_disagreement_rate"],
            )
            self.assertGreaterEqual(
                metrics["mean_current_map_q_opportunity_cost"], 0.0
            )

    def test_bootstrap_is_deterministic_and_uses_frozen_quantiles(self) -> None:
        first = diagnostics._bootstrap_estimate(
            (0.0, 1.0, 2.0, 3.0), resamples=256
        )
        second = diagnostics._bootstrap_estimate(
            (0.0, 1.0, 2.0, 3.0), resamples=256
        )
        self.assertEqual(first, second)
        self.assertEqual(first.mean, 1.5)
        self.assertAlmostEqual(
            diagnostics._quantile((0.0, 10.0), 0.025), 0.25
        )

    def test_small_report_is_diagnostic_and_finite(self) -> None:
        self.assertEqual(self.report.seeds, IDS_AUDIT_TEST_SEEDS)
        self.assertEqual(self.report.block_length, 16)
        self.assertEqual(self.report.sample_count, 16)
        self.assertEqual(self.report.bootstrap_resamples, 128)
        self.assertEqual(
            self.report.bootstrap_seed,
            diagnostics.IDS_FAILURE_AUDIT_BOOTSTRAP_SEED,
        )
        self.assertEqual(self.report.causal_archive_rate, 1.0)
        self.assertEqual(self.report.evidence_level, "E1_LOCAL_DIAGNOSTIC")
        self.assertIn(
            self.report.reward_deficit_replication,
            {"replicated", "not_resolved"},
        )
        self.assertIn(
            self.report.model_implied_decision_cost,
            {"resolved_above_zero", "not_resolved"},
        )
        self.assertIn(
            self.report.dominant_disagreement_channel,
            {"mixture", "ensemble", "staleness", "unresolved"},
        )
        serialized = self.report.to_dict()
        self.assertNotIn("passes", serialized)
        self.assertNotIn("worlds", serialized)
        self.assertTrue(
            all(
                math.isfinite(value)
                for estimate in self.report.full_run.values()
                for value in (
                    estimate.mean,
                    estimate.lower_95,
                    estimate.upper_95,
                )
            )
        )

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            diagnostics.run_ids_failure_audit(())
        with self.assertRaises(ValidationError):
            diagnostics.run_ids_failure_audit((25320, 25320))
        with self.assertRaises(ValidationError):
            diagnostics.run_ids_failure_audit((True,))  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            diagnostics.run_ids_failure_audit(
                (25320,), bootstrap_resamples=0
            )


if __name__ == "__main__":
    unittest.main()
