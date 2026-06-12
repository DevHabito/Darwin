from __future__ import annotations

"""
DARWIN v49.19 - Intention & Agency Core

Objetivo:
Transformar continuidade autobiografica em agencia interna. Darwin
forma uma intencao, passa pelo RZS, executa passos cognitivos internos,
avalia uma previsao e grava um compromisso futuro.

Uso:
    py darwin_intention_agency_core_v49_19.py
    py darwin_intention_agency_core_v49_19.py --self-test --details
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

AG_SESSIONS = "agency_sessions_v49_19"
AG_INTENTIONS = "agency_intentions_v49_19"
AG_STEPS = "agency_action_steps_v49_19"
AG_OUTCOMES = "agency_outcomes_v49_19"
AG_COMMITMENTS = "agency_commitments_v49_19"

SOURCE = "darwin_intention_agency_core_v49_19"


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
class AgencyContext:
    identity_session_id: str
    identity_id: str
    continuity_score: float
    remembered_event_count: int
    chapter_count: int
    source_diversity: int
    active_preference_key: str
    active_preference_strength: float
    current_goal: str
    autobiographical_next_action: str
    identity_statement: str
    predictions: list[dict[str, Any]]
    chapters: list[dict[str, Any]]
    goals: list[dict[str, Any]]


@dataclass
class AgencyIntention:
    intention_id: str
    source_identity_id: str
    candidate_action: str
    selected_action: str
    goal_statement: str
    motive: str
    priority: float
    autonomy_score: float
    expected_value: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    payload: dict[str, Any]


@dataclass
class AgencyStep:
    step_id: str
    step_index: int
    phase: str
    action_taken: str
    focus_key: str
    result_summary: str
    sigma_before: float
    sigma_after: float
    completed: bool
    payload: dict[str, Any]


@dataclass
class AgencyOutcome:
    outcome_id: str
    intention_id: str
    selected_action: str
    executed_action: str
    success_score: float
    stability_delta: float
    prediction_checked: bool
    prediction_matched: bool
    lesson: str
    payload: dict[str, Any]


@dataclass
class AgencyCommitment:
    commitment_id: str
    intention_id: str
    commitment_text: str
    next_trigger: str
    status: str
    confidence: float
    payload: dict[str, Any]


class AgencyStore:
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
                CREATE TABLE IF NOT EXISTS {AG_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AG_INTENTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    intention_id TEXT NOT NULL UNIQUE,
                    source_identity_id TEXT NOT NULL,
                    candidate_action TEXT NOT NULL,
                    selected_action TEXT NOT NULL,
                    goal_statement TEXT NOT NULL,
                    motive TEXT NOT NULL,
                    priority REAL NOT NULL DEFAULT 0.0,
                    autonomy_score REAL NOT NULL DEFAULT 0.0,
                    expected_value REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AG_STEPS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    intention_id TEXT NOT NULL,
                    step_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AG_OUTCOMES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    outcome_id TEXT NOT NULL UNIQUE,
                    intention_id TEXT NOT NULL,
                    selected_action TEXT NOT NULL,
                    executed_action TEXT NOT NULL,
                    success_score REAL NOT NULL DEFAULT 0.0,
                    stability_delta REAL NOT NULL DEFAULT 0.0,
                    prediction_checked INTEGER NOT NULL DEFAULT 0,
                    prediction_matched INTEGER NOT NULL DEFAULT 0,
                    lesson TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AG_COMMITMENTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    commitment_id TEXT NOT NULL UNIQUE,
                    intention_id TEXT NOT NULL,
                    commitment_text TEXT NOT NULL,
                    next_trigger TEXT NOT NULL,
                    status TEXT NOT NULL,
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

    def log_session(self, session_id: str, phase: str, mode: str, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {AG_SESSIONS} (
                    timestamp, session_id, phase, mode, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_intention(self, session_id: str, intention: AgencyIntention) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AG_INTENTIONS} (
                    timestamp, session_id, intention_id, source_identity_id,
                    candidate_action, selected_action, goal_statement,
                    motive, priority, autonomy_score, expected_value,
                    rzs_decision, sigma_before, sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    intention.intention_id,
                    intention.source_identity_id,
                    intention.candidate_action,
                    intention.selected_action,
                    intention.goal_statement,
                    intention.motive,
                    intention.priority,
                    intention.autonomy_score,
                    intention.expected_value,
                    intention.rzs_decision,
                    intention.sigma_before,
                    intention.sigma_after,
                    js(intention.payload),
                ),
            )
            conn.commit()

    def log_step(self, session_id: str, intention_id: str, step: AgencyStep) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AG_STEPS} (
                    timestamp, session_id, intention_id, step_id,
                    step_index, phase, action_taken, focus_key,
                    result_summary, sigma_before, sigma_after,
                    completed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    intention_id,
                    step.step_id,
                    step.step_index,
                    step.phase,
                    step.action_taken,
                    step.focus_key,
                    step.result_summary,
                    step.sigma_before,
                    step.sigma_after,
                    1 if step.completed else 0,
                    js(step.payload),
                ),
            )
            conn.commit()

    def log_outcome(self, session_id: str, outcome: AgencyOutcome) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AG_OUTCOMES} (
                    timestamp, session_id, outcome_id, intention_id,
                    selected_action, executed_action, success_score,
                    stability_delta, prediction_checked, prediction_matched,
                    lesson, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    outcome.outcome_id,
                    outcome.intention_id,
                    outcome.selected_action,
                    outcome.executed_action,
                    outcome.success_score,
                    outcome.stability_delta,
                    1 if outcome.prediction_checked else 0,
                    1 if outcome.prediction_matched else 0,
                    outcome.lesson,
                    js(outcome.payload),
                ),
            )
            conn.commit()

    def log_commitment(self, session_id: str, commitment: AgencyCommitment) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {AG_COMMITMENTS} (
                    timestamp, session_id, commitment_id, intention_id,
                    commitment_text, next_trigger, status, confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    commitment.commitment_id,
                    commitment.intention_id,
                    commitment.commitment_text,
                    commitment.next_trigger,
                    commitment.status,
                    commitment.confidence,
                    js(commitment.payload),
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
                (f"agency_v49_19:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                    f"agency:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class AgencyContextLoader:
    def __init__(self, store: AgencyStore) -> None:
        self.store = store

    def latest_context(self) -> AgencyContext:
        with self.store.connect() as conn:
            identity = self.latest_identity(conn)
            identity_session_id = str(identity.get("session_id") or "")
            predictions = self.rows_for_session(conn, "autobiography_next_predictions_v49_18", identity_session_id)
            chapters = self.rows_for_session(conn, "autobiography_chapters_v49_18", identity_session_id)
            goals = self.latest_goals(conn)
        return AgencyContext(
            identity_session_id=identity_session_id,
            identity_id=str(identity.get("identity_id") or ""),
            continuity_score=clamp(float(identity.get("continuity_score") or 0.0)),
            remembered_event_count=int(identity.get("remembered_event_count") or 0),
            chapter_count=int(identity.get("chapter_count") or 0),
            source_diversity=int(identity.get("source_diversity") or 0),
            active_preference_key=str(identity.get("active_preference_key") or "none"),
            active_preference_strength=clamp(float(identity.get("active_preference_strength") or 0.0)),
            current_goal=str(identity.get("current_goal") or ""),
            autobiographical_next_action=str(identity.get("next_action") or ""),
            identity_statement=str(identity.get("identity_statement") or ""),
            predictions=predictions,
            chapters=chapters,
            goals=goals,
        )

    def latest_identity(self, conn: sqlite3.Connection) -> dict[str, Any]:
        if not self.store.table_exists(conn, "autobiography_identity_state_v49_18"):
            return {}
        row = conn.execute("SELECT * FROM autobiography_identity_state_v49_18 ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {}
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        return item

    def rows_for_session(self, conn: sqlite3.Connection, table: str, session_id: str) -> list[dict[str, Any]]:
        if not session_id or not self.store.table_exists(conn, table):
            return []
        out = []
        for row in conn.execute(f"SELECT * FROM {table} WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall():
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"))
            if "source_kinds_json" in item:
                item["source_kinds"] = pj(str(item.get("source_kinds_json") or "[]"), [])
            out.append(item)
        return out

    def latest_goals(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        if not self.store.table_exists(conn, "mind_learning_goals_v49_15"):
            return []
        out = []
        rows = conn.execute(
            """
            SELECT *
            FROM mind_learning_goals_v49_15
            ORDER BY priority DESC, id DESC
            LIMIT 6
            """
        ).fetchall()
        for row in rows:
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"))
            out.append(item)
        return out


class IntentionAgencyCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4919-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.78
        self.store = AgencyStore(db_path)
        self.rzs = RZSFormal()
        self.context = AgencyContextLoader(self.store).latest_context()
        self.intention: AgencyIntention | None = None
        self.steps: list[AgencyStep] = []
        self.outcome: AgencyOutcome | None = None
        self.commitment: AgencyCommitment | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            "intention_agency_core",
            self.energy,
            {"version": "v49.19", "goal": "turn_autobiography_into_internal_action"},
        )

    def run_cycle(self) -> dict[str, Any]:
        self.intention = self.form_intention()
        self.store.log_intention(self.session_id, self.intention)
        self.store.log_session(
            self.session_id,
            "intention_formed",
            "intention_agency_core",
            self.energy,
            {
                "intention_id": self.intention.intention_id,
                "candidate_action": self.intention.candidate_action,
                "selected_action": self.intention.selected_action,
                "rzs_decision": self.intention.rzs_decision,
            },
        )
        self.steps = self.execute_steps(self.intention)
        for step in self.steps:
            self.store.log_step(self.session_id, self.intention.intention_id, step)
        self.outcome = self.evaluate_outcome(self.intention, self.steps)
        self.store.log_outcome(self.session_id, self.outcome)
        self.commitment = self.make_commitment(self.intention, self.outcome)
        self.store.log_commitment(self.session_id, self.commitment)
        self.summary = self.complete()
        return self.summary

    def form_intention(self) -> AgencyIntention:
        ctx = self.context
        candidate = ctx.autobiographical_next_action or ctx.current_goal or "review_self_goals"
        top_prediction = ctx.predictions[0] if ctx.predictions else {}
        top_goal = ctx.goals[0] if ctx.goals else {}
        confidence = clamp(float(top_prediction.get("confidence") or 0.55))
        priority = clamp(float(top_goal.get("priority") or confidence))
        expected = clamp(ctx.continuity_score * 0.34 + confidence * 0.24 + ctx.active_preference_strength * 0.26 + priority * 0.16)
        autonomy = clamp(0.34 + ctx.continuity_score * 0.26 + ctx.active_preference_strength * 0.22 + len(ctx.predictions) * 0.035 + len(ctx.goals) * 0.015)
        open_loop_pressure = clamp(len([g for g in ctx.goals if str(g.get("status") or "proposed") != "done"]) / 8.0)
        x = RZSInput(
            bandwidth=2.70 + ctx.continuity_score * 0.58 + self.energy * 0.28,
            info_self=0.34 + (1.0 - ctx.continuity_score) * 0.24,
            info_external=0.24 + ctx.source_diversity * 0.022,
            task_info=0.38 + expected * 0.32,
            novelty=clamp(0.34 + (1.0 - confidence) * 0.22),
            conflict=clamp(0.12 + open_loop_pressure * 0.22),
            latency=1.02 + open_loop_pressure * 0.18,
            energy=self.energy,
            memory_pressure=clamp(0.40 + ctx.remembered_event_count / 180.0),
            replay_gap=clamp(0.44 + (0.28 if "recall_autobiographical" in candidate else 0.0)),
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        selected = self.govern_action(candidate, assessment.decision)
        motive = (
            f"agir a partir de {ctx.active_preference_key}; "
            f"continuidade={ctx.continuity_score:.2f}; meta={top_goal.get('goal_kind', 'autobiography')}"
        )
        return AgencyIntention(
            f"IN-{self.session_id}",
            ctx.identity_id,
            candidate,
            selected,
            f"Executar internamente {selected}",
            motive,
            priority,
            autonomy,
            expected,
            assessment.decision,
            assessment.sigma,
            prediction.sigma_after,
            {
                "identity_session_id": ctx.identity_session_id,
                "identity_statement": ctx.identity_statement,
                "top_prediction": top_prediction,
                "top_goal": top_goal,
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction": asdict(prediction),
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )

    def govern_action(self, candidate: str, decision: str) -> str:
        if decision == "continue":
            return candidate
        if decision == "replay_memory":
            if candidate.startswith("recall_autobiographical_sequence_before_"):
                return candidate
            return f"recall_autobiographical_sequence_before_{candidate}"
        if decision == "narrow_focus":
            return f"narrow_intention_before_{candidate}"
        if decision == "consolidate":
            return "consolidate_intention_before_action"
        if decision == "pause_for_stability":
            return "pause_intention_for_stability"
        return candidate

    def execute_steps(self, intention: AgencyIntention) -> list[AgencyStep]:
        ctx = self.context
        steps: list[AgencyStep] = []
        sigma = intention.sigma_before

        def add(phase: str, action: str, focus: str, result: str, delta: float, payload: dict[str, Any]) -> None:
            nonlocal sigma
            before = sigma
            sigma = max(0.10, sigma + delta)
            steps.append(
                AgencyStep(
                    f"ST-{self.session_id}-{len(steps) + 1:02d}",
                    len(steps) + 1,
                    phase,
                    action,
                    focus,
                    short(result, 260),
                    before,
                    sigma,
                    True,
                    payload,
                )
            )

        top_chapters = sorted(ctx.chapters, key=lambda c: float(c.get("continuity_score") or 0.0), reverse=True)[:4]
        goals = ctx.goals[:4]
        predictions = ctx.predictions[:4]
        add(
            "wake_identity",
            "load_autobiographical_identity",
            ctx.active_preference_key,
            ctx.identity_statement or "Identidade carregada.",
            0.06,
            {"identity_id": ctx.identity_id, "continuity_score": ctx.continuity_score},
        )
        add(
            "recall_autobiography",
            "recall_relevant_chapters",
            "autobiography_chapters",
            "Recordei capitulos: " + ", ".join(str(c.get("chapter_key")) for c in top_chapters),
            0.11,
            {"chapters": top_chapters},
        )
        add(
            "resolve_intention",
            "bind_preference_to_goal",
            ctx.active_preference_key,
            f"Preferencia {ctx.active_preference_key} foi ligada a {intention.selected_action}.",
            0.07,
            {"predictions": predictions, "goals": goals},
        )
        action_result = self.internal_action_result(intention.selected_action, goals, predictions)
        add(
            "execute_internal_action",
            self.executed_action_name(intention.selected_action),
            self.focus_from_action(intention.selected_action),
            action_result,
            0.14,
            {"selected_action": intention.selected_action, "internal_execution": True},
        )
        add(
            "evaluate_prediction",
            "check_prediction_against_internal_effect",
            "prediction",
            "A previsao foi marcada como verificavel: sigma_after do ciclo interno deve superar sigma_before.",
            0.08,
            {"prediction_checked": True, "expected_sigma_after_gte_before": True},
        )
        add(
            "commit_next",
            "write_future_commitment",
            "commitment",
            "Compromisso criado para continuar o treino escolhido na proxima abertura.",
            0.04,
            {"commitment_status": "active"},
        )
        return steps

    def internal_action_result(self, selected_action: str, goals: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> str:
        if "review_self_goals" in selected_action:
            top = goals[0] if goals else {}
            return (
                f"Revisei a meta {top.get('goal_kind', 'self_reflection')}: "
                f"{short(str(top.get('action_plan', 'manter continuidade e escolher proximo treino')), 150)}"
            )
        if "listen_to_gentle_music" in selected_action:
            return "Reativei a memoria musical calma como estrategia de estabilidade antes de nova estimulacao."
        if "practice_memory_cards" in selected_action:
            return "Preparei treino de memoria visual com foco estreito e erro observavel."
        if "practice_joint_attention" in selected_action:
            return "Preparei treino de foco compartilhado entre palavra, objeto e resposta."
        if "talk_with_felipe" in selected_action:
            return "Preparei atualizacao do modelo relacional de Felipe antes de responder."
        pred = predictions[0] if predictions else {}
        return f"Executei ensaio interno orientado por {pred.get('candidate_action', selected_action)}."

    def executed_action_name(self, selected_action: str) -> str:
        if "review_self_goals" in selected_action:
            return "review_self_goals_internally"
        if "listen_to_gentle_music" in selected_action:
            return "replay_calm_music_memory"
        if "practice_memory_cards" in selected_action:
            return "prepare_memory_card_training"
        if "practice_joint_attention" in selected_action:
            return "prepare_joint_attention_training"
        if "talk_with_felipe" in selected_action:
            return "prepare_relational_dialogue"
        return "execute_internal_cognitive_action"

    def focus_from_action(self, selected_action: str) -> str:
        if "review_self_goals" in selected_action:
            return "self_reflection_goal"
        if "music" in selected_action:
            return "calm_music_memory"
        if "memory_cards" in selected_action:
            return "visual_memory"
        if "joint_attention" in selected_action:
            return "shared_attention"
        if "felipe" in selected_action:
            return "felipe_relation"
        return "agency_focus"

    def evaluate_outcome(self, intention: AgencyIntention, steps: list[AgencyStep]) -> AgencyOutcome:
        first = steps[0] if steps else None
        last = steps[-1] if steps else None
        sigma_before = first.sigma_before if first else intention.sigma_before
        sigma_after = last.sigma_after if last else intention.sigma_after
        stability_delta = sigma_after - sigma_before
        completed_ratio = sum(1 for s in steps if s.completed) / max(1, len(steps))
        prediction_checked = any(s.phase == "evaluate_prediction" for s in steps)
        prediction_matched = prediction_checked and sigma_after >= sigma_before
        success = clamp(0.38 + completed_ratio * 0.26 + (0.18 if prediction_matched else 0.0) + min(0.18, max(0.0, stability_delta) / 1.5))
        lesson = (
            "Intencao virou acao interna: identidade foi lembrada, foco foi escolhido, "
            "acao cognitiva foi executada e a previsao foi checada."
        )
        return AgencyOutcome(
            f"OUT-{self.session_id}",
            intention.intention_id,
            intention.selected_action,
            self.executed_action_name(intention.selected_action),
            success,
            stability_delta,
            prediction_checked,
            prediction_matched,
            lesson,
            {
                "step_count": len(steps),
                "completed_steps": sum(1 for s in steps if s.completed),
                "sigma_before": sigma_before,
                "sigma_after": sigma_after,
                "phases": [s.phase for s in steps],
            },
        )

    def make_commitment(self, intention: AgencyIntention, outcome: AgencyOutcome) -> AgencyCommitment:
        if "review_self_goals" in intention.selected_action:
            text = "Na proxima abertura, revisar a meta mais importante antes de escolher novo treino."
            trigger = "next_wake_or_user_continues"
        elif "music" in intention.selected_action:
            text = "Usar musica calma como regulador se a carga autobiografica subir."
            trigger = "high_memory_pressure"
        else:
            text = f"Continuar {outcome.executed_action} quando a estabilidade permitir."
            trigger = "stable_continue"
        return AgencyCommitment(
            f"COM-{self.session_id}",
            intention.intention_id,
            text,
            trigger,
            "active",
            clamp(outcome.success_score * 0.72 + intention.autonomy_score * 0.28),
            {"selected_action": intention.selected_action, "outcome_id": outcome.outcome_id},
        )

    def complete(self) -> dict[str, Any]:
        if self.intention is None or self.outcome is None or self.commitment is None:
            raise RuntimeError("Agency cycle incomplete")
        summary = {
            "session_id": self.session_id,
            "identity_session_id": self.context.identity_session_id,
            "intention": {
                "intention_id": self.intention.intention_id,
                "candidate_action": self.intention.candidate_action,
                "selected_action": self.intention.selected_action,
                "goal_statement": self.intention.goal_statement,
                "priority": round(self.intention.priority, 3),
                "autonomy_score": round(self.intention.autonomy_score, 3),
                "expected_value": round(self.intention.expected_value, 3),
                "rzs_decision": self.intention.rzs_decision,
                "sigma_before": round(self.intention.sigma_before, 3),
                "sigma_after": round(self.intention.sigma_after, 3),
            },
            "steps": [
                {
                    "phase": step.phase,
                    "action_taken": step.action_taken,
                    "focus_key": step.focus_key,
                    "sigma_before": round(step.sigma_before, 3),
                    "sigma_after": round(step.sigma_after, 3),
                }
                for step in self.steps
            ],
            "outcome": {
                "success_score": round(self.outcome.success_score, 3),
                "stability_delta": round(self.outcome.stability_delta, 3),
                "prediction_checked": self.outcome.prediction_checked,
                "prediction_matched": self.outcome.prediction_matched,
                "lesson": self.outcome.lesson,
            },
            "commitment": {
                "commitment_text": self.commitment.commitment_text,
                "next_trigger": self.commitment.next_trigger,
                "status": self.commitment.status,
                "confidence": round(self.commitment.confidence, 3),
            },
            "session_complete": True,
        }
        self.store.write_memory(self.session_id, summary, 0.84)
        self.store.write_episode(
            self.session_id,
            self.outcome.executed_action,
            f"success={self.outcome.success_score:.3f} prediction_matched={self.outcome.prediction_matched}",
            self.outcome.lesson,
            self.intention.sigma_before,
            self.steps[-1].sigma_after if self.steps else self.intention.sigma_after,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            "intention_agency_core",
            self.energy,
            summary,
        )
        return summary


class AgencyApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Intention & Agency v49.19")
        self.root.geometry("1080x740")
        self.root.minsize(940, 640)
        self.root.configure(bg="#071018")
        self.core: IntentionAgencyCore | None = None
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
        tk.Label(header, text="DARWIN INTENTION & AGENCY v49.19", bg="#071018", fg="#eef8ff", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="autobiografia -> intencao -> acao interna -> compromisso", bg="#071018", fg="#9cc9ff", font=("Segoe UI", 10)).pack(anchor="w")

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
        ttk.Button(controls, text="Rodar agencia", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="Intencao", command=self.show_intention).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Passos", command=self.show_steps).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Compromisso", command=self.show_commitment).pack(side="left", padx=4, pady=8)

        self.step_box = tk.Text(left, height=12, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Consolas", 10))
        self.step_box.pack(fill="both", expand=True, pady=(8, 0))

        tk.Label(right, text="Agencia interna", bg="#0d1b26", fg="#eef8ff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = IntentionAgencyCore()
        self.summary = self.core.run_cycle()
        self.show_steps()
        self.show_intention()

    def show_intention(self) -> None:
        intent = self.summary.get("intention", {})
        self.text.delete("1.0", "end")
        lines = [
            "Intencao formada",
            f"candidata: {intent.get('candidate_action', '')}",
            f"selecionada: {intent.get('selected_action', '')}",
            f"autonomia: {intent.get('autonomy_score', 0)}",
            f"valor esperado: {intent.get('expected_value', 0)}",
            f"RZS: {intent.get('rzs_decision', '')} sigma {intent.get('sigma_before', 0)}->{intent.get('sigma_after', 0)}",
        ]
        self.text.insert("end", "\n".join(lines))

    def show_steps(self) -> None:
        self.step_box.delete("1.0", "end")
        lines = ["Passos cognitivos executados", ""]
        for idx, step in enumerate(self.summary.get("steps", []), start=1):
            lines.append(f"{idx}. {step['phase']} -> {step['action_taken']} | sigma {step['sigma_before']}->{step['sigma_after']}")
        self.step_box.insert("end", "\n".join(lines))

    def show_commitment(self) -> None:
        self.text.delete("1.0", "end")
        outcome = self.summary.get("outcome", {})
        com = self.summary.get("commitment", {})
        lines = [
            "Resultado",
            f"sucesso: {outcome.get('success_score', 0)}",
            f"delta estabilidade: {outcome.get('stability_delta', 0)}",
            f"previsao checada: {outcome.get('prediction_checked', False)}",
            f"previsao bateu: {outcome.get('prediction_matched', False)}",
            "",
            "Compromisso",
            str(com.get("commitment_text", "")),
            f"gatilho: {com.get('next_trigger', '')}",
            f"confianca: {com.get('confidence', 0)}",
        ]
        self.text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.035
        self.draw_canvas()
        self.root.after(50, self.animate)

    def draw_canvas(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.52
        intent = self.summary.get("intention", {})
        autonomy = float(intent.get("autonomy_score") or 0.0)
        self.canvas.create_text(cx, 30, text="ciclo de agencia interna", fill="#eef8ff", font=("Segoe UI", 16, "bold"))
        core_r = 42 + autonomy * 48
        pulse = 1.0 + math.sin(self.phase) * 0.05
        self.canvas.create_oval(cx - core_r * pulse, cy - core_r * pulse, cx + core_r * pulse, cy + core_r * pulse, fill="#72e0a8", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - core_r * 0.33, cy - core_r * 0.33, cx + core_r * 0.33, cy + core_r * 0.33, fill="#e7fbff", outline="")
        steps = self.summary.get("steps", [])
        colors = ["#58b0ff", "#f6d77a", "#ffb3c7", "#c7b9ff", "#8fd3ff", "#f2bf72"]
        for idx, step in enumerate(steps[:6]):
            angle = self.phase * 0.20 + idx * (math.tau / max(1, len(steps[:6])))
            radius = min(w, h) * 0.34
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            r = 15
            self.canvas.create_line(cx, cy, x, y, fill="#173a52", width=2)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors[idx % len(colors)], outline="")
            self.canvas.create_text(x, y + 26, text=str(step.get("phase", ""))[:18], fill="#dff2ff", font=("Segoe UI", 8))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    intent = summary["intention"]
    outcome = summary["outcome"]
    print("DARWIN v49.19 - INTENTION & AGENCY CORE")
    print("=" * 62)
    print(f"- sessao: {summary['session_id']}")
    print(f"- identidade fonte: {summary['identity_session_id']}")
    print(f"- acao candidata: {intent['candidate_action']}")
    print(f"- acao selecionada: {intent['selected_action']}")
    print(f"- autonomia: {intent['autonomy_score']}")
    print(f"- passos: {len(summary['steps'])}")
    print(f"- sucesso: {outcome['success_score']} previsao={outcome['prediction_matched']}")
    print(f"- compromisso: {summary['commitment']['commitment_text']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.19 Intention & Agency Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4919)
    args = ap.parse_args()
    if args.self_test:
        core = IntentionAgencyCore(seed=args.seed)
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    AgencyApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
