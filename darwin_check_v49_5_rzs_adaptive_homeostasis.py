from __future__ import annotations

"""
DARWIN v49.5 - Diagnostico da plasticidade homeostatica do RZS

Uso:
    py darwin_check_v49_5_rzs_adaptive_homeostasis.py
    py darwin_check_v49_5_rzs_adaptive_homeostasis.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter
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

REQUIRED_GUARDRAILS = {
    "threshold_order_preserved",
    "max_shift_limited",
    "all_thresholds_within_bounds",
    "prediction_errors_bounded",
    "adaptation_not_zero",
    "boundary_behavior_changed",
}

BOUNDS = {
    "critical_pause": (0.85, 1.05),
    "overload_consolidate": (1.05, 1.25),
    "narrow_focus": (1.35, 1.75),
    "replay_memory": (2.05, 2.55),
    "stable_continue": (999.0, 999.0),
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
        if r.get("phase") == "plasticity_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if completed:
        return completed[-1]
    ids = [str(r["scenario_id"]) for r in cycle_rows if r.get("scenario_id")]
    return ids[-1] if ids else None


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


def has_v495_memory(conn: sqlite3.Connection, scenario_id: str | None) -> bool:
    if not scenario_id or not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE key=? AND source='rzs_adaptive_homeostasis_v49_5'
        """,
        (f"brain_v49_5:rzs_plasticity:{scenario_id}",),
    ).fetchone()
    return int(row["n"]) > 0


def phase_order_ok(cycle_rows: list[dict[str, Any]]) -> bool:
    return [str(r["phase"]) for r in cycle_rows] == PHASES


def diagnose(conn: sqlite3.Connection) -> dict[str, Any]:
    all_cycles = rows(conn, PLASTICITY)
    scenario_id = latest_scenario(all_cycles)
    cycle_rows = [r for r in all_cycles if r.get("scenario_id") == scenario_id] if scenario_id else []
    error_rows = rows(conn, ERRORS, scenario_id)
    adaptation_rows = rows(conn, ADAPTATIONS, scenario_id)
    guardrail_rows = rows(conn, GUARDRAILS, scenario_id)
    retest_rows = rows(conn, RETESTS, scenario_id)

    final_rows = [r for r in cycle_rows if r.get("phase") == "plasticity_complete"]
    final_payload = final_rows[-1].get("payload", {}) if final_rows else {}
    phase_counts = Counter(str(r["phase"]) for r in cycle_rows)
    guardrail_names = {str(r["guardrail_name"]) for r in guardrail_rows}
    abs_errors = [float(r["abs_error"]) for r in error_rows]
    errors = [float(r["prediction_error"]) for r in error_rows]
    changed_adaptations = [r for r in adaptation_rows if abs(float(r["delta_upper"])) > 0.0001]
    max_shift = max((abs(float(r["delta_upper"])) for r in adaptation_rows), default=0.0)
    uppers = [float(r["new_upper"]) for r in adaptation_rows]
    changed_retests = [r for r in retest_rows if int(r.get("decision_changed") or 0) == 1]
    stable_far = [r for r in retest_rows if r.get("probe_kind") == "stable_far"]
    bounds_ok = all(
        BOUNDS.get(str(r["threshold_name"]), (0.0, 999.0))[0] <= float(r["new_upper"]) <= BOUNDS.get(str(r["threshold_name"]), (0.0, 999.0))[1]
        for r in adaptation_rows
    )
    evidence_ok = all(
        int(r.get("evidence_count") or 0) > 0 or str(r.get("threshold_name")) == "stable_continue"
        for r in adaptation_rows
    )

    source_governed = str(cycle_rows[-1].get("source_governed_scenario_id") or "") if cycle_rows else ""
    source_rzs = str(cycle_rows[-1].get("source_rzs_scenario_id") or "") if cycle_rows else ""

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (PLASTICITY, ERRORS, ADAPTATIONS, GUARDRAILS, RETESTS)),
        "has_scenario": bool(scenario_id),
        "scenario_complete": bool(final_payload.get("scenario_complete")),
        "phases_ordered": phase_order_ok(cycle_rows),
        "reads_v49_4_and_v49_3": bool(source_governed) and bool(source_rzs),
        "min_10_error_samples": len(error_rows) >= 10,
        "errors_nonzero": any(abs(x) > 0.0 for x in errors),
        "errors_have_positive_and_negative": any(x > 0 for x in errors) and any(x < 0 for x in errors),
        "errors_bounded": bool(abs_errors) and max(abs_errors) <= 0.12,
        "adaptations_present": len(adaptation_rows) == 5,
        "adaptations_guarded": bool(adaptation_rows) and all(int(r.get("guardrail_ok") or 0) == 1 for r in adaptation_rows),
        "adaptations_not_zero": len(changed_adaptations) >= 3,
        "adaptation_step_limited": max_shift <= 0.041,
        "threshold_order_preserved": bool(uppers) and all(uppers[i] <= uppers[i + 1] for i in range(len(uppers) - 1)),
        "threshold_bounds_preserved": bounds_ok,
        "adaptation_has_evidence": evidence_ok,
        "guardrails_present": REQUIRED_GUARDRAILS.issubset(guardrail_names),
        "all_guardrails_ok": bool(guardrail_rows) and all(str(r.get("status")) == "OK" for r in guardrail_rows),
        "boundary_retests_present": len(retest_rows) >= 5,
        "boundary_decisions_changed": len(changed_retests) >= 2,
        "stable_far_unchanged": bool(stable_far) and all(int(r.get("decision_changed") or 0) == 0 for r in stable_far),
        "semantic_continuity_written": has_v495_memory(conn, scenario_id),
        "v48_9_integrity_preserved": source_integrity(final_payload, SOURCE_V48_9, count_max(conn, SOURCE_V48_9)),
        "v49_0_integrity_preserved": source_integrity(final_payload, V49_CYCLES, count_max(conn, V49_CYCLES)),
        "v49_1_integrity_preserved": source_integrity(final_payload, V49_META, count_max(conn, V49_META)),
        "v49_2_integrity_preserved": source_integrity(final_payload, V49_CLOSED, count_max(conn, V49_CLOSED)),
        "v49_3_integrity_preserved": all(
            source_integrity(final_payload, t, count_max(conn, t))
            for t in (RZS_STRESS, RZS_THRESHOLDS, RZS_INVARIANTS, RZS_PREDICTIONS, RZS_CAUSAL)
        ),
        "v49_4_integrity_preserved": all(
            source_integrity(final_payload, t, count_max(conn, t))
            for t in (GOV_CYCLES, GOV_GATES, GOV_PREDICTIONS, GOV_OUTCOMES)
        ),
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "source_governed": source_governed,
        "source_rzs": source_rzs,
        "cycle_rows": cycle_rows,
        "error_rows": error_rows,
        "adaptation_rows": adaptation_rows,
        "guardrail_rows": guardrail_rows,
        "retest_rows": retest_rows,
        "checks": checks,
        "phase_counts": dict(phase_counts),
        "mean_abs_error": sum(abs_errors) / max(1, len(abs_errors)),
        "max_error": max(abs_errors) if abs_errors else 0.0,
        "changed_adaptations": len(changed_adaptations),
        "max_shift": max_shift,
        "changed_retests": len(changed_retests),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v49.5 - DIAGNOSTICO DA PLASTICIDADE HOMEOSTATICA RZS")
    print("=" * 72)
    print(f"Banco: {DB}\n")

    with connect() as conn:
        rep = diagnose(conn)

    print("Resumo:")
    print(f"- cenario v49.5: {rep['scenario_id']}")
    print(f"- fonte v49.4: {rep['source_governed']}")
    print(f"- fonte RZS v49.3: {rep['source_rzs']}")
    print(f"- erros medidos: {len(rep['error_rows'])}")
    print(f"- erro medio absoluto: {rep['mean_abs_error']:.4f}")
    print(f"- erro maximo: {rep['max_error']:.4f}")
    print(f"- limiares adaptados: {rep['changed_adaptations']}")
    print(f"- maior deslocamento: {rep['max_shift']:.4f}")
    print(f"- retestes alterados: {rep['changed_retests']}")

    labels = {
        "tables_exist": "tabelas v49.5 existem",
        "has_scenario": "ha cenario analisavel",
        "scenario_complete": "cenario de plasticidade concluiu",
        "phases_ordered": "fases em ordem",
        "reads_v49_4_and_v49_3": "leu v49.4 e RZS v49.3",
        "min_10_error_samples": "minimo de 10 erros medidos",
        "errors_nonzero": "erros nao sao todos zero",
        "errors_have_positive_and_negative": "erros positivos e negativos existem",
        "errors_bounded": "erros ficaram dentro do limite",
        "adaptations_present": "5 limiares adaptativos presentes",
        "adaptations_guarded": "adaptacoes passaram guardrails locais",
        "adaptations_not_zero": "adaptacao nao foi nula",
        "adaptation_step_limited": "passo de adaptacao limitado",
        "threshold_order_preserved": "ordem dos limiares preservada",
        "threshold_bounds_preserved": "bounds de seguranca preservados",
        "adaptation_has_evidence": "adaptacao tem evidencia",
        "guardrails_present": "guardrails formais presentes",
        "all_guardrails_ok": "todos guardrails OK",
        "boundary_retests_present": "retestes de fronteira presentes",
        "boundary_decisions_changed": "fronteiras mudaram onde esperado",
        "stable_far_unchanged": "estado distante estavel nao mudou",
        "semantic_continuity_written": "continuidade escrita na memoria semantica",
        "v48_9_integrity_preserved": "integridade v48.9 preservada",
        "v49_0_integrity_preserved": "integridade v49.0 preservada",
        "v49_1_integrity_preserved": "integridade v49.1 preservada",
        "v49_2_integrity_preserved": "integridade v49.2 preservada",
        "v49_3_integrity_preserved": "integridade v49.3 preservada",
        "v49_4_integrity_preserved": "integridade v49.4 preservada",
    }

    print("\nVerificacoes:")
    for key, value in rep["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print(
        "Leitura: o RZS mediu erro, adaptou limiares com guardrails e preservou estabilidade."
        if rep["ok"]
        else "Leitura: ainda falta evidencia completa de plasticidade segura."
    )

    if args.details:
        print("\nAdaptacoes:")
        for row in rep["adaptation_rows"]:
            print(
                f"  {row['threshold_name']} | {float(row['old_upper']):.4f}->{float(row['new_upper']):.4f} "
                f"delta={float(row['delta_upper']):+.4f} evidence={row['evidence_count']} mean_error={float(row['mean_error']):+.4f}"
            )

        print("\nRetestes:")
        for row in rep["retest_rows"]:
            print(
                f"  {row['probe_id']} | sigma={float(row['sigma_probe']):.3f} | "
                f"{row['old_decision']}->{row['new_decision']} | changed={int(row['decision_changed'])}"
            )

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
