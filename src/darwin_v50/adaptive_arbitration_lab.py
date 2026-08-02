"""Adaptive arbitration between current inference and retrieved memory.

Darwin H50-L8 treats the run-length posterior as an always-awake expert and a
retrieved regime prototype as a sleeping expert.  Weights are updated only
after the corresponding outcome has been observed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any

from .models import ValidationError, canonical_json, parse_json
from .regime_memory_lab import RegimeRepositoryForecaster
from .temporal_lab import BinaryStreamObservation


ARBITRATION_SCHEDULE_XOR_MASK = 0xA81F3
TOTAL_ARBITRATION_OBSERVATIONS = 4200
ARBITRATION_AGE_BOUNDARIES = (16, 32, 64, 128)
ARBITRATION_BIN_COUNT = len(ARBITRATION_AGE_BOUNDARIES) + 1

ARBITRATION_FAMILIES = (
    "exact_recurrence",
    "shifted_recurrence",
    "returning_novelty",
    "late_novelty",
)

ARBITRATION_LABELS = {
    "exact_recurrence": ("A", "B", "A", "B", "A", "B", "A"),
    "shifted_recurrence": ("A", "B", "A", "B", "A", "B", "A"),
    "returning_novelty": ("A", "B", "A", "C", "B", "C", "A"),
    "late_novelty": ("A", "B", "A", "B", "C", "A", "B"),
}


def _validate_probability(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < value < 1.0
    ):
        raise ValidationError(f"{field} must be within (0, 1)")
    return float(value)


@dataclass(frozen=True, slots=True)
class ArbitrationSchedule:
    seed: int
    family: str
    durations: tuple[int, int, int, int, int, int, int]
    labels: tuple[str, str, str, str, str, str, str]
    probabilities: tuple[float, float, float, float, float, float, float]

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("schedule seed must be an integer")
        if self.family not in ARBITRATION_FAMILIES:
            raise ValidationError("arbitration schedule family is invalid")
        if self.family != ARBITRATION_FAMILIES[self.seed % 4]:
            raise ValidationError("schedule family does not match seed")
        if self.labels != ARBITRATION_LABELS[self.family]:
            raise ValidationError("schedule labels do not match family")
        if (
            not isinstance(self.durations, tuple)
            or len(self.durations) != 7
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 450 <= value <= 550
                for value in self.durations[:6]
            )
            or not 900 <= self.durations[6] <= 1500
            or sum(self.durations) != TOTAL_ARBITRATION_OBSERVATIONS
        ):
            raise ValidationError("arbitration schedule durations are invalid")
        if (
            not isinstance(self.probabilities, tuple)
            or len(self.probabilities) != 7
        ):
            raise ValidationError("arbitration probabilities are invalid")
        for index, probability in enumerate(self.probabilities):
            _validate_probability(probability, f"probabilities[{index}]")
        if any(
            abs(left - right) < 0.25
            for left, right in zip(
                self.probabilities[:-1],
                self.probabilities[1:],
                strict=True,
            )
        ):
            raise ValidationError(
                "adjacent regime probabilities must be separated"
            )
        if self.family != "shifted_recurrence":
            by_label: dict[str, float] = {}
            for label, probability in zip(
                self.labels,
                self.probabilities,
                strict=True,
            ):
                previous = by_label.setdefault(label, probability)
                if previous != probability:
                    raise ValidationError(
                        "non-shifted identities must have exact probabilities"
                    )
        else:
            for label in ("A", "B"):
                values = tuple(
                    probability
                    for candidate, probability in zip(
                        self.labels,
                        self.probabilities,
                        strict=True,
                    )
                    if candidate == label
                )
                if max(values) - min(values) > 0.08 + 1e-12:
                    raise ValidationError(
                        "shifted identity exceeds registered displacement"
                    )

    @classmethod
    def from_seed(cls, seed: int) -> "ArbitrationSchedule":
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("schedule seed must be an integer")
        rng = random.Random(seed ^ ARBITRATION_SCHEDULE_XOR_MASK)
        high = rng.choice((0.86, 0.90))
        low = rng.choice((0.10, 0.14))
        a_is_high = bool(rng.randrange(2))
        probability_by_label = {
            "A": high if a_is_high else low,
            "B": low if a_is_high else high,
            "C": rng.choice((0.45, 0.50, 0.55)),
        }
        first_six = tuple(rng.randint(450, 550) for _ in range(6))
        durations = first_six + (
            TOTAL_ARBITRATION_OBSERVATIONS - sum(first_six),
        )
        family = ARBITRATION_FAMILIES[seed % 4]
        labels = ARBITRATION_LABELS[family]
        if family == "shifted_recurrence":
            offsets = (-0.04, -0.02, 0.0, 0.02, 0.04)
            probabilities = tuple(
                probability_by_label[label] + rng.choice(offsets)
                for label in labels
            )
        else:
            probabilities = tuple(
                probability_by_label[label] for label in labels
            )
        return cls(
            seed=seed,
            family=family,
            durations=durations,  # type: ignore[arg-type]
            labels=labels,
            probabilities=probabilities,  # type: ignore[arg-type]
        )

    @property
    def phase_start_indices(
        self,
    ) -> tuple[int, int, int, int, int, int, int]:
        starts = [1]
        for duration in self.durations[:-1]:
            starts.append(starts[-1] + duration)
        return tuple(starts)  # type: ignore[return-value]

    @property
    def recurrence_indices(self) -> tuple[int, ...]:
        seen: set[str] = set()
        result: list[int] = []
        for label, start in zip(
            self.labels,
            self.phase_start_indices,
            strict=True,
        ):
            if label in seen:
                result.append(start)
            seen.add(label)
        return tuple(result)

    @property
    def novelty_indices(self) -> tuple[int, ...]:
        seen: set[str] = set()
        result: list[int] = []
        for label, start in zip(
            self.labels,
            self.phase_start_indices,
            strict=True,
        ):
            if label not in seen and label == "C":
                result.append(start)
            seen.add(label)
        return tuple(result)

    def phase_index_at(self, index: int) -> int:
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= TOTAL_ARBITRATION_OBSERVATIONS
        ):
            raise ValidationError("stream index is outside the registered range")
        phase = 0
        for candidate, start in enumerate(self.phase_start_indices):
            if index < start:
                break
            phase = candidate
        return phase

    def label_at(self, index: int) -> str:
        return self.labels[self.phase_index_at(index)]

    def probability_at(self, index: int) -> float:
        return self.probabilities[self.phase_index_at(index)]


class ArbitrationBernoulliStream:
    """Hidden seven-phase stream used by H50-L8."""

    def __init__(self, seed: int) -> None:
        self.schedule = ArbitrationSchedule.from_seed(seed)
        self._rng = random.Random(seed)
        self._next_index = 1

    def next_observation(self) -> BinaryStreamObservation:
        if self._next_index > TOTAL_ARBITRATION_OBSERVATIONS:
            raise StopIteration("stream is exhausted")
        index = self._next_index
        observation = BinaryStreamObservation(
            index=index,
            outcome=self._rng.random() < self.schedule.probability_at(index),
        )
        self._next_index += 1
        return observation


def arbitration_bin_for_age(age: int) -> int:
    if isinstance(age, bool) or not isinstance(age, int) or age < 1:
        raise ValidationError("active age must be a positive integer")
    for index, boundary in enumerate(ARBITRATION_AGE_BOUNDARIES):
        if age <= boundary:
            return index
    return ARBITRATION_BIN_COUNT - 1


@dataclass(frozen=True, slots=True)
class ExpertWeightDecision:
    probability: float
    base_probability: float
    memory_probability: float
    memory_weight: float
    active_age: int
    age_bin: int

    def __post_init__(self) -> None:
        for field, value in (
            ("probability", self.probability),
            ("base_probability", self.base_probability),
            ("memory_probability", self.memory_probability),
        ):
            _validate_probability(value, field)
        if (
            isinstance(self.memory_weight, bool)
            or not isinstance(self.memory_weight, (int, float))
            or not math.isfinite(self.memory_weight)
            or not 0.0 <= self.memory_weight <= 1.0
        ):
            raise ValidationError("memory_weight must be within [0, 1]")
        if arbitration_bin_for_age(self.active_age) != self.age_bin:
            raise ValidationError("age_bin does not match active_age")
        expected = (
            (1.0 - self.memory_weight) * self.base_probability
            + self.memory_weight * self.memory_probability
        )
        if not math.isclose(
            self.probability,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValidationError("expert decision probability is inconsistent")


class AgeBinnedExpertWeights:
    """Discounted exponential weights for an intermittently awake expert."""

    def __init__(
        self,
        *,
        learning_rate: float = 8.0,
        loss_discount: float = 0.99,
    ) -> None:
        if (
            isinstance(learning_rate, bool)
            or not isinstance(learning_rate, (int, float))
            or not math.isfinite(learning_rate)
            or learning_rate <= 0.0
        ):
            raise ValidationError("learning_rate must be finite and positive")
        if (
            isinstance(loss_discount, bool)
            or not isinstance(loss_discount, (int, float))
            or not math.isfinite(loss_discount)
            or not 0.0 < loss_discount <= 1.0
        ):
            raise ValidationError("loss_discount must be within (0, 1]")
        self.learning_rate = float(learning_rate)
        self.loss_discount = float(loss_discount)
        self._base_losses = [0.0] * ARBITRATION_BIN_COUNT
        self._memory_losses = [0.0] * ARBITRATION_BIN_COUNT

    @property
    def base_losses(self) -> tuple[float, ...]:
        return tuple(self._base_losses)

    @property
    def memory_losses(self) -> tuple[float, ...]:
        return tuple(self._memory_losses)

    def memory_weight(self, active_age: int) -> float:
        age_bin = arbitration_bin_for_age(active_age)
        base_score = math.log(0.75) - (
            self.learning_rate * self._base_losses[age_bin]
        )
        memory_score = math.log(0.25) - (
            self.learning_rate * self._memory_losses[age_bin]
        )
        maximum = max(base_score, memory_score)
        base_weight = math.exp(base_score - maximum)
        memory_weight = math.exp(memory_score - maximum)
        return memory_weight / (base_weight + memory_weight)

    def predict(
        self,
        *,
        base_probability: float,
        memory_probability: float,
        active_age: int,
    ) -> ExpertWeightDecision:
        base = _validate_probability(
            base_probability,
            "base_probability",
        )
        memory = _validate_probability(
            memory_probability,
            "memory_probability",
        )
        weight = self.memory_weight(active_age)
        return ExpertWeightDecision(
            probability=(1.0 - weight) * base + weight * memory,
            base_probability=base,
            memory_probability=memory,
            memory_weight=weight,
            active_age=active_age,
            age_bin=arbitration_bin_for_age(active_age),
        )

    def observe(
        self,
        decision: ExpertWeightDecision,
        outcome: bool,
    ) -> None:
        if not isinstance(outcome, bool):
            raise ValidationError("outcome must be boolean")
        age_bin = decision.age_bin
        numeric_outcome = float(outcome)
        self._base_losses[age_bin] = (
            self.loss_discount * self._base_losses[age_bin]
            + (decision.base_probability - numeric_outcome) ** 2
        )
        self._memory_losses[age_bin] = (
            self.loss_discount * self._memory_losses[age_bin]
            + (decision.memory_probability - numeric_outcome) ** 2
        )


@dataclass(frozen=True, slots=True)
class AdaptiveArbitrationForecast:
    probability: float
    base_probability: float
    fixed_mix_probability: float
    memory_probability: float | None
    memory_weight: float
    active_age: int | None
    age_bin: int | None

    def __post_init__(self) -> None:
        for field, value in (
            ("probability", self.probability),
            ("base_probability", self.base_probability),
            ("fixed_mix_probability", self.fixed_mix_probability),
        ):
            _validate_probability(value, field)
        if self.memory_probability is None:
            if (
                self.memory_weight != 0.0
                or self.active_age is not None
                or self.age_bin is not None
                or self.probability != self.base_probability
                or self.fixed_mix_probability != self.base_probability
            ):
                raise ValidationError("sleeping memory forecast is inconsistent")
        else:
            _validate_probability(
                self.memory_probability,
                "memory_probability",
            )
            if (
                not 0.0 <= self.memory_weight <= 1.0
                or self.active_age is None
                or self.age_bin is None
                or arbitration_bin_for_age(self.active_age) != self.age_bin
            ):
                raise ValidationError("active memory forecast is inconsistent")


class AdaptiveMemoryArbitrator:
    """Causal wrapper over H50-L7 with age-binned expert arbitration."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        learning_rate: float = 8.0,
        loss_discount: float = 0.99,
    ) -> None:
        self.learning_rate = float(learning_rate)
        self.loss_discount = float(loss_discount)
        self._weights = AgeBinnedExpertWeights(
            learning_rate=learning_rate,
            loss_discount=loss_discount,
        )
        self._repository = RegimeRepositoryForecaster(
            detector_window_size=64,
            false_alarm_delta=0.05,
            match_tolerance=0.15,
            retrieval_weight=0.25,
            maximum_working_memory=512,
            retrieval_enabled=True,
            expected_duration=400,
            maximum_hypotheses=64,
        )
        self._active_age: int | None = None
        self._pending: AdaptiveArbitrationForecast | None = None

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return self._repository.archive

    @property
    def prototypes(self) -> tuple[Any, ...]:
        return self._repository.prototypes

    @property
    def transitions(self) -> tuple[Any, ...]:
        return self._repository.transitions

    @property
    def active_age(self) -> int | None:
        return self._active_age

    @property
    def base_losses(self) -> tuple[float, ...]:
        return self._weights.base_losses

    @property
    def memory_losses(self) -> tuple[float, ...]:
        return self._weights.memory_losses

    def predict(self) -> AdaptiveArbitrationForecast:
        if self._pending is not None:
            return self._pending
        repository_forecast = self._repository.predict()
        memory_probability = (
            repository_forecast.active_prototype_probability
        )
        if memory_probability is None:
            forecast = AdaptiveArbitrationForecast(
                probability=repository_forecast.base_probability,
                base_probability=repository_forecast.base_probability,
                fixed_mix_probability=repository_forecast.base_probability,
                memory_probability=None,
                memory_weight=0.0,
                active_age=None,
                age_bin=None,
            )
        else:
            if self._active_age is None:
                raise ValidationError("active repository lacks arbitration age")
            decision = self._weights.predict(
                base_probability=repository_forecast.base_probability,
                memory_probability=memory_probability,
                active_age=self._active_age + 1,
            )
            forecast = AdaptiveArbitrationForecast(
                probability=decision.probability,
                base_probability=decision.base_probability,
                fixed_mix_probability=repository_forecast.probability,
                memory_probability=decision.memory_probability,
                memory_weight=decision.memory_weight,
                active_age=decision.active_age,
                age_bin=decision.age_bin,
            )
        self._pending = forecast
        return forecast

    def observe(self, observation: BinaryStreamObservation) -> None:
        if self._pending is None:
            raise ValidationError("predict must precede observe")
        pending = self._pending
        previous_active_id = self._repository.active_prototype_id
        if pending.memory_probability is not None:
            self._weights.observe(
                ExpertWeightDecision(
                    probability=pending.probability,
                    base_probability=pending.base_probability,
                    memory_probability=pending.memory_probability,
                    memory_weight=pending.memory_weight,
                    active_age=pending.active_age or 0,
                    age_bin=pending.age_bin if pending.age_bin is not None else -1,
                ),
                observation.outcome,
            )
        self._repository.observe(observation)
        current_active_id = self._repository.active_prototype_id
        if current_active_id is None:
            self._active_age = None
        elif current_active_id != previous_active_id:
            self._active_age = 0
        elif self._active_age is None:
            raise ValidationError("unchanged active prototype lacks age")
        else:
            self._active_age += 1
        self._pending = None

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "learning_rate": self.learning_rate,
                "loss_discount": self.loss_discount,
                "age_boundaries": list(ARBITRATION_AGE_BOUNDARIES),
                "base_losses": list(self.base_losses),
                "memory_losses": list(self.memory_losses),
                "active_age": self._active_age,
                "pending": (
                    {
                        "probability": self._pending.probability,
                        "base_probability": self._pending.base_probability,
                        "fixed_mix_probability": (
                            self._pending.fixed_mix_probability
                        ),
                        "memory_probability": self._pending.memory_probability,
                        "memory_weight": self._pending.memory_weight,
                        "active_age": self._pending.active_age,
                        "age_bin": self._pending.age_bin,
                    }
                    if self._pending is not None
                    else None
                ),
                "repository": parse_json(self._repository.to_snapshot()),
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "AdaptiveMemoryArbitrator":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported arbitration snapshot")
        try:
            model = cls(
                learning_rate=parsed["learning_rate"],
                loss_discount=parsed["loss_discount"],
            )
            repository = parsed["repository"]
            pending = parsed["pending"]
        except KeyError as error:
            raise ValidationError(
                f"arbitration snapshot missing field: {error.args[0]}"
            ) from error
        if not isinstance(repository, dict):
            raise ValidationError("arbitration repository snapshot is invalid")
        archive_rows = repository.get("archive")
        if not isinstance(archive_rows, list):
            raise ValidationError("arbitration archive must be a list")
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
            model.predict()
            model.observe(observation)
        if pending is not None:
            if not isinstance(pending, dict):
                raise ValidationError("pending forecast must be an object")
            model.predict()
        if canonical_json(parsed) != model.to_snapshot():
            raise ValidationError(
                "arbitration snapshot does not match replayed archive"
            )
        return model
