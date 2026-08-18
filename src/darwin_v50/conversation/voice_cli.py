"""Hidden-until-called Windows voice host for the v50 local runtime."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk
from typing import Mapping, TextIO

from ..language import LanguageBoundaryError
from ..models import DarwinV50Error, ValidationError
from .config import ConversationBackendKind, ConversationSettings
from .local_seed import (
    LlamaCppServerTransport,
    LocalSeedTransportError,
    PortableLocalLanguageBackend,
)
from .runtime import ConversationAvailability, ConversationRuntime
from .voice_runtime import (
    DarwinVoiceController,
    VoiceAction,
    VoiceActionKind,
    VoiceHostState,
    contains_wake_word,
    is_sleep_command,
)
from .windows_voice_io import (
    RecognizedSpeech,
    WindowsSpeechListener,
    WindowsSpeechSynthesizer,
)


_INSTANCE_MUTEX: int | None = None


class VoiceHostStartupError(DarwinV50Error):
    """Raised before microphone capture when local inference is unavailable."""


def _write(stream: TextIO, message: str) -> None:
    stream.write(message + "\n")
    stream.flush()


def _acquire_single_instance() -> bool:
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\DarwinV50VoiceHost")
    if not handle:
        return True
    _INSTANCE_MUTEX = int(handle)
    return kernel32.GetLastError() != 183


def create_local_runtime(
    environment: Mapping[str, str] | None = None,
) -> ConversationRuntime:
    source = os.environ if environment is None else environment
    settings = ConversationSettings.from_environment(source)
    if settings.backend is not ConversationBackendKind.LOCAL:
        raise VoiceHostStartupError("voice_host_requires_explicit_local_backend")
    if settings.model is None:
        raise VoiceHostStartupError("voice_host_local_model_not_configured")
    endpoint = source.get("DARWIN_LOCAL_ENDPOINT", "").strip()
    api_key = source.get("DARWIN_LOCAL_API_KEY", "").strip()
    if not endpoint:
        raise VoiceHostStartupError("voice_host_local_endpoint_not_configured")
    if not api_key:
        raise VoiceHostStartupError("voice_host_local_key_not_configured")
    transport = LlamaCppServerTransport(
        endpoint=endpoint,
        api_key=api_key,
        timeout_seconds=settings.request_timeout_seconds,
    )
    backend = PortableLocalLanguageBackend(
        model=settings.model,
        transport=transport,
    )
    backend.probe_model()
    runtime = ConversationRuntime.create(settings, local_backend=backend)
    if runtime.snapshot().availability is not ConversationAvailability.AVAILABLE:
        reason = runtime.snapshot().unavailable_reason or "unknown"
        runtime.close()
        raise VoiceHostStartupError(f"voice_host_runtime_unavailable:{reason}")
    return runtime


class DarwinV50VoiceApp:
    """Session-only GUI; status text is never used as a spoken reply."""

    def __init__(self, root: tk.Tk, runtime: ConversationRuntime) -> None:
        self.root = root
        self.root.title("Darwin v50 Voice Development")
        self.root.geometry("900x620")
        self.root.minsize(760, 500)
        self.root.protocol("WM_DELETE_WINDOW", self.sleep)
        self.controller = DarwinVoiceController(runtime)
        self.busy = False
        self.closed = False
        self.status = tk.StringVar(value="Starting local voice listener")
        self._build()
        self.listener = WindowsSpeechListener(
            self._listener_ready,
            self._recognized,
            self._low_confidence,
            self._listener_error,
            culture="pt-BR",
            minimum_confidence=0.25,
            listener_role="DarwinV50VoiceHost",
        )
        self.synthesizer = WindowsSpeechSynthesizer(
            self._speech_started,
            self._speech_stopped,
            self._speech_error,
        )
        self.root.withdraw()
        self.listener.start()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Darwin v50 — local voice development").pack(
            anchor="w"
        )
        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(4, 14))
        self.transcript = tk.Text(frame, wrap="word", state="disabled")
        self.transcript.pack(fill="both", expand=True)
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(12, 0))
        ttk.Button(controls, text="Sleep", command=self.sleep).pack(side="left")
        ttk.Button(controls, text="End temporary session", command=self.close).pack(
            side="right"
        )

    def _schedule(self, callback: object, *args: object) -> None:
        if self.closed:
            return
        self.root.after(0, callback, *args)  # type: ignore[arg-type]

    def _listener_ready(self, culture: str, name: str) -> None:
        self._schedule(self.status.set, f"Sleeping — listener ready: {culture} / {name}")

    def _recognized(self, speech: RecognizedSpeech) -> None:
        self._schedule(self._accept_recognized, speech)

    def _low_confidence(self, _speech: RecognizedSpeech) -> None:
        return

    def _listener_error(self, error: str) -> None:
        self._schedule(self.status.set, f"Voice listener unavailable: {error}")

    def _accept_recognized(self, speech: RecognizedSpeech) -> None:
        if self.closed or self.busy:
            return
        if (
            self.controller.state is VoiceHostState.SLEEPING
            and not contains_wake_word(speech.text)
        ):
            return
        if (
            self.controller.state is VoiceHostState.AWAKE
            and is_sleep_command(speech.text)
        ):
            self._apply_action(
                self.controller.handle(speech.text, confidence=speech.confidence)
            )
            return
        self.busy = True
        self.listener.set_paused(True)
        if contains_wake_word(speech.text):
            self._show()
        self.status.set("Processing one local model turn")
        threading.Thread(
            target=self._run_turn,
            args=(speech,),
            daemon=True,
        ).start()

    def _run_turn(self, speech: RecognizedSpeech) -> None:
        action = self.controller.handle(speech.text, confidence=speech.confidence)
        self._schedule(self._apply_action, action)

    def _apply_action(self, action: VoiceAction) -> None:
        if action.kind is VoiceActionKind.AWAKENED:
            self._show()
            self.status.set("Awake — listening")
            self._resume_listener()
            return
        if action.kind is VoiceActionKind.SLEPT:
            self.root.withdraw()
            self.status.set("Sleeping — say Darwin to open")
            self._resume_listener()
            return
        if action.kind is VoiceActionKind.MODEL_REPLY:
            assert action.model_input is not None
            assert action.expression_text is not None
            self._show()
            self._append("You", action.model_input)
            self._append("Darwin", action.expression_text)
            self.status.set("Speaking model output")
            self.synthesizer.speak(action.expression_text)
            return
        if action.kind is VoiceActionKind.FAILED_CLOSED:
            self._show()
            self.status.set(f"Turn failed closed: {action.error_code}")
            self._resume_listener()
            return
        self._resume_listener()

    def _append(self, role: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{role}: {text}\n\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def _speech_started(self) -> None:
        return

    def _speech_stopped(self) -> None:
        self._schedule(self._finish_speech)

    def _finish_speech(self) -> None:
        self.status.set("Awake — listening")
        self._resume_listener()

    def _speech_error(self, error: str) -> None:
        self._schedule(self.status.set, f"Speech synthesis failed: {error}")

    def _resume_listener(self) -> None:
        self.busy = False
        self.listener.set_paused(False)

    def sleep(self) -> None:
        if self.closed:
            return
        self.controller.sleep()
        self.root.withdraw()
        self.status.set("Sleeping — say Darwin to open")
        self._resume_listener()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.listener.stop()
        self.synthesizer.stop()
        self.controller.close()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.root.destroy()


def main() -> int:
    if os.name != "nt":
        _write(sys.stderr, "Darwin v50 voice host requires Windows.")
        return 2
    if not _acquire_single_instance():
        _write(sys.stderr, "Darwin v50 voice host is already running.")
        return 2
    try:
        runtime = create_local_runtime()
    except (
        LanguageBoundaryError,
        LocalSeedTransportError,
        ValidationError,
        VoiceHostStartupError,
    ) as exc:
        _write(sys.stderr, f"Darwin v50 voice host is unavailable: {exc}")
        return 2
    root = tk.Tk()
    app = DarwinV50VoiceApp(root, runtime)
    try:
        root.mainloop()
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
