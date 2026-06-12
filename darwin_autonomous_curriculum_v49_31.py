from __future__ import annotations

"""
DARWIN v49.31 - Autonomous Curriculum

Objetivo:
Darwin usa o marco v49.30 "learning to learn" para escolher sozinho o
proximo treino. A escolha nao roda modulos externos automaticamente; ela
faz um ensaio cognitivo interno, auditavel, com candidatos, pontuacao,
RZS, custo, novidade, preferencia e resultado observado.

Uso:
    py darwin_autonomous_curriculum_v49_31.py
    py darwin_autonomous_curriculum_v49_31.py --self-test --cycles 12 --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
import tkinter as tk
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_autonomous_curriculum_v49_31"

AC_SESSIONS = "autonomous_curriculum_sessions_v49_31"
AC_CANDIDATES = "curriculum_candidates_v49_31"
AC_CHOICES = "curriculum_choices_v49_31"
AC_TRIALS = "curriculum_trials_v49_31"
AC_REFLECTIONS = "curriculum_reflections_v49_31"
AC_HANDOFFS = "curriculum_handoffs_v49_31"

PROTECTED_SOURCE_TABLES = [
    "learning_to_learn_sessions_v49_30",
    "learning_strategies_v49_30",
    "learning_trials_v49_30",
    "affective_preferences_v49_17",
    "affective_consolidation_v49_17",
    "formula_sketch_sessions_v49_28",
    "formula_sketch_intentions_v49_28",
    "story_nursery_sessions_v49_29",
    "story_reactions_v49_29",
    "music_reactions_v49_16",
    "memory_card_sessions_v49_13",
    "memory_card_moves_v49_13",
    "voice_first_word_nodes_v49_10",
    "brain_meta_cycles_v49_1",
]

CURRICULUM_MODULES = [
    "formula_sketch",
    "child_story",
    "classical_music",
    "memory_cards",
    "first_words",
    "self_review",
    "preference_choice",
    "geometry_error",
    "voice_presence",
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


@dataclass
class CurriculumCandidate:
    candidate_id: str
    step_index: int
    module_key: str
    domain: str
    candidate_action: str
    source_kind: str
    preference_key: str
    preference_strength: float
    learning_strategy: str
    expected_gain: float
    novelty: float
    stability: float
    cost: float
    readiness: float
    score_before_rzs: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    score_after_rzs: float
    chosen_action: str
    evidence: dict[str, Any]
    payload: dict[str, Any]


@dataclass
class CurriculumChoice:
    choice_id: str
    step_index: int
    selected_candidate_id: str
    module_key: str
    chosen_action: str
    reason: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    score: float
    expected_gain: float
    predicted_outcome: str
    payload: dict[str, Any]


@dataclass
class CurriculumTrial:
    trial_id: str
    step_index: int
    module_key: str
    trial_kind: str
    chosen_action: str
    predicted_gain: float
    observed_gain: float
    autonomy_score: float
    stability_after: float
    energy_after: float
    outcome: str
    payload: dict[str, Any]


class CurriculumStore:
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
                CREATE TABLE IF NOT EXISTS {AC_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    step_index INTEGER NOT NULL DEFAULT 0,
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AC_CANDIDATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    module_key TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    candidate_action TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    preference_strength REAL NOT NULL DEFAULT 0.0,
                    learning_strategy TEXT NOT NULL,
                    expected_gain REAL NOT NULL DEFAULT 0.0,
                    novelty REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    cost REAL NOT NULL DEFAULT 0.0,
                    readiness REAL NOT NULL DEFAULT 0.0,
                    score_before_rzs REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    score_after_rzs REAL NOT NULL DEFAULT 0.0,
                    chosen_action TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AC_CHOICES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    choice_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    selected_candidate_id TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    chosen_action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    score REAL NOT NULL DEFAULT 0.0,
                    expected_gain REAL NOT NULL DEFAULT 0.0,
                    predicted_outcome TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AC_TRIALS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    module_key TEXT NOT NULL,
                    trial_kind TEXT NOT NULL,
                    chosen_action TEXT NOT NULL,
                    predicted_gain REAL NOT NULL DEFAULT 0.0,
                    observed_gain REAL NOT NULL DEFAULT 0.0,
                    autonomy_score REAL NOT NULL DEFAULT 0.0,
                    stability_after REAL NOT NULL DEFAULT 0.0,
                    energy_after REAL NOT NULL DEFAULT 0.0,
                    outcome TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AC_REFLECTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reflection_id TEXT NOT NULL UNIQUE,
                    reflection_kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AC_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_action TEXT NOT NULL,
                    autonomous_curriculum_ready INTEGER NOT NULL DEFAULT 0,
                    selected_module_count INTEGER NOT NULL DEFAULT 0,
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
            if "evidence_json" in item:
                item["evidence"] = pj(str(item.get("evidence_json") or "{}"), {})
            if "source_kinds_json" in item:
                item["source_kinds"] = pj(str(item.get("source_kinds_json") or "[]"), [])
            if "tags_json" in item:
                item["tags"] = pj(str(item.get("tags_json") or "[]"), [])
            if "evidence_refs_json" in item:
                item["evidence_refs"] = pj(str(item.get("evidence_refs_json") or "[]"), [])
            out.append(item)
        return out

    def latest_phase(self, conn: sqlite3.Connection, table: str, phase: str, id_column: str = "session_id") -> tuple[str, dict[str, Any], dict[str, Any]]:
        if not self.table_exists(conn, table):
            return "", {}, {}
        row = conn.execute(f"SELECT * FROM {table} WHERE phase=? ORDER BY id DESC LIMIT 1", (phase,)).fetchone()
        if not row:
            return "", {}, {}
        item = {k: row[k] for k in row.keys()}
        payload = pj(str(item.get("payload_json") or "{}"), {})
        return str(item.get(id_column) or ""), item, payload

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
                INSERT INTO {AC_SESSIONS} (
                    timestamp, session_id, phase, mode, step_index, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, step_index, energy, js(payload or {})),
            )
            conn.commit()

    def log_candidate(self, session_id: str, candidate: CurriculumCandidate) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AC_CANDIDATES} (
                    timestamp, session_id, candidate_id, step_index, module_key,
                    domain, candidate_action, source_kind, preference_key,
                    preference_strength, learning_strategy, expected_gain,
                    novelty, stability, cost, readiness, score_before_rzs,
                    rzs_decision, sigma_before, sigma_after, score_after_rzs,
                    chosen_action, evidence_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    candidate.candidate_id,
                    candidate.step_index,
                    candidate.module_key,
                    candidate.domain,
                    candidate.candidate_action,
                    candidate.source_kind,
                    candidate.preference_key,
                    candidate.preference_strength,
                    candidate.learning_strategy,
                    candidate.expected_gain,
                    candidate.novelty,
                    candidate.stability,
                    candidate.cost,
                    candidate.readiness,
                    candidate.score_before_rzs,
                    candidate.rzs_decision,
                    candidate.sigma_before,
                    candidate.sigma_after,
                    candidate.score_after_rzs,
                    candidate.chosen_action,
                    js(candidate.evidence),
                    js(candidate.payload),
                ),
            )
            conn.commit()

    def log_choice(self, session_id: str, choice: CurriculumChoice) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AC_CHOICES} (
                    timestamp, session_id, choice_id, step_index,
                    selected_candidate_id, module_key, chosen_action, reason,
                    rzs_decision, sigma_before, sigma_after, score,
                    expected_gain, predicted_outcome, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    choice.choice_id,
                    choice.step_index,
                    choice.selected_candidate_id,
                    choice.module_key,
                    choice.chosen_action,
                    choice.reason,
                    choice.rzs_decision,
                    choice.sigma_before,
                    choice.sigma_after,
                    choice.score,
                    choice.expected_gain,
                    choice.predicted_outcome,
                    js(choice.payload),
                ),
            )
            conn.commit()

    def log_trial(self, session_id: str, trial: CurriculumTrial) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AC_TRIALS} (
                    timestamp, session_id, trial_id, step_index, module_key,
                    trial_kind, chosen_action, predicted_gain, observed_gain,
                    autonomy_score, stability_after, energy_after, outcome,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    trial.trial_id,
                    trial.step_index,
                    trial.module_key,
                    trial.trial_kind,
                    trial.chosen_action,
                    trial.predicted_gain,
                    trial.observed_gain,
                    trial.autonomy_score,
                    trial.stability_after,
                    trial.energy_after,
                    trial.outcome,
                    js(trial.payload),
                ),
            )
            conn.commit()

    def log_reflection(self, session_id: str, reflection_id: str, kind: str, summary: str, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AC_REFLECTIONS} (
                    timestamp, session_id, reflection_id, reflection_kind,
                    summary, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, reflection_id, kind, summary, clamp(confidence), js(payload)),
            )
            conn.commit()

    def log_handoff(self, session_id: str, next_action: str, ready: bool, selected_module_count: int, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AC_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_action,
                    autonomous_curriculum_ready, selected_module_count,
                    confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    f"HO-{session_id}-01",
                    next_action,
                    1 if ready else 0,
                    selected_module_count,
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
                (f"autonomous_curriculum_v49_31:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"autonomous_curriculum:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class AutonomousCurriculumCore:
    def __init__(self, seed: int | None = None, mode: str = "gui") -> None:
        self.store = CurriculumStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000) % 100_000_000)
        self.session_id = f"V4931-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.energy = 0.82
        self.source_counts_before = self.store.protected_counts()
        self.source_state: dict[str, Any] = {}
        self.candidates: list[CurriculumCandidate] = []
        self.choices: list[CurriculumChoice] = []
        self.trials: list[CurriculumTrial] = []
        self.selection_counts: Counter[str] = Counter()
        self.recent_modules: list[str] = []
        self.prepared = False

    def load_source_state(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            l2l_sid, _row, l2l_payload = self.store.latest_phase(conn, "learning_to_learn_sessions_v49_30", "session_complete")
            strategies = self.store.rows(conn, "learning_strategies_v49_30", "WHERE session_id=?", (l2l_sid,)) if l2l_sid else []

            pref_sid, _row, pref_payload = self.store.latest_phase(conn, "affective_preference_sessions_v49_17", "session_complete")
            preferences = self.store.rows(conn, "affective_preferences_v49_17", "WHERE session_id=?", (pref_sid,)) if pref_sid else []

            form_sid, _row, form_payload = self.store.latest_phase(conn, "formula_sketch_sessions_v49_28", "sketch_complete")
            story_sid, _row, story_payload = self.store.latest_phase(conn, "story_nursery_sessions_v49_29", "session_complete")
            memory_sid, _row, memory_payload = self.store.latest_phase(conn, "memory_card_sessions_v49_13", "memory_cards_complete")
            words_sid, _row, words_payload = self.store.latest_phase(conn, "voice_first_word_sessions_v49_10", "first_words_complete")
            voice_sid, _row, voice_payload = self.store.latest_phase(conn, "voice_presence_sessions_v49_9", "voice_session_complete", "voice_session_id")

            music_rows = self.store.rows(conn, "music_reactions_v49_16")
            music = {
                "count": len(music_rows),
                "comfort": mean([number(r.get("comfort")) for r in music_rows], 0.0),
                "stability": mean([number(r.get("stability")) for r in music_rows], 0.0),
                "curiosity": mean([number(r.get("curiosity")) for r in music_rows], 0.0),
            }

            geometry_rows = self.store.rows(conn, "geometry_error_replay_v49_7")
            if geometry_rows:
                before = mean([number(r.get("error_before")) for r in geometry_rows[-12:]], 0.35)
                after = mean([number(r.get("error_after")) for r in geometry_rows[-12:]], 0.22)
                geometry = {"count": len(geometry_rows), "before": before, "after": after, "gain": clamp((before - after) / max(0.1, before))}
            else:
                geometry = {"count": 0, "before": 0.0, "after": 0.0, "gain": 0.0}

            move_rows = self.store.rows(conn, "memory_card_moves_v49_13", "WHERE session_id=?", (memory_sid,)) if memory_sid else []
            mismatches = sum(1 for r in move_rows if int(r.get("matched") or 0) == 0) // 2
            memory = {
                "session_id": memory_sid,
                "payload": memory_payload,
                "move_count": len(move_rows),
                "mismatches": mismatches,
                "memory_pick_ratio": mean([1.0 if "memory" in str(r.get("decision_source") or "") else 0.0 for r in move_rows], 0.0),
            }

            meta_rows = self.store.rows(conn, "brain_meta_cycles_v49_1")
            health = [number(r.get("health_score")) for r in meta_rows if str(r.get("phase") or "") == "meta_action_execute"]
            meta = {"count": len(meta_rows), "health": health[-1] if health else 0.72, "risk": clamp(1.0 - (health[-1] if health else 0.72))}

        return {
            "learning_session_id": l2l_sid,
            "learning_payload": l2l_payload,
            "strategies": strategies,
            "preference_session_id": pref_sid,
            "preference_payload": pref_payload,
            "preferences": preferences,
            "formula_session_id": form_sid,
            "formula_payload": form_payload,
            "story_session_id": story_sid,
            "story_payload": story_payload,
            "music": music,
            "memory": memory,
            "first_words_session_id": words_sid,
            "first_words_payload": words_payload,
            "voice_session_id": voice_sid,
            "voice_payload": voice_payload,
            "geometry": geometry,
            "metacognition": meta,
        }

    def prepare(self) -> None:
        if self.prepared:
            return
        self.source_state = self.load_source_state()
        self.store.log_session(
            self.session_id,
            "curriculum_start",
            self.mode,
            0,
            self.energy,
            {
                "goal": "choose_next_training_autonomously",
                "learning_session_id": self.source_state.get("learning_session_id", ""),
                "preference_session_id": self.source_state.get("preference_session_id", ""),
                "protected_counts_before": self.source_counts_before,
            },
        )
        self.prepared = True

    def pref(self, *keys: str) -> tuple[str, float, dict[str, Any]]:
        prefs = self.source_state.get("preferences", [])
        best: dict[str, Any] = {}
        for pref in prefs:
            if str(pref.get("preference_key") or "") in keys:
                if not best or number(pref.get("strength")) > number(best.get("strength")):
                    best = pref
        if best:
            return str(best.get("preference_key")), clamp(number(best.get("strength"))), best
        return keys[0] if keys else "", 0.42, {}

    def strategy(self, *keys: str) -> tuple[str, float, float, dict[str, Any]]:
        strategies = self.source_state.get("strategies", [])
        best: dict[str, Any] = {}
        for strategy in strategies:
            if str(strategy.get("strategy_key") or "") in keys:
                value = number(strategy.get("expected_gain")) * 0.65 + number(strategy.get("confidence")) * 0.35
                best_value = number(best.get("expected_gain")) * 0.65 + number(best.get("confidence")) * 0.35 if best else -1.0
                if value > best_value:
                    best = strategy
        if best:
            return str(best.get("strategy_key")), clamp(number(best.get("expected_gain"))), clamp(number(best.get("confidence"))), best
        return keys[0] if keys else "", 0.30, 0.50, {}

    def base_score(self, preference: float, expected_gain: float, novelty: float, stability: float, cost: float, readiness: float, strategy_conf: float) -> float:
        return clamp(
            preference * 0.25
            + expected_gain * 0.25
            + novelty * 0.13
            + stability * 0.16
            + readiness * 0.16
            + strategy_conf * 0.10
            - cost * 0.12
        )

    def build_seed_candidates(self, step_index: int) -> list[dict[str, Any]]:
        s = self.source_state
        formula = s.get("formula_payload", {})
        story = s.get("story_payload", {})
        music = s.get("music", {})
        memory = s.get("memory", {})
        words = s.get("first_words_payload", {})
        geometry = s.get("geometry", {})
        meta = s.get("metacognition", {})
        voice = s.get("voice_payload", {})

        f_mistakes = max(1.0, number(formula.get("mistake_count"), 1.0))
        f_corrections = number(formula.get("correction_count"), 0.0)
        f_fusions = number(formula.get("fusion_count"), 0.0)
        f_intentions = max(1.0, number(formula.get("intention_count"), 1.0))

        learned_words = number(words.get("learned_count"), 0.0)
        word_conf = number(words.get("mean_meaning_confidence"), 0.36)
        memory_moves = max(1.0, number(memory.get("move_count"), 1.0))
        memory_mismatch_ratio = clamp(number(memory.get("mismatches")) / max(1.0, memory_moves / 2.0))
        voice_recognized = number(voice.get("recognized"), 0.0)

        return [
            {
                "module_key": "formula_sketch",
                "domain": "visual_formula",
                "action": "practice_formula_sketching",
                "source_kind": "formula_sketch_v49_28",
                "pref_keys": ("pref_geometry",),
                "strategy_keys": ("error_as_experience_node", "cross_domain_fusion"),
                "novelty": clamp(0.34 + f_fusions / max(1.0, f_intentions) * 2.0),
                "stability": clamp(0.45 + f_corrections / f_mistakes * 0.38),
                "cost": 0.56,
                "readiness": clamp(0.25 + min(1.0, f_intentions / 48.0) * 0.50 + (1 if f_corrections > 0 else 0) * 0.15),
                "evidence": {"source_session_id": s.get("formula_session_id", ""), "mistakes": f_mistakes, "corrections": f_corrections, "fusions": f_fusions, "intentions": f_intentions},
            },
            {
                "module_key": "child_story",
                "domain": "narrative_affect",
                "action": "listen_to_child_story",
                "source_kind": "child_story_v49_29",
                "pref_keys": ("pref_companion_relation", "pref_joint_attention"),
                "strategy_keys": ("affective_safe_context",),
                "novelty": clamp(number(story.get("avg_curiosity"), 0.45) + 0.10),
                "stability": clamp(number(story.get("avg_stability"), 0.58)),
                "cost": 0.22,
                "readiness": clamp(0.30 + number(story.get("story_count"), 0.0) / 8.0 + (0.15 if story.get("child_safe_storybook") else 0.0)),
                "evidence": {"source_session_id": s.get("story_session_id", ""), "avg_stability": story.get("avg_stability"), "avg_curiosity": story.get("avg_curiosity"), "child_safe": story.get("child_safe_storybook")},
            },
            {
                "module_key": "classical_music",
                "domain": "auditory_pattern",
                "action": "listen_to_gentle_classical_music",
                "source_kind": "music_reactions_v49_16",
                "pref_keys": ("pref_music_calm",),
                "strategy_keys": ("consolidate_after_pattern",),
                "novelty": clamp(0.24 + number(music.get("curiosity"), 0.25) * 0.45),
                "stability": clamp(number(music.get("stability"), 0.62) * 0.72 + number(music.get("comfort"), 0.58) * 0.22),
                "cost": 0.12,
                "readiness": clamp(0.35 + min(1.0, number(music.get("count"), 0.0) / 12.0) * 0.45),
                "evidence": {"reaction_count": music.get("count"), "comfort": music.get("comfort"), "stability": music.get("stability")},
            },
            {
                "module_key": "memory_cards",
                "domain": "visual_memory",
                "action": "practice_memory_cards",
                "source_kind": "memory_cards_v49_13",
                "pref_keys": ("pref_memory_cards",),
                "strategy_keys": ("replay_before_retry",),
                "novelty": clamp(0.34 + memory_mismatch_ratio * 0.42),
                "stability": clamp(0.52 + number(memory.get("memory_pick_ratio"), 0.25) * 0.28),
                "cost": 0.34,
                "readiness": clamp(0.38 + (0.28 if memory.get("payload", {}).get("game_complete") else 0.0) + min(0.25, memory_moves / 80.0)),
                "evidence": {"source_session_id": memory.get("session_id"), "move_count": memory.get("move_count"), "mismatches": memory.get("mismatches"), "memory_pick_ratio": memory.get("memory_pick_ratio")},
            },
            {
                "module_key": "first_words",
                "domain": "early_language",
                "action": "practice_first_words",
                "source_kind": "first_words_v49_10",
                "pref_keys": ("pref_first_words", "pref_vocal_imitation"),
                "strategy_keys": ("replay_before_retry", "self_check_before_advance"),
                "novelty": clamp(0.58 - word_conf * 0.24 + max(0.0, 8.0 - learned_words) * 0.025),
                "stability": clamp(0.42 + word_conf * 0.40),
                "cost": 0.30,
                "readiness": clamp(0.30 + learned_words / 12.0 + word_conf * 0.22),
                "evidence": {"source_session_id": s.get("first_words_session_id", ""), "learned_words": words.get("learned_words"), "learned_count": learned_words, "mean_meaning_confidence": word_conf},
            },
            {
                "module_key": "self_review",
                "domain": "metacognition",
                "action": "review_self_goals",
                "source_kind": "brain_meta_cycles_v49_1",
                "pref_keys": ("pref_self_reflection",),
                "strategy_keys": ("self_check_before_advance", "evidence_weighted_choice"),
                "novelty": clamp(0.24 + number(meta.get("risk"), 0.20) * 0.50),
                "stability": clamp(number(meta.get("health"), 0.72)),
                "cost": 0.18,
                "readiness": clamp(0.42 + min(1.0, number(meta.get("count"), 0.0) / 42.0) * 0.36),
                "evidence": {"health": meta.get("health"), "risk": meta.get("risk"), "meta_events": meta.get("count")},
            },
            {
                "module_key": "preference_choice",
                "domain": "choice",
                "action": "choose_from_preferences",
                "source_kind": "affective_preference_v49_17",
                "pref_keys": ("pref_companion_relation", "pref_self_reflection", "pref_music_calm"),
                "strategy_keys": ("evidence_weighted_choice",),
                "novelty": 0.31,
                "stability": clamp(number(s.get("preference_payload", {}).get("top_preferences", [{}])[0].get("strength"), 0.62) if isinstance(s.get("preference_payload", {}).get("top_preferences"), list) and s.get("preference_payload", {}).get("top_preferences") else 0.62),
                "cost": 0.16,
                "readiness": clamp(0.45 + number(s.get("preference_payload", {}).get("preference_count"), 0.0) / 16.0),
                "evidence": {"source_session_id": s.get("preference_session_id", ""), "top_preference_key": s.get("preference_payload", {}).get("top_preference_key"), "selected_action": s.get("preference_payload", {}).get("selected_action")},
            },
            {
                "module_key": "geometry_error",
                "domain": "geometry",
                "action": "practice_geometry_error_replay",
                "source_kind": "geometry_v49_7",
                "pref_keys": ("pref_geometry",),
                "strategy_keys": ("error_as_experience_node", "replay_before_retry", "narrow_focus_on_conflict"),
                "novelty": clamp(0.28 + max(0.0, number(geometry.get("after"), 0.18)) * 0.70),
                "stability": clamp(0.45 + number(geometry.get("gain"), 0.35) * 0.38),
                "cost": 0.38,
                "readiness": clamp(0.35 + min(1.0, number(geometry.get("count"), 0.0) / 24.0) * 0.45),
                "evidence": geometry,
            },
            {
                "module_key": "voice_presence",
                "domain": "relation_voice",
                "action": "practice_voice_presence",
                "source_kind": "voice_presence_v49_9",
                "pref_keys": ("pref_vocal_imitation", "pref_companion_relation"),
                "strategy_keys": ("self_check_before_advance", "affective_safe_context"),
                "novelty": clamp(0.46 + (0.16 if voice_recognized <= 0 else 0.0)),
                "stability": clamp(0.50 + min(0.22, voice_recognized * 0.03)),
                "cost": 0.42,
                "readiness": clamp(0.28 + min(0.40, voice_recognized * 0.08) + (0.16 if voice.get("session_complete") else 0.0)),
                "evidence": {"source_session_id": s.get("voice_session_id", ""), "recognized": voice_recognized, "note": "microphone_real_time_depends_on_windows_recognizer"},
            },
        ]

    def rzs_input(self, item: dict[str, Any], strategy_conf: float, step_index: int) -> RZSInput:
        readiness = number(item.get("readiness"), 0.5)
        stability = number(item.get("stability"), 0.5)
        novelty = number(item.get("novelty"), 0.5)
        cost = number(item.get("cost"), 0.3)
        recent_pressure = 0.09 if item["module_key"] in self.recent_modules[-2:] else 0.0
        return RZSInput(
            bandwidth=2.88 + self.energy * 0.70 + stability * 0.30 + strategy_conf * 0.12,
            info_self=0.28 + (1.0 - readiness) * 0.22,
            info_external=0.34 + novelty * 0.28,
            task_info=0.42 + number(item.get("expected_gain"), 0.35) * 0.28 + cost * 0.14,
            novelty=clamp(novelty + (0.10 if step_index % 6 == 0 else 0.0)),
            conflict=clamp(0.12 + cost * 0.42 + max(0.0, 0.60 - stability) * 0.30 + recent_pressure),
            latency=0.88 + cost * 0.58 + (1.0 - readiness) * 0.22,
            energy=self.energy,
            memory_pressure=clamp(0.22 + (1.0 - readiness) * 0.30 + (0.42 if step_index % 7 == 0 else 0.0)),
            replay_gap=clamp(0.24 + novelty * 0.58 + (0.28 if step_index % 5 == 0 else 0.0)),
        )

    def governed_action(self, action: str, decision: str) -> str:
        if decision == "continue":
            return action
        if decision == "narrow_focus":
            return f"narrow_{action}"
        if decision == "replay_memory":
            return f"replay_before_{action}"
        if decision == "consolidate":
            return f"consolidate_before_{action}"
        if decision == "pause_for_stability":
            return "pause_curriculum_for_stability"
        return action

    def decision_bonus(self, decision: str, module_key: str) -> float:
        if decision == "continue":
            return 0.010
        if decision == "narrow_focus":
            return 0.040 if module_key in {"formula_sketch", "geometry_error", "voice_presence"} else 0.018
        if decision == "replay_memory":
            return 0.052 if module_key in {"memory_cards", "first_words", "child_story", "geometry_error"} else 0.030
        if decision == "consolidate":
            return 0.045 if module_key in {"classical_music", "preference_choice", "self_review"} else 0.020
        if decision == "pause_for_stability":
            return -0.035
        return 0.0

    def score_candidates(self, step_index: int) -> list[CurriculumCandidate]:
        out: list[CurriculumCandidate] = []
        for idx, item in enumerate(self.build_seed_candidates(step_index), start=1):
            pref_key, pref_strength, pref_payload = self.pref(*item["pref_keys"])
            strategy_key, expected_gain, strategy_conf, strategy_payload = self.strategy(*item["strategy_keys"])
            item["expected_gain"] = expected_gain
            before = self.base_score(pref_strength, expected_gain, item["novelty"], item["stability"], item["cost"], item["readiness"], strategy_conf)
            x = self.rzs_input(item, strategy_conf, step_index)
            assessment = self.rzs.classify(x)
            y = self.rzs.apply_action_model(x, assessment.decision)
            sigma_after = self.rzs.sigma(y)
            count_penalty = self.selection_counts[item["module_key"]] * 0.045
            recent_penalty = 0.16 if item["module_key"] == (self.recent_modules[-1] if self.recent_modules else "") else 0.0
            recent_penalty += 0.05 if item["module_key"] in self.recent_modules[-3:] else 0.0
            exploration_bonus = 0.070 if self.selection_counts[item["module_key"]] == 0 else 0.020 / (1 + self.selection_counts[item["module_key"]])
            jitter = self.rng.uniform(-0.008, 0.008)
            after = clamp(before + self.decision_bonus(assessment.decision, item["module_key"]) + exploration_bonus - count_penalty - recent_penalty + jitter)
            chosen = self.governed_action(item["action"], assessment.decision)
            evidence = {
                **item["evidence"],
                "learning_session_id": self.source_state.get("learning_session_id", ""),
                "preference_session_id": self.source_state.get("preference_session_id", ""),
                "preference": pref_payload,
                "strategy": strategy_payload,
            }
            candidate = CurriculumCandidate(
                candidate_id=f"CA-{self.session_id}-{step_index:02d}-{idx:02d}",
                step_index=step_index,
                module_key=item["module_key"],
                domain=item["domain"],
                candidate_action=item["action"],
                source_kind=item["source_kind"],
                preference_key=pref_key,
                preference_strength=pref_strength,
                learning_strategy=strategy_key,
                expected_gain=expected_gain,
                novelty=clamp(number(item["novelty"])),
                stability=clamp(number(item["stability"])),
                cost=clamp(number(item["cost"])),
                readiness=clamp(number(item["readiness"])),
                score_before_rzs=before,
                rzs_decision=assessment.decision,
                sigma_before=assessment.sigma,
                sigma_after=sigma_after,
                score_after_rzs=after,
                chosen_action=chosen,
                evidence=evidence,
                payload={
                    "rzs_reason": assessment.reason,
                    "threshold_name": assessment.threshold_name,
                    "selection_count_before": self.selection_counts[item["module_key"]],
                    "recent_modules": list(self.recent_modules[-4:]),
                    "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
                    "rzs_input": asdict(x),
                    "rzs_after": asdict(y),
                },
            )
            out.append(candidate)
            self.store.log_candidate(self.session_id, candidate)
        self.candidates.extend(out)
        self.store.log_session(
            self.session_id,
            "candidate_scan",
            self.mode,
            step_index,
            self.energy,
            {"candidate_count": len(out), "modules": sorted({c.module_key for c in out})},
        )
        return out

    def choose(self, step_index: int, candidates: list[CurriculumCandidate]) -> CurriculumChoice:
        ranked = sorted(candidates, key=lambda c: (c.score_after_rzs, c.readiness, c.expected_gain), reverse=True)
        selected = ranked[0]
        self.selection_counts[selected.module_key] += 1
        self.recent_modules.append(selected.module_key)
        if len(self.recent_modules) > 8:
            self.recent_modules = self.recent_modules[-8:]
        reason = (
            f"Escolhi {selected.module_key}: score={selected.score_after_rzs:.3f}, "
            f"estrategia={selected.learning_strategy}, preferencia={selected.preference_key}, RZS={selected.rzs_decision}."
        )
        predicted = (
            f"Se eu fizer {selected.chosen_action}, espero ganho aproximado "
            f"{selected.expected_gain:.3f} com estabilidade {selected.stability:.3f}."
        )
        choice = CurriculumChoice(
            choice_id=f"CH-{self.session_id}-{step_index:02d}",
            step_index=step_index,
            selected_candidate_id=selected.candidate_id,
            module_key=selected.module_key,
            chosen_action=selected.chosen_action,
            reason=reason,
            rzs_decision=selected.rzs_decision,
            sigma_before=selected.sigma_before,
            sigma_after=selected.sigma_after,
            score=selected.score_after_rzs,
            expected_gain=selected.expected_gain,
            predicted_outcome=predicted,
            payload={
                "candidate": asdict(selected),
                "ranked_candidates": [
                    {"module_key": c.module_key, "score": c.score_after_rzs, "rzs": c.rzs_decision, "strategy": c.learning_strategy}
                    for c in ranked[:5]
                ],
                "selection_counts": dict(self.selection_counts),
            },
        )
        self.choices.append(choice)
        self.store.log_choice(self.session_id, choice)
        self.store.log_session(
            self.session_id,
            "curriculum_choice",
            self.mode,
            step_index,
            self.energy,
            {"choice_id": choice.choice_id, "module_key": choice.module_key, "chosen_action": choice.chosen_action, "rzs_decision": choice.rzs_decision},
        )
        return choice

    def execute_trial(self, choice: CurriculumChoice) -> CurriculumTrial:
        candidate = next(c for c in self.candidates if c.candidate_id == choice.selected_candidate_id)
        decision_factor = {
            "continue": 0.000,
            "narrow_focus": 0.026,
            "replay_memory": 0.038,
            "consolidate": 0.032,
            "pause_for_stability": -0.020,
        }.get(choice.rzs_decision, 0.0)
        diversity = clamp(len(set(self.recent_modules)) / max(1, len(CURRICULUM_MODULES)))
        prediction = clamp(choice.expected_gain * (0.72 + candidate.readiness * 0.22) + candidate.stability * 0.08)
        observed = clamp(prediction + decision_factor + self.rng.uniform(-0.018, 0.026) - candidate.cost * 0.026)
        self.energy = clamp(self.energy - candidate.cost * 0.024 + observed * 0.012 + (0.018 if choice.rzs_decision in {"consolidate", "pause_for_stability"} else 0.0))
        autonomy = clamp(choice.score * 0.42 + observed * 0.30 + diversity * 0.18 + (0.10 if choice.rzs_decision != "continue" else 0.04))
        stability_after = clamp(candidate.stability * 0.82 + candidate.readiness * 0.10 + observed * 0.08)
        outcome = f"{choice.module_key}: observed_gain={observed:.3f}; autonomy={autonomy:.3f}; energy={self.energy:.3f}"
        trial = CurriculumTrial(
            trial_id=f"TR-{self.session_id}-{choice.step_index:02d}",
            step_index=choice.step_index,
            module_key=choice.module_key,
            trial_kind="internal_curriculum_probe",
            chosen_action=choice.chosen_action,
            predicted_gain=prediction,
            observed_gain=observed,
            autonomy_score=autonomy,
            stability_after=stability_after,
            energy_after=self.energy,
            outcome=outcome,
            payload={
                "selected_candidate_id": choice.selected_candidate_id,
                "decision_factor": decision_factor,
                "diversity": diversity,
                "not_external_module_execution": True,
                "interpretation": "ensaio interno para escolher treino; nao executa corpo, robo, camera ou microfone",
            },
        )
        self.trials.append(trial)
        self.store.log_trial(self.session_id, trial)
        self.store.log_session(
            self.session_id,
            "curriculum_trial",
            self.mode,
            choice.step_index,
            self.energy,
            {"trial_id": trial.trial_id, "module_key": trial.module_key, "observed_gain": trial.observed_gain, "autonomy_score": trial.autonomy_score},
        )
        return trial

    def reflect_step(self, choice: CurriculumChoice, trial: CurriculumTrial) -> None:
        summary = (
            f"No ciclo {choice.step_index}, escolhi {choice.module_key} por {choice.reason} "
            f"O ensaio retornou ganho={trial.observed_gain:.3f}."
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-{choice.step_index:02d}",
            "curriculum_step_reflection",
            summary,
            clamp(0.58 + trial.autonomy_score * 0.28),
            {"choice": asdict(choice), "trial": asdict(trial)},
        )

    def run_cycle(self, step_index: int) -> tuple[CurriculumChoice, CurriculumTrial]:
        candidates = self.score_candidates(step_index)
        choice = self.choose(step_index, candidates)
        trial = self.execute_trial(choice)
        self.reflect_step(choice, trial)
        return choice, trial

    def run(self, cycles: int = 12) -> dict[str, Any]:
        self.prepare()
        cycles = max(8, int(cycles))
        for step in range(1, cycles + 1):
            self.run_cycle(step)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        counts_after = self.store.protected_counts()
        selected_modules = [c.module_key for c in self.choices]
        decisions = sorted({c.rzs_decision for c in self.choices})
        module_counts = dict(Counter(selected_modules))
        avg_gain = mean([t.observed_gain for t in self.trials], 0.0)
        avg_autonomy = mean([t.autonomy_score for t in self.trials], 0.0)
        avg_score = mean([c.score for c in self.choices], 0.0)
        top_module = Counter(selected_modules).most_common(1)[0][0] if selected_modules else ""
        ready = (
            len(self.choices) >= 8
            and len(set(selected_modules)) >= 4
            and any(d != "continue" for d in decisions)
            and avg_autonomy >= 0.35
            and counts_after == self.source_counts_before
        )
        summary = {
            "session_id": self.session_id,
            "candidate_count": len(self.candidates),
            "choice_count": len(self.choices),
            "trial_count": len(self.trials),
            "selected_modules": sorted(set(selected_modules)),
            "module_counts": module_counts,
            "top_module": top_module,
            "rzs_decisions": decisions,
            "avg_observed_gain": avg_gain,
            "avg_autonomy_score": avg_autonomy,
            "avg_choice_score": avg_score,
            "final_energy": self.energy,
            "learning_session_id": self.source_state.get("learning_session_id", ""),
            "preference_session_id": self.source_state.get("preference_session_id", ""),
            "protected_counts_before": self.source_counts_before,
            "protected_counts_after": counts_after,
            "protected_sources_unchanged": counts_after == self.source_counts_before,
            "autonomous_curriculum_ready": ready,
            "session_complete": True,
        }
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-SUMMARY",
            "curriculum_autonomy_summary",
            f"Curriculo autonomo: {len(set(selected_modules))} modulos escolhidos, top={top_module}, autonomia media={avg_autonomy:.3f}.",
            clamp(0.62 + avg_autonomy * 0.26),
            summary,
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-LIMIT",
            "epistemic_boundary",
            "Este marco nao prova consciencia; prova escolha auditavel de treino por evidencia, preferencia, custo e RZS.",
            0.94,
            {"claim": "autonomous_curriculum_not_consciousness_proof"},
        )
        self.store.write_memory(self.session_id, summary, 0.88 if ready else 0.70)
        self.store.write_episode(
            self.session_id,
            "choose_own_training_curriculum",
            f"choices={len(self.choices)} modules={len(set(selected_modules))} top={top_module}",
            "Darwin passa a selecionar o proximo treino por metaprendizagem, preferencias e RZS.",
            self.choices[0].sigma_before if self.choices else 0.0,
            self.choices[-1].sigma_after if self.choices else 0.0,
        )
        self.store.log_handoff(
            self.session_id,
            "usar_curriculo_autonomo_v49_31_para_decidir_o_proximo_treino",
            ready,
            len(set(selected_modules)),
            0.88 if ready else 0.62,
            summary,
        )
        self.store.log_session(self.session_id, "curriculum_complete", self.mode, len(self.choices), self.energy, summary)
        return summary


class AutonomousCurriculumApp:
    BG = "#071018"
    PANEL = "#0d1b26"
    INK = "#eef8ff"
    MUTED = "#a9c7df"
    GREEN = "#7ee2a8"
    BLUE = "#72b7ff"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Autonomous Curriculum v49.31")
        self.root.geometry("1180x780")
        self.root.minsize(980, 640)
        self.root.configure(bg=self.BG)
        self.core = AutonomousCurriculumCore(mode="gui")
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
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(header, text="DARWIN AUTONOMOUS CURRICULUM v49.31", bg=self.BG, fg=self.INK, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(header, text="candidatos -> RZS -> escolha -> ensaio -> reflexao", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=400)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=260)
        self.canvas.pack(fill="x")
        buttons = tk.Frame(left, bg="#102231")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Rodar 12 ciclos", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(buttons, text="Escolhas", command=self.show_choices).pack(side="left", padx=4, pady=8)
        ttk.Button(buttons, text="Candidatos", command=self.show_candidates).pack(side="left", padx=4, pady=8)
        ttk.Button(buttons, text="Ensaios", command=self.show_trials).pack(side="left", padx=4, pady=8)
        self.main = tk.Text(left, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.main.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Resumo", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.side = tk.Text(right, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.side.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = AutonomousCurriculumCore(mode="gui")
        self.summary = self.core.run(12)
        self.show_choices()
        self.show_summary()

    def show_summary(self) -> None:
        s = self.summary
        lines = [
            f"sessao: {s.get('session_id', '')}",
            f"candidatos: {s.get('candidate_count', 0)}",
            f"escolhas: {s.get('choice_count', 0)}",
            f"modulos: {', '.join(s.get('selected_modules', []))}",
            f"top: {s.get('top_module', '')}",
            f"RZS: {', '.join(s.get('rzs_decisions', []))}",
            "",
            f"ganho medio: {s.get('avg_observed_gain', 0):.3f}",
            f"autonomia media: {s.get('avg_autonomy_score', 0):.3f}",
            f"energia final: {s.get('final_energy', 0):.3f}",
            f"pronto: {s.get('autonomous_curriculum_ready', False)}",
        ]
        self.side.delete("1.0", "end")
        self.side.insert("end", "\n".join(lines))

    def show_choices(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Escolhas autonomas", ""]
        for choice in self.core.choices:
            lines.append(
                f"{choice.step_index:02d} {choice.module_key} -> {choice.chosen_action}\n"
                f"   score={choice.score:.3f} gain={choice.expected_gain:.3f} RZS={choice.rzs_decision}"
            )
        self.main.insert("end", "\n".join(lines))

    def show_candidates(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Ultimos candidatos pontuados", ""]
        for c in self.core.candidates[-27:]:
            lines.append(
                f"{c.step_index:02d} {c.module_key:<18} score={c.score_after_rzs:.3f} "
                f"pref={c.preference_strength:.3f} gain={c.expected_gain:.3f} RZS={c.rzs_decision}"
            )
        self.main.insert("end", "\n".join(lines))

    def show_trials(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Ensaios internos", ""]
        for trial in self.core.trials:
            lines.append(f"{trial.step_index:02d} {trial.module_key} gain={trial.observed_gain:.3f} autonomia={trial.autonomy_score:.3f} energia={trial.energy_after:.3f}")
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
        self.canvas.create_text(cx, 30, text="qual treino eu escolho agora?", fill=self.INK, font=("Segoe UI", 17, "bold"))
        radius = min(w, h) * 0.28
        modules = CURRICULUM_MODULES
        counts = self.summary.get("module_counts", {})
        for i, module in enumerate(modules):
            angle = (math.tau / len(modules)) * i + self.phase * 0.12
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius * 0.62
            selected = counts.get(module, 0)
            fill = self.GREEN if selected else "#173044"
            outline = self.BLUE if module == self.summary.get("top_module") else "#31516a"
            r = 18 + selected * 3
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=outline, width=2)
            self.canvas.create_text(x, y + r + 14, text=module, fill=self.MUTED, font=("Segoe UI", 8))
        pulse = 1.0 + math.sin(self.phase) * 0.05
        rr = 42 * pulse
        self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="#72b7ff", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - rr * 0.36, cy - rr * 0.36, cx + rr * 0.36, cy + rr * 0.36, fill="#e7fbff", outline="")
        self.canvas.create_text(cx, h - 26, text=f"ultima escolha: {self.core.choices[-1].module_key if self.core.choices else 'nenhuma'}", fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.31 - AUTONOMOUS CURRICULUM")
    print("=" * 72)
    print(f"- sessao: {summary['session_id']}")
    print(f"- candidatos={summary['candidate_count']} escolhas={summary['choice_count']} ensaios={summary['trial_count']}")
    print(f"- modulos escolhidos: {', '.join(summary['selected_modules'])}")
    print(f"- top modulo: {summary['top_module']}")
    print(f"- ganho medio={summary['avg_observed_gain']:.3f} autonomia media={summary['avg_autonomy_score']:.3f}")
    print(f"- RZS: {', '.join(summary['rzs_decisions'])}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.31 Autonomous Curriculum")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cycles", type=int, default=12)
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4931)
    args = ap.parse_args()
    if args.self_test:
        core = AutonomousCurriculumCore(seed=args.seed, mode="self_test")
        summary = core.run(args.cycles)
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    AutonomousCurriculumApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
