"""E063 engineering admission checks; no maintained v50 kernel is invoked."""
from __future__ import annotations

import json
import math
import random
import unittest

from darwin_v50.noisy_alignment_lab import (
    NoisyAlignmentBelief,
    NoisyCue,
    _digest,
)


class NoisyAlignmentEngineeringTests(unittest.TestCase):
    def make_filter(self, hazard: float = 0.06, sensor_correct: float = 0.8):
        return NoisyAlignmentBelief(hazard=hazard, sensor_correct=sensor_correct)

    def accept(self, tracker: NoisyAlignmentBelief, action_id: str, cue: int) -> None:
        tracker.register_dispatch(action_id)
        tracker.observe(NoisyCue(len(tracker.archive) + 1, action_id, cue))

    def test_initial_prior_is_uniform_and_no_mode_is_asserted(self):
        tracker = self.make_filter()
        self.assertEqual(tracker.posterior, (1 / 3,) * 3)
        self.assertFalse(hasattr(tracker, "current_rotation"))
        self.assertEqual(tracker.prediction(), tracker.posterior)

    def test_one_observation_matches_exact_bayes(self):
        tracker = self.make_filter()
        self.accept(tracker, "dispatch-a", 1)
        for actual, expected in zip(tracker.posterior, (0.1, 0.8, 0.1)):
            self.assertAlmostEqual(actual, expected)

    def test_prediction_uses_declared_change_hazard(self):
        tracker = self.make_filter(hazard=0.06)
        self.accept(tracker, "dispatch-a", 1)
        prior = tracker.prediction()
        self.assertAlmostEqual(prior[1], 0.8 * 0.94 + 0.2 * 0.03)
        self.assertAlmostEqual(prior[0], 0.1 * 0.94 + 0.9 * 0.03)

    def test_two_symmetric_cues_leave_an_exact_near_tie(self):
        tracker = self.make_filter(hazard=0)
        self.accept(tracker, "dispatch-a", 0)
        self.accept(tracker, "dispatch-b", 1)
        self.assertAlmostEqual(tracker.posterior[0], tracker.posterior[1], places=12)
        self.assertGreater(tracker.posterior[0], tracker.posterior[2])

    def test_uninformative_sensor_remains_uniform(self):
        tracker = self.make_filter(sensor_correct=1 / 3)
        for n, cue in enumerate((0, 2, 1, 1, 2, 0), 1):
            self.accept(tracker, f"dispatch-{n}", cue)
            for p in tracker.posterior:
                self.assertAlmostEqual(p, 1 / 3)

    def test_known_certain_observation_and_contradiction(self):
        tracker = self.make_filter(hazard=0, sensor_correct=1)
        self.accept(tracker, "dispatch-a", 2)
        self.assertEqual(tracker.posterior, (0.0, 0.0, 1.0))
        tracker.register_dispatch("dispatch-b")
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.observe(NoisyCue(2, "dispatch-b", 0))
        self.assertEqual(tracker.snapshot(), before)

    def test_invalid_model_probabilities_are_rejected(self):
        for value in (-0.1, 1.1, 10 ** 500, float("nan"), float("inf"), -float("inf"), True, None, "0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.make_filter(hazard=value)
        for value in (-1, 0, 0.32, 1.1, 10 ** 500, float("nan"), float("inf"), False, "0.8"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.make_filter(sensor_correct=value)

    def test_valid_boundary_model_probabilities(self):
        self.make_filter(hazard=0, sensor_correct=1 / 3)
        self.make_filter(hazard=1, sensor_correct=1)

    def test_invalid_observation_payloads(self):
        for sequence in (0, -1, 1.0, True, "1"):
            with self.subTest(seq=sequence), self.assertRaises(ValueError):
                NoisyCue(sequence, "id", 0)
        for cue in (-1, 3, 0.0, True, None):
            with self.subTest(cue=cue), self.assertRaises(ValueError):
                NoisyCue(1, "id", cue)
        for name in (None, "", "  ", 3):
            with self.subTest(name=name), self.assertRaises(ValueError):
                NoisyCue(1, name, 1)

    def test_missing_dispatch_is_rejected_without_state_change(self):
        tracker = self.make_filter()
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.observe(NoisyCue(1, "unregistered", 0))
        self.assertEqual(tracker.snapshot(), before)

    def test_wrong_action_is_rejected_without_state_change(self):
        tracker = self.make_filter()
        tracker.register_dispatch("one")
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.observe(NoisyCue(1, "two", 0))
        self.assertEqual(tracker.snapshot(), before)

    def test_out_of_order_observation_is_atomic(self):
        tracker = self.make_filter()
        tracker.register_dispatch("one")
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.observe(NoisyCue(2, "one", 0))
        self.assertEqual(tracker.snapshot(), before)
        self.assertEqual(tracker.pending_action, "one")

    def test_dispatch_is_not_accepted_twice_concurrently(self):
        tracker = self.make_filter()
        tracker.register_dispatch("one")
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.register_dispatch("two")
        self.assertEqual(tracker.snapshot(), before)

    def test_duplicate_action_id_cannot_be_reused(self):
        tracker = self.make_filter()
        self.accept(tracker, "one", 0)
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.register_dispatch("one")
        self.assertEqual(tracker.snapshot(), before)

    def test_empty_action_id_is_rejected(self):
        tracker = self.make_filter()
        for name in ("", "  ", None, 42):
            with self.subTest(name=name), self.assertRaises(ValueError):
                tracker.register_dispatch(name)

    def test_non_cue_object_is_rejected_atomically(self):
        tracker = self.make_filter()
        tracker.register_dispatch("one")
        before = tracker.snapshot()
        with self.assertRaises(ValueError):
            tracker.observe({"sequence": 1, "action_id": "one", "cue": 0})
        self.assertEqual(tracker.snapshot(), before)

    def test_snapshot_round_trip_after_observation(self):
        tracker = self.make_filter()
        for n, cue in enumerate((0, 1, 1, 2, 0), 1):
            self.accept(tracker, f"one-{n}", cue)
        replay = NoisyAlignmentBelief.from_snapshot(tracker.snapshot())
        self.assertEqual(replay.snapshot(), tracker.snapshot())
        self.assertEqual(replay.archive, tracker.archive)

    def test_snapshot_replays_outstanding_dispatch(self):
        tracker = self.make_filter()
        self.accept(tracker, "one", 0)
        tracker.register_dispatch("two")
        replay = NoisyAlignmentBelief.from_snapshot(tracker.snapshot())
        self.assertEqual(replay.pending_action, "two")
        replay.observe(NoisyCue(2, "two", 1))
        tracker.observe(NoisyCue(2, "two", 1))
        self.assertEqual(replay.snapshot(), tracker.snapshot())

    def test_snapshot_digest_detects_accidental_corruption(self):
        tracker = self.make_filter()
        self.accept(tracker, "one", 0)
        document = json.loads(tracker.snapshot())
        document["body"]["archive"][0]["cue"] = 2
        with self.assertRaises(ValueError):
            NoisyAlignmentBelief.from_snapshot(json.dumps(document))

    def test_recomputed_digest_does_not_bypass_replay_inconsistency(self):
        tracker = self.make_filter()
        self.accept(tracker, "one", 0)
        document = json.loads(tracker.snapshot())
        document["body"]["archive"][0]["cue"] = 2
        document["sha256"] = _digest(document["body"])
        with self.assertRaises(ValueError):
            NoisyAlignmentBelief.from_snapshot(json.dumps(document))

    def test_duplicate_and_missing_sequences_in_archive_are_rejected(self):
        tracker = self.make_filter()
        self.accept(tracker, "one", 0)
        self.accept(tracker, "two", 1)
        for sequence in (1, 3):
            document = json.loads(tracker.snapshot())
            document["body"]["archive"][1]["sequence"] = sequence
            document["sha256"] = _digest(document["body"])
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                NoisyAlignmentBelief.from_snapshot(json.dumps(document))

    def test_replay_rejects_schema_and_extra_fields(self):
        tracker = self.make_filter()
        for change in ("schema", "extra", "observation_extra"):
            document = json.loads(tracker.snapshot())
            if change == "schema":
                document["body"]["schema"] = "old-or-unknown"
            elif change == "extra":
                document["body"]["hidden_mode"] = 2
            else:
                self.accept(tracker, "first" if not tracker.archive else "second", 0)
                document = json.loads(tracker.snapshot())
                document["body"]["archive"][0]["true_rotation"] = 0
            document["sha256"] = _digest(document["body"])
            with self.subTest(change=change), self.assertRaises(ValueError):
                NoisyAlignmentBelief.from_snapshot(json.dumps(document))

    def test_replay_rejects_non_finite_or_malformed_fields(self):
        tracker = self.make_filter()
        for name, invalid in (("posterior", [float("nan"), 0, 1]), ("hazard", -1), ("archive", {})):
            document = json.loads(tracker.snapshot())
            document["body"][name] = invalid
            if name != "posterior":
                document["sha256"] = _digest(document["body"])
            with self.subTest(name=name), self.assertRaises(ValueError):
                NoisyAlignmentBelief.from_snapshot(json.dumps(document))

    def test_observation_fields_do_not_expose_hidden_mode(self):
        self.assertEqual(set(NoisyCue(1, "one", 2).to_dict()), {"sequence", "action_id", "cue"})

    def test_posterior_is_not_exposed_as_mutable_state(self):
        tracker = self.make_filter()
        self.assertIsInstance(tracker.posterior, tuple)
        self.assertIsInstance(tracker.archive, tuple)
        with self.assertRaises(AttributeError):
            tracker.posterior = (1, 0, 0)

    def test_randomized_observations_stay_normalized(self):
        rng = random.Random(63063)
        tracker = self.make_filter(hazard=0.09, sensor_correct=0.73)
        for n in range(1, 257):
            self.accept(tracker, f"random-{n}", rng.randrange(3))
            self.assertTrue(all(math.isfinite(p) and 0 <= p <= 1 for p in tracker.posterior))
            self.assertAlmostEqual(sum(tracker.posterior), 1)
        self.assertEqual(NoisyAlignmentBelief.from_snapshot(tracker.snapshot()).snapshot(), tracker.snapshot())

    def test_updates_only_use_observed_prefix(self):
        observations = [0, 2, 1, 1, 2, 0, 1, 2]
        short = self.make_filter()
        long = self.make_filter()
        for n, cue in enumerate(observations[:4], 1):
            self.accept(short, f"prefix-{n}", cue)
        for n, cue in enumerate(observations, 1):
            self.accept(long, f"prefix-{n}", cue)
            if n == 4:
                self.assertEqual(short.posterior, long.posterior)

    def test_independent_single_step_reference(self):
        tracker = self.make_filter(hazard=0.2, sensor_correct=0.7)
        self.accept(tracker, "a", 2)
        self.accept(tracker, "b", 0)
        predicted = tuple(0.8 * x + 0.1 * (1 - x) for x in (0.15, 0.15, 0.70))
        weights = tuple(predicted[r] * (0.7 if r == 0 else 0.15) for r in range(3))
        expected = tuple(w / sum(weights) for w in weights)
        for actual, reference in zip(tracker.posterior, expected):
            self.assertAlmostEqual(actual, reference)


if __name__ == "__main__":
    unittest.main()
