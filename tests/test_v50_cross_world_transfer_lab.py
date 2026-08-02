from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_lab import (
    AlignedTransferTask,
    PrequentialTransferModel,
    TransferFamilyCell,
    TransferFamilySpecification,
    TransferPrior,
    TransferWorldSpecification,
    balanced_transfer_schedule,
    require_disjoint_seed_sets,
    transfer_cell_keys,
)
from darwin_v50.learned_context_lab import CONTEXT_ACTIONS
from darwin_v50.models import ValidationError


class TransferFamilyTests(unittest.TestCase):
    def test_family_and_world_draws_are_deterministic_and_distinct(self) -> None:
        family = TransferFamilySpecification.from_seed(26000)
        self.assertEqual(
            family,
            TransferFamilySpecification.from_seed(26000),
        )
        first = TransferWorldSpecification.from_family(
            family, world_seed=26100
        )
        self.assertEqual(
            first,
            TransferWorldSpecification.from_family(
                family, world_seed=26100
            ),
        )
        second = TransferWorldSpecification.from_family(
            family, world_seed=26101
        )
        self.assertNotEqual(first.cells, second.cells)
        self.assertEqual(
            tuple((item.context, item.action) for item in family.cells),
            transfer_cell_keys(),
        )

    def test_opposed_family_reverses_actionable_mappings(self) -> None:
        family = TransferFamilySpecification.from_seed(26001)
        opposed = family.opposed(seed=26002)
        for context, action in transfer_cell_keys():
            other = "violet" if action == "amber" else "amber"
            self.assertAlmostEqual(
                opposed.cell(context, action).transition_mean,
                1.0 - family.cell(context, action).transition_mean,
            )
            self.assertEqual(
                opposed.cell(context, action).reward_mean,
                family.cell(context, other).reward_mean,
            )

    def test_incomplete_or_noncanonical_family_is_rejected(self) -> None:
        family = TransferFamilySpecification.from_seed(26003)
        with self.assertRaises(ValidationError):
            TransferFamilySpecification(
                seed=26003,
                cells=family.cells[:-1],
            )
        duplicate = TransferFamilyCell(
            context=family.cells[1].context,
            action=family.cells[1].action,
            transition_mean=0.5,
            reward_mean=0.5,
        )
        with self.assertRaises(ValidationError):
            TransferFamilySpecification(
                seed=26003,
                cells=(duplicate,) + family.cells[1:],
            )


class TransferTaskAndPriorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.family = TransferFamilySpecification.from_seed(26010)
        self.world_specification = TransferWorldSpecification.from_family(
            self.family,
            world_seed=26110,
        )

    def test_task_returns_only_the_chosen_cell_outcomes(self) -> None:
        task = AlignedTransferTask(
            self.world_specification,
            outcome_seed=26210,
        )
        context, action = transfer_cell_keys()[0]
        first = task.act(context, action)
        second = task.act(context, action)
        replay = AlignedTransferTask(
            self.world_specification,
            outcome_seed=26210,
        )
        self.assertEqual(first, replay.act(context, action))
        self.assertEqual(second, replay.act(context, action))
        self.assertEqual(first.index, 0)
        self.assertEqual(second.index, 1)
        self.assertNotIn("counterfactual", first.__dataclass_fields__)

    def test_task_can_hide_evaluator_seed_identity(self) -> None:
        task = AlignedTransferTask(
            self.world_specification,
            outcome_seed=26213,
            public_world_id="opaque-task",
        )
        context, action = transfer_cell_keys()[0]
        observation = task.act(context, action)
        self.assertEqual(observation.world_id, "opaque-task")
        self.assertNotIn(str(self.family.seed), observation.world_id)
        self.assertNotIn(
            str(self.world_specification.world_seed),
            observation.world_id,
        )

    def test_oracle_prior_matches_hidden_family_distribution(self) -> None:
        prior = TransferPrior.oracle(self.family)
        self.assertTrue(prior.provenance.startswith("evaluator-oracle"))
        for context, action in transfer_cell_keys():
            family_cell = self.family.cell(context, action)
            prior_cell = prior.cell(context, action)
            self.assertAlmostEqual(
                prior_cell.transition.mean,
                family_cell.transition_mean,
            )
            self.assertAlmostEqual(
                prior_cell.reward.mean,
                family_cell.reward_mean,
            )

    def test_prequential_model_requires_matching_chosen_outcome(self) -> None:
        prior = TransferPrior.scratch()
        model = PrequentialTransferModel(
            world_id=self.world_specification.world_id,
            prior=prior,
        )
        task = AlignedTransferTask(
            self.world_specification,
            outcome_seed=26211,
        )
        context, action = transfer_cell_keys()[0]
        forecast = model.forecast(context, action)
        self.assertEqual(forecast.transition_probability, 0.5)
        self.assertEqual(forecast.reward_probability, 0.5)
        with self.assertRaises(ValidationError):
            model.forecast(context, action)
        observation = task.act(context, action)
        model.observe(observation)
        self.assertEqual(model.archive, (observation,))
        updated = model.forecast(context, action)
        self.assertNotEqual(
            (updated.transition_probability, updated.reward_probability),
            (0.5, 0.5),
        )

    def test_peek_compares_actions_without_creating_evidence(self) -> None:
        model = PrequentialTransferModel(
            world_id=self.world_specification.world_id,
            prior=TransferPrior.scratch(),
        )
        context, action = transfer_cell_keys()[0]
        other_action = next(
            candidate for candidate in CONTEXT_ACTIONS
            if candidate != action
        )
        first = model.peek(context, action)
        second = model.peek(context, other_action)
        self.assertEqual(first.index, 0)
        self.assertEqual(second.index, 0)
        self.assertIsNone(model.pending)
        self.assertEqual(model.archive, ())
        with self.assertRaises(ValidationError):
            model.observe(
                AlignedTransferTask(
                    self.world_specification,
                    outcome_seed=26214,
                ).act(context, action)
            )

    def test_observation_cannot_cross_worlds_or_actions(self) -> None:
        model = PrequentialTransferModel(
            world_id=self.world_specification.world_id,
            prior=TransferPrior.scratch(),
        )
        context, action = transfer_cell_keys()[0]
        model.forecast(context, action)
        other_world = TransferWorldSpecification.from_family(
            self.family,
            world_seed=26111,
        )
        other_task = AlignedTransferTask(other_world, outcome_seed=26212)
        with self.assertRaises(ValidationError):
            model.observe(other_task.act(context, action))


class TransferBoundaryTests(unittest.TestCase):
    def test_balanced_schedule_covers_every_cell_per_cycle(self) -> None:
        schedule = balanced_transfer_schedule(cycles=3, seed=26300)
        self.assertEqual(len(schedule), 3 * len(transfer_cell_keys()))
        keys = set(transfer_cell_keys())
        width = len(keys)
        for start in range(0, len(schedule), width):
            self.assertEqual(set(schedule[start : start + width]), keys)
        self.assertEqual(
            schedule,
            balanced_transfer_schedule(cycles=3, seed=26300),
        )

    def test_seed_namespaces_must_be_disjoint(self) -> None:
        normalized = require_disjoint_seed_sets(
            source=(26400, 26401),
            development=(26500, 26501),
            calibration=(26600, 26601),
            final=(26700, 26701),
        )
        self.assertEqual(normalized["final"], (26700, 26701))
        with self.assertRaises(ValidationError):
            require_disjoint_seed_sets(
                source=(26400,),
                final=(26400,),
            )
        with self.assertRaises(ValidationError):
            require_disjoint_seed_sets(source=(26400, 26400))


if __name__ == "__main__":
    unittest.main()
