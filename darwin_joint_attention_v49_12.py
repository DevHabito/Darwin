from __future__ import annotations

"""
DARWIN v49.12 - Joint Attention Nursery

Objetivo:
Depois de primeiras palavras (v49.10) e imitacao vocal (v49.11),
Darwin aprende atencao compartilhada: palavra + foco visual + objeto
+ significado relacional. O cuidador aponta; Darwin tenta prever a
referencia; erra; recebe correcao; reforca o vinculo.

Uso:
    py darwin_joint_attention_v49_12.py
    py darwin_joint_attention_v49_12.py --self-test --details
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

FW_SESSIONS = "voice_first_word_sessions_v49_10"
FW_MEANINGS = "voice_word_meanings_v49_10"
VI_SESSIONS = "vocal_imitation_sessions_v49_11"

JA_SESSIONS = "joint_attention_sessions_v49_12"
JA_SCENES = "joint_attention_scenes_v49_12"
JA_FOCUS = "joint_attention_focus_events_v49_12"
JA_BINDINGS = "joint_attention_word_bindings_v49_12"
JA_ERRORS = "joint_attention_prediction_errors_v49_12"
JA_REPLAY = "joint_attention_replay_v49_12"


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


@dataclass
class SceneEntity:
    entity_id: str
    label_word: str
    entity_kind: str
    relational_meaning: str
    color: str
    x: float
    y: float
    priority: float = 0.5
    source: str = ""


@dataclass
class BindingState:
    label_word: str
    entity_id: str
    strength: float
    confidence: float
    exposure_count: int = 0
    error_count: int = 0
    is_correct: bool = False


@dataclass
class FocusExperience:
    focus_id: str
    cycle_id: int
    target_word: str
    target_entity_id: str
    predicted_entity_id: str
    correct: bool
    confidence_before: float
    confidence_after: float
    binding_strength_before: float
    binding_strength_after: float
    prediction_error: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    response_text: str


class JointAttentionStore:
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
                CREATE TABLE IF NOT EXISTS {JA_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    source_first_words_session_id TEXT NOT NULL DEFAULT '',
                    source_vocal_imitation_session_id TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {JA_SCENES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    label_word TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    relational_meaning TEXT NOT NULL,
                    x REAL NOT NULL DEFAULT 0.0,
                    y REAL NOT NULL DEFAULT 0.0,
                    priority REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, entity_id)
                );

                CREATE TABLE IF NOT EXISTS {JA_FOCUS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    focus_id TEXT NOT NULL UNIQUE,
                    cycle_id INTEGER NOT NULL,
                    target_word TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    predicted_entity_id TEXT NOT NULL,
                    correct INTEGER NOT NULL DEFAULT 0,
                    confidence_before REAL NOT NULL DEFAULT 0.0,
                    confidence_after REAL NOT NULL DEFAULT 0.0,
                    binding_strength_before REAL NOT NULL DEFAULT 0.0,
                    binding_strength_after REAL NOT NULL DEFAULT 0.0,
                    prediction_error REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    response_text TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {JA_BINDINGS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    label_word TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    binding_strength REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    exposure_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    is_correct INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {JA_ERRORS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    focus_id TEXT NOT NULL,
                    target_word TEXT NOT NULL,
                    expected_entity_id TEXT NOT NULL,
                    predicted_entity_id TEXT NOT NULL,
                    error_kind TEXT NOT NULL,
                    correction_applied REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {JA_REPLAY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    source_focus_id TEXT NOT NULL,
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

    def latest_session(self, table: str, phase: str) -> str:
        with self.connect() as conn:
            if not self.table_exists(conn, table):
                return ""
            row = conn.execute(
                f"SELECT session_id FROM {table} WHERE phase=? ORDER BY id DESC LIMIT 1",
                (phase,),
            ).fetchone()
            return str(row["session_id"]) if row else ""

    def load_first_word_entities(self) -> tuple[str, list[SceneEntity]]:
        source = self.latest_session(FW_SESSIONS, "first_words_complete")
        rows: list[sqlite3.Row] = []
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
        colors = {
            "mamae": "#e879b9",
            "papai": "#62a6ff",
            "felipe": "#7ee787",
            "darwin": "#f2cc60",
            "nao": "#ff707a",
            "ajuda": "#b197fc",
            "agua": "#67d4ff",
            "brincar": "#f2a65a",
            "oi": "#a7f3d0",
        }
        positions = [(0.18, 0.32), (0.38, 0.24), (0.62, 0.27), (0.82, 0.34), (0.24, 0.68), (0.50, 0.70), (0.74, 0.66)]
        entities: list[SceneEntity] = []
        for idx, row in enumerate(rows):
            word = str(row["canonical_word"])
            x, y = positions[idx % len(positions)]
            priority = clamp(
                0.28
                + float(row["meaning_confidence"]) * 0.30
                + float(row["sound_confidence"]) * 0.20
                + min(0.16, int(row["exposure_count"]) * 0.03)
            )
            entities.append(
                SceneEntity(
                    entity_id=f"entity:{word}",
                    label_word=word,
                    entity_kind=str(row["meaning_key"]),
                    relational_meaning=str(row["relational_meaning"]),
                    color=colors.get(word, "#8ab4f8"),
                    x=x,
                    y=y,
                    priority=priority,
                    source=source,
                )
            )
        if entities:
            return source, entities
        fallback = [
            ("mamae", "caregiver_mother", "cuidado e presenca"),
            ("papai", "caregiver_father", "presenca e protecao"),
            ("felipe", "primary_person", "pessoa que ensina Darwin"),
            ("darwin", "self_name", "nome proprio do Darwin"),
            ("agua", "need_water", "necessidade basica simbolica"),
            ("brincar", "play", "exploracao segura"),
        ]
        for idx, (word, kind, meaning) in enumerate(fallback):
            x, y = positions[idx % len(positions)]
            entities.append(SceneEntity(f"entity:{word}", word, kind, meaning, colors.get(word, "#8ab4f8"), x, y, 0.45, "fallback"))
        return "", entities

    def log_session(self, session_id: str, phase: str, fw_source: str, vi_source: str, mode: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {JA_SESSIONS} (
                    timestamp, session_id, phase, source_first_words_session_id,
                    source_vocal_imitation_session_id, mode, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, fw_source, vi_source, mode, js(payload or {})),
            )
            conn.commit()

    def log_scene_entity(self, session_id: str, entity: SceneEntity) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {JA_SCENES} (
                    timestamp, session_id, entity_id, label_word, entity_kind,
                    relational_meaning, x, y, priority, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, entity_id) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    priority=excluded.priority,
                    payload_json=excluded.payload_json
                """,
                (
                    now(),
                    session_id,
                    entity.entity_id,
                    entity.label_word,
                    entity.entity_kind,
                    entity.relational_meaning,
                    entity.x,
                    entity.y,
                    entity.priority,
                    js({"color": entity.color, "source": entity.source}),
                ),
            )
            conn.commit()

    def log_focus(self, session_id: str, exp: FocusExperience, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {JA_FOCUS} (
                    timestamp, session_id, focus_id, cycle_id, target_word,
                    target_entity_id, predicted_entity_id, correct,
                    confidence_before, confidence_after,
                    binding_strength_before, binding_strength_after,
                    prediction_error, rzs_decision, sigma_before, sigma_after,
                    response_text, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    exp.focus_id,
                    exp.cycle_id,
                    exp.target_word,
                    exp.target_entity_id,
                    exp.predicted_entity_id,
                    1 if exp.correct else 0,
                    exp.confidence_before,
                    exp.confidence_after,
                    exp.binding_strength_before,
                    exp.binding_strength_after,
                    exp.prediction_error,
                    exp.rzs_decision,
                    exp.sigma_before,
                    exp.sigma_after,
                    exp.response_text,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_binding(self, session_id: str, binding: BindingState, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {JA_BINDINGS} (
                    timestamp, session_id, label_word, entity_id,
                    binding_strength, confidence, exposure_count,
                    error_count, is_correct, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    binding.label_word,
                    binding.entity_id,
                    binding.strength,
                    binding.confidence,
                    binding.exposure_count,
                    binding.error_count,
                    1 if binding.is_correct else 0,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_error(self, session_id: str, exp: FocusExperience, correction: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {JA_ERRORS} (
                    timestamp, session_id, focus_id, target_word,
                    expected_entity_id, predicted_entity_id, error_kind,
                    correction_applied, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    exp.focus_id,
                    exp.target_word,
                    exp.target_entity_id,
                    exp.predicted_entity_id,
                    "wrong_referent",
                    correction,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_replay(self, session_id: str, replay_id: str, source: FocusExperience, error_after: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {JA_REPLAY} (
                    timestamp, session_id, replay_id, source_focus_id,
                    target_word, error_before, error_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, replay_id, source.focus_id, source.target_word, source.prediction_error, error_after, js(payload or {})),
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
                (key, content, clamp(confidence, 0.0, 0.99), "darwin_joint_attention_v49_12", now()),
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
                (now(), "darwin_joint_attention_v49_12", context, action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class JointAttentionBrain:
    def __init__(self, store: JointAttentionStore | None = None, seed: int = 4912, mode: str = "gui") -> None:
        self.store = store or JointAttentionStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.mode = mode
        self.session_id = f"V4912-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.first_words_source, self.entities = self.store.load_first_word_entities()
        self.vocal_source = self.store.latest_session(VI_SESSIONS, "vocal_imitation_complete")
        self.bindings = self.seed_bindings()
        self.focus_events: list[FocusExperience] = []
        self.error_events: list[FocusExperience] = []
        self.last_replay_cycle = 0
        self.store.log_session(
            self.session_id,
            "joint_attention_start",
            self.first_words_source,
            self.vocal_source,
            mode,
            {"entity_count": len(self.entities), "entities": [e.label_word for e in self.entities]},
        )
        for entity in self.entities:
            self.store.log_scene_entity(self.session_id, entity)
        for binding in self.bindings.values():
            self.store.log_binding(self.session_id, binding, {"phase": "seed"})

    def seed_bindings(self) -> dict[tuple[str, str], BindingState]:
        bindings: dict[tuple[str, str], BindingState] = {}
        for entity in self.entities:
            for candidate in self.entities:
                correct = candidate.entity_id == entity.entity_id
                base = 0.18 + entity.priority * 0.08 if correct else 0.10 + self.rng.random() * 0.14
                confidence = 0.10 + entity.priority * 0.06 if correct else 0.06
                bindings[(entity.label_word, candidate.entity_id)] = BindingState(
                    entity.label_word,
                    candidate.entity_id,
                    clamp(base),
                    clamp(confidence),
                    is_correct=correct,
                )
        return bindings

    def rzs_input(self, cycle_id: int) -> RZSInput:
        correct_bindings = [b for b in self.bindings.values() if b.is_correct]
        avg_conf = mean([b.confidence for b in correct_bindings])
        recent_error = mean([e.prediction_error for e in self.focus_events[-8:]]) if self.focus_events else 0.72
        replay_gap = clamp((cycle_id - self.last_replay_cycle) / 14.0)
        return RZSInput(
            bandwidth=4.4 + avg_conf * 1.8,
            info_self=0.32 + (1.0 - avg_conf) * 0.24,
            info_external=0.48,
            task_info=0.62 + recent_error * 0.30,
            novelty=clamp(0.70 - avg_conf * 0.42),
            conflict=clamp(0.16 + recent_error * 0.50),
            latency=0.74 + recent_error * 0.42,
            energy=0.84,
            memory_pressure=clamp(1.0 - avg_conf),
            replay_gap=replay_gap,
        )

    def choose_entity(self, cycle_id: int, decision: str) -> SceneEntity:
        unexposed = []
        for entity in self.entities:
            b = self.bindings[(entity.label_word, entity.entity_id)]
            if b.exposure_count == 0:
                unexposed.append(entity)
        if unexposed:
            return sorted(unexposed, key=lambda e: e.label_word)[0]
        if decision == "narrow_focus":
            return min(self.entities, key=lambda e: self.bindings[(e.label_word, e.entity_id)].confidence)
        if decision == "replay_memory" and self.error_events:
            word = self.error_events[-1].target_word
            return next(e for e in self.entities if e.label_word == word)
        return sorted(self.entities, key=lambda e: (self.bindings[(e.label_word, e.entity_id)].exposure_count, -e.priority))[cycle_id % len(self.entities)]

    def predict_entity(self, target: SceneEntity, cycle_id: int, decision: str) -> str:
        correct = self.bindings[(target.label_word, target.entity_id)]
        if correct.exposure_count == 0:
            candidates = [e for e in self.entities if e.entity_id != target.entity_id]
            return candidates[cycle_id % len(candidates)].entity_id
        best_entity = target.entity_id
        best_score = -1.0
        for entity in self.entities:
            b = self.bindings[(target.label_word, entity.entity_id)]
            noise = self.rng.uniform(-0.018, 0.018)
            score = b.strength + b.confidence * 0.36 + noise
            if decision == "narrow_focus" and entity.entity_id == target.entity_id:
                score += 0.04
            if score > best_score:
                best_score = score
                best_entity = entity.entity_id
        return best_entity

    def observe(self, target_word: str | None = None, cycle_id: int | None = None) -> FocusExperience:
        cycle_id = cycle_id if cycle_id is not None else len(self.focus_events) + 1
        x = self.rzs_input(cycle_id)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        if assessment.decision == "replay_memory" and self.error_events:
            self.replay(cycle_id)
        if target_word:
            target = next((e for e in self.entities if e.label_word == target_word), None)
            if target is None:
                target = self.choose_entity(cycle_id, assessment.decision)
        else:
            target = self.choose_entity(cycle_id, assessment.decision)
        correct_binding = self.bindings[(target.label_word, target.entity_id)]
        strength_before = correct_binding.strength
        confidence_before = correct_binding.confidence
        predicted_id = self.predict_entity(target, cycle_id, assessment.decision)
        correct = predicted_id == target.entity_id
        correction = self.update_bindings(target, predicted_id, correct, assessment.decision)
        prediction_error = 0.0 if correct else 1.0
        response = self.response_for(target, predicted_id, correct, assessment.decision)
        exp = FocusExperience(
            focus_id=f"joint:{self.session_id}:{cycle_id:04d}:{target.label_word}",
            cycle_id=cycle_id,
            target_word=target.label_word,
            target_entity_id=target.entity_id,
            predicted_entity_id=predicted_id,
            correct=correct,
            confidence_before=confidence_before,
            confidence_after=correct_binding.confidence,
            binding_strength_before=strength_before,
            binding_strength_after=correct_binding.strength,
            prediction_error=prediction_error,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            response_text=response,
        )
        self.store.log_focus(
            self.session_id,
            exp,
            {"target_meaning": target.relational_meaning, "decision_reason": assessment.reason},
        )
        self.store.log_binding(self.session_id, correct_binding, {"phase": "after_focus", "focus_id": exp.focus_id})
        if not correct:
            wrong = self.bindings[(target.label_word, predicted_id)]
            self.store.log_binding(self.session_id, wrong, {"phase": "wrong_referent_corrected", "focus_id": exp.focus_id})
            self.store.log_error(self.session_id, exp, correction, {"corrected_to": target.entity_id})
            self.error_events.append(exp)
        self.store.write_episode(
            f"joint_attention:{self.session_id}:{exp.focus_id}",
            "shared_focus_prediction",
            f"{target.label_word}->{predicted_id}",
            "A word becomes grounded when focus, object and caregiver correction converge.",
            assessment.sigma,
            sigma_after,
        )
        self.focus_events.append(exp)
        return exp

    def update_bindings(self, target: SceneEntity, predicted_id: str, correct: bool, decision: str) -> float:
        correct_binding = self.bindings[(target.label_word, target.entity_id)]
        correct_binding.exposure_count += 1
        rate = 0.115 if correct else 0.185
        if decision in {"narrow_focus", "replay_memory"}:
            rate += 0.035
        target_strength = 0.94 if correct else 0.86
        target_conf = 0.92 if correct else 0.78
        correct_binding.strength = clamp(correct_binding.strength + rate * (target_strength - correct_binding.strength))
        correct_binding.confidence = clamp(correct_binding.confidence + rate * (target_conf - correct_binding.confidence))
        if not correct:
            correct_binding.error_count += 1
            wrong = self.bindings[(target.label_word, predicted_id)]
            wrong.error_count += 1
            wrong.strength = clamp(wrong.strength * 0.72)
            wrong.confidence = clamp(wrong.confidence * 0.68)
        return rate

    def replay(self, cycle_id: int) -> None:
        source = max(self.error_events[-10:], key=lambda e: e.prediction_error + (1.0 - e.confidence_after))
        binding = self.bindings[(source.target_word, source.target_entity_id)]
        before_error = source.prediction_error
        binding.strength = clamp(binding.strength + 0.055)
        binding.confidence = clamp(binding.confidence + 0.045)
        replay_id = f"joint_replay:{self.session_id}:{cycle_id:04d}:{source.target_word}"
        self.store.log_replay(
            self.session_id,
            replay_id,
            source,
            max(0.0, before_error - 0.35),
            {"rule": "strengthen_correct_word_object_binding"},
        )
        self.store.log_binding(self.session_id, binding, {"phase": "replay", "replay_id": replay_id})
        self.last_replay_cycle = cycle_id

    def response_for(self, target: SceneEntity, predicted_id: str, correct: bool, decision: str) -> str:
        predicted_word = next((e.label_word for e in self.entities if e.entity_id == predicted_id), predicted_id)
        prefix = {
            "replay_memory": "Vou lembrar o foco anterior. ",
            "narrow_focus": "Vou olhar para uma coisa so. ",
            "pause_for_stability": "Vou responder devagar. ",
        }.get(decision, "")
        if correct:
            return f"{prefix}Voce apontou {target.label_word}; eu olhei para {predicted_word}. Acertei a referencia."
        return f"{prefix}Voce apontou {target.label_word}; eu olhei para {predicted_word}. Corrigindo: {target.label_word} e {target.relational_meaning}."

    def run(self, cycles: int = 72) -> dict[str, Any]:
        cycles = max(24, int(cycles))
        for cycle_id in range(1, cycles + 1):
            self.observe(cycle_id=cycle_id)
        if self.error_events:
            self.replay(cycles + 1)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        first = self.focus_events[: max(1, len(self.focus_events) // 4)]
        last = self.focus_events[-max(1, len(self.focus_events) // 4) :]
        correct_bindings = [b for b in self.bindings.values() if b.is_correct]
        payload = {
            "session_complete": True,
            "focus_count": len(self.focus_events),
            "entity_count": len(self.entities),
            "error_count": sum(1 for e in self.focus_events if not e.correct),
            "first_error": mean([e.prediction_error for e in first]),
            "last_error": mean([e.prediction_error for e in last]),
            "mean_binding_confidence": mean([b.confidence for b in correct_bindings]),
            "source_first_words_session_id": self.first_words_source,
            "source_vocal_imitation_session_id": self.vocal_source,
        }
        self.store.log_session(self.session_id, "joint_attention_complete", self.first_words_source, self.vocal_source, self.mode, payload)
        self.store.write_memory(
            f"joint_attention_v49_12:{self.session_id}",
            (
                f"Joint attention grounded {payload['entity_count']} entities; focus_events={payload['focus_count']}; "
                f"errors={payload['error_count']}; first_error={payload['first_error']:.3f}; "
                f"last_error={payload['last_error']:.3f}; binding_confidence={payload['mean_binding_confidence']:.3f}."
            ),
            clamp(payload["mean_binding_confidence"], 0.0, 0.95),
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
                "$s.Rate = -1; $s.Volume = 100; "
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
            time.sleep(max(0.8, min(9.0, len(text) / 15.0)))
        finally:
            self.on_stop()


class JointAttentionApp:
    BG = "#071018"
    PANEL = "#10202d"
    INK = "#edf7fb"
    MUTED = "#93aabd"
    BLUE = "#58b0ff"
    GREEN = "#75e7a8"
    RED = "#ff707a"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Joint Attention v49.12")
        self.root.geometry("1060x780")
        self.root.minsize(880, 660)
        self.root.configure(bg=self.BG)
        self.brain = JointAttentionBrain(mode="gui")
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking)
        self.tick = 0.0
        self.level = 0.0
        self.speaking = False
        self.speech_text = ""
        self.last_focus: FocusExperience | None = None

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x")
        for entity in self.brain.entities[:8]:
            ttk.Button(controls, text=f"Apontar {entity.label_word}", command=lambda w=entity.label_word: self.point(w)).pack(side="left", padx=(8, 0), pady=10)
        ttk.Button(controls, text="Auto", command=self.auto_point).pack(side="left", padx=(14, 8), pady=10)
        ttk.Button(controls, text="Replay", command=self.replay).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Parar fala", command=self.stop_speech).pack(side="left", padx=(0, 14), pady=10)

        self.transcript = tk.Text(root, height=9, bg="#061019", fg=self.INK, insertbackground=self.INK, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.transcript.pack(fill="x")
        self.transcript.config(state="disabled")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.write("Darwin", "Cena de atencao compartilhada iniciada. Aponte um objeto/pessoa.")
        self.animate()

    def write(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")
        self.transcript.config(state="disabled")

    def point(self, word: str) -> None:
        exp = self.brain.observe(target_word=word)
        self.last_focus = exp
        self.write("Felipe", f"aponta: {word}")
        self.write("Darwin", exp.response_text)
        self.speech.speak(exp.response_text)

    def auto_point(self) -> None:
        exp = self.brain.observe()
        self.last_focus = exp
        self.write("Felipe", f"aponta: {exp.target_word}")
        self.write("Darwin", exp.response_text)
        self.speech.speak(exp.response_text)

    def replay(self) -> None:
        if not self.brain.error_events:
            self.write("Darwin", "Ainda nao tenho erro recente para replay.")
            return
        self.brain.replay(len(self.brain.focus_events) + 1)
        self.write("Darwin", "Reforcei a ligacao palavra-objeto mais fraca.")

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
        c.create_text(w / 2, 36, text="DARWIN JOINT ATTENTION v49.12", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(w / 2, 66, text="palavra + foco + objeto + correcao", fill=self.MUTED, font=("Segoe UI", 11))
        for entity in self.brain.entities:
            x = entity.x * w
            y = 110 + entity.y * (h - 230)
            r = 42
            active = self.last_focus and self.last_focus.target_entity_id == entity.entity_id
            outline = self.GREEN if active else "#d7f5ff"
            c.create_oval(x - r, y - r, x + r, y + r, fill=entity.color, outline=outline, width=3)
            c.create_text(x, y + 62, text=entity.label_word, fill=self.INK, font=("Segoe UI", 11, "bold"))
        cx = w / 2
        cy = h - 95
        radius = 38 + 18 * self.level
        color = self.GREEN if self.last_focus and self.last_focus.correct else self.RED if self.last_focus else self.BLUE
        c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#e5f7ff", width=2)
        if self.last_focus:
            footer = (
                f"alvo {self.last_focus.target_word}  previsto {self.last_focus.predicted_entity_id.replace('entity:', '')}  "
                f"erro {self.last_focus.prediction_error:.1f}  RZS {self.last_focus.rzs_decision}"
            )
        else:
            footer = "aponte para algo para Darwin aprender referencia"
        c.create_text(cx, h - 34, text=footer, fill=self.MUTED, font=("Segoe UI", 10))

    def on_close(self) -> None:
        self.speech.stop()
        result = self.brain.complete()
        self.write("Sistema", f"Sessao encerrada: {result['session_id']}")
        self.root.destroy()


def run_self_test(cycles: int = 72, details: bool = False) -> dict[str, Any]:
    brain = JointAttentionBrain(mode="self_test")
    result = brain.run(cycles=cycles)
    if details:
        print(js(result))
    else:
        print(
            f"DARWIN v49.12 joint attention self-test concluido: "
            f"session={result['session_id']} focus={result['focus_count']}"
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Joint Attention Nursery v49.12")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cycles", type=int, default=72)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test(cycles=args.cycles, details=args.details)
        return 0
    root = tk.Tk()
    JointAttentionApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
