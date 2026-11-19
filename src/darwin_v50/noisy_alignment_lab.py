"""An uncertainty-preserving, action-correlated E063 observation prototype.

This is a separate engineering study. It is not wired to the Darwin v50
kernel, has no execution authority, and knows its transition and sensor model.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

MODES = (0, 1, 2)
SCHEMA = "darwin-e063-noisy-observation-v1"
UNIFORM = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)


def _finite_probability(value: object, *, low: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite probability")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= 1.0:
        raise ValueError(f"{name} outside supported probability range")
    return number


def _normalize(values: tuple[float, float, float]) -> tuple[float, float, float]:
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("invalid probability mass")
    total = sum(values)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("observation impossible under declared model")
    return tuple(value / total for value in values)  # type: ignore[return-value]


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class NoisyCue:
    sequence: int
    action_id: str
    cue: int

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("action_id must be a nonempty string")
        if type(self.cue) is not int or self.cue not in MODES:
            raise ValueError("cue must be an integer in {0, 1, 2}")

    def to_dict(self) -> dict[str, object]:
        return {"sequence": self.sequence, "action_id": self.action_id, "cue": self.cue}


class NoisyAlignmentBelief:
    """Known-likelihood Bayesian filter; never invents a definitive mode.

    The caller must provide dispatch IDs. This matches IDs within this process,
    but does not verify dispatches from the authenticated v50 causal kernel.
    """

    def __init__(self, *, hazard: float, sensor_correct: float) -> None:
        self.hazard = _finite_probability(hazard, low=0.0, name="hazard")
        self.sensor_correct = _finite_probability(
            sensor_correct, low=1.0 / 3.0, name="sensor_correct"
        )
        self._posterior: tuple[float, float, float] = UNIFORM
        self._archive: list[NoisyCue] = []
        self._pending_action: str | None = None
        self._used_actions: set[str] = set()

    @property
    def posterior(self) -> tuple[float, float, float]:
        return self._posterior

    @property
    def archive(self) -> tuple[NoisyCue, ...]:
        return tuple(self._archive)

    @property
    def pending_action(self) -> str | None:
        return self._pending_action

    def prediction(self) -> tuple[float, float, float]:
        if not self._archive:
            return UNIFORM
        h = self.hazard
        return _normalize(tuple(
            (1.0 - h) * self._posterior[mode]
            + (h / 2.0) * (1.0 - self._posterior[mode])
            for mode in MODES
        ))

    def register_dispatch(self, action_id: str) -> None:
        if not isinstance(action_id, str) or not action_id.strip():
            raise ValueError("action_id must be a nonempty string")
        if self._pending_action is not None:
            raise ValueError("an action is already pending")
        if action_id in self._used_actions:
            raise ValueError("action identifiers cannot be reused")
        self._pending_action = action_id

    def observe(self, observation: NoisyCue) -> tuple[float, float, float]:
        if not isinstance(observation, NoisyCue):
            raise ValueError("observation type is invalid")
        if self._pending_action is None or observation.action_id != self._pending_action:
            raise ValueError("observation does not match a pending dispatch")
        if observation.sequence != len(self._archive) + 1:
            raise ValueError("observation sequence must be contiguous")

        prior = self.prediction()
        mismatch_likelihood = (1.0 - self.sensor_correct) / 2.0
        posterior = _normalize(tuple(
            prior[mode] * (
                self.sensor_correct if mode == observation.cue else mismatch_likelihood
            )
            for mode in MODES
        ))

        # Commit accepted evidence only after every validation and Bayes step.
        self._posterior = posterior
        self._archive.append(observation)
        self._used_actions.add(observation.action_id)
        self._pending_action = None
        return posterior

    def snapshot(self) -> str:
        body = {
            "schema": SCHEMA,
            "hazard": self.hazard,
            "sensor_correct": self.sensor_correct,
            "archive": [item.to_dict() for item in self._archive],
            "pending_action": self._pending_action,
            "posterior": list(self._posterior),
        }
        return json.dumps(
            {"body": body, "sha256": _digest(body)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @classmethod
    def from_snapshot(cls, raw: str) -> "NoisyAlignmentBelief":
        if not isinstance(raw, str):
            raise ValueError("snapshot must be JSON text")
        try:
            document = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
            if type(document) is not dict or set(document) != {"body", "sha256"}:
                raise ValueError("invalid snapshot envelope")
            body = document["body"]
            if type(body) is not dict or set(body) != {
                "schema", "hazard", "sensor_correct", "archive", "pending_action", "posterior"
            }:
                raise ValueError("invalid snapshot body")
            if body["schema"] != SCHEMA or type(document["sha256"]) is not str:
                raise ValueError("snapshot schema mismatch")
            if _digest(body) != document["sha256"]:
                raise ValueError("snapshot digest mismatch")
            if type(body["archive"]) is not list or type(body["posterior"]) is not list:
                raise ValueError("invalid snapshot arrays")
            if len(body["posterior"]) != 3 or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in body["posterior"]
            ):
                raise ValueError("invalid recorded posterior")
            result = cls(hazard=body["hazard"], sensor_correct=body["sensor_correct"])
            for record in body["archive"]:
                if type(record) is not dict or set(record) != {"sequence", "action_id", "cue"}:
                    raise ValueError("invalid archived observation")
                cue = NoisyCue(**record)
                result.register_dispatch(cue.action_id)
                result.observe(cue)
            pending = body["pending_action"]
            if pending is not None:
                result.register_dispatch(pending)
            if any(abs(actual - recorded) > 1e-12 for actual, recorded in zip(
                result.posterior, body["posterior"]
            )):
                raise ValueError("replayed posterior differs from recorded posterior")
            if result.pending_action != pending:
                raise ValueError("pending action replay mismatch")
            return result
        except (TypeError, KeyError, ValueError, json.JSONDecodeError, OverflowError) as error:
            raise ValueError("snapshot cannot be safely replayed") from error
