"""E064: label-free moment identification for one symmetric three-mode HMM.

The fit sees observed cue sequences only. The model is stationary, symmetric,
and conditionally independent; it cannot diagnose arbitrary real sensors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

MODES = (0, 1, 2)
CUTOFF = 0.04


@dataclass(frozen=True, slots=True)
class ReliabilityEstimate:
    status: str
    hazard: float | None
    sensor_correct: float | None
    equality_rates: tuple[float, float, float]
    pair_counts: tuple[int, int, int]
    predicted_lag3: float | None

    @property
    def lag3_absolute_gap(self) -> float | None:
        if self.predicted_lag3 is None:
            return None
        return abs(self.equality_rates[2] - self.predicted_lag3)


def population_lag_equality(hazard: float, sensor_correct: float, lag: int) -> float:
    """Analytic reference, not used in the fit. Assumes a stationary HMM."""
    if type(lag) is not int or lag < 1:
        raise ValueError("lag must be a positive integer")
    if not (math.isfinite(hazard) and 0 <= hazard <= 1):
        raise ValueError("hazard outside model")
    if not (math.isfinite(sensor_correct) and 1/3 <= sensor_correct <= 1):
        raise ValueError("sensor correctness outside model")
    a = 1 - 1.5 * hazard
    b = (3 * sensor_correct - 1) / 2
    return 1 / 3 + 2 / 3 * b * b * (a ** lag)


def _invert(first: float, second: float) -> tuple[float, float] | None:
    """Return (h,q) only when two observed moments identify this model."""
    c1 = (3 * first - 1) / 2
    c2 = (3 * second - 1) / 2
    if c1 <= CUTOFF or c2 <= CUTOFF:
        return None
    a = c2 / c1
    b2 = c1 * c1 / c2
    if not math.isfinite(a) or not math.isfinite(b2):
        return None
    if not (0 < a <= 1 and 0 < b2 <= 1):
        return None
    b = math.sqrt(b2)
    hazard = 2 * (1 - a) / 3
    sensor_correct = (1 + 2 * b) / 3
    if not (0 <= hazard < 2/3 and 1/3 < sensor_correct <= 1):
        return None
    return hazard, sensor_correct


def estimate_symmetric_sensor(sequences: Sequence[Sequence[int]]) -> ReliabilityEstimate:
    """Estimate h,q using cue equalities alone; never reads hidden state.

    The caller supplies independent, continuous recordings. Each recording is
    treated as its own segment: no cross-recording lag pairs are permitted.
    """
    if isinstance(sequences, (str, bytes)) or not isinstance(sequences, (list, tuple)) or not sequences:
        raise ValueError("expected at least one observation sequence")
    matching = [0, 0, 0]
    pairs = [0, 0, 0]
    for sequence in sequences:
        if isinstance(sequence, (str, bytes)) or not isinstance(sequence, (tuple, list)) or len(sequence) < 4:
            raise ValueError("each observation sequence needs at least four cues")
        if any(type(cue) is not int or cue not in MODES for cue in sequence):
            raise ValueError("cues must be exact integers in {0,1,2}")
        for lag in (1, 2, 3):
            pairs[lag - 1] += len(sequence) - lag
            matching[lag - 1] += sum(sequence[t] == sequence[t + lag] for t in range(len(sequence) - lag))
    rates = tuple(count / total for count, total in zip(matching, pairs))
    parameters = _invert(rates[0], rates[1])
    if parameters is None:
        return ReliabilityEstimate("UNIDENTIFIABLE", None, None, rates, tuple(pairs), None)
    h, q = parameters
    predicted = population_lag_equality(h, q, 3)
    return ReliabilityEstimate("FITTED", h, q, rates, tuple(pairs), predicted)
