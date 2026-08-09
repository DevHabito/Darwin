"""Authenticated evidence envelopes for external Darwin v50 adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
from typing import Any, Mapping, Protocol

from .models import (
    Clock,
    IdFactory,
    JSONValue,
    ValidationError,
    canonical_json,
    new_id,
    require_text,
    utc_now,
)


HMAC_SCHEME = "hmac-sha256-v1"


def compute_action_digest(
    action_name: str,
    parameters: Mapping[str, JSONValue],
) -> str:
    action_name = require_text(action_name, "action_name")
    encoded = canonical_json(
        {
            "action_name": action_name,
            "parameters": dict(parameters),
        }
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ActionRequest:
    session_id: str
    goal_id: str
    action_id: str
    action_name: str
    parameters: Mapping[str, JSONValue]
    action_digest: str

    def __post_init__(self) -> None:
        require_text(self.session_id, "session_id")
        require_text(self.goal_id, "goal_id")
        require_text(self.action_id, "action_id")
        require_text(self.action_name, "action_name")
        expected = compute_action_digest(self.action_name, self.parameters)
        if not hmac.compare_digest(expected, self.action_digest):
            raise ValidationError("action request digest does not match its payload")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "action_id": self.action_id,
            "action_name": self.action_name,
            "parameters": dict(self.parameters),
            "action_digest": self.action_digest,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActionRequest":
        try:
            parameters = value["parameters"]
            if not isinstance(parameters, dict):
                raise ValidationError("action parameters must be an object")
            return cls(
                session_id=str(value["session_id"]),
                goal_id=str(value["goal_id"]),
                action_id=str(value["action_id"]),
                action_name=str(value["action_name"]),
                parameters=parameters,
                action_digest=str(value["action_digest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("invalid action request payload") from exc


@dataclass(frozen=True, slots=True)
class ObservationEnvelope:
    source: str
    session_id: str
    goal_id: str
    action_id: str
    action_digest: str
    nonce: str
    occurred_at: datetime
    metrics: Mapping[str, JSONValue]
    scheme: str
    signature: str

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_text(self.session_id, "session_id")
        require_text(self.goal_id, "goal_id")
        require_text(self.action_id, "action_id")
        require_text(self.action_digest, "action_digest")
        require_text(self.nonce, "nonce")
        if self.occurred_at.tzinfo is None:
            raise ValidationError("observation occurred_at must be timezone-aware")
        canonical_json(dict(self.metrics))
        if self.scheme != HMAC_SCHEME:
            raise ValidationError(f"unsupported evidence scheme: {self.scheme}")
        if len(self.signature) != 64:
            raise ValidationError("HMAC signature must be 64 hexadecimal characters")
        try:
            bytes.fromhex(self.signature)
        except ValueError as exc:
            raise ValidationError("HMAC signature is not hexadecimal") from exc

    def signing_payload(self) -> dict[str, JSONValue]:
        return {
            "source": self.source,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "action_id": self.action_id,
            "action_digest": self.action_digest,
            "nonce": self.nonce,
            "occurred_at": self.occurred_at.isoformat(),
            "metrics": dict(self.metrics),
            "scheme": self.scheme,
        }

    def signing_bytes(self) -> bytes:
        return canonical_json(self.signing_payload()).encode("utf-8")

    def to_dict(self) -> dict[str, JSONValue]:
        return {**self.signing_payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ObservationEnvelope":
        try:
            metrics = value["metrics"]
            if not isinstance(metrics, dict):
                raise ValidationError("observation metrics must be an object")
            return cls(
                source=str(value["source"]),
                session_id=str(value["session_id"]),
                goal_id=str(value["goal_id"]),
                action_id=str(value["action_id"]),
                action_digest=str(value["action_digest"]),
                nonce=str(value["nonce"]),
                occurred_at=datetime.fromisoformat(str(value["occurred_at"])),
                metrics=metrics,
                scheme=str(value["scheme"]),
                signature=str(value["signature"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("invalid observation envelope payload") from exc


@dataclass(frozen=True, slots=True)
class VerificationResult:
    valid: bool
    reason: str


class ObservationVerifier(Protocol):
    source: str

    def verify(self, envelope: ObservationEnvelope) -> VerificationResult:
        """Verify authenticity and freshness without changing state."""


def _validated_secret(secret: bytes) -> bytes:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValidationError("evidence secret must contain at least 32 bytes")
    return secret


class HMACObservationSigner:
    """Sign adapter observations.

    A production deployment must keep this signer outside the Darwin process.
    Keeping signer and verifier together only authenticates an adapter boundary
    in tests; it is not process isolation.
    """

    def __init__(
        self,
        *,
        source: str,
        secret: bytes,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ) -> None:
        self.source = require_text(source, "source")
        self._secret = _validated_secret(secret)
        self._clock = clock
        self._id_factory = id_factory

    def attest(
        self,
        request: ActionRequest,
        metrics: Mapping[str, JSONValue],
    ) -> ObservationEnvelope:
        unsigned = {
            "source": self.source,
            "session_id": request.session_id,
            "goal_id": request.goal_id,
            "action_id": request.action_id,
            "action_digest": request.action_digest,
            "nonce": f"nonce:{self._id_factory()}",
            "occurred_at": self._clock(),
            "metrics": dict(metrics),
            "scheme": HMAC_SCHEME,
        }
        provisional = ObservationEnvelope(signature="0" * 64, **unsigned)
        signature = hmac.new(
            self._secret,
            provisional.signing_bytes(),
            hashlib.sha256,
        ).hexdigest()
        return ObservationEnvelope(signature=signature, **unsigned)


class HMACObservationVerifier:
    def __init__(
        self,
        *,
        source: str,
        secret: bytes,
        clock: Clock = utc_now,
        max_age: timedelta = timedelta(minutes=5),
        future_tolerance: timedelta = timedelta(seconds=30),
    ) -> None:
        self.source = require_text(source, "source")
        self._secret = _validated_secret(secret)
        self._clock = clock
        if max_age <= timedelta(0):
            raise ValidationError("max_age must be positive")
        if future_tolerance < timedelta(0):
            raise ValidationError("future_tolerance cannot be negative")
        self._max_age = max_age
        self._future_tolerance = future_tolerance

    def verify(self, envelope: ObservationEnvelope) -> VerificationResult:
        if envelope.source != self.source:
            return VerificationResult(False, "verifier_source_mismatch")
        expected = hmac.new(
            self._secret,
            envelope.signing_bytes(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, envelope.signature):
            return VerificationResult(False, "signature_invalid")

        age = self._clock() - envelope.occurred_at
        if age > self._max_age:
            return VerificationResult(False, "attestation_stale")
        if age < -self._future_tolerance:
            return VerificationResult(False, "attestation_from_future")
        return VerificationResult(True, "signature_valid")
