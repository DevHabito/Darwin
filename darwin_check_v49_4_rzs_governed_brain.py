from __future__ import annotations

"""
DARWIN v49.4 - Diagnostico do Brain Core governado por RZS formal

Uso:
    py darwin_check_v49_4_rzs_governed_brain.py
    py darwin_check_v49_4_rzs_governed_brain.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
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

EXPECTED_ACTIONS = {
    "continue",
    "narrow_focus",
    "replay_memory",
    "consolidate",
    "pause_for_stability",
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


def latest_scenario(cycle_rows: list[dict[str, Any]]) -> str | None:
    completed = [
        str(r["scenario_id"])
        for r in cycle_rows
        if r.get("phase") == "governed_cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if completed:
        return completed[-1]
    ids = [str(r["scenario_id"]) for r in cycle_rows if r.get("scenario_id")]
    return ids[-1] if ids else None


def phase_order_ok(cycle_rows: list[dict[str, Any]]) -> tuple[bool, dict[int, list[str]]]:
    by_cycle: dict[int, list[str]] = defaultdict(list)
    for row in cycle_rows:
        by_cycle[int(row["governed_cycle_id"])].append(str(row["phase"]))
    return bool(by_cycle) and all(phases == PHASES for phases in by_cycle.values()), dict(by_cycle)


def count_max(conn: sqlite3.Connection, table: str) -> tuple[int, int]:
    if not table_exists(conn, table):
        return 0, 0
    row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
    return int(row["n"]), int(row["max_id"])


def source_integrity(final_payload: dict[str, Any], table: str, now_pair: tuple[int, int]) -> bool:
    before = final_payload.get("source_counts_before", {}).get(table)
    after = final_payload.get("source_counts_after", {}).get(table)
    if before is None or after is None:
        return False
    return tuple(before) == tuple(after) == now_pair


def latest_rzs_scenario(conn: sqlite3.Connection) -> str | None:
    stress_rows = rows(conn, RZS_STRESS)
    completed = [
        str(r["scenario_id"])
        for r in stress_rows
        if r.get("phase") == "scenario_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    return completed[-1] if completed else None


def has_v494_memory(conn: sqlite3.Connection, scenario_id: str | None) -> bool:
    if not scenario_id or not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE key=? AND source='brain_rzs_governed_v49_4'
        """,
        (f"brain_v49_4:rzs_governed:{scenario_id}",),
    ).fetchone()
    return int(row["n"]) > 0


def diagnose(conn: sqlite3.Connection) -> dict[str, Any]:
    all_cycles = rows(conn, GOV_CYCLES)
    scenario_id = latest_scenario(all_cycles)
    cycle_rows = [r for r in all_cycles if r.get("scenario_id") == scenario_id] if scenario_id else []
    gate_rows = rows(conn, GOV_GATES, scenario_id)
    pred_rows = rows(conn, GOV_PREDICTIONS, scenario_id)
    outcome_rows = rows(conn, GOV_OUTCOMES, scenario_id)
    ordered_ok, observed_phases = phase_order_ok(cycle_rows)

    completed = sorted({int(r["governed_cycle_id"]) for r in cycle_rows if r.get("phase") == "governed_cycle_complete"})
    final_rows = [
        r for r in cycle_rows
        if r.get("phase") == "governed_cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    final_payload = final_rows[-1].get("payload", {}) if final_rows else {}
    phase_counts = Counter(str(r["phase"]) for r in cycle_rows)
    executed_actions = Counter(str(r.get("executed_action") or "") for r in outcome_rows)
    rzs_actions = Counter(str(r.get("rzs_action") or "") for r in gate_rows)
    overrides = [r for r in gate_rows if int(r.get("rzs_changed_decision") or 0) == 1]
    threshold_crossed = [r for r in gate_rows if int(r.get("threshold_crossed") or 0) == 1]
    regrets = [r for r in pred_rows if float(r.get("predicted_regret") or 0.0) > 0.0]

    by_cycle_phase = {(int(r["governed_cycle_id"]), str(r["phase"])): int(r["id"]) for r in cycle_rows}
    causal_order = True
    for cycle_id in completed:
        proposal_id = by_cycle_phase.get((cycle_id, "candidate_action_propose"), 0)
        gate_id = by_cycle_phase.get((cycle_id, "rzs_formal_gate"), 0)
        exec_id = by_cycle_phase.get((cycle_id, "cognitive_action_execute"), 0)
        if not (proposal_id < gate_id < exec_id):
            causal_order = False
            break

    gate_cycles = {int(r["governed_cycle_id"]) for r in gate_rows}
    pred_cycles = {int(r["governed_cycle_id"]) for r in pred_rows}
    outcome_cycles = {int(r["governed_cycle_id"]) for r in outcome_rows}
    completed_set = set(completed)

    overridden_outcomes_ok = True
    outcomes_by_cycle = {int(r["governed_cycle_id"]): r for r in outcome_rows}
    for gate in overrides:
        outcome = outcomes_by_cycle.get(int(gate["governed_cycle_id"]))
        if not outcome or outcome.get("executed_action") != gate.get("rzs_action") or outcome.get("executed_action") == gate.get("proposed_action"):
            overridden_outcomes_ok = False
            break

    rzs_sid = str(final_rows[-1].get("rzs_scenario_id") or "") if final_rows else ""
    current_rzs_sid = latest_rzs_scenario(conn)
    formal_context_ok = bool(rzs_sid) and rzs_sid == current_rzs_sid
    formal_thresholds = len(rows(conn, RZS_THRESHOLDS, rzs_sid)) if rzs_sid else 0
    formal_invariants = len(rows(conn, RZS_INVARIANTS, rzs_sid)) if rzs_sid else 0

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (GOV_CYCLES, GOV_GATES, GOV_PREDICTIONS, GOV_OUTCOMES)),
        "has_scenario": bool(scenario_id),
        "scenario_complete": bool(final_payload.get("scenario_complete")),
        "min_10_cycles": len(completed) >= 10,
        "phases_ordered": ordered_ok,
        "proposal_gate_execute_order": causal_order,
        "gate_for_every_cycle": gate_cycles == completed_set and bool(completed_set),
        "prediction_for_every_cycle": pred_cycles == completed_set and bool(completed_set),
        "outcome_for_every_cycle": outcome_cycles == completed_set and bool(completed_set),
        "formal_rzs_context_used": formal_context_ok and formal_thresholds >= 5 and formal_invariants >= 90,
        "all_predictions_valid": bool(pred_rows) and all(int(r.get("prediction_valid") or 0) == 1 for r in pred_rows),
        "causal_overrides_present": len(overrides) >= 7,
        "threshold_crossings_present": len(threshold_crossed) >= 7,
        "predicted_regret_present": len(regrets) >= 8,
        "overrides_execute_rzs_action": overridden_outcomes_ok,
        "executed_actions_cover_rzs_space": EXPECTED_ACTIONS.issubset(set(executed_actions.keys())),
        "rzs_actions_cover_policy_space": EXPECTED_ACTIONS.issubset(set(rzs_actions.keys())),
        "semantic_continuity_written": has_v494_memory(conn, scenario_id),
        "v48_9_integrity_preserved": source_integrity(final_payload, SOURCE_V48_9, count_max(conn, SOURCE_V48_9)),
        "v49_0_integrity_preserved": source_integrity(final_payload, V49_CYCLES, count_max(conn, V49_CYCLES)),
        "v49_1_integrity_preserved": source_integrity(final_payload, V49_META, count_max(conn, V49_META)),
        "v49_2_integrity_preserved": source_integrity(final_payload, V49_CLOSED, count_max(conn, V49_CLOSED)),
        "v49_3_integrity_preserved": all(
            source_integrity(final_payload, t, count_max(conn, t))
            for t in (RZS_STRESS, RZS_THRESHOLDS, RZS_INVARIANTS, RZS_PREDICTIONS, RZS_CAUSAL)
        ),
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "rzs_scenario_id": rzs_sid,
        "cycle_rows": cycle_rows,
        "gate_rows": gate_rows,
        "pred_rows": pred_rows,
        "outcome_rows": outcome_rows,
        "checks": checks,
        "completed": completed,
        "phase_counts": dict(phase_counts),
        "executed_actions": dict(executed_actions),
        "rzs_actions": dict(rzs_actions),
        "overrides": len(overrides),
        "threshold_crossed": len(threshold_crossed),
        "regrets": len(regrets),
        "observed_phases": observed_phases,
    }


def cycle_summary(row: dict[str, Any]) -> str:
    return (
        f"#{row['id']} | cycle={row['governed_cycle_id']:02d} | {row['phase']} | "
        f"proposal={row.get('proposed_action') or '-'} | rzs={row.get('rzs_action') or '-'} | "
        f"exec={row.get('executed_action') or '-'} | "
        f"sigma={float(row.get('sigma_before') or 0.0):.3f}->{float(row.get('sigma_after') or 0.0):.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v49.4 - DIAGNOSTICO DO BRAIN GOVERNADO POR RZS")
    print("=" * 72)
    print(f"Banco: {DB}\n")

    with connect() as conn:
        rep = diagnose(conn)

    print("Resumo:")
    print(f"- cenario v49.4: {rep['scenario_id']}")
    print(f"- RZS formal usado: {rep['rzs_scenario_id']}")
    print(f"- ciclos completos: {len(rep['completed'])}")
    print(f"- gates: {len(rep['gate_rows'])}")
    print(f"- predicoes: {len(rep['pred_rows'])}")
    print(f"- outcomes: {len(rep['outcome_rows'])}")
    print(f"- overrides causais: {rep['overrides']}")
    print(f"- arrependimentos previstos: {rep['regrets']}")

    print("\nAcoes executadas:")
    for action, count in sorted(rep["executed_actions"].items()):
        if action:
            print(f"- {action}: {count}")

    labels = {
        "tables_exist": "tabelas v49.4 existem",
        "has_scenario": "ha cenario analisavel",
        "scenario_complete": "cenario governado concluiu",
        "min_10_cycles": "minimo de 10 ciclos",
        "phases_ordered": "fases em ordem causal",
        "proposal_gate_execute_order": "proposta -> gate -> execucao",
        "gate_for_every_cycle": "gate RZS em todo ciclo",
        "prediction_for_every_cycle": "predicao em todo ciclo",
        "outcome_for_every_cycle": "outcome em todo ciclo",
        "formal_rzs_context_used": "RZS formal v49.3 foi usado",
        "all_predictions_valid": "todas predicoes validas",
        "causal_overrides_present": "overrides causais presentes",
        "threshold_crossings_present": "cruzamentos de limiar presentes",
        "predicted_regret_present": "arrependimento previsto presente",
        "overrides_execute_rzs_action": "override executa acao do RZS",
        "executed_actions_cover_rzs_space": "acoes executadas cobrem espaco RZS",
        "rzs_actions_cover_policy_space": "acoes RZS cobrem espaco regulatorio",
        "semantic_continuity_written": "continuidade escrita na memoria semantica",
        "v48_9_integrity_preserved": "integridade v48.9 preservada",
        "v49_0_integrity_preserved": "integridade v49.0 preservada",
        "v49_1_integrity_preserved": "integridade v49.1 preservada",
        "v49_2_integrity_preserved": "integridade v49.2 preservada",
        "v49_3_integrity_preserved": "integridade v49.3 preservada",
    }

    print("\nVerificacoes:")
    for key, value in rep["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print(
        "Leitura: nenhuma acao cognitiva executou sem passar pelo RZS formal."
        if rep["ok"]
        else "Leitura: ainda falta prova completa de governanca obrigatoria por RZS."
    )

    if args.details:
        print("\nEventos:")
        for row in rep["cycle_rows"]:
            print("  " + cycle_summary(row))

        print("\nGates:")
        for row in rep["gate_rows"]:
            print(
                f"  cycle={row['governed_cycle_id']:02d} | proposal={row['proposed_action']} | "
                f"rzs={row['rzs_action']} | exec={row['executed_action']} | "
                f"changed={int(row['rzs_changed_decision'])} | threshold={row['threshold_name']}"
            )

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
