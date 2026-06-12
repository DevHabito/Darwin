from __future__ import annotations

"""
DARWIN v49.1 - Metacognicao operacional do Brain Core

Objetivo:
Observar o Brain Core v49.0, medir sua saude operacional, detectar riscos
internos e registrar intervencoes cognitivas sem criar um corpo fisico.

Fora de escopo:
- consciencia declarada;
- corpo fisico, sensores reais, camera, microfone ou atuadores;
- dependencias externas.

Uso:
    py darwin_brain_metacognition_v49_1.py --passes 6
    py darwin_brain_metacognition_v49_1.py --passes 6 --details
"""

import argparse
import json
import random
import sqlite3
import time
from collections import Counter, defaultdict
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
SELF_CHECKS = "brain_self_checks_v49_1"
INTERVENTIONS = "brain_stability_interventions_v49_1"

V49_PHASES = [
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

META_PHASES = [
    "meta_cycle_start",
    "read_brain_trace",
    "self_check",
    "health_assess",
    "meta_decision_select",
    "meta_action_execute",
    "meta_cycle_complete",
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
class TraceSummary:
    observed_scenario_id: str
    completed_cycles: int
    cycle_events: int
    phase_integrity: bool
    rzs_non_continue: int
    last_sigma: float
    current_energy: float
    attention_lock_ratio: float
    dominant_focus: str
    action_monotony_ratio: float
    dominant_action: str
    max_working_memory_items: int
    replay_events: int
    cycles_since_replay: int
    consolidation_events: int
    v48_9_integrity: bool


@dataclass
class RiskVector:
    integrity: float
    sigma_low: float
    energy_low: float
    attention_lock: float
    action_monotony: float
    replay_gap: float
    working_memory_pressure: float
    rzs_absence: float

    def total(self) -> float:
        return clamp(
            self.integrity * 0.35
            + self.sigma_low * 0.16
            + self.energy_low * 0.14
            + self.attention_lock * 0.18
            + self.action_monotony * 0.08
            + self.replay_gap * 0.10
            + self.working_memory_pressure * 0.06
            + self.rzs_absence * 0.12
        )


@dataclass
class MetaDecision:
    meta_decision: str
    meta_action: str
    rationale: str


class MetaStore:
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
                CREATE TABLE IF NOT EXISTS {META_CYCLES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    meta_cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    observed_scenario_id TEXT NOT NULL DEFAULT '',
                    health_score REAL NOT NULL DEFAULT 0.0,
                    risk_score REAL NOT NULL DEFAULT 0.0,
                    meta_decision TEXT NOT NULL DEFAULT '',
                    meta_action TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SELF_CHECKS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    meta_cycle_id INTEGER NOT NULL,
                    observed_scenario_id TEXT NOT NULL DEFAULT '',
                    check_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {INTERVENTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    meta_cycle_id INTEGER NOT NULL,
                    observed_scenario_id TEXT NOT NULL DEFAULT '',
                    intervention_kind TEXT NOT NULL,
                    meta_decision TEXT NOT NULL,
                    meta_action TEXT NOT NULL,
                    health_before REAL NOT NULL DEFAULT 0.0,
                    health_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )
            conn.commit()

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def rows(self, conn: sqlite3.Connection, table: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
        if not self.table_exists(conn, table):
            return []
        where = ""
        params: tuple[Any, ...] = ()
        if scenario_id is not None and "scenario_id" in self.columns(conn, table):
            where = " WHERE scenario_id=?"
            params = (scenario_id,)
        out = []
        for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"))
            out.append(item)
        return out

    def columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        if not self.table_exists(conn, table):
            return set()
        return {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def latest_v49_scenario(self, conn: sqlite3.Connection) -> str | None:
        rows = self.rows(conn, V49_CYCLES)
        completed = [
            str(r["scenario_id"])
            for r in rows
            if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
        ]
        if completed:
            return completed[-1]
        ids = [str(r["scenario_id"]) for r in rows if r.get("scenario_id")]
        return ids[-1] if ids else None

    def current_energy(self, conn: sqlite3.Connection) -> float:
        if not self.table_exists(conn, "current_state"):
            return 1.0
        row = conn.execute("SELECT energy FROM current_state WHERE id=1").fetchone()
        return float(row["energy"]) if row else 1.0

    def v48_9_count_max(self, conn: sqlite3.Connection) -> tuple[int, int]:
        if not self.table_exists(conn, SOURCE_V48_9):
            return 0, 0
        row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {SOURCE_V48_9}").fetchone()
        return int(row["n"]), int(row["max_id"])

    def log_meta(
        self,
        scenario_id: str,
        meta_cycle_id: int,
        phase: str,
        *,
        observed_scenario_id: str = "",
        health_score: float = 0.0,
        risk_score: float = 0.0,
        meta_decision: str = "",
        meta_action: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {META_CYCLES} (
                    timestamp, scenario_id, meta_cycle_id, phase, observed_scenario_id,
                    health_score, risk_score, meta_decision, meta_action, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    meta_cycle_id,
                    phase,
                    observed_scenario_id,
                    health_score,
                    risk_score,
                    meta_decision,
                    meta_action,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_check(
        self,
        scenario_id: str,
        meta_cycle_id: int,
        observed_scenario_id: str,
        check_name: str,
        status: bool,
        score: float,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SELF_CHECKS} (
                    timestamp, scenario_id, meta_cycle_id, observed_scenario_id,
                    check_name, status, score, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    meta_cycle_id,
                    observed_scenario_id,
                    check_name,
                    "OK" if status else "ATTENTION",
                    score,
                    js(payload),
                ),
            )
            conn.commit()

    def log_intervention(
        self,
        scenario_id: str,
        meta_cycle_id: int,
        observed_scenario_id: str,
        decision: MetaDecision,
        health_before: float,
        health_after: float,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {INTERVENTIONS} (
                    timestamp, scenario_id, meta_cycle_id, observed_scenario_id,
                    intervention_kind, meta_decision, meta_action, health_before,
                    health_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    meta_cycle_id,
                    observed_scenario_id,
                    decision.meta_action,
                    decision.meta_decision,
                    decision.meta_action,
                    health_before,
                    health_after,
                    js(payload),
                ),
            )
            conn.commit()

    def upsert_semantic_memory(self, key: str, content: str, confidence: float) -> None:
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
                (key, content, clamp(confidence, 0.0, 0.99), "brain_metacognition_v49_1", now()),
            )
            conn.commit()


class MetaCognition:
    def __init__(self, passes: int = 6, seed: int | None = None, execute: bool = True) -> None:
        self.store = MetaStore()
        self.passes = max(1, passes)
        self.execute = execute
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.scenario_id = f"V491-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.last_summary: TraceSummary | None = None
        self.last_risk: RiskVector | None = None
        self.last_decision: MetaDecision | None = None

    def trace_summary(self) -> TraceSummary:
        with self.store.connect() as conn:
            observed = self.store.latest_v49_scenario(conn)
            if not observed:
                raise RuntimeError("Nenhum cenario v49.0 encontrado. Rode primeiro: py darwin_brain_core_v49_0.py --headless --cycles 12")

            cycle_rows = [r for r in self.store.rows(conn, V49_CYCLES) if r.get("scenario_id") == observed]
            wm_rows = [r for r in self.store.rows(conn, V49_WM) if r.get("scenario_id") == observed]
            att_rows = [r for r in self.store.rows(conn, V49_ATT) if r.get("scenario_id") == observed]
            replay_rows = [r for r in self.store.rows(conn, V49_REPLAY) if r.get("scenario_id") == observed]
            current_energy = self.store.current_energy(conn)
            v48_count_now, v48_max_now = self.store.v48_9_count_max(conn)

        by_cycle: dict[int, list[str]] = defaultdict(list)
        for row in cycle_rows:
            by_cycle[int(row["cycle_id"])].append(str(row["phase"]))
        phase_integrity = bool(by_cycle) and all(phases == V49_PHASES for phases in by_cycle.values())
        completed_cycles = sorted(int(r["cycle_id"]) for r in cycle_rows if r.get("phase") == "cycle_complete")

        decisions = [str(r.get("rzs_decision") or "") for r in cycle_rows if r.get("phase") == "rzs_assess"]
        actions = [str(r.get("cognitive_action") or "") for r in cycle_rows if r.get("phase") == "cognitive_action_execute"]
        focuses = [str(r.get("focus_key") or "") for r in att_rows if str(r.get("focus_key") or "")]
        wm_per_cycle = Counter(int(r["cycle_id"]) for r in wm_rows)
        replay_cycles = sorted({int(r["cycle_id"]) for r in replay_rows})

        focus_counts = Counter(focuses)
        dominant_focus, dominant_focus_count = focus_counts.most_common(1)[0] if focus_counts else ("", 0)
        action_counts = Counter(actions)
        dominant_action, dominant_action_count = action_counts.most_common(1)[0] if action_counts else ("", 0)

        final_rows = [
            r for r in cycle_rows
            if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
        ]
        final_payload = final_rows[-1].get("payload", {}) if final_rows else {}
        v48_integrity = (
            bool(final_payload)
            and final_payload.get("v48_9_count_before") == final_payload.get("v48_9_count_after") == v48_count_now
            and final_payload.get("v48_9_max_before") == final_payload.get("v48_9_max_after") == v48_max_now
        )
        last_sigma = float(final_rows[-1].get("sigma_after") or 0.0) if final_rows else 0.0
        last_cycle = max(completed_cycles) if completed_cycles else 0
        last_replay = max(replay_cycles) if replay_cycles else 0

        return TraceSummary(
            observed_scenario_id=observed,
            completed_cycles=len(completed_cycles),
            cycle_events=len(cycle_rows),
            phase_integrity=phase_integrity,
            rzs_non_continue=sum(1 for x in decisions if x and x != "continue"),
            last_sigma=last_sigma,
            current_energy=current_energy,
            attention_lock_ratio=dominant_focus_count / max(1, len(focuses)),
            dominant_focus=dominant_focus,
            action_monotony_ratio=dominant_action_count / max(1, len(actions)),
            dominant_action=dominant_action,
            max_working_memory_items=max(wm_per_cycle.values()) if wm_per_cycle else 0,
            replay_events=len(replay_rows),
            cycles_since_replay=max(0, last_cycle - last_replay) if last_cycle else 999,
            consolidation_events=sum(1 for x in actions if x in {"consolidate", "pause_for_stability"}),
            v48_9_integrity=v48_integrity,
        )

    def self_checks(self, summary: TraceSummary) -> list[tuple[str, bool, float, dict[str, Any]]]:
        return [
            ("v49_phase_integrity", summary.phase_integrity, 1.0 if summary.phase_integrity else 0.0, asdict(summary)),
            ("v49_minimum_cycles", summary.completed_cycles >= 12, min(1.0, summary.completed_cycles / 12.0), {"cycles": summary.completed_cycles}),
            ("rzs_regulation_present", summary.rzs_non_continue > 0, min(1.0, summary.rzs_non_continue / 2.0), {"non_continue": summary.rzs_non_continue}),
            (
                "attention_flexibility",
                summary.attention_lock_ratio <= 0.70,
                clamp(1.0 - summary.attention_lock_ratio),
                {"dominant_focus": summary.dominant_focus, "ratio": summary.attention_lock_ratio},
            ),
            (
                "action_diversity",
                summary.action_monotony_ratio <= 0.80,
                clamp(1.0 - summary.action_monotony_ratio),
                {"dominant_action": summary.dominant_action, "ratio": summary.action_monotony_ratio},
            ),
            (
                "working_memory_bound",
                summary.max_working_memory_items <= 7,
                clamp(1.0 - max(0, summary.max_working_memory_items - 7) / 7.0),
                {"max_items": summary.max_working_memory_items},
            ),
            (
                "replay_recency",
                summary.replay_events > 0 and summary.cycles_since_replay <= 5,
                clamp(1.0 - max(0, summary.cycles_since_replay - 3) / 9.0),
                {"replay_events": summary.replay_events, "cycles_since_replay": summary.cycles_since_replay},
            ),
            (
                "consolidation_available",
                summary.consolidation_events > 0,
                min(1.0, summary.consolidation_events / 2.0),
                {"consolidation_events": summary.consolidation_events},
            ),
            ("v48_9_integrity", summary.v48_9_integrity, 1.0 if summary.v48_9_integrity else 0.0, {"source_table": SOURCE_V48_9}),
        ]

    def risk_vector(self, summary: TraceSummary) -> RiskVector:
        return RiskVector(
            integrity=0.0 if summary.phase_integrity and summary.v48_9_integrity else 1.0,
            sigma_low=clamp((1.35 - summary.last_sigma) / 1.35),
            energy_low=clamp((0.70 - summary.current_energy) / 0.70),
            attention_lock=clamp((summary.attention_lock_ratio - 0.55) / 0.45),
            action_monotony=clamp((summary.action_monotony_ratio - 0.65) / 0.35),
            replay_gap=clamp((summary.cycles_since_replay - 5) / 8.0),
            working_memory_pressure=clamp((summary.max_working_memory_items / 7.0 - 0.60) / 0.40),
            rzs_absence=0.0 if summary.rzs_non_continue > 0 else 1.0,
        )

    def decide(self, summary: TraceSummary, risk: RiskVector, meta_cycle_id: int) -> MetaDecision:
        if risk.integrity > 0.0:
            return MetaDecision("halt", "halt_on_integrity_risk", "integridade causal ou v48.9 falhou")
        if risk.sigma_low > 0.45 or risk.energy_low > 0.45:
            return MetaDecision("stabilize", "request_consolidation", "sigma ou energia indicam instabilidade")
        if risk.attention_lock > 0.45:
            return MetaDecision("intervene", "stabilize_attention", "foco dominante repetido acima do limiar")
        if risk.replay_gap > 0.30:
            return MetaDecision("intervene", "schedule_replay", "intervalo desde o ultimo replay ficou alto")
        if risk.action_monotony > 0.55:
            return MetaDecision("intervene", "diversify_cognitive_action", "acao cognitiva dominante demais")
        if meta_cycle_id % 3 == 0:
            return MetaDecision("maintain", "write_self_memory", "registrar continuidade metacognitiva")
        return MetaDecision("observe", "continue_observing", "saude operacional aceitavel")

    def execute_action(self, summary: TraceSummary, risk: RiskVector, decision: MetaDecision, health_before: float) -> tuple[float, dict[str, Any]]:
        if not self.execute:
            return health_before, {"executed": False, "reason": "execution disabled"}

        expected_gain = 0.0
        memory_key = f"brain_v49_1:continuity:{summary.observed_scenario_id}"
        memory_content = (
            f"metacognitive_observation health={health_before:.3f} "
            f"action={decision.meta_action} focus={summary.dominant_focus} "
            f"replay_gap={summary.cycles_since_replay}"
        )

        if decision.meta_action == "stabilize_attention":
            expected_gain = 0.06
            memory_key = f"brain_v49_1:attention:{summary.observed_scenario_id}"
            memory_content = (
                f"attention_lock_detected ratio={summary.attention_lock_ratio:.3f}; "
                "next brain cycle should diversify focus before repeating weak memory."
            )
        elif decision.meta_action == "schedule_replay":
            expected_gain = 0.05
            memory_key = f"brain_v49_1:replay_request:{summary.observed_scenario_id}"
            memory_content = f"replay should be prioritized; cycles_since_replay={summary.cycles_since_replay}"
        elif decision.meta_action == "request_consolidation":
            expected_gain = 0.07
            memory_key = f"brain_v49_1:consolidation_request:{summary.observed_scenario_id}"
            memory_content = f"stability requested from metacognition; sigma={summary.last_sigma:.3f}; energy={summary.current_energy:.3f}"
        elif decision.meta_action == "diversify_cognitive_action":
            expected_gain = 0.04
            memory_key = f"brain_v49_1:action_diversity:{summary.observed_scenario_id}"
            memory_content = f"dominant action {summary.dominant_action} ratio={summary.action_monotony_ratio:.3f}"
        elif decision.meta_action == "halt_on_integrity_risk":
            expected_gain = 0.0
            memory_key = f"brain_v49_1:integrity_alert:{summary.observed_scenario_id}"
            memory_content = "integrity risk detected; do not advance baseline before audit."
        elif decision.meta_action == "write_self_memory":
            expected_gain = 0.02

        confidence = 0.62 + min(0.20, risk.total() * 0.20)
        self.store.upsert_semantic_memory(memory_key, memory_content, confidence)
        health_after = clamp(health_before + expected_gain)
        return health_after, {
            "executed": True,
            "memory_key": memory_key,
            "expected_gain": expected_gain,
            "memory_content": memory_content,
        }

    def run_pass(self, meta_cycle_id: int) -> None:
        summary = self.trace_summary()
        risk = self.risk_vector(summary)
        risk_score = risk.total()
        health_score = clamp(1.0 - risk_score)
        decision = self.decide(summary, risk, meta_cycle_id)
        self.last_summary = summary
        self.last_risk = risk
        self.last_decision = decision

        common = {
            "observed_scenario_id": summary.observed_scenario_id,
            "health_score": health_score,
            "risk_score": risk_score,
            "meta_decision": decision.meta_decision,
            "meta_action": decision.meta_action,
        }
        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "meta_cycle_start",
            observed_scenario_id=summary.observed_scenario_id,
            payload={"phase_order": META_PHASES},
        )
        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "read_brain_trace",
            **common,
            payload={
                "source_tables": [V49_CYCLES, V49_WM, V49_ATT, V49_REPLAY, SOURCE_V48_9, "current_state"],
                "trace_summary": asdict(summary),
            },
        )

        checks = self.self_checks(summary)
        for name, status, score, payload in checks:
            self.store.log_check(self.scenario_id, meta_cycle_id, summary.observed_scenario_id, name, status, score, payload)

        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "self_check",
            **common,
            payload={"checks": [{"name": n, "status": ok, "score": s} for n, ok, s, _ in checks]},
        )
        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "health_assess",
            **common,
            payload={"risk_vector": asdict(risk), "risk_score": risk_score, "health_score": health_score},
        )
        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "meta_decision_select",
            **common,
            payload={"decision": asdict(decision), "summary": asdict(summary)},
        )

        health_after, action_payload = self.execute_action(summary, risk, decision, health_score)
        self.store.log_intervention(
            self.scenario_id,
            meta_cycle_id,
            summary.observed_scenario_id,
            decision,
            health_score,
            health_after,
            {"risk_vector": asdict(risk), "action_payload": action_payload},
        )
        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "meta_action_execute",
            observed_scenario_id=summary.observed_scenario_id,
            health_score=health_after,
            risk_score=risk_score,
            meta_decision=decision.meta_decision,
            meta_action=decision.meta_action,
            payload=action_payload,
        )
        self.store.log_meta(
            self.scenario_id,
            meta_cycle_id,
            "meta_cycle_complete",
            observed_scenario_id=summary.observed_scenario_id,
            health_score=health_after,
            risk_score=risk_score,
            meta_decision=decision.meta_decision,
            meta_action=decision.meta_action,
            payload={"scenario_complete": meta_cycle_id >= self.passes, "passes_completed": meta_cycle_id},
        )

    def run(self) -> None:
        for i in range(1, self.passes + 1):
            self.run_pass(i)


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Brain Metacognition v49.1")
    ap.add_argument("--passes", type=int, default=6, help="Numero de ciclos metacognitivos.")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-execute", action="store_true", help="Calcula e loga, mas nao escreve memoria semantica de intervencao.")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    meta = MetaCognition(passes=args.passes, seed=args.seed, execute=not args.no_execute)
    meta.run()

    print(f"DARWIN v49.1 Metacognition concluido: scenario={meta.scenario_id} passes={args.passes}")
    if args.details and meta.last_summary and meta.last_risk and meta.last_decision:
        print(f"observed_v49_0={meta.last_summary.observed_scenario_id}")
        print(f"health={1.0 - meta.last_risk.total():.4f} risk={meta.last_risk.total():.4f}")
        print(f"decision={meta.last_decision.meta_decision} action={meta.last_decision.meta_action}")
        print(f"dominant_focus={meta.last_summary.dominant_focus} ratio={meta.last_summary.attention_lock_ratio:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
