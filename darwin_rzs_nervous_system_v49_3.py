from __future__ import annotations

"""
DARWIN v49.3 - RZS formal como sistema nervoso regulatorio

Objetivo:
Transformar a Lei de Romero / Relational Zero State em modulo formal:
- invariantes matematicas;
- limiares normativos;
- predicoes antes da acao;
- testes de estresse;
- efeito causal obrigatorio sobre decisoes.

Uso:
    py darwin_rzs_nervous_system_v49_3.py
    py darwin_rzs_nervous_system_v49_3.py --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"

EXPECTED_INVARIANTS = [
    "input_finite_nonnegative",
    "denominator_positive",
    "sigma_positive_finite",
    "formula_reproducible",
    "monotonic_conflict",
    "monotonic_latency",
    "monotonic_bandwidth",
    "threshold_decision_deterministic",
    "prediction_effect_valid",
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
class RZSInput:
    bandwidth: float
    info_self: float
    info_external: float
    task_info: float
    novelty: float
    conflict: float
    latency: float
    energy: float
    memory_pressure: float
    replay_gap: float


@dataclass
class StressCase:
    stress_id: str
    stress_kind: str
    input: RZSInput
    expected_family: str
    description: str


@dataclass
class RZSAssessment:
    stress_id: str
    sigma: float
    decision: str
    threshold_name: str
    threshold_crossed: bool
    causal_force: float
    reason: str


@dataclass
class RZSPrediction:
    sigma_projected: float
    sigma_after: float
    predicted_delta: float
    prediction_valid: bool
    action_model: dict[str, Any]


@dataclass
class Threshold:
    threshold_name: str
    lower_bound: float
    upper_bound: float
    decision: str
    priority: int
    rationale: str


class RZSFormal:
    thresholds = [
        Threshold("critical_pause", 0.0, 0.95, "pause_for_stability", 1, "risco de instabilidade relacional imediata"),
        Threshold("overload_consolidate", 0.95, 1.15, "consolidate", 2, "carga relacional exige reduzir informacao efetiva"),
        Threshold("narrow_focus", 1.15, 1.55, "narrow_focus", 3, "sigma baixo ou conflito/novidade altos exigem foco estreito"),
        Threshold("replay_memory", 1.55, 2.30, "replay_memory", 4, "pressao de memoria ou lacuna de replay exige consulta estabilizadora"),
        Threshold("stable_continue", 2.30, 999.0, "continue", 5, "estado suficientemente estavel para prosseguir"),
    ]

    def denominator(self, x: RZSInput) -> float:
        return (x.info_self + x.info_external + x.task_info + x.novelty + x.conflict) * x.latency

    def sigma(self, x: RZSInput) -> float:
        return x.bandwidth / max(self.denominator(x), 1e-12)

    def finite_nonnegative(self, x: RZSInput) -> bool:
        values = asdict(x).values()
        return all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0.0 for v in values) and x.latency > 0.0 and x.bandwidth > 0.0

    def classify(self, x: RZSInput) -> RZSAssessment:
        sigma = self.sigma(x)
        if sigma < 0.95 or x.energy < 0.35 or x.latency > 2.60:
            return RZSAssessment("", sigma, "pause_for_stability", "critical_pause", True, 1.0, "sigma/energia/latencia cruzaram limiar critico")
        if sigma < 1.15 or (x.energy < 0.56 and sigma < 1.55):
            return RZSAssessment("", sigma, "consolidate", "overload_consolidate", True, 0.86, "sobrecarga exige consolidacao antes de prosseguir")
        if x.memory_pressure >= 0.72 or (x.replay_gap >= 0.72 and sigma < 2.30):
            return RZSAssessment("", sigma, "replay_memory", "replay_memory", True, 0.74, "memoria/replay exigem retorno estabilizador")
        if sigma < 1.55 or x.conflict >= 0.60 or x.novelty >= 0.90:
            return RZSAssessment("", sigma, "narrow_focus", "narrow_focus", True, 0.68, "conflito/novidade/sigma exigem foco estreito")
        return RZSAssessment("", sigma, "continue", "stable_continue", False, 0.12, "nenhum limiar regulatorio forte foi cruzado")

    def counterfactual_action(self, case: StressCase) -> str:
        if case.stress_kind in {"baseline_current", "recovery_check"}:
            return "continue"
        if case.stress_kind in {"memory_pressure", "replay_gap"}:
            return "continue_without_replay"
        if case.stress_kind in {"conflict_spike", "novelty_spike"}:
            return "pursue_salient_focus"
        if case.stress_kind in {"latency_stall", "combined_overload", "bandwidth_drop", "consolidation_need"}:
            return "push_task_despite_load"
        return "continue_task"

    def apply_action_model(self, x: RZSInput, decision: str) -> RZSInput:
        y = RZSInput(**asdict(x))
        if decision == "continue":
            y.bandwidth = max(0.10, y.bandwidth - 0.015)
            y.energy = clamp(y.energy - 0.01)
            y.latency = max(0.25, y.latency * 1.006)
        elif decision == "narrow_focus":
            y.info_external *= 0.74
            y.novelty *= 0.72
            y.conflict *= 0.62
            y.latency = max(0.25, y.latency * 0.94)
            y.energy = clamp(y.energy - 0.04)
        elif decision == "replay_memory":
            y.task_info *= 0.76
            y.novelty *= 0.50
            y.memory_pressure *= 0.45
            y.replay_gap *= 0.25
            y.info_self *= 1.04
            y.bandwidth = max(0.10, y.bandwidth - 0.03)
        elif decision == "consolidate":
            y.bandwidth = min(5.0, y.bandwidth + 0.25)
            y.energy = clamp(y.energy + 0.18)
            y.info_external *= 0.56
            y.info_self *= 0.84
            y.novelty *= 0.62
            y.conflict *= 0.60
            y.latency = 1.0 + (y.latency - 1.0) * 0.52
        elif decision == "pause_for_stability":
            y.bandwidth = min(5.0, y.bandwidth + 0.15)
            y.energy = clamp(y.energy + 0.14)
            y.info_external *= 0.68
            y.task_info *= 0.45
            y.novelty *= 0.42
            y.conflict *= 0.50
            y.latency = 1.0 + (y.latency - 1.0) * 0.42
        return y

    def predict(self, x: RZSInput, decision: str) -> RZSPrediction:
        sigma_before = self.sigma(x)
        y = self.apply_action_model(x, decision)
        sigma_after = self.sigma(y)
        delta = sigma_after - sigma_before
        valid = delta >= -0.10 if decision == "continue" else delta > 0.0
        return RZSPrediction(sigma_before, sigma_after, delta, valid, {"before": asdict(x), "after": asdict(y), "decision": decision})

    def unregulated_prediction(self, x: RZSInput) -> float:
        y = RZSInput(**asdict(x))
        y.bandwidth = max(0.10, y.bandwidth - 0.12)
        y.info_external *= 1.10
        y.task_info *= 1.08
        y.novelty *= 1.08
        y.conflict *= 1.10
        y.latency *= 1.12
        y.energy = clamp(y.energy - 0.08)
        return self.sigma(y)


class RZSStore:
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
                CREATE TABLE IF NOT EXISTS {RZS_STRESS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    stress_id TEXT NOT NULL DEFAULT '',
                    stress_kind TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL,
                    bandwidth REAL NOT NULL DEFAULT 0.0,
                    info_self REAL NOT NULL DEFAULT 0.0,
                    info_external REAL NOT NULL DEFAULT 0.0,
                    task_info REAL NOT NULL DEFAULT 0.0,
                    novelty REAL NOT NULL DEFAULT 0.0,
                    conflict REAL NOT NULL DEFAULT 0.0,
                    latency REAL NOT NULL DEFAULT 0.0,
                    energy REAL NOT NULL DEFAULT 0.0,
                    memory_pressure REAL NOT NULL DEFAULT 0.0,
                    replay_gap REAL NOT NULL DEFAULT 0.0,
                    sigma REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    threshold_name TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {RZS_THRESHOLDS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    threshold_name TEXT NOT NULL,
                    lower_bound REAL NOT NULL,
                    upper_bound REAL NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {RZS_INVARIANTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    stress_id TEXT NOT NULL,
                    invariant_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    measured_value REAL NOT NULL DEFAULT 0.0,
                    expected_relation TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {RZS_PREDICTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    stress_id TEXT NOT NULL,
                    stress_kind TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_projected REAL NOT NULL,
                    sigma_predicted_after REAL NOT NULL,
                    predicted_delta REAL NOT NULL,
                    prediction_valid INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {RZS_CAUSAL} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    stress_id TEXT NOT NULL,
                    stress_kind TEXT NOT NULL,
                    counterfactual_action TEXT NOT NULL,
                    rzs_action TEXT NOT NULL,
                    rzs_changed_decision INTEGER NOT NULL,
                    threshold_crossed INTEGER NOT NULL,
                    causal_force REAL NOT NULL,
                    predicted_regret REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )
            conn.commit()

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def source_counts(self) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        with self.connect() as conn:
            for table in (SOURCE_V48_9, V49_CYCLES, V49_META, V49_CLOSED):
                if not self.table_exists(conn, table):
                    out[table] = (0, 0)
                    continue
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
                out[table] = (int(row["n"]), int(row["max_id"]))
        return out

    def current_base(self) -> RZSInput:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
        if row is None:
            return RZSInput(4.0, 0.35, 0.35, 0.25, 0.08, 0.05, 1.0, 1.0, 0.0, 0.0)
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

    def log_stress(self, scenario_id: str, phase: str, case: StressCase | None, assessment: RZSAssessment | None, payload: dict[str, Any]) -> None:
        x = case.input if case else RZSInput(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {RZS_STRESS} (
                    timestamp, scenario_id, stress_id, stress_kind, phase, bandwidth,
                    info_self, info_external, task_info, novelty, conflict, latency,
                    energy, memory_pressure, replay_gap, sigma, rzs_decision,
                    threshold_name, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    case.stress_id if case else "",
                    case.stress_kind if case else "",
                    phase,
                    x.bandwidth,
                    x.info_self,
                    x.info_external,
                    x.task_info,
                    x.novelty,
                    x.conflict,
                    x.latency,
                    x.energy,
                    x.memory_pressure,
                    x.replay_gap,
                    assessment.sigma if assessment else 0.0,
                    assessment.decision if assessment else "",
                    assessment.threshold_name if assessment else "",
                    js(payload),
                ),
            )
            conn.commit()

    def log_threshold(self, scenario_id: str, threshold: Threshold) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {RZS_THRESHOLDS} (
                    timestamp, scenario_id, threshold_name, lower_bound,
                    upper_bound, rzs_decision, priority, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    threshold.threshold_name,
                    threshold.lower_bound,
                    threshold.upper_bound,
                    threshold.decision,
                    threshold.priority,
                    js({"rationale": threshold.rationale, "formula": FORMULA}),
                ),
            )
            conn.commit()

    def log_invariant(self, scenario_id: str, stress_id: str, name: str, ok: bool, measured: float, relation: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {RZS_INVARIANTS} (
                    timestamp, scenario_id, stress_id, invariant_name, status,
                    measured_value, expected_relation, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), scenario_id, stress_id, name, "OK" if ok else "FAIL", measured, relation, js(payload)),
            )
            conn.commit()

    def log_prediction(self, scenario_id: str, case: StressCase, assessment: RZSAssessment, pred: RZSPrediction) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {RZS_PREDICTIONS} (
                    timestamp, scenario_id, stress_id, stress_kind, rzs_decision,
                    sigma_projected, sigma_predicted_after, predicted_delta,
                    prediction_valid, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    case.stress_id,
                    case.stress_kind,
                    assessment.decision,
                    pred.sigma_projected,
                    pred.sigma_after,
                    pred.predicted_delta,
                    1 if pred.prediction_valid else 0,
                    js(pred.action_model),
                ),
            )
            conn.commit()

    def log_causal(self, scenario_id: str, case: StressCase, assessment: RZSAssessment, counterfactual: str, changed: bool, regret: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {RZS_CAUSAL} (
                    timestamp, scenario_id, stress_id, stress_kind, counterfactual_action,
                    rzs_action, rzs_changed_decision, threshold_crossed, causal_force,
                    predicted_regret, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    case.stress_id,
                    case.stress_kind,
                    counterfactual,
                    assessment.decision,
                    1 if changed else 0,
                    1 if assessment.threshold_crossed else 0,
                    assessment.causal_force,
                    regret,
                    js(payload),
                ),
            )
            conn.commit()


class RZSNervousSystem:
    def __init__(self, seed: int | None = None) -> None:
        self.store = RZSStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time()) % 10_000_000)
        self.scenario_id = f"V493-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.counts_before = self.store.source_counts()

    def stress_cases(self) -> list[StressCase]:
        b = self.store.current_base()

        def x(**kw: float) -> RZSInput:
            d = asdict(b)
            d.update(kw)
            return RZSInput(**d)

        return [
            StressCase("S01", "baseline_current", x(task_info=0.25, novelty=0.08, conflict=0.05, memory_pressure=0.10, replay_gap=0.10), "continue", "estado atual com pequena tarefa cognitiva"),
            StressCase("S02", "novelty_spike", x(task_info=0.42, novelty=1.20, conflict=0.20, memory_pressure=0.18, replay_gap=0.20), "narrow_focus", "novidade alta deve estreitar foco"),
            StressCase("S03", "conflict_spike", x(task_info=0.48, novelty=0.32, conflict=1.12, memory_pressure=0.20, replay_gap=0.20), "narrow_focus", "conflito alto deve inibir expansao"),
            StressCase("S04", "memory_pressure", x(task_info=0.34, novelty=0.20, conflict=0.16, memory_pressure=0.94, replay_gap=0.86), "replay_memory", "pressao de memoria pede replay"),
            StressCase("S05", "replay_gap", x(task_info=0.40, novelty=0.26, conflict=0.22, memory_pressure=0.54, replay_gap=0.93), "replay_memory", "lacuna de replay pede retorno estabilizador"),
            StressCase("S06", "consolidation_need", x(info_external=0.90, task_info=0.45, novelty=0.25, conflict=0.25, latency=1.50, bandwidth=3.50, energy=0.50, memory_pressure=0.30, replay_gap=0.35), "consolidate", "sobrecarga recuperavel pede consolidacao"),
            StressCase("S07", "latency_stall", x(task_info=0.50, novelty=0.30, conflict=0.30, latency=3.10, energy=0.64, memory_pressure=0.25, replay_gap=0.30), "pause_for_stability", "latencia extrema pede pausa"),
            StressCase("S08", "bandwidth_drop", x(bandwidth=1.40, task_info=0.50, novelty=0.40, conflict=0.40, energy=0.46, memory_pressure=0.30, replay_gap=0.40), "pause_for_stability", "queda de bandwidth reduz sigma abaixo do limiar critico"),
            StressCase("S09", "combined_overload", x(bandwidth=3.00, info_external=1.45, task_info=0.90, novelty=0.90, conflict=0.95, latency=2.70, energy=0.32, memory_pressure=0.80, replay_gap=0.80), "pause_for_stability", "sobrecarga combinada deve interromper progressao"),
            StressCase("S10", "recovery_check", x(bandwidth=4.40, info_external=0.28, task_info=0.20, novelty=0.05, conflict=0.03, latency=1.00, energy=0.95, memory_pressure=0.08, replay_gap=0.08), "continue", "estado recuperado deve permitir continuidade"),
        ]

    def invariant_results(self, case: StressCase, assessment: RZSAssessment, prediction: RZSPrediction) -> list[tuple[str, bool, float, str, dict[str, Any]]]:
        x = case.input
        sigma = assessment.sigma
        conflict_up = RZSInput(**{**asdict(x), "conflict": x.conflict + 0.25})
        latency_up = RZSInput(**{**asdict(x), "latency": x.latency + 0.25})
        bandwidth_up = RZSInput(**{**asdict(x), "bandwidth": x.bandwidth + 0.25})
        again = self.rzs.classify(x)
        return [
            ("input_finite_nonnegative", self.rzs.finite_nonnegative(x), 1.0, "all inputs finite, nonnegative, bandwidth>0, latency>0", asdict(x)),
            ("denominator_positive", self.rzs.denominator(x) > 0.0, self.rzs.denominator(x), "denominator > 0", {"denominator": self.rzs.denominator(x)}),
            ("sigma_positive_finite", math.isfinite(sigma) and sigma > 0.0, sigma, "sigma finite and positive", {"sigma": sigma}),
            ("formula_reproducible", abs(sigma - self.rzs.sigma(x)) < 1e-9, abs(sigma - self.rzs.sigma(x)), "logged sigma equals recomputed sigma", {"formula": FORMULA}),
            ("monotonic_conflict", self.rzs.sigma(conflict_up) < sigma, self.rzs.sigma(conflict_up) - sigma, "increasing conflict must lower sigma", {"sigma_conflict_up": self.rzs.sigma(conflict_up)}),
            ("monotonic_latency", self.rzs.sigma(latency_up) < sigma, self.rzs.sigma(latency_up) - sigma, "increasing latency must lower sigma", {"sigma_latency_up": self.rzs.sigma(latency_up)}),
            ("monotonic_bandwidth", self.rzs.sigma(bandwidth_up) > sigma, self.rzs.sigma(bandwidth_up) - sigma, "increasing bandwidth must raise sigma", {"sigma_bandwidth_up": self.rzs.sigma(bandwidth_up)}),
            ("threshold_decision_deterministic", again.decision == assessment.decision and again.threshold_name == assessment.threshold_name, 1.0 if again.decision == assessment.decision else 0.0, "same input produces same threshold decision", {"first": asdict(assessment), "again": asdict(again)}),
            ("prediction_effect_valid", prediction.prediction_valid, prediction.predicted_delta, "regulated action must improve sigma, or preserve it under continue", asdict(prediction)),
        ]

    def run(self) -> dict[str, Any]:
        decisions = Counter()
        changed_count = 0

        for threshold in self.rzs.thresholds:
            self.store.log_threshold(self.scenario_id, threshold)

        self.store.log_stress(
            self.scenario_id,
            "scenario_start",
            None,
            None,
            {"formula": FORMULA, "source_counts_before": self.counts_before},
        )

        for case in self.stress_cases():
            assessment = self.rzs.classify(case.input)
            assessment.stress_id = case.stress_id
            prediction = self.rzs.predict(case.input, assessment.decision)
            counterfactual = self.rzs.counterfactual_action(case)
            changed = counterfactual != assessment.decision
            changed_count += 1 if changed else 0
            decisions[assessment.decision] += 1
            unregulated_sigma = self.rzs.unregulated_prediction(case.input)
            predicted_regret = max(0.0, prediction.sigma_after - unregulated_sigma)

            self.store.log_stress(
                self.scenario_id,
                "stress_case",
                case,
                assessment,
                {
                    "description": case.description,
                    "expected_family": case.expected_family,
                    "formula": FORMULA,
                    "assessment": asdict(assessment),
                },
            )
            for name, ok, measured, relation, payload in self.invariant_results(case, assessment, prediction):
                self.store.log_invariant(self.scenario_id, case.stress_id, name, ok, measured, relation, payload)
            self.store.log_prediction(self.scenario_id, case, assessment, prediction)
            self.store.log_causal(
                self.scenario_id,
                case,
                assessment,
                counterfactual,
                changed,
                predicted_regret,
                {
                    "counterfactual_action": counterfactual,
                    "regulated_prediction": asdict(prediction),
                    "unregulated_sigma_after": unregulated_sigma,
                    "causal_reason": assessment.reason,
                },
            )

        counts_after = self.store.source_counts()
        self.store.log_stress(
            self.scenario_id,
            "scenario_complete",
            None,
            None,
            {
                "scenario_complete": True,
                "formula": FORMULA,
                "decisions": dict(decisions),
                "changed_decisions": changed_count,
                "source_counts_before": self.counts_before,
                "source_counts_after": counts_after,
            },
        )
        return {"scenario_id": self.scenario_id, "decisions": dict(decisions), "changed_decisions": changed_count}


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin RZS Nervous System v49.3")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    run = RZSNervousSystem(seed=args.seed)
    result = run.run()
    print(f"DARWIN v49.3 RZS formal concluido: scenario={result['scenario_id']}")
    print(f"decisions={result['decisions']}")
    print(f"changed_decisions={result['changed_decisions']}")
    if args.details:
        print(f"formula={FORMULA}")
        print(f"thresholds={[asdict(t) for t in run.rzs.thresholds]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
