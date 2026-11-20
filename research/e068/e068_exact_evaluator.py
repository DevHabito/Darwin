"""E068 registered exact enumeration; do not alter after freezing this runner.

No Darwin kernel, external effect, file database, model server, or randomness.
"""
from __future__ import annotations

import argparse
import json
from fractions import Fraction
from itertools import product
from pathlib import Path

from darwin_v50.shared_sensor_evidence_lab import (
    MODES, emission, pair_likelihood, visible_pair_probability,
    source_posterior, single_sensor_posterior, agreement_probability,
    multiclass_brier,
)

ZERO = Fraction(0)
ONE = Fraction(1)
THIRD = Fraction(1, 3)
A = (Fraction(4, 5), Fraction(3, 4))
B = (Fraction(19, 20), Fraction(9, 77))
I = (Fraction(4, 5), ZERO)
D = (Fraction(4, 5), ONE)
THRESHOLD = Fraction(9, 10)


def exact(value: Fraction | int) -> str:
    return str(Fraction(value))


def reference_observation_probability(
    first: int, second: int, q: Fraction, alpha: Fraction,
) -> Fraction:
    """Independent formula using direct generative loops, not candidate marginal."""
    total = ZERO
    for r in MODES:
        p_first = q if first == r else (ONE - q) / 2
        p_second = q if second == r else (ONE - q) / 2
        total += THIRD * p_first * (
            (alpha if first == second else ZERO) + (ONE - alpha) * p_second
        )
    return total


def expected_brier(true_model: tuple[Fraction, Fraction],
                   candidate: tuple[Fraction, Fraction]) -> Fraction:
    q_true, alpha_true = true_model
    total = ZERO
    for r, i, j in product(MODES, repeat=3):
        mass = THIRD * pair_likelihood(q_true, alpha_true, truth=r,
                                       first=i, second=j)
        if not mass:
            continue
        posterior = source_posterior(i, j, reliability=candidate[0],
                                     copy_probability=candidate[1])
        total += mass * multiclass_brier(posterior, truth=r)
    return total


def proper_score_gap(true_model: tuple[Fraction, Fraction],
                     candidate: tuple[Fraction, Fraction]) -> Fraction:
    total = ZERO
    for i, j in product(MODES, repeat=2):
        mass = reference_observation_probability(i, j, *true_model)
        if not mass:
            continue
        correct = source_posterior(i, j, reliability=true_model[0],
                                   copy_probability=true_model[1])
        other = source_posterior(i, j, reliability=candidate[0],
                                 copy_probability=candidate[1])
        total += mass * sum(((p - q) ** 2 for p, q in zip(correct, other)), ZERO)
    return total


def selective_metrics(true_model: tuple[Fraction, Fraction],
                      candidate: tuple[Fraction, Fraction]) -> dict[str, str]:
    coverage = ZERO
    correct = ZERO
    for i, j in product(MODES, repeat=2):
        posterior = source_posterior(i, j, reliability=candidate[0],
                                     copy_probability=candidate[1])
        top = max(posterior)
        if top < THRESHOLD:
            continue
        selected = posterior.index(top)
        observation_mass = reference_observation_probability(i, j, *true_model)
        coverage += observation_mass
        correct += THIRD * pair_likelihood(*true_model, truth=selected,
                                           first=i, second=j)
    return {
        "assertion_probability": exact(coverage),
        "correct_assertion_probability": exact(correct),
        "conditional_accuracy_given_assertion": exact(correct / coverage) if coverage else None,
    }


def evaluate() -> dict[str, object]:
    visible = {}
    for name, model in (("shared_A", A), ("confounded_B", B),
                        ("independent_I", I), ("duplicate_D", D)):
        q, alpha = model
        events = [THIRD * pair_likelihood(q, alpha, truth=r, first=i, second=j)
                  for r, i, j in product(MODES, repeat=3)]
        visible[name] = {
            "total_mass": exact(sum(events, ZERO)),
            "joint": {f"{i}{j}": exact(reference_observation_probability(i, j, q, alpha))
                      for i, j in product(MODES, repeat=2)},
            "agree": exact(agreement_probability(reliability=q,
                                                 copy_probability=alpha)),
            "q": exact(q),
            "copy_probability": exact(alpha),
        }
    max_diff = max((abs(reference_observation_probability(i, j, *A) -
                        reference_observation_probability(i, j, *B))
                    for i, j in product(MODES, repeat=2)))
    tv = sum((abs(reference_observation_probability(i, j, *A) -
                  reference_observation_probability(i, j, *B))
              for i, j in product(MODES, repeat=2)), ZERO) / 2

    correct_posterior = source_posterior(0, 0, reliability=A[0], copy_probability=A[1])
    confused_posterior = source_posterior(0, 0, reliability=B[0], copy_probability=B[1])
    naive_posterior = source_posterior(0, 0, reliability=I[0], copy_probability=I[1])
    correct_risk = expected_brier(A, A)
    naive_risk = expected_brier(A, I)
    gap = naive_risk - correct_risk
    gap_proper = proper_score_gap(A, I)
    honest = selective_metrics(A, A)
    naive = selective_metrics(A, I)
    observed_agreement = agreement_probability(reliability=A[0], copy_probability=A[1])

    checks = {
        "enumerates_27_latent_sensor_triplets": len(list(product(MODES, repeat=3))) == 27,
        "every_configuration_exactly_normalized": all(item["total_mass"] == "1" for item in visible.values()),
        "complete_visible_laws_identical_A_B": max_diff == ZERO and tv == ZERO,
        "both_confounded_models_exact_agreement_183_200": visible["shared_A"]["agree"] == "183/200" and visible["confounded_B"]["agree"] == "183/200",
        "matching_and_distinct_pair_closed_form": all(
            reference_observation_probability(i, j, *A) ==
            (observed_agreement / 3 if i == j else (ONE - observed_agreement) / 6)
            for i, j in product(MODES, repeat=2)
        ),
        "candidate_and_independent_reference_match_all_models": all(
            visible_pair_probability(i, j, reliability=q, copy_probability=alpha)
            == reference_observation_probability(i, j, q, alpha)
            for q, alpha in (A, B, I, D) for i, j in product(MODES, repeat=2)
        ),
        "indistinguishable_models_disagree_on_latent_posterior": abs(correct_posterior[0] - confused_posterior[0]) > Fraction(1, 10),
        "naive_multiply_is_overconfident_on_duplicate_like_agreement": naive_posterior[0] > THRESHOLD and correct_posterior[0] < THRESHOLD,
        "independent_control_agrees_with_independent_fusion": all(
            source_posterior(i, j, reliability=I[0], copy_probability=I[1])
            == source_posterior(i, j, reliability=A[0], copy_probability=ZERO)
            for i, j in product(MODES, repeat=2)
        ),
        "full_copy_has_zero_disagreement_and_single_sensor_posterior": all(
            (reference_observation_probability(i, j, *D) == ZERO if i != j else
             source_posterior(i, j, reliability=D[0], copy_probability=D[1])
             == single_sensor_posterior(i, reliability=D[0]))
            for i, j in product(MODES, repeat=2)
        ),
        "correct_model_strictly_improves_Brier_and_proper_scoring_identity": gap > ZERO and gap == gap_proper,
        "correct_model_abstains_at_90_percent": honest["assertion_probability"] == "0",
        "naive_model_asserts_only_agreements": naive["assertion_probability"] == "183/200",
        "naive_assertions_less_than_90_percent_correct": (
            naive["conditional_accuracy_given_assertion"] is not None and
            Fraction(naive["conditional_accuracy_given_assertion"]) < THRESHOLD
        ),
    }
    return {
        "experiment": "E068", "status": "PASS_EXACT_BOUNDARY" if all(checks.values()) else "FAIL_FROZEN_CONJUNCTION",
        "evidence": "preregistered finite exact-rational mathematical enumeration; no new Darwin learning ability",
        "observation_pairs": 9, "latent_triplets_per_model": 27,
        "assumptions": visible,
        "checks": checks,
        "total_variation_A_B": exact(tv),
        "largest_observable_probability_difference_A_B": exact(max_diff),
        "posterior_for_pair_00": {
            "correct_A_R0": exact(correct_posterior[0]),
            "confounded_B_R0": exact(confused_posterior[0]),
            "naive_independent_R0": exact(naive_posterior[0]),
        },
        "expected_multiclass_brier_under_A": {
            "correct_A": exact(correct_risk),
            "naive_independent": exact(naive_risk),
            "naive_minus_correct": exact(gap),
            "independent_proper_scoring_gap": exact(gap_proper),
        },
        "frozen_selective_threshold": exact(THRESHOLD),
        "selective_under_A": {"correct_model": honest, "naive_independent": naive},
        "interpretation": "Agreement does not identify hidden reliability and copied evidence must not be multiplied as if independent. Declared models, not learned truth."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E068 immutable exact shared-sensor audit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True,
                                     sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("E068: " + report["status"])
    print("Checks: "+ str(sum(report["checks"].values())) + "/" + str(len(report["checks"])))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
