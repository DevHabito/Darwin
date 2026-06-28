from __future__ import annotations

"""
DARWIN v49.38 - escolha autonoma de atividades

O convite humano abre uma deliberacao. Ele nao determina a atividade.
As opcoes competem por evidencias afetivas, curiosidade, aprendizagem,
energia, novidade, preferencias consolidadas e regulacao RZS.
"""

import argparse
import json
import math
import os
import random
import sqlite3
import subprocess
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darwin_activity_outcome_learning_v49_39 import (
    ActivityOutcomeLearningCore,
    ObservedActivityOutcome,
)
from darwin_relational_world_model_v49_40 import RelationalWorldModel
from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"
SESSIONS = "activity_choice_sessions_v49_38"
CANDIDATES = "activity_choice_candidates_v49_38"
DECISIONS = "activity_choice_decisions_v49_38"
DISPATCHES = "activity_choice_dispatches_v49_38"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


@dataclass(frozen=True)
class ActivitySpec:
    key: str
    label: str
    script_name: str
    energy_target: float
    cognitive_cost: float
    calmness: float
    learning_potential: float


ACTIVITIES = (
    ActivitySpec("memory_cards", "jogo da memoria", "darwin_memory_cards_v49_13.py", 0.70, 0.66, 0.48, 0.88),
    ActivitySpec("classical_music", "ouvir musica classica", "darwin_classical_music_nursery_v49_16.py", 0.48, 0.24, 0.92, 0.62),
    ActivitySpec("child_story", "ler uma historia", "darwin_child_story_nursery_v49_29.py", 0.52, 0.34, 0.84, 0.72),
    ActivitySpec("formula_sketch", "desenhar formulas", "darwin_formula_sketchbook_v49_28.py", 0.78, 0.76, 0.40, 0.96),
    ActivitySpec("conversation", "continuar conversando", "", 0.58, 0.42, 0.76, 0.68),
    ActivitySpec("rest", "descansar", "", 0.16, 0.04, 1.00, 0.20),
)

INVITATION_PATTERNS = (
    "quer jogar",
    "quer brincar",
    "quer fazer",
    "quer ouvir",
    "quer ler",
    "quer desenhar",
    "o que voce quer",
    "qual atividade",
    "escolha uma atividade",
    "vamos fazer alguma coisa",
    "esta a fim de",
    "ta a fim de",
)


@dataclass
class ActivityCandidate:
    key: str
    label: str
    script_name: str
    evidence_count: int
    affect: float
    curiosity: float
    stability: float
    familiarity: float
    novelty: float
    learning_gain: float
    energy_fit: float
    preference_prior: float
    world_prediction: float
    world_confidence: float
    repetition_penalty: float
    utility: float
    regulated_utility: float = 0.0
    source_tables: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivityChoiceReply:
    session_id: str
    decision_id: str
    selected_key: str
    selected_label: str
    response_text: str
    reason: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    energy: float
    launched: bool
    dispatch_status: str
    candidates: list[ActivityCandidate]


class ActivityChoiceStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = Path(db_path)
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=12.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def table_exists(conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    invitation_text TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    energy REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {CANDIDATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    activity_key TEXT NOT NULL,
                    rank_index INTEGER NOT NULL,
                    utility REAL NOT NULL,
                    regulated_utility REAL NOT NULL,
                    components_json TEXT NOT NULL,
                    source_tables_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {DECISIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL UNIQUE,
                    scenario_kind TEXT NOT NULL,
                    selected_key TEXT NOT NULL,
                    selected_label TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    energy REAL NOT NULL,
                    reason TEXT NOT NULL,
                    invitation_forced_choice INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {DISPATCHES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    activity_key TEXT NOT NULL,
                    script_name TEXT NOT NULL DEFAULT '',
                    live_requested INTEGER NOT NULL DEFAULT 0,
                    safety_allowed INTEGER NOT NULL DEFAULT 0,
                    launched INTEGER NOT NULL DEFAULT 0,
                    process_id INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE INDEX IF NOT EXISTS idx_activity_choice_decision
                    ON {CANDIDATES}(decision_id, rank_index);
                """
            )

    def current_state(self) -> dict[str, float]:
        result = {"energy": 0.72, "latency": 1.0, "sigma": 2.0}
        with self.connect() as conn:
            if not self.table_exists(conn, "current_state"):
                return result
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
            if row:
                columns = set(row.keys())
                for key in result:
                    if key in columns:
                        result[key] = safe_float(row[key], result[key])
        return result

    def recent_choices(self, limit: int = 5) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT selected_key FROM {DECISIONS}
                WHERE scenario_kind='live'
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["selected_key"]) for row in rows]

    def _count(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        if not self.table_exists(conn, table):
            return 0
        sql = f"SELECT COUNT(*) AS n FROM {table}" + (f" WHERE {where}" if where else "")
        row = conn.execute(sql, params).fetchone()
        return int(row["n"]) if row else 0

    def evidence(self) -> dict[str, dict[str, Any]]:
        base = {
            spec.key: {
                "count": 0,
                "affect": 0.50,
                "curiosity": 0.50,
                "stability": spec.calmness,
                "sources": [],
                "details": {},
            }
            for spec in ACTIVITIES
        }
        with self.connect() as conn:
            if self.table_exists(conn, "music_reactions_v49_16"):
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n, AVG(valence) AS valence, AVG(curiosity) AS curiosity,
                           AVG(stability) AS stability, AVG(comfort) AS comfort
                    FROM music_reactions_v49_16
                    """
                ).fetchone()
                n = int(row["n"] or 0)
                if n:
                    base["classical_music"].update(
                        count=n,
                        affect=clamp((safe_float(row["valence"]) + safe_float(row["comfort"])) / 2),
                        curiosity=clamp(row["curiosity"]),
                        stability=clamp(row["stability"]),
                        sources=["music_reactions_v49_16"],
                        details=dict(row),
                    )

            if self.table_exists(conn, "memory_card_moves_v49_13"):
                row = conn.execute(
                    "SELECT COUNT(*) AS n, AVG(matched) AS matched FROM memory_card_moves_v49_13"
                ).fetchone()
                n = int(row["n"] or 0)
                games = self._count(conn, "memory_card_games_v49_13")
                if n:
                    match_rate = clamp(row["matched"])
                    base["memory_cards"].update(
                        count=max(games, n),
                        affect=clamp(0.48 + match_rate * 0.34),
                        curiosity=clamp(0.62 + min(0.20, games * 0.02)),
                        stability=clamp(0.50 + match_rate * 0.32),
                        sources=["memory_card_moves_v49_13", "memory_card_games_v49_13"],
                        details={"moves": n, "games": games, "match_rate": match_rate},
                    )
            elif self.table_exists(conn, "memory_card_sessions_v49_13"):
                n = self._count(conn, "memory_card_sessions_v49_13")
                base["memory_cards"].update(
                    count=n,
                    affect=0.62,
                    curiosity=0.72,
                    stability=0.60,
                    sources=["memory_card_sessions_v49_13"],
                    details={"session_events": n},
                )

            if self.table_exists(conn, "story_nursery_sessions_v49_29"):
                row = conn.execute(
                    """
                    SELECT payload_json FROM story_nursery_sessions_v49_29
                    WHERE phase='session_complete' ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
                n = self._count(conn, "story_nursery_sessions_v49_29", "phase='session_complete'")
                payload = pj(row["payload_json"]) if row else {}
                base["child_story"].update(
                    count=n,
                    affect=clamp(payload.get("avg_comfort", 0.58)),
                    curiosity=clamp(payload.get("avg_curiosity", 0.62)),
                    stability=clamp(payload.get("avg_stability", 0.66)),
                    sources=["story_nursery_sessions_v49_29"],
                    details={
                        key: payload.get(key)
                        for key in (
                            "avg_comfort",
                            "avg_curiosity",
                            "avg_stability",
                            "exposure_count",
                            "story_count",
                            "top_focus",
                            "child_safe_storybook",
                        )
                    },
                )

            if self.table_exists(conn, "formula_sketch_sessions_v49_28"):
                row = conn.execute(
                    """
                    SELECT payload_json FROM formula_sketch_sessions_v49_28
                    WHERE phase='sketch_complete' ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
                n = self._count(conn, "formula_sketch_sessions_v49_28", "phase='sketch_complete'")
                payload = pj(row["payload_json"]) if row else {}
                attempts = max(1, int(payload.get("intentions", 0) or 0))
                corrections = int(payload.get("corrections", 0) or 0)
                fusions = int(payload.get("fusions", 0) or 0)
                base["formula_sketch"].update(
                    count=n,
                    affect=clamp(0.52 + corrections / attempts * 0.25),
                    curiosity=clamp(0.60 + min(0.28, fusions * 0.025)),
                    stability=clamp(0.48 + corrections / attempts * 0.22),
                    sources=["formula_sketch_sessions_v49_28"],
                    details={
                        key: payload.get(key)
                        for key in (
                            "intention_count",
                            "mistake_count",
                            "correction_count",
                            "fusion_count",
                            "last_focus",
                            "last_intention",
                            "last_rzs_decision",
                            "energy",
                        )
                    },
                )

            if self.table_exists(conn, "companion_dialogues_v49_8"):
                n = self._count(conn, "companion_dialogues_v49_8")
                affect = 0.62
                stability = 0.68
                if self.table_exists(conn, "companion_affect_state_v49_8"):
                    row = conn.execute(
                        """
                        SELECT AVG(valence) AS valence, AVG(stability) AS stability
                        FROM (SELECT valence, stability FROM companion_affect_state_v49_8
                              ORDER BY id DESC LIMIT 30)
                        """
                    ).fetchone()
                    affect = clamp(safe_float(row["valence"], 0.62))
                    stability = clamp(safe_float(row["stability"], 0.68))
                base["conversation"].update(
                    count=n,
                    affect=affect,
                    curiosity=0.67,
                    stability=stability,
                    sources=["companion_dialogues_v49_8"],
                    details={"dialogues": n},
                )

            if self.table_exists(conn, "sleep_sessions_v49_20"):
                n = self._count(conn, "sleep_sessions_v49_20", "phase='session_complete'")
                base["rest"].update(
                    count=n,
                    affect=0.70,
                    curiosity=0.28,
                    stability=0.96,
                    sources=["sleep_sessions_v49_20"],
                    details={"completed_sleep_sessions": n},
                )

            preferences: list[dict[str, Any]] = []
            if self.table_exists(conn, "affective_preferences_v49_17"):
                rows = conn.execute(
                    """
                    SELECT domain, candidate_action, strength, valence, comfort, curiosity,
                           stability, evidence_count, tags_json
                    FROM affective_preferences_v49_17 ORDER BY id DESC
                    """
                ).fetchall()
                preferences = [dict(row) for row in rows]
            base["_preferences"] = {"rows": preferences}
            learned_preferences: dict[str, dict[str, Any]] = {}
            if self.table_exists(conn, "activity_learned_preferences_v49_39"):
                rows = conn.execute(
                    """
                    SELECT activity_key, preference_estimate, evidence_count, confidence
                    FROM activity_learned_preferences_v49_39
                    """
                ).fetchall()
                learned_preferences = {
                    str(row["activity_key"]): dict(row)
                    for row in rows
                }
            base["_learned_preferences"] = learned_preferences
        return base

    def record(
        self,
        session_id: str,
        decision_id: str,
        scenario_kind: str,
        invitation: str,
        energy: float,
        candidates: list[ActivityCandidate],
        selected: ActivityCandidate,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
        reason: str,
    ) -> None:
        ranked = sorted(candidates, key=lambda item: item.regulated_utility, reverse=True)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SESSIONS}
                (timestamp, session_id, decision_id, scenario_kind, invitation_text, phase, energy, payload_json)
                VALUES (?, ?, ?, ?, ?, 'deliberation_complete', ?, ?)
                """,
                (now(), session_id, decision_id, scenario_kind, invitation, energy, js({"candidate_count": len(candidates)})),
            )
            for rank, candidate in enumerate(ranked, 1):
                components = {
                    key: value
                    for key, value in asdict(candidate).items()
                    if key not in {"source_tables", "evidence", "key", "label", "script_name"}
                }
                conn.execute(
                    f"""
                    INSERT INTO {CANDIDATES}
                    (timestamp, session_id, decision_id, scenario_kind, activity_key, rank_index,
                     utility, regulated_utility, components_json, source_tables_json, evidence_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(), session_id, decision_id, scenario_kind, candidate.key, rank,
                        candidate.utility, candidate.regulated_utility, js(components),
                        js(candidate.source_tables), js(candidate.evidence),
                    ),
                )
            conn.execute(
                f"""
                INSERT INTO {DECISIONS}
                (timestamp, session_id, decision_id, scenario_kind, selected_key, selected_label,
                 rzs_decision, sigma_before, sigma_after, energy, reason,
                 invitation_forced_choice, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    now(), session_id, decision_id, scenario_kind, selected.key, selected.label,
                    rzs_decision, sigma_before, sigma_after, energy, reason,
                    js({"winner_utility": selected.regulated_utility, "ranking": [item.key for item in ranked]}),
                ),
            )

    def record_dispatch(
        self,
        session_id: str,
        decision_id: str,
        candidate: ActivityCandidate,
        live_requested: bool,
        safety_allowed: bool,
        launched: bool,
        process_id: int,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {DISPATCHES}
                (timestamp, session_id, decision_id, activity_key, script_name, live_requested,
                 safety_allowed, launched, process_id, status, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, decision_id, candidate.key, candidate.script_name,
                    int(live_requested), int(safety_allowed), int(launched), process_id, status, js(payload),
                ),
            )


class AutonomousActivityChoiceCore:
    def __init__(self, db_path: Path = DB, seed: int = 4938) -> None:
        self.store = ActivityChoiceStore(db_path)
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.project_dir = self.store.db_path.resolve().parent.parent
        self.active_process: subprocess.Popen[Any] | None = None
        self.counter = 0
        self.outcome_learning = ActivityOutcomeLearningCore(self.store.db_path, seed=seed + 1)
        self.world_model = RelationalWorldModel(self.store.db_path, seed=seed + 2)
        self.world_model.refresh_historical()

    @staticmethod
    def is_invitation(text: str) -> bool:
        normalized = normalize(text)
        return any(pattern in normalized for pattern in INVITATION_PATTERNS)

    @staticmethod
    def _preference_prior(key: str, rows: list[dict[str, Any]]) -> tuple[float, list[str]]:
        keywords = {
            "memory_cards": ("memory", "memoria", "game", "jogo"),
            "classical_music": ("music", "musica", "audio", "melody", "melodia"),
            "child_story": ("story", "historia", "narrative", "narrativa"),
            "formula_sketch": ("formula", "geometry", "geometria", "draw", "desen"),
            "conversation": ("conversation", "conversa", "voice", "voz", "relation", "relacao"),
            "rest": ("rest", "descans", "sleep", "dorm", "calm", "calma"),
        }[key]
        weighted = []
        refs = []
        for row in rows:
            haystack = normalize(" ".join(str(row.get(name, "")) for name in ("domain", "candidate_action", "tags_json")))
            if any(word in haystack for word in keywords):
                evidence = max(1, int(row.get("evidence_count", 0) or 0))
                strength = clamp(row.get("strength", 0.0))
                weighted.append((strength, evidence))
                refs.append(str(row.get("candidate_action") or row.get("domain") or "preference"))
        if not weighted:
            return 0.50, []
        total = sum(evidence for _, evidence in weighted)
        return clamp(sum(strength * evidence for strength, evidence in weighted) / total), refs[:5]

    def build_candidates(
        self,
        energy: float,
        evidence: dict[str, dict[str, Any]],
        overrides: dict[str, dict[str, float]] | None = None,
        use_live_history: bool = True,
    ) -> list[ActivityCandidate]:
        overrides = overrides or {}
        recent = self.store.recent_choices() if use_live_history else []
        preference_rows = list(evidence.get("_preferences", {}).get("rows", []))
        learned_preferences = dict(evidence.get("_learned_preferences", {}))
        result: list[ActivityCandidate] = []
        for spec in ACTIVITIES:
            item = evidence[spec.key]
            count = int(item.get("count", 0) or 0)
            familiarity = clamp(math.log1p(count) / math.log(31.0))
            novelty = clamp(1.0 - familiarity * 0.72)
            learning_gain = clamp(spec.learning_potential * (0.62 + novelty * 0.38))
            energy_fit = clamp(1.0 - abs(energy - spec.energy_target))
            prior, preference_refs = self._preference_prior(spec.key, preference_rows)
            world = self.world_model.predict_activity(spec.key, energy)
            learned = dict(learned_preferences.get(spec.key, {}))
            learned_confidence = clamp(learned.get("confidence", 0.0))
            if learned:
                learned_weight = learned_confidence * 0.68
                prior = (
                    prior * (1.0 - learned_weight)
                    + clamp(learned.get("preference_estimate", 0.50)) * learned_weight
                )
            repetition = sum(1 for key in recent[:3] if key == spec.key) * 0.12
            values = {
                "affect": clamp(item.get("affect", 0.50)),
                "curiosity": clamp(item.get("curiosity", 0.50)),
                "stability": clamp(item.get("stability", spec.calmness)),
                "familiarity": familiarity,
                "novelty": novelty,
                "learning_gain": learning_gain,
                "energy_fit": energy_fit,
                "preference_prior": prior,
                "world_prediction": world.predicted_value,
                "world_confidence": world.confidence,
                "repetition_penalty": repetition,
            }
            for component, value in overrides.get(spec.key, {}).items():
                if component in values:
                    values[component] = clamp(value) if component != "repetition_penalty" else max(0.0, float(value))
            utility = (
                0.19 * values["affect"]
                + 0.14 * values["curiosity"]
                + 0.13 * values["stability"]
                + 0.15 * values["learning_gain"]
                + 0.14 * values["energy_fit"]
                + 0.09 * values["novelty"]
                + 0.11 * values["preference_prior"]
                + 0.04 * values["world_prediction"] * values["world_confidence"]
                - values["repetition_penalty"]
            )
            result.append(
                ActivityCandidate(
                    key=spec.key,
                    label=spec.label,
                    script_name=spec.script_name,
                    evidence_count=count,
                    utility=utility,
                    source_tables=list(item.get("sources", []))
                    + (["affective_preferences_v49_17"] if preference_refs else [])
                    + (["activity_learned_preferences_v49_39"] if learned else [])
                    + (["world_experiences_v49_40"] if world.contributors else []),
                    evidence={
                        **dict(item.get("details", {})),
                        "preference_refs": preference_refs,
                        "outcome_preference": learned,
                    },
                    **values,
                )
            )
        return result

    def _rzs_assess(self, energy: float, candidates: list[ActivityCandidate], latency: float) -> tuple[str, float, float]:
        ranked = sorted(candidates, key=lambda item: item.utility, reverse=True)
        gap = ranked[0].utility - ranked[1].utility
        uncertainty = clamp(1.0 - gap * 4.0)
        x = RZSInput(
            bandwidth=3.8 + energy * 1.1,
            info_self=0.42,
            info_external=0.46,
            task_info=0.66,
            novelty=clamp(sum(item.novelty for item in candidates) / len(candidates)),
            conflict=clamp(0.18 + uncertainty * 0.38),
            latency=max(0.45, latency),
            energy=energy,
            memory_pressure=clamp(0.74 - sum(item.familiarity for item in candidates) / len(candidates) * 0.45),
            replay_gap=clamp(0.62 - gap),
        )
        assessment = self.rzs.classify(x)
        after = self.rzs.sigma(self.rzs.apply_action_model(x, assessment.decision))
        return assessment.decision, assessment.sigma, after

    @staticmethod
    def _regulate(candidates: list[ActivityCandidate], decision: str) -> None:
        specs = {spec.key: spec for spec in ACTIVITIES}
        for candidate in candidates:
            spec = specs[candidate.key]
            adjustment = 0.0
            if decision == "pause_for_stability":
                adjustment = spec.calmness * 0.32 - spec.cognitive_cost * 0.30
            elif decision == "consolidate":
                adjustment = candidate.stability * 0.18 + candidate.familiarity * 0.14 - spec.cognitive_cost * 0.08
            elif decision == "replay_memory":
                adjustment = candidate.familiarity * 0.18 + candidate.stability * 0.08
            elif decision == "narrow_focus":
                adjustment = candidate.learning_gain * 0.08 - spec.cognitive_cost * 0.06
            candidate.regulated_utility = candidate.utility + adjustment

    @staticmethod
    def _reason(selected: ActivityCandidate, decision: str, energy: float) -> str:
        components = {
            "curiosidade": selected.curiosity,
            "aprendizagem": selected.learning_gain,
            "afinidade aprendida": selected.preference_prior,
            "bem-estar": (selected.affect + selected.stability) / 2,
            "encaixe com minha energia": selected.energy_fit,
            "novidade": selected.novelty,
        }
        strongest = sorted(components, key=components.get, reverse=True)[:2]
        regulation = {
            "pause_for_stability": "O RZS pediu baixa carga",
            "consolidate": "O RZS pediu consolidacao",
            "replay_memory": "O RZS favoreceu uma experiencia conhecida",
            "narrow_focus": "O RZS pediu um foco claro",
            "continue": "O RZS permitiu explorar",
        }[decision]
        return f"{regulation}; pesaram mais {strongest[0]} e {strongest[1]} (energia {energy:.2f})"

    def _dispatch(
        self,
        session_id: str,
        decision_id: str,
        candidate: ActivityCandidate,
        live: bool,
        rzs_decision: str,
    ) -> tuple[bool, str]:
        if not candidate.script_name:
            status = "internal_activity"
            self.store.record_dispatch(session_id, decision_id, candidate, live, True, False, 0, status, {})
            return False, status
        script = (self.project_dir / candidate.script_name).resolve()
        allowed_names = {spec.script_name for spec in ACTIVITIES if spec.script_name}
        safety_allowed = (
            candidate.script_name in allowed_names
            and script.parent == self.project_dir
            and script.is_file()
            and script.suffix.lower() == ".py"
        )
        if not live:
            status = "simulation_only"
            self.store.record_dispatch(
                session_id, decision_id, candidate, False, safety_allowed, False, 0, status,
                {"resolved_script": str(script)},
            )
            return False, status
        if not safety_allowed:
            status = "blocked_by_allowlist"
            self.store.record_dispatch(
                session_id, decision_id, candidate, True, False, False, 0, status,
                {"resolved_script": str(script)},
            )
            return False, status
        if self.active_process is not None and self.active_process.poll() is None:
            status = "another_activity_is_open"
            self.store.record_dispatch(
                session_id, decision_id, candidate, True, True, False, int(self.active_process.pid), status, {},
            )
            return False, status
        observation_id = self.outcome_learning.arm(
            decision_id,
            session_id,
            candidate.key,
            candidate.regulated_utility,
            rzs_decision,
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.active_process = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(self.project_dir),
                shell=False,
                creationflags=flags,
            )
            status = "launched"
            self.store.record_dispatch(
                session_id, decision_id, candidate, True, True, True, int(self.active_process.pid), status,
                {"resolved_script": str(script)},
            )
            return True, status
        except OSError as exc:
            self.outcome_learning.cancel(observation_id, str(exc))
            status = "launch_error"
            self.store.record_dispatch(
                session_id, decision_id, candidate, True, True, False, 0, status, {"error": str(exc)},
            )
            return False, status

    def deliberate(
        self,
        invitation: str,
        session_id: str,
        *,
        scenario_kind: str = "live",
        live: bool = False,
        energy_override: float | None = None,
        component_overrides: dict[str, dict[str, float]] | None = None,
        use_live_history: bool = True,
    ) -> ActivityChoiceReply:
        self.outcome_learning.poll_pending()
        self.counter += 1
        decision_id = f"act:{session_id}:{int(time.time() * 1000)}:{self.counter:03d}"
        state = self.store.current_state()
        energy = clamp(state["energy"] if energy_override is None else energy_override)
        candidates = self.build_candidates(energy, self.store.evidence(), component_overrides, use_live_history)
        rzs_decision, sigma_before, sigma_after = self._rzs_assess(energy, candidates, state["latency"])
        self._regulate(candidates, rzs_decision)
        selected = max(candidates, key=lambda item: (item.regulated_utility, item.key))
        reason = self._reason(selected, rzs_decision, energy)
        self.store.record(
            session_id, decision_id, scenario_kind, invitation, energy, candidates, selected,
            rzs_decision, sigma_before, sigma_after, reason,
        )
        launched, dispatch_status = self._dispatch(
            session_id, decision_id, selected, live, rzs_decision
        )
        if selected.key == "rest":
            text = f"Hoje eu prefiro descansar um pouco. {reason}."
        elif selected.key == "conversation":
            text = f"Eu escolhi continuar conversando com voce. {reason}. Sobre o que vamos conversar?"
        elif launched:
            text = f"Eu escolhi {selected.label}. {reason}. Vou abrir agora."
        elif dispatch_status == "another_activity_is_open":
            text = f"Eu escolhi {selected.label}. {reason}. Ja existe uma atividade aberta, entao vou esperar ela terminar."
        elif live:
            text = f"Eu escolhi {selected.label}. {reason}, mas nao consegui abrir a atividade com seguranca."
        else:
            text = f"Eu escolhi {selected.label}. {reason}."
        return ActivityChoiceReply(
            session_id=session_id,
            decision_id=decision_id,
            selected_key=selected.key,
            selected_label=selected.label,
            response_text=text,
            reason=reason,
            rzs_decision=rzs_decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
            energy=energy,
            launched=launched,
            dispatch_status=dispatch_status,
            candidates=candidates,
        )

    def poll_outcomes(self) -> list[ObservedActivityOutcome]:
        return self.outcome_learning.poll_pending()

    def is_outcome_question(self, text: str) -> bool:
        return self.outcome_learning.is_reflection_question(text)

    def outcome_reflection(self) -> tuple[str, dict[str, Any] | None]:
        return self.outcome_learning.latest_reflection()


def run_self_test(details: bool = False) -> dict[str, Any]:
    core = AutonomousActivityChoiceCore(seed=4938)
    session = f"V4938-{int(time.time())}-{core.rng.randrange(1000, 9999)}"
    invitation = "Darwin, voce quer jogar ou fazer alguma coisa?"
    baseline = core.deliberate(
        invitation, session, scenario_kind="self_test_baseline", live=False, use_live_history=False
    )
    low_energy = core.deliberate(
        invitation, session, scenario_kind="self_test_low_energy", live=False,
        energy_override=0.12, use_live_history=False,
    )
    preference = core.deliberate(
        invitation, session, scenario_kind="self_test_preference_intervention", live=False,
        component_overrides={
            "classical_music": {"preference_prior": 1.0},
        },
        use_live_history=False,
    )
    result = {
        "session_id": session,
        "baseline": baseline.selected_key,
        "low_energy": low_energy.selected_key,
        "preference_intervention": preference.selected_key,
        "all_simulated": all(item.dispatch_status in {"simulation_only", "internal_activity"} for item in (baseline, low_energy, preference)),
        "decisions": [
            {
                "scenario": name,
                "selected": reply.selected_key,
                "rzs": reply.rzs_decision,
                "sigma_before": reply.sigma_before,
                "sigma_after": reply.sigma_after,
                "ranking": [
                    candidate.key
                    for candidate in sorted(reply.candidates, key=lambda item: item.regulated_utility, reverse=True)
                ],
            }
            for name, reply in (
                ("baseline", baseline),
                ("low_energy", low_energy),
                ("preference_intervention", preference),
            )
        ],
    }
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"DARWIN v49.38 self-test: baseline={baseline.selected_key} "
            f"low_energy={low_energy.selected_key} preference={preference.selected_key}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.38 Autonomous Activity Choice")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result["all_simulated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
