from __future__ import annotations

import unittest

from darwin_v50.cross_world_transfer_lab import (
    TransferFamilySpecification,
    TransferObservation,
    TransferPrior,
    transfer_cell_keys,
)
from darwin_v50.cross_world_transfer_learning import (
    GatedTransferModel,
    collect_source_family_evidence,
    learn_transfer_prior,
    pooled_source_prior,
)
from darwin_v50.models import ValidationError


class SourceLearnedPriorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.family = TransferFamilySpecification.from_seed(27300)
        cls.evidence = collect_source_family_evidence(
            cls.family,
            base_seed=27301,
            task_count=16,
            cycles=8,
        )

    def test_source_evidence_is_deterministic_and_contains_no_parameters(self) -> None:
        repeated = collect_source_family_evidence(
            self.family,
            base_seed=27301,
            task_count=16,
            cycles=8,
        )
        self.assertEqual(self.evidence, repeated)
        self.assertEqual(len({item.world_id for item in self.evidence}), 16)
        self.assertTrue(all(item.interactions == 128 for item in self.evidence))
        self.assertEqual(
            tuple(item.world_id for item in self.evidence),
            tuple(f"source-task:{index}" for index in range(16)),
        )
        self.assertTrue(
            all(
                str(self.family.seed) not in item.world_id
                and "27301" not in item.world_id
                for item in self.evidence
            )
        )
        for task in self.evidence:
            for cell in task.cells:
                self.assertNotIn(
                    "probability",
                    " ".join(cell.__dataclass_fields__).lower(),
                )

    def test_learned_prior_is_finite_aligned_and_not_the_oracle(self) -> None:
        learned = learn_transfer_prior(self.evidence)
        oracle = TransferPrior.oracle(self.family)
        self.assertTrue(learned.provenance.startswith("learned-beta-binomial"))
        self.assertNotEqual(learned, oracle)
        self.assertEqual(
            tuple((item.context, item.action) for item in learned.cells),
            transfer_cell_keys(),
        )

    def test_naive_pooling_is_more_concentrated_than_hierarchical_fit(self) -> None:
        learned = learn_transfer_prior(self.evidence)
        pooled = pooled_source_prior(self.evidence)
        self.assertTrue(
            all(
                pooled_cell.transition.alpha
                + pooled_cell.transition.beta
                > learned_cell.transition.alpha
                + learned_cell.transition.beta
                for learned_cell, pooled_cell in zip(
                    learned.cells, pooled.cells
                )
            )
        )

    def test_duplicate_source_task_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            learn_transfer_prior((self.evidence[0], self.evidence[0]))


class CompatibilityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        family = TransferFamilySpecification.from_seed(27310)
        self.source_prior = TransferPrior.oracle(family)
        self.context, self.action = next(
            (cell.context, cell.action)
            for cell in family.cells
            if cell.transition_mean > 0.5 and cell.reward_mean > 0.5
        )

    def _run_outcomes(self, *, matching: bool) -> GatedTransferModel:
        model = GatedTransferModel(
            world_id="gate-test-world",
            source_prior=self.source_prior,
            initial_source_weight=0.5,
        )
        for index in range(6):
            model.forecast(self.context, self.action)
            model.observe(
                TransferObservation(
                    world_id="gate-test-world",
                    index=index,
                    context=self.context,
                    action=self.action,
                    next_observation=matching,
                    reward=matching,
                )
            )
        return model

    def test_weight_rises_only_after_compatible_observations(self) -> None:
        model = self._run_outcomes(matching=True)
        self.assertGreater(model.source_weight, 0.5)
        self.assertEqual(len(model.weight_history), 6)

    def test_weight_falls_after_incompatible_observations(self) -> None:
        model = self._run_outcomes(matching=False)
        self.assertLess(model.source_weight, 0.5)

    def test_gate_requires_matching_prequential_observation(self) -> None:
        model = GatedTransferModel(
            world_id="gate-test-world",
            source_prior=self.source_prior,
            initial_source_weight=0.5,
        )
        with self.assertRaises(ValidationError):
            model.observe(
                TransferObservation(
                    world_id="gate-test-world",
                    index=0,
                    context=self.context,
                    action=self.action,
                    next_observation=True,
                    reward=True,
                )
            )
        model.forecast(self.context, self.action)
        with self.assertRaises(ValidationError):
            model.forecast(self.context, self.action)


if __name__ == "__main__":
    unittest.main()
