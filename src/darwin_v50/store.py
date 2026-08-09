"""Versioned SQLite event store for Darwin v50.

The v50 application id is intentionally different from the unversioned v49
database.  Opening a populated, unidentified SQLite database is refused rather
than guessed.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Iterator

from .capabilities import CapabilityError, CapabilityGrant
from .consent import ConsentError, ConsentReceipt, ConsentRequest
from .evidence import ActionRequest
from .models import (
    CausalEvent,
    ComparisonCondition,
    ConcurrentUpdateError,
    Goal,
    GoalNotFoundError,
    GoalStatus,
    StoreCompatibilityError,
    ValidationError,
    canonical_json,
    parse_json,
    require_text,
)


APPLICATION_ID = 0x4452574E  # ASCII "DRWN"
SCHEMA_VERSION = 3
REQUIRED_TABLES = frozenset(
    {
        "events",
        "goals",
        "evidence_nonces",
        "consent_requests",
        "consent_receipts",
        "capability_grants",
    }
)


SCHEMA_SQL = f"""
BEGIN IMMEDIATE;

CREATE TABLE events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    parent_event_id TEXT NULL,
    goal_id TEXT NULL,
    action_id TEXT NULL,
    observation_id TEXT NULL,
    payload_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    FOREIGN KEY (parent_event_id) REFERENCES events(event_id)
);

CREATE INDEX ix_events_session_sequence
    ON events(session_id, sequence);
CREATE INDEX ix_events_goal_sequence
    ON events(goal_id, sequence);
CREATE INDEX ix_events_action
    ON events(action_id);
CREATE INDEX ix_events_observation
    ON events(observation_id);
CREATE UNIQUE INDEX ux_events_action_dispatch
    ON events(action_id)
    WHERE kind = 'action.dispatched';
CREATE UNIQUE INDEX ux_events_observation_recorded
    ON events(observation_id)
    WHERE kind = 'observation.recorded';
CREATE UNIQUE INDEX ux_events_goal_succeeded
    ON events(goal_id)
    WHERE kind = 'goal.succeeded';

CREATE TABLE goals (
    goal_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence_source TEXT NOT NULL,
    condition_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'planned',
            'active',
            'waiting_observation',
            'succeeded',
            'cancelled'
        )
    ),
    created_event_id TEXT NOT NULL,
    last_event_id TEXT NOT NULL,
    expected_action_id TEXT NULL,
    expected_action_event_id TEXT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    CHECK (
        (expected_action_id IS NULL AND expected_action_event_id IS NULL)
        OR
        (expected_action_id IS NOT NULL AND expected_action_event_id IS NOT NULL)
    ),
    FOREIGN KEY (created_event_id) REFERENCES events(event_id),
    FOREIGN KEY (last_event_id) REFERENCES events(event_id),
    FOREIGN KEY (expected_action_event_id) REFERENCES events(event_id)
);

CREATE INDEX ix_goals_session_status
    ON goals(session_id, status);

CREATE TABLE evidence_nonces (
    source TEXT NOT NULL,
    nonce TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    observation_event_id TEXT NOT NULL UNIQUE,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (source, nonce),
    FOREIGN KEY (goal_id) REFERENCES goals(goal_id),
    FOREIGN KEY (observation_event_id) REFERENCES events(event_id)
);

CREATE TABLE consent_requests (
    consent_id TEXT PRIMARY KEY,
    adapter_source TEXT NOT NULL,
    session_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_digest TEXT NOT NULL,
    resource_scope TEXT NOT NULL,
    risk TEXT NOT NULL CHECK (risk IN ('low', 'medium', 'high', 'critical')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    request_digest TEXT NOT NULL UNIQUE,
    request_json TEXT NOT NULL,
    requested_event_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (goal_id) REFERENCES goals(goal_id),
    FOREIGN KEY (requested_event_id) REFERENCES events(event_id),
    UNIQUE (goal_id, action_id)
);

CREATE TABLE consent_receipts (
    receipt_id TEXT PRIMARY KEY,
    consent_id TEXT NOT NULL UNIQUE,
    issuer TEXT NOT NULL,
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    channel TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    receipt_digest TEXT NOT NULL UNIQUE,
    receipt_json TEXT NOT NULL,
    decision_event_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (consent_id) REFERENCES consent_requests(consent_id),
    FOREIGN KEY (decision_event_id) REFERENCES events(event_id)
);

CREATE TABLE capability_grants (
    grant_id TEXT PRIMARY KEY,
    issuer TEXT NOT NULL,
    adapter_source TEXT NOT NULL,
    session_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_digest TEXT NOT NULL,
    resource_scope TEXT NOT NULL,
    consent_id TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    grant_json TEXT NOT NULL,
    registered_event_id TEXT NOT NULL UNIQUE,
    consumed_event_id TEXT NULL UNIQUE,
    consumed_at TEXT NULL,
    FOREIGN KEY (goal_id) REFERENCES goals(goal_id),
    FOREIGN KEY (consent_id) REFERENCES consent_requests(consent_id),
    FOREIGN KEY (registered_event_id) REFERENCES events(event_id),
    FOREIGN KEY (consumed_event_id) REFERENCES events(event_id)
);

CREATE UNIQUE INDEX ux_capability_grants_action
    ON capability_grants(goal_id, action_id);

PRAGMA application_id = {APPLICATION_ID};
PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""


MIGRATION_1_TO_2_SQL = """
BEGIN IMMEDIATE;

CREATE TABLE consent_requests (
    consent_id TEXT PRIMARY KEY,
    adapter_source TEXT NOT NULL,
    session_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_digest TEXT NOT NULL,
    resource_scope TEXT NOT NULL,
    risk TEXT NOT NULL CHECK (risk IN ('low', 'medium', 'high', 'critical')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    request_digest TEXT NOT NULL UNIQUE,
    request_json TEXT NOT NULL,
    requested_event_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (goal_id) REFERENCES goals(goal_id),
    FOREIGN KEY (requested_event_id) REFERENCES events(event_id),
    UNIQUE (goal_id, action_id)
);

CREATE TABLE consent_receipts (
    receipt_id TEXT PRIMARY KEY,
    consent_id TEXT NOT NULL UNIQUE,
    issuer TEXT NOT NULL,
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    channel TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    receipt_digest TEXT NOT NULL UNIQUE,
    receipt_json TEXT NOT NULL,
    decision_event_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (consent_id) REFERENCES consent_requests(consent_id),
    FOREIGN KEY (decision_event_id) REFERENCES events(event_id)
);

ALTER TABLE capability_grants ADD COLUMN consent_id TEXT NULL;
CREATE UNIQUE INDEX ux_capability_grants_consent
    ON capability_grants(consent_id)
    WHERE consent_id IS NOT NULL;

PRAGMA user_version = 2;
COMMIT;
"""


MIGRATION_2_TO_3_SQL = """
BEGIN IMMEDIATE;
PRAGMA user_version = 3;
COMMIT;
"""


class SQLiteEventStore:
    """Own one SQLite connection and expose explicit atomic operations."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            self.database,
            timeout=12.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 12000")
        if self.database != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def _initialize(self) -> None:
        application_id = int(
            self._connection.execute("PRAGMA application_id").fetchone()[0]
        )
        user_version = int(
            self._connection.execute("PRAGMA user_version").fetchone()[0]
        )
        tables = {
            str(row["name"])
            for row in self._connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }

        if application_id not in {0, APPLICATION_ID}:
            self.close()
            raise StoreCompatibilityError(
                f"database application_id={application_id} is not Darwin v50"
            )

        if application_id == 0:
            if tables:
                self.close()
                raise StoreCompatibilityError(
                    "populated database has no Darwin v50 application id; "
                    "implicit legacy migration is forbidden"
                )
            try:
                self._connection.executescript(SCHEMA_SQL)
            except sqlite3.Error:
                self.close()
                raise
            return

        if user_version == 1:
            try:
                self._connection.executescript(MIGRATION_1_TO_2_SQL)
            except sqlite3.Error:
                self.close()
                raise
            user_version = 2
            tables = {
                str(row["name"])
                for row in self._connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }

        if user_version == 2:
            unbound_requests = int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM consent_requests"
                ).fetchone()[0]
            )
            if unbound_requests:
                self.close()
                raise StoreCompatibilityError(
                    "schema 2 contains consent requests without a bound "
                    "authority fingerprint; implicit migration is forbidden"
                )
            try:
                self._connection.executescript(MIGRATION_2_TO_3_SQL)
            except sqlite3.Error:
                self.close()
                raise
            user_version = 3

        if user_version != SCHEMA_VERSION:
            self.close()
            raise StoreCompatibilityError(
                f"unsupported Darwin v50 schema version: {user_version}"
            )
        if not REQUIRED_TABLES.issubset(tables):
            self.close()
            missing = ", ".join(sorted(REQUIRED_TABLES - tables))
            raise StoreCompatibilityError(f"Darwin v50 database is missing: {missing}")

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> "SQLiteEventStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("event store is closed")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Start an immediate transaction, serializing competing writers."""

        with self._lock:
            self._ensure_open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    def append_event(
        self,
        event: CausalEvent,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> CausalEvent:
        if connection is None:
            with self.transaction() as transaction:
                return self.append_event(event, connection=transaction)

        parent: sqlite3.Row | None = None
        if event.parent_event_id is not None:
            parent = connection.execute(
                """
                SELECT
                    session_id,
                    kind,
                    goal_id,
                    action_id,
                    observation_id,
                    payload_json
                FROM events
                WHERE event_id = ?
                """,
                (event.parent_event_id,),
            ).fetchone()
            if parent is None:
                raise ValidationError(
                    f"parent event does not exist: {event.parent_event_id}"
                )
            if str(parent["session_id"]) != event.session_id:
                raise ValidationError("parent event belongs to another session")

        self._validate_event_semantics(event, parent, connection)

        try:
            cursor = connection.execute(
                """
                INSERT INTO events (
                    event_id,
                    session_id,
                    kind,
                    occurred_at,
                    parent_event_id,
                    goal_id,
                    action_id,
                    observation_id,
                    payload_json,
                    schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.kind,
                    event.occurred_at.isoformat(),
                    event.parent_event_id,
                    event.goal_id,
                    event.action_id,
                    event.observation_id,
                    canonical_json(dict(event.payload)),
                    event.schema_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"event violates store invariants: {exc}") from exc
        return replace(event, sequence=int(cursor.lastrowid))

    @staticmethod
    def _validate_event_semantics(
        event: CausalEvent,
        parent: sqlite3.Row | None,
        connection: sqlite3.Connection,
    ) -> None:
        """Defend goal transitions even when callers bypass the kernel."""

        goal_row = None
        if event.goal_id is not None:
            goal_row = connection.execute(
                """
                SELECT
                    session_id,
                    status,
                    last_event_id,
                    expected_action_id,
                    expected_action_event_id
                FROM goals
                WHERE goal_id = ?
                """,
                (event.goal_id,),
            ).fetchone()
            if goal_row is None and event.kind != "goal.created":
                raise ValidationError("event references an unknown goal")
            if (
                goal_row is not None
                and str(goal_row["session_id"]) != event.session_id
            ):
                raise ValidationError("event goal belongs to another session")

        if event.kind == "goal.created":
            if event.goal_id is None or event.parent_event_id is not None:
                raise ValidationError("goal.created must be a goal root event")
            if goal_row is not None:
                raise ValidationError("goal already exists")
            return

        known_goal_events = {
            "goal.started",
            "goal.continued",
            "action.dispatched",
            "observation.rejected",
            "observation.recorded",
            "goal.condition_unsatisfied",
            "goal.succeeded",
            "goal.cancelled",
        }
        if event.kind not in known_goal_events:
            return
        if event.goal_id is None or goal_row is None:
            raise ValidationError(f"{event.kind} requires an existing goal")

        status = str(goal_row["status"])
        last_event_id = str(goal_row["last_event_id"])
        expected_action_id = (
            str(goal_row["expected_action_id"])
            if goal_row["expected_action_id"] is not None
            else None
        )
        expected_action_event_id = (
            str(goal_row["expected_action_event_id"])
            if goal_row["expected_action_event_id"] is not None
            else None
        )

        if event.kind == "goal.started":
            if status != GoalStatus.PLANNED.value:
                raise ValidationError("goal.started requires a planned goal")
            if event.parent_event_id != last_event_id:
                raise ValidationError("goal.started must follow the latest goal event")
            return

        if event.kind == "action.dispatched":
            if status != GoalStatus.ACTIVE.value:
                raise ValidationError("action.dispatched requires an active goal")
            if event.parent_event_id != last_event_id or event.action_id is None:
                raise ValidationError("action dispatch is not correlated to the active goal")
            return

        if event.kind == "goal.cancelled":
            if status in {GoalStatus.SUCCEEDED.value, GoalStatus.CANCELLED.value}:
                raise ValidationError("terminal goal cannot be cancelled")
            if event.parent_event_id != last_event_id:
                raise ValidationError("goal.cancelled must follow the latest goal event")
            return

        if status != GoalStatus.WAITING_OBSERVATION.value:
            raise ValidationError(f"{event.kind} requires a waiting goal")

        if event.kind == "observation.rejected":
            if event.parent_event_id != last_event_id or event.observation_id is None:
                raise ValidationError("rejected observation lacks goal correlation")
            return

        if event.kind == "observation.recorded":
            if (
                event.action_id != expected_action_id
                or event.parent_event_id != expected_action_event_id
                or event.observation_id is None
            ):
                raise ValidationError(
                    "recorded observation does not match the dispatched action"
                )
            if parent is None or str(parent["kind"]) != "action.dispatched":
                raise ValidationError(
                    "recorded observation parent is not an action dispatch"
                )
            return

        if event.kind == "goal.continued":
            if event.parent_event_id != last_event_id:
                raise ValidationError(
                    "goal.continued must follow the latest goal event"
                )
            if (
                parent is None
                or str(parent["kind"]) != "goal.condition_unsatisfied"
            ):
                raise ValidationError(
                    "goal.continued requires an unsatisfied decision"
                )
            if event.action_id != expected_action_id:
                raise ValidationError(
                    "goal.continued does not match the completed action"
                )
            return

        if parent is None or str(parent["kind"]) != "observation.recorded":
            raise ValidationError("goal decision parent is not a recorded observation")
        if (
            event.action_id != str(parent["action_id"])
            or event.observation_id != str(parent["observation_id"])
            or event.goal_id != str(parent["goal_id"])
        ):
            raise ValidationError("goal decision does not match its observation")

        satisfied = event.payload.get("satisfied")
        if event.kind == "goal.succeeded" and satisfied is not True:
            raise ValidationError("goal.succeeded requires satisfied=true")
        if event.kind == "goal.condition_unsatisfied" and satisfied is not False:
            raise ValidationError(
                "goal.condition_unsatisfied requires satisfied=false"
            )

    def insert_goal(
        self,
        goal: Goal,
        *,
        connection: sqlite3.Connection,
    ) -> None:
        root = connection.execute(
            """
            SELECT session_id, kind, goal_id
            FROM events
            WHERE event_id = ?
            """,
            (goal.created_event_id,),
        ).fetchone()
        if root is None:
            raise ValidationError("goal root event does not exist")
        if (
            str(root["session_id"]) != goal.session_id
            or str(root["kind"]) != "goal.created"
            or str(root["goal_id"]) != goal.goal_id
        ):
            raise ValidationError("goal root event does not match the goal")

        try:
            connection.execute(
                """
                INSERT INTO goals (
                    goal_id,
                    session_id,
                    description,
                    evidence_source,
                    condition_json,
                    status,
                    created_event_id,
                    last_event_id,
                    expected_action_id,
                    expected_action_event_id,
                    version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal.goal_id,
                    goal.session_id,
                    goal.description,
                    goal.evidence_source,
                    canonical_json(goal.condition.to_dict()),
                    goal.status.value,
                    goal.created_event_id,
                    goal.last_event_id,
                    goal.expected_action_id,
                    goal.expected_action_event_id,
                    goal.version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"goal violates store invariants: {exc}") from exc

    def update_goal(
        self,
        goal: Goal,
        *,
        expected_version: int,
        connection: sqlite3.Connection,
    ) -> Goal:
        next_version = expected_version + 1
        cursor = connection.execute(
            """
            UPDATE goals
            SET
                status = ?,
                last_event_id = ?,
                expected_action_id = ?,
                expected_action_event_id = ?,
                version = ?
            WHERE goal_id = ? AND version = ?
            """,
            (
                goal.status.value,
                goal.last_event_id,
                goal.expected_action_id,
                goal.expected_action_event_id,
                next_version,
                goal.goal_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ConcurrentUpdateError(
                f"goal {goal.goal_id} changed after version {expected_version}"
            )
        return replace(goal, version=next_version)

    def get_goal(
        self,
        goal_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Goal:
        self._ensure_open()
        if connection is None:
            with self._lock:
                row = self._connection.execute(
                    "SELECT * FROM goals WHERE goal_id = ?",
                    (goal_id,),
                ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM goals WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()
        if row is None:
            raise GoalNotFoundError(goal_id)
        return self._row_to_goal(row)

    def get_event(
        self,
        event_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> CausalEvent:
        self._ensure_open()
        if connection is None:
            with self._lock:
                row = self._connection.execute(
                    "SELECT * FROM events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            raise LookupError(event_id)
        return self._row_to_event(row)

    def evidence_nonce_claimed(
        self,
        *,
        source: str,
        nonce: str,
        connection: sqlite3.Connection,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM evidence_nonces
            WHERE source = ? AND nonce = ?
            """,
            (source, nonce),
        ).fetchone()
        return row is not None

    def claim_evidence_nonce(
        self,
        *,
        source: str,
        nonce: str,
        goal_id: str,
        action_id: str,
        observation_event_id: str,
        claimed_at: datetime,
        connection: sqlite3.Connection,
    ) -> None:
        try:
            connection.execute(
                """
                INSERT INTO evidence_nonces (
                    source,
                    nonce,
                    goal_id,
                    action_id,
                    observation_event_id,
                    claimed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    nonce,
                    goal_id,
                    action_id,
                    observation_event_id,
                    claimed_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                f"evidence nonce violates replay invariants: {exc}"
            ) from exc

    def insert_consent_request(
        self,
        request: ConsentRequest,
        *,
        requested_event_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        event = connection.execute(
            """
            SELECT
                session_id,
                goal_id,
                action_id,
                kind,
                parent_event_id,
                payload_json
            FROM events
            WHERE event_id = ?
            """,
            (requested_event_id,),
        ).fetchone()
        if event is None or str(event["kind"]) != "consent.requested":
            raise ConsentError("consent_request_event_missing")
        if (
            str(event["session_id"]) != request.session_id
            or str(event["goal_id"]) != request.goal_id
            or str(event["action_id"]) != request.action_id
        ):
            raise ConsentError("consent_request_event_mismatch")
        action_event = connection.execute(
            """
            SELECT event_id
            FROM events
            WHERE action_id = ? AND kind = 'action.dispatched'
            """,
            (request.action_id,),
        ).fetchone()
        if (
            action_event is None
            or str(event["parent_event_id"]) != str(action_event["event_id"])
        ):
            raise ConsentError("consent_request_parent_mismatch")
        event_payload = parse_json(str(event["payload_json"]))
        if (
            not isinstance(event_payload, dict)
            or event_payload.get("consent_id") != request.consent_id
            or event_payload.get("request_digest") != request.request_digest
            or event_payload.get("authority_issuer")
            != request.authority_issuer
            or event_payload.get("authority_scheme")
            != request.authority_scheme
            or event_payload.get("authority_fingerprint")
            != request.authority_fingerprint
            or event_payload.get("action_digest") != request.action_digest
            or event_payload.get("resource_scope") != request.resource_scope
        ):
            raise ConsentError("consent_request_event_payload_mismatch")
        try:
            connection.execute(
                """
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.consent_id,
                    request.adapter_source,
                    request.session_id,
                    request.goal_id,
                    request.action_id,
                    request.action_digest,
                    request.resource_scope,
                    request.risk.value,
                    request.created_at.isoformat(),
                    request.expires_at.isoformat(),
                    request.request_digest,
                    canonical_json(request.to_dict()),
                    requested_event_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ConsentError("consent_request_already_exists") from exc

    def get_consent_request(
        self,
        consent_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ConsentRequest:
        self._ensure_open()
        if connection is None:
            with self._lock:
                row = self._connection.execute(
                    """
                    SELECT request_json
                    FROM consent_requests
                    WHERE consent_id = ?
                    """,
                    (consent_id,),
                ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT request_json
                FROM consent_requests
                WHERE consent_id = ?
                """,
                (consent_id,),
            ).fetchone()
        if row is None:
            raise ConsentError("consent_request_not_registered")
        payload = parse_json(str(row["request_json"]))
        if not isinstance(payload, dict):
            raise ConsentError("consent_request_corrupt")
        return ConsentRequest.from_dict(payload)

    def consent_event_id(
        self,
        consent_id: str,
        *,
        decision: bool,
        connection: sqlite3.Connection,
    ) -> str:
        if decision:
            row = connection.execute(
                """
                SELECT decision_event_id AS event_id
                FROM consent_receipts
                WHERE consent_id = ?
                """,
                (consent_id,),
            ).fetchone()
            missing = "consent_decision_not_registered"
        else:
            row = connection.execute(
                """
                SELECT requested_event_id AS event_id
                FROM consent_requests
                WHERE consent_id = ?
                """,
                (consent_id,),
            ).fetchone()
            missing = "consent_request_not_registered"
        if row is None:
            raise ConsentError(missing)
        return str(row["event_id"])

    def register_consent_receipt(
        self,
        request: ConsentRequest,
        receipt: ConsentReceipt,
        *,
        decision_event_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        persisted = connection.execute(
            """
            SELECT request_json, requested_event_id
            FROM consent_requests
            WHERE consent_id = ?
            """,
            (request.consent_id,),
        ).fetchone()
        if (
            persisted is None
            or str(persisted["request_json"]) != canonical_json(request.to_dict())
        ):
            raise ConsentError("consent_request_payload_mismatch")
        event = connection.execute(
            """
            SELECT
                session_id,
                goal_id,
                action_id,
                kind,
                parent_event_id,
                payload_json
            FROM events
            WHERE event_id = ?
            """,
            (decision_event_id,),
        ).fetchone()
        expected_kind = "consent.approved" if receipt.approved else "consent.denied"
        if event is None or str(event["kind"]) != expected_kind:
            raise ConsentError("consent_decision_event_missing")
        if (
            str(event["session_id"]) != request.session_id
            or str(event["goal_id"]) != request.goal_id
            or str(event["action_id"]) != request.action_id
            or str(event["parent_event_id"])
            != str(persisted["requested_event_id"])
        ):
            raise ConsentError("consent_decision_event_mismatch")
        event_payload = parse_json(str(event["payload_json"]))
        if (
            not isinstance(event_payload, dict)
            or event_payload.get("receipt_id") != receipt.receipt_id
            or event_payload.get("consent_id") != receipt.consent_id
            or event_payload.get("request_digest") != receipt.request_digest
            or event_payload.get("receipt_digest") != receipt.receipt_digest
            or event_payload.get("approved") is not receipt.approved
            or event_payload.get("channel") != receipt.channel
        ):
            raise ConsentError("consent_decision_event_payload_mismatch")
        try:
            connection.execute(
                """
                INSERT INTO consent_receipts (
                    receipt_id,
                    consent_id,
                    issuer,
                    approved,
                    channel,
                    decision_reason,
                    decided_at,
                    receipt_digest,
                    receipt_json,
                    decision_event_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_id,
                    receipt.consent_id,
                    receipt.issuer,
                    int(receipt.approved),
                    receipt.channel,
                    receipt.decision_reason,
                    receipt.decided_at.isoformat(),
                    receipt.receipt_digest,
                    canonical_json(receipt.to_dict()),
                    decision_event_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ConsentError("consent_decision_already_registered") from exc

    def register_capability(
        self,
        grant: CapabilityGrant,
        *,
        registered_event_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        event = connection.execute(
            """
            SELECT
                session_id,
                goal_id,
                action_id,
                kind,
                parent_event_id,
                payload_json
            FROM events
            WHERE event_id = ?
            """,
            (registered_event_id,),
        ).fetchone()
        if event is None or str(event["kind"]) != "capability.registered":
            raise CapabilityError("capability_registration_event_missing")
        if (
            str(event["session_id"]) != grant.session_id
            or str(event["goal_id"]) != grant.goal_id
            or str(event["action_id"]) != grant.action_id
        ):
            raise CapabilityError("capability_registration_mismatch")
        event_payload = parse_json(str(event["payload_json"]))
        if (
            not isinstance(event_payload, dict)
            or event_payload.get("grant_id") != grant.grant_id
            or event_payload.get("action_digest") != grant.action_digest
            or event_payload.get("resource_scope") != grant.resource_scope
            or event_payload.get("consent_id") != grant.consent_id
            or event_payload.get("consent_receipt_digest")
            != grant.consent_receipt_digest
        ):
            raise CapabilityError("capability_registration_payload_mismatch")
        consent = connection.execute(
            """
            SELECT
                cr.adapter_source,
                cr.session_id,
                cr.goal_id,
                cr.action_id,
                cr.action_digest,
                cr.resource_scope,
                cr.expires_at,
                cd.approved,
                cd.receipt_digest,
                cd.decision_event_id
            FROM consent_requests AS cr
            JOIN consent_receipts AS cd ON cd.consent_id = cr.consent_id
            WHERE cr.consent_id = ?
            """,
            (grant.consent_id,),
        ).fetchone()
        if consent is None:
            raise CapabilityError("approved_consent_not_registered")
        if int(consent["approved"]) != 1:
            raise CapabilityError("consent_not_approved")
        if (
            str(consent["adapter_source"]) != grant.adapter_source
            or str(consent["session_id"]) != grant.session_id
            or str(consent["goal_id"]) != grant.goal_id
            or str(consent["action_id"]) != grant.action_id
            or str(consent["action_digest"]) != grant.action_digest
            or str(consent["resource_scope"]) != grant.resource_scope
            or str(consent["receipt_digest"]) != grant.consent_receipt_digest
            or datetime.fromisoformat(str(consent["expires_at"])) < grant.expires_at
            or str(event["parent_event_id"])
            != str(consent["decision_event_id"])
        ):
            raise CapabilityError("capability_consent_mismatch")
        try:
            connection.execute(
                """
                INSERT INTO capability_grants (
                    grant_id,
                    issuer,
                    adapter_source,
                    session_id,
                    goal_id,
                    action_id,
                    action_digest,
                    resource_scope,
                    consent_id,
                    expires_at,
                    grant_json,
                    registered_event_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    grant.grant_id,
                    grant.issuer,
                    grant.adapter_source,
                    grant.session_id,
                    grant.goal_id,
                    grant.action_id,
                    grant.action_digest,
                    grant.resource_scope,
                    grant.consent_id,
                    grant.expires_at.isoformat(),
                    canonical_json(grant.to_dict()),
                    registered_event_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise CapabilityError("capability_already_registered") from exc

    def capability_registration_event_id(
        self,
        grant_id: str,
        *,
        connection: sqlite3.Connection,
    ) -> str:
        row = connection.execute(
            """
            SELECT registered_event_id
            FROM capability_grants
            WHERE grant_id = ?
            """,
            (grant_id,),
        ).fetchone()
        if row is None:
            raise CapabilityError("capability_not_registered")
        return str(row["registered_event_id"])

    def consume_capability(
        self,
        grant: CapabilityGrant,
        request: ActionRequest,
        *,
        adapter_source: str,
        resource_scope: str,
        consumed_event: CausalEvent,
        now: datetime,
        connection: sqlite3.Connection,
    ) -> CausalEvent:
        row = connection.execute(
            """
            SELECT *
            FROM capability_grants
            WHERE grant_id = ?
            """,
            (grant.grant_id,),
        ).fetchone()
        if row is None:
            raise CapabilityError("capability_not_registered")
        if str(row["grant_json"]) != canonical_json(grant.to_dict()):
            raise CapabilityError("capability_payload_mismatch")
        if row["consumed_event_id"] is not None:
            raise CapabilityError("capability_already_consumed")
        if datetime.fromisoformat(str(row["expires_at"])) <= now:
            raise CapabilityError("capability_expired")
        if (
            str(row["adapter_source"]) != adapter_source
            or str(row["session_id"]) != request.session_id
            or str(row["goal_id"]) != request.goal_id
            or str(row["action_id"]) != request.action_id
            or str(row["action_digest"]) != request.action_digest
            or str(row["resource_scope"]) != resource_scope
        ):
            raise CapabilityError("capability_correlation_mismatch")
        if (
            consumed_event.kind != "capability.consumed"
            or consumed_event.session_id != request.session_id
            or consumed_event.goal_id != request.goal_id
            or consumed_event.action_id != request.action_id
            or consumed_event.parent_event_id
            != str(row["registered_event_id"])
        ):
            raise CapabilityError("capability_consumption_event_mismatch")

        persisted_event = self.append_event(
            consumed_event,
            connection=connection,
        )
        cursor = connection.execute(
            """
            UPDATE capability_grants
            SET consumed_event_id = ?, consumed_at = ?
            WHERE grant_id = ? AND consumed_event_id IS NULL
            """,
            (
                persisted_event.event_id,
                now.isoformat(),
                grant.grant_id,
            ),
        )
        if cursor.rowcount != 1:
            raise CapabilityError("capability_already_consumed")
        return persisted_event

    def events_for_goal(self, goal_id: str) -> list[CausalEvent]:
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT *
                FROM events
                WHERE goal_id = ?
                ORDER BY sequence
                """,
                (goal_id,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def events_for_session(
        self,
        session_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[CausalEvent]:
        """Return one session stream in committed causal order."""

        session_id = require_text(session_id, "session_id")
        if connection is None:
            with self._lock:
                self._ensure_open()
                rows = self._connection.execute(
                    """
                    SELECT *
                    FROM events
                    WHERE session_id = ?
                    ORDER BY sequence
                    """,
                    (session_id,),
                ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM events
                WHERE session_id = ?
                ORDER BY sequence
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def count_events(self, *, goal_id: str, kind: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM events WHERE goal_id = ?"
        parameters: list[str] = [goal_id]
        if kind is not None:
            query += " AND kind = ?"
            parameters.append(kind)
        with self._lock:
            self._ensure_open()
            return int(self._connection.execute(query, parameters).fetchone()[0])

    def schema_metadata(self) -> dict[str, int]:
        with self._lock:
            self._ensure_open()
            return {
                "application_id": int(
                    self._connection.execute("PRAGMA application_id").fetchone()[0]
                ),
                "user_version": int(
                    self._connection.execute("PRAGMA user_version").fetchone()[0]
                ),
                "foreign_keys": int(
                    self._connection.execute("PRAGMA foreign_keys").fetchone()[0]
                ),
            }

    @staticmethod
    def _row_to_goal(row: sqlite3.Row) -> Goal:
        return Goal(
            goal_id=str(row["goal_id"]),
            session_id=str(row["session_id"]),
            description=str(row["description"]),
            evidence_source=str(row["evidence_source"]),
            condition=ComparisonCondition.from_dict(
                parse_json(str(row["condition_json"]))
            ),
            status=GoalStatus(str(row["status"])),
            created_event_id=str(row["created_event_id"]),
            last_event_id=str(row["last_event_id"]),
            expected_action_id=(
                str(row["expected_action_id"])
                if row["expected_action_id"] is not None
                else None
            ),
            expected_action_event_id=(
                str(row["expected_action_event_id"])
                if row["expected_action_event_id"] is not None
                else None
            ),
            version=int(row["version"]),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> CausalEvent:
        return CausalEvent(
            event_id=str(row["event_id"]),
            session_id=str(row["session_id"]),
            kind=str(row["kind"]),
            occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
            payload=parse_json(str(row["payload_json"])),
            parent_event_id=(
                str(row["parent_event_id"])
                if row["parent_event_id"] is not None
                else None
            ),
            goal_id=str(row["goal_id"]) if row["goal_id"] is not None else None,
            action_id=(
                str(row["action_id"]) if row["action_id"] is not None else None
            ),
            observation_id=(
                str(row["observation_id"])
                if row["observation_id"] is not None
                else None
            ),
            schema_version=int(row["schema_version"]),
            sequence=int(row["sequence"]),
        )
