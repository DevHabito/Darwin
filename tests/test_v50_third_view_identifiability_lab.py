"""E069 implementation tests: exact fractions and hard inference boundaries."""
from __future__ import annotations

import unittest
from fractions import Fraction
from itertools import product

from darwin_v50.third_view_identifiability_lab import (
    A, B, MODES, ONE, ZERO, THIRD,
    _exact_probability, copied_triplet_likelihood,
    independent_triplet_likelihood, independent_triplet_posterior,
    sensor_emission,
)


class ThirdViewIdentifiabilityTests(unittest.TestCase):
    def test_models_are_exact_and_distinct(self):
        self.assertEqual(A, (Fraction(4, 5), Fraction(3, 4)))
        self.assertEqual(B, (Fraction(19, 20), Fraction(9, 77)))
        self.assertNotEqual(A, B)

    def test_sensor_emission_sums_exactly(self):
        for q in (THIRD, Fraction(4, 5), ONE):
            for truth in MODES:
                self.assertEqual(sum((sensor_emission(q, truth=truth, reading=r)
                                      for r in MODES), ZERO), ONE)

    def test_frozen_pair_law_agrees_across_models(self):
        for first, second in product(MODES, repeat=2):
            def pair_mass(model):
                return sum((independent_triplet_likelihood(
                    first, second, third, model=model, third_reliability=ONE)
                    for third in MODES), ZERO)
            self.assertEqual(pair_mass("A"), pair_mass("B"))

    def test_pair_agreement_183_over_200(self):
        total = sum((independent_triplet_likelihood(
            symbol, symbol, third, model="A", third_reliability=ONE)
            for symbol, third in product(MODES, repeat=2)), ZERO)
        self.assertEqual(total, Fraction(183, 200))

    def test_triplet_distribution_normalized_exactly(self):
        for model in ("A", "B"):
            for t in (THIRD, Fraction(4, 5), ONE):
                total = sum((independent_triplet_likelihood(
                    *triple, model=model, third_reliability=t)
                    for triple in product(MODES, repeat=3)), ZERO)
                self.assertEqual(total, ONE)

    def test_observer_never_has_a_source_label_argument(self):
        import inspect
        params = tuple(inspect.signature(independent_triplet_posterior).parameters)
        self.assertEqual(params, ("first", "second", "third", "third_reliability"))

    def test_posterior_exactly_normalized(self):
        for triple in product(MODES, repeat=3):
            posterior = independent_triplet_posterior(*triple)
            self.assertTrue(all(type(p) is Fraction for p in posterior))
            self.assertEqual(sum(posterior, ZERO), ONE)

    def test_posterior_matches_direct_bayes_ratio(self):
        for triple in product(MODES, repeat=3):
            a = independent_triplet_likelihood(
                *triple, model="A", third_reliability=Fraction(4, 5))
            b = independent_triplet_likelihood(
                *triple, model="B", third_reliability=Fraction(4, 5))
            self.assertEqual(independent_triplet_posterior(*triple),
                             (a/(a+b), b/(a+b)))

    def test_uniform_third_is_no_evidence(self):
        for triple in product(MODES, repeat=3):
            self.assertEqual(independent_triplet_posterior(
                *triple, third_reliability=THIRD), (Fraction(1, 2),)*2)

    def test_independent_view_distinguishes_two_hypotheses(self):
        self.assertNotEqual(
            independent_triplet_likelihood(0, 0, 0,
               model="A", third_reliability=Fraction(4, 5)),
            independent_triplet_likelihood(0, 0, 0,
               model="B", third_reliability=Fraction(4, 5)),
        )

    def test_copy_offdiagonal_is_exactly_zero(self):
        for first, second, third in product(MODES, repeat=3):
            if first != third:
                self.assertEqual(copied_triplet_likelihood(
                    first, second, third, model="A"), ZERO)

    def test_copy_distribution_normalized(self):
        for model in ("A", "B"):
            self.assertEqual(sum((copied_triplet_likelihood(
                *triple, model=model)
                for triple in product(MODES, repeat=3)), ZERO), ONE)

    def test_copy_cannot_distinguish_models(self):
        for triple in product(MODES, repeat=3):
            self.assertEqual(copied_triplet_likelihood(*triple, model="A"),
                             copied_triplet_likelihood(*triple, model="B"))

    def test_copy_can_falsely_look_informative_to_naive_model(self):
        self.assertNotEqual(independent_triplet_posterior(0, 0, 0),
                            (Fraction(1, 2), Fraction(1, 2)))

    def test_reject_invalid_readings(self):
        for item in (-1, 3, 0.0, True, "0", None):
            for position in range(3):
                args = [0, 1, 2]
                args[position] = item
                with self.subTest(item=item, position=position), self.assertRaises(ValueError):
                    independent_triplet_posterior(*args)

    def test_reject_invalid_third_reliability(self):
        for t in (None, True, 0.5, 0.2, -1, Fraction(4, 3), float("nan"), float("inf"), "0.8"):
            with self.subTest(t=t), self.assertRaises(ValueError):
                independent_triplet_posterior(0, 1, 2, third_reliability=t)

    def test_accept_fraction_boundary_reliabilities(self):
        independent_triplet_posterior(0, 0, 0, third_reliability=THIRD)
        independent_triplet_posterior(0, 0, 0, third_reliability=ONE)

    def test_reject_invalid_model_label(self):
        for label in ("C", "a", 0, False, None):
            with self.subTest(label=label), self.assertRaises(ValueError):
                independent_triplet_likelihood(0, 0, 0,
                    model=label, third_reliability=Fraction(4, 5))

    def test_copy_rejects_invalid_model_label(self):
        with self.assertRaises(ValueError):
            copied_triplet_likelihood(0, 0, 0, model="D")

    def test_positive_mass_for_supported_observations(self):
        for triple in product(MODES, repeat=3):
            self.assertGreater(independent_triplet_likelihood(
                *triple, model="A", third_reliability=Fraction(4, 5)), ZERO)

    def test_input_integer_is_not_implicitly_a_float_probability(self):
        self.assertEqual(_exact_probability(1, name="test", minimum=THIRD), ONE)
        with self.assertRaises(ValueError):
            _exact_probability(0, name="test", minimum=THIRD)


if __name__ == "__main__":
    unittest.main()
