"""Exact, authority-free E068 sensor redundancy laboratory.

This module never accesses Darwin's kernel, store, external tools, or labels
for the realized latent state. Parameters are externally declared, not learned.
"""
from __future__ import annotations

from fractions import Fraction

MODES = (0, 1, 2)
THIRD = Fraction(1, 3)
ZERO = Fraction(0)
ONE = Fraction(1)


def _probability(value: Fraction | int, *, name: str, lower: Fraction) -> Fraction:
    if type(value) not in (int, Fraction):
        raise ValueError(f"{name} must be an exact rational probability")
    exact = Fraction(value)
    if not lower <= exact <= ONE:
        raise ValueError(f"{name} outside the declared probability domain")
    return exact


def _label(label: int, *, name: str) -> int:
    if type(label) is not int or label not in MODES:
        raise ValueError(f"{name} must be in {{0, 1, 2}}")
    return label


def emission(reliability: Fraction | int, *, truth: int, observed: int) -> Fraction:
    q = _probability(reliability, name="reliability", lower=THIRD)
    _label(truth, name="truth")
    _label(observed, name="observed")
    return q if observed == truth else (ONE - q) / 2


def pair_likelihood(
    reliability: Fraction | int,
    copy_probability: Fraction | int,
    *,
    truth: int,
    first: int,
    second: int,
) -> Fraction:
    """Evaluator generative likelihood. `truth` is not a candidate input."""
    q = _probability(reliability, name="reliability", lower=THIRD)
    alpha = _probability(copy_probability, name="copy_probability", lower=ZERO)
    _label(truth, name="truth")
    _label(first, name="first")
    _label(second, name="second")
    return emission(q, truth=truth, observed=first) * (
        (alpha if first == second else ZERO)
        + (ONE - alpha) * emission(q, truth=truth, observed=second)
    )


def visible_pair_probability(
    first: int,
    second: int,
    *,
    reliability: Fraction | int,
    copy_probability: Fraction | int,
) -> Fraction:
    """Marginal observation probability; does not expose a realized truth."""
    _label(first, name="first")
    _label(second, name="second")
    return sum(
        (THIRD * pair_likelihood(reliability, copy_probability,
                                 truth=latent, first=first, second=second)
         for latent in MODES),
        ZERO,
    )


def source_posterior(
    first: int,
    second: int,
    *,
    reliability: Fraction | int,
    copy_probability: Fraction | int,
) -> tuple[Fraction, Fraction, Fraction]:
    """Posterior P(R | Y1, Y2) for declared sensor assumptions only.

    No hidden realized state, source provenance or goal/action handle is accepted.
    """
    _label(first, name="first")
    _label(second, name="second")
    weights = tuple(
        THIRD * pair_likelihood(reliability, copy_probability,
                                truth=latent, first=first, second=second)
        for latent in MODES
    )
    mass = sum(weights, ZERO)
    if mass <= ZERO:
        raise ValueError("observation impossible under the declared model")
    return tuple(weight / mass for weight in weights)  # type: ignore[return-value]


def single_sensor_posterior(
    observed: int, *, reliability: Fraction | int,
) -> tuple[Fraction, Fraction, Fraction]:
    q = _probability(reliability, name="reliability", lower=THIRD)
    _label(observed, name="observed")
    return tuple(
        emission(q, truth=latent, observed=observed) for latent in MODES
    )  # type: ignore[return-value]


def agreement_probability(
    *, reliability: Fraction | int, copy_probability: Fraction | int,
) -> Fraction:
    q = _probability(reliability, name="reliability", lower=THIRD)
    alpha = _probability(copy_probability, name="copy_probability", lower=ZERO)
    independent_agreement = q * q + (ONE - q) ** 2 / 2
    return alpha + (ONE - alpha) * independent_agreement


def multiclass_brier(
    posterior: tuple[Fraction, Fraction, Fraction], *, truth: int,
) -> Fraction:
    _label(truth, name="truth")
    if (type(posterior) is not tuple or len(posterior) != 3
            or any(type(v) is not Fraction or v < 0 for v in posterior)
            or sum(posterior, ZERO) != ONE):
        raise ValueError("posterior is not an exact normalized three-mode probability")
    return sum(
        ((posterior[r] - (ONE if r == truth else ZERO)) ** 2 for r in MODES),
        ZERO,
    )
