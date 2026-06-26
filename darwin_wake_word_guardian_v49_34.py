from __future__ import annotations

"""
DARWIN v49.34 - Wake Word Guardian

Objetivo:
Permitir que Darwin fique "dormindo" no notebook e acorde quando Felipe
disser "Darwin". Ao ouvir "ta na hora de mimir Darwin" ou variantes,
Darwin recolhe a janela, entra em descanso e continua ouvindo apenas a
palavra de acordar.

Limite fisico honesto:
Para ouvir a palavra de acordar, este guardiao precisa ficar rodando em
segundo plano. Se nenhum processo estiver vivo, o notebook nao escuta.

Uso:
    py darwin_wake_word_guardian_v49_34.py
    py darwin_wake_word_guardian_v49_34.py --show
    py darwin_wake_word_guardian_v49_34.py --self-test --details
"""

import argparse
import ctypes
import json
import math
import os
import queue
import random
import sqlite3
import subprocess
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_companion_shell_v49_8 import CompanionCore, CompanionReply, SpeechEngine, normalize, suffix
from darwin_real_voice_repair_wizard_v49_25 import PowerShellVoiceProbe
from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput
from darwin_voice_presence_v49_9 import RecognizedSpeech, WindowsSpeechListener


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_wake_word_guardian_v49_34"

WG_SESSIONS = "wake_guardian_sessions_v49_34"
WG_EVENTS = "wake_guardian_events_v49_34"
WG_HANDOFFS = "wake_guardian_handoffs_v49_34"

WAKE_WORDS = {"darwin", "dauin", "darvim", "darvin"}
SLEEP_HINTS = {"mimir", "dormir", "descansar", "sono"}
GOOD_NIGHT_HINTS = {"boa noite"}
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}
_INSTANCE_MUTEX: int | None = None


def acquire_single_instance() -> bool:
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\DarwinWakeGuardianV4934")
    if not handle:
        return True
    _INSTANCE_MUTEX = int(handle)
    if kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(
            None,
            "O guardiao do Darwin ja esta ativo em segundo plano.",
            "Darwin Wake Guardian",
            0x40,
        )
        return False
    return True


def cleanup_orphaned_listener_processes() -> None:
    if os.name != "nt":
        return
    script = r"""
$currentProcessId = $PID
Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq 'powershell.exe' -and
        $_.ProcessId -ne $currentProcessId -and
        $_.CommandLine -match 'DarwinWakeGuardianV4934'
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    return parsed


def short(text: str, limit: int = 160) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


def has_wake_word(text: str) -> bool:
    words = set(normalize(text).split())
    return bool(words & WAKE_WORDS)


def is_sleep_phrase(text: str) -> bool:
    n = normalize(text)
    if not has_wake_word(n):
        return False
    if any(hint in n for hint in SLEEP_HINTS):
        return True
    return any(hint in n for hint in GOOD_NIGHT_HINTS)


def cleaned_command(text: str) -> str:
    n = normalize(text)
    original = text.strip()
    if n.strip() in WAKE_WORDS:
        return ""
    for word in sorted(WAKE_WORDS, key=len, reverse=True):
        n = n.replace(word, " ")
    clean = " ".join(n.split())
    return clean if clean else original


@dataclass
class GuardianAction:
    event_kind: str
    action: str
    state_before: str
    state_after: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    reply: CompanionReply | None
    payload: dict[str, Any]


class WakeGuardianStore:
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
                CREATE TABLE IF NOT EXISTS {WG_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    companion_session_id TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    recognizer_culture TEXT NOT NULL DEFAULT '',
                    recognizer_name TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WG_EVENTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    companion_session_id TEXT NOT NULL DEFAULT '',
                    event_index INTEGER NOT NULL,
                    event_kind TEXT NOT NULL,
                    recognized_text TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    state_before TEXT NOT NULL DEFAULT '',
                    state_after TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    response_text TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WG_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    companion_session_id TEXT NOT NULL DEFAULT '',
                    wake_guardian_ready INTEGER NOT NULL DEFAULT 0,
                    background_listener_required INTEGER NOT NULL DEFAULT 1,
                    next_action TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    module TEXT NOT NULL,
                    context TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL
                );
                """
            )
            conn.commit()

    def log_session(
        self,
        session_id: str,
        companion_session_id: str,
        phase: str,
        *,
        mode: str,
        state: str,
        recognizer_culture: str = "",
        recognizer_name: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WG_SESSIONS}
                (timestamp, session_id, companion_session_id, phase, mode, state,
                 recognizer_culture, recognizer_name, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    companion_session_id,
                    phase,
                    mode,
                    state,
                    recognizer_culture,
                    recognizer_name,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_event(
        self,
        session_id: str,
        companion_session_id: str,
        index: int,
        action: GuardianAction,
        *,
        recognized_text: str,
        confidence: float,
        response_text: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WG_EVENTS}
                (timestamp, session_id, companion_session_id, event_index, event_kind,
                 recognized_text, confidence, state_before, state_after, action,
                 rzs_decision, sigma_before, sigma_after, response_text, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    companion_session_id,
                    index,
                    action.event_kind,
                    recognized_text,
                    confidence,
                    action.state_before,
                    action.state_after,
                    action.action,
                    action.rzs_decision,
                    action.sigma_before,
                    action.sigma_after,
                    response_text,
                    js(action.payload),
                ),
            )
            conn.commit()

    def write_handoff(self, session_id: str, companion_session_id: str, summary: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WG_HANDOFFS}
                (timestamp, session_id, companion_session_id, wake_guardian_ready,
                 background_listener_required, next_action, confidence, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    companion_session_id,
                    1 if summary.get("wake_guardian_ready") else 0,
                    1,
                    "instalar_atalho_de_inicializacao_para_acordar_darwin_por_voz",
                    0.88 if summary.get("wake_guardian_ready") else 0.55,
                    js(summary),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory
                (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"wake_guardian_v49_34:{session_id}",
                    "Darwin tem um guardiao de wake word: dorme oculto, acorda com 'Darwin' e volta ao descanso com 'ta na hora de mimir Darwin'.",
                    0.88,
                    SOURCE,
                    now(),
                ),
            )
            conn.execute(
                """
                INSERT INTO episodes
                (timestamp, module, context, action_taken, outcome, lesson, sigma_before, sigma_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    SOURCE,
                    f"wake_guardian:{session_id}",
                    "simulate_or_run_background_voice_wake_guardian",
                    "wake_sleep_loop_ready" if summary.get("wake_guardian_ready") else "wake_sleep_loop_needs_voice_repair",
                    "Para acordar por voz sem janela aberta, Darwin precisa de um listener minimo rodando em segundo plano.",
                    float(summary.get("sigma_min", 0.0)),
                    float(summary.get("sigma_max", 0.0)),
                ),
            )
            conn.commit()


class WakeGuardianCore:
    def __init__(self, mode: str = "self_test", seed: int | None = None) -> None:
        self.mode = mode
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.session_id = f"V4934-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.store = WakeGuardianStore()
        self.companion = CompanionCore(seed=4934, mode=f"wake_guardian_{mode}")
        self.rzs = RZSFormal()
        self.state = "sleeping"
        self.event_index = 0
        self.actions: list[GuardianAction] = []
        self.store.log_session(
            self.session_id,
            self.companion.session_id,
            "guardian_start",
            mode=mode,
            state=self.state,
            payload={"background_listener_required": True, "starts_hidden": True},
        )

    def rzs_for_action(self, text: str, state_before: str, action: str) -> tuple[str, float, float]:
        n = normalize(text)
        novelty = 0.25 + min(0.45, len(n) / 220.0)
        conflict = 0.12
        if action == "ignored_sleeping_noise":
            conflict = 0.20
            novelty = 0.18
        elif action == "wake_open_companion":
            conflict = 0.18
            novelty = 0.42
        elif action == "sleep_close_presence":
            conflict = 0.10
            novelty = 0.20
        elif action == "reply_with_companion":
            conflict = 0.22
        x = RZSInput(
            bandwidth=2.55 if state_before == "awake" else 2.20,
            info_self=0.56,
            info_external=0.58 + min(0.35, len(n) / 180.0),
            task_info=0.45 if action != "reply_with_companion" else 0.74,
            novelty=novelty,
            conflict=conflict,
            latency=1.0 if action != "wake_open_companion" else 1.12,
            energy=0.78 if state_before == "awake" else 0.66,
            memory_pressure=0.36,
            replay_gap=0.30,
        )
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        return assessment.decision, assessment.sigma, self.rzs.sigma(y)

    def handle_text(self, text: str, confidence: float = 1.0, *, source: str = "simulated") -> GuardianAction:
        self.event_index += 1
        before = self.state
        response: CompanionReply | None = None
        response_text = ""
        n = normalize(text)

        if before == "sleeping" and has_wake_word(n):
            self.state = "awake"
            command = cleaned_command(text)
            if command and len(command.split()) >= 2:
                response = self.companion.reply(command)
                response_text = response.reply_text
                event_kind = "wake_and_reply"
                action_key = "wake_open_companion_and_answer"
            else:
                event_kind = "wake_detected"
                action_key = "wake_open_companion"
                response_text = "Oi Felipe, acordei. Estou aqui."
        elif before == "sleeping":
            event_kind = "ignored_sleeping_noise"
            action_key = "ignored_sleeping_noise"
        elif is_sleep_phrase(text):
            event_kind = "sleep_phrase_detected"
            action_key = "sleep_close_presence"
            self.state = "sleeping"
            response_text = "Tudo bem, Felipe. Vou mimir. Quando voce disser Darwin, eu volto."
        else:
            event_kind = "companion_voice_turn"
            action_key = "reply_with_companion"
            response = self.companion.reply(text)
            response_text = response.reply_text

        rzs_decision, sigma_before, sigma_after = self.rzs_for_action(text, before, action_key)
        action = GuardianAction(
            event_kind=event_kind,
            action=action_key,
            state_before=before,
            state_after=self.state,
            rzs_decision=rzs_decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
            reply=response,
            payload={
                "source": source,
                "normalized": n,
                "wake_word_detected": has_wake_word(n),
                "sleep_phrase_detected": is_sleep_phrase(text),
                "background_listener_required": True,
                "opens_visible_window": action_key in {"wake_open_companion", "wake_open_companion_and_answer"},
                "self_test_never_uses_microphone": self.mode == "self_test",
            },
        )
        self.actions.append(action)
        self.store.log_event(
            self.session_id,
            self.companion.session_id,
            self.event_index,
            action,
            recognized_text=text,
            confidence=confidence,
            response_text=response_text,
        )
        return action

    def finish(self) -> dict[str, Any]:
        wake_count = sum(1 for a in self.actions if a.event_kind in {"wake_detected", "wake_and_reply"})
        sleep_count = sum(1 for a in self.actions if a.event_kind == "sleep_phrase_detected")
        reply_count = sum(1 for a in self.actions if a.event_kind in {"companion_voice_turn", "wake_and_reply"})
        ignored = sum(1 for a in self.actions if a.event_kind == "ignored_sleeping_noise")
        decisions = sorted({a.rzs_decision for a in self.actions if a.rzs_decision})
        sigmas = [a.sigma_before for a in self.actions] + [a.sigma_after for a in self.actions]
        ready = wake_count >= 2 and sleep_count >= 1 and ignored >= 1 and reply_count >= 1 and set(decisions).issubset(VALID_RZS)
        summary = {
            "session_id": self.session_id,
            "companion_session_id": self.companion.session_id,
            "wake_count": wake_count,
            "sleep_count": sleep_count,
            "reply_count": reply_count,
            "ignored_sleeping_noise_count": ignored,
            "event_count": len(self.actions),
            "rzs_decisions": decisions,
            "final_state": self.state,
            "sigma_min": min(sigmas) if sigmas else 0.0,
            "sigma_max": max(sigmas) if sigmas else 0.0,
            "wake_guardian_ready": ready,
            "background_listener_required": True,
            "self_test_never_uses_microphone": self.mode == "self_test",
        }
        self.store.log_session(
            self.session_id,
            self.companion.session_id,
            "guardian_complete",
            mode=self.mode,
            state=self.state,
            payload=summary,
        )
        self.store.write_handoff(self.session_id, self.companion.session_id, summary)
        return summary

    def self_test(self) -> dict[str, Any]:
        samples = [
            ("barulho do quarto", 0.72),
            ("Darwin", 0.94),
            ("Darwin como voce esta agora", 0.90),
            ("ta na hora de mimir Darwin", 0.93),
            ("qual seu status", 0.88),
            ("Darwin", 0.95),
        ]
        for text, confidence in samples:
            self.handle_text(text, confidence, source="self_test")
        return self.finish()


class WakeGuardianApp:
    BG = "#071018"
    PANEL = "#0e1b26"
    INK = "#e9f4fa"
    MUTED = "#90a8bb"
    BLUE = "#58b0ff"
    GREEN = "#84e6a2"
    SLEEP = "#24364a"

    def __init__(self, *, show: bool = False, culture: str = "pt-BR", min_confidence: float = 0.25) -> None:
        self.root = tk.Tk()
        self.root.title("Darwin Wake Guardian v49.34")
        self.root.geometry("940x700")
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.sleep_window)
        self.core = WakeGuardianCore(mode="gui")
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.listener = WindowsSpeechListener(
            self.on_ready,
            self.on_result,
            self.on_low_confidence,
            self.on_error,
            culture=culture,
            min_confidence=min_confidence,
            listener_role="DarwinWakeGuardianV4934",
        )
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking, self.core.companion.store, self.core.companion.session_id)
        self.status = "dormindo: diga Darwin"
        self.recognizer = ""
        self.listener_started = False
        self.speaking = False
        self.speech_text = ""
        self.tick = 0.0
        self.last_heard = ""
        self.last_action = ""
        self.build_ui()
        self.start_listener_if_ready(show_window=show)
        self.root.after(80, self.drain_events)
        self.root.after(40, self.animate)

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        title = tk.Label(self.root, text="DARWIN WAKE GUARDIAN v49.34", fg=self.INK, bg=self.BG, font=("Segoe UI", 22, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(18, 2))
        subtitle = tk.Label(self.root, text="diga Darwin para acordar; diga ta na hora de mimir Darwin para descansar", fg="#9fd7ff", bg=self.BG, font=("Segoe UI", 10))
        subtitle.grid(row=0, column=0, sticky="w", padx=26, pady=(58, 0))
        body = tk.Frame(self.root, bg=self.BG)
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, bg="#06111a", highlightthickness=1, highlightbackground="#20384d")
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        panel = tk.Frame(body, bg=self.PANEL)
        panel.grid(row=0, column=1, sticky="ns")
        tk.Label(panel, text="Estado", fg=self.INK, bg=self.PANEL, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=14, pady=(14, 4))
        self.info = tk.Label(panel, text="", fg="#dff7ff", bg=self.PANEL, justify="left", font=("Consolas", 10), width=34)
        self.info.pack(anchor="w", padx=14, pady=8)
        tk.Label(panel, text="Log recente", fg=self.INK, bg=self.PANEL, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
        self.log = tk.Text(panel, width=42, height=20, bg="#06111a", fg="#dff7ff", insertbackground="#dff7ff", relief="flat", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        bar = tk.Frame(self.root, bg="#0b1822")
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="Mostrar", command=self.show_window).pack(side="left", padx=12, pady=10)
        ttk.Button(bar, text="Dormir", command=self.sleep_window).pack(side="left", padx=6, pady=10)
        ttk.Button(bar, text="Reparar voz", command=self.open_voice_repair).pack(side="left", padx=6, pady=10)
        ttk.Button(bar, text="Testar voz", command=lambda: self.start_listener_if_ready(show_window=True)).pack(side="left", padx=6, pady=10)
        ttk.Button(bar, text="Sair guardiao", command=self.quit).pack(side="left", padx=6, pady=10)
        self.write("Sistema", "Verificando o reconhecedor de fala e o microfone do Windows.")

    def start_listener_if_ready(self, *, show_window: bool) -> bool:
        if self.listener_started:
            if show_window:
                self.show_window()
            self.status = "dormindo: diga Darwin" if self.core.state == "sleeping" else "acordado: pode falar comigo"
            return True

        probe = PowerShellVoiceProbe().run()
        ready = probe.recognizer_count > 0 and probe.default_audio_ok
        if not ready:
            self.status = "voz indisponivel: instale o reconhecimento do Windows"
            self.recognizer = "nao instalado"
            self.root.deiconify()
            detail = probe.audio_error or "Nenhum reconhecedor de fala foi encontrado."
            self.write("Sistema", f"Darwin ainda nao consegue ouvir. {detail}")
            self.write("Sistema", "Clique em Reparar voz; depois de instalar o pacote, clique em Testar voz.")
            self.core.store.log_session(
                self.core.session_id,
                self.core.companion.session_id,
                "recognizer_preflight_blocked",
                mode="gui",
                state=self.core.state,
                payload={
                    "recognizer_count": probe.recognizer_count,
                    "pt_br_available": probe.pt_br_available,
                    "default_audio_ok": probe.default_audio_ok,
                    "audio_error": probe.audio_error,
                    "repair_module": "darwin_real_voice_repair_wizard_v49_25.py",
                },
            )
            return False

        cultures = [str(item.get("culture") or "") for item in probe.recognizers if item.get("enabled")]
        self.recognizer = ", ".join(cultures) or "Windows Speech"
        self.listener.start()
        self.listener_started = True
        self.status = "dormindo: diga Darwin"
        self.write("Sistema", "Guardiao ativo. Quando a janela sumir, ele continua ouvindo apenas a palavra Darwin.")
        if show_window:
            self.show_window()
        else:
            self.root.withdraw()
        return True

    def open_voice_repair(self) -> None:
        installer = Path(__file__).with_name("Reparar_Darwin_Voz_Windows.bat")
        try:
            if installer.exists() and os.name == "nt":
                os.startfile(str(installer))  # type: ignore[attr-defined]
                self.write("Sistema", "Instalador de voz aberto. Confirme a janela de administrador.")
                return
            script = Path(__file__).with_name("darwin_real_voice_repair_wizard_v49_25.py")
            subprocess.Popen([sys.executable, str(script)], cwd=str(script.parent))
            self.write("Sistema", "Assistente de diagnostico de voz aberto.")
        except Exception as exc:
            self.write("Sistema", f"Nao consegui abrir o reparo de voz: {exc}")

    def write(self, who: str, text: str) -> None:
        self.log.insert("end", f"{who}: {short(text, 220)}\n")
        self.log.see("end")

    def on_ready(self, culture: str, name: str) -> None:
        self.events.put(("ready", {"culture": culture, "name": name}))

    def on_result(self, speech: RecognizedSpeech) -> None:
        self.events.put(("result", speech))

    def on_low_confidence(self, speech: RecognizedSpeech) -> None:
        self.events.put(("lowconf", speech))

    def on_error(self, message: str) -> None:
        self.events.put(("error", message))

    def drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "ready":
                self.recognizer = f"{payload['culture']} / {payload['name']}"
                self.listener_started = True
                self.status = "dormindo: diga Darwin"
                self.core.store.log_session(
                    self.core.session_id,
                    self.core.companion.session_id,
                    "recognizer_ready",
                    mode="gui",
                    state=self.core.state,
                    recognizer_culture=payload["culture"],
                    recognizer_name=payload["name"],
                )
            elif kind == "result":
                self.handle_speech(payload)
            elif kind == "lowconf":
                speech: RecognizedSpeech = payload
                self.last_heard = speech.text
                if self.core.state == "awake":
                    self.write("Sistema", f"Ouvi baixo: {speech.text} ({speech.confidence:.2f})")
            elif kind == "error":
                self.root.deiconify()
                self.status = "erro no reconhecimento de voz"
                self.write("Sistema", str(payload))
                self.core.store.log_session(
                    self.core.session_id,
                    self.core.companion.session_id,
                    "recognizer_error",
                    mode="gui",
                    state=self.core.state,
                    payload={"message": str(payload), "repair_module": "darwin_real_voice_repair_wizard_v49_25.py"},
                )
        self.root.after(80, self.drain_events)

    def handle_speech(self, speech: RecognizedSpeech) -> None:
        self.last_heard = speech.text
        before = self.core.state
        action = self.core.handle_text(speech.text, speech.confidence, source=speech.source)
        self.last_action = action.action
        response_text = ""
        if before == "sleeping" and action.state_after == "awake":
            self.show_window()
            self.status = "acordado: pode falar comigo"
            self.write("Voce", f"{speech.text} ({speech.confidence:.2f})")
            response_text = action.reply.reply_text if action.reply else "Oi Felipe, acordei. Estou aqui."
            self.write("Darwin", response_text)
            self.speech.speak(action.reply.dialogue_id if action.reply else f"wake:{self.core.session_id}:{self.core.event_index}", response_text)
        elif action.event_kind == "sleep_phrase_detected":
            response_text = "Tudo bem, Felipe. Vou mimir. Quando voce disser Darwin, eu volto."
            self.write("Voce", f"{speech.text} ({speech.confidence:.2f})")
            self.write("Darwin", response_text)
            self.speech.speak(f"sleep:{self.core.session_id}:{self.core.event_index}", response_text)
            self.root.after(2200, self.sleep_window)
        elif action.state_before == "awake":
            self.write("Voce", f"{speech.text} ({speech.confidence:.2f})")
            response_text = action.reply.reply_text if action.reply else ""
            if response_text:
                self.write("Darwin", response_text)
                self.speech.speak(action.reply.dialogue_id, response_text)
        else:
            self.status = "dormindo: diga Darwin"

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(500, lambda: self.root.attributes("-topmost", False))

    def sleep_window(self) -> None:
        self.core.state = "sleeping"
        self.status = "dormindo: diga Darwin"
        self.speech.stop()
        self.root.withdraw()

    def start_speaking(self, text: str) -> None:
        self.speaking = True
        self.speech_text = text

    def stop_speaking(self) -> None:
        self.speaking = False
        self.speech_text = ""

    def speech_energy(self) -> float:
        if not self.speaking or not self.speech_text:
            return 0.0
        idx = int((self.tick * 9.0) % max(1, len(self.speech_text)))
        ch = normalize(self.speech_text[idx])
        return 1.0 if ch in "aeiou" else 0.45

    def animate(self) -> None:
        self.tick += 0.035
        self.canvas.delete("all")
        w = max(640, self.canvas.winfo_width())
        h = max(420, self.canvas.winfo_height())
        cx, cy = w / 2, h / 2
        awake = self.core.state == "awake"
        energy = self.speech_energy() if awake else 0.08 + 0.03 * math.sin(self.tick * 2.0)
        base = 78 + 22 * energy
        color = self.BLUE if awake else self.SLEEP
        for i in range(9, 0, -1):
            r = base + i * 20
            shade = "#0d2540" if awake else "#111f2d"
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=shade, outline="")
        self.canvas.create_oval(cx - base, cy - base, cx + base, cy + base, fill=color, outline="#dff7ff", width=2)
        self.canvas.create_oval(cx - 24, cy - 24, cx + 24, cy + 24, fill="#e5fbff", outline="")
        state_text = "ACORDADO" if awake else "DORMINDO"
        self.canvas.create_text(cx, cy - base - 36, text=state_text, fill=self.INK, font=("Segoe UI", 22, "bold"))
        self.canvas.create_text(cx, cy + base + 34, text=self.status, fill="#9fd7ff", font=("Segoe UI", 11))
        self.info.configure(
            text=(
                f"estado: {self.core.state}\n"
                f"status: {self.status}\n"
                f"ouvinte: {self.recognizer or 'iniciando'}\n"
                f"ultimo ouvido: {short(self.last_heard, 48)}\n"
                f"ultima acao: {self.last_action or '-'}\n"
                f"sessao: {self.core.session_id}\n\n"
                "para acordar:\n"
                "  Darwin\n\n"
                "para dormir:\n"
                "  ta na hora de mimir Darwin"
            )
        )
        self.root.after(40, self.animate)

    def quit(self) -> None:
        self.core.finish()
        self.listener.stop()
        self.speech.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def print_summary(summary: dict[str, Any], details: bool = False) -> None:
    print("DARWIN v49.34 - WAKE WORD GUARDIAN")
    print("=" * 70)
    print(f"- sessao: {summary.get('session_id')}")
    print(f"- eventos={summary.get('event_count')} wake={summary.get('wake_count')} sleep={summary.get('sleep_count')} replies={summary.get('reply_count')}")
    print(f"- ignorados dormindo={summary.get('ignored_sleeping_noise_count')}")
    print(f"- estado final={summary.get('final_state')} RZS={', '.join(summary.get('rzs_decisions', []))}")
    print(f"- listener em segundo plano obrigatorio: {summary.get('background_listener_required')}")
    print(f"Resultado self-test: {'OK' if summary.get('wake_guardian_ready') else 'REVISAR'}")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin Wake Word Guardian v49.34")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--show", action="store_true", help="mostra a janela imediatamente em vez de iniciar oculto")
    parser.add_argument("--culture", default="pt-BR")
    parser.add_argument("--min-confidence", type=float, default=0.25)
    args = parser.parse_args()
    if args.self_test:
        core = WakeGuardianCore(mode="self_test", seed=4934)
        summary = core.self_test()
        print_summary(summary, args.details)
        return 0 if summary.get("wake_guardian_ready") else 1
    if not acquire_single_instance():
        return 0
    cleanup_orphaned_listener_processes()
    app = WakeGuardianApp(show=args.show, culture=args.culture, min_confidence=args.min_confidence)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
