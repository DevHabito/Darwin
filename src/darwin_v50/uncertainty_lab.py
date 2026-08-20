"""Partially observable stochastic laboratory for Darwin H50-L3.

This module implements a deliberately small uncertainty problem.  It does not
claim general probabilistic reasoning: it tests whether empirical forecasts
learned from outcomes can support a cost-sensitive request for information.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import random
from typing import Any, Sequence

from .models import ValidationError, canonical_json, parse_json, require_text


DOMAIN_ID = "hidden-signal-v1"
INSPECT = "inspect"
CHOOSE_ALPHA = "choose_alpha"
CHOOSE_BETA = "choose_beta"
CHOICE_ACTIONS = (CHOOSE_ALPHA, CHOOSE_BETA)
INITIAL_CONTEXTS = (
    "clear_alpha",
    "clear_beta",
    "weak_alpha",
    "weak_beta",
)
REVEALED_CONTEXTS = ("revealed_alpha", "revealed_beta")
ALL_CONTEXTS = INITIAL_CONTEXTS + REVEALED_CONTEXTS


@dataclass(frozen=True, slots=True)
class HiddenSignalObservation:
    domain_id: str
    episode_id: str
    context: str
    step_index: int
    terminal: bool
    inspection_used: bool


@dataclass(frozen=True, slots=True)
class HiddenSignalStep:
    observation: HiddenSignalObservation
    action: str
    success: bool | None
    reward: float
    information_cost: float


class HiddenSignalWorld:
    """Binary hidden state with noisy cues and stochastic action outcomes."""

    def __init__(
        self,
        seed: int,
        *,
        clear_probability: float = 0.50,
        clear_reliability: float = 0.95,
        weak_reliability: float = 0.65,
        matched_success_probability: float = 0.90,
        mismatched_success_probability: float = 0.10,
        inspection_cost: float = 0.12,
    ) -> None:
        probabilities = {
            "clear_probability": clear_probability,
            "clear_reliability": clear_reliability,
            "weak_reliability": weak_reliability,
            "matched_success_probability": matched_success_probability,
            "mismatched_success_probability": mismatched_success_probability,
        }
        for name, value in probabilities.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValidationError(f"{name} must be a probability")
        if clear_reliability <= weak_reliability:
            raise ValidationError(
                "clear_reliability must exceed weak_reliability"
            )
        if matched_success_probability <= mismatched_success_probability:
            raise ValidationError(
                "matched success must exceed mismatched success"
            )
        if (
            isinstance(inspection_cost, bool)
            or not isinstance(inspection_cost, (int, float))
            or not math.isfinite(inspection_cost)
            or inspection_cost < 0.0
        ):
            raise ValidationError("inspection_cost must be finite and non-negative")
        self.seed = int(seed)
        self.domain_id = DOMAIN_ID
        self.clear_probability = float(clear_probability)
        self.clear_reliability = float(clear_reliability)
        self.weak_reliability = float(weak_reliability)
        self.matched_success_probability = float(matched_success_probability)
        self.mismatched_success_probability = float(
            mismatched_success_probability
        )
        self.inspection_cost = float(inspection_cost)
        self._rng = random.Random(seed)
        self._episode_counter = 0
        self._episode_id = ""
        self.__hidden_state = ""
        self._context = ""
        self._step_index = 0
        self._terminal = False
        self._inspection_used = False

    def reset(self) -> HiddenSignalObservation:
        self._episode_counter += 1
        self._episode_id = (
            f"{self.domain_id}:{self.seed}:episode:{self._episode_counter:08d}"
        )
        self.__hidden_state = (
            "alpha" if self._rng.random() < 0.50 else "beta"
        )
        clear = self._rng.random() < self.clear_probability
        reliability = self.clear_reliability if clear else self.weak_reliability
        cue_matches = self._rng.random() < reliability
        cue_state = (
            self.__hidden_state
            if cue_matches
            else ("beta" if self.__hidden_state == "alpha" else "alpha")
        )
        strength = "clear" if clear else "weak"
        self._context = f"{strength}_{cue_state}"
        self._step_index = 0
        self._terminal = False
        self._inspection_used = False
        return self.observe()

    def observe(self) -> HiddenSignalObservation:
        if not self._episode_id:
            raise RuntimeError("environment has not been reset")
        return HiddenSignalObservation(
            domain_id=self.domain_id,
            episode_id=self._episode_id,
            context=self._context,
            step_index=self._step_index,
            terminal=self._terminal,
            inspection_used=self._inspection_used,
        )

    def available_actions(self) -> tuple[str, ...]:
        if not self._episode_id:
            raise RuntimeError("environment has not been reset")
        if self._terminal:
            return ()
        if self._inspection_used:
            return CHOICE_ACTIONS
        return (INSPECT,) + CHOICE_ACTIONS

    def step(self, action: str) -> HiddenSignalStep:
        if action not in self.available_actions():
            raise ValidationError("action is not available")
        self._step_index += 1
        if action == INSPECT:
            self._inspection_used = True
            self._context = f"revealed_{self.__hidden_state}"
            return HiddenSignalStep(
                observation=self.observe(),
                action=action,
                success=None,
                reward=-self.inspection_cost,
                information_cost=self.inspection_cost,
            )

        selected = "alpha" if action == CHOOSE_ALPHA else "beta"
        success_probability = (
            self.matched_success_probability
            if selected == self.__hidden_state
            else self.mismatched_success_probability
        )
        success = self._rng.random() < success_probability
        self._terminal = True
        self._context = "success" if success else "failure"
        return HiddenSignalStep(
            observation=self.observe(),
            action=action,
            success=success,
            reward=1.0 if success else 0.0,
            information_cost=0.0,
        )


@dataclass(frozen=True, slots=True)
class OutcomeExperience:
    experience_id: str
    domain_id: str
    episode_id: str
    context: str
    action: str
    success: bool

    def __post_init__(self) -> None:
        require_text(self.experience_id, "experience_id")
        require_text(self.domain_id, "domain_id")
        require_text(self.episode_id, "episode_id")
        require_text(self.context, "context")
        require_text(self.action, "action")
        if self.context not in ALL_CONTEXTS:
            raise ValidationError("unknown outcome context")
        if self.action not in CHOICE_ACTIONS:
            raise ValidationError("outcome action must be a terminal choice")
        if not isinstance(self.success, bool):
            raise ValidationError("success must be boolean")


@dataclass(frozen=True, slots=True)
class OutcomeForecast:
    context: str
    action: str
    success_probability: float
    posterior_standard_deviation: float
    evidence_count: int
    success_count: int
    failure_count: int


class BetaBernoulliOutcomeModel:
    """Empirical Bernoulli forecasts with a fixed symmetric Beta prior."""

    SNAPSHOT_SCHEMA = 1

    def __init__(
        self,
        *,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
    ) -> None:
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
        self.prior_alpha = float(prior_alpha)
        self.prior_beta = float(prior_beta)
        self._counts: dict[tuple[str, str], Counter[bool]] = {}
        self._experiences: dict[str, OutcomeExperience] = {}
        self._domain_id = ""

    @property
    def experience_count(self) -> int:
        return len(self._experiences)

    @property
    def domain_id(self) -> str:
        return self._domain_id

    def evidence_count_for(self, context: str, action: str) -> int:
        return sum(self._counts.get((context, action), {}).values())

    def observe(self, experience: OutcomeExperience) -> bool:
        existing = self._experiences.get(experience.experience_id)
        if existing is not None:
            if existing != experience:
                raise ValidationError(
                    "outcome identifier replayed with different content"
                )
            return False
        if self._domain_id and experience.domain_id != self._domain_id:
            raise ValidationError(
                "one outcome model cannot mix distinct domains"
            )
        self._domain_id = experience.domain_id
        self._experiences[experience.experience_id] = experience
        counts = self._counts.setdefault(
            (experience.context, experience.action),
            Counter(),
        )
        counts[experience.success] += 1
        return True

    def predict(self, context: str, action: str) -> OutcomeForecast:
        if context not in ALL_CONTEXTS:
            raise ValidationError("unknown forecast context")
        if action not in CHOICE_ACTIONS:
            raise ValidationError("forecast action must be a terminal choice")
        counts = self._counts.get((context, action), Counter())
        successes = counts[True]
        failures = counts[False]
        alpha = self.prior_alpha + successes
        beta = self.prior_beta + failures
        total = alpha + beta
        probability = alpha / total
        variance = (alpha * beta) / (total * total * (total + 1.0))
        return OutcomeForecast(
            context=context,
            action=action,
            success_probability=probability,
            posterior_standard_deviation=math.sqrt(variance),
            evidence_count=successes + failures,
            success_count=successes,
            failure_count=failures,
        )

    def best_choice(self, context: str) -> OutcomeForecast:
        forecasts = [self.predict(context, action) for action in CHOICE_ACTIONS]
        return max(
            forecasts,
            key=lambda forecast: (
                forecast.success_probability,
                -CHOICE_ACTIONS.index(forecast.action),
            ),
        )

    def to_snapshot(self) -> str:
        experiences = [
            {
                "experience_id": experience.experience_id,
                "domain_id": experience.domain_id,
                "episode_id": experience.episode_id,
                "context": experience.context,
                "action": experience.action,
                "success": experience.success,
            }
            for experience in sorted(
                self._experiences.values(),
                key=lambda item: item.experience_id,
            )
        ]
        return canonical_json(
            {
                "schema": self.SNAPSHOT_SCHEMA,
                "prior_alpha": self.prior_alpha,
                "prior_beta": self.prior_beta,
                "experiences": experiences,
            }
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "BetaBernoulliOutcomeModel":
        parsed = parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("schema") != cls.SNAPSHOT_SCHEMA:
            raise ValidationError("unsupported outcome model snapshot")
        experiences = parsed.get("experiences")
        if not isinstance(experiences, list):
            raise ValidationError("invalid outcome model snapshot")
        try:
            model = cls(
                prior_alpha=parsed["prior_alpha"],
                prior_beta=parsed["prior_beta"],
            )
        except KeyError as error:
            raise ValidationError(
                f"outcome snapshot missing field: {error.args[0]}"
            ) from error
        for row in experiences:
            if not isinstance(row, dict):
                raise ValidationError("invalid outcome experience row")
            try:
                experience = OutcomeExperience(
                    experience_id=row["experience_id"],
                    domain_id=row["domain_id"],
                    episode_id=row["episode_id"],
                    context=row["context"],
                    action=row["action"],
                    success=row["success"],
                )
            except KeyError as error:
                raise ValidationError(
                    f"outcome experience missing field: {error.args[0]}"
                ) from error
            model.observe(experience)
        return model


@dataclass(frozen=True, slots=True)
class InformationDecision:
    action: str
    requested_information: bool
    forecast: OutcomeForecast
    reason: str


class SelectiveInformationPolicy:
    """Request a reveal only when the current forecast is not actionable."""

    def __init__(
        self,
        model: BetaBernoulliOutcomeModel,
        *,
        actionability_threshold: float = 0.75,
        minimum_evidence: int = 50,
    ) -> None:
        if not 0.5 < actionability_threshold < 1.0:
            raise ValidationError(
                "actionability_threshold must be strictly between 0.5 and 1"
            )
        if (
            isinstance(minimum_evidence, bool)
            or not isinstance(minimum_evidence, int)
            or minimum_evidence < 1
        ):
            raise ValidationError("minimum_evidence must be positive")
        self.model = model
        self.actionability_threshold = actionability_threshold
        self.minimum_evidence = minimum_evidence

    def decide(self, observation: HiddenSignalObservation) -> InformationDecision:
        if observation.terminal:
            raise RuntimeError("cannot decide after terminal outcome")
        forecast = self.model.best_choice(observation.context)
        if observation.context in REVEALED_CONTEXTS:
            return InformationDecision(
                action=forecast.action,
                requested_information=False,
                forecast=forecast,
                reason="revealed_context",
            )
        insufficient_evidence = forecast.evidence_count < self.minimum_evidence
        insufficient_probability = (
            forecast.success_probability < self.actionability_threshold
        )
        if not observation.inspection_used and (
            insufficient_evidence or insufficient_probability
        ):
            reason = (
                "insufficient_evidence"
                if insufficient_evidence
                else "forecast_below_actionability_threshold"
            )
            return InformationDecision(
                action=INSPECT,
                requested_information=True,
                forecast=forecast,
                reason=reason,
            )
        return InformationDecision(
            action=forecast.action,
            requested_information=False,
            forecast=forecast,
            reason="forecast_actionable",
        )


def outcome_experience(
    *,
    observation: HiddenSignalObservation,
    action: str,
    success: bool,
) -> OutcomeExperience:
    return OutcomeExperience(
        experience_id=(
            f"{observation.episode_id}:outcome:{observation.step_index + 1}"
        ),
        domain_id=observation.domain_id,
        episode_id=observation.episode_id,
        context=observation.context,
        action=action,
        success=success,
    )


def action_label(action: str) -> str:
    if action == CHOOSE_ALPHA:
        return "alpha"
    if action == CHOOSE_BETA:
        return "beta"
    raise ValidationError("action is not a choice")


def validate_contexts(contexts: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(require_text(context, "context") for context in contexts)
    if any(context not in ALL_CONTEXTS for context in normalized):
        raise ValidationError("unknown context")
    return normalized
