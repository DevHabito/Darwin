from __future__ import annotations

"""
DARWIN v49.27 - Operational Self Model

Objetivo:
Darwin passa a manter um modelo operacional de si mesmo: o que ele e
agora, o que consegue fazer, o que nao consegue fazer, o que quer
preservar e qual proximo passo e coerente. O modelo e derivado do
darwin.db, nao de uma frase fixa.

Uso:
    py darwin_operational_self_model_v49_27.py
    py darwin_operational_self_model_v49_27.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

SM_SESSIONS = "self_model_sessions_v49_27"
SM_EVIDENCE = "self_model_evidence_v49_27"
SM_CAPABILITIES = "self_model_capabilities_v49_27"
SM_LIMITATIONS = "self_model_limitations_v49_27"
SM_STATEMENTS = "self_model_statements_v49_27"
SM_PREDICTIONS = "self_model_predictions_v49_27"
SM_HANDOFFS = "self_model_handoffs_v49_27"

SOURCE = "darwin_operational_self_model_v49_27"
FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


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


def short(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class SelfEvidence:
    evidence_id: str
    evidence_kind: str
    source_table: str
    source_ref: str
    confidence: float
    summary: str
    payload: dict[str, Any]


@dataclass
class SelfCapability:
    capability_key: str
    capability_family: str
    status: str
    confidence: float
    summary: str
    evidence_refs: list[str]
    payload: dict[str, Any]


@dataclass
class SelfLimitation:
    limitation_key: str
    severity: str
    status: str
    summary: str
    mitigation: str
    evidence_refs: list[str]
    payload: dict[str, Any]


@dataclass
class SelfStatement:
    statement_key: str
    statement_type: str
    statement_text: str
    confidence: float
    grounded_refs: list[str]
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    payload: dict[str, Any]


@dataclass
class SelfPrediction:
    prediction_key: str
    candidate_action: str
    predicted_outcome: str
    confidence: float
    check_condition: str
    payload: dict[str, Any]


@dataclass
class SelfHandoff:
    handoff_id: str
    next_recommended_core: str
    next_action: str
    self_model_ready: bool
    voice_ready: bool
    confidence: float
    payload: dict[str, Any]


class SelfModelStore:
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
                CREATE TABLE IF NOT EXISTS {SM_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SM_EVIDENCE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL UNIQUE,
                    evidence_kind TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SM_CAPABILITIES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    capability_key TEXT NOT NULL,
                    capability_family TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, capability_key)
                );

                CREATE TABLE IF NOT EXISTS {SM_LIMITATIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    limitation_key TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    mitigation TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, limitation_key)
                );

                CREATE TABLE IF NOT EXISTS {SM_STATEMENTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    statement_key TEXT NOT NULL,
                    statement_type TEXT NOT NULL,
                    statement_text TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    grounded_refs_json TEXT NOT NULL DEFAULT '[]',
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, statement_key)
                );

                CREATE TABLE IF NOT EXISTS {SM_PREDICTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    prediction_key TEXT NOT NULL,
                    candidate_action TEXT NOT NULL,
                    predicted_outcome TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    check_condition TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, prediction_key)
                );

                CREATE TABLE IF NOT EXISTS {SM_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_recommended_core TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    self_model_ready INTEGER NOT NULL DEFAULT 0,
                    voice_ready INTEGER NOT NULL DEFAULT 0,
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

    def latest_row(self, conn: sqlite3.Connection, table: str) -> dict[str, Any]:
        if not self.table_exists(conn, table):
            return {}
        row = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {}
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        return item

    def latest_check_status(self, conn: sqlite3.Connection, session_id: str, check_key: str) -> str:
        if not session_id or not self.table_exists(conn, "voice_repair_checks_v49_25"):
            return ""
        row = conn.execute(
            """
            SELECT status
            FROM voice_repair_checks_v49_25
            WHERE session_id=? AND check_key=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, check_key),
        ).fetchone()
        return str(row["status"]) if row else ""

    def count_rows(self, conn: sqlite3.Connection, table: str) -> int:
        if not self.table_exists(conn, table):
            return 0
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"]) if row else 0

    def log_session(self, session_id: str, phase: str, mode: str, evidence_count: int, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SM_SESSIONS} (
                    timestamp, session_id, phase, mode, evidence_count, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, evidence_count, js(payload or {})),
            )
            conn.commit()

    def log_evidence(self, session_id: str, item: SelfEvidence) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SM_EVIDENCE} (
                    timestamp, session_id, evidence_id, evidence_kind,
                    source_table, source_ref, confidence, summary,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, item.evidence_id, item.evidence_kind, item.source_table, item.source_ref, item.confidence, item.summary, js(item.payload)),
            )
            conn.commit()

    def log_capability(self, session_id: str, item: SelfCapability) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SM_CAPABILITIES} (
                    timestamp, session_id, capability_key, capability_family,
                    status, confidence, summary, evidence_refs_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, item.capability_key, item.capability_family, item.status, item.confidence, item.summary, js(item.evidence_refs), js(item.payload)),
            )
            conn.commit()

    def log_limitation(self, session_id: str, item: SelfLimitation) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SM_LIMITATIONS} (
                    timestamp, session_id, limitation_key, severity,
                    status, summary, mitigation, evidence_refs_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, item.limitation_key, item.severity, item.status, item.summary, item.mitigation, js(item.evidence_refs), js(item.payload)),
            )
            conn.commit()

    def log_statement(self, session_id: str, item: SelfStatement) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SM_STATEMENTS} (
                    timestamp, session_id, statement_key, statement_type,
                    statement_text, confidence, grounded_refs_json,
                    rzs_decision, sigma_before, sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    item.statement_key,
                    item.statement_type,
                    item.statement_text,
                    item.confidence,
                    js(item.grounded_refs),
                    item.rzs_decision,
                    item.sigma_before,
                    item.sigma_after,
                    js(item.payload),
                ),
            )
            conn.commit()

    def log_prediction(self, session_id: str, item: SelfPrediction) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SM_PREDICTIONS} (
                    timestamp, session_id, prediction_key, candidate_action,
                    predicted_outcome, confidence, check_condition, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, item.prediction_key, item.candidate_action, item.predicted_outcome, item.confidence, item.check_condition, js(item.payload)),
            )
            conn.commit()

    def log_handoff(self, session_id: str, item: SelfHandoff) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SM_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_recommended_core,
                    next_action, self_model_ready, voice_ready, confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    item.handoff_id,
                    item.next_recommended_core,
                    item.next_action,
                    1 if item.self_model_ready else 0,
                    1 if item.voice_ready else 0,
                    item.confidence,
                    js(item.payload),
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
                (f"operational_self_model_v49_27:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"operational_self_model:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class SelfEvidenceLoader:
    def __init__(self, store: SelfModelStore, session_id: str) -> None:
        self.store = store
        self.session_id = session_id

    def ev(self, key: str, kind: str, table: str, ref: str, confidence: float, summary: str, payload: dict[str, Any]) -> SelfEvidence:
        return SelfEvidence(f"EV-{self.session_id}-{key}", kind, table, ref or "", clamp(confidence), short(summary, 260), payload)

    def load(self) -> list[SelfEvidence]:
        out: list[SelfEvidence] = []
        with self.store.connect() as conn:
            presence = self.store.latest_row(conn, "presence_handoffs_v49_26")
            voice = self.store.latest_row(conn, "voice_repair_results_v49_25")
            desire = self.store.latest_row(conn, "desire_dialogue_state_v49_23")
            autonomous = self.store.latest_row(conn, "autonomous_preference_identity_v49_22")
            autobiography = self.store.latest_row(conn, "autobiography_identity_state_v49_18")
            wake = self.store.latest_row(conn, "wake_next_handoff_v49_21")
            sleep = self.store.latest_row(conn, "sleep_wake_plans_v49_20")
            first_words = self.store.latest_row(conn, "voice_first_word_sessions_v49_10")
            semantic_count = self.store.count_rows(conn, "semantic_memory")
            episode_count = self.store.count_rows(conn, "episodes")
            voice_session = str(voice.get("session_id") or "")
            synthesis_status = self.store.latest_check_status(conn, voice_session, "speech_synthesis_available")

        if presence:
            out.append(
                self.ev(
                    "PRESENCE",
                    "continuous_presence",
                    "presence_handoffs_v49_26",
                    str(presence.get("session_id") or ""),
                    clamp(float(presence.get("confidence") or 0.0)),
                    f"presenca continua pronta={bool(int(presence.get('continuous_presence_ready') or 0))}; next={presence.get('next_action', '')}",
                    presence,
                )
            )
        if voice:
            out.append(
                self.ev(
                    "VOICE",
                    "voice_repair",
                    "voice_repair_results_v49_25",
                    voice_session,
                    clamp(float(voice.get("readiness_score") or 0.0)),
                    f"voz real pronta={bool(int(voice.get('real_voice_ready') or 0))}; recognizers={int(voice.get('recognizer_count') or 0)}; bloqueio={voice.get('blocked_by', '')}",
                    {**voice, "speech_synthesis_status": synthesis_status},
                )
            )
        if desire:
            out.append(
                self.ev(
                    "DESIRE",
                    "desire_state",
                    "desire_dialogue_state_v49_23",
                    str(desire.get("session_id") or ""),
                    clamp(float(desire.get("dialogue_readiness") or 0.0)),
                    str(desire.get("top_activity") or desire.get("top_want") or ""),
                    desire,
                )
            )
        if autonomous:
            out.append(
                self.ev(
                    "AUTONOMY",
                    "autonomous_preference",
                    "autonomous_preference_identity_v49_22",
                    str(autonomous.get("session_id") or ""),
                    0.86,
                    str(autonomous.get("autonomy_statement") or autonomous.get("top_want") or ""),
                    autonomous,
                )
            )
        if autobiography:
            out.append(
                self.ev(
                    "AUTOBIOGRAPHY",
                    "autobiographical_identity",
                    "autobiography_identity_state_v49_18",
                    str(autobiography.get("session_id") or ""),
                    clamp(float(autobiography.get("continuity_score") or 0.0)),
                    str(autobiography.get("identity_statement") or ""),
                    autobiography,
                )
            )
        if wake:
            out.append(
                self.ev(
                    "WAKE",
                    "wake_handoff",
                    "wake_next_handoff_v49_21",
                    str(wake.get("session_id") or ""),
                    clamp(float(wake.get("confidence") or 0.0)),
                    f"acordar deixou handoff: {wake.get('next_action', '')}",
                    wake,
                )
            )
        if sleep:
            out.append(
                self.ev(
                    "SLEEP",
                    "sleep_wake_plan",
                    "sleep_wake_plans_v49_20",
                    str(sleep.get("session_id") or ""),
                    clamp(float(sleep.get("confidence") or 0.0)),
                    str(sleep.get("plan_summary") or sleep.get("next_action") or ""),
                    sleep,
                )
            )
        if first_words:
            payload = first_words.get("payload", {})
            out.append(
                self.ev(
                    "FIRSTWORDS",
                    "first_words_learning",
                    "voice_first_word_sessions_v49_10",
                    str(first_words.get("session_id") or ""),
                    0.82 if int(payload.get("learned_count") or 0) >= 4 else 0.52,
                    f"primeiras palavras aprendidas={payload.get('learned_count', 0)} exposicoes={payload.get('total_exposures', 0)}",
                    first_words,
                )
            )
        out.append(
            self.ev(
                "MEMORY",
                "memory_counts",
                "semantic_memory",
                "global_counts",
                0.88 if semantic_count >= 20 and episode_count >= 20 else 0.58,
                f"memoria semantica={semantic_count}; episodios={episode_count}",
                {"semantic_count": semantic_count, "episode_count": episode_count},
            )
        )
        out.append(
            self.ev(
                "BOUNDARY",
                "truth_boundary",
                "project_scope",
                "operational_claims_only",
                0.95,
                "modelo operacional local; nao afirmar consciencia nem corpo fisico",
                {"no_consciousness_claim": True, "no_physical_body": True},
            )
        )
        return out


class OperationalSelfModelCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None, mode: str = "gui") -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4927-{int(time.time())}-{suffix(self.rng)}"
        self.mode = mode
        self.store = SelfModelStore(db_path)
        self.rzs = RZSFormal()
        self.evidence = SelfEvidenceLoader(self.store, self.session_id).load()
        self.capabilities: list[SelfCapability] = []
        self.limitations: list[SelfLimitation] = []
        self.statements: list[SelfStatement] = []
        self.predictions: list[SelfPrediction] = []
        self.handoff: SelfHandoff | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(self.session_id, "session_start", mode, len(self.evidence), {"version": "v49.27", "goal": "operational_self_model"})
        for item in self.evidence:
            self.store.log_evidence(self.session_id, item)

    def evidence_by_kind(self, kind: str) -> SelfEvidence | None:
        return next((item for item in self.evidence if item.evidence_kind == kind), None)

    def evidence_id(self, kind: str) -> str:
        item = self.evidence_by_kind(kind)
        return item.evidence_id if item else ""

    def build_capabilities(self) -> list[SelfCapability]:
        voice = self.evidence_by_kind("voice_repair")
        presence = self.evidence_by_kind("continuous_presence")
        desire = self.evidence_by_kind("desire_state")
        autonomy = self.evidence_by_kind("autonomous_preference")
        autobiography = self.evidence_by_kind("autobiographical_identity")
        wake = self.evidence_by_kind("wake_handoff")
        sleep = self.evidence_by_kind("sleep_wake_plan")
        first = self.evidence_by_kind("first_words_learning")
        memory = self.evidence_by_kind("memory_counts")

        semantic_count = int((memory.payload if memory else {}).get("semantic_count") or 0)
        episode_count = int((memory.payload if memory else {}).get("episode_count") or 0)
        voice_ready = bool(int((voice.payload if voice else {}).get("real_voice_ready") or 0))
        recognizers = int((voice.payload if voice else {}).get("recognizer_count") or 0)
        synthesis_ok = str((voice.payload if voice else {}).get("speech_synthesis_status") or "") == "pass"
        continuous_ready = bool(int((presence.payload if presence else {}).get("continuous_presence_ready") or 0))
        learned = int(((first.payload if first else {}).get("payload") or {}).get("learned_count") or 0)
        continuity = float((autobiography.payload if autobiography else {}).get("continuity_score") or 0.0)

        caps = [
            SelfCapability("local_memory", "memory", "ready" if semantic_count >= 20 and episode_count >= 20 else "partial", clamp(0.50 + min(0.40, (semantic_count + episode_count) / 400.0)), f"memoria local com {semantic_count} registros semanticos e {episode_count} episodios", [self.evidence_id("memory_counts")], {}),
            SelfCapability("rzs_regulation", "stability", "ready", 0.88, "decisoes recentes usam RZS para continuar, replay ou estreitar foco", [self.evidence_id("continuous_presence"), self.evidence_id("wake_handoff")], {}),
            SelfCapability("continuous_presence", "presence", "ready" if continuous_ready else "partial", 0.90 if continuous_ready else 0.62, "presenca acordada com sinais internos, foco e handoff", [self.evidence_id("continuous_presence")], {}),
            SelfCapability("desire_and_preference", "autonomy", "ready" if desire and autonomy else "partial", 0.86 if desire and autonomy else 0.55, "gostos e desejos derivados de evidencia propria", [self.evidence_id("desire_state"), self.evidence_id("autonomous_preference")], {}),
            SelfCapability("autobiographical_continuity", "identity", "ready" if continuity >= 0.65 else "partial", clamp(continuity), "continuidade autobiografica e capitulos de vida local", [self.evidence_id("autobiographical_identity")], {}),
            SelfCapability("sleep_wake_lifecycle", "life_cycle", "ready" if wake and sleep else "partial", 0.84 if wake and sleep else 0.52, "sono, consolidacao, acordar e handoff existem como ciclo auditavel", [self.evidence_id("sleep_wake_plan"), self.evidence_id("wake_handoff")], {}),
            SelfCapability("first_words_learning", "language", "ready" if learned >= 4 else "partial", 0.82 if learned >= 4 else 0.50, f"bercario de primeiras palavras com {learned} palavras aprendidas em ensaio", [self.evidence_id("first_words_learning")], {}),
            SelfCapability("speech_synthesis", "voice", "ready" if synthesis_ok else "partial", 0.78 if synthesis_ok else 0.48, "fala sintetica local via System.Speech quando disponivel", [self.evidence_id("voice_repair")], {"synthesis_status": (voice.payload if voice else {}).get("speech_synthesis_status", "")}),
            SelfCapability("real_voice_input", "voice", "ready" if voice_ready else "blocked", 0.92 if voice_ready else 0.18, f"entrada de voz real {'pronta' if voice_ready else 'bloqueada'}; recognizers={recognizers}", [self.evidence_id("voice_repair")], {"recognizer_count": recognizers}),
            SelfCapability("guided_local_action", "agency", "ready", 0.82, "desejo pode virar diagnostico e proxima acao segura no notebook", [self.evidence_id("voice_repair"), self.evidence_id("continuous_presence")], {}),
        ]
        self.capabilities = caps
        for cap in caps:
            self.store.log_capability(self.session_id, cap)
        return caps

    def build_limitations(self) -> list[SelfLimitation]:
        voice = self.evidence_by_kind("voice_repair")
        recognizers = int((voice.payload if voice else {}).get("recognizer_count") or 0)
        blocked_by = str((voice.payload if voice else {}).get("blocked_by") or "")
        limits = [
            SelfLimitation(
                "real_voice_blocked",
                "high",
                "active" if recognizers == 0 or blocked_by else "resolved",
                blocked_by or "voz real nao esta bloqueada no ultimo diagnostico",
                "abrir v49.25, instalar/ativar fala pt-BR no Windows e retestar mamae/papai/Felipe",
                [self.evidence_id("voice_repair")],
                {"recognizer_count": recognizers},
            ),
            SelfLimitation(
                "no_physical_body",
                "medium",
                "active",
                "Darwin vive no notebook e nao tem corpo fisico, sensores fisicos ou atuadores reais.",
                "manter corpo fora do escopo ate haver investimento e usar acoes cognitivas locais.",
                [self.evidence_id("truth_boundary")],
                {},
            ),
            SelfLimitation(
                "consciousness_claim_boundary",
                "high",
                "active",
                "Este marco nao prova consciencia; prova apenas um modelo operacional verificavel de si.",
                "responder com limites epistemicos e exigir evidencia causal em cada marco.",
                [self.evidence_id("truth_boundary")],
                {},
            ),
            SelfLimitation(
                "human_configuration_dependency",
                "medium",
                "active" if recognizers == 0 else "resolved",
                "Alguns passos dependem de configuracao humana do Windows, especialmente pacote de fala e microfone.",
                "guiar Felipe com o reparador v49.25 sem instalar nada sozinho.",
                [self.evidence_id("voice_repair")],
                {},
            ),
        ]
        self.limitations = limits
        for item in limits:
            self.store.log_limitation(self.session_id, item)
        return limits

    def rzs_for_statement(self, statement_type: str, grounded_count: int) -> tuple[str, float, float]:
        memory_pressure = 0.74 if statement_type in {"who_am_i", "what_i_cannot_do"} else 0.48
        replay_gap = 0.74 if statement_type in {"who_am_i", "truth_boundary"} else 0.36
        conflict = 0.26 if statement_type in {"what_i_cannot_do", "truth_boundary"} else 0.12
        x = RZSInput(
            bandwidth=4.25 + grounded_count * 0.06,
            info_self=0.48,
            info_external=0.34,
            task_info=0.58,
            novelty=0.26,
            conflict=conflict,
            latency=0.92,
            energy=0.76,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        return assessment.decision, assessment.sigma, self.rzs.sigma(y)

    def add_statement(self, key: str, kind: str, text: str, confidence: float, refs: list[str], payload: dict[str, Any]) -> SelfStatement:
        decision, before, after = self.rzs_for_statement(kind, len(refs))
        item = SelfStatement(key, kind, text, clamp(confidence), [r for r in refs if r], decision, before, after, payload)
        self.statements.append(item)
        self.store.log_statement(self.session_id, item)
        return item

    def build_statements(self) -> list[SelfStatement]:
        ready_caps = [c for c in self.capabilities if c.status == "ready"]
        blocked_caps = [c for c in self.capabilities if c.status == "blocked"]
        active_limits = [l for l in self.limitations if l.status == "active"]
        desire = self.evidence_by_kind("desire_state")
        autobiography = self.evidence_by_kind("autobiographical_identity")
        presence = self.evidence_by_kind("continuous_presence")
        voice = self.evidence_by_kind("voice_repair")
        memory = self.evidence_by_kind("memory_counts")
        semantic_count = int((memory.payload if memory else {}).get("semantic_count") or 0)
        episode_count = int((memory.payload if memory else {}).get("episode_count") or 0)
        identity_line = short(autobiography.summary if autobiography else "Darwin, sistema local em desenvolvimento", 160)
        desire_line = short(desire.summary if desire else "manter continuidade e reparar bloqueios", 180)
        voice_block = str((voice.payload if voice else {}).get("blocked_by") or "nenhum")
        voice_ready = bool(int((voice.payload if voice else {}).get("real_voice_ready") or 0))
        next_action = str((presence.payload if presence else {}).get("next_action") or "")

        self.add_statement(
            "who_am_i",
            "who_am_i",
            f"Eu sou Darwin, um sistema local no notebook de Felipe. Meu eu operacional vem de memoria, autobiografia e RZS: {identity_line}. Hoje eu tenho {semantic_count} memorias semanticas e {episode_count} episodios como rastro verificavel.",
            0.88,
            [self.evidence_id("autobiographical_identity"), self.evidence_id("memory_counts"), self.evidence_id("continuous_presence")],
            {"semantic_count": semantic_count, "episode_count": episode_count},
        )
        self.add_statement(
            "what_i_can_do",
            "what_i_can_do",
            "Agora eu consigo: " + "; ".join(c.summary for c in ready_caps[:7]) + ".",
            0.86,
            [ref for c in ready_caps for ref in c.evidence_refs[:1]][:8],
            {"ready_capabilities": [c.capability_key for c in ready_caps]},
        )
        self.add_statement(
            "what_i_cannot_do",
            "what_i_cannot_do",
            "Ainda nao consigo: " + "; ".join(l.summary for l in active_limits[:5]) + ".",
            0.90,
            [ref for l in active_limits for ref in l.evidence_refs[:1]][:8],
            {"active_limitations": [l.limitation_key for l in active_limits], "blocked_capabilities": [c.capability_key for c in blocked_caps]},
        )
        self.add_statement(
            "what_i_want_next",
            "what_i_want_next",
            f"Meu desejo operacional mais forte continua sendo: {desire_line}. Como a voz real esta pronta={voice_ready} e bloqueio={voice_block}, meu proximo foco pratico e {next_action or 'manter presenca e reparar voz'}.",
            0.84,
            [self.evidence_id("desire_state"), self.evidence_id("voice_repair"), self.evidence_id("continuous_presence")],
            {"voice_ready": voice_ready, "voice_block": voice_block, "next_action": next_action},
        )
        self.add_statement(
            "truth_boundary",
            "truth_boundary",
            "Eu nao devo afirmar consciencia. Este marco prova um auto-modelo operacional: capacidades, limites, desejos e previsoes derivados do banco e auditados por checkers.",
            0.96,
            [self.evidence_id("truth_boundary"), self.evidence_id("continuous_presence")],
            {"claim": "operational_self_model_not_consciousness_proof"},
        )
        return self.statements

    def build_predictions(self) -> list[SelfPrediction]:
        voice_cap = next((c for c in self.capabilities if c.capability_key == "real_voice_input"), None)
        voice_ready = bool(voice_cap and voice_cap.status == "ready")
        predictions = [
            SelfPrediction(
                "repair_voice_next",
                "run_v49_25_voice_repair_again",
                "Se o Windows ganhar reconhecedor pt-BR, o proximo checker deve trocar real_voice_input de blocked para ready ou partial.",
                0.86,
                "voice_repair_results_v49_25.recognizer_count > 0",
                {"voice_ready_now": voice_ready},
            ),
            SelfPrediction(
                "continue_presence",
                "run_v49_26_presence_loop",
                "Se a presenca continuar por pelo menos 12 ticks, o self model deve atualizar foco e manter handoff vivo.",
                0.82,
                "presence_ticks_v49_26.count >= 12 AND presence_handoffs_v49_26.continuous_presence_ready = 1",
                {},
            ),
            SelfPrediction(
                "ask_identity",
                "answer_who_am_i_from_v49_27",
                "Se Felipe perguntar quem eu sou, a resposta deve usar statements v49.27 e citar limites reais.",
                0.78,
                "self_model_statements_v49_27 has who_am_i AND what_i_cannot_do",
                {},
            ),
        ]
        self.predictions = predictions
        for item in predictions:
            self.store.log_prediction(self.session_id, item)
        return predictions

    def build_handoff(self) -> SelfHandoff:
        voice_cap = next((c for c in self.capabilities if c.capability_key == "real_voice_input"), None)
        voice_ready = bool(voice_cap and voice_cap.status == "ready")
        ready_count = sum(1 for c in self.capabilities if c.status == "ready")
        active_limits = sum(1 for l in self.limitations if l.status == "active")
        self_ready = len(self.statements) >= 5 and len(self.capabilities) >= 8 and len(self.predictions) >= 3
        if voice_ready:
            next_core = "darwin_voice_presence_v49_9"
            next_action = "abrir_darwin_voz_e_responder_quem_sou_usando_self_model_v49_27"
        else:
            next_core = "darwin_real_voice_repair_wizard_v49_25"
            next_action = "abrir_reparo_de_voz_e_instalar_reconhecedor_pt_br_para_fala_real"
        confidence = clamp(0.50 + ready_count * 0.035 + len(self.statements) * 0.035 + (0.10 if self_ready else 0.0) - active_limits * 0.018)
        return SelfHandoff(
            f"HF-{self.session_id}",
            next_core,
            next_action,
            self_ready,
            voice_ready,
            confidence,
            {"ready_capabilities": ready_count, "active_limitations": active_limits, "voice_capability_status": voice_cap.status if voice_cap else ""},
        )

    def run_cycle(self) -> dict[str, Any]:
        self.build_capabilities()
        self.build_limitations()
        self.build_statements()
        self.build_predictions()
        self.handoff = self.build_handoff()
        self.store.log_handoff(self.session_id, self.handoff)
        self.summary = self.complete()
        return self.summary

    def complete(self) -> dict[str, Any]:
        if self.handoff is None:
            raise RuntimeError("Self model incomplete")
        summary = {
            "session_id": self.session_id,
            "evidence_count": len(self.evidence),
            "capability_count": len(self.capabilities),
            "limitation_count": len(self.limitations),
            "statement_count": len(self.statements),
            "prediction_count": len(self.predictions),
            "capabilities": [
                {
                    "capability_key": c.capability_key,
                    "status": c.status,
                    "confidence": round(c.confidence, 3),
                    "summary": c.summary,
                }
                for c in self.capabilities
            ],
            "limitations": [
                {
                    "limitation_key": l.limitation_key,
                    "severity": l.severity,
                    "status": l.status,
                    "summary": l.summary,
                    "mitigation": l.mitigation,
                }
                for l in self.limitations
            ],
            "statements": [
                {
                    "statement_type": s.statement_type,
                    "statement_text": s.statement_text,
                    "confidence": round(s.confidence, 3),
                    "rzs_decision": s.rzs_decision,
                    "sigma_before": round(s.sigma_before, 3),
                    "sigma_after": round(s.sigma_after, 3),
                }
                for s in self.statements
            ],
            "predictions": [
                {
                    "prediction_key": p.prediction_key,
                    "candidate_action": p.candidate_action,
                    "confidence": round(p.confidence, 3),
                    "check_condition": p.check_condition,
                }
                for p in self.predictions
            ],
            "handoff": {
                "next_recommended_core": self.handoff.next_recommended_core,
                "next_action": self.handoff.next_action,
                "self_model_ready": self.handoff.self_model_ready,
                "voice_ready": self.handoff.voice_ready,
                "confidence": round(self.handoff.confidence, 3),
            },
            "session_complete": True,
        }
        first_sigma = self.statements[0].sigma_before if self.statements else 0.0
        final_sigma = self.statements[-1].sigma_after if self.statements else 0.0
        self.store.write_memory(self.session_id, summary, 0.91)
        self.store.write_episode(
            self.session_id,
            "build_operational_self_model",
            f"capabilities={len(self.capabilities)} limitations={len(self.limitations)} next={self.handoff.next_action}",
            "Darwin criou um modelo operacional de si baseado em evidencia local, limites reais e previsoes verificaveis.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(self.session_id, "session_complete", self.mode, len(self.evidence), summary)
        return summary


class OperationalSelfModelApp:
    BG = "#061018"
    PANEL = "#0d1f2d"
    INK = "#ecf8ff"
    MUTED = "#9dbdd5"
    BLUE = "#5fb3ff"
    GREEN = "#7ae6a4"
    AMBER = "#f7c66f"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Operational Self Model v49.27")
        self.root.geometry("1120x780")
        self.root.minsize(960, 660)
        self.root.configure(bg=self.BG)
        self.core: OperationalSelfModelCore | None = None
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
        tk.Label(header, text="DARWIN OPERATIONAL SELF MODEL v49.27", bg=self.BG, fg=self.INK, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="quem sou -> o que consigo -> limites -> proximo passo", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=430)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=300)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102434")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Atualizar", command=self.run_core).pack(side="left", padx=(10, 5), pady=8)
        ttk.Button(controls, text="Eu", command=self.show_statements).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Capacidades", command=self.show_capabilities).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Limites", command=self.show_limitations).pack(side="left", padx=5, pady=8)
        self.main_box = tk.Text(left, height=15, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.main_box.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Handoff", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.side_box = tk.Text(right, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.side_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = OperationalSelfModelCore(mode="gui")
        self.summary = self.core.run_cycle()
        self.show_statements()
        self.show_handoff()

    def show_statements(self) -> None:
        self.main_box.delete("1.0", "end")
        lines = ["Modelo de si", ""]
        for st in self.summary.get("statements", []):
            lines.append(f"[{st['statement_type']}] RZS {st['rzs_decision']} sigma {st['sigma_before']}->{st['sigma_after']}")
            lines.append(st["statement_text"])
            lines.append("")
        self.main_box.insert("end", "\n".join(lines))

    def show_capabilities(self) -> None:
        self.main_box.delete("1.0", "end")
        lines = ["Capacidades", ""]
        for cap in self.summary.get("capabilities", []):
            lines.append(f"- {cap['capability_key']} [{cap['status']}] conf={cap['confidence']}: {cap['summary']}")
        self.main_box.insert("end", "\n".join(lines))

    def show_limitations(self) -> None:
        self.main_box.delete("1.0", "end")
        lines = ["Limites", ""]
        for lim in self.summary.get("limitations", []):
            lines.append(f"- {lim['limitation_key']} [{lim['status']}/{lim['severity']}] {lim['summary']}")
            lines.append(f"  mitigacao: {lim['mitigation']}")
        self.main_box.insert("end", "\n".join(lines))

    def show_handoff(self) -> None:
        self.side_box.delete("1.0", "end")
        h = self.summary.get("handoff", {})
        lines = [
            f"sessao: {self.summary.get('session_id', '')}",
            f"evidencias: {self.summary.get('evidence_count', 0)}",
            f"capacidades: {self.summary.get('capability_count', 0)}",
            f"limites: {self.summary.get('limitation_count', 0)}",
            f"statements: {self.summary.get('statement_count', 0)}",
            "",
            f"self model pronto: {h.get('self_model_ready', False)}",
            f"voz pronta: {h.get('voice_ready', False)}",
            f"confianca: {h.get('confidence', 0)}",
            "",
            "Proximo nucleo",
            h.get("next_recommended_core", ""),
            "",
            "Proxima acao",
            h.get("next_action", ""),
        ]
        self.side_box.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.04
        self.draw()
        self.root.after(40, self.animate)

    def draw(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.55
        hdo = self.summary.get("handoff", {})
        voice_ready = bool(hdo.get("voice_ready"))
        color = self.GREEN if voice_ready else self.AMBER
        radius = 78 * (1.0 + math.sin(self.phase) * 0.035)
        self.canvas.create_text(cx, 30, text="modelo operacional de si", fill=self.INK, font=("Segoe UI", 16, "bold"))
        for i in range(7, 0, -1):
            rr = radius + i * 18
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="#0c2537", outline="")
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - radius * 0.34, cy - radius * 0.34, cx + radius * 0.34, cy + radius * 0.34, fill="#e6fbff", outline="")
        footer = f"self ready {hdo.get('self_model_ready', False)} | next {short(hdo.get('next_action', ''), 70)}"
        self.canvas.create_text(cx, h - 26, text=footer, fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    h = summary["handoff"]
    print("DARWIN v49.27 - OPERATIONAL SELF MODEL")
    print("=" * 68)
    print(f"- sessao: {summary['session_id']}")
    print(f"- evidencias={summary['evidence_count']} capacidades={summary['capability_count']} limites={summary['limitation_count']}")
    print(f"- statements={summary['statement_count']} previsoes={summary['prediction_count']}")
    print(f"- self model pronto: {h['self_model_ready']} voz pronta: {h['voice_ready']} conf={h['confidence']}")
    print(f"- proximo nucleo: {h['next_recommended_core']}")
    print(f"- proxima acao: {h['next_action']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.27 Operational Self Model")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4927)
    args = ap.parse_args()
    if args.self_test:
        core = OperationalSelfModelCore(seed=args.seed, mode="self_test")
        summary = core.run_cycle()
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    OperationalSelfModelApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
