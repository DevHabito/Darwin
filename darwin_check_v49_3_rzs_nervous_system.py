from __future__ import annotations

"""
DARWIN v49.3 - Diagnostico do RZS formal como sistema nervoso

Uso:
    py darwin_check_v49_3_rzs_nervous_system.py
    py darwin_check_v49_3_rzs_nervous_system.py --details
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

FORMULA = "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)"

EXPECTED_INVARIANTS = {
    "input_finite_nonnegative",
    "denominator_positive",
    "sigma_positive_finite",
    "formula_reproducible",
    "monotonic_conflict",
    "monotonic_latency",
    "monotonic_bandwidth",
    "threshold_decision_deterministic",
    "prediction_effect_valid",
}

EXPECTED_THRESHOLDS = {
    "critical_pause",
    "overload_consolidate",
    "narrow_focus",
    "replay_memory",
    "stable_continue",
}

EXPECTED_DECISIONS = {
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


def latest_scenario(stress_rows: list[dict[str, Any]]) -> str | None:
    completed = [
        str(r["scenario_id"])
        for r in stress_rows
        if r.get("phase") == "scenario_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if completed:
        return completed[-1]
    ids = [str(r["scenario_id"]) for r in stress_rows if r.get("scenario_id")]
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


def invariant_matrix_ok(stress_rows: list[dict[str, Any]], invariant_rows: list[dict[str, Any]]) -> bool:
    stress_ids = {str(r["stress_id"]) for r in stress_rows if r.get("phase") == "stress_case"}
    by_stress: dict[str, set[str]] = defaultdict(set)
    for row in invariant_rows:
        if row.get("status") == "OK":
            by_stress[str(row["stress_id"])].add(str(row["invariant_name"]))
    return bool(stress_ids) and all(EXPECTED_INVARIANTS.issubset(by_stress[sid]) for sid in stress_ids)


def diagnose(conn: sqlite3.Connection) -> dict[str, Any]:
    all_stress = rows(conn, RZS_STRESS)
    scenario_id = latest_scenario(all_stress)
    stress_rows = [r for r in all_stress if r.get("scenario_id") == scenario_id] if scenario_id else []
    threshold_rows = rows(conn, RZS_THRESHOLDS, scenario_id)
    invariant_rows = rows(conn, RZS_INVARIANTS, scenario_id)
    prediction_rows = rows(conn, RZS_PREDICTIONS, scenario_id)
    causal_rows = rows(conn, RZS_CAUSAL, scenario_id)

    stress_cases = [r for r in stress_rows if r.get("phase") == "stress_case"]
    complete_rows = [r for r in stress_rows if r.get("phase") == "scenario_complete"]
    final_payload = complete_rows[-1].get("payload", {}) if complete_rows else {}
    threshold_names = {str(r["threshold_name"]) for r in threshold_rows}
    invariant_names = {str(r["invariant_name"]) for r in invariant_rows}
    decisions = Counter(str(r["rzs_decision"]) for r in stress_cases)
    stress_ids = {str(r["stress_id"]) for r in stress_cases}
    prediction_ids = {str(r["stress_id"]) for r in prediction_rows}
    causal_ids = {str(r["stress_id"]) for r in causal_rows}
    changed_rows = [r for r in causal_rows if int(r.get("rzs_changed_decision") or 0) == 1]
    threshold_crossed_rows = [r for r in causal_rows if int(r.get("threshold_crossed") or 0) == 1]
    regret_rows = [r for r in causal_rows if float(r.get("predicted_regret") or 0.0) > 0.0]

    baseline = next((r for r in stress_cases if r.get("stress_kind") == "baseline_current"), None)
    combined = next((r for r in stress_cases if r.get("stress_kind") == "combined_overload"), None)
    recovery = next((r for r in stress_cases if r.get("stress_kind") == "recovery_check"), None)
    sigma_stress_order = bool(baseline and combined and recovery) and float(combined["sigma"]) < float(baseline["sigma"]) < float(recovery["sigma"])

    v48_ok = source_integrity(final_payload, SOURCE_V48_9, count_max(conn, SOURCE_V48_9))
    v49_ok = source_integrity(final_payload, V49_CYCLES, count_max(conn, V49_CYCLES))
    v491_ok = source_integrity(final_payload, V49_META, count_max(conn, V49_META))
    v492_ok = source_integrity(final_payload, V49_CLOSED, count_max(conn, V49_CLOSED))

    formula_rows = [
        r for r in stress_cases
        if r.get("payload", {}).get("formula") == FORMULA
    ]
    causal_reason_rows = [
        r for r in causal_rows
        if str(r.get("payload", {}).get("causal_reason") or "")
    ]

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (RZS_STRESS, RZS_THRESHOLDS, RZS_INVARIANTS, RZS_PREDICTIONS, RZS_CAUSAL)),
        "has_scenario": bool(scenario_id),
        "scenario_complete": bool(final_payload.get("scenario_complete")),
        "min_10_stress_cases": len(stress_cases) >= 10,
        "formula_logged": len(formula_rows) == len(stress_cases) and len(stress_cases) > 0,
        "thresholds_present": EXPECTED_THRESHOLDS.issubset(threshold_names),
        "invariants_present": EXPECTED_INVARIANTS.issubset(invariant_names),
        "all_invariants_ok": bool(invariant_rows) and all(str(r.get("status")) == "OK" for r in invariant_rows),
        "invariant_matrix_complete": invariant_matrix_ok(stress_rows, invariant_rows),
        "decisions_cover_policy_space": EXPECTED_DECISIONS.issubset(set(decisions.keys())),
        "predictions_for_all_stress": stress_ids == prediction_ids and bool(stress_ids),
        "all_predictions_valid": bool(prediction_rows) and all(int(r.get("prediction_valid") or 0) == 1 for r in prediction_rows),
        "causal_rows_for_all_stress": stress_ids == causal_ids and bool(stress_ids),
        "causal_decisions_changed": len(changed_rows) >= 8,
        "threshold_crossings_logged": len(threshold_crossed_rows) >= 8,
        "predicted_regret_positive": len(regret_rows) >= 8,
        "causal_reason_logged": len(causal_reason_rows) == len(causal_rows) and bool(causal_rows),
        "stress_sigma_order": sigma_stress_order,
        "v48_9_integrity_preserved": v48_ok,
        "v49_0_integrity_preserved": v49_ok,
        "v49_1_integrity_preserved": v491_ok,
        "v49_2_integrity_preserved": v492_ok,
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "stress_rows": stress_cases,
        "threshold_rows": threshold_rows,
        "invariant_rows": invariant_rows,
        "prediction_rows": prediction_rows,
        "causal_rows": causal_rows,
        "checks": checks,
        "decisions": dict(decisions),
        "threshold_names": sorted(threshold_names),
        "invariant_names": sorted(invariant_names),
        "changed_count": len(changed_rows),
        "regret_count": len(regret_rows),
        "final_payload": final_payload,
    }


def stress_summary(row: dict[str, Any]) -> str:
    return (
        f"{row['stress_id']} | {row['stress_kind']} | sigma={float(row['sigma']):.4f} | "
        f"decision={row['rzs_decision']} | threshold={row['threshold_name']}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v49.3 - DIAGNOSTICO DO RZS FORMAL")
    print("=" * 72)
    print(f"Banco: {DB}\n")

    with connect() as conn:
        rep = diagnose(conn)

    print("Resumo:")
    print(f"- cenario v49.3: {rep['scenario_id']}")
    print(f"- stress tests: {len(rep['stress_rows'])}")
    print(f"- thresholds: {len(rep['threshold_rows'])}")
    print(f"- invariantes: {len(rep['invariant_rows'])}")
    print(f"- predicoes: {len(rep['prediction_rows'])}")
    print(f"- decisoes causais: {len(rep['causal_rows'])}")
    print(f"- decisoes alteradas por RZS: {rep['changed_count']}")
    print(f"- arrependimentos previstos positivos: {rep['regret_count']}")

    print("\nDecisoes RZS:")
    for decision, count in sorted(rep["decisions"].items()):
        print(f"- {decision}: {count}")

    labels = {
        "tables_exist": "tabelas v49.3 existem",
        "has_scenario": "ha cenario analisavel",
        "scenario_complete": "cenario RZS concluiu",
        "min_10_stress_cases": "minimo de 10 stress tests",
        "formula_logged": "formula de Romero registrada",
        "thresholds_present": "limiares formais presentes",
        "invariants_present": "invariantes formais presentes",
        "all_invariants_ok": "todas invariantes passaram",
        "invariant_matrix_complete": "cada stress tem matriz completa de invariantes",
        "decisions_cover_policy_space": "decisoes cobrem espaco regulatorio",
        "predictions_for_all_stress": "ha predicao para cada stress",
        "all_predictions_valid": "todas predicoes sao validas",
        "causal_rows_for_all_stress": "ha contrafactual para cada stress",
        "causal_decisions_changed": "RZS mudou decisoes sob risco",
        "threshold_crossings_logged": "cruzamentos de limiar registrados",
        "predicted_regret_positive": "arrependimento sem RZS previsto",
        "causal_reason_logged": "razao causal registrada",
        "stress_sigma_order": "sigma responde ao estresse em ordem esperada",
        "v48_9_integrity_preserved": "integridade v48.9 preservada",
        "v49_0_integrity_preserved": "integridade v49.0 preservada",
        "v49_1_integrity_preserved": "integridade v49.1 preservada",
        "v49_2_integrity_preserved": "integridade v49.2 preservada",
    }

    print("\nVerificacoes:")
    for key, value in rep["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print(
        "Leitura: RZS atuou como sistema nervoso formal, preditivo e causal."
        if rep["ok"]
        else "Leitura: RZS ainda nao possui evidencia formal completa."
    )

    if args.details:
        print("\nStress tests:")
        for row in rep["stress_rows"]:
            print("  " + stress_summary(row))

        print("\nThresholds:")
        for row in rep["threshold_rows"]:
            print(f"  {row['threshold_name']} [{row['lower_bound']}, {row['upper_bound']}) -> {row['rzs_decision']}")

        print("\nCausalidade:")
        for row in rep["causal_rows"]:
            print(
                f"  {row['stress_id']} | counter={row['counterfactual_action']} | "
                f"rzs={row['rzs_action']} | changed={int(row['rzs_changed_decision'])} | "
                f"regret={float(row['predicted_regret']):.4f}"
            )

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
