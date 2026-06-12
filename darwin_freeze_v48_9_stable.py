from __future__ import annotations
"""
DARWIN — Freeze Baseline v48.9 Stable

Congela o estado atual depois do planejamento multi-etapas v48.9.

Preserva:
- v48.0: encaixe físico;
- v48.1: rotação ativa;
- v48.2: erro controlado;
- v48.3.1: estratégia após erro com ordem auditável;
- v48.4: generalização por tipo de falha;
- v48.5: generalização por variação de ambiente;
- v48.6: currículo explícito de medidas e ângulos;
- v48.7: transferência conceitual com explicação antes da ação;
- v48.8: explicação causal contrastiva;
- v48.9: planejamento de ação em múltiplos passos com revisão após falha.

Uso:
    py darwin_freeze_v48_9_stable.py --dry-run
    py darwin_freeze_v48_9_stable.py

Opcional:
    py darwin_freeze_v48_9_stable.py --include-logs
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
HOME = ROOT / "darwin_home"
BASELINES = ROOT / "baselines"

REQ = [
    "darwin_v61_nursery_v47.py",
    "darwin_tension_persistence_v47.py",
    "darwin_home.py",

    "darwin_shape_sorter_nursery_v48.py",
    "darwin_shape_sorter_v48_test.py",

    "darwin_shape_sorter_live_v48_1_active_rotation.py",
    "darwin_check_v48_1_live_rotation.py",

    "darwin_shape_sorter_live_v48_2_controlled_error.py",
    "darwin_check_v48_2_controlled_error.py",

    "darwin_repair_v48_3_1_strategy_order.py",
    "darwin_shape_sorter_live_v48_3_1_strategy_after_error.py",
    "darwin_check_v48_3_1_strategy_after_error.py",

    "darwin_shape_sorter_live_v48_4_strategy_generalization.py",
    "darwin_check_v48_4_strategy_generalization.py",

    "darwin_shape_sorter_live_v48_5_variation_generalization.py",
    "darwin_check_v48_5_variation_generalization.py",

    "darwin_measure_angle_curriculum_v48_6.py",
    "darwin_check_v48_6_measure_angle_curriculum.py",

    "darwin_concept_transfer_v48_7.py",
    "darwin_check_v48_7_concept_transfer.py",

    "darwin_contrastive_explanation_v48_8.py",
    "darwin_check_v48_8_contrastive_explanation.py",

    "darwin_multistep_planning_v48_9.py",
    "darwin_check_v48_9_multistep_planning.py",
]

OPT = [
    "darwin_check_v47_tensions.py",
    "darwin_tension_dashboard_v47.py",
    "darwin_sleep_auto_guard.py",
    "darwin_sleep_consolidation.py",

    "darwin_shape_sorter_live_v48_1.py",
    "darwin_shape_sorter_live_v48_3_strategy_after_error.py",
    "darwin_check_v48_3_strategy_after_error.py",

    "darwin_freeze_v48_6_stable.py",
    "darwin_freeze_v48_7_stable.py",
    "darwin_freeze_v48_8_stable.py",

    "darwin_repair_v48_6_freeze_nameerror.py",
    "darwin_repair_v48_9_memory_log_outcome.py",
    "darwin_repair_v48_9_check_failure_detected.py",
]

V47_ZERO = [
    "tension_cases",
    "tension_events",
    "tension_probes",
    "tension_outcomes",
    "tension_resolution_routines",
    "tension_resolution_steps",
    "tension_context_comparisons",
    "tension_prediction_influences",
    "tension_hypothesis_lineage",
    "tension_cognitive_cycle_reports",
    "tension_cycle_memory_reviews",
]

V48_MIN = {
    "geometry_shapes_v48": 3,
    "geometry_pieces_v48": 6,
    "geometry_holes_v48": 3,
    "geometry_fit_attempts_v48": 27,
    "geometry_rules_v48": 3,
    "geometry_spatial_concepts_v48": 5,
}

README = """DARWIN — Baseline v48.9 Stable
==============================

Esta baseline representa o marco estável da v48.9.

Linha pedagógica preservada:
- v48.0: encaixe físico por contorno, tamanho, profundidade e orientação;
- v48.1: rotação ativa;
- v48.2: erro exploratório controlado, recuo, memória do erro e evitação;
- v48.3.1: estratégia após erro com ordem auditável correta;
- v48.4: generalização de estratégia para múltiplos tipos de falha;
- v48.5: generalização por variação de IDs, medidas, tolerância e ângulo;
- v48.6: currículo explícito de medidas e ângulos;
- v48.7: transferência conceitual para novos problemas;
- v48.8: explicação causal contrastiva;
- v48.9: planejamento de ação em múltiplos passos.

Novo marco v48.9:
Darwin criou planos curtos, justificou cada etapa, executou passo a passo,
detectou uma falha oculta, revisou o plano e concluiu a tarefa com segurança.

Cenários validados:
- rotação seguida de inserção;
- seleção de buraco alternativo;
- rejeição segura por tamanho;
- inserção direta;
- falha oculta de profundidade seguida de revisão de plano.

Cadeia pedagógica v48.9:
tarefa nova → plano → justificativa por etapa → execução → observação → revisão se falhar → conclusão segura.

Regra:
NÃO editar esta baseline diretamente.
NÃO rodar experimentos dentro desta baseline.
Use-a apenas como ponto de retorno, auditoria e preservação histórica.

Próximo desenvolvimento sugerido:
começar v48.10/v49 a partir da pasta operacional atual, não desta baseline.

Direção natural:
v48.10 — planejamento hierárquico com metas e sub-metas.
Darwin deve separar objetivo final, subobjetivos, pré-condições, riscos e critérios de parada.
"""


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ps(kind: str, msg: str) -> None:
    print(f"[{kind:<7}] {msg}")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_payload(value: str) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    if table not in set(table_names(conn)):
        return None
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return None


def rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if table not in set(table_names(conn)):
        return []
    out = []
    for row in conn.execute(f"SELECT * FROM {table} ORDER BY id ASC").fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = parse_payload(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def has(rs: list[dict[str, Any]], action: str) -> bool:
    return any(r.get("action_kind") == action for r in rs)


def latest_done(rs: list[dict[str, Any]], action: str, outcome: str | None = None) -> str | None:
    done = []
    for r in rs:
        if r.get("action_kind") != action:
            continue
        if outcome is not None:
            if r.get("outcome") == outcome or r.get("observed_outcome") == outcome:
                done.append(r.get("scenario_id"))
        else:
            done.append(r.get("scenario_id"))
    if done:
        return str(done[-1])
    ids = [r.get("scenario_id") for r in rs if r.get("scenario_id")]
    return str(ids[-1]) if ids else None


def basic_ready(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    rs = rows(conn, table)
    counts = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "has_rotate_success": has(rs, "rotate_success"),
        "has_insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_2(conn: sqlite3.Connection) -> dict[str, Any]:
    rs = rows(conn, "geometry_live_actions_v48_2")
    counts = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "has_controlled_explore_choose": has(rs, "controlled_explore_choose"),
        "has_controlled_collision": has(rs, "controlled_collision"),
        "has_error_memory_write": has(rs, "error_memory_write"),
        "has_avoid_repeat": has(rs, "avoid_repeat"),
        "has_rotate_success": has(rs, "rotate_success"),
        "has_insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_3_1(conn: sqlite3.Connection) -> dict[str, Any]:
    rs = rows(conn, "geometry_live_actions_v48_3_1")
    counts = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "has_strategy_select": has(rs, "strategy_select"),
        "has_strategy_execute": has(rs, "strategy_execute"),
        "has_controlled_collision": has(rs, "controlled_collision"),
        "has_error_memory_write": has(rs, "error_memory_write"),
        "has_rotate_success": has(rs, "rotate_success"),
        "has_insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_4(conn: sqlite3.Connection) -> dict[str, Any]:
    rs = rows(conn, "geometry_live_actions_v48_4")
    counts = Counter(r.get("action_kind", "") for r in rs)
    notes = {str(r.get("note", "")) for r in rs if r.get("action_kind") == "strategy_select"}
    checks = {
        "has_rows": bool(rs),
        "try_alternate_hole": "try_alternate_hole" in notes,
        "reject_pair_size": "reject_pair_size" in notes,
        "reject_pair_depth": "reject_pair_depth" in notes,
        "cautious_exploration": "cautious_exploration" in notes,
        "rotate_piece": "rotate_piece" in notes,
        "rotate_success": has(rs, "rotate_success"),
        "insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_5(conn: sqlite3.Connection) -> dict[str, Any]:
    all_rows = rows(conn, "geometry_live_actions_v48_5")
    sid = latest_done(all_rows, "scenario_complete", "success")
    rs = [r for r in all_rows if r.get("scenario_id") == sid] if sid else []
    counts = Counter(r.get("action_kind", "") for r in rs)
    piece_ids = {r.get("piece_id") for r in rs if r.get("piece_id")}
    hole_ids = {r.get("hole_id") for r in rs if r.get("hole_id")}
    checks = {
        "has_rows": bool(rs),
        "scenario_complete": has(rs, "scenario_complete"),
        "randomized_ids": (
            len(piece_ids) >= 6
            and len(hole_ids) >= 3
            and all(str(x).startswith("object_") for x in piece_ids)
            and all(str(x).startswith("aperture_") for x in hole_ids)
        ),
        "strategy_count": sum(1 for r in rs if r.get("action_kind") == "strategy_select") >= 5,
        "rotate_success": has(rs, "rotate_success"),
        "insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"scenario_id": sid, "total": len(rs), "global_total": len(all_rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def learned(rs: list[dict[str, Any]], concept: str, relation: str, verdict: str, case_id: str) -> bool:
    for r in rs:
        if r.get("action_kind") != "concept_learned":
            continue
        if r.get("concept_key") != concept or r.get("case_id") != case_id:
            continue
        if r.get("relation") != relation or r.get("verdict") != verdict:
            continue
        if not r.get("payload", {}).get("passed_expectation", False):
            continue
        return True
    return False


def live_v48_6(conn: sqlite3.Connection) -> dict[str, Any]:
    all_rows = rows(conn, "geometry_measure_curriculum_v48_6")
    sid = latest_done(all_rows, "curriculum_complete")
    rs = [r for r in all_rows if r.get("scenario_id") == sid] if sid else []
    counts = Counter(r.get("action_kind", "") for r in rs)
    init = [r for r in rs if r.get("action_kind") == "curriculum_init"]
    values_varied = False
    if init:
        p = init[-1].get("payload", {})
        values_varied = (
            all(k in p for k in ["size_hole", "size_large", "depth_hole", "depth_deep", "angle", "minimal_rotation"])
            and p["size_large"] > p["size_hole"]
            and p["depth_deep"] > p["depth_hole"]
        )
    checks = {
        "has_rows": bool(rs),
        "curriculum_complete": has(rs, "curriculum_complete"),
        "measurement_values_varied": values_varied,
        "learned_larger_than": learned(rs, "larger_smaller", "larger_than", "reject_size", "case_size_larger"),
        "learned_tolerance": learned(rs, "tolerance", "within_tolerance", "accept", "case_size_tolerance"),
        "learned_deeper_than": learned(rs, "deep_shallow", "deeper_than", "reject_depth", "case_depth_deeper"),
        "learned_shallow_accept": learned(rs, "deep_shallow", "shallower_or_equal", "accept", "case_depth_shallow"),
        "learned_angle_rotation": learned(rs, "angle_rotation_minimum", "rotation_needed", "rotate", "case_angle_rotation"),
        "learned_shape_vs_orientation": learned(rs, "shape_vs_orientation", "same_shape_different_orientation", "rotate", "case_same_shape_orientation"),
        "learned_shape_vs_scale": learned(rs, "shape_vs_scale", "same_shape_different_scale", "compare_scale", "case_same_shape_scale"),
        "learned_different_shape": learned(rs, "shape_not_scale_or_orientation", "different_shape", "reject_shape", "case_different_shape"),
        "enough_concept_events": sum(1 for r in rs if r.get("action_kind") == "concept_learned") >= 8,
        "enough_compare_events": sum(1 for r in rs if r.get("action_kind") == "measure_compare") >= 8,
    }
    return {"scenario_id": sid, "total": len(rs), "global_total": len(all_rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def row_has(rs: list[dict[str, Any]], action: str | None = None, problem_id: str | None = None,
            task_id: str | None = None, relation: str | None = None, decision: str | None = None,
            primary: str | None = None, alt: str | None = None, outcome: str | None = None,
            step_kind: str | None = None, final_status: str | None = None,
            revision_id: int | None = None) -> bool:
    for r in rs:
        if action is not None and r.get("action_kind") != action:
            continue
        if problem_id is not None and r.get("problem_id") != problem_id:
            continue
        if task_id is not None and r.get("task_id") != task_id:
            continue
        if relation is not None and r.get("relation") != relation:
            continue
        if decision is not None and r.get("decision") != decision:
            continue
        if primary is not None and r.get("primary_contrast") != primary:
            continue
        if alt is not None and r.get("rejected_alternative") != alt:
            continue
        if outcome is not None and r.get("outcome") != outcome and r.get("observed_outcome") != outcome:
            continue
        if step_kind is not None and r.get("step_kind") != step_kind:
            continue
        if final_status is not None and r.get("final_status") != final_status:
            continue
        if revision_id is not None and int(r.get("revision_id", 0)) != revision_id:
            continue
        return True
    return False


def live_v48_7(conn: sqlite3.Connection) -> dict[str, Any]:
    all_rows = rows(conn, "geometry_concept_transfer_v48_7")
    sid = latest_done(all_rows, "transfer_complete", "success")
    rs = [r for r in all_rows if r.get("scenario_id") == sid] if sid else []
    counts = Counter(r.get("action_kind", "") for r in rs)
    problems = ["problem_oversize", "problem_tolerance", "problem_depth", "problem_rotation", "problem_shape"]
    checks = {
        "has_rows": bool(rs),
        "transfer_complete": row_has(rs, "transfer_complete", outcome="success"),
        "all_problems_presented": all(row_has(rs, "problem_present", problem_id=p) for p in problems),
        "all_have_recall": all(row_has(rs, "concept_recall", problem_id=p) for p in problems),
        "explanations": sum(1 for r in rs if r.get("action_kind") == "explanation_before_action") >= 5,
        "decisions": sum(1 for r in rs if r.get("action_kind") == "action_decide") >= 5,
        "executions": sum(1 for r in rs if r.get("action_kind") == "action_execute") >= 5,
    }
    return {"scenario_id": sid, "total": len(rs), "global_total": len(all_rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_8(conn: sqlite3.Connection) -> dict[str, Any]:
    all_rows = rows(conn, "geometry_contrastive_explanations_v48_8")
    sid = latest_done(all_rows, "contrastive_complete", "success")
    rs = [r for r in all_rows if r.get("scenario_id") == sid] if sid else []
    counts = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "contrastive_complete": row_has(rs, "contrastive_complete", outcome="success"),
        "contrastive_explanations": sum(1 for r in rs if r.get("action_kind") == "contrastive_explanation") >= 5,
        "alternative_rejections": sum(1 for r in rs if r.get("action_kind") == "alternative_rejected") >= 15,
        "action_decisions": sum(1 for r in rs if r.get("action_kind") == "action_decide") >= 5,
        "action_executions": sum(1 for r in rs if r.get("action_kind") == "action_execute") >= 5,
    }
    return {"scenario_id": sid, "total": len(rs), "global_total": len(all_rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def plan_steps(rs: list[dict[str, Any]], task_id: str, min_steps: int, action: str = "step_justify", revision_id: int = 0) -> bool:
    return sum(
        1 for r in rs
        if r.get("action_kind") == action and r.get("task_id") == task_id and int(r.get("revision_id", 0)) == revision_id
    ) >= min_steps


def live_v48_9(conn: sqlite3.Connection) -> dict[str, Any]:
    all_rows = rows(conn, "geometry_multistep_plans_v48_9")
    sid = latest_done(all_rows, "planning_complete", "success")
    rs = [r for r in all_rows if r.get("scenario_id") == sid] if sid else []
    counts = Counter(r.get("action_kind", "") for r in rs)

    tasks = ["task_rotate_insert", "task_alternate_shape", "task_reject_oversize", "task_direct_insert", "task_revision_hidden_depth"]

    checks = {
        "has_rows": bool(rs),
        "planning_complete": row_has(rs, "planning_complete", outcome="success"),
        "all_tasks_presented": all(row_has(rs, "task_present", task_id=t) for t in tasks),
        "all_tasks_have_plans": all(row_has(rs, "plan_create", task_id=t) for t in tasks),

        "rotate_plan_has_three_steps": plan_steps(rs, "task_rotate_insert", 3),
        "rotate_step_executed": row_has(rs, "step_execute", task_id="task_rotate_insert", step_kind="rotate_piece"),
        "rotate_inserted": row_has(rs, "step_observe", task_id="task_rotate_insert", step_kind="insert_primary", outcome="inserted"),
        "rotate_task_complete": row_has(rs, "task_complete", task_id="task_rotate_insert", final_status="inserted"),

        "alternate_plan_has_four_steps": plan_steps(rs, "task_alternate_shape", 4),
        "alternate_selected": row_has(rs, "step_observe", task_id="task_alternate_shape", step_kind="select_alternate_hole", outcome="alternate_selected"),
        "alternate_inserted": row_has(rs, "step_observe", task_id="task_alternate_shape", step_kind="insert_alternate", outcome="inserted"),
        "alternate_task_complete": row_has(rs, "task_complete", task_id="task_alternate_shape", final_status="inserted"),

        "oversize_plan_rejects": row_has(rs, "step_observe", task_id="task_reject_oversize", step_kind="safe_reject_size", outcome="rejected_size"),
        "oversize_task_complete": row_has(rs, "task_complete", task_id="task_reject_oversize", final_status="rejected_size"),

        "direct_plan_has_two_steps": plan_steps(rs, "task_direct_insert", 2),
        "direct_inserted": row_has(rs, "step_observe", task_id="task_direct_insert", step_kind="insert_primary", outcome="inserted"),
        "direct_task_complete": row_has(rs, "task_complete", task_id="task_direct_insert", final_status="inserted"),

        "revision_failure_detected": row_has(rs, "plan_failure_detected", task_id="task_revision_hidden_depth", outcome="hidden_depth_failure"),
        "revision_plan_created": row_has(rs, "plan_revise", task_id="task_revision_hidden_depth", revision_id=1),
        "revision_has_steps": plan_steps(rs, "task_revision_hidden_depth", 3, "revision_step_justify", 1),
        "revision_rejects_depth": row_has(rs, "step_observe", task_id="task_revision_hidden_depth", step_kind="safe_reject", outcome="rejected_depth", revision_id=1),
        "revision_task_complete": row_has(rs, "task_complete", task_id="task_revision_hidden_depth", final_status="rejected_depth_after_revision"),

        "source_v48_8_available": any(
            r.get("action_kind") == "planning_init"
            and r.get("payload", {}).get("source_table") == "geometry_contrastive_explanations_v48_8"
            and r.get("payload", {}).get("source_status", {}).get("available") is True
            for r in rs
        ),
    }

    return {"scenario_id": sid, "total": len(rs), "global_total": len(all_rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def sqlite_summary(db_path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "not_found",
        "tables": {},
        "v47_clean": False,
        "v48_geometry_ready": False,
        "v48_1_live_rotation_ready": False,
        "v48_2_controlled_error_ready": False,
        "v48_3_1_strategy_ready": False,
        "v48_4_strategy_generalization_ready": False,
        "v48_5_variation_generalization_ready": False,
        "v48_6_measure_angle_curriculum_ready": False,
        "v48_7_concept_transfer_ready": False,
        "v48_8_contrastive_explanation_ready": False,
        "v48_9_multistep_planning_ready": False,
        "baseline_ready": False,
        "baseline_warnings": [],
    }

    if not db_path.exists():
        return summary

    summary["status"] = "ok"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        for name in table_names(conn):
            summary["tables"][name] = table_count(conn, name)

        warnings = []

        for table in V47_ZERO:
            n = summary["tables"].get(table, 0)
            if n not in (0, None):
                warnings.append(f"v47_not_clean:{table}={n}")

        for table, minimum in V48_MIN.items():
            n = summary["tables"].get(table, 0)
            if n is None or int(n) < minimum:
                warnings.append(f"v48_missing_or_low:{table}={n}, expected>={minimum}")

        live1 = basic_ready(conn, "geometry_live_actions_v48_1")
        live2 = live_v48_2(conn)
        live31 = live_v48_3_1(conn)
        live4 = live_v48_4(conn)
        live5 = live_v48_5(conn)
        live6 = live_v48_6(conn)
        live7 = live_v48_7(conn)
        live8 = live_v48_8(conn)
        live9 = live_v48_9(conn)

        summary["live_v48_1_summary"] = live1
        summary["live_v48_2_summary"] = live2
        summary["live_v48_3_1_summary"] = live31
        summary["live_v48_4_summary"] = live4
        summary["live_v48_5_summary"] = live5
        summary["live_v48_6_summary"] = live6
        summary["live_v48_7_summary"] = live7
        summary["live_v48_8_summary"] = live8
        summary["live_v48_9_summary"] = live9

        checks = [
            ("v48_1_live_rotation_ready", "v48_1_live_rotation_not_ready", live1),
            ("v48_2_controlled_error_ready", "v48_2_controlled_error_not_ready", live2),
            ("v48_3_1_strategy_ready", "v48_3_1_strategy_not_ready", live31),
            ("v48_4_strategy_generalization_ready", "v48_4_strategy_generalization_not_ready", live4),
            ("v48_5_variation_generalization_ready", "v48_5_variation_generalization_not_ready", live5),
            ("v48_6_measure_angle_curriculum_ready", "v48_6_measure_angle_curriculum_not_ready", live6),
            ("v48_7_concept_transfer_ready", "v48_7_concept_transfer_not_ready", live7),
            ("v48_8_contrastive_explanation_ready", "v48_8_contrastive_explanation_not_ready", live8),
            ("v48_9_multistep_planning_ready", "v48_9_multistep_planning_not_ready", live9),
        ]

        for flag, warning, live in checks:
            summary[flag] = bool(live.get("ready"))
            if not live.get("ready"):
                warnings.append(warning)

        summary["v47_clean"] = not any(w.startswith("v47_not_clean:") for w in warnings)
        summary["v48_geometry_ready"] = not any(w.startswith("v48_missing_or_low:") for w in warnings)
        summary["baseline_ready"] = all(summary[k] for k in [
            "v47_clean",
            "v48_geometry_ready",
            "v48_1_live_rotation_ready",
            "v48_2_controlled_error_ready",
            "v48_3_1_strategy_ready",
            "v48_4_strategy_generalization_ready",
            "v48_5_variation_generalization_ready",
            "v48_6_measure_angle_curriculum_ready",
            "v48_7_concept_transfer_ready",
            "v48_8_contrastive_explanation_ready",
            "v48_9_multistep_planning_ready",
        ])
        summary["baseline_warnings"] = warnings

    finally:
        conn.close()

    return summary


def copy_file(src: Path, dst: Path, dry: bool, manifest: dict[str, Any], label: str = "") -> None:
    rel = src.relative_to(ROOT)
    if not src.exists():
        ps("AUSENTE", str(rel))
        manifest["missing"].append(str(rel))
        return

    if dry:
        ps("DRYRUN", f"copiaria {rel}")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    item = {"source": str(src), "dest": str(dst), "size": src.stat().st_size, "sha256": sha(src)}
    if label:
        item["label"] = label
    manifest["files"].append(item)
    ps("OK", str(rel))


def copy_dir(src: Path, dst: Path, dry: bool, manifest: dict[str, Any], include_logs: bool = False) -> None:
    rel = src.relative_to(ROOT)
    if not src.exists():
        ps("AUSENTE", str(rel))
        manifest["missing"].append(str(rel))
        return

    if not src.is_dir():
        copy_file(src, dst, dry, manifest)
        return

    if rel.as_posix().endswith("logs") and not include_logs:
        ps("PULOU", f"{rel} (use --include-logs para incluir)")
        return

    if dry:
        n = sum(1 for p in src.rglob("*") if p.is_file())
        ps("DRYRUN", f"copiaria diretório {rel} -> {n} arquivo(s)")
        return

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    n = sum(1 for p in dst.rglob("*") if p.is_file())
    manifest["directories"].append({"source": str(src), "dest": str(dst), "files": n})
    ps("DIR", f"{rel} -> {n} arquivo(s)")


def ensure_project_root() -> None:
    missing = [f for f in REQ if not (ROOT / f).exists()]
    if not (HOME / "darwin.db").exists():
        missing.append("darwin_home/darwin.db")

    if missing:
        raise FileNotFoundError(
            "Arquivos essenciais ausentes:\n"
            + "\n".join(f"- {x}" for x in missing)
            + "\n\nRode este script dentro da pasta darwin_local."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela baseline estável Darwin v48.9.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-logs", action="store_true")
    args = parser.parse_args()

    ensure_project_root()

    bdir = BASELINES / f"baseline_v48_9_stable_{stamp()}"
    srcdir = bdir / "source_files"
    homedir = bdir / "darwin_home"

    manifest: dict[str, Any] = {
        "baseline": "v48.9_stable",
        "project_root": str(ROOT),
        "baseline_dir": str(bdir),
        "files": [],
        "directories": [],
        "missing": [],
        "created_at": iso(),
        "sqlite_summary": {},
    }

    print("=" * 72)
    print("DARWIN — FREEZE BASELINE v48.9 STABLE")
    print("=" * 72)
    print(f"Raiz do projeto: {ROOT}")
    print(f"Destino:         {bdir}")
    print(f"Dry-run:         {args.dry_run}")
    print()

    print("Arquivos essenciais:")
    for filename in REQ:
        copy_file(ROOT / filename, srcdir / filename, args.dry_run, manifest, "required")

    print()
    print("Arquivos opcionais:")
    for filename in OPT:
        if (ROOT / filename).exists():
            copy_file(ROOT / filename, srcdir / filename, args.dry_run, manifest, "optional")
        else:
            ps("AUSENTE", filename)

    print()
    print("darwin_home/")
    for item in ["darwin.db", "snapshots", "exports", "backups"]:
        src = HOME / item
        dst = homedir / item
        if src.is_dir():
            copy_dir(src, dst, args.dry_run, manifest, args.include_logs)
        else:
            copy_file(src, dst, args.dry_run, manifest)

    logs = HOME / "logs"
    if logs.exists():
        copy_dir(logs, homedir / "logs", args.dry_run, manifest, args.include_logs)

    manifest["sqlite_summary"] = sqlite_summary(HOME / "darwin.db")

    if args.dry_run:
        ps("DRYRUN", "criaria README_BASELINE.txt e manifest.json")
        ps("DRYRUN", f"criaria ZIP: {bdir.with_suffix('.zip')}")
    else:
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "README_BASELINE.txt").write_text(README, encoding="utf-8")
        (bdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        ps("OK", "README_BASELINE.txt")
        ps("OK", "manifest.json")

        zip_path = bdir.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        shutil.make_archive(str(bdir), "zip", root_dir=bdir)
        print()
        print(f"ZIP criado: {zip_path}")

    summary = manifest["sqlite_summary"]
    live9 = summary.get("live_v48_9_summary", {})

    print()
    print("Resumo SQLite:")
    for key in [
        "status",
        "v47_clean",
        "v48_geometry_ready",
        "v48_1_live_rotation_ready",
        "v48_2_controlled_error_ready",
        "v48_3_1_strategy_ready",
        "v48_4_strategy_generalization_ready",
        "v48_5_variation_generalization_ready",
        "v48_6_measure_angle_curriculum_ready",
        "v48_7_concept_transfer_ready",
        "v48_8_contrastive_explanation_ready",
        "v48_9_multistep_planning_ready",
        "baseline_ready",
    ]:
        print(f"- {key}: {summary.get(key)}")

    print(f"- v48_9_scenario_id: {live9.get('scenario_id')}")
    print(f"- v48_9_scenario_events_total: {live9.get('total')}")
    print(f"- v48_9_global_events_total: {live9.get('global_total')}")
    print(f"- v48_9_action_counts: {live9.get('counts')}")

    warnings = summary.get("baseline_warnings") or []
    if warnings:
        print("- baseline_warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if not args.dry_run:
        important_tables = (
            V47_ZERO
            + list(V48_MIN.keys())
            + [
                "geometry_live_actions_v48_1",
                "geometry_live_actions_v48_2",
                "geometry_live_actions_v48_3_1",
                "geometry_live_actions_v48_4",
                "geometry_live_actions_v48_5",
                "geometry_measure_curriculum_v48_6",
                "geometry_concept_transfer_v48_7",
                "geometry_contrastive_explanations_v48_8",
                "geometry_multistep_plans_v48_9",
            ]
        )
        for table in important_tables:
            print(f"- table:{table}: {summary.get('tables', {}).get(table)}")

        print()
        print(f"Baseline v48.9 congelada com sucesso em: {bdir}")
        print(f"Pacote ZIP: {bdir.with_suffix('.zip')}")
        if warnings:
            print("ATENÇÃO: baseline tem avisos. Verifique antes de tratar como stable.")
        else:
            print("Baseline OK: v47 limpo, v48 pedagógico preservado e v48.9 planejamento multi-etapas registrado.")
        print("Próximo passo: iniciar v48.10/v49 a partir da pasta operacional atual, não desta baseline.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
