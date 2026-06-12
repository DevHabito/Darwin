from __future__ import annotations

"""
DARWIN — Freeze Baseline v48.5 Stable

Congela o estado atual depois da generalização por variação v48.5.

Esta baseline preserva:
- v48.0: encaixe físico;
- v48.1: rotação ativa;
- v48.2: erro controlado;
- v48.3.1: estratégia após erro com ordem auditável;
- v48.4: generalização por tipo de falha;
- v48.5: generalização por variação de IDs, medidas, tolerância e ângulo.

NÃO zera tabelas geometry_* nem geometry_live_actions_*.
Elas são memória pedagógica física e evidência operacional.

Uso:
    py darwin_freeze_v48_5_stable.py --dry-run
    py darwin_freeze_v48_5_stable.py

Opcional:
    py darwin_freeze_v48_5_stable.py --include-logs
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


PROJECT_ROOT = Path.cwd()
DARWIN_HOME = PROJECT_ROOT / "darwin_home"
BASELINES_DIR = PROJECT_ROOT / "baselines"

REQUIRED_FILES = [
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
]

OPTIONAL_FILES = [
    "darwin_check_v47_tensions.py",
    "darwin_tension_dashboard_v47.py",
    "darwin_sleep_auto_guard.py",
    "darwin_sleep_consolidation.py",

    "darwin_repair_v47_8_resolution_policy.py",
    "darwin_repair_v47_8_1_resolution_policy.py",
    "darwin_v47_8_resolution_policy_test.py",

    "darwin_patch_v47_9_compare_context_operator.py",
    "darwin_repair_v47_9_1_compare_context.py",
    "darwin_v47_9_compare_context_operator_test.py",

    "darwin_patch_v47_10_prediction_influence.py",
    "darwin_v47_10_prediction_influence_test.py",

    "darwin_patch_v47_11_hypothesis_lineage.py",
    "darwin_v47_11_hypothesis_lineage_test.py",

    "darwin_repair_v47_12_1_cycle_report.py",
    "darwin_v47_12_cycle_report_test.py",

    "darwin_patch_v47_13_cycle_memory_review.py",
    "darwin_v47_13_cycle_memory_review_test.py",

    "darwin_shape_sorter_live_v48_1.py",
    "darwin_shape_sorter_live_v48_1_active_rotation.py",
    "darwin_shape_sorter_live_v48_2_controlled_error.py",
    "darwin_shape_sorter_live_v48_3_strategy_after_error.py",
    "darwin_check_v48_3_strategy_after_error.py",
    "darwin_shape_sorter_live_v48_3_1_strategy_after_error.py",
    "darwin_shape_sorter_live_v48_4_strategy_generalization.py",
    "darwin_shape_sorter_live_v48_5_variation_generalization.py",
]

HOME_ITEMS = [
    "darwin.db",
    "snapshots",
    "exports",
    "backups",
]

V47_CLEAN_TABLES = [
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

V48_MIN_COUNTS = {
    "geometry_shapes_v48": 3,
    "geometry_pieces_v48": 6,
    "geometry_holes_v48": 3,
    "geometry_fit_attempts_v48": 27,
    "geometry_rules_v48": 3,
    "geometry_spatial_concepts_v48": 5,
}

README_TEXT = """DARWIN — Baseline v48.5 Stable
==============================

Esta baseline representa o marco estável da v48.5.

Linha pedagógica preservada:
- v48.0: encaixe físico por contorno, tamanho, profundidade e orientação;
- v48.1: rotação ativa;
- v48.2: erro exploratório controlado, recuo, memória do erro e evitação;
- v48.3.1: estratégia após erro com ordem auditável correta;
- v48.4: generalização de estratégia para múltiplos tipos de falha;
- v48.5: generalização por variação.

Novo marco v48.5:
Darwin demonstrou que a política não depende de nomes fixos como piece_triangle
ou hole_square. O cenário usa IDs variáveis, medidas variáveis, tolerância variável
e ângulo variável. A validação é feita por papéis e propriedades:

- valid_triangle + target_square: contour_mismatch → try_alternate_hole;
- oversize_circle + target_circle: size_mismatch → reject_pair_size;
- deep_square + target_square: depth_mismatch → reject_pair_depth;
- unknown_piece + target_circle: uncertain_failure → cautious_exploration;
- rotated_square + target_square: rotation_mismatch → rotate_piece.

Cadeia pedagógica v48.5:
variação de ambiente → avaliação por propriedades → classificação da falha
→ seleção de estratégia → execução → resolução ou rejeição segura.

Regra:
NÃO editar esta baseline diretamente.
NÃO rodar experimentos dentro desta baseline.
Use-a apenas como ponto de retorno, auditoria e preservação histórica.

Observação:
As tabelas geometry_*_v48 e geometry_live_actions_* NÃO são zeradas.
Elas representam memória pedagógica física e evidência operacional.

Próximo desenvolvimento sugerido:
começar v48.6 a partir da pasta operacional atual, não desta baseline.

Direção natural:
v48.6 — currículo de medidas e ângulos.
Darwin deve aprender explicitamente:
- maior/menor;
- largo/estreito;
- profundo/raso;
- tolerância;
- ângulo;
- rotação mínima necessária;
- diferença entre forma, orientação e escala.
"""


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def print_status(kind: str, message: str) -> None:
    print(f"[{kind:<7}] {message}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_project_root() -> None:
    missing = []
    for filename in REQUIRED_FILES:
        if not (PROJECT_ROOT / filename).exists():
            missing.append(filename)

    if not (DARWIN_HOME / "darwin.db").exists():
        missing.append("darwin_home/darwin.db")

    if missing:
        raise FileNotFoundError(
            "Arquivos essenciais não encontrados na pasta atual:\n"
            + "\n".join(f"- {x}" for x in missing)
            + "\n\nRode este script dentro da pasta darwin_local."
        )


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [str(name) for (name,) in rows]


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    if table not in set(table_names(conn)):
        return None
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return None


def parse_payload(value: str) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def live_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if table not in set(table_names(conn)):
        return []

    rows = conn.execute(f"SELECT * FROM {table} ORDER BY id ASC").fetchall()
    out = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        item["payload"] = parse_payload(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def has_event(rows: list[dict[str, Any]], action: str | None = None, piece_role: str | None = None,
              hole_role: str | None = None, failure_reason: str | None = None,
              recommendation: str | None = None, note_contains: str | None = None) -> bool:
    for row in rows:
        if action is not None and row.get("action_kind") != action:
            continue
        if piece_role is not None and row.get("piece_role") != piece_role:
            continue
        if hole_role is not None and row.get("hole_role") != hole_role:
            continue
        if failure_reason is not None and row.get("failure_reason") != failure_reason:
            continue
        if recommendation is not None and row.get("recommendation") != recommendation:
            continue
        if note_contains is not None and note_contains not in str(row.get("note", "")):
            continue
        return True
    return False


def legacy_ready(conn: sqlite3.Connection, table: str, checks: dict[str, tuple]) -> dict[str, Any]:
    rows = live_rows(conn, table)
    counts = Counter(row.get("action_kind", "") for row in rows)
    result = {"has_rows": bool(rows)}
    for key, args in checks.items():
        result[key] = has_event(rows, *args)
    return {"total": len(rows), "counts": dict(counts), "checks": result, "ready": all(result.values())}


def live_v48_1_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, "geometry_live_actions_v48_1")
    counts = Counter(row.get("action_kind", "") for row in rows)
    checks = {
        "has_rows": bool(rows),
        "has_rotate_success": any(row.get("action_kind") == "rotate_success" for row in rows),
        "has_insert_success": sum(1 for row in rows if row.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_2_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, "geometry_live_actions_v48_2")
    counts = Counter(row.get("action_kind", "") for row in rows)
    checks = {
        "has_rows": bool(rows),
        "has_controlled_explore_choose": any(row.get("action_kind") == "controlled_explore_choose" for row in rows),
        "has_controlled_collision": any(row.get("action_kind") == "controlled_collision" for row in rows),
        "has_error_memory_write": any(row.get("action_kind") == "error_memory_write" for row in rows),
        "has_avoid_repeat": any(row.get("action_kind") == "avoid_repeat" for row in rows),
        "has_rotate_success": any(row.get("action_kind") == "rotate_success" for row in rows),
        "has_insert_success": sum(1 for row in rows if row.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_3_1_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, "geometry_live_actions_v48_3_1")
    counts = Counter(row.get("action_kind", "") for row in rows)
    checks = {
        "has_rows": bool(rows),
        "has_strategy_select": any(row.get("action_kind") == "strategy_select" for row in rows),
        "has_strategy_execute": any(row.get("action_kind") == "strategy_execute" for row in rows),
        "has_controlled_collision": any(row.get("action_kind") == "controlled_collision" for row in rows),
        "has_error_memory_write": any(row.get("action_kind") == "error_memory_write" for row in rows),
        "has_rotate_success": any(row.get("action_kind") == "rotate_success" for row in rows),
        "has_insert_success": sum(1 for row in rows if row.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_4_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, "geometry_live_actions_v48_4")
    counts = Counter(row.get("action_kind", "") for row in rows)
    checks = {
        "has_rows": bool(rows),
        "contour_strategy": any(row.get("action_kind") == "strategy_select" and row.get("note") == "try_alternate_hole" for row in rows),
        "size_strategy": any(row.get("action_kind") == "strategy_select" and row.get("note") == "reject_pair_size" for row in rows),
        "depth_strategy": any(row.get("action_kind") == "strategy_select" and row.get("note") == "reject_pair_depth" for row in rows),
        "uncertain_strategy": any(row.get("action_kind") == "strategy_select" and row.get("note") == "cautious_exploration" for row in rows),
        "rotation_strategy": any(row.get("action_kind") == "strategy_select" and row.get("note") == "rotate_piece" for row in rows),
        "rotate_success": any(row.get("action_kind") == "rotate_success" for row in rows),
        "insert_success": sum(1 for row in rows if row.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def latest_v48_5_scenario(rows: list[dict[str, Any]]) -> str | None:
    completed = [row.get("scenario_id") for row in rows if row.get("action_kind") == "scenario_complete" and row.get("outcome") == "success"]
    if completed:
        return str(completed[-1])
    ids = [row.get("scenario_id") for row in rows if row.get("scenario_id")]
    return str(ids[-1]) if ids else None


def live_v48_5_ready(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, "geometry_live_actions_v48_5")
    scenario_id = latest_v48_5_scenario(rows)
    scenario_rows = [row for row in rows if row.get("scenario_id") == scenario_id] if scenario_id else []
    counts = Counter(row.get("action_kind", "") for row in scenario_rows)

    piece_ids = {row.get("piece_id") for row in scenario_rows if row.get("piece_id")}
    hole_ids = {row.get("hole_id") for row in scenario_rows if row.get("hole_id")}
    randomized_ids = (
        len(piece_ids) >= 6
        and len(hole_ids) >= 3
        and all(str(pid).startswith("object_") for pid in piece_ids)
        and all(str(hid).startswith("aperture_") for hid in hole_ids)
    )

    init_rows = [row for row in scenario_rows if row.get("action_kind") == "scenario_init"]
    measurements_varied = False
    if init_rows:
        payload = init_rows[-1].get("payload", {})
        required = ["square_size", "triangle_size", "circle_size", "base_depth", "tolerance", "bad_angle"]
        measurements_varied = all(k in payload for k in required) and payload.get("bad_angle") not in (0, 45)

    checks = {
        "has_rows": bool(scenario_rows),
        "scenario_complete": any(row.get("action_kind") == "scenario_complete" and row.get("outcome") == "success" for row in scenario_rows),
        "randomized_ids": randomized_ids,
        "measurements_varied": measurements_varied,

        "contour_strategy": has_event(scenario_rows, "strategy_select", "valid_triangle", "target_square", "contour_mismatch", "try_alternate_hole"),
        "contour_alternate_target": has_event(scenario_rows, "strategy_execute_alternate_target", "valid_triangle", "target_triangle", recommendation="try_alternate_hole"),
        "triangle_success": has_event(scenario_rows, "insert_success", "valid_triangle", "target_triangle"),

        "size_strategy": has_event(scenario_rows, "strategy_select", "oversize_circle", "target_circle", "size_mismatch", "reject_pair_size"),
        "size_outcome": has_event(scenario_rows, "strategy_outcome", "oversize_circle", "target_circle", "size_mismatch", "reject_pair_size"),

        "depth_strategy": has_event(scenario_rows, "strategy_select", "deep_square", "target_square", "depth_mismatch", "reject_pair_depth"),
        "depth_outcome": has_event(scenario_rows, "strategy_outcome", "deep_square", "target_square", "depth_mismatch", "reject_pair_depth"),

        "uncertain_strategy": has_event(scenario_rows, "strategy_select", "unknown_piece", "target_circle", "uncertain_failure", "cautious_exploration"),
        "uncertain_outcome": has_event(scenario_rows, "strategy_outcome", "unknown_piece", "target_circle", "uncertain_failure", "cautious_exploration"),

        "rotation_strategy": has_event(scenario_rows, "strategy_select", "rotated_square", "target_square", "rotation_mismatch", "rotate_piece"),
        "rotation_execute": has_event(scenario_rows, "strategy_execute", "rotated_square", "target_square", "rotation_mismatch", "rotate_piece"),
        "rotate_success": has_event(scenario_rows, "rotate_success", "rotated_square", "target_square"),
        "square_success": has_event(scenario_rows, "insert_success", "rotated_square", "target_square"),

        "circle_success": has_event(scenario_rows, "insert_success", "valid_circle", "target_circle"),
    }

    return {
        "scenario_id": scenario_id,
        "total": len(scenario_rows),
        "global_total": len(rows),
        "counts": dict(counts),
        "checks": checks,
        "ready": all(checks.values()),
    }


def sqlite_summary(db_path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "not_found",
        "db_file": str(db_path),
        "tables": {},
        "v47_clean": False,
        "v48_geometry_ready": False,
        "v48_1_live_rotation_ready": False,
        "v48_2_controlled_error_ready": False,
        "v48_3_1_strategy_ready": False,
        "v48_4_strategy_generalization_ready": False,
        "v48_5_variation_generalization_ready": False,
        "baseline_ready": False,
        "baseline_warnings": [],
        "live_v48_1_summary": {},
        "live_v48_2_summary": {},
        "live_v48_3_1_summary": {},
        "live_v48_4_summary": {},
        "live_v48_5_summary": {},
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

        for table in V47_CLEAN_TABLES:
            count = summary["tables"].get(table, 0)
            if count not in (0, None):
                warnings.append(f"v47_not_clean:{table}={count}")

        for table, minimum in V48_MIN_COUNTS.items():
            count = summary["tables"].get(table, 0)
            if count is None or int(count) < minimum:
                warnings.append(f"v48_missing_or_low:{table}={count}, expected>={minimum}")

        live1 = live_v48_1_ready(conn)
        live2 = live_v48_2_ready(conn)
        live31 = live_v48_3_1_ready(conn)
        live4 = live_v48_4_ready(conn)
        live5 = live_v48_5_ready(conn)

        summary["live_v48_1_summary"] = live1
        summary["live_v48_2_summary"] = live2
        summary["live_v48_3_1_summary"] = live31
        summary["live_v48_4_summary"] = live4
        summary["live_v48_5_summary"] = live5

        if not live1.get("ready"):
            warnings.append("v48_1_live_rotation_not_ready")
        if not live2.get("ready"):
            warnings.append("v48_2_controlled_error_not_ready")
        if not live31.get("ready"):
            warnings.append("v48_3_1_strategy_not_ready")
        if not live4.get("ready"):
            warnings.append("v48_4_strategy_generalization_not_ready")
        if not live5.get("ready"):
            warnings.append("v48_5_variation_generalization_not_ready")

        summary["v47_clean"] = not any(w.startswith("v47_not_clean:") for w in warnings)
        summary["v48_geometry_ready"] = not any(w.startswith("v48_missing_or_low:") for w in warnings)
        summary["v48_1_live_rotation_ready"] = bool(live1.get("ready"))
        summary["v48_2_controlled_error_ready"] = bool(live2.get("ready"))
        summary["v48_3_1_strategy_ready"] = bool(live31.get("ready"))
        summary["v48_4_strategy_generalization_ready"] = bool(live4.get("ready"))
        summary["v48_5_variation_generalization_ready"] = bool(live5.get("ready"))
        summary["baseline_ready"] = (
            summary["v47_clean"]
            and summary["v48_geometry_ready"]
            and summary["v48_1_live_rotation_ready"]
            and summary["v48_2_controlled_error_ready"]
            and summary["v48_3_1_strategy_ready"]
            and summary["v48_4_strategy_generalization_ready"]
            and summary["v48_5_variation_generalization_ready"]
        )
        summary["baseline_warnings"] = warnings

    finally:
        conn.close()

    return summary


def copy_file(src: Path, dst: Path, dry_run: bool, manifest: dict[str, Any], label: str = "") -> None:
    rel = src.relative_to(PROJECT_ROOT)

    if not src.exists():
        print_status("AUSENTE", str(rel))
        manifest["missing"].append(str(rel))
        return

    if dry_run:
        print_status("DRYRUN", f"copiaria {rel}")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    item = {"source": str(src), "dest": str(dst), "size": src.stat().st_size, "sha256": sha256_file(src)}
    if label:
        item["label"] = label
    manifest["files"].append(item)
    print_status("OK", str(rel))


def copy_dir(src: Path, dst: Path, dry_run: bool, manifest: dict[str, Any], include_logs: bool = False) -> None:
    rel = src.relative_to(PROJECT_ROOT)

    if not src.exists():
        print_status("AUSENTE", str(rel))
        manifest["missing"].append(str(rel))
        return

    if not src.is_dir():
        copy_file(src, dst, dry_run, manifest)
        return

    if rel.as_posix().endswith("logs") and not include_logs:
        print_status("PULOU", f"{rel} (use --include-logs para incluir)")
        return

    if dry_run:
        count = sum(1 for p in src.rglob("*") if p.is_file())
        print_status("DRYRUN", f"copiaria diretório {rel} -> {count} arquivo(s)")
        return

    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst)

    file_count = 0
    total_bytes = 0
    for path in dst.rglob("*"):
        if path.is_file():
            file_count += 1
            total_bytes += path.stat().st_size

    manifest["directories"].append({"source": str(src), "dest": str(dst), "files": file_count, "bytes": total_bytes})
    print_status("DIR", f"{rel} -> {file_count} arquivo(s)")


def make_zip(baseline_dir: Path, dry_run: bool) -> Path:
    zip_path = baseline_dir.with_suffix(".zip")

    if dry_run:
        print_status("DRYRUN", f"criaria ZIP: {zip_path}")
        return zip_path

    if zip_path.exists():
        zip_path.unlink()

    shutil.make_archive(str(baseline_dir), "zip", root_dir=baseline_dir)
    print()
    print(f"ZIP criado: {zip_path}")
    return zip_path


def write_readme_and_manifest(baseline_dir: Path, manifest: dict[str, Any], dry_run: bool) -> None:
    manifest["sqlite_summary"] = sqlite_summary(DARWIN_HOME / "darwin.db")
    manifest["created_at"] = now_iso()

    if dry_run:
        print_status("DRYRUN", "criaria README_BASELINE.txt e manifest.json")
        return

    (baseline_dir / "README_BASELINE.txt").write_text(README_TEXT, encoding="utf-8")
    (baseline_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", "README_BASELINE.txt")
    print_status("OK", "manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela baseline estável Darwin v48.5.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    parser.add_argument("--include-logs", action="store_true", help="Inclui darwin_home/logs se existir.")
    args = parser.parse_args()

    baseline_name = f"baseline_v48_5_stable_{now_stamp()}"
    baseline_dir = BASELINES_DIR / baseline_name

    print("=" * 72)
    print("DARWIN — FREEZE BASELINE v48.5 STABLE")
    print("=" * 72)
    print(f"Raiz do projeto: {PROJECT_ROOT}")
    print(f"Destino:         {baseline_dir}")
    print(f"Dry-run:         {args.dry_run}")
    print()

    ensure_project_root()

    manifest: dict[str, Any] = {
        "baseline": "v48.5_stable",
        "project_root": str(PROJECT_ROOT),
        "baseline_dir": str(baseline_dir),
        "files": [],
        "directories": [],
        "missing": [],
        "sqlite_summary": {},
    }

    source_dir = baseline_dir / "source_files"
    home_dir = baseline_dir / "darwin_home"

    print("Arquivos essenciais:")
    for filename in REQUIRED_FILES:
        copy_file(PROJECT_ROOT / filename, source_dir / filename, args.dry_run, manifest, label="required")

    print()
    print("Arquivos opcionais:")
    for filename in OPTIONAL_FILES:
        src = PROJECT_ROOT / filename
        if src.exists():
            copy_file(src, source_dir / filename, args.dry_run, manifest, label="optional")
        else:
            print_status("AUSENTE", filename)

    print()
    print("darwin_home/")
    for item in HOME_ITEMS:
        src = DARWIN_HOME / item
        dst = home_dir / item
        if src.is_dir():
            copy_dir(src, dst, args.dry_run, manifest, include_logs=args.include_logs)
        else:
            copy_file(src, dst, args.dry_run, manifest)

    logs_src = DARWIN_HOME / "logs"
    if logs_src.exists():
        copy_dir(logs_src, home_dir / "logs", args.dry_run, manifest, include_logs=args.include_logs)

    write_readme_and_manifest(baseline_dir, manifest, args.dry_run)
    zip_path = make_zip(baseline_dir, args.dry_run)

    summary = manifest["sqlite_summary"]
    live5 = summary.get("live_v48_5_summary", {})

    print()
    print("Resumo SQLite:")
    print(f"- status: {summary.get('status')}")
    print(f"- v47_clean: {summary.get('v47_clean')}")
    print(f"- v48_geometry_ready: {summary.get('v48_geometry_ready')}")
    print(f"- v48_1_live_rotation_ready: {summary.get('v48_1_live_rotation_ready')}")
    print(f"- v48_2_controlled_error_ready: {summary.get('v48_2_controlled_error_ready')}")
    print(f"- v48_3_1_strategy_ready: {summary.get('v48_3_1_strategy_ready')}")
    print(f"- v48_4_strategy_generalization_ready: {summary.get('v48_4_strategy_generalization_ready')}")
    print(f"- v48_5_variation_generalization_ready: {summary.get('v48_5_variation_generalization_ready')}")
    print(f"- baseline_ready: {summary.get('baseline_ready')}")
    print(f"- v48_5_scenario_id: {live5.get('scenario_id')}")
    print(f"- v48_5_scenario_actions_total: {live5.get('total')}")
    print(f"- v48_5_global_actions_total: {live5.get('global_total')}")
    print(f"- v48_5_action_counts: {live5.get('counts')}")

    warnings = summary.get("baseline_warnings") or []
    if warnings:
        print("- baseline_warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if not args.dry_run:
        important_tables = (
            V47_CLEAN_TABLES
            + list(V48_MIN_COUNTS.keys())
            + [
                "geometry_curriculum_events_v48",
                "geometry_live_actions_v48_1",
                "geometry_live_actions_v48_2",
                "geometry_live_actions_v48_3_1",
                "geometry_live_actions_v48_4",
                "geometry_live_actions_v48_5",
            ]
        )
        for table in important_tables:
            print(f"- table:{table}: {summary.get('tables', {}).get(table)}")

        print()
        print(f"Baseline v48.5 congelada com sucesso em: {baseline_dir}")
        print(f"Pacote ZIP: {zip_path}")
        if warnings:
            print("ATENÇÃO: baseline tem avisos. Verifique antes de tratar como stable.")
        else:
            print("Baseline OK: v47 limpo, v48 pedagógico preservado e v48.5 variação registrada.")
        print("Próximo passo: iniciar v48.6 a partir da pasta operacional atual, não desta baseline.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
