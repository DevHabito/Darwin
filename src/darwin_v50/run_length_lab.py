"""Pruned Bayesian run-length memory for Darwin H50-L6.

This module implements a Beta-Bernoulli online changepoint approximation.  It
keeps only the highest-mass run-length hypotheses, so it must not be described
as exact Bayesian Online Changepoint Detection.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from .models import ValidationError, canonical_json, parse_json
from .temporal_lab import BinaryStreamObservation


SCHEDULE_XOR_MASK = 0xD4A21
TOTAL_VARIABLE_OBSERVATIONS = 3000


@dataclass(frozen=True, slots=True)
class VariableRegimeSchedule:
    seed: int
    first_duration: int
    opposite_duration: int
    recurrence_duration: int
    gradual_duration: int
    first_probability: float
    opposite_probability: float

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValidationError("schedule seed must be an integer")
        for name, value in (
            ("first_duration", self.first_duration),
            ("opposite_duration", self.opposite_duration),
            ("recurrence_duration", self.recurrence_duration),
            ("gradual_duration", self.gradual_duration),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 450 <= value <= 600
            ):
                raise ValidationError(
                    f"{name} must be an integer within [450, 600]"
                )
        for name, value in (
            ("first_probability", self.first_probability),
            ("opposite_probability", self.opposite_probability),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 < value < 1.0
            ):
                raise ValidationError(f"{name} must be a probability")
        if abs(self.first_probability - self.opposite_probability) < 0.45:
            raise ValidationError("registered regimes must be well separated")
        if self.gradual_end_index >= TOTAL_VARIABLE_OBSERVATIONS:
            raise ValidationError("schedule leaves no final stable regime")

    @property
    def first_abrupt_index(self) -> int:
        return self.first_duration + 1

    @property
    def recurrence_index(self) -> int:
        return self.first_duration + self.opposite_duration + 1

    @property
    def gradual_start_index(self) -> int:
        return (
            self.first_duration
            + self.opposite_duration
            + self.recurrence_duration
            + 1
        )

    @property
    def gradual_end_index(self) -> int:
        return self.gradual_start_index + self.gradual_duration - 1

    @classmethod
    def from_seed(cls, seed: int) -> "VariableRegimeSchedule":
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("schedule seed must be an integer")
        rng = random.Random(seed ^ SCHEDULE_XOR_MASK)
        high = rng.choice((0.75, 0.80, 0.85, 0.90))
        low = rng.choice((0.10, 0.15, 0.20, 0.25))
        starts_high = bool(rng.randrange(2))
        return cls(
            seed=seed,
            first_duration=rng.randint(450, 600),
            opposite_duration=rng.randint(450, 600),
            recurrence_duration=rng.randint(450, 600),
            gradual_duration=rng.randint(450, 600),
            first_probability=high if starts_high else low,
            opposite_probability=low if starts_high else high,
        )

    def probability_at(self, index: int) -> float:
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= TOTAL_VARIABLE_OBSERVATIONS
        ):
            raise ValidationError("stream index is outside the registered range")
        if index < self.first_abrupt_index:
            return self.first_probability
        if index < self.recurrence_index:
            return self.opposite_probability
        if index < self.gradual_start_index:
            return self.first_probability
        if index <= self.gradual_end_index:
            progress = (index - self.gradual_start_index) / (
                self.gradual_duration - 1
            )
            return self.first_probability + progress * (
                self.opposite_probability - self.first_probability
            )
        return self.opposite_probability


class VariableRegimeBernoulliStream:
    """Outcome stream whose hidden schedule varies by seed."""

    def __init__(self, seed: int) -> None:
        self.schedule = VariableRegimeSchedule.from_seed(seed)
        self._rng = random.Random(seed)
        self._next_index = 1

    def next_observation(self) -> BinaryStreamObservation:
        if self._next_index > TOTAL_VARIABLE_OBSERVATIONS:
            raise StopIteration("stream is exhausted")
        index = self._next_index
        observation = BinaryStreamObservation(
            index=index,
            outcome=(
                self._rng.random() < self.schedule.probability_at(index)
            ),
        )
        self._next_index += 1
        return observation


@dataclass(frozen=True, slots=True)
class RunLengthHypothesis:
    run_length: int
    alpha: float
    beta: float
    mass: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.run_length, bool)
            or not isinstance(self.run_length, int)
            or self.run_length < 0
        ):
            raise ValidationError("run_length must be a non-negative integer")
        for name, value in (("alpha", self.alpha), ("beta", self.beta)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0.0
            ):
                raise ValidationError(f"{name} must be finite and positive")
        if (
            isinstance(self.mass, bool)
            or not isinstance(self.mass, (int, float))
            or not math.isfinite(self.mass)
            or self.mass <= 0.0
        ):
            raise ValidationError(
                "hypothesis mass must be finite and positive"
            )

    @property
    def probability(self) -> float:
        return self.alpha / (self.alpha + self.beta)


@dataclass(frozen=True, slots=True)
class RunLengthForecast:
    probability: float
    expected_run_length: float
    most_likely_run_length: int
    hypothesis_count: int
    last_change_probability: float

    def __post_init__(self) -> None:
        for name, value in (
            ("probability", self.probability),
            ("last_change_probability", self.last_change_probability),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError(f"{name} must be within [0, 1]")
        if (
            isinstance(self.expected_run_length, bool)
            or not isinstance(self.expected_run_length, (int, float))
            or not math.isfinite(self.expected_run_length)
            or self.expected_run_length < 0.0
        ):
            raise ValidationError(
                "expected_run_length must be finite and non-negative"
            )
        if (
            isinstance(self.most_likely_run_length, bool)
            or not isinstance(self.most_likely_run_length, int)
            or self.most_likely_run_length < 0
        ):
            raise ValidationError(
                "most_likely_run_length must be non-negative"
            )
        if (
            isinstance(self.hypothesis_count, bool)
            or not isinstance(self.hypothesis_count, int)
            or self.hypothesis_count < 1
        ):
            raise ValidationError("hypothesis_count must be positive")


class PrunedBayesianRunLengthForecaster:
    """Beta-Bernoulli run-length posterior with deterministic top-k pruning."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        expected_duration: int = 400,
        maximum_hypotheses: int = 32,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
    ) -> None:
        if (
            isinstance(expected_duration, bool)
            or not isinstance(expected_duration, int)
            or expected_duration < 2
        ):
            raise ValidationError(
                "expected_duration must be an integer of at least two"
            )
        if (
            isinstance(maximum_hypotheses, bool)
            or not isinstance(maximum_hypotheses, int)
            or maximum_hypotheses < 2
        ):
            raise ValidationError(
                "maximum_hypotheses must be an integer of at least two"
            )
        for name, value in (
            ("prior_alpha", prior_alpha),
            ("prior_beta", prior_beta),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0.0
            ):
                raise ValidationError(f"{name} must be finite and positive")
        self.expected_duration = expected_duration
        self.maximum_hypotheses = maximum_hypotheses
        self.prior_alpha = float(prior_alpha)
        self.prior_beta = float(prior_beta)
        self._hazard = 1.0 / expected_duration
        self._run_lengths = [0]
        self._alphas = [self.prior_alpha]
        self._betas = [self.prior_beta]
        self._masses = [1.0]
        self._last_change_probability = 0.0
        self._archive: list[BinaryStreamObservation] = []

    @property
    def hypotheses(self) -> tuple[RunLengthHypothesis, ...]:
        return tuple(
            RunLengthHypothesis(run_length, alpha, beta, mass)
            for run_length, alpha, beta, mass in zip(
                self._run_lengths,
                self._alphas,
                self._betas,
                self._masses,
                strict=True,
            )
        )

    @property
    def hypothesis_count(self) -> int:
        return len(self._run_lengths)

    @property
    def archive(self) -> tuple[BinaryStreamObservation, ...]:
        return tuple(self._archive)

    @property
    def last_change_probability(self) -> float:
        return self._last_change_probability

    def predict_probability(self) -> float:
        return sum(
            mass * alpha / (alpha + beta)
            for alpha, beta, mass in zip(
                self._alphas,
                self._betas,
                self._masses,
                strict=True,
            )
        )

    def predict(self) -> RunLengthForecast:
        probability = self.predict_probability()
        expected_run_length = sum(
            mass * run_length
            for run_length, mass in zip(
                self._run_lengths,
                self._masses,
                strict=True,
            )
        )
        most_likely_index = max(
            range(len(self._masses)),
            key=lambda index: (
                self._masses[index],
                -self._run_lengths[index],
            ),
        )
        return RunLengthForecast(
            probability=probability,
            expected_run_length=expected_run_length,
            most_likely_run_length=self._run_lengths[most_likely_index],
            hypothesis_count=len(self._run_lengths),
            last_change_probability=self._last_change_probability,
        )

    def _update_posterior(self, outcome: bool) -> None:
        prior_probability = self.prior_alpha / (
            self.prior_alpha + self.prior_beta
        )
        prior_likelihood = (
            prior_probability if outcome else 1.0 - prior_probability
        )
        candidate_run_lengths = [0]
        candidate_alphas = [self.prior_alpha + int(outcome)]
        candidate_betas = [self.prior_beta + int(not outcome)]
        candidate_masses = [self._hazard * prior_likelihood]
        for run_length, alpha, beta, mass in zip(
            self._run_lengths,
            self._alphas,
            self._betas,
            self._masses,
            strict=True,
        ):
            probability = alpha / (alpha + beta)
            likelihood = (
                probability
                if outcome
                else 1.0 - probability
            )
            candidate_run_lengths.append(run_length + 1)
            candidate_alphas.append(alpha + int(outcome))
            candidate_betas.append(beta + int(not outcome))
            candidate_masses.append(
                (1.0 - self._hazard) * mass * likelihood
            )
        total_mass = sum(candidate_masses)
        normalized_masses = [
            mass / total_mass for mass in candidate_masses
        ]
        retained_indices = sorted(
            range(len(candidate_run_lengths)),
            key=lambda index: (
                -normalized_masses[index],
                candidate_run_lengths[index],
            )
        )[: self.maximum_hypotheses]
        retained_indices.sort(
            key=candidate_run_lengths.__getitem__
        )
        retained_total = sum(
            normalized_masses[index] for index in retained_indices
        )
        self._run_lengths = [
            candidate_run_lengths[index] for index in retained_indices
        ]
        self._alphas = [
            candidate_alphas[index] for index in retained_indices
        ]
        self._betas = [
            candidate_betas[index] for index in retained_indices
        ]
        self._masses = [
            normalized_masses[index] / retained_total
            for index in retained_indices
        ]
        self._last_change_probability = next(
            (
                mass
                for run_length, mass in zip(
                    self._run_lengths,
                    self._masses,
                    strict=True,
                )
                if run_length == 0
            ),
            0.0,
        )

    def observe(self, observation: BinaryStreamObservation) -> None:
        expected = len(self._archive) + 1
        if observation.index != expected:
            raise ValidationError(
                f"expected observation index {expected}, got {observation.index}"
            )
        self._update_posterior(observation.outcome)
        self._archive.append(observation)

    def to_snapshot(self) -> str:
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "expected_duration": self.expected_duration,
                "maximum_hypotheses": self.maximum_hypotheses,
                "prior_alpha": self.prior_alpha,
                "prior_beta": self.prior_beta,
                "last_change_probability": self._last_change_probability,
                "hypotheses": [
                    {
                        "run_length": item.run_length,
                        "alpha": item.alpha,
                        "beta": item.beta,
                        "mass": item.mass,
                    }
                    for item in self.hypotheses
                ],
                "archive": [
                    {"index": item.index, "outcome": item.outcome}
                    for item in self._archive
                ],
            }
        )

    @classmethod
    def from_snapshot(
        cls,
        raw: str,
    ) -> "PrunedBayesianRunLengthForecaster":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported run-length snapshot")
        try:
            model = cls(
                expected_duration=parsed["expected_duration"],
                maximum_hypotheses=parsed["maximum_hypotheses"],
                prior_alpha=parsed["prior_alpha"],
                prior_beta=parsed["prior_beta"],
            )
            archive_rows = parsed["archive"]
            hypothesis_rows = parsed["hypotheses"]
            stored_change_probability = parsed["last_change_probability"]
        except KeyError as error:
            raise ValidationError(
                f"run-length snapshot missing field: {error.args[0]}"
            ) from error
        if not isinstance(archive_rows, list) or not isinstance(
            hypothesis_rows, list
        ):
            raise ValidationError("invalid run-length snapshot")
        stored_hypotheses: list[RunLengthHypothesis] = []
        for row in hypothesis_rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid run-length hypothesis")
            try:
                item = RunLengthHypothesis(
                    run_length=row["run_length"],
                    alpha=row["alpha"],
                    beta=row["beta"],
                    mass=row["mass"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"run-length hypothesis missing field: {error.args[0]}"
                ) from error
            stored_hypotheses.append(item)
        if not stored_hypotheses:
            raise ValidationError("snapshot requires run-length hypotheses")
        if len(stored_hypotheses) > model.maximum_hypotheses:
            raise ValidationError("snapshot exceeds hypothesis limit")
        if any(
            left.run_length >= right.run_length
            for left, right in zip(
                stored_hypotheses[:-1],
                stored_hypotheses[1:],
                strict=True,
            )
        ):
            raise ValidationError(
                "snapshot hypotheses must be strictly ordered"
            )
        if not math.isclose(
            sum(item.mass for item in stored_hypotheses),
            1.0,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValidationError("snapshot hypothesis masses must sum to one")
        if (
            isinstance(stored_change_probability, bool)
            or not isinstance(stored_change_probability, (int, float))
            or not math.isfinite(stored_change_probability)
            or not 0.0 <= stored_change_probability <= 1.0
        ):
            raise ValidationError(
                "snapshot change probability must be within [0, 1]"
            )
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
        if tuple(stored_hypotheses) != model.hypotheses:
            raise ValidationError(
                "snapshot hypotheses do not match replayed archive"
            )
        if stored_change_probability != model.last_change_probability:
            raise ValidationError(
                "snapshot change probability does not match replay"
            )
        return model
