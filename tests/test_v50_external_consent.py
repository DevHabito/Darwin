from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from darwin_v50.asymmetric_consent import (
    Ed25519ConsentReceiptSigner,
    Ed25519ConsentReceiptVerifier,
)
from darwin_v50.capabilities import (
    CapabilityApprovalSigner,
    CapabilityApprovalVerifier,
)
from darwin_v50.consent import (
    TEST_HARNESS_CHANNEL,
    ConsentError,
    ConsentReceiptVerifier,
    ConsentRisk,
    InteractiveConsentGate,
)
from darwin_v50.consent_broker import (
    ConsentBrokerError,
    export_consent_receipt,
    export_consent_request,
    generate_encrypted_keypair,
    load_consent_receipt,
    load_consent_request,
    load_private_key,
    load_public_key,
)
from darwin_v50.executor import CREATE_TEXT_FILE
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import ComparisonCondition, ComparisonOperator


SOURCE = "workspace.external-consent.test"
CONSENT_ISSUER = "consent.external.test"
CAPABILITY_ISSUER = "capability.external.test"
CAPABILITY_SECRET = b"darwin-v50-external-capability-secret-minimum"
HMAC_CONSENT_SECRET = b"darwin-v50-hmac-consent-rejection-secret-min"
PASSPHRASE = b"correct horse battery staple"
SCOPE = "workspace:sha256:" + "c" * 64


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 27, 21, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


class DarwinV50ExternalConsentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.clock = FixedClock()
        self.private_key = Ed25519PrivateKey.generate()
        self.public_verifier = Ed25519ConsentReceiptVerifier(
            issuer=CONSENT_ISSUER,
            public_key=self.private_key.public_key(),
            clock=self.clock,
        )
        self.kernel = DarwinKernelV50.open(
            self.root / "darwin-v50.db",
            clock=self.clock,
            consent_verifiers={CONSENT_ISSUER: self.public_verifier},
            accepted_consent_channels={TEST_HARNESS_CHANNEL},
            capability_verifiers={
                CAPABILITY_ISSUER: CapabilityApprovalVerifier(
                    issuer=CAPABILITY_ISSUER,
                    secret=CAPABILITY_SECRET,
                    clock=self.clock,
                )
            },
        )
        self.capability_signer = CapabilityApprovalSigner(
            issuer=CAPABILITY_ISSUER,
            secret=CAPABILITY_SECRET,
            clock=self.clock,
        )

    def tearDown(self) -> None:
        if not self.kernel.store.closed:
            self.kernel.close()
        self.temporary_directory.cleanup()

    def dispatch(self):
        goal = self.kernel.create_goal(
            session_id="session:external-consent",
            description="Authorize through a public-key verified broker",
            evidence_source=SOURCE,
            condition=ComparisonCondition(
                "file_exists",
                ComparisonOperator.EQUAL,
                True,
            ),
        )
        self.kernel.start_goal(goal.goal_id)
        self.kernel.dispatch_action(
            goal.goal_id,
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "broker-authorized.txt", "content": "authorized"},
        )
        return self.kernel.pending_action(goal.goal_id)

    def request(self, action):
        return self.kernel.request_consent(
            action.goal_id,
            consent_issuer=CONSENT_ISSUER,
            expected_resource_scope=SCOPE,
            risk=ConsentRisk.LOW,
        )

    def sign_for_test(self, request):
        signer = Ed25519ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            private_key=self.private_key,
            channel=TEST_HARNESS_CHANNEL,
            clock=self.clock,
        )
        return InteractiveConsentGate(
            signer,
            clock=self.clock,
            require_tty=False,
        ).decide(
            request,
            input_stream=StringIO(f"APROVAR {request.challenge}\n"),
            output_stream=StringIO(),
        )

    def test_file_handoff_public_verification_and_grant_registration(self) -> None:
        action = self.dispatch()
        request = self.request(action)
        request_file = self.root / "request.json"
        receipt_file = self.root / "receipt.json"

        export_consent_request(request_file, request)
        broker_request = load_consent_request(request_file)
        receipt = self.sign_for_test(broker_request)
        export_consent_receipt(receipt_file, receipt)
        imported_receipt = load_consent_receipt(receipt_file)

        self.assertEqual(broker_request, request)
        self.assertEqual(imported_receipt, receipt)
        self.kernel.register_consent_receipt(imported_receipt)
        grant = self.capability_signer.approve(
            action,
            adapter_source=SOURCE,
            resource_scope=SCOPE,
            consent=imported_receipt,
        )
        self.kernel.register_capability_grant(
            grant,
            expected_resource_scope=SCOPE,
        )

        events = self.kernel.goal_events(action.goal_id)
        approved = next(event for event in events if event.kind == "consent.approved")
        self.assertEqual(
            approved.payload["receipt_digest"],
            receipt.receipt_digest,
        )
        self.assertEqual(
            self.public_verifier.fingerprint,
            Ed25519ConsentReceiptSigner(
                issuer=CONSENT_ISSUER,
                private_key=self.private_key,
                channel=TEST_HARNESS_CHANNEL,
                clock=self.clock,
            ).fingerprint,
        )

    def test_receipt_signed_by_another_private_key_is_rejected(self) -> None:
        action = self.dispatch()
        request = self.request(action)
        wrong_signer = Ed25519ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            private_key=Ed25519PrivateKey.generate(),
            channel=TEST_HARNESS_CHANNEL,
            clock=self.clock,
        )
        receipt = wrong_signer.decide(
            request,
            approved=True,
            decision_reason="wrong_private_key",
        )

        with self.assertRaises(ConsentError) as captured:
            self.kernel.register_consent_receipt(receipt)

        self.assertEqual(captured.exception.code, "consent_signature_invalid")

    def test_authority_key_cannot_be_substituted_after_request(self) -> None:
        action = self.dispatch()
        request = self.request(action)
        replacement_private = Ed25519PrivateKey.generate()
        replacement_signer = Ed25519ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            private_key=replacement_private,
            channel=TEST_HARNESS_CHANNEL,
            clock=self.clock,
        )
        replacement_verifier = Ed25519ConsentReceiptVerifier(
            issuer=CONSENT_ISSUER,
            public_key=replacement_private.public_key(),
            clock=self.clock,
        )
        receipt = replacement_signer.decide(
            request,
            approved=True,
            decision_reason="substituted_authority",
        )

        verification = replacement_verifier.verify(receipt, request)

        self.assertFalse(verification.valid)
        self.assertEqual(verification.reason, "consent_authority_mismatch")

    def test_encrypted_private_key_round_trip_and_wrong_passphrase(self) -> None:
        private_path = self.root / "consent-private.pem"
        public_path = self.root / "consent-public.pem"
        fingerprint = generate_encrypted_keypair(
            private_key_path=private_path,
            public_key_path=public_path,
            passphrase=PASSPHRASE,
        )

        private_bytes = private_path.read_bytes()
        self.assertIn(b"BEGIN ENCRYPTED PRIVATE KEY", private_bytes)
        loaded_private = load_private_key(
            private_path,
            passphrase=PASSPHRASE,
        )
        loaded_public = load_public_key(public_path)
        self.assertEqual(
            Ed25519ConsentReceiptVerifier(
                issuer=CONSENT_ISSUER,
                public_key=loaded_public,
                clock=self.clock,
            ).fingerprint,
            fingerprint,
        )
        self.assertEqual(
            loaded_private.public_key().public_bytes_raw(),
            loaded_public.public_bytes_raw(),
        )
        with self.assertRaises(ConsentBrokerError) as captured:
            load_private_key(
                private_path,
                passphrase=b"wrong passphrase is long enough",
            )
        self.assertEqual(
            captured.exception.code,
            "broker_private_key_invalid",
        )

    def test_key_and_handoff_files_never_overwrite_existing_targets(self) -> None:
        private_path = self.root / "private.pem"
        public_path = self.root / "public.pem"
        public_path.write_text("existing", encoding="utf-8")

        with self.assertRaises(ConsentBrokerError) as key_error:
            generate_encrypted_keypair(
                private_key_path=private_path,
                public_key_path=public_path,
                passphrase=PASSPHRASE,
            )

        self.assertEqual(key_error.exception.code, "broker_target_exists")
        self.assertFalse(private_path.exists())

        action = self.dispatch()
        request = self.request(action)
        handoff = self.root / "request.json"
        export_consent_request(handoff, request)
        with self.assertRaises(ConsentBrokerError) as handoff_error:
            export_consent_request(handoff, request)
        self.assertEqual(handoff_error.exception.code, "broker_target_exists")

    def test_duplicate_json_keys_are_rejected_by_broker_protocol(self) -> None:
        duplicate = self.root / "duplicate.json"
        duplicate.write_text(
            '{"consent_id":"first","consent_id":"second"}',
            encoding="utf-8",
        )

        with self.assertRaises(ConsentBrokerError) as captured:
            load_consent_request(duplicate)

        self.assertEqual(captured.exception.code, "broker_json_duplicate_key")

    def test_hmac_consent_is_rejected_by_default_production_scheme(self) -> None:
        database = self.root / "hmac-refused.db"
        kernel = DarwinKernelV50.open(
            database,
            clock=self.clock,
            consent_verifiers={
                CONSENT_ISSUER: ConsentReceiptVerifier(
                    issuer=CONSENT_ISSUER,
                    secret=HMAC_CONSENT_SECRET,
                    clock=self.clock,
                )
            },
            accepted_consent_channels={TEST_HARNESS_CHANNEL},
        )
        try:
            goal = kernel.create_goal(
                session_id="session:hmac-refused",
                description="Production policy requires asymmetric consent",
                evidence_source=SOURCE,
                condition=ComparisonCondition(
                    "file_exists",
                    ComparisonOperator.EQUAL,
                    True,
                ),
            )
            kernel.start_goal(goal.goal_id)
            kernel.dispatch_action(
                goal.goal_id,
                action_name=CREATE_TEXT_FILE,
                parameters={"path": "hmac.txt", "content": "blocked"},
            )
            with self.assertRaises(ConsentError) as captured:
                kernel.request_consent(
                    goal.goal_id,
                    consent_issuer=CONSENT_ISSUER,
                    expected_resource_scope=SCOPE,
                    risk=ConsentRisk.LOW,
                )

            self.assertEqual(
                captured.exception.code,
                "consent_scheme_not_accepted",
            )
        finally:
            kernel.close()

    def test_weak_key_passphrase_is_rejected_before_file_creation(self) -> None:
        private_path = self.root / "weak-private.pem"
        public_path = self.root / "weak-public.pem"

        with self.assertRaises(ConsentBrokerError) as captured:
            generate_encrypted_keypair(
                private_key_path=private_path,
                public_key_path=public_path,
                passphrase=b"short",
            )

        self.assertEqual(
            captured.exception.code,
            "broker_passphrase_too_weak",
        )
        self.assertFalse(private_path.exists())
        self.assertFalse(public_path.exists())


if __name__ == "__main__":
    unittest.main()
