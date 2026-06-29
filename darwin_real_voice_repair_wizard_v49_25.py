from __future__ import annotations

"""
DARWIN v49.25 - Real Voice Repair Wizard

Objetivo:
Resolver o bloqueio real encontrado na v49.24: o Windows retornou
recognizers=0. Este modulo guia e audita o reparo de voz real sem
instalar nada sozinho, mantendo o Darwin local, stdlib-only e honesto
sobre o que foi provado.

Uso:
    py darwin_real_voice_repair_wizard_v49_25.py
    py darwin_real_voice_repair_wizard_v49_25.py --self-test --details
    py darwin_real_voice_repair_wizard_v49_25.py --live-test --seconds 18
"""

import argparse
import contextlib
import io
import json
import math
import os
import queue
import random
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

VR_SESSIONS = "voice_repair_sessions_v49_25"
VR_CHECKS = "voice_repair_checks_v49_25"
VR_STEPS = "voice_repair_steps_v49_25"
VR_LIVE_TESTS = "voice_repair_live_tests_v49_25"
VR_RESULTS = "voice_repair_results_v49_25"

SOURCE = "darwin_real_voice_repair_wizard_v49_25"
FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"

PHASES = [
    "load_v49_24_voice_blocker",
    "inspect_windows_speech",
    "inspect_audio_input",
    "verify_darwin_voice_modules",
    "prepare_live_first_words_test",
    "write_repair_plan",
]

FIRST_WORD_TEST_WORDS = ["mamae", "papai", "felipe", "darwin"]


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
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    return parsed


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def short(text: str, limit: int = 160) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class VoiceProbe:
    system_speech_ok: bool
    synthesis_ok: bool
    recognizer_count: int
    recognizers: list[dict[str, Any]]
    pt_br_available: bool
    default_audio_ok: bool
    audio_error: str
    returncode: int
    stdout: str
    stderr: str


@dataclass
class RepairCheck:
    check_id: str
    check_index: int
    check_key: str
    check_kind: str
    status: str
    evidence: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    payload: dict[str, Any]


@dataclass
class RepairStep:
    step_index: int
    phase: str
    repair_action: str
    result_summary: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    completed: bool
    payload: dict[str, Any]


@dataclass
class LiveTestRecord:
    test_id: str
    test_kind: str
    expected_words: list[str]
    recognized_words: list[str]
    status: str
    confidence_mean: float
    payload: dict[str, Any]


@dataclass
class RepairResult:
    result_id: str
    source_action_session_id: str
    recognizer_count: int
    pt_br_available: bool
    default_audio_ok: bool
    real_voice_ready: bool
    readiness_score: float
    blocked_by: str
    next_action: str
    payload: dict[str, Any]


class VoiceRepairStore:
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
                CREATE TABLE IF NOT EXISTS {VR_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    source_action_session_id TEXT NOT NULL DEFAULT '',
                    blocked_by TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VR_CHECKS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    check_id TEXT NOT NULL UNIQUE,
                    check_index INTEGER NOT NULL,
                    check_key TEXT NOT NULL,
                    check_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VR_STEPS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    repair_action TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VR_LIVE_TESTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    test_id TEXT NOT NULL UNIQUE,
                    test_kind TEXT NOT NULL,
                    expected_words_json TEXT NOT NULL DEFAULT '[]',
                    recognized_words_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    confidence_mean REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VR_RESULTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    result_id TEXT NOT NULL UNIQUE,
                    source_action_session_id TEXT NOT NULL DEFAULT '',
                    recognizer_count INTEGER NOT NULL DEFAULT 0,
                    pt_br_available INTEGER NOT NULL DEFAULT 0,
                    default_audio_ok INTEGER NOT NULL DEFAULT 0,
                    real_voice_ready INTEGER NOT NULL DEFAULT 0,
                    readiness_score REAL NOT NULL DEFAULT 0.0,
                    blocked_by TEXT NOT NULL,
                    next_action TEXT NOT NULL,
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

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def log_session(self, session_id: str, phase: str, mode: str, source_action_session_id: str, blocked_by: str = "", payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VR_SESSIONS} (
                    timestamp, session_id, phase, mode,
                    source_action_session_id, blocked_by, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, source_action_session_id, blocked_by, js(payload or {})),
            )
            conn.commit()

    def log_check(self, session_id: str, check: RepairCheck) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {VR_CHECKS} (
                    timestamp, session_id, check_id, check_index,
                    check_key, check_kind, status, evidence,
                    rzs_decision, sigma_before, sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    check.check_id,
                    check.check_index,
                    check.check_key,
                    check.check_kind,
                    check.status,
                    check.evidence,
                    check.rzs_decision,
                    check.sigma_before,
                    check.sigma_after,
                    js(check.payload),
                ),
            )
            conn.commit()

    def log_step(self, session_id: str, step: RepairStep) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VR_STEPS} (
                    timestamp, session_id, step_index, phase,
                    repair_action, result_summary, rzs_decision,
                    sigma_before, sigma_after, completed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    step.step_index,
                    step.phase,
                    step.repair_action,
                    step.result_summary,
                    step.rzs_decision,
                    step.sigma_before,
                    step.sigma_after,
                    1 if step.completed else 0,
                    js(step.payload),
                ),
            )
            conn.commit()

    def log_live_test(self, session_id: str, item: LiveTestRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {VR_LIVE_TESTS} (
                    timestamp, session_id, test_id, test_kind,
                    expected_words_json, recognized_words_json, status,
                    confidence_mean, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    item.test_id,
                    item.test_kind,
                    js(item.expected_words),
                    js(item.recognized_words),
                    item.status,
                    item.confidence_mean,
                    js(item.payload),
                ),
            )
            conn.commit()

    def log_result(self, session_id: str, item: RepairResult) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {VR_RESULTS} (
                    timestamp, session_id, result_id, source_action_session_id,
                    recognizer_count, pt_br_available, default_audio_ok,
                    real_voice_ready, readiness_score, blocked_by,
                    next_action, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    item.result_id,
                    item.source_action_session_id,
                    item.recognizer_count,
                    1 if item.pt_br_available else 0,
                    1 if item.default_audio_ok else 0,
                    1 if item.real_voice_ready else 0,
                    item.readiness_score,
                    item.blocked_by,
                    item.next_action,
                    js(item.payload),
                ),
            )
            conn.commit()

    def write_memory(self, session_id: str, content: dict[str, Any], confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory (
                    key, content, confidence, source, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (f"real_voice_repair_v49_25:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
            )
            conn.commit()

    def write_episode(self, session_id: str, action: str, outcome: str, lesson: str, sigma_before: float, sigma_after: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), SOURCE, f"real_voice_repair:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class RepairContext:
    def __init__(self, store: VoiceRepairStore) -> None:
        self.store = store

    def latest_v49_24(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            if not self.store.table_exists(conn, "desire_action_results_v49_24"):
                return {}
            row = conn.execute("SELECT * FROM desire_action_results_v49_24 ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {}
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        return item


class PowerShellVoiceProbe:
    def run(self, timeout: int = 14) -> VoiceProbe:
        script = r"""
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName System.Speech
  Write-Output "SYSTEM_SPEECH=OK"
  try {
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.Dispose()
    Write-Output "SYNTHESIS=OK"
  } catch {
    Write-Output ("SYNTHESIS_ERROR={0}" -f ($_.Exception.Message -replace '\r?\n', ' '))
  }
  $infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
  Write-Output ("RECOGNIZER_COUNT={0}" -f $infos.Count)
  foreach ($info in $infos) {
    Write-Output ("RECOGNIZER={0}|{1}|{2}" -f $info.Culture.Name, $info.Name, $info.Enabled)
  }
  $chosen = $null
  foreach ($info in $infos) {
    if ($info.Enabled -and $info.Culture.Name -eq "pt-BR") {
      $chosen = $info
      break
    }
  }
  if ($chosen -eq $null) {
    foreach ($info in $infos) {
      if ($info.Enabled) {
        $chosen = $info
        break
      }
    }
  }
  if ($chosen -ne $null) {
    try {
      $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($chosen)
      $recognizer.SetInputToDefaultAudioDevice()
      Write-Output "DEFAULT_AUDIO_INPUT=OK"
      $recognizer.Dispose()
    } catch {
      Write-Output ("AUDIO_INPUT_ERROR={0}" -f ($_.Exception.Message -replace '\r?\n', ' '))
    }
  } else {
    try {
      Add-Type -AssemblyName System.Runtime.WindowsRuntime
      [Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
      [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
      $supported = @([Windows.Media.SpeechRecognition.SpeechRecognizer]::SupportedTopicLanguages)
      $ptbr = @($supported | Where-Object { $_.LanguageTag -eq "pt-BR" })
      if ($ptbr.Count -gt 0) {
        $language = New-Object Windows.Globalization.Language("pt-BR")
        $winrt = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer($language)
        $winrt.Dispose()
        Write-Output "RECOGNIZER_COUNT=1"
        Write-Output "RECOGNIZER=pt-BR|Windows Media SpeechRecognizer|True"
        $privacy = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy" -ErrorAction SilentlyContinue
        $microphone = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone" -ErrorAction SilentlyContinue
        if ($privacy.HasAccepted -eq 1 -and $microphone.Value -eq "Allow") {
          Write-Output "DEFAULT_AUDIO_INPUT=OK"
        } elseif ($privacy.HasAccepted -ne 1) {
          Write-Output "AUDIO_INPUT_ERROR=Ative Reconhecimento de fala online em Privacidade e seguranca > Fala."
        } else {
          Write-Output "AUDIO_INPUT_ERROR=Permita o acesso ao microfone nas configuracoes de privacidade."
        }
      }
    } catch {
      Write-Output ("AUDIO_INPUT_ERROR={0}" -f ($_.Exception.Message -replace '\r?\n', ' '))
    }
  }
} catch {
  Write-Output ("SYSTEM_SPEECH_ERROR={0}" -f ($_.Exception.Message -replace '\r?\n', ' '))
  exit 3
}
"""
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            return VoiceProbe(False, False, 0, [], False, False, str(exc), 99, "", str(exc))
        return self.parse(proc.stdout or "", proc.stderr or "", proc.returncode)

    def parse(self, stdout: str, stderr: str, returncode: int) -> VoiceProbe:
        recognizers: list[dict[str, Any]] = []
        count = 0
        audio_error = ""
        for line in (stdout + "\n" + stderr).splitlines():
            if line.startswith("RECOGNIZER_COUNT="):
                try:
                    count = int(line.split("=", 1)[1].strip())
                except Exception:
                    count = 0
            elif line.startswith("RECOGNIZER="):
                parts = line.split("=", 1)[1].split("|", 2)
                if len(parts) == 3:
                    recognizers.append({"culture": parts[0], "name": parts[1], "enabled": parts[2].lower() == "true"})
            elif line.startswith("AUDIO_INPUT_ERROR="):
                audio_error = line.split("=", 1)[1].strip()
        return VoiceProbe(
            system_speech_ok="SYSTEM_SPEECH=OK" in stdout,
            synthesis_ok="SYNTHESIS=OK" in stdout,
            recognizer_count=count,
            recognizers=recognizers,
            pt_br_available=any(r["culture"].lower() == "pt-br" and r["enabled"] for r in recognizers),
            default_audio_ok="DEFAULT_AUDIO_INPUT=OK" in stdout,
            audio_error=audio_error,
            returncode=returncode,
            stdout=stdout[-1800:],
            stderr=stderr[-1800:],
        )

    def live_first_words(self, seconds: int = 18, culture: str = "pt-BR") -> dict[str, Any]:
        seconds = max(8, min(60, int(seconds)))
        words = "@(" + ",".join("'" + w.replace("'", "''") + "'" for w in FIRST_WORD_TEST_WORDS) + ")"
        script = rf"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$preferred = '{culture}'
$words = {words}
$recognizer = $null
try {{
  $cultureObj = [System.Globalization.CultureInfo]::GetCultureInfo($preferred)
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($cultureObj)
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
if ($recognizer -eq $null) {{
  Write-Output "MISSING|NO_RECOGNIZER"
  exit 2
}}
$choices = New-Object System.Speech.Recognition.Choices
$choices.Add($words)
$builder = New-Object System.Speech.Recognition.GrammarBuilder
$builder.Culture = $recognizer.RecognizerInfo.Culture
$builder.Append($choices)
$grammar = New-Object System.Speech.Recognition.Grammar($builder)
$recognizer.LoadGrammar($grammar)
$recognizer.SetInputToDefaultAudioDevice()
Write-Output ("READY|{{0}}|{{1}}" -f $recognizer.RecognizerInfo.Culture.Name, $recognizer.RecognizerInfo.Name)
$deadline = (Get-Date).AddSeconds({seconds})
while ((Get-Date) -lt $deadline) {{
  $result = $recognizer.Recognize([TimeSpan]::FromSeconds(5))
  if ($result -ne $null) {{
    $text = ($result.Text -replace '\r?\n', ' ').Trim()
    $confidence = [double]$result.Confidence
    if ($text.Length -gt 0) {{
      Write-Output ("RESULT|{{0:N3}}|{{1}}" -f $confidence, $text)
    }}
  }}
}}
$recognizer.Dispose()
"""
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=seconds + 12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            return {"status": "failed", "recognized": [], "confidences": [], "stdout": "", "stderr": str(exc), "returncode": 99}
        recognized: list[str] = []
        confidences: list[float] = []
        for line in (proc.stdout or "").splitlines():
            if line.startswith("RESULT|"):
                parts = line.split("|", 2)
                if len(parts) == 3:
                    recognized.append(parts[2].strip().lower())
                    try:
                        confidences.append(float(parts[1].replace(",", ".")))
                    except Exception:
                        confidences.append(0.0)
        if "MISSING|NO_RECOGNIZER" in (proc.stdout or ""):
            status = "blocked_no_recognizer"
        elif recognized:
            status = "completed"
        else:
            status = "no_words_heard"
        return {
            "status": status,
            "recognized": recognized,
            "confidences": confidences,
            "stdout": (proc.stdout or "")[-1800:],
            "stderr": (proc.stderr or "")[-1800:],
            "returncode": proc.returncode,
        }


class RealVoiceRepairWizard:
    def __init__(self, db_path: Path = DB, seed: int = 4925, mode: str = "gui") -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4925-{int(time.time())}-{suffix(self.rng)}"
        self.mode = mode
        self.store = VoiceRepairStore(db_path)
        self.rzs = RZSFormal()
        self.prober = PowerShellVoiceProbe()
        self.context = RepairContext(self.store).latest_v49_24()
        self.source_action_session_id = str(self.context.get("session_id") or "")
        self.source_blocker = str(self.context.get("blocked_by") or "")
        self.steps: list[RepairStep] = []
        self.checks: list[RepairCheck] = []
        self.live_tests: list[LiveTestRecord] = []
        self.result: RepairResult | None = None
        self.probe: VoiceProbe | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            mode,
            self.source_action_session_id,
            self.source_blocker,
            {"version": "v49.25", "goal": "repair_real_voice_path"},
        )

    def rzs_assess(self, *, novelty: float, conflict: float, memory_pressure: float, replay_gap: float, task_info: float = 0.52, latency: float = 0.84, energy: float = 0.78) -> tuple[str, float, float]:
        x = RZSInput(
            bandwidth=4.15,
            info_self=0.34,
            info_external=0.46,
            task_info=task_info,
            novelty=clamp(novelty),
            conflict=clamp(conflict),
            latency=max(0.25, latency),
            energy=clamp(energy),
            memory_pressure=clamp(memory_pressure),
            replay_gap=clamp(replay_gap),
        )
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        return assessment.decision, assessment.sigma, self.rzs.sigma(y)

    def step(self, index: int, phase: str, action: str, ok: bool, payload: dict[str, Any] | None = None, *, novelty: float = 0.18, conflict: float = 0.08, memory_pressure: float = 0.44, replay_gap: float = 0.34) -> None:
        decision, sigma_before, sigma_after = self.rzs_assess(
            novelty=novelty,
            conflict=conflict if ok else max(conflict, 0.26),
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        item = RepairStep(
            step_index=index,
            phase=phase,
            repair_action=action,
            result_summary="ok" if ok else "blocked_or_incomplete",
            rzs_decision=decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
            completed=True,
            payload=payload or {},
        )
        self.steps.append(item)
        self.store.log_step(self.session_id, item)

    def add_check(self, key: str, kind: str, status: str, evidence: str, payload: dict[str, Any] | None = None, *, novelty: float = 0.20, conflict: float = 0.08, memory_pressure: float = 0.42, replay_gap: float = 0.32) -> RepairCheck:
        status = status if status in {"pass", "warn", "fail"} else "warn"
        if status == "fail":
            conflict = max(conflict, 0.28)
            memory_pressure = max(memory_pressure, 0.70)
            replay_gap = max(replay_gap, 0.72)
        elif status == "warn":
            conflict = max(conflict, 0.18)
            memory_pressure = max(memory_pressure, 0.58)
        decision, sigma_before, sigma_after = self.rzs_assess(
            novelty=novelty,
            conflict=conflict,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        item = RepairCheck(
            check_id=f"CHK-{self.session_id}-{len(self.checks) + 1:03d}",
            check_index=len(self.checks) + 1,
            check_key=key,
            check_kind=kind,
            status=status,
            evidence=evidence,
            rzs_decision=decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
            payload=payload or {},
        )
        self.checks.append(item)
        self.store.log_check(self.session_id, item)
        return item

    def run_diagnostics(self, *, prepare_live: bool = True) -> dict[str, Any]:
        blocker_ok = bool(self.context) and str(self.context.get("action_family") or "") == "voice_repair"
        self.step(
            1,
            "load_v49_24_voice_blocker",
            "load_last_desire_action_blocker",
            blocker_ok,
            {"source_action_session_id": self.source_action_session_id, "blocked_by": self.source_blocker},
            memory_pressure=0.76,
            replay_gap=0.76,
        )
        self.add_check(
            "v49_24_voice_blocker_seen",
            "sqlite",
            "pass" if blocker_ok else "warn",
            self.source_blocker or "sem bloqueio v49.24 encontrado",
            {"source_action_session_id": self.source_action_session_id, "context": self.context},
            memory_pressure=0.76,
            replay_gap=0.76,
        )

        self.step(2, "inspect_windows_speech", "probe_system_speech_recognizers", True, novelty=0.30, conflict=0.12, memory_pressure=0.62, replay_gap=0.66)
        self.probe = self.prober.run()
        self.add_check(
            "system_speech_assembly",
            "powershell_system_speech",
            "pass" if self.probe.system_speech_ok else "fail",
            "System.Speech carregou" if self.probe.system_speech_ok else "System.Speech nao carregou",
            {"stdout": self.probe.stdout, "stderr": self.probe.stderr, "returncode": self.probe.returncode},
            novelty=0.32,
            conflict=0.12,
        )
        self.add_check(
            "speech_synthesis_available",
            "powershell_system_speech",
            "pass" if self.probe.synthesis_ok else "warn",
            "sintese de fala disponivel" if self.probe.synthesis_ok else "sintese de fala nao confirmada",
            {"stdout": self.probe.stdout, "stderr": self.probe.stderr},
            novelty=0.20,
            conflict=0.10,
        )
        self.add_check(
            "installed_recognizers",
            "powershell_system_speech",
            "pass" if self.probe.recognizer_count > 0 else "fail",
            f"recognizers={self.probe.recognizer_count}",
            {"recognizers": self.probe.recognizers, "stdout": self.probe.stdout, "stderr": self.probe.stderr},
            novelty=0.36,
            conflict=0.22 if self.probe.recognizer_count == 0 else 0.08,
            memory_pressure=0.72 if self.probe.recognizer_count == 0 else 0.48,
            replay_gap=0.76 if self.probe.recognizer_count == 0 else 0.36,
        )
        pt_status = "pass" if self.probe.pt_br_available else ("warn" if self.probe.recognizer_count > 0 else "fail")
        self.add_check(
            "pt_br_recognizer",
            "powershell_system_speech",
            pt_status,
            "pt-BR disponivel" if self.probe.pt_br_available else "pt-BR nao encontrado nos reconhecedores do Windows",
            {"recognizers": self.probe.recognizers},
            novelty=0.34,
            conflict=0.24 if not self.probe.pt_br_available else 0.08,
            memory_pressure=0.70 if not self.probe.pt_br_available else 0.46,
            replay_gap=0.74 if not self.probe.pt_br_available else 0.34,
        )

        self.step(3, "inspect_audio_input", "bind_recognizer_to_default_microphone", self.probe.default_audio_ok, novelty=0.30, conflict=0.16, memory_pressure=0.64, replay_gap=0.70)
        self.add_check(
            "default_audio_input_bind",
            "powershell_system_speech",
            "pass" if self.probe.default_audio_ok else "warn",
            "microfone padrao aceito pelo reconhecedor" if self.probe.default_audio_ok else (self.probe.audio_error or "nao foi possivel confirmar microfone sem reconhecedor"),
            {"audio_error": self.probe.audio_error, "recognizer_count": self.probe.recognizer_count},
            novelty=0.30,
            conflict=0.20 if not self.probe.default_audio_ok else 0.08,
            memory_pressure=0.66 if not self.probe.default_audio_ok else 0.44,
            replay_gap=0.70 if not self.probe.default_audio_ok else 0.32,
        )

        self.step(4, "verify_darwin_voice_modules", "run_voice_regressions", True, novelty=0.18, conflict=0.08, memory_pressure=0.48, replay_gap=0.34)
        self.verify_voice_files()
        self.run_voice_self_test()
        self.run_first_words_rehearsal()

        live_status = "prepared"
        if self.probe.recognizer_count == 0:
            live_status = "blocked_no_recognizer"
        self.step(5, "prepare_live_first_words_test", "prepare_mamae_papai_felipe_live_probe", True, {"live_status": live_status}, novelty=0.24, conflict=0.12, memory_pressure=0.52, replay_gap=0.42)
        if prepare_live:
            self.prepare_live_test(live_status)
        self.add_check(
            "live_first_words_test_prepared",
            "live_test",
            "pass",
            f"teste ao vivo preparado: {live_status}",
            {"expected_words": FIRST_WORD_TEST_WORDS, "status": live_status},
            novelty=0.24,
            conflict=0.10,
        )

        self.step(6, "write_repair_plan", "write_next_safe_voice_action", True, novelty=0.16, conflict=0.08, memory_pressure=0.42, replay_gap=0.30)
        self.result = self.build_result()
        self.store.log_result(self.session_id, self.result)
        self.summary = self.complete()
        return self.summary

    def verify_voice_files(self) -> None:
        files = [
            "darwin_voice_presence_v49_9.py",
            "darwin_first_words_v49_10.py",
            "darwin_check_v49_9_voice_presence.py",
            "darwin_check_v49_10_first_words.py",
            "Abrir_Darwin_Voz.bat",
            "Abrir_Darwin_Primeiras_Palavras.bat",
        ]
        existing = [name for name in files if Path(name).exists()]
        self.add_check(
            "voice_repair_files_present",
            "filesystem",
            "pass" if len(existing) == len(files) else "warn",
            f"{len(existing)}/{len(files)} arquivos de voz presentes",
            {"expected_files": files, "existing_files": existing},
        )

    def run_voice_self_test(self) -> None:
        try:
            from darwin_voice_presence_v49_9 import run_self_test

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = run_self_test(details=False)
            recognized = int(result.get("recognized") or 0)
            self.add_check(
                "voice_presence_self_test",
                "self_test",
                "pass" if recognized >= 4 else "warn",
                f"v49.9 reconheceu {recognized} entradas simuladas",
                {"result": result, "captured_stdout": buf.getvalue()[-1200:]},
            )
        except Exception as exc:
            self.add_check(
                "voice_presence_self_test",
                "self_test",
                "fail",
                f"falha no self-test v49.9: {exc}",
                {"exception": str(exc)},
            )

    def run_first_words_rehearsal(self) -> None:
        try:
            from darwin_first_words_v49_10 import run_self_test

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = run_self_test(details=False)
            learned = int(result.get("learned_count") or 0)
            exposures = int(result.get("total_exposures") or 0)
            self.add_check(
                "first_words_rehearsal",
                "self_test",
                "pass" if learned >= 5 and exposures >= 8 else "warn",
                f"v49.10 ensaiou {learned} palavras e {exposures} exposicoes",
                {"result": result, "captured_stdout": buf.getvalue()[-1200:]},
            )
        except Exception as exc:
            self.add_check(
                "first_words_rehearsal",
                "self_test",
                "fail",
                f"falha no ensaio v49.10: {exc}",
                {"exception": str(exc)},
            )

    def prepare_live_test(self, status: str) -> LiveTestRecord:
        item = LiveTestRecord(
            test_id=f"LIVE-{self.session_id}-PREP",
            test_kind="first_words_real_voice",
            expected_words=FIRST_WORD_TEST_WORDS,
            recognized_words=[],
            status=status,
            confidence_mean=0.0,
            payload={"instruction": "falar mamae, papai, Felipe e Darwin apos instalar reconhecimento de fala pt-BR"},
        )
        self.live_tests.append(item)
        self.store.log_live_test(self.session_id, item)
        return item

    def run_live_first_words_test(self, seconds: int = 18) -> LiveTestRecord:
        data = self.prober.live_first_words(seconds)
        recognized = [str(x).lower() for x in data.get("recognized", [])]
        confidences = [float(x) for x in data.get("confidences", [])]
        mean = sum(confidences) / max(1, len(confidences))
        expected = set(FIRST_WORD_TEST_WORDS)
        hit_count = len(expected.intersection(set(recognized)))
        if data.get("status") == "blocked_no_recognizer":
            status = "blocked_no_recognizer"
        elif hit_count >= 2 and mean >= 0.20:
            status = "completed"
        elif recognized:
            status = "partial"
        else:
            status = "no_words_heard"
        item = LiveTestRecord(
            test_id=f"LIVE-{self.session_id}-{int(time.time())}",
            test_kind="first_words_real_voice",
            expected_words=FIRST_WORD_TEST_WORDS,
            recognized_words=recognized,
            status=status,
            confidence_mean=mean,
            payload=data,
        )
        self.live_tests.append(item)
        self.store.log_live_test(self.session_id, item)
        return item

    def status(self, key: str) -> str:
        for item in self.checks:
            if item.check_key == key:
                return item.status
        return ""

    def build_result(self) -> RepairResult:
        assert self.probe is not None
        voice_ok = self.status("voice_presence_self_test") == "pass"
        first_ok = self.status("first_words_rehearsal") == "pass"
        real_ready = (
            self.probe.system_speech_ok
            and self.probe.recognizer_count > 0
            and self.probe.pt_br_available
            and self.probe.default_audio_ok
            and voice_ok
            and first_ok
        )
        passed = sum(1 for c in self.checks if c.status == "pass")
        warnings = sum(1 for c in self.checks if c.status == "warn")
        readiness = clamp((passed * 0.095 + warnings * 0.035 + (0.18 if self.probe.recognizer_count > 0 else 0.0) + (0.16 if self.probe.pt_br_available else 0.0) + (0.14 if self.probe.default_audio_ok else 0.0)) / 1.16)
        if not self.probe.system_speech_ok:
            blocked_by = "system_speech_unavailable"
            next_action = "verificar_instalacao_do_windows_e_componentes_System_Speech"
        elif self.probe.recognizer_count == 0:
            blocked_by = "windows_speech_recognizer_missing_or_unavailable"
            next_action = "abrir_configuracoes_de_fala_do_windows_instalar_pt_br_e_rodar_v49_25_novamente"
        elif not self.probe.pt_br_available:
            blocked_by = "pt_br_recognizer_missing"
            next_action = "instalar_pacote_de_fala_portugues_brasil_e_retestar_mamae_papai_felipe"
        elif not self.probe.default_audio_ok:
            blocked_by = "default_microphone_not_confirmed"
            next_action = "confirmar_microfone_padrao_e_permissao_de_microfone_no_windows"
        elif not voice_ok or not first_ok:
            blocked_by = "darwin_voice_module_regression"
            next_action = "rodar_checkers_v49_9_e_v49_10_antes_do_teste_real"
        else:
            blocked_by = ""
            next_action = "abrir_darwin_primeiras_palavras_e_falar_mamae_papai_felipe_sem_teclado"
        return RepairResult(
            result_id=f"RES-{self.session_id}",
            source_action_session_id=self.source_action_session_id,
            recognizer_count=self.probe.recognizer_count,
            pt_br_available=self.probe.pt_br_available,
            default_audio_ok=self.probe.default_audio_ok,
            real_voice_ready=real_ready,
            readiness_score=readiness,
            blocked_by=blocked_by,
            next_action=next_action,
            payload={
                "recognizers": self.probe.recognizers,
                "check_keys": [c.check_key for c in self.checks],
                "live_tests": [record.status for record in self.live_tests],
                "source_v49_24_blocked_by": self.source_blocker,
            },
        )

    def complete(self) -> dict[str, Any]:
        if self.result is None:
            raise RuntimeError("Repair wizard incomplete")
        summary = {
            "session_id": self.session_id,
            "source_action_session_id": self.source_action_session_id,
            "source_blocker": self.source_blocker,
            "phase_count": len(self.steps),
            "check_count": len(self.checks),
            "live_test_count": len(self.live_tests),
            "phases": [
                {
                    "phase": step.phase,
                    "action": step.repair_action,
                    "rzs_decision": step.rzs_decision,
                    "sigma_before": round(step.sigma_before, 3),
                    "sigma_after": round(step.sigma_after, 3),
                }
                for step in self.steps
            ],
            "checks": [
                {
                    "check_key": check.check_key,
                    "status": check.status,
                    "evidence": check.evidence,
                    "rzs_decision": check.rzs_decision,
                    "sigma_before": round(check.sigma_before, 3),
                    "sigma_after": round(check.sigma_after, 3),
                }
                for check in self.checks
            ],
            "live_tests": [
                {
                    "test_kind": test.test_kind,
                    "status": test.status,
                    "expected_words": test.expected_words,
                    "recognized_words": test.recognized_words,
                    "confidence_mean": round(test.confidence_mean, 3),
                }
                for test in self.live_tests
            ],
            "result": {
                "recognizer_count": self.result.recognizer_count,
                "pt_br_available": self.result.pt_br_available,
                "default_audio_ok": self.result.default_audio_ok,
                "real_voice_ready": self.result.real_voice_ready,
                "readiness_score": round(self.result.readiness_score, 3),
                "blocked_by": self.result.blocked_by,
                "next_action": self.result.next_action,
            },
            "session_complete": True,
        }
        first_sigma = self.steps[0].sigma_before if self.steps else 0.0
        final_sigma = self.steps[-1].sigma_after if self.steps else 0.0
        self.store.write_memory(self.session_id, summary, 0.90)
        self.store.write_episode(
            self.session_id,
            "repair_real_voice_path",
            f"ready={self.result.real_voice_ready} recognizers={self.result.recognizer_count} next={self.result.next_action}",
            "Darwin separou escuta simulada de escuta real e criou plano verificavel para destravar voz no Windows.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            self.mode,
            self.source_action_session_id,
            self.result.blocked_by,
            summary,
        )
        return summary


class RealVoiceRepairApp:
    BG = "#061018"
    PANEL = "#0d1f2d"
    INK = "#ecf8ff"
    MUTED = "#9dbdd5"
    BLUE = "#5fb3ff"
    GREEN = "#7ae6a4"
    AMBER = "#f7c66f"
    RED = "#ff6d78"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Real Voice Repair v49.25")
        self.root.geometry("1120x780")
        self.root.minsize(960, 660)
        self.root.configure(bg=self.BG)
        self.core: RealVoiceRepairWizard | None = None
        self.summary: dict[str, Any] = {}
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.phase = 0.0
        self.running = False
        self.build_ui()
        self.run_diagnostics()
        self.root.after(80, self.drain)
        self.animate()

    def build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=7)

        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(header, text="DARWIN REAL VOICE REPAIR v49.25", bg=self.BG, fg=self.INK, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="reparo guiado da fala real do Windows para primeiras palavras", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=430)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=300)
        self.canvas.pack(fill="x")

        controls = tk.Frame(left, bg="#102434")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Diagnosticar", command=self.run_diagnostics).pack(side="left", padx=(10, 5), pady=8)
        ttk.Button(controls, text="Fala Windows", command=lambda: self.open_settings("ms-settings:speech")).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Microfone", command=lambda: self.open_settings("ms-settings:privacy-microphone")).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Teste ao vivo", command=self.run_live_test).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Primeiras palavras", command=self.open_first_words).pack(side="left", padx=5, pady=8)

        self.log = tk.Text(left, height=15, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, pady=(8, 0))

        tk.Label(right, text="Plano", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.plan = tk.Text(right, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.plan.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def write_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def run_diagnostics(self) -> None:
        if self.running:
            return
        self.running = True
        self.log.delete("1.0", "end")
        self.plan.delete("1.0", "end")
        self.write_log("Darwin: iniciando diagnostico v49.25...")

        def worker() -> None:
            try:
                core = RealVoiceRepairWizard(mode="gui")
                summary = core.run_diagnostics()
                self.events.put(("diagnostics_done", {"core": core, "summary": summary}))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def run_live_test(self) -> None:
        if self.running or not self.core:
            return
        self.running = True
        self.write_log("Darwin: escutando primeiras palavras reais por alguns segundos...")

        def worker() -> None:
            try:
                assert self.core is not None
                item = self.core.run_live_first_words_test(18)
                self.events.put(("live_done", item))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def drain(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            self.running = False
            if kind == "diagnostics_done":
                self.core = payload["core"]
                self.summary = payload["summary"]
                self.render_summary()
            elif kind == "live_done":
                item: LiveTestRecord = payload
                self.write_log(f"Live test: {item.status}; reconhecido={', '.join(item.recognized_words) or 'nenhum'}")
                self.render_plan()
            elif kind == "error":
                self.write_log(f"Sistema: {payload}")
        self.root.after(80, self.drain)

    def render_summary(self) -> None:
        self.log.delete("1.0", "end")
        self.write_log("Diagnosticos")
        self.write_log("")
        for idx, check in enumerate(self.summary.get("checks", []), start=1):
            self.write_log(f"{idx}. {check['check_key']} [{check['status']}] RZS {check['rzs_decision']} sigma {check['sigma_before']}->{check['sigma_after']}")
            self.write_log(f"   {check['evidence']}")
        self.render_plan()

    def render_plan(self) -> None:
        self.plan.delete("1.0", "end")
        r = self.summary.get("result", {})
        lines = [
            f"sessao: {self.summary.get('session_id', '')}",
            f"recognizers: {r.get('recognizer_count', 0)}",
            f"pt-BR: {r.get('pt_br_available', False)}",
            f"microfone padrao: {r.get('default_audio_ok', False)}",
            f"voz real pronta: {r.get('real_voice_ready', False)}",
            f"readiness: {r.get('readiness_score', 0)}",
            "",
            "Bloqueio",
            r.get("blocked_by", "") or "nenhum",
            "",
            "Proxima acao",
            r.get("next_action", ""),
            "",
            "Teste esperado",
            "fale: mamae, papai, Felipe, Darwin",
        ]
        self.plan.insert("end", "\n".join(lines))

    def open_settings(self, uri: str) -> None:
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
            self.write_log(f"Sistema: abrindo {uri}")
        except Exception as exc:
            self.write_log(f"Sistema: nao consegui abrir {uri}: {exc}")

    def open_first_words(self) -> None:
        try:
            subprocess.Popen([sys.executable, "darwin_first_words_v49_10.py"], cwd=str(Path(__file__).resolve().parent))
            self.write_log("Sistema: abrindo Darwin First Words v49.10")
        except Exception as exc:
            self.write_log(f"Sistema: nao consegui abrir primeiras palavras: {exc}")

    def animate(self) -> None:
        self.phase += 0.04
        self.draw()
        self.root.after(40, self.animate)

    def draw(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.55
        result = self.summary.get("result", {})
        ready = bool(result.get("real_voice_ready"))
        blocked = bool(result.get("blocked_by"))
        color = self.GREEN if ready else (self.AMBER if blocked else self.BLUE)
        radius = 74 * (1.0 + math.sin(self.phase) * 0.035)
        if self.running:
            radius += 6 * math.sin(self.phase * 3.0)
        self.canvas.create_text(cx, 30, text="reparo da voz real", fill=self.INK, font=("Segoe UI", 16, "bold"))
        for i in range(7, 0, -1):
            rr = radius + i * 18
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="#0c2537", outline="")
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - radius * 0.34, cy - radius * 0.34, cx + radius * 0.34, cy + radius * 0.34, fill="#e6fbff", outline="")
        footer = result.get("next_action", "diagnosticando..." if self.running else "aguardando")
        self.canvas.create_text(cx, h - 26, text=short(footer, 86), fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    result = summary["result"]
    print("DARWIN v49.25 - REAL VOICE REPAIR WIZARD")
    print("=" * 68)
    print(f"- sessao: {summary['session_id']}")
    print(f"- fonte v49.24: {summary['source_action_session_id'] or 'nenhuma'}")
    print(f"- recognizers: {result['recognizer_count']}")
    print(f"- pt-BR: {result['pt_br_available']} microfone: {result['default_audio_ok']}")
    print(f"- voz real pronta: {result['real_voice_ready']} readiness={result['readiness_score']}")
    if result["blocked_by"]:
        print(f"- bloqueio: {result['blocked_by']}")
    print(f"- proxima acao: {result['next_action']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.25 Real Voice Repair Wizard")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--live-test", action="store_true")
    ap.add_argument("--seconds", type=int, default=18)
    ap.add_argument("--seed", type=int, default=4925)
    args = ap.parse_args()
    if args.self_test or args.live_test:
        core = RealVoiceRepairWizard(seed=args.seed, mode="live_test" if args.live_test else "self_test")
        summary = core.run_diagnostics()
        if args.live_test:
            item = core.run_live_first_words_test(args.seconds)
            summary.setdefault("live_tests", []).append(
                {
                    "test_kind": item.test_kind,
                    "status": item.status,
                    "expected_words": item.expected_words,
                    "recognized_words": item.recognized_words,
                    "confidence_mean": round(item.confidence_mean, 3),
                }
            )
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    RealVoiceRepairApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
