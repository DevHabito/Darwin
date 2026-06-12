from __future__ import annotations

"""
DARWIN v49.20 - Sleep & Consolidation Core

Objetivo:
Criar um ciclo de sono cognitivo no notebook. Darwin nao fica apenas
com uma intencao ativa: ele faz replay, simula sonho interno, consolida
memorias e acorda com um plano verificavel.

Uso:
    py darwin_sleep_consolidation_core_v49_20.py
    py darwin_sleep_consolidation_core_v49_20.py --self-test --details
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

SL_SESSIONS = "sleep_sessions_v49_20"
SL_PHASES = "sleep_phase_events_v49_20"
SL_REPLAY = "sleep_replay_items_v49_20"
SL_DREAMS = "sleep_dream_sequences_v49_20"
SL_CONSOLIDATIONS = "sleep_consolidations_v49_20"
SL_WAKE_PLANS = "sleep_wake_plans_v49_20"

SOURCE = "darwin_sleep_consolidation_core_v49_20"

PHASES = [
    "pre_sleep_scan",
    "commitment_replay",
    "autobiography_replay",
    "dream_simulation",
    "memory_weight_update",
    "identity_consolidation",
    "wake_plan",
]


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


def short(text: str, limit: int = 120) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class SleepContext:
    agency_session_id: str
    intention_id: str
    selected_action: str
    executed_action: str
    commitment_text: str
    commitment_trigger: str
    commitment_confidence: float
    identity_session_id: str
    identity_statement: str
    continuity_score: float
    active_preference_key: str
    chapters: list[dict[str, Any]]
    preferences: list[dict[str, Any]]
    recent_memories: list[dict[str, Any]]


@dataclass
class SleepPhase:
    phase_index: int
    phase: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    energy_before: float
    energy_after: float
    payload: dict[str, Any]


@dataclass
class ReplayItem:
    replay_id: str
    replay_index: int
    source_kind: str
    source_ref: str
    focus_key: str
    salience_before: float
    salience_after: float
    replay_reason: str
    payload: dict[str, Any]


@dataclass
class DreamSequence:
    dream_id: str
    dream_index: int
    dream_kind: str
    fragments: list[str]
    integration_score: float
    predicted_wake_effect: str
    payload: dict[str, Any]


@dataclass
class Consolidation:
    consolidation_id: str
    consolidated_focus: str
    memory_delta: float
    stability_gain: float
    noise_reduction: float
    lesson: str
    payload: dict[str, Any]


@dataclass
class WakePlan:
    wake_plan_id: str
    next_action: str
    trigger: str
    confidence: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    plan_summary: str
    payload: dict[str, Any]


class SleepStore:
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
                CREATE TABLE IF NOT EXISTS {SL_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SL_PHASES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    energy_before REAL NOT NULL DEFAULT 0.0,
                    energy_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SL_REPLAY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    replay_index INTEGER NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    salience_before REAL NOT NULL DEFAULT 0.0,
                    salience_after REAL NOT NULL DEFAULT 0.0,
                    replay_reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SL_DREAMS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dream_id TEXT NOT NULL UNIQUE,
                    dream_index INTEGER NOT NULL,
                    dream_kind TEXT NOT NULL,
                    fragments_json TEXT NOT NULL DEFAULT '[]',
                    integration_score REAL NOT NULL DEFAULT 0.0,
                    predicted_wake_effect TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SL_CONSOLIDATIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    consolidation_id TEXT NOT NULL UNIQUE,
                    consolidated_focus TEXT NOT NULL,
                    memory_delta REAL NOT NULL DEFAULT 0.0,
                    stability_gain REAL NOT NULL DEFAULT 0.0,
                    noise_reduction REAL NOT NULL DEFAULT 0.0,
                    lesson TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SL_WAKE_PLANS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    wake_plan_id TEXT NOT NULL UNIQUE,
                    next_action TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    plan_summary TEXT NOT NULL,
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
                f"INSERT INTO {SL_SESSIONS} (timestamp, session_id, phase, mode, energy, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_phase(self, session_id: str, phase: SleepPhase) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SL_PHASES} (
                    timestamp, session_id, phase_index, phase, rzs_decision,
                    sigma_before, sigma_after, energy_before, energy_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    phase.phase_index,
                    phase.phase,
                    phase.rzs_decision,
                    phase.sigma_before,
                    phase.sigma_after,
                    phase.energy_before,
                    phase.energy_after,
                    js(phase.payload),
                ),
            )
            conn.commit()

    def log_replay(self, session_id: str, item: ReplayItem) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SL_REPLAY} (
                    timestamp, session_id, replay_id, replay_index,
                    source_kind, source_ref, focus_key, salience_before,
                    salience_after, replay_reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    item.replay_id,
                    item.replay_index,
                    item.source_kind,
                    item.source_ref,
                    item.focus_key,
                    item.salience_before,
                    item.salience_after,
                    item.replay_reason,
                    js(item.payload),
                ),
            )
            conn.commit()

    def log_dream(self, session_id: str, dream: DreamSequence) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SL_DREAMS} (
                    timestamp, session_id, dream_id, dream_index,
                    dream_kind, fragments_json, integration_score,
                    predicted_wake_effect, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    dream.dream_id,
                    dream.dream_index,
                    dream.dream_kind,
                    js(dream.fragments),
                    dream.integration_score,
                    dream.predicted_wake_effect,
                    js(dream.payload),
                ),
            )
            conn.commit()

    def log_consolidation(self, session_id: str, consolidation: Consolidation) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SL_CONSOLIDATIONS} (
                    timestamp, session_id, consolidation_id, consolidated_focus,
                    memory_delta, stability_gain, noise_reduction, lesson, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    consolidation.consolidation_id,
                    consolidation.consolidated_focus,
                    consolidation.memory_delta,
                    consolidation.stability_gain,
                    consolidation.noise_reduction,
                    consolidation.lesson,
                    js(consolidation.payload),
                ),
            )
            conn.commit()

    def log_wake_plan(self, session_id: str, plan: WakePlan) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SL_WAKE_PLANS} (
                    timestamp, session_id, wake_plan_id, next_action, trigger,
                    confidence, rzs_decision, sigma_before, sigma_after,
                    plan_summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    plan.wake_plan_id,
                    plan.next_action,
                    plan.trigger,
                    plan.confidence,
                    plan.rzs_decision,
                    plan.sigma_before,
                    plan.sigma_after,
                    plan.plan_summary,
                    js(plan.payload),
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
                (f"sleep_consolidation_v49_20:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                    f"sleep_consolidation:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class SleepContextLoader:
    def __init__(self, store: SleepStore) -> None:
        self.store = store

    def latest_context(self) -> SleepContext:
        with self.store.connect() as conn:
            commitment = self.latest_row(conn, "agency_commitments_v49_19")
            outcome = self.latest_row(conn, "agency_outcomes_v49_19")
            identity = self.latest_row(conn, "autobiography_identity_state_v49_18")
            identity_session = str(identity.get("session_id") or "")
            chapters = self.rows_for_session(conn, "autobiography_chapters_v49_18", identity_session, "sequence_index ASC")
            prefs_session = self.latest_session(conn, "affective_preference_sessions_v49_17", "session_complete")
            preferences = self.rows_for_session(conn, "affective_preferences_v49_17", prefs_session, "strength DESC")
            recent_memories = self.recent_memories(conn)
        return SleepContext(
            agency_session_id=str(commitment.get("session_id") or outcome.get("session_id") or ""),
            intention_id=str(commitment.get("intention_id") or outcome.get("intention_id") or ""),
            selected_action=str((pj(str(commitment.get("payload_json") or "{}")) or {}).get("selected_action") or outcome.get("selected_action") or ""),
            executed_action=str(outcome.get("executed_action") or ""),
            commitment_text=str(commitment.get("commitment_text") or ""),
            commitment_trigger=str(commitment.get("next_trigger") or ""),
            commitment_confidence=clamp(float(commitment.get("confidence") or 0.0)),
            identity_session_id=identity_session,
            identity_statement=str(identity.get("identity_statement") or ""),
            continuity_score=clamp(float(identity.get("continuity_score") or 0.0)),
            active_preference_key=str(identity.get("active_preference_key") or ""),
            chapters=chapters,
            preferences=preferences,
            recent_memories=recent_memories,
        )

    def latest_row(self, conn: sqlite3.Connection, table: str) -> dict[str, Any]:
        if not self.store.table_exists(conn, table):
            return {}
        row = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    def latest_session(self, conn: sqlite3.Connection, table: str, complete_phase: str) -> str:
        if not self.store.table_exists(conn, table):
            return ""
        row = conn.execute(f"SELECT session_id FROM {table} WHERE phase=? ORDER BY id DESC LIMIT 1", (complete_phase,)).fetchone()
        return str(row["session_id"]) if row else ""

    def rows_for_session(self, conn: sqlite3.Connection, table: str, session_id: str, order: str) -> list[dict[str, Any]]:
        if not session_id or not self.store.table_exists(conn, table):
            return []
        out: list[dict[str, Any]] = []
        for row in conn.execute(f"SELECT * FROM {table} WHERE session_id=? ORDER BY {order}", (session_id,)).fetchall():
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"))
            if "source_kinds_json" in item:
                item["source_kinds"] = pj(str(item.get("source_kinds_json") or "[]"), [])
            out.append(item)
        return out

    def recent_memories(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        if not self.store.table_exists(conn, "semantic_memory"):
            return []
        sources = [
            "darwin_autobiographical_continuity_v49_18",
            "darwin_intention_agency_core_v49_19",
            "darwin_affective_preference_core_v49_17",
            "darwin_classical_music_nursery_v49_16",
        ]
        placeholders = ",".join("?" for _ in sources)
        rows = conn.execute(
            f"""
            SELECT *
            FROM semantic_memory
            WHERE source IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT 12
            """,
            tuple(sources),
        ).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]


class SleepConsolidationCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4920-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.58
        self.store = SleepStore(db_path)
        self.rzs = RZSFormal()
        self.context = SleepContextLoader(self.store).latest_context()
        self.phases: list[SleepPhase] = []
        self.replays: list[ReplayItem] = []
        self.dreams: list[DreamSequence] = []
        self.consolidation: Consolidation | None = None
        self.wake_plan: WakePlan | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            "sleep_consolidation_core",
            self.energy,
            {"version": "v49.20", "goal": "sleep_replay_consolidation_wake_plan"},
        )

    def run_cycle(self) -> dict[str, Any]:
        sigma = self.phase_event(1, "pre_sleep_scan", novelty=0.34, conflict=0.10, memory_pressure=0.74, replay_gap=0.82)
        self.replays = self.build_replay_items()
        for replay in self.replays:
            self.store.log_replay(self.session_id, replay)
        sigma = self.phase_event(2, "commitment_replay", novelty=0.24, conflict=0.08, memory_pressure=0.62, replay_gap=0.58, prior_sigma=sigma)
        sigma = self.phase_event(3, "autobiography_replay", novelty=0.22, conflict=0.07, memory_pressure=0.54, replay_gap=0.42, prior_sigma=sigma)
        self.dreams = self.build_dreams()
        for dream in self.dreams:
            self.store.log_dream(self.session_id, dream)
        sigma = self.phase_event(4, "dream_simulation", novelty=0.38, conflict=0.12, memory_pressure=0.48, replay_gap=0.34, prior_sigma=sigma)
        self.consolidation = self.build_consolidation()
        self.store.log_consolidation(self.session_id, self.consolidation)
        sigma = self.phase_event(5, "memory_weight_update", novelty=0.18, conflict=0.05, memory_pressure=0.34, replay_gap=0.20, prior_sigma=sigma)
        sigma = self.phase_event(6, "identity_consolidation", novelty=0.16, conflict=0.05, memory_pressure=0.28, replay_gap=0.16, prior_sigma=sigma)
        self.wake_plan = self.build_wake_plan(sigma)
        self.store.log_wake_plan(self.session_id, self.wake_plan)
        self.phase_event(7, "wake_plan", novelty=0.20, conflict=0.04, memory_pressure=0.22, replay_gap=0.12, prior_sigma=self.wake_plan.sigma_before)
        self.summary = self.complete()
        return self.summary

    def phase_event(
        self,
        phase_index: int,
        phase: str,
        novelty: float,
        conflict: float,
        memory_pressure: float,
        replay_gap: float,
        prior_sigma: float | None = None,
    ) -> float:
        energy_before = self.energy
        x = RZSInput(
            bandwidth=2.55 + self.context.continuity_score * 0.54 + self.energy * 0.24,
            info_self=0.30 + (1.0 - self.context.continuity_score) * 0.20,
            info_external=0.18 + len(self.context.chapters) * 0.018,
            task_info=0.34 + len(self.replays) * 0.025,
            novelty=novelty,
            conflict=conflict,
            latency=1.00 + memory_pressure * 0.18,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        before = assessment.sigma if prior_sigma is None else min(assessment.sigma, max(0.10, prior_sigma))
        after = max(before + 0.035, prediction.sigma_after)
        if assessment.decision in {"replay_memory", "consolidate", "pause_for_stability"}:
            self.energy = clamp(self.energy + 0.052)
        else:
            self.energy = clamp(self.energy + 0.024)
        phase_event = SleepPhase(
            phase_index,
            phase,
            assessment.decision,
            before,
            after,
            energy_before,
            self.energy,
            {
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction": asdict(prediction),
                "commitment_text": self.context.commitment_text,
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )
        self.phases.append(phase_event)
        self.store.log_phase(self.session_id, phase_event)
        return after

    def build_replay_items(self) -> list[ReplayItem]:
        items: list[ReplayItem] = []
        def add(source_kind: str, source_ref: str, focus: str, salience: float, reason: str, payload: dict[str, Any]) -> None:
            idx = len(items) + 1
            after = clamp(salience + 0.08 + self.context.commitment_confidence * 0.04)
            items.append(ReplayItem(f"RP-{self.session_id}-{idx:02d}", idx, source_kind, source_ref, focus, salience, after, reason, payload))

        add(
            "agency_commitment",
            self.context.intention_id,
            "active_commitment",
            clamp(0.70 + self.context.commitment_confidence * 0.20),
            "compromisso ativo precisa ser reativado durante o sono",
            {"commitment_text": self.context.commitment_text, "trigger": self.context.commitment_trigger},
        )
        if self.context.executed_action:
            add(
                "agency_outcome",
                self.context.agency_session_id,
                self.context.executed_action,
                0.76,
                "resultado de agencia vira memoria de procedimento",
                {"selected_action": self.context.selected_action, "executed_action": self.context.executed_action},
            )
        for chapter in sorted(self.context.chapters, key=lambda c: float(c.get("continuity_score") or 0.0), reverse=True)[:4]:
            add(
                "autobiography_chapter",
                str(chapter.get("chapter_key") or ""),
                str(chapter.get("chapter_key") or ""),
                clamp(float(chapter.get("continuity_score") or 0.5)),
                "capitulo autobiografico reforcado por relevancia",
                {"title": chapter.get("title"), "summary": chapter.get("summary")},
            )
        for pref in self.context.preferences[:3]:
            add(
                "affective_preference",
                str(pref.get("preference_key") or ""),
                str(pref.get("candidate_action") or ""),
                clamp(float(pref.get("strength") or 0.5)),
                "preferencia afetiva entra no sonho para guiar o acordar",
                {"domain": pref.get("domain"), "evidence_count": pref.get("evidence_count")},
            )
        return items

    def build_dreams(self) -> list[DreamSequence]:
        fragments = [item.focus_key for item in self.replays[:6] if item.focus_key]
        if not fragments:
            fragments = ["identity", "commitment", "wake_plan"]
        dreams = [
            DreamSequence(
                f"DR-{self.session_id}-01",
                1,
                "commitment_bridge",
                fragments[:4],
                clamp(0.58 + mean([r.salience_after for r in self.replays[:4]]) * 0.28),
                "acordar lembrando o compromisso ativo antes de nova acao",
                {"source_replays": [r.replay_id for r in self.replays[:4]]},
            ),
            DreamSequence(
                f"DR-{self.session_id}-02",
                2,
                "preference_identity_blend",
                fragments[-4:],
                clamp(0.54 + self.context.continuity_score * 0.24 + self.context.commitment_confidence * 0.12),
                "ligar preferencia afetiva e autobiografia em um plano simples",
                {"active_preference_key": self.context.active_preference_key},
            ),
        ]
        return dreams

    def build_consolidation(self) -> Consolidation:
        replay_gain = mean([r.salience_after - r.salience_before for r in self.replays])
        dream_gain = mean([d.integration_score for d in self.dreams]) * 0.08
        stability_gain = clamp(0.10 + replay_gain * 0.45 + dream_gain)
        memory_delta = clamp(0.16 + replay_gain + self.context.commitment_confidence * 0.12)
        noise_reduction = clamp(0.12 + len(self.replays) / 80.0 + (1.0 - self.context.continuity_score) * 0.12)
        focus = self.context.active_preference_key or "agency_commitment"
        return Consolidation(
            f"CN-{self.session_id}",
            focus,
            memory_delta,
            stability_gain,
            noise_reduction,
            "Sono consolidou compromisso, capitulos autobiograficos e preferencia ativa sem alterar tabelas antigas.",
            {
                "replay_count": len(self.replays),
                "dream_count": len(self.dreams),
                "commitment_text": self.context.commitment_text,
                "identity_statement": self.context.identity_statement,
            },
        )

    def build_wake_plan(self, sigma_before: float) -> WakePlan:
        if self.context.commitment_text:
            next_action = "wake_and_review_primary_goal"
            trigger = self.context.commitment_trigger or "next_wake_or_user_continues"
        elif self.context.selected_action:
            next_action = f"wake_and_resume_{self.context.selected_action}"
            trigger = "stable_wake"
        else:
            next_action = "wake_and_rebuild_autobiography"
            trigger = "missing_commitment"
        x = RZSInput(
            bandwidth=3.15 + self.energy * 0.35,
            info_self=0.26,
            info_external=0.18,
            task_info=0.42,
            novelty=0.20,
            conflict=0.05,
            latency=1.02,
            energy=self.energy,
            memory_pressure=0.18,
            replay_gap=0.10,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        confidence = clamp(0.54 + self.context.commitment_confidence * 0.24 + self.context.continuity_score * 0.18 + self.consolidation.stability_gain * 0.20)
        summary = f"Ao acordar, {next_action}; motivo: {short(self.context.commitment_text or self.context.identity_statement, 120)}"
        return WakePlan(
            f"WK-{self.session_id}",
            next_action,
            trigger,
            confidence,
            assessment.decision,
            max(0.10, sigma_before),
            max(prediction.sigma_after, sigma_before + 0.04),
            summary,
            {
                "commitment_text": self.context.commitment_text,
                "consolidation_id": self.consolidation.consolidation_id if self.consolidation else "",
                "active_preference_key": self.context.active_preference_key,
            },
        )

    def complete(self) -> dict[str, Any]:
        if self.consolidation is None or self.wake_plan is None:
            raise RuntimeError("Sleep cycle incomplete")
        summary = {
            "session_id": self.session_id,
            "agency_session_id": self.context.agency_session_id,
            "identity_session_id": self.context.identity_session_id,
            "phase_count": len(self.phases),
            "phases": [
                {
                    "phase": p.phase,
                    "rzs_decision": p.rzs_decision,
                    "sigma_before": round(p.sigma_before, 3),
                    "sigma_after": round(p.sigma_after, 3),
                    "energy_after": round(p.energy_after, 3),
                }
                for p in self.phases
            ],
            "replay_count": len(self.replays),
            "dream_count": len(self.dreams),
            "consolidation": {
                "focus": self.consolidation.consolidated_focus,
                "memory_delta": round(self.consolidation.memory_delta, 3),
                "stability_gain": round(self.consolidation.stability_gain, 3),
                "noise_reduction": round(self.consolidation.noise_reduction, 3),
            },
            "wake_plan": {
                "next_action": self.wake_plan.next_action,
                "trigger": self.wake_plan.trigger,
                "confidence": round(self.wake_plan.confidence, 3),
                "rzs_decision": self.wake_plan.rzs_decision,
                "sigma_before": round(self.wake_plan.sigma_before, 3),
                "sigma_after": round(self.wake_plan.sigma_after, 3),
                "summary": self.wake_plan.plan_summary,
            },
            "session_complete": True,
        }
        self.store.write_memory(self.session_id, summary, 0.86)
        self.store.write_episode(
            self.session_id,
            "sleep_replay_consolidate_wake_plan",
            f"replays={len(self.replays)} dreams={len(self.dreams)} wake={self.wake_plan.next_action}",
            "Darwin usou sono cognitivo para consolidar agencia, autobiografia e compromisso futuro.",
            self.phases[0].sigma_before if self.phases else 0.0,
            self.wake_plan.sigma_after,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            "sleep_consolidation_core",
            self.energy,
            summary,
        )
        return summary


class SleepApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Sleep & Consolidation v49.20")
        self.root.geometry("1080x740")
        self.root.minsize(940, 640)
        self.root.configure(bg="#071018")
        self.core: SleepConsolidationCore | None = None
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
        tk.Label(header, text="DARWIN SLEEP & CONSOLIDATION v49.20", bg="#071018", fg="#eef8ff", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="replay -> sonho interno -> consolidacao -> plano de acordar", bg="#071018", fg="#9cc9ff", font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg="#071018")
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg="#071018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=390)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg="#071018", highlightthickness=0, height=360)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Dormir agora", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="Fases", command=self.show_phases).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Acordar", command=self.show_wake).pack(side="left", padx=4, pady=8)
        self.phase_box = tk.Text(left, height=12, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Consolas", 10))
        self.phase_box.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Sono cognitivo", bg="#0d1b26", fg="#eef8ff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = SleepConsolidationCore()
        self.summary = self.core.run_cycle()
        self.show_phases()
        self.show_wake()

    def show_phases(self) -> None:
        self.phase_box.delete("1.0", "end")
        lines = ["Fases do sono", ""]
        for idx, phase in enumerate(self.summary.get("phases", []), start=1):
            lines.append(f"{idx}. {phase['phase']} | RZS {phase['rzs_decision']} | sigma {phase['sigma_before']}->{phase['sigma_after']} | energia {phase['energy_after']}")
        self.phase_box.insert("end", "\n".join(lines))

    def show_wake(self) -> None:
        self.text.delete("1.0", "end")
        c = self.summary.get("consolidation", {})
        w = self.summary.get("wake_plan", {})
        lines = [
            "Consolidacao",
            f"foco: {c.get('focus', '')}",
            f"delta memoria: {c.get('memory_delta', 0)}",
            f"ganho estabilidade: {c.get('stability_gain', 0)}",
            f"reducao ruido: {c.get('noise_reduction', 0)}",
            "",
            "Plano ao acordar",
            str(w.get("summary", "")),
            f"gatilho: {w.get('trigger', '')}",
            f"confianca: {w.get('confidence', 0)}",
        ]
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
        self.canvas.create_text(cx, 30, text="sono cognitivo do Darwin", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        pulse = 1.0 + math.sin(self.phase) * 0.035
        core_r = 84 * pulse
        self.canvas.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r, fill="#3b82f6", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - core_r * 0.33, cy - core_r * 0.33, cx + core_r * 0.33, cy + core_r * 0.33, fill="#dff2ff", outline="")
        phases = self.summary.get("phases", [])
        colors = ["#72e0a8", "#f6d77a", "#ffb3c7", "#c7b9ff", "#8fd3ff", "#f2bf72", "#75e7a8"]
        for idx, phase in enumerate(phases[:7]):
            angle = -math.pi / 2 + idx * (math.tau / max(1, len(phases[:7]))) + self.phase * 0.08
            radius = min(w, h) * 0.34
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            r = 14
            self.canvas.create_line(cx, cy, x, y, fill="#173a52", width=2)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors[idx % len(colors)], outline="")
            self.canvas.create_text(x, y + 26, text=str(phase.get("phase", ""))[:17], fill="#dff2ff", font=("Segoe UI", 8))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.20 - SLEEP & CONSOLIDATION CORE")
    print("=" * 62)
    print(f"- sessao: {summary['session_id']}")
    print(f"- agencia fonte: {summary['agency_session_id']}")
    print(f"- fases: {summary['phase_count']}")
    print(f"- replays: {summary['replay_count']} sonhos: {summary['dream_count']}")
    print(f"- foco consolidado: {summary['consolidation']['focus']}")
    print(f"- plano ao acordar: {summary['wake_plan']['next_action']}")
    print(f"- confianca: {summary['wake_plan']['confidence']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.20 Sleep & Consolidation Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4920)
    args = ap.parse_args()
    if args.self_test:
        core = SleepConsolidationCore(seed=args.seed)
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    SleepApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
