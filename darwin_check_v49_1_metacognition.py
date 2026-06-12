from __future__ import annotations

"""
DARWIN v49.1 - Diagnostico de metacognicao operacional

Uso:
    py darwin_check_v49_1_metacognition.py
    py darwin_check_v49_1_metacognition.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
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

META_PHASES = [
    "meta_cycle_start",
    "read_brain_trace",
    "self_check",
    "health_assess",
    "meta_decision_select",
    "meta_action_execute",
    "meta_cycle_complete",
]

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

REQUIRED_CHECKS = {
    "v49_phase_integrity",
    "v49_minimum_cycles",
    "rzs_regulation_present",
    "attention_flexibility",
    "action_diversity",
    "working_memory_bound",
    "replay_recency",
    "consolidation_available",
    "v48_9_integrity",
}


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if scenario_id is not None:
        where = " WHERE scenario_id=?"
        params = (scenario_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_meta_scenario(meta_rows: list[dict[str, Any]]) -> str | None:
    completed = [
        str(r["scenario_id"])
        for r in meta_rows
        if r.get("phase") == "meta_cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if completed:
        return completed[-1]
    ids = [str(r["scenario_id"]) for r in meta_rows if r.get("scenario_id")]
    return ids[-1] if ids else None


def phase_order_ok(meta_rows: list[dict[str, Any]]) -> tuple[bool, dict[int, list[str]]]:
    by_cycle: dict[int, list[str]] = defaultdict(list)
    for row in meta_rows:
        by_cycle[int(row["meta_cycle_id"])].append(str(row["phase"]))
    return bool(by_cycle) and all(phases == META_PHASES for phases in by_cycle.values()), dict(by_cycle)


def latest_observed_v49(meta_rows: list[dict[str, Any]]) -> str | None:
    ids = [str(r.get("observed_scenario_id") or "") for r in meta_rows if str(r.get("observed_scenario_id") or "")]
    return ids[-1] if ids else None


def v49_phase_integrity(conn: sqlite3.Connection, observed_scenario_id: str | None) -> bool:
    if not observed_scenario_id:
        return False
    cycle_rows = rows(conn, V49_CYCLES, observed_scenario_id)
    by_cycle: dict[int, list[str]] = defaultdict(list)
    for row in cycle_rows:
        by_cycle[int(row["cycle_id"])].append(str(row["phase"]))
    completed = {int(r["cycle_id"]) for r in cycle_rows if r.get("phase") == "cycle_complete"}
    return len(completed) >= 12 and bool(by_cycle) and all(phases == V49_PHASES for phases in by_cycle.values())


def v48_9_integrity(conn: sqlite3.Connection, observed_scenario_id: str | None) -> bool:
    if not observed_scenario_id or not table_exists(conn, SOURCE_V48_9):
        return False
    row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {SOURCE_V48_9}").fetchone()
    now_count, now_max = int(row["n"]), int(row["max_id"])
    final_rows = [
        r for r in rows(conn, V49_CYCLES, observed_scenario_id)
        if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if not final_rows:
        return False
    payload = final_rows[-1]["payload"]
    return (
        payload.get("v48_9_count_before") == payload.get("v48_9_count_after") == now_count
        and payload.get("v48_9_max_before") == payload.get("v48_9_max_after") == now_max
    )


def has_v491_semantic_memory(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM semantic_memory WHERE key LIKE 'brain_v49_1:%' AND source='brain_metacognition_v49_1'"
    ).fetchone()
    return int(row["n"]) > 0


def diagnose(conn: sqlite3.Connection) -> dict[str, Any]:
    all_meta = rows(conn, META_CYCLES)
    scenario_id = latest_meta_scenario(all_meta)
    meta_rows = [r for r in all_meta if r.get("scenario_id") == scenario_id] if scenario_id else []
    check_rows = rows(conn, SELF_CHECKS, scenario_id)
    intervention_rows = rows(conn, INTERVENTIONS, scenario_id)
    observed_v49 = latest_observed_v49(meta_rows)
    ordered_ok, observed_phases = phase_order_ok(meta_rows)

    completed_meta_cycles = sorted({int(r["meta_cycle_id"]) for r in meta_rows if r.get("phase") == "meta_cycle_complete"})
    phase_counts = Counter(str(r["phase"]) for r in meta_rows)
    actions = Counter(str(r.get("meta_action") or "-") for r in meta_rows if r.get("phase") == "meta_action_execute")
    decisions = Counter(str(r.get("meta_decision") or "-") for r in meta_rows if r.get("phase") == "meta_decision_select")
    check_names = {str(r.get("check_name")) for r in check_rows}
    attention_findings = [
        r for r in check_rows
        if r.get("check_name") == "attention_flexibility" and r.get("status") == "ATTENTION"
    ]
    health_rows = [r for r in meta_rows if r.get("phase") == "health_assess"]
    read_rows = [r for r in meta_rows if r.get("phase") == "read_brain_trace"]

    health_scores = [float(r.get("health_score") or 0.0) for r in health_rows]
    risk_scores = [float(r.get("risk_score") or 0.0) for r in health_rows]
    source_sets = [
        set(str(x) for x in r.get("payload", {}).get("source_tables", []))
        for r in read_rows
    ]
    needed_sources = {V49_CYCLES, V49_WM, V49_ATT, V49_REPLAY, SOURCE_V48_9, "current_state"}

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (META_CYCLES, SELF_CHECKS, INTERVENTIONS)),
        "has_scenario": bool(scenario_id),
        "scenario_complete": any(r.get("payload", {}).get("scenario_complete") is True for r in meta_rows if r.get("phase") == "meta_cycle_complete"),
        "min_6_meta_cycles": len(completed_meta_cycles) >= 6,
        "meta_phases_ordered": ordered_ok,
        "reads_v49_0_tables": bool(source_sets) and all(needed_sources.issubset(s) for s in source_sets),
        "self_checks_present": REQUIRED_CHECKS.issubset(check_names),
        "health_assessed": bool(health_rows) and all(0.0 <= x <= 1.0 for x in health_scores) and all(0.0 <= x <= 1.0 for x in risk_scores),
        "risk_vector_logged": all("risk_vector" in r.get("payload", {}) for r in health_rows),
        "decision_selected": bool(decisions) and all(k != "-" for k in decisions),
        "intervention_logged": bool(intervention_rows),
        "non_passive_intervention": any(str(r.get("meta_action")) != "continue_observing" for r in intervention_rows),
        "attention_lock_detected": bool(attention_findings),
        "semantic_continuity_written": has_v491_semantic_memory(conn),
        "v49_0_integrity_preserved": v49_phase_integrity(conn, observed_v49),
        "v48_9_integrity_preserved": v48_9_integrity(conn, observed_v49),
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "observed_v49": observed_v49,
        "meta_rows": meta_rows,
        "check_rows": check_rows,
        "intervention_rows": intervention_rows,
        "checks": checks,
        "phase_counts": dict(phase_counts),
        "actions": dict(actions),
        "decisions": dict(decisions),
        "completed_meta_cycles": completed_meta_cycles,
        "observed_phases": observed_phases,
        "health_scores": health_scores,
        "risk_scores": risk_scores,
        "check_names": sorted(check_names),
    }


def summary(row: dict[str, Any]) -> str:
    return (
        f"#{row['id']} | meta_cycle={row['meta_cycle_id']:02d} | {row['phase']} | "
        f"health={float(row.get('health_score') or 0.0):.3f} | "
        f"risk={float(row.get('risk_score') or 0.0):.3f} | "
        f"decision={row.get('meta_decision') or '-'} | action={row.get('meta_action') or '-'}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v49.1 - DIAGNOSTICO DE METACOGNICAO OPERACIONAL")
    print("=" * 72)
    print(f"Banco: {DB}\n")

    with connect() as conn:
        rep = diagnose(conn)

    print("Resumo:")
    print(f"- cenario v49.1: {rep['scenario_id']}")
    print(f"- cenario v49.0 observado: {rep['observed_v49']}")
    print(f"- ciclos metacognitivos completos: {len(rep['completed_meta_cycles'])}")
    print(f"- eventos meta: {len(rep['meta_rows'])}")
    print(f"- self-checks: {len(rep['check_rows'])}")
    print(f"- intervencoes: {len(rep['intervention_rows'])}")
    if rep["health_scores"]:
        print(f"- health final: {rep['health_scores'][-1]:.4f}")
        print(f"- risk final: {rep['risk_scores'][-1]:.4f}")

    print("\nFases:")
    for phase in META_PHASES:
        print(f"- {phase}: {rep['phase_counts'].get(phase, 0)}")

    print("\nDecisoes:")
    for decision, count in sorted(rep["decisions"].items()):
        print(f"- {decision}: {count}")

    print("\nAcoes:")
    for action, count in sorted(rep["actions"].items()):
        print(f"- {action}: {count}")

    labels = {
        "tables_exist": "tabelas v49.1 existem",
        "has_scenario": "ha cenario analisavel",
        "scenario_complete": "cenario metacognitivo concluiu",
        "min_6_meta_cycles": "minimo de 6 ciclos metacognitivos",
        "meta_phases_ordered": "fases metacognitivas em ordem",
        "reads_v49_0_tables": "leu tabelas do Brain Core v49.0",
        "self_checks_present": "self-checks obrigatorios existem",
        "health_assessed": "health/risk score calculados",
        "risk_vector_logged": "vetor de risco registrado",
        "decision_selected": "decisao metacognitiva selecionada",
        "intervention_logged": "intervencao registrada",
        "non_passive_intervention": "intervencao nao passiva ocorreu",
        "attention_lock_detected": "travamento atencional foi detectado",
        "semantic_continuity_written": "continuidade escrita na memoria semantica",
        "v49_0_integrity_preserved": "integridade v49.0 preservada",
        "v48_9_integrity_preserved": "integridade v48.9 preservada",
    }

    print("\nVerificacoes:")
    for key, value in rep["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print(
        "Leitura: Darwin observou o proprio Brain Core e registrou autocorrecao operacional."
        if rep["ok"]
        else "Leitura: ainda falta evidencia metacognitiva completa."
    )

    if args.details:
        print("\nEventos meta:")
        for row in rep["meta_rows"]:
            print("  " + summary(row))

        print("\nSelf-checks:")
        for row in rep["check_rows"]:
            print(
                f"  #{row['id']} | meta_cycle={row['meta_cycle_id']:02d} | "
                f"{row['check_name']}={row['status']} | score={float(row.get('score') or 0.0):.3f}"
            )

        print("\nIntervencoes:")
        for row in rep["intervention_rows"]:
            print(
                f"  #{row['id']} | meta_cycle={row['meta_cycle_id']:02d} | "
                f"{row['meta_decision']} -> {row['meta_action']} | "
                f"health={float(row.get('health_before') or 0.0):.3f}->{float(row.get('health_after') or 0.0):.3f}"
            )

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
