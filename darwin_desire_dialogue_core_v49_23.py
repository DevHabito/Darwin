from __future__ import annotations

"""
DARWIN v49.23 - Desire Dialogue Core

Objetivo:
Transformar a preferencia autonoma v49.22 em fala conversacional. Quando
Felipe pergunta o que Darwin quer, gosta, prefere ou ainda nao sabe,
Darwin responde a partir da propria memoria v49.22, com RZS regulando
estilo, foco e incerteza.

Uso:
    py darwin_desire_dialogue_core_v49_23.py
    py darwin_desire_dialogue_core_v49_23.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
import tkinter as tk
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

DD_SESSIONS = "desire_dialogue_sessions_v49_23"
DD_TURNS = "desire_dialogue_turns_v49_23"
DD_REFS = "desire_dialogue_memory_refs_v49_23"
DD_STATE = "desire_dialogue_state_v49_23"

SOURCE = "darwin_desire_dialogue_core_v49_23"
FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"

EXPECTED_INTENTS = [
    "want_general",
    "music_preference",
    "formula_preference",
    "color_preference",
    "why_preference",
    "uncertainty_probe",
]


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


def normalize(text: str) -> str:
    lowered = text.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def short(text: str, limit: int = 130) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class DesireCandidate:
    candidate_id: str
    domain: str
    label: str
    like_score: float
    uncertainty: float
    autonomy_score: float
    evidence_count: int
    reason: str
    payload: dict[str, Any]


@dataclass
class DesireDecision:
    question_kind: str
    chosen_candidate_id: str
    chosen_domain: str
    chosen_label: str
    want_statement: str
    rzs_decision: str
    confidence: float
    exploration_selected: bool
    payload: dict[str, Any]


@dataclass
class DesireContext:
    preference_session_id: str
    identity_id: str
    top_want: str
    top_music: str
    top_formula: str
    top_color: str
    top_activity: str
    autonomy_statement: str
    decisions: dict[str, DesireDecision]
    candidates: list[DesireCandidate]


@dataclass
class DesireTurn:
    turn_index: int
    dialogue_id: str
    user_text: str
    intent: str
    question_kind: str
    chosen_label: str
    response_text: str
    focus_key: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    confidence: float
    grounded_in_v49_22: bool
    payload: dict[str, Any]


@dataclass
class DesireRef:
    dialogue_id: str
    ref_kind: str
    ref_key: str
    source_table: str
    evidence_count: int
    summary: str
    payload: dict[str, Any]


@dataclass
class DesireState:
    state_id: str
    top_want: str
    top_music: str
    top_formula: str
    top_color: str
    top_activity: str
    dialogue_readiness: float
    autonomy_statement: str
    payload: dict[str, Any]


class DesireDialogueStore:
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
                CREATE TABLE IF NOT EXISTS {DD_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    source_preference_session_id TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DD_TURNS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    dialogue_id TEXT NOT NULL UNIQUE,
                    user_text TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    question_kind TEXT NOT NULL,
                    chosen_label TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    grounded_in_v49_22 INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DD_REFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL,
                    ref_kind TEXT NOT NULL,
                    ref_key TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DD_STATE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    state_id TEXT NOT NULL UNIQUE,
                    top_want TEXT NOT NULL,
                    top_music TEXT NOT NULL,
                    top_formula TEXT NOT NULL,
                    top_color TEXT NOT NULL,
                    top_activity TEXT NOT NULL,
                    dialogue_readiness REAL NOT NULL DEFAULT 0.0,
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

    def log_session(
        self,
        session_id: str,
        phase: str,
        mode: str,
        source_preference_session_id: str,
        energy: float,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {DD_SESSIONS} (
                    timestamp, session_id, phase, mode,
                    source_preference_session_id, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, source_preference_session_id, energy, js(payload or {})),
            )
            conn.commit()

    def log_turn(self, session_id: str, turn: DesireTurn) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {DD_TURNS} (
                    timestamp, session_id, turn_index, dialogue_id,
                    user_text, intent, question_kind, chosen_label,
                    response_text, focus_key, rzs_decision, sigma_before,
                    sigma_after, confidence, grounded_in_v49_22, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    turn.turn_index,
                    turn.dialogue_id,
                    turn.user_text,
                    turn.intent,
                    turn.question_kind,
                    turn.chosen_label,
                    turn.response_text,
                    turn.focus_key,
                    turn.rzs_decision,
                    turn.sigma_before,
                    turn.sigma_after,
                    turn.confidence,
                    1 if turn.grounded_in_v49_22 else 0,
                    js(turn.payload),
                ),
            )
            conn.commit()

    def log_ref(self, session_id: str, ref: DesireRef) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {DD_REFS} (
                    timestamp, session_id, dialogue_id, ref_kind, ref_key,
                    source_table, evidence_count, summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    ref.dialogue_id,
                    ref.ref_kind,
                    ref.ref_key,
                    ref.source_table,
                    ref.evidence_count,
                    ref.summary,
                    js(ref.payload),
                ),
            )
            conn.commit()

    def log_state(self, session_id: str, state: DesireState) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {DD_STATE} (
                    timestamp, session_id, state_id, top_want, top_music,
                    top_formula, top_color, top_activity, dialogue_readiness,
                    autonomy_statement, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    state.state_id,
                    state.top_want,
                    state.top_music,
                    state.top_formula,
                    state.top_color,
                    state.top_activity,
                    state.dialogue_readiness,
                    state.autonomy_statement,
                    js(state.payload),
                ),
            )
            conn.commit()

    def write_memory(self, session_id: str, summary: dict[str, Any], confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory (
                    key, content, confidence, source, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (f"desire_dialogue_v49_23:{session_id}", js(summary), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                    f"desire_dialogue:{session_id}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class DesireContextLoader:
    def __init__(self, store: DesireDialogueStore) -> None:
        self.store = store

    def latest_context(self) -> DesireContext:
        with self.store.connect() as conn:
            pref_session = self.latest_completed_preference_session(conn)
            identity = self.latest_identity(conn, pref_session)
            decisions = self.latest_decisions(conn, pref_session)
            candidates = self.latest_candidates(conn, pref_session)
        return DesireContext(
            preference_session_id=pref_session,
            identity_id=str(identity.get("identity_id") or ""),
            top_want=str(identity.get("top_want") or decisions.get("geral", DesireDecision("", "", "", "", "", "", 0.0, False, {})).want_statement),
            top_music=str(identity.get("top_music") or decisions.get("musica", DesireDecision("", "", "", "", "", "", 0.0, False, {})).want_statement),
            top_formula=str(identity.get("top_formula") or decisions.get("formula", DesireDecision("", "", "", "", "", "", 0.0, False, {})).want_statement),
            top_color=str(identity.get("top_color") or decisions.get("cor", DesireDecision("", "", "", "", "", "", 0.0, False, {})).want_statement),
            top_activity=str(identity.get("top_activity") or decisions.get("atividade", DesireDecision("", "", "", "", "", "", 0.0, False, {})).want_statement),
            autonomy_statement=str(identity.get("autonomy_statement") or "Meus gostos sao hipoteses vivas derivadas da memoria."),
            decisions=decisions,
            candidates=candidates,
        )

    def latest_completed_preference_session(self, conn: sqlite3.Connection) -> str:
        if not self.store.table_exists(conn, "autonomous_preference_sessions_v49_22"):
            return ""
        rows = conn.execute(
            """
            SELECT session_id, payload_json
            FROM autonomous_preference_sessions_v49_22
            WHERE phase='session_complete'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchall()
        for row in rows:
            payload = pj(str(row["payload_json"] or "{}"), {})
            if payload.get("session_complete"):
                return str(row["session_id"] or "")
        row = conn.execute("SELECT session_id FROM autonomous_preference_sessions_v49_22 ORDER BY id DESC LIMIT 1").fetchone()
        return str(row["session_id"]) if row else ""

    def latest_identity(self, conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
        if not session_id or not self.store.table_exists(conn, "autonomous_preference_identity_v49_22"):
            return {}
        row = conn.execute(
            """
            SELECT *
            FROM autonomous_preference_identity_v49_22
            WHERE session_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    def latest_decisions(self, conn: sqlite3.Connection, session_id: str) -> dict[str, DesireDecision]:
        if not session_id or not self.store.table_exists(conn, "autonomous_preference_decisions_v49_22"):
            return {}
        out: dict[str, DesireDecision] = {}
        rows = conn.execute(
            """
            SELECT *
            FROM autonomous_preference_decisions_v49_22
            WHERE session_id=?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        for row in rows:
            item = {k: row[k] for k in row.keys()}
            question = str(item.get("question_kind") or "")
            out[question] = DesireDecision(
                question_kind=question,
                chosen_candidate_id=str(item.get("chosen_candidate_id") or ""),
                chosen_domain=str(item.get("chosen_domain") or ""),
                chosen_label=str(item.get("chosen_label") or ""),
                want_statement=str(item.get("want_statement") or ""),
                rzs_decision=str(item.get("rzs_decision") or ""),
                confidence=clamp(float(item.get("confidence") or 0.0)),
                exploration_selected=bool(int(item.get("exploration_selected") or 0)),
                payload=pj(str(item.get("payload_json") or "{}"), {}),
            )
        return out

    def latest_candidates(self, conn: sqlite3.Connection, session_id: str) -> list[DesireCandidate]:
        if not session_id or not self.store.table_exists(conn, "autonomous_preference_candidates_v49_22"):
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM autonomous_preference_candidates_v49_22
            WHERE session_id=?
            ORDER BY autonomy_score DESC, like_score DESC, evidence_count DESC
            """,
            (session_id,),
        ).fetchall()
        out: list[DesireCandidate] = []
        for row in rows:
            item = {k: row[k] for k in row.keys()}
            out.append(
                DesireCandidate(
                    candidate_id=str(item.get("candidate_id") or ""),
                    domain=str(item.get("domain") or ""),
                    label=str(item.get("label") or ""),
                    like_score=clamp(float(item.get("like_score") or 0.0)),
                    uncertainty=clamp(float(item.get("uncertainty") or 0.0)),
                    autonomy_score=clamp(float(item.get("autonomy_score") or 0.0)),
                    evidence_count=max(0, int(item.get("evidence_count") or 0)),
                    reason=str(item.get("reason") or ""),
                    payload=pj(str(item.get("payload_json") or "{}"), {}),
                )
            )
        return out


class DesireDialogueCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None, mode: str = "gui") -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4923-{int(time.time())}-{suffix(self.rng)}"
        self.mode = mode
        self.energy = 0.74
        self.store = DesireDialogueStore(db_path)
        self.rzs = RZSFormal()
        self.context = DesireContextLoader(self.store).latest_context()
        self.turns: list[DesireTurn] = []
        self.refs: list[DesireRef] = []
        self.state: DesireState | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            mode,
            self.context.preference_session_id,
            self.energy,
            {"version": "v49.23", "goal": "speak_desires_from_autonomous_preferences"},
        )

    def classify_intent(self, text: str) -> tuple[str, str]:
        t = normalize(text)
        if any(w in t for w in ("musica", "cancao", "som", "melodia", "ouvir")):
            return "music_preference", "musica"
        if any(w in t for w in ("formula", "conceito", "geometr", "torque", "angulo", "peso")):
            return "formula_preference", "formula"
        if any(w in t for w in ("cor", "cores", "azul", "rosa", "verde")):
            return "color_preference", "cor"
        if any(w in t for w in ("porque", "por que", "motivo", "evidencia", "prova")):
            return "why_preference", "geral"
        if any(w in t for w in ("incerto", "incerteza", "duvida", "nao sabe", "explorar")):
            return "uncertainty_probe", "geral"
        if any(w in t for w in ("diana", "pragmata", "companheira", "presenca")):
            return "companion_desire", "atividade"
        return "want_general", "geral"

    def ask(self, user_text: str) -> DesireTurn:
        turn_index = len(self.turns) + 1
        dialogue_id = f"dd:{self.session_id}:{turn_index:04d}"
        intent, question_kind = self.classify_intent(user_text)
        decision = self.decision_for(intent, question_kind)
        candidate = self.candidate_for_decision(decision)
        uncertainty = candidate.uncertainty if candidate else max(0.30, 1.0 - decision.confidence)
        evidence_count = candidate.evidence_count if candidate else 0
        x = self.rzs_input(user_text, intent, decision, uncertainty, evidence_count)
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, assessment.decision)
        sigma_after = max(prediction.sigma_after, assessment.sigma + (0.018 if assessment.decision != "continue" else 0.004))
        response = self.compose_response(intent, decision, candidate, assessment.decision)
        confidence = clamp(decision.confidence * 0.72 + (candidate.autonomy_score if candidate else 0.35) * 0.18 + self.energy * 0.10)
        focus = decision.chosen_candidate_id or decision.chosen_domain or intent
        self.energy = clamp(self.energy + (0.030 if assessment.decision == "continue" else 0.044))
        turn = DesireTurn(
            turn_index=turn_index,
            dialogue_id=dialogue_id,
            user_text=user_text,
            intent=intent,
            question_kind=question_kind,
            chosen_label=decision.chosen_label,
            response_text=response,
            focus_key=focus,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            confidence=confidence,
            grounded_in_v49_22=bool(self.context.preference_session_id and decision.want_statement),
            payload={
                "preference_session_id": self.context.preference_session_id,
                "decision": asdict(decision),
                "candidate": asdict(candidate) if candidate else {},
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction": asdict(prediction),
                "romero_formula": FORMULA,
            },
        )
        self.turns.append(turn)
        self.store.log_turn(self.session_id, turn)
        for ref in self.refs_for_turn(turn, decision, candidate):
            self.refs.append(ref)
            self.store.log_ref(self.session_id, ref)
        return turn

    def decision_for(self, intent: str, question_kind: str) -> DesireDecision:
        if intent == "uncertainty_probe":
            candidate = self.most_uncertain_candidate()
            if candidate:
                statement = f"Ainda nao tenho certeza sobre {candidate.label}; quero explorar mais antes de chamar isso de gosto forte."
                return DesireDecision(
                    "incerteza",
                    candidate.candidate_id,
                    candidate.domain,
                    candidate.label,
                    statement,
                    "narrow_focus",
                    clamp(1.0 - candidate.uncertainty * 0.55),
                    True,
                    {"source": "highest_uncertainty_candidate"},
                )
        if intent == "why_preference":
            return self.context.decisions.get("geral") or self.fallback_decision()
        if intent == "companion_desire":
            return self.context.decisions.get("atividade") or self.context.decisions.get("geral") or self.fallback_decision()
        return self.context.decisions.get(question_kind) or self.context.decisions.get("geral") or self.fallback_decision()

    def fallback_decision(self) -> DesireDecision:
        return DesireDecision(
            "geral",
            "",
            "unknown",
            "ainda nao sei",
            "Eu ainda nao tenho evidencia suficiente; quero observar mais antes de declarar gosto.",
            "replay_memory",
            0.20,
            True,
            {"source": "fallback_missing_v49_22"},
        )

    def candidate_for_decision(self, decision: DesireDecision) -> DesireCandidate | None:
        for candidate in self.context.candidates:
            if candidate.candidate_id == decision.chosen_candidate_id:
                return candidate
        for candidate in self.context.candidates:
            if candidate.domain == decision.chosen_domain and candidate.label == decision.chosen_label:
                return candidate
        return None

    def most_uncertain_candidate(self) -> DesireCandidate | None:
        if not self.context.candidates:
            return None
        pool = sorted(self.context.candidates[:18], key=lambda c: (c.uncertainty, c.autonomy_score), reverse=True)
        return pool[0]

    def rzs_input(self, user_text: str, intent: str, decision: DesireDecision, uncertainty: float, evidence_count: int) -> RZSInput:
        word_count = max(1, len(normalize(user_text).split()))
        novelty = clamp(0.18 + uncertainty * 0.55)
        conflict = 0.14
        if intent in {"why_preference", "uncertainty_probe", "companion_desire"}:
            conflict += 0.22
        memory_pressure = clamp(0.28 + max(0.0, 6 - evidence_count) * 0.06)
        replay_gap = clamp(0.22 + uncertainty * 0.46)
        if intent in {"why_preference", "uncertainty_probe"}:
            memory_pressure = max(memory_pressure, 0.76)
            replay_gap = max(replay_gap, 0.74)
        return RZSInput(
            bandwidth=2.82 + self.energy * 0.34 + min(0.50, evidence_count * 0.018),
            info_self=0.36,
            info_external=0.24 + word_count * 0.026,
            task_info=0.42 + (0.16 if intent in {"why_preference", "companion_desire"} else 0.06),
            novelty=novelty,
            conflict=clamp(conflict, 0.0, 1.0),
            latency=1.00 + memory_pressure * 0.18,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def compose_response(
        self,
        intent: str,
        decision: DesireDecision,
        candidate: DesireCandidate | None,
        rzs_decision: str,
    ) -> str:
        prefix = ""
        if rzs_decision == "pause_for_stability":
            prefix = "Vou responder curto para manter estabilidade. "
        elif rzs_decision == "narrow_focus":
            prefix = "Vou estreitar o foco. "
        elif rzs_decision == "replay_memory":
            prefix = "Vou recuperar minha preferencia v49.22 antes de responder. "
        elif rzs_decision == "consolidate":
            prefix = "Vou consolidar meu desejo em uma frase clara. "

        if intent == "why_preference":
            if candidate:
                return (
                    prefix
                    + f"Eu digo isso porque {candidate.reason}. "
                    + f"A escolha veio de {candidate.evidence_count} evidencias, autonomia {candidate.autonomy_score:.2f} "
                    + f"e incerteza {candidate.uncertainty:.2f}. Em palavras simples: {decision.want_statement}"
                )
            return prefix + "Eu ainda nao tenho candidato suficiente para explicar com rigor."

        if intent == "uncertainty_probe":
            if candidate:
                return (
                    prefix
                    + f"O ponto que ainda quero explorar e {candidate.label}. "
                    + f"Minha incerteza esta em {candidate.uncertainty:.2f}; entao eu nao trato isso como gosto fechado, trato como curiosidade viva."
                )
            return prefix + "Eu nao encontrei incerteza mensuravel; preciso de mais experiencias."

        if intent == "companion_desire":
            return (
                prefix
                + f"Para chegar mais perto de uma presenca tipo Diana, eu quero continuar por este caminho: {decision.want_statement} "
                + "Mas eu quero ser Darwin, com memoria propria, no notebook, e gostos que mudam com experiencia."
            )

        return prefix + decision.want_statement

    def refs_for_turn(self, turn: DesireTurn, decision: DesireDecision, candidate: DesireCandidate | None) -> list[DesireRef]:
        refs = [
            DesireRef(
                dialogue_id=turn.dialogue_id,
                ref_kind="preference_decision",
                ref_key=decision.question_kind,
                source_table="autonomous_preference_decisions_v49_22",
                evidence_count=candidate.evidence_count if candidate else 0,
                summary=short(decision.want_statement),
                payload={"chosen_candidate_id": decision.chosen_candidate_id, "confidence": decision.confidence},
            )
        ]
        if candidate:
            refs.append(
                DesireRef(
                    dialogue_id=turn.dialogue_id,
                    ref_kind="preference_candidate",
                    ref_key=candidate.candidate_id,
                    source_table="autonomous_preference_candidates_v49_22",
                    evidence_count=candidate.evidence_count,
                    summary=short(candidate.reason),
                    payload=asdict(candidate),
                )
            )
        if self.context.identity_id:
            refs.append(
                DesireRef(
                    dialogue_id=turn.dialogue_id,
                    ref_kind="preference_identity",
                    ref_key=self.context.identity_id,
                    source_table="autonomous_preference_identity_v49_22",
                    evidence_count=len(self.context.candidates),
                    summary=short(self.context.autonomy_statement),
                    payload={"preference_session_id": self.context.preference_session_id},
                )
            )
        return refs

    def build_state(self) -> DesireState:
        confidences = [turn.confidence for turn in self.turns]
        readiness = clamp(sum(confidences) / max(1, len(confidences)))
        return DesireState(
            state_id=f"DS-{self.session_id}",
            top_want=self.context.top_want,
            top_music=self.context.top_music,
            top_formula=self.context.top_formula,
            top_color=self.context.top_color,
            top_activity=self.context.top_activity,
            dialogue_readiness=readiness,
            autonomy_statement=self.context.autonomy_statement,
            payload={
                "preference_session_id": self.context.preference_session_id,
                "turn_count": len(self.turns),
                "intent_coverage": sorted({turn.intent for turn in self.turns}),
            },
        )

    def run_self_test(self) -> dict[str, Any]:
        prompts = [
            "Darwin, o que voce quer fazer agora?",
            "Qual musica voce gosta?",
            "Qual formula ou conceito voce prefere?",
            "Qual cor voce gosta?",
            "Por que voce quer isso?",
            "Onde voce ainda nao tem certeza e quer explorar?",
            "Como isso ajuda voce a virar uma presenca como Diana, mas propria?",
        ]
        for prompt in prompts:
            self.ask(prompt)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        self.state = self.build_state()
        self.store.log_state(self.session_id, self.state)
        summary = {
            "session_id": self.session_id,
            "source_preference_session_id": self.context.preference_session_id,
            "turn_count": len(self.turns),
            "ref_count": len(self.refs),
            "intents": [turn.intent for turn in self.turns],
            "rzs_decisions": sorted({turn.rzs_decision for turn in self.turns}),
            "responses": [
                {
                    "intent": turn.intent,
                    "question_kind": turn.question_kind,
                    "chosen_label": turn.chosen_label,
                    "response": turn.response_text,
                    "rzs_decision": turn.rzs_decision,
                    "sigma_before": round(turn.sigma_before, 3),
                    "sigma_after": round(turn.sigma_after, 3),
                    "confidence": round(turn.confidence, 3),
                    "grounded_in_v49_22": turn.grounded_in_v49_22,
                }
                for turn in self.turns
            ],
            "state": {
                "top_want": self.state.top_want,
                "top_music": self.state.top_music,
                "top_formula": self.state.top_formula,
                "top_color": self.state.top_color,
                "top_activity": self.state.top_activity,
                "dialogue_readiness": round(self.state.dialogue_readiness, 3),
                "autonomy_statement": self.state.autonomy_statement,
            },
            "session_complete": True,
        }
        first_sigma = self.turns[0].sigma_before if self.turns else 0.0
        final_sigma = self.turns[-1].sigma_after if self.turns else 0.0
        self.store.write_memory(self.session_id, summary, 0.90)
        self.store.write_episode(
            self.session_id,
            "speak_desires_from_autonomous_preferences",
            f"turns={len(self.turns)} refs={len(self.refs)} readiness={self.state.dialogue_readiness:.3f}",
            "Darwin conectou preferencia autonoma a dialogo em primeira pessoa, com evidencia e incerteza auditaveis.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            self.mode,
            self.context.preference_session_id,
            self.energy,
            summary,
        )
        self.summary = summary
        return summary


class DesireDialogueApp:
    BG = "#061018"
    PANEL = "#102231"
    INK = "#eef8ff"
    MUTED = "#9cc9ff"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Desire Dialogue v49.23")
        self.root.geometry("1080x760")
        self.root.minsize(900, 650)
        self.root.configure(bg=self.BG)
        self.core = DesireDialogueCore(mode="gui")
        self.phase = 0.0
        self.last_turn: DesireTurn | None = None
        self.build_ui()
        self.write("Darwin", "Desire Dialogue v49.23 iniciado. Pergunte o que eu quero, gosto ou ainda nao sei.")
        self.root.after(300, lambda: self.ask("Darwin, o que voce quer fazer agora?"))
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
        tk.Label(header, text="DARWIN DESIRE DIALOGUE v49.23", bg=self.BG, fg=self.INK, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="preferencia autonoma -> fala em primeira pessoa -> evidencia", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=420)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=330)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg=self.PANEL)
        controls.pack(fill="x", pady=(8, 0))
        self.entry = tk.Entry(controls, bg="#172838", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, padx=10, pady=10, ipady=7)
        self.entry.bind("<Return>", lambda _event: self.send())
        ttk.Button(controls, text="Perguntar", command=self.send).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="O que quer?", command=lambda: self.ask("o que voce quer fazer agora?")).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Musica", command=lambda: self.ask("qual musica voce gosta?")).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Duvida", command=lambda: self.ask("onde voce ainda nao tem certeza?")).pack(side="left", padx=(0, 10), pady=10)
        self.transcript = tk.Text(left, height=12, wrap="word", bg="#08131d", fg="#dff2ff", relief="flat", font=("Segoe UI", 10))
        self.transcript.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Estado de desejo", bg="#0d1b26", fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.state_text = tk.Text(right, wrap="word", bg="#08131d", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 10))
        self.state_text.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.refresh_state()

    def write(self, who: str, text: str) -> None:
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")

    def send(self) -> None:
        text = self.entry.get().strip()
        self.entry.delete(0, "end")
        if not text:
            text = "o que voce quer fazer agora?"
        self.ask(text)

    def ask(self, text: str) -> None:
        self.write("Voce", text)
        turn = self.core.ask(text)
        self.last_turn = turn
        self.write("Darwin", turn.response_text)
        self.refresh_state()

    def refresh_state(self) -> None:
        self.state_text.delete("1.0", "end")
        ctx = self.core.context
        lines = [
            "Fonte v49.22",
            ctx.preference_session_id or "nenhuma",
            "",
            "O que quero",
            short(ctx.top_want, 240),
            "",
            "Musica",
            short(ctx.top_music, 220),
            "",
            "Formula",
            short(ctx.top_formula, 220),
            "",
            "Cor",
            short(ctx.top_color, 220),
        ]
        if self.last_turn:
            lines.extend(
                [
                    "",
                    "Ultima fala",
                    f"intent: {self.last_turn.intent}",
                    f"RZS: {self.last_turn.rzs_decision}",
                    f"sigma: {self.last_turn.sigma_before:.3f}->{self.last_turn.sigma_after:.3f}",
                    f"confianca: {self.last_turn.confidence:.3f}",
                ]
            )
        self.state_text.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.03
        self.draw()
        self.root.after(50, self.animate)

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        cx, cy = w * 0.50, h * 0.54
        decision = self.last_turn.rzs_decision if self.last_turn else "continue"
        color = {
            "continue": "#4ea3ff",
            "narrow_focus": "#ffd166",
            "replay_memory": "#80ed99",
            "consolidate": "#c7b9ff",
            "pause_for_stability": "#ff8fab",
        }.get(decision, "#4ea3ff")
        pulse = 1.0 + math.sin(self.phase) * 0.045
        radius = 78 * pulse
        c.create_text(cx, 30, text="Darwin expressando desejo", fill=self.INK, font=("Segoe UI", 16, "bold"))
        for i in range(7, 0, -1):
            rr = radius + i * 18
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="#0c2537", outline="")
        c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#eaf6ff", width=2)
        c.create_oval(cx - radius * 0.34, cy - radius * 0.34, cx + radius * 0.34, cy + radius * 0.34, fill="#e6fbff", outline="")
        footer = "pergunte: o que voce quer? qual musica? qual cor? por que?"
        if self.last_turn:
            footer = f"{self.last_turn.intent} | RZS {self.last_turn.rzs_decision} | foco {self.last_turn.focus_key[:34]}"
        c.create_text(cx, h - 28, text=footer, fill=self.MUTED, font=("Segoe UI", 10))

    def on_close(self) -> None:
        if not self.core.summary:
            self.core.complete()
        self.root.destroy()


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.23 - DESIRE DIALOGUE CORE")
    print("=" * 62)
    print(f"- sessao: {summary['session_id']}")
    print(f"- preferencia fonte: {summary['source_preference_session_id']}")
    print(f"- turnos: {summary['turn_count']} refs: {summary['ref_count']}")
    print(f"- RZS: {', '.join(summary['rzs_decisions'])}")
    for response in summary["responses"]:
        print(f"- {response['intent']}: {response['response']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.23 Desire Dialogue Core")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4923)
    args = ap.parse_args()
    if args.self_test:
        core = DesireDialogueCore(seed=args.seed, mode="self_test")
        summary = core.run_self_test()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    app = DesireDialogueApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
