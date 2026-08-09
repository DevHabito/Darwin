from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.uncertainty_evaluation import (
    ForecastRecord,
    calibration_metrics,
    record_uncertainty_result,
    report_with_utility_advantages,
    run_uncertainty_suite,
    train_balanced_outcome_model,
)
from darwin_v50.uncertainty_lab import (
    ALL_CONTEXTS,
    CHOICE_ACTIONS,
    CHOOSE_ALPHA,
    CHOOSE_BETA,
    DOMAIN_ID,
    INSPECT,
    BetaBernoulliOutcomeModel,
    HiddenSignalObservation,
    HiddenSignalWorld,
    OutcomeExperience,
    SelectiveInformationPolicy,
)


class HiddenSignalWorldTests(unittest.TestCase):
    def test_initial_observation_aliases_both_hidden_states(self) -> None:
        world = HiddenSignalWorld(6100)
        revealed_by_initial = {context: set() for context in ALL_CONTEXTS[:4]}
        for _ in range(3000):
            initial = world.reset()
            revealed = world.step(INSPECT).observation
            revealed_by_initial[initial.context].add(revealed.context)

        self.assertTrue(
            all(
                values == {"revealed_alpha", "revealed_beta"}
                for values in revealed_by_initial.values()
            )
        )

    def test_inspection_has_cost_and_cannot_be_repeated(self) -> None:
        world = HiddenSignalWorld(6101)
        initial = world.reset()
        inspected = world.step(INSPECT)

        self.assertFalse(initial.inspection_used)
        self.assertTrue(inspected.observation.inspection_used)
        self.assertIn(inspected.observation.context, ALL_CONTEXTS[4:])
        self.assertEqual(inspected.information_cost, 0.12)
        self.assertEqual(inspected.reward, -0.12)
        self.assertNotIn(INSPECT, world.available_actions())
        with self.assertRaises(ValidationError):
            world.step(INSPECT)

    def test_outcomes_are_stochastic_and_conditioned_on_hidden_state(self) -> None:
        matching_world = HiddenSignalWorld(6102)
        mismatching_world = HiddenSignalWorld(6103)
        matching: list[bool] = []
        mismatching: list[bool] = []
        while len(matching) < 1000:
            matching_world.reset()
            revealed = matching_world.step(INSPECT).observation
            if revealed.context != "revealed_alpha":
                continue
            result = matching_world.step(CHOOSE_ALPHA)
            assert result.success is not None
            matching.append(result.success)
        while len(mismatching) < 1000:
            mismatching_world.reset()
            revealed = mismatching_world.step(INSPECT).observation
            if revealed.context != "revealed_alpha":
                continue
            result = mismatching_world.step(CHOOSE_BETA)
            assert result.success is not None
            mismatching.append(result.success)

        matching_rate = sum(matching) / len(matching)
        mismatching_rate = sum(mismatching) / len(mismatching)
        self.assertGreater(matching_rate, 0.85)
        self.assertLess(matching_rate, 0.95)
        self.assertGreater(mismatching_rate, 0.05)
        self.assertLess(mismatching_rate, 0.15)


class ProbabilisticOutcomeModelTests(unittest.TestCase):
    def test_prior_replay_conflict_and_domain_isolation(self) -> None:
        model = BetaBernoulliOutcomeModel()
        prior = model.predict("clear_alpha", CHOOSE_ALPHA)
        experience = OutcomeExperience(
            experience_id="outcome:1",
            domain_id=DOMAIN_ID,
            episode_id="episode:1",
            context="clear_alpha",
            action=CHOOSE_ALPHA,
            success=True,
        )

        self.assertEqual(prior.success_probability, 0.5)
        self.assertEqual(prior.evidence_count, 0)
        self.assertTrue(model.observe(experience))
        self.assertFalse(model.observe(experience))
        self.assertGreater(
            model.predict("clear_alpha", CHOOSE_ALPHA).success_probability,
            0.5,
        )
        with self.assertRaises(ValidationError):
            model.observe(replace(experience, success=False))
        with self.assertRaises(ValidationError):
            model.observe(
                replace(
                    experience,
                    experience_id="outcome:2",
                    domain_id="another-domain",
                )
            )

    def test_balanced_training_and_snapshot_round_trip(self) -> None:
        model = train_balanced_outcome_model(
            seed=6200,
            samples_per_context_action=40,
        )
        restored = BetaBernoulliOutcomeModel.from_snapshot(model.to_snapshot())

        self.assertEqual(
            model.experience_count,
            len(ALL_CONTEXTS) * len(CHOICE_ACTIONS) * 40,
        )
        self.assertEqual(restored.to_snapshot(), model.to_snapshot())
        for context in ALL_CONTEXTS:
            for action in CHOICE_ACTIONS:
                self.assertEqual(
                    restored.predict(context, action),
                    model.predict(context, action),
                )

    def test_selective_policy_distinguishes_weak_clear_and_revealed_contexts(
        self,
    ) -> None:
        model = train_balanced_outcome_model(
            seed=6201,
            samples_per_context_action=250,
        )
        policy = SelectiveInformationPolicy(model)

        def observation(context: str, *, inspected: bool = False):
            return HiddenSignalObservation(
                domain_id=DOMAIN_ID,
                episode_id=f"episode:{context}",
                context=context,
                step_index=int(inspected),
                terminal=False,
                inspection_used=inspected,
            )

        clear = policy.decide(observation("clear_alpha"))
        weak = policy.decide(observation("weak_alpha"))
        revealed = policy.decide(
            observation("revealed_alpha", inspected=True)
        )

        self.assertNotEqual(clear.action, INSPECT)
        self.assertEqual(clear.reason, "forecast_actionable")
        self.assertEqual(weak.action, INSPECT)
        self.assertTrue(weak.requested_information)
        self.assertEqual(revealed.action, CHOOSE_ALPHA)
        self.assertEqual(revealed.reason, "revealed_context")

    def test_calibration_metrics_reject_unbounded_probabilities(self) -> None:
        records = (
            ForecastRecord("clear_alpha", CHOOSE_ALPHA, 0.8, True),
            ForecastRecord("clear_alpha", CHOOSE_ALPHA, 0.8, False),
        )
        metrics = calibration_metrics(records)
        self.assertEqual(metrics.records, 2)
        self.assertGreaterEqual(metrics.brier_score, 0.0)
        with self.assertRaises(ValidationError):
            calibration_metrics(
                (
                    ForecastRecord(
                        "clear_alpha",
                        CHOOSE_ALPHA,
                        1.1,
                        True,
                    ),
                )
            )


class UncertaintySuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_uncertainty_suite()

    def test_held_out_forecasts_are_calibrated_and_informative(self) -> None:
        calibration = self.report.calibration
        self.assertEqual(calibration.records, 6000)
        self.assertLessEqual(calibration.brier_score, 0.18)
        self.assertGreaterEqual(calibration.brier_improvement, 0.07)
        self.assertLessEqual(calibration.expected_calibration_error, 0.04)
        self.assertIn("disjoint RNG seeds", self.report.held_out_definition)

    def test_selective_information_beats_both_fixed_policies(self) -> None:
        report = self.report
        self.assertGreaterEqual(report.selective.inspection_rate, 0.35)
        self.assertLessEqual(report.selective.inspection_rate, 0.65)
        self.assertGreaterEqual(report.selective_utility_delta_vs_never, 0.05)
        self.assertGreaterEqual(report.selective_utility_delta_vs_always, 0.02)
        self.assertTrue(report.passes_regression_criteria())
        self.assertEqual(report.evidence_level, "E1_LOCAL_AUTOMATED_EVALUATOR")

    def test_suite_is_deterministic(self) -> None:
        arguments = {
            "training_seed": 7600,
            "calibration_seed": 7601,
            "evaluation_seeds": range(7602, 7605),
            "training_samples_per_context_action": 40,
            "calibration_samples_per_context_action": 60,
            "policy_episodes_per_seed": 80,
        }
        first = run_uncertainty_suite(**arguments)
        second = run_uncertainty_suite(**arguments)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_suite_rejects_seed_reuse_and_pseudoreplication(self) -> None:
        with self.assertRaises(ValidationError):
            run_uncertainty_suite(
                training_seed=7700,
                calibration_seed=7700,
                evaluation_seeds=(7701,),
                training_samples_per_context_action=2,
                calibration_samples_per_context_action=2,
                policy_episodes_per_seed=2,
            )
        with self.assertRaises(ValidationError):
            run_uncertainty_suite(
                training_seed=7700,
                calibration_seed=7701,
                evaluation_seeds=(7702, 7702),
                training_samples_per_context_action=2,
                calibration_samples_per_context_action=2,
                policy_episodes_per_seed=2,
            )

    def test_result_is_recorded_as_unauthenticated_local_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "uncertainty.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_uncertainty_result(kernel, self.report)
                observation = next(
                    event
                    for event in kernel.goal_events(result.goal.goal_id)
                    if event.kind == "observation.recorded"
                )

        self.assertTrue(result.accepted)
        self.assertTrue(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertFalse(observation.payload["authenticated"])

    def test_failed_utility_advantage_cannot_create_success(self) -> None:
        failed = report_with_utility_advantages(
            self.report,
            delta_vs_never=0.01,
            delta_vs_always=-0.01,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "failed-uncertainty.db"
            with DarwinKernelV50.open(database) as kernel:
                result = record_uncertainty_result(kernel, failed)
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
