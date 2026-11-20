"""Registered E069 exact evaluator; freeze before full enumeration.

Reference probabilities use explicit independent latent-state enumeration.
They do not call the candidate likelihood. This is a synthetic exact-rational
experiment, not an authentic Darwin sensor or kernel evaluation.
"""
from __future__ import annotations

import argparse
import io
import json
import unittest
from fractions import Fraction
from itertools import product
from pathlib import Path

from darwin_v50.third_view_identifiability_lab import (
    A, B, MODES, ONE, THIRD, ZERO, independent_triplet_posterior,
)

MODELS = {"A": A, "B": B}
T = Fraction(4, 5)
HALF = Fraction(1, 2)
TRIPLES = tuple(product(MODES, repeat=3))
PAIRS = tuple(product(MODES, repeat=2))


def reference_emission(q: Fraction, truth: int, reading: int) -> Fraction:
    return q if truth == reading else (ONE - q) / 2


def reference_mass(
    hypothesis: str, triple: tuple[int, int, int], *,
    mechanism: str, reliability: Fraction,
) -> Fraction:
    """Separate reference over R, Y1, copied-vs-fresh Y2, and Y3 mechanism."""
    q, copying = MODELS[hypothesis]
    first, second, third = triple
    total = ZERO
    for latent in MODES:
        first_mass = reference_emission(q, latent, first)
        second_mass = (
            copying * (ONE if second == first else ZERO)
            + (ONE - copying) * reference_emission(q, latent, second)
        )
        if mechanism == "independent":
            third_mass = reference_emission(reliability, latent, third)
        elif mechanism == "copied":
            third_mass = ONE if third == first else ZERO
        else:
            raise ValueError("unknown registered third-view mechanism")
        total += THIRD * first_mass * second_mass * third_mass
    return total


def law(mechanism: str, reliability: Fraction) -> dict[str, dict[tuple[int, int, int], Fraction]]:
    return {
        hypothesis: {
            triple: reference_mass(hypothesis, triple,
                mechanism=mechanism, reliability=reliability)
            for triple in TRIPLES
        }
        for hypothesis in MODELS
    }


def total_variation(source_law: dict[str, dict[tuple[int, int, int], Fraction]]) -> Fraction:
    return sum((abs(source_law["A"][x] - source_law["B"][x])
                for x in TRIPLES), ZERO) / 2


def bayes_accuracy(source_law: dict[str, dict[tuple[int, int, int], Fraction]]) -> Fraction:
    return sum((max(source_law["A"][x], source_law["B"][x])
                for x in TRIPLES), ZERO) / 2


def agreement_y1_y3(single_law: dict[tuple[int, int, int], Fraction]) -> Fraction:
    return sum((mass for (first, _second, third), mass in single_law.items()
                if first == third), ZERO)


def candidate_matches_reference(source_law: dict[str, dict[tuple[int, int, int], Fraction]],
                                reliability: Fraction) -> bool:
    for triple in TRIPLES:
        a = source_law["A"][triple]
        b = source_law["B"][triple]
        if a + b == ZERO:
            continue
        if independent_triplet_posterior(*triple, third_reliability=reliability) != (
            a / (a + b), b / (a + b)
        ):
            return False
    return True


def copy_misspecification(
    copied_law: dict[str, dict[tuple[int, int, int], Fraction]],
) -> dict[str, Fraction]:
    declared_confidence = ZERO
    actual_correct = ZERO
    asserted_events = 0
    for triple in TRIPLES:
        a = copied_law["A"][triple]
        b = copied_law["B"][triple]
        if a + b == ZERO:
            continue
        inferred_a, inferred_b = independent_triplet_posterior(
            *triple, third_reliability=T,
        )
        declared_confidence += (a + b) * HALF * max(inferred_a, inferred_b)
        actual_correct += a * HALF if inferred_a >= inferred_b else b * HALF
        asserted_events += 1
    return {
        "expected_reported_confidence": declared_confidence,
        "true_balanced_classification_accuracy": actual_correct,
        "supported_copied_triples": Fraction(asserted_events),
        "confidence_excess_over_accuracy": declared_confidence - actual_correct,
    }


def evaluate(*, unit_tests_passed: bool) -> dict[str, object]:
    informative = law("independent", T)
    uninformative = law("independent", THIRD)
    copied = law("copied", T)
    distributions = {
        "independent_informative": informative,
        "independent_uninformative": uninformative,
        "copied": copied,
    }
    pair_marginals: dict[str, dict[tuple[int, int], Fraction]] = {}
    for hypothesis in MODELS:
        pair_marginals[hypothesis] = {
            pair: sum((informative[hypothesis][(*pair, third)] for third in MODES), ZERO)
            for pair in PAIRS
        }
    pair_tv = sum((abs(pair_marginals["A"][pair] - pair_marginals["B"][pair])
                   for pair in PAIRS), ZERO) / 2
    metrics = {
        name: {
            "tv": total_variation(source_law),
            "accuracy": bayes_accuracy(source_law),
            "mass_A": sum(source_law["A"].values(), ZERO),
            "mass_B": sum(source_law["B"].values(), ZERO),
            "support_A": Fraction(sum(m > ZERO for m in source_law["A"].values())),
            "support_B": Fraction(sum(m > ZERO for m in source_law["B"].values())),
        }
        for name, source_law in distributions.items()
    }
    copy_risk = copy_misspecification(copied)
    rate_a = agreement_y1_y3(informative["A"])
    rate_b = agreement_y1_y3(informative["B"])
    independent_candidate_matches = candidate_matches_reference(informative, T)
    uninformative_candidate_matches = candidate_matches_reference(uninformative, THIRD)
    pair_mass_exact = all(sum(pair_marginals[hypothesis].values(), ZERO) == ONE
                          for hypothesis in MODELS)
    criteria = {
        "unit_tests_and_reference_checks": unit_tests_passed,
        "two_view_laws_identical": pair_tv == ZERO and pair_mass_exact
            and all(pair_marginals["A"][pair] == pair_marginals["B"][pair]
                    for pair in PAIRS),
        "candidate_matches_independent_bayes": independent_candidate_matches,
        "all_mechanism_hypothesis_masses_exactly_one": all(
            record["mass_A"] == ONE and record["mass_B"] == ONE
            for record in metrics.values()
        ),
        "informative_third_has_at_least_registered_tv": (
            metrics["independent_informative"]["tv"] >= Fraction(21, 200)
            and metrics["independent_informative"]["accuracy"] > HALF
            and metrics["independent_informative"]["accuracy"] ==
            (ONE + metrics["independent_informative"]["tv"]) / 2
        ),
        "independent_agreement_rates_exact": (
            rate_a == Fraction(33, 50) and rate_b == Fraction(153, 200)
        ),
        "uninformative_third_has_no_source_information": (
            metrics["independent_uninformative"]["tv"] == ZERO
            and metrics["independent_uninformative"]["accuracy"] == HALF
            and uninformative_candidate_matches
            and all(independent_triplet_posterior(*x, third_reliability=THIRD)
                    == (HALF, HALF) for x in TRIPLES)
        ),
        "copied_third_has_no_source_information": (
            metrics["copied"]["tv"] == ZERO
            and metrics["copied"]["accuracy"] == HALF
            and all(copied[hypothesis][x] == ZERO
                    for hypothesis in MODELS for x in TRIPLES if x[0] != x[2])
        ),
        "falsely_independent_copy_is_overconfident": (
            copy_risk["true_balanced_classification_accuracy"] == HALF
            and copy_risk["expected_reported_confidence"] > HALF
        ),
        "no_effectful_integration": True,  # scope: isolated module, evaluator and tests only
    }
    metrics_report: dict[str, object] = {
        "pair_only_tv": str(pair_tv),
        "hypotheses": {
            name: {"reliability_q": str(model[0]), "copy_probability_alpha": str(model[1])}
            for name, model in MODELS.items()
        },
        "independent_third_reliability": str(T),
        "independent_matching_rate_A": str(rate_a),
        "independent_matching_rate_B": str(rate_b),
        "independent_matching_rate_difference": str(abs(rate_a - rate_b)),
        "mechanisms": {
            name: {key: str(value) for key, value in values.items()}
            for name, values in metrics.items()
        },
        "copied_as_independent_risk": {key: str(value) for key, value in copy_risk.items()},
        "all_27_observable_triples": [
            {
                "readings": "".join(map(str, triple)),
                "A_independent": str(informative["A"][triple]),
                "B_independent": str(informative["B"][triple]),
                "A_copied": str(copied["A"][triple]),
                "B_copied": str(copied["B"][triple]),
            }
            for triple in TRIPLES
        ],
    }
    return {
        "experiment": "E069",
        "status": ("PASS_EXACT_THIRD_VIEW_BOUNDARY" if all(criteria.values())
                   else "FAIL_REGISTERED_EXACT_EVALUATION"),
        "evidence_level": "E0_E1_FINITE_SYNTHETIC_MATHEMATICAL_BOUNDARY",
        "candidate_uses_true_source_label": False,
        "candidate_knows_real_independence": False,
        "source_labels_evaluator_only": True,
        "latent_truth_externally_supplied_to_candidate": False,
        "enumeration": {"latent_quadruples_per_model": 81,
                        "observable_triples": len(TRIPLES),
                        "hypotheses": 2, "mechanisms": 3},
        "criteria": criteria,
        "metrics": metrics_report,
        "interpretation": ("A third view helps only under the declared independent "
            "observation mechanism; copied and uninformative views do not "
            "resolve the E068 equivalence. Independence is not established "
            "by the candidate, and the experiment is not a cognitive capability."),
    }


def test_preflight() -> tuple[bool, int, str]:
    """Run committed focused tests before enumerating any registered events."""
    root = Path(__file__).resolve().parents[2]
    suite = unittest.TestLoader().discover(
        start_dir=str(root / "tests"),
        pattern="test_v50_third_view_identifiability_lab.py",
    )
    count = suite.countTestCases()
    stream = io.StringIO()
    outcome = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    return outcome.wasSuccessful() and count >= 20, count, stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Exact preregistered E069 evaluation")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    passed, test_count, test_log = test_preflight()
    if not passed:
        print("E069 admission failed before enumeration:", test_log)
        return 1
    output = evaluate(unit_tests_passed=passed)
    output["unit_tests_executed"] = test_count
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True,
                                      ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    for check, accepted in output["criteria"].items():
        print(f"{check}: {'PASS' if accepted else 'FAIL'}")
    print("Result:", output["status"])
    print("Report:", args.output)
    return 0 if all(output["criteria"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
