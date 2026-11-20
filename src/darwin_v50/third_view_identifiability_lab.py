"""E069: exact source-hypothesis inference with one declared independent view.

This is a finite statistical laboratory, not a Darwin v50 runtime component.
The model descriptions and third-view reliability are supplied externally;
neither independence nor sensor quality is estimated from these observations.
"""
from __future__ import annotations

from fractions import Fraction

MODES = (0, 1, 2)
ZERO = Fraction(0)
ONE = Fraction(1)
THIRD = Fraction(1, 3)
A = (Fraction(4, 5), Fraction(3, 4))
B = (Fraction(19, 20), Fraction(9, 77))
DEFAULT_THIRD_RELIABILITY = Fraction(4, 5)


def _exact_probability(value: Fraction | int, *, name: str, minimum: Fraction) -> Fraction:
    if type(value) not in (int, Fraction):
        raise ValueError(f"{name} must be an exact rational probability")
    result = Fraction(value)
    if not minimum <= result <= ONE:
        raise ValueError(f"{name} is outside its declared probability range")
    return result


def _cue(value: int, *, name: str) -> int:
    if type(value) is not int or value not in MODES:
        raise ValueError(f"{name} must be an integer in {{0,1,2}}")
    return value


def sensor_emission(reliability: Fraction | int, *, truth: int, reading: int) -> Fraction:
    """Probability of a symmetric three-state sensor reading."""
    q = _exact_probability(reliability, name="reliability", minimum=THIRD)
    _cue(truth, name="truth")
    _cue(reading, name="reading")
    return q if reading == truth else (ONE - q) / 2


def _pair_given_state(
    *, reliability: Fraction, copying: Fraction, truth: int, first: int, second: int,
) -> Fraction:
    first_mass = sensor_emission(reliability, truth=truth, reading=first)
    independent_second = sensor_emission(reliability, truth=truth, reading=second)
    copy_mass = copying if first == second else ZERO
    return first_mass * (copy_mass + (ONE - copying) * independent_second)


def independent_triplet_likelihood(
    first: int, second: int, third: int, *, model: str,
    third_reliability: Fraction | int,
) -> Fraction:
    """Observable likelihood for one *declared independent* third reading.

    Does not accept the realized source class or latent state. The named A/B
    hypotheses are frozen scientific descriptions, not discovered quantities.
    """
    _cue(first, name="first")
    _cue(second, name="second")
    _cue(third, name="third")
    t = _exact_probability(
        third_reliability, name="third_reliability", minimum=THIRD,
    )
    if type(model) is not str or model not in ("A", "B"):
        raise ValueError("model must be one of the two preregistered hypotheses")
    q, alpha = A if model == "A" else B
    return sum(
        (
            THIRD
            * _pair_given_state(
                reliability=q, copying=alpha, truth=hidden,
                first=first, second=second,
            )
            * sensor_emission(t, truth=hidden, reading=third)
            for hidden in MODES
        ),
        ZERO,
    )


def independent_triplet_posterior(
    first: int, second: int, third: int, *,
    third_reliability: Fraction | int = DEFAULT_THIRD_RELIABILITY,
) -> tuple[Fraction, Fraction]:
    """Return exact P(A|Y1,Y2,Y3), P(B|Y1,Y2,Y3) under equal priors.

    The function cannot learn source reliability or verify independence. It
    does not receive the realized source label, latent state, or copy flag.
    """
    a = independent_triplet_likelihood(
        first, second, third, model="A", third_reliability=third_reliability,
    )
    b = independent_triplet_likelihood(
        first, second, third, model="B", third_reliability=third_reliability,
    )
    mass = a + b
    if mass <= ZERO:
        raise ValueError("observation has zero mass under both hypotheses")
    return a / mass, b / mass


def copied_triplet_likelihood(
    first: int, second: int, third: int, *, model: str,
) -> Fraction:
    """Negative-control distribution. Not used by the inference candidate."""
    _cue(first, name="first")
    _cue(second, name="second")
    _cue(third, name="third")
    if type(model) is not str or model not in ("A", "B"):
        raise ValueError("unknown frozen hypothesis")
    if first != third:
        return ZERO
    q, alpha = A if model == "A" else B
    return sum(
        (
            THIRD * _pair_given_state(
                reliability=q, copying=alpha, truth=hidden,
                first=first, second=second,
            ) for hidden in MODES
        ),
        ZERO,
    )
