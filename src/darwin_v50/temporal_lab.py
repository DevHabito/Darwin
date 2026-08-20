"""Temporal adaptation components for Darwin H50-L4.

The implementation separates an immutable observation archive from a bounded
working memory.  A conservative two-window mean detector may reset working
memory after an observed distribution shift; archived evidence is never
deleted by that adaptation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import random
from typing import Any, Sequence

from .models import ValidationError, canonical_json, parse_json


@dataclass(frozen=True, slots=True)
class BinaryStreamObservation:
    index: int
    outcome: bool

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise ValidationError("observation index must be an integer")
        if self.index < 1:
            raise ValidationError("observation index must be positive")
        if not isinstance(self.outcome, bool):
            raise ValidationError("outcome must be boolean")


@dataclass(frozen=True, slots=True)
class BinaryForecast:
    probability: float
    evidence_count: int
    success_count: int
    failure_count: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.probability, bool)
            or not isinstance(self.probability, (int, float))
            or not math.isfinite(self.probability)
            or not 0.0 <= self.probability <= 1.0
        ):
            raise ValidationError("forecast probability must be within [0, 1]")
        for name, value in (
            ("evidence_count", self.evidence_count),
            ("success_count", self.success_count),
            ("failure_count", self.failure_count),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValidationError(f"{name} must be a non-negative integer")
        if self.success_count + self.failure_count != self.evidence_count:
            raise ValidationError("forecast counts must sum to evidence_count")


@dataclass(frozen=True, slots=True)
class ChangeDetection:
    detection_index: int
    estimated_boundary_index: int
    earlier_mean: float
    recent_mean: float
    absolute_mean_gap: float
    threshold: float
    window_size: int

    def __post_init__(self) -> None:
        for name, value in (
            ("detection_index", self.detection_index),
            ("estimated_boundary_index", self.estimated_boundary_index),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise ValidationError(f"{name} must be a positive integer")
        if self.estimated_boundary_index > self.detection_index:
            raise ValidationError("estimated boundary cannot follow detection")
        if (
            isinstance(self.window_size, bool)
            or not isinstance(self.window_size, int)
            or self.window_size < 8
        ):
            raise ValidationError("detection window_size must be at least eight")
        for name, value in (
            ("earlier_mean", self.earlier_mean),
            ("recent_mean", self.recent_mean),
            ("absolute_mean_gap", self.absolute_mean_gap),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError(f"{name} must be within [0, 1]")
        if not math.isclose(
            self.absolute_mean_gap,
            abs(self.earlier_mean - self.recent_mean),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValidationError("absolute_mean_gap is inconsistent")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(self.threshold)
            or self.threshold <= 0.0
        ):
            raise ValidationError("detection threshold must be positive")
        if self.absolute_mean_gap <= self.threshold:
            raise ValidationError("detection gap must exceed its threshold")


class RegimeShiftBernoulliStream:
    """One abrupt hidden probability change at a pre-registered index."""

    def __init__(
        self,
        seed: int,
        *,
        pre_change_probability: float = 0.85,
        post_change_probability: float = 0.15,
        change_index: int = 1001,
        total_observations: int = 2000,
    ) -> None:
        for name, value in (
            ("pre_change_probability", pre_change_probability),
            ("post_change_probability", post_change_probability),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError(f"{name} must be a probability")
        if pre_change_probability == post_change_probability:
            raise ValidationError("the two regimes must differ")
        if (
            isinstance(change_index, bool)
            or not isinstance(change_index, int)
            or change_index < 2
        ):
            raise ValidationError("change_index must be an integer after one")
        if (
            isinstance(total_observations, bool)
            or not isinstance(total_observations, int)
            or total_observations < change_index
        ):
            raise ValidationError(
                "total_observations must include the post-change regime"
            )
        self.seed = int(seed)
        self.pre_change_probability = float(pre_change_probability)
        self.post_change_probability = float(post_change_probability)
        self.change_index = change_index
        self.total_observations = total_observations
        self._rng = random.Random(seed)
        self._next_index = 1

    def next_observation(self) -> BinaryStreamObservation:
        if self._next_index > self.total_observations:
            raise StopIteration("stream is exhausted")
        probability = (
            self.pre_change_probability
            if self._next_index < self.change_index
            else self.post_change_probability
        )
        observation = BinaryStreamObservation(
            index=self._next_index,
            outcome=self._rng.random() < probability,
        )
        self._next_index += 1
        return observation


def beta_bernoulli_forecast(
    observations: Sequence[BinaryStreamObservation],
    *,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> BinaryForecast:
    for name, value in (("prior_alpha", prior_alpha), ("prior_beta", prior_beta)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0.0
        ):
            raise ValidationError(f"{name} must be finite and positive")
    successes = sum(observation.outcome for observation in observations)
    failures = len(observations) - successes
    probability = (prior_alpha + successes) / (
        prior_alpha + prior_beta + len(observations)
    )
    return BinaryForecast(
        probability=probability,
        evidence_count=len(observations),
        success_count=successes,
        failure_count=failures,
    )


class StationaryBernoulliForecaster:
    """Baseline that gives every historical outcome equal weight forever."""

    def __init__(self) -> None:
        self._archive: list[BinaryStreamObservation] = []

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._archive)

    def predict(self) -> BinaryForecast:
        return beta_bernoulli_forecast(self._archive)

    def observe(self, observation: BinaryStreamObservation) -> None:
        expected = len(self._archive) + 1
        if observation.index != expected:
            raise ValidationError(
                f"expected observation index {expected}, got {observation.index}"
            )
        self._archive.append(observation)


class FixedWindowBernoulliForecaster:
    """Reactive baseline with a pre-selected, permanently short memory."""

    def __init__(self, window_size: int = 64) -> None:
        if (
            isinstance(window_size, bool)
            or not isinstance(window_size, int)
            or window_size < 2
        ):
            raise ValidationError("window_size must be an integer of at least two")
        self.window_size = window_size
        self._archive: list[BinaryStreamObservation] = []
        self._working: deque[BinaryStreamObservation] = deque(
            maxlen=window_size
        )

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._archive)

    def predict(self) -> BinaryForecast:
        return beta_bernoulli_forecast(tuple(self._working))

    def observe(self, observation: BinaryStreamObservation) -> None:
        expected = len(self._archive) + 1
        if observation.index != expected:
            raise ValidationError(
                f"expected observation index {expected}, got {observation.index}"
            )
        self._archive.append(observation)
        self._working.append(observation)


class TwoWindowMeanShiftDetector:
    """Detect a Bernoulli mean gap using two adjacent equal windows.

    This is not a full ADWIN or CUSUM implementation.  The threshold is a
    conservative Hoeffding-style bound fixed by ``false_alarm_delta``.
    """

    def __init__(
        self,
        *,
        window_size: int = 64,
        false_alarm_delta: float = 1e-6,
    ) -> None:
        if (
            isinstance(window_size, bool)
            or not isinstance(window_size, int)
            or window_size < 8
        ):
            raise ValidationError("detector window_size must be at least eight")
        if (
            isinstance(false_alarm_delta, bool)
            or not isinstance(false_alarm_delta, (int, float))
            or not math.isfinite(false_alarm_delta)
            or not 0.0 < false_alarm_delta < 1.0
        ):
            raise ValidationError("false_alarm_delta must be within (0, 1)")
        self.window_size = window_size
        self.false_alarm_delta = float(false_alarm_delta)
        self._buffer: deque[BinaryStreamObservation] = deque(
            maxlen=2 * window_size
        )

    @property
    def threshold(self) -> float:
        reciprocal_sum = 2.0 / self.window_size
        return math.sqrt(
            0.5
            * math.log(4.0 / self.false_alarm_delta)
            * reciprocal_sum
        )

    @property
    def buffer(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._buffer)

    def restore_buffer(
        self,
        observations: Sequence[BinaryStreamObservation],
    ) -> None:
        if len(observations) > 2 * self.window_size:
            raise ValidationError("restored detector buffer exceeds its capacity")
        self._buffer.clear()
        self._buffer.extend(observations)

    def observe(
        self,
        observation: BinaryStreamObservation,
    ) -> tuple[ChangeDetection | None, tuple[BinaryStreamObservation, ...]]:
        self._buffer.append(observation)
        if len(self._buffer) < 2 * self.window_size:
            return None, ()
        values = tuple(self._buffer)
        earlier = values[: self.window_size]
        recent = values[self.window_size :]
        earlier_mean = fmean_binary(earlier)
        recent_mean = fmean_binary(recent)
        gap = abs(earlier_mean - recent_mean)
        if gap <= self.threshold:
            return None, ()
        detection = ChangeDetection(
            detection_index=observation.index,
            estimated_boundary_index=recent[0].index,
            earlier_mean=earlier_mean,
            recent_mean=recent_mean,
            absolute_mean_gap=gap,
            threshold=self.threshold,
            window_size=self.window_size,
        )
        recent_copy = tuple(recent)
        self._buffer.clear()
        return detection, recent_copy


def fmean_binary(observations: Sequence[BinaryStreamObservation]) -> float:
    if not observations:
        raise ValidationError("mean requires observations")
    return sum(observation.outcome for observation in observations) / len(
        observations
    )


class AdaptiveBernoulliForecaster:
    """Forecast from working memory while retaining a complete archive."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        detector_window_size: int = 64,
        false_alarm_delta: float = 1e-6,
        maximum_working_memory: int = 512,
    ) -> None:
        detector = TwoWindowMeanShiftDetector(
            window_size=detector_window_size,
            false_alarm_delta=false_alarm_delta,
        )
        if (
            isinstance(maximum_working_memory, bool)
            or not isinstance(maximum_working_memory, int)
            or maximum_working_memory < detector.window_size
        ):
            raise ValidationError(
                "maximum_working_memory must cover a detector window"
            )
        self.detector_window_size = detector.window_size
        self.false_alarm_delta = detector.false_alarm_delta
        self.maximum_working_memory = maximum_working_memory
        self._archive: list[BinaryStreamObservation] = []
        self._working: deque[BinaryStreamObservation] = deque(
            maxlen=maximum_working_memory
        )
        self._detections: list[ChangeDetection] = []
        self._detector = detector

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._archive)

    @property
    def working_memory(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._working)

    @property
    def detections(self) -> tuple[ChangeDetection, ...]:
        return tuple(self._detections)

    def predict(self) -> BinaryForecast:
        return beta_bernoulli_forecast(tuple(self._working))

    def observe(
        self,
        observation: BinaryStreamObservation,
    ) -> ChangeDetection | None:
        expected = len(self._archive) + 1
        if observation.index != expected:
            raise ValidationError(
                f"expected observation index {expected}, got {observation.index}"
            )
        self._archive.append(observation)
        self._working.append(observation)
        detection, recent = self._detector.observe(observation)
        if detection is not None:
            self._detections.append(detection)
            self._working.clear()
            self._working.extend(recent)
        return detection

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "detector_window_size": self.detector_window_size,
                "false_alarm_delta": self.false_alarm_delta,
                "maximum_working_memory": self.maximum_working_memory,
                "archive": [
                    {"index": item.index, "outcome": item.outcome}
                    for item in self._archive
                ],
                "working_indices": [item.index for item in self._working],
                "detector_buffer_indices": [
                    item.index for item in self._detector.buffer
                ],
                "detections": [
                    {
                        "detection_index": event.detection_index,
                        "estimated_boundary_index": (
                            event.estimated_boundary_index
                        ),
                        "earlier_mean": event.earlier_mean,
                        "recent_mean": event.recent_mean,
                        "absolute_mean_gap": event.absolute_mean_gap,
                        "threshold": event.threshold,
                        "window_size": event.window_size,
                    }
                    for event in self._detections
                ],
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "AdaptiveBernoulliForecaster":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported adaptive model snapshot")
        try:
            model = cls(
                detector_window_size=parsed["detector_window_size"],
                false_alarm_delta=parsed["false_alarm_delta"],
                maximum_working_memory=parsed["maximum_working_memory"],
            )
            archive_rows = parsed["archive"]
            working_indices = parsed["working_indices"]
            detector_indices = parsed["detector_buffer_indices"]
            detection_rows = parsed["detections"]
        except KeyError as error:
            raise ValidationError(
                f"adaptive snapshot missing field: {error.args[0]}"
            ) from error
        if (
            not isinstance(archive_rows, list)
            or not isinstance(working_indices, list)
            or not isinstance(detector_indices, list)
            or not isinstance(detection_rows, list)
        ):
            raise ValidationError("invalid adaptive model snapshot")
        archive: list[BinaryStreamObservation] = []
        for row in archive_rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid archived observation")
            try:
                item = BinaryStreamObservation(
                    index=row["index"],
                    outcome=row["outcome"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"archived observation missing field: {error.args[0]}"
                ) from error
            if item.index != len(archive) + 1:
                raise ValidationError("archive indices must be contiguous")
            archive.append(item)
        by_index = {item.index: item for item in archive}

        def resolve_indices(
            values: list[Any],
            field: str,
        ) -> list[BinaryStreamObservation]:
            resolved: list[BinaryStreamObservation] = []
            for value in values:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValidationError(f"{field} must contain integer indices")
                item = by_index.get(value)
                if item is None:
                    raise ValidationError(f"{field} references missing archive item")
                resolved.append(item)
            if any(
                left.index >= right.index
                for left, right in zip(
                    resolved[:-1],
                    resolved[1:],
                    strict=True,
                )
            ):
                raise ValidationError(f"{field} must be strictly ordered")
            return resolved

        working = resolve_indices(working_indices, "working_indices")
        detector_buffer = resolve_indices(
            detector_indices,
            "detector_buffer_indices",
        )
        if len(working) > model.maximum_working_memory:
            raise ValidationError("working memory exceeds configured maximum")
        if working and working != archive[-len(working) :]:
            raise ValidationError("working memory must be an archive suffix")
        if detector_buffer and detector_buffer != archive[-len(detector_buffer) :]:
            raise ValidationError("detector buffer must be an archive suffix")
        detections: list[ChangeDetection] = []
        for row in detection_rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid detection row")
            try:
                detection = ChangeDetection(
                    detection_index=row["detection_index"],
                    estimated_boundary_index=row["estimated_boundary_index"],
                    earlier_mean=row["earlier_mean"],
                    recent_mean=row["recent_mean"],
                    absolute_mean_gap=row["absolute_mean_gap"],
                    threshold=row["threshold"],
                    window_size=row["window_size"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"detection row missing field: {error.args[0]}"
                ) from error
            if detection.detection_index not in by_index:
                raise ValidationError("detection references missing archive item")
            if detection.estimated_boundary_index not in by_index:
                raise ValidationError(
                    "detection boundary references missing archive item"
                )
            if detection.window_size != model.detector_window_size:
                raise ValidationError(
                    "detection window does not match model configuration"
                )
            if (
                detection.estimated_boundary_index
                != detection.detection_index - detection.window_size + 1
            ):
                raise ValidationError(
                    "detection boundary is inconsistent with its window"
                )
            if not math.isclose(
                detection.threshold,
                model._detector.threshold,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValidationError(
                    "detection threshold does not match model configuration"
                )
            if (
                detections
                and detection.detection_index
                <= detections[-1].detection_index
            ):
                raise ValidationError("detections must be strictly ordered")
            detection_end = detection.detection_index
            earlier_start = detection_end - 2 * detection.window_size + 1
            if earlier_start < 1:
                raise ValidationError(
                    "detection does not have two archived windows"
                )
            earlier = archive[
                earlier_start - 1 : earlier_start - 1 + detection.window_size
            ]
            recent = archive[
                detection.estimated_boundary_index - 1 : detection_end
            ]
            if (
                not math.isclose(
                    fmean_binary(earlier),
                    detection.earlier_mean,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or not math.isclose(
                    fmean_binary(recent),
                    detection.recent_mean,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ):
                raise ValidationError(
                    "detection means do not match archived observations"
                )
            detections.append(detection)
        model._archive = archive
        model._working.clear()
        model._working.extend(working)
        model._detections = detections
        model._detector.restore_buffer(detector_buffer)
        return model
