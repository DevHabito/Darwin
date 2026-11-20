#!/usr/bin/env python3
"""Exact reference for a proposed Darwin v50 noisy-alignment benchmark.

This is NOT a Darwin kernel test. It computes the best possible classification
accuracy for a fixed latent mode among three equally likely modes, with each
conditionally independent observation reporting the true mode with probability
4/5 and either incorrect mode with probability 1/10.

Standard library only; no repository imports, no network, no persistent state.
"""
from fractions import Fraction
from math import factorial


def multinomial(n: int, counts: tuple[int, int, int]) -> int:
    a, b, c = counts
    return factorial(n) // (factorial(a) * factorial(b) * factorial(c))


def accuracy_by_maximum_likelihood(n: int) -> Fraction:
    correct = Fraction(4, 5)
    wrong = Fraction(1, 10)
    total = Fraction(0)
    for a in range(n + 1):
        for b in range(n - a + 1):
            c = n - a - b
            likelihoods = [
                correct**k * wrong**(n - k)
                for k in (a, b, c)
            ]
            total += Fraction(multinomial(n, (a, b, c)), 3) * max(likelihoods)
    return total


def accuracy_by_true_mode_ties(n: int) -> Fraction:
    """Independent cross-check: fix true mode 0 and break ML ties fairly."""
    correct = Fraction(4, 5)
    wrong = Fraction(1, 10)
    total = Fraction(0)
    for a in range(n + 1):
        for b in range(n - a + 1):
            c = n - a - b
            counts = (a, b, c)
            tie_count = sum(k == max(counts) for k in counts)
            decision_prob = Fraction(1, tie_count) if a == max(counts) else Fraction(0)
            total += (
                multinomial(n, counts)
                * correct**a
                * wrong**(b + c)
                * decision_prob
            )
    return total


def main() -> None:
    for n in (0, 1, 2, 3, 4, 5, 7, 9):
        method_a = accuracy_by_maximum_likelihood(n)
        method_b = accuracy_by_true_mode_ties(n)
        assert method_a == method_b, f"reference methods disagree at n={n}"
        print(f"n={n:2d}  accuracy={float(method_a):.6%}  exact={method_a}")
    assert accuracy_by_maximum_likelihood(1) == Fraction(4, 5)
    assert accuracy_by_maximum_likelihood(3) == Fraction(114, 125)
    assert accuracy_by_maximum_likelihood(5) == Fraction(3004, 3125)
    print("Exact-arithmetic cross-checks: PASS")


if __name__ == "__main__":
    main()
