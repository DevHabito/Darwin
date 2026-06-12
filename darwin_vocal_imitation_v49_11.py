from __future__ import annotations

"""
DARWIN v49.11 - Vocal Imitation Nursery

Objetivo:
Depois de aprender primeiras palavras como experiencia (v49.10),
Darwin comeca a pratica vocal: tenta repetir silabas e palavras,
erra, ajusta pesos articulatorios, recebe reforco e cria nos de
experiencia vocal.

Nao depende de reconhecimento de fala instalado. A voz usa o TTS
local do Windows quando disponivel; o erro articulatorio inicial e
um modelo interno/simulado auditavel.

Uso:
    py darwin_vocal_imitation_v49_11.py
    py darwin_vocal_imitation_v49_11.py --self-test --details
"""

import argparse
import json
import math
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
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

FW_MEANINGS = "voice_word_meanings_v49_10"
FW_NODES = "voice_first_word_nodes_v49_10"
FW_SESSIONS = "voice_first_word_sessions_v49_10"

VI_SESSIONS = "vocal_imitation_sessions_v49_11"
VI_TARGETS = "vocal_imitation_targets_v49_11"
VI_ATTEMPTS = "vocal_motor_attempts_v49_11"
VI_WEIGHTS = "vocal_articulation_weights_v49_11"
VI_FEEDBACK = "vocal_caregiver_feedback_v49_11"
VI_REPLAY = "vocal_imitation_replay_v49_11"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def syllables(word: str) -> list[str]:
    table = {
        "mamae": ["ma", "mae"],
        "papai": ["pa", "pai"],
        "felipe": ["fe", "li", "pe"],
        "darwin": ["dar", "win"],
        "nao": ["nao"],
        "ajuda": ["a", "ju", "da"],
        "oi": ["oi"],
        "agua": ["a", "gua"],
        "brincar": ["brin", "car"],
    }
    return table.get(word, [word])


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[-1]


def word_similarity(a: str, b: str) -> float:
    denom = max(1, max(len(a), len(b)))
    return clamp(1.0 - edit_distance(a, b) / denom)


@dataclass
class VocalTarget:
    canonical_word: str
    meaning_key: str
    relational_meaning: str
    syllables: list[str]
    source_session: str = ""
    priority: float = 0.5


@dataclass
class MotorUnit:
    unit: str
    clarity: float
    control: float
    attempts: int = 0
    successes: int = 0


@dataclass
class VocalAttempt:
    attempt_id: str
    cycle_id: int
    target_word: str
    target_syllables: list[str]
    produced_syllables: list[str]
    produced_text: str
    similarity: float
    articulation_error: float
    feedback_value: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    response_text: str


class VocalImitationStore:
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
                CREATE TABLE IF NOT EXISTS {VI_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    source_first_words_session_id TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VI_TARGETS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    target_word TEXT NOT NULL,
                    meaning_key TEXT NOT NULL,
                    relational_meaning TEXT NOT NULL,
                    syllables_json TEXT NOT NULL DEFAULT '[]',
                    priority REAL NOT NULL DEFAULT 0.0,
                    source_first_words_session_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, target_word)
                );

                CREATE TABLE IF NOT EXISTS {VI_ATTEMPTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL UNIQUE,
                    cycle_id INTEGER NOT NULL,
                    target_word TEXT NOT NULL,
                    target_syllables_json TEXT NOT NULL DEFAULT '[]',
                    produced_syllables_json TEXT NOT NULL DEFAULT '[]',
                    produced_text TEXT NOT NULL,
                    similarity REAL NOT NULL DEFAULT 0.0,
                    articulation_error REAL NOT NULL DEFAULT 0.0,
                    feedback_value REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    response_text TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VI_WEIGHTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    motor_unit TEXT NOT NULL,
                    clarity_before REAL NOT NULL DEFAULT 0.0,
                    clarity_after REAL NOT NULL DEFAULT 0.0,
                    control_before REAL NOT NULL DEFAULT 0.0,
                    control_after REAL NOT NULL DEFAULT 0.0,
                    update_reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VI_FEEDBACK} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    target_word TEXT NOT NULL,
                    feedback_kind TEXT NOT NULL,
                    feedback_value REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VI_REPLAY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    source_attempt_id TEXT NOT NULL,
                    target_word TEXT NOT NULL,
                    error_before REAL NOT NULL DEFAULT 0.0,
                    error_after REAL NOT NULL DEFAULT 0.0,
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

    def latest_first_words_session(self) -> str:
        with self.connect() as conn:
            if not self.table_exists(conn, FW_SESSIONS):
                return ""
            row = conn.execute(
                f"""
                SELECT session_id
                FROM {FW_SESSIONS}
                WHERE phase='first_words_complete'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            return str(row["session_id"]) if row else ""

    def load_first_word_targets(self) -> list[VocalTarget]:
        source = self.latest_first_words_session()
        out: list[VocalTarget] = []
        with self.connect() as conn:
            if source and self.table_exists(conn, FW_MEANINGS):
                rows = conn.execute(
                    f"""
                    SELECT canonical_word, meaning_key, relational_meaning,
                           exposure_count, meaning_confidence, sound_confidence
                    FROM {FW_MEANINGS}
                    WHERE session_id=?
                    ORDER BY exposure_count DESC, meaning_confidence DESC
                    """,
                    (source,),
                ).fetchall()
                for row in rows:
                    word = str(row["canonical_word"])
                    priority = clamp(
                        0.30
                        + float(row["meaning_confidence"]) * 0.32
                        + float(row["sound_confidence"]) * 0.24
                        + min(0.20, int(row["exposure_count"]) * 0.035)
                    )
                    out.append(
                        VocalTarget(
                            word,
                            str(row["meaning_key"]),
                            str(row["relational_meaning"]),
                            syllables(word),
                            source,
                            priority,
                        )
                    )
        if out:
            return out
        fallback = [
            ("mamae", "caregiver_mother", "cuidado e presenca"),
            ("papai", "caregiver_father", "presenca e protecao"),
            ("felipe", "primary_person", "pessoa que ensina Darwin"),
            ("darwin", "self_name", "nome proprio do Darwin"),
        ]
        return [VocalTarget(w, k, m, syllables(w), "", 0.50) for w, k, m in fallback]

    def log_session(self, session_id: str, phase: str, source: str, mode: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VI_SESSIONS} (
                    timestamp, session_id, phase, source_first_words_session_id,
                    mode, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, source, mode, js(payload or {})),
            )
            conn.commit()

    def log_target(self, session_id: str, target: VocalTarget) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VI_TARGETS} (
                    timestamp, session_id, target_word, meaning_key,
                    relational_meaning, syllables_json, priority,
                    source_first_words_session_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, target_word) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    priority=excluded.priority,
                    payload_json=excluded.payload_json
                """,
                (
                    now(),
                    session_id,
                    target.canonical_word,
                    target.meaning_key,
                    target.relational_meaning,
                    js(target.syllables),
                    target.priority,
                    target.source_session,
                    js({"source": "first_words_v49_10"}),
                ),
            )
            conn.commit()

    def log_attempt(self, session_id: str, attempt: VocalAttempt, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VI_ATTEMPTS} (
                    timestamp, session_id, attempt_id, cycle_id, target_word,
                    target_syllables_json, produced_syllables_json, produced_text,
                    similarity, articulation_error, feedback_value,
                    rzs_decision, sigma_before, sigma_after, response_text,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    attempt.attempt_id,
                    attempt.cycle_id,
                    attempt.target_word,
                    js(attempt.target_syllables),
                    js(attempt.produced_syllables),
                    attempt.produced_text,
                    attempt.similarity,
                    attempt.articulation_error,
                    attempt.feedback_value,
                    attempt.rzs_decision,
                    attempt.sigma_before,
                    attempt.sigma_after,
                    attempt.response_text,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_weight(self, session_id: str, cycle_id: int, unit: MotorUnit, clarity_before: float, control_before: float, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VI_WEIGHTS} (
                    timestamp, session_id, cycle_id, motor_unit,
                    clarity_before, clarity_after, control_before, control_after,
                    update_reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    cycle_id,
                    unit.unit,
                    clarity_before,
                    unit.clarity,
                    control_before,
                    unit.control,
                    reason,
                    js({"attempts": unit.attempts, "successes": unit.successes}),
                ),
            )
            conn.commit()

    def log_feedback(self, session_id: str, attempt: VocalAttempt, kind: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VI_FEEDBACK} (
                    timestamp, session_id, attempt_id, target_word,
                    feedback_kind, feedback_value, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, attempt.attempt_id, attempt.target_word, kind, attempt.feedback_value, js(payload or {})),
            )
            conn.commit()

    def log_replay(self, session_id: str, replay_id: str, source: VocalAttempt, error_after: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VI_REPLAY} (
                    timestamp, session_id, replay_id, source_attempt_id,
                    target_word, error_before, error_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, replay_id, source.attempt_id, source.target_word, source.articulation_error, error_after, js(payload or {})),
            )
            conn.commit()

    def write_memory(self, key: str, content: str, confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    confidence=max(semantic_memory.confidence, excluded.confidence),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (key, content, clamp(confidence, 0.0, 0.99), "darwin_vocal_imitation_v49_11", now()),
            )
            conn.commit()

    def write_episode(self, context: str, action: str, outcome: str, lesson: str, sigma_before: float, sigma_after: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), "darwin_vocal_imitation_v49_11", context, action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class VocalImitationBrain:
    def __init__(self, store: VocalImitationStore | None = None, seed: int = 4911, mode: str = "gui") -> None:
        self.store = store or VocalImitationStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.mode = mode
        self.session_id = f"V4911-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.targets = self.store.load_first_word_targets()
        self.source_first_words = self.targets[0].source_session if self.targets else ""
        self.units = self.seed_motor_units()
        self.attempts: list[VocalAttempt] = []
        self.last_replay_cycle = 0
        self.store.log_session(
            self.session_id,
            "vocal_imitation_start",
            self.source_first_words,
            mode,
            {"target_count": len(self.targets), "targets": [t.canonical_word for t in self.targets]},
        )
        for target in self.targets:
            self.store.log_target(self.session_id, target)

    def seed_motor_units(self) -> dict[str, MotorUnit]:
        units: dict[str, MotorUnit] = {}
        for target in self.targets:
            for unit in target.syllables:
                if unit not in units:
                    base = 0.12 + self.rng.random() * 0.10
                    if unit in {"ma", "pa", "a"}:
                        base += 0.08
                    units[unit] = MotorUnit(unit, clamp(base), clamp(base * 0.82 + 0.04))
        return units

    def rzs_input(self, cycle_id: int) -> RZSInput:
        avg_clarity = mean([u.clarity for u in self.units.values()])
        recent_error = mean([a.articulation_error for a in self.attempts[-6:]]) if self.attempts else 0.72
        replay_gap = clamp((cycle_id - self.last_replay_cycle) / 12.0)
        return RZSInput(
            bandwidth=4.0 + avg_clarity * 1.2,
            info_self=0.34 + (1.0 - avg_clarity) * 0.22,
            info_external=0.36,
            task_info=0.54 + recent_error * 0.32,
            novelty=clamp(0.58 - avg_clarity * 0.24),
            conflict=clamp(0.18 + recent_error * 0.46),
            latency=0.78 + recent_error * 0.38,
            energy=0.82,
            memory_pressure=clamp(1.0 - avg_clarity),
            replay_gap=replay_gap,
        )

    def choose_target(self, cycle_id: int, decision: str) -> VocalTarget:
        if decision == "narrow_focus":
            return min(self.targets, key=lambda t: mean([self.units[u].clarity for u in t.syllables]))
        if decision == "replay_memory" and self.attempts:
            weakest = max(self.attempts[-8:], key=lambda a: a.articulation_error)
            for target in self.targets:
                if target.canonical_word == weakest.target_word:
                    return target
        ordered = sorted(self.targets, key=lambda t: (-t.priority, t.canonical_word))
        return ordered[(cycle_id - 1) % len(ordered)]

    def produce_unit(self, unit: MotorUnit, decision: str) -> str:
        clarity = unit.clarity
        if decision in {"narrow_focus", "replay_memory"}:
            clarity += 0.08
        if self.rng.random() < clarity:
            return unit.unit
        confusions = {
            "ma": ["ba", "na", "m"],
            "mae": ["me", "mai", "ma"],
            "pa": ["ba", "ta", "p"],
            "pai": ["pa", "bai", "pe"],
            "fe": ["ve", "pe", "f"],
            "li": ["ri", "i", "le"],
            "pe": ["be", "te", "pa"],
            "dar": ["da", "bar", "ar"],
            "win": ["vin", "in", "wi"],
            "nao": ["na", "ao", "mao"],
            "ju": ["zu", "du", "u"],
            "da": ["ta", "ba", "a"],
        }
        return self.rng.choice(confusions.get(unit.unit, [unit.unit[:1], unit.unit]))

    def attempt(self, cycle_id: int, feedback_override: float | None = None) -> VocalAttempt:
        x = self.rzs_input(cycle_id)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        if assessment.decision == "replay_memory" and self.attempts:
            self.replay(cycle_id)
        target = self.choose_target(cycle_id, assessment.decision)
        produced = [self.produce_unit(self.units[u], assessment.decision) for u in target.syllables]
        produced_text = "".join(produced)
        expected_text = "".join(target.syllables)
        similarity = word_similarity(produced_text, expected_text)
        error = 1.0 - similarity
        if feedback_override is None:
            feedback = clamp(similarity * 0.78 + target.priority * 0.22)
        else:
            feedback = clamp(feedback_override)
        response = self.response_for(target, produced_text, similarity, assessment.decision)
        attempt = VocalAttempt(
            attempt_id=f"imit:{self.session_id}:{cycle_id:04d}:{target.canonical_word}",
            cycle_id=cycle_id,
            target_word=target.canonical_word,
            target_syllables=target.syllables,
            produced_syllables=produced,
            produced_text=produced_text,
            similarity=similarity,
            articulation_error=error,
            feedback_value=feedback,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            response_text=response,
        )
        self.update_units(cycle_id, target, produced, similarity, feedback, assessment.decision)
        self.store.log_attempt(
            self.session_id,
            attempt,
            {
                "expected_text": expected_text,
                "meaning_key": target.meaning_key,
                "relational_meaning": target.relational_meaning,
            },
        )
        self.store.log_feedback(
            self.session_id,
            attempt,
            "internal_similarity" if feedback_override is None else "caregiver_override",
            {"similarity": similarity},
        )
        self.store.write_episode(
            f"vocal_imitation:{self.session_id}:{attempt.attempt_id}",
            "imitate_first_word",
            f"{target.canonical_word}->{produced_text}",
            "Vocal production improves when motor units are corrected after an attempt.",
            assessment.sigma,
            sigma_after,
        )
        self.attempts.append(attempt)
        return attempt

    def update_units(self, cycle_id: int, target: VocalTarget, produced: list[str], similarity: float, feedback: float, decision: str) -> None:
        learning_rate = 0.10 + feedback * 0.10
        if decision in {"narrow_focus", "replay_memory"}:
            learning_rate += 0.04
        for expected, got in zip(target.syllables, produced):
            unit = self.units[expected]
            clarity_before = unit.clarity
            control_before = unit.control
            unit.attempts += 1
            if expected == got:
                unit.successes += 1
                target_value = 0.92
                reason = "matched_syllable"
            else:
                target_value = 0.62 + similarity * 0.18
                reason = "corrected_confused_syllable"
            unit.clarity = clamp(unit.clarity + learning_rate * (target_value - unit.clarity))
            unit.control = clamp(unit.control + learning_rate * 0.82 * (target_value - unit.control))
            self.store.log_weight(self.session_id, cycle_id, unit, clarity_before, control_before, reason)

    def replay(self, cycle_id: int) -> None:
        source = max(self.attempts[-8:], key=lambda a: a.articulation_error)
        target = next(t for t in self.targets if t.canonical_word == source.target_word)
        for unit_name in target.syllables:
            unit = self.units[unit_name]
            clarity_before = unit.clarity
            control_before = unit.control
            unit.clarity = clamp(unit.clarity + 0.045)
            unit.control = clamp(unit.control + 0.035)
            self.store.log_weight(self.session_id, cycle_id, unit, clarity_before, control_before, "replay_motor_trace")
        error_after = max(0.0, source.articulation_error - 0.12)
        replay_id = f"vocal_replay:{self.session_id}:{cycle_id:04d}:{source.target_word}"
        self.store.log_replay(
            self.session_id,
            replay_id,
            source,
            error_after,
            {"rule": "increase motor clarity on worst recent attempt"},
        )
        self.last_replay_cycle = cycle_id

    def response_for(self, target: VocalTarget, produced: str, similarity: float, decision: str) -> str:
        if similarity >= 0.88:
            quality = "ficou perto"
        elif similarity >= 0.55:
            quality = "ainda esta torto, mas reconhecivel"
        else:
            quality = "errei o som"
        prefix = {
            "replay_memory": "Vou lembrar o som antes de tentar. ",
            "narrow_focus": "Vou focar em uma palavra. ",
            "pause_for_stability": "Vou tentar devagar. ",
        }.get(decision, "")
        return f"{prefix}Alvo {target.canonical_word}. Eu tentei dizer {produced}; {quality}."

    def run(self, cycles: int = 48) -> dict[str, Any]:
        cycles = max(16, int(cycles))
        for cycle_id in range(1, cycles + 1):
            self.attempt(cycle_id)
        if self.attempts:
            self.replay(cycles + 1)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        first = self.attempts[: max(1, len(self.attempts) // 4)]
        last = self.attempts[-max(1, len(self.attempts) // 4) :]
        avg_clarity = mean([u.clarity for u in self.units.values()])
        payload = {
            "session_complete": True,
            "attempt_count": len(self.attempts),
            "target_count": len(self.targets),
            "motor_unit_count": len(self.units),
            "first_error": mean([a.articulation_error for a in first]),
            "last_error": mean([a.articulation_error for a in last]),
            "mean_similarity": mean([a.similarity for a in self.attempts]),
            "mean_motor_clarity": avg_clarity,
            "source_first_words_session_id": self.source_first_words,
        }
        self.store.log_session(self.session_id, "vocal_imitation_complete", self.source_first_words, self.mode, payload)
        self.store.write_memory(
            f"vocal_imitation_v49_11:{self.session_id}",
            (
                f"Vocal imitation learned {payload['target_count']} first-word targets; "
                f"attempts={payload['attempt_count']}; first_error={payload['first_error']:.3f}; "
                f"last_error={payload['last_error']:.3f}; motor_clarity={payload['mean_motor_clarity']:.3f}."
            ),
            clamp(avg_clarity, 0.0, 0.95),
        )
        return {"session_id": self.session_id, **payload}


class SpeechEngine:
    def __init__(self, on_start, on_stop) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self.proc: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    def speak(self, text: str) -> None:
        with self.lock:
            self.stop()
            t = threading.Thread(target=self._worker, args=(text,), daemon=True)
            t.start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def _worker(self, text: str) -> None:
        self.on_start(text)
        try:
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = -2; $s.Volume = 100; "
                "$text = [Console]::In.ReadToEnd(); "
                "$s.Speak($text);"
            )
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            assert self.proc.stdin is not None
            self.proc.stdin.write(text)
            self.proc.stdin.close()
            self.proc.wait()
        except Exception:
            time.sleep(max(0.8, min(8.0, len(text) / 14.0)))
        finally:
            self.on_stop()


class VocalImitationApp:
    BG = "#071018"
    PANEL = "#10202d"
    INK = "#edf7fb"
    MUTED = "#93aabd"
    BLUE = "#58b0ff"
    GREEN = "#75e7a8"
    AMBER = "#f2bf72"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Vocal Imitation v49.11")
        self.root.geometry("1040x760")
        self.root.minsize(860, 640)
        self.root.configure(bg=self.BG)
        self.brain = VocalImitationBrain(mode="gui")
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking)
        self.tick = 0.0
        self.level = 0.0
        self.speaking = False
        self.speech_text = ""
        self.last_attempt: VocalAttempt | None = None
        self.cycle_id = 0

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x")
        ttk.Button(controls, text="Tentar palavra", command=self.try_word).pack(side="left", padx=(14, 8), pady=12)
        ttk.Button(controls, text="Bom", command=lambda: self.feedback(1.0)).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Quase", command=lambda: self.feedback(0.62)).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="De novo", command=self.replay).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Parar fala", command=self.stop_speech).pack(side="left", padx=(0, 14), pady=12)
        self.transcript = tk.Text(root, height=10, bg="#061019", fg=self.INK, insertbackground=self.INK, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.transcript.pack(fill="x")
        self.transcript.config(state="disabled")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.write("Darwin", "Estou praticando minha propria fala. Vou tentar repetir palavras que aprendi.")
        self.root.after(500, self.try_word)
        self.animate()

    def write(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")
        self.transcript.config(state="disabled")

    def try_word(self) -> None:
        self.cycle_id += 1
        attempt = self.brain.attempt(self.cycle_id)
        self.last_attempt = attempt
        self.write("Darwin", attempt.response_text)
        speak_text = " ".join(attempt.produced_syllables)
        self.speech.speak(speak_text)

    def feedback(self, value: float) -> None:
        if not self.last_attempt:
            return
        self.brain.store.log_feedback(
            self.brain.session_id,
            self.last_attempt,
            "caregiver_gui",
            {"manual_value": value},
        )
        self.write("Felipe", f"feedback {value:.2f}")

    def replay(self) -> None:
        if not self.brain.attempts:
            return
        self.brain.replay(self.cycle_id + 1)
        self.write("Darwin", "Vou reforcar a memoria motora e tentar de novo.")
        self.try_word()

    def stop_speech(self) -> None:
        self.speech.stop()
        self.stop_speaking()

    def start_speaking(self, text: str) -> None:
        self.speaking = True
        self.speech_text = text

    def stop_speaking(self) -> None:
        self.speaking = False
        self.level = 0.0

    def speech_energy(self) -> float:
        if not self.speaking or not self.speech_text:
            return 0.0
        idx = int((self.tick * 8.0) % max(1, len(self.speech_text)))
        ch = self.speech_text[idx]
        if ch.lower() in "aeiou":
            return 1.0
        if ch.isalpha():
            return 0.58
        return 0.25

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
        cy = h / 2 - 24
        attempt = self.last_attempt
        color = self.GREEN if attempt and attempt.similarity >= 0.75 else self.AMBER if attempt else self.BLUE
        radius = 82 + 32 * self.level
        x = cx + math.sin(self.tick * 2.1) * 28 * self.level
        y = cy + math.cos(self.tick * 1.8) * 20 * self.level
        for i in range(7, 0, -1):
            rr = radius + i * 18
            shade = 20 + i * 8
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline="", fill=f"#{shade//2:02x}{shade:02x}{min(130, shade+45):02x}")
        c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="#e5f7ff", width=3)
        inner = radius * (0.34 + self.level * 0.12)
        c.create_oval(x - inner, y - inner, x + inner, y + inner, fill="#ebfbff", outline="")
        c.create_text(cx, 38, text="DARWIN VOCAL IMITATION v49.11", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(cx, 70, text="pratica vocal: alvo -> tentativa -> erro -> ajuste", fill=self.MUTED, font=("Segoe UI", 11))
        if attempt:
            c.create_text(cx, h - 58, text=f"alvo {attempt.target_word}   produzido {attempt.produced_text}   similaridade {attempt.similarity:.2f}", fill=self.MUTED, font=("Segoe UI", 10))
            c.create_text(cx, h - 32, text=f"erro {attempt.articulation_error:.2f}   RZS {attempt.rzs_decision}", fill=self.MUTED, font=("Segoe UI", 10))

    def on_close(self) -> None:
        self.speech.stop()
        result = self.brain.complete()
        self.write("Sistema", f"Sessao encerrada: {result['session_id']}")
        self.root.destroy()


def run_self_test(cycles: int = 48, details: bool = False) -> dict[str, Any]:
    brain = VocalImitationBrain(mode="self_test")
    result = brain.run(cycles=cycles)
    if details:
        print(js(result))
    else:
        print(
            f"DARWIN v49.11 vocal imitation self-test concluido: "
            f"session={result['session_id']} attempts={result['attempt_count']}"
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Vocal Imitation Nursery v49.11")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cycles", type=int, default=48)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test(cycles=args.cycles, details=args.details)
        return 0
    root = tk.Tk()
    VocalImitationApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
