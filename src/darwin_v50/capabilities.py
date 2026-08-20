"""One-use capability grants for Darwin v50 external actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

from .consent import ConsentReceipt
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


CAPABILITY_SCHEME = "hmac-capability-v1"


class CapabilityError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def workspace_scope(root: str | Path) -> str:
    path = Path(root)
    if not path.exists() or not path.is_dir():
        raise ValidationError("capability workspace must be an existing directory")
    normalized = os.path.normcase(str(path.resolve(strict=True))).encode("utf-8")
    return f"workspace:sha256:{hashlib.sha256(normalized).hexdigest()}"


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    grant_id: str
    issuer: str
    adapter_source: str
    session_id: str
    goal_id: str
    action_id: str
    action_digest: str
    resource_scope: str
    consent_id: str
    consent_receipt_digest: str
    issued_at: datetime
    expires_at: datetime
    max_uses: int
    scheme: str
    signature: str

    def __post_init__(self) -> None:
        for field_name in (
            "grant_id",
            "issuer",
            "adapter_source",
            "session_id",
            "goal_id",
            "action_id",
            "action_digest",
            "resource_scope",
            "consent_id",
        ):
            require_text(str(getattr(self, field_name)), field_name)
        if len(self.consent_receipt_digest) != 64:
            raise ValidationError(
                "consent_receipt_digest must be a SHA-256 hexadecimal digest"
            )
        try:
            bytes.fromhex(self.consent_receipt_digest)
        except ValueError as exc:
            raise ValidationError(
                "consent_receipt_digest is not hexadecimal"
            ) from exc
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValidationError("capability timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValidationError("capability expiration must follow issuance")
        if (
            not isinstance(self.max_uses, int)
            or isinstance(self.max_uses, bool)
            or self.max_uses != 1
        ):
            raise ValidationError("Darwin v50 capability grants are one-use")
        if self.scheme != CAPABILITY_SCHEME:
            raise ValidationError(f"unsupported capability scheme: {self.scheme}")
        if len(self.signature) != 64:
            raise ValidationError(
                "capability signature must be 64 hexadecimal characters"
            )
        try:
            bytes.fromhex(self.signature)
        except ValueError as exc:
            raise ValidationError("capability signature is not hexadecimal") from exc

    def signing_payload(self) -> dict[str, JSONValue]:
        return {
            "grant_id": self.grant_id,
            "issuer": self.issuer,
            "adapter_source": self.adapter_source,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "action_id": self.action_id,
            "action_digest": self.action_digest,
            "resource_scope": self.resource_scope,
            "consent_id": self.consent_id,
            "consent_receipt_digest": self.consent_receipt_digest,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "max_uses": self.max_uses,
            "scheme": self.scheme,
        }

    def signing_bytes(self) -> bytes:
        return canonical_json(self.signing_payload()).encode("utf-8")

    def to_dict(self) -> dict[str, JSONValue]:
        return {**self.signing_payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CapabilityGrant":
        try:
            return cls(
                grant_id=str(value["grant_id"]),
                issuer=str(value["issuer"]),
                adapter_source=str(value["adapter_source"]),
                session_id=str(value["session_id"]),
                goal_id=str(value["goal_id"]),
                action_id=str(value["action_id"]),
                action_digest=str(value["action_digest"]),
                resource_scope=str(value["resource_scope"]),
                consent_id=str(value["consent_id"]),
                consent_receipt_digest=str(value["consent_receipt_digest"]),
                issued_at=datetime.fromisoformat(str(value["issued_at"])),
                expires_at=datetime.fromisoformat(str(value["expires_at"])),
                max_uses=int(value["max_uses"]),
                scheme=str(value["scheme"]),
                signature=str(value["signature"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("invalid capability grant payload") from exc

    def correlates(
        self,
        request: ActionRequest,
        *,
        adapter_source: str,
        resource_scope: str,
    ) -> bool:
        return (
            self.adapter_source == adapter_source
            and self.session_id == request.session_id
            and self.goal_id == request.goal_id
            and self.action_id == request.action_id
            and self.action_digest == request.action_digest
            and self.resource_scope == resource_scope
        )


def _validated_secret(secret: bytes) -> bytes:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValidationError("capability secret must contain at least 32 bytes")
    return secret


class CapabilityApprovalSigner:
    """Issue a capability only after receiving an approved consent receipt.

    This class does not verify the receipt signature; the kernel verifies the
    exact persisted receipt before registering the resulting grant.
    """

    def __init__(
        self,
        *,
        issuer: str,
        secret: bytes,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ) -> None:
        self.issuer = require_text(issuer, "issuer")
        self._secret = _validated_secret(secret)
        self._clock = clock
        self._id_factory = id_factory

    def approve(
        self,
        request: ActionRequest,
        *,
        adapter_source: str,
        resource_scope: str,
        consent: ConsentReceipt | None = None,
        ttl: timedelta = timedelta(minutes=2),
    ) -> CapabilityGrant:
        if ttl <= timedelta(0):
            raise ValidationError("capability ttl must be positive")
        issued_at = self._clock()
        if consent is None:
            raise CapabilityError("consent_required")
        if not consent.approved:
            raise CapabilityError("consent_not_approved")
        if (
            consent.session_id != request.session_id
            or consent.goal_id != request.goal_id
            or consent.action_id != request.action_id
            or consent.action_digest != request.action_digest
            or consent.resource_scope != resource_scope
        ):
            raise CapabilityError("consent_correlation_mismatch")
        if issued_at < consent.decided_at:
            raise CapabilityError("consent_from_future")
        if issued_at >= consent.consent_expires_at:
            raise CapabilityError("consent_expired")
        expires_at = min(issued_at + ttl, consent.consent_expires_at)
        unsigned = {
            "grant_id": f"grant:{self._id_factory()}",
            "issuer": self.issuer,
            "adapter_source": require_text(adapter_source, "adapter_source"),
            "session_id": request.session_id,
            "goal_id": request.goal_id,
            "action_id": request.action_id,
            "action_digest": request.action_digest,
            "resource_scope": require_text(resource_scope, "resource_scope"),
            "consent_id": consent.consent_id,
            "consent_receipt_digest": consent.receipt_digest,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "max_uses": 1,
            "scheme": CAPABILITY_SCHEME,
        }
        provisional = CapabilityGrant(signature="0" * 64, **unsigned)
        signature = hmac.new(
            self._secret,
            provisional.signing_bytes(),
            hashlib.sha256,
        ).hexdigest()
        return CapabilityGrant(signature=signature, **unsigned)


class CapabilityApprovalVerifier:
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

    def verify(self, grant: CapabilityGrant) -> VerificationResult:
        if grant.issuer != self.issuer:
            return VerificationResult(False, "capability_issuer_mismatch")
        expected = hmac.new(
            self._secret,
            grant.signing_bytes(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, grant.signature):
            return VerificationResult(False, "capability_signature_invalid")
        now = self._clock()
        if grant.issued_at - now > self._future_tolerance:
            return VerificationResult(False, "capability_from_future")
        if now >= grant.expires_at:
            return VerificationResult(False, "capability_expired")
        return VerificationResult(True, "capability_valid")
