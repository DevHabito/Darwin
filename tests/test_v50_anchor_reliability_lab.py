"""E067 focused engineering checks; registered full enumeration is separate."""
from __future__ import annotations

from fractions import Fraction
import unittest

from darwin_v50.anchor_reliability_lab import (
    SourcePosterior, anchor_likelihood, infer_source,
)
from darwin_v50.causal_source_identifiability_lab import (
    A, B, joint_likelihood,
)


class AnchorReliabilityUnitTests(unittest.TestCase):
    def test_uninformative_anchor_leaves_equal_sources(self):
        self.assertEqual(infer_source((0, 1, 2, 0, 1), 1, Fraction(1, 3)).world, Fraction(1, 2))

    def test_anchored_world_observation_prefers_world(self):
        result = infer_source((0, 2, 1, 1, 2), 2, Fraction(4, 5))
        self.assertEqual((result.world, result.sensor), (Fraction(8, 9), Fraction(1, 9)))
        self.assertEqual(result.select(), "WORLD")

    def test_anchored_sensor_observation_prefers_sensor(self):
        result = infer_source((0, 2, 1, 1, 2), 0, Fraction(4, 5))
        self.assertEqual(result.world, Fraction(1, 9))
        self.assertEqual(result.select(), "SENSOR")

    def test_third_symbol_abstains(self):
        result = infer_source((0, 1, 2, 2, 1), 2, Fraction(4, 5))
        self.assertEqual(result.world, Fraction(1, 2))
        self.assertEqual(result.select(), "ABSTAIN")

    def test_no_signal_when_first_equals_last(self):
        result = infer_source((0, 1, 1, 2, 0), 0, Fraction(4, 5))
        self.assertEqual(result.world, Fraction(1, 2))
        self.assertEqual(result.select(), "ABSTAIN")

    def test_perfect_anchor_unmodelled_third_symbol(self):
        result = infer_source((0, 1, 2, 2, 1), 2, Fraction(1))
        self.assertEqual(result.status, "UNMODELLED")
        self.assertIsNone(result.world)
        self.assertEqual(result.select(), "ABSTAIN")

    def test_perfect_anchor_can_distinguish_compatible_world(self):
        result = infer_source((0, 1, 1, 1, 2), 2, Fraction(1))
        self.assertEqual(result.world, 1)
        self.assertEqual(result.select(), "WORLD")

    def test_float_is_rejected_even_at_valid_value(self):
        with self.assertRaises(ValueError):
            infer_source((0, 1, 0, 2, 1), 1, 0.8)

    def test_bool_rejected_as_anchor(self):
        with self.assertRaises(ValueError):
            infer_source((0, 1, 0, 2, 1), True, Fraction(4, 5))

    def test_bool_rejected_as_reliability(self):
        with self.assertRaises(ValueError):
            infer_source((0, 1, 0, 2, 1), 1, True)

    def test_fraction_below_one_third_rejected(self):
        with self.assertRaises(ValueError):
            infer_source((0, 1, 0, 2, 1), 1, Fraction(1, 4))

    def test_fraction_above_one_rejected(self):
        with self.assertRaises(ValueError):
            infer_source((0, 1, 0, 2, 1), 1, Fraction(5, 4))

    def test_invalid_cue_length_rejected(self):
        for bad in ((), (0,), (0, 1, 2, 1), (0, 1, 2, 1, 2, 0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                infer_source(bad, 0, Fraction(4, 5))

    def test_invalid_cue_type_rejected(self):
        for bad in ((0, 1, 2, 1, True), (0, 1, 2, 1, 3), (0, 1, 2, 1, 0.0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                infer_source(bad, 0, Fraction(4, 5))

    def test_invalid_anchor_type_rejected(self):
        for bad in (3, "0", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                infer_source((0, 1, 0, 2, 1), bad, Fraction(4, 5))

    def test_invalid_source_state_rejected(self):
        with self.assertRaises(ValueError):
            anchor_likelihood(0, 3, Fraction(4, 5))

    def test_input_not_mutated(self):
        cues = [0, 1, 0, 2, 1]
        before = cues[:]
        infer_source(cues, 1, Fraction(4, 5))
        self.assertEqual(cues, before)

    def test_global_permutation_invariance(self):
        history = (0, 1, 2, 1, 2)
        map_ = {0: 1, 1: 2, 2: 0}
        original = infer_source(history, 2, Fraction(4, 5))
        transformed = infer_source(tuple(map_[x] for x in history), map_[2], Fraction(4, 5))
        self.assertEqual(original, transformed)

    def test_prefix_not_future_dependent_for_fixed_five_cues(self):
        a = infer_source((0, 0, 0, 0, 1), 1, Fraction(4, 5))
        b = infer_source((0, 2, 1, 2, 1), 1, Fraction(4, 5))
        self.assertEqual(a, b)

    def test_select_rejects_invalid_threshold(self):
        posterior = infer_source((0, 0, 0, 0, 1), 1, Fraction(4, 5))
        for bad in (0.8, -1, Fraction(6, 5), True):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                posterior.select(bad)

    def test_high_threshold_abstains_instead_of_confident_claim(self):
        posterior = infer_source((0, 0, 0, 0, 1), 1, Fraction(4, 5))
        self.assertEqual(posterior.select(Fraction(9, 10)), "ABSTAIN")

    def test_one_independent_forward_reference(self):
        cues = (0, 2, 2, 1, 2)
        r = Fraction(4, 5)
        likelihoods = []
        for hazard_pair in (A, B):
            p = sum((joint_likelihood(cues, *hazard_pair, anchors={4: mode})
                     * anchor_likelihood(2, mode, r) for mode in (0, 1, 2)), Fraction(0))
            likelihoods.append(p)
        candidate = infer_source(cues, 2, r)
        self.assertEqual(candidate.world, likelihoods[0] / sum(likelihoods))
        self.assertEqual(candidate.sensor, likelihoods[1] / sum(likelihoods))

    def test_wrong_primitive_input_rejected(self):
        for bad in ("01201", 123, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                infer_source(bad, 0, Fraction(4, 5))

    def test_immutable_posterior(self):
        result = infer_source((0, 1, 0, 2, 1), 0, Fraction(4, 5))
        with self.assertRaises(AttributeError):
            result.world = Fraction(1)


if __name__ == "__main__":
    unittest.main()
