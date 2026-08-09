from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from darwin_v50.capabilities import (
    CapabilityApprovalSigner,
    CapabilityApprovalVerifier,
    CapabilityError,
    workspace_scope,
)
from darwin_v50.consent import (
    HMAC_CONSENT_SCHEME,
    TEST_HARNESS_CHANNEL,
    ConsentReceiptSigner,
    ConsentReceiptVerifier,
    ConsentRisk,
)
from darwin_v50.evidence import HMACObservationVerifier
from darwin_v50.executor import CREATE_TEXT_FILE
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.isolation import (
    IsolationMechanism,
    IsolationPolicyError,
    require_os_security_boundary,
)
from darwin_v50.models import (
    ComparisonCondition,
    ComparisonOperator,
    GoalStatus,
)
from darwin_v50.subprocess_executor import (
    SubprocessExecutionError,
    SubprocessWorkspaceExecutor,
)
from darwin_v50.windows_isolation import (
    current_process_appcontainer_evidence,
    probe_windows_isolation_availability,
)


SOURCE = "workspace.subprocess.test"
ISSUER = "approval.test"
CONSENT_ISSUER = "consent.test"
APPROVAL_SECRET = b"darwin-v50-approval-test-secret-32-bytes-minimum"
CONSENT_SECRET = b"darwin-v50-consent-test-secret-32-bytes-minimum"
OBSERVATION_SECRET = b"darwin-v50-observation-test-secret-32-bytes-min"


class DarwinV50SubprocessCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.database = self.root / "darwin-v50.db"
        self.scope = workspace_scope(self.workspace)
        self.approval_signer = CapabilityApprovalSigner(
            issuer=ISSUER,
            secret=APPROVAL_SECRET,
        )
        self.consent_signer = ConsentReceiptSigner(
            issuer=CONSENT_ISSUER,
            secret=CONSENT_SECRET,
            channel=TEST_HARNESS_CHANNEL,
        )
        self.consents = {}
        self.kernel = DarwinKernelV50.open(
            self.database,
            evidence_verifiers={
                SOURCE: HMACObservationVerifier(
                    source=SOURCE,
                    secret=OBSERVATION_SECRET,
                )
            },
            capability_verifiers={
                ISSUER: CapabilityApprovalVerifier(
                    issuer=ISSUER,
                    secret=APPROVAL_SECRET,
                )
            },
            consent_verifiers={
                CONSENT_ISSUER: ConsentReceiptVerifier(
                    issuer=CONSENT_ISSUER,
                    secret=CONSENT_SECRET,
                )
            },
            accepted_consent_channels={TEST_HARNESS_CHANNEL},
            accepted_consent_schemes={HMAC_CONSENT_SCHEME},
        )
        self.executor = SubprocessWorkspaceExecutor(
            database=self.database,
            workspace_root=self.workspace,
            adapter_source=SOURCE,
            observation_secret=OBSERVATION_SECRET,
            python_executable=sys.executable,
        )

    def tearDown(self) -> None:
        if not self.kernel.store.closed:
            self.kernel.close()
        self.temporary_directory.cleanup()

    def dispatch(self, filename: str = "authorized.txt"):
        goal = self.kernel.create_goal(
            session_id="session:capability",
            description="Create one explicitly authorized file",
            evidence_source=SOURCE,
            condition=ComparisonCondition(
                "file_exists",
                ComparisonOperator.EQUAL,
                True,
            ),
        )
        self.kernel.start_goal(goal.goal_id)
        goal = self.kernel.dispatch_action(
            goal.goal_id,
            action_name=CREATE_TEXT_FILE,
            parameters={"path": filename, "content": "authorized effect"},
        )
        return goal, self.kernel.pending_action(goal.goal_id)

    def issue_test_consent(self, request, *, scope=None):
        effective_scope = scope or self.scope
        consent_request = self.kernel.request_consent(
            request.goal_id,
            consent_issuer=CONSENT_ISSUER,
            expected_resource_scope=effective_scope,
            risk=ConsentRisk.LOW,
        )
        receipt = self.consent_signer.decide(
            consent_request,
            approved=True,
            decision_reason="automated_test_fixture",
        )
        self.kernel.register_consent_receipt(receipt)
        self.consents[request.action_id] = receipt
        return receipt

    def approve(self, request, *, scope=None):
        effective_scope = scope or self.scope
        consent = self.consents.get(request.action_id)
        if consent is None:
            consent = self.issue_test_consent(request, scope=effective_scope)
        return self.approval_signer.approve(
            request,
            adapter_source=SOURCE,
            resource_scope=effective_scope,
            consent=consent,
        )

    def approve_and_register(self, request):
        grant = self.approve(request)
        self.kernel.register_capability_grant(
            grant,
            expected_resource_scope=self.scope,
        )
        return grant

    def test_separate_process_consumes_grant_and_completes_goal(self) -> None:
        goal, request = self.dispatch()
        grant = self.approve_and_register(request)

        envelope = self.executor.execute(request, grant)
        result = self.kernel.record_attested_observation(envelope)

        self.assertNotEqual(envelope.metrics["worker_pid"], os.getpid())
        self.assertIs(envelope.metrics["separate_process"], True)
        self.assertEqual(envelope.metrics["capability_grant_id"], grant.grant_id)
        self.assertIs(envelope.metrics["appcontainer_query_succeeded"], True)
        self.assertIs(envelope.metrics["appcontainer_token"], False)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertEqual(
            (self.workspace / "authorized.txt").read_text(encoding="utf-8"),
            "authorized effect",
        )
        events = self.kernel.goal_events(goal.goal_id)
        kinds = [event.kind for event in events]
        self.assertLess(
            kinds.index("capability.registered"),
            kinds.index("capability.consumed"),
        )
        self.assertLess(
            kinds.index("capability.consumed"),
            kinds.index("observation.recorded"),
        )
        registered = next(
            event for event in events if event.kind == "capability.registered"
        )
        consumed = next(
            event for event in events if event.kind == "capability.consumed"
        )
        self.assertEqual(consumed.parent_event_id, registered.event_id)

    def test_executor_does_not_claim_an_os_security_boundary(self) -> None:
        assessment = self.executor.isolation

        self.assertEqual(
            assessment.mechanism,
            IsolationMechanism.SAME_USER_SUBPROCESS,
        )
        self.assertTrue(assessment.separate_process)
        self.assertTrue(assessment.same_user_identity)
        self.assertFalse(assessment.security_boundary)
        self.assertFalse(assessment.filesystem_enforced_by_os)
        self.assertFalse(assessment.network_enforced_by_os)
        self.assertFalse(assessment.runtime_verified)
        with self.assertRaises(IsolationPolicyError) as captured:
            require_os_security_boundary(assessment)
        self.assertEqual(
            captured.exception.code,
            "isolation_not_runtime_verified",
        )

    def test_appcontainer_requirement_fails_before_consumption_or_effect(
        self,
    ) -> None:
        evidence = current_process_appcontainer_evidence()
        if evidence.is_appcontainer:
            self.skipTest("test runner is already inside AppContainer")
        _, request = self.dispatch("requires-appcontainer.txt")
        grant = self.approve_and_register(request)
        guarded = SubprocessWorkspaceExecutor(
            database=self.database,
            workspace_root=self.workspace,
            adapter_source=SOURCE,
            observation_secret=OBSERVATION_SECRET,
            python_executable=sys.executable,
            require_appcontainer=True,
        )

        with self.assertRaises(SubprocessExecutionError) as captured:
            guarded.execute(request, grant)

        self.assertEqual(captured.exception.code, "appcontainer_required")
        self.assertFalse((self.workspace / "requires-appcontainer.txt").exists())

        envelope = self.executor.execute(request, grant)
        result = self.kernel.record_attested_observation(envelope)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)

    def test_windows_isolation_probe_never_claims_a_launch(self) -> None:
        availability = probe_windows_isolation_availability()

        self.assertTrue(availability.platform_supported)
        self.assertTrue(availability.current_token.query_succeeded)
        self.assertFalse(availability.current_token.is_appcontainer)
        self.assertIsInstance(
            availability.legacy_appcontainer_profile_api,
            bool,
        )
        self.assertIsInstance(
            availability.experimental_sandbox_api,
            bool,
        )

    def test_unregistered_grant_cannot_execute(self) -> None:
        _, request = self.dispatch("unregistered.txt")
        grant = self.approve(request)

        with self.assertRaises(SubprocessExecutionError) as captured:
            self.executor.execute(request, grant)

        self.assertEqual(captured.exception.code, "capability_not_registered")
        self.assertFalse((self.workspace / "unregistered.txt").exists())

    def test_parent_secrets_are_not_inherited_by_worker(self) -> None:
        _, request = self.dispatch("no-secret-inheritance.txt")
        grant = self.approve_and_register(request)

        with patch.dict(
            os.environ,
            {
                "DARWIN_V50_APPROVAL_SECRET": "must-not-cross",
                "DARWIN_V50_CONSENT_SECRET": "must-not-cross",
            },
        ):
            envelope = self.executor.execute(request, grant)

        result = self.kernel.record_attested_observation(envelope)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        self.assertTrue((self.workspace / "no-secret-inheritance.txt").is_file())

    def test_grant_is_one_use_even_before_observation_is_recorded(self) -> None:
        _, request = self.dispatch("one-use.txt")
        grant = self.approve_and_register(request)

        envelope = self.executor.execute(request, grant)
        with self.assertRaises(SubprocessExecutionError) as captured:
            self.executor.execute(request, grant)

        self.assertEqual(captured.exception.code, "capability_already_consumed")
        result = self.kernel.record_attested_observation(envelope)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)

    def test_action_cannot_receive_two_registered_grants(self) -> None:
        _, request = self.dispatch("single-grant.txt")
        first = self.approve_and_register(request)
        second = self.approval_signer.approve(
            request,
            adapter_source=SOURCE,
            resource_scope=self.scope,
            consent=self.consents[request.action_id],
        )

        with self.assertRaises(CapabilityError) as captured:
            self.kernel.register_capability_grant(
                second,
                expected_resource_scope=self.scope,
            )

        self.assertNotEqual(first.grant_id, second.grant_id)
        self.assertEqual(captured.exception.code, "capability_already_registered")
        self.assertFalse((self.workspace / "single-grant.txt").exists())

    def test_forged_grant_is_rejected_before_registration(self) -> None:
        _, request = self.dispatch("forged.txt")
        valid = self.approve(request)
        forged = replace(valid, signature="0" * 64)

        with self.assertRaises(CapabilityError) as captured:
            self.kernel.register_capability_grant(
                forged,
                expected_resource_scope=self.scope,
            )

        self.assertEqual(captured.exception.code, "capability_signature_invalid")
        self.assertFalse((self.workspace / "forged.txt").exists())

    def test_expired_grant_is_rejected_before_registration(self) -> None:
        _, request = self.dispatch("expired.txt")
        valid = self.approve(request)
        verifier_time = valid.expires_at + timedelta(seconds=1)
        checking_kernel = DarwinKernelV50.open(
            self.database,
            capability_verifiers={
                ISSUER: CapabilityApprovalVerifier(
                    issuer=ISSUER,
                    secret=APPROVAL_SECRET,
                    clock=lambda: verifier_time,
                )
            },
            consent_verifiers={
                CONSENT_ISSUER: ConsentReceiptVerifier(
                    issuer=CONSENT_ISSUER,
                    secret=CONSENT_SECRET,
                    clock=lambda: verifier_time,
                )
            },
            accepted_consent_channels={TEST_HARNESS_CHANNEL},
            accepted_consent_schemes={HMAC_CONSENT_SCHEME},
        )
        try:
            with self.assertRaises(CapabilityError) as captured:
                checking_kernel.register_capability_grant(
                    valid,
                    expected_resource_scope=self.scope,
                )
        finally:
            checking_kernel.close()

        self.assertEqual(captured.exception.code, "capability_expired")
        self.assertFalse((self.workspace / "expired.txt").exists())

    def test_grant_expiring_after_registration_is_rejected_by_worker(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=10)
        database = self.root / "post-registration-expiry.db"
        kernel = DarwinKernelV50.open(
            database,
            clock=lambda: past,
            evidence_verifiers={
                SOURCE: HMACObservationVerifier(
                    source=SOURCE,
                    secret=OBSERVATION_SECRET,
                )
            },
            capability_verifiers={
                ISSUER: CapabilityApprovalVerifier(
                    issuer=ISSUER,
                    secret=APPROVAL_SECRET,
                    clock=lambda: past + timedelta(seconds=1),
                )
            },
            consent_verifiers={
                CONSENT_ISSUER: ConsentReceiptVerifier(
                    issuer=CONSENT_ISSUER,
                    secret=CONSENT_SECRET,
                    clock=lambda: past + timedelta(seconds=1),
                )
            },
            accepted_consent_channels={TEST_HARNESS_CHANNEL},
            accepted_consent_schemes={HMAC_CONSENT_SCHEME},
        )
        try:
            goal = kernel.create_goal(
                session_id="session:expires-after-registration",
                description="Expire before worker consumption",
                evidence_source=SOURCE,
                condition=ComparisonCondition(
                    "file_exists",
                    ComparisonOperator.EQUAL,
                    True,
                ),
            )
            kernel.start_goal(goal.goal_id)
            goal = kernel.dispatch_action(
                goal.goal_id,
                action_name=CREATE_TEXT_FILE,
                parameters={"path": "expired-later.txt", "content": "forbidden"},
            )
            request = kernel.pending_action(goal.goal_id)
            signer = CapabilityApprovalSigner(
                issuer=ISSUER,
                secret=APPROVAL_SECRET,
                clock=lambda: past,
            )
            consent_request = kernel.request_consent(
                request.goal_id,
                consent_issuer=CONSENT_ISSUER,
                expected_resource_scope=self.scope,
                risk=ConsentRisk.LOW,
            )
            consent = ConsentReceiptSigner(
                issuer=CONSENT_ISSUER,
                secret=CONSENT_SECRET,
                channel=TEST_HARNESS_CHANNEL,
                clock=lambda: past,
            ).decide(
                consent_request,
                approved=True,
                decision_reason="automated_test_fixture",
            )
            kernel.register_consent_receipt(consent)
            grant = signer.approve(
                request,
                adapter_source=SOURCE,
                resource_scope=self.scope,
                consent=consent,
                ttl=timedelta(minutes=1),
            )
            kernel.register_capability_grant(
                grant,
                expected_resource_scope=self.scope,
            )
            executor = SubprocessWorkspaceExecutor(
                database=database,
                workspace_root=self.workspace,
                adapter_source=SOURCE,
                observation_secret=OBSERVATION_SECRET,
                python_executable=sys.executable,
            )

            with self.assertRaises(SubprocessExecutionError) as captured:
                executor.execute(request, grant)

            self.assertEqual(captured.exception.code, "capability_expired")
            self.assertFalse((self.workspace / "expired-later.txt").exists())
        finally:
            kernel.close()

    def test_wrong_scope_is_rejected_before_registration(self) -> None:
        _, request = self.dispatch("wrong-scope.txt")
        wrong_scope = "workspace:sha256:" + "0" * 64
        grant = self.approve(request, scope=wrong_scope)

        with self.assertRaises(CapabilityError) as captured:
            self.kernel.register_capability_grant(
                grant,
                expected_resource_scope=self.scope,
            )

        self.assertEqual(captured.exception.code, "capability_correlation_mismatch")
        self.assertFalse((self.workspace / "wrong-scope.txt").exists())

    def test_grant_for_another_action_cannot_be_substituted(self) -> None:
        _, request_a = self.dispatch("action-a.txt")
        _, request_b = self.dispatch("action-b.txt")
        grant_a = self.approve_and_register(request_a)

        with self.assertRaises(SubprocessExecutionError) as captured:
            self.executor.execute(request_b, grant_a)

        self.assertEqual(captured.exception.code, "capability_correlation_mismatch")
        self.assertFalse((self.workspace / "action-a.txt").exists())
        self.assertFalse((self.workspace / "action-b.txt").exists())


if __name__ == "__main__":
    unittest.main()
