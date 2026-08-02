"""Multiscale temporal learning components for Darwin H50-L5.

The forecaster combines stationary and fixed-window experts using a
multiplicative loss update followed by fixed weight sharing.  It is a local,
auditable implementation inspired by fixed-share; no theorem from the
published algorithm is claimed for this exact configuration.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import random
from typing import Sequence

from .models import ValidationError, canonical_json, parse_json
from .temporal_lab import BinaryStreamObservation


DEFAULT_EXPERT_WINDOWS = (16, 32, 64, 128, 256, 512, 1024)


def _fixed_share_weights_after_outcome(
    weights: tuple[float, ...],
    probabilities: tuple[float, ...],
    outcome: bool,
    *,
    eta: float,
    share_rate: float,
) -> tuple[float, ...]:
    numeric_outcome = float(outcome)
    multiplicative = tuple(
        weight
        * math.exp(-eta * (expert_probability - numeric_outcome) ** 2)
        for weight, expert_probability in zip(
            weights,
            probabilities,
            strict=True,
        )
    )
    total = sum(multiplicative)
    if not math.isfinite(total) or total <= 0.0:
        raise RuntimeError("expert weights lost numeric normalization")
    normalized = tuple(value / total for value in multiplicative)
    expert_count = len(normalized)
    shared = tuple(
        (1.0 - share_rate) * value + share_rate / expert_count
        for value in normalized
    )
    shared_total = sum(shared)
    return tuple(value / shared_total for value in shared)


@dataclass(frozen=True, slots=True)
class MultiscaleForecast:
    probability: float
    expert_labels: tuple[str, ...]
    expert_probabilities: tuple[float, ...]
    expert_weights: tuple[float, ...]
    dominant_expert: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.probability, bool)
            or not isinstance(self.probability, (int, float))
            or not math.isfinite(self.probability)
            or not 0.0 <= self.probability <= 1.0
        ):
            raise ValidationError(
                "multiscale probability must be within [0, 1]"
            )
        count = len(self.expert_labels)
        if count < 2:
            raise ValidationError("multiscale forecast requires experts")
        if (
            len(set(self.expert_labels)) != count
            or len(self.expert_probabilities) != count
            or len(self.expert_weights) != count
        ):
            raise ValidationError("multiscale expert vectors are inconsistent")
        if self.dominant_expert not in self.expert_labels:
            raise ValidationError("dominant expert is not in the expert set")
        for value in self.expert_probabilities:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError(
                    "expert probabilities must be within [0, 1]"
                )
        for value in self.expert_weights:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValidationError(
                    "expert weights must be finite and non-negative"
                )
        if not math.isclose(
            sum(self.expert_weights),
            1.0,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValidationError("expert weights must sum to one")
        expected_dominant = self.expert_labels[
            max(range(count), key=self.expert_weights.__getitem__)
        ]
        if self.dominant_expert != expected_dominant:
            raise ValidationError("dominant expert does not match weights")


class MultiphaseBernoulliStream:
    """Pre-registered abrupt, recurrent, and gradual Bernoulli regimes."""

    TOTAL_OBSERVATIONS = 3000
    FIRST_ABRUPT_INDEX = 601
    RECURRENCE_INDEX = 1201
    GRADUAL_START_INDEX = 1801
    GRADUAL_END_INDEX = 2400

    def __init__(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("stream seed must be an integer")
        self.seed = seed
        self._rng = random.Random(seed)
        self._next_index = 1

    @classmethod
    def probability_at(cls, index: int) -> float:
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= cls.TOTAL_OBSERVATIONS
        ):
            raise ValidationError("stream index is outside the registered range")
        if index < cls.FIRST_ABRUPT_INDEX:
            return 0.85
        if index < cls.RECURRENCE_INDEX:
            return 0.15
        if index < cls.GRADUAL_START_INDEX:
            return 0.85
        if index <= cls.GRADUAL_END_INDEX:
            progress = (index - cls.GRADUAL_START_INDEX) / (
                cls.GRADUAL_END_INDEX - cls.GRADUAL_START_INDEX
            )
            return 0.85 - 0.70 * progress
        return 0.15

    def next_observation(self) -> BinaryStreamObservation:
        if self._next_index > self.TOTAL_OBSERVATIONS:
            raise StopIteration("stream is exhausted")
        index = self._next_index
        observation = BinaryStreamObservation(
            index=index,
            outcome=self._rng.random() < self.probability_at(index),
        )
        self._next_index += 1
        return observation


class FixedShareMemoryForecaster:
    """Online arbitration among stationary and fixed-window memories."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        window_sizes: Sequence[int] = DEFAULT_EXPERT_WINDOWS,
        eta: float = 2.0,
        share_rate: float = 0.01,
    ) -> None:
        normalized_windows = tuple(window_sizes)
        if not normalized_windows:
            raise ValidationError("at least one window expert is required")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 2
            for value in normalized_windows
        ):
            raise ValidationError(
                "expert windows must be integers of at least two"
            )
        if (
            len(set(normalized_windows)) != len(normalized_windows)
            or tuple(sorted(normalized_windows)) != normalized_windows
        ):
            raise ValidationError(
                "expert windows must be unique and strictly increasing"
            )
        if (
            isinstance(eta, bool)
            or not isinstance(eta, (int, float))
            or not math.isfinite(eta)
            or eta <= 0.0
        ):
            raise ValidationError("eta must be finite and positive")
        if (
            isinstance(share_rate, bool)
            or not isinstance(share_rate, (int, float))
            or not math.isfinite(share_rate)
            or not 0.0 < share_rate < 1.0
        ):
            raise ValidationError("share_rate must be within (0, 1)")
        self.window_sizes = normalized_windows
        self.eta = float(eta)
        self.share_rate = float(share_rate)
        self._stationary_successes = 0
        self._window_buffers = tuple(
            deque(maxlen=window_size)
            for window_size in self.window_sizes
        )
        self._window_successes = [0 for _ in self.window_sizes]
        expert_count = 1 + len(self.window_sizes)
        self._weights = tuple(1.0 / expert_count for _ in range(expert_count))
        self._archive: list[BinaryStreamObservation] = []
        self._pending_forecast: MultiscaleForecast | None = None

    @property
    def expert_labels(self) -> tuple[str, ...]:
        return ("stationary",) + tuple(
            f"window_{window_size}" for window_size in self.window_sizes
        )

    @property
    def weights(self) -> tuple[float, ...]:
        return self._weights

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._archive)

    def _expert_probabilities(self) -> tuple[float, ...]:
        stationary_probability = (1 + self._stationary_successes) / (
            2 + len(self._archive)
        )
        return (stationary_probability,) + tuple(
            (1 + successes) / (2 + len(buffer))
            for successes, buffer in zip(
                self._window_successes,
                self._window_buffers,
                strict=True,
            )
        )

    def predict(self) -> MultiscaleForecast:
        probabilities = self._expert_probabilities()
        probability = sum(
            weight * expert_probability
            for weight, expert_probability in zip(
                self._weights,
                probabilities,
                strict=True,
            )
        )
        dominant_index = max(
            range(len(self._weights)),
            key=self._weights.__getitem__,
        )
        labels = self.expert_labels
        forecast = MultiscaleForecast(
            probability=probability,
            expert_labels=labels,
            expert_probabilities=probabilities,
            expert_weights=self._weights,
            dominant_expert=labels[dominant_index],
        )
        self._pending_forecast = forecast
        return forecast

    def observe(self, observation: BinaryStreamObservation) -> None:
        expected = len(self._archive) + 1
        if observation.index != expected:
            raise ValidationError(
                f"expected observation index {expected}, got {observation.index}"
            )
        if (
            self._pending_forecast is not None
            and self._pending_forecast.expert_weights == self._weights
        ):
            probabilities = self._pending_forecast.expert_probabilities
        else:
            probabilities = self._expert_probabilities()
        self._weights = _fixed_share_weights_after_outcome(
            self._weights,
            probabilities,
            observation.outcome,
            eta=self.eta,
            share_rate=self.share_rate,
        )
        self._pending_forecast = None
        self._stationary_successes += int(observation.outcome)
        for index, buffer in enumerate(self._window_buffers):
            if (
                len(buffer) == buffer.maxlen
                and buffer[0]
            ):
                self._window_successes[index] -= 1
            buffer.append(observation.outcome)
            self._window_successes[index] += int(observation.outcome)
        self._archive.append(observation)

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "window_sizes": list(self.window_sizes),
                "eta": self.eta,
                "share_rate": self.share_rate,
                "weights": list(self._weights),
                "archive": [
                    {"index": item.index, "outcome": item.outcome}
                    for item in self._archive
                ],
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "FixedShareMemoryForecaster":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported multiscale snapshot")
        try:
            model = cls(
                window_sizes=parsed["window_sizes"],
                eta=parsed["eta"],
                share_rate=parsed["share_rate"],
            )
            archive_rows = parsed["archive"]
            stored_weights = parsed["weights"]
        except KeyError as error:
            raise ValidationError(
                f"multiscale snapshot missing field: {error.args[0]}"
            ) from error
        if not isinstance(archive_rows, list) or not isinstance(
            stored_weights, list
        ):
            raise ValidationError("invalid multiscale snapshot")
        if len(stored_weights) != len(model.weights):
            raise ValidationError("snapshot expert weight count is invalid")
        validated_weights: list[float] = []
        for value in stored_weights:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValidationError(
                    "snapshot weights must be finite and non-negative"
                )
            validated_weights.append(float(value))
        if not math.isclose(
            sum(validated_weights),
            1.0,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValidationError("snapshot weights must sum to one")
        for row in archive_rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid archived observation")
            try:
                observation = BinaryStreamObservation(
                    index=row["index"],
                    outcome=row["outcome"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"archived observation missing field: {error.args[0]}"
                ) from error
            model.observe(observation)
        if tuple(validated_weights) != model.weights:
            raise ValidationError(
                "snapshot weights do not match replayed archive"
            )
        return model
