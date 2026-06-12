from __future__ import annotations

"""
DARWIN v49.0 - Diagnostico do Brain Core operacional

Uso:
    py darwin_check_v49_0_brain_core.py
    py darwin_check_v49_0_brain_core.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
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

REQUIRED_EVENT_FIELDS = [
    "scenario_id",
    "cycle_id",
    "phase",
    "focus_key",
    "rzs_decision",
    "sigma_before",
    "sigma_after",
    "cognitive_action",
    "payload_json",
]


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


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def fetch_table(conn: sqlite3.Connection, table: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    params: tuple[Any, ...] = ()
    where = ""
    if scenario_id is not None:
        where = " WHERE scenario_id=?"
        params = (scenario_id,)
    out: list[dict[str, Any]] = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_scenario(cycle_rows: list[dict[str, Any]]) -> str | None:
    completed = [
        str(r["scenario_id"])
        for r in cycle_rows
        if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if completed:
        return completed[-1]
    ids = [str(r["scenario_id"]) for r in cycle_rows if r.get("scenario_id")]
    return ids[-1] if ids else None


def phase_order_ok(rows: list[dict[str, Any]]) -> tuple[bool, dict[int, list[str]]]:
    by_cycle: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cycle[int(row["cycle_id"])].append(row)

    observed: dict[int, list[str]] = {}
    ok = True
    for cycle_id, cycle_rows in sorted(by_cycle.items()):
        phases = [str(r["phase"]) for r in cycle_rows]
        observed[cycle_id] = phases
        if phases != PHASES:
            ok = False
    return ok and bool(by_cycle), observed


def source_table_count(conn: sqlite3.Connection, table: str) -> tuple[int, int]:
    if not table_exists(conn, table):
        return 0, 0
    row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
    return int(row["n"]), int(row["max_id"])


def table_column_check(conn: sqlite3.Connection) -> dict[str, bool]:
    return {
        table: set(REQUIRED_EVENT_FIELDS).issubset(columns(conn, table))
        for table in (CYCLES_TABLE, WM_TABLE, ATT_TABLE, REPLAY_TABLE)
    }


def diagnose(conn: sqlite3.Connection) -> dict[str, Any]:
    all_cycles = fetch_table(conn, CYCLES_TABLE)
    scenario_id = latest_scenario(all_cycles)
    rows = [r for r in all_cycles if r.get("scenario_id") == scenario_id] if scenario_id else []
    wm_rows = fetch_table(conn, WM_TABLE, scenario_id)
    att_rows = fetch_table(conn, ATT_TABLE, scenario_id)
    replay_rows = fetch_table(conn, REPLAY_TABLE, scenario_id)

    phase_counts = Counter(str(r["phase"]) for r in rows)
    decisions = Counter(str(r.get("rzs_decision") or "-") for r in rows if r.get("phase") == "rzs_assess")
    actions = Counter(str(r.get("cognitive_action") or "-") for r in rows if r.get("phase") == "cognitive_action_execute")
    completed_cycles = sorted({int(r["cycle_id"]) for r in rows if r.get("phase") == "cycle_complete"})
    ordered_ok, observed_phases = phase_order_ok(rows)

    perception_sources: set[str] = set()
    for row in rows:
        if row.get("phase") != "perceive_internal_events":
            continue
        for source in row.get("payload", {}).get("sources", []):
            perception_sources.add(str(source))

    wm_per_cycle = Counter(int(r["cycle_id"]) for r in wm_rows)
    wm_payload_decayed = any(r.get("payload", {}).get("decayed") is True for r in wm_rows)
    wm_cycle_payload_decayed = any(
        r.get("phase") == "working_memory_update" and r.get("payload", {}).get("decay_applied") is True
        for r in rows
    )
    wm_promoted = any(int(r.get("promoted") or 0) == 1 or int(r.get("evidence_count") or 0) >= 2 for r in wm_rows)

    demanded_cycles = {
        int(r["cycle_id"])
        for r in rows
        if r.get("phase") == "rzs_assess" and r.get("payload", {}).get("stability_demanded") is True
    }
    stability_actions = {
        int(r["cycle_id"])
        for r in rows
        if r.get("phase") == "cognitive_action_execute"
        and str(r.get("cognitive_action")) in {"consolidate", "pause_for_stability"}
    }

    final_payloads = [
        r.get("payload", {})
        for r in rows
        if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    final_payload = final_payloads[-1] if final_payloads else {}
    source_count_now, source_max_now = source_table_count(conn, SOURCE_V48_9)
    v48_payload_clean = (
        bool(final_payload)
        and final_payload.get("v48_9_count_before") == final_payload.get("v48_9_count_after")
        and final_payload.get("v48_9_max_before") == final_payload.get("v48_9_max_after")
    )
    v48_now_clean = (
        bool(final_payload)
        and final_payload.get("v48_9_count_after") == source_count_now
        and final_payload.get("v48_9_max_after") == source_max_now
    )

    table_columns = table_column_check(conn)
    checks = {
        "new_tables_exist": all(table_exists(conn, t) for t in (CYCLES_TABLE, WM_TABLE, ATT_TABLE, REPLAY_TABLE)),
        "required_event_fields": all(table_columns.values()),
        "has_scenario": bool(scenario_id),
        "scenario_complete": bool(final_payload.get("scenario_complete")),
        "min_12_cycles": len(completed_cycles) >= 12,
        "cycle_phases_in_causal_order": ordered_ok,
        "perception_reads_internal_events": {"episodes", "semantic_memory", "state_history", SOURCE_V48_9}.issubset(perception_sources),
        "attention_selected_focus": bool(att_rows) and all(str(r.get("focus_key") or "") for r in att_rows),
        "working_memory_updated": bool(wm_rows),
        "working_memory_limit_7": bool(wm_per_cycle) and max(wm_per_cycle.values()) <= 7,
        "working_memory_decay_logged": wm_payload_decayed and wm_cycle_payload_decayed,
        "working_memory_repetition_evidence": wm_promoted,
        "rzs_assessed": phase_counts.get("rzs_assess", 0) >= len(completed_cycles) >= 1,
        "rzs_influenced_decision": any(str(k) not in {"", "-", "continue"} for k in decisions),
        "cognitive_action_selected": phase_counts.get("cognitive_action_select", 0) >= len(completed_cycles) >= 1,
        "cognitive_action_executed": phase_counts.get("cognitive_action_execute", 0) >= len(completed_cycles) >= 1,
        "replay_occurred": bool(replay_rows),
        "consolidation_when_demanded": bool(demanded_cycles) and demanded_cycles.issubset(stability_actions),
        "v48_9_not_corrupted": v48_payload_clean and v48_now_clean,
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "rows": rows,
        "wm_rows": wm_rows,
        "att_rows": att_rows,
        "replay_rows": replay_rows,
        "checks": checks,
        "phase_counts": dict(phase_counts),
        "decisions": dict(decisions),
        "actions": dict(actions),
        "completed_cycles": completed_cycles,
        "observed_phases": observed_phases,
        "perception_sources": sorted(perception_sources),
        "table_columns": table_columns,
        "final_payload": final_payload,
    }


def summary(row: dict[str, Any]) -> str:
    return (
        f"#{row['id']} | cycle={row['cycle_id']:02d} | {row['phase']} | "
        f"focus={row.get('focus_key') or '-'} | rzs={row.get('rzs_decision') or '-'} | "
        f"action={row.get('cognitive_action') or '-'} | "
        f"sigma={float(row.get('sigma_before') or 0.0):.3f}->{float(row.get('sigma_after') or 0.0):.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v49.0 - DIAGNOSTICO DO BRAIN CORE")
    print("=" * 72)
    print(f"Banco: {DB}\n")

    with connect() as conn:
        rep = diagnose(conn)

    print("Resumo:")
    print(f"- cenario analisado: {rep['scenario_id']}")
    print(f"- ciclos completos: {len(rep['completed_cycles'])}")
    print(f"- eventos de ciclo: {len(rep['rows'])}")
    print(f"- eventos de memoria de trabalho: {len(rep['wm_rows'])}")
    print(f"- eventos de atencao: {len(rep['att_rows'])}")
    print(f"- eventos de replay: {len(rep['replay_rows'])}")
    print(f"- fontes perceptivas: {', '.join(rep['perception_sources']) or '-'}")

    print("\nFases:")
    for phase in PHASES:
        print(f"- {phase}: {rep['phase_counts'].get(phase, 0)}")

    print("\nRZS:")
    for decision, count in sorted(rep["decisions"].items()):
        print(f"- {decision}: {count}")

    print("\nAcoes cognitivas:")
    for action, count in sorted(rep["actions"].items()):
        print(f"- {action}: {count}")

    labels = {
        "new_tables_exist": "tabelas v49.0 existem",
        "required_event_fields": "campos obrigatorios existem",
        "has_scenario": "ha cenario analisavel",
        "scenario_complete": "cenario concluiu",
        "min_12_cycles": "minimo de 12 ciclos completos",
        "cycle_phases_in_causal_order": "fases em ordem causal fixa",
        "perception_reads_internal_events": "percepcao usa eventos internos",
        "attention_selected_focus": "atencao escolheu foco",
        "working_memory_updated": "memoria de trabalho atualizou",
        "working_memory_limit_7": "memoria de trabalho respeitou limite 7",
        "working_memory_decay_logged": "memoria de trabalho decaiu por ciclo",
        "working_memory_repetition_evidence": "repeticao/evidencia apareceu na memoria",
        "rzs_assessed": "RZS avaliou todos os ciclos",
        "rzs_influenced_decision": "RZS influenciou pelo menos uma decisao",
        "cognitive_action_selected": "acao cognitiva foi selecionada",
        "cognitive_action_executed": "acao cognitiva foi executada",
        "replay_occurred": "replay ocorreu",
        "consolidation_when_demanded": "consolidacao/pausa ocorreu quando exigida",
        "v48_9_not_corrupted": "eventos v48.9 nao foram corrompidos",
    }

    print("\nVerificacoes:")
    for key, value in rep["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print(
        "Leitura: Darwin executou um loop cognitivo unico, auditavel e regulado por RZS."
        if rep["ok"]
        else "Leitura: ainda falta evidencia completa para declarar a v49.0 operacional."
    )

    if args.details:
        print("\nEventos do cenario:")
        for row in rep["rows"]:
            print("  " + summary(row))

        print("\nMemoria de trabalho por ciclo:")
        counts = Counter(int(r["cycle_id"]) for r in rep["wm_rows"])
        for cycle_id in sorted(counts):
            print(f"  cycle={cycle_id:02d} itens={counts[cycle_id]}")

        print("\nReplay:")
        for row in rep["replay_rows"]:
            print(
                f"  #{row['id']} | cycle={row['cycle_id']:02d} | "
                f"{row.get('replay_kind') or '-'} | key={row.get('replay_key') or '-'}"
            )

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
