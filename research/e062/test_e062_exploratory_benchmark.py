"""Standard library tests for the *independent* E062 toy simulator."""
from __future__ import annotations

import unittest
from dataclasses import fields
from fractions import Fraction

from darwin_noisy_alignment_exact_reference import accuracy_by_maximum_likelihood
from e062_exploratory_benchmark import (
    BurstyWorld, CausalFilter, FixedWorld, JointModeOffsetFilter, Observation, brier, classify, digest, evaluate,
    normalize, transition, update, UNINFORMATIVE_CORRECT,
)


class ExactReferenceTests(unittest.TestCase):
    def test_exact_stationary_optimal_accuracy(self):
        self.assertEqual(accuracy_by_maximum_likelihood(0), Fraction(1, 3))
        self.assertEqual(accuracy_by_maximum_likelihood(1), Fraction(4, 5))
        self.assertEqual(accuracy_by_maximum_likelihood(2), Fraction(4, 5))
        self.assertEqual(accuracy_by_maximum_likelihood(3), Fraction(114, 125))
        self.assertEqual(accuracy_by_maximum_likelihood(5), Fraction(3004, 3125))

    def test_known_bayes_update(self):
        posterior = update((1/3, 1/3, 1/3), 0, .8)
        self.assertAlmostEqual(posterior[0], .8)
        self.assertAlmostEqual(posterior[1], .1)
        self.assertAlmostEqual(posterior[2], .1)

    def test_correct_hazard_prediction(self):
        predicted = transition((.8, .1, .1), .06)
        self.assertAlmostEqual(predicted[0], .758)
        self.assertAlmostEqual(predicted[1], .121)
        self.assertAlmostEqual(predicted[2], .121)

    def test_uninformative_sensor_does_not_change_belief(self):
        prior = (.758, .121, .121)
        for y in (1, 2, 0, 2, 1):
            after = update(prior, y, UNINFORMATIVE_CORRECT)
            self.assertTrue(all(abs(a-b) < 1e-14 for a, b in zip(prior, after)))
            prior = after


class CausalLineageTests(unittest.TestCase):
    def test_observation_exposes_no_hidden_state(self):
        self.assertEqual([field.name for field in fields(Observation)], ["sequence", "action_id", "cue"])

    def test_evidence_requires_matching_action(self):
        tracker = CausalFilter(hazard=.06, emission_correct=.8)
        tracker.begin_action("a")
        with self.assertRaises(ValueError):
            tracker.observe(Observation(1, "other", 0))
        tracker.observe(Observation(1, "a", 0))
        with self.assertRaises(ValueError):
            tracker.observe(Observation(2, "a", 1))

    def test_rejects_gaps_and_replays(self):
        tracker = CausalFilter(hazard=.06, emission_correct=.8)
        tracker.begin_action("a")
        with self.assertRaises(ValueError):
            tracker.observe(Observation(2, "a", 0))
        tracker.observe(Observation(1, "a", 0))
        tracker.begin_action("b")
        with self.assertRaises(ValueError):
            tracker.observe(Observation(1, "b", 1))
        tracker.observe(Observation(2, "b", 1))

    def test_no_concurrent_or_empty_actions(self):
        tracker = CausalFilter(hazard=.06, emission_correct=.8)
        with self.assertRaises(ValueError):
            tracker.begin_action("")
        tracker.begin_action("a")
        with self.assertRaises(ValueError):
            tracker.begin_action("b")
        with self.assertRaises(ValueError):
            tracker.snapshot()

    def test_deterministic_one_observation_exact(self):
        for r in (0, 1, 2):
            tracker = CausalFilter(hazard=.06, emission_correct=1.)
            tracker.begin_action(f"a{r}")
            belief = tracker.observe(Observation(1, f"a{r}", r))
            self.assertEqual(classify(belief), r)
            self.assertEqual(belief[r], 1.)

    def test_shifted_evidence_is_negative_control(self):
        tracker = CausalFilter(hazard=.06, emission_correct=1., shifted_cue=1)
        tracker.begin_action("a")
        belief = tracker.observe(Observation(1, "a", 0))
        self.assertEqual(classify(belief), 1)

    def test_snapshot_replay_and_tamper_detection(self):
        tracker = CausalFilter(hazard=.06, emission_correct=.8)
        for t, cue in enumerate((0, 2, 0, 1, 0), 1):
            action = f"action-{t}"
            tracker.begin_action(action)
            tracker.observe(Observation(t, action, cue))
        snapshot = tracker.snapshot()
        self.assertEqual(snapshot, CausalFilter.replay(snapshot).snapshot())
        snapshot["content"]["archive"][1]["cue"] = 1
        with self.assertRaises(ValueError):
            CausalFilter.replay(snapshot)

    def test_recomputed_checksum_does_not_bypass_replay(self):
        tracker = CausalFilter(hazard=.06, emission_correct=.8)
        tracker.begin_action("a")
        tracker.observe(Observation(1, "a", 0))
        snapshot = tracker.snapshot()
        snapshot["content"]["belief"][0] = .4
        snapshot["sha256"] = digest(snapshot["content"])
        with self.assertRaises(ValueError):
            CausalFilter.replay(snapshot)

    def test_same_prefix_independent_of_future(self):
        a = CausalFilter(hazard=.06, emission_correct=.8)
        b = CausalFilter(hazard=.06, emission_correct=.8)
        for t, cue in enumerate((0, 1, 0), 1):
            for tracker in (a, b):
                tracker.begin_action(str(t))
                tracker.observe(Observation(t, str(t), cue))
        self.assertEqual(a.snapshot(), b.snapshot())
        b.begin_action("4")
        b.observe(Observation(4, "4", 2))
        self.assertEqual(len(a.archive), 3)

    def test_joint_filter_matches_markov_under_iid_noise(self):
        independent = CausalFilter(hazard=.06, emission_correct=.8)
        joint = JointModeOffsetFilter(hazard=.06, emission_correct=.8, persistence=0.)
        for i, cue in enumerate((0, 1, 0, 2, 2, 0, 1, 0), 1):
            name = f"action-{i}"
            a = independent.begin_action(name)
            b = joint.begin_action(name)
            self.assertTrue(all(abs(x-y)<1e-12 for x, y in zip(a,b)))
            a = independent.observe(Observation(i, name, cue))
            b = joint.observe(Observation(i, name, cue))
            self.assertTrue(all(abs(x-y)<1e-12 for x, y in zip(a,b)))

    def test_joint_snapshot_replay_and_detection(self):
        tracker = JointModeOffsetFilter(hazard=.06, emission_correct=.8, persistence=.85)
        for i, cue in enumerate((0, 2, 0, 0, 2), 1):
            tracker.begin_action(str(i))
            tracker.observe(Observation(i, str(i), cue))
        snapshot = tracker.snapshot()
        self.assertEqual(snapshot, JointModeOffsetFilter.replay(snapshot).snapshot())
        snapshot["content"]["joint"][0][0] = .75
        snapshot["sha256"] = digest(snapshot["content"])
        with self.assertRaises(ValueError):
            JointModeOffsetFilter.replay(snapshot)

    def test_bursty_noise_reproducibility(self):
        a = BurstyWorld(seed=54321, steps=100, hazard=.06, emission_correct=.8, persistence=.85)
        b = BurstyWorld(seed=54321, steps=100, hazard=.06, emission_correct=.8, persistence=.85)
        self.assertEqual([a.step(str(i)) for i in range(100)], [b.step(str(i)) for i in range(100)])

    def test_generation_is_reproducible(self):
        a = FixedWorld(seed=54321, steps=100, hazard=.06, emission_correct=.8)
        b = FixedWorld(seed=54321, steps=100, hazard=.06, emission_correct=.8)
        self.assertEqual([a.step(str(i)) for i in range(100)], [b.step(str(i)) for i in range(100)])

    def test_float_roundoff_does_not_break_uniform_tie(self):
        self.assertEqual(classify((1/3, 1/3, 1/3 + 3e-16)), 0)
        self.assertEqual(classify((.1, .8000000000001, .1)), 1)

    def test_uniform_brier(self):
        self.assertAlmostEqual(brier((1/3, 1/3, 1/3), 2), 2/3)

    def test_rejects_impossible_mass(self):
        with self.assertRaises(ValueError):
            normalize((0., 0., 0.))

    def test_smoke_runs_without_darwin_import(self):
        result = evaluate(seeds=(62000, 62001), steps=8)
        self.assertEqual(result["status"], "EXPLORATORY_ONLY_NO_DARWIN_KERNEL_TESTED")
        self.assertTrue(result["conditions"]["informative_iid"]["all_replays_exact"])
        self.assertTrue(result["conditions"]["uninformative_iid"]["all_replays_exact"])
        self.assertTrue(result["conditions"]["correlated_error_stress"]["all_replays_exact"])


if __name__ == "__main__":
    unittest.main()
