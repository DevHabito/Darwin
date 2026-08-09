"""Headless desktop lifecycle boundary for the Darwin v50 kernel.

This module records operational continuity only. It does not model subjective
continuity, choose goals, run external effects, or connect a language model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
import os
from pathlib import Path
from typing import BinaryIO, Mapping

from .kernel import DarwinKernelV50
from .language import (
    DarwinLanguageGateway,
    LanguageMode,
    LanguageObservation,
    UnderstandingRequest,
)
from .models import (
    CausalEvent,
    Clock,
    DarwinV50Error,
    IdFactory,
    JSONValue,
    ValidationError,
    new_id,
    utc_now,
)
from .store import SQLiteEventStore


DESKTOP_RUNTIME_CONTRACT = "darwin-desktop-runtime-v1"
DESKTOP_RUNTIME_STREAM = "desktop-runtime:v1"

_STARTED = "desktop.started"
_ACTIVATED = "desktop.activated"
_SLEPT = "desktop.slept"
_CHECKPOINTED = "desktop.checkpointed"
_STOPPED = "desktop.stopped"
_EVENT_KINDS = frozenset(
    {_STARTED, _ACTIVATED, _SLEPT, _CHECKPOINTED, _STOPPED}
)


class DesktopRuntimeError(DarwinV50Error):
    """A lifecycle request could not be represented honestly."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DesktopRuntimeState(StrEnum):
    NEW = "new"
    SLEEPING = "sleeping"
    ACTIVE = "active"
    CLOSED = "closed"


class ContinuityGapKind(StrEnum):
    FIRST_START = "first_start"
    CLEAN_OFFLINE = "clean_offline"
    UNCLEAN_UNOBSERVED = "unclean_unobserved"


class ActivationSource(StrEnum):
    EXPLICIT_USER = "explicit_user"


class SleepReason(StrEnum):
    EXPLICIT_USER = "explicit_user"


class ShutdownReason(StrEnum):
    EXPLICIT_USER = "explicit_user"
    APPLICATION_EXIT = "application_exit"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass(frozen=True, slots=True)
class ContinuityGap:
    """A measured ledger gap, not a claim about experienced time."""

    kind: ContinuityGapKind
    started_at: datetime | None
    ended_at: datetime
    seconds: float | None


@dataclass(frozen=True, slots=True)
class DesktopSnapshot:
    """Authority-free state intended for a future desktop presentation layer."""

    contract_version: str
    state: DesktopRuntimeState
    boot_id: str
    boot_number: int
    recovered_after_unclean_shutdown: bool
    continuity_gap: ContinuityGap
    language_mode: LanguageMode
    language_source: str
    external_effects_enabled: bool
    automatic_actions_enabled: bool
    supported_operations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReplayState:
    boot_count: int
    current_boot_id: str | None
    presence: DesktopRuntimeState | None
    process_open: bool
    last_event: CausalEvent | None
    current_gap: ContinuityGap | None
    recovered_after_unclean_shutdown: bool


class _RuntimeLease:
    """Best-effort same-machine single-process lease for one database."""

    def __init__(self, handle: BinaryIO | None) -> None:
        self._handle = handle
        self._released = False

    @classmethod
    def acquire(cls, database: str | Path) -> "_RuntimeLease":
        if str(database) == ":memory:":
            return cls(None)

        database_path = Path(database).expanduser().resolve(strict=False)
        if not database_path.parent.is_dir():
            raise DesktopRuntimeError("database_parent_missing")
        lock_path = Path(f"{database_path}.desktop.lock")
        handle = lock_path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise DesktopRuntimeError("runtime_lease_unavailable") from exc
        return cls(handle)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()


def _exact_payload(
    event: CausalEvent,
    expected: set[str],
) -> Mapping[str, JSONValue]:
    if set(event.payload) != expected:
        raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
    if event.payload.get("contract_version") != DESKTOP_RUNTIME_CONTRACT:
        raise DesktopRuntimeError("lifecycle_contract_version_mismatch")
    return event.payload


def _payload_text(payload: Mapping[str, JSONValue], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
    return value


def _payload_bool(payload: Mapping[str, JSONValue], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
    return value


def _payload_number_or_none(
    payload: Mapping[str, JSONValue],
    field: str,
) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
    return number


def _replay_lifecycle(events: list[CausalEvent]) -> _ReplayState:
    boot_count = 0
    current_boot_id: str | None = None
    presence: DesktopRuntimeState | None = None
    process_open = False
    last_event: CausalEvent | None = None
    current_gap: ContinuityGap | None = None
    recovered = False
    seen_boots: set[str] = set()

    for event in events:
        if event.session_id != DESKTOP_RUNTIME_STREAM:
            raise DesktopRuntimeError("lifecycle_stream_mismatch")
        if event.kind not in _EVENT_KINDS:
            raise DesktopRuntimeError("unknown_lifecycle_event")
        if any(
            value is not None
            for value in (event.goal_id, event.action_id, event.observation_id)
        ):
            raise DesktopRuntimeError("lifecycle_authority_reference_forbidden")
        expected_parent = last_event.event_id if last_event is not None else None
        if event.parent_event_id != expected_parent:
            raise DesktopRuntimeError("lifecycle_chain_forked")
        if last_event is not None and event.occurred_at < last_event.occurred_at:
            raise DesktopRuntimeError("lifecycle_clock_regression")

        if event.kind == _STARTED:
            payload = _exact_payload(
                event,
                {
                    "contract_version",
                    "boot_id",
                    "boot_number",
                    "recovered_after_unclean_shutdown",
                    "continuity_gap_kind",
                    "continuity_gap_seconds",
                    "presence_state",
                    "language_mode",
                    "external_effects_enabled",
                    "automatic_actions_enabled",
                },
            )
            boot_id = _payload_text(payload, "boot_id")
            if boot_id in seen_boots:
                raise DesktopRuntimeError("duplicate_boot_id")
            raw_boot_number = payload.get("boot_number")
            if (
                isinstance(raw_boot_number, bool)
                or not isinstance(raw_boot_number, int)
                or raw_boot_number != boot_count + 1
            ):
                raise DesktopRuntimeError("lifecycle_boot_sequence_mismatch")

            expected_recovered = last_event is not None and process_open
            if (
                _payload_bool(payload, "recovered_after_unclean_shutdown")
                is not expected_recovered
            ):
                raise DesktopRuntimeError("lifecycle_recovery_mismatch")
            expected_gap_kind = (
                ContinuityGapKind.FIRST_START
                if last_event is None
                else (
                    ContinuityGapKind.UNCLEAN_UNOBSERVED
                    if expected_recovered
                    else ContinuityGapKind.CLEAN_OFFLINE
                )
            )
            if payload.get("continuity_gap_kind") != expected_gap_kind.value:
                raise DesktopRuntimeError("lifecycle_gap_kind_mismatch")
            observed_seconds = _payload_number_or_none(
                payload,
                "continuity_gap_seconds",
            )
            if last_event is None:
                if observed_seconds is not None:
                    raise DesktopRuntimeError("lifecycle_gap_value_mismatch")
                gap_start = None
            else:
                expected_seconds = (
                    event.occurred_at - last_event.occurred_at
                ).total_seconds()
                if observed_seconds is None or not math.isclose(
                    observed_seconds,
                    expected_seconds,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                ):
                    raise DesktopRuntimeError("lifecycle_gap_value_mismatch")
                gap_start = last_event.occurred_at
            if payload.get("presence_state") != DesktopRuntimeState.SLEEPING.value:
                raise DesktopRuntimeError("lifecycle_start_not_sleeping")
            if payload.get("language_mode") != LanguageMode.PURE.value:
                raise DesktopRuntimeError("lifecycle_language_mode_not_pure")
            if _payload_bool(payload, "external_effects_enabled"):
                raise DesktopRuntimeError("lifecycle_external_effects_forbidden")
            if _payload_bool(payload, "automatic_actions_enabled"):
                raise DesktopRuntimeError("lifecycle_automatic_actions_forbidden")

            boot_count += 1
            seen_boots.add(boot_id)
            current_boot_id = boot_id
            presence = DesktopRuntimeState.SLEEPING
            process_open = True
            recovered = expected_recovered
            current_gap = ContinuityGap(
                kind=expected_gap_kind,
                started_at=gap_start,
                ended_at=event.occurred_at,
                seconds=observed_seconds,
            )

        else:
            if not process_open or current_boot_id is None or presence is None:
                raise DesktopRuntimeError("lifecycle_event_without_open_process")
            payload = event.payload
            if event.kind == _ACTIVATED:
                payload = _exact_payload(
                    event,
                    {"contract_version", "boot_id", "source", "presence_state"},
                )
                if presence is not DesktopRuntimeState.SLEEPING:
                    raise DesktopRuntimeError("invalid_activation_transition")
                if payload.get("source") != ActivationSource.EXPLICIT_USER.value:
                    raise DesktopRuntimeError("non_explicit_activation_forbidden")
                if payload.get("presence_state") != DesktopRuntimeState.ACTIVE.value:
                    raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
                presence = DesktopRuntimeState.ACTIVE
            elif event.kind == _SLEPT:
                payload = _exact_payload(
                    event,
                    {"contract_version", "boot_id", "reason", "presence_state"},
                )
                if presence is not DesktopRuntimeState.ACTIVE:
                    raise DesktopRuntimeError("invalid_sleep_transition")
                try:
                    SleepReason(str(payload.get("reason")))
                except ValueError as exc:
                    raise DesktopRuntimeError(
                        "lifecycle_payload_contract_mismatch"
                    ) from exc
                if payload.get("presence_state") != DesktopRuntimeState.SLEEPING.value:
                    raise DesktopRuntimeError("lifecycle_payload_contract_mismatch")
                presence = DesktopRuntimeState.SLEEPING
            elif event.kind == _CHECKPOINTED:
                payload = _exact_payload(
                    event,
                    {"contract_version", "boot_id", "presence_state"},
                )
                if payload.get("presence_state") != presence.value:
                    raise DesktopRuntimeError("checkpoint_state_mismatch")
            elif event.kind == _STOPPED:
                payload = _exact_payload(
                    event,
                    {
                        "contract_version",
                        "boot_id",
                        "reason",
                        "final_presence_state",
                        "clean_shutdown",
                    },
                )
                try:
                    ShutdownReason(str(payload.get("reason")))
                except ValueError as exc:
                    raise DesktopRuntimeError(
                        "lifecycle_payload_contract_mismatch"
                    ) from exc
                if payload.get("final_presence_state") != presence.value:
                    raise DesktopRuntimeError("stop_state_mismatch")
                if _payload_bool(payload, "clean_shutdown") is not True:
                    raise DesktopRuntimeError("false_clean_shutdown_forbidden")
                process_open = False
                presence = None

            if _payload_text(payload, "boot_id") != current_boot_id:
                raise DesktopRuntimeError("lifecycle_boot_id_mismatch")

        last_event = event

    return _ReplayState(
        boot_count=boot_count,
        current_boot_id=current_boot_id,
        presence=presence,
        process_open=process_open,
        last_event=last_event,
        current_gap=current_gap,
        recovered_after_unclean_shutdown=recovered,
    )


class DesktopRuntime:
    """Own the v50 kernel behind a narrow, pure-mode desktop API."""

    _SUPPORTED_OPERATIONS = (
        "explicit_activation",
        "explicit_sleep",
        "pure_language_observation",
        "lifecycle_checkpoint",
        "clean_shutdown",
    )

    def __init__(
        self,
        *,
        kernel: DarwinKernelV50,
        language: DarwinLanguageGateway,
        lease: _RuntimeLease,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._kernel = kernel
        self._language = language
        self._lease = lease
        self._clock = clock
        self._id_factory = id_factory
        self._state = DesktopRuntimeState.NEW
        self._boot_id: str | None = None
        self._boot_number = 0
        self._gap: ContinuityGap | None = None
        self._recovered = False

    @classmethod
    def open(
        cls,
        database: str | Path,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ) -> "DesktopRuntime":
        lease = _RuntimeLease.acquire(database)
        store: SQLiteEventStore | None = None
        try:
            store = SQLiteEventStore(database)
            kernel = DarwinKernelV50(
                store,
                clock=clock,
                id_factory=id_factory,
            )
            language = DarwinLanguageGateway()
            if language.mode is not LanguageMode.PURE:
                raise DesktopRuntimeError("desktop_language_mode_not_pure")
            return cls(
                kernel=kernel,
                language=language,
                lease=lease,
                clock=clock,
                id_factory=id_factory,
            )
        except BaseException:
            if store is not None and not store.closed:
                store.close()
            lease.release()
            raise

    @property
    def state(self) -> DesktopRuntimeState:
        return self._state

    def _new_id(self, kind: str) -> str:
        return f"desktop-{kind}:{self._id_factory()}"

    def _ensure_started(self) -> None:
        if self._state is DesktopRuntimeState.NEW:
            raise DesktopRuntimeError("runtime_not_started")
        if self._state is DesktopRuntimeState.CLOSED:
            raise DesktopRuntimeError("runtime_closed")

    @staticmethod
    def _ensure_clock_not_regressed(
        now: datetime,
        previous: CausalEvent | None,
    ) -> None:
        if now.tzinfo is None:
            raise ValidationError("desktop runtime clock must be timezone-aware")
        if previous is not None and now < previous.occurred_at:
            raise DesktopRuntimeError("wall_clock_regression")

    def start(self) -> DesktopSnapshot:
        if self._state is not DesktopRuntimeState.NEW:
            raise DesktopRuntimeError("runtime_already_started")
        with self._kernel.store.transaction() as connection:
            events = self._kernel.store.events_for_session(
                DESKTOP_RUNTIME_STREAM,
                connection=connection,
            )
            replay = _replay_lifecycle(events)
            now = self._clock()
            self._ensure_clock_not_regressed(now, replay.last_event)
            recovered = replay.last_event is not None and replay.process_open
            gap_kind = (
                ContinuityGapKind.FIRST_START
                if replay.last_event is None
                else (
                    ContinuityGapKind.UNCLEAN_UNOBSERVED
                    if recovered
                    else ContinuityGapKind.CLEAN_OFFLINE
                )
            )
            gap_seconds = (
                None
                if replay.last_event is None
                else (now - replay.last_event.occurred_at).total_seconds()
            )
            boot_id = self._new_id("boot")
            event = CausalEvent(
                event_id=self._new_id("event"),
                session_id=DESKTOP_RUNTIME_STREAM,
                kind=_STARTED,
                occurred_at=now,
                parent_event_id=(
                    replay.last_event.event_id
                    if replay.last_event is not None
                    else None
                ),
                payload={
                    "contract_version": DESKTOP_RUNTIME_CONTRACT,
                    "boot_id": boot_id,
                    "boot_number": replay.boot_count + 1,
                    "recovered_after_unclean_shutdown": recovered,
                    "continuity_gap_kind": gap_kind.value,
                    "continuity_gap_seconds": gap_seconds,
                    "presence_state": DesktopRuntimeState.SLEEPING.value,
                    "language_mode": LanguageMode.PURE.value,
                    "external_effects_enabled": False,
                    "automatic_actions_enabled": False,
                },
            )
            self._kernel.store.append_event(event, connection=connection)

        self._boot_id = boot_id
        self._boot_number = replay.boot_count + 1
        self._state = DesktopRuntimeState.SLEEPING
        self._recovered = recovered
        self._gap = ContinuityGap(
            kind=gap_kind,
            started_at=(
                replay.last_event.occurred_at
                if replay.last_event is not None
                else None
            ),
            ended_at=now,
            seconds=gap_seconds,
        )
        return self.snapshot()

    def _append_current_event(
        self,
        *,
        kind: str,
        payload: Mapping[str, JSONValue],
    ) -> None:
        self._ensure_started()
        if self._boot_id is None:
            raise DesktopRuntimeError("runtime_boot_missing")
        with self._kernel.store.transaction() as connection:
            events = self._kernel.store.events_for_session(
                DESKTOP_RUNTIME_STREAM,
                connection=connection,
            )
            replay = _replay_lifecycle(events)
            if (
                not replay.process_open
                or replay.current_boot_id != self._boot_id
                or replay.presence is not self._state
            ):
                raise DesktopRuntimeError("runtime_state_diverged")
            now = self._clock()
            self._ensure_clock_not_regressed(now, replay.last_event)
            if replay.last_event is None:
                raise DesktopRuntimeError("runtime_history_missing")
            event = CausalEvent(
                event_id=self._new_id("event"),
                session_id=DESKTOP_RUNTIME_STREAM,
                kind=kind,
                occurred_at=now,
                parent_event_id=replay.last_event.event_id,
                payload=dict(payload),
            )
            self._kernel.store.append_event(event, connection=connection)

    def activate(
        self,
        source: ActivationSource = ActivationSource.EXPLICIT_USER,
    ) -> DesktopSnapshot:
        self._ensure_started()
        if not isinstance(source, ActivationSource):
            raise ValidationError("activation source is invalid")
        if source is not ActivationSource.EXPLICIT_USER:
            raise DesktopRuntimeError("non_explicit_activation_forbidden")
        if self._state is not DesktopRuntimeState.SLEEPING:
            raise DesktopRuntimeError("runtime_not_sleeping")
        if self._boot_id is None:
            raise DesktopRuntimeError("runtime_boot_missing")
        self._append_current_event(
            kind=_ACTIVATED,
            payload={
                "contract_version": DESKTOP_RUNTIME_CONTRACT,
                "boot_id": self._boot_id,
                "source": source.value,
                "presence_state": DesktopRuntimeState.ACTIVE.value,
            },
        )
        self._state = DesktopRuntimeState.ACTIVE
        return self.snapshot()

    def sleep(
        self,
        reason: SleepReason = SleepReason.EXPLICIT_USER,
    ) -> DesktopSnapshot:
        self._ensure_started()
        if not isinstance(reason, SleepReason):
            raise ValidationError("sleep reason is invalid")
        if self._state is not DesktopRuntimeState.ACTIVE:
            raise DesktopRuntimeError("runtime_not_active")
        if self._boot_id is None:
            raise DesktopRuntimeError("runtime_boot_missing")
        self._append_current_event(
            kind=_SLEPT,
            payload={
                "contract_version": DESKTOP_RUNTIME_CONTRACT,
                "boot_id": self._boot_id,
                "reason": reason.value,
                "presence_state": DesktopRuntimeState.SLEEPING.value,
            },
        )
        self._state = DesktopRuntimeState.SLEEPING
        return self.snapshot()

    def observe_text(
        self,
        text: str,
        *,
        locale: str = "und",
    ) -> LanguageObservation:
        self._ensure_started()
        if self._state is not DesktopRuntimeState.ACTIVE:
            raise DesktopRuntimeError("runtime_sleeping")
        return self._language.understand(
            UnderstandingRequest(text=text, locale=locale)
        )

    def checkpoint(self) -> DesktopSnapshot:
        self._ensure_started()
        if self._boot_id is None:
            raise DesktopRuntimeError("runtime_boot_missing")
        self._append_current_event(
            kind=_CHECKPOINTED,
            payload={
                "contract_version": DESKTOP_RUNTIME_CONTRACT,
                "boot_id": self._boot_id,
                "presence_state": self._state.value,
            },
        )
        return self.snapshot()

    def snapshot(self) -> DesktopSnapshot:
        self._ensure_started()
        if self._boot_id is None or self._gap is None:
            raise DesktopRuntimeError("runtime_snapshot_incomplete")
        return DesktopSnapshot(
            contract_version=DESKTOP_RUNTIME_CONTRACT,
            state=self._state,
            boot_id=self._boot_id,
            boot_number=self._boot_number,
            recovered_after_unclean_shutdown=self._recovered,
            continuity_gap=self._gap,
            language_mode=self._language.mode,
            language_source=self._language.source_name,
            external_effects_enabled=False,
            automatic_actions_enabled=False,
            supported_operations=self._SUPPORTED_OPERATIONS,
        )

    def shutdown(
        self,
        reason: ShutdownReason = ShutdownReason.EXPLICIT_USER,
    ) -> None:
        if self._state is DesktopRuntimeState.CLOSED:
            return
        if not isinstance(reason, ShutdownReason):
            raise ValidationError("shutdown reason is invalid")
        if self._state is DesktopRuntimeState.NEW:
            self.close()
            return
        if self._boot_id is None:
            raise DesktopRuntimeError("runtime_boot_missing")
        try:
            self._append_current_event(
                kind=_STOPPED,
                payload={
                    "contract_version": DESKTOP_RUNTIME_CONTRACT,
                    "boot_id": self._boot_id,
                    "reason": reason.value,
                    "final_presence_state": self._state.value,
                    "clean_shutdown": True,
                },
            )
        finally:
            self.close()

    def close(self) -> None:
        """Release resources without claiming that shutdown was clean."""

        if self._state is DesktopRuntimeState.CLOSED:
            return
        try:
            self._kernel.close()
        finally:
            self._lease.release()
            self._state = DesktopRuntimeState.CLOSED

    def __enter__(self) -> "DesktopRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        if self._state in {
            DesktopRuntimeState.SLEEPING,
            DesktopRuntimeState.ACTIVE,
        }:
            self.shutdown(ShutdownReason.APPLICATION_EXIT)
        else:
            self.close()
