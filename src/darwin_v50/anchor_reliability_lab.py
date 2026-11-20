"""E067 exact-rational source inference under an explicitly declared anchor model.

The two source hypotheses are E066's world-only vs sensor-only process.
This module does not infer the reliability of the anchor and never observes
which source actually generated the data. No runtime or effect authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

MODES = (0, 1, 2)
EXPECTED_LENGTH = 5


@dataclass(frozen=True, slots=True)
class SourcePosterior:
    status: str
    world: Fraction | None
    sensor: Fraction | None

    @property
    def maximum(self) -> Fraction | None:
        if self.world is None or self.sensor is None:
            return None
        return max(self.world, self.sensor)

    def select(self, minimum_confidence: Fraction = Fraction(4, 5)) -> str:
        minimum = _probability(minimum_confidence)
        if self.status != "INFERRED" or self.maximum is None:
            return "ABSTAIN"
        if self.maximum < minimum or self.world == self.sensor:
            return "ABSTAIN"
        return "WORLD" if self.world > self.sensor else "SENSOR"


def _probability(value: object) -> Fraction:
    if type(value) not in (int, Fraction):
        raise ValueError("probability must be an exact rational")
    number = Fraction(value)
    if number < 0 or number > 1:
        raise ValueError("probability outside [0, 1]")
    return number


def _cue_history(values: object) -> tuple[int, ...]:
    if type(values) not in (list, tuple) or len(values) != EXPECTED_LENGTH:
        raise ValueError("exactly five observed cues are required")
    if any(type(cue) is not int or cue not in MODES for cue in values):
        raise ValueError("all observed cues must be integers from {0, 1, 2}")
    return tuple(values)


def anchor_likelihood(anchor: int, predicted_world: int,
                      reliability: Fraction | int) -> Fraction:
    if type(anchor) is not int or anchor not in MODES:
        raise ValueError("anchor value is invalid")
    if type(predicted_world) is not int or predicted_world not in MODES:
        raise ValueError("predicted world state is invalid")
    r = _probability(reliability)
    if r < Fraction(1, 3):
        raise ValueError("declared anchor reliability is outside supported model")
    return r if anchor == predicted_world else (1 - r) / 2


def infer_source(cues: tuple[int, ...] | list[int], anchor: int,
                 reliability: Fraction | int) -> SourcePosterior:
    """Return P(world-only|Y,A) and P(sensor-only|Y,A) under equal priors.

    E066 establishes equal P(Y) for the two specific hypotheses. World-only
    predicts R_last=Y_last; sensor-only predicts R_last=Y_first. Neither
    realized source nor hidden R is available to this candidate function.
    """
    history = _cue_history(cues)
    world = anchor_likelihood(anchor, history[-1], reliability)
    sensor = anchor_likelihood(anchor, history[0], reliability)
    normalizer = world + sensor
    if normalizer == 0:
        return SourcePosterior("UNMODELLED", None, None)
    return SourcePosterior("INFERRED", world / normalizer, sensor / normalizer)
