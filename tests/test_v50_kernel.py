from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from darwin_v50.kernel import DarwinKernelV50
from darwin_v50.models import (
    CausalEvent,
    ComparisonCondition,
    ComparisonOperator,
    GoalStateError,
    GoalStatus,
    StoreCompatibilityError,
    ValidationError,
)
from darwin_v50.store import APPLICATION_ID, SCHEMA_VERSION, SQLiteEventStore


class DarwinV50KernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "darwin-v50.db"
        self.kernel = DarwinKernelV50.open(self.database)

    def tearDown(self) -> None:
        if not self.kernel.store.closed:
            self.kernel.close()
        self.temporary_directory.cleanup()

    def waiting_goal(
        self,
        *,
        session_id: str = "session:test",
        evidence_source: str = "sandbox.oracle",
        metric: str = "absolute_prediction_error",
        operator: ComparisonOperator = ComparisonOperator.LESS_THAN_OR_EQUAL,
        expected: float = 0.12,
    ):
        goal = self.kernel.create_goal(
            session_id=session_id,
            description="Reduce held-out prediction error",
            evidence_source=evidence_source,
            condition=ComparisonCondition(metric, operator, expected),
        )
        goal = self.kernel.start_goal(goal.goal_id)
        return self.kernel.dispatch_action(
            goal.goal_id,
            action_name="evaluate-held-out-transition",
            parameters={"split": "test"},
        )

    def test_false_condition_never_completes_goal(self) -> None:
        goal = self.waiting_goal()

        result = self.kernel.record_observation(
            goal.goal_id,
            action_id=goal.expected_action_id or "",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 1.0},
        )

        self.assertTrue(result.accepted)
        self.assertFalse(result.condition_satisfied)
        self.assertEqual(result.goal.status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=goal.goal_id,
                kind="goal.succeeded",
            ),
            0,
        )

    def test_later_true_observation_completes_exactly_once(self) -> None:
        goal = self.waiting_goal()
        first = self.kernel.record_observation(
            goal.goal_id,
            action_id=goal.expected_action_id or "",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 0.8},
        )

        second = self.kernel.record_observation(
            goal.goal_id,
            action_id=goal.expected_action_id or "",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 0.08},
        )

        self.assertFalse(first.condition_satisfied)
        self.assertTrue(second.condition_satisfied)
        self.assertEqual(second.goal.status, GoalStatus.SUCCEEDED)
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=goal.goal_id,
                kind="goal.succeeded",
            ),
            1,
        )
        with self.assertRaises(GoalStateError):
            self.kernel.record_observation(
                goal.goal_id,
                action_id=goal.expected_action_id or "",
                source="sandbox.oracle",
                metrics={"absolute_prediction_error": 0.01},
            )

    def test_wrong_action_and_source_are_rejected(self) -> None:
        goal = self.waiting_goal()

        wrong_action = self.kernel.record_observation(
            goal.goal_id,
            action_id="action:not-the-dispatched-action",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 0.01},
        )
        wrong_source = self.kernel.record_observation(
            goal.goal_id,
            action_id=goal.expected_action_id or "",
            source="self_report",
            metrics={"absolute_prediction_error": 0.01},
        )

        self.assertFalse(wrong_action.accepted)
        self.assertEqual(wrong_action.reason, "action_mismatch")
        self.assertFalse(wrong_source.accepted)
        self.assertEqual(wrong_source.reason, "evidence_source_mismatch")
        self.assertEqual(self.kernel.get_goal(goal.goal_id).status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=goal.goal_id,
                kind="goal.succeeded",
            ),
            0,
        )

    def test_observation_cannot_cross_between_open_goals(self) -> None:
        goal_a = self.waiting_goal(session_id="session:a")
        goal_b = self.waiting_goal(session_id="session:b")

        rejected = self.kernel.record_observation(
            goal_a.goal_id,
            action_id=goal_b.expected_action_id or "",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 0.01},
        )
        completed_b = self.kernel.record_observation(
            goal_b.goal_id,
            action_id=goal_b.expected_action_id or "",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 0.01},
        )

        self.assertFalse(rejected.accepted)
        self.assertEqual(self.kernel.get_goal(goal_a.goal_id).status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(completed_b.goal.status, GoalStatus.SUCCEEDED)
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=goal_a.goal_id,
                kind="goal.succeeded",
            ),
            0,
        )

    def test_restart_preserves_condition_action_and_version(self) -> None:
        before = self.waiting_goal()
        self.kernel.close()

        reopened = DarwinKernelV50.open(self.database)
        try:
            recovered = reopened.get_goal(before.goal_id)
            self.assertEqual(recovered, before)
            result = reopened.record_observation(
                recovered.goal_id,
                action_id=recovered.expected_action_id or "",
                source=recovered.evidence_source,
                metrics={"absolute_prediction_error": 0.05},
            )
            self.assertEqual(result.goal.status, GoalStatus.SUCCEEDED)
        finally:
            reopened.close()

    def test_success_has_complete_causal_lineage(self) -> None:
        goal = self.waiting_goal()
        self.kernel.record_observation(
            goal.goal_id,
            action_id=goal.expected_action_id or "",
            source="sandbox.oracle",
            metrics={"absolute_prediction_error": 0.05},
        )
        events = self.kernel.goal_events(goal.goal_id)
        by_kind = {event.kind: event for event in events}

        self.assertIsNone(by_kind["goal.created"].parent_event_id)
        self.assertEqual(
            by_kind["goal.started"].parent_event_id,
            by_kind["goal.created"].event_id,
        )
        self.assertEqual(
            by_kind["action.dispatched"].parent_event_id,
            by_kind["goal.started"].event_id,
        )
        self.assertEqual(
            by_kind["observation.recorded"].parent_event_id,
            by_kind["action.dispatched"].event_id,
        )
        self.assertEqual(
            by_kind["goal.succeeded"].parent_event_id,
            by_kind["observation.recorded"].event_id,
        )
        self.assertEqual(
            by_kind["observation.recorded"].action_id,
            by_kind["action.dispatched"].action_id,
        )

    def test_concurrent_observations_produce_at_most_one_success(self) -> None:
        goal = self.waiting_goal()
        second_kernel = DarwinKernelV50.open(self.database)
        barrier = Barrier(2)

        def complete(kernel: DarwinKernelV50) -> str:
            barrier.wait(timeout=5)
            try:
                result = kernel.record_observation(
                    goal.goal_id,
                    action_id=goal.expected_action_id or "",
                    source="sandbox.oracle",
                    metrics={"absolute_prediction_error": 0.02},
                )
                return result.goal.status.value
            except GoalStateError:
                return "state_error"

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(complete, [self.kernel, second_kernel])
                )
            self.assertCountEqual(results, ["succeeded", "state_error"])
            self.assertEqual(
                self.kernel.store.count_events(
                    goal_id=goal.goal_id,
                    kind="goal.succeeded",
                ),
                1,
            )
        finally:
            second_kernel.close()

    def test_cancelled_goal_rejects_late_evidence(self) -> None:
        goal = self.waiting_goal()
        cancelled = self.kernel.cancel_goal(
            goal.goal_id,
            reason="user withdrew authorization",
        )
        self.assertEqual(cancelled.status, GoalStatus.CANCELLED)

        with self.assertRaises(GoalStateError):
            self.kernel.record_observation(
                goal.goal_id,
                action_id=goal.expected_action_id or "",
                source="sandbox.oracle",
                metrics={"absolute_prediction_error": 0.01},
            )
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=goal.goal_id,
                kind="goal.succeeded",
            ),
            0,
        )

    def test_non_json_numbers_are_rejected_without_state_change(self) -> None:
        goal = self.kernel.create_goal(
            session_id="session:strict-json",
            description="Reject ambiguous numeric evidence",
            evidence_source="sandbox.oracle",
            condition=ComparisonCondition(
                "score",
                ComparisonOperator.GREATER_THAN,
                0.5,
            ),
        )
        goal = self.kernel.start_goal(goal.goal_id)

        with self.assertRaises(ValidationError):
            self.kernel.dispatch_action(
                goal.goal_id,
                action_name="bad-parameters",
                parameters={"invalid": math.nan},
            )
        self.assertEqual(self.kernel.get_goal(goal.goal_id).status, GoalStatus.ACTIVE)

        with self.assertRaises(ValidationError):
            self.kernel.dispatch_action(
                goal.goal_id,
                action_name="bad-object-key",
                parameters={"nested": {1: "not a JSON object key"}},  # type: ignore[dict-item]
            )
        self.assertEqual(self.kernel.get_goal(goal.goal_id).status, GoalStatus.ACTIVE)

    def test_store_rejects_a_fabricated_success_event(self) -> None:
        goal = self.waiting_goal()
        fabricated = CausalEvent.create(
            session_id=goal.session_id,
            kind="goal.succeeded",
            goal_id=goal.goal_id,
            action_id=goal.expected_action_id,
            observation_id="observation:fabricated",
            parent_event_id=goal.expected_action_event_id,
            payload={"satisfied": True},
        )

        with self.assertRaises(ValidationError):
            self.kernel.store.append_event(fabricated)
        self.assertEqual(self.kernel.get_goal(goal.goal_id).status, GoalStatus.WAITING_OBSERVATION)
        self.assertEqual(
            self.kernel.store.count_events(
                goal_id=goal.goal_id,
                kind="goal.succeeded",
            ),
            0,
        )

    def test_events_are_immutable_and_parents_cannot_cross_sessions(self) -> None:
        first = CausalEvent.create(
            session_id="session:one",
            kind="test.root",
            payload={},
        )
        self.kernel.store.append_event(first)

        with self.assertRaises(ValidationError):
            self.kernel.store.append_event(first)

        cross_session = CausalEvent.create(
            session_id="session:two",
            kind="test.child",
            parent_event_id=first.event_id,
            payload={},
        )
        with self.assertRaises(ValidationError):
            self.kernel.store.append_event(cross_session)

    def test_schema_identity_and_foreign_keys_are_enabled(self) -> None:
        self.assertEqual(
            self.kernel.store.schema_metadata(),
            {
                "application_id": APPLICATION_ID,
                "user_version": SCHEMA_VERSION,
                "foreign_keys": 1,
            },
        )


class DarwinV50CompatibilityTests(unittest.TestCase):
    def test_schema_v2_with_unbound_consent_is_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "schema-v2-unbound.db"
            SQLiteEventStore(database).close()
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                PRAGMA foreign_keys = OFF;
                INSERT INTO consent_requests (
                    consent_id,
                    adapter_source,
                    session_id,
                    goal_id,
                    action_id,
                    action_digest,
                    resource_scope,
                    risk,
                    created_at,
                    expires_at,
                    request_digest,
                    request_json,
                    requested_event_id
                )
                VALUES (
                    'consent:legacy',
                    'legacy.source',
                    'session:legacy',
                    'goal:legacy',
                    'action:legacy',
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'workspace:legacy',
                    'low',
                    '2026-07-27T20:00:00+00:00',
                    '2026-07-27T20:05:00+00:00',
                    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                    '{}',
                    'event:legacy'
                );
                PRAGMA user_version = 2;
                """
            )
            connection.close()

            with self.assertRaises(StoreCompatibilityError) as captured:
                SQLiteEventStore(database)

            self.assertIn(
                "without a bound authority fingerprint",
                str(captured.exception),
            )

    def test_schema_v1_is_migrated_explicitly_to_consent_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "schema-v1.db"
            SQLiteEventStore(database).close()
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                PRAGMA foreign_keys = OFF;
                ALTER TABLE capability_grants RENAME TO capability_grants_v2;
                DROP INDEX ux_capability_grants_action;
                CREATE TABLE capability_grants (
                    grant_id TEXT PRIMARY KEY,
                    issuer TEXT NOT NULL,
                    adapter_source TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    goal_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    action_digest TEXT NOT NULL,
                    resource_scope TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    grant_json TEXT NOT NULL,
                    registered_event_id TEXT NOT NULL UNIQUE,
                    consumed_event_id TEXT NULL UNIQUE,
                    consumed_at TEXT NULL,
                    FOREIGN KEY (goal_id) REFERENCES goals(goal_id),
                    FOREIGN KEY (registered_event_id) REFERENCES events(event_id),
                    FOREIGN KEY (consumed_event_id) REFERENCES events(event_id)
                );
                CREATE UNIQUE INDEX ux_capability_grants_action
                    ON capability_grants(goal_id, action_id);
                DROP TABLE capability_grants_v2;
                DROP TABLE consent_receipts;
                DROP TABLE consent_requests;
                PRAGMA user_version = 1;
                """
            )
            connection.close()

            migrated = SQLiteEventStore(database)
            try:
                self.assertEqual(
                    migrated.schema_metadata()["user_version"],
                    SCHEMA_VERSION,
                )
                columns = {
                    str(row[1])
                    for row in migrated._connection.execute(
                        "PRAGMA table_info(capability_grants)"
                    )
                }
                self.assertIn("consent_id", columns)
            finally:
                migrated.close()

    def test_populated_unidentified_database_is_not_migrated_implicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE legacy_memory (value TEXT)")
            connection.commit()
            connection.close()

            with self.assertRaises(StoreCompatibilityError):
                SQLiteEventStore(database)


if __name__ == "__main__":
    unittest.main()
