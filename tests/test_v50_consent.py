from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from darwin_v50.capabilities import (
    CapabilityApprovalSigner,
    CapabilityApprovalVerifier,
    CapabilityError,
)
from darwin_v50.consent import (
    HMAC_CONSENT_SCHEME,
    INTERACTIVE_TTY_CHANNEL,
    TEST_HARNESS_CHANNEL,
    ConsentError,
    ConsentReceiptSigner,
    ConsentReceiptVerifier,
    ConsentRisk,
    InteractiveConsentGate,
)
from darwin_v50.executor import CREATE_TEXT_FILE
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import (
    CausalEvent,
    ComparisonCondition,
    ComparisonOperator,
)


SOURCE = "workspace.consent.test"
CAPABILITY_ISSUER = "capability.consent.test"
CONSENT_ISSUER = "human-consent.test"
CAPABILITY_SECRET = b"darwin-v50-capability-consent-test-secret-minimum"
CONSENT_SECRET = b"darwin-v50-explicit-consent-test-secret-minimum"
SCOPE = "workspace:sha256:" + "a" * 64


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class DarwinV50ConsentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.clock = MutableClock(
            datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
        )
        self.consent_signer = ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            secret=CONSENT_SECRET,
            channel=TEST_HARNESS_CHANNEL,
            clock=self.clock,
        )
        self.capability_signer = CapabilityApprovalSigner(
            issuer=CAPABILITY_ISSUER,
            secret=CAPABILITY_SECRET,
            clock=self.clock,
        )
        self.kernel = self.open_kernel(accept_test_channel=True)

    def tearDown(self) -> None:
        if not self.kernel.store.closed:
            self.kernel.close()
        self.temporary_directory.cleanup()

    def open_kernel(
        self,
        *,
        database: Path | None = None,
        accept_test_channel: bool,
    ) -> DarwinKernelV50:
        options = {}
        if accept_test_channel:
            options["accepted_consent_channels"] = {TEST_HARNESS_CHANNEL}
        options["accepted_consent_schemes"] = {HMAC_CONSENT_SCHEME}
        return DarwinKernelV50.open(
            database or self.root / "darwin-v50.db",
            clock=self.clock,
            consent_verifiers={
                CONSENT_ISSUER: ConsentReceiptVerifier(
                    issuer=CONSENT_ISSUER,
                    secret=CONSENT_SECRET,
                    clock=self.clock,
                )
            },
            capability_verifiers={
                CAPABILITY_ISSUER: CapabilityApprovalVerifier(
                    issuer=CAPABILITY_ISSUER,
                    secret=CAPABILITY_SECRET,
                    clock=self.clock,
                )
            },
            **options,
        )

    def dispatch(self, filename: str = "consented.txt"):
        goal = self.kernel.create_goal(
            session_id="session:consent",
            description="Require an explicit decision before a real effect",
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
            parameters={"path": filename, "content": "authorized"},
        )
        return self.kernel.pending_action(goal.goal_id)

    def request_consent(self, action):
        return self.kernel.request_consent(
            action.goal_id,
            consent_issuer=CONSENT_ISSUER,
            expected_resource_scope=SCOPE,
            risk=ConsentRisk.LOW,
            ttl=timedelta(minutes=5),
        )

    def approve_in_test_gate(self, request):
        gate = InteractiveConsentGate(
            self.consent_signer,
            clock=self.clock,
            require_tty=False,
        )
        output = StringIO()
        receipt = gate.decide(
            request,
            input_stream=StringIO(f"APROVAR {request.challenge}\n"),
            output_stream=output,
        )
        self.assertIn(request.action_name, output.getvalue())
        self.assertIn(request.resource_scope, output.getvalue())
        return receipt

    def test_exact_challenge_is_audited_before_grant_registration(self) -> None:
        action = self.dispatch()
        request = self.request_consent(action)
        receipt = self.approve_in_test_gate(request)

        self.assertTrue(receipt.approved)
        self.assertEqual(receipt.channel, TEST_HARNESS_CHANNEL)
        self.kernel.register_consent_receipt(receipt)
        grant = self.capability_signer.approve(
            action,
            adapter_source=SOURCE,
            resource_scope=SCOPE,
            consent=receipt,
        )
        self.kernel.register_capability_grant(
            grant,
            expected_resource_scope=SCOPE,
        )

        kinds = [
            event.kind
            for event in self.kernel.goal_events(action.goal_id)
        ]
        self.assertLess(
            kinds.index("action.dispatched"),
            kinds.index("consent.requested"),
        )
        self.assertLess(
            kinds.index("consent.requested"),
            kinds.index("consent.approved"),
        )
        self.assertLess(
            kinds.index("consent.approved"),
            kinds.index("capability.registered"),
        )
        events = {
            event.kind: event
            for event in self.kernel.goal_events(action.goal_id)
        }
        self.assertEqual(
            events["consent.requested"].parent_event_id,
            events["action.dispatched"].event_id,
        )
        self.assertEqual(
            events["consent.approved"].parent_event_id,
            events["consent.requested"].event_id,
        )
        self.assertEqual(
            events["capability.registered"].parent_event_id,
            events["consent.approved"].event_id,
        )

    def test_capability_cannot_be_issued_without_consent(self) -> None:
        action = self.dispatch("missing-consent.txt")

        with self.assertRaises(CapabilityError) as captured:
            self.capability_signer.approve(
                action,
                adapter_source=SOURCE,
                resource_scope=SCOPE,
            )

        self.assertEqual(captured.exception.code, "consent_required")

    def test_non_tty_input_is_refused_by_default(self) -> None:
        action = self.dispatch("non-tty.txt")
        request = self.request_consent(action)
        interactive_signer = ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            secret=CONSENT_SECRET,
            channel=INTERACTIVE_TTY_CHANNEL,
            clock=self.clock,
        )
        gate = InteractiveConsentGate(
            interactive_signer,
            clock=self.clock,
        )

        with self.assertRaises(ConsentError) as captured:
            gate.decide(
                request,
                input_stream=StringIO(f"APROVAR {request.challenge}\n"),
                output_stream=StringIO(),
            )

        self.assertEqual(captured.exception.code, "interactive_tty_required")

    def test_interactive_gate_labels_only_a_tty_bound_signer_as_interactive(
        self,
    ) -> None:
        action = self.dispatch("real-tty-channel.txt")
        request = self.request_consent(action)
        interactive_signer = ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            secret=CONSENT_SECRET,
            channel=INTERACTIVE_TTY_CHANNEL,
            clock=self.clock,
        )
        gate = InteractiveConsentGate(
            interactive_signer,
            clock=self.clock,
        )

        receipt = gate.decide(
            request,
            input_stream=TTYStringIO(f"APROVAR {request.challenge}\n"),
            output_stream=TTYStringIO(),
        )

        self.assertTrue(receipt.approved)
        self.assertEqual(receipt.channel, INTERACTIVE_TTY_CHANNEL)
        with self.assertRaisesRegex(
            ValueError,
            "signer channel does not match",
        ):
            InteractiveConsentGate(
                self.consent_signer,
                clock=self.clock,
            )

    def test_test_harness_receipt_is_rejected_by_production_default(self) -> None:
        database = self.root / "production-channel.db"
        production_kernel = self.open_kernel(
            database=database,
            accept_test_channel=False,
        )
        try:
            goal = production_kernel.create_goal(
                session_id="session:production-channel",
                description="Refuse simulated consent in production policy",
                evidence_source=SOURCE,
                condition=ComparisonCondition(
                    "file_exists",
                    ComparisonOperator.EQUAL,
                    True,
                ),
            )
            production_kernel.start_goal(goal.goal_id)
            production_kernel.dispatch_action(
                goal.goal_id,
                action_name=CREATE_TEXT_FILE,
                parameters={"path": "production.txt", "content": "blocked"},
            )
            action = production_kernel.pending_action(goal.goal_id)
            request = production_kernel.request_consent(
                goal.goal_id,
                consent_issuer=CONSENT_ISSUER,
                expected_resource_scope=SCOPE,
                risk=ConsentRisk.LOW,
            )
            receipt = self.consent_signer.decide(
                request,
                approved=True,
                decision_reason="automated_test_fixture",
            )

            with self.assertRaises(ConsentError) as captured:
                production_kernel.register_consent_receipt(receipt)

            self.assertEqual(
                captured.exception.code,
                "consent_channel_not_accepted",
            )
            self.assertEqual(action.action_id, request.action_id)
        finally:
            production_kernel.close()

    def test_wrong_challenge_records_denial_and_cannot_authorize(self) -> None:
        action = self.dispatch("wrong-challenge.txt")
        request = self.request_consent(action)
        gate = InteractiveConsentGate(
            self.consent_signer,
            clock=self.clock,
            require_tty=False,
        )
        receipt = gate.decide(
            request,
            input_stream=StringIO("APROVAR WRONG000\n"),
            output_stream=StringIO(),
        )

        self.assertFalse(receipt.approved)
        self.assertEqual(receipt.decision_reason, "challenge_mismatch")
        self.kernel.register_consent_receipt(receipt)
        with self.assertRaises(CapabilityError) as captured:
            self.capability_signer.approve(
                action,
                adapter_source=SOURCE,
                resource_scope=SCOPE,
                consent=receipt,
            )

        self.assertEqual(captured.exception.code, "consent_not_approved")
        kinds = [
            event.kind
            for event in self.kernel.goal_events(action.goal_id)
        ]
        self.assertIn("consent.denied", kinds)
        self.assertNotIn("capability.registered", kinds)

    def test_forged_receipt_is_rejected_without_audit_event(self) -> None:
        action = self.dispatch("forged-consent.txt")
        request = self.request_consent(action)
        receipt = self.approve_in_test_gate(request)
        forged = replace(receipt, signature="0" * 64)

        with self.assertRaises(ConsentError) as captured:
            self.kernel.register_consent_receipt(forged)

        self.assertEqual(captured.exception.code, "consent_signature_invalid")
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=action.goal_id,
                kind="consent.approved",
            ),
            0,
        )

    def test_expired_request_cannot_be_decided_or_registered(self) -> None:
        action = self.dispatch("expired-consent.txt")
        request = self.request_consent(action)
        valid_before_expiry = self.consent_signer.decide(
            request,
            approved=True,
            decision_reason="automated_test_fixture",
        )
        self.clock.value = request.expires_at

        with self.assertRaises(ConsentError) as signing:
            self.consent_signer.decide(
                request,
                approved=True,
                decision_reason="too_late",
            )
        with self.assertRaises(ConsentError) as registration:
            self.kernel.register_consent_receipt(valid_before_expiry)

        self.assertEqual(signing.exception.code, "consent_request_expired")
        self.assertEqual(registration.exception.code, "consent_expired")

    def test_receipt_cannot_cross_actions_or_scopes(self) -> None:
        action_a = self.dispatch("action-a.txt")
        request_a = self.request_consent(action_a)
        receipt_a = self.approve_in_test_gate(request_a)
        action_b = self.dispatch("action-b.txt")

        with self.assertRaises(CapabilityError) as cross_action:
            self.capability_signer.approve(
                action_b,
                adapter_source=SOURCE,
                resource_scope=SCOPE,
                consent=receipt_a,
            )
        with self.assertRaises(CapabilityError) as cross_scope:
            self.capability_signer.approve(
                action_a,
                adapter_source=SOURCE,
                resource_scope="workspace:sha256:" + "b" * 64,
                consent=receipt_a,
            )

        self.assertEqual(
            cross_action.exception.code,
            "consent_correlation_mismatch",
        )
        self.assertEqual(
            cross_scope.exception.code,
            "consent_correlation_mismatch",
        )

    def test_unregistered_and_replayed_receipts_cannot_create_two_grants(self) -> None:
        action = self.dispatch("replay.txt")
        request = self.request_consent(action)
        receipt = self.approve_in_test_gate(request)
        grant = self.capability_signer.approve(
            action,
            adapter_source=SOURCE,
            resource_scope=SCOPE,
            consent=receipt,
        )

        with self.assertRaises(CapabilityError) as unregistered:
            self.kernel.register_capability_grant(
                grant,
                expected_resource_scope=SCOPE,
            )
        self.assertEqual(
            unregistered.exception.code,
            "approved_consent_not_registered",
        )

        self.kernel.register_consent_receipt(receipt)
        with self.assertRaises(ConsentError) as replay:
            self.kernel.register_consent_receipt(receipt)
        self.assertEqual(
            replay.exception.code,
            "consent_decision_already_registered",
        )

        self.kernel.register_capability_grant(
            grant,
            expected_resource_scope=SCOPE,
        )
        second = self.capability_signer.approve(
            action,
            adapter_source=SOURCE,
            resource_scope=SCOPE,
            consent=receipt,
        )
        with self.assertRaises(CapabilityError) as duplicate_grant:
            self.kernel.register_capability_grant(
                second,
                expected_resource_scope=SCOPE,
            )
        self.assertEqual(
            duplicate_grant.exception.code,
            "capability_already_registered",
        )

    def test_store_rejects_fabricated_capability_event_payload(self) -> None:
        action = self.dispatch("fabricated-ledger-event.txt")
        request = self.request_consent(action)
        receipt = self.approve_in_test_gate(request)
        self.kernel.register_consent_receipt(receipt)
        grant = self.capability_signer.approve(
            action,
            adapter_source=SOURCE,
            resource_scope=SCOPE,
            consent=receipt,
        )
        approved_event = next(
            event
            for event in self.kernel.goal_events(action.goal_id)
            if event.kind == "consent.approved"
        )
        fabricated = CausalEvent.create(
            session_id=action.session_id,
            kind="capability.registered",
            goal_id=action.goal_id,
            action_id=action.action_id,
            parent_event_id=approved_event.event_id,
            payload={
                "grant_id": "grant:fabricated",
                "action_digest": grant.action_digest,
                "resource_scope": grant.resource_scope,
                "consent_id": grant.consent_id,
                "consent_receipt_digest": grant.consent_receipt_digest,
            },
            clock=self.clock,
        )

        with self.assertRaises(CapabilityError) as captured:
            with self.kernel.store.transaction() as connection:
                self.kernel.store.append_event(
                    fabricated,
                    connection=connection,
                )
                self.kernel.store.register_capability(
                    grant,
                    registered_event_id=fabricated.event_id,
                    connection=connection,
                )

        self.assertEqual(
            captured.exception.code,
            "capability_registration_payload_mismatch",
        )
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=action.goal_id,
                kind="capability.registered",
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
