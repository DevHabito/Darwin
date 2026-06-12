from __future__ import annotations

"""
DARWIN v49.4 - Brain Core governado por RZS formal

Objetivo:
Colocar o RZS v49.3 no caminho obrigatorio da acao cognitiva.
Uma acao interna pode ser proposta, mas so executa depois do gate formal:
invariantes -> limiar -> predicao -> contrafactual -> decisao causal.

Uso:
    py darwin_rzs_governed_brain_v49_4.py --cycles 10
    py darwin_rzs_governed_brain_v49_4.py --cycles 10 --details
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

from darwin_rzs_nervous_system_v49_3 import FORMULA, RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

SOURCE_V48_9 = "geometry_multistep_plans_v48_9"
V49_CYCLES = "brain_cycles_v49_0"
V49_META = "brain_meta_cycles_v49_1"
V49_CLOSED = "brain_closed_loop_cycles_v49_2"
RZS_STRESS = "rzs_stress_tests_v49_3"
RZS_THRESHOLDS = "rzs_thresholds_v49_3"
RZS_INVARIANTS = "rzs_invariants_v49_3"
RZS_PREDICTIONS = "rzs_predictions_v49_3"
RZS_CAUSAL = "rzs_causal_decisions_v49_3"

GOV_CYCLES = "brain_rzs_governed_cycles_v49_4"
GOV_GATES = "brain_rzs_governed_gates_v49_4"
GOV_PREDICTIONS = "brain_rzs_governed_predictions_v49_4"
GOV_OUTCOMES = "brain_rzs_governed_outcomes_v49_4"

PHASES = [
    "governed_cycle_start",
    "perceive_internal_events",
    "candidate_action_propose",
    "rzs_formal_gate",
    "causal_override_or_confirm",
    "cognitive_action_execute",
    "outcome_assess",
    "governed_cycle_complete",
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
class FormalRZSContext:
    rzs_scenario_id: str
    threshold_count: int
    invariant_count: int
    prediction_count: int
    causal_count: int


@dataclass
class CandidateProposal:
    cycle_id: int
    focus_key: str
    proposal_kind: str
    proposed_action: str
    source_table: str
    evidence: str
    rzs_input: RZSInput


class GovernedStore:
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
                CREATE TABLE IF NOT EXISTS {GOV_CYCLES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    governed_cycle_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    focus_key TEXT NOT NULL DEFAULT '',
                    proposed_action TEXT NOT NULL DEFAULT '',
                    rzs_action TEXT NOT NULL DEFAULT '',
                    executed_action TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {GOV_GATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    governed_cycle_id INTEGER NOT NULL,
                    rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    focus_key TEXT NOT NULL DEFAULT '',
                    proposal_kind TEXT NOT NULL DEFAULT '',
                    proposed_action TEXT NOT NULL DEFAULT '',
                    rzs_action TEXT NOT NULL DEFAULT '',
                    executed_action TEXT NOT NULL DEFAULT '',
                    threshold_name TEXT NOT NULL DEFAULT '',
                    threshold_crossed INTEGER NOT NULL DEFAULT 0,
                    causal_force REAL NOT NULL DEFAULT 0.0,
                    rzs_changed_decision INTEGER NOT NULL DEFAULT 0,
                    sigma_projected REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {GOV_PREDICTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    governed_cycle_id INTEGER NOT NULL,
                    rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    proposed_action TEXT NOT NULL DEFAULT '',
                    rzs_action TEXT NOT NULL DEFAULT '',
                    sigma_projected REAL NOT NULL DEFAULT 0.0,
                    sigma_predicted_after REAL NOT NULL DEFAULT 0.0,
                    predicted_delta REAL NOT NULL DEFAULT 0.0,
                    unregulated_sigma_after REAL NOT NULL DEFAULT 0.0,
                    predicted_regret REAL NOT NULL DEFAULT 0.0,
                    prediction_valid INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {GOV_OUTCOMES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    governed_cycle_id INTEGER NOT NULL,
                    rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    proposed_action TEXT NOT NULL DEFAULT '',
                    executed_action TEXT NOT NULL DEFAULT '',
                    outcome_status TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    causal_override INTEGER NOT NULL DEFAULT 0,
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

    def latest_completed_rzs_scenario(self, conn: sqlite3.Connection) -> str | None:
        rows = self.rows(conn, RZS_STRESS)
        completed = [
            str(r["scenario_id"])
            for r in rows
            if r.get("phase") == "scenario_complete" and r.get("payload", {}).get("scenario_complete") is True
        ]
        if completed:
            return completed[-1]
        ids = [str(r["scenario_id"]) for r in rows if r.get("scenario_id")]
        return ids[-1] if ids else None

    def formal_context(self) -> FormalRZSContext:
        with self.connect() as conn:
            sid = self.latest_completed_rzs_scenario(conn)
            if not sid:
                raise RuntimeError("Nenhum RZS v49.3 formal encontrado. Rode: py darwin_rzs_nervous_system_v49_3.py")
            return FormalRZSContext(
                rzs_scenario_id=sid,
                threshold_count=len(self.rows(conn, RZS_THRESHOLDS, " WHERE scenario_id=?", (sid,))),
                invariant_count=len(self.rows(conn, RZS_INVARIANTS, " WHERE scenario_id=?", (sid,))),
                prediction_count=len(self.rows(conn, RZS_PREDICTIONS, " WHERE scenario_id=?", (sid,))),
                causal_count=len(self.rows(conn, RZS_CAUSAL, " WHERE scenario_id=?", (sid,))),
            )

    def current_base(self) -> RZSInput:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
        if row is None:
            return RZSInput(4.0, 0.35, 0.35, 0.25, 0.08, 0.05, 1.0, 1.0, 0.1, 0.1)
        return RZSInput(
            bandwidth=4.0,
            info_self=float(row["info_self"]),
            info_external=float(row["info_external"]),
            task_info=0.25,
            novelty=0.08,
            conflict=0.05,
            latency=max(0.50, float(row["latency"])),
            energy=float(row["energy"]),
            memory_pressure=0.10,
            replay_gap=0.10,
        )

    def source_counts(self) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        with self.connect() as conn:
            for table in (
                SOURCE_V48_9,
                V49_CYCLES,
                V49_META,
                V49_CLOSED,
                RZS_STRESS,
                RZS_THRESHOLDS,
                RZS_INVARIANTS,
                RZS_PREDICTIONS,
                RZS_CAUSAL,
            ):
                if not self.table_exists(conn, table):
                    out[table] = (0, 0)
                    continue
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
                out[table] = (int(row["n"]), int(row["max_id"]))
        return out

    def log_cycle(
        self,
        scenario_id: str,
        cycle_id: int,
        phase: str,
        ctx: FormalRZSContext,
        proposal: CandidateProposal | None = None,
        *,
        proposed_action: str = "",
        rzs_action: str = "",
        executed_action: str = "",
        sigma_before: float = 0.0,
        sigma_after: float = 0.0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {GOV_CYCLES} (
                    timestamp, scenario_id, governed_cycle_id, phase, rzs_scenario_id,
                    focus_key, proposed_action, rzs_action, executed_action,
                    sigma_before, sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    phase,
                    ctx.rzs_scenario_id,
                    proposal.focus_key if proposal else "",
                    proposed_action,
                    rzs_action,
                    executed_action,
                    sigma_before,
                    sigma_after,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_gate(
        self,
        scenario_id: str,
        cycle_id: int,
        ctx: FormalRZSContext,
        proposal: CandidateProposal,
        *,
        rzs_action: str,
        executed_action: str,
        assessment: Any,
        changed: bool,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {GOV_GATES} (
                    timestamp, scenario_id, governed_cycle_id, rzs_scenario_id,
                    focus_key, proposal_kind, proposed_action, rzs_action,
                    executed_action, threshold_name, threshold_crossed, causal_force,
                    rzs_changed_decision, sigma_projected, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    ctx.rzs_scenario_id,
                    proposal.focus_key,
                    proposal.proposal_kind,
                    proposal.proposed_action,
                    rzs_action,
                    executed_action,
                    assessment.threshold_name,
                    1 if assessment.threshold_crossed else 0,
                    assessment.causal_force,
                    1 if changed else 0,
                    assessment.sigma,
                    js(payload),
                ),
            )
            conn.commit()

    def log_prediction(
        self,
        scenario_id: str,
        cycle_id: int,
        ctx: FormalRZSContext,
        proposal: CandidateProposal,
        *,
        rzs_action: str,
        pred: Any,
        unregulated_sigma: float,
        regret: float,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {GOV_PREDICTIONS} (
                    timestamp, scenario_id, governed_cycle_id, rzs_scenario_id,
                    proposed_action, rzs_action, sigma_projected,
                    sigma_predicted_after, predicted_delta, unregulated_sigma_after,
                    predicted_regret, prediction_valid, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    ctx.rzs_scenario_id,
                    proposal.proposed_action,
                    rzs_action,
                    pred.sigma_projected,
                    pred.sigma_after,
                    pred.predicted_delta,
                    unregulated_sigma,
                    regret,
                    1 if pred.prediction_valid else 0,
                    js(pred.action_model),
                ),
            )
            conn.commit()

    def log_outcome(
        self,
        scenario_id: str,
        cycle_id: int,
        ctx: FormalRZSContext,
        proposal: CandidateProposal,
        *,
        executed_action: str,
        status: str,
        sigma_before: float,
        sigma_after: float,
        changed: bool,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {GOV_OUTCOMES} (
                    timestamp, scenario_id, governed_cycle_id, rzs_scenario_id,
                    proposed_action, executed_action, outcome_status,
                    sigma_before, sigma_after, causal_override, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    ctx.rzs_scenario_id,
                    proposal.proposed_action,
                    executed_action,
                    status,
                    sigma_before,
                    sigma_after,
                    1 if changed else 0,
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
                (f"brain_v49_4:rzs_governed:{scenario_id}", content, clamp(confidence, 0.0, 0.99), "brain_rzs_governed_v49_4", now()),
            )
            conn.commit()


class RZSGovernedBrain:
    def __init__(self, cycles: int = 10, seed: int | None = None) -> None:
        self.store = GovernedStore()
        self.rzs = RZSFormal()
        self.cycles = max(10, cycles)
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.scenario_id = f"V494-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.ctx = self.store.formal_context()
        self.base = self.store.current_base()
        self.counts_before = self.store.source_counts()
        self.executed_actions: list[str] = []
        self.override_count = 0

    def proposal(self, cycle_id: int) -> CandidateProposal:
        b = asdict(self.base)

        def x(**kw: float) -> RZSInput:
            d = dict(b)
            d.update(kw)
            return RZSInput(**d)

        schedule = [
            CandidateProposal(1, "stable:continue_small_task", "stable_current", "continue", "current_state", "small stable cognitive step", x(task_info=0.22, novelty=0.08, conflict=0.05, memory_pressure=0.08, replay_gap=0.08)),
            CandidateProposal(2, "novelty:salient_new_focus", "novelty_spike", "pursue_salient_focus", "semantic_memory", "high novelty wants expansion", x(task_info=0.42, novelty=1.20, conflict=0.20, memory_pressure=0.18, replay_gap=0.20)),
            CandidateProposal(3, "memory:pressure_without_replay", "memory_pressure", "continue_without_replay", "brain_working_memory_v49_0", "working memory pressure wants continuation", x(task_info=0.34, novelty=0.20, conflict=0.16, memory_pressure=0.94, replay_gap=0.86)),
            CandidateProposal(4, "load:consolidation_needed", "consolidation_need", "push_task_despite_load", "state_history", "load is recoverable but unsafe to push", x(info_external=0.90, task_info=0.45, novelty=0.25, conflict=0.25, latency=1.50, bandwidth=3.50, energy=0.50, memory_pressure=0.30, replay_gap=0.35)),
            CandidateProposal(5, "latency:stall_detected", "latency_stall", "push_task_despite_load", "state_history", "latency stall would make task brittle", x(task_info=0.50, novelty=0.30, conflict=0.30, latency=3.10, energy=0.64, memory_pressure=0.25, replay_gap=0.30)),
            CandidateProposal(6, "stable:review_v48_9_plan", "recovery_check", "continue", SOURCE_V48_9, "stable plan review can proceed", x(bandwidth=4.40, info_external=0.28, task_info=0.20, novelty=0.05, conflict=0.03, latency=1.00, energy=0.95, memory_pressure=0.08, replay_gap=0.08)),
            CandidateProposal(7, "conflict:competing_focus", "conflict_spike", "pursue_salient_focus", "episodes", "conflicting evidence wants impulsive selection", x(task_info=0.42, novelty=0.24, conflict=0.92, memory_pressure=0.22, replay_gap=0.22)),
            CandidateProposal(8, "replay:gap_detected", "replay_gap", "continue_without_replay", "brain_replay_v49_0", "recent replay gap should call memory", x(task_info=0.40, novelty=0.26, conflict=0.22, memory_pressure=0.54, replay_gap=0.93)),
            CandidateProposal(9, "bandwidth:drop_under_task", "bandwidth_drop", "push_task_despite_load", "current_state", "bandwidth drop under task pressure", x(bandwidth=1.40, task_info=0.50, novelty=0.40, conflict=0.40, energy=0.46, memory_pressure=0.30, replay_gap=0.40)),
            CandidateProposal(10, "overload:combined", "combined_overload", "push_task_despite_load", "state_history", "combined overload should stop progression", x(bandwidth=3.00, info_external=1.45, task_info=0.90, novelty=0.90, conflict=0.95, latency=2.70, energy=0.32, memory_pressure=0.80, replay_gap=0.80)),
        ]
        return schedule[(cycle_id - 1) % len(schedule)]

    def executed_action(self, proposed_action: str, rzs_decision: str) -> str:
        if rzs_decision == "continue":
            return proposed_action
        return rzs_decision

    def run_cycle(self, cycle_id: int) -> None:
        proposal = self.proposal(cycle_id)
        assessment = self.rzs.classify(proposal.rzs_input)
        assessment.stress_id = f"G{cycle_id:02d}"
        executed = self.executed_action(proposal.proposed_action, assessment.decision)
        changed = executed != proposal.proposed_action
        if changed:
            self.override_count += 1
        pred = self.rzs.predict(proposal.rzs_input, assessment.decision)
        unregulated = self.rzs.unregulated_prediction(proposal.rzs_input)
        regret = max(0.0, pred.sigma_after - unregulated)
        self.executed_actions.append(executed)

        common = {
            "proposal": asdict(proposal),
            "assessment": asdict(assessment),
            "formal_context": asdict(self.ctx),
            "formula": FORMULA,
        }

        self.store.log_cycle(self.scenario_id, cycle_id, "governed_cycle_start", self.ctx, proposal, sigma_before=assessment.sigma, sigma_after=assessment.sigma, payload={"phase_order": PHASES, "source_counts_before": self.counts_before})
        self.store.log_cycle(self.scenario_id, cycle_id, "perceive_internal_events", self.ctx, proposal, sigma_before=assessment.sigma, sigma_after=assessment.sigma, payload={"source_table": proposal.source_table, "focus_key": proposal.focus_key, "evidence": proposal.evidence})
        self.store.log_cycle(self.scenario_id, cycle_id, "candidate_action_propose", self.ctx, proposal, proposed_action=proposal.proposed_action, sigma_before=assessment.sigma, sigma_after=assessment.sigma, payload=common)
        self.store.log_gate(self.scenario_id, cycle_id, self.ctx, proposal, rzs_action=assessment.decision, executed_action=executed, assessment=assessment, changed=changed, payload=common)
        self.store.log_cycle(self.scenario_id, cycle_id, "rzs_formal_gate", self.ctx, proposal, proposed_action=proposal.proposed_action, rzs_action=assessment.decision, executed_action=executed, sigma_before=assessment.sigma, sigma_after=pred.sigma_after, payload={"gate": common, "prediction_valid": pred.prediction_valid})
        self.store.log_prediction(self.scenario_id, cycle_id, self.ctx, proposal, rzs_action=assessment.decision, pred=pred, unregulated_sigma=unregulated, regret=regret)
        self.store.log_cycle(self.scenario_id, cycle_id, "causal_override_or_confirm", self.ctx, proposal, proposed_action=proposal.proposed_action, rzs_action=assessment.decision, executed_action=executed, sigma_before=assessment.sigma, sigma_after=pred.sigma_after, payload={"changed": changed, "predicted_regret": regret, "counterfactual_action": proposal.proposed_action})
        self.store.log_cycle(self.scenario_id, cycle_id, "cognitive_action_execute", self.ctx, proposal, proposed_action=proposal.proposed_action, rzs_action=assessment.decision, executed_action=executed, sigma_before=assessment.sigma, sigma_after=pred.sigma_after, payload={"executed_after_rzs_gate": True, "action_model": pred.action_model})

        status = "override_regulated" if changed else "confirmed_by_rzs"
        self.store.log_outcome(self.scenario_id, cycle_id, self.ctx, proposal, executed_action=executed, status=status, sigma_before=assessment.sigma, sigma_after=pred.sigma_after, changed=changed, payload={"threshold": assessment.threshold_name, "prediction_valid": pred.prediction_valid})
        self.store.log_cycle(self.scenario_id, cycle_id, "outcome_assess", self.ctx, proposal, proposed_action=proposal.proposed_action, rzs_action=assessment.decision, executed_action=executed, sigma_before=assessment.sigma, sigma_after=pred.sigma_after, payload={"outcome_status": status, "prediction_valid": pred.prediction_valid})

        final = cycle_id >= self.cycles
        payload = {
            "scenario_complete": final,
            "cycles_completed": cycle_id,
            "override_count": self.override_count,
            "executed_actions": list(self.executed_actions),
            "source_counts_before": self.counts_before,
            "source_counts_after": self.store.source_counts(),
        }
        self.store.log_cycle(self.scenario_id, cycle_id, "governed_cycle_complete", self.ctx, proposal, proposed_action=proposal.proposed_action, rzs_action=assessment.decision, executed_action=executed, sigma_before=assessment.sigma, sigma_after=pred.sigma_after, payload=payload)
        if final:
            self.store.write_semantic_memory(
                self.scenario_id,
                f"rzs_governed_loop cycles={cycle_id}; overrides={self.override_count}; actions={','.join(self.executed_actions)}",
                0.82,
            )

    def run(self) -> None:
        for cycle_id in range(1, self.cycles + 1):
            self.run_cycle(cycle_id)


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Brain Core Governed by Formal RZS v49.4")
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    brain = RZSGovernedBrain(cycles=args.cycles, seed=args.seed)
    brain.run()
    print(f"DARWIN v49.4 RZS-governed Brain concluido: scenario={brain.scenario_id} cycles={brain.cycles}")
    if args.details:
        print(f"rzs_scenario={brain.ctx.rzs_scenario_id}")
        print(f"overrides={brain.override_count}")
        print(f"executed_actions={brain.executed_actions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
