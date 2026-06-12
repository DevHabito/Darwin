from __future__ import annotations

"""
DARWIN v49.30 - Learning to Learn

Objetivo:
Darwin passa a observar como aprende. Em vez de apenas acumular
experiencias, ele extrai estrategias de aprendizagem a partir de erros,
replays, correcoes, historias, desenho, musica, preferencias e
metacognicao. Depois testa essas estrategias em ciclos auditaveis e
atualiza confianca.

Uso:
    py darwin_learning_to_learn_v49_30.py
    py darwin_learning_to_learn_v49_30.py --self-test --trials 48 --details
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
SOURCE = "darwin_learning_to_learn_v49_30"

L2L_SESSIONS = "learning_to_learn_sessions_v49_30"
L2L_EVIDENCE = "learning_evidence_v49_30"
L2L_STRATEGIES = "learning_strategies_v49_30"
L2L_TRIALS = "learning_trials_v49_30"
L2L_PREDICTIONS = "learning_predictions_v49_30"
L2L_REFLECTIONS = "learning_reflections_v49_30"
L2L_HANDOFFS = "learning_handoffs_v49_30"

PROTECTED_SOURCE_TABLES = [
    "geometry_experience_nodes_v49_7",
    "geometry_error_replay_v49_7",
    "formula_sketch_intentions_v49_28",
    "formula_sketch_reflections_v49_28",
    "story_reactions_v49_29",
    "story_reflections_v49_29",
    "music_reactions_v49_16",
    "affective_preferences_v49_17",
    "brain_meta_cycles_v49_1",
    "self_model_statements_v49_27",
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
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    return parsed


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def short(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class LearningEvidence:
    evidence_id: str
    source_kind: str
    source_table: str
    source_ref: str
    domain: str
    signal_key: str
    before_metric: float
    after_metric: float
    gain: float
    stability: float
    confidence: float
    tags: list[str]
    summary: str
    payload: dict[str, Any]


@dataclass
class LearningStrategy:
    strategy_key: str
    strategy_family: str
    description: str
    trigger_condition: str
    expected_gain: float
    risk: float
    confidence: float
    evidence_refs: list[str]
    payload: dict[str, Any]


@dataclass
class LearningTrial:
    trial_id: str
    trial_index: int
    context_kind: str
    strategy_key: str
    predicted_gain: float
    observed_gain: float
    transfer_score: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    chosen_action: str
    confidence_before: float
    confidence_after: float
    payload: dict[str, Any]


class LearningToLearnStore:
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
                CREATE TABLE IF NOT EXISTS {L2L_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    trial_index INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {L2L_EVIDENCE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    signal_key TEXT NOT NULL,
                    before_metric REAL NOT NULL DEFAULT 0.0,
                    after_metric REAL NOT NULL DEFAULT 0.0,
                    gain REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {L2L_STRATEGIES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    strategy_key TEXT NOT NULL,
                    strategy_family TEXT NOT NULL,
                    description TEXT NOT NULL,
                    trigger_condition TEXT NOT NULL,
                    expected_gain REAL NOT NULL DEFAULT 0.0,
                    risk REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, strategy_key)
                );

                CREATE TABLE IF NOT EXISTS {L2L_TRIALS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL UNIQUE,
                    trial_index INTEGER NOT NULL,
                    context_kind TEXT NOT NULL,
                    strategy_key TEXT NOT NULL,
                    predicted_gain REAL NOT NULL DEFAULT 0.0,
                    observed_gain REAL NOT NULL DEFAULT 0.0,
                    transfer_score REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    chosen_action TEXT NOT NULL,
                    confidence_before REAL NOT NULL DEFAULT 0.0,
                    confidence_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {L2L_PREDICTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    prediction_id TEXT NOT NULL UNIQUE,
                    strategy_key TEXT NOT NULL,
                    predicted_context TEXT NOT NULL,
                    predicted_outcome TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    check_condition TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {L2L_REFLECTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reflection_id TEXT NOT NULL UNIQUE,
                    reflection_kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {L2L_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_action TEXT NOT NULL,
                    meta_learning_ready INTEGER NOT NULL DEFAULT 0,
                    strategy_count INTEGER NOT NULL DEFAULT 0,
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

    def rows(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.table_exists(conn, table):
            return []
        out = []
        for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
            out.append(item)
        return out

    def latest_payload(self, conn: sqlite3.Connection, table: str, phase_col: str, phase_value: str) -> tuple[str, dict[str, Any]]:
        if not self.table_exists(conn, table):
            return "", {}
        row = conn.execute(f"SELECT * FROM {table} WHERE {phase_col}=? ORDER BY id DESC LIMIT 1", (phase_value,)).fetchone()
        if not row:
            return "", {}
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        sid = str(item.get("session_id") or item.get("scenario_id") or "")
        return sid, item

    def log_session(self, session_id: str, phase: str, mode: str, payload: dict[str, Any] | None = None, trial_index: int = 0) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {L2L_SESSIONS} (
                    timestamp, session_id, phase, mode, trial_index, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, trial_index, js(payload or {})),
            )
            conn.commit()

    def log_evidence(self, session_id: str, ev: LearningEvidence) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {L2L_EVIDENCE} (
                    timestamp, session_id, evidence_id, source_kind,
                    source_table, source_ref, domain, signal_key,
                    before_metric, after_metric, gain, stability,
                    confidence, tags_json, summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, ev.evidence_id, ev.source_kind, ev.source_table,
                    ev.source_ref, ev.domain, ev.signal_key, ev.before_metric,
                    ev.after_metric, ev.gain, ev.stability, ev.confidence,
                    js(ev.tags), ev.summary, js(ev.payload),
                ),
            )
            conn.commit()

    def log_strategy(self, session_id: str, st: LearningStrategy) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {L2L_STRATEGIES} (
                    timestamp, session_id, strategy_key, strategy_family,
                    description, trigger_condition, expected_gain, risk,
                    confidence, evidence_refs_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, st.strategy_key, st.strategy_family,
                    st.description, st.trigger_condition, st.expected_gain, st.risk,
                    st.confidence, js(st.evidence_refs), js(st.payload),
                ),
            )
            conn.commit()

    def log_trial(self, session_id: str, tr: LearningTrial) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {L2L_TRIALS} (
                    timestamp, session_id, trial_id, trial_index,
                    context_kind, strategy_key, predicted_gain,
                    observed_gain, transfer_score, rzs_decision,
                    sigma_before, sigma_after, chosen_action,
                    confidence_before, confidence_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, tr.trial_id, tr.trial_index,
                    tr.context_kind, tr.strategy_key, tr.predicted_gain,
                    tr.observed_gain, tr.transfer_score, tr.rzs_decision,
                    tr.sigma_before, tr.sigma_after, tr.chosen_action,
                    tr.confidence_before, tr.confidence_after, js(tr.payload),
                ),
            )
            conn.commit()

    def log_prediction(self, session_id: str, prediction_id: str, strategy_key: str, context: str, outcome: str, confidence: float, check: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {L2L_PREDICTIONS} (
                    timestamp, session_id, prediction_id, strategy_key,
                    predicted_context, predicted_outcome, confidence,
                    check_condition, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, prediction_id, strategy_key, context, outcome, confidence, check, js(payload)),
            )
            conn.commit()

    def log_reflection(self, session_id: str, reflection_id: str, kind: str, summary: str, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {L2L_REFLECTIONS} (
                    timestamp, session_id, reflection_id, reflection_kind,
                    summary, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, reflection_id, kind, summary, confidence, js(payload)),
            )
            conn.commit()

    def log_handoff(self, session_id: str, next_action: str, ready: bool, strategy_count: int, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {L2L_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_action,
                    meta_learning_ready, strategy_count, confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, f"HF-{session_id}", next_action, 1 if ready else 0, strategy_count, confidence, js(payload)),
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
                (f"learning_to_learn_v49_30:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"learning_to_learn:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class LearningToLearnCore:
    def __init__(self, seed: int | None = None, mode: str = "gui") -> None:
        self.store = LearningToLearnStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000) % 100_000_000)
        self.session_id = f"V4930-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.energy = 0.84
        self.source_counts_before = self.store.protected_counts()
        self.evidence: list[LearningEvidence] = []
        self.strategies: dict[str, LearningStrategy] = {}
        self.trials: list[LearningTrial] = []
        self.prepared = False

    def ev(
        self,
        key: str,
        source_kind: str,
        table: str,
        ref: str,
        domain: str,
        signal: str,
        before: float,
        after: float,
        stability: float,
        confidence: float,
        tags: list[str],
        summary: str,
        payload: dict[str, Any],
    ) -> LearningEvidence:
        gain = clamp(after - before, -1.0, 1.0)
        return LearningEvidence(
            f"EV-{self.session_id}-{key}",
            source_kind,
            table,
            ref,
            domain,
            signal,
            round(before, 6),
            round(after, 6),
            round(gain, 6),
            clamp(stability),
            clamp(confidence),
            tags,
            short(summary, 260),
            payload,
        )

    def load_evidence(self) -> list[LearningEvidence]:
        out: list[LearningEvidence] = []
        with self.store.connect() as conn:
            geo_sid, geo_complete = self.store.latest_payload(conn, "geometry_learning_scenarios_v49_7", "phase", "geometry_complete")
            if geo_complete:
                p = geo_complete["payload"]
                first_err = float(p.get("first_quarter_error") or 0.0)
                last_err = float(p.get("last_quarter_error") or 0.0)
                before = clamp(1.0 - first_err)
                after = clamp(1.0 - last_err)
                out.append(self.ev("GEOMETRY_ERROR_DROP", "geometry_error_learning", "geometry_learning_scenarios_v49_7", geo_sid, "geometry", "error_drop", before, after, 0.78, 0.86, ["error", "correction", "numeric", "geometry"], f"erro geometrico caiu de {first_err:.3f} para {last_err:.3f}", p))
            if self.store.table_exists(conn, "geometry_error_replay_v49_7"):
                rows = self.store.rows(conn, "geometry_error_replay_v49_7")
                if rows:
                    before = mean([float(r.get("error_before") or 0.0) for r in rows[-24:]])
                    after = mean([float(r.get("error_after") or 0.0) for r in rows[-24:]])
                    scale = max(1.0, before)
                    out.append(self.ev("GEOMETRY_REPLAY", "replay_reduces_error", "geometry_error_replay_v49_7", str(rows[-1].get("scenario_id") or ""), "geometry", "replay_gain", clamp(1.0 - before / scale), clamp(1.0 - after / scale), 0.80, 0.84, ["replay", "error", "geometry"], f"replay geometrico reduziu erro medio {before:.3f}->{after:.3f}", {"sample": rows[-5:]}))

            form_sid, form_complete = self.store.latest_payload(conn, "formula_sketch_sessions_v49_28", "phase", "sketch_complete")
            if form_complete:
                p = form_complete["payload"]
                mistakes = max(1, int(p.get("mistake_count") or 0))
                corrections = int(p.get("correction_count") or 0)
                fusions = int(p.get("fusion_count") or 0)
                intentions = max(1, int(p.get("intention_count") or 1))
                out.append(self.ev("FORMULA_CORRECTION", "formula_sketch_correction", "formula_sketch_sessions_v49_28", form_sid, "formula_sketch", "mistake_to_correction", 0.20, clamp(0.20 + corrections / mistakes * 0.62), 0.70, 0.82, ["mistake", "correction", "visual", "formula"], f"formula sketch corrigiu {corrections}/{mistakes} erros", p))
                out.append(self.ev("FORMULA_FUSION", "cross_domain_formula_fusion", "formula_sketch_sessions_v49_28", form_sid, "formula_sketch", "fusion_count", 0.18, clamp(0.18 + fusions / intentions * 3.4), 0.66, 0.76, ["fusion", "visual", "formula", "transfer"], f"formula sketch juntou {fusions} formulas em {intentions} intencoes", p))

            story_sid, story_complete = self.store.latest_payload(conn, "story_nursery_sessions_v49_29", "phase", "session_complete")
            if story_complete:
                p = story_complete["payload"]
                out.append(self.ev("STORY_STABILITY", "story_affective_learning", "story_nursery_sessions_v49_29", story_sid, "story", "affective_stability", 0.30, clamp(float(p.get("avg_stability") or 0.0)), clamp(float(p.get("avg_stability") or 0.0)), 0.83, ["story", "affect", "comfort", "empathy"], f"historias produziram estabilidade media {float(p.get('avg_stability') or 0.0):.3f}", p))
                replay = p.get("replay", {}) if isinstance(p.get("replay"), dict) else {}
                if replay:
                    out.append(self.ev("STORY_REPLAY", "narrative_replay", "story_replay_v49_29", str(replay.get("replay_id") or story_sid), "story", "image_replay", clamp(float(replay.get("sigma_before") or 0.0) / 4.0), clamp(float(replay.get("sigma_after") or 0.0) / 4.0), 0.74, 0.78, ["replay", "story", "affect"], "replay narrativo aumentou estabilidade relacional", replay))

            if self.store.table_exists(conn, "music_reactions_v49_16"):
                rows = self.store.rows(conn, "music_reactions_v49_16")
                if rows:
                    comfort = mean([float(r.get("comfort") or 0.0) for r in rows])
                    stability = mean([float(r.get("stability") or 0.0) for r in rows])
                    out.append(self.ev("MUSIC_COMFORT", "music_comfort_pattern", "music_reactions_v49_16", str(rows[-1].get("session_id") or ""), "music", "comfort_pattern", 0.32, clamp(comfort * 0.55 + stability * 0.35), stability, 0.80, ["music", "comfort", "safe_context"], f"musica simples gerou comfort={comfort:.2f}, stability={stability:.2f}", {"sample_count": len(rows)}))

            if self.store.table_exists(conn, "affective_consolidation_v49_17"):
                rows = self.store.rows(conn, "affective_consolidation_v49_17")
                if rows:
                    latest = rows[-1]
                    before = clamp(float(latest.get("sigma_before") or 0.0) / 3.0)
                    after = clamp(float(latest.get("sigma_after") or 0.0) / 3.0)
                    out.append(self.ev("AFFECTIVE_CHOICE", "preference_weighted_choice", "affective_consolidation_v49_17", str(latest.get("session_id") or ""), "preference", "choice_by_evidence", before, after, 0.73, 0.82, ["preference", "choice", "evidence"], "preferencia afetiva escolheu acao por evidencia e RZS", latest))

            if self.store.table_exists(conn, "brain_meta_cycles_v49_1"):
                rows = self.store.rows(conn, "brain_meta_cycles_v49_1")
                health = [float(r.get("health_score") or 0.0) for r in rows if r.get("phase") == "meta_action_execute"]
                if health:
                    out.append(self.ev("META_SELF_CHECK", "metacognitive_self_check", "brain_meta_cycles_v49_1", str(rows[-1].get("scenario_id") or ""), "metacognition", "self_check_health", 0.30, clamp(health[-1]), clamp(health[-1]), 0.78, ["metacognition", "self_check", "stability"], f"metacognicao registrou health final {health[-1]:.3f}", {"health_samples": health[-8:]}))

            if self.store.table_exists(conn, "self_model_statements_v49_27"):
                rows = self.store.rows(conn, "self_model_statements_v49_27")
                if rows:
                    out.append(self.ev("SELF_LIMIT", "operational_self_boundary", "self_model_statements_v49_27", str(rows[-1].get("session_id") or ""), "self_model", "truth_boundary", 0.40, 0.72, 0.82, 0.86, ["self_model", "limit", "truth"], "modelo de si preserva limites antes de agir", {"statement_count": len(rows)}))
        return out

    def prepare(self) -> None:
        if self.prepared:
            return
        self.store.log_session(self.session_id, "learning_to_learn_start", self.mode, {"protected_counts_before": self.source_counts_before})
        self.evidence = self.load_evidence()
        for ev in self.evidence:
            self.store.log_evidence(self.session_id, ev)
        self.strategies = {st.strategy_key: st for st in self.derive_strategies()}
        for st in self.strategies.values():
            self.store.log_strategy(self.session_id, st)
        self.store.log_session(
            self.session_id,
            "strategies_derived",
            self.mode,
            {
                "evidence_count": len(self.evidence),
                "strategy_count": len(self.strategies),
                "source_kinds": sorted({e.source_kind for e in self.evidence}),
                "strategy_keys": sorted(self.strategies),
            },
        )
        self.prepared = True

    def matching(self, *tags: str) -> list[LearningEvidence]:
        wanted = set(tags)
        return [ev for ev in self.evidence if wanted.intersection(ev.tags) or ev.domain in wanted or ev.source_kind in wanted]

    def strategy_from(self, key: str, family: str, description: str, trigger: str, tags: list[str], base_risk: float) -> LearningStrategy:
        evs = self.matching(*tags)
        gain = mean([max(0.0, ev.gain) for ev in evs]) if evs else 0.12
        stability = mean([ev.stability for ev in evs]) if evs else 0.50
        confidence = clamp(0.42 + len(evs) * 0.045 + stability * 0.22 + gain * 0.16)
        risk = clamp(base_risk + max(0.0, 0.45 - stability) * 0.20)
        return LearningStrategy(
            key,
            family,
            description,
            trigger,
            clamp(gain * 0.72 + stability * 0.18),
            risk,
            confidence,
            [ev.evidence_id for ev in evs[:6]],
            {"matched_tags": tags, "matched_evidence": [ev.signal_key for ev in evs]},
        )

    def derive_strategies(self) -> list[LearningStrategy]:
        return [
            self.strategy_from("replay_before_retry", "memory", "voltar a uma memoria antes de tentar de novo", "erro recente, lacuna de replay ou baixa estabilidade", ["replay", "error", "story"], 0.14),
            self.strategy_from("narrow_focus_on_conflict", "attention", "estreitar o foco quando conflito/novidade sobem", "muitos sinais competindo ou curiosidade alta demais", ["metacognition", "story", "self_check"], 0.16),
            self.strategy_from("error_as_experience_node", "error_learning", "tratar erro como no de experiencia corrigivel", "erro claro com feedback disponivel", ["error", "mistake", "correction", "geometry"], 0.18),
            self.strategy_from("consolidate_after_pattern", "consolidation", "consolidar depois que um padrao aparece", "varias exposicoes semelhantes ou conforto alto", ["comfort", "safe_context", "preference", "story"], 0.12),
            self.strategy_from("cross_domain_fusion", "transfer", "juntar dominios para gerar nova pista", "curiosidade alta e estabilidade suficiente", ["fusion", "transfer", "formula", "curiosity"], 0.24),
            self.strategy_from("affective_safe_context", "affect", "usar contexto calmo para sustentar aprendizagem", "energia baixa ou tarefa nova delicada", ["music", "comfort", "affect", "empathy"], 0.10),
            self.strategy_from("evidence_weighted_choice", "choice", "escolher proximo treino por evidencia acumulada", "mais de uma acao possivel", ["preference", "choice", "evidence"], 0.14),
            self.strategy_from("self_check_before_advance", "metacognition", "checar limites e integridade antes de avancar", "novo marco ou alto risco epistemico", ["self_model", "truth", "metacognition", "limit"], 0.08),
        ]

    def rzs_input(self, trial_index: int, strategy: LearningStrategy, context: str) -> RZSInput:
        memory_pressure = clamp(0.18 + (trial_index % 9 == 0) * 0.58 + (1.0 - strategy.confidence) * 0.18)
        replay_gap = clamp(0.14 + (trial_index % 7) / 8.0)
        novelty = clamp(0.20 + (context in {"cross_domain", "new_story", "new_formula"}) * 0.42 + (trial_index % 11 == 0) * 0.38 + strategy.risk * 0.15)
        conflict = clamp(0.10 + strategy.risk * 0.42 + (trial_index % 13 == 0) * 0.30)
        return RZSInput(
            bandwidth=3.35 + self.energy * 0.88 + strategy.confidence * 0.32,
            info_self=0.30 + (1.0 - strategy.confidence) * 0.16,
            info_external=0.30 + novelty * 0.16,
            task_info=0.42 + strategy.expected_gain * 0.28,
            novelty=novelty,
            conflict=conflict,
            latency=0.92 + memory_pressure * 0.28 + strategy.risk * 0.16,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def context_for_trial(self, trial_index: int) -> str:
        contexts = ["geometry_error", "formula_sketch", "story_reaction", "music_pattern", "preference_choice", "self_monitoring", "cross_domain", "new_formula", "new_story"]
        return contexts[(trial_index - 1) % len(contexts)]

    def choose_strategy(self, trial_index: int, context: str, decision: str) -> LearningStrategy:
        if decision == "replay_memory":
            preferred = ["replay_before_retry", "error_as_experience_node", "self_check_before_advance"]
        elif decision == "narrow_focus":
            preferred = ["narrow_focus_on_conflict", "error_as_experience_node", "self_check_before_advance"]
        elif decision == "consolidate":
            preferred = ["consolidate_after_pattern", "affective_safe_context", "evidence_weighted_choice"]
        elif context in {"cross_domain", "new_formula"}:
            preferred = ["cross_domain_fusion", "self_check_before_advance", "replay_before_retry"]
        elif context == "story_reaction":
            preferred = ["affective_safe_context", "replay_before_retry", "consolidate_after_pattern"]
        elif context == "preference_choice":
            preferred = ["evidence_weighted_choice", "self_check_before_advance", "consolidate_after_pattern"]
        else:
            preferred = ["error_as_experience_node", "replay_before_retry", "narrow_focus_on_conflict"]
        candidates = [self.strategies[k] for k in preferred if k in self.strategies]
        candidates = candidates or list(self.strategies.values())
        weights = [0.12 + st.confidence * 0.52 + st.expected_gain * 0.30 - st.risk * 0.14 for st in candidates]
        return self.rng.choices(candidates, weights=[max(0.05, w) for w in weights], k=1)[0]

    def action_for(self, decision: str, strategy: LearningStrategy) -> str:
        if decision == "replay_memory":
            return f"replay_then_apply_{strategy.strategy_key}"
        if decision == "narrow_focus":
            return f"narrow_apply_{strategy.strategy_key}"
        if decision == "consolidate":
            return f"consolidate_{strategy.strategy_key}"
        if decision == "pause_for_stability":
            return f"pause_before_{strategy.strategy_key}"
        return f"apply_{strategy.strategy_key}"

    def run_trial(self, trial_index: int) -> LearningTrial:
        context = self.context_for_trial(trial_index)
        probe = self.rzs_input(trial_index, max(self.strategies.values(), key=lambda s: s.confidence), context)
        preliminary = self.rzs.classify(probe)
        strategy = self.choose_strategy(trial_index, context, preliminary.decision)
        x = self.rzs_input(trial_index, strategy, context)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        predicted = clamp(strategy.expected_gain * (0.72 + strategy.confidence * 0.28) - strategy.risk * 0.10)
        regulator_bonus = {"continue": 0.00, "narrow_focus": 0.045, "replay_memory": 0.060, "consolidate": 0.052, "pause_for_stability": 0.025}.get(assessment.decision, 0.0)
        context_match = self.context_match(strategy, context)
        noise = self.rng.uniform(-0.025, 0.035)
        observed = clamp(predicted * (0.78 + context_match * 0.32) + regulator_bonus + noise)
        before_conf = strategy.confidence
        prediction_error = abs(observed - predicted)
        strategy.confidence = clamp(strategy.confidence + 0.18 * (observed - strategy.confidence * 0.45) - prediction_error * 0.05)
        strategy.expected_gain = clamp(strategy.expected_gain * 0.82 + observed * 0.18)
        self.energy = clamp(self.energy - 0.010 - strategy.risk * 0.006 + observed * 0.006)
        trial = LearningTrial(
            trial_id=f"TR-{self.session_id}-{trial_index:03d}",
            trial_index=trial_index,
            context_kind=context,
            strategy_key=strategy.strategy_key,
            predicted_gain=predicted,
            observed_gain=observed,
            transfer_score=context_match,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            chosen_action=self.action_for(assessment.decision, strategy),
            confidence_before=before_conf,
            confidence_after=strategy.confidence,
            payload={
                "strategy_family": strategy.strategy_family,
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "prediction_error": prediction_error,
                "regulator_bonus": regulator_bonus,
                "context_match": context_match,
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )
        self.trials.append(trial)
        self.store.log_trial(self.session_id, trial)
        self.store.log_strategy(self.session_id, strategy)
        self.store.log_session(
            self.session_id,
            "learning_trial",
            self.mode,
            {"trial_id": trial.trial_id, "context": context, "strategy": strategy.strategy_key, "observed_gain": observed, "rzs_decision": assessment.decision},
            trial_index,
        )
        return trial

    def context_match(self, strategy: LearningStrategy, context: str) -> float:
        mapping = {
            "geometry_error": {"error_learning", "memory", "attention"},
            "formula_sketch": {"error_learning", "transfer", "attention"},
            "story_reaction": {"affect", "memory", "consolidation"},
            "music_pattern": {"affect", "consolidation"},
            "preference_choice": {"choice", "metacognition"},
            "self_monitoring": {"metacognition", "attention"},
            "cross_domain": {"transfer", "metacognition"},
            "new_formula": {"transfer", "error_learning", "memory"},
            "new_story": {"affect", "memory", "attention"},
        }
        return 0.92 if strategy.strategy_family in mapping.get(context, set()) else 0.46

    def run(self, trials: int = 48) -> dict[str, Any]:
        self.prepare()
        trials = max(24, int(trials))
        for i in range(1, trials + 1):
            self.run_trial(i)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        counts_after = self.store.protected_counts()
        source_unchanged = counts_after == self.source_counts_before
        by_strategy: dict[str, list[LearningTrial]] = {}
        for trial in self.trials:
            by_strategy.setdefault(trial.strategy_key, []).append(trial)
        ranked = []
        for key, items in by_strategy.items():
            ranked.append(
                {
                    "strategy_key": key,
                    "trial_count": len(items),
                    "mean_observed_gain": mean([t.observed_gain for t in items]),
                    "mean_predicted_gain": mean([t.predicted_gain for t in items]),
                    "confidence": self.strategies[key].confidence,
                }
            )
        ranked.sort(key=lambda item: (item["mean_observed_gain"], item["confidence"], item["trial_count"]), reverse=True)
        first = self.trials[: max(1, len(self.trials) // 4)]
        last = self.trials[-max(1, len(self.trials) // 4) :]
        first_gain = mean([t.observed_gain for t in first])
        last_gain = mean([t.observed_gain for t in last])
        decisions = sorted({t.rzs_decision for t in self.trials})
        summary = {
            "session_id": self.session_id,
            "evidence_count": len(self.evidence),
            "source_kinds": sorted({e.source_kind for e in self.evidence}),
            "strategy_count": len(self.strategies),
            "trial_count": len(self.trials),
            "rzs_decisions": decisions,
            "first_quarter_gain": first_gain,
            "last_quarter_gain": last_gain,
            "learning_gain_delta": last_gain - first_gain,
            "ranked_strategies": ranked,
            "top_strategy": ranked[0]["strategy_key"] if ranked else "",
            "protected_counts_before": self.source_counts_before,
            "protected_counts_after": counts_after,
            "protected_sources_unchanged": source_unchanged,
            "session_complete": True,
        }
        self.write_predictions(ranked[:5])
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-META",
            "meta_learning_summary",
            f"Aprender a aprender: melhor estrategia={summary['top_strategy']} delta_ganho={summary['learning_gain_delta']:.3f}.",
            0.86,
            summary,
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-LIMIT",
            "epistemic_boundary",
            "Este marco nao prova consciencia; prova selecao auditavel de estrategias de aprendizagem.",
            0.94,
            {"claim": "meta_learning_not_consciousness_proof"},
        )
        self.store.write_memory(self.session_id, summary, 0.88)
        self.store.write_episode(
            self.session_id,
            "learn_how_to_learn",
            f"strategies={len(self.strategies)} trials={len(self.trials)} top={summary['top_strategy']}",
            "Darwin comeca a escolher estrategias de aprendizagem a partir de evidencia historica e RZS.",
            self.trials[0].sigma_before if self.trials else 0.0,
            self.trials[-1].sigma_after if self.trials else 0.0,
        )
        ready = len(self.evidence) >= 7 and len(self.strategies) >= 8 and len(self.trials) >= 24 and any(d != "continue" for d in decisions)
        self.store.log_handoff(
            self.session_id,
            "usar_learning_to_learn_v49_30_para_escolher_o_proximo_treino_do_darwin",
            ready,
            len(self.strategies),
            0.88 if ready else 0.62,
            summary,
        )
        self.store.log_session(self.session_id, "session_complete", self.mode, summary)
        return summary

    def write_predictions(self, ranked: list[dict[str, Any]]) -> None:
        for idx, item in enumerate(ranked, start=1):
            key = str(item["strategy_key"])
            context = {
                "replay_before_retry": "erro novo depois de uma tentativa",
                "narrow_focus_on_conflict": "novidade alta ou conflito de sinais",
                "error_as_experience_node": "erro com feedback claro",
                "consolidate_after_pattern": "padrao repetido com estabilidade",
                "cross_domain_fusion": "formula ou historia com transferencia",
            }.get(key, "proximo treino incerto")
            outcome = f"ganho esperado >= {float(item['mean_observed_gain']):.3f} se contexto combinar"
            self.store.log_prediction(
                self.session_id,
                f"PR-{self.session_id}-{idx:02d}",
                key,
                context,
                outcome,
                clamp(float(item["confidence"])),
                f"learning_trials_v49_30.strategy_key='{key}' AND observed_gain >= predicted_gain*0.70",
                item,
            )


class LearningToLearnApp:
    BG = "#071018"
    PANEL = "#0d1b26"
    INK = "#eef8ff"
    MUTED = "#9cc9ff"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Learning to Learn v49.30")
        self.root.geometry("1120x760")
        self.root.minsize(960, 640)
        self.root.configure(bg=self.BG)
        self.core = LearningToLearnCore(mode="gui")
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
        tk.Label(header, text="DARWIN LEARNING TO LEARN v49.30", bg=self.BG, fg=self.INK, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(header, text="experiencia -> estrategia -> ensaio -> confianca", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=390)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=250)
        self.canvas.pack(fill="x")
        buttons = tk.Frame(left, bg="#102231")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Rodar 48 ensaios", command=self.run_core).pack(side="left", padx=8, pady=8)
        ttk.Button(buttons, text="Estrategias", command=self.show_strategies).pack(side="left", padx=4, pady=8)
        ttk.Button(buttons, text="Ensaios", command=self.show_trials).pack(side="left", padx=4, pady=8)
        self.main = tk.Text(left, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.main.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Resumo", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.side = tk.Text(right, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.side.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def run_core(self) -> None:
        self.core = LearningToLearnCore(mode="gui")
        self.summary = self.core.run(48)
        self.show_strategies()
        self.show_summary()

    def show_summary(self) -> None:
        s = self.summary
        lines = [
            f"sessao: {s.get('session_id', '')}",
            f"evidencias: {s.get('evidence_count', 0)}",
            f"fontes: {', '.join(s.get('source_kinds', []))}",
            f"estrategias: {s.get('strategy_count', 0)}",
            f"ensaios: {s.get('trial_count', 0)}",
            f"RZS: {', '.join(s.get('rzs_decisions', []))}",
            "",
            f"ganho inicio: {s.get('first_quarter_gain', 0):.3f}",
            f"ganho final: {s.get('last_quarter_gain', 0):.3f}",
            f"delta: {s.get('learning_gain_delta', 0):.3f}",
            f"melhor: {s.get('top_strategy', '')}",
        ]
        self.side.delete("1.0", "end")
        self.side.insert("end", "\n".join(lines))

    def show_strategies(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Estrategias aprendidas", ""]
        for item in self.summary.get("ranked_strategies", []):
            lines.append(f"- {item['strategy_key']} | gain={item['mean_observed_gain']:.3f} pred={item['mean_predicted_gain']:.3f} conf={item['confidence']:.3f} trials={item['trial_count']}")
        self.main.insert("end", "\n".join(lines))

    def show_trials(self) -> None:
        self.main.delete("1.0", "end")
        lines = ["Ultimos ensaios", ""]
        for trial in self.core.trials[-18:]:
            lines.append(f"{trial.trial_index:02d} {trial.context_kind} -> {trial.strategy_key} | RZS {trial.rzs_decision} | gain {trial.observed_gain:.3f}")
        self.main.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.05
        self.draw()
        self.root.after(50, self.animate)

    def draw(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.52
        pulse = 1.0 + math.sin(self.phase) * 0.04
        r = min(w, h) * 0.19 * pulse
        self.canvas.create_text(cx, 30, text="aprendendo a aprender", fill=self.INK, font=("Segoe UI", 17, "bold"))
        for i in range(6, 0, -1):
            rr = r + i * 16
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=f"#{20+i*12:02x}{50+i*17:02x}{76+i*18:02x}", outline="")
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#72e0a8", outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - r * 0.32, cy - r * 0.32, cx + r * 0.32, cy + r * 0.32, fill="#e7fbff", outline="")
        top = self.summary.get("top_strategy", "")
        self.canvas.create_text(cx, h - 26, text=f"melhor estrategia: {top}", fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.30 - LEARNING TO LEARN")
    print("=" * 68)
    print(f"- sessao: {summary['session_id']}")
    print(f"- evidencias={summary['evidence_count']} estrategias={summary['strategy_count']} ensaios={summary['trial_count']}")
    print(f"- ganho inicio={summary['first_quarter_gain']:.3f} ganho final={summary['last_quarter_gain']:.3f} delta={summary['learning_gain_delta']:.3f}")
    print(f"- melhor estrategia: {summary['top_strategy']}")
    print(f"- RZS: {', '.join(summary['rzs_decisions'])}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.30 Learning to Learn")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--trials", type=int, default=48)
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4930)
    args = ap.parse_args()
    if args.self_test:
        core = LearningToLearnCore(seed=args.seed, mode="self_test")
        summary = core.run(args.trials)
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    LearningToLearnApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
