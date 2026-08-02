"""Explicit, signed consent records for Darwin v50 capabilities.

The signature makes a decision tamper-evident; it does not prove who was
physically present.  The recorded channel states how the decision was obtained
so test automation cannot be confused with an interactive human confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import sys
from typing import Any, Protocol, TextIO

from .evidence import ActionRequest, VerificationResult
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


HMAC_CONSENT_SCHEME = "hmac-consent-v1"
ED25519_CONSENT_SCHEME = "ed25519-consent-v1"
CONSENT_SCHEME = HMAC_CONSENT_SCHEME
SUPPORTED_CONSENT_SCHEMES = frozenset(
    {HMAC_CONSENT_SCHEME, ED25519_CONSENT_SCHEME}
)
INTERACTIVE_TTY_CHANNEL = "interactive_tty"
TEST_HARNESS_CHANNEL = "test_harness"


class ConsentError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ConsentRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _require_sha256(value: str, field: str) -> str:
    require_text(value, field)
    if len(value) != 64:
        raise ValidationError(f"{field} must be a SHA-256 hexadecimal digest")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValidationError(f"{field} is not hexadecimal") from exc
    return value


def _validated_secret(secret: bytes) -> bytes:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValidationError("consent secret must contain at least 32 bytes")
    return secret


@dataclass(frozen=True, slots=True)
class ConsentRequest:
    consent_id: str
    authority_issuer: str
    authority_scheme: str
    authority_fingerprint: str
    adapter_source: str
    session_id: str
    goal_id: str
    action_id: str
    action_name: str
    parameters: dict[str, JSONValue]
    action_digest: str
    resource_scope: str
    risk: ConsentRisk
    created_at: datetime
    expires_at: datetime
    challenge: str

    def __post_init__(self) -> None:
        for field_name in (
            "consent_id",
            "authority_issuer",
            "authority_fingerprint",
            "adapter_source",
            "session_id",
            "goal_id",
            "action_id",
            "action_name",
            "resource_scope",
        ):
            require_text(str(getattr(self, field_name)), field_name)
        if self.authority_scheme not in SUPPORTED_CONSENT_SCHEMES:
            raise ValidationError(
                f"unsupported consent authority scheme: {self.authority_scheme}"
            )
        _require_sha256(self.action_digest, "action_digest")
        canonical_json(self.parameters)
        if not isinstance(self.risk, ConsentRisk):
            raise ValidationError("risk must be a ConsentRisk value")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValidationError("consent timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValidationError("consent expiration must follow creation")
        if (
            len(self.challenge) != 8
            or not self.challenge.isascii()
            or not self.challenge.isalnum()
            or self.challenge != self.challenge.upper()
        ):
            raise ValidationError(
                "consent challenge must contain 8 uppercase ASCII letters or digits"
            )

    def signing_payload(self) -> dict[str, JSONValue]:
        return {
            "consent_id": self.consent_id,
            "authority_issuer": self.authority_issuer,
            "authority_scheme": self.authority_scheme,
            "authority_fingerprint": self.authority_fingerprint,
            "adapter_source": self.adapter_source,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "action_id": self.action_id,
            "action_name": self.action_name,
            "parameters": self.parameters,
            "action_digest": self.action_digest,
            "resource_scope": self.resource_scope,
            "risk": self.risk.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "challenge": self.challenge,
        }

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(
            canonical_json(self.signing_payload()).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, JSONValue]:
        return self.signing_payload()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConsentRequest":
        try:
            parameters = value["parameters"]
            if not isinstance(parameters, dict):
                raise TypeError("parameters must be an object")
            return cls(
                consent_id=str(value["consent_id"]),
                authority_issuer=str(value["authority_issuer"]),
                authority_scheme=str(value["authority_scheme"]),
                authority_fingerprint=str(value["authority_fingerprint"]),
                adapter_source=str(value["adapter_source"]),
                session_id=str(value["session_id"]),
                goal_id=str(value["goal_id"]),
                action_id=str(value["action_id"]),
                action_name=str(value["action_name"]),
                parameters=parameters,
                action_digest=str(value["action_digest"]),
                resource_scope=str(value["resource_scope"]),
                risk=ConsentRisk(str(value["risk"])),
                created_at=datetime.fromisoformat(str(value["created_at"])),
                expires_at=datetime.fromisoformat(str(value["expires_at"])),
                challenge=str(value["challenge"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("invalid consent request payload") from exc

    def correlates(self, request: ActionRequest, *, resource_scope: str) -> bool:
        return (
            self.session_id == request.session_id
            and self.goal_id == request.goal_id
            and self.action_id == request.action_id
            and self.action_name == request.action_name
            and self.parameters == request.parameters
            and self.action_digest == request.action_digest
            and self.resource_scope == resource_scope
        )


@dataclass(frozen=True, slots=True)
class ConsentReceipt:
    receipt_id: str
    issuer: str
    consent_id: str
    request_digest: str
    session_id: str
    goal_id: str
    action_id: str
    action_digest: str
    resource_scope: str
    approved: bool
    channel: str
    decision_reason: str
    decided_at: datetime
    consent_expires_at: datetime
    scheme: str
    signature: str

    def __post_init__(self) -> None:
        for field_name in (
            "receipt_id",
            "issuer",
            "consent_id",
            "session_id",
            "goal_id",
            "action_id",
            "resource_scope",
            "channel",
            "decision_reason",
        ):
            require_text(str(getattr(self, field_name)), field_name)
        _require_sha256(self.request_digest, "request_digest")
        _require_sha256(self.action_digest, "action_digest")
        if not isinstance(self.approved, bool):
            raise ValidationError("approved must be boolean")
        if self.decided_at.tzinfo is None or self.consent_expires_at.tzinfo is None:
            raise ValidationError("consent receipt timestamps must be timezone-aware")
        if self.scheme not in SUPPORTED_CONSENT_SCHEMES:
            raise ValidationError(f"unsupported consent scheme: {self.scheme}")
        expected_signature_length = (
            64 if self.scheme == HMAC_CONSENT_SCHEME else 128
        )
        if len(self.signature) != expected_signature_length:
            raise ValidationError(
                "consent signature has the wrong hexadecimal length"
            )
        try:
            bytes.fromhex(self.signature)
        except ValueError as exc:
            raise ValidationError("consent signature is not hexadecimal") from exc

    def signing_payload(self) -> dict[str, JSONValue]:
        return {
            "receipt_id": self.receipt_id,
            "issuer": self.issuer,
            "consent_id": self.consent_id,
            "request_digest": self.request_digest,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "action_id": self.action_id,
            "action_digest": self.action_digest,
            "resource_scope": self.resource_scope,
            "approved": self.approved,
            "channel": self.channel,
            "decision_reason": self.decision_reason,
            "decided_at": self.decided_at.isoformat(),
            "consent_expires_at": self.consent_expires_at.isoformat(),
            "scheme": self.scheme,
        }

    def signing_bytes(self) -> bytes:
        return canonical_json(self.signing_payload()).encode("utf-8")

    def to_dict(self) -> dict[str, JSONValue]:
        return {**self.signing_payload(), "signature": self.signature}

    @property
    def receipt_digest(self) -> str:
        return hashlib.sha256(
            canonical_json(self.to_dict()).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConsentReceipt":
        try:
            approved = value["approved"]
            if not isinstance(approved, bool):
                raise TypeError("approved must be boolean")
            return cls(
                receipt_id=str(value["receipt_id"]),
                issuer=str(value["issuer"]),
                consent_id=str(value["consent_id"]),
                request_digest=str(value["request_digest"]),
                session_id=str(value["session_id"]),
                goal_id=str(value["goal_id"]),
                action_id=str(value["action_id"]),
                action_digest=str(value["action_digest"]),
                resource_scope=str(value["resource_scope"]),
                approved=approved,
                channel=str(value["channel"]),
                decision_reason=str(value["decision_reason"]),
                decided_at=datetime.fromisoformat(str(value["decided_at"])),
                consent_expires_at=datetime.fromisoformat(
                    str(value["consent_expires_at"])
                ),
                scheme=str(value["scheme"]),
                signature=str(value["signature"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("invalid consent receipt payload") from exc

    def correlates(self, request: ConsentRequest) -> bool:
        return (
            self.consent_id == request.consent_id
            and self.issuer == request.authority_issuer
            and self.scheme == request.authority_scheme
            and self.request_digest == request.request_digest
            and self.session_id == request.session_id
            and self.goal_id == request.goal_id
            and self.action_id == request.action_id
            and self.action_digest == request.action_digest
            and self.resource_scope == request.resource_scope
            and self.consent_expires_at == request.expires_at
        )


class ConsentReceiptSigner:
    """Sign a decision supplied by a trusted consent acquisition channel."""

    def __init__(
        self,
        *,
        issuer: str,
        secret: bytes,
        channel: str,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ) -> None:
        self.issuer = require_text(issuer, "issuer")
        self.channel = require_text(channel, "channel")
        self._secret = _validated_secret(secret)
        self._clock = clock
        self._id_factory = id_factory

    @property
    def scheme(self) -> str:
        return HMAC_CONSENT_SCHEME

    @property
    def fingerprint(self) -> str:
        return f"hmac:sha256:{hashlib.sha256(self._secret).hexdigest()}"

    def decide(
        self,
        request: ConsentRequest,
        *,
        approved: bool,
        decision_reason: str,
    ) -> ConsentReceipt:
        if not isinstance(approved, bool):
            raise ValidationError("approved must be boolean")
        decided_at = self._clock()
        if decided_at < request.created_at:
            raise ConsentError("consent_decision_before_request")
        if decided_at >= request.expires_at:
            raise ConsentError("consent_request_expired")
        unsigned = {
            "receipt_id": f"receipt:{self._id_factory()}",
            "issuer": self.issuer,
            "consent_id": request.consent_id,
            "request_digest": request.request_digest,
            "session_id": request.session_id,
            "goal_id": request.goal_id,
            "action_id": request.action_id,
            "action_digest": request.action_digest,
            "resource_scope": request.resource_scope,
            "approved": approved,
            "channel": self.channel,
            "decision_reason": require_text(decision_reason, "decision_reason"),
            "decided_at": decided_at,
            "consent_expires_at": request.expires_at,
            "scheme": CONSENT_SCHEME,
        }
        provisional = ConsentReceipt(signature="0" * 64, **unsigned)
        signature = hmac.new(
            self._secret,
            provisional.signing_bytes(),
            hashlib.sha256,
        ).hexdigest()
        return ConsentReceipt(signature=signature, **unsigned)


class ConsentReceiptVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        secret: bytes,
        clock: Clock = utc_now,
        future_tolerance: timedelta = timedelta(seconds=30),
    ) -> None:
        self.issuer = require_text(issuer, "issuer")
        self._secret = _validated_secret(secret)
        self._clock = clock
        if future_tolerance < timedelta(0):
            raise ValidationError("future_tolerance cannot be negative")
        self._future_tolerance = future_tolerance

    @property
    def scheme(self) -> str:
        return HMAC_CONSENT_SCHEME

    @property
    def fingerprint(self) -> str:
        return f"hmac:sha256:{hashlib.sha256(self._secret).hexdigest()}"

    def verify(
        self,
        receipt: ConsentReceipt,
        request: ConsentRequest,
    ) -> VerificationResult:
        if (
            request.authority_issuer != self.issuer
            or request.authority_scheme != self.scheme
            or request.authority_fingerprint != self.fingerprint
        ):
            return VerificationResult(False, "consent_authority_mismatch")
        if receipt.issuer != self.issuer:
            return VerificationResult(False, "consent_issuer_mismatch")
        expected = hmac.new(
            self._secret,
            receipt.signing_bytes(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, receipt.signature):
            return VerificationResult(False, "consent_signature_invalid")
        if not receipt.correlates(request):
            return VerificationResult(False, "consent_correlation_mismatch")
        if receipt.decided_at < request.created_at:
            return VerificationResult(False, "consent_decision_before_request")
        if receipt.decided_at >= request.expires_at:
            return VerificationResult(False, "consent_expired")
        now = self._clock()
        if receipt.decided_at - now > self._future_tolerance:
            return VerificationResult(False, "consent_from_future")
        if now >= request.expires_at:
            return VerificationResult(False, "consent_expired")
        return VerificationResult(True, "consent_valid")


class ConsentVerifier(Protocol):
    issuer: str
    scheme: str
    fingerprint: str

    def verify(
        self,
        receipt: ConsentReceipt,
        request: ConsentRequest,
    ) -> VerificationResult: ...


class ConsentSigner(Protocol):
    issuer: str
    channel: str
    scheme: str
    fingerprint: str

    def decide(
        self,
        request: ConsentRequest,
        *,
        approved: bool,
        decision_reason: str,
    ) -> ConsentReceipt: ...


class InteractiveConsentGate:
    """Acquire one explicit terminal decision using an exact challenge."""

    def __init__(
        self,
        signer: ConsentSigner,
        *,
        clock: Clock = utc_now,
        require_tty: bool = True,
    ) -> None:
        self._signer = signer
        self._clock = clock
        self._require_tty = require_tty
        expected_channel = (
            INTERACTIVE_TTY_CHANNEL if require_tty else TEST_HARNESS_CHANNEL
        )
        if signer.channel != expected_channel:
            raise ValidationError(
                "consent signer channel does not match gate acquisition mode"
            )

    def decide(
        self,
        request: ConsentRequest,
        *,
        input_stream: TextIO = sys.stdin,
        output_stream: TextIO = sys.stdout,
    ) -> ConsentReceipt:
        if (
            request.authority_issuer != self._signer.issuer
            or request.authority_scheme != self._signer.scheme
            or request.authority_fingerprint != self._signer.fingerprint
        ):
            raise ConsentError("consent_authority_mismatch")
        if self._require_tty and not (
            input_stream.isatty() and output_stream.isatty()
        ):
            raise ConsentError("interactive_tty_required")
        if self._clock() >= request.expires_at:
            raise ConsentError("consent_request_expired")

        output_stream.write(
            "\nDARWIN v50 — CONSENTIMENTO EXPLÍCITO\n"
            f"Ação: {request.action_name}\n"
            f"Parâmetros exatos: {canonical_json(request.parameters)}\n"
            f"Fonte executora: {request.adapter_source}\n"
            f"Autoridade: {request.authority_issuer}\n"
            f"Esquema: {request.authority_scheme}\n"
            f"Fingerprint: {request.authority_fingerprint}\n"
            f"Escopo: {request.resource_scope}\n"
            f"Risco declarado: {request.risk.value}\n"
            f"Expira em: {request.expires_at.isoformat()}\n"
            f"Para aprovar, digite exatamente: APROVAR {request.challenge}\n"
            "Para negar, digite: NEGAR\n> "
        )
        output_stream.flush()
        response = input_stream.readline()
        normalized = response.strip()
        expected = f"APROVAR {request.challenge}"
        if normalized == expected:
            return self._signer.decide(
                request,
                approved=True,
                decision_reason="challenge_confirmed",
            )
        reason = (
            "user_denied"
            if normalized == "NEGAR"
            else "challenge_mismatch"
            if normalized
            else "input_closed"
        )
        return self._signer.decide(
            request,
            approved=False,
            decision_reason=reason,
        )
