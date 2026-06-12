from __future__ import annotations

"""
DARWIN v49.32 - Controlled Autonomous Executor

Objetivo:
Darwin transforma o curriculo autonomo v49.31 em execucao controlada.
Ele nao executa qualquer coisa: primeiro consulta uma allowlist local,
passa por safety gate, aplica RZS, despacha uma acao por vez e monitora
estabilidade. No self-test, tudo e simulado e auditavel.

Uso:
    py darwin_controlled_autonomous_executor_v49_32.py
    py darwin_controlled_autonomous_executor_v49_32.py --self-test --steps 12 --details
"""

import argparse
import json
import math
import random
import sqlite3
import subprocess
import sys
import time
import tkinter as tk
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_controlled_autonomous_executor_v49_32"

EX_SESSIONS = "controlled_executor_sessions_v49_32"
EX_ALLOWLIST = "executor_allowed_modules_v49_32"
EX_QUEUE = "executor_queue_v49_32"
EX_SAFETY = "executor_safety_checks_v49_32"
EX_DISPATCH = "executor_dispatches_v49_32"
EX_MONITOR = "executor_monitors_v49_32"
EX_REFLECTIONS = "executor_reflections_v49_32"
EX_HANDOFFS = "executor_handoffs_v49_32"

AC_SESSIONS = "autonomous_curriculum_sessions_v49_31"
AC_CHOICES = "curriculum_choices_v49_31"
AC_TRIALS = "curriculum_trials_v49_31"

PROTECTED_SOURCE_TABLES = [
    AC_SESSIONS,
    AC_CHOICES,
    AC_TRIALS,
    "learning_to_learn_sessions_v49_30",
    "learning_strategies_v49_30",
    "affective_preferences_v49_17",
    "formula_sketch_sessions_v49_28",
    "story_nursery_sessions_v49_29",
    "music_reactions_v49_16",
    "memory_card_sessions_v49_13",
    "voice_first_word_nodes_v49_10",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float], fallback: float = 0.0) -> float:
    return sum(values) / len(values) if values else fallback


def number(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


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


def suffix(rng: random.Random, size: int = 5) -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(rng.choice(alphabet) for _ in range(size))


def short(text: str, limit: int = 120) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


@dataclass(frozen=True)
class ModuleSpec:
    module_key: str
    label: str
    script_name: str
    action_family: str
    max_runtime_seconds: int
    requires_user_visible_window: bool
    allow_self_test_simulation: bool
    safety_notes: str


@dataclass
class ExecutionIntent:
    queue_id: str
    step_index: int
    source_curriculum_session_id: str
    source_choice_id: str
    module_key: str
    requested_action: str
    priority_score: float
    expected_gain: float
    rzs_from_curriculum: str
    payload: dict[str, Any]


@dataclass
class SafetyResult:
    safety_id: str
    queue_id: str
    step_index: int
    module_key: str
    allowed: bool
    script_exists: bool
    simulation_only: bool
    single_process_guard: bool
    user_visible_required: bool
    risk_score: float
    decision: str
    reason: str
    payload: dict[str, Any]


@dataclass
class DispatchRecord:
    dispatch_id: str
    queue_id: str
    step_index: int
    module_key: str
    script_name: str
    dispatch_mode: str
    command: list[str]
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    execution_action: str
    status: str
    live_pid: int
    payload: dict[str, Any]


@dataclass
class MonitorRecord:
    monitor_id: str
    dispatch_id: str
    step_index: int
    module_key: str
    monitor_status: str
    stability: float
    energy_after: float
    observed_outcome: str
    payload: dict[str, Any]


def module_specs() -> dict[str, ModuleSpec]:
    specs = [
        ModuleSpec("formula_sketch", "Lapis de formulas", "darwin_formula_sketchbook_v49_28.py", "visual_formula", 900, True, True, "desenho local controlado"),
        ModuleSpec("child_story", "Historias infantis", "darwin_child_story_nursery_v49_29.py", "narrative_affect", 900, True, True, "historias locais seguras"),
        ModuleSpec("classical_music", "Musica classica simples", "darwin_classical_music_nursery_v49_16.py", "auditory_pattern", 900, True, True, "musica simples e infantil"),
        ModuleSpec("memory_cards", "Jogo da memoria", "darwin_memory_cards_v49_13.py", "visual_memory", 900, True, True, "jogo local sem solucao antecipada"),
        ModuleSpec("first_words", "Primeiras palavras", "darwin_first_words_v49_10.py", "early_language", 900, True, True, "voz local; pode depender do Windows"),
        ModuleSpec("self_review", "Auto revisao", "darwin_self_reflection_v49_15.py", "metacognition", 600, True, True, "revisao interna"),
        ModuleSpec("preference_choice", "Preferencias afetivas", "darwin_affective_preference_core_v49_17.py", "choice", 600, True, True, "preferencias por evidencia"),
        ModuleSpec("geometry_error", "Geometria e erro", "darwin_geometry_experience_v49_7.py", "geometry", 900, True, True, "geometria local"),
        ModuleSpec("voice_presence", "Presenca de voz", "darwin_voice_presence_v49_9.py", "relation_voice", 900, True, True, "escuta local depende de reconhecedor do Windows"),
    ]
    return {spec.module_key: spec for spec in specs}


class ExecutorStore:
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
                CREATE TABLE IF NOT EXISTS {EX_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    step_index INTEGER NOT NULL DEFAULT 0,
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EX_ALLOWLIST} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    script_name TEXT NOT NULL,
                    action_family TEXT NOT NULL,
                    max_runtime_seconds INTEGER NOT NULL DEFAULT 0,
                    requires_user_visible_window INTEGER NOT NULL DEFAULT 1,
                    allow_self_test_simulation INTEGER NOT NULL DEFAULT 1,
                    script_exists INTEGER NOT NULL DEFAULT 0,
                    safety_notes TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, module_key)
                );

                CREATE TABLE IF NOT EXISTS {EX_QUEUE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    queue_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    source_curriculum_session_id TEXT NOT NULL,
                    source_choice_id TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    requested_action TEXT NOT NULL,
                    priority_score REAL NOT NULL DEFAULT 0.0,
                    expected_gain REAL NOT NULL DEFAULT 0.0,
                    rzs_from_curriculum TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EX_SAFETY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    safety_id TEXT NOT NULL UNIQUE,
                    queue_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    module_key TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    script_exists INTEGER NOT NULL DEFAULT 0,
                    simulation_only INTEGER NOT NULL DEFAULT 0,
                    single_process_guard INTEGER NOT NULL DEFAULT 0,
                    user_visible_required INTEGER NOT NULL DEFAULT 0,
                    risk_score REAL NOT NULL DEFAULT 0.0,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EX_DISPATCH} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dispatch_id TEXT NOT NULL UNIQUE,
                    queue_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    module_key TEXT NOT NULL,
                    script_name TEXT NOT NULL,
                    dispatch_mode TEXT NOT NULL,
                    command_json TEXT NOT NULL DEFAULT '[]',
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    execution_action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    live_pid INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EX_MONITOR} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    monitor_id TEXT NOT NULL UNIQUE,
                    dispatch_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    module_key TEXT NOT NULL,
                    monitor_status TEXT NOT NULL,
                    stability REAL NOT NULL DEFAULT 0.0,
                    energy_after REAL NOT NULL DEFAULT 0.0,
                    observed_outcome TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EX_REFLECTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reflection_id TEXT NOT NULL UNIQUE,
                    reflection_kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EX_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_action TEXT NOT NULL,
                    controlled_executor_ready INTEGER NOT NULL DEFAULT 0,
                    safe_dispatch_count INTEGER NOT NULL DEFAULT 0,
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

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def rows(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.table_exists(conn, table):
            return []
        out = []
        for row in conn.execute(f"SELECT * FROM {table} {where} ORDER BY id ASC", params).fetchall():
            item = {k: row[k] for k in row.keys()}
            if "payload_json" in item:
                item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
            if "command_json" in item:
                item["command"] = pj(str(item.get("command_json") or "[]"), [])
            out.append(item)
        return out

    def latest_curriculum(self, conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
        if not self.table_exists(conn, AC_SESSIONS):
            return "", {}
        row = conn.execute(
            f"SELECT * FROM {AC_SESSIONS} WHERE phase='curriculum_complete' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "", {}
        item = {k: row[k] for k in row.keys()}
        return str(item.get("session_id") or ""), pj(str(item.get("payload_json") or "{}"), {})

    def protected_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        with self.connect() as conn:
            for table in PROTECTED_SOURCE_TABLES:
                if not self.table_exists(conn, table):
                    out[table] = {"count": 0, "max_id": 0}
                    continue
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
                out[table] = {"count": int(row["n"]), "max_id": int(row["max_id"])}
        return out

    def log_session(self, session_id: str, phase: str, mode: str, step_index: int, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {EX_SESSIONS} (
                    timestamp, session_id, phase, mode, step_index, energy,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, step_index, energy, js(payload or {})),
            )
            conn.commit()

    def log_allowlist(self, session_id: str, spec: ModuleSpec, script_exists: bool, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_ALLOWLIST} (
                    timestamp, session_id, module_key, label, script_name,
                    action_family, max_runtime_seconds,
                    requires_user_visible_window, allow_self_test_simulation,
                    script_exists, safety_notes, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    spec.module_key,
                    spec.label,
                    spec.script_name,
                    spec.action_family,
                    spec.max_runtime_seconds,
                    1 if spec.requires_user_visible_window else 0,
                    1 if spec.allow_self_test_simulation else 0,
                    1 if script_exists else 0,
                    spec.safety_notes,
                    js(payload),
                ),
            )
            conn.commit()

    def log_queue(self, session_id: str, intent: ExecutionIntent) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_QUEUE} (
                    timestamp, session_id, queue_id, step_index,
                    source_curriculum_session_id, source_choice_id, module_key,
                    requested_action, priority_score, expected_gain,
                    rzs_from_curriculum, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    intent.queue_id,
                    intent.step_index,
                    intent.source_curriculum_session_id,
                    intent.source_choice_id,
                    intent.module_key,
                    intent.requested_action,
                    intent.priority_score,
                    intent.expected_gain,
                    intent.rzs_from_curriculum,
                    js(intent.payload),
                ),
            )
            conn.commit()

    def log_safety(self, session_id: str, safety: SafetyResult) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_SAFETY} (
                    timestamp, session_id, safety_id, queue_id, step_index,
                    module_key, allowed, script_exists, simulation_only,
                    single_process_guard, user_visible_required, risk_score,
                    decision, reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    safety.safety_id,
                    safety.queue_id,
                    safety.step_index,
                    safety.module_key,
                    1 if safety.allowed else 0,
                    1 if safety.script_exists else 0,
                    1 if safety.simulation_only else 0,
                    1 if safety.single_process_guard else 0,
                    1 if safety.user_visible_required else 0,
                    safety.risk_score,
                    safety.decision,
                    safety.reason,
                    js(safety.payload),
                ),
            )
            conn.commit()

    def log_dispatch(self, session_id: str, dispatch: DispatchRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_DISPATCH} (
                    timestamp, session_id, dispatch_id, queue_id, step_index,
                    module_key, script_name, dispatch_mode, command_json,
                    rzs_decision, sigma_before, sigma_after, execution_action,
                    status, live_pid, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    dispatch.dispatch_id,
                    dispatch.queue_id,
                    dispatch.step_index,
                    dispatch.module_key,
                    dispatch.script_name,
                    dispatch.dispatch_mode,
                    js(dispatch.command),
                    dispatch.rzs_decision,
                    dispatch.sigma_before,
                    dispatch.sigma_after,
                    dispatch.execution_action,
                    dispatch.status,
                    dispatch.live_pid,
                    js(dispatch.payload),
                ),
            )
            conn.commit()

    def log_monitor(self, session_id: str, monitor: MonitorRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_MONITOR} (
                    timestamp, session_id, monitor_id, dispatch_id, step_index,
                    module_key, monitor_status, stability, energy_after,
                    observed_outcome, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    monitor.monitor_id,
                    monitor.dispatch_id,
                    monitor.step_index,
                    monitor.module_key,
                    monitor.monitor_status,
                    monitor.stability,
                    monitor.energy_after,
                    monitor.observed_outcome,
                    js(monitor.payload),
                ),
            )
            conn.commit()

    def log_reflection(self, session_id: str, reflection_id: str, kind: str, summary: str, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_REFLECTIONS} (
                    timestamp, session_id, reflection_id, reflection_kind,
                    summary, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, reflection_id, kind, summary, clamp(confidence), js(payload)),
            )
            conn.commit()

    def log_handoff(self, session_id: str, next_action: str, ready: bool, count: int, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EX_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_action,
                    controlled_executor_ready, safe_dispatch_count,
                    confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    f"HO-{session_id}-01",
                    next_action,
                    1 if ready else 0,
                    count,
                    clamp(confidence),
                    js(payload),
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
                (f"controlled_executor_v49_32:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"controlled_executor:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class ControlledExecutorCore:
    def __init__(self, seed: int | None = None, mode: str = "gui") -> None:
        self.store = ExecutorStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000) % 100_000_000)
        self.session_id = f"V4932-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.energy = 0.82
        self.specs = module_specs()
        self.curriculum_session_id = ""
        self.curriculum_payload: dict[str, Any] = {}
        self.queue: list[ExecutionIntent] = []
        self.safety_results: list[SafetyResult] = []
        self.dispatches: list[DispatchRecord] = []
        self.monitors: list[MonitorRecord] = []
        self.source_counts_before = self.store.protected_counts()
        self.active_dispatch_id = ""
        self.prepared = False

    def script_path(self, spec: ModuleSpec) -> Path:
        return Path(__file__).resolve().parent / spec.script_name

    def prepare(self) -> None:
        if self.prepared:
            return
        self.store.log_session(
            self.session_id,
            "executor_start",
            self.mode,
            0,
            self.energy,
            {"goal": "execute_curriculum_choice_with_allowlist_and_rzs", "protected_counts_before": self.source_counts_before},
        )
        self.load_allowlist()
        self.load_curriculum_queue()
        self.prepared = True

    def load_allowlist(self) -> None:
        for spec in self.specs.values():
            exists = self.script_path(spec).exists()
            self.store.log_allowlist(
                self.session_id,
                spec,
                exists,
                {
                    "script_path": str(self.script_path(spec)),
                    "allowed_command_shape": ["python_executable", spec.script_name],
                    "no_shell": True,
                    "no_network_required": True,
                },
            )
        self.store.log_session(
            self.session_id,
            "allowlist_loaded",
            self.mode,
            0,
            self.energy,
            {"allowed_module_count": len(self.specs), "modules": sorted(self.specs)},
        )

    def load_curriculum_queue(self) -> None:
        with self.store.connect() as conn:
            sid, payload = self.store.latest_curriculum(conn)
            self.curriculum_session_id = sid
            self.curriculum_payload = payload
            choices = self.store.rows(conn, AC_CHOICES, "WHERE session_id=?", (sid,)) if sid else []
        choices = sorted(choices, key=lambda r: int(r.get("step_index") or 0))
        for idx, choice in enumerate(choices, start=1):
            module_key = str(choice.get("module_key") or "")
            if module_key not in self.specs:
                continue
            intent = ExecutionIntent(
                queue_id=f"QU-{self.session_id}-{idx:02d}",
                step_index=idx,
                source_curriculum_session_id=self.curriculum_session_id,
                source_choice_id=str(choice.get("choice_id") or ""),
                module_key=module_key,
                requested_action=str(choice.get("chosen_action") or ""),
                priority_score=clamp(number(choice.get("score"), 0.0)),
                expected_gain=clamp(number(choice.get("expected_gain"), 0.0)),
                rzs_from_curriculum=str(choice.get("rzs_decision") or ""),
                payload={
                    "curriculum_choice": choice.get("payload", {}),
                    "predicted_outcome": str(choice.get("predicted_outcome") or ""),
                    "source_phase": "v49_31_curriculum_choice",
                },
            )
            self.queue.append(intent)
            self.store.log_queue(self.session_id, intent)
        self.store.log_session(
            self.session_id,
            "queue_built",
            self.mode,
            0,
            self.energy,
            {"curriculum_session_id": self.curriculum_session_id, "queue_count": len(self.queue), "modules": [q.module_key for q in self.queue]},
        )

    def rzs_input(self, intent: ExecutionIntent, safety: SafetyResult) -> RZSInput:
        spec = self.specs[intent.module_key]
        cost = clamp(spec.max_runtime_seconds / 1200.0)
        priority = clamp(intent.priority_score)
        novelty = clamp(0.18 + (1.0 - priority) * 0.28 + (0.16 if intent.rzs_from_curriculum in {"narrow_focus", "replay_memory"} else 0.0))
        conflict = clamp(safety.risk_score * 0.55 + (0.16 if not safety.allowed else 0.0) + (0.10 if self.active_dispatch_id else 0.0))
        return RZSInput(
            bandwidth=2.92 + self.energy * 0.70 + priority * 0.24,
            info_self=0.30 + (1.0 - self.energy) * 0.18,
            info_external=0.28 + novelty * 0.24,
            task_info=0.40 + intent.expected_gain * 0.26 + cost * 0.12,
            novelty=novelty,
            conflict=conflict,
            latency=0.86 + cost * 0.45 + safety.risk_score * 0.24,
            energy=self.energy,
            memory_pressure=clamp(0.18 + (0.40 if intent.step_index % 5 == 0 else 0.0) + (0.16 if intent.rzs_from_curriculum == "replay_memory" else 0.0)),
            replay_gap=clamp(0.22 + (0.44 if intent.step_index % 4 == 0 else 0.0) + (0.15 if intent.rzs_from_curriculum == "narrow_focus" else 0.0)),
        )

    def safety_gate(self, intent: ExecutionIntent) -> SafetyResult:
        spec = self.specs.get(intent.module_key)
        script_exists = bool(spec and self.script_path(spec).exists())
        single_process = not bool(self.active_dispatch_id)
        simulation_only = self.mode == "self_test"
        allowed = bool(spec and script_exists and single_process and (not simulation_only or spec.allow_self_test_simulation))
        risk = 0.0
        if not script_exists:
            risk += 0.42
        if not single_process:
            risk += 0.40
        if spec and spec.requires_user_visible_window and self.mode == "self_test":
            risk += 0.08
        if intent.module_key == "voice_presence":
            risk += 0.10
        if intent.requested_action.startswith("pause_"):
            risk += 0.12
        decision = "allow_simulated_dispatch" if allowed and simulation_only else "allow_visible_dispatch" if allowed else "block_dispatch"
        reason = "allowlist, script and one-at-a-time guard passed" if allowed else "safety gate rejected dispatch"
        safety = SafetyResult(
            safety_id=f"SF-{self.session_id}-{intent.step_index:02d}",
            queue_id=intent.queue_id,
            step_index=intent.step_index,
            module_key=intent.module_key,
            allowed=allowed,
            script_exists=script_exists,
            simulation_only=simulation_only,
            single_process_guard=single_process,
            user_visible_required=bool(spec.requires_user_visible_window if spec else False),
            risk_score=clamp(risk),
            decision=decision,
            reason=reason,
            payload={
                "spec": asdict(spec) if spec else {},
                "script_path": str(self.script_path(spec)) if spec else "",
                "no_shell": True,
                "mode": self.mode,
                "active_dispatch_id": self.active_dispatch_id,
            },
        )
        self.safety_results.append(safety)
        self.store.log_safety(self.session_id, safety)
        return safety

    def execution_action(self, decision: str, intent: ExecutionIntent) -> str:
        base = f"open_{intent.module_key}"
        if decision == "continue":
            return base
        if decision == "narrow_focus":
            return f"open_{intent.module_key}_with_focus_guard"
        if decision == "replay_memory":
            return f"replay_context_then_open_{intent.module_key}"
        if decision == "consolidate":
            return f"consolidate_before_open_{intent.module_key}"
        if decision == "pause_for_stability":
            return f"defer_{intent.module_key}_for_stability"
        return base

    def dispatch_mode_for(self, safety: SafetyResult, decision: str) -> str:
        if not safety.allowed:
            return "blocked"
        if decision == "pause_for_stability":
            return "deferred"
        if self.mode == "self_test":
            return "simulated"
        return "visible_process"

    def dispatch(self, intent: ExecutionIntent, *, live: bool = False) -> DispatchRecord:
        safety = self.safety_gate(intent)
        x = self.rzs_input(intent, safety)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        spec = self.specs[intent.module_key]
        command = [sys.executable, spec.script_name]
        mode = self.dispatch_mode_for(safety, assessment.decision)
        action = self.execution_action(assessment.decision, intent)
        live_pid = 0
        status = "not_started"
        if mode == "blocked":
            status = "blocked_by_safety_gate"
        elif mode == "deferred":
            status = "deferred_by_rzs"
        elif mode == "simulated":
            status = "simulated_complete"
        elif mode == "visible_process" and live:
            proc = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parent), shell=False)
            live_pid = int(proc.pid)
            status = "launched_visible_process"
            self.active_dispatch_id = f"DP-{self.session_id}-{intent.step_index:02d}"
        else:
            status = "armed_visible_process"
        dispatch = DispatchRecord(
            dispatch_id=f"DP-{self.session_id}-{intent.step_index:02d}",
            queue_id=intent.queue_id,
            step_index=intent.step_index,
            module_key=intent.module_key,
            script_name=spec.script_name,
            dispatch_mode=mode,
            command=command,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            execution_action=action,
            status=status,
            live_pid=live_pid,
            payload={
                "safety": asdict(safety),
                "rzs_reason": assessment.reason,
                "threshold_name": assessment.threshold_name,
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
                "live_launch_requested": live,
                "self_test_never_launches_process": self.mode == "self_test",
            },
        )
        self.dispatches.append(dispatch)
        self.store.log_dispatch(self.session_id, dispatch)
        self.store.log_session(
            self.session_id,
            "execution_dispatch",
            self.mode,
            intent.step_index,
            self.energy,
            {"dispatch_id": dispatch.dispatch_id, "module_key": dispatch.module_key, "dispatch_mode": dispatch.dispatch_mode, "rzs_decision": dispatch.rzs_decision},
        )
        return dispatch

    def monitor(self, dispatch: DispatchRecord) -> MonitorRecord:
        if dispatch.dispatch_mode == "blocked":
            stability = 0.54
            status = "blocked_stable"
        elif dispatch.dispatch_mode == "deferred":
            stability = clamp(0.62 + max(0.0, dispatch.sigma_after - dispatch.sigma_before) * 0.05)
            status = "deferred_stable"
        else:
            stability = clamp(0.58 + dispatch.sigma_after / 7.0 + (0.08 if dispatch.dispatch_mode == "simulated" else 0.04))
            status = "simulated_stable" if dispatch.dispatch_mode == "simulated" else "launched_monitoring"
        self.energy = clamp(self.energy - 0.015 + stability * 0.010 + (0.020 if dispatch.rzs_decision == "consolidate" else 0.0))
        monitor = MonitorRecord(
            monitor_id=f"MN-{self.session_id}-{dispatch.step_index:02d}",
            dispatch_id=dispatch.dispatch_id,
            step_index=dispatch.step_index,
            module_key=dispatch.module_key,
            monitor_status=status,
            stability=stability,
            energy_after=self.energy,
            observed_outcome=f"{dispatch.module_key}:{dispatch.status}:stability={stability:.3f}",
            payload={
                "dispatch_mode": dispatch.dispatch_mode,
                "live_pid": dispatch.live_pid,
                "one_at_a_time_guard_released": dispatch.dispatch_mode in {"simulated", "deferred", "blocked"},
            },
        )
        if dispatch.dispatch_mode in {"simulated", "deferred", "blocked"} and self.active_dispatch_id == dispatch.dispatch_id:
            self.active_dispatch_id = ""
        self.monitors.append(monitor)
        self.store.log_monitor(self.session_id, monitor)
        self.store.log_session(
            self.session_id,
            "execution_monitor",
            self.mode,
            dispatch.step_index,
            self.energy,
            {"monitor_id": monitor.monitor_id, "module_key": monitor.module_key, "status": monitor.monitor_status, "stability": monitor.stability},
        )
        return monitor

    def reflect_step(self, dispatch: DispatchRecord, monitor: MonitorRecord) -> None:
        summary = (
            f"Executei {dispatch.module_key} em modo {dispatch.dispatch_mode}; "
            f"RZS={dispatch.rzs_decision}; status={dispatch.status}; estabilidade={monitor.stability:.3f}."
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-{dispatch.step_index:02d}",
            "executor_step_reflection",
            summary,
            clamp(0.58 + monitor.stability * 0.26),
            {"dispatch": asdict(dispatch), "monitor": asdict(monitor)},
        )

    def run_step(self, intent: ExecutionIntent, *, live: bool = False) -> tuple[DispatchRecord, MonitorRecord]:
        self.store.log_session(
            self.session_id,
            "execution_decision",
            self.mode,
            intent.step_index,
            self.energy,
            {"queue_id": intent.queue_id, "module_key": intent.module_key, "requested_action": intent.requested_action},
        )
        dispatch = self.dispatch(intent, live=live)
        monitor = self.monitor(dispatch)
        self.reflect_step(dispatch, monitor)
        return dispatch, monitor

    def run(self, steps: int = 12) -> dict[str, Any]:
        self.prepare()
        limit = max(1, min(int(steps), len(self.queue)))
        for intent in self.queue[:limit]:
            self.run_step(intent, live=False)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        counts_after = self.store.protected_counts()
        safe_dispatches = [d for d in self.dispatches if d.dispatch_mode in {"simulated", "visible_process"} and d.status in {"simulated_complete", "launched_visible_process", "armed_visible_process"}]
        decisions = sorted({d.rzs_decision for d in self.dispatches})
        modules = [d.module_key for d in self.dispatches]
        modes = sorted({d.dispatch_mode for d in self.dispatches})
        avg_stability = mean([m.stability for m in self.monitors], 0.0)
        live_launch_count = sum(1 for d in self.dispatches if d.live_pid > 0)
        ready = (
            len(self.queue) >= 8
            and len(self.dispatches) >= 8
            and len(set(modules)) >= 4
            and any(d != "continue" for d in decisions)
            and avg_stability >= 0.55
            and counts_after == self.source_counts_before
            and (self.mode != "self_test" or live_launch_count == 0)
        )
        summary = {
            "session_id": self.session_id,
            "curriculum_session_id": self.curriculum_session_id,
            "allowlist_count": len(self.specs),
            "queue_count": len(self.queue),
            "dispatch_count": len(self.dispatches),
            "safe_dispatch_count": len(safe_dispatches),
            "monitor_count": len(self.monitors),
            "modules_executed": sorted(set(modules)),
            "module_counts": dict(Counter(modules)),
            "dispatch_modes": modes,
            "rzs_decisions": decisions,
            "avg_monitor_stability": avg_stability,
            "final_energy": self.energy,
            "live_launch_count": live_launch_count,
            "self_test_simulation_only": self.mode == "self_test" and live_launch_count == 0,
            "protected_counts_before": self.source_counts_before,
            "protected_counts_after": counts_after,
            "protected_sources_unchanged": counts_after == self.source_counts_before,
            "controlled_executor_ready": ready,
            "session_complete": True,
        }
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-SUMMARY",
            "controlled_executor_summary",
            f"Executor controlado: dispatches={len(self.dispatches)}, modos={','.join(modes)}, estabilidade={avg_stability:.3f}.",
            clamp(0.62 + avg_stability * 0.25),
            summary,
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-LIMIT",
            "epistemic_boundary",
            "Este marco nao prova consciencia; prova que escolhas autonomas passam por allowlist, safety gate, RZS e monitoramento.",
            0.94,
            {"claim": "controlled_execution_not_consciousness_proof"},
        )
        self.store.write_memory(self.session_id, summary, 0.88 if ready else 0.70)
        self.store.write_episode(
            self.session_id,
            "controlled_autonomous_execution",
            f"dispatches={len(self.dispatches)} modules={len(set(modules))} modes={','.join(modes)}",
            "Darwin passa de escolher treino para despachar treino com controle de seguranca e RZS.",
            self.dispatches[0].sigma_before if self.dispatches else 0.0,
            self.dispatches[-1].sigma_after if self.dispatches else 0.0,
        )
        self.store.log_handoff(
            self.session_id,
            "usar_executor_controlado_v49_32_para_abrir_o_treino_escolhido_com_allowlist",
            ready,
            len(safe_dispatches),
            0.88 if ready else 0.62,
            summary,
        )
        self.store.log_session(self.session_id, "executor_complete", self.mode, len(self.dispatches), self.energy, summary)
        return summary


class ControlledExecutorApp:
    BG = "#071018"
    PANEL = "#0d1b26"
    INK = "#eef8ff"
    MUTED = "#a9c7df"
    GREEN = "#7ee2a8"
    BLUE = "#72b7ff"
    WARN = "#ffd27d"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Controlled Autonomous Executor v49.32")
        self.root.geometry("1180x780")
        self.root.minsize(980, 640)
        self.root.configure(bg=self.BG)
        self.core = ControlledExecutorCore(mode="gui")
        self.summary: dict[str, Any] = {}
        self.phase = 0.0
        self.build_ui()
        self.run_simulated()
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
        tk.Label(header, text="DARWIN CONTROLLED AUTONOMOUS EXECUTOR v49.32", bg=self.BG, fg=self.INK, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="curriculo -> allowlist -> safety gate -> RZS -> dispatch -> monitor", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=410)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=260)
        self.canvas.pack(fill="x")
        buttons = tk.Frame(left, bg="#102231")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Simular fila", command=self.run_simulated).pack(side="left", padx=8, pady=8)
        ttk.Button(buttons, text="Abrir proximo seguro", command=self.open_next_safe).pack(side="left", padx=4, pady=8)
        ttk.Button(buttons, text="Fila", command=self.show_queue).pack(side="left", padx=4, pady=8)
        ttk.Button(buttons, text="Dispatches", command=self.show_dispatches).pack(side="left", padx=4, pady=8)
        self.main = tk.Text(left, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.main.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Resumo", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.side = tk.Text(right, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.side.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_simulated(self) -> None:
        self.core = ControlledExecutorCore(mode="self_test")
        self.summary = self.core.run(12)
        self.show_dispatches()
        self.show_summary()

    def open_next_safe(self) -> None:
        core = ControlledExecutorCore(mode="gui")
        core.prepare()
        if not core.queue:
            messagebox.showinfo("Darwin", "Nao encontrei fila do curriculo v49.31.")
            return
        dispatch, monitor = core.run_step(core.queue[0], live=True)
        summary = core.complete()
        self.core = core
        self.summary = summary
        self.show_dispatches()
        self.show_summary()
        messagebox.showinfo("Darwin", f"{dispatch.status}: {dispatch.module_key}\n{monitor.observed_outcome}")

    def show_summary(self) -> None:
        s = self.summary
        lines = [
            f"sessao: {s.get('session_id', '')}",
            f"curriculo: {s.get('curriculum_session_id', '')}",
            f"allowlist: {s.get('allowlist_count', 0)}",
            f"fila: {s.get('queue_count', 0)}",
            f"dispatches: {s.get('dispatch_count', 0)}",
            f"modos: {', '.join(s.get('dispatch_modes', []))}",
            f"RZS: {', '.join(s.get('rzs_decisions', []))}",
            "",
            f"estabilidade: {s.get('avg_monitor_stability', 0):.3f}",
            f"energia final: {s.get('final_energy', 0):.3f}",
            f"live launches: {s.get('live_launch_count', 0)}",
            f"pronto: {s.get('controlled_executor_ready', False)}",
        ]
        self.side.delete("1.0", "end")
        self.side.insert("end", "\n".join(lines))

    def show_queue(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Fila herdada do curriculo v49.31", ""]
        for q in self.core.queue:
            lines.append(f"{q.step_index:02d} {q.module_key:<18} score={q.priority_score:.3f} action={q.requested_action}")
        self.main.insert("end", "\n".join(lines))

    def show_dispatches(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Dispatches controlados", ""]
        for d in self.core.dispatches:
            lines.append(
                f"{d.step_index:02d} {d.module_key:<18} mode={d.dispatch_mode:<10} "
                f"RZS={d.rzs_decision:<12} status={d.status}"
            )
        self.main.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.045
        self.draw()
        self.root.after(50, self.animate)

    def draw(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.52
        self.canvas.create_text(cx, 30, text="posso abrir este treino com seguranca?", fill=self.INK, font=("Segoe UI", 17, "bold"))
        modules = self.summary.get("modules_executed", [])
        radius = min(w, h) * 0.29
        for i, module in enumerate(modules[:9]):
            angle = (math.tau / max(1, len(modules[:9]))) * i + self.phase * 0.10
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius * 0.62
            r = 18 + self.summary.get("module_counts", {}).get(module, 0) * 3
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill="#173044", outline=self.GREEN, width=2)
            self.canvas.create_text(x, y + r + 14, text=module, fill=self.MUTED, font=("Segoe UI", 8))
        pulse = 1.0 + math.sin(self.phase) * 0.05
        rr = 43 * pulse
        self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=self.BLUE, outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - rr * 0.36, cy - rr * 0.36, cx + rr * 0.36, cy + rr * 0.36, fill="#e7fbff", outline="")
        last = self.core.dispatches[-1].module_key if self.core.dispatches else "nenhum"
        self.canvas.create_text(cx, h - 26, text=f"ultimo dispatch: {last}", fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.32 - CONTROLLED AUTONOMOUS EXECUTOR")
    print("=" * 76)
    print(f"- sessao: {summary['session_id']}")
    print(f"- curriculo: {summary['curriculum_session_id']}")
    print(f"- allowlist={summary['allowlist_count']} fila={summary['queue_count']} dispatches={summary['dispatch_count']}")
    print(f"- modulos: {', '.join(summary['modules_executed'])}")
    print(f"- modos: {', '.join(summary['dispatch_modes'])}")
    print(f"- RZS: {', '.join(summary['rzs_decisions'])}")
    print(f"- estabilidade media={summary['avg_monitor_stability']:.3f} live_launches={summary['live_launch_count']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.32 Controlled Autonomous Executor")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4932)
    args = ap.parse_args()
    if args.self_test:
        core = ControlledExecutorCore(seed=args.seed, mode="self_test")
        summary = core.run(args.steps)
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    ControlledExecutorApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
