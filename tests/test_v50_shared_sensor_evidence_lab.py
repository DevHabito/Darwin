"""Engineering checks frozen before E068 registered enumeration."""
from __future__ import annotations

from fractions import Fraction
import inspect
import unittest

from darwin_v50.shared_sensor_evidence_lab import (
    MODES, emission, pair_likelihood, visible_pair_probability,
    source_posterior, single_sensor_posterior, agreement_probability,
    multiclass_brier,
)


class SharedSensorEvidenceTests(unittest.TestCase):
    Q = Fraction(4, 5)
    ALPHA = Fraction(3, 4)

    def test_one_sensor_reliability(self):
        self.assertEqual(emission(self.Q, truth=0, observed=0), self.Q)
        self.assertEqual(emission(self.Q, truth=0, observed=1), Fraction(1, 10))

    def test_pair_conditional_copy_event(self):
        self.assertEqual(
            pair_likelihood(self.Q, 1, truth=0, first=1, second=1), Fraction(1, 10)
        )
        self.assertEqual(
            pair_likelihood(self.Q, 1, truth=0, first=1, second=0), 0
        )

    def test_declared_pair_law_is_normalized_per_hidden_state(self):
        for r in MODES:
            total = sum(
                (pair_likelihood(self.Q, self.ALPHA,
                                 truth=r, first=i, second=j)
                 for i in MODES for j in MODES),
                Fraction(0),
            )
            self.assertEqual(total, 1)

    def test_posterior_uniform_when_reliability_is_third(self):
        for a in (0, self.ALPHA):
            self.assertEqual(source_posterior(1, 2, reliability=Fraction(1, 3),
                                              copy_probability=a), (Fraction(1, 3),) * 3)

    def test_posterior_uses_exact_fractions(self):
        actual = source_posterior(0, 0, reliability=self.Q,
                                  copy_probability=self.ALPHA)
        self.assertEqual(actual, (Fraction(152, 183), Fraction(31, 366), Fraction(31, 366)))
        self.assertEqual(sum(actual), 1)
        self.assertTrue(all(type(x) is Fraction for x in actual))

    def test_posterior_rejects_impossible_pair(self):
        with self.assertRaises(ValueError):
            source_posterior(0, 1, reliability=1, copy_probability=1)

    def test_fully_duplicated_sensor_is_single_evidence(self):
        self.assertEqual(source_posterior(2, 2, reliability=self.Q,
                                          copy_probability=1),
                         single_sensor_posterior(2, reliability=self.Q))

    def test_independent_case_is_product_of_emissions(self):
        self.assertEqual(pair_likelihood(self.Q, 0, truth=2, first=0, second=1),
                         Fraction(1, 100))

    def test_agreement_formula_spot_check(self):
        self.assertEqual(agreement_probability(reliability=self.Q,
                                              copy_probability=self.ALPHA),
                         Fraction(183, 200))

    def test_confounded_model_has_same_agreement(self):
        self.assertEqual(agreement_probability(reliability=Fraction(19, 20),
                                              copy_probability=Fraction(9, 77)),
                         Fraction(183, 200))

    def test_visible_pair_symmetry(self):
        self.assertEqual(visible_pair_probability(0, 1, reliability=self.Q,
                                                  copy_probability=self.ALPHA),
                         visible_pair_probability(2, 1, reliability=self.Q,
                                                  copy_probability=self.ALPHA))

    def test_source_posterior_signature_does_not_accept_hidden_truth(self):
        self.assertEqual(set(inspect.signature(source_posterior).parameters),
                         {"first", "second", "reliability", "copy_probability"})

    def test_brier_perfect(self):
        self.assertEqual(multiclass_brier((Fraction(1), Fraction(0), Fraction(0)), truth=0), 0)

    def test_brier_uniform(self):
        self.assertEqual(multiclass_brier((Fraction(1, 3),) * 3, truth=2), Fraction(2, 3))

    def test_brier_rejects_bad_probabilities(self):
        for posterior in ((.5, .5, 0), (Fraction(1), Fraction(1), Fraction(0)),
                          (Fraction(-1), Fraction(1), Fraction(1))):
            with self.subTest(posterior=posterior), self.assertRaises(ValueError):
                multiclass_brier(posterior, truth=0)

    def test_reliability_rejects_nonexact_inputs(self):
        for value in (0, Fraction(1, 4), Fraction(101, 100), 0.8, "0.8", True,
                      False, None, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                source_posterior(0, 0, reliability=value, copy_probability=0)

    def test_copy_probability_rejects_nonexact_inputs(self):
        for value in (-1, Fraction(-1, 100), Fraction(101, 100), 0.75,
                      "0.75", True, None, float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                source_posterior(0, 0, reliability=self.Q, copy_probability=value)

    def test_rejects_invalid_truth_and_readings(self):
        for value in (-1, 3, 0.0, True, None, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                emission(self.Q, truth=value, observed=0)
            with self.subTest(value=value), self.assertRaises(ValueError):
                source_posterior(value, 0, reliability=self.Q,
                                 copy_probability=self.ALPHA)

    def test_zero_mass_pair_rejected(self):
        with self.assertRaises(ValueError):
            source_posterior(1, 2, reliability=1, copy_probability=0)

    def test_single_sensor_posterior_is_normalized(self):
        self.assertEqual(sum(single_sensor_posterior(1, reliability=self.Q)), 1)


if __name__ == '__main__':
    unittest.main()
