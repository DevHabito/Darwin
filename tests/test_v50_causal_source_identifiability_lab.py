"""E066 local engineering tests; full registered enumeration lives in runner."""
from __future__ import annotations

import unittest
from fractions import Fraction as F
from itertools import product

from darwin_v50.causal_source_identifiability_lab import (
    A, B, C, D, convolution, effective_hazard, joint_likelihood,
    kernel, observable_likelihood, paired_witness,
)


class CausalSourceIdentifiabilityTests(unittest.TestCase):
    def test_exact_world_increment_kernel(self) -> None:
        self.assertEqual(kernel(F(1, 8)), (F(7, 8), F(1, 16), F(1, 16)))
        self.assertEqual(sum(kernel(F(1, 8))), 1)

    def test_both_zero_kernels_are_identity(self) -> None:
        self.assertEqual(convolution(0, 0), (1, 0, 0))

    def test_independent_convolution_formula_exact(self) -> None:
        self.assertEqual(convolution(F(1, 10), F(1, 6)), kernel(F(29, 120)))

    def test_hazard_zero_and_one_bounds(self) -> None:
        self.assertEqual(kernel(0), (1, 0, 0))
        self.assertEqual(kernel(1), (0, F(1, 2), F(1, 2)))

    def test_invalid_hazard_types_fail_closed(self) -> None:
        for h in (True, False, 0.5, "1/2", None, float('nan'), float('inf')):
            with self.subTest(h=h), self.assertRaises(ValueError):
                kernel(h)

    def test_invalid_hazard_range_fails_closed(self) -> None:
        for h in (-1, F(-1, 10), F(11, 10), 2):
            with self.subTest(h=h), self.assertRaises(ValueError):
                effective_hazard(h, 0)

    def test_effective_hazard_is_symmetric(self) -> None:
        for h in (0, F(1, 8), F(2, 3), 1):
            for s in (0, F(1, 3), 1):
                self.assertEqual(effective_hazard(h, s), effective_hazard(s, h))
                self.assertEqual(convolution(h, s), kernel(effective_hazard(h, s)))

    def test_frozen_equivalence_pairs_exact(self) -> None:
        self.assertNotEqual(A, B)
        self.assertNotEqual(C, D)
        self.assertEqual(effective_hazard(*A), F(1, 8))
        self.assertEqual(effective_hazard(*C), F(29, 120))
        self.assertEqual(effective_hazard(*A), effective_hazard(*B))
        self.assertEqual(effective_hazard(*C), effective_hazard(*D))

    def test_initial_observation_is_uniform(self) -> None:
        for cue in (0, 1, 2):
            self.assertEqual(observable_likelihood((cue,), *A), F(1, 3))
            self.assertEqual(joint_likelihood((cue,), *B), F(1, 3))

    def test_joint_and_observed_likelihood_agree_on_short_traces(self) -> None:
        for history in ((0, 0, 0), (1, 2, 0), (2, 1, 2), (0, 2, 0)):
            for world in (A, B, C, D):
                self.assertEqual(joint_likelihood(history, *world),
                                 observable_likelihood(history, *world))

    def test_short_histories_normalize(self) -> None:
        for world in (A, B, C, D):
            for length in (1, 2, 3):
                total = sum((observable_likelihood(seq, *world)
                             for seq in product(range(3), repeat=length)), F(0))
                self.assertEqual(total, 1)

    def test_observable_pairs_equal_on_short_histories(self) -> None:
        for history in ((0, 0), (0, 1), (1, 2, 0), (2, 0, 2)):
            self.assertEqual(observable_likelihood(history, *A),
                             observable_likelihood(history, *B))
            self.assertEqual(observable_likelihood(history, *C),
                             observable_likelihood(history, *D))

    def test_cue_input_validation(self) -> None:
        for history in ((), [], (3,), (-1,), (True,), (0.0,), ('1',),
                        (0, None), (0, 3), '012', None, {0: 1}):
            with self.subTest(history=history), self.assertRaises(ValueError):
                observable_likelihood(history, *A)

    def test_cue_validation_joint_reference(self) -> None:
        for history in ((True,), (-1,), [], None):
            with self.subTest(history=history), self.assertRaises(ValueError):
                joint_likelihood(history, *A)

    def test_witness_has_exact_same_visible_trace(self) -> None:
        history = (0, 1, 2, 1, 1, 0)
        witness = paired_witness(history)
        self.assertEqual(witness['observed'], history)
        self.assertEqual(witness['world_only']['R'], history)
        self.assertEqual(witness['world_only']['O'], (0,) * len(history))
        self.assertEqual(witness['sensor_only']['R'], (0,) * len(history))
        self.assertNotEqual(witness['world_only']['R'], witness['sensor_only']['R'])
        self.assertEqual(witness['observed_changes'], 4)

    def test_witness_support_is_positive_under_both_worlds(self) -> None:
        history = (0, 1, 2, 1, 1, 0)
        self.assertGreater(joint_likelihood(history, *A), 0)
        self.assertEqual(joint_likelihood(history, *A), joint_likelihood(history, *B))

    def test_trusted_world_anchor_breaks_equivalence(self) -> None:
        history = (0, 1, 1, 2)
        self.assertEqual(joint_likelihood(history, *A, anchors={2: 0}), 0)
        self.assertGreater(joint_likelihood(history, *B, anchors={2: 0}), 0)

    def test_compatible_world_anchor_is_allowed(self) -> None:
        history = (0, 1, 1, 2)
        self.assertEqual(joint_likelihood(history, *A, anchors={2: 1}),
                         joint_likelihood(history, *A))

    def test_anchor_at_initial_time(self) -> None:
        history = (0, 1, 1)
        self.assertEqual(joint_likelihood(history, *A, anchors={0: 1}), 0)
        self.assertEqual(joint_likelihood(history, *B, anchors={0: 0}),
                         joint_likelihood(history, *B))

    def test_invalid_anchor_map_rejected(self) -> None:
        history = (0, 1, 1)
        for anchor in ({3: 0}, {-1: 0}, {True: 0}, {0.0: 0},
                       {0: True}, {0: 3}, {0: -1}, {'0': 0},
                       [], 'not-an-anchor'):
            with self.subTest(anchor=anchor), self.assertRaises(ValueError):
                joint_likelihood(history, *A, anchors=anchor)

    def test_full_trace_probability_nonnegative(self) -> None:
        for history in ((0, 1, 1, 0, 2), (2, 2, 0, 1, 1)):
            for world in (A, B, C, D):
                self.assertGreaterEqual(joint_likelihood(history, *world), 0)
                self.assertGreaterEqual(observable_likelihood(history, *world), 0)


if __name__ == '__main__':
    unittest.main()
