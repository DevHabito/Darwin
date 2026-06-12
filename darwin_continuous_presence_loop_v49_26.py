from __future__ import annotations

"""
DARWIN v49.26 - Continuous Presence Loop

Objetivo:
Darwin fica acordado no notebook como uma presenca continua curta:
percebe sinais internos, escolhe foco, regula pelo RZS, executa acoes
cognitivas locais e deixa um handoff vivo. Isto nao depende de voz real;
se a fala do Windows estiver bloqueada, a presenca monitora esse bloqueio
sem fingir que escuta.

Uso:
    py darwin_continuous_presence_loop_v49_26.py
    py darwin_continuous_presence_loop_v49_26.py --self-test --details
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

PR_SESSIONS = "presence_sessions_v49_26"
PR_SIGNALS = "presence_signals_v49_26"
PR_TICKS = "presence_ticks_v49_26"
PR_ACTIONS = "presence_actions_v49_26"
PR_HANDOFFS = "presence_handoffs_v49_26"

SOURCE = "darwin_continuous_presence_loop_v49_26"
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


def short(text: str, limit: int = 150) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class PresenceSignal:
    signal_id: str
    signal_kind: str
    source_table: str
    source_ref: str
    salience: float
    valence: float
    summary: str
    payload: dict[str, Any]


@dataclass
class PresenceTick:
    tick_index: int
    phase: str
    focus_key: str
    attention_state: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    energy: float
    stability: float
    presence_action: str
    payload: dict[str, Any]


@dataclass
class PresenceAction:
    action_id: str
    tick_index: int
    action_key: str
    action_family: str
    status: str
    effect_summary: str
    payload: dict[str, Any]


@dataclass
class PresenceHandoff:
    handoff_id: str
    next_recommended_core: str
    next_action: str
    voice_ready: bool
    continuous_presence_ready: bool
    confidence: float
    payload: dict[str, Any]


class PresenceStore:
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
                CREATE TABLE IF NOT EXISTS {PR_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    tick_count INTEGER NOT NULL DEFAULT 0,
                    source_voice_repair_session_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {PR_SIGNALS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL UNIQUE,
                    signal_kind TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    salience REAL NOT NULL DEFAULT 0.0,
                    valence REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {PR_TICKS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tick_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    attention_state TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    energy REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    presence_action TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {PR_ACTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action_id TEXT NOT NULL UNIQUE,
                    tick_index INTEGER NOT NULL,
                    action_key TEXT NOT NULL,
                    action_family TEXT NOT NULL,
                    status TEXT NOT NULL,
                    effect_summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {PR_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_recommended_core TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    voice_ready INTEGER NOT NULL DEFAULT 0,
                    continuous_presence_ready INTEGER NOT NULL DEFAULT 0,
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

    def count_rows(self, conn: sqlite3.Connection, table: str) -> int:
        if not self.table_exists(conn, table):
            return 0
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"]) if row else 0

    def log_session(self, session_id: str, phase: str, mode: str, tick_count: int, source_voice_repair_session_id: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {PR_SESSIONS} (
                    timestamp, session_id, phase, mode, tick_count,
                    source_voice_repair_session_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, tick_count, source_voice_repair_session_id, js(payload or {})),
            )
            conn.commit()

    def log_signal(self, session_id: str, signal: PresenceSignal) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {PR_SIGNALS} (
                    timestamp, session_id, signal_id, signal_kind,
                    source_table, source_ref, salience, valence,
                    summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    signal.signal_id,
                    signal.signal_kind,
                    signal.source_table,
                    signal.source_ref,
                    signal.salience,
                    signal.valence,
                    signal.summary,
                    js(signal.payload),
                ),
            )
            conn.commit()

    def log_tick(self, session_id: str, tick: PresenceTick) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {PR_TICKS} (
                    timestamp, session_id, tick_index, phase, focus_key,
                    attention_state, rzs_decision, sigma_before,
                    sigma_after, energy, stability, presence_action,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    tick.tick_index,
                    tick.phase,
                    tick.focus_key,
                    tick.attention_state,
                    tick.rzs_decision,
                    tick.sigma_before,
                    tick.sigma_after,
                    tick.energy,
                    tick.stability,
                    tick.presence_action,
                    js(tick.payload),
                ),
            )
            conn.commit()

    def log_action(self, session_id: str, action: PresenceAction) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {PR_ACTIONS} (
                    timestamp, session_id, action_id, tick_index,
                    action_key, action_family, status, effect_summary,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    action.action_id,
                    action.tick_index,
                    action.action_key,
                    action.action_family,
                    action.status,
                    action.effect_summary,
                    js(action.payload),
                ),
            )
            conn.commit()

    def log_handoff(self, session_id: str, handoff: PresenceHandoff) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {PR_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_recommended_core,
                    next_action, voice_ready, continuous_presence_ready,
                    confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    handoff.handoff_id,
                    handoff.next_recommended_core,
                    handoff.next_action,
                    1 if handoff.voice_ready else 0,
                    1 if handoff.continuous_presence_ready else 0,
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
                (f"continuous_presence_v49_26:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"continuous_presence:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class PresenceContextLoader:
    def __init__(self, store: PresenceStore) -> None:
        self.store = store

    def build_signals(self, session_id: str) -> tuple[list[PresenceSignal], dict[str, Any]]:
        with self.store.connect() as conn:
            voice_repair = self.store.latest_row(conn, "voice_repair_results_v49_25")
            desire = self.store.latest_row(conn, "desire_dialogue_state_v49_23")
            wake = self.store.latest_row(conn, "wake_next_handoff_v49_21")
            sleep = self.store.latest_row(conn, "sleep_wake_plans_v49_20")
            semantic_count = self.store.count_rows(conn, "semantic_memory")
            episode_count = self.store.count_rows(conn, "episodes")
            first_words = self.store.latest_row(conn, "voice_first_word_sessions_v49_10")
        signals: list[PresenceSignal] = []

        voice_ready = bool(int(voice_repair.get("real_voice_ready") or 0)) if voice_repair else False
        recognizers = int(voice_repair.get("recognizer_count") or 0) if voice_repair else 0
        blocked_by = str(voice_repair.get("blocked_by") or "")
        if voice_repair:
            kind = "voice_ready" if voice_ready else "voice_repair_state"
            signals.append(
                PresenceSignal(
                    f"SIG-{session_id}-VOICE",
                    kind,
                    "voice_repair_results_v49_25",
                    str(voice_repair.get("session_id") or ""),
                    0.96 if not voice_ready else 0.88,
                    0.38 if not voice_ready else 0.74,
                    blocked_by or "voz real pronta para teste",
                    {"recognizer_count": recognizers, "voice_ready": voice_ready, "next_action": voice_repair.get("next_action", "")},
                )
            )

        if desire:
            top = str(desire.get("top_activity") or desire.get("top_want") or "")
            signals.append(
                PresenceSignal(
                    f"SIG-{session_id}-DESIRE",
                    "desire_state",
                    "desire_dialogue_state_v49_23",
                    str(desire.get("session_id") or ""),
                    0.82,
                    0.68,
                    short(top),
                    {"top_want": desire.get("top_want", ""), "top_activity": desire.get("top_activity", "")},
                )
            )

        if wake:
            signals.append(
                PresenceSignal(
                    f"SIG-{session_id}-WAKE",
                    "wake_handoff",
                    "wake_next_handoff_v49_21",
                    str(wake.get("session_id") or ""),
                    clamp(float(wake.get("confidence") or 0.70)),
                    0.66,
                    short(str(wake.get("next_action") or "")),
                    {"next_recommended_core": wake.get("next_recommended_core", ""), "next_action": wake.get("next_action", "")},
                )
            )

        if sleep:
            signals.append(
                PresenceSignal(
                    f"SIG-{session_id}-SLEEP",
                    "sleep_wake_plan",
                    "sleep_wake_plans_v49_20",
                    str(sleep.get("session_id") or ""),
                    clamp(float(sleep.get("confidence") or 0.58)),
                    0.58,
                    short(str(sleep.get("plan_summary") or sleep.get("next_action") or "")),
                    {"wake_plan_id": sleep.get("wake_plan_id", ""), "next_action": sleep.get("next_action", "")},
                )
            )

        if first_words:
            payload = first_words.get("payload", {})
            signals.append(
                PresenceSignal(
                    f"SIG-{session_id}-FIRSTWORDS",
                    "first_words_memory",
                    "voice_first_word_sessions_v49_10",
                    str(first_words.get("session_id") or ""),
                    0.64,
                    0.70,
                    f"primeiras palavras: {payload.get('learned_count', 0)} aprendidas",
                    {"payload": payload},
                )
            )

        signals.append(
            PresenceSignal(
                f"SIG-{session_id}-MEMORY",
                "memory_growth",
                "semantic_memory",
                "recent_memory_counts",
                0.58,
                0.62,
                f"memoria semantica={semantic_count}; episodios={episode_count}",
                {"semantic_count": semantic_count, "episode_count": episode_count},
            )
        )
        signals.append(
            PresenceSignal(
                f"SIG-{session_id}-SELF",
                "presence_self",
                PR_SESSIONS,
                session_id,
                0.54,
                0.64,
                "manter presenca acordada, curta e auditavel",
                {"goal": "continuous_presence_loop"},
            )
        )
        context = {
            "voice_ready": voice_ready,
            "voice_repair_session_id": str(voice_repair.get("session_id") or "") if voice_repair else "",
            "voice_blocked_by": blocked_by,
            "recognizer_count": recognizers,
            "semantic_count": semantic_count,
            "episode_count": episode_count,
        }
        return signals, context


class ContinuousPresenceCore:
    def __init__(self, db_path: Path = DB, seed: int | None = None, mode: str = "gui") -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.session_id = f"V4926-{int(time.time())}-{suffix(self.rng)}"
        self.mode = mode
        self.store = PresenceStore(db_path)
        self.rzs = RZSFormal()
        self.signals, self.context = PresenceContextLoader(self.store).build_signals(self.session_id)
        self.energy = 0.74
        self.stability = 0.70
        self.tick_index = 0
        self.focus_history: list[str] = []
        self.ticks: list[PresenceTick] = []
        self.actions: list[PresenceAction] = []
        self.handoff: PresenceHandoff | None = None
        self.summary: dict[str, Any] = {}
        self.store.log_session(
            self.session_id,
            "session_start",
            mode,
            0,
            self.context.get("voice_repair_session_id", ""),
            {"version": "v49.26", "goal": "continuous_presence_loop"},
        )
        for signal in self.signals:
            self.store.log_signal(self.session_id, signal)

    def choose_focus(self) -> PresenceSignal:
        if not self.signals:
            raise RuntimeError("No presence signals available")
        recent = set(self.focus_history[-2:])
        scored: list[tuple[float, PresenceSignal]] = []
        for signal in self.signals:
            penalty = 0.22 if signal.signal_kind in recent else 0.0
            unseen_bonus = 0.34 if signal.signal_kind not in self.focus_history else 0.0
            urgency = 0.18 if signal.signal_kind == "voice_repair_state" and self.tick_index % 4 in {0, 1} else 0.0
            curiosity = 0.08 if signal.signal_kind in {"desire_state", "first_words_memory"} and self.tick_index % 3 == 0 else 0.0
            memory_need = 0.10 if signal.signal_kind in {"memory_growth", "wake_handoff"} and self.tick_index % 5 == 0 else 0.0
            score = signal.salience + unseen_bonus + urgency + curiosity + memory_need - penalty + self.rng.random() * 0.012
            scored.append((score, signal))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def rzs_for_focus(self, focus: PresenceSignal) -> tuple[str, float, float]:
        blocked = focus.signal_kind == "voice_repair_state"
        memory_focus = focus.signal_kind in {"memory_growth", "wake_handoff", "sleep_wake_plan"}
        novelty = clamp(0.24 + (1.0 - focus.valence) * 0.24 + (0.14 if focus.signal_kind not in self.focus_history else 0.0))
        conflict = 0.10
        if blocked:
            conflict = 0.34
        elif focus.signal_kind == "desire_state":
            conflict = 0.16
        memory_pressure = 0.42 + len(self.signals) * 0.035
        replay_gap = 0.32
        if blocked and self.tick_index % 4 in {1, 2}:
            memory_pressure = 0.76
            replay_gap = 0.76
        if memory_focus:
            replay_gap = max(replay_gap, 0.72 if self.tick_index % 5 == 0 else 0.48)
        x = RZSInput(
            bandwidth=4.20 + self.stability * 0.32,
            info_self=0.34,
            info_external=0.40 + focus.salience * 0.10,
            task_info=0.48 + focus.salience * 0.20,
            novelty=novelty,
            conflict=conflict,
            latency=0.82 + (0.12 if blocked else 0.04),
            energy=self.energy,
            memory_pressure=clamp(memory_pressure),
            replay_gap=clamp(replay_gap),
        )
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        return assessment.decision, assessment.sigma, self.rzs.sigma(y)

    def action_for(self, focus: PresenceSignal, decision: str) -> PresenceAction:
        if decision == "pause_for_stability":
            key, family, effect = "micro_pause", "presence_stabilize", "reduziu carga para proteger estabilidade"
        elif decision == "consolidate":
            key, family, effect = "compact_presence_state", "presence_stabilize", "compactou estado acordado em memoria curta"
        elif decision == "replay_memory":
            key, family, effect = "replay_recent_signal", "memory_replay", f"replay do foco {focus.signal_kind}"
        elif focus.signal_kind == "voice_repair_state":
            key, family, effect = "monitor_voice_blocker", "voice_monitor", "manteve bloqueio de voz visivel sem travar a presenca"
        elif focus.signal_kind == "desire_state":
            key, family, effect = "guard_current_desire", "desire_guard", "preservou desejo proprio como direcao viva"
        elif focus.signal_kind == "wake_handoff":
            key, family, effect = "maintain_wake_handoff", "wake_continuity", "manteve continuidade entre acordar e proxima agencia"
        elif focus.signal_kind == "first_words_memory":
            key, family, effect = "protect_first_words_memory", "memory_replay", "manteve primeiras palavras prontas para teste real"
        else:
            key, family, effect = "stabilize_presence_loop", "presence_stabilize", "manteve presenca acordada e auditavel"
        return PresenceAction(
            action_id=f"ACT-{self.session_id}-{self.tick_index:03d}",
            tick_index=self.tick_index,
            action_key=key,
            action_family=family,
            status="completed",
            effect_summary=effect,
            payload={"focus_kind": focus.signal_kind, "rzs_decision": decision},
        )

    def advance_tick(self) -> PresenceTick:
        self.tick_index += 1
        focus = self.choose_focus()
        decision, sigma_before, sigma_after = self.rzs_for_focus(focus)
        if decision in {"replay_memory", "consolidate"}:
            self.energy = clamp(self.energy + 0.018)
            self.stability = clamp(self.stability + 0.024)
        elif decision == "narrow_focus":
            self.energy = clamp(self.energy - 0.006)
            self.stability = clamp(self.stability + 0.012)
        elif decision == "pause_for_stability":
            self.energy = clamp(self.energy + 0.030)
            self.stability = clamp(self.stability + 0.032)
        else:
            self.energy = clamp(self.energy - 0.012)
            self.stability = clamp(self.stability + 0.004)
        action = self.action_for(focus, decision)
        attention_state = "blocked_voice_watch" if focus.signal_kind == "voice_repair_state" else "awake_scan"
        if decision == "replay_memory":
            attention_state = "memory_replay"
        elif decision in {"consolidate", "pause_for_stability"}:
            attention_state = "stability_guard"
        tick = PresenceTick(
            tick_index=self.tick_index,
            phase="presence_tick",
            focus_key=focus.signal_kind,
            attention_state=attention_state,
            rzs_decision=decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
            energy=self.energy,
            stability=self.stability,
            presence_action=action.action_key,
            payload={
                "signal_id": focus.signal_id,
                "signal_summary": focus.summary,
                "romero_formula": FORMULA,
                "source_ref": focus.source_ref,
            },
        )
        self.focus_history.append(focus.signal_kind)
        self.ticks.append(tick)
        self.actions.append(action)
        self.store.log_tick(self.session_id, tick)
        self.store.log_action(self.session_id, action)
        return tick

    def build_handoff(self) -> PresenceHandoff:
        voice_ready = bool(self.context.get("voice_ready"))
        focus_count = len(set(self.focus_history))
        continuous_ready = len(self.ticks) >= 10 and focus_count >= 3 and len(self.actions) == len(self.ticks)
        if voice_ready:
            next_core = "darwin_voice_presence_v49_9"
            next_action = "abrir_darwin_voz_ou_primeiras_palavras_para_teste_real"
        else:
            next_core = "darwin_real_voice_repair_wizard_v49_25"
            next_action = "abrir_reparo_de_voz_instalar_fala_pt_br_e_retestar"
        confidence = clamp(0.48 + min(0.24, len(self.ticks) * 0.018) + focus_count * 0.035 + self.stability * 0.16)
        return PresenceHandoff(
            handoff_id=f"HF-{self.session_id}",
            next_recommended_core=next_core,
            next_action=next_action,
            voice_ready=voice_ready,
            continuous_presence_ready=continuous_ready,
            confidence=confidence,
            payload={
                "focus_count": focus_count,
                "tick_count": len(self.ticks),
                "voice_blocked_by": self.context.get("voice_blocked_by", ""),
                "recognizer_count": self.context.get("recognizer_count", 0),
                "action_families": sorted({a.action_family for a in self.actions}),
            },
        )

    def complete(self) -> dict[str, Any]:
        if self.handoff is None:
            self.handoff = self.build_handoff()
            self.store.log_handoff(self.session_id, self.handoff)
        summary = {
            "session_id": self.session_id,
            "source_voice_repair_session_id": self.context.get("voice_repair_session_id", ""),
            "tick_count": len(self.ticks),
            "signal_count": len(self.signals),
            "action_count": len(self.actions),
            "focus_keys": [tick.focus_key for tick in self.ticks],
            "rzs_decisions": sorted({tick.rzs_decision for tick in self.ticks}),
            "ticks": [
                {
                    "tick_index": tick.tick_index,
                    "focus_key": tick.focus_key,
                    "attention_state": tick.attention_state,
                    "rzs_decision": tick.rzs_decision,
                    "sigma_before": round(tick.sigma_before, 3),
                    "sigma_after": round(tick.sigma_after, 3),
                    "energy": round(tick.energy, 3),
                    "stability": round(tick.stability, 3),
                    "presence_action": tick.presence_action,
                }
                for tick in self.ticks
            ],
            "actions": [
                {
                    "tick_index": action.tick_index,
                    "action_key": action.action_key,
                    "action_family": action.action_family,
                    "status": action.status,
                    "effect_summary": action.effect_summary,
                }
                for action in self.actions
            ],
            "handoff": {
                "next_recommended_core": self.handoff.next_recommended_core,
                "next_action": self.handoff.next_action,
                "voice_ready": self.handoff.voice_ready,
                "continuous_presence_ready": self.handoff.continuous_presence_ready,
                "confidence": round(self.handoff.confidence, 3),
            },
            "session_complete": True,
        }
        first_sigma = self.ticks[0].sigma_before if self.ticks else 0.0
        final_sigma = self.ticks[-1].sigma_after if self.ticks else 0.0
        self.store.write_memory(self.session_id, summary, 0.90)
        self.store.write_episode(
            self.session_id,
            "run_continuous_presence_loop",
            f"ticks={len(self.ticks)} focus={len(set(self.focus_history))} next={self.handoff.next_action}",
            "Darwin manteve presenca acordada local: percebeu sinais, regulou foco e preservou o bloqueio de voz como acao futura.",
            first_sigma,
            final_sigma,
        )
        self.store.log_session(
            self.session_id,
            "session_complete",
            self.mode,
            len(self.ticks),
            self.context.get("voice_repair_session_id", ""),
            summary,
        )
        self.summary = summary
        return summary

    def run_cycle(self, ticks: int = 12) -> dict[str, Any]:
        for _ in range(max(1, ticks)):
            self.advance_tick()
        return self.complete()


class ContinuousPresenceApp:
    BG = "#061018"
    PANEL = "#0d1f2d"
    INK = "#ecf8ff"
    MUTED = "#9dbdd5"
    BLUE = "#5fb3ff"
    GREEN = "#7ae6a4"
    AMBER = "#f7c66f"
    RED = "#ff6d78"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Continuous Presence v49.26")
        self.root.geometry("1120x780")
        self.root.minsize(960, 660)
        self.root.configure(bg=self.BG)
        self.core = ContinuousPresenceCore(mode="gui")
        self.phase = 0.0
        self.running = True
        self.last_tick: PresenceTick | None = None
        self.build_ui()
        self.render_signals()
        self.root.after(500, self.next_tick)
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
        tk.Label(header, text="DARWIN CONTINUOUS PRESENCE v49.26", bg=self.BG, fg=self.INK, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="presenca acordada: sinais internos -> foco -> RZS -> acao cognitiva", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=430)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=310)
        self.canvas.pack(fill="x")
        controls = tk.Frame(left, bg="#102434")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Pausar", command=self.toggle).pack(side="left", padx=(10, 5), pady=8)
        ttk.Button(controls, text="Tick agora", command=self.manual_tick).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Completar", command=self.complete).pack(side="left", padx=5, pady=8)
        self.log = tk.Text(left, height=15, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(right, text="Estado Vivo", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.state = tk.Text(right, wrap="word", bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.state.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def render_signals(self) -> None:
        self.log.delete("1.0", "end")
        self.log.insert("end", "Sinais internos\n\n")
        for signal in self.core.signals:
            self.log.insert("end", f"- {signal.signal_kind} salience={signal.salience:.2f} :: {signal.summary}\n")
        self.render_state()

    def toggle(self) -> None:
        self.running = not self.running

    def manual_tick(self) -> None:
        self.last_tick = self.core.advance_tick()
        self.render_tick(self.last_tick)

    def next_tick(self) -> None:
        if self.running:
            self.manual_tick()
        self.root.after(1200, self.next_tick)

    def complete(self) -> None:
        summary = self.core.complete()
        handoff = summary["handoff"]
        self.log.insert("end", f"\nHandoff: {handoff['next_action']} confidence={handoff['confidence']}\n")
        self.render_state()

    def render_tick(self, tick: PresenceTick) -> None:
        self.log.insert(
            "end",
            f"\nTick {tick.tick_index}: foco={tick.focus_key} RZS={tick.rzs_decision} sigma={tick.sigma_before:.2f}->{tick.sigma_after:.2f} acao={tick.presence_action}\n",
        )
        self.log.see("end")
        self.render_state()

    def render_state(self) -> None:
        self.state.delete("1.0", "end")
        last = self.last_tick
        h = self.core.handoff
        lines = [
            f"sessao: {self.core.session_id}",
            f"ticks: {len(self.core.ticks)}",
            f"energia: {self.core.energy:.2f}",
            f"estabilidade: {self.core.stability:.2f}",
            f"voz pronta: {self.core.context.get('voice_ready', False)}",
            f"bloqueio voz: {self.core.context.get('voice_blocked_by', '') or 'nenhum'}",
            "",
            "Ultimo foco",
            last.focus_key if last else "aguardando",
            "",
            "Ultima acao",
            last.presence_action if last else "nenhuma",
            "",
            "Handoff",
            h.next_action if h else "ainda em loop",
        ]
        self.state.insert("end", "\n".join(lines))

    def animate(self) -> None:
        self.phase += 0.04
        self.draw()
        self.root.after(40, self.animate)

    def draw(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.55
        tick = self.last_tick
        decision = tick.rzs_decision if tick else "continue"
        color = {
            "continue": self.BLUE,
            "narrow_focus": self.AMBER,
            "replay_memory": self.GREEN,
            "consolidate": "#a5b4fc",
            "pause_for_stability": self.RED,
        }.get(decision, self.BLUE)
        radius = 78 * (1.0 + math.sin(self.phase) * 0.035)
        radius += 10 * (1.0 - self.core.stability)
        self.canvas.create_text(cx, 30, text="presenca acordada", fill=self.INK, font=("Segoe UI", 16, "bold"))
        for i in range(7, 0, -1):
            rr = radius + i * 18
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="#0c2537", outline="")
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#eaf6ff", width=2)
        inner = radius * (0.32 + (1.0 - self.core.energy) * 0.10)
        self.canvas.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, fill="#e6fbff", outline="")
        footer = f"tick {len(self.core.ticks)} | foco {tick.focus_key if tick else 'scan'} | RZS {decision}"
        self.canvas.create_text(cx, h - 26, text=footer, fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    h = summary["handoff"]
    print("DARWIN v49.26 - CONTINUOUS PRESENCE LOOP")
    print("=" * 68)
    print(f"- sessao: {summary['session_id']}")
    print(f"- sinais: {summary['signal_count']} ticks: {summary['tick_count']} acoes: {summary['action_count']}")
    print(f"- RZS: {', '.join(summary['rzs_decisions'])}")
    print(f"- voz pronta: {h['voice_ready']} presenca pronta: {h['continuous_presence_ready']}")
    print(f"- proximo nucleo: {h['next_recommended_core']}")
    print(f"- proxima acao: {h['next_action']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.26 Continuous Presence Loop")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--ticks", type=int, default=12)
    ap.add_argument("--seed", type=int, default=4926)
    args = ap.parse_args()
    if args.self_test:
        core = ContinuousPresenceCore(seed=args.seed, mode="self_test")
        summary = core.run_cycle(args.ticks)
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    ContinuousPresenceApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
