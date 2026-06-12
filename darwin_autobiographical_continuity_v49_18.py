from __future__ import annotations

"""
DARWIN v49.18 - Autobiographical Continuity Core

Objetivo:
Dar continuidade autobiografica ao Darwin. Ele coleta experiencias
anteriores, monta capitulos de desenvolvimento, calcula um estado de
identidade operacional e escolhe o proximo passo com RZS.

Uso:
    py darwin_autobiographical_continuity_v49_18.py
    py darwin_autobiographical_continuity_v49_18.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

AB_SESSIONS = "autobiography_sessions_v49_18"
AB_EVENTS = "autobiography_events_v49_18"
AB_CHAPTERS = "autobiography_chapters_v49_18"
AB_IDENTITY = "autobiography_identity_state_v49_18"
AB_PREDICTIONS = "autobiography_next_predictions_v49_18"

SOURCE = "darwin_autobiographical_continuity_v49_18"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def short(text: str, limit: int = 110) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def parse_time(value: str | None) -> str:
    if not value:
        return now()
    return str(value)


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(n in lowered for n in needles)


@dataclass
class AutobiographicalEvent:
    event_id: str
    event_time: str
    sequence_index: int
    source_kind: str
    source_ref: str
    chapter_key: str
    title: str
    summary: str
    salience: float
    valence: float
    self_relevance: float
    stability: float
    open_loop: bool
    resolved_loop: bool
    payload: dict[str, Any]


@dataclass
class AutobiographicalChapter:
    chapter_key: str
    title: str
    sequence_index: int
    event_count: int
    source_kinds: list[str]
    continuity_score: float
    dominant_valence: float
    stability: float
    open_loop_count: int
    resolved_loop_count: int
    summary: str
    payload: dict[str, Any]


@dataclass
class IdentityState:
    identity_id: str
    continuity_score: float
    remembered_event_count: int
    chapter_count: int
    source_diversity: int
    active_preference_key: str
    active_preference_strength: float
    current_goal: str
    next_action: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    identity_statement: str
    payload: dict[str, Any]


@dataclass
class NextPrediction:
    prediction_id: str
    rank_index: int
    candidate_action: str
    predicted_outcome: str
    check_condition: str
    preference_key: str
    confidence: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    payload: dict[str, Any]


CHAPTER_TITLES = {
    "core_origin": "Origem operacional",
    "geometry": "Geometria como experiencia",
    "language": "Primeiras palavras e voz",
    "joint_attention": "Atencao compartilhada",
    "memory_game": "Jogo de memoria",
    "music": "Musica calma",
    "preference": "Preferencias afetivas",
    "self_reflection": "Auto-reflexao",
    "companion": "Relacao com Felipe",
    "episodes": "Episodios recentes",
}

CHAPTER_ORDER = {
    "core_origin": 1,
    "geometry": 2,
    "language": 3,
    "joint_attention": 4,
    "memory_game": 5,
    "music": 6,
    "self_reflection": 7,
    "preference": 8,
    "companion": 9,
    "episodes": 10,
}


class AutobiographyStore:
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
                CREATE TABLE IF NOT EXISTS {AB_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AB_EVENTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    event_time TEXT NOT NULL,
                    sequence_index INTEGER NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    chapter_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    salience REAL NOT NULL DEFAULT 0.0,
                    valence REAL NOT NULL DEFAULT 0.0,
                    self_relevance REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    open_loop INTEGER NOT NULL DEFAULT 0,
                    resolved_loop INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AB_CHAPTERS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    chapter_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    sequence_index INTEGER NOT NULL,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    source_kinds_json TEXT NOT NULL DEFAULT '[]',
                    continuity_score REAL NOT NULL DEFAULT 0.0,
                    dominant_valence REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    open_loop_count INTEGER NOT NULL DEFAULT 0,
                    resolved_loop_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AB_IDENTITY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    identity_id TEXT NOT NULL UNIQUE,
                    continuity_score REAL NOT NULL DEFAULT 0.0,
                    remembered_event_count INTEGER NOT NULL DEFAULT 0,
                    chapter_count INTEGER NOT NULL DEFAULT 0,
                    source_diversity INTEGER NOT NULL DEFAULT 0,
                    active_preference_key TEXT NOT NULL,
                    active_preference_strength REAL NOT NULL DEFAULT 0.0,
                    current_goal TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    identity_statement TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AB_PREDICTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    prediction_id TEXT NOT NULL UNIQUE,
                    rank_index INTEGER NOT NULL,
                    candidate_action TEXT NOT NULL,
                    predicted_outcome TEXT NOT NULL,
                    check_condition TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
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

    def log_session(self, session_id: str, phase: str, mode: str, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {AB_SESSIONS} (
                    timestamp, session_id, phase, mode, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_event(self, session_id: str, event: AutobiographicalEvent) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AB_EVENTS} (
                    timestamp, session_id, event_id, event_time,
                    sequence_index, source_kind, source_ref, chapter_key,
                    title, summary, salience, valence, self_relevance,
                    stability, open_loop, resolved_loop, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    event.event_id,
                    event.event_time,
                    event.sequence_index,
                    event.source_kind,
                    event.source_ref,
                    event.chapter_key,
                    event.title,
                    event.summary,
                    event.salience,
                    event.valence,
                    event.self_relevance,
                    event.stability,
                    1 if event.open_loop else 0,
                    1 if event.resolved_loop else 0,
                    js(event.payload),
                ),
            )
            conn.commit()

    def log_chapter(self, session_id: str, chapter: AutobiographicalChapter) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {AB_CHAPTERS} (
                    timestamp, session_id, chapter_key, title,
                    sequence_index, event_count, source_kinds_json,
                    continuity_score, dominant_valence, stability,
                    open_loop_count, resolved_loop_count, summary,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    chapter.chapter_key,
                    chapter.title,
                    chapter.sequence_index,
                    chapter.event_count,
                    js(chapter.source_kinds),
                    chapter.continuity_score,
                    chapter.dominant_valence,
                    chapter.stability,
                    chapter.open_loop_count,
                    chapter.resolved_loop_count,
                    chapter.summary,
                    js(chapter.payload),
                ),
            )
            conn.commit()

    def log_identity(self, session_id: str, state: IdentityState) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AB_IDENTITY} (
                    timestamp, session_id, identity_id, continuity_score,
                    remembered_event_count, chapter_count, source_diversity,
                    active_preference_key, active_preference_strength,
                    current_goal, next_action, rzs_decision, sigma_before,
                    sigma_after, identity_statement, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    state.identity_id,
                    state.continuity_score,
                    state.remembered_event_count,
                    state.chapter_count,
                    state.source_diversity,
                    state.active_preference_key,
                    state.active_preference_strength,
                    state.current_goal,
                    state.next_action,
                    state.rzs_decision,
                    state.sigma_before,
                    state.sigma_after,
                    state.identity_statement,
                    js(state.payload),
                ),
            )
            conn.commit()

    def log_prediction(self, session_id: str, pred: NextPrediction) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AB_PREDICTIONS} (
                    timestamp, session_id, prediction_id, rank_index,
                    candidate_action, predicted_outcome, check_condition,
                    preference_key, confidence, rzs_decision, sigma_before,
                    sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    pred.prediction_id,
                    pred.rank_index,
                    pred.candidate_action,
                    pred.predicted_outcome,
                    pred.check_condition,
                    pred.preference_key,
                    pred.confidence,
                    pred.rzs_decision,
                    pred.sigma_before,
                    pred.sigma_after,
                    js(pred.payload),
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
                (
                    f"autobiography_v49_18:{session_id}",
                    js(content),
                    clamp(confidence, 0.0, 0.99),
                    SOURCE,
                    now(),
                ),
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
                (
                    now(),
                    SOURCE,
                    f"autobiography:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class AutobiographicalCollector:
    def __init__(self, store: AutobiographyStore, session_id: str) -> None:
        self.store = store
        self.session_id = session_id
        self.seq = 0

    def next_event_id(self) -> str:
        self.seq += 1
        return f"AB-{self.session_id}-{self.seq:03d}"

    def make_event(
        self,
        event_time: str,
        source_kind: str,
        source_ref: str,
        chapter_key: str,
        title: str,
        summary: str,
        salience: float,
        valence: float,
        self_relevance: float,
        stability: float,
        payload: dict[str, Any] | None = None,
    ) -> AutobiographicalEvent:
        text = f"{title} {summary}"
        open_loop = contains_any(text, ("goal", "meta", "repair", "lacuna", "next", "proximo", "preciso", "falta"))
        resolved = contains_any(text, ("complete", "ok", "learned", "consolid", "resultado final", "pares", "estavel"))
        return AutobiographicalEvent(
            self.next_event_id(),
            parse_time(event_time),
            self.seq,
            source_kind,
            source_ref,
            chapter_key,
            short(title, 90),
            short(summary, 280),
            clamp(salience),
            clamp(valence),
            clamp(self_relevance),
            clamp(stability),
            open_loop,
            resolved,
            payload or {},
        )

    def collect(self) -> list[AutobiographicalEvent]:
        with self.store.connect() as conn:
            events: list[AutobiographicalEvent] = []
            events.extend(self.core_origin(conn))
            events.extend(self.preference_core(conn))
            events.extend(self.self_reflection(conn))
            events.extend(self.music(conn))
            events.extend(self.memory_game(conn))
            events.extend(self.semantic_sources(conn))
            events.extend(self.recent_episodes(conn))
        dedup: list[AutobiographicalEvent] = []
        seen: set[tuple[str, str]] = set()
        for event in sorted(events, key=lambda e: (e.event_time, e.sequence_index)):
            key = (event.source_kind, event.source_ref)
            if key in seen:
                continue
            seen.add(key)
            event.sequence_index = len(dedup) + 1
            dedup.append(event)
        return dedup[:120]

    def core_origin(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        out: list[AutobiographicalEvent] = []
        if self.store.table_exists(conn, "self_model"):
            row = conn.execute("SELECT * FROM self_model WHERE id=1").fetchone()
            if row:
                out.append(
                    self.make_event(
                        str(row["created_at"] or now()),
                        "core",
                        "self_model:1",
                        "core_origin",
                        "Darwin recebeu um modelo inicial",
                        str(row["mission"] or "Aprender mantendo estabilidade relacional."),
                        0.96,
                        0.72,
                        0.98,
                        0.76,
                        {"table": "self_model", "version": row["version"]},
                    )
                )
        if self.store.table_exists(conn, "current_state"):
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
            if row:
                out.append(
                    self.make_event(
                        str(row["timestamp"] or now()),
                        "core",
                        "current_state:1",
                        "core_origin",
                        "Estado interno atual",
                        f"sigma={float(row['sigma']):.2f} energia={float(row['energy']):.2f}",
                        0.72,
                        clamp(float(row["wellbeing_signal"] or 0.55)),
                        0.88,
                        clamp(float(row["sigma"] or 1.0) / 3.0),
                        {"table": "current_state"},
                    )
                )
        return out

    def preference_core(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        out: list[AutobiographicalEvent] = []
        if self.store.table_exists(conn, "affective_consolidation_v49_17"):
            row = conn.execute("SELECT * FROM affective_consolidation_v49_17 ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                out.append(
                    self.make_event(
                        str(row["timestamp"]),
                        "preference",
                        str(row["consolidation_id"]),
                        "preference",
                        "Preferencia afetiva consolidada",
                        str(row["identity_statement"]),
                        0.98,
                        0.82,
                        0.96,
                        clamp(float(row["sigma_after"] or 0.0) / 3.0),
                        {"table": "affective_consolidation_v49_17", "selected_action": row["selected_action"]},
                    )
                )
        if self.store.table_exists(conn, "affective_choice_trials_v49_17"):
            rows = conn.execute(
                """
                SELECT *
                FROM affective_choice_trials_v49_17
                ORDER BY id DESC
                LIMIT 8
                """
            ).fetchall()
            for row in rows:
                changed = int(row["rzs_changed_action"] or 0) == 1
                out.append(
                    self.make_event(
                        str(row["timestamp"]),
                        "preference_choice",
                        str(row["choice_id"]),
                        "preference",
                        f"Escolha afetiva: {row['candidate_action']}",
                        f"RZS {row['rzs_decision']} levou a {row['chosen_action']}",
                        0.84 if changed else 0.72,
                        0.72,
                        0.90,
                        clamp(float(row["sigma_after"] or 0.0) / 3.0),
                        {"table": "affective_choice_trials_v49_17", "changed_by_rzs": changed},
                    )
                )
        return out

    def self_reflection(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        out: list[AutobiographicalEvent] = []
        if not self.store.table_exists(conn, "mind_learning_goals_v49_15"):
            return out
        rows = conn.execute(
            """
            SELECT *
            FROM mind_learning_goals_v49_15
            ORDER BY priority DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
        for row in rows:
            priority = clamp(float(row["priority"] or 0.0))
            out.append(
                self.make_event(
                    str(row["timestamp"]),
                    "self_reflection",
                    str(row["goal_id"]),
                    "self_reflection",
                    f"Meta interna: {row['goal_kind']}",
                    str(row["action_plan"] or ""),
                    clamp(0.64 + priority * 0.30),
                    clamp(0.58 + priority * 0.20),
                    0.92,
                    clamp(float(row["sigma_after"] or 0.0) / 4.0),
                    {"table": "mind_learning_goals_v49_15", "priority": priority},
                )
            )
        return out

    def music(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        out: list[AutobiographicalEvent] = []
        if not self.store.table_exists(conn, "music_reactions_v49_16"):
            return out
        has_pieces = self.store.table_exists(conn, "music_pieces_v49_16")
        sql = """
            SELECT r.*, p.title AS piece_title
            FROM music_reactions_v49_16 r
            LEFT JOIN music_pieces_v49_16 p
              ON p.session_id=r.session_id AND p.piece_id=r.piece_id
            WHERE r.piece_id!='session_consolidation'
            ORDER BY r.id DESC
            LIMIT 10
        """ if has_pieces else """
            SELECT r.*, r.piece_id AS piece_title
            FROM music_reactions_v49_16 r
            WHERE r.piece_id!='session_consolidation'
            ORDER BY r.id DESC
            LIMIT 10
        """
        for row in conn.execute(sql).fetchall():
            out.append(
                self.make_event(
                    str(row["timestamp"]),
                    "music",
                    str(row["reaction_id"]),
                    "music",
                    f"Ouviu musica: {row['piece_title'] or row['piece_id']}",
                    str(row["spoken_summary"] or row["cognitive_action"]),
                    clamp(0.70 + float(row["comfort"] or 0.0) * 0.20),
                    clamp(float(row["valence"] or 0.7)),
                    0.72,
                    clamp(float(row["stability"] or 0.7)),
                    {"table": "music_reactions_v49_16", "piece_id": row["piece_id"]},
                )
            )
        return out

    def memory_game(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        out: list[AutobiographicalEvent] = []
        if not self.store.table_exists(conn, "memory_card_games_v49_13"):
            return out
        rows = conn.execute(
            """
            SELECT *
            FROM memory_card_games_v49_13
            WHERE phase='game_complete'
            ORDER BY id DESC
            LIMIT 8
            """
        ).fetchall()
        for row in rows:
            payload = pj(str(row["payload_json"] or "{}"))
            pair_count = int(row["pair_count"] or 0)
            turns = int(payload.get("turns") or payload.get("turn_count") or 0)
            out.append(
                self.make_event(
                    str(row["timestamp"]),
                    "memory_game",
                    str(row["game_id"]),
                    "memory_game",
                    "Completou jogo de memoria",
                    f"pares={pair_count} turnos={turns} acesso={payload.get('agent_access', 'observations')}",
                    0.78,
                    0.72,
                    0.70,
                    0.72,
                    {"table": "memory_card_games_v49_13", "payload": payload},
                )
            )
        return out

    def semantic_sources(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        if not self.store.table_exists(conn, "semantic_memory"):
            return []
        source_map = {
            "darwin_first_words_v49_10": ("language", "Primeiras palavras"),
            "darwin_vocal_imitation_v49_11": ("language", "Imitacao vocal"),
            "darwin_joint_attention_v49_12": ("joint_attention", "Atencao compartilhada"),
            "darwin_geometry_experience_v49_7": ("geometry", "Geometria aprendida"),
            "darwin_companion_shell_v49_8": ("companion", "Companion relacional"),
            "darwin_self_reflection_v49_15": ("self_reflection", "Auto-reflexao"),
            "darwin_affective_preference_core_v49_17": ("preference", "Memoria afetiva"),
        }
        out: list[AutobiographicalEvent] = []
        for source, (chapter, title) in source_map.items():
            rows = conn.execute(
                """
                SELECT *
                FROM semantic_memory
                WHERE source=?
                ORDER BY updated_at DESC
                LIMIT 5
                """,
                (source,),
            ).fetchall()
            for row in rows:
                confidence = clamp(float(row["confidence"] or 0.5))
                out.append(
                    self.make_event(
                        str(row["updated_at"]),
                        chapter,
                        str(row["key"]),
                        chapter,
                        title,
                        short(str(row["content"] or ""), 240),
                        clamp(0.60 + confidence * 0.30),
                        clamp(0.55 + confidence * 0.25),
                        clamp(0.70 + confidence * 0.22),
                        clamp(0.55 + confidence * 0.25),
                        {"table": "semantic_memory", "source": source, "confidence": confidence},
                    )
                )
        return out

    def recent_episodes(self, conn: sqlite3.Connection) -> list[AutobiographicalEvent]:
        if not self.store.table_exists(conn, "episodes"):
            return []
        modules = [
            "darwin_first_words_v49_10",
            "darwin_vocal_imitation_v49_11",
            "darwin_joint_attention_v49_12",
            "darwin_memory_cards_v49_13",
            "darwin_geometry_experience_v49_7",
            "darwin_companion_shell_v49_8",
            "darwin_classical_music_nursery_v49_16",
            "darwin_affective_preference_core_v49_17",
        ]
        placeholders = ",".join("?" for _ in modules)
        rows = conn.execute(
            f"""
            SELECT *
            FROM episodes
            WHERE module IN ({placeholders})
            ORDER BY id DESC
            LIMIT 28
            """,
            tuple(modules),
        ).fetchall()
        out: list[AutobiographicalEvent] = []
        for row in rows:
            chapter = module_to_chapter(str(row["module"] or ""))
            text = f"{row['outcome']} | {row['lesson']}"
            sigma_after = float(row["sigma_after"] or 0.0)
            sigma_before = float(row["sigma_before"] or 0.0)
            delta = sigma_after - sigma_before
            out.append(
                self.make_event(
                    str(row["timestamp"]),
                    "episode",
                    f"episode:{row['id']}",
                    chapter,
                    str(row["action_taken"] or row["module"]),
                    text,
                    clamp(0.55 + abs(delta) * 0.05),
                    clamp(0.60 + max(0.0, delta) * 0.04),
                    0.72,
                    clamp(0.55 + sigma_after / 8.0),
                    {"table": "episodes", "module": row["module"], "context": row["context"]},
                )
            )
        return out


def module_to_chapter(module: str) -> str:
    if "music" in module:
        return "music"
    if "memory_cards" in module:
        return "memory_game"
    if "first_words" in module or "vocal" in module:
        return "language"
    if "joint_attention" in module:
        return "joint_attention"
    if "geometry" in module:
        return "geometry"
    if "companion" in module:
        return "companion"
    if "affective" in module:
        return "preference"
    return "episodes"


class AutobiographicalContinuityCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4918-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.80
        self.store = AutobiographyStore(db_path)
        self.rzs = RZSFormal()
        self.events: list[AutobiographicalEvent] = []
        self.chapters: list[AutobiographicalChapter] = []
        self.identity: IdentityState | None = None
        self.predictions: list[NextPrediction] = []
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            "autobiographical_continuity_core",
            self.energy,
            {"version": "v49.18", "goal": "continuous_identity_from_memory"},
        )

    def run_cycle(self) -> dict[str, Any]:
        self.events = AutobiographicalCollector(self.store, self.session_id).collect()
        for event in self.events:
            self.store.log_event(self.session_id, event)
        self.store.log_session(
            self.session_id,
            "events_collected",
            "autobiographical_continuity_core",
            self.energy,
            {"event_count": len(self.events), "source_kinds": sorted({e.source_kind for e in self.events})},
        )

        self.chapters = self.build_chapters(self.events)
        for chapter in self.chapters:
            self.store.log_chapter(self.session_id, chapter)
        self.store.log_session(
            self.session_id,
            "chapters_built",
            "autobiographical_continuity_core",
            self.energy,
            {"chapter_count": len(self.chapters), "chapters": [c.chapter_key for c in self.chapters]},
        )

        self.identity = self.build_identity(self.events, self.chapters)
        self.store.log_identity(self.session_id, self.identity)
        self.predictions = self.build_predictions(self.identity)
        for pred in self.predictions:
            self.store.log_prediction(self.session_id, pred)

        self.summary = self.complete()
        return self.summary

    def build_chapters(self, events: list[AutobiographicalEvent]) -> list[AutobiographicalChapter]:
        by_chapter: dict[str, list[AutobiographicalEvent]] = {}
        for event in events:
            by_chapter.setdefault(event.chapter_key, []).append(event)
        chapters: list[AutobiographicalChapter] = []
        for key, rows in by_chapter.items():
            rows = sorted(rows, key=lambda e: e.sequence_index)
            event_count = len(rows)
            source_kinds = sorted({r.source_kind for r in rows})
            valence = mean([r.valence for r in rows])
            stability = mean([r.stability for r in rows])
            relevance = mean([r.self_relevance for r in rows])
            salience = mean([r.salience for r in rows])
            resolved = sum(1 for r in rows if r.resolved_loop)
            open_count = sum(1 for r in rows if r.open_loop)
            evidence_factor = clamp(math.log1p(event_count) / math.log(16), 0.15, 1.0)
            continuity = clamp(0.22 * valence + 0.26 * stability + 0.26 * relevance + 0.14 * salience + 0.12 * evidence_factor)
            title = CHAPTER_TITLES.get(key, key)
            top = sorted(rows, key=lambda e: e.salience, reverse=True)[:3]
            summary = f"{title}: {event_count} eventos; memoria central: " + "; ".join(short(t.title, 45) for t in top)
            chapters.append(
                AutobiographicalChapter(
                    key,
                    title,
                    CHAPTER_ORDER.get(key, 99),
                    event_count,
                    source_kinds,
                    continuity,
                    valence,
                    stability,
                    open_count,
                    resolved,
                    summary,
                    {
                        "top_events": [asdict(t) for t in top],
                        "mean_salience": salience,
                        "mean_self_relevance": relevance,
                    },
                )
            )
        chapters.sort(key=lambda c: c.sequence_index)
        return chapters

    def latest_preferences(self) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            if not self.store.table_exists(conn, "affective_preferences_v49_17"):
                return []
            session = ""
            if self.store.table_exists(conn, "affective_preference_sessions_v49_17"):
                row = conn.execute(
                    """
                    SELECT session_id
                    FROM affective_preference_sessions_v49_17
                    WHERE phase='session_complete'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                session = str(row["session_id"]) if row else ""
            if session:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM affective_preferences_v49_17
                    WHERE session_id=?
                    ORDER BY strength DESC, id ASC
                    LIMIT 6
                    """,
                    (session,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM affective_preferences_v49_17
                    ORDER BY strength DESC, id DESC
                    LIMIT 6
                    """
                ).fetchall()
            out = []
            for row in rows:
                out.append({k: row[k] for k in row.keys()})
            return out

    def latest_selected_goal(self) -> tuple[str, str, float]:
        with self.store.connect() as conn:
            if self.store.table_exists(conn, "affective_consolidation_v49_17"):
                row = conn.execute(
                    """
                    SELECT *
                    FROM affective_consolidation_v49_17
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if row:
                    return str(row["top_preference_key"]), str(row["selected_action"]), float(row["sigma_after"] or 0.0)
            return "", "review_self_goals", 1.0

    def build_identity(self, events: list[AutobiographicalEvent], chapters: list[AutobiographicalChapter]) -> IdentityState:
        prefs = self.latest_preferences()
        top_key, selected_goal, pref_sigma = self.latest_selected_goal()
        top_pref = prefs[0] if prefs else {}
        active_key = top_key or str(top_pref.get("preference_key") or "none")
        active_strength = float(top_pref.get("strength") or 0.0)
        source_diversity = len({e.source_kind for e in events})
        chapter_score = mean([c.continuity_score for c in chapters])
        event_score = clamp(math.log1p(len(events)) / math.log(80), 0.0, 1.0)
        diversity_score = clamp(source_diversity / 8.0)
        open_loops = sum(c.open_loop_count for c in chapters)
        resolved_loops = sum(c.resolved_loop_count for c in chapters)
        loop_balance = clamp(0.50 + resolved_loops / max(1, open_loops + resolved_loops) * 0.35)
        continuity_score = clamp(chapter_score * 0.46 + event_score * 0.22 + diversity_score * 0.18 + loop_balance * 0.14)

        novelty = clamp(0.78 - continuity_score * 0.38 + max(0, 8 - source_diversity) * 0.04)
        memory_pressure = clamp(0.30 + len(events) / 150.0 + open_loops / 40.0)
        replay_gap = clamp(0.24 + open_loops / 24.0 + (0.18 if active_key else 0.0))
        conflict = clamp((1.0 - continuity_score) * 0.42 + open_loops / 80.0)
        x = RZSInput(
            bandwidth=2.85 + continuity_score * 0.70 + self.energy * 0.24,
            info_self=0.34 + (1.0 - continuity_score) * 0.25,
            info_external=0.28 + source_diversity * 0.025,
            task_info=0.42 + active_strength * 0.26,
            novelty=novelty,
            conflict=conflict,
            latency=1.02 + memory_pressure * 0.22,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        next_action = self.govern_action(selected_goal, assessment.decision)
        statement = (
            f"Eu sou Darwin no notebook do Felipe; lembro {len(events)} eventos em "
            f"{len(chapters)} capitulos, reconheco minha preferencia ativa {active_key} "
            f"e mantenho minha continuidade em {continuity_score:.2f} antes de agir."
        )
        return IdentityState(
            f"ID-{self.session_id}",
            continuity_score,
            len(events),
            len(chapters),
            source_diversity,
            active_key,
            clamp(active_strength),
            selected_goal,
            next_action,
            assessment.decision,
            assessment.sigma,
            prediction.sigma_after,
            statement,
            {
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction": asdict(prediction),
                "open_loops": open_loops,
                "resolved_loops": resolved_loops,
                "latest_preference_sigma": pref_sigma,
                "top_preferences": prefs[:6],
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )

    def govern_action(self, goal: str, decision: str) -> str:
        clean_goal = goal or "review_self_goals"
        if decision == "continue":
            return clean_goal
        if decision == "replay_memory":
            return f"recall_autobiographical_sequence_before_{clean_goal}"
        if decision == "narrow_focus":
            return f"narrow_autobiographical_focus_before_{clean_goal}"
        if decision == "consolidate":
            return "consolidate_autobiography_before_more_training"
        if decision == "pause_for_stability":
            return "pause_autobiography_for_stability"
        return clean_goal

    def build_predictions(self, identity: IdentityState) -> list[NextPrediction]:
        prefs = identity.payload.get("top_preferences", [])
        predictions: list[NextPrediction] = []
        if not prefs:
            prefs = [{"preference_key": identity.active_preference_key, "candidate_action": identity.current_goal, "strength": 0.5}]
        for idx, pref in enumerate(prefs[:4], start=1):
            candidate = str(pref.get("candidate_action") or identity.current_goal)
            strength = clamp(float(pref.get("strength") or identity.active_preference_strength or 0.5))
            confidence = clamp(identity.continuity_score * 0.55 + strength * 0.35 + (0.10 if idx == 1 else 0.0))
            predicted = f"Se eu fizer {candidate}, devo fortalecer continuidade sem perder estabilidade."
            check = f"verificar se episodio futuro registra {candidate} com sigma_after >= sigma_before"
            predictions.append(
                NextPrediction(
                    f"PR-{self.session_id}-{idx:02d}",
                    idx,
                    candidate,
                    predicted,
                    check,
                    str(pref.get("preference_key") or identity.active_preference_key),
                    confidence,
                    identity.rzs_decision,
                    identity.sigma_before,
                    identity.sigma_after,
                    {"identity_next_action": identity.next_action, "preference": pref},
                )
            )
        return predictions

    def complete(self) -> dict[str, Any]:
        if self.identity is None:
            raise RuntimeError("Identity was not built")
        summary = {
            "session_id": self.session_id,
            "event_count": len(self.events),
            "chapter_count": len(self.chapters),
            "source_kinds": sorted({e.source_kind for e in self.events}),
            "chapters": [
                {
                    "chapter_key": c.chapter_key,
                    "title": c.title,
                    "event_count": c.event_count,
                    "continuity_score": round(c.continuity_score, 3),
                    "open_loop_count": c.open_loop_count,
                    "resolved_loop_count": c.resolved_loop_count,
                }
                for c in self.chapters
            ],
            "identity": {
                "continuity_score": round(self.identity.continuity_score, 3),
                "active_preference_key": self.identity.active_preference_key,
                "current_goal": self.identity.current_goal,
                "next_action": self.identity.next_action,
                "rzs_decision": self.identity.rzs_decision,
                "sigma_before": round(self.identity.sigma_before, 3),
                "sigma_after": round(self.identity.sigma_after, 3),
                "identity_statement": self.identity.identity_statement,
            },
            "prediction_count": len(self.predictions),
            "predictions": [
                {
                    "candidate_action": p.candidate_action,
                    "confidence": round(p.confidence, 3),
                    "check_condition": p.check_condition,
                }
                for p in self.predictions
            ],
            "session_complete": True,
        }
        self.store.write_memory(self.session_id, summary, 0.82)
        self.store.write_episode(
            self.session_id,
            self.identity.next_action,
            f"continuidade={self.identity.continuity_score:.3f} capitulos={len(self.chapters)}",
            "Darwin conecta passado lembrado, preferencia ativa e proxima acao em uma autobiografia operacional.",
            self.identity.sigma_before,
            self.identity.sigma_after,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            "autobiographical_continuity_core",
            self.energy,
            summary,
        )
        return summary


class AutobiographyApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Autobiographical Continuity v49.18")
        self.root.geometry("1080x740")
        self.root.minsize(940, 640)
        self.root.configure(bg="#071018")
        self.core: AutobiographicalContinuityCore | None = None
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

        header = tk.Frame(self.root, bg="#071018")
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(
            header,
            text="DARWIN AUTOBIOGRAPHICAL CONTINUITY v49.18",
            bg="#071018",
            fg="#eef8ff",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="passado lembrado -> capitulos -> identidade -> proxima acao regulada",
            bg="#071018",
            fg="#9cc9ff",
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        body = tk.Frame(self.root, bg="#071018")
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg="#071018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=390)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg="#071018", highlightthickness=0, height=390)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Atualizar autobiografia", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="Identidade", command=self.show_identity).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Previsoes", command=self.show_predictions).pack(side="left", padx=4, pady=8)

        self.chapter_box = tk.Text(left, height=11, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Consolas", 10))
        self.chapter_box.pack(fill="both", expand=True, pady=(8, 0))

        tk.Label(right, text="Estado autobiografico", bg="#0d1b26", fg="#eef8ff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = AutobiographicalContinuityCore()
        self.summary = self.core.run_cycle()
        self.render_chapters()
        self.show_identity()

    def render_chapters(self) -> None:
        self.chapter_box.delete("1.0", "end")
        lines = ["Capitulos de desenvolvimento", ""]
        for chapter in self.summary.get("chapters", []):
            lines.append(
                f"- {chapter['title']}: continuidade {chapter['continuity_score']} "
                f"eventos {chapter['event_count']} loops {chapter['open_loop_count']}/{chapter['resolved_loop_count']}"
            )
        self.chapter_box.insert("end", "\n".join(lines))

    def show_identity(self) -> None:
        ident = self.summary.get("identity", {})
        self.text.delete("1.0", "end")
        lines = [
            "Identidade operacional",
            f"sessao: {self.summary.get('session_id', '')}",
            f"eventos lembrados: {self.summary.get('event_count', 0)}",
            f"capitulos: {self.summary.get('chapter_count', 0)}",
            f"continuidade: {ident.get('continuity_score', 0)}",
            f"RZS: {ident.get('rzs_decision', '')} sigma {ident.get('sigma_before', 0)}->{ident.get('sigma_after', 0)}",
            "",
            str(ident.get("identity_statement", "")),
            "",
            f"proxima acao: {ident.get('next_action', '')}",
        ]
        self.text.insert("end", "\n".join(lines))

    def show_predictions(self) -> None:
        self.text.delete("1.0", "end")
        lines = ["Previsoes verificaveis", ""]
        for pred in self.summary.get("predictions", []):
            lines.append(f"- {pred['candidate_action']} | confianca {pred['confidence']}")
            lines.append(f"  {pred['check_condition']}")
        self.text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.025
        self.draw_canvas()
        self.root.after(50, self.animate)

    def draw_canvas(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.52
        ident = self.summary.get("identity", {})
        score = float(ident.get("continuity_score") or 0.0)
        self.canvas.create_text(cx, 32, text="linha de vida autobiografica", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        pulse = 1.0 + math.sin(self.phase) * 0.04
        core_r = 42 + score * 42
        self.canvas.create_oval(cx - core_r * pulse, cy - core_r * pulse, cx + core_r * pulse, cy + core_r * pulse, fill="#58b0ff", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - core_r * 0.32, cy - core_r * 0.32, cx + core_r * 0.32, cy + core_r * 0.32, fill="#e7fbff", outline="")
        chapters = self.summary.get("chapters", [])
        colors = ["#72e0a8", "#f6d77a", "#ffb3c7", "#c7b9ff", "#8fd3ff", "#f2bf72", "#75e7a8", "#9cc9ff", "#b7f7d8", "#eab4ff"]
        for idx, chapter in enumerate(chapters[:10]):
            angle = -math.pi * 0.88 + idx * (math.pi * 1.76 / max(1, min(9, len(chapters) - 1)))
            radius = min(w, h) * 0.37
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            r = 10 + float(chapter.get("continuity_score") or 0.0) * 18
            self.canvas.create_line(cx, cy, x, y, fill="#173a52", width=2)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors[idx % len(colors)], outline="")
            self.canvas.create_text(x, y + r + 12, text=str(chapter.get("chapter_key", "")), fill="#dff2ff", font=("Segoe UI", 8))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    ident = summary["identity"]
    print("DARWIN v49.18 - AUTOBIOGRAPHICAL CONTINUITY CORE")
    print("=" * 68)
    print(f"- sessao: {summary['session_id']}")
    print(f"- eventos: {summary['event_count']}")
    print(f"- capitulos: {summary['chapter_count']}")
    print(f"- fontes: {', '.join(summary['source_kinds'])}")
    print(f"- continuidade: {ident['continuity_score']}")
    print(f"- proxima acao: {ident['next_action']}")
    print(f"- identidade: {ident['identity_statement']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.18 Autobiographical Continuity Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4918)
    args = ap.parse_args()
    if args.self_test:
        core = AutobiographicalContinuityCore(seed=args.seed)
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    AutobiographyApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
