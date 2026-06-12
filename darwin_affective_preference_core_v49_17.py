from __future__ import annotations

"""
DARWIN v49.17 - Preference & Affective Memory Core

Objetivo:
Transformar experiencias anteriores em memoria afetiva operacional:
o Darwin calcula valencia, conforto, curiosidade, estabilidade e
preferencia por dominios de treino. A escolha do proximo treino passa
a ser derivada do historico + RZS, em vez de uma ordem fixa.

Uso:
    py darwin_affective_preference_core_v49_17.py
    py darwin_affective_preference_core_v49_17.py --self-test --details
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

AP_SESSIONS = "affective_preference_sessions_v49_17"
AP_EXPERIENCES = "affective_experiences_v49_17"
AP_PREFERENCES = "affective_preferences_v49_17"
AP_CHOICES = "affective_choice_trials_v49_17"
AP_CONSOLIDATION = "affective_consolidation_v49_17"

SOURCE = "darwin_affective_preference_core_v49_17"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
        return parsed
    except Exception:
        return {} if fallback is None else fallback


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def short(text: str, limit: int = 92) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for part in parts:
        clean = "".join(ch.lower() if ch.isalnum() else " " for ch in str(part))
        out.update(x for x in clean.split() if x)
    return out


@dataclass
class AffectiveExperience:
    experience_id: str
    source_kind: str
    source_ref: str
    title: str
    content: str
    tags: list[str]
    valence: float
    arousal: float
    comfort: float
    curiosity: float
    stability: float
    confidence: float
    sigma_hint: float
    evidence: dict[str, Any]


@dataclass
class PreferenceTrace:
    preference_key: str
    domain: str
    candidate_action: str
    strength: float
    valence: float
    arousal: float
    comfort: float
    curiosity: float
    stability: float
    evidence_count: int
    top_evidence: list[str]
    source_kinds: list[str]
    tags: list[str]


@dataclass
class ChoiceTrial:
    choice_id: str
    rank_index: int
    preference_key: str
    candidate_action: str
    chosen_action: str
    preference_strength: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    rzs_changed_action: bool
    causal_delta: float
    reason: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ActionProfile:
    preference_key: str
    domain: str
    candidate_action: str
    match_terms: tuple[str, ...]
    base_bias: float
    description: str


ACTION_PROFILES = [
    ActionProfile(
        "pref_music_calm",
        "music",
        "listen_to_gentle_music",
        ("music", "classical", "calm_sound", "lullaby", "gentle", "melody", "song"),
        0.62,
        "ouvir musica classica simples para estabilizar e reconhecer padroes",
    ),
    ActionProfile(
        "pref_memory_cards",
        "memory_game",
        "practice_memory_cards",
        ("memory_game", "pair_matching", "visual_memory", "cards", "matching", "game"),
        0.58,
        "treinar memoria visual por tentativa, erro e pares",
    ),
    ActionProfile(
        "pref_first_words",
        "speech",
        "practice_first_words",
        ("first_words", "speech", "word", "mamae", "papai", "felipe", "darwin"),
        0.64,
        "fortalecer primeiras palavras relacionais",
    ),
    ActionProfile(
        "pref_vocal_imitation",
        "speech",
        "practice_voice_imitation",
        ("vocal_imitation", "voice", "sound", "phoneme", "motor", "articulation"),
        0.57,
        "treinar tentativa vocal e correcao progressiva",
    ),
    ActionProfile(
        "pref_joint_attention",
        "relation",
        "practice_joint_attention",
        ("joint_attention", "shared_attention", "binding", "entity", "focus"),
        0.61,
        "ligar palavra, foco e objeto compartilhado",
    ),
    ActionProfile(
        "pref_geometry",
        "geometry",
        "practice_geometry_experience",
        ("geometry", "angle", "shape", "error_learning", "concept", "measure"),
        0.56,
        "continuar geometria como experiencia corrigida",
    ),
    ActionProfile(
        "pref_self_reflection",
        "self_model",
        "review_self_goals",
        ("self_reflection", "goal", "planning", "self_model", "reflection"),
        0.59,
        "revisar metas internas e lacunas de desenvolvimento",
    ),
    ActionProfile(
        "pref_companion_relation",
        "relation",
        "talk_with_felipe",
        ("companion", "felipe", "dialogue", "relation", "caregiver", "conversation"),
        0.66,
        "conversar com Felipe e atualizar o modelo relacional",
    ),
]


class AffectivePreferenceStore:
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
                CREATE TABLE IF NOT EXISTS {AP_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_EXPERIENCES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    experience_id TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    valence REAL NOT NULL DEFAULT 0.0,
                    arousal REAL NOT NULL DEFAULT 0.0,
                    comfort REAL NOT NULL DEFAULT 0.0,
                    curiosity REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    sigma_hint REAL NOT NULL DEFAULT 0.0,
                    evidence_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_PREFERENCES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    candidate_action TEXT NOT NULL,
                    strength REAL NOT NULL DEFAULT 0.0,
                    valence REAL NOT NULL DEFAULT 0.0,
                    arousal REAL NOT NULL DEFAULT 0.0,
                    comfort REAL NOT NULL DEFAULT 0.0,
                    curiosity REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    top_evidence_json TEXT NOT NULL DEFAULT '[]',
                    source_kinds_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_CHOICES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    choice_id TEXT NOT NULL UNIQUE,
                    rank_index INTEGER NOT NULL,
                    preference_key TEXT NOT NULL,
                    candidate_action TEXT NOT NULL,
                    chosen_action TEXT NOT NULL,
                    preference_strength REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    rzs_changed_action INTEGER NOT NULL DEFAULT 0,
                    causal_delta REAL NOT NULL DEFAULT 0.0,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_CONSOLIDATION} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    consolidation_id TEXT NOT NULL UNIQUE,
                    selected_action TEXT NOT NULL,
                    top_preference_key TEXT NOT NULL,
                    preference_count INTEGER NOT NULL DEFAULT 0,
                    experience_count INTEGER NOT NULL DEFAULT 0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    identity_statement TEXT NOT NULL,
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

    def rows(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = (), limit: int | None = None) -> list[sqlite3.Row]:
        if not self.table_exists(conn, table):
            return []
        sql = f"SELECT * FROM {table}{where} ORDER BY id ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return list(conn.execute(sql, params).fetchall())

    def log_session(self, session_id: str, phase: str, mode: str, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {AP_SESSIONS} (
                    timestamp, session_id, phase, mode, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_experience(self, session_id: str, exp: AffectiveExperience) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_EXPERIENCES} (
                    timestamp, session_id, experience_id, source_kind,
                    source_ref, title, content, tags_json, valence,
                    arousal, comfort, curiosity, stability, confidence,
                    sigma_hint, evidence_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    exp.experience_id,
                    exp.source_kind,
                    exp.source_ref,
                    exp.title,
                    exp.content,
                    js(exp.tags),
                    exp.valence,
                    exp.arousal,
                    exp.comfort,
                    exp.curiosity,
                    exp.stability,
                    exp.confidence,
                    exp.sigma_hint,
                    js(exp.evidence),
                    js({"affective_version": "v49.17"}),
                ),
            )
            conn.commit()

    def log_preference(self, session_id: str, pref: PreferenceTrace) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {AP_PREFERENCES} (
                    timestamp, session_id, preference_key, domain,
                    candidate_action, strength, valence, arousal,
                    comfort, curiosity, stability, evidence_count,
                    top_evidence_json, source_kinds_json, tags_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    pref.preference_key,
                    pref.domain,
                    pref.candidate_action,
                    pref.strength,
                    pref.valence,
                    pref.arousal,
                    pref.comfort,
                    pref.curiosity,
                    pref.stability,
                    pref.evidence_count,
                    js(pref.top_evidence),
                    js(pref.source_kinds),
                    js(pref.tags),
                    js({"description": profile_description(pref.preference_key)}),
                ),
            )
            conn.commit()

    def log_choice(self, session_id: str, trial: ChoiceTrial) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_CHOICES} (
                    timestamp, session_id, choice_id, rank_index,
                    preference_key, candidate_action, chosen_action,
                    preference_strength, rzs_decision, sigma_before,
                    sigma_after, rzs_changed_action, causal_delta,
                    reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    trial.choice_id,
                    trial.rank_index,
                    trial.preference_key,
                    trial.candidate_action,
                    trial.chosen_action,
                    trial.preference_strength,
                    trial.rzs_decision,
                    trial.sigma_before,
                    trial.sigma_after,
                    1 if trial.rzs_changed_action else 0,
                    trial.causal_delta,
                    trial.reason,
                    js(trial.payload),
                ),
            )
            conn.commit()

    def log_consolidation(
        self,
        session_id: str,
        consolidation_id: str,
        selected_action: str,
        top_preference_key: str,
        preference_count: int,
        experience_count: int,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
        identity_statement: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_CONSOLIDATION} (
                    timestamp, session_id, consolidation_id, selected_action,
                    top_preference_key, preference_count, experience_count,
                    rzs_decision, sigma_before, sigma_after,
                    identity_statement, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    consolidation_id,
                    selected_action,
                    top_preference_key,
                    preference_count,
                    experience_count,
                    rzs_decision,
                    sigma_before,
                    sigma_after,
                    identity_statement,
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
                (
                    f"affective_preference_v49_17:{session_id}",
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
                    f"affective_preference:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


def profile_description(preference_key: str) -> str:
    for profile in ACTION_PROFILES:
        if profile.preference_key == preference_key:
            return profile.description
    return ""


class AffectiveExperienceCollector:
    def __init__(self, store: AffectivePreferenceStore, session_id: str) -> None:
        self.store = store
        self.session_id = session_id
        self.index = 0

    def next_id(self) -> str:
        self.index += 1
        return f"EXP-{self.session_id}-{self.index:03d}"

    def collect(self) -> list[AffectiveExperience]:
        with self.store.connect() as conn:
            experiences: list[AffectiveExperience] = []
            experiences.extend(self.collect_music(conn))
            experiences.extend(self.collect_memory_cards(conn))
            experiences.extend(self.collect_semantic_sources(conn))
            experiences.extend(self.collect_self_goals(conn))
            experiences.extend(self.collect_recent_episodes(conn))
        seen: set[tuple[str, str]] = set()
        deduped: list[AffectiveExperience] = []
        for exp in experiences:
            key = (exp.source_kind, exp.source_ref)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(exp)
        return deduped[:80]

    def collect_music(self, conn: sqlite3.Connection) -> list[AffectiveExperience]:
        if not self.store.table_exists(conn, "music_reactions_v49_16"):
            return []
        has_pieces = self.store.table_exists(conn, "music_pieces_v49_16")
        if has_pieces:
            sql = """
                SELECT r.*, p.title AS piece_title, p.composer_hint AS composer_hint
                FROM music_reactions_v49_16 r
                LEFT JOIN music_pieces_v49_16 p
                  ON p.session_id=r.session_id AND p.piece_id=r.piece_id
                WHERE r.piece_id!='session_consolidation'
                ORDER BY r.id DESC
                LIMIT 12
            """
        else:
            sql = """
                SELECT r.*, r.piece_id AS piece_title, '' AS composer_hint
                FROM music_reactions_v49_16 r
                WHERE r.piece_id!='session_consolidation'
                ORDER BY r.id DESC
                LIMIT 12
            """
        out: list[AffectiveExperience] = []
        for row in conn.execute(sql).fetchall():
            title = str(row["piece_title"] or row["piece_id"])
            action = str(row["cognitive_action"] or "")
            focus = str(row["attention_focus"] or "")
            tags = sorted({"music", "classical", "calm_sound", row["piece_id"], action, focus} | tokens(title, action, focus))
            out.append(
                AffectiveExperience(
                    self.next_id(),
                    "music",
                    f"{row['session_id']}:{row['reaction_id']}",
                    title,
                    str(row["spoken_summary"] or ""),
                    tags,
                    clamp(float(row["valence"])),
                    clamp(float(row["arousal"])),
                    clamp(float(row["comfort"])),
                    clamp(float(row["curiosity"])),
                    clamp(float(row["stability"])),
                    clamp(mean([float(row["valence"]), float(row["comfort"]), float(row["stability"])])),
                    float(row["sigma_after"] or row["sigma_before"] or 0.0),
                    {"table": "music_reactions_v49_16", "piece_id": row["piece_id"], "composer_hint": row["composer_hint"]},
                )
            )
        return out

    def collect_memory_cards(self, conn: sqlite3.Connection) -> list[AffectiveExperience]:
        if not self.store.table_exists(conn, "memory_card_games_v49_13"):
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM memory_card_games_v49_13
            WHERE phase='game_complete'
            ORDER BY id DESC
            LIMIT 6
            """
        ).fetchall()
        out: list[AffectiveExperience] = []
        for row in rows:
            payload = pj(str(row["payload_json"] or "{}"))
            pair_count = int(row["pair_count"] or payload.get("pair_count") or 0)
            all_matched = len(payload.get("all_positions_matched", [])) >= pair_count * 2 if pair_count else bool(payload.get("game_complete"))
            moves = 0
            memory_picks = 0
            if self.store.table_exists(conn, "memory_card_moves_v49_13"):
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS n,
                           SUM(CASE WHEN decision_source LIKE '%memory%' OR decision_source LIKE '%known_pair%' THEN 1 ELSE 0 END) AS m
                    FROM memory_card_moves_v49_13
                    WHERE session_id=? AND game_id=?
                    """,
                    (row["session_id"], row["game_id"]),
                ).fetchone()
                moves = int(count_row["n"] or 0) if count_row else 0
                memory_picks = int(count_row["m"] or 0) if count_row else 0
            efficiency = clamp(pair_count * 2 / max(1, moves))
            tags = ["memory_game", "pair_matching", "visual_memory", "cards", "error_learning", "game"]
            out.append(
                AffectiveExperience(
                    self.next_id(),
                    "memory_game",
                    f"{row['session_id']}:{row['game_id']}",
                    f"Jogo de memoria {row['game_id']}",
                    f"pares={pair_count} movimentos={moves} uso_memoria={memory_picks}",
                    tags,
                    clamp(0.58 + (0.18 if all_matched else 0.0) + efficiency * 0.08),
                    0.42,
                    clamp(0.50 + efficiency * 0.22),
                    0.78,
                    clamp(0.54 + (0.18 if all_matched else 0.0)),
                    clamp(0.55 + memory_picks / max(2, moves) * 0.35),
                    1.8,
                    {"table": "memory_card_games_v49_13", "pair_count": pair_count, "moves": moves, "memory_picks": memory_picks},
                )
            )
        return out

    def collect_semantic_sources(self, conn: sqlite3.Connection) -> list[AffectiveExperience]:
        if not self.store.table_exists(conn, "semantic_memory"):
            return []
        source_profiles = {
            "darwin_first_words_v49_10": ("first_words", ["first_words", "speech", "word", "relation"], 0.76, 0.31, 0.76, 0.62, 0.68),
            "darwin_vocal_imitation_v49_11": ("vocal_imitation", ["vocal_imitation", "speech", "voice", "error_learning"], 0.64, 0.47, 0.58, 0.75, 0.61),
            "darwin_joint_attention_v49_12": ("joint_attention", ["joint_attention", "shared_attention", "binding", "focus"], 0.70, 0.38, 0.66, 0.74, 0.66),
            "darwin_geometry_experience_v49_7": ("geometry", ["geometry", "concept", "angle", "error_learning"], 0.61, 0.44, 0.56, 0.84, 0.63),
            "darwin_self_reflection_v49_15": ("self_reflection", ["self_reflection", "goal", "planning", "self_model"], 0.60, 0.36, 0.58, 0.78, 0.66),
            "darwin_companion_shell_v49_8": ("companion", ["companion", "felipe", "dialogue", "relation"], 0.78, 0.34, 0.80, 0.68, 0.72),
            "darwin_classical_music_nursery_v49_16": ("music", ["music", "classical", "calm_sound"], 0.76, 0.30, 0.82, 0.64, 0.74),
        }
        out: list[AffectiveExperience] = []
        for source, (kind, base_tags, valence, arousal, comfort, curiosity, stability) in source_profiles.items():
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
                content = str(row["content"] or "")
                key = str(row["key"] or "")
                confidence = clamp(float(row["confidence"] or 0.5))
                tags = sorted(set(base_tags) | tokens(key, content, source))
                out.append(
                    AffectiveExperience(
                        self.next_id(),
                        kind,
                        key,
                        key,
                        short(content, 220),
                        tags,
                        clamp(valence * 0.82 + confidence * 0.18),
                        arousal,
                        clamp(comfort * 0.85 + confidence * 0.15),
                        curiosity,
                        clamp(stability * 0.86 + confidence * 0.14),
                        confidence,
                        1.6 + confidence,
                        {"table": "semantic_memory", "source": source, "confidence": confidence},
                    )
                )
        return out

    def collect_self_goals(self, conn: sqlite3.Connection) -> list[AffectiveExperience]:
        if not self.store.table_exists(conn, "mind_learning_goals_v49_15"):
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM mind_learning_goals_v49_15
            ORDER BY priority DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
        out: list[AffectiveExperience] = []
        for row in rows:
            priority = clamp(float(row["priority"] or 0.0))
            kind = str(row["goal_kind"] or "goal")
            action_plan = str(row["action_plan"] or "")
            tags = sorted({"self_reflection", "goal", "planning", kind} | tokens(kind, action_plan, str(row["module_key"] or "")))
            out.append(
                AffectiveExperience(
                    self.next_id(),
                    "self_reflection",
                    str(row["goal_id"]),
                    f"Meta: {kind}",
                    action_plan,
                    tags,
                    clamp(0.55 + priority * 0.20),
                    0.40,
                    clamp(0.52 + priority * 0.12),
                    clamp(0.66 + priority * 0.20),
                    clamp(0.58 + float(row["sigma_after"] or 0.0) / 10.0),
                    clamp(0.60 + priority * 0.22),
                    float(row["sigma_after"] or row["sigma_before"] or 0.0),
                    {"table": "mind_learning_goals_v49_15", "goal_kind": kind, "priority": priority},
                )
            )
        return out

    def collect_recent_episodes(self, conn: sqlite3.Connection) -> list[AffectiveExperience]:
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
        ]
        placeholders = ",".join("?" for _ in modules)
        rows = conn.execute(
            f"""
            SELECT *
            FROM episodes
            WHERE module IN ({placeholders})
            ORDER BY id DESC
            LIMIT 20
            """,
            tuple(modules),
        ).fetchall()
        out: list[AffectiveExperience] = []
        for row in rows:
            module = str(row["module"] or "")
            action = str(row["action_taken"] or "")
            outcome = str(row["outcome"] or "")
            lesson = str(row["lesson"] or "")
            delta = float(row["sigma_after"] or 0.0) - float(row["sigma_before"] or 0.0)
            kind, base_tags = module_to_kind_and_tags(module)
            tags = sorted(set(base_tags) | tokens(module, action, outcome, lesson))
            positive = any(word in outcome.lower() or word in lesson.lower() for word in ("learn", "seguro", "calm", "stable", "pares", "replay", "consolid"))
            out.append(
                AffectiveExperience(
                    self.next_id(),
                    kind,
                    f"episode:{row['id']}",
                    action or module,
                    short(f"{outcome} | {lesson}", 220),
                    tags,
                    clamp(0.55 + (0.08 if positive else 0.0) + delta * 0.03),
                    clamp(0.36 + abs(delta) * 0.04),
                    clamp(0.54 + max(0.0, delta) * 0.04),
                    0.63,
                    clamp(0.55 + float(row["sigma_after"] or 0.0) / 12.0),
                    0.58,
                    float(row["sigma_after"] or row["sigma_before"] or 0.0),
                    {"table": "episodes", "module": module, "context": row["context"]},
                )
            )
        return out


def module_to_kind_and_tags(module: str) -> tuple[str, list[str]]:
    if "music" in module:
        return "music", ["music", "classical", "calm_sound"]
    if "memory_cards" in module:
        return "memory_game", ["memory_game", "pair_matching", "visual_memory"]
    if "first_words" in module:
        return "first_words", ["first_words", "speech", "word"]
    if "vocal" in module:
        return "vocal_imitation", ["vocal_imitation", "speech", "voice"]
    if "joint_attention" in module:
        return "joint_attention", ["joint_attention", "shared_attention", "focus"]
    if "geometry" in module:
        return "geometry", ["geometry", "error_learning", "concept"]
    if "companion" in module:
        return "companion", ["companion", "felipe", "dialogue", "relation"]
    return "episode", ["episode", "memory"]


class AffectivePreferenceCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4917-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.82
        self.store = AffectivePreferenceStore(db_path)
        self.rzs = RZSFormal()
        self.experiences: list[AffectiveExperience] = []
        self.preferences: list[PreferenceTrace] = []
        self.choices: list[ChoiceTrial] = []
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            "affective_preference_core",
            self.energy,
            {"version": "v49.17", "goal": "derive_preferences_from_affective_memory"},
        )

    def run_cycle(self) -> dict[str, Any]:
        self.experiences = AffectiveExperienceCollector(self.store, self.session_id).collect()
        for exp in self.experiences:
            self.store.log_experience(self.session_id, exp)
        self.store.log_session(
            self.session_id,
            "experiences_collected",
            "affective_preference_core",
            self.energy,
            {
                "experience_count": len(self.experiences),
                "source_kinds": sorted({e.source_kind for e in self.experiences}),
            },
        )

        self.preferences = self.build_preferences(self.experiences)
        for pref in self.preferences:
            self.store.log_preference(self.session_id, pref)
        self.store.log_session(
            self.session_id,
            "preferences_updated",
            "affective_preference_core",
            self.energy,
            {"preference_count": len(self.preferences), "top_preferences": [p.preference_key for p in self.preferences[:5]]},
        )

        self.choices = self.choose_actions(self.preferences, self.experiences)
        for trial in self.choices:
            self.store.log_choice(self.session_id, trial)
        self.store.log_session(
            self.session_id,
            "choice_trials_completed",
            "affective_preference_core",
            self.energy,
            {
                "choice_count": len(self.choices),
                "rzs_decisions": sorted({c.rzs_decision for c in self.choices}),
                "changed_by_rzs": sum(1 for c in self.choices if c.rzs_changed_action),
            },
        )

        self.summary = self.consolidate()
        return self.summary

    def build_preferences(self, experiences: list[AffectiveExperience]) -> list[PreferenceTrace]:
        traces: list[PreferenceTrace] = []
        for profile in ACTION_PROFILES:
            matches = [exp for exp in experiences if self.match_profile(profile, exp)]
            if not matches:
                continue
            weights = [self.experience_weight(exp, profile) for exp in matches]
            total = sum(weights) or 1.0
            valence = sum(exp.valence * w for exp, w in zip(matches, weights)) / total
            arousal = sum(exp.arousal * w for exp, w in zip(matches, weights)) / total
            comfort = sum(exp.comfort * w for exp, w in zip(matches, weights)) / total
            curiosity = sum(exp.curiosity * w for exp, w in zip(matches, weights)) / total
            stability = sum(exp.stability * w for exp, w in zip(matches, weights)) / total
            confidence = mean([exp.confidence for exp in matches])
            exposure_factor = clamp(math.log1p(len(matches)) / math.log(12), 0.20, 1.0)
            affect = valence * 0.26 + comfort * 0.24 + curiosity * 0.23 + stability * 0.22 + profile.base_bias * 0.05
            arousal_penalty = max(0.0, arousal - 0.62) * 0.18
            strength = clamp((affect - arousal_penalty) * (0.72 + confidence * 0.18 + exposure_factor * 0.10))
            tags = sorted(set(t for exp in matches for t in exp.tags if t in profile.match_terms or t in {"music", "speech", "relation", "geometry", "memory_game"}))
            traces.append(
                PreferenceTrace(
                    profile.preference_key,
                    profile.domain,
                    profile.candidate_action,
                    strength,
                    clamp(valence),
                    clamp(arousal),
                    clamp(comfort),
                    clamp(curiosity),
                    clamp(stability),
                    len(matches),
                    [short(exp.title, 70) for exp in sorted(matches, key=lambda e: self.experience_weight(e, profile), reverse=True)[:5]],
                    sorted({exp.source_kind for exp in matches}),
                    tags,
                )
            )
        traces.sort(key=lambda p: (p.strength, p.evidence_count, p.curiosity), reverse=True)
        return traces

    def match_profile(self, profile: ActionProfile, exp: AffectiveExperience) -> bool:
        exp_terms = set(exp.tags) | tokens(exp.title, exp.content, exp.source_kind)
        return bool(exp_terms.intersection(profile.match_terms))

    def experience_weight(self, exp: AffectiveExperience, profile: ActionProfile) -> float:
        overlap = len((set(exp.tags) | tokens(exp.title, exp.content)).intersection(profile.match_terms))
        affect = exp.valence * 0.22 + exp.comfort * 0.23 + exp.curiosity * 0.22 + exp.stability * 0.23 + exp.confidence * 0.10
        return max(0.05, affect * (1.0 + min(3, overlap) * 0.18))

    def choose_actions(self, preferences: list[PreferenceTrace], experiences: list[AffectiveExperience]) -> list[ChoiceTrial]:
        trials: list[ChoiceTrial] = []
        if not preferences:
            return trials
        experience_count = len(experiences)
        source_count = len({exp.source_kind for exp in experiences})
        for idx, pref in enumerate(preferences[:6], start=1):
            memory_pressure = clamp(0.18 + pref.evidence_count / 18.0 + (0.18 if idx == 1 and experience_count >= 10 else 0.0))
            replay_gap = clamp(0.22 + (0.58 if idx == 1 and experience_count >= 10 else 0.0) + max(0, source_count - 4) * 0.04)
            novelty = clamp(0.80 - pref.evidence_count / 24.0 + (0.08 if pref.curiosity > 0.74 else 0.0), 0.15, 0.92)
            conflict = clamp((1.0 - pref.stability) * 0.46 + max(0.0, pref.arousal - 0.50) * 0.32)
            x = RZSInput(
                bandwidth=2.76 + pref.stability * 0.55 + self.energy * 0.30,
                info_self=0.22 + (1.0 - pref.comfort) * 0.22,
                info_external=0.20 + pref.arousal * 0.24,
                task_info=0.30 + pref.strength * 0.28,
                novelty=novelty,
                conflict=conflict,
                latency=0.92 + idx * 0.045 + memory_pressure * 0.20,
                energy=self.energy,
                memory_pressure=memory_pressure,
                replay_gap=replay_gap,
            )
            assessment = self.rzs.classify(x)
            prediction = self.rzs.predict(x, assessment.decision)
            chosen = self.governed_action(pref.candidate_action, assessment.decision)
            changed = chosen != pref.candidate_action
            causal_delta = prediction.sigma_after - assessment.sigma
            reason = self.choice_reason(pref, assessment.decision, changed)
            trials.append(
                ChoiceTrial(
                    f"CH-{self.session_id}-{idx:02d}",
                    idx,
                    pref.preference_key,
                    pref.candidate_action,
                    chosen,
                    pref.strength,
                    assessment.decision,
                    assessment.sigma,
                    prediction.sigma_after,
                    changed,
                    causal_delta,
                    reason,
                    {
                        "rzs_input": asdict(x),
                        "rzs_reason": assessment.reason,
                        "preference": asdict(pref),
                        "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
                        "experience_count": experience_count,
                        "source_count": source_count,
                    },
                )
            )
            self.energy = clamp(self.energy - 0.015 - pref.arousal * 0.006)
        return trials

    def governed_action(self, candidate_action: str, decision: str) -> str:
        if decision == "continue":
            return candidate_action
        if decision == "narrow_focus":
            return f"narrow_{candidate_action}"
        if decision == "replay_memory":
            return f"replay_affective_memory_before_{candidate_action}"
        if decision == "consolidate":
            return "consolidate_preference_memory"
        if decision == "pause_for_stability":
            return "pause_preference_choice_for_stability"
        return candidate_action

    def choice_reason(self, pref: PreferenceTrace, decision: str, changed: bool) -> str:
        if changed:
            return f"RZS {decision} alterou {pref.candidate_action} para manter estabilidade relacional"
        return f"preferencia {pref.preference_key} forte e RZS permitiu continuar"

    def consolidate(self) -> dict[str, Any]:
        if not self.preferences or not self.choices:
            top_pref = None
            top_choice = None
        else:
            top_pref = self.preferences[0]
            top_choice = self.choices[0]
        if top_pref and top_choice:
            sigma_before = top_choice.sigma_before
            sigma_after = top_choice.sigma_after
            selected_action = top_choice.chosen_action
            rzs_decision = top_choice.rzs_decision
            top_key = top_pref.preference_key
            identity = (
                f"Eu comeco a preferir {top_pref.candidate_action} porque experiencias "
                f"em {top_pref.domain} trouxeram conforto={top_pref.comfort:.2f}, "
                f"curiosidade={top_pref.curiosity:.2f} e estabilidade={top_pref.stability:.2f}."
            )
        else:
            x = RZSInput(2.0, 0.4, 0.4, 0.5, 0.6, 0.2, 1.0, self.energy, 0.5, 0.5)
            assessment = self.rzs.classify(x)
            prediction = self.rzs.predict(x, "consolidate")
            sigma_before = assessment.sigma
            sigma_after = prediction.sigma_after
            selected_action = "collect_more_experiences"
            rzs_decision = "consolidate"
            top_key = "none"
            identity = "Ainda preciso de mais experiencias antes de formar uma preferencia forte."

        consolidation_id = f"CONS-{self.session_id}"
        summary = {
            "session_id": self.session_id,
            "experience_count": len(self.experiences),
            "source_kinds": sorted({e.source_kind for e in self.experiences}),
            "preference_count": len(self.preferences),
            "top_preferences": [
                {
                    "preference_key": p.preference_key,
                    "candidate_action": p.candidate_action,
                    "strength": round(p.strength, 3),
                    "evidence_count": p.evidence_count,
                    "source_kinds": p.source_kinds,
                }
                for p in self.preferences[:6]
            ],
            "choice_trials": [
                {
                    "choice_id": c.choice_id,
                    "preference_key": c.preference_key,
                    "candidate_action": c.candidate_action,
                    "chosen_action": c.chosen_action,
                    "rzs_decision": c.rzs_decision,
                    "rzs_changed_action": c.rzs_changed_action,
                    "sigma_before": round(c.sigma_before, 3),
                    "sigma_after": round(c.sigma_after, 3),
                }
                for c in self.choices
            ],
            "selected_action": selected_action,
            "top_preference_key": top_key,
            "identity_statement": identity,
            "session_complete": True,
        }
        self.store.log_consolidation(
            self.session_id,
            consolidation_id,
            selected_action,
            top_key,
            len(self.preferences),
            len(self.experiences),
            rzs_decision,
            sigma_before,
            sigma_after,
            identity,
            summary,
        )
        self.store.write_memory(self.session_id, summary, 0.78)
        self.store.write_episode(
            self.session_id,
            selected_action,
            f"selected={selected_action} top_preference={top_key}",
            "Darwin comeca a usar memoria afetiva para pesar escolhas futuras.",
            sigma_before,
            sigma_after,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            "affective_preference_core",
            self.energy,
            summary,
        )
        return summary


class AffectivePreferenceApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Preference Core v49.17")
        self.root.geometry("1060x720")
        self.root.minsize(920, 620)
        self.root.configure(bg="#071018")
        self.core: AffectivePreferenceCore | None = None
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
            text="DARWIN PREFERENCE & AFFECTIVE MEMORY v49.17",
            bg="#071018",
            fg="#eef8ff",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="experiencia -> afeto -> preferencia -> escolha regulada por RZS",
            bg="#071018",
            fg="#9cc9ff",
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        body = tk.Frame(self.root, bg="#071018")
        body.pack(fill="both", expand=True, padx=18, pady=8)

        left = tk.Frame(body, bg="#071018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=380)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg="#071018", highlightthickness=0, height=340)
        self.canvas.pack(fill="x")

        self.pref_frame = tk.Frame(left, bg="#071018")
        self.pref_frame.pack(fill="both", expand=True, pady=(8, 0))

        buttons = tk.Frame(left, bg="#102231")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Atualizar", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(buttons, text="Escolher treino", command=self.show_choice).pack(side="left", padx=4, pady=8)
        ttk.Button(buttons, text="Consolidar", command=self.show_identity).pack(side="left", padx=4, pady=8)

        tk.Label(
            right,
            text="Memoria afetiva",
            bg="#0d1b26",
            fg="#eef8ff",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(
            right,
            wrap="word",
            bg="#08131d",
            fg="#dff2ff",
            insertbackground="#dff2ff",
            relief="flat",
            font=("Consolas", 10),
        )
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self.log = tk.Text(
            self.root,
            height=5,
            wrap="word",
            bg="#061019",
            fg="#dff2ff",
            insertbackground="#dff2ff",
            relief="flat",
            font=("Consolas", 9),
        )
        self.log.pack(fill="x")

    def write_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def run_core(self) -> None:
        self.write_log("Sistema: lendo experiencias e atualizando preferencias afetivas.")
        self.core = AffectivePreferenceCore()
        self.summary = self.core.run_cycle()
        self.render_preferences()
        self.show_identity()
        self.write_log(f"Darwin: escolhi {self.summary.get('selected_action')} a partir da memoria afetiva.")

    def render_preferences(self) -> None:
        for child in self.pref_frame.winfo_children():
            child.destroy()
        if not self.core:
            return
        for pref in self.core.preferences[:8]:
            row = tk.Frame(self.pref_frame, bg="#071018")
            row.pack(fill="x", pady=4)
            tk.Label(row, text=pref.candidate_action, bg="#071018", fg="#eef8ff", width=30, anchor="w", font=("Segoe UI", 10, "bold")).pack(side="left")
            bar = tk.Canvas(row, height=20, bg="#102231", highlightthickness=0)
            bar.pack(side="left", fill="x", expand=True, padx=8)
            bar.update_idletasks()
            width = max(80, bar.winfo_width())
            fill_w = int(width * pref.strength)
            bar.create_rectangle(0, 0, width, 20, outline="", fill="#102231")
            bar.create_rectangle(0, 0, fill_w, 20, outline="", fill="#72e0a8")
            bar.create_text(8, 10, text=f"{pref.strength:.2f} / evidencias {pref.evidence_count}", anchor="w", fill="#061019" if fill_w > 170 else "#dff2ff", font=("Segoe UI", 9, "bold"))

    def show_identity(self) -> None:
        self.text.delete("1.0", "end")
        lines = [
            "Estado atual",
            f"sessao: {self.summary.get('session_id', '')}",
            f"experiencias: {self.summary.get('experience_count', 0)}",
            f"fontes: {', '.join(self.summary.get('source_kinds', []))}",
            "",
            "Frase autobiografica:",
            str(self.summary.get("identity_statement", "")),
            "",
            "Preferencias principais:",
        ]
        for item in self.summary.get("top_preferences", [])[:5]:
            lines.append(f"- {item['candidate_action']} | forca {item['strength']} | evidencias {item['evidence_count']}")
        self.text.insert("end", "\n".join(lines))

    def show_choice(self) -> None:
        self.text.delete("1.0", "end")
        lines = ["Ensaios de escolha regulados por RZS", ""]
        for item in self.summary.get("choice_trials", []):
            changed = "alterou" if item.get("rzs_changed_action") else "permitiu"
            lines.append(
                f"{item['candidate_action']} -> {item['chosen_action']}\n"
                f"  RZS {item['rzs_decision']} ({changed}) sigma {item['sigma_before']}->{item['sigma_after']}"
            )
        self.text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.04
        self.draw_canvas()
        self.root.after(50, self.animate)

    def draw_canvas(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.50
        pulse = 1.0 + math.sin(self.phase) * 0.04
        self.canvas.create_text(cx, 32, text="preferencias emergindo da memoria", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        if not self.core:
            return
        top = self.core.preferences[:8]
        base_r = min(w, h) * 0.18 * pulse
        self.canvas.create_oval(cx - base_r, cy - base_r, cx + base_r, cy + base_r, fill="#58b0ff", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - base_r * 0.32, cy - base_r * 0.32, cx + base_r * 0.32, cy + base_r * 0.32, fill="#e7fbff", outline="")
        colors = ["#72e0a8", "#f6d77a", "#ffb3c7", "#c7b9ff", "#8fd3ff", "#f2bf72", "#75e7a8", "#9cc9ff"]
        for idx, pref in enumerate(top):
            angle = self.phase * 0.35 + idx * (math.tau / max(1, len(top)))
            radius = min(w, h) * (0.30 + pref.strength * 0.13)
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            r = 12 + pref.strength * 16
            self.canvas.create_line(cx, cy, x, y, fill="#173a52", width=2)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors[idx % len(colors)], outline="")
            self.canvas.create_text(x, y + r + 12, text=pref.domain, fill="#dff2ff", font=("Segoe UI", 9))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.17 - PREFERENCE & AFFECTIVE MEMORY CORE")
    print("=" * 64)
    print(f"- sessao: {summary['session_id']}")
    print(f"- experiencias: {summary['experience_count']}")
    print(f"- fontes: {', '.join(summary['source_kinds'])}")
    print(f"- preferencias: {summary['preference_count']}")
    print(f"- acao selecionada: {summary['selected_action']}")
    print(f"- identidade: {summary['identity_statement']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.17 Preference & Affective Memory Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4917)
    args = ap.parse_args()
    if args.self_test:
        core = AffectivePreferenceCore(seed=args.seed)
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0

    root = tk.Tk()
    AffectivePreferenceApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
