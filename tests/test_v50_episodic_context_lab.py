from __future__ import annotations

import json
import math
import unittest

import darwin_v50.episodic_context_evaluation as evaluation
from darwin_v50.episodic_context_lab import (
    EPISODE_COUNT,
    STEPS_PER_EPISODE,
    EpisodeRetrievalDecision,
    EpisodicActionMemory,
    EpisodicContextWorld,
    EpisodicInteraction,
    EpisodicStep,
    EpisodicWorldSpecification,
    forced_action,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import GoalStatus, ValidationError
from darwin_v50.store import SQLiteEventStore


def _complete_episode(
    model: EpisodicActionMemory,
    episode_index: int,
    cues: tuple[bool, bool, bool, bool],
    *,
    rewarding_action: int,
) -> tuple[int, ...]:
    model.begin_episode(episode_index)
    actions: list[int] = []
    for _ in range(STEPS_PER_EPISODE):
        model.observe_cues(cues)
        action = model.choose_action()
        actions.append(action)
        model.observe_outcome(action, action == rewarding_action)
    model.end_episode()
    return tuple(actions)


class EpisodicWorldTests(unittest.TestCase):
    def test_four_families_are_deterministic_and_complete(self) -> None:
        worlds = tuple(
            EpisodicContextWorld(seed) for seed in range(15000, 15004)
        )
        self.assertEqual(
            tuple(item.specification.family for item in worlds),
            (
                "exact_recurrence",
                "cue_drift",
                "reward_drift",
                "novelty",
            ),
        )
        for seed, world in zip(
            range(15000, 15004),
            worlds,
            strict=True,
        ):
            self.assertEqual(
                world.steps,
                EpisodicContextWorld(seed).steps,
            )
            self.assertEqual(
                len(world.steps),
                EPISODE_COUNT * STEPS_PER_EPISODE,
            )
            self.assertTrue(
                all(
                    len(step.potential_outcomes) == 3
                    and len(step.reward_probabilities) == 3
                    for step in world.steps
                )
            )
            self.assertEqual(
                tuple(
                    world.episode_steps(index)[0].context_label
                    for index in range(1, EPISODE_COUNT + 1)
                ),
                world.specification.episode_labels,
            )

    def test_contexts_are_separated_and_rewards_keep_one_best_action(self) -> None:
        for seed in range(15000, 15004):
            specification = EpisodicWorldSpecification.from_seed(seed)
            codes = tuple(item.code for item in specification.contexts)
            self.assertEqual(len(codes), len(set(codes)))
            self.assertTrue(
                all(
                    sum(
                        left != right
                        for left, right in zip(a, b, strict=True)
                    )
                    >= 2
                    for index, a in enumerate(codes)
                    for b in codes[index + 1 :]
                )
            )
            for step in EpisodicContextWorld(seed).steps:
                self.assertEqual(
                    sum(
                        probability == max(step.reward_probabilities)
                        for probability in step.reward_probabilities
                    ),
                    1,
                )

    def test_forced_actions_are_registered_and_deterministic(self) -> None:
        self.assertEqual(forced_action(1, 1), 0)
        self.assertEqual(forced_action(1, 2), 1)
        self.assertEqual(forced_action(1, 3), 2)
        self.assertEqual(forced_action(1, 10), 2)
        self.assertEqual(forced_action(2, 10), 0)
        self.assertEqual(forced_action(1, 20), 0)
        self.assertIsNone(forced_action(1, 4))
        with self.assertRaises(ValidationError):
            forced_action(True, 1)

    def test_invalid_step_probability_shape_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EpisodicStep(
                episode_index=1,
                step_index=1,
                context_label="A",
                cues=(False, False, False, False),
                potential_outcomes=(False, False, False),
                reward_probabilities=(0.15, 0.85),  # type: ignore[arg-type]
            )


class EpisodicActionMemoryTests(unittest.TestCase):
    def test_action_must_precede_exactly_one_chosen_outcome(self) -> None:
        model = EpisodicActionMemory(memory_enabled=False)
        model.begin_episode(1)
        model.observe_cues((False, False, False, False))
        self.assertEqual(model.choose_action(), 0)
        self.assertEqual(model.choose_action(), 0)
        with self.assertRaises(ValidationError):
            model.observe_outcome(1, True)
        model.observe_outcome(0, True)
        self.assertEqual(len(model.archive), 1)
        self.assertEqual(model.archive[0].action, 0)
        self.assertTrue(model.archive[0].outcome)
        with self.assertRaises(ValidationError):
            model.observe_outcome(0, False)
        snapshot_row = json.loads(model.to_snapshot())["archive"][0]
        self.assertEqual(
            set(snapshot_row),
            {"episode_index", "step_index", "cues", "action", "outcome"},
        )

    def test_exact_context_retrieves_locked_prototype(self) -> None:
        model = EpisodicActionMemory(
            minimum_cues=4,
            match_tolerance=0.10,
        )
        a = (False, False, False, False)
        b = (False, False, True, True)
        c = (False, True, False, True)
        _complete_episode(model, 1, a, rewarding_action=2)
        _complete_episode(model, 2, b, rewarding_action=1)
        _complete_episode(model, 3, c, rewarding_action=0)
        model.begin_episode(4)
        for step_index in range(1, 5):
            model.observe_cues(a)
            action = model.choose_action()
            model.observe_outcome(action, action == 2)
            if step_index < 4:
                self.assertIsNone(model.active_prototype_id)
        decision = model.retrieval_decisions[-1]
        self.assertEqual(decision.episode_index, 4)
        self.assertEqual(decision.step_index, 4)
        self.assertEqual(decision.retrieved_prototype_id, 1)
        self.assertEqual(decision.distance, 0.0)
        self.assertFalse(decision.abstained)
        self.assertEqual(model.active_prototype_id, 1)
        for _ in range(4, STEPS_PER_EPISODE):
            model.observe_cues(a)
            action = model.choose_action()
            model.observe_outcome(action, action == 2)
        model.end_episode()
        self.assertEqual(len(model.prototypes), 3)
        self.assertEqual(model.prototypes[0].consolidations, 2)

    def test_novel_context_abstains_and_forms_a_new_prototype(self) -> None:
        model = EpisodicActionMemory(
            minimum_cues=4,
            match_tolerance=0.10,
        )
        a = (False, False, False, False)
        novel = (True, True, True, True)
        _complete_episode(model, 1, a, rewarding_action=0)
        model.begin_episode(2)
        for _ in range(STEPS_PER_EPISODE):
            model.observe_cues(novel)
            action = model.choose_action()
            model.observe_outcome(action, action == 1)
        self.assertTrue(model.retrieval_decisions[-1].abstained)
        self.assertIsNone(model.active_prototype_id)
        model.end_episode()
        self.assertEqual(len(model.prototypes), 2)

    def test_disabled_memory_resets_and_never_consolidates(self) -> None:
        model = EpisodicActionMemory(memory_enabled=False)
        actions = _complete_episode(
            model,
            1,
            (False, False, False, False),
            rewarding_action=2,
        )
        self.assertEqual(actions[:3], (0, 1, 2))
        self.assertEqual(model.prototypes, ())
        self.assertEqual(model.retrieval_decisions, ())
        model.begin_episode(2)
        self.assertEqual(model.action_probabilities(), (0.5, 0.5, 0.5))

    def test_snapshot_preserves_pending_action_and_future(self) -> None:
        original = EpisodicActionMemory(
            minimum_cues=4,
            match_tolerance=0.20,
        )
        _complete_episode(
            original,
            1,
            (False, False, False, False),
            rewarding_action=2,
        )
        original.begin_episode(2)
        original.observe_cues((False, False, False, False))
        pending = original.choose_action()
        snapshot = original.to_snapshot()
        restored = EpisodicActionMemory.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.choose_action(), pending)
        original.observe_outcome(pending, pending == 2)
        restored.observe_outcome(pending, pending == 2)
        for _ in range(1, STEPS_PER_EPISODE):
            cues = (False, False, False, False)
            original.observe_cues(cues)
            restored.observe_cues(cues)
            self.assertEqual(original.choose_action(), restored.choose_action())
            action = original.choose_action()
            original.observe_outcome(action, action == 2)
            restored.observe_outcome(action, action == 2)
        original.end_episode()
        restored.end_episode()
        self.assertEqual(restored.to_snapshot(), original.to_snapshot())

    def test_snapshot_rejects_action_and_state_tampering(self) -> None:
        model = EpisodicActionMemory()
        _complete_episode(
            model,
            1,
            (False, False, False, False),
            rewarding_action=0,
        )
        action_tamper = json.loads(model.to_snapshot())
        action_tamper["archive"][0]["action"] = 1
        with self.assertRaises(ValidationError):
            EpisodicActionMemory.from_snapshot(json.dumps(action_tamper))
        state_tamper = json.loads(model.to_snapshot())
        state_tamper["prototypes"][0]["cue_count"] += 1
        with self.assertRaises(ValidationError):
            EpisodicActionMemory.from_snapshot(json.dumps(state_tamper))

    def test_future_episode_indices_are_valid_but_booleans_are_not(self) -> None:
        interaction = EpisodicInteraction(
            episode_index=EPISODE_COUNT + 1,
            step_index=1,
            cues=(False, False, False, False),
            action=0,
            outcome=True,
        )
        self.assertEqual(interaction.episode_index, EPISODE_COUNT + 1)
        model = EpisodicActionMemory()
        with self.assertRaises(ValidationError):
            model.begin_episode(True)

    def test_retrieval_decision_rejects_nonfinite_values(self) -> None:
        with self.assertRaises(ValidationError):
            EpisodeRetrievalDecision(
                episode_index=1,
                step_index=4,
                retrieved_prototype_id=1,
                distance=math.nan,
                current_cue_means=(0.0, 0.0, 0.0, 0.0),
                prototype_cue_means=(0.0, 0.0, 0.0, 0.0),
                abstained=False,
            )


class EpisodicEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = evaluation.run_episodic_suite(
            development_seeds=(15200, 15201, 15202, 15203),
            final_seeds=(15300, 15301, 15302, 15303),
            minimum_cue_candidates=(4,),
            tolerance_candidates=(0.24,),
        )

    def test_small_suite_is_balanced_disjoint_and_persistent(self) -> None:
        self.assertEqual(self.report.final_world_count, 4)
        self.assertEqual(set(self.report.family_counts.values()), {1})
        self.assertEqual(self.report.unique_world_count, 4)
        self.assertFalse(
            set(self.report.development.seeds)
            & set(self.report.final_seeds)
        )
        self.assertEqual(self.report.archive_retention_rate, 1.0)
        self.assertEqual(self.report.snapshot_round_trip_rate, 1.0)
        self.assertEqual(
            self.report.development.selected_minimum_cues,
            4,
        )
        self.assertEqual(
            self.report.development.selected_match_tolerance,
            0.24,
        )
        self.assertIn("15200-15203", self.report.held_out_definition)
        self.assertIn("15300-15303", self.report.held_out_definition)

    def test_seed_overlap_and_invalid_grid_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation.run_episodic_suite(
                development_seeds=(15400,),
                final_seeds=(15400,),
                minimum_cue_candidates=(4,),
                tolerance_candidates=(0.24,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_episodic_configuration(
                seeds=(15401,),
                minimum_cue_candidates=(4, 4),
                tolerance_candidates=(0.24,),
            )
        with self.assertRaises(ValidationError):
            evaluation.select_episodic_configuration(
                seeds=(15401,),
                minimum_cue_candidates=(4,),
                tolerance_candidates=(0.24, float("nan")),
            )

    def test_regression_criteria_are_strictly_conjunctive(self) -> None:
        passing = evaluation.report_with_episodic_metrics(
            self.report,
            total_improvement_vs_local=0.04,
            world_win_rate_vs_local=0.75,
            total_improvement_vs_global=0.05,
            recurrence_improvement_vs_local=0.06,
            exact_recurrence_improvement_vs_local=0.08,
            cue_drift_improvement_vs_local=0.05,
            reward_drift_improvement_vs_local=0.05,
            novelty_degradation_vs_local=0.02,
            gap_to_oracle=0.15,
            correct_recurrence_retrieval_coverage=0.85,
            retrieval_precision=0.90,
            novelty_abstention_coverage=0.80,
            novelty_false_retrieval_rate=0.10,
            archive_retention_rate=1.0,
            snapshot_round_trip_rate=1.0,
        )
        self.assertTrue(passing.passes_regression_criteria())
        self.assertFalse(
            evaluation.report_with_episodic_metrics(
                passing,
                exact_recurrence_improvement_vs_local=0.08 - 1e-12,
            ).passes_regression_criteria()
        )

    def test_kernel_does_not_promote_a_failed_conjunction(self) -> None:
        failing = evaluation.report_with_episodic_metrics(
            self.report,
            total_improvement_vs_local=-1.0,
        )
        kernel = DarwinKernelV50(SQLiteEventStore(":memory:"))
        result = evaluation.record_episodic_result(kernel, failing)
        self.assertEqual(
            result.goal.status,
            GoalStatus.WAITING_OBSERVATION,
        )
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
