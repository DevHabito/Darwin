#!/usr/bin/env python3
"""Independent E062 exploration; DOES NOT import or run Darwin.

Finite-state causal observation simulation with fixed known transition and
sensor models. This is a mathematical baseline and a software regression
exercise, NOT a Darwin capability test, a confirmatory result or a live agent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODES = (0, 1, 2)
DEVELOPMENT_SEEDS = tuple(range(62000, 62128))
STEPS_PER_WORLD = 256
TRANSITION_HAZARD = 0.06
INFORMATIVE_CORRECT = 0.80
UNINFORMATIVE_CORRECT = 1.0 / 3.0
BURST_OFFSET_PERSISTENCE = 0.85
BOOTSTRAP_SEED = 62026
BOOTSTRAP_DRAWS = 2048


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def normalize(values: tuple[float, float, float]) -> tuple[float, float, float]:
    if len(values) != 3 or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("invalid likelihood or probability")
    total = sum(values)
    if total <= 0:
        raise ValueError("impossible observation under declared model")
    return tuple(x / total for x in values)  # type: ignore[return-value]


def transition(belief: tuple[float, float, float], hazard: float) -> tuple[float, float, float]:
    if not 0 <= hazard <= 1:
        raise ValueError("hazard outside [0, 1]")
    return normalize(tuple((1 - hazard) * belief[r] + (hazard / 2) * (1 - belief[r]) for r in MODES))


def update(belief: tuple[float, float, float], cue: int, correct_probability: float) -> tuple[float, float, float]:
    if cue not in MODES or not 1 / 3 <= correct_probability <= 1:
        raise ValueError("invalid sensor parameters")
    wrong = (1 - correct_probability) / 2
    return normalize(tuple(belief[r] * (correct_probability if r == cue else wrong) for r in MODES))


def classify(belief: tuple[float, float, float]) -> int:
    # Ties within a numerical tolerance are not independent evidence.
    # Otherwise, a uniform negative control can acquire a spurious label.
    high = max(belief)
    return min(r for r in MODES if high - belief[r] <= 1e-12)


@dataclass(frozen=True)
class Observation:
    sequence: int
    action_id: str
    cue: int

    def __post_init__(self) -> None:
        if self.sequence < 1 or self.cue not in MODES or not self.action_id:
            raise ValueError("invalid observation")


class CausalFilter:
    """Observations only, with strict sequence/action matching and replay."""

    def __init__(self, *, hazard: float, emission_correct: float, shifted_cue: int = 0) -> None:
        if shifted_cue not in MODES or not 0 <= hazard <= 1 or not 1 / 3 <= emission_correct <= 1:
            raise ValueError("invalid filter setup")
        self.hazard = hazard
        self.emission_correct = emission_correct
        self.shifted_cue = shifted_cue
        self.belief = (1 / 3, 1 / 3, 1 / 3)
        self.archive: list[Observation] = []
        self._pending: str | None = None

    def begin_action(self, action_id: str) -> tuple[float, float, float]:
        if self._pending is not None or not action_id:
            raise ValueError("action already pending or missing")
        self._pending = action_id
        if self.archive:
            self.belief = transition(self.belief, self.hazard)
        return self.belief

    def observe(self, observation: Observation) -> tuple[float, float, float]:
        if self._pending != observation.action_id:
            raise ValueError("no matching dispatched action")
        if observation.sequence != len(self.archive) + 1:
            raise ValueError("observation sequence is not contiguous")
        cue = (observation.cue + self.shifted_cue) % 3
        posterior = update(self.belief, cue, self.emission_correct)
        self.belief = posterior
        self.archive.append(observation)
        self._pending = None
        return posterior

    def snapshot(self) -> dict[str, Any]:
        if self._pending is not None:
            raise ValueError("refuse checkpoint with pending action")
        content = {
            "version": 1,
            "hazard": self.hazard,
            "emission_correct": self.emission_correct,
            "shifted_cue": self.shifted_cue,
            "belief": list(self.belief),
            "archive": [o.__dict__ for o in self.archive],
        }
        return {"content": content, "sha256": digest(content)}

    @classmethod
    def replay(cls, snapshot: dict[str, Any]) -> "CausalFilter":
        content = snapshot["content"]
        if digest(content) != snapshot["sha256"] or content["version"] != 1:
            raise ValueError("snapshot digest/contract mismatch")
        result = cls(
            hazard=content["hazard"],
            emission_correct=content["emission_correct"],
            shifted_cue=content["shifted_cue"],
        )
        for row in content["archive"]:
            observation = Observation(**row)
            result.begin_action(observation.action_id)
            result.observe(observation)
        if any(abs(a - b) > 1e-12 for a, b in zip(result.belief, content["belief"])):
            raise ValueError("replayed belief differs from recorded belief")
        return result


class JointModeOffsetFilter:
    """Exact nine-state filter for a KNOWN persistent sensor-offset model.

    This is a fully specified HMM reference, not an algorithm learned by Darwin.
    Both hidden mode and hidden sensor offset are kept in the posterior.
    """

    def __init__(self, *, hazard: float, emission_correct: float, persistence: float) -> None:
        if not 0 <= hazard <= 1 or not 1/3 <= emission_correct <= 1 or not 0 <= persistence < 1:
            raise ValueError("invalid joint-filter setup")
        self.hazard = hazard
        self.emission_correct = emission_correct
        self.persistence = persistence
        self.offset_prior = (emission_correct, (1 - emission_correct) / 2, (1 - emission_correct) / 2)
        self.joint = tuple(tuple((1/3)*self.offset_prior[e] for e in MODES) for r in MODES)
        self.archive: list[Observation] = []
        self._pending: str | None = None

    def marginal(self) -> tuple[float, float, float]:
        return normalize(tuple(sum(self.joint[r]) for r in MODES))

    def begin_action(self, action_id: str) -> tuple[float, float, float]:
        if self._pending is not None or not action_id:
            raise ValueError("action already pending or missing")
        self._pending = action_id
        if self.archive:
            next_joint = [[0.0]*3 for _ in MODES]
            for r in MODES:
                for e in MODES:
                    prior_mass = self.joint[r][e]
                    for nr in MODES:
                        pr = (1-self.hazard) if nr == r else self.hazard/2
                        for ne in MODES:
                            pe = self.persistence * (ne == e) + (1-self.persistence)*self.offset_prior[ne]
                            next_joint[nr][ne] += prior_mass * pr * pe
            total = sum(sum(row) for row in next_joint)
            self.joint = tuple(tuple(x/total for x in row) for row in next_joint)
        return self.marginal()

    def observe(self, observation: Observation) -> tuple[float, float, float]:
        if self._pending != observation.action_id:
            raise ValueError("no matching dispatched action")
        if observation.sequence != len(self.archive) + 1:
            raise ValueError("observation sequence is not contiguous")
        updated = [[self.joint[r][e] if (r+e) % 3 == observation.cue else 0.0 for e in MODES] for r in MODES]
        mass = sum(sum(row) for row in updated)
        if mass <= 0:
            raise ValueError("observation impossible under declared joint model")
        self.joint = tuple(tuple(x / mass for x in row) for row in updated)
        self.archive.append(observation)
        self._pending = None
        return self.marginal()

    def snapshot(self) -> dict[str, Any]:
        if self._pending is not None:
            raise ValueError("refuse checkpoint with pending action")
        content = {
            "version": 1,
            "hazard": self.hazard,
            "emission_correct": self.emission_correct,
            "persistence": self.persistence,
            "joint": [list(row) for row in self.joint],
            "archive": [o.__dict__ for o in self.archive],
        }
        return {"content": content, "sha256": digest(content)}

    @classmethod
    def replay(cls, snapshot: dict[str, Any]) -> "JointModeOffsetFilter":
        content = snapshot["content"]
        if digest(content) != snapshot["sha256"] or content["version"] != 1:
            raise ValueError("joint snapshot digest/contract mismatch")
        result = cls(
            hazard=content["hazard"],
            emission_correct=content["emission_correct"],
            persistence=content["persistence"],
        )
        for row in content["archive"]:
            obs = Observation(**row)
            result.begin_action(obs.action_id)
            result.observe(obs)
        for r in MODES:
            for e in MODES:
                if abs(result.joint[r][e] - content["joint"][r][e]) > 1e-12:
                    raise ValueError("replayed joint distribution mismatch")
        return result


class FixedWorld:
    """Evaluator-only state. Candidate receives Observation, never hidden mode."""

    def __init__(self, *, seed: int, steps: int, hazard: float, emission_correct: float) -> None:
        self.rng = random.Random(seed)
        self.steps = steps
        self.hazard = hazard
        self.emission_correct = emission_correct
        self.hidden_mode = self.rng.randrange(3)
        self.index = 0
        self.transition_count = 0

    def step(self, action_id: str) -> tuple[Observation, int]:
        if self.index >= self.steps:
            raise ValueError("world exhausted")
        if self.index > 0 and self.rng.random() < self.hazard:
            alternatives = [r for r in MODES if r != self.hidden_mode]
            self.hidden_mode = alternatives[self.rng.randrange(2)]
            self.transition_count += 1
        correct = self.rng.random() < self.emission_correct
        if correct:
            cue = self.hidden_mode
        else:
            alternatives = [r for r in MODES if r != self.hidden_mode]
            cue = alternatives[self.rng.randrange(2)]
        self.index += 1
        return Observation(self.index, action_id, cue), self.hidden_mode


class BurstyWorld(FixedWorld):
    """Synthetic correlated-error stress test with stationary offset marginals.

    The evaluator's additive sensor error persists with probability rho and
    otherwise resamples from {0: p, 1: (1-p)/2, 2: (1-p)/2}.
    The filter is deliberately unaware of the extra sensor state.
    """

    def __init__(self, *, seed: int, steps: int, hazard: float, emission_correct: float, persistence: float) -> None:
        super().__init__(seed=seed, steps=steps, hazard=hazard, emission_correct=emission_correct)
        if not 0 <= persistence < 1:
            raise ValueError("invalid sensor persistence")
        self.persistence = persistence
        self.error_offset: int | None = None

    def step(self, action_id: str) -> tuple[Observation, int]:
        if self.index >= self.steps:
            raise ValueError("world exhausted")
        if self.index > 0 and self.rng.random() < self.hazard:
            alternatives = [r for r in MODES if r != self.hidden_mode]
            self.hidden_mode = alternatives[self.rng.randrange(2)]
            self.transition_count += 1
        if self.error_offset is None or self.rng.random() >= self.persistence:
            draw = self.rng.random()
            if draw < self.emission_correct:
                self.error_offset = 0
            elif draw < (1 + self.emission_correct) / 2:
                self.error_offset = 1
            else:
                self.error_offset = 2
        cue = (self.hidden_mode + self.error_offset) % 3
        self.index += 1
        return Observation(self.index, action_id, cue), self.hidden_mode


class FreshCue:
    def __init__(self, emission_correct: float) -> None:
        self.emission_correct = emission_correct
        self.belief = (1 / 3, 1 / 3, 1 / 3)

    def predict(self) -> tuple[float, float, float]:
        return self.belief

    def observe(self, cue: int) -> tuple[float, float, float]:
        self.belief = update((1 / 3, 1 / 3, 1 / 3), cue, self.emission_correct)
        return self.belief


def brier(prob: tuple[float, float, float], hidden: int) -> float:
    # Unnormalized multiclass Brier score; uniform benchmark is 2/3.
    return sum((prob[i] - int(i == hidden)) ** 2 for i in MODES)


def nll(prob: tuple[float, float, float], hidden: int) -> float:
    # Numerical floor is recorded as part of diagnostics, never a pass gate.
    return -math.log(max(prob[hidden], 1e-300))


def run_world(seed: int, *, emission_correct: float, steps: int = STEPS_PER_WORLD, bursty: bool = False) -> dict[str, Any]:
    world = (
        BurstyWorld(seed=seed, steps=steps, hazard=TRANSITION_HAZARD, emission_correct=emission_correct, persistence=BURST_OFFSET_PERSISTENCE)
        if bursty else FixedWorld(seed=seed, steps=steps, hazard=TRANSITION_HAZARD, emission_correct=emission_correct)
    )
    models = {
        "joint_known_sensor": JointModeOffsetFilter(
            hazard=TRANSITION_HAZARD,
            emission_correct=emission_correct,
            persistence=BURST_OFFSET_PERSISTENCE if bursty else 0.0,
        ),
        "markov": CausalFilter(hazard=TRANSITION_HAZARD, emission_correct=emission_correct),
        "cumulative": CausalFilter(hazard=0.0, emission_correct=emission_correct),
        "shifted": CausalFilter(hazard=TRANSITION_HAZARD, emission_correct=emission_correct, shifted_cue=1),
        "uninformative": CausalFilter(hazard=TRANSITION_HAZARD, emission_correct=UNINFORMATIVE_CORRECT),
        "misspecified": CausalFilter(hazard=TRANSITION_HAZARD, emission_correct=INFORMATIVE_CORRECT),
    }
    fresh = FreshCue(emission_correct)
    names = [*models.keys(), "fresh"]
    totals = {key: {"post_correct": 0, "pre_correct": 0, "brier": 0.0, "nll": 0.0} for key in names}
    # Compare predictions without sharing hidden modes with any tracker.
    for step in range(steps):
        action_id = f"development:{seed}:{step + 1:04d}"
        pre = {name: model.begin_action(action_id) for name, model in models.items()}
        pre["fresh"] = fresh.predict()
        observation, hidden = world.step(action_id)
        post = {name: model.observe(observation) for name, model in models.items()}
        post["fresh"] = fresh.observe(observation.cue)
        for name in names:
            totals[name]["pre_correct"] += int(classify(pre[name]) == hidden)
            totals[name]["post_correct"] += int(classify(post[name]) == hidden)
            totals[name]["brier"] += brier(post[name], hidden)
            totals[name]["nll"] += nll(post[name], hidden)
    final = {}
    for name, totals_i in totals.items():
        final[name] = {key: v / steps for key, v in totals_i.items()}
    markov = models["markov"]
    snapshot = markov.snapshot()
    reconstructed = CausalFilter.replay(snapshot)
    assert reconstructed.snapshot() == snapshot
    joint = models["joint_known_sensor"]
    joint_snapshot = joint.snapshot()
    assert JointModeOffsetFilter.replay(joint_snapshot).snapshot() == joint_snapshot
    return {
        "seed": seed,
        "transition_count": world.transition_count,
        "metrics": final,
        "replay_exact": reconstructed.snapshot() == snapshot and JointModeOffsetFilter.replay(joint_snapshot).snapshot() == joint_snapshot,
        "trace_digest": digest({"markov": snapshot, "joint": joint_snapshot}),
    }


def paired_world_bootstrap(worlds: list[dict[str, Any]], left: str, right: str, metric: str) -> dict[str, float]:
    diffs = [w["metrics"][left][metric] - w["metrics"][right][metric] for w in worlds]
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(BOOTSTRAP_DRAWS):
        samples.append(statistics.mean(diffs[rng.randrange(len(diffs))] for __ in range(len(diffs))))
    samples.sort()
    return {"mean": statistics.mean(diffs), "low": samples[int(0.025 * (len(samples) - 1))], "high": samples[int(0.975 * (len(samples) - 1))]}


def evaluate(*, seeds: tuple[int, ...] = DEVELOPMENT_SEEDS, steps: int = STEPS_PER_WORLD) -> dict[str, Any]:
    conditions = {
        "informative_iid": (INFORMATIVE_CORRECT, False),
        "uninformative_iid": (UNINFORMATIVE_CORRECT, False),
        "correlated_error_stress": (INFORMATIVE_CORRECT, True),
    }
    results = {}
    for condition, (emission_correct, bursty) in conditions.items():
        worlds = [run_world(seed, emission_correct=emission_correct, steps=steps, bursty=bursty) for seed in seeds]
        policies = sorted(worlds[0]["metrics"])
        means = {
            name: {metric: statistics.mean(w["metrics"][name][metric] for w in worlds) for metric in ("pre_correct", "post_correct", "brier", "nll")}
            for name in policies
        }
        results[condition] = {
            "worlds": len(worlds),
            "steps_per_world": steps,
            "total_observations": len(worlds) * steps,
            "mean_mode_transitions": statistics.mean(w["transition_count"] for w in worlds),
            "all_replays_exact": all(w["replay_exact"] for w in worlds),
            "means": means,
            "paired_post_markov_minus_fresh": paired_world_bootstrap(worlds, "markov", "fresh", "post_correct"),
            "paired_post_markov_minus_cumulative": paired_world_bootstrap(worlds, "markov", "cumulative", "post_correct"),
            "paired_post_joint_minus_markov": paired_world_bootstrap(worlds, "joint_known_sensor", "markov", "post_correct"),
            "paired_post_joint_minus_fresh": paired_world_bootstrap(worlds, "joint_known_sensor", "fresh", "post_correct"),
            "paired_pre_markov_minus_fresh": paired_world_bootstrap(worlds, "markov", "fresh", "pre_correct"),
            "trace_digest": digest([w["trace_digest"] for w in worlds]),
        }
    return {
        "status": "EXPLORATORY_ONLY_NO_DARWIN_KERNEL_TESTED",
        "protocol": {
            "world_seeds": [seeds[0], seeds[-1]] if seeds else [],
            "world_count": len(seeds),
            "steps_per_world": steps,
            "transition_hazard": TRANSITION_HAZARD,
            "informative_sensor_correct": INFORMATIVE_CORRECT,
            "uninformative_sensor_correct": UNINFORMATIVE_CORRECT,
            "bursty_error_offset_persistence": BURST_OFFSET_PERSISTENCE,
            "paired_bootstrap_draws": BOOTSTRAP_DRAWS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "sensor_independence": "conditioned_on_current_hidden_mode",
            "latent_hazard": "switch_to_one_of_other_two_modes_uniformly",
        },
        "conditions": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="E062 independent exploratory finite-mode benchmark")
    parser.add_argument("--output", type=Path, help="Write strict JSON result to this path")
    parser.add_argument("--small-smoke", action="store_true", help="Use a small deterministic development smoke sample")
    args = parser.parse_args()
    result = evaluate(seeds=tuple(range(62000, 62008)) if args.small_smoke else DEVELOPMENT_SEEDS, steps=16 if args.small_smoke else STEPS_PER_WORLD)
    if args.output:
        args.output.write_bytes(canonical_bytes(result) + b"\n")
    for case, report in result["conditions"].items():
        print(f"{case}: {report['total_observations']} observations, replay_exact={report['all_replays_exact']}")
        for policy in ("joint_known_sensor", "markov", "fresh", "cumulative", "shifted", "uninformative", "misspecified"):
            row = report["means"][policy]
            print(f"  {policy:14s} pre={row['pre_correct']:.5f} post={row['post_correct']:.5f} Brier={row['brier']:.5f} logloss={row['nll']:.5f}")
        paired = report["paired_post_markov_minus_fresh"]
        print(f"  Markov - fresh post accuracy: {paired['mean']:+.5f}; paired world bootstrap 95% [{paired['low']:+.5f}, {paired['high']:+.5f}]")
        joint_gap = report["paired_post_joint_minus_markov"]
        print(f"  Joint - Markov post accuracy: {joint_gap['mean']:+.5f}; paired world bootstrap 95% [{joint_gap['low']:+.5f}, {joint_gap['high']:+.5f}]")
    print("All outputs are exploratory; no Darwin source or private memory was accessed.")


if __name__ == "__main__":
    main()
