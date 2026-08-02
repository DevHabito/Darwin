from __future__ import annotations

import json
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
    permuted_transfer_prior,
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

    def test_permutation_preserves_priors_but_breaks_alignment(self) -> None:
        learned = learn_transfer_prior(self.evidence)
        permuted = permuted_transfer_prior(learned, offset=1)
        self.assertNotEqual(permuted, learned)
        self.assertEqual(
            sorted(
                (cell.transition.alpha, cell.transition.beta)
                for cell in permuted.cells
            ),
            sorted(
                (cell.transition.alpha, cell.transition.beta)
                for cell in learned.cells
            ),
        )
        with self.assertRaises(ValidationError):
            permuted_transfer_prior(learned, offset=16)

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

    def test_snapshot_replay_preserves_state_and_future(self) -> None:
        model = self._run_outcomes(matching=True)
        restored = GatedTransferModel.from_snapshot(model.to_snapshot())
        self.assertEqual(restored.source_weight, model.source_weight)
        self.assertEqual(restored.weight_history, model.weight_history)
        self.assertEqual(restored.archive, model.archive)
        first = model.forecast(self.context, self.action)
        second = restored.forecast(self.context, self.action)
        self.assertEqual(first, second)
        observation = TransferObservation(
            world_id="gate-test-world",
            index=6,
            context=self.context,
            action=self.action,
            next_observation=True,
            reward=True,
        )
        model.observe(observation)
        restored.observe(observation)
        self.assertEqual(restored.to_snapshot(), model.to_snapshot())

    def test_snapshot_rejects_derived_and_prior_tampering(self) -> None:
        model = self._run_outcomes(matching=True)
        payload = json.loads(model.to_snapshot())
        payload["derived"]["source_weight"] = 0.25
        with self.assertRaises(ValidationError):
            GatedTransferModel.from_snapshot(json.dumps(payload))
        payload = json.loads(model.to_snapshot())
        payload["configuration"]["source_prior"]["cells"][0][
            "transition"
        ]["alpha"] += 1.0
        with self.assertRaises(ValidationError):
            GatedTransferModel.from_snapshot(json.dumps(payload))

    def test_snapshot_rejects_pending_and_duplicate_json_keys(self) -> None:
        model = GatedTransferModel(
            world_id="gate-test-world",
            source_prior=self.source_prior,
            initial_source_weight=0.5,
        )
        model.forecast(self.context, self.action)
        with self.assertRaises(ValidationError):
            model.to_snapshot()
        with self.assertRaises(ValidationError):
            GatedTransferModel.from_snapshot(
                '{"schema":1,"schema":1}'
            )


if __name__ == "__main__":
    unittest.main()
