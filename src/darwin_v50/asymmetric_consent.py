"""Ed25519 consent authority for an out-of-process Darwin broker."""

from __future__ import annotations

from datetime import timedelta
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .consent import (
    ED25519_CONSENT_SCHEME,
    ConsentError,
    ConsentReceipt,
    ConsentRequest,
)
from .evidence import VerificationResult
from .models import (
    Clock,
    IdFactory,
    ValidationError,
    new_id,
    require_text,
    utc_now,
)


def public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:sha256:{hashlib.sha256(raw).hexdigest()}"


class Ed25519ConsentReceiptSigner:
    """Hold the private key that must remain outside the Darwin kernel."""

    def __init__(
        self,
        *,
        issuer: str,
        private_key: Ed25519PrivateKey,
        channel: str,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ) -> None:
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValidationError("private_key must be an Ed25519 private key")
        self.issuer = require_text(issuer, "issuer")
        self.channel = require_text(channel, "channel")
        self._private_key = private_key
        self._clock = clock
        self._id_factory = id_factory

    @property
    def fingerprint(self) -> str:
        return public_key_fingerprint(self._private_key.public_key())

    @property
    def scheme(self) -> str:
        return ED25519_CONSENT_SCHEME

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
            "decision_reason": require_text(
                decision_reason,
                "decision_reason",
            ),
            "decided_at": decided_at,
            "consent_expires_at": request.expires_at,
            "scheme": ED25519_CONSENT_SCHEME,
        }
        provisional = ConsentReceipt(signature="0" * 128, **unsigned)
        signature = self._private_key.sign(provisional.signing_bytes()).hex()
        return ConsentReceipt(signature=signature, **unsigned)


class Ed25519ConsentReceiptVerifier:
    """Verify consent with a public key incapable of producing signatures."""

    def __init__(
        self,
        *,
        issuer: str,
        public_key: Ed25519PublicKey,
        clock: Clock = utc_now,
        future_tolerance: timedelta = timedelta(seconds=30),
    ) -> None:
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValidationError("public_key must be an Ed25519 public key")
        self.issuer = require_text(issuer, "issuer")
        self._public_key = public_key
        self._clock = clock
        if future_tolerance < timedelta(0):
            raise ValidationError("future_tolerance cannot be negative")
        self._future_tolerance = future_tolerance

    @property
    def fingerprint(self) -> str:
        return public_key_fingerprint(self._public_key)

    @property
    def scheme(self) -> str:
        return ED25519_CONSENT_SCHEME

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
        if receipt.scheme != ED25519_CONSENT_SCHEME:
            return VerificationResult(False, "consent_scheme_mismatch")
        try:
            self._public_key.verify(
                bytes.fromhex(receipt.signature),
                receipt.signing_bytes(),
            )
        except (InvalidSignature, ValueError):
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
