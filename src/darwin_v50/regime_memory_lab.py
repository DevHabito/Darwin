"""Selective recurrent-regime memory for Darwin H50-L7.

The model stores Beta-Bernoulli prototypes after causal change detections and
may reuse a matching prototype later.  A failed match means only that no
prototype is activated; the run-length posterior still emits a forecast.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import math
import random
from typing import Any, Sequence

from .models import ValidationError, canonical_json, parse_json
from .run_length_lab import PrunedBayesianRunLengthForecaster
from .temporal_lab import (
    BinaryStreamObservation,
    ChangeDetection,
    TwoWindowMeanShiftDetector,
)


REGIME_MEMORY_SCHEDULE_XOR_MASK = 0x7E611
TOTAL_REGIME_MEMORY_OBSERVATIONS = 3000


def _is_probability(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0.0 < value < 1.0
    )


@dataclass(frozen=True, slots=True)
class RegimeMemorySchedule:
    seed: int
    family: str
    durations: tuple[int, int, int, int, int]
    labels: tuple[str, str, str, str, str]
    probability_a: float
    probability_b: float
    probability_c: float

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("schedule seed must be an integer")
        if self.family not in {"recurring", "novelty"}:
            raise ValidationError("schedule family is invalid")
        if (
            not isinstance(self.durations, tuple)
            or len(self.durations) != 5
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 400
                for value in self.durations
            )
            or any(value > 500 for value in self.durations[:4])
            or sum(self.durations) != TOTAL_REGIME_MEMORY_OBSERVATIONS
        ):
            raise ValidationError("schedule durations are invalid")
        expected_labels = (
            ("A", "B", "A", "B", "A")
            if self.family == "recurring"
            else ("A", "B", "A", "C", "B")
        )
        if self.labels != expected_labels:
            raise ValidationError("schedule labels do not match its family")
        for name, value in (
            ("probability_a", self.probability_a),
            ("probability_b", self.probability_b),
            ("probability_c", self.probability_c),
        ):
            if not _is_probability(value):
                raise ValidationError(f"{name} must be a probability")
        if abs(self.probability_a - self.probability_b) < 0.70 - 1e-12:
            raise ValidationError("A and B must be separated by at least 0.70")
        if min(
            abs(self.probability_c - self.probability_a),
            abs(self.probability_c - self.probability_b),
        ) < 0.30 - 1e-12:
            raise ValidationError("C must be separated from A and B")

    @classmethod
    def from_seed(cls, seed: int) -> "RegimeMemorySchedule":
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("schedule seed must be an integer")
        rng = random.Random(seed ^ REGIME_MEMORY_SCHEDULE_XOR_MASK)
        high = rng.choice((0.85, 0.90))
        low = rng.choice((0.10, 0.15))
        a_is_high = bool(rng.randrange(2))
        first_four = tuple(rng.randint(400, 500) for _ in range(4))
        final_duration = TOTAL_REGIME_MEMORY_OBSERVATIONS - sum(first_four)
        family = "recurring" if seed % 2 == 0 else "novelty"
        return cls(
            seed=seed,
            family=family,
            durations=(
                first_four[0],
                first_four[1],
                first_four[2],
                first_four[3],
                final_duration,
            ),
            labels=(
                ("A", "B", "A", "B", "A")
                if family == "recurring"
                else ("A", "B", "A", "C", "B")
            ),
            probability_a=high if a_is_high else low,
            probability_b=low if a_is_high else high,
            probability_c=rng.choice((0.45, 0.50, 0.55)),
        )

    @property
    def phase_start_indices(self) -> tuple[int, int, int, int, int]:
        starts = [1]
        for duration in self.durations[:-1]:
            starts.append(starts[-1] + duration)
        return tuple(starts)  # type: ignore[return-value]

    @property
    def recurrence_indices(self) -> tuple[int, ...]:
        seen: set[str] = set()
        result: list[int] = []
        for label, index in zip(
            self.labels,
            self.phase_start_indices,
            strict=True,
        ):
            if label in seen:
                result.append(index)
            seen.add(label)
        return tuple(result)

    @property
    def novelty_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for label, index in zip(
                self.labels,
                self.phase_start_indices,
                strict=True,
            )
            if label == "C"
        )

    def phase_index_at(self, index: int) -> int:
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= TOTAL_REGIME_MEMORY_OBSERVATIONS
        ):
            raise ValidationError("stream index is outside the registered range")
        phase = 0
        for candidate, start in enumerate(self.phase_start_indices):
            if index >= start:
                phase = candidate
            else:
                break
        return phase

    def label_at(self, index: int) -> str:
        return self.labels[self.phase_index_at(index)]

    def probability_at(self, index: int) -> float:
        label = self.label_at(index)
        return {
            "A": self.probability_a,
            "B": self.probability_b,
            "C": self.probability_c,
        }[label]


class RegimeMemoryBernoulliStream:
    """Outcome stream with recurrent and genuinely novel regime families."""

    def __init__(self, seed: int) -> None:
        self.schedule = RegimeMemorySchedule.from_seed(seed)
        self._rng = random.Random(seed)
        self._next_index = 1

    def next_observation(self) -> BinaryStreamObservation:
        if self._next_index > TOTAL_REGIME_MEMORY_OBSERVATIONS:
            raise StopIteration("stream is exhausted")
        index = self._next_index
        observation = BinaryStreamObservation(
            index=index,
            outcome=self._rng.random() < self.schedule.probability_at(index),
        )
        self._next_index += 1
        return observation


@dataclass(frozen=True, slots=True)
class RegimePrototype:
    prototype_id: int
    successes: int
    failures: int
    consolidations: int

    def __post_init__(self) -> None:
        for name, value in (
            ("prototype_id", self.prototype_id),
            ("successes", self.successes),
            ("failures", self.failures),
            ("consolidations", self.consolidations),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < (1 if name in {"prototype_id", "consolidations"} else 0)
            ):
                raise ValidationError(f"{name} has an invalid value")
        if self.successes + self.failures < 1:
            raise ValidationError("prototype requires evidence")

    @property
    def evidence_count(self) -> int:
        return self.successes + self.failures

    @property
    def probability(self) -> float:
        return (1.0 + self.successes) / (2.0 + self.evidence_count)


@dataclass(frozen=True, slots=True)
class RegimeMemoryTransition:
    detection_index: int
    decision_index: int
    estimated_boundary_index: int
    consolidated_prototype_id: int
    retrieved_prototype_id: int | None
    retrieved_probability: float | None
    recent_mean: float
    repository_size: int
    abstained: bool

    def __post_init__(self) -> None:
        for name, value in (
            ("detection_index", self.detection_index),
            ("decision_index", self.decision_index),
            ("estimated_boundary_index", self.estimated_boundary_index),
            ("consolidated_prototype_id", self.consolidated_prototype_id),
            ("repository_size", self.repository_size),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise ValidationError(f"{name} must be a positive integer")
        if self.estimated_boundary_index > self.detection_index:
            raise ValidationError("estimated boundary cannot follow detection")
        if self.decision_index <= self.detection_index:
            raise ValidationError("decision must follow detection")
        if (
            isinstance(self.recent_mean, bool)
            or not isinstance(self.recent_mean, (int, float))
            or not math.isfinite(self.recent_mean)
            or not 0.0 <= self.recent_mean <= 1.0
        ):
            raise ValidationError("recent_mean must be within [0, 1]")
        if self.retrieved_prototype_id is None:
            if self.retrieved_probability is not None or not self.abstained:
                raise ValidationError("abstention fields are inconsistent")
        else:
            if (
                isinstance(self.retrieved_prototype_id, bool)
                or not isinstance(self.retrieved_prototype_id, int)
                or self.retrieved_prototype_id < 1
                or not _is_probability(self.retrieved_probability)
                or self.abstained
            ):
                raise ValidationError("retrieval fields are inconsistent")


@dataclass(frozen=True, slots=True)
class RegimeMemoryForecast:
    probability: float
    base_probability: float
    active_prototype_id: int | None
    active_prototype_probability: float | None

    def __post_init__(self) -> None:
        for name, value in (
            ("probability", self.probability),
            ("base_probability", self.base_probability),
        ):
            if not _is_probability(value):
                raise ValidationError(f"{name} must be within (0, 1)")
        if self.active_prototype_id is None:
            if self.active_prototype_probability is not None:
                raise ValidationError("inactive forecast cannot have a prototype")
        elif (
            isinstance(self.active_prototype_id, bool)
            or not isinstance(self.active_prototype_id, int)
            or self.active_prototype_id < 1
            or not _is_probability(self.active_prototype_probability)
        ):
            raise ValidationError("active prototype fields are invalid")


class RegimeRepositoryForecaster:
    """Run-length predictor with explicit, selectively activated prototypes."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        detector_window_size: int = 64,
        false_alarm_delta: float = 0.05,
        match_tolerance: float = 0.10,
        retrieval_weight: float = 0.25,
        maximum_working_memory: int = 512,
        retrieval_enabled: bool = True,
        expected_duration: int = 400,
        maximum_hypotheses: int = 64,
    ) -> None:
        detector = TwoWindowMeanShiftDetector(
            window_size=detector_window_size,
            false_alarm_delta=false_alarm_delta,
        )
        for name, value in (
            ("match_tolerance", match_tolerance),
            ("retrieval_weight", retrieval_weight),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 < value < 1.0
            ):
                raise ValidationError(f"{name} must be within (0, 1)")
        if (
            isinstance(maximum_working_memory, bool)
            or not isinstance(maximum_working_memory, int)
            or maximum_working_memory < 2 * detector.window_size
        ):
            raise ValidationError(
                "maximum_working_memory must cover both detector windows"
            )
        if not isinstance(retrieval_enabled, bool):
            raise ValidationError("retrieval_enabled must be boolean")
        self.detector_window_size = detector.window_size
        self.false_alarm_delta = detector.false_alarm_delta
        self.match_tolerance = float(match_tolerance)
        self.retrieval_weight = float(retrieval_weight)
        self.maximum_working_memory = maximum_working_memory
        self.retrieval_enabled = retrieval_enabled
        self.expected_duration = expected_duration
        self.maximum_hypotheses = maximum_hypotheses
        self._base = PrunedBayesianRunLengthForecaster(
            expected_duration=expected_duration,
            maximum_hypotheses=maximum_hypotheses,
        )
        self._detector = detector
        self._archive: list[BinaryStreamObservation] = []
        self._working: deque[BinaryStreamObservation] = deque(
            maxlen=maximum_working_memory
        )
        self._prototypes: list[RegimePrototype] = []
        self._transitions: list[RegimeMemoryTransition] = []
        self._active_prototype_id: int | None = None
        self._pending_detection: ChangeDetection | None = None
        self._pending_consolidated_prototype_id: int | None = None
        self._confirmation: list[BinaryStreamObservation] = []

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._archive)

    @property
    def working_memory(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._working)

    @property
    def prototypes(self) -> tuple[RegimePrototype, ...]:
        return tuple(self._prototypes)

    @property
    def transitions(self) -> tuple[RegimeMemoryTransition, ...]:
        return tuple(self._transitions)

    @property
    def active_prototype_id(self) -> int | None:
        return self._active_prototype_id

    def _prototype_by_id(self, prototype_id: int) -> RegimePrototype:
        return self._prototypes[prototype_id - 1]

    def predict(self) -> RegimeMemoryForecast:
        base_probability = self._base.predict_probability()
        active = (
            self._prototype_by_id(self._active_prototype_id)
            if self._active_prototype_id is not None
            else None
        )
        if active is None or not self.retrieval_enabled:
            probability = base_probability
            active_id = None
            active_probability = None
        else:
            active_probability = active.probability
            probability = (
                (1.0 - self.retrieval_weight) * base_probability
                + self.retrieval_weight * active_probability
            )
            active_id = active.prototype_id
        return RegimeMemoryForecast(
            probability=probability,
            base_probability=base_probability,
            active_prototype_id=active_id,
            active_prototype_probability=active_probability,
        )

    def _nearest_prototype(self, probability: float) -> RegimePrototype | None:
        if not self._prototypes:
            return None
        nearest = min(
            self._prototypes,
            key=lambda item: (
                abs(item.probability - probability),
                item.prototype_id,
            ),
        )
        if abs(nearest.probability - probability) > self.match_tolerance:
            return None
        return nearest

    def _consolidate(
        self,
        observations: Sequence[BinaryStreamObservation],
    ) -> RegimePrototype:
        if not observations:
            raise ValidationError("cannot consolidate empty evidence")
        successes = sum(item.outcome for item in observations)
        failures = len(observations) - successes
        probability = (1.0 + successes) / (2.0 + len(observations))
        nearest = self._nearest_prototype(probability)
        if nearest is None:
            result = RegimePrototype(
                prototype_id=len(self._prototypes) + 1,
                successes=successes,
                failures=failures,
                consolidations=1,
            )
            self._prototypes.append(result)
            return result
        result = replace(
            nearest,
            successes=nearest.successes + successes,
            failures=nearest.failures + failures,
            consolidations=nearest.consolidations + 1,
        )
        self._prototypes[nearest.prototype_id - 1] = result
        return result

    def observe(
        self,
        observation: BinaryStreamObservation,
    ) -> ChangeDetection | None:
        expected = len(self._archive) + 1
        if observation.index != expected:
            raise ValidationError(
                f"expected observation index {expected}, got {observation.index}"
            )
        self._base.observe(observation)
        self._archive.append(observation)
        self._working.append(observation)
        detection, recent = self._detector.observe(observation)
        if self._pending_detection is not None:
            if detection is not None:
                raise ValidationError(
                    "detector signalled during a confirmation window"
                )
            self._confirmation.append(observation)
            if len(self._confirmation) < self.detector_window_size:
                return None
            confirmation_mean = sum(
                item.outcome for item in self._confirmation
            ) / len(self._confirmation)
            nearest = self._nearest_prototype(confirmation_mean)
            retrieved = nearest if nearest is not None else None
            self._active_prototype_id = (
                retrieved.prototype_id
                if retrieved is not None and self.retrieval_enabled
                else None
            )
            pending = self._pending_detection
            consolidated_id = self._pending_consolidated_prototype_id
            if consolidated_id is None:
                raise ValidationError("pending consolidation is missing")
            self._transitions.append(
                RegimeMemoryTransition(
                    detection_index=pending.detection_index,
                    decision_index=observation.index,
                    estimated_boundary_index=pending.estimated_boundary_index,
                    consolidated_prototype_id=consolidated_id,
                    retrieved_prototype_id=(
                        retrieved.prototype_id
                        if retrieved is not None
                        else None
                    ),
                    retrieved_probability=(
                        retrieved.probability
                        if retrieved is not None
                        else None
                    ),
                    recent_mean=confirmation_mean,
                    repository_size=len(self._prototypes),
                    abstained=retrieved is None,
                )
            )
            self._pending_detection = None
            self._pending_consolidated_prototype_id = None
            self._confirmation.clear()
            return None
        if detection is None:
            return None
        earlier = tuple(
            item
            for item in self._working
            if item.index < detection.estimated_boundary_index
        )
        consolidated = self._consolidate(earlier)
        self._active_prototype_id = None
        self._pending_detection = detection
        self._pending_consolidated_prototype_id = consolidated.prototype_id
        self._confirmation.clear()
        self._working.clear()
        self._working.extend(recent)
        return detection

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "detector_window_size": self.detector_window_size,
                "false_alarm_delta": self.false_alarm_delta,
                "match_tolerance": self.match_tolerance,
                "retrieval_weight": self.retrieval_weight,
                "maximum_working_memory": self.maximum_working_memory,
                "retrieval_enabled": self.retrieval_enabled,
                "expected_duration": self.expected_duration,
                "maximum_hypotheses": self.maximum_hypotheses,
                "archive": [
                    {"index": item.index, "outcome": item.outcome}
                    for item in self._archive
                ],
                "working_indices": [item.index for item in self._working],
                "detector_buffer_indices": [
                    item.index for item in self._detector.buffer
                ],
                "prototypes": [
                    {
                        "prototype_id": item.prototype_id,
                        "successes": item.successes,
                        "failures": item.failures,
                        "consolidations": item.consolidations,
                    }
                    for item in self._prototypes
                ],
                "transitions": [
                    {
                        "detection_index": item.detection_index,
                        "decision_index": item.decision_index,
                        "estimated_boundary_index": (
                            item.estimated_boundary_index
                        ),
                        "consolidated_prototype_id": (
                            item.consolidated_prototype_id
                        ),
                        "retrieved_prototype_id": item.retrieved_prototype_id,
                        "retrieved_probability": item.retrieved_probability,
                        "recent_mean": item.recent_mean,
                        "repository_size": item.repository_size,
                        "abstained": item.abstained,
                    }
                    for item in self._transitions
                ],
                "active_prototype_id": self._active_prototype_id,
                "pending_detection": (
                    {
                        "detection_index": self._pending_detection.detection_index,
                        "estimated_boundary_index": (
                            self._pending_detection.estimated_boundary_index
                        ),
                        "earlier_mean": self._pending_detection.earlier_mean,
                        "recent_mean": self._pending_detection.recent_mean,
                        "absolute_mean_gap": (
                            self._pending_detection.absolute_mean_gap
                        ),
                        "threshold": self._pending_detection.threshold,
                        "window_size": self._pending_detection.window_size,
                    }
                    if self._pending_detection is not None
                    else None
                ),
                "pending_consolidated_prototype_id": (
                    self._pending_consolidated_prototype_id
                ),
                "confirmation_indices": [
                    item.index for item in self._confirmation
                ],
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "RegimeRepositoryForecaster":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported regime-memory snapshot")
        try:
            model = cls(
                detector_window_size=parsed["detector_window_size"],
                false_alarm_delta=parsed["false_alarm_delta"],
                match_tolerance=parsed["match_tolerance"],
                retrieval_weight=parsed["retrieval_weight"],
                maximum_working_memory=parsed["maximum_working_memory"],
                retrieval_enabled=parsed["retrieval_enabled"],
                expected_duration=parsed["expected_duration"],
                maximum_hypotheses=parsed["maximum_hypotheses"],
            )
            archive_rows = parsed["archive"]
        except KeyError as error:
            raise ValidationError(
                f"regime-memory snapshot missing field: {error.args[0]}"
            ) from error
        if not isinstance(archive_rows, list):
            raise ValidationError("regime-memory archive must be a list")
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
        if canonical_json(parsed) != model.to_snapshot():
            raise ValidationError(
                "regime-memory snapshot does not match replayed archive"
            )
        return model
