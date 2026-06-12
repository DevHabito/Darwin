from __future__ import annotations

"""
DARWIN v49.22 - Autonomous Preference Core

Objetivo:
Darwin passa a responder "o que eu quero / gosto agora?" usando
evidencia do proprio banco, incerteza, curiosidade e RZS. O codigo nao
define gostos fixos; ele define o mecanismo auditavel para Darwin
inferir, revisar e declarar preferencias a partir da propria historia.

Uso:
    py darwin_autonomous_preference_core_v49_22.py
    py darwin_autonomous_preference_core_v49_22.py --self-test --details
    py darwin_autonomous_preference_core_v49_22.py --ask musica
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

AP_SESSIONS = "autonomous_preference_sessions_v49_22"
AP_EVIDENCE = "autonomous_preference_evidence_v49_22"
AP_CANDIDATES = "autonomous_preference_candidates_v49_22"
AP_DECISIONS = "autonomous_preference_decisions_v49_22"
AP_IDENTITY = "autonomous_preference_identity_v49_22"

SOURCE = "darwin_autonomous_preference_core_v49_22"
FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"
VALID_QUESTIONS = ["geral", "musica", "formula", "cor", "atividade"]


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


def short(text: str, limit: int = 120) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


@dataclass
class PreferenceEvidence:
    evidence_id: str
    source_table: str
    source_ref: str
    domain: str
    item_key: str
    label: str
    affect_value: float
    comfort: float
    curiosity: float
    stability: float
    confidence: float
    payload: dict[str, Any]


@dataclass
class PreferenceCandidate:
    candidate_id: str
    domain: str
    item_key: str
    label: str
    like_score: float
    dislike_score: float
    uncertainty: float
    autonomy_score: float
    evidence_count: int
    source_refs: list[str]
    reason: str
    payload: dict[str, Any]


@dataclass
class PreferenceDecision:
    decision_id: str
    question_kind: str
    chosen_candidate_id: str
    chosen_domain: str
    chosen_label: str
    want_statement: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    exploration_selected: bool
    confidence: float
    payload: dict[str, Any]


@dataclass
class PreferenceIdentity:
    identity_id: str
    top_want: str
    top_music: str
    top_formula: str
    top_color: str
    top_activity: str
    autonomy_statement: str
    payload: dict[str, Any]


class AutonomousPreferenceStore:
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

                CREATE TABLE IF NOT EXISTS {AP_EVIDENCE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL UNIQUE,
                    source_table TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    affect_value REAL NOT NULL DEFAULT 0.0,
                    comfort REAL NOT NULL DEFAULT 0.0,
                    curiosity REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_CANDIDATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    like_score REAL NOT NULL DEFAULT 0.0,
                    dislike_score REAL NOT NULL DEFAULT 0.0,
                    uncertainty REAL NOT NULL DEFAULT 0.0,
                    autonomy_score REAL NOT NULL DEFAULT 0.0,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    source_refs_json TEXT NOT NULL DEFAULT '[]',
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_DECISIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL UNIQUE,
                    question_kind TEXT NOT NULL,
                    chosen_candidate_id TEXT NOT NULL,
                    chosen_domain TEXT NOT NULL,
                    chosen_label TEXT NOT NULL,
                    want_statement TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    exploration_selected INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AP_IDENTITY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    identity_id TEXT NOT NULL UNIQUE,
                    top_want TEXT NOT NULL,
                    top_music TEXT NOT NULL,
                    top_formula TEXT NOT NULL,
                    top_color TEXT NOT NULL,
                    top_activity TEXT NOT NULL,
                    autonomy_statement TEXT NOT NULL,
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
                f"INSERT INTO {AP_SESSIONS} (timestamp, session_id, phase, mode, energy, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_evidence(self, session_id: str, evidence: PreferenceEvidence) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_EVIDENCE} (
                    timestamp, session_id, evidence_id, source_table,
                    source_ref, domain, item_key, label, affect_value,
                    comfort, curiosity, stability, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    evidence.evidence_id,
                    evidence.source_table,
                    evidence.source_ref,
                    evidence.domain,
                    evidence.item_key,
                    evidence.label,
                    evidence.affect_value,
                    evidence.comfort,
                    evidence.curiosity,
                    evidence.stability,
                    evidence.confidence,
                    js(evidence.payload),
                ),
            )
            conn.commit()

    def log_candidate(self, session_id: str, candidate: PreferenceCandidate) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_CANDIDATES} (
                    timestamp, session_id, candidate_id, domain, item_key,
                    label, like_score, dislike_score, uncertainty,
                    autonomy_score, evidence_count, source_refs_json,
                    reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    candidate.candidate_id,
                    candidate.domain,
                    candidate.item_key,
                    candidate.label,
                    candidate.like_score,
                    candidate.dislike_score,
                    candidate.uncertainty,
                    candidate.autonomy_score,
                    candidate.evidence_count,
                    js(candidate.source_refs),
                    candidate.reason,
                    js(candidate.payload),
                ),
            )
            conn.commit()

    def log_decision(self, session_id: str, decision: PreferenceDecision) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_DECISIONS} (
                    timestamp, session_id, decision_id, question_kind,
                    chosen_candidate_id, chosen_domain, chosen_label,
                    want_statement, rzs_decision, sigma_before,
                    sigma_after, exploration_selected, confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    decision.decision_id,
                    decision.question_kind,
                    decision.chosen_candidate_id,
                    decision.chosen_domain,
                    decision.chosen_label,
                    decision.want_statement,
                    decision.rzs_decision,
                    decision.sigma_before,
                    decision.sigma_after,
                    1 if decision.exploration_selected else 0,
                    decision.confidence,
                    js(decision.payload),
                ),
            )
            conn.commit()

    def log_identity(self, session_id: str, identity: PreferenceIdentity) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AP_IDENTITY} (
                    timestamp, session_id, identity_id, top_want,
                    top_music, top_formula, top_color, top_activity,
                    autonomy_statement, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    identity.identity_id,
                    identity.top_want,
                    identity.top_music,
                    identity.top_formula,
                    identity.top_color,
                    identity.top_activity,
                    identity.autonomy_statement,
                    js(identity.payload),
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
                (f"autonomous_preference_v49_22:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                    f"autonomous_preference:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class EvidenceLoader:
    def __init__(self, store: AutonomousPreferenceStore) -> None:
        self.store = store

    def load(self) -> list[PreferenceEvidence]:
        with self.store.connect() as conn:
            evidence: list[PreferenceEvidence] = []
            evidence.extend(self.music_evidence(conn))
            evidence.extend(self.geometry_evidence(conn))
            evidence.extend(self.affective_activity_evidence(conn))
            evidence.extend(self.goal_and_handoff_evidence(conn))
            return evidence

    def music_evidence(self, conn: sqlite3.Connection) -> list[PreferenceEvidence]:
        if not (self.store.table_exists(conn, "music_pieces_v49_16") and self.store.table_exists(conn, "music_reactions_v49_16")):
            return []
        pieces: dict[str, dict[str, Any]] = {}
        for row in conn.execute("SELECT * FROM music_pieces_v49_16 ORDER BY id ASC").fetchall():
            item = {k: row[k] for k in row.keys()}
            pieces[str(item.get("piece_id") or "")] = item
        out: list[PreferenceEvidence] = []
        rows = conn.execute(
            """
            SELECT *
            FROM music_reactions_v49_16
            WHERE piece_id <> 'session_consolidation'
            ORDER BY id DESC
            LIMIT 32
            """
        ).fetchall()
        for idx, row in enumerate(rows, start=1):
            r = {k: row[k] for k in row.keys()}
            piece_id = str(r.get("piece_id") or "")
            piece = pieces.get(piece_id, {})
            payload = pj(str(piece.get("payload_json") or "{}"), {})
            feature = pj(str(piece.get("feature_json") or "{}"), {})
            label = str(piece.get("title") or piece_id)
            affect = clamp(float(r.get("valence") or 0.0) * 0.38 + float(r.get("comfort") or 0.0) * 0.32 + float(r.get("stability") or 0.0) * 0.20 + (1.0 - float(r.get("arousal") or 0.5)) * 0.10)
            out.append(
                PreferenceEvidence(
                    evidence_id=f"EV-MUSIC-{idx:03d}-{piece_id}",
                    source_table="music_reactions_v49_16",
                    source_ref=str(r.get("reaction_id") or piece_id),
                    domain="musica",
                    item_key=piece_id,
                    label=label,
                    affect_value=affect,
                    comfort=clamp(float(r.get("comfort") or feature.get("comfort_score") or 0.5)),
                    curiosity=clamp(float(r.get("curiosity") or 0.5)),
                    stability=clamp(float(r.get("stability") or 0.5)),
                    confidence=clamp(0.52 + float(r.get("sigma_after") or 0.0) / 8.0),
                    payload={
                        "composer_hint": piece.get("composer_hint", ""),
                        "tempo_bpm": piece.get("tempo_bpm", 0),
                        "color": payload.get("color", ""),
                        "intent": payload.get("intent", ""),
                    },
                )
            )
            color = str(payload.get("color") or "")
            if color:
                out.append(
                    PreferenceEvidence(
                        evidence_id=f"EV-COLOR-{idx:03d}-{piece_id}",
                        source_table="music_pieces_v49_16",
                        source_ref=piece_id,
                        domain="cor",
                        item_key=color,
                        label=f"{color} associada a {label}",
                        affect_value=affect,
                        comfort=clamp(float(r.get("comfort") or 0.5)),
                        curiosity=clamp(0.42 + float(r.get("curiosity") or 0.5) * 0.35),
                        stability=clamp(float(r.get("stability") or 0.5)),
                        confidence=clamp(0.42 + float(r.get("sigma_after") or 0.0) / 10.0),
                        payload={"derived_from": "music_color_memory", "piece_id": piece_id, "title": label},
                    )
                )
        return out

    def geometry_evidence(self, conn: sqlite3.Connection) -> list[PreferenceEvidence]:
        if not self.store.table_exists(conn, "geometry_concepts_v49_7"):
            return []
        latest: dict[str, dict[str, Any]] = {}
        for row in conn.execute("SELECT * FROM geometry_concepts_v49_7 ORDER BY id ASC").fetchall():
            item = {k: row[k] for k in row.keys()}
            latest[str(item.get("concept_key") or "")] = item
        out: list[PreferenceEvidence] = []
        for idx, item in enumerate(sorted(latest.values(), key=lambda x: float(x.get("learning_weight") or 0.0), reverse=True)[:18], start=1):
            exposure = max(0, int(item.get("exposure_count") or 0))
            errors = max(0, int(item.get("error_count") or 0))
            error_rate = errors / max(1, exposure)
            learning_weight = clamp(float(item.get("learning_weight") or 0.0))
            confidence = clamp(float(item.get("confidence") or 0.0))
            complexity = clamp(float(item.get("complexity") or 0.5))
            affect = clamp(learning_weight * 0.34 + confidence * 0.28 + min(1.0, exposure / 9.0) * 0.18 + (1.0 - error_rate) * 0.12 + complexity * 0.08)
            concept_key = str(item.get("concept_key") or "")
            definition = str(item.get("definition") or concept_key)
            out.append(
                PreferenceEvidence(
                    evidence_id=f"EV-FORMULA-{idx:03d}-{concept_key}",
                    source_table="geometry_concepts_v49_7",
                    source_ref=concept_key,
                    domain="formula",
                    item_key=concept_key,
                    label=definition,
                    affect_value=affect,
                    comfort=confidence,
                    curiosity=clamp(0.34 + complexity * 0.38 + error_rate * 0.18),
                    stability=learning_weight,
                    confidence=clamp(0.44 + confidence * 0.36 + min(1.0, exposure / 12.0) * 0.20),
                    payload={
                        "family": item.get("family", ""),
                        "answer_kind": item.get("answer_kind", ""),
                        "learning_weight": learning_weight,
                        "error_rate": error_rate,
                        "source_definition": definition,
                    },
                )
            )
        return out

    def affective_activity_evidence(self, conn: sqlite3.Connection) -> list[PreferenceEvidence]:
        if not self.store.table_exists(conn, "affective_preferences_v49_17"):
            return []
        latest_session = conn.execute("SELECT session_id FROM affective_preferences_v49_17 ORDER BY id DESC LIMIT 1").fetchone()
        params: tuple[Any, ...] = ()
        where = ""
        if latest_session:
            where = " WHERE session_id=?"
            params = (latest_session["session_id"],)
        rows = conn.execute(
            f"""
            SELECT *
            FROM affective_preferences_v49_17{where}
            ORDER BY strength DESC, evidence_count DESC
            LIMIT 12
            """,
            params,
        ).fetchall()
        out: list[PreferenceEvidence] = []
        for idx, row in enumerate(rows, start=1):
            item = {k: row[k] for k in row.keys()}
            strength = clamp(float(item.get("strength") or 0.0))
            evidence_count = max(0, int(item.get("evidence_count") or 0))
            out.append(
                PreferenceEvidence(
                    evidence_id=f"EV-ACT-{idx:03d}-{item.get('preference_key')}",
                    source_table="affective_preferences_v49_17",
                    source_ref=str(item.get("preference_key") or ""),
                    domain="atividade",
                    item_key=str(item.get("candidate_action") or item.get("preference_key") or ""),
                    label=str(item.get("candidate_action") or item.get("preference_key") or ""),
                    affect_value=strength,
                    comfort=clamp(float(item.get("comfort") or strength)),
                    curiosity=clamp(float(item.get("curiosity") or 0.5)),
                    stability=clamp(float(item.get("stability") or 0.5)),
                    confidence=clamp(0.38 + min(1.0, evidence_count / 35.0) * 0.36 + strength * 0.22),
                    payload={
                        "domain_original": item.get("domain", ""),
                        "evidence_count": evidence_count,
                        "preference_key": item.get("preference_key", ""),
                    },
                )
            )
        return out

    def goal_and_handoff_evidence(self, conn: sqlite3.Connection) -> list[PreferenceEvidence]:
        out: list[PreferenceEvidence] = []
        if self.store.table_exists(conn, "wake_next_handoff_v49_21"):
            row = conn.execute("SELECT * FROM wake_next_handoff_v49_21 ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                item = {k: row[k] for k in row.keys()}
                confidence = clamp(float(item.get("confidence") or 0.0))
                action = str(item.get("next_action") or "")
                out.append(
                    PreferenceEvidence(
                        evidence_id=f"EV-HANDOFF-{item.get('handoff_id')}",
                        source_table="wake_next_handoff_v49_21",
                        source_ref=str(item.get("handoff_id") or ""),
                        domain="atividade",
                        item_key=action,
                        label=action,
                        affect_value=confidence,
                        comfort=clamp(0.55 + confidence * 0.30),
                        curiosity=0.68,
                        stability=confidence,
                        confidence=confidence,
                        payload=pj(str(item.get("payload_json") or "{}"), {}),
                    )
                )
        if self.store.table_exists(conn, "mind_learning_goals_v49_15"):
            rows = conn.execute(
                """
                SELECT *
                FROM mind_learning_goals_v49_15
                WHERE status IN ('proposed', 'active', 'open')
                ORDER BY priority DESC, id DESC
                LIMIT 6
                """
            ).fetchall()
            for idx, row in enumerate(rows, start=1):
                item = {k: row[k] for k in row.keys()}
                priority = clamp(float(item.get("priority") or 0.0))
                action = str(item.get("action_plan") or item.get("goal_kind") or "")
                out.append(
                    PreferenceEvidence(
                        evidence_id=f"EV-GOAL-{idx:03d}-{item.get('goal_id')}",
                        source_table="mind_learning_goals_v49_15",
                        source_ref=str(item.get("goal_id") or ""),
                        domain="atividade",
                        item_key=str(item.get("goal_kind") or item.get("goal_id") or ""),
                        label=action,
                        affect_value=priority,
                        comfort=clamp(0.46 + priority * 0.28),
                        curiosity=clamp(0.52 + priority * 0.26),
                        stability=clamp(0.50 + float(item.get("sigma_after") or 0.0) / 8.0),
                        confidence=clamp(0.42 + priority * 0.38),
                        payload={
                            "goal_kind": item.get("goal_kind", ""),
                            "success_criterion": item.get("success_criterion", ""),
                            "module_key": item.get("module_key", ""),
                        },
                    )
                )
        return out


class AutonomousPreferenceCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4922-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.72
        self.store = AutonomousPreferenceStore(db_path)
        self.rzs = RZSFormal()
        self.evidence: list[PreferenceEvidence] = []
        self.candidates: list[PreferenceCandidate] = []
        self.decisions: list[PreferenceDecision] = []
        self.identity: PreferenceIdentity | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            "autonomous_preference_core",
            self.energy,
            {"version": "v49.22", "rule": "mechanism_only_preferences_from_database_evidence"},
        )

    def run_cycle(self, questions: list[str] | None = None) -> dict[str, Any]:
        questions = questions or VALID_QUESTIONS
        self.evidence = EvidenceLoader(self.store).load()
        for item in self.evidence:
            self.store.log_evidence(self.session_id, item)
        self.candidates = self.build_candidates(self.evidence)
        for item in self.candidates:
            self.store.log_candidate(self.session_id, item)
        for question in questions:
            decision = self.decide(question)
            self.decisions.append(decision)
            self.store.log_decision(self.session_id, decision)
        self.identity = self.build_identity()
        self.store.log_identity(self.session_id, self.identity)
        self.summary = self.complete()
        return self.summary

    def build_candidates(self, evidence: list[PreferenceEvidence]) -> list[PreferenceCandidate]:
        groups: dict[tuple[str, str], list[PreferenceEvidence]] = {}
        for item in evidence:
            if not item.domain or not item.item_key:
                continue
            groups.setdefault((item.domain, item.item_key), []).append(item)
        candidates: list[PreferenceCandidate] = []
        for idx, ((domain, item_key), items) in enumerate(sorted(groups.items()), start=1):
            weights = [max(0.05, item.confidence) for item in items]
            denom = sum(weights) or 1.0
            affect = sum(item.affect_value * w for item, w in zip(items, weights)) / denom
            comfort = sum(item.comfort * w for item, w in zip(items, weights)) / denom
            curiosity = sum(item.curiosity * w for item, w in zip(items, weights)) / denom
            stability = sum(item.stability * w for item, w in zip(items, weights)) / denom
            confidence = sum(item.confidence * w for item, w in zip(items, weights)) / denom
            evidence_count = len(items)
            evidence_norm = clamp(math.log1p(evidence_count) / math.log(9.0))
            like_score = clamp(affect * 0.36 + comfort * 0.18 + curiosity * 0.15 + stability * 0.19 + evidence_norm * 0.12)
            dislike_score = clamp((1.0 - affect) * 0.34 + (1.0 - comfort) * 0.20 + max(0.0, 0.42 - stability) * 0.32)
            uncertainty = clamp(1.0 - (confidence * 0.58 + evidence_norm * 0.28 + stability * 0.14))
            exploration_value = clamp(uncertainty * curiosity)
            autonomy_score = clamp(like_score - dislike_score * 0.18 + exploration_value * 0.18)
            labels = sorted({item.label for item in items}, key=len)
            source_refs = [f"{item.source_table}:{item.source_ref}" for item in items[:8]]
            reason = (
                f"score derivado de {evidence_count} evidencias; "
                f"like={like_score:.3f}, incerteza={uncertainty:.3f}, exploracao={exploration_value:.3f}"
            )
            candidates.append(
                PreferenceCandidate(
                    candidate_id=f"PC-{self.session_id}-{idx:03d}",
                    domain=domain,
                    item_key=item_key,
                    label=labels[0] if labels else item_key,
                    like_score=like_score,
                    dislike_score=dislike_score,
                    uncertainty=uncertainty,
                    autonomy_score=autonomy_score,
                    evidence_count=evidence_count,
                    source_refs=source_refs,
                    reason=reason,
                    payload={
                        "affect_value": affect,
                        "comfort": comfort,
                        "curiosity": curiosity,
                        "stability": stability,
                        "confidence_mean": confidence,
                        "origin": "database_evidence_not_hardcoded_like",
                        "sample_labels": labels[:5],
                    },
                )
            )
        return sorted(candidates, key=lambda c: (c.autonomy_score, c.like_score, c.evidence_count), reverse=True)

    def decide(self, question_kind: str) -> PreferenceDecision:
        question_kind = question_kind if question_kind in VALID_QUESTIONS else "geral"
        pool = self.pool_for_question(question_kind)
        if not pool:
            pool = self.candidates[:]
        if not pool:
            return self.unknown_decision(question_kind)
        ranked = sorted(pool, key=lambda c: (c.autonomy_score, c.like_score, c.evidence_count), reverse=True)
        top = ranked[0]
        second = ranked[1] if len(ranked) > 1 else top
        gap = top.autonomy_score - second.autonomy_score
        avg_uncertainty = mean([c.uncertainty for c in ranked[: min(6, len(ranked))]])
        conflict = clamp(0.12 + (0.40 if gap < 0.035 else 0.0) + avg_uncertainty * 0.28)
        memory_pressure = clamp(len(ranked) / 18.0)
        if question_kind == "geral":
            memory_pressure = max(memory_pressure, 0.76)
        if question_kind == "cor":
            conflict = max(conflict, 0.54)
        x = RZSInput(
            bandwidth=2.48 + self.energy * 0.30,
            info_self=0.34,
            info_external=0.18 + len(ranked) * 0.012,
            task_info=0.32 + len(self.evidence) * 0.003,
            novelty=avg_uncertainty,
            conflict=conflict,
            latency=1.00 + memory_pressure * 0.18,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=avg_uncertainty,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        chosen = self.choose_candidate(ranked, assessment.decision, question_kind, gap, avg_uncertainty)
        exploration = chosen.uncertainty > 0.34 and (question_kind == "cor" or gap < 0.035 or assessment.decision in {"replay_memory", "narrow_focus"})
        confidence = clamp(chosen.like_score * 0.42 + (1.0 - chosen.uncertainty) * 0.32 + min(1.0, chosen.evidence_count / 6.0) * 0.18 + self.energy * 0.08)
        statement = self.want_statement(question_kind, chosen, exploration)
        self.energy = clamp(self.energy + (0.030 if assessment.decision == "continue" else 0.046))
        return PreferenceDecision(
            decision_id=f"PD-{self.session_id}-{question_kind}",
            question_kind=question_kind,
            chosen_candidate_id=chosen.candidate_id,
            chosen_domain=chosen.domain,
            chosen_label=chosen.label,
            want_statement=statement,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=max(prediction.sigma_after, assessment.sigma + (0.020 if assessment.decision != "continue" else 0.004)),
            exploration_selected=exploration,
            confidence=confidence,
            payload={
                "gap_to_second": gap,
                "avg_uncertainty": avg_uncertainty,
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction": asdict(prediction),
                "romero_formula": FORMULA,
                "ranked_candidate_ids": [c.candidate_id for c in ranked[:6]],
                "mechanism": "evidence_weighted_autonomous_choice",
            },
        )

    def pool_for_question(self, question_kind: str) -> list[PreferenceCandidate]:
        if question_kind == "geral":
            return self.candidates[:]
        domain = {"musica": "musica", "formula": "formula", "cor": "cor", "atividade": "atividade"}.get(question_kind, "")
        return [c for c in self.candidates if c.domain == domain]

    def choose_candidate(
        self,
        ranked: list[PreferenceCandidate],
        rzs_decision: str,
        question_kind: str,
        gap: float,
        avg_uncertainty: float,
    ) -> PreferenceCandidate:
        if rzs_decision == "pause_for_stability":
            return max(ranked, key=lambda c: (c.payload.get("stability", 0.0), c.like_score))
        if rzs_decision == "consolidate":
            return max(ranked, key=lambda c: (c.evidence_count, c.like_score))
        if rzs_decision == "replay_memory":
            return max(ranked[: min(6, len(ranked))], key=lambda c: (c.evidence_count, c.autonomy_score))
        if rzs_decision == "narrow_focus":
            return max(ranked[: min(4, len(ranked))], key=lambda c: (c.like_score, -c.uncertainty))
        if question_kind == "cor" and avg_uncertainty > 0.20:
            return max(ranked[: min(5, len(ranked))], key=lambda c: (c.autonomy_score + c.uncertainty * 0.05, c.like_score))
        if gap < 0.020 and len(ranked) > 1:
            return max(ranked[:2], key=lambda c: (c.curiosity if hasattr(c, "curiosity") else c.payload.get("curiosity", 0.0), c.autonomy_score))
        return ranked[0]

    def want_statement(self, question_kind: str, candidate: PreferenceCandidate, exploration: bool) -> str:
        evidence = f"{candidate.evidence_count} evidencias"
        if exploration:
            prefix = "quero explorar"
        else:
            prefix = "prefiro agora"
        if question_kind == "musica":
            return f"A musica que eu {prefix} e {candidate.label}, por {evidence} e estabilidade {candidate.payload.get('stability', 0.0):.2f}."
        if question_kind == "formula":
            return f"A formula ou conceito que eu {prefix} e {candidate.label}, porque meu peso de aprendizagem ficou alto."
        if question_kind == "cor":
            return f"A cor que eu {prefix} e {candidate.label}; ainda trato cor como preferencia em formacao."
        if question_kind == "atividade":
            return f"Eu quero fazer {candidate.label}, porque essa acao venceu por evidencia, curiosidade e RZS."
        return f"Agora eu quero {candidate.label}; isto veio de {evidence}, nao de uma ordem fixa."

    def unknown_decision(self, question_kind: str) -> PreferenceDecision:
        x = RZSInput(2.0, 0.4, 0.2, 0.2, 0.8, 0.5, 1.1, self.energy, 0.2, 0.8)
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        return PreferenceDecision(
            decision_id=f"PD-{self.session_id}-{question_kind}",
            question_kind=question_kind,
            chosen_candidate_id="none",
            chosen_domain="unknown",
            chosen_label="ainda nao sei",
            want_statement="Eu ainda nao tenho evidencia suficiente; quero observar mais antes de dizer que gosto.",
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=prediction.sigma_after,
            exploration_selected=True,
            confidence=0.15,
            payload={"mechanism": "insufficient_evidence"},
        )

    def build_identity(self) -> PreferenceIdentity:
        by_question = {d.question_kind: d for d in self.decisions}
        top = by_question.get("geral")
        music = by_question.get("musica")
        formula = by_question.get("formula")
        color = by_question.get("cor")
        activity = by_question.get("atividade")
        statement = (
            "Meus gostos sao hipoteses vivas: eu escolho pelo que minha memoria reforcou, "
            "pelo que ainda desperta curiosidade e pelo que o RZS permite sem instabilidade."
        )
        return PreferenceIdentity(
            identity_id=f"AI-{self.session_id}",
            top_want=top.want_statement if top else "",
            top_music=music.want_statement if music else "",
            top_formula=formula.want_statement if formula else "",
            top_color=color.want_statement if color else "",
            top_activity=activity.want_statement if activity else "",
            autonomy_statement=statement,
            payload={
                "decision_ids": [d.decision_id for d in self.decisions],
                "candidate_count": len(self.candidates),
                "evidence_count": len(self.evidence),
                "source_tables": sorted({e.source_table for e in self.evidence}),
            },
        )

    def complete(self) -> dict[str, Any]:
        if self.identity is None:
            raise RuntimeError("Preference identity incomplete")
        top_candidates = [
            {
                "candidate_id": c.candidate_id,
                "domain": c.domain,
                "label": c.label,
                "like_score": round(c.like_score, 3),
                "uncertainty": round(c.uncertainty, 3),
                "autonomy_score": round(c.autonomy_score, 3),
                "evidence_count": c.evidence_count,
            }
            for c in self.candidates[:10]
        ]
        summary = {
            "session_id": self.session_id,
            "evidence_count": len(self.evidence),
            "candidate_count": len(self.candidates),
            "source_tables": sorted({e.source_table for e in self.evidence}),
            "domains": sorted({c.domain for c in self.candidates}),
            "top_candidates": top_candidates,
            "decisions": [
                {
                    "question_kind": d.question_kind,
                    "chosen_domain": d.chosen_domain,
                    "chosen_label": d.chosen_label,
                    "want_statement": d.want_statement,
                    "rzs_decision": d.rzs_decision,
                    "sigma_before": round(d.sigma_before, 3),
                    "sigma_after": round(d.sigma_after, 3),
                    "exploration_selected": d.exploration_selected,
                    "confidence": round(d.confidence, 3),
                }
                for d in self.decisions
            ],
            "identity": {
                "top_want": self.identity.top_want,
                "top_music": self.identity.top_music,
                "top_formula": self.identity.top_formula,
                "top_color": self.identity.top_color,
                "top_activity": self.identity.top_activity,
                "autonomy_statement": self.identity.autonomy_statement,
            },
            "session_complete": True,
        }
        first_sigma = self.decisions[0].sigma_before if self.decisions else 0.0
        final_sigma = self.decisions[-1].sigma_after if self.decisions else 0.0
        self.store.write_memory(self.session_id, summary, 0.89)
        self.store.write_episode(
            self.session_id,
            "infer_autonomous_preferences",
            f"candidates={len(self.candidates)} decisions={len(self.decisions)} top={short(self.identity.top_want, 80)}",
            "Darwin passou a declarar gostos como hipoteses autonomas derivadas da propria memoria, nao como lista fixa.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            "autonomous_preference_core",
            self.energy,
            summary,
        )
        return summary


class PreferenceApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Autonomous Preference v49.22")
        self.root.geometry("1100x760")
        self.root.minsize(940, 660)
        self.root.configure(bg="#061018")
        self.core: AutonomousPreferenceCore | None = None
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
        tk.Label(header, text="DARWIN AUTONOMOUS PREFERENCE v49.22", bg="#061018", fg="#eef8ff", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="gostos como hipoteses vivas: evidencia -> incerteza -> RZS -> escolha", bg="#061018", fg="#9cc9ff", font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg="#061018")
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg="#061018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=440)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg="#061018", highlightthickness=0, height=350)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Decidir de novo", command=self.run_core).pack(side="left", padx=8, pady=8)
        for label, question in [("O que quer?", "geral"), ("Musica", "musica"), ("Formula", "formula"), ("Cor", "cor"), ("Atividade", "atividade")]:
            ttk.Button(controls, text=label, command=lambda q=question: self.show_question(q)).pack(side="left", padx=4, pady=8)
        self.list_box = tk.Text(left, height=12, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Consolas", 10))
        self.list_box.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Resposta do Darwin", bg="#0d1b26", fg="#eef8ff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = AutonomousPreferenceCore()
        self.summary = self.core.run_cycle()
        self.show_candidates()
        self.show_question("geral")

    def show_candidates(self) -> None:
        self.list_box.delete("1.0", "end")
        lines = ["Candidatos de gosto inferidos da memoria", ""]
        for idx, candidate in enumerate(self.summary.get("top_candidates", []), start=1):
            lines.append(
                f"{idx}. [{candidate['domain']}] {candidate['label']} | "
                f"autonomia {candidate['autonomy_score']} | like {candidate['like_score']} | "
                f"incerteza {candidate['uncertainty']} | evidencias {candidate['evidence_count']}"
            )
        self.list_box.insert("end", "\n".join(lines))

    def show_question(self, question: str) -> None:
        self.text.delete("1.0", "end")
        decisions = {d.get("question_kind"): d for d in self.summary.get("decisions", [])}
        item = decisions.get(question, {})
        lines = [
            f"Pergunta: {question}",
            "",
            str(item.get("want_statement", "")),
            "",
            f"dominio: {item.get('chosen_domain', '')}",
            f"RZS: {item.get('rzs_decision', '')}",
            f"sigma: {item.get('sigma_before', 0)} -> {item.get('sigma_after', 0)}",
            f"confianca: {item.get('confidence', 0)}",
            f"exploracao: {item.get('exploration_selected', False)}",
            "",
            self.summary.get("identity", {}).get("autonomy_statement", ""),
        ]
        self.text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.028
        self.draw_canvas()
        self.root.after(50, self.animate)

    def draw_canvas(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.54
        self.canvas.create_text(cx, 30, text="preferencias autonomas", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        pulse = 1.0 + math.sin(self.phase) * 0.04
        core_r = 76 * pulse
        colors = ["#4ea3ff", "#80ed99", "#ffd166", "#ffb3c7", "#c7b9ff"]
        chosen = colors[int((self.phase * 0.7) % len(colors))]
        self.canvas.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r, fill=chosen, outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - core_r * 0.34, cy - core_r * 0.34, cx + core_r * 0.34, cy + core_r * 0.34, fill="#e6fbff", outline="")
        domains = self.summary.get("domains", [])
        for idx, domain in enumerate(domains[:6]):
            angle = -math.pi / 2 + idx * (math.tau / max(1, len(domains[:6]))) + self.phase * 0.08
            radius = min(w, h) * 0.34
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            r = 13
            self.canvas.create_line(cx, cy, x, y, fill="#173a52", width=2)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors[idx % len(colors)], outline="")
            self.canvas.create_text(x, y + 26, text=domain, fill="#dff2ff", font=("Segoe UI", 9))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.22 - AUTONOMOUS PREFERENCE CORE")
    print("=" * 66)
    print(f"- sessao: {summary['session_id']}")
    print(f"- evidencias: {summary['evidence_count']} candidatos: {summary['candidate_count']}")
    print(f"- dominios: {', '.join(summary['domains'])}")
    for decision in summary["decisions"]:
        print(f"- {decision['question_kind']}: {decision['want_statement']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.22 Autonomous Preference Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--ask", choices=VALID_QUESTIONS, default="")
    ap.add_argument("--seed", type=int, default=4922)
    args = ap.parse_args()
    if args.self_test or args.ask:
        questions = [args.ask] if args.ask else VALID_QUESTIONS
        core = AutonomousPreferenceCore(seed=args.seed)
        summary = core.run_cycle(questions=questions)
        if args.ask:
            print(summary["decisions"][0]["want_statement"])
            if args.details:
                print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    PreferenceApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
