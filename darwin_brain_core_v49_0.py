from __future__ import annotations

"""
DARWIN v49.0 - Brain Core operacional no notebook

Objetivo:
Unificar percepcao interna, atencao, memoria de trabalho, RZS/Romero,
acao cognitiva interna, replay e consolidacao em um loop auditavel.

Fora de escopo nesta versao:
- corpo fisico;
- robotica;
- camera;
- microfone;
- atuadores reais.

Uso:
    py darwin_brain_core_v49_0.py
    py darwin_brain_core_v49_0.py --headless --cycles 12
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


DB = Path("darwin_home") / "darwin.db"

CYCLES_TABLE = "brain_cycles_v49_0"
WM_TABLE = "brain_working_memory_v49_0"
ATT_TABLE = "brain_attention_v49_0"
REPLAY_TABLE = "brain_replay_v49_0"
SOURCE_V48_9 = "geometry_multistep_plans_v48_9"

PHASES = [
    "cycle_start",
    "perceive_internal_events",
    "attention_select",
    "working_memory_update",
    "rzs_assess",
    "cognitive_action_select",
    "cognitive_action_execute",
    "replay_or_consolidate",
    "cycle_complete",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def pj(value: str) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


@dataclass
class CoreState:
    bandwidth: float = 4.0
    sigma: float = 1.0
    energy: float = 1.0
    info_self: float = 0.35
    info_external: float = 0.35
    latency: float = 1.0
    pain_signal: float = 0.0
    wellbeing_signal: float = 1.0


@dataclass
class TaskEstimate:
    task_info: float
    novelty: float
    conflict: float
    latency_cost: float
    energy_cost: float


@dataclass
class Percept:
    focus_key: str
    kind: str
    priority: float
    novelty: float
    conflict: float
    task_info: float
    source_table: str
    evidence: str
    payload: dict[str, Any]


@dataclass
class WorkingItem:
    focus_key: str
    kind: str
    activation: float
    evidence_count: int
    first_cycle: int
    last_cycle: int
    promoted: bool = False


class RomeroRZS:
    def __init__(self, eps: float = 1e-8) -> None:
        self.eps = eps

    def sigma(self, state: CoreState, estimate: TaskEstimate | None = None) -> float:
        info_eff = state.info_self + state.info_external
        bandwidth = state.bandwidth
        latency = state.latency

        if estimate is not None:
            info_eff += estimate.task_info + estimate.novelty + estimate.conflict
            bandwidth = max(bandwidth - estimate.energy_cost, self.eps)
            latency = max(latency + estimate.latency_cost, self.eps)

        return bandwidth / (max(info_eff, self.eps) * max(latency, self.eps))


class BrainMemory:
    def __init__(self, limit: int = 7) -> None:
        self.limit = limit
        self.items: dict[str, WorkingItem] = {}

    def update(self, percept: Percept, cycle_id: int) -> tuple[list[WorkingItem], list[WorkingItem]]:
        for item in self.items.values():
            item.activation = clamp(item.activation * 0.72, 0.0, 1.0)

        item = self.items.get(percept.focus_key)
        if item is None:
            item = WorkingItem(
                focus_key=percept.focus_key,
                kind=percept.kind,
                activation=clamp(0.45 + percept.priority * 0.45, 0.0, 1.0),
                evidence_count=1,
                first_cycle=cycle_id,
                last_cycle=cycle_id,
            )
            self.items[percept.focus_key] = item
        else:
            item.activation = clamp(item.activation + 0.32 + percept.priority * 0.20, 0.0, 1.0)
            item.evidence_count += 1
            item.last_cycle = cycle_id

        ordered = sorted(self.items.values(), key=lambda x: (-x.activation, -x.evidence_count, x.focus_key))
        kept = ordered[: self.limit]
        dropped = ordered[self.limit :]
        self.items = {x.focus_key: x for x in kept}
        return kept, dropped

    def snapshot(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in sorted(self.items.values(), key=lambda x: (-x.activation, x.focus_key))]

    def contains(self, focus_key: str) -> bool:
        return focus_key in self.items

    def activation(self, focus_key: str) -> float:
        item = self.items.get(focus_key)
        return item.activation if item else 0.0


class BrainStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = db_path
        self.enabled = True
        self._ensure()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin nao encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {CYCLES_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    focus_key TEXT NOT NULL DEFAULT '',
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WM_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    focus_key TEXT NOT NULL DEFAULT '',
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL DEFAULT '',
                    item_key TEXT NOT NULL DEFAULT '',
                    activation REAL NOT NULL DEFAULT 0.0,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    promoted INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {ATT_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    focus_key TEXT NOT NULL DEFAULT '',
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL DEFAULT '',
                    attention_score REAL NOT NULL DEFAULT 0.0,
                    candidates_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {REPLAY_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    focus_key TEXT NOT NULL DEFAULT '',
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL DEFAULT '',
                    replay_key TEXT NOT NULL DEFAULT '',
                    replay_kind TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )
            conn.commit()

    def table_count(self, table: str) -> int:
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                return 0
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def current_state(self) -> CoreState:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
        if row is None:
            return CoreState(sigma=4.0 / ((0.35 + 0.35) * 1.0))
        state = CoreState(
            sigma=float(row["sigma"]),
            energy=float(row["energy"]),
            info_self=float(row["info_self"]),
            info_external=float(row["info_external"]),
            latency=float(row["latency"]),
            pain_signal=float(row["pain_signal"]),
            wellbeing_signal=float(row["wellbeing_signal"]),
        )
        state.sigma = RomeroRZS().sigma(state)
        return state

    def save_state(self, state: CoreState) -> None:
        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE current_state
                SET timestamp=?, sigma=?, energy=?, info_self=?, info_external=?,
                    latency=?, pain_signal=?, wellbeing_signal=?
                WHERE id=1
                """,
                (
                    ts,
                    state.sigma,
                    state.energy,
                    state.info_self,
                    state.info_external,
                    state.latency,
                    state.pain_signal,
                    state.wellbeing_signal,
                ),
            )
            conn.execute(
                """
                INSERT INTO state_history (
                    timestamp, sigma, energy, info_self, info_external,
                    latency, pain_signal, wellbeing_signal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    state.sigma,
                    state.energy,
                    state.info_self,
                    state.info_external,
                    state.latency,
                    state.pain_signal,
                    state.wellbeing_signal,
                ),
            )
            conn.commit()

    def add_semantic_memory(self, key: str, content: str, confidence: float) -> None:
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
                (key, content, clamp(confidence, 0.0, 0.99), "brain_core_v49_0", now()),
            )
            conn.commit()

    def log_cycle(
        self,
        scenario_id: str,
        cycle_id: int,
        phase: str,
        *,
        focus_key: str = "",
        rzs_decision: str = "",
        sigma_before: float = 0.0,
        sigma_after: float = 0.0,
        cognitive_action: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {CYCLES_TABLE} (
                    timestamp, scenario_id, cycle_id, phase, focus_key, rzs_decision,
                    sigma_before, sigma_after, cognitive_action, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    phase,
                    focus_key,
                    rzs_decision,
                    sigma_before,
                    sigma_after,
                    cognitive_action,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_attention(
        self,
        scenario_id: str,
        cycle_id: int,
        focus: Percept,
        candidates: list[dict[str, Any]],
        score: float,
        sigma_before: float,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {ATT_TABLE} (
                    timestamp, scenario_id, cycle_id, phase, focus_key, rzs_decision,
                    sigma_before, sigma_after, cognitive_action, attention_score,
                    candidates_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    "attention_select",
                    focus.focus_key,
                    "",
                    sigma_before,
                    sigma_before,
                    "",
                    score,
                    js(candidates),
                    js({"selected": asdict(focus)}),
                ),
            )
            conn.commit()

    def log_working_memory(
        self,
        scenario_id: str,
        cycle_id: int,
        focus_key: str,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
        action: str,
        items: list[WorkingItem],
        dropped: list[WorkingItem],
    ) -> None:
        with self.connect() as conn:
            for item in items:
                conn.execute(
                    f"""
                    INSERT INTO {WM_TABLE} (
                        timestamp, scenario_id, cycle_id, phase, focus_key, rzs_decision,
                        sigma_before, sigma_after, cognitive_action, item_key, activation,
                        evidence_count, promoted, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(),
                        scenario_id,
                        cycle_id,
                        "working_memory_update",
                        focus_key,
                        rzs_decision,
                        sigma_before,
                        sigma_after,
                        action,
                        item.focus_key,
                        item.activation,
                        item.evidence_count,
                        1 if item.promoted else 0,
                        js({"item": asdict(item), "decayed": True, "dropped": [asdict(x) for x in dropped]}),
                    ),
                )
            conn.commit()

    def log_replay(
        self,
        scenario_id: str,
        cycle_id: int,
        focus_key: str,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
        action: str,
        replay_key: str,
        replay_kind: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {REPLAY_TABLE} (
                    timestamp, scenario_id, cycle_id, phase, focus_key, rzs_decision,
                    sigma_before, sigma_after, cognitive_action, replay_key,
                    replay_kind, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    "replay_or_consolidate",
                    focus_key,
                    rzs_decision,
                    sigma_before,
                    sigma_after,
                    action,
                    replay_key,
                    replay_kind,
                    js(payload),
                ),
            )
            conn.commit()

    def recent_internal_events(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "episodes": [],
            "semantic_memory": [],
            "state_history": [],
            "v48_9": {"count": 0, "max_id": 0, "recent": []},
            "open_tensions": 0,
        }
        with self.connect() as conn:
            for table in ("episodes", "semantic_memory", "state_history", SOURCE_V48_9, "tension_cases"):
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not exists:
                    continue

                if table == "episodes":
                    out["episodes"] = [
                        dict(r)
                        for r in conn.execute(
                            "SELECT id,timestamp,module,context,action_taken,outcome,lesson,sigma_before,sigma_after "
                            "FROM episodes ORDER BY id DESC LIMIT 12"
                        ).fetchall()
                    ]
                elif table == "semantic_memory":
                    out["semantic_memory"] = [
                        dict(r)
                        for r in conn.execute(
                            "SELECT key,content,confidence,source,updated_at "
                            "FROM semantic_memory ORDER BY updated_at DESC LIMIT 20"
                        ).fetchall()
                    ]
                elif table == "state_history":
                    out["state_history"] = [
                        dict(r)
                        for r in conn.execute(
                            "SELECT id,timestamp,sigma,energy,info_self,info_external,latency,pain_signal,wellbeing_signal "
                            "FROM state_history ORDER BY id DESC LIMIT 12"
                        ).fetchall()
                    ]
                elif table == SOURCE_V48_9:
                    row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id),0) AS max_id FROM {SOURCE_V48_9}").fetchone()
                    out["v48_9"]["count"] = int(row["n"])
                    out["v48_9"]["max_id"] = int(row["max_id"])
                    out["v48_9"]["recent"] = [
                        dict(r)
                        for r in conn.execute(
                            f"SELECT id,scenario_id,action_kind,task_id,final_status,observed_outcome "
                            f"FROM {SOURCE_V48_9} ORDER BY id DESC LIMIT 8"
                        ).fetchall()
                    ]
                elif table == "tension_cases":
                    row = conn.execute("SELECT COUNT(*) AS n FROM tension_cases WHERE status='open'").fetchone()
                    out["open_tensions"] = int(row["n"])
        return out


class BrainCore:
    def __init__(self, cycles_target: int = 12, seed: int | None = None) -> None:
        self.store = BrainStore()
        self.rzs = RomeroRZS()
        self.memory = BrainMemory(limit=7)
        self.state = self.store.current_state()
        self.cycles_target = max(1, cycles_target)
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.scenario_id = f"V490-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.cycle_id = 0
        self.last_focus: Percept | None = None
        self.last_action = ""
        self.last_rzs_decision = ""
        self.last_log: list[str] = []
        self.v48_9_count_before = self.store.table_count(SOURCE_V48_9)
        self.v48_9_max_before = self._v48_9_max_id()

    def _v48_9_max_id(self) -> int:
        try:
            with self.store.connect() as conn:
                row = conn.execute(f"SELECT COALESCE(MAX(id),0) AS n FROM {SOURCE_V48_9}").fetchone()
                return int(row["n"]) if row else 0
        except Exception:
            return 0

    def append_log(self, text: str) -> None:
        self.last_log.append(text)
        self.last_log = self.last_log[-12:]

    def task_for_percept(self, percept: Percept) -> TaskEstimate:
        base_latency = 0.03 + percept.task_info * 0.06 + percept.conflict * 0.08
        return TaskEstimate(
            task_info=percept.task_info,
            novelty=percept.novelty,
            conflict=percept.conflict,
            latency_cost=base_latency,
            energy_cost=0.04 + percept.conflict * 0.05 + percept.novelty * 0.03,
        )

    def perceive(self, cycle_id: int) -> list[Percept]:
        data = self.store.recent_internal_events()
        percepts: list[Percept] = []

        for ep in data["episodes"][:5]:
            outcome = str(ep.get("outcome", ""))
            if outcome and outcome != "success":
                percepts.append(
                    Percept(
                        focus_key=f"failure_recent:episode:{ep['id']}",
                        kind="failure_recent",
                        priority=0.96,
                        novelty=0.38,
                        conflict=0.62,
                        task_info=0.48,
                        source_table="episodes",
                        evidence=str(ep.get("lesson", ""))[:180],
                        payload={"episode": ep},
                    )
                )
                break

        open_tensions = int(data.get("open_tensions", 0))
        if open_tensions > 0:
            percepts.append(
                Percept(
                    focus_key="tension:open_cases",
                    kind="tension_open",
                    priority=0.90,
                    novelty=0.30,
                    conflict=0.58,
                    task_info=0.50,
                    source_table="tension_cases",
                    evidence=f"{open_tensions} tension cases open",
                    payload={"open_tensions": open_tensions},
                )
            )

        v48 = data["v48_9"]
        has_complete = any(r.get("action_kind") == "planning_complete" for r in v48.get("recent", []))
        if not has_complete:
            percepts.append(
                Percept(
                    focus_key="plan:v48_9_completion_uncertain",
                    kind="plan_incomplete",
                    priority=0.76,
                    novelty=0.24,
                    conflict=0.44,
                    task_info=0.52,
                    source_table=SOURCE_V48_9,
                    evidence="recent v48.9 window has no planning_complete",
                    payload={"v48_9": v48},
                )
            )
        else:
            percepts.append(
                Percept(
                    focus_key="plan:v48_9_stable_chain",
                    kind="plan_trace",
                    priority=0.54,
                    novelty=0.18,
                    conflict=0.12,
                    task_info=0.38,
                    source_table=SOURCE_V48_9,
                    evidence="v48.9 planning trace available for replay",
                    payload={"v48_9": v48},
                )
            )

        weak = [m for m in data["semantic_memory"] if float(m.get("confidence", 1.0)) < 0.45]
        if weak:
            m = weak[0]
            percepts.append(
                Percept(
                    focus_key=f"memory_weak:{m['key']}",
                    kind="memory_weak",
                    priority=0.68,
                    novelty=0.22,
                    conflict=0.20,
                    task_info=0.36,
                    source_table="semantic_memory",
                    evidence=f"low confidence memory {m['key']}",
                    payload={"memory": m},
                )
            )
        else:
            percepts.append(
                Percept(
                    focus_key="memory:brain_v49_bootstrap_gap",
                    kind="memory_weak",
                    priority=0.62,
                    novelty=0.32,
                    conflict=0.16,
                    task_info=0.34,
                    source_table="semantic_memory",
                    evidence="brain v49 has no stable working-memory trace yet",
                    payload={"semantic_memory_seen": len(data["semantic_memory"])},
                )
            )

        if data["state_history"]:
            latest = data["state_history"][0]
            sigma = float(latest.get("sigma", self.state.sigma))
            energy = float(latest.get("energy", self.state.energy))
        else:
            sigma = self.state.sigma
            energy = self.state.energy

        internal_load = self.state.info_external + self.state.info_self + self.state.latency
        if sigma < 1.10 or energy < 0.55 or internal_load > 3.25 or cycle_id in (6, 12):
            percepts.append(
                Percept(
                    focus_key="stability:rzs_consolidation_need",
                    kind="need_consolidation",
                    priority=0.92,
                    novelty=0.10,
                    conflict=0.52,
                    task_info=0.44,
                    source_table="state_history",
                    evidence=f"sigma={sigma:.3f}; energy={energy:.3f}; load={internal_load:.3f}",
                    payload={"sigma": sigma, "energy": energy, "internal_load": internal_load},
                )
            )

        if data["episodes"]:
            ep = data["episodes"][0]
            percepts.append(
                Percept(
                    focus_key=f"replay:episode:{ep['id']}",
                    kind="replay_candidate",
                    priority=0.50,
                    novelty=0.14,
                    conflict=0.12,
                    task_info=0.28,
                    source_table="episodes",
                    evidence=str(ep.get("lesson", ""))[:180],
                    payload={"episode": ep},
                )
            )

        return percepts

    def select_attention(self, percepts: list[Percept]) -> tuple[Percept, list[dict[str, Any]], float]:
        candidates: list[tuple[float, Percept]] = []
        for p in percepts:
            wm_bonus = 0.12 if self.memory.contains(p.focus_key) else 0.0
            fatigue_penalty = self.memory.activation(p.focus_key) * 0.08
            score = p.priority + wm_bonus + p.conflict * 0.20 + p.novelty * 0.10 - fatigue_penalty
            candidates.append((score, p))
        candidates.sort(key=lambda x: (-x[0], x[1].focus_key))
        selected_score, selected = candidates[0]
        return selected, [{"score": round(s, 4), **asdict(p)} for s, p in candidates], selected_score

    def assess_rzs(self, percept: Percept, cycle_id: int) -> tuple[str, float, bool, TaskEstimate]:
        estimate = self.task_for_percept(percept)
        projected = self.rzs.sigma(self.state, estimate)
        demanded = projected < 1.10 or self.state.energy < 0.58 or percept.kind == "need_consolidation"

        if self.state.energy < 0.55 or projected < 0.95 or percept.kind == "need_consolidation":
            decision = "consolidate"
        elif projected < 1.10:
            decision = "pause_for_stability"
        elif percept.conflict > 0.50:
            decision = "narrow_focus"
        elif cycle_id % 4 == 0 and len(self.memory.items) >= 2:
            decision = "replay_memory"
        else:
            decision = "continue"

        return decision, projected, demanded, estimate

    def select_action(self, percept: Percept, rzs_decision: str) -> str:
        if rzs_decision == "consolidate":
            return "consolidate"
        if rzs_decision == "pause_for_stability":
            return "pause_for_stability"
        if rzs_decision == "replay_memory":
            return "replay_memory"
        if rzs_decision == "narrow_focus":
            return "narrow_focus"
        if percept.kind == "failure_recent":
            return "form_hypothesis"
        if percept.kind == "plan_incomplete":
            return "review_plan"
        if percept.kind == "memory_weak":
            return "consult_memory"
        if percept.kind == "plan_trace":
            return "replay_v48_9_plan"
        return "observe_internal"

    def execute_action(self, percept: Percept, action: str, estimate: TaskEstimate) -> tuple[float, dict[str, Any]]:
        sigma_before = self.state.sigma
        payload: dict[str, Any] = {"percept": asdict(percept), "estimate": asdict(estimate)}

        if action == "consolidate":
            self.state.bandwidth = clamp(self.state.bandwidth + 0.30, 1.2, 5.0)
            self.state.energy = clamp(self.state.energy + 0.22, 0.0, 1.0)
            self.state.info_external = clamp(self.state.info_external * 0.58, 0.0, 3.0)
            self.state.info_self = clamp(self.state.info_self * 0.82, 0.0, 3.0)
            self.state.latency = clamp(1.0 + (self.state.latency - 1.0) * 0.55, 0.75, 3.0)
            self.state.pain_signal = clamp(self.state.pain_signal * 0.35, 0.0, 3.0)
            payload["effect"] = "reduced load and restored energy"
        elif action == "pause_for_stability":
            self.state.energy = clamp(self.state.energy + 0.08, 0.0, 1.0)
            self.state.info_external = clamp(self.state.info_external * 0.78, 0.0, 3.0)
            self.state.latency = clamp(self.state.latency * 0.92, 0.75, 3.0)
            payload["effect"] = "paused before unstable action"
        elif action in ("replay_memory", "replay_v48_9_plan"):
            self.state.info_self = clamp(self.state.info_self + 0.05, 0.0, 3.0)
            self.state.info_external = clamp(self.state.info_external * 0.86, 0.0, 3.0)
            self.state.energy = clamp(self.state.energy - 0.02, 0.0, 1.0)
            payload["effect"] = "replayed stored trace"
        elif action == "narrow_focus":
            self.state.info_external = clamp(self.state.info_external * 0.88, 0.0, 3.0)
            self.state.info_self = clamp(self.state.info_self + 0.04, 0.0, 3.0)
            self.state.energy = clamp(self.state.energy - estimate.energy_cost * 0.45, 0.0, 1.0)
            payload["effect"] = "reduced attentional breadth"
        else:
            self.state.bandwidth = clamp(self.state.bandwidth - estimate.energy_cost, 1.2, 5.0)
            self.state.energy = clamp(self.state.energy - estimate.energy_cost, 0.0, 1.0)
            self.state.info_external = clamp(self.state.info_external + estimate.task_info * 0.12 + estimate.novelty * 0.10, 0.0, 3.0)
            self.state.info_self = clamp(self.state.info_self + estimate.conflict * 0.10, 0.0, 3.0)
            self.state.latency = clamp(self.state.latency + estimate.latency_cost, 0.75, 3.0)
            payload["effect"] = "internal cognitive work"

        self.state.sigma = self.rzs.sigma(self.state)
        delta = self.state.sigma - sigma_before
        self.state.pain_signal = clamp((0.0 if delta >= -0.12 else abs(delta) * 0.45) + self.state.pain_signal, 0.0, 3.0)
        self.state.wellbeing_signal = clamp(self.state.energy + max(0.0, delta) * 0.20, 0.0, 3.0)
        self.store.save_state(self.state)
        return self.state.sigma, payload

    def promote_memory_if_ready(self, items: list[WorkingItem]) -> None:
        for item in items:
            if item.promoted:
                continue
            if item.evidence_count >= 2 and item.activation >= 0.55:
                key = f"brain_v49:focus:{item.focus_key}"
                self.store.add_semantic_memory(
                    key,
                    f"working_memory_focus kind={item.kind} evidence={item.evidence_count}",
                    min(0.72, 0.42 + item.evidence_count * 0.10),
                )
                item.promoted = True

    def maybe_replay(self, cycle_id: int, percept: Percept, rzs_decision: str, action: str, sigma_before: float, sigma_after: float) -> None:
        should_replay = action in ("replay_memory", "replay_v48_9_plan") or cycle_id % 5 == 0
        if not should_replay:
            return
        snapshot = self.memory.snapshot()
        replay_key = snapshot[0]["focus_key"] if snapshot else percept.focus_key
        replay_kind = "working_memory_replay" if action == "replay_memory" else "background_trace_replay"
        self.store.log_replay(
            self.scenario_id,
            cycle_id,
            percept.focus_key,
            rzs_decision,
            sigma_before,
            sigma_after,
            action,
            replay_key,
            replay_kind,
            {"working_memory": snapshot, "selected_percept": asdict(percept)},
        )

    def run_cycle(self) -> bool:
        if self.cycle_id >= self.cycles_target:
            return False

        self.cycle_id += 1
        cid = self.cycle_id
        sigma_at_start = self.state.sigma

        self.store.log_cycle(
            self.scenario_id,
            cid,
            "cycle_start",
            sigma_before=sigma_at_start,
            sigma_after=sigma_at_start,
            payload={
                "phase_order": PHASES,
                "v48_9_count_before": self.v48_9_count_before,
                "v48_9_max_before": self.v48_9_max_before,
            },
        )

        percepts = self.perceive(cid)
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "perceive_internal_events",
            sigma_before=self.state.sigma,
            sigma_after=self.state.sigma,
            payload={
                "sources": sorted({p.source_table for p in percepts}),
                "percepts": [asdict(p) for p in percepts],
            },
        )

        focus, candidates, score = self.select_attention(percepts)
        self.last_focus = focus
        self.store.log_attention(self.scenario_id, cid, focus, candidates, score, self.state.sigma)
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "attention_select",
            focus_key=focus.focus_key,
            sigma_before=self.state.sigma,
            sigma_after=self.state.sigma,
            payload={"score": score, "selected": asdict(focus), "candidates": candidates},
        )

        items, dropped = self.memory.update(focus, cid)
        self.promote_memory_if_ready(items)
        self.store.log_working_memory(self.scenario_id, cid, focus.focus_key, "", self.state.sigma, self.state.sigma, "", items, dropped)
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "working_memory_update",
            focus_key=focus.focus_key,
            sigma_before=self.state.sigma,
            sigma_after=self.state.sigma,
            payload={
                "limit": self.memory.limit,
                "items": [asdict(x) for x in items],
                "dropped": [asdict(x) for x in dropped],
                "decay_applied": True,
            },
        )

        rzs_decision, projected_sigma, stability_demanded, estimate = self.assess_rzs(focus, cid)
        self.last_rzs_decision = rzs_decision
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "rzs_assess",
            focus_key=focus.focus_key,
            rzs_decision=rzs_decision,
            sigma_before=self.state.sigma,
            sigma_after=projected_sigma,
            payload={
                "formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
                "estimate": asdict(estimate),
                "state": asdict(self.state),
                "projected_sigma": projected_sigma,
                "stability_demanded": stability_demanded,
            },
        )

        action = self.select_action(focus, rzs_decision)
        self.last_action = action
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "cognitive_action_select",
            focus_key=focus.focus_key,
            rzs_decision=rzs_decision,
            sigma_before=self.state.sigma,
            sigma_after=projected_sigma,
            cognitive_action=action,
            payload={"selection_reason": f"action selected from rzs_decision={rzs_decision} and focus_kind={focus.kind}"},
        )

        sigma_before_action = self.state.sigma
        sigma_after_action, action_payload = self.execute_action(focus, action, estimate)
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "cognitive_action_execute",
            focus_key=focus.focus_key,
            rzs_decision=rzs_decision,
            sigma_before=sigma_before_action,
            sigma_after=sigma_after_action,
            cognitive_action=action,
            payload=action_payload,
        )

        self.maybe_replay(cid, focus, rzs_decision, action, sigma_before_action, sigma_after_action)
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "replay_or_consolidate",
            focus_key=focus.focus_key,
            rzs_decision=rzs_decision,
            sigma_before=sigma_before_action,
            sigma_after=sigma_after_action,
            cognitive_action=action,
            payload={
                "replay_considered": True,
                "replay_executed": action in ("replay_memory", "replay_v48_9_plan") or cid % 5 == 0,
                "working_memory": self.memory.snapshot(),
            },
        )

        is_final = cid >= self.cycles_target
        self.store.log_cycle(
            self.scenario_id,
            cid,
            "cycle_complete",
            focus_key=focus.focus_key,
            rzs_decision=rzs_decision,
            sigma_before=sigma_at_start,
            sigma_after=self.state.sigma,
            cognitive_action=action,
            payload={
                "scenario_complete": is_final,
                "cycles_completed": cid,
                "v48_9_count_before": self.v48_9_count_before,
                "v48_9_count_after": self.store.table_count(SOURCE_V48_9),
                "v48_9_max_before": self.v48_9_max_before,
                "v48_9_max_after": self._v48_9_max_id(),
            },
        )

        self.append_log(
            f"C{cid:02d} focus={focus.kind} rzs={rzs_decision} action={action} sigma={self.state.sigma:.3f}"
        )
        return not is_final

    def run_headless(self) -> None:
        while self.run_cycle():
            pass


class BrainPanel:
    BG = "#edf3f8"
    INK = "#172534"
    MUTED = "#5e7387"
    BLUE = "#316bd1"
    GREEN = "#2b9e68"
    ORANGE = "#c77a22"

    def __init__(self, root: tk.Tk, core: BrainCore, interval_ms: int = 700) -> None:
        self.root = root
        self.core = core
        self.interval_ms = interval_ms
        self.running = False

        root.title("DARWIN v49.0 - Brain Core")
        root.geometry("1280x800")
        root.configure(bg=self.BG)

        self.cv = tk.Canvas(root, width=820, height=760, bg=self.BG, highlightthickness=0)
        self.cv.pack(side="left", padx=12, pady=12)

        side = tk.Frame(root, bg=self.BG)
        side.pack(side="right", fill="both", expand=True, padx=(0, 12), pady=12)

        bar = tk.Frame(side, bg=self.BG)
        bar.pack(fill="x")
        ttk.Button(bar, text="Iniciar", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Ciclo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        for i in range(3):
            bar.grid_columnconfigure(i, weight=1)

        self.status = tk.StringVar(value="Pronto. Brain Core v49.0 aguardando ciclo.")
        tk.Label(side, textvariable=self.status, bg="white", fg=self.INK, wraplength=410,
                 justify="left", anchor="w", padx=10, pady=8, relief="solid", bd=1).pack(fill="x", pady=(8, 8))

        self.trace = tk.Text(side, height=18, wrap="word", bg="white", fg=self.INK, relief="solid", bd=1)
        self.trace.pack(fill="x", pady=(0, 8))
        self.trace.config(state="disabled")

        self.hist = tk.Text(side, height=22, wrap="word", bg="#10263d", fg="#e8f4ff", relief="solid", bd=1)
        self.hist.pack(fill="both", expand=True)
        self.hist.config(state="disabled")

        self.loop()

    def start(self) -> None:
        self.running = True
        self.write_history("AUTO iniciado.")

    def pause(self) -> None:
        self.running = False
        self.write_history("AUTO pausado.")

    def step(self) -> None:
        more = self.core.run_cycle()
        self.running = self.running and more
        self.refresh_text()

    def loop(self) -> None:
        if self.running:
            more = self.core.run_cycle()
            self.running = more
            self.refresh_text()
        self.draw()
        self.root.after(self.interval_ms, self.loop)

    def refresh_text(self) -> None:
        focus = self.core.last_focus
        lines = [
            f"Scenario: {self.core.scenario_id}",
            f"Cycle: {self.core.cycle_id}/{self.core.cycles_target}",
            f"Sigma: {self.core.state.sigma:.4f}",
            f"Energy: {self.core.state.energy:.4f}",
            f"Info self/external: {self.core.state.info_self:.4f}/{self.core.state.info_external:.4f}",
            f"Latency: {self.core.state.latency:.4f}",
            f"RZS decision: {self.core.last_rzs_decision or '-'}",
            f"Cognitive action: {self.core.last_action or '-'}",
            "",
            "Focus:",
            f"- {focus.focus_key if focus else '-'}",
            f"- kind={focus.kind if focus else '-'}",
            f"- evidence={focus.evidence if focus else '-'}",
            "",
            "Working memory:",
        ]
        for item in self.core.memory.snapshot():
            lines.append(f"- {item['focus_key']} | act={item['activation']:.2f} | evidence={item['evidence_count']}")
        self.write_trace("\n".join(lines))
        if self.core.last_log:
            self.write_history(self.core.last_log[-1])
        self.status.set(
            f"Cycle {self.core.cycle_id}/{self.core.cycles_target}: "
            f"{self.core.last_rzs_decision or '-'} -> {self.core.last_action or '-'}"
        )

    def write_trace(self, text: str) -> None:
        self.trace.config(state="normal")
        self.trace.delete("1.0", "end")
        self.trace.insert("1.0", text)
        self.trace.config(state="disabled")

    def write_history(self, text: str) -> None:
        self.hist.config(state="normal")
        self.hist.insert("end", text + "\n")
        self.hist.see("end")
        self.hist.config(state="disabled")

    def rr(self, x1: int, y1: int, x2: int, y2: int, r: int = 16, **kw) -> int:
        pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, splinesteps=18, **kw)

    def draw(self) -> None:
        c = self.cv
        c.delete("all")
        self.rr(18, 18, 802, 742, 26, fill="#f9fbfe", outline="#c8d6e5", width=2)
        c.create_text(42, 48, anchor="w", text="DARWIN v49.0 - Brain Core", font=("Segoe UI", 20, "bold"), fill=self.INK)
        c.create_text(42, 76, anchor="w", text="Loop cognitivo unico: percepcao interna, atencao, memoria, RZS, acao e replay.", font=("Segoe UI", 10), fill=self.MUTED)

        cx, cy = 170, 235
        c.create_oval(cx-64, cy-64, cx+64, cy+64, fill="#dfefff", outline="#94b8e8", width=3)
        c.create_oval(cx-22, cy-18, cx-10, cy-6, fill=self.INK, outline="")
        c.create_oval(cx+10, cy-18, cx+22, cy-6, fill=self.INK, outline="")
        c.create_arc(cx-26, cy-4, cx+26, cy+34, start=200, extent=140, style="arc", outline=self.GREEN, width=3)
        c.create_text(cx, cy+92, text=f"sigma {self.core.state.sigma:.2f}", font=("Segoe UI", 14, "bold"), fill=self.BLUE)

        phases = PHASES[:-1]
        x0, y0 = 340, 130
        for i, ph in enumerate(phases):
            y = y0 + i * 62
            active = i == min(max(self.core.cycle_id % len(phases), 0), len(phases)-1)
            col = self.BLUE if active else "#d6e2ef"
            fill = "#eef6ff" if active else "white"
            self.rr(x0, y, x0+390, y+42, 12, fill=fill, outline=col, width=2)
            c.create_text(x0+16, y+21, anchor="w", text=ph, font=("Segoe UI", 10, "bold"), fill=self.INK)

        c.create_text(48, 390, anchor="w", text="Atencao", font=("Segoe UI", 14, "bold"), fill=self.INK)
        focus = self.core.last_focus
        focus_text = focus.focus_key if focus else "(sem foco ainda)"
        c.create_text(48, 420, anchor="w", text=focus_text[:42], font=("Segoe UI", 10), fill=self.MUTED)
        c.create_text(48, 455, anchor="w", text=f"RZS: {self.core.last_rzs_decision or '-'}", font=("Segoe UI", 12, "bold"), fill=self.ORANGE)
        c.create_text(48, 485, anchor="w", text=f"Acao: {self.core.last_action or '-'}", font=("Segoe UI", 12, "bold"), fill=self.BLUE)

        c.create_text(48, 540, anchor="w", text="Memoria de trabalho", font=("Segoe UI", 14, "bold"), fill=self.INK)
        for i, item in enumerate(self.core.memory.snapshot()[:7]):
            y = 570 + i * 24
            width = int(170 * item["activation"])
            c.create_rectangle(50, y, 50+width, y+14, fill="#8ed0a8", outline="")
            c.create_text(230, y+7, anchor="w", text=item["focus_key"][:48], font=("Segoe UI", 8), fill=self.MUTED)


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Brain Core v49.0")
    ap.add_argument("--headless", action="store_true", help="Executa sem painel Tkinter.")
    ap.add_argument("--cycles", type=int, default=12, help="Numero de ciclos para executar.")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    core = BrainCore(cycles_target=args.cycles, seed=args.seed)
    if args.headless:
        core.run_headless()
        print(f"DARWIN v49.0 Brain Core concluido: scenario={core.scenario_id} cycles={core.cycle_id}")
        return 0

    root = tk.Tk()
    BrainPanel(root, core)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
