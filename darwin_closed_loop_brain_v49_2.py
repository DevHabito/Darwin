from __future__ import annotations

"""
DARWIN v49.2 - Closed-loop metacognitivo do Brain Core

Objetivo:
Fechar o laco entre metacognicao e cognicao. A v49.1 detectou travamento
atencional e escreveu uma intervencao; a v49.2 consome essa intervencao,
modula a selecao de foco e demonstra mudanca comportamental auditavel.

Fora de escopo:
- corpo fisico;
- sensores reais;
- camera, microfone ou atuadores;
- dependencias externas.

Uso:
    py darwin_closed_loop_brain_v49_2.py --cycles 8
    py darwin_closed_loop_brain_v49_2.py --cycles 8 --details
"""

import argparse
import json
import random
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

V49_CYCLES = "brain_cycles_v49_0"
V49_WM = "brain_working_memory_v49_0"
V49_ATT = "brain_attention_v49_0"
V49_REPLAY = "brain_replay_v49_0"
SOURCE_V48_9 = "geometry_multistep_plans_v48_9"

META_CYCLES = "brain_meta_cycles_v49_1"
META_CHECKS = "brain_self_checks_v49_1"
META_INTERVENTIONS = "brain_stability_interventions_v49_1"

CLOSED_LOOP = "brain_closed_loop_cycles_v49_2"
MODULATION = "brain_attention_modulation_v49_2"
BEHAVIOR_DELTA = "brain_behavior_delta_v49_2"

PHASES = [
    "closed_loop_start",
    "read_metacognitive_intervention",
    "perceive_internal_events",
    "apply_modulation_policy",
    "attention_select_modulated",
    "cognitive_action_execute",
    "measure_behavior_delta",
    "closed_loop_complete",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


@dataclass
class Percept:
    focus_key: str
    kind: str
    priority: float
    novelty: float
    conflict: float
    source_table: str
    evidence: str
    payload: dict[str, Any]


@dataclass
class InterventionContext:
    meta_scenario_id: str
    observed_v49_0: str
    meta_decision: str
    meta_action: str
    inhibited_focus: str
    baseline_attention_lock_ratio: float
    baseline_dominant_focus: str
    health_before: float
    health_after: float


@dataclass
class ModulationPolicy:
    policy_kind: str
    inhibited_focus: str
    inhibition_strength: float
    directive_boost: float
    plan_boost: float
    replay_boost: float
    repetition_penalty: float


class ClosedLoopStore:
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
                CREATE TABLE IF NOT EXISTS {CLOSED_LOOP} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    loop_cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    observed_v49_0 TEXT NOT NULL DEFAULT '',
                    observed_v49_1 TEXT NOT NULL DEFAULT '',
                    inhibited_focus TEXT NOT NULL DEFAULT '',
                    selected_focus TEXT NOT NULL DEFAULT '',
                    modulation_action TEXT NOT NULL DEFAULT '',
                    health_before REAL NOT NULL DEFAULT 0.0,
                    health_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MODULATION} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    loop_cycle_id INTEGER NOT NULL,
                    observed_v49_0 TEXT NOT NULL DEFAULT '',
                    observed_v49_1 TEXT NOT NULL DEFAULT '',
                    focus_key TEXT NOT NULL,
                    candidate_kind TEXT NOT NULL,
                    raw_score REAL NOT NULL DEFAULT 0.0,
                    adjusted_score REAL NOT NULL DEFAULT 0.0,
                    inhibition_applied REAL NOT NULL DEFAULT 0.0,
                    boost_applied REAL NOT NULL DEFAULT 0.0,
                    repetition_applied REAL NOT NULL DEFAULT 0.0,
                    selected INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {BEHAVIOR_DELTA} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    observed_v49_0 TEXT NOT NULL DEFAULT '',
                    observed_v49_1 TEXT NOT NULL DEFAULT '',
                    baseline_focus TEXT NOT NULL DEFAULT '',
                    baseline_lock_ratio REAL NOT NULL DEFAULT 0.0,
                    modulated_dominant_focus TEXT NOT NULL DEFAULT '',
                    modulated_dominant_ratio REAL NOT NULL DEFAULT 0.0,
                    modulated_inhibited_ratio REAL NOT NULL DEFAULT 0.0,
                    attention_shift INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )
            conn.commit()

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def rows(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.table_exists(conn, table):
            return []
        out = []
        for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"))
            out.append(item)
        return out

    def latest_completed_meta_scenario(self, conn: sqlite3.Connection) -> str | None:
        rows = self.rows(conn, META_CYCLES)
        completed = [
            str(r["scenario_id"])
            for r in rows
            if r.get("phase") == "meta_cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
        ]
        if completed:
            return completed[-1]
        ids = [str(r["scenario_id"]) for r in rows if r.get("scenario_id")]
        return ids[-1] if ids else None

    def intervention_context(self) -> InterventionContext:
        with self.connect() as conn:
            meta_id = self.latest_completed_meta_scenario(conn)
            if not meta_id:
                raise RuntimeError("Nenhum cenario v49.1 encontrado. Rode primeiro: py darwin_brain_metacognition_v49_1.py --passes 6")

            meta_rows = self.rows(conn, META_CYCLES, " WHERE scenario_id=?", (meta_id,))
            interventions = self.rows(conn, META_INTERVENTIONS, " WHERE scenario_id=?", (meta_id,))
            if not interventions:
                raise RuntimeError("Cenario v49.1 nao possui intervencoes registradas.")

        read_rows = [r for r in meta_rows if r.get("phase") == "read_brain_trace"]
        if not read_rows:
            raise RuntimeError("Cenario v49.1 nao possui read_brain_trace.")

        summary = read_rows[-1].get("payload", {}).get("trace_summary", {})
        intervention = interventions[-1]
        return InterventionContext(
            meta_scenario_id=meta_id,
            observed_v49_0=str(summary.get("observed_scenario_id") or intervention.get("observed_scenario_id") or ""),
            meta_decision=str(intervention.get("meta_decision") or ""),
            meta_action=str(intervention.get("meta_action") or ""),
            inhibited_focus=str(summary.get("dominant_focus") or ""),
            baseline_attention_lock_ratio=float(summary.get("attention_lock_ratio") or 0.0),
            baseline_dominant_focus=str(summary.get("dominant_focus") or ""),
            health_before=float(intervention.get("health_before") or 0.0),
            health_after=float(intervention.get("health_after") or 0.0),
        )

    def source_counts(self) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        with self.connect() as conn:
            for table in (SOURCE_V48_9, V49_CYCLES, META_CYCLES):
                if not self.table_exists(conn, table):
                    out[table] = (0, 0)
                    continue
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
                out[table] = (int(row["n"]), int(row["max_id"]))
        return out

    def recent_internal_events(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "episodes": [],
            "semantic_memory": [],
            "state_history": [],
            "v48_9": {"count": 0, "max_id": 0, "recent": []},
        }
        with self.connect() as conn:
            if self.table_exists(conn, "episodes"):
                out["episodes"] = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT id,timestamp,module,context,action_taken,outcome,lesson,sigma_before,sigma_after "
                        "FROM episodes ORDER BY id DESC LIMIT 8"
                    ).fetchall()
                ]
            if self.table_exists(conn, "semantic_memory"):
                out["semantic_memory"] = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT key,content,confidence,source,updated_at "
                        "FROM semantic_memory ORDER BY updated_at DESC LIMIT 60"
                    ).fetchall()
                ]
            if self.table_exists(conn, "state_history"):
                out["state_history"] = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT id,timestamp,sigma,energy,info_self,info_external,latency,pain_signal,wellbeing_signal "
                        "FROM state_history ORDER BY id DESC LIMIT 8"
                    ).fetchall()
                ]
            if self.table_exists(conn, SOURCE_V48_9):
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {SOURCE_V48_9}").fetchone()
                out["v48_9"]["count"] = int(row["n"])
                out["v48_9"]["max_id"] = int(row["max_id"])
                out["v48_9"]["recent"] = [
                    dict(r)
                    for r in conn.execute(
                        f"SELECT id,scenario_id,action_kind,task_id,final_status,observed_outcome "
                        f"FROM {SOURCE_V48_9} ORDER BY id DESC LIMIT 8"
                    ).fetchall()
                ]
        return out

    def log_cycle(
        self,
        scenario_id: str,
        loop_cycle_id: int,
        phase: str,
        ctx: InterventionContext,
        *,
        selected_focus: str = "",
        modulation_action: str = "",
        health_before: float = 0.0,
        health_after: float = 0.0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {CLOSED_LOOP} (
                    timestamp, scenario_id, loop_cycle_id, phase, observed_v49_0,
                    observed_v49_1, inhibited_focus, selected_focus,
                    modulation_action, health_before, health_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    loop_cycle_id,
                    phase,
                    ctx.observed_v49_0,
                    ctx.meta_scenario_id,
                    ctx.inhibited_focus,
                    selected_focus,
                    modulation_action,
                    health_before,
                    health_after,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_modulation(
        self,
        scenario_id: str,
        loop_cycle_id: int,
        ctx: InterventionContext,
        candidate: Percept,
        raw_score: float,
        adjusted_score: float,
        inhibition: float,
        boost: float,
        repetition: float,
        selected: bool,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MODULATION} (
                    timestamp, scenario_id, loop_cycle_id, observed_v49_0,
                    observed_v49_1, focus_key, candidate_kind, raw_score,
                    adjusted_score, inhibition_applied, boost_applied,
                    repetition_applied, selected, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    loop_cycle_id,
                    ctx.observed_v49_0,
                    ctx.meta_scenario_id,
                    candidate.focus_key,
                    candidate.kind,
                    raw_score,
                    adjusted_score,
                    inhibition,
                    boost,
                    repetition,
                    1 if selected else 0,
                    js(asdict(candidate)),
                ),
            )
            conn.commit()

    def log_delta(
        self,
        scenario_id: str,
        ctx: InterventionContext,
        dominant_focus: str,
        dominant_ratio: float,
        inhibited_ratio: float,
        attention_shift: bool,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {BEHAVIOR_DELTA} (
                    timestamp, scenario_id, observed_v49_0, observed_v49_1,
                    baseline_focus, baseline_lock_ratio, modulated_dominant_focus,
                    modulated_dominant_ratio, modulated_inhibited_ratio,
                    attention_shift, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    ctx.observed_v49_0,
                    ctx.meta_scenario_id,
                    ctx.baseline_dominant_focus,
                    ctx.baseline_attention_lock_ratio,
                    dominant_focus,
                    dominant_ratio,
                    inhibited_ratio,
                    1 if attention_shift else 0,
                    js(payload),
                ),
            )
            conn.commit()

    def write_semantic_memory(self, scenario_id: str, content: str, confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    confidence=max(semantic_memory.confidence, excluded.confidence),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    f"brain_v49_2:closed_loop:{scenario_id}",
                    content,
                    clamp(confidence, 0.0, 0.99),
                    "brain_closed_loop_v49_2",
                    now(),
                ),
            )
            conn.commit()


class ClosedLoopBrain:
    def __init__(self, cycles: int = 8, seed: int | None = None) -> None:
        self.store = ClosedLoopStore()
        self.cycles = max(4, cycles)
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.scenario_id = f"V492-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.ctx = self.store.intervention_context()
        self.policy = self.make_policy(self.ctx)
        self.selected_history: list[str] = []
        self.health = self.ctx.health_after
        self.counts_before = self.store.source_counts()

    def make_policy(self, ctx: InterventionContext) -> ModulationPolicy:
        if ctx.meta_action == "stabilize_attention":
            return ModulationPolicy(
                policy_kind="attention_stabilization",
                inhibited_focus=ctx.inhibited_focus,
                inhibition_strength=0.58,
                directive_boost=0.20,
                plan_boost=0.16,
                replay_boost=0.14,
                repetition_penalty=0.24,
            )
        return ModulationPolicy(
            policy_kind="observe_only",
            inhibited_focus="",
            inhibition_strength=0.0,
            directive_boost=0.05,
            plan_boost=0.05,
            replay_boost=0.05,
            repetition_penalty=0.08,
        )

    def percepts(self, loop_cycle_id: int) -> list[Percept]:
        data = self.store.recent_internal_events()
        out: list[Percept] = []

        out.append(
            Percept(
                focus_key="metacognition:stabilize_attention_directive",
                kind="metacognitive_directive",
                priority=0.72 if loop_cycle_id in (1, 5) else 0.58,
                novelty=0.20,
                conflict=0.30,
                source_table=META_INTERVENTIONS,
                evidence=f"{self.ctx.meta_decision}->{self.ctx.meta_action}",
                payload=asdict(self.ctx),
            )
        )

        weak = [m for m in data["semantic_memory"] if float(m.get("confidence", 1.0)) < 0.45]
        if weak:
            m = weak[0]
            out.append(
                Percept(
                    focus_key=f"memory_weak:{m['key']}",
                    kind="memory_weak",
                    priority=0.68,
                    novelty=0.22,
                    conflict=0.20,
                    source_table="semantic_memory",
                    evidence=f"low confidence memory {m['key']}",
                    payload={"memory": m},
                )
            )
        if self.ctx.inhibited_focus and all(p.focus_key != self.ctx.inhibited_focus for p in out):
            out.append(
                Percept(
                    focus_key=self.ctx.inhibited_focus,
                    kind="memory_weak",
                    priority=0.68,
                    novelty=0.22,
                    conflict=0.20,
                    source_table="semantic_memory",
                    evidence="dominant weak-memory focus reconstructed from v49.1 trace",
                    payload={"reconstructed_from": "brain_meta_cycles_v49_1", "inhibited_focus": self.ctx.inhibited_focus},
                )
            )

        v48 = data["v48_9"]
        out.append(
            Percept(
                focus_key="plan:v48_9_stable_chain",
                kind="plan_trace",
                priority=0.57,
                novelty=0.18,
                conflict=0.12,
                source_table=SOURCE_V48_9,
                evidence="v48.9 stable plan chain available for diversified focus",
                payload={"v48_9": v48},
            )
        )

        if data["episodes"]:
            ep = data["episodes"][0]
            out.append(
                Percept(
                    focus_key=f"replay:episode:{ep['id']}",
                    kind="replay_candidate",
                    priority=0.51,
                    novelty=0.14,
                    conflict=0.12,
                    source_table="episodes",
                    evidence=str(ep.get("lesson", ""))[:180],
                    payload={"episode": ep},
                )
            )

        if loop_cycle_id in (4, 8):
            latest = data["state_history"][0] if data["state_history"] else {}
            out.append(
                Percept(
                    focus_key="stability:closed_loop_consolidation",
                    kind="need_consolidation",
                    priority=0.64,
                    novelty=0.10,
                    conflict=0.34,
                    source_table="state_history",
                    evidence=f"scheduled closed-loop stability check cycle={loop_cycle_id}",
                    payload={"state": latest},
                )
            )

        return out

    def score(self, candidate: Percept) -> tuple[float, float, float, float, float]:
        raw = candidate.priority + candidate.conflict * 0.20 + candidate.novelty * 0.10
        inhibition = self.policy.inhibition_strength if candidate.focus_key == self.policy.inhibited_focus else 0.0
        boost = 0.0
        if candidate.kind == "metacognitive_directive":
            boost += self.policy.directive_boost
        elif candidate.kind == "plan_trace":
            boost += self.policy.plan_boost
        elif candidate.kind == "replay_candidate":
            boost += self.policy.replay_boost
        elif candidate.kind == "need_consolidation":
            boost += 0.10

        repetition_count = sum(1 for x in self.selected_history if x == candidate.focus_key)
        repetition = min(0.72, repetition_count * self.policy.repetition_penalty)
        adjusted = raw - inhibition + boost - repetition
        return raw, adjusted, inhibition, boost, repetition

    def select_focus(self, candidates: list[Percept], loop_cycle_id: int) -> tuple[Percept, list[dict[str, Any]]]:
        scored = []
        for candidate in candidates:
            raw, adjusted, inhibition, boost, repetition = self.score(candidate)
            scored.append((adjusted, raw, inhibition, boost, repetition, candidate))
        scored.sort(key=lambda x: (-x[0], x[5].focus_key))
        selected = scored[0][5]

        audit = []
        for adjusted, raw, inhibition, boost, repetition, candidate in scored:
            is_selected = candidate.focus_key == selected.focus_key
            self.store.log_modulation(
                self.scenario_id,
                loop_cycle_id,
                self.ctx,
                candidate,
                raw,
                adjusted,
                inhibition,
                boost,
                repetition,
                is_selected,
            )
            audit.append(
                {
                    "focus_key": candidate.focus_key,
                    "kind": candidate.kind,
                    "raw_score": raw,
                    "adjusted_score": adjusted,
                    "inhibition": inhibition,
                    "boost": boost,
                    "repetition": repetition,
                    "selected": is_selected,
                }
            )
        return selected, audit

    def action_for(self, selected: Percept) -> str:
        if selected.kind == "metacognitive_directive":
            return "apply_attention_policy"
        if selected.kind == "plan_trace":
            return "review_stable_plan"
        if selected.kind == "replay_candidate":
            return "replay_memory"
        if selected.kind == "need_consolidation":
            return "consolidate"
        if selected.kind == "memory_weak":
            return "consult_memory"
        return "observe_internal"

    def run_cycle(self, loop_cycle_id: int) -> None:
        before = self.health
        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "closed_loop_start",
            self.ctx,
            health_before=before,
            health_after=before,
            payload={"phase_order": PHASES, "source_counts_before": self.counts_before},
        )
        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "read_metacognitive_intervention",
            self.ctx,
            modulation_action=self.ctx.meta_action,
            health_before=before,
            health_after=before,
            payload={"intervention_context": asdict(self.ctx)},
        )

        candidates = self.percepts(loop_cycle_id)
        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "perceive_internal_events",
            self.ctx,
            health_before=before,
            health_after=before,
            payload={"sources": sorted({p.source_table for p in candidates}), "percepts": [asdict(p) for p in candidates]},
        )

        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "apply_modulation_policy",
            self.ctx,
            modulation_action=self.policy.policy_kind,
            health_before=before,
            health_after=before,
            payload={"policy": asdict(self.policy), "selected_history": list(self.selected_history)},
        )

        selected, audit = self.select_focus(candidates, loop_cycle_id)
        self.selected_history.append(selected.focus_key)
        shifted = selected.focus_key != self.ctx.inhibited_focus
        self.health = clamp(self.health + (0.020 if shifted else -0.035))
        action = self.action_for(selected)

        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "attention_select_modulated",
            self.ctx,
            selected_focus=selected.focus_key,
            modulation_action=self.policy.policy_kind,
            health_before=before,
            health_after=self.health,
            payload={"selected": asdict(selected), "audit": audit, "attention_shifted": shifted},
        )

        if action == "consolidate":
            self.health = clamp(self.health + 0.015)
        elif action == "replay_memory":
            self.health = clamp(self.health + 0.010)
        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "cognitive_action_execute",
            self.ctx,
            selected_focus=selected.focus_key,
            modulation_action=action,
            health_before=before,
            health_after=self.health,
            payload={"action": action, "selected": asdict(selected)},
        )

        delta = self.current_delta()
        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "measure_behavior_delta",
            self.ctx,
            selected_focus=selected.focus_key,
            modulation_action="measure_delta",
            health_before=before,
            health_after=self.health,
            payload=delta,
        )

        final = loop_cycle_id >= self.cycles
        payload = {
            "scenario_complete": final,
            "cycles_completed": loop_cycle_id,
            "source_counts_before": self.counts_before,
            "source_counts_after": self.store.source_counts(),
            "delta": delta,
        }
        self.store.log_cycle(
            self.scenario_id,
            loop_cycle_id,
            "closed_loop_complete",
            self.ctx,
            selected_focus=selected.focus_key,
            modulation_action=action,
            health_before=before,
            health_after=self.health,
            payload=payload,
        )

        if final:
            attention_shift = bool(delta["attention_shift"])
            self.store.log_delta(
                self.scenario_id,
                self.ctx,
                str(delta["modulated_dominant_focus"]),
                float(delta["modulated_dominant_ratio"]),
                float(delta["modulated_inhibited_ratio"]),
                attention_shift,
                payload,
            )
            self.store.write_semantic_memory(
                self.scenario_id,
                (
                    f"closed_loop_applied action={self.ctx.meta_action}; "
                    f"baseline_lock={self.ctx.baseline_attention_lock_ratio:.3f}; "
                    f"inhibited_after={float(delta['modulated_inhibited_ratio']):.3f}; "
                    f"dominant_after={float(delta['modulated_dominant_ratio']):.3f}"
                ),
                0.76 if attention_shift else 0.52,
            )

    def current_delta(self) -> dict[str, Any]:
        counts = Counter(self.selected_history)
        dominant_focus, dominant_count = counts.most_common(1)[0] if counts else ("", 0)
        total = max(1, len(self.selected_history))
        inhibited_count = counts.get(self.ctx.inhibited_focus, 0)
        dominant_ratio = dominant_count / total
        inhibited_ratio = inhibited_count / total
        attention_shift = (
            self.ctx.meta_action == "stabilize_attention"
            and self.ctx.baseline_attention_lock_ratio > 0.0
            and inhibited_ratio <= max(0.05, self.ctx.baseline_attention_lock_ratio - 0.45)
            and dominant_ratio < self.ctx.baseline_attention_lock_ratio
        )
        return {
            "baseline_focus": self.ctx.baseline_dominant_focus,
            "baseline_lock_ratio": self.ctx.baseline_attention_lock_ratio,
            "modulated_dominant_focus": dominant_focus,
            "modulated_dominant_ratio": dominant_ratio,
            "modulated_inhibited_ratio": inhibited_ratio,
            "selected_history": list(self.selected_history),
            "attention_shift": attention_shift,
        }

    def run(self) -> None:
        for cycle_id in range(1, self.cycles + 1):
            self.run_cycle(cycle_id)


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Closed-loop Brain v49.2")
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    brain = ClosedLoopBrain(cycles=args.cycles, seed=args.seed)
    brain.run()
    delta = brain.current_delta()

    print(f"DARWIN v49.2 Closed-loop concluido: scenario={brain.scenario_id} cycles={brain.cycles}")
    if args.details:
        print(f"observed_v49_0={brain.ctx.observed_v49_0}")
        print(f"observed_v49_1={brain.ctx.meta_scenario_id}")
        print(f"meta_action={brain.ctx.meta_action}")
        print(f"inhibited_focus={brain.ctx.inhibited_focus}")
        print(f"baseline_lock={brain.ctx.baseline_attention_lock_ratio:.4f}")
        print(f"modulated_inhibited_ratio={float(delta['modulated_inhibited_ratio']):.4f}")
        print(f"modulated_dominant_ratio={float(delta['modulated_dominant_ratio']):.4f}")
        print(f"attention_shift={delta['attention_shift']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
