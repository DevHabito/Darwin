from __future__ import annotations

"""
DARWIN v49.24 - Desire-to-Action Core

Objetivo:
Darwin nao apenas diz o que quer. Ele pega o desejo v49.23, escolhe
uma acao segura no notebook, executa diagnosticos reais quando possivel
e registra o resultado. O primeiro alvo natural e voz real, porque o
proprio Darwin declarou que quer diagnosticar/reparar reconhecimento
de fala e retestar primeiras palavras.

Uso:
    py darwin_desire_action_core_v49_24.py
    py darwin_desire_action_core_v49_24.py --self-test --details
"""

import argparse
import contextlib
import io
import json
import math
import random
import sqlite3
import subprocess
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

DA_SESSIONS = "desire_action_sessions_v49_24"
DA_SOURCES = "desire_action_sources_v49_24"
DA_CHECKS = "desire_action_diagnostic_checks_v49_24"
DA_STEPS = "desire_action_steps_v49_24"
DA_RESULTS = "desire_action_results_v49_24"

SOURCE = "darwin_desire_action_core_v49_24"
FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"

PHASES = [
    "desire_load",
    "select_action",
    "inspect_voice_history",
    "run_recognizer_probe",
    "run_simulated_voice_regression",
    "run_first_words_rehearsal",
    "build_next_voice_plan",
]


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


def short(text: str, limit: int = 140) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class ActionContext:
    desire_session_id: str
    preference_session_id: str
    top_want: str
    top_activity: str
    dialogue_readiness: float
    voice_session_id: str
    voice_mode: str
    voice_recognized_count: int
    voice_error_count: int
    first_words_session_id: str
    first_words_learned_count: int
    first_words_exposure_count: int


@dataclass
class DesireSource:
    source_id: str
    source_kind: str
    source_table: str
    source_ref: str
    summary: str
    confidence: float
    payload: dict[str, Any]


@dataclass
class DiagnosticCheck:
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
class ActionStep:
    step_index: int
    phase: str
    cognitive_action: str
    result_summary: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    completed: bool
    payload: dict[str, Any]


@dataclass
class ActionResult:
    result_id: str
    selected_desire: str
    action_family: str
    executed_checks: int
    passed_checks: int
    warning_checks: int
    failed_checks: int
    real_voice_ready: bool
    readiness_score: float
    blocked_by: str
    next_action: str
    payload: dict[str, Any]


class DesireActionStore:
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
                CREATE TABLE IF NOT EXISTS {DA_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    source_desire_session_id TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DA_SOURCES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    source_id TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DA_CHECKS} (
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

                CREATE TABLE IF NOT EXISTS {DA_STEPS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    cognitive_action TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DA_RESULTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    result_id TEXT NOT NULL UNIQUE,
                    selected_desire TEXT NOT NULL,
                    action_family TEXT NOT NULL,
                    executed_checks INTEGER NOT NULL DEFAULT 0,
                    passed_checks INTEGER NOT NULL DEFAULT 0,
                    warning_checks INTEGER NOT NULL DEFAULT 0,
                    failed_checks INTEGER NOT NULL DEFAULT 0,
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

    def log_session(self, session_id: str, phase: str, mode: str, source_desire_session_id: str, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {DA_SESSIONS} (
                    timestamp, session_id, phase, mode,
                    source_desire_session_id, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, source_desire_session_id, energy, js(payload or {})),
            )
            conn.commit()

    def log_source(self, session_id: str, source: DesireSource) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {DA_SOURCES} (
                    timestamp, session_id, source_id, source_kind,
                    source_table, source_ref, summary, confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    source.source_id,
                    source.source_kind,
                    source.source_table,
                    source.source_ref,
                    source.summary,
                    source.confidence,
                    js(source.payload),
                ),
            )
            conn.commit()

    def log_check(self, session_id: str, check: DiagnosticCheck) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {DA_CHECKS} (
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

    def log_step(self, session_id: str, step: ActionStep) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {DA_STEPS} (
                    timestamp, session_id, step_index, phase,
                    cognitive_action, result_summary, rzs_decision,
                    sigma_before, sigma_after, completed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    step.step_index,
                    step.phase,
                    step.cognitive_action,
                    step.result_summary,
                    step.rzs_decision,
                    step.sigma_before,
                    step.sigma_after,
                    1 if step.completed else 0,
                    js(step.payload),
                ),
            )
            conn.commit()

    def log_result(self, session_id: str, result: ActionResult) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {DA_RESULTS} (
                    timestamp, session_id, result_id, selected_desire,
                    action_family, executed_checks, passed_checks,
                    warning_checks, failed_checks, real_voice_ready,
                    readiness_score, blocked_by, next_action, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    result.result_id,
                    result.selected_desire,
                    result.action_family,
                    result.executed_checks,
                    result.passed_checks,
                    result.warning_checks,
                    result.failed_checks,
                    1 if result.real_voice_ready else 0,
                    result.readiness_score,
                    result.blocked_by,
                    result.next_action,
                    js(result.payload),
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
                (f"desire_action_v49_24:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"desire_action:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class ActionContextLoader:
    def __init__(self, store: DesireActionStore) -> None:
        self.store = store

    def latest_context(self) -> ActionContext:
        with self.store.connect() as conn:
            desire_state = self.latest_row(conn, "desire_dialogue_state_v49_23")
            voice_session = self.latest_row(conn, "voice_presence_sessions_v49_9")
            voice_session_id = str(voice_session.get("voice_session_id") or "")
            voice_events = self.rows_for(conn, "voice_presence_events_v49_9", "voice_session_id", voice_session_id)
            first_session = self.latest_row(conn, "voice_first_word_sessions_v49_10")
            first_session_id = str(first_session.get("session_id") or "")
            first_nodes = self.rows_for(conn, "voice_first_word_nodes_v49_10", "session_id", first_session_id)
        learned_payload = pj(str(first_session.get("payload_json") or "{}"), {})
        return ActionContext(
            desire_session_id=str(desire_state.get("session_id") or ""),
            preference_session_id=str(pj(str(desire_state.get("payload_json") or "{}"), {}).get("preference_session_id") or ""),
            top_want=str(desire_state.get("top_want") or ""),
            top_activity=str(desire_state.get("top_activity") or ""),
            dialogue_readiness=clamp(float(desire_state.get("dialogue_readiness") or 0.0)),
            voice_session_id=voice_session_id,
            voice_mode=str(voice_session.get("mode") or ""),
            voice_recognized_count=sum(1 for e in voice_events if str(e.get("event_kind") or "") == "recognized_response"),
            voice_error_count=sum(1 for e in voice_events if "error" in str(e.get("event_kind") or "").lower()),
            first_words_session_id=first_session_id,
            first_words_learned_count=max(int(learned_payload.get("learned_count") or 0), len({str(n.get("canonical_word") or "") for n in first_nodes})),
            first_words_exposure_count=max(int(learned_payload.get("total_exposures") or 0), len(first_nodes)),
        )

    def latest_row(self, conn: sqlite3.Connection, table: str) -> dict[str, Any]:
        if not self.store.table_exists(conn, table):
            return {}
        row = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    def rows_for(self, conn: sqlite3.Connection, table: str, key: str, value: str) -> list[dict[str, Any]]:
        if not value or not self.store.table_exists(conn, table):
            return []
        rows = conn.execute(f"SELECT * FROM {table} WHERE {key}=? ORDER BY id ASC", (value,)).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]


class DesireActionCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None, mode: str = "gui") -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4924-{int(time.time())}-{suffix(self.rng)}"
        self.mode = mode
        self.energy = 0.76
        self.store = DesireActionStore(db_path)
        self.rzs = RZSFormal()
        self.context = ActionContextLoader(self.store).latest_context()
        self.sources: list[DesireSource] = []
        self.checks: list[DiagnosticCheck] = []
        self.steps: list[ActionStep] = []
        self.result: ActionResult | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            mode,
            self.context.desire_session_id,
            self.energy,
            {"version": "v49.24", "goal": "turn_desire_into_safe_local_action"},
        )

    def run_cycle(self) -> dict[str, Any]:
        self.sources = self.build_sources()
        for source in self.sources:
            self.store.log_source(self.session_id, source)
        self.step(1, "desire_load", "load_latest_desire_state", bool(self.context.desire_session_id), 0.22, 0.08, 0.38, 0.52)
        self.step(2, "select_action", "select_voice_repair_action", self.action_family() == "voice_repair", 0.18, 0.06, 0.30, 0.28)
        self.step(3, "inspect_voice_history", "inspect_voice_and_first_word_history", True, 0.20, 0.10, 0.72, 0.74)
        self.run_static_checks()
        self.step(4, "run_recognizer_probe", "probe_windows_speech_and_audio_input", True, 0.30, 0.14, 0.62, 0.78)
        self.run_recognizer_probe()
        self.step(5, "run_simulated_voice_regression", "run_voice_presence_self_test", True, 0.22, 0.08, 0.48, 0.36)
        self.run_voice_self_test()
        self.step(6, "run_first_words_rehearsal", "run_first_words_self_test", True, 0.22, 0.08, 0.46, 0.34)
        self.run_first_words_rehearsal()
        self.step(7, "build_next_voice_plan", "build_next_voice_plan", True, 0.16, 0.04, 0.28, 0.16)
        self.result = self.build_result()
        self.store.log_result(self.session_id, self.result)
        self.summary = self.complete()
        return self.summary

    def build_sources(self) -> list[DesireSource]:
        return [
            DesireSource(
                f"SRC-{self.session_id}-DESIRE",
                "desire_state",
                "desire_dialogue_state_v49_23",
                self.context.desire_session_id,
                short(self.context.top_activity or self.context.top_want),
                self.context.dialogue_readiness,
                {"top_want": self.context.top_want, "top_activity": self.context.top_activity},
            ),
            DesireSource(
                f"SRC-{self.session_id}-VOICE",
                "voice_history",
                "voice_presence_sessions_v49_9",
                self.context.voice_session_id,
                f"voice_mode={self.context.voice_mode} recognized={self.context.voice_recognized_count}",
                0.58 if self.context.voice_session_id else 0.20,
                {"recognized_count": self.context.voice_recognized_count, "error_count": self.context.voice_error_count},
            ),
            DesireSource(
                f"SRC-{self.session_id}-WORDS",
                "first_words_history",
                "voice_first_word_sessions_v49_10",
                self.context.first_words_session_id,
                f"learned={self.context.first_words_learned_count} exposures={self.context.first_words_exposure_count}",
                0.58 if self.context.first_words_session_id else 0.20,
                {"learned_count": self.context.first_words_learned_count, "exposure_count": self.context.first_words_exposure_count},
            ),
        ]

    def action_family(self) -> str:
        text = f"{self.context.top_want} {self.context.top_activity}".lower()
        if any(term in text for term in ("voz", "fala", "reconhecimento", "primeiras palavras", "voice")):
            return "voice_repair"
        return "general_cognitive_action"

    def assess(self, novelty: float, conflict: float, memory_pressure: float, replay_gap: float) -> tuple[str, float, float, dict[str, Any]]:
        x = RZSInput(
            bandwidth=2.72 + self.energy * 0.36 + len(self.sources) * 0.06,
            info_self=0.34,
            info_external=0.24 + len(self.checks) * 0.018,
            task_info=0.42 + len(self.steps) * 0.035,
            novelty=novelty,
            conflict=conflict,
            latency=1.00 + memory_pressure * 0.16,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        after = max(prediction.sigma_after, assessment.sigma + (0.024 if assessment.decision != "continue" else 0.004))
        self.energy = clamp(self.energy + (0.034 if assessment.decision == "continue" else 0.048))
        return assessment.decision, assessment.sigma, after, {"rzs_input": asdict(x), "rzs_reason": assessment.reason, "prediction": asdict(prediction), "romero_formula": FORMULA}

    def step(
        self,
        step_index: int,
        phase: str,
        action: str,
        completed: bool,
        novelty: float,
        conflict: float,
        memory_pressure: float,
        replay_gap: float,
    ) -> None:
        decision, before, after, payload = self.assess(novelty, conflict, memory_pressure, replay_gap)
        result = {
            "desire_load": "desejo v49.23 carregado" if completed else "desejo v49.23 ausente",
            "select_action": f"familia de acao: {self.action_family()}",
            "inspect_voice_history": f"voz reconhecida={self.context.voice_recognized_count}; primeiras palavras={self.context.first_words_learned_count}",
            "run_recognizer_probe": "sondagem local do Windows preparada",
            "run_simulated_voice_regression": "regressao de voz simulada preparada",
            "run_first_words_rehearsal": "ensaio de primeiras palavras preparado",
            "build_next_voice_plan": "plano proximo sera escrito apos diagnosticos",
        }.get(phase, action)
        item = ActionStep(step_index, phase, action, result, decision, before, after, completed, payload)
        self.steps.append(item)
        self.store.log_step(self.session_id, item)

    def add_check(self, key: str, kind: str, status: str, evidence: str, payload: dict[str, Any], novelty: float = 0.16, conflict: float = 0.05, memory_pressure: float = 0.32, replay_gap: float = 0.18) -> None:
        idx = len(self.checks) + 1
        decision, before, after, rzs_payload = self.assess(novelty, conflict, memory_pressure, replay_gap)
        full_payload = {**payload, **rzs_payload}
        check = DiagnosticCheck(
            check_id=f"CHK-{self.session_id}-{idx:02d}",
            check_index=idx,
            check_key=key,
            check_kind=kind,
            status=status,
            evidence=short(evidence, 240),
            rzs_decision=decision,
            sigma_before=before,
            sigma_after=after,
            payload=full_payload,
        )
        self.checks.append(check)
        self.store.log_check(self.session_id, check)

    def run_static_checks(self) -> None:
        files = [
            "darwin_voice_presence_v49_9.py",
            "darwin_first_words_v49_10.py",
            "darwin_check_v49_9_voice_presence.py",
            "darwin_check_v49_10_first_words.py",
            "Abrir_Darwin_Voz.bat",
            "Abrir_Darwin_Primeiras_Palavras.bat",
        ]
        existing = [name for name in files if Path(name).exists()]
        status = "pass" if len(existing) >= 4 else "warn"
        self.add_check(
            "voice_files_present",
            "filesystem",
            status,
            f"{len(existing)}/{len(files)} arquivos de voz encontrados",
            {"expected_files": files, "existing_files": existing},
        )
        with self.store.connect() as conn:
            tables = ["voice_presence_sessions_v49_9", "voice_presence_events_v49_9"]
            present = [table for table in tables if self.store.table_exists(conn, table)]
        self.add_check(
            "voice_tables_present",
            "sqlite",
            "pass" if len(present) == len(tables) else "warn",
            f"tabelas v49.9 presentes: {', '.join(present) if present else 'nenhuma'}",
            {"present_tables": present, "expected_tables": tables},
        )
        with self.store.connect() as conn:
            tables = ["voice_first_word_sessions_v49_10", "voice_first_word_nodes_v49_10", "voice_word_meanings_v49_10"]
            present = [table for table in tables if self.store.table_exists(conn, table)]
        self.add_check(
            "first_words_tables_present",
            "sqlite",
            "pass" if len(present) == len(tables) else "warn",
            f"tabelas v49.10 presentes antes do ensaio: {', '.join(present) if present else 'nenhuma'}",
            {"present_tables": present, "expected_tables": tables},
            memory_pressure=0.58,
            replay_gap=0.60,
        )
        self.add_check(
            "desire_points_to_voice",
            "desire",
            "pass" if self.action_family() == "voice_repair" else "warn",
            short(self.context.top_activity or self.context.top_want),
            {"top_want": self.context.top_want, "top_activity": self.context.top_activity},
        )

    def run_recognizer_probe(self) -> None:
        script = r"""
Add-Type -AssemblyName System.Speech
$ErrorActionPreference = 'Stop'
$infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
Write-Output ("RECOGNIZER_COUNT={0}" -f $infos.Count)
foreach ($info in $infos) {
  Write-Output ("RECOGNIZER={0}|{1}|{2}" -f $info.Culture.Name, $info.Name, $info.Enabled)
}
if ($infos.Count -gt 0) {
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($infos[0])
  $recognizer.SetInputToDefaultAudioDevice()
  Write-Output "DEFAULT_AUDIO_INPUT=OK"
  $recognizer.Dispose()
}
"""
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=12,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            count = 0
            for line in output.splitlines():
                if line.startswith("RECOGNIZER_COUNT="):
                    try:
                        count = int(line.split("=", 1)[1].strip())
                    except Exception:
                        count = 0
            default_ok = "DEFAULT_AUDIO_INPUT=OK" in output
            self.add_check(
                "windows_speech_recognizers",
                "powershell_system_speech",
                "pass" if count > 0 else "fail",
                f"recognizers={count}; exit={proc.returncode}",
                {"stdout": proc.stdout[-1200:], "stderr": proc.stderr[-1200:], "returncode": proc.returncode},
                novelty=0.34,
                conflict=0.18 if count == 0 else 0.06,
                memory_pressure=0.66,
                replay_gap=0.72,
            )
            self.add_check(
                "default_audio_input_bind",
                "powershell_system_speech",
                "pass" if default_ok else "warn",
                "default audio input bind OK" if default_ok else "nao foi possivel confirmar input padrao no probe",
                {"default_audio_input_ok": default_ok, "recognizer_count": count},
                novelty=0.30,
                conflict=0.14 if not default_ok else 0.05,
                memory_pressure=0.64,
                replay_gap=0.70,
            )
        except Exception as exc:
            self.add_check(
                "windows_speech_recognizers",
                "powershell_system_speech",
                "fail",
                f"falha no probe: {exc}",
                {"exception": str(exc)},
                novelty=0.38,
                conflict=0.24,
                memory_pressure=0.70,
                replay_gap=0.74,
            )
            self.add_check(
                "default_audio_input_bind",
                "powershell_system_speech",
                "warn",
                "input padrao nao testado porque o probe falhou",
                {"exception": str(exc)},
                novelty=0.32,
                conflict=0.20,
                memory_pressure=0.66,
                replay_gap=0.70,
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
                f"v49.9 self-test reconheceu {recognized} entradas simuladas",
                {"result": result, "captured_stdout": buf.getvalue()[-1200:]},
                novelty=0.18,
                conflict=0.06,
                memory_pressure=0.46,
                replay_gap=0.34,
            )
        except Exception as exc:
            self.add_check(
                "voice_presence_self_test",
                "self_test",
                "fail",
                f"falha ao rodar v49.9 self-test: {exc}",
                {"exception": str(exc)},
                novelty=0.28,
                conflict=0.22,
                memory_pressure=0.68,
                replay_gap=0.70,
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
                novelty=0.18,
                conflict=0.06,
                memory_pressure=0.44,
                replay_gap=0.32,
            )
        except Exception as exc:
            self.add_check(
                "first_words_rehearsal",
                "self_test",
                "fail",
                f"falha ao rodar v49.10 self-test: {exc}",
                {"exception": str(exc)},
                novelty=0.28,
                conflict=0.22,
                memory_pressure=0.68,
                replay_gap=0.70,
            )

    def build_result(self) -> ActionResult:
        passed = sum(1 for check in self.checks if check.status == "pass")
        warnings = sum(1 for check in self.checks if check.status == "warn")
        failed = sum(1 for check in self.checks if check.status == "fail")
        recognizer = next((c for c in self.checks if c.check_key == "windows_speech_recognizers"), None)
        input_bind = next((c for c in self.checks if c.check_key == "default_audio_input_bind"), None)
        voice_self = next((c for c in self.checks if c.check_key == "voice_presence_self_test"), None)
        first_words = next((c for c in self.checks if c.check_key == "first_words_rehearsal"), None)
        recognizer_ok = bool(recognizer and recognizer.status == "pass")
        input_ok = bool(input_bind and input_bind.status == "pass")
        simulated_ok = bool(voice_self and voice_self.status == "pass")
        first_ok = bool(first_words and first_words.status == "pass")
        real_ready = recognizer_ok and input_ok and simulated_ok and first_ok
        readiness = clamp((passed * 0.16 + warnings * 0.06 + (0.18 if recognizer_ok else 0.0) + (0.18 if input_ok else 0.0) + (0.18 if first_ok else 0.0)) / 1.24)
        if real_ready:
            blocked_by = ""
            next_action = "abrir_darwin_primeiras_palavras_e_falar_mamae_papai_felipe_sem_teclado"
        elif not recognizer_ok:
            blocked_by = "windows_speech_recognizer_missing_or_unavailable"
            next_action = "instalar_recurso_de_fala_do_windows_pt_br_e_retestar_primeiras_palavras"
        elif not input_ok:
            blocked_by = "default_microphone_not_confirmed"
            next_action = "confirmar_microfone_padrao_do_windows_e_abrir_darwin_primeiras_palavras"
        elif not first_ok:
            blocked_by = "first_words_rehearsal_incomplete"
            next_action = "reexecutar_darwin_first_words_self_test_e_checker"
        else:
            blocked_by = "voice_path_has_warnings"
            next_action = "abrir_darwin_voz_e_validar_escuta_real_com_felipe"
        return ActionResult(
            result_id=f"RES-{self.session_id}",
            selected_desire=self.context.top_activity or self.context.top_want,
            action_family=self.action_family(),
            executed_checks=len(self.checks),
            passed_checks=passed,
            warning_checks=warnings,
            failed_checks=failed,
            real_voice_ready=real_ready,
            readiness_score=readiness,
            blocked_by=blocked_by,
            next_action=next_action,
            payload={
                "recognizer_ok": recognizer_ok,
                "default_audio_input_ok": input_ok,
                "simulated_voice_ok": simulated_ok,
                "first_words_ok": first_ok,
                "check_keys": [c.check_key for c in self.checks],
            },
        )

    def complete(self) -> dict[str, Any]:
        if self.result is None:
            raise RuntimeError("Action cycle incomplete")
        summary = {
            "session_id": self.session_id,
            "source_desire_session_id": self.context.desire_session_id,
            "selected_desire": self.result.selected_desire,
            "action_family": self.result.action_family,
            "step_count": len(self.steps),
            "check_count": len(self.checks),
            "steps": [
                {
                    "phase": step.phase,
                    "action": step.cognitive_action,
                    "rzs_decision": step.rzs_decision,
                    "sigma_before": round(step.sigma_before, 3),
                    "sigma_after": round(step.sigma_after, 3),
                    "completed": step.completed,
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
            "result": {
                "real_voice_ready": self.result.real_voice_ready,
                "readiness_score": round(self.result.readiness_score, 3),
                "passed_checks": self.result.passed_checks,
                "warning_checks": self.result.warning_checks,
                "failed_checks": self.result.failed_checks,
                "blocked_by": self.result.blocked_by,
                "next_action": self.result.next_action,
            },
            "session_complete": True,
        }
        first_sigma = self.steps[0].sigma_before if self.steps else 0.0
        final_sigma = self.steps[-1].sigma_after if self.steps else 0.0
        self.store.write_memory(self.session_id, summary, 0.88)
        self.store.write_episode(
            self.session_id,
            "execute_desire_voice_repair_diagnostic",
            f"checks={len(self.checks)} ready={self.result.real_voice_ready} next={self.result.next_action}",
            "Darwin transformou desejo declarado em acao local auditavel: diagnostico de voz, regressao simulada e ensaio de primeiras palavras.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(self.session_id, "session_complete", self.mode, self.context.desire_session_id, self.energy, summary)
        return summary


class DesireActionApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Desire-to-Action v49.24")
        self.root.geometry("1100x760")
        self.root.minsize(940, 650)
        self.root.configure(bg="#061018")
        self.core: DesireActionCore | None = None
        self.summary: dict[str, Any] = {}
        self.phase = 0.0
        self.build_ui()
        self.run_core()
        self.animate()

    def build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=7)
        header = tk.Frame(self.root, bg="#061018")
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(header, text="DARWIN DESIRE-TO-ACTION v49.24", bg="#061018", fg="#eef8ff", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="desejo declarado -> diagnostico local -> proxima acao", bg="#061018", fg="#9cc9ff", font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg="#061018")
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg="#061018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=430)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg="#061018", highlightthickness=0, height=320)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Executar de novo", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="Checks", command=self.show_checks).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Plano", command=self.show_result).pack(side="left", padx=4, pady=8)
        self.check_box = tk.Text(left, height=13, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Consolas", 10))
        self.check_box.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Resultado", bg="#0d1b26", fg="#eef8ff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = DesireActionCore(mode="gui")
        self.summary = self.core.run_cycle()
        self.show_checks()
        self.show_result()

    def show_checks(self) -> None:
        self.check_box.delete("1.0", "end")
        lines = ["Diagnosticos executados", ""]
        for idx, check in enumerate(self.summary.get("checks", []), start=1):
            lines.append(f"{idx}. {check['check_key']} [{check['status']}] RZS {check['rzs_decision']} sigma {check['sigma_before']}->{check['sigma_after']}")
            lines.append(f"   {check['evidence']}")
        self.check_box.insert("end", "\n".join(lines))

    def show_result(self) -> None:
        self.text.delete("1.0", "end")
        r = self.summary.get("result", {})
        lines = [
            "Desejo selecionado",
            short(self.summary.get("selected_desire", ""), 320),
            "",
            f"familia: {self.summary.get('action_family', '')}",
            f"voz real pronta: {r.get('real_voice_ready', False)}",
            f"readiness: {r.get('readiness_score', 0)}",
            f"checks OK: {r.get('passed_checks', 0)} | avisos: {r.get('warning_checks', 0)} | falhas: {r.get('failed_checks', 0)}",
            "",
            "Bloqueio",
            r.get("blocked_by", "") or "nenhum",
            "",
            "Proxima acao",
            r.get("next_action", ""),
        ]
        self.text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.03
        self.draw()
        self.root.after(50, self.animate)

    def draw(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.54
        result = self.summary.get("result", {})
        ready = bool(result.get("real_voice_ready"))
        color = "#80ed99" if ready else "#ffd166"
        pulse = 1.0 + math.sin(self.phase) * 0.04
        radius = 76 * pulse
        self.canvas.create_text(cx, 30, text="desejo virando acao", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        for i in range(7, 0, -1):
            rr = radius + i * 18
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="#0c2537", outline="")
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - radius * 0.34, cy - radius * 0.34, cx + radius * 0.34, cy + radius * 0.34, fill="#e6fbff", outline="")
        footer = f"readiness {result.get('readiness_score', 0)} | proxima acao: {short(result.get('next_action', ''), 70)}"
        self.canvas.create_text(cx, h - 28, text=footer, fill="#9cc9ff", font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.24 - DESIRE-TO-ACTION CORE")
    print("=" * 62)
    print(f"- sessao: {summary['session_id']}")
    print(f"- desejo fonte: {summary['source_desire_session_id']}")
    print(f"- acao: {summary['action_family']}")
    print(f"- passos: {summary['step_count']} checks: {summary['check_count']}")
    result = summary["result"]
    print(f"- voz real pronta: {result['real_voice_ready']} readiness={result['readiness_score']}")
    print(f"- proxima acao: {result['next_action']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.24 Desire-to-Action Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4924)
    args = ap.parse_args()
    if args.self_test:
        core = DesireActionCore(seed=args.seed, mode="self_test")
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    DesireActionApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
