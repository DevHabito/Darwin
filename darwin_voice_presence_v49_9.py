from __future__ import annotations

"""
DARWIN v49.9 - Voice Presence

Objetivo:
Darwin escuta o microfone local e responde sem o usuario digitar
ou apertar botao para falar. Usa reconhecimento de fala do Windows
quando disponivel e mantem tudo local no notebook.

Nota tecnica:
Isto reconhece fala captada pelo microfone. Nao e biometria de voz.
Identificar "Felipe" como falante unico exigira um modulo futuro de
perfil vocal/speaker verification.

Uso:
    py darwin_voice_presence_v49_9.py
    py darwin_voice_presence_v49_9.py --self-test --details
"""

import argparse
import json
import math
import queue
import random
import sqlite3
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from darwin_companion_shell_v49_8 import CompanionCore, CompanionReply, SpeechEngine, clamp, normalize, suffix


DB = Path("darwin_home") / "darwin.db"

VOICE_SESSIONS = "voice_presence_sessions_v49_9"
VOICE_EVENTS = "voice_presence_events_v49_9"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@dataclass
class RecognizedSpeech:
    text: str
    confidence: float
    culture: str
    source: str = "windows_speech"


class VoicePresenceStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = db_path
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin nao encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {VOICE_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    voice_session_id TEXT NOT NULL,
                    companion_session_id TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL,
                    recognizer_culture TEXT NOT NULL DEFAULT '',
                    recognizer_name TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VOICE_EVENTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    voice_session_id TEXT NOT NULL,
                    companion_session_id TEXT NOT NULL DEFAULT '',
                    dialogue_id TEXT NOT NULL DEFAULT '',
                    event_kind TEXT NOT NULL,
                    recognized_text TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    response_text TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )
            conn.commit()

    def log_session(
        self,
        voice_session_id: str,
        companion_session_id: str,
        phase: str,
        *,
        mode: str = "",
        recognizer_culture: str = "",
        recognizer_name: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VOICE_SESSIONS} (
                    timestamp, voice_session_id, companion_session_id, phase,
                    recognizer_culture, recognizer_name, mode, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    voice_session_id,
                    companion_session_id,
                    phase,
                    recognizer_culture,
                    recognizer_name,
                    mode,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_event(
        self,
        voice_session_id: str,
        companion_session_id: str,
        event_kind: str,
        *,
        dialogue_id: str = "",
        recognized_text: str = "",
        confidence: float = 0.0,
        rzs_decision: str = "",
        sigma_before: float = 0.0,
        sigma_after: float = 0.0,
        response_text: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VOICE_EVENTS} (
                    timestamp, voice_session_id, companion_session_id,
                    dialogue_id, event_kind, recognized_text, confidence,
                    rzs_decision, sigma_before, sigma_after, response_text,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    voice_session_id,
                    companion_session_id,
                    dialogue_id,
                    event_kind,
                    recognized_text,
                    confidence,
                    rzs_decision,
                    sigma_before,
                    sigma_after,
                    response_text,
                    js(payload or {}),
                ),
            )
            conn.commit()


class WindowsSpeechListener:
    def __init__(
        self,
        on_ready: Callable[[str, str], None],
        on_result: Callable[[RecognizedSpeech], None],
        on_low_confidence: Callable[[RecognizedSpeech], None],
        on_error: Callable[[str], None],
        *,
        culture: str = "pt-BR",
        min_confidence: float = 0.30,
        listener_role: str = "DarwinVoicePresence",
    ) -> None:
        self.on_ready = on_ready
        self.on_result = on_result
        self.on_low_confidence = on_low_confidence
        self.on_error = on_error
        self.culture = culture
        self.min_confidence = min_confidence
        self.listener_role = "".join(ch for ch in listener_role if ch.isalnum()) or "DarwinVoicePresence"
        self.proc: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.stop_requested = False
        self.paused = False
        self.current_culture = ""

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_requested = False
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def restart(self) -> None:
        self.stop()
        previous = self.thread
        if previous and previous.is_alive() and previous is not threading.current_thread():
            previous.join(timeout=2.0)
        self.thread = None
        self.proc = None
        self.paused = False
        self.start()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def _script(self) -> str:
        return rf"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$darwinListenerRole = '{self.listener_role}'
$preferred = '{self.culture}'
$minConfidence = {self.min_confidence:.3f}
$recognizer = $null

Add-Type -AssemblyName System.Speech
try {{
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo($preferred)
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
}} catch {{
    $recognizer = $null
}}
if ($recognizer -eq $null) {{
    $infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
    foreach ($info in $infos) {{
        if ($info.Enabled) {{
            $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
            break
        }}
    }}
}}
if ($recognizer -ne $null) {{
    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $grammar.Name = 'DarwinDictation'
    $recognizer.LoadGrammar($grammar)
    $recognizer.SetInputToDefaultAudioDevice()
    $recognizer.BabbleTimeout = [TimeSpan]::FromSeconds(1.5)
    $recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds(7)
    $recognizer.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(900)
    $cultureName = $recognizer.RecognizerInfo.Culture.Name
    $recName = $recognizer.RecognizerInfo.Name
    [Console]::Out.WriteLine("READY|$cultureName|$recName")
    [Console]::Out.Flush()
    while ($true) {{
        try {{
            $result = $recognizer.Recognize([TimeSpan]::FromSeconds(8))
            if ($result -ne $null) {{
                $text = ($result.Text -replace '\r?\n', ' ').Trim()
                $confidence = [double]$result.Confidence
                if ($text.Length -gt 0 -and $confidence -ge $minConfidence) {{
                    [Console]::Out.WriteLine(("RESULT|{{0:N3}}|{{1}}" -f $confidence, $text))
                    [Console]::Out.Flush()
                }} elseif ($text.Length -gt 0) {{
                    [Console]::Out.WriteLine(("LOWCONF|{{0:N3}}|{{1}}" -f $confidence, $text))
                    [Console]::Out.Flush()
                }}
            }}
        }} catch {{
            $message = $_.Exception.Message -replace '\r?\n', ' '
            [Console]::Out.WriteLine("ERROR|RECOGNIZE|$message")
            [Console]::Out.Flush()
            Start-Sleep -Milliseconds 500
        }}
    }}
    exit 0
}}

# Windows 11 installs pt-BR as a WinRT recognizer. System.Speech may still
# report zero recognizers, so Darwin uses the modern API as its real fallback.
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null

function Wait-WinRtOperation {{
    param($Operation, [Type]$ResultType)
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {{
            $_.Name -eq 'AsTask' -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        }} |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}}

try {{
    $language = New-Object Windows.Globalization.Language($preferred)
    $probeRecognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer($language)
    $compile = Wait-WinRtOperation ($probeRecognizer.CompileConstraintsAsync()) ([Windows.Media.SpeechRecognition.SpeechRecognitionCompilationResult])
    if ($compile.Status.ToString() -ne 'Success') {{
        throw "Falha ao compilar reconhecimento WinRT: $($compile.Status)"
    }}
    $probeRecognizer.Dispose()
    [Console]::Out.WriteLine("READY|$preferred|Windows Media SpeechRecognizer")
    [Console]::Out.Flush()
    while ($true) {{
        $turnRecognizer = $null
        try {{
            # A new one-shot recognizer per turn avoids a Windows 11 state in
            # which a second RecognizeAsync call can remain pending forever.
            $turnRecognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer($language)
            $turnCompile = Wait-WinRtOperation ($turnRecognizer.CompileConstraintsAsync()) ([Windows.Media.SpeechRecognition.SpeechRecognitionCompilationResult])
            if ($turnCompile.Status.ToString() -ne 'Success') {{
                throw "Falha ao preparar turno WinRT: $($turnCompile.Status)"
            }}
            $result = Wait-WinRtOperation ($turnRecognizer.RecognizeAsync()) ([Windows.Media.SpeechRecognition.SpeechRecognitionResult])
            $text = ($result.Text -replace '\r?\n', ' ').Trim()
            $confidence = switch ($result.Confidence.ToString()) {{
                'High' {{ 0.92 }}
                'Medium' {{ 0.72 }}
                'Low' {{ 0.48 }}
                default {{ 0.25 }}
            }}
            if ($text.Length -gt 0 -and $confidence -ge $minConfidence) {{
                [Console]::Out.WriteLine(("RESULT|{{0:N3}}|{{1}}" -f $confidence, $text))
                [Console]::Out.Flush()
            }} elseif ($text.Length -gt 0) {{
                [Console]::Out.WriteLine(("LOWCONF|{{0:N3}}|{{1}}" -f $confidence, $text))
                [Console]::Out.Flush()
            }}
        }} catch {{
            $message = $_.Exception.Message -replace '\r?\n', ' '
            [Console]::Out.WriteLine("ERROR|WINRT_RECOGNIZE|$message")
            [Console]::Out.Flush()
            Start-Sleep -Milliseconds 500
        }} finally {{
            if ($turnRecognizer -ne $null) {{
                $turnRecognizer.Dispose()
            }}
        }}
    }}
}} catch {{
    $message = $_.Exception.Message -replace '\r?\n', ' '
    [Console]::Out.WriteLine("ERROR|NO_RECOGNIZER|$message")
    [Console]::Out.Flush()
    exit 2
}}
"""

    def _worker(self) -> None:
        try:
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", self._script()],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            self.on_error(f"Falha ao iniciar reconhecimento de voz: {exc}")
            return
        assert self.proc.stdout is not None
        while not self.stop_requested:
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            self._handle_line(line.strip())
        if not self.stop_requested:
            code = self.proc.poll()
            self.on_error(f"Reconhecimento de voz encerrou. Codigo={code}")

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        parts = line.split("|", 2)
        kind = parts[0]
        if kind == "READY" and len(parts) >= 3:
            self.current_culture = parts[1]
            self.on_ready(parts[1], parts[2])
            return
        if kind in {"RESULT", "LOWCONF"} and len(parts) >= 3:
            confidence = 0.0
            try:
                confidence = float(parts[1].replace(",", "."))
            except Exception:
                pass
            speech = RecognizedSpeech(parts[2], confidence, self.current_culture or self.culture)
            if self.paused:
                return
            if kind == "RESULT":
                self.on_result(speech)
            else:
                self.on_low_confidence(speech)
            return
        if kind == "ERROR":
            self.on_error(parts[-1] if parts else line)
            return
        self.on_error(line)


class VoicePresenceApp:
    BG = "#071018"
    PANEL = "#0e1b26"
    INK = "#e9f4fa"
    MUTED = "#90a8bb"
    BLUE = "#58b0ff"
    GREEN = "#75e7a8"
    AMBER = "#f2bf72"
    RED = "#ff6f7a"

    def __init__(self, root: tk.Tk, culture: str = "pt-BR", min_confidence: float = 0.30) -> None:
        self.root = root
        self.root.title("Darwin Voice Presence v49.9")
        self.root.geometry("1040x760")
        self.root.minsize(860, 640)
        self.root.configure(bg=self.BG)

        self.store = VoicePresenceStore()
        self.core = CompanionCore(mode="voice_gui")
        self.voice_session_id = f"V499-{int(time.time()) % 10_000_000}-{suffix(random.Random(4990))}"
        self.store.log_session(self.voice_session_id, self.core.session_id, "voice_session_start", mode="gui")
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking, self.core.store, self.core.session_id)
        self.listener = WindowsSpeechListener(
            self.on_ready,
            self.on_voice_result,
            self.on_low_confidence,
            self.on_listener_error,
            culture=culture,
            min_confidence=min_confidence,
        )

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.speaking = False
        self.listening_ready = False
        self.status_text = "iniciando microfone"
        self.recognizer_culture = ""
        self.recognizer_name = ""
        self.tick = 0.0
        self.level = 0.0
        self.speech_text = ""
        self.last_reply: CompanionReply | None = None
        self.last_heard = ""
        self.last_confidence = 0.0

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x")
        ttk.Button(controls, text="Escutar", command=self.start_listening).pack(side="left", padx=(14, 8), pady=12)
        ttk.Button(controls, text="Pausar", command=self.pause_listening).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Status", command=lambda: self.answer_text("status", source="button")).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Parar fala", command=self.stop_speech).pack(side="left", padx=(0, 14), pady=12)

        self.transcript = tk.Text(
            root,
            height=10,
            bg="#061019",
            fg=self.INK,
            insertbackground=self.INK,
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.transcript.pack(fill="x")
        self.transcript.config(state="disabled")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.write("Darwin", "Voice Presence v49.9 iniciado. Vou escutar o microfone automaticamente.")
        self.start_listening()
        self.root.after(500, lambda: self.answer_text("oi", source="boot"))
        self.root.after(60, self.drain_events)
        self.animate()

    def write(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")
        self.transcript.config(state="disabled")

    def start_listening(self) -> None:
        self.listener.set_paused(False)
        self.listener.start()
        self.status_text = "escutando"
        self.store.log_event(self.voice_session_id, self.core.session_id, "listener_start")

    def pause_listening(self) -> None:
        self.listener.set_paused(True)
        self.status_text = "escuta pausada"
        self.store.log_event(self.voice_session_id, self.core.session_id, "listener_pause")

    def stop_speech(self) -> None:
        self.speech.stop()
        self.stop_speaking()

    def on_ready(self, culture: str, name: str) -> None:
        self.events.put(("ready", {"culture": culture, "name": name}))

    def on_voice_result(self, speech: RecognizedSpeech) -> None:
        self.events.put(("result", speech))

    def on_low_confidence(self, speech: RecognizedSpeech) -> None:
        self.events.put(("lowconf", speech))

    def on_listener_error(self, message: str) -> None:
        self.events.put(("error", message))

    def drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "ready":
                self.listening_ready = True
                self.recognizer_culture = payload["culture"]
                self.recognizer_name = payload["name"]
                self.status_text = f"escutando {self.recognizer_culture}"
                self.write("Sistema", f"Microfone ativo: {self.recognizer_culture} / {self.recognizer_name}")
                self.store.log_session(
                    self.voice_session_id,
                    self.core.session_id,
                    "recognizer_ready",
                    mode="gui",
                    recognizer_culture=self.recognizer_culture,
                    recognizer_name=self.recognizer_name,
                )
            elif kind == "result":
                speech: RecognizedSpeech = payload
                self.last_heard = speech.text
                self.last_confidence = speech.confidence
                self.write("Voce", f"{speech.text}  ({speech.confidence:.2f})")
                self.answer_text(speech.text, source=speech.source, confidence=speech.confidence)
            elif kind == "lowconf":
                speech = payload
                self.last_heard = speech.text
                self.last_confidence = speech.confidence
                self.status_text = "fala incerta"
                self.write("Sistema", f"Ouvi com baixa confianca: {speech.text} ({speech.confidence:.2f})")
                self.store.log_event(
                    self.voice_session_id,
                    self.core.session_id,
                    "low_confidence",
                    recognized_text=speech.text,
                    confidence=speech.confidence,
                    payload={"culture": speech.culture},
                )
            elif kind == "error":
                self.status_text = "erro no reconhecimento"
                self.write("Sistema", str(payload))
                self.store.log_event(
                    self.voice_session_id,
                    self.core.session_id,
                    "listener_error",
                    payload={"message": str(payload)},
                )
        self.root.after(60, self.drain_events)

    def answer_text(self, text: str, *, source: str, confidence: float = 1.0) -> None:
        if not text.strip():
            return
        reply = self.core.reply(text)
        self.last_reply = reply
        self.write("Darwin", reply.reply_text)
        self.store.log_event(
            self.voice_session_id,
            self.core.session_id,
            "recognized_response",
            dialogue_id=reply.dialogue_id,
            recognized_text=text,
            confidence=confidence,
            rzs_decision=reply.rzs_decision,
            sigma_before=reply.sigma_before,
            sigma_after=reply.sigma_after,
            response_text=reply.reply_text,
            payload={"source": source, "intent": reply.intent, "focus_key": reply.focus_key},
        )
        self.speech.speak(reply.dialogue_id, reply.reply_text)

    def start_speaking(self, text: str) -> None:
        self.speaking = True
        self.speech_text = text
        self.listener.set_paused(True)
        self.status_text = "falando; microfone ignorado"

    def stop_speaking(self) -> None:
        self.speaking = False
        self.level = 0.0
        self.root.after(1000, self.resume_after_speech)

    def resume_after_speech(self) -> None:
        self.listener.set_paused(False)
        self.status_text = "escutando"

    def speech_energy(self) -> float:
        if not self.speaking or not self.speech_text:
            return 0.0
        idx = int((self.tick * 8.0) % max(1, len(self.speech_text)))
        ch = self.speech_text[idx]
        if normalize(ch) in "aeiou":
            return 1.0
        if ch.isalpha():
            return 0.58
        if ch in ".,;:":
            return 0.12
        return 0.34

    def animate(self) -> None:
        self.tick += 0.075
        target = self.speech_energy()
        self.level = self.level * 0.76 + target * 0.24
        self.draw()
        self.root.after(16, self.animate)

    def draw(self) -> None:
        c = self.canvas
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.delete("all")
        cx = w / 2
        cy = h / 2 - 26
        reply = self.last_reply
        decision = reply.rzs_decision if reply else "listening"
        color = {
            "continue": self.BLUE,
            "narrow_focus": self.AMBER,
            "replay_memory": self.GREEN,
            "consolidate": "#a5b4fc",
            "pause_for_stability": self.RED,
            "listening": "#395a70",
        }.get(decision, self.BLUE)
        listen_pulse = 0.22 if self.listener.paused else 0.42
        radius = 82 + 32 * self.level + (6 * listen_pulse if not self.speaking else 0)
        x = cx + self.level * 28 * math.sin(self.tick * 2.1)
        y = cy + self.level * 20 * math.cos(self.tick * 1.8)
        for i in range(7, 0, -1):
            rr = radius + i * 18
            shade = 20 + i * 8
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline="", fill=f"#{shade//2:02x}{shade:02x}{min(130, shade+45):02x}")
        c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="#e5f7ff", width=3)
        inner = radius * (0.33 + self.level * 0.12)
        c.create_oval(x - inner, y - inner, x + inner, y + inner, fill="#ebfbff", outline="")
        c.create_text(cx, 38, text="DARWIN VOICE PRESENCE v49.9", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(cx, 70, text=self.status_text, fill=self.MUTED, font=("Segoe UI", 11))
        heard = self.last_heard[:82] if self.last_heard else "fale normalmente; nao precisa apertar botao"
        c.create_text(cx, h - 58, text=f"ultimo ouvido: {heard}", fill=self.MUTED, font=("Segoe UI", 10))
        c.create_text(cx, h - 32, text=f"confianca {self.last_confidence:.2f}   RZS {decision}", fill=self.MUTED, font=("Segoe UI", 10))

    def on_close(self) -> None:
        self.listener.stop()
        self.speech.stop()
        result = self.core.complete()
        self.store.log_session(
            self.voice_session_id,
            self.core.session_id,
            "voice_session_complete",
            mode="gui",
            recognizer_culture=self.recognizer_culture,
            recognizer_name=self.recognizer_name,
            payload=result,
        )
        self.root.destroy()


def run_self_test(details: bool = False) -> dict[str, Any]:
    store = VoicePresenceStore()
    core = CompanionCore(mode="voice_self_test")
    voice_session_id = f"V499-{int(time.time()) % 10_000_000}-{suffix(random.Random(4991))}"
    store.log_session(voice_session_id, core.session_id, "voice_session_start", mode="self_test")
    samples = [
        RecognizedSpeech("oi Darwin", 0.92, "simulated"),
        RecognizedSpeech("qual seu status", 0.88, "simulated"),
        RecognizedSpeech("o que voce aprendeu sobre geometria angulos e pesos", 0.91, "simulated"),
        RecognizedSpeech("vamos continuar rumo a uma presenca parecida com Diana", 0.86, "simulated"),
    ]
    replies = []
    for sample in samples:
        reply = core.reply(sample.text)
        store.log_event(
            voice_session_id,
            core.session_id,
            "recognized_response",
            dialogue_id=reply.dialogue_id,
            recognized_text=sample.text,
            confidence=sample.confidence,
            rzs_decision=reply.rzs_decision,
            sigma_before=reply.sigma_before,
            sigma_after=reply.sigma_after,
            response_text=reply.reply_text,
            payload={"source": "self_test", "intent": reply.intent, "focus_key": reply.focus_key},
        )
        core.store.log_voice(core.session_id, reply.dialogue_id, "speech_simulated", reply.reply_text)
        replies.append({"text": sample.text, "reply": reply.reply_text, "rzs": reply.rzs_decision})
    result = core.complete()
    store.log_session(
        voice_session_id,
        core.session_id,
        "voice_session_complete",
        mode="self_test",
        recognizer_culture="simulated",
        recognizer_name="self_test",
        payload={"session_complete": True, "recognized": len(samples), "companion": result},
    )
    final = {"voice_session_id": voice_session_id, "companion_session_id": core.session_id, "recognized": len(samples), "replies": replies}
    if details:
        print(js(final))
    else:
        print(f"DARWIN v49.9 voice self-test concluido: voice_session={voice_session_id} recognized={len(samples)}")
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Voice Presence v49.9")
    ap.add_argument("--culture", default="pt-BR")
    ap.add_argument("--min-confidence", type=float, default=0.30)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test(details=args.details)
        return 0
    root = tk.Tk()
    VoicePresenceApp(root, culture=args.culture, min_confidence=args.min_confidence)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
