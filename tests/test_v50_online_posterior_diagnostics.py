from __future__ import annotations

import math
import unittest

import darwin_v50.online_posterior_diagnostics as diagnostics
import darwin_v50.online_posterior_evaluation as evaluation
from darwin_v50.models import ValidationError


AUDIT_TEST_SEEDS = (23310, 23311, 23312, 23313)


class OnlinePosteriorFailureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = diagnostics.run_posterior_failure_audit(
            AUDIT_TEST_SEEDS,
            bootstrap_resamples=128,
        )

    def test_shadow_instrumentation_preserves_registered_candidate(self) -> None:
        seed = 23300
        schedule = evaluation.make_online_schedule(seed)
        traced = diagnostics._run_candidate_trace(seed, schedule)
        registered = evaluation._run_posterior_policy(
            seed,
            schedule,
            resampling_length=32,
            policy_seed_mask=evaluation.ONLINE_CANDIDATE_POLICY_XOR_MASK,
        )
        self.assertEqual(traced.rewards, registered.rewards)
        self.assertTrue(traced.causal_archive_complete)

    def test_world_trace_has_frozen_metrics_and_exact_quarters(self) -> None:
        world = diagnostics.run_posterior_audit_world(23301)
        self.assertEqual(world.trace_length, evaluation.ONLINE_INTERACTION_COUNT)
        self.assertEqual(len(world.quarters), 4)
        self.assertEqual(
            set(world.full_run), set(diagnostics._METRIC_NAMES)
        )
        self.assertTrue(world.causal_archive_complete)
        for metrics in (world.full_run, *world.quarters):
            for name in (
                "candidate_vs_map_disagreement_rate",
                "order_channel_disagreement_rate",
                "parameter_channel_disagreement_rate",
                "sampled_order_map_mismatch_rate",
            ):
                self.assertGreaterEqual(metrics[name], 0.0)
                self.assertLessEqual(metrics[name], 1.0)
            self.assertGreaterEqual(
                metrics["mean_map_q_opportunity_cost"], 0.0
            )
            self.assertAlmostEqual(
                metrics["parameter_minus_order_disagreement_rate"],
                metrics["parameter_channel_disagreement_rate"]
                - metrics["order_channel_disagreement_rate"],
            )
            self.assertAlmostEqual(
                metrics["candidate_minus_certainty_reward"],
                metrics["candidate_reward"]
                - metrics["certainty_equivalent_reward"],
            )

    def test_bootstrap_is_deterministic_and_uses_frozen_seed(self) -> None:
        first = diagnostics._bootstrap_estimate(
            (0.0, 1.0, 2.0, 3.0), resamples=256
        )
        second = diagnostics._bootstrap_estimate(
            (0.0, 1.0, 2.0, 3.0), resamples=256
        )
        self.assertEqual(first, second)
        self.assertEqual(first.mean, 1.5)
        self.assertLessEqual(first.lower_95, first.mean)
        self.assertGreaterEqual(first.upper_95, first.mean)
        self.assertAlmostEqual(
            diagnostics._quantile((0.0, 10.0), 0.025), 0.25
        )

    def test_small_report_is_diagnostic_not_a_pass_fail_claim(self) -> None:
        self.assertEqual(self.report.seeds, AUDIT_TEST_SEEDS)
        self.assertEqual(self.report.resampling_length, 32)
        self.assertEqual(self.report.bootstrap_resamples, 128)
        self.assertEqual(
            self.report.bootstrap_seed,
            diagnostics.POSTERIOR_AUDIT_BOOTSTRAP_SEED,
        )
        self.assertEqual(self.report.causal_archive_rate, 1.0)
        self.assertEqual(self.report.evidence_level, "E1_LOCAL_DIAGNOSTIC")
        self.assertIn(
            self.report.reward_deficit_replication,
            {"replicated", "not_resolved"},
        )
        self.assertIn(
            self.report.model_implied_sampling_cost,
            {"resolved_above_zero", "not_resolved"},
        )
        self.assertIn(
            self.report.dominant_action_change_channel,
            {"parameter", "order", "unresolved"},
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

    def test_invalid_seed_and_bootstrap_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            diagnostics.run_posterior_failure_audit(())
        with self.assertRaises(ValidationError):
            diagnostics.run_posterior_failure_audit((23320, 23320))
        with self.assertRaises(ValidationError):
            diagnostics.run_posterior_failure_audit((True,))  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            diagnostics.run_posterior_failure_audit(
                (23320,), bootstrap_resamples=0
            )


if __name__ == "__main__":
    unittest.main()
