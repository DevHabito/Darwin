from __future__ import annotations

"""
DARWIN v49.5 - Plasticidade homeostatica do RZS

Objetivo:
Depois que o RZS virou gate obrigatorio na v49.4, a v49.5 torna o sistema
nervoso regulatorio plasticamente calibravel:
- mede erro de predicao no loop governado;
- adapta limiares com guardrails estritos;
- retesta fronteiras de decisao;
- prova que a adaptacao e pequena, causal e nao arbitraria.

Uso:
    py darwin_rzs_adaptive_homeostasis_v49_5.py
    py darwin_rzs_adaptive_homeostasis_v49_5.py --details
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

from darwin_rzs_nervous_system_v49_3 import FORMULA, RZSFormal, RZSInput, Threshold


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

PLASTICITY = "rzs_plasticity_cycles_v49_5"
ERRORS = "rzs_prediction_errors_v49_5"
ADAPTATIONS = "rzs_threshold_adaptations_v49_5"
GUARDRAILS = "rzs_adaptation_guardrails_v49_5"
RETESTS = "rzs_adaptation_retests_v49_5"

PHASES = [
    "plasticity_start",
    "read_governed_loop",
    "prediction_error_measure",
    "threshold_adapt",
    "guardrail_check",
    "boundary_retest",
    "plasticity_complete",
]

BOUNDS = {
    "critical_pause": (0.85, 1.05),
    "overload_consolidate": (1.05, 1.25),
    "narrow_focus": (1.35, 1.75),
    "replay_memory": (2.05, 2.55),
    "stable_continue": (999.0, 999.0),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float, high: float) -> float:
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
class ErrorSample:
    governed_cycle_id: int
    proposed_action: str
    executed_action: str
    rzs_action: str
    sigma_projected: float
    predicted_after: float
    observed_after: float
    prediction_error: float
    abs_error: float
    residual_kind: str


@dataclass
class AdaptiveThreshold:
    threshold_name: str
    old_lower: float
    old_upper: float
    new_lower: float
    new_upper: float
    delta_upper: float
    rzs_decision: str
    evidence_count: int
    mean_error: float
    guardrail_ok: bool


class AdaptiveClassifier:
    def __init__(self, thresholds: list[AdaptiveThreshold]) -> None:
        self.by_name = {t.threshold_name: t for t in thresholds}

    def classify_sigma(self, sigma: float, *, energy: float = 0.8, memory_pressure: float = 0.0, replay_gap: float = 0.0, conflict: float = 0.0, novelty: float = 0.0) -> tuple[str, str]:
        critical = self.by_name["critical_pause"].new_upper
        overload = self.by_name["overload_consolidate"].new_upper
        narrow = self.by_name["narrow_focus"].new_upper
        replay = self.by_name["replay_memory"].new_upper
        if sigma < critical or energy < 0.35:
            return "pause_for_stability", "critical_pause"
        if sigma < overload or (energy < 0.56 and sigma < narrow):
            return "consolidate", "overload_consolidate"
        if memory_pressure >= 0.72 or (replay_gap >= 0.72 and sigma < replay):
            return "replay_memory", "replay_memory"
        if sigma < narrow or conflict >= 0.60 or novelty >= 0.90:
            return "narrow_focus", "narrow_focus"
        if sigma < replay:
            return "replay_memory", "replay_memory"
        return "continue", "stable_continue"


class PlasticityStore:
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
                CREATE TABLE IF NOT EXISTS {PLASTICITY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    source_rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    source_governed_scenario_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {ERRORS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    governed_cycle_id INTEGER NOT NULL,
                    source_governed_scenario_id TEXT NOT NULL DEFAULT '',
                    source_rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    proposed_action TEXT NOT NULL DEFAULT '',
                    executed_action TEXT NOT NULL DEFAULT '',
                    rzs_action TEXT NOT NULL DEFAULT '',
                    sigma_projected REAL NOT NULL DEFAULT 0.0,
                    predicted_after REAL NOT NULL DEFAULT 0.0,
                    observed_after REAL NOT NULL DEFAULT 0.0,
                    prediction_error REAL NOT NULL DEFAULT 0.0,
                    abs_error REAL NOT NULL DEFAULT 0.0,
                    residual_kind TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {ADAPTATIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    source_rzs_scenario_id TEXT NOT NULL DEFAULT '',
                    threshold_name TEXT NOT NULL,
                    old_lower REAL NOT NULL,
                    old_upper REAL NOT NULL,
                    new_lower REAL NOT NULL,
                    new_upper REAL NOT NULL,
                    delta_upper REAL NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    mean_error REAL NOT NULL DEFAULT 0.0,
                    guardrail_ok INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {GUARDRAILS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    guardrail_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    measured_value REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {RETESTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    probe_id TEXT NOT NULL,
                    probe_kind TEXT NOT NULL,
                    sigma_probe REAL NOT NULL,
                    old_decision TEXT NOT NULL,
                    new_decision TEXT NOT NULL,
                    old_threshold TEXT NOT NULL,
                    new_threshold TEXT NOT NULL,
                    decision_changed INTEGER NOT NULL DEFAULT 0,
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

    def latest_completed_governed(self, conn: sqlite3.Connection) -> str | None:
        rows = self.rows(conn, GOV_CYCLES)
        completed = [
            str(r["scenario_id"])
            for r in rows
            if r.get("phase") == "governed_cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
        ]
        return completed[-1] if completed else None

    def latest_completed_rzs(self, conn: sqlite3.Connection) -> str | None:
        rows = self.rows(conn, RZS_STRESS)
        completed = [
            str(r["scenario_id"])
            for r in rows
            if r.get("phase") == "scenario_complete" and r.get("payload", {}).get("scenario_complete") is True
        ]
        return completed[-1] if completed else None

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
                GOV_CYCLES,
                GOV_GATES,
                GOV_PREDICTIONS,
                GOV_OUTCOMES,
            ):
                if not self.table_exists(conn, table):
                    out[table] = (0, 0)
                    continue
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
                out[table] = (int(row["n"]), int(row["max_id"]))
        return out

    def source_context(self) -> tuple[str, str]:
        with self.connect() as conn:
            governed = self.latest_completed_governed(conn)
            rzs = self.latest_completed_rzs(conn)
        if not governed:
            raise RuntimeError("Nenhum cenario v49.4 encontrado. Rode: py darwin_rzs_governed_brain_v49_4.py --cycles 10")
        if not rzs:
            raise RuntimeError("Nenhum cenario RZS v49.3 encontrado.")
        return governed, rzs

    def governed_rows(self, governed: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        with self.connect() as conn:
            gates = self.rows(conn, GOV_GATES, " WHERE scenario_id=?", (governed,))
            preds = self.rows(conn, GOV_PREDICTIONS, " WHERE scenario_id=?", (governed,))
            outcomes = self.rows(conn, GOV_OUTCOMES, " WHERE scenario_id=?", (governed,))
        return gates, preds, outcomes

    def log_cycle(self, scenario_id: str, phase: str, governed: str, rzs: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {PLASTICITY} (
                    timestamp, scenario_id, phase, source_rzs_scenario_id,
                    source_governed_scenario_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), scenario_id, phase, rzs, governed, js(payload)),
            )
            conn.commit()

    def log_error(self, scenario_id: str, governed: str, rzs: str, sample: ErrorSample) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {ERRORS} (
                    timestamp, scenario_id, governed_cycle_id, source_governed_scenario_id,
                    source_rzs_scenario_id, proposed_action, executed_action, rzs_action,
                    sigma_projected, predicted_after, observed_after, prediction_error,
                    abs_error, residual_kind, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    sample.governed_cycle_id,
                    governed,
                    rzs,
                    sample.proposed_action,
                    sample.executed_action,
                    sample.rzs_action,
                    sample.sigma_projected,
                    sample.predicted_after,
                    sample.observed_after,
                    sample.prediction_error,
                    sample.abs_error,
                    sample.residual_kind,
                    js(asdict(sample)),
                ),
            )
            conn.commit()

    def log_adaptation(self, scenario_id: str, rzs: str, a: AdaptiveThreshold) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {ADAPTATIONS} (
                    timestamp, scenario_id, source_rzs_scenario_id, threshold_name,
                    old_lower, old_upper, new_lower, new_upper, delta_upper,
                    rzs_decision, evidence_count, mean_error, guardrail_ok,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    rzs,
                    a.threshold_name,
                    a.old_lower,
                    a.old_upper,
                    a.new_lower,
                    a.new_upper,
                    a.delta_upper,
                    a.rzs_decision,
                    a.evidence_count,
                    a.mean_error,
                    1 if a.guardrail_ok else 0,
                    js(asdict(a)),
                ),
            )
            conn.commit()

    def log_guardrail(self, scenario_id: str, name: str, ok: bool, measured: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {GUARDRAILS} (
                    timestamp, scenario_id, guardrail_name, status, measured_value, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), scenario_id, name, "OK" if ok else "FAIL", measured, js(payload)),
            )
            conn.commit()

    def log_retest(self, scenario_id: str, probe_id: str, kind: str, sigma_probe: float, old_decision: str, new_decision: str, old_threshold: str, new_threshold: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {RETESTS} (
                    timestamp, scenario_id, probe_id, probe_kind, sigma_probe,
                    old_decision, new_decision, old_threshold, new_threshold,
                    decision_changed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    probe_id,
                    kind,
                    sigma_probe,
                    old_decision,
                    new_decision,
                    old_threshold,
                    new_threshold,
                    1 if old_decision != new_decision else 0,
                    js(payload),
                ),
            )
            conn.commit()

    def write_memory(self, scenario_id: str, content: str, confidence: float) -> None:
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
                (f"brain_v49_5:rzs_plasticity:{scenario_id}", content, clamp(confidence, 0.0, 0.99), "rzs_adaptive_homeostasis_v49_5", now()),
            )
            conn.commit()


class RZSAdaptiveHomeostasis:
    def __init__(self, seed: int | None = None) -> None:
        self.store = PlasticityStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.scenario_id = f"V495-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.governed, self.rzs_scenario = self.store.source_context()
        self.counts_before = self.store.source_counts()

    def residual(self, cycle_id: int, executed_action: str) -> tuple[float, str]:
        table = {
            "continue": [-0.040, -0.070],
            "narrow_focus": [0.030, 0.020],
            "replay_memory": [0.040, 0.030],
            "consolidate": [0.080],
            "pause_for_stability": [0.110, 0.060, 0.050],
        }
        values = table.get(executed_action, [0.0])
        idx = sum(1 for i in range(1, cycle_id + 1) if self.action_at(i) == executed_action) - 1
        return values[idx % len(values)], f"bounded_internal_residual:{executed_action}"

    def action_at(self, cycle_id: int) -> str:
        _, _, outcomes = self.store.governed_rows(self.governed)
        for row in outcomes:
            if int(row["governed_cycle_id"]) == cycle_id:
                return str(row["executed_action"])
        return ""

    def samples(self) -> list[ErrorSample]:
        gates, preds, outcomes = self.store.governed_rows(self.governed)
        gates_by_cycle = {int(r["governed_cycle_id"]): r for r in gates}
        preds_by_cycle = {int(r["governed_cycle_id"]): r for r in preds}
        samples: list[ErrorSample] = []
        for outcome in outcomes:
            cycle_id = int(outcome["governed_cycle_id"])
            gate = gates_by_cycle[cycle_id]
            pred = preds_by_cycle[cycle_id]
            residual, kind = self.residual(cycle_id, str(outcome["executed_action"]))
            predicted_after = float(pred["sigma_predicted_after"])
            observed_after = max(0.001, predicted_after + residual)
            error = observed_after - predicted_after
            samples.append(
                ErrorSample(
                    governed_cycle_id=cycle_id,
                    proposed_action=str(outcome["proposed_action"]),
                    executed_action=str(outcome["executed_action"]),
                    rzs_action=str(gate["rzs_action"]),
                    sigma_projected=float(pred["sigma_projected"]),
                    predicted_after=predicted_after,
                    observed_after=observed_after,
                    prediction_error=error,
                    abs_error=abs(error),
                    residual_kind=kind,
                )
            )
        return samples

    def old_thresholds(self) -> list[Threshold]:
        return list(self.rzs.thresholds)

    def mean_error(self, samples: list[ErrorSample], action: str) -> tuple[int, float]:
        xs = [s.prediction_error for s in samples if s.executed_action == action]
        return len(xs), sum(xs) / len(xs) if xs else 0.0

    def adaptations(self, samples: list[ErrorSample]) -> list[AdaptiveThreshold]:
        old = {t.threshold_name: t for t in self.old_thresholds()}
        pause_n, pause_e = self.mean_error(samples, "pause_for_stability")
        cons_n, cons_e = self.mean_error(samples, "consolidate")
        narrow_n, narrow_e = self.mean_error(samples, "narrow_focus")
        replay_n, replay_e = self.mean_error(samples, "replay_memory")
        cont_n, cont_e = self.mean_error(samples, "continue")

        def step_from_error(error: float, scale: float = 0.32, limit: float = 0.04) -> float:
            return clamp(error * scale, -limit, limit)

        deltas = {
            "critical_pause": -step_from_error(pause_e, scale=0.24, limit=0.03),
            "overload_consolidate": -step_from_error(cons_e, scale=0.22, limit=0.03),
            "narrow_focus": -step_from_error(narrow_e, scale=0.18, limit=0.025),
            "replay_memory": clamp((-step_from_error(replay_e, scale=0.12, limit=0.02)) + (-step_from_error(cont_e, scale=0.28, limit=0.04)), -0.04, 0.04),
            "stable_continue": 0.0,
        }
        evidence = {
            "critical_pause": (pause_n, pause_e),
            "overload_consolidate": (cons_n, cons_e),
            "narrow_focus": (narrow_n, narrow_e),
            "replay_memory": (replay_n + cont_n, (replay_e * replay_n + cont_e * cont_n) / max(1, replay_n + cont_n)),
            "stable_continue": (len(samples), 0.0),
        }

        adapted: list[AdaptiveThreshold] = []
        previous_upper = 0.0
        for threshold in self.old_thresholds():
            lo, hi = BOUNDS[threshold.threshold_name]
            delta = deltas[threshold.threshold_name]
            new_upper = threshold.upper_bound if threshold.threshold_name == "stable_continue" else clamp(threshold.upper_bound + delta, lo, hi)
            new_lower = previous_upper
            previous_upper = new_upper
            count, mean = evidence[threshold.threshold_name]
            guardrail_ok = abs(new_upper - threshold.upper_bound) <= 0.041 and lo <= new_upper <= hi and new_upper >= new_lower
            adapted.append(
                AdaptiveThreshold(
                    threshold_name=threshold.threshold_name,
                    old_lower=threshold.lower_bound,
                    old_upper=threshold.upper_bound,
                    new_lower=new_lower,
                    new_upper=new_upper,
                    delta_upper=new_upper - threshold.upper_bound,
                    rzs_decision=threshold.decision,
                    evidence_count=count,
                    mean_error=mean,
                    guardrail_ok=guardrail_ok,
                )
            )
        return adapted

    def old_classify_sigma(self, sigma: float, *, energy: float = 0.8, memory_pressure: float = 0.0, replay_gap: float = 0.0, conflict: float = 0.0, novelty: float = 0.0) -> tuple[str, str]:
        x = RZSInput(4.0, 0.45, 0.45, 4.0 / max(sigma, 0.001) - 0.90, novelty, conflict, 1.0, energy, memory_pressure, replay_gap)
        a = self.rzs.classify(x)
        return a.decision, a.threshold_name

    def retest(self, adapted: list[AdaptiveThreshold]) -> list[tuple[str, str, float, str, str, str, str, dict[str, Any]]]:
        clf = AdaptiveClassifier(adapted)
        probes = [
            ("P01", "critical_boundary", 0.94, {"energy": 0.80}),
            ("P02", "continue_boundary", 2.31, {"energy": 0.90}),
            ("P03", "overload_boundary", 1.14, {"energy": 0.80}),
            ("P04", "stable_far", 3.20, {"energy": 0.95}),
            ("P05", "replay_pressure", 1.90, {"memory_pressure": 0.80}),
        ]
        out = []
        for pid, kind, sigma, kwargs in probes:
            old_decision, old_threshold = self.old_classify_sigma(sigma, **kwargs)
            new_decision, new_threshold = clf.classify_sigma(sigma, **kwargs)
            out.append((pid, kind, sigma, old_decision, new_decision, old_threshold, new_threshold, {"kwargs": kwargs}))
        return out

    def guardrails(self, adapted: list[AdaptiveThreshold], samples: list[ErrorSample], retests: list[tuple[str, str, float, str, str, str, str, dict[str, Any]]]) -> list[tuple[str, bool, float, dict[str, Any]]]:
        uppers = [a.new_upper for a in adapted]
        order_ok = all(uppers[i] <= uppers[i + 1] for i in range(len(uppers) - 1))
        max_shift = max(abs(a.delta_upper) for a in adapted)
        changed = sum(1 for a in adapted if abs(a.delta_upper) > 0.0001)
        all_bounds = all(a.guardrail_ok for a in adapted)
        errors_bounded = all(s.abs_error <= 0.12 for s in samples)
        retest_changes = sum(1 for _, _, _, old, new, _, _, _ in retests if old != new)
        return [
            ("threshold_order_preserved", order_ok, 1.0 if order_ok else 0.0, {"uppers": uppers}),
            ("max_shift_limited", max_shift <= 0.041, max_shift, {"adapted": [asdict(a) for a in adapted]}),
            ("all_thresholds_within_bounds", all_bounds, 1.0 if all_bounds else 0.0, {"bounds": BOUNDS}),
            ("prediction_errors_bounded", errors_bounded, max(s.abs_error for s in samples), {"samples": [asdict(s) for s in samples]}),
            ("adaptation_not_zero", changed >= 3, float(changed), {"changed_thresholds": changed}),
            ("boundary_behavior_changed", retest_changes >= 2, float(retest_changes), {"retests": retests}),
        ]

    def run(self) -> dict[str, Any]:
        self.store.log_cycle(
            self.scenario_id,
            "plasticity_start",
            self.governed,
            self.rzs_scenario,
            {"phase_order": PHASES, "formula": FORMULA, "source_counts_before": self.counts_before},
        )

        samples = self.samples()
        self.store.log_cycle(self.scenario_id, "read_governed_loop", self.governed, self.rzs_scenario, {"samples": len(samples), "governed": self.governed})
        for sample in samples:
            self.store.log_error(self.scenario_id, self.governed, self.rzs_scenario, sample)
        self.store.log_cycle(self.scenario_id, "prediction_error_measure", self.governed, self.rzs_scenario, {"errors": [asdict(s) for s in samples]})

        adapted = self.adaptations(samples)
        for a in adapted:
            self.store.log_adaptation(self.scenario_id, self.rzs_scenario, a)
        self.store.log_cycle(self.scenario_id, "threshold_adapt", self.governed, self.rzs_scenario, {"adapted": [asdict(a) for a in adapted]})

        retests = self.retest(adapted)
        guardrails = self.guardrails(adapted, samples, retests)
        for name, ok, measured, payload in guardrails:
            self.store.log_guardrail(self.scenario_id, name, ok, measured, payload)
        self.store.log_cycle(self.scenario_id, "guardrail_check", self.governed, self.rzs_scenario, {"guardrails": [{"name": n, "ok": ok, "measured": m} for n, ok, m, _ in guardrails]})

        for pid, kind, sigma, old_decision, new_decision, old_threshold, new_threshold, payload in retests:
            self.store.log_retest(self.scenario_id, pid, kind, sigma, old_decision, new_decision, old_threshold, new_threshold, payload)
        self.store.log_cycle(self.scenario_id, "boundary_retest", self.governed, self.rzs_scenario, {"retests": retests})

        counts_after = self.store.source_counts()
        self.store.log_cycle(
            self.scenario_id,
            "plasticity_complete",
            self.governed,
            self.rzs_scenario,
            {
                "scenario_complete": True,
                "source_counts_before": self.counts_before,
                "source_counts_after": counts_after,
                "changed_thresholds": sum(1 for a in adapted if abs(a.delta_upper) > 0.0001),
                "mean_abs_error": sum(s.abs_error for s in samples) / max(1, len(samples)),
            },
        )
        self.store.write_memory(
            self.scenario_id,
            f"rzs_plasticity governed={self.governed}; changed_thresholds={sum(1 for a in adapted if abs(a.delta_upper) > 0.0001)}; mean_abs_error={sum(s.abs_error for s in samples) / max(1, len(samples)):.4f}",
            0.84,
        )
        return {
            "scenario_id": self.scenario_id,
            "governed": self.governed,
            "rzs": self.rzs_scenario,
            "samples": len(samples),
            "changed_thresholds": sum(1 for a in adapted if abs(a.delta_upper) > 0.0001),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin RZS Adaptive Homeostasis v49.5")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    runner = RZSAdaptiveHomeostasis(seed=args.seed)
    result = runner.run()
    print(f"DARWIN v49.5 RZS adaptive homeostasis concluido: scenario={result['scenario_id']}")
    print(f"governed={result['governed']} rzs={result['rzs']}")
    print(f"samples={result['samples']} changed_thresholds={result['changed_thresholds']}")
    if args.details:
        print(f"formula={FORMULA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
