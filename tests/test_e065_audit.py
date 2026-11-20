"""Engineering checks before registered E065 samples are generated."""
from __future__ import annotations

import unittest
from research.e065.e065_audit import generate_trace, score_trace
from darwin_v50.reliability_identifiability_lab import estimate_symmetric_sensor


class CorrelatedSensorAuditTests(unittest.TestCase):
    def test_reproducibility_on_nonregistered_seed(self):
        self.assertEqual(generate_trace(64995,64,.6),generate_trace(64995,64,.6))

    def test_generator_lengths_and_domain(self):
        trace=generate_trace(64995,64,.6)
        self.assertEqual(len(trace.cues),64)
        self.assertEqual(len(trace.hidden),64)
        self.assertTrue(set(trace.cues)<=set(range(3)))
        self.assertTrue(set(trace.hidden)<=set(range(3)))

    def test_invalid_generator_rejected(self):
        for rho in (-1,1,2):
            with self.assertRaises(ValueError): generate_trace(64995,64,rho)

    def test_cues_only_fit_on_development_seed(self):
        trace=generate_trace(64995,512,0)
        fit=estimate_symmetric_sensor([trace.cues])
        self.assertEqual(len(fit.pair_counts),3)

    def test_prefix_e063_scoring_is_finite(self):
        trace=generate_trace(64995,64,.6)
        scores=score_trace(64995,trace,.15,.85)
        self.assertEqual(set(scores),{'fitted','iid_oracle_parameters','last_cue'})
        self.assertTrue(all(0 <= x <= 2 for x in scores.values()))


if __name__=='__main__': unittest.main()
