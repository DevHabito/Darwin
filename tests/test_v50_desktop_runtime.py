from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from darwin_v50 import (
    DESKTOP_RUNTIME_STREAM,
    ActivationSource,
    ContinuityGapKind,
    DesktopRuntime,
    DesktopRuntimeError,
    DesktopRuntimeState,
    LanguageMode,
    SQLiteEventStore,
)
from darwin_v50.models import CausalEvent


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class SequentialIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"id-{self.value}"


class DesktopRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.database = Path(self.temporary.name) / "darwin-v50.sqlite3"
        self.clock = MutableClock(
            datetime(2035, 1, 2, 12, 0, tzinfo=timezone.utc)
        )
        self.ids = SequentialIds()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def open_runtime(self) -> DesktopRuntime:
        return DesktopRuntime.open(
            self.database,
            clock=self.clock,
            id_factory=self.ids,
        )

    def lifecycle_events(self) -> list[CausalEvent]:
        with SQLiteEventStore(self.database) as store:
            return store.events_for_session(DESKTOP_RUNTIME_STREAM)

    def test_first_start_is_sleeping_pure_and_authority_free(self) -> None:
        runtime = self.open_runtime()
        snapshot = runtime.start()

        self.assertEqual(snapshot.state, DesktopRuntimeState.SLEEPING)
        self.assertEqual(snapshot.boot_number, 1)
        self.assertEqual(
            snapshot.continuity_gap.kind,
            ContinuityGapKind.FIRST_START,
        )
        self.assertIsNone(snapshot.continuity_gap.started_at)
        self.assertIsNone(snapshot.continuity_gap.seconds)
        self.assertFalse(snapshot.recovered_after_unclean_shutdown)
        self.assertEqual(snapshot.language_mode, LanguageMode.PURE)
        self.assertEqual(snapshot.language_source, "darwin-pure")
        self.assertFalse(snapshot.external_effects_enabled)
        self.assertFalse(snapshot.automatic_actions_enabled)
        self.assertNotIn("execute", snapshot.supported_operations)
        self.assertFalse(hasattr(runtime, "execute"))
        self.assertFalse(hasattr(runtime, "dispatch_action"))
        self.assertFalse(hasattr(snapshot, "database"))
        self.assertFalse(hasattr(snapshot, "store"))
        self.assertFalse(hasattr(snapshot, "kernel"))
        with self.assertRaises(FrozenInstanceError):
            snapshot.boot_number = 9  # type: ignore[misc]

        runtime.shutdown()

    def test_clean_restart_records_exact_offline_gap_and_chain(self) -> None:
        first = self.open_runtime()
        first.start()
        first.activate()
        self.clock.advance(2)
        first.sleep()
        self.clock.advance(3)
        first.shutdown()

        self.clock.advance(11)
        second = self.open_runtime()
        snapshot = second.start()

        self.assertEqual(snapshot.state, DesktopRuntimeState.SLEEPING)
        self.assertEqual(snapshot.boot_number, 2)
        self.assertFalse(snapshot.recovered_after_unclean_shutdown)
        self.assertEqual(
            snapshot.continuity_gap.kind,
            ContinuityGapKind.CLEAN_OFFLINE,
        )
        self.assertEqual(snapshot.continuity_gap.seconds, 11.0)
        second.shutdown()

        events = self.lifecycle_events()
        self.assertEqual(events[0].parent_event_id, None)
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current.parent_event_id, previous.event_id)
        self.assertEqual(
            [event.kind for event in events],
            [
                "desktop.started",
                "desktop.activated",
                "desktop.slept",
                "desktop.stopped",
                "desktop.started",
                "desktop.stopped",
            ],
        )

    def test_interrupted_restart_reports_unobserved_not_offline(self) -> None:
        first = self.open_runtime()
        first.start()
        first.activate(ActivationSource.EXPLICIT_USER)
        self.clock.advance(4)
        first.checkpoint()
        first.close()

        self.clock.advance(17)
        second = self.open_runtime()
        snapshot = second.start()

        self.assertTrue(snapshot.recovered_after_unclean_shutdown)
        self.assertEqual(snapshot.state, DesktopRuntimeState.SLEEPING)
        self.assertEqual(
            snapshot.continuity_gap.kind,
            ContinuityGapKind.UNCLEAN_UNOBSERVED,
        )
        self.assertEqual(snapshot.continuity_gap.seconds, 17.0)
        second.shutdown()

    def test_sleeping_rejects_text_and_active_pure_mode_abstains(self) -> None:
        runtime = self.open_runtime()
        runtime.start()
        with self.assertRaisesRegex(DesktopRuntimeError, "runtime_sleeping"):
            runtime.observe_text("Darwin, are you there?", locale="en-US")

        runtime.activate()
        observation = runtime.observe_text(
            "Darwin, are you there?",
            locale="en-US",
        )

        self.assertEqual(observation.intent, "unclassified")
        self.assertEqual(observation.confidence, 0.0)
        self.assertEqual(observation.mode, LanguageMode.PURE)
        runtime.shutdown()

        persisted = "\n".join(
            str(dict(event.payload)) for event in self.lifecycle_events()
        )
        self.assertNotIn("Darwin, are you there?", persisted)

    def test_second_live_instance_is_rejected(self) -> None:
        first = self.open_runtime()
        try:
            with self.assertRaisesRegex(
                DesktopRuntimeError,
                "runtime_lease_unavailable",
            ):
                self.open_runtime()
        finally:
            first.close()

    def test_backward_wall_clock_fails_closed(self) -> None:
        first = self.open_runtime()
        first.start()
        first.shutdown()
        self.clock.advance(-1)

        second = self.open_runtime()
        try:
            with self.assertRaisesRegex(
                DesktopRuntimeError,
                "wall_clock_regression",
            ):
                second.start()
        finally:
            second.close()

    def test_unknown_lifecycle_event_fails_replay(self) -> None:
        first = self.open_runtime()
        first.start()
        first.shutdown()
        events = self.lifecycle_events()
        last = events[-1]
        self.clock.advance(1)
        with SQLiteEventStore(self.database) as store:
            store.append_event(
                CausalEvent(
                    event_id="corrupt-event",
                    session_id=DESKTOP_RUNTIME_STREAM,
                    kind="desktop.unknown",
                    occurred_at=self.clock(),
                    parent_event_id=last.event_id,
                    payload={},
                )
            )

        second = self.open_runtime()
        try:
            with self.assertRaisesRegex(
                DesktopRuntimeError,
                "unknown_lifecycle_event",
            ):
                second.start()
        finally:
            second.close()

    def test_forked_lifecycle_history_fails_replay(self) -> None:
        first = self.open_runtime()
        first.start()
        first.activate()
        first.shutdown()
        events = self.lifecycle_events()
        self.clock.advance(1)
        with SQLiteEventStore(self.database) as store:
            store.append_event(
                CausalEvent(
                    event_id="forked-event",
                    session_id=DESKTOP_RUNTIME_STREAM,
                    kind="desktop.checkpointed",
                    occurred_at=self.clock(),
                    parent_event_id=events[0].event_id,
                    payload={
                        "contract_version": "darwin-desktop-runtime-v1",
                        "boot_id": events[0].payload["boot_id"],
                        "presence_state": "active",
                    },
                )
            )

        second = self.open_runtime()
        try:
            with self.assertRaisesRegex(
                DesktopRuntimeError,
                "lifecycle_chain_forked",
            ):
                second.start()
        finally:
            second.close()

    def test_contract_incompatible_history_fails_replay(self) -> None:
        self.clock.advance(1)
        with SQLiteEventStore(self.database) as store:
            store.append_event(
                CausalEvent(
                    event_id="wrong-contract-event",
                    session_id=DESKTOP_RUNTIME_STREAM,
                    kind="desktop.started",
                    occurred_at=self.clock(),
                    payload={
                        "contract_version": "darwin-desktop-runtime-v0",
                        "boot_id": "old-boot",
                        "boot_number": 1,
                        "recovered_after_unclean_shutdown": False,
                        "continuity_gap_kind": "first_start",
                        "continuity_gap_seconds": None,
                        "presence_state": "sleeping",
                        "language_mode": "pure",
                        "external_effects_enabled": False,
                        "automatic_actions_enabled": False,
                    },
                )
            )

        runtime = self.open_runtime()
        try:
            with self.assertRaisesRegex(
                DesktopRuntimeError,
                "lifecycle_contract_version_mismatch",
            ):
                runtime.start()
        finally:
            runtime.close()

    def test_non_explicit_persisted_activation_fails_replay(self) -> None:
        first = self.open_runtime()
        first.start()
        first.close()
        events = self.lifecycle_events()
        started = events[-1]
        self.clock.advance(1)
        with SQLiteEventStore(self.database) as store:
            store.append_event(
                CausalEvent(
                    event_id="implicit-activation",
                    session_id=DESKTOP_RUNTIME_STREAM,
                    kind="desktop.activated",
                    occurred_at=self.clock(),
                    parent_event_id=started.event_id,
                    payload={
                        "contract_version": "darwin-desktop-runtime-v1",
                        "boot_id": started.payload["boot_id"],
                        "source": "automatic",
                        "presence_state": "active",
                    },
                )
            )

        second = self.open_runtime()
        try:
            with self.assertRaisesRegex(
                DesktopRuntimeError,
                "non_explicit_activation_forbidden",
            ):
                second.start()
        finally:
            second.close()

    def test_invalid_transitions_are_rejected(self) -> None:
        runtime = self.open_runtime()
        with self.assertRaisesRegex(DesktopRuntimeError, "runtime_not_started"):
            runtime.snapshot()
        runtime.start()
        with self.assertRaisesRegex(DesktopRuntimeError, "runtime_not_active"):
            runtime.sleep()
        runtime.activate()
        with self.assertRaisesRegex(DesktopRuntimeError, "runtime_not_sleeping"):
            runtime.activate()
        runtime.sleep()
        runtime.shutdown()
        with self.assertRaisesRegex(DesktopRuntimeError, "runtime_closed"):
            runtime.observe_text("hello")

    def test_context_manager_records_controlled_application_exit(self) -> None:
        with self.open_runtime() as runtime:
            runtime.start()
            runtime.activate()

        events = self.lifecycle_events()
        self.assertEqual(events[-1].kind, "desktop.stopped")
        self.assertEqual(events[-1].payload["reason"], "application_exit")
        self.assertIs(events[-1].payload["clean_shutdown"], True)


if __name__ == "__main__":
    unittest.main()
