from __future__ import annotations

"""
DARWIN v49.21 - Wake & Life Loop Core

Objetivo:
Depois do sono cognitivo v49.20, Darwin acorda no notebook, carrega o
plano de acordar, restaura identidade, cumpre o compromisso ativo e
deixa um handoff verificavel para o proximo ciclo de agencia/sono.

Uso:
    py darwin_wake_life_loop_v49_21.py
    py darwin_wake_life_loop_v49_21.py --self-test --details
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

WK_SESSIONS = "wake_sessions_v49_21"
WK_PHASES = "wake_phase_events_v49_21"
WK_RESOLUTIONS = "wake_commitment_resolutions_v49_21"
WK_LIFE_CYCLES = "wake_life_cycles_v49_21"
WK_HANDOFFS = "wake_next_handoff_v49_21"

SOURCE = "darwin_wake_life_loop_v49_21"

PHASES = [
    "wake_start",
    "load_sleep_plan",
    "restore_identity",
    "fulfill_commitment",
    "run_life_cycle",
    "evaluate_wake_state",
    "handoff_next_sleep",
]

VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}
FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"


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


@dataclass
class WakeContext:
    sleep_session_id: str
    wake_plan_id: str
    wake_next_action: str
    wake_trigger: str
    wake_confidence: float
    wake_summary: str
    wake_payload: dict[str, Any]
    consolidation_id: str
    consolidation_focus: str
    memory_delta: float
    stability_gain: float
    commitment_id: str
    intention_id: str
    commitment_text: str
    commitment_trigger: str
    commitment_confidence: float
    identity_session_id: str
    identity_statement: str
    continuity_score: float
    current_goal: str
    identity_next_action: str
    active_preference_key: str
    active_preference_strength: float
    primary_goal_id: str
    primary_goal_kind: str
    primary_goal_priority: float
    primary_goal_plan: str
    primary_goal_success: str
    recent_semantic: list[dict[str, Any]]


@dataclass
class WakePhase:
    phase_index: int
    phase: str
    focus_key: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    energy_before: float
    energy_after: float
    cognitive_action: str
    payload: dict[str, Any]


@dataclass
class CommitmentResolution:
    resolution_id: str
    source_commitment_id: str
    commitment_text: str
    reviewed_goal_id: str
    resolution_status: str
    fulfilled_score: float
    evidence: dict[str, Any]
    payload: dict[str, Any]


@dataclass
class LifeCycle:
    cycle_index: int
    cycle_key: str
    focus_key: str
    action_taken: str
    result_summary: str
    expected_effect: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    energy_after: float
    completed: bool
    payload: dict[str, Any]


@dataclass
class WakeHandoff:
    handoff_id: str
    source_wake_plan_id: str
    next_recommended_core: str
    next_action: str
    agency_ready: bool
    sleep_ready: bool
    confidence: float
    payload: dict[str, Any]


class WakeStore:
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
                CREATE TABLE IF NOT EXISTS {WK_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    source_sleep_session_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WK_PHASES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    energy_before REAL NOT NULL DEFAULT 0.0,
                    energy_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WK_RESOLUTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    resolution_id TEXT NOT NULL UNIQUE,
                    source_commitment_id TEXT NOT NULL,
                    commitment_text TEXT NOT NULL,
                    reviewed_goal_id TEXT NOT NULL,
                    resolution_status TEXT NOT NULL,
                    fulfilled_score REAL NOT NULL DEFAULT 0.0,
                    evidence_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WK_LIFE_CYCLES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cycle_index INTEGER NOT NULL,
                    cycle_key TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    expected_effect TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    energy_after REAL NOT NULL DEFAULT 0.0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WK_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    source_wake_plan_id TEXT NOT NULL,
                    next_recommended_core TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    agency_ready INTEGER NOT NULL DEFAULT 0,
                    sleep_ready INTEGER NOT NULL DEFAULT 0,
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

    def log_session(
        self,
        session_id: str,
        phase: str,
        mode: str,
        energy: float,
        source_sleep_session_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WK_SESSIONS} (
                    timestamp, session_id, phase, mode, energy,
                    source_sleep_session_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, energy, source_sleep_session_id, js(payload or {})),
            )
            conn.commit()

    def log_phase(self, session_id: str, phase: WakePhase) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WK_PHASES} (
                    timestamp, session_id, phase_index, phase, focus_key,
                    rzs_decision, sigma_before, sigma_after,
                    energy_before, energy_after, cognitive_action,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    phase.phase_index,
                    phase.phase,
                    phase.focus_key,
                    phase.rzs_decision,
                    phase.sigma_before,
                    phase.sigma_after,
                    phase.energy_before,
                    phase.energy_after,
                    phase.cognitive_action,
                    js(phase.payload),
                ),
            )
            conn.commit()

    def log_resolution(self, session_id: str, resolution: CommitmentResolution) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {WK_RESOLUTIONS} (
                    timestamp, session_id, resolution_id, source_commitment_id,
                    commitment_text, reviewed_goal_id, resolution_status,
                    fulfilled_score, evidence_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    resolution.resolution_id,
                    resolution.source_commitment_id,
                    resolution.commitment_text,
                    resolution.reviewed_goal_id,
                    resolution.resolution_status,
                    resolution.fulfilled_score,
                    js(resolution.evidence),
                    js(resolution.payload),
                ),
            )
            conn.commit()

    def log_life_cycle(self, session_id: str, cycle: LifeCycle) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WK_LIFE_CYCLES} (
                    timestamp, session_id, cycle_index, cycle_key,
                    focus_key, action_taken, result_summary,
                    expected_effect, rzs_decision, sigma_before,
                    sigma_after, energy_after, completed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    cycle.cycle_index,
                    cycle.cycle_key,
                    cycle.focus_key,
                    cycle.action_taken,
                    cycle.result_summary,
                    cycle.expected_effect,
                    cycle.rzs_decision,
                    cycle.sigma_before,
                    cycle.sigma_after,
                    cycle.energy_after,
                    1 if cycle.completed else 0,
                    js(cycle.payload),
                ),
            )
            conn.commit()

    def log_handoff(self, session_id: str, handoff: WakeHandoff) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {WK_HANDOFFS} (
                    timestamp, session_id, handoff_id, source_wake_plan_id,
                    next_recommended_core, next_action, agency_ready,
                    sleep_ready, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    handoff.handoff_id,
                    handoff.source_wake_plan_id,
                    handoff.next_recommended_core,
                    handoff.next_action,
                    1 if handoff.agency_ready else 0,
                    1 if handoff.sleep_ready else 0,
                    handoff.confidence,
                    js(handoff.payload),
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
                (f"wake_life_loop_v49_21:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                    f"wake_life_loop:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class WakeContextLoader:
    def __init__(self, store: WakeStore) -> None:
        self.store = store

    def latest_context(self) -> WakeContext:
        with self.store.connect() as conn:
            wake_plan = self.latest_row(conn, "sleep_wake_plans_v49_20")
            sleep_session_id = str(wake_plan.get("session_id") or "")
            consolidation = self.latest_row(conn, "sleep_consolidations_v49_20", "session_id=?", (sleep_session_id,))
            commitment = self.latest_commitment(conn)
            identity = self.latest_row(conn, "autobiography_identity_state_v49_18")
            goal = self.latest_goal(conn)
            semantic = self.recent_semantic(conn)

        wake_payload = pj(str(wake_plan.get("payload_json") or "{}"), {})
        commitment_payload = pj(str(commitment.get("payload_json") or "{}"), {})
        primary_goal_plan = str(goal.get("action_plan") or identity.get("current_goal") or "review_self_goals")
        return WakeContext(
            sleep_session_id=sleep_session_id,
            wake_plan_id=str(wake_plan.get("wake_plan_id") or ""),
            wake_next_action=str(wake_plan.get("next_action") or "wake_and_review_primary_goal"),
            wake_trigger=str(wake_plan.get("trigger") or "next_wake_or_user_continues"),
            wake_confidence=clamp(float(wake_plan.get("confidence") or 0.65)),
            wake_summary=str(wake_plan.get("plan_summary") or ""),
            wake_payload=wake_payload if isinstance(wake_payload, dict) else {},
            consolidation_id=str(consolidation.get("consolidation_id") or wake_payload.get("consolidation_id") or ""),
            consolidation_focus=str(consolidation.get("consolidated_focus") or wake_payload.get("active_preference_key") or ""),
            memory_delta=clamp(float(consolidation.get("memory_delta") or 0.10)),
            stability_gain=clamp(float(consolidation.get("stability_gain") or 0.10)),
            commitment_id=str(commitment.get("commitment_id") or ""),
            intention_id=str(commitment.get("intention_id") or ""),
            commitment_text=str(commitment.get("commitment_text") or wake_payload.get("commitment_text") or ""),
            commitment_trigger=str(commitment.get("next_trigger") or "next_wake_or_user_continues"),
            commitment_confidence=clamp(float(commitment.get("confidence") or commitment_payload.get("confidence") or 0.68)),
            identity_session_id=str(identity.get("session_id") or ""),
            identity_statement=str(identity.get("identity_statement") or ""),
            continuity_score=clamp(float(identity.get("continuity_score") or 0.50)),
            current_goal=str(identity.get("current_goal") or primary_goal_plan),
            identity_next_action=str(identity.get("next_action") or ""),
            active_preference_key=str(identity.get("active_preference_key") or wake_payload.get("active_preference_key") or "pref_self_reflection"),
            active_preference_strength=clamp(float(identity.get("active_preference_strength") or 0.50)),
            primary_goal_id=str(goal.get("goal_id") or "goal_review_self"),
            primary_goal_kind=str(goal.get("goal_kind") or "self_review"),
            primary_goal_priority=clamp(float(goal.get("priority") or 0.70)),
            primary_goal_plan=primary_goal_plan,
            primary_goal_success=str(goal.get("success_criterion") or "registrar revisao de meta principal com estabilidade relacional"),
            recent_semantic=semantic,
        )

    def latest_row(
        self,
        conn: sqlite3.Connection,
        table: str,
        where: str = "",
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        if not self.store.table_exists(conn, table):
            return {}
        suffix_sql = f" WHERE {where}" if where else ""
        row = conn.execute(f"SELECT * FROM {table}{suffix_sql} ORDER BY id DESC LIMIT 1", params).fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    def latest_commitment(self, conn: sqlite3.Connection) -> dict[str, Any]:
        if not self.store.table_exists(conn, "agency_commitments_v49_19"):
            return {}
        row = conn.execute(
            """
            SELECT *
            FROM agency_commitments_v49_19
            WHERE status IN ('active', 'pending', 'open')
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            row = conn.execute("SELECT * FROM agency_commitments_v49_19 ORDER BY id DESC LIMIT 1").fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    def latest_goal(self, conn: sqlite3.Connection) -> dict[str, Any]:
        if not self.store.table_exists(conn, "mind_learning_goals_v49_15"):
            return {}
        row = conn.execute(
            """
            SELECT *
            FROM mind_learning_goals_v49_15
            WHERE status IN ('proposed', 'active', 'open')
            ORDER BY priority DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            row = conn.execute("SELECT * FROM mind_learning_goals_v49_15 ORDER BY priority DESC, id DESC LIMIT 1").fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    def recent_semantic(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        if not self.store.table_exists(conn, "semantic_memory"):
            return []
        sources = [
            "darwin_sleep_consolidation_core_v49_20",
            "darwin_intention_agency_core_v49_19",
            "darwin_autobiographical_continuity_v49_18",
            "darwin_affective_preference_core_v49_17",
            "darwin_self_reflection_v49_15",
        ]
        placeholders = ",".join("?" for _ in sources)
        rows = conn.execute(
            f"""
            SELECT key, source, confidence, updated_at, content
            FROM semantic_memory
            WHERE source IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            tuple(sources),
        ).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]


class WakeLifeLoopCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4921-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.49
        self.store = WakeStore(db_path)
        self.rzs = RZSFormal()
        self.context = WakeContextLoader(self.store).latest_context()
        self.phases: list[WakePhase] = []
        self.life_cycles: list[LifeCycle] = []
        self.resolution: CommitmentResolution | None = None
        self.handoff: WakeHandoff | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            "wake_life_loop_core",
            self.energy,
            self.context.sleep_session_id,
            {
                "version": "v49.21",
                "goal": "wake_from_sleep_plan_fulfill_commitment_handoff",
                "source_wake_plan_id": self.context.wake_plan_id,
            },
        )

    def run_cycle(self) -> dict[str, Any]:
        sigma = self.phase_event(1, "wake_start", "wake_plan", "open_wake_window", 0.18, 0.04, 0.34, 0.30)
        sigma = self.phase_event(2, "load_sleep_plan", self.context.wake_plan_id, "load_v49_20_wake_plan", 0.14, 0.03, 0.28, 0.22, sigma)
        sigma = self.phase_event(3, "restore_identity", self.context.active_preference_key, "restore_autobiographical_identity", 0.22, 0.08, 0.74, 0.75, sigma)
        sigma = self.phase_event(4, "fulfill_commitment", self.context.primary_goal_id, "review_primary_goal_and_fulfill_commitment", 0.18, 0.06, 0.44, 0.22, sigma)
        self.resolution = self.resolve_commitment()
        self.store.log_resolution(self.session_id, self.resolution)
        sigma = self.phase_event(5, "run_life_cycle", self.context.current_goal, "run_internal_life_cycles", 0.24, 0.08, 0.42, 0.18, sigma)
        self.life_cycles = self.build_life_cycles(sigma)
        for cycle in self.life_cycles:
            self.store.log_life_cycle(self.session_id, cycle)
        sigma = self.phase_event(6, "evaluate_wake_state", "relational_stability", "evaluate_wake_state", 0.16, 0.03, 0.24, 0.12, sigma)
        self.handoff = self.build_handoff(sigma)
        self.store.log_handoff(self.session_id, self.handoff)
        self.phase_event(7, "handoff_next_sleep", self.handoff.next_recommended_core, "write_next_handoff", 0.12, 0.02, 0.20, 0.08, self.handoff.confidence + 1.25)
        self.summary = self.complete()
        return self.summary

    def phase_event(
        self,
        phase_index: int,
        phase: str,
        focus_key: str,
        cognitive_action: str,
        novelty: float,
        conflict: float,
        memory_pressure: float,
        replay_gap: float,
        prior_sigma: float | None = None,
    ) -> float:
        energy_before = self.energy
        x = RZSInput(
            bandwidth=2.42 + self.context.continuity_score * 0.48 + self.context.wake_confidence * 0.22 + self.energy * 0.30,
            info_self=0.32 + (1.0 - self.context.continuity_score) * 0.20,
            info_external=0.16 + len(self.context.recent_semantic) * 0.015,
            task_info=0.34 + phase_index * 0.035 + (0.08 if self.context.commitment_text else 0.0),
            novelty=novelty,
            conflict=conflict,
            latency=1.00 + memory_pressure * 0.18,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        before = assessment.sigma
        if prior_sigma is not None:
            before = max(0.10, min(before, prior_sigma + 0.16))
        after = max(prediction.sigma_after, before + (0.035 if assessment.decision != "continue" else 0.014))
        if assessment.decision in {"replay_memory", "consolidate", "pause_for_stability"}:
            self.energy = clamp(self.energy + 0.052)
        elif assessment.decision == "narrow_focus":
            self.energy = clamp(self.energy + 0.032)
        else:
            self.energy = clamp(self.energy + 0.038)
        event = WakePhase(
            phase_index=phase_index,
            phase=phase,
            focus_key=focus_key or "unknown_focus",
            rzs_decision=assessment.decision,
            sigma_before=before,
            sigma_after=after,
            energy_before=energy_before,
            energy_after=self.energy,
            cognitive_action=cognitive_action,
            payload={
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction": asdict(prediction),
                "romero_formula": FORMULA,
                "source_sleep_session_id": self.context.sleep_session_id,
                "source_wake_plan_id": self.context.wake_plan_id,
                "wake_plan_summary": self.context.wake_summary,
            },
        )
        self.phases.append(event)
        self.store.log_phase(self.session_id, event)
        return after

    def resolve_commitment(self) -> CommitmentResolution:
        reviewed = bool(self.context.primary_goal_id and self.context.primary_goal_plan)
        status = "fulfilled_in_wake_loop" if reviewed else "advanced_without_primary_goal"
        wake_bonus = 0.12 if self.context.wake_next_action == "wake_and_review_primary_goal" else 0.06
        score = clamp(
            0.52
            + self.context.wake_confidence * 0.16
            + self.context.continuity_score * 0.14
            + self.context.primary_goal_priority * 0.12
            + wake_bonus
            + self.context.stability_gain * 0.08
        )
        evidence = {
            "reviewed_primary_goal": reviewed,
            "wake_plan_id": self.context.wake_plan_id,
            "wake_next_action": self.context.wake_next_action,
            "primary_goal_id": self.context.primary_goal_id,
            "primary_goal_plan": self.context.primary_goal_plan,
            "success_criterion": self.context.primary_goal_success,
            "source_commitment_trigger": self.context.commitment_trigger,
        }
        return CommitmentResolution(
            resolution_id=f"RS-{self.session_id}",
            source_commitment_id=self.context.commitment_id,
            commitment_text=self.context.commitment_text or "revisar meta principal ao acordar",
            reviewed_goal_id=self.context.primary_goal_id,
            resolution_status=status,
            fulfilled_score=score,
            evidence=evidence,
            payload={
                "identity_statement": self.context.identity_statement,
                "active_preference_key": self.context.active_preference_key,
                "sleep_consolidation_id": self.context.consolidation_id,
            },
        )

    def build_life_cycles(self, prior_sigma: float) -> list[LifeCycle]:
        sequence = [
            (
                "orient_to_wake_plan",
                self.context.wake_plan_id,
                "orient_to_v49_20_wake_plan",
                f"Plano carregado: {short(self.context.wake_summary or self.context.wake_next_action)}",
                "Darwin sabe por que acordou.",
                0.16,
                0.04,
                0.28,
                0.20,
            ),
            (
                "review_primary_goal",
                self.context.primary_goal_id,
                "review_primary_goal",
                f"Meta revisada: {short(self.context.primary_goal_plan)}",
                "Compromisso v49.19 recebe evidencia de cumprimento.",
                0.22,
                0.05,
                0.38,
                0.20,
            ),
            (
                "select_next_focus",
                self.context.active_preference_key,
                "select_next_focus_from_goal_and_preference",
                f"Foco escolhido: {self.context.current_goal or self.context.active_preference_key}",
                "Acordar vira direcao de agencia, nao apenas estado passivo.",
                0.20,
                0.07,
                0.34,
                0.18,
            ),
            (
                "stabilize_with_sleep_memory",
                self.context.consolidation_focus,
                "stabilize_with_sleep_consolidation",
                f"Consolidacao {self.context.consolidation_id or 'v49.20'} usada como memoria de apoio.",
                "Sono reduz ruido antes da proxima escolha.",
                0.15,
                0.04,
                0.76,
                0.72,
            ),
            (
                "prepare_next_agency_cycle",
                "agency_handoff",
                "prepare_agency_cycle",
                "Proximo nucleo recomendado: agencia interna sobre a meta revisada.",
                "Darwin deixa uma intencao pronta para continuar.",
                0.18,
                0.04,
                0.30,
                0.12,
            ),
            (
                "close_wake_window",
                "relational_stability",
                "close_wake_window",
                "Janela de acordar fechada com energia estavel e memoria escrita.",
                "O ciclo acordado termina sem corromper passado.",
                0.10,
                0.02,
                0.18,
                0.08,
            ),
        ]
        cycles: list[LifeCycle] = []
        sigma_anchor = prior_sigma
        for idx, (cycle_key, focus, action, result, effect, novelty, conflict, memory_pressure, replay_gap) in enumerate(sequence, start=1):
            x = RZSInput(
                bandwidth=2.55 + self.energy * 0.36 + self.context.continuity_score * 0.24,
                info_self=0.28 + (1.0 - self.context.continuity_score) * 0.12,
                info_external=0.18,
                task_info=0.34 + idx * 0.025,
                novelty=novelty,
                conflict=conflict,
                latency=1.00 + memory_pressure * 0.16,
                energy=self.energy,
                memory_pressure=memory_pressure,
                replay_gap=replay_gap,
            )
            assessment = self.rzs.classify(x)
            prediction = self.rzs.predict(x, assessment.decision)
            before = max(0.10, min(assessment.sigma, sigma_anchor + 0.12))
            after = max(prediction.sigma_after, before + (0.026 if assessment.decision != "continue" else 0.010))
            self.energy = clamp(self.energy + (0.034 if assessment.decision != "replay_memory" else 0.048))
            cycles.append(
                LifeCycle(
                    cycle_index=idx,
                    cycle_key=cycle_key,
                    focus_key=focus or "unknown_focus",
                    action_taken=action,
                    result_summary=result,
                    expected_effect=effect,
                    rzs_decision=assessment.decision,
                    sigma_before=before,
                    sigma_after=after,
                    energy_after=self.energy,
                    completed=True,
                    payload={
                        "rzs_input": asdict(x),
                        "rzs_reason": assessment.reason,
                        "prediction": asdict(prediction),
                        "source_wake_plan_id": self.context.wake_plan_id,
                        "source_commitment_id": self.context.commitment_id,
                    },
                )
            )
            sigma_anchor = after
        return cycles

    def build_handoff(self, sigma_before: float) -> WakeHandoff:
        if self.context.primary_goal_plan:
            next_action = f"run_agency_for_{self.context.primary_goal_kind}"
        else:
            next_action = "run_agency_for_reviewed_goal"
        confidence = clamp(
            0.48
            + self.context.wake_confidence * 0.20
            + self.context.continuity_score * 0.12
            + (self.resolution.fulfilled_score if self.resolution else 0.65) * 0.14
            + self.context.stability_gain * 0.10
        )
        return WakeHandoff(
            handoff_id=f"HF-{self.session_id}",
            source_wake_plan_id=self.context.wake_plan_id,
            next_recommended_core="darwin_intention_agency_core_v49_19",
            next_action=next_action,
            agency_ready=True,
            sleep_ready=True,
            confidence=confidence,
            payload={
                "reviewed_goal_id": self.context.primary_goal_id,
                "reviewed_goal_plan": self.context.primary_goal_plan,
                "source_sleep_session_id": self.context.sleep_session_id,
                "source_commitment_id": self.context.commitment_id,
                "sigma_before": sigma_before,
                "active_preference_key": self.context.active_preference_key,
                "note": "v49.21 acordou, cumpriu o plano v49.20 e preparou continuidade de agencia.",
            },
        )

    def complete(self) -> dict[str, Any]:
        if self.resolution is None or self.handoff is None:
            raise RuntimeError("Wake life loop incomplete")
        summary = {
            "session_id": self.session_id,
            "source_sleep_session_id": self.context.sleep_session_id,
            "source_wake_plan_id": self.context.wake_plan_id,
            "phase_count": len(self.phases),
            "life_cycle_count": len(self.life_cycles),
            "phases": [
                {
                    "phase": p.phase,
                    "focus_key": p.focus_key,
                    "rzs_decision": p.rzs_decision,
                    "sigma_before": round(p.sigma_before, 3),
                    "sigma_after": round(p.sigma_after, 3),
                    "energy_after": round(p.energy_after, 3),
                    "cognitive_action": p.cognitive_action,
                }
                for p in self.phases
            ],
            "resolution": {
                "resolution_id": self.resolution.resolution_id,
                "source_commitment_id": self.resolution.source_commitment_id,
                "status": self.resolution.resolution_status,
                "fulfilled_score": round(self.resolution.fulfilled_score, 3),
                "reviewed_goal_id": self.resolution.reviewed_goal_id,
            },
            "life_cycles": [
                {
                    "cycle_key": c.cycle_key,
                    "focus_key": c.focus_key,
                    "action_taken": c.action_taken,
                    "rzs_decision": c.rzs_decision,
                    "sigma_before": round(c.sigma_before, 3),
                    "sigma_after": round(c.sigma_after, 3),
                    "completed": c.completed,
                }
                for c in self.life_cycles
            ],
            "handoff": {
                "handoff_id": self.handoff.handoff_id,
                "next_recommended_core": self.handoff.next_recommended_core,
                "next_action": self.handoff.next_action,
                "agency_ready": self.handoff.agency_ready,
                "sleep_ready": self.handoff.sleep_ready,
                "confidence": round(self.handoff.confidence, 3),
            },
            "session_complete": True,
        }
        first_sigma = self.phases[0].sigma_before if self.phases else 0.0
        final_sigma = self.phases[-1].sigma_after if self.phases else self.handoff.confidence
        self.store.write_memory(self.session_id, summary, 0.88)
        self.store.write_episode(
            self.session_id,
            "wake_from_sleep_fulfill_commitment_handoff",
            f"resolution={self.resolution.resolution_status} cycles={len(self.life_cycles)} handoff={self.handoff.next_action}",
            "Darwin fechou o arco sono-acordar: plano v49.20 foi consumido, compromisso v49.19 foi revisado e agencia futura ficou preparada.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            "wake_life_loop_core",
            self.energy,
            self.context.sleep_session_id,
            summary,
        )
        return summary


class WakeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Wake & Life Loop v49.21")
        self.root.geometry("1080x740")
        self.root.minsize(940, 640)
        self.root.configure(bg="#061018")
        self.core: WakeLifeLoopCore | None = None
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
        tk.Label(header, text="DARWIN WAKE & LIFE LOOP v49.21", bg="#061018", fg="#eef8ff", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="acordar -> restaurar identidade -> cumprir compromisso -> preparar agencia", bg="#061018", fg="#9cc9ff", font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg="#061018")
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg="#061018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=390)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg="#061018", highlightthickness=0, height=360)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Acordar agora", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="Fases", command=self.show_phases).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Ciclos", command=self.show_cycles).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Handoff", command=self.show_handoff).pack(side="left", padx=4, pady=8)
        self.phase_box = tk.Text(left, height=12, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Consolas", 10))
        self.phase_box.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Acordado", bg="#0d1b26", fg="#eef8ff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = WakeLifeLoopCore()
        self.summary = self.core.run_cycle()
        self.show_phases()
        self.show_handoff()

    def show_phases(self) -> None:
        self.phase_box.delete("1.0", "end")
        lines = ["Fases do acordar", ""]
        for idx, phase in enumerate(self.summary.get("phases", []), start=1):
            lines.append(
                f"{idx}. {phase['phase']} | foco {phase['focus_key']} | RZS {phase['rzs_decision']} | "
                f"sigma {phase['sigma_before']}->{phase['sigma_after']} | energia {phase['energy_after']}"
            )
        self.phase_box.insert("end", "\n".join(lines))

    def show_cycles(self) -> None:
        self.text.delete("1.0", "end")
        lines = ["Ciclos de vida acordada", ""]
        for idx, cycle in enumerate(self.summary.get("life_cycles", []), start=1):
            lines.append(f"{idx}. {cycle['cycle_key']}")
            lines.append(f"   acao: {cycle['action_taken']}")
            lines.append(f"   RZS: {cycle['rzs_decision']} | sigma {cycle['sigma_before']}->{cycle['sigma_after']}")
        self.text.insert("end", "\n".join(lines))

    def show_handoff(self) -> None:
        self.text.delete("1.0", "end")
        r = self.summary.get("resolution", {})
        h = self.summary.get("handoff", {})
        lines = [
            "Compromisso",
            f"status: {r.get('status', '')}",
            f"score: {r.get('fulfilled_score', 0)}",
            f"meta revisada: {r.get('reviewed_goal_id', '')}",
            "",
            "Proximo handoff",
            f"nucleo: {h.get('next_recommended_core', '')}",
            f"acao: {h.get('next_action', '')}",
            f"agencia pronta: {h.get('agency_ready', False)}",
            f"sono pronto: {h.get('sleep_ready', False)}",
            f"confianca: {h.get('confidence', 0)}",
        ]
        self.text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.03
        self.draw_canvas()
        self.root.after(50, self.animate)

    def draw_canvas(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.54
        self.canvas.create_text(cx, 30, text="Darwin acordado", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        pulse = 1.0 + math.sin(self.phase) * 0.04
        core_r = 78 * pulse
        self.canvas.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r, fill="#4ea3ff", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - core_r * 0.34, cy - core_r * 0.34, cx + core_r * 0.34, cy + core_r * 0.34, fill="#e6fbff", outline="")
        phases = self.summary.get("phases", [])
        colors = ["#80ed99", "#ffd166", "#9bf6ff", "#ffb3c1", "#bdb2ff", "#fdffb6", "#98f5e1"]
        for idx, phase in enumerate(phases[:7]):
            angle = -math.pi / 2 + idx * (math.tau / max(1, len(phases[:7]))) + self.phase * 0.075
            radius = min(w, h) * 0.34
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            r = 13
            self.canvas.create_line(cx, cy, x, y, fill="#173a52", width=2)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors[idx % len(colors)], outline="")
            self.canvas.create_text(x, y + 26, text=str(phase.get("phase", ""))[:17], fill="#dff2ff", font=("Segoe UI", 8))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.21 - WAKE & LIFE LOOP CORE")
    print("=" * 62)
    print(f"- sessao: {summary['session_id']}")
    print(f"- sono fonte: {summary['source_sleep_session_id']}")
    print(f"- plano acordar: {summary['source_wake_plan_id']}")
    print(f"- fases: {summary['phase_count']} ciclos acordados: {summary['life_cycle_count']}")
    print(f"- compromisso: {summary['resolution']['status']} score={summary['resolution']['fulfilled_score']}")
    print(f"- proximo handoff: {summary['handoff']['next_action']} confianca={summary['handoff']['confidence']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.21 Wake & Life Loop Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4921)
    args = ap.parse_args()
    if args.self_test:
        core = WakeLifeLoopCore(seed=args.seed)
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    WakeApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
