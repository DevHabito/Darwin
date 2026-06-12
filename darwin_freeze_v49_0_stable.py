from __future__ import annotations

"""
DARWIN - Freeze Baseline v49.0 Stable

Congela o estado atual depois do Brain Core v49.0.

Uso:
    py darwin_freeze_v49_0_stable.py --dry-run
    py darwin_freeze_v49_0_stable.py

Opcional:
    py darwin_freeze_v49_0_stable.py --include-logs
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
HOME = ROOT / "darwin_home"
DB = HOME / "darwin.db"
BASELINES = ROOT / "baselines"

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
    "darwin_brain_core_v49_0.py",
    "darwin_check_v49_0_brain_core.py",
    "darwin_freeze_v49_0_stable.py",
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
    "darwin_freeze_v48_9_stable.py",
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
    "geometry_live_actions_v48_1": 18,
    "geometry_live_actions_v48_2": 17,
    "geometry_live_actions_v48_3_1": 17,
    "geometry_live_actions_v48_4": 34,
    "geometry_live_actions_v48_5": 35,
    "geometry_measure_curriculum_v48_6": 26,
    "geometry_concept_transfer_v48_7": 28,
    "geometry_contrastive_explanations_v48_8": 42,
    SOURCE_V48_9: 67,
}

README = """DARWIN - Baseline v49.0 Stable
================================

Esta baseline representa o marco estavel da v49.0: Brain Core operacional
no notebook, sem corpo fisico, robotica, camera, microfone ou atuadores reais.

Marco v49.0:
- loop cognitivo unico e auditavel;
- percepcao por eventos internos do darwin.db;
- atencao com selecao de foco;
- memoria de trabalho curta com limite 7 e decaimento por ciclo;
- RZS/Romero como regulador obrigatorio;
- acoes cognitivas internas;
- replay e consolidacao;
- checker headless para auditoria.

Loop validado:
cycle_start -> perceive_internal_events -> attention_select ->
working_memory_update -> rzs_assess -> cognitive_action_select ->
cognitive_action_execute -> replay_or_consolidate -> cycle_complete.

Regra:
NAO editar esta baseline diretamente.
NAO rodar experimentos dentro desta baseline.
Use-a apenas como ponto de retorno, auditoria e preservacao historica.

Nota cientifica:
A v49.0 nao afirma consciencia. Ela cria o primeiro cerebro operacional
integrado e verificavel do Darwin, com regulacao relacional explicita.
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


def parse_payload(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    if table not in table_names(conn):
        return None
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return None


def table_count_max(conn: sqlite3.Connection, table: str) -> tuple[int, int]:
    if table not in table_names(conn):
        return 0, 0
    row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
    return int(row["n"]), int(row["max_id"])


def rows(conn: sqlite3.Connection, table: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
    if table not in table_names(conn):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if scenario_id is not None:
        where = " WHERE scenario_id=?"
        params = (scenario_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = parse_payload(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_brain_scenario(cycle_rows: list[dict[str, Any]]) -> str | None:
    done = [
        str(r.get("scenario_id"))
        for r in cycle_rows
        if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if done:
        return done[-1]
    ids = [str(r.get("scenario_id")) for r in cycle_rows if r.get("scenario_id")]
    return ids[-1] if ids else None


def phase_order_ok(cycle_rows: list[dict[str, Any]]) -> bool:
    by_cycle: dict[int, list[str]] = defaultdict(list)
    for row in cycle_rows:
        by_cycle[int(row["cycle_id"])].append(str(row["phase"]))
    return bool(by_cycle) and all(phases == PHASES for phases in by_cycle.values())


def brain_v49_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    all_cycles = rows(conn, CYCLES_TABLE)
    scenario_id = latest_brain_scenario(all_cycles)
    cycle_rows = [r for r in all_cycles if r.get("scenario_id") == scenario_id] if scenario_id else []
    wm_rows = rows(conn, WM_TABLE, scenario_id)
    att_rows = rows(conn, ATT_TABLE, scenario_id)
    replay_rows = rows(conn, REPLAY_TABLE, scenario_id)

    completed = sorted({int(r["cycle_id"]) for r in cycle_rows if r.get("phase") == "cycle_complete"})
    sources: set[str] = set()
    for row in cycle_rows:
        if row.get("phase") == "perceive_internal_events":
            sources.update(str(x) for x in row.get("payload", {}).get("sources", []))

    decisions = {str(r.get("rzs_decision") or "") for r in cycle_rows if r.get("phase") == "rzs_assess"}
    wm_per_cycle = Counter(int(r["cycle_id"]) for r in wm_rows)
    demanded = {
        int(r["cycle_id"])
        for r in cycle_rows
        if r.get("phase") == "rzs_assess" and r.get("payload", {}).get("stability_demanded") is True
    }
    stability_actions = {
        int(r["cycle_id"])
        for r in cycle_rows
        if r.get("phase") == "cognitive_action_execute"
        and str(r.get("cognitive_action")) in {"consolidate", "pause_for_stability"}
    }
    final_payloads = [
        r.get("payload", {})
        for r in cycle_rows
        if r.get("phase") == "cycle_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    final_payload = final_payloads[-1] if final_payloads else {}
    v48_count, v48_max = table_count_max(conn, SOURCE_V48_9)

    checks = {
        "has_scenario": bool(scenario_id),
        "scenario_complete": final_payload.get("scenario_complete") is True,
        "min_12_cycles": len(completed) >= 12,
        "ordered_phases": phase_order_ok(cycle_rows),
        "internal_perception": {"episodes", "semantic_memory", "state_history", SOURCE_V48_9}.issubset(sources),
        "attention": bool(att_rows) and all(str(r.get("focus_key") or "") for r in att_rows),
        "working_memory": bool(wm_rows) and bool(wm_per_cycle) and max(wm_per_cycle.values()) <= 7,
        "working_memory_decay": any(r.get("payload", {}).get("decayed") is True for r in wm_rows),
        "rzs_influence": any(x not in {"", "continue"} for x in decisions),
        "replay": bool(replay_rows),
        "consolidation": bool(demanded) and demanded.issubset(stability_actions),
        "v48_9_unchanged": (
            bool(final_payload)
            and final_payload.get("v48_9_count_before") == final_payload.get("v48_9_count_after") == v48_count
            and final_payload.get("v48_9_max_before") == final_payload.get("v48_9_max_after") == v48_max
        ),
    }
    return {
        "ready": all(checks.values()),
        "scenario_id": scenario_id,
        "checks": checks,
        "cycles": len(completed),
        "cycle_events": len(cycle_rows),
        "working_memory_events": len(wm_rows),
        "attention_events": len(att_rows),
        "replay_events": len(replay_rows),
        "sources": sorted(sources),
        "decisions": sorted(x for x in decisions if x),
    }


def sqlite_summary() -> dict[str, Any]:
    if not DB.exists():
        return {"ok": False, "error": f"missing database: {DB}"}

    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables = table_names(conn)
        counts = {name: table_count(conn, name) for name in sorted(tables)}
        v47_clean = all((table_count(conn, t) in (0, None)) for t in V47_ZERO)
        v48_checks = {table: (table_count(conn, table) or 0) >= minimum for table, minimum in V48_MIN.items()}
        v49 = brain_v49_ready(conn)

    prior_ready = v47_clean and all(v48_checks.values())
    baseline_ready = prior_ready and v49["ready"]
    return {
        "ok": True,
        "database": str(DB),
        "tables": sorted(tables),
        "counts": counts,
        "v47_clean": v47_clean,
        "v48_checks": v48_checks,
        "v48_chain_ready": prior_ready,
        "v49_brain_core": v49,
        "baseline_ready": baseline_ready,
    }


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_dir(src: Path, dst: Path, include_logs: bool) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        blocked = {"__pycache__"}
        if not include_logs:
            blocked.update({n for n in names if n.lower().endswith((".log", ".tmp"))})
        return blocked.intersection(names)

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def ensure_project_root() -> None:
    missing = [name for name in REQ if not (ROOT / name).exists()]
    if missing:
        raise FileNotFoundError("Arquivos obrigatorios ausentes: " + ", ".join(missing))
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin ausente: {DB}")


def build_manifest(summary: dict[str, Any], files: list[str], baseline_name: str, zip_path: Path | None) -> dict[str, Any]:
    return {
        "baseline": "v49.0_stable",
        "baseline_name": baseline_name,
        "created_at_utc": iso(),
        "description": "Darwin Brain Core v49.0 operacional no notebook.",
        "scope": {
            "body": False,
            "robotics": False,
            "camera": False,
            "microphone": False,
            "real_actuators": False,
            "stdlib_only": True,
            "sqlite_truth_source": True,
        },
        "required_files": REQ,
        "optional_files_found": [name for name in OPT if (ROOT / name).exists()],
        "files_sha256": files,
        "sqlite_summary": summary,
        "baseline_ready": bool(summary.get("baseline_ready")),
        "zip": str(zip_path) if zip_path else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-logs", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN - FREEZE BASELINE v49.0 STABLE")
    print("=" * 72)

    ensure_project_root()
    summary = sqlite_summary()
    v49 = summary.get("v49_brain_core", {})

    ps("DB", str(DB))
    ps("READY", f"v48_chain_ready={summary.get('v48_chain_ready')} v49_ready={v49.get('ready')}")
    ps("BRAIN", f"scenario={v49.get('scenario_id')} cycles={v49.get('cycles')} replay={v49.get('replay_events')}")

    if not summary.get("baseline_ready"):
        ps("ERRO", "Baseline v49.0 ainda nao esta pronta. Rode o Brain Core e o checker ate Resultado final: OK.")
        for key, value in v49.get("checks", {}).items():
            ps("CHECK", f"{key}={'OK' if value else 'FALHOU'}")
        return 2

    files = []
    for name in REQ + [x for x in OPT if (ROOT / x).exists()]:
        path = ROOT / name
        if path.exists():
            files.append({"path": name, "sha256": sha(path), "bytes": path.stat().st_size})

    baseline_name = f"baseline_v49_0_stable_{stamp()}"
    bdir = BASELINES / baseline_name
    zip_path = BASELINES / f"{baseline_name}.zip"
    manifest = build_manifest(summary, files, baseline_name, zip_path if not args.dry_run else None)

    if args.dry_run:
        ps("DRYRUN", f"criaria {bdir}")
        ps("DRYRUN", f"criaria {zip_path}")
        ps("OK", "Dry-run concluido; nenhum arquivo foi copiado.")
        print(f"baseline_ready: {manifest['baseline_ready']}")
        return 0

    if bdir.exists() or zip_path.exists():
        raise FileExistsError(f"Baseline ja existe: {bdir} ou {zip_path}")

    (bdir / "source_files").mkdir(parents=True, exist_ok=True)
    for item in files:
        copy_file(ROOT / str(item["path"]), bdir / "source_files" / str(item["path"]))

    copy_dir(HOME, bdir / "darwin_home", include_logs=args.include_logs)
    (bdir / "README.txt").write_text(README, encoding="utf-8")
    (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    shutil.make_archive(str(zip_path.with_suffix("")), "zip", BASELINES, baseline_name)

    ps("OK", f"Baseline criada: {bdir}")
    ps("OK", f"Arquivo zip: {zip_path}")
    print(f"baseline_ready: {manifest['baseline_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
