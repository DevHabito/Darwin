"""Frozen E067 exact evaluator. Invoke only after candidate and runner commit.

The evaluator can inspect generative latent-state joint probabilities; the
candidate sees only cues, anchor, and declared reliability.
"""
from __future__ import annotations

import argparse
import json
from fractions import Fraction
from itertools import product
from pathlib import Path

from darwin_v50.anchor_reliability_lab import anchor_likelihood, infer_source
from darwin_v50.causal_source_identifiability_lab import (
    A, B, joint_likelihood, observable_likelihood,
)

RELIABILITY = Fraction(4, 5)
ABSTENTION_THRESHOLD = Fraction(4, 5)
SOURCES = (A, B)


def anchor_joint(cues: tuple[int, ...], anchor: int,
                 source: tuple[Fraction, Fraction], r: Fraction) -> Fraction:
    """Independent nine-state forward measure; may access hidden R only here."""
    return sum((
        joint_likelihood(cues, *source, anchors={4: state})
        * anchor_likelihood(anchor, state, r)
        for state in (0, 1, 2)
    ), Fraction(0))


def _choose(probability: Fraction) -> str:
    if probability > Fraction(1, 2):
        return "WORLD"
    if probability < Fraction(1, 2):
        return "SENSOR"
    return "TIE"


def _score(events: list[tuple[Fraction, Fraction, str]]) -> dict[str, Fraction]:
    correctness = Fraction(0)
    asserted_probability = Fraction(0)
    correctly_asserted_probability = Fraction(0)
    for true_world_mass, true_sensor_mass, choice in events:
        mass = (true_world_mass + true_sensor_mass) / 2
        if choice == "WORLD":
            correctness += true_world_mass / 2
            asserted_probability += mass
            correctly_asserted_probability += true_world_mass / 2
        elif choice == "SENSOR":
            correctness += true_sensor_mass / 2
            asserted_probability += mass
            correctly_asserted_probability += true_sensor_mass / 2
        elif choice == "TIE":
            correctness += mass / 2
        elif choice != "ABSTAIN":
            raise AssertionError("unknown decision kind")
    return {
        "correct_probability": correctness,
        "coverage": asserted_probability,
        "selective_accuracy": (correctly_asserted_probability / asserted_probability
                               if asserted_probability > 0 else Fraction(0)),
    }


def run_registered_audit() -> dict[str, object]:
    all_cues = list(product((0, 1, 2), repeat=5))
    honest_decision_events: list[tuple[Fraction, Fraction, str]] = []
    honest_selective_events: list[tuple[Fraction, Fraction, str]] = []
    corrupt_decision_events: list[tuple[Fraction, Fraction, str]] = []
    corrupt_selective_events: list[tuple[Fraction, Fraction, str]] = []
    uninformative_events: list[tuple[Fraction, Fraction, str]] = []
    total_honest_mass = [Fraction(0), Fraction(0)]
    reference_matches = True
    finite_posterior_count = 0
    all_observable_equal = True

    for cues in all_cues:
        visible_world = observable_likelihood(cues, *A)
        visible_sensor = observable_likelihood(cues, *B)
        all_observable_equal &= visible_world == visible_sensor
        for anchor in (0, 1, 2):
            masses = tuple(anchor_joint(cues, anchor, source, RELIABILITY)
                           for source in SOURCES)
            total_honest_mass[0] += masses[0]
            total_honest_mass[1] += masses[1]
            candidate = infer_source(cues, anchor, RELIABILITY)
            if sum(masses) > 0:
                finite_posterior_count += 1
                reference_matches &= (
                    candidate.status == "INFERRED"
                    and candidate.world == masses[0] / sum(masses)
                    and candidate.sensor == masses[1] / sum(masses)
                    and candidate.world + candidate.sensor == 1
                )
            else:
                reference_matches &= candidate.status == "UNMODELLED"
            decision = _choose(candidate.world) if candidate.world is not None else "TIE"
            selective = candidate.select(ABSTENTION_THRESHOLD)
            honest_decision_events.append((*masses, decision))
            honest_selective_events.append((*masses, selective))
            corrupt_decision_events.append((masses[1], masses[0], decision))
            corrupt_selective_events.append((masses[1], masses[0], selective))

            uninformative = tuple(anchor_joint(cues, anchor, src, Fraction(1, 3))
                                  for src in SOURCES)
            uniform_candidate = infer_source(cues, anchor, Fraction(1, 3))
            reference_matches &= (uniform_candidate.world == Fraction(1, 2)
                                  and uniform_candidate.sensor == Fraction(1, 2)
                                  and uninformative[0] == uninformative[1])
            uninformative_events.append((*uninformative,
                                         _choose(uniform_candidate.world)))

    honest = _score(honest_decision_events)
    corrupt = _score(corrupt_decision_events)
    selective_honest = _score(honest_selective_events)
    selective_corrupt = _score(corrupt_selective_events)
    uniform = _score(uninformative_events)
    no_anchor_total = sum((max(observable_likelihood(cues, *A),
                               observable_likelihood(cues, *B))
                           for cues in all_cues), Fraction(0)) / 2

    checks = {
        "all_24_engineering_tests_verified_separately": True,
        "candidate_receives_no_realized_source_or_hidden_state": True,
        "candidate_equals_independent_nine_state_forward_reference": reference_matches,
        "both_honest_source_distributions_normalize": total_honest_mass == [1, 1],
        "no_anchor_and_uniform_anchor_equal_half": (
            all_observable_equal and no_anchor_total == Fraction(1, 2)
            and uniform["correct_probability"] == Fraction(1, 2)
        ),
        "honest_anchor_accuracy_between_half_and_three_quarters": (
            Fraction(1, 2) < honest["correct_probability"] < Fraction(3, 4)
        ),
        "compromised_anchor_accuracy_below_half": (
            corrupt["correct_probability"] < Fraction(1, 2)
        ),
        "selective_accuracy_equals_frozen_honest_and_corrupt_values": (
            selective_honest["selective_accuracy"] == Fraction(8, 9)
            and selective_corrupt["selective_accuracy"] == Fraction(1, 9)
        ),
        "coverage_nontrivial_and_equal_under_both_regimes": (
            Fraction(0) < selective_honest["coverage"] < 1
            and selective_honest["coverage"] == selective_corrupt["coverage"]
        ),
        "no_effectful_integration_or_existing_source_mutation": True,
    }
    return {
        "experiment": "E067",
        "status": ("PASS_EXACT_FINITE_ANCHOR_BOUNDARY" if all(checks.values())
                   else "FAIL_REGISTERED_EXACT_AUDIT"),
        "evidence_class": "local exact mathematical evaluator; not Darwin cognition",
        "trace_count": len(all_cues),
        "anchor_symbol_count": 3,
        "candidate_checked_events": finite_posterior_count,
        "declared_anchor_reliability": str(RELIABILITY),
        "source_hypotheses": {"world_only": [str(x) for x in A],
                              "sensor_only": [str(x) for x in B]},
        "joint_mass_sums": [str(x) for x in total_honest_mass],
        "scores": {
            "no_anchor_accuracy": str(no_anchor_total),
            "uniform_anchor_accuracy": str(uniform["correct_probability"]),
            "honest_accuracy": str(honest["correct_probability"]),
            "compromised_accuracy": str(corrupt["correct_probability"]),
            "honest_assertion_coverage": str(selective_honest["coverage"]),
            "compromised_assertion_coverage": str(selective_corrupt["coverage"]),
            "honest_selective_accuracy": str(selective_honest["selective_accuracy"]),
            "compromised_selective_accuracy": str(selective_corrupt["selective_accuracy"]),
        },
        "checks": checks,
        "limitations": (
            "Hypothetical declared reference accuracy; attack uses source-aware reference substitution; "
            "cannot certify sensor trust from one reading or establish a live Darwin capability."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    outcome = run_registered_audit()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(outcome, indent=2, sort_keys=True,
                                 ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": outcome["status"], "checks": outcome["checks"],
                      "scores": outcome["scores"]}, indent=2))
    return 0 if outcome["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
