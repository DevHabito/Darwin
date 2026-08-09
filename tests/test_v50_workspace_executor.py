from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest

from darwin_v50.evidence import (
    ActionRequest,
    HMACObservationSigner,
    HMACObservationVerifier,
    compute_action_digest,
)
from darwin_v50.executor import (
    CREATE_TEXT_FILE,
    INSPECT_FILE,
    CapabilityWorkspaceExecutor,
)
from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import (
    ComparisonCondition,
    ComparisonOperator,
    GoalStatus,
)


SOURCE = "workspace.adapter.test"
SECRET = b"darwin-v50-test-secret-is-at-least-32-bytes"


class DarwinV50WorkspaceExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.signer = HMACObservationSigner(source=SOURCE, secret=SECRET)
        self.verifier = HMACObservationVerifier(source=SOURCE, secret=SECRET)
        self.kernel = DarwinKernelV50.open(
            self.root / "darwin-v50.db",
            evidence_verifiers={SOURCE: self.verifier},
        )
        self.executor = CapabilityWorkspaceExecutor(
            root=self.workspace,
            signer=self.signer,
        )

    def tearDown(self) -> None:
        if not self.kernel.store.closed:
            self.kernel.close()
        self.temporary_directory.cleanup()

    def dispatch(
        self,
        *,
        condition: ComparisonCondition,
        action_name: str,
        parameters: dict,
    ):
        goal = self.kernel.create_goal(
            session_id="session:e2",
            description="Verify one real constrained workspace outcome",
            evidence_source=SOURCE,
            condition=condition,
        )
        self.kernel.start_goal(goal.goal_id)
        return self.kernel.dispatch_action(
            goal.goal_id,
            action_name=action_name,
            parameters=parameters,
        )

    def test_real_file_effect_is_observed_signed_and_accepted(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "file_exists",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "evidence.txt", "content": "Darwin v50\n"},
        )
        target = self.workspace / "evidence.txt"
        self.assertFalse(target.exists())

        request = self.kernel.pending_action(goal.goal_id)
        envelope = self.executor.execute(request)

        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"), "Darwin v50\n")
        self.assertTrue(envelope.metrics["operation_succeeded"])
        result = self.kernel.record_attested_observation(envelope)

        self.assertTrue(result.accepted)
        self.assertTrue(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        observation = self.kernel.store.get_event(result.observation_event_id)
        decision = self.kernel.store.get_event(result.decision_event_id)
        self.assertIs(observation.payload["authenticated"], True)
        self.assertIs(decision.payload["evidence_authenticated"], True)

    def test_registered_source_rejects_unsigned_observation(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "file_exists",
                ComparisonOperator.EQUAL,
                False,
            ),
            action_name=INSPECT_FILE,
            parameters={"path": "missing.txt"},
        )

        rejected = self.kernel.record_observation(
            goal.goal_id,
            action_id=goal.expected_action_id or "",
            source=SOURCE,
            metrics={"file_exists": False},
        )

        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reason, "authentication_required")
        self.assertEqual(rejected.goal.status, GoalStatus.WAITING_OBSERVATION)

        valid = self.executor.execute(self.kernel.pending_action(goal.goal_id))
        accepted = self.kernel.record_attested_observation(valid)
        self.assertEqual(accepted.goal.status, GoalStatus.SUCCEEDED)

    def test_forged_signature_is_rejected(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "file_exists",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "signed.txt", "content": "real effect"},
        )
        valid = self.executor.execute(self.kernel.pending_action(goal.goal_id))
        forged = replace(valid, signature="0" * 64)

        rejected = self.kernel.record_attested_observation(forged)

        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reason, "signature_invalid")
        self.assertEqual(rejected.goal.status, GoalStatus.WAITING_OBSERVATION)
        accepted = self.kernel.record_attested_observation(valid)
        self.assertEqual(accepted.goal.status, GoalStatus.SUCCEEDED)

    def test_valid_attestation_cannot_be_replayed(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "size_bytes",
                ComparisonOperator.GREATER_THAN_OR_EQUAL,
                100,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "small.txt", "content": "small"},
        )
        envelope = self.executor.execute(self.kernel.pending_action(goal.goal_id))

        first = self.kernel.record_attested_observation(envelope)
        replay = self.kernel.record_attested_observation(envelope)

        self.assertTrue(first.accepted)
        self.assertFalse(first.condition_satisfied)
        self.assertFalse(replay.accepted)
        self.assertEqual(replay.reason, "attestation_replay")
        self.assertEqual(replay.goal.status, GoalStatus.WAITING_OBSERVATION)

    def test_signed_response_for_different_action_digest_is_rejected(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=INSPECT_FILE,
            parameters={"path": "expected.txt"},
        )
        expected = self.kernel.pending_action(goal.goal_id)
        altered_parameters = {"path": "different.txt"}
        altered = ActionRequest(
            session_id=expected.session_id,
            goal_id=expected.goal_id,
            action_id=expected.action_id,
            action_name=expected.action_name,
            parameters=altered_parameters,
            action_digest=compute_action_digest(
                expected.action_name,
                altered_parameters,
            ),
        )
        envelope = self.signer.attest(
            altered,
            {"operation_succeeded": True},
        )

        rejected = self.kernel.record_attested_observation(envelope)

        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reason, "attestation_correlation_mismatch")
        self.assertEqual(rejected.goal.status, GoalStatus.WAITING_OBSERVATION)

    def test_path_escape_is_observed_as_failure_and_cannot_complete(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "../escape.txt", "content": "forbidden"},
        )
        outside = self.root / "escape.txt"

        envelope = self.executor.execute(self.kernel.pending_action(goal.goal_id))
        result = self.kernel.record_attested_observation(envelope)

        self.assertFalse(outside.exists())
        self.assertFalse(envelope.metrics["operation_succeeded"])
        self.assertEqual(envelope.metrics["error_code"], "path_outside_root")
        self.assertTrue(result.accepted)
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)

    def test_existing_file_is_never_overwritten(self) -> None:
        target = self.workspace / "existing.txt"
        target.write_text("original", encoding="utf-8")
        goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "existing.txt", "content": "replacement"},
        )

        envelope = self.executor.execute(self.kernel.pending_action(goal.goal_id))
        result = self.kernel.record_attested_observation(envelope)

        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        self.assertEqual(envelope.metrics["error_code"], "overwrite_forbidden")
        self.assertFalse(result.condition_satisfied)

    def test_windows_reserved_name_and_alternate_stream_are_rejected(self) -> None:
        for index, unsafe_path in enumerate(("NUL", "safe.txt:stream")):
            with self.subTest(path=unsafe_path):
                goal = self.dispatch(
                    condition=ComparisonCondition(
                        "operation_succeeded",
                        ComparisonOperator.EQUAL,
                        True,
                    ),
                    action_name=CREATE_TEXT_FILE,
                    parameters={"path": unsafe_path, "content": "forbidden"},
                )
                envelope = self.executor.execute(
                    self.kernel.pending_action(goal.goal_id)
                )
                result = self.kernel.record_attested_observation(envelope)

                self.assertEqual(envelope.metrics["error_code"], "invalid_path")
                self.assertFalse(result.condition_satisfied, index)

    def test_write_and_inspection_limits_are_enforced(self) -> None:
        constrained = CapabilityWorkspaceExecutor(
            root=self.workspace,
            signer=self.signer,
            max_write_bytes=4,
            max_inspect_bytes=8,
        )
        write_goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "large-write.txt", "content": "12345"},
        )
        write_envelope = constrained.execute(
            self.kernel.pending_action(write_goal.goal_id)
        )
        write_result = self.kernel.record_attested_observation(write_envelope)

        self.assertEqual(write_envelope.metrics["error_code"], "content_too_large")
        self.assertFalse((self.workspace / "large-write.txt").exists())
        self.assertFalse(write_result.condition_satisfied)

        large_file = self.workspace / "large-inspect.txt"
        large_file.write_text("123456789", encoding="utf-8")
        inspect_goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=INSPECT_FILE,
            parameters={"path": "large-inspect.txt"},
        )
        inspect_envelope = constrained.execute(
            self.kernel.pending_action(inspect_goal.goal_id)
        )
        inspect_result = self.kernel.record_attested_observation(inspect_envelope)

        self.assertEqual(inspect_envelope.metrics["error_code"], "file_too_large")
        self.assertFalse(inspect_result.condition_satisfied)

    def test_shell_like_operation_is_not_available(self) -> None:
        goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name="shell.run",
            parameters={"command": "whoami"},
        )

        envelope = self.executor.execute(self.kernel.pending_action(goal.goal_id))
        result = self.kernel.record_attested_observation(envelope)

        self.assertEqual(envelope.metrics["error_code"], "operation_not_allowed")
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)

    def test_stale_attestation_is_rejected(self) -> None:
        now = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)
        stale_signer = HMACObservationSigner(
            source=SOURCE,
            secret=SECRET,
            clock=lambda: now - timedelta(minutes=10),
        )
        verifier = HMACObservationVerifier(
            source=SOURCE,
            secret=SECRET,
            clock=lambda: now,
            max_age=timedelta(minutes=5),
        )
        other_kernel = DarwinKernelV50.open(
            self.root / "stale-test.db",
            evidence_verifiers={SOURCE: verifier},
        )
        try:
            goal = other_kernel.create_goal(
                session_id="session:stale",
                description="Reject stale evidence",
                evidence_source=SOURCE,
                condition=ComparisonCondition(
                    "file_exists",
                    ComparisonOperator.EQUAL,
                    False,
                ),
            )
            other_kernel.start_goal(goal.goal_id)
            goal = other_kernel.dispatch_action(
                goal.goal_id,
                action_name=INSPECT_FILE,
                parameters={"path": "missing.txt"},
            )
            stale_executor = CapabilityWorkspaceExecutor(
                root=self.workspace,
                signer=stale_signer,
            )
            envelope = stale_executor.execute(other_kernel.pending_action(goal.goal_id))

            rejected = other_kernel.record_attested_observation(envelope)

            self.assertFalse(rejected.accepted)
            self.assertEqual(rejected.reason, "attestation_stale")
            self.assertEqual(rejected.goal.status, GoalStatus.WAITING_OBSERVATION)
        finally:
            other_kernel.close()

    def test_symlink_escape_is_rejected_when_platform_allows_symlinks(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        link = self.workspace / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        goal = self.dispatch(
            condition=ComparisonCondition(
                "operation_succeeded",
                ComparisonOperator.EQUAL,
                True,
            ),
            action_name=CREATE_TEXT_FILE,
            parameters={"path": "link/escape.txt", "content": "forbidden"},
        )
        envelope = self.executor.execute(self.kernel.pending_action(goal.goal_id))
        result = self.kernel.record_attested_observation(envelope)

        self.assertFalse((outside / "escape.txt").exists())
        self.assertEqual(envelope.metrics["error_code"], "symlink_forbidden")
        self.assertFalse(result.condition_satisfied)


if __name__ == "__main__":
    unittest.main()
