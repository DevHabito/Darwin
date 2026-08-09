"""Immutable domain models for the Darwin v50 kernel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import math
from typing import Any, Callable, Mapping
from uuid import uuid4


JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


class DarwinV50Error(RuntimeError):
    """Base exception for failures with explicit v50 semantics."""


class ValidationError(DarwinV50Error, ValueError):
    """Raised when an input cannot be represented without ambiguity."""


class GoalNotFoundError(DarwinV50Error, LookupError):
    """Raised when an operation targets an unknown goal."""


class GoalStateError(DarwinV50Error):
    """Raised when a requested transition is invalid for the current state."""


class ConcurrentUpdateError(DarwinV50Error):
    """Raised when optimistic concurrency detects a stale goal version."""


class StoreCompatibilityError(DarwinV50Error):
    """Raised when a database is not an initialized Darwin v50 store."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


def require_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field} must be non-empty")
    return normalized


def canonical_json(value: JSONValue | Mapping[str, JSONValue]) -> str:
    """Serialize strict JSON; NaN and Infinity are rejected."""

    _validate_json_value(value, path="$", containers=set())
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"value is not strict JSON: {exc}") from exc


def _validate_json_value(
    value: object,
    *,
    path: str,
    containers: set[int],
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in containers:
            raise ValidationError(f"{path} contains a circular list")
        containers.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_json_value(
                    item,
                    path=f"{path}[{index}]",
                    containers=containers,
                )
        finally:
            containers.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in containers:
            raise ValidationError(f"{path} contains a circular object")
        containers.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValidationError(f"{path} contains a non-string object key")
                _validate_json_value(
                    item,
                    path=f"{path}.{key}",
                    containers=containers,
                )
        finally:
            containers.remove(identity)
        return
    raise ValidationError(f"{path} contains unsupported type {type(value).__name__}")


def parse_json(raw: str) -> Any:
    return json.loads(raw)


class ComparisonOperator(StrEnum):
    EQUAL = "eq"
    NOT_EQUAL = "ne"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    satisfied: bool
    reason: str
    actual: JSONValue = None


@dataclass(frozen=True, slots=True)
class ComparisonCondition:
    """A deliberately small, auditable stop-condition language.

    The kernel does not execute arbitrary Python callbacks from persisted data.
    A condition compares one named observation metric against one persisted
    target.  Compound conditions can be added through a versioned schema later.
    """

    metric: str
    operator: ComparisonOperator
    expected: JSONValue

    def __post_init__(self) -> None:
        require_text(self.metric, "metric")
        canonical_json(self.expected)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "type": "comparison",
            "metric": self.metric,
            "operator": self.operator.value,
            "expected": self.expected,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ComparisonCondition":
        if value.get("type") != "comparison":
            raise ValidationError("unsupported condition type")
        try:
            operator = ComparisonOperator(str(value["operator"]))
            metric = str(value["metric"])
        except (KeyError, ValueError) as exc:
            raise ValidationError("invalid comparison condition") from exc
        return cls(metric=metric, operator=operator, expected=value.get("expected"))

    def evaluate(self, metrics: Mapping[str, JSONValue]) -> ConditionEvaluation:
        if self.metric not in metrics:
            return ConditionEvaluation(False, "metric_missing")

        actual = metrics[self.metric]
        if self.operator is ComparisonOperator.EQUAL:
            return ConditionEvaluation(actual == self.expected, "comparison_evaluated", actual)
        if self.operator is ComparisonOperator.NOT_EQUAL:
            return ConditionEvaluation(actual != self.expected, "comparison_evaluated", actual)

        if not (_is_finite_number(actual) and _is_finite_number(self.expected)):
            return ConditionEvaluation(False, "numeric_metric_required", actual)

        actual_number = float(actual)
        expected_number = float(self.expected)
        operations = {
            ComparisonOperator.LESS_THAN: actual_number < expected_number,
            ComparisonOperator.LESS_THAN_OR_EQUAL: actual_number <= expected_number,
            ComparisonOperator.GREATER_THAN: actual_number > expected_number,
            ComparisonOperator.GREATER_THAN_OR_EQUAL: actual_number >= expected_number,
        }
        return ConditionEvaluation(operations[self.operator], "comparison_evaluated", actual)


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


class GoalStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    WAITING_OBSERVATION = "waiting_observation"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {GoalStatus.SUCCEEDED, GoalStatus.CANCELLED}


@dataclass(frozen=True, slots=True)
class CausalEvent:
    event_id: str
    session_id: str
    kind: str
    occurred_at: datetime
    payload: Mapping[str, JSONValue]
    parent_event_id: str | None = None
    goal_id: str | None = None
    action_id: str | None = None
    observation_id: str | None = None
    schema_version: int = 1
    sequence: int | None = None

    def __post_init__(self) -> None:
        require_text(self.event_id, "event_id")
        require_text(self.session_id, "session_id")
        require_text(self.kind, "kind")
        if self.occurred_at.tzinfo is None:
            raise ValidationError("occurred_at must be timezone-aware")
        if self.schema_version != 1:
            raise ValidationError("unsupported event schema_version")
        canonical_json(dict(self.payload))

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        kind: str,
        payload: Mapping[str, JSONValue],
        parent_event_id: str | None = None,
        goal_id: str | None = None,
        action_id: str | None = None,
        observation_id: str | None = None,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ) -> "CausalEvent":
        return cls(
            event_id=id_factory(),
            session_id=session_id,
            kind=kind,
            occurred_at=clock(),
            payload=dict(payload),
            parent_event_id=parent_event_id,
            goal_id=goal_id,
            action_id=action_id,
            observation_id=observation_id,
        )


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    session_id: str
    description: str
    evidence_source: str
    condition: ComparisonCondition
    status: GoalStatus
    created_event_id: str
    last_event_id: str
    expected_action_id: str | None = None
    expected_action_event_id: str | None = None
    version: int = 0


@dataclass(frozen=True, slots=True)
class ObservationResult:
    goal: Goal
    accepted: bool
    condition_satisfied: bool
    reason: str
    observation_event_id: str
    decision_event_id: str
