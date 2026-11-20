"""Pre-evaluation E064 tests. No registered evaluation seeds are used."""

from __future__ import annotations

import inspect
import math
import random
import unittest

from darwin_v50.noisy_alignment_lab import NoisyAlignmentBelief, NoisyCue
from darwin_v50.reliability_identifiability_lab import (
    ReliabilityEstimate, _invert, estimate_symmetric_sensor,
    population_lag_equality,
)


class IdentifiabilityEngineeringTests(unittest.TestCase):
    def test_analytic_population_inversion(self):
        for hazard, q in ((0.08, .78), (.10, .6), (.001, .98), (.2, .8)):
            with self.subTest(hazard=hazard, q=q):
                first = population_lag_equality(hazard, q, 1)
                second = population_lag_equality(hazard, q, 2)
                fit = _invert(first, second)
                self.assertIsNotNone(fit)
                self.assertAlmostEqual(fit[0], hazard, places=10)
                self.assertAlmostEqual(fit[1], q, places=10)
                self.assertAlmostEqual(population_lag_equality(*fit, 3), population_lag_equality(hazard, q, 3))

    def test_memoryless_or_uninformative_is_not_identified(self):
        for hazard, q in ((.08, 1/3), (2/3, .78)):
            first = population_lag_equality(hazard, q, 1)
            second = population_lag_equality(hazard, q, 2)
            self.assertIsNone(_invert(first, second))

    def test_invalid_lag_or_probabilities(self):
        for args in ((.08, .78, 0), (.08, .78, 1.0), (float('nan'), .8, 1), (.08, float('inf'), 1), (-1, .8, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                population_lag_equality(*args)

    def test_input_rejection(self):
        for candidate in ([], (), '0012', [[0, 1, 2]], [[0, 1, 2, 3]], [[0, 1, 2, True]], [[0, 1, 2, 2.0]], [[0, 1, 2, '2']], [None]):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                estimate_symmetric_sensor(candidate)

    def test_observable_only_signature(self):
        self.assertEqual(tuple(inspect.signature(estimate_symmetric_sensor).parameters), ('sequences',))

    def test_pair_counts_do_not_join_segments(self):
        result = estimate_symmetric_sensor([[0, 1, 1, 2], [2, 2, 0, 1]])
        self.assertEqual(result.pair_counts, (6, 4, 2))

    def test_no_information_balanced_cues_abstain(self):
        result = estimate_symmetric_sensor([[0, 1, 2] * 1000])
        self.assertEqual(result.status, 'UNIDENTIFIABLE')
        self.assertIsNone(result.hazard)
        self.assertIsNone(result.sensor_correct)
        self.assertIsNone(result.lag3_absolute_gap)

    def test_permutation_invariance(self):
        rng = random.Random(63992)
        seq = [rng.randrange(3) for _ in range(2000)]
        a = estimate_symmetric_sensor([seq])
        b = estimate_symmetric_sensor([[{0:2,1:0,2:1}[cue] for cue in seq]])
        self.assertEqual(a, b)

    def test_lag3_diagnostic_is_defined_for_fitted_result(self):
        rates = tuple(population_lag_equality(.08,.78,lag) for lag in (1,2,3))
        e = ReliabilityEstimate('FITTED', .08, .78, rates, (100,99,98), rates[2])
        self.assertEqual(e.lag3_absolute_gap, 0.0)

    def test_invalid_empirical_inversion_fails_closed(self):
        for first, second in ((.5,.8), (.4,.2), (.9,.4), (1/3,1/3), (.99,.9)):
            with self.subTest(first=first,second=second):
                self.assertIsNone(_invert(first,second))

    def test_prefix_causal_e063_interface(self):
        belief = NoisyAlignmentBelief(hazard=.08, sensor_correct=.78)
        for index, cue in enumerate((1, 2, 0, 1, 1),1):
            action = f'synthetic-action-{index}'
            belief.register_dispatch(action)
            posterior = belief.observe(NoisyCue(index, action, cue))
            self.assertAlmostEqual(sum(posterior),1.0)
            self.assertTrue(all(math.isfinite(p) and 0 <= p <= 1 for p in posterior))
        self.assertEqual(len(belief.archive),5)

    def test_no_hidden_mode_in_estimator_output(self):
        self.assertEqual(set(ReliabilityEstimate.__dataclass_fields__),
            {'status','hazard','sensor_correct','equality_rates','pair_counts','predicted_lag3'})


if __name__ == '__main__':
    unittest.main()
