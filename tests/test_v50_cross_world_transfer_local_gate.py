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
    CellwiseGatedTransferModel,
)
from darwin_v50.models import ValidationError


class CellwiseCompatibilityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        family = TransferFamilySpecification.from_seed(37800)
        self.source_prior = TransferPrior.oracle(family)
        self.context, self.action = max(
            transfer_cell_keys(),
            key=lambda key: (
                self.source_prior.cell(key[0], key[1]).transition.mean
                + self.source_prior.cell(key[0], key[1]).reward.mean
            ),
        )
        self.other_context, self.other_action = next(
            key
            for key in transfer_cell_keys()
            if key != (self.context, self.action)
        )

    def _model(self, *, fallback: bool) -> CellwiseGatedTransferModel:
        return CellwiseGatedTransferModel(
            world_id="cellwise-test-world",
            source_prior=self.source_prior,
            initial_source_weight=0.5,
            scratch_fallback=fallback,
        )

    def _observe(
        self,
        model: CellwiseGatedTransferModel,
        *,
        index: int,
        outcome: bool,
    ) -> None:
        model.forecast(self.context, self.action)
        model.observe(
            TransferObservation(
                world_id="cellwise-test-world",
                index=index,
                context=self.context,
                action=self.action,
                next_observation=outcome,
                reward=outcome,
            )
        )

    def test_incompatible_evidence_triggers_only_local_fallback(self) -> None:
        model = self._model(fallback=True)
        self._observe(model, index=0, outcome=False)
        self.assertLess(
            model.posterior_source_weight(self.context, self.action),
            0.5,
        )
        self.assertEqual(
            model.effective_source_weight(self.context, self.action),
            0.0,
        )
        self.assertEqual(
            model.posterior_source_weight(
                self.other_context,
                self.other_action,
            ),
            0.5,
        )
        self.assertEqual(
            model.effective_source_weight(
                self.other_context,
                self.other_action,
            ),
            0.5,
        )

    def test_nonfallback_ablation_keeps_posterior_mixture(self) -> None:
        model = self._model(fallback=False)
        self._observe(model, index=0, outcome=False)
        posterior = model.posterior_source_weight(
            self.context,
            self.action,
        )
        self.assertLess(posterior, 0.5)
        self.assertEqual(
            model.effective_source_weight(self.context, self.action),
            posterior,
        )

    def test_compatible_evidence_retains_local_source(self) -> None:
        model = self._model(fallback=True)
        self._observe(model, index=0, outcome=True)
        posterior = model.posterior_source_weight(
            self.context,
            self.action,
        )
        self.assertGreater(posterior, 0.5)
        self.assertEqual(
            model.effective_source_weight(self.context, self.action),
            posterior,
        )

    def test_snapshot_replay_preserves_weights_archive_and_future(self) -> None:
        model = self._model(fallback=True)
        self._observe(model, index=0, outcome=False)
        snapshot = model.to_snapshot()
        restored = CellwiseGatedTransferModel.from_snapshot(snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)
        self.assertEqual(restored.archive, model.archive)
        self.assertEqual(
            restored.posterior_source_weights,
            model.posterior_source_weights,
        )
        self.assertEqual(
            restored.effective_source_weights,
            model.effective_source_weights,
        )
        self.assertEqual(
            restored.peek(self.context, self.action),
            model.peek(self.context, self.action),
        )

    def test_snapshot_rejects_tampering_and_pending_state(self) -> None:
        model = self._model(fallback=True)
        payload = json.loads(model.to_snapshot())
        payload["derived"]["fallback_cell_rate"] = 1.0
        with self.assertRaises(ValidationError):
            CellwiseGatedTransferModel.from_snapshot(json.dumps(payload))
        model.forecast(self.context, self.action)
        with self.assertRaises(ValidationError):
            model.to_snapshot()

    def test_invalid_configuration_and_sequence_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            CellwiseGatedTransferModel(
                world_id="cellwise-test-world",
                source_prior=self.source_prior,
                initial_source_weight=0.5,
                scratch_fallback="yes",  # type: ignore[arg-type]
            )
        model = self._model(fallback=True)
        with self.assertRaises(ValidationError):
            model.observe(
                TransferObservation(
                    world_id="cellwise-test-world",
                    index=0,
                    context=self.context,
                    action=self.action,
                    next_observation=True,
                    reward=True,
                )
            )


if __name__ == "__main__":
    unittest.main()
