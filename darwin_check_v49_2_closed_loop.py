from __future__ import annotations

"""
DARWIN v49.2 - Diagnostico de closed-loop metacognitivo

Uso:
    py darwin_check_v49_2_closed_loop.py
    py darwin_check_v49_2_closed_loop.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

V49_CYCLES = "brain_cycles_v49_0"
SOURCE_V48_9 = "geometry_multistep_plans_v48_9"
META_CYCLES = "brain_meta_cycles_v49_1"
META_INTERVENTIONS = "brain_stability_interventions_v49_1"

CLOSED_LOOP = "brain_closed_loop_cycles_v49_2"
MODULATION = "brain_attention_modulation_v49_2"
BEHAVIOR_DELTA = "brain_behavior_delta_v49_2"

PHASES = [
    "closed_loop_start",
    "read_metacognitive_intervention",
    "perceive_internal_events",
    "apply_modulation_policy",
    "attention_select_modulated",
    "cognitive_action_execute",
    "measure_behavior_delta",
    "closed_loop_complete",
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


def latest_scenario(loop_rows: list[dict[str, Any]]) -> str | None:
    completed = [
        str(r["scenario_id"])
        for r in loop_rows
        if r.get("phase") == "closed_loop_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if completed:
        return completed[-1]
    ids = [str(r["scenario_id"]) for r in loop_rows if r.get("scenario_id")]
    return ids[-1] if ids else None


def phase_order_ok(loop_rows: list[dict[str, Any]]) -> tuple[bool, dict[int, list[str]]]:
    by_cycle: dict[int, list[str]] = defaultdict(list)
    for row in loop_rows:
        by_cycle[int(row["loop_cycle_id"])].append(str(row["phase"]))
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


def has_v492_memory(conn: sqlite3.Connection, scenario_id: str | None) -> bool:
    if not scenario_id or not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE key=? AND source='brain_closed_loop_v49_2'
        """,
        (f"brain_v49_2:closed_loop:{scenario_id}",),
    ).fetchone()
    return int(row["n"]) > 0


def diagnose(conn: sqlite3.Connection) -> dict[str, Any]:
    all_loop = rows(conn, CLOSED_LOOP)
    scenario_id = latest_scenario(all_loop)
    loop_rows = [r for r in all_loop if r.get("scenario_id") == scenario_id] if scenario_id else []
    mod_rows = rows(conn, MODULATION, scenario_id)
    delta_rows = rows(conn, BEHAVIOR_DELTA, scenario_id)
    ordered_ok, observed_phases = phase_order_ok(loop_rows)

    completed = sorted({int(r["loop_cycle_id"]) for r in loop_rows if r.get("phase") == "closed_loop_complete"})
    phase_counts = Counter(str(r["phase"]) for r in loop_rows)
    selected_rows = [r for r in mod_rows if int(r.get("selected") or 0) == 1]
    selected_focuses = [str(r.get("focus_key") or "") for r in selected_rows]
    selected_counts = Counter(selected_focuses)

    final_rows = [
        r for r in loop_rows
        if r.get("phase") == "closed_loop_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    final_payload = final_rows[-1].get("payload", {}) if final_rows else {}
    latest_delta = delta_rows[-1] if delta_rows else {}

    inhibited_focus = str(final_rows[-1].get("inhibited_focus") or "") if final_rows else ""
    baseline_lock = float(latest_delta.get("baseline_lock_ratio") or 0.0) if latest_delta else 0.0
    inhibited_ratio = float(latest_delta.get("modulated_inhibited_ratio") or 0.0) if latest_delta else 0.0
    dominant_ratio = float(latest_delta.get("modulated_dominant_ratio") or 0.0) if latest_delta else 0.0
    attention_shift = int(latest_delta.get("attention_shift") or 0) == 1 if latest_delta else False

    read_rows = [r for r in loop_rows if r.get("phase") == "read_metacognitive_intervention"]
    policy_rows = [r for r in loop_rows if r.get("phase") == "apply_modulation_policy"]
    perception_sources: set[str] = set()
    for row in loop_rows:
        if row.get("phase") == "perceive_internal_events":
            perception_sources.update(str(x) for x in row.get("payload", {}).get("sources", []))

    inhibition_rows = [r for r in mod_rows if float(r.get("inhibition_applied") or 0.0) > 0.0]
    inhibited_selected = [f for f in selected_focuses if f == inhibited_focus]
    shifted_selected = [f for f in selected_focuses if f and f != inhibited_focus]

    observed_v49_0 = str(final_rows[-1].get("observed_v49_0") or "") if final_rows else ""
    observed_v49_1 = str(final_rows[-1].get("observed_v49_1") or "") if final_rows else ""
    v48_ok = source_integrity(final_payload, SOURCE_V48_9, count_max(conn, SOURCE_V48_9))
    v49_ok = source_integrity(final_payload, V49_CYCLES, count_max(conn, V49_CYCLES))
    v491_ok = source_integrity(final_payload, META_CYCLES, count_max(conn, META_CYCLES))

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (CLOSED_LOOP, MODULATION, BEHAVIOR_DELTA)),
        "has_scenario": bool(scenario_id),
        "scenario_complete": bool(final_payload.get("scenario_complete")),
        "min_8_cycles": len(completed) >= 8,
        "phases_ordered": ordered_ok,
        "read_v49_1_intervention": bool(read_rows) and any(r.get("modulation_action") == "stabilize_attention" for r in read_rows),
        "policy_applied": bool(policy_rows) and any(r.get("payload", {}).get("policy", {}).get("policy_kind") == "attention_stabilization" for r in policy_rows),
        "internal_perception_sources": {META_INTERVENTIONS, "semantic_memory", SOURCE_V48_9}.issubset(perception_sources),
        "modulation_logged": bool(mod_rows) and len(mod_rows) >= len(completed) * 3,
        "inhibition_applied_to_problem_focus": bool(inhibition_rows) and all(r.get("focus_key") == inhibited_focus for r in inhibition_rows),
        "selected_focus_shifted": bool(shifted_selected) and len(inhibited_selected) < len(shifted_selected),
        "behavior_delta_logged": bool(delta_rows),
        "baseline_lock_was_high": baseline_lock >= 0.70,
        "inhibited_ratio_reduced": inhibited_ratio <= max(0.05, baseline_lock - 0.45),
        "dominant_ratio_reduced": dominant_ratio < baseline_lock,
        "attention_shift_confirmed": attention_shift,
        "semantic_continuity_written": has_v492_memory(conn, scenario_id),
        "observed_v49_0_present": bool(observed_v49_0),
        "observed_v49_1_present": bool(observed_v49_1),
        "v48_9_integrity_preserved": v48_ok,
        "v49_0_integrity_preserved": v49_ok,
        "v49_1_integrity_preserved": v491_ok,
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "observed_v49_0": observed_v49_0,
        "observed_v49_1": observed_v49_1,
        "loop_rows": loop_rows,
        "mod_rows": mod_rows,
        "delta_rows": delta_rows,
        "checks": checks,
        "phase_counts": dict(phase_counts),
        "completed": completed,
        "observed_phases": observed_phases,
        "selected_counts": dict(selected_counts),
        "inhibited_focus": inhibited_focus,
        "baseline_lock": baseline_lock,
        "inhibited_ratio": inhibited_ratio,
        "dominant_ratio": dominant_ratio,
        "attention_shift": attention_shift,
        "perception_sources": sorted(perception_sources),
    }


def summary(row: dict[str, Any]) -> str:
    return (
        f"#{row['id']} | cycle={row['loop_cycle_id']:02d} | {row['phase']} | "
        f"selected={row.get('selected_focus') or '-'} | action={row.get('modulation_action') or '-'} | "
        f"health={float(row.get('health_before') or 0.0):.3f}->{float(row.get('health_after') or 0.0):.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v49.2 - DIAGNOSTICO DE CLOSED-LOOP METACOGNITIVO")
    print("=" * 72)
    print(f"Banco: {DB}\n")

    with connect() as conn:
        rep = diagnose(conn)

    print("Resumo:")
    print(f"- cenario v49.2: {rep['scenario_id']}")
    print(f"- cenario v49.0 observado: {rep['observed_v49_0']}")
    print(f"- cenario v49.1 consumido: {rep['observed_v49_1']}")
    print(f"- ciclos completos: {len(rep['completed'])}")
    print(f"- eventos closed-loop: {len(rep['loop_rows'])}")
    print(f"- eventos de modulacao: {len(rep['mod_rows'])}")
    print(f"- foco inibido: {rep['inhibited_focus']}")
    print(f"- lock baseline: {rep['baseline_lock']:.4f}")
    print(f"- ratio inibido apos modulacao: {rep['inhibited_ratio']:.4f}")
    print(f"- ratio dominante apos modulacao: {rep['dominant_ratio']:.4f}")
    print(f"- attention_shift: {rep['attention_shift']}")

    print("\nFases:")
    for phase in PHASES:
        print(f"- {phase}: {rep['phase_counts'].get(phase, 0)}")

    print("\nFocos selecionados:")
    for focus, count in sorted(rep["selected_counts"].items(), key=lambda x: (-x[1], x[0])):
        print(f"- {focus}: {count}")

    labels = {
        "tables_exist": "tabelas v49.2 existem",
        "has_scenario": "ha cenario analisavel",
        "scenario_complete": "cenario closed-loop concluiu",
        "min_8_cycles": "minimo de 8 ciclos",
        "phases_ordered": "fases em ordem causal",
        "read_v49_1_intervention": "intervencao v49.1 foi lida",
        "policy_applied": "politica de modulacao aplicada",
        "internal_perception_sources": "percepcao interna usou fontes esperadas",
        "modulation_logged": "modulacao por candidato foi registrada",
        "inhibition_applied_to_problem_focus": "inibicao aplicada ao foco problemático",
        "selected_focus_shifted": "foco selecionado mudou",
        "behavior_delta_logged": "delta comportamental registrado",
        "baseline_lock_was_high": "baseline tinha travamento alto",
        "inhibited_ratio_reduced": "ratio do foco inibido caiu",
        "dominant_ratio_reduced": "dominancia atencional caiu",
        "attention_shift_confirmed": "mudanca atencional confirmada",
        "semantic_continuity_written": "continuidade escrita na memoria semantica",
        "observed_v49_0_present": "cenario v49.0 referenciado",
        "observed_v49_1_present": "cenario v49.1 referenciado",
        "v48_9_integrity_preserved": "integridade v48.9 preservada",
        "v49_0_integrity_preserved": "integridade v49.0 preservada",
        "v49_1_integrity_preserved": "integridade v49.1 preservada",
    }

    print("\nVerificacoes:")
    for key, value in rep["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print(
        "Leitura: a intervencao metacognitiva modulou o ciclo seguinte e alterou o foco."
        if rep["ok"]
        else "Leitura: ainda falta prova completa de closed-loop metacognitivo."
    )

    if args.details:
        print("\nEventos closed-loop:")
        for row in rep["loop_rows"]:
            print("  " + summary(row))

        print("\nDelta:")
        for row in rep["delta_rows"]:
            print(
                f"  #{row['id']} | baseline={float(row['baseline_lock_ratio']):.3f} | "
                f"inibido={float(row['modulated_inhibited_ratio']):.3f} | "
                f"dominante={float(row['modulated_dominant_ratio']):.3f} | "
                f"shift={int(row['attention_shift'])}"
            )

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
