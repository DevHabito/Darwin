from __future__ import annotations

"""
DARWIN — Freeze Baseline v48.3.1 Stable

Congela o estado atual da v48.3.1 depois da correção da ordem auditável
da estratégia após erro.

Diferente das baselines v47:
- NÃO zera tabelas geometry_*_v48.
- NÃO zera geometry_live_actions_v48_1.
- NÃO zera geometry_live_actions_v48_2.
- NÃO zera geometry_live_actions_v48_3_1.

Essas tabelas representam memória pedagógica física e evidência operacional.

Estado ideal:
- núcleo executivo v47 limpo:
  tension_* = 0

- geometria v48.0 preservada:
  geometry_shapes_v48 >= 3
  geometry_pieces_v48 >= 6
  geometry_holes_v48 >= 3
  geometry_fit_attempts_v48 >= 27
  geometry_rules_v48 >= 3
  geometry_spatial_concepts_v48 >= 5

- rotação ativa v48.1 registrada:
  geometry_live_actions_v48_1 existe
  rotate_success >= 1
  insert_success >= 3

- erro controlado v48.2 registrado:
  geometry_live_actions_v48_2 existe
  controlled_explore_choose >= 1
  controlled_collision >= 1
  error_memory_write >= 1
  avoid_repeat >= 1
  insert_success >= 3

- estratégia após erro v48.3.1 registrada:
  geometry_live_actions_v48_3_1 existe
  controlled_explore_choose >= 1
  controlled_collision_start >= 1
  controlled_collision >= 1
  error_memory_write >= 1
  strategy_select >= 1
  strategy_execute >= 1
  avoid_repeat >= 1
  rotate_success >= 1
  insert_success >= 3
  ciclo ordenado:
      controlled_explore_choose
      -> controlled_collision_start
      -> controlled_collision
      -> error_memory_write
      -> strategy_select
      -> strategy_execute
      -> insert_success

Uso:
    py darwin_freeze_v48_3_1_stable.py --dry-run
    py darwin_freeze_v48_3_1_stable.py

Incluir logs, se houver:
    py darwin_freeze_v48_3_1_stable.py --include-logs
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

    # v48.0
    "darwin_shape_sorter_nursery_v48.py",
    "darwin_shape_sorter_v48_test.py",

    # v48.1
    "darwin_shape_sorter_live_v48_1_active_rotation.py",
    "darwin_check_v48_1_live_rotation.py",

    # v48.2
    "darwin_shape_sorter_live_v48_2_controlled_error.py",
    "darwin_check_v48_2_controlled_error.py",

    # v48.3 / v48.3.1
    "darwin_shape_sorter_live_v48_3_strategy_after_error.py",
    "darwin_check_v48_3_strategy_after_error.py",
    "darwin_repair_v48_3_1_strategy_order.py",
    "darwin_shape_sorter_live_v48_3_1_strategy_after_error.py",
    "darwin_check_v48_3_1_strategy_after_error.py",
]

OPTIONAL_FILES = [
    # ferramentas úteis
    "darwin_check_v47_tensions.py",
    "darwin_tension_dashboard_v47.py",
    "darwin_sleep_auto_guard.py",
    "darwin_sleep_consolidation.py",

    # v47.8/v47.8.1
    "darwin_repair_v47_8_resolution_policy.py",
    "darwin_repair_v47_8_1_resolution_policy.py",
    "darwin_v47_8_resolution_policy_test.py",

    # v47.9/v47.9.1
    "darwin_patch_v47_9_compare_context_operator.py",
    "darwin_repair_v47_9_1_compare_context.py",
    "darwin_v47_9_compare_context_operator_test.py",

    # v47.10
    "darwin_patch_v47_10_prediction_influence.py",
    "darwin_v47_10_prediction_influence_test.py",

    # v47.11
    "darwin_patch_v47_11_hypothesis_lineage.py",
    "darwin_v47_11_hypothesis_lineage_test.py",

    # v47.12/v47.12.1
    "darwin_repair_v47_12_1_cycle_report.py",
    "darwin_v47_12_cycle_report_test.py",

    # v47.13
    "darwin_patch_v47_13_cycle_memory_review.py",
    "darwin_v47_13_cycle_memory_review_test.py",

    # visualizadores v48
    "darwin_shape_sorter_live_v48_1.py",
    "darwin_shape_sorter_live_v48_1_active_rotation.py",
    "darwin_shape_sorter_live_v48_2_controlled_error.py",
    "darwin_shape_sorter_live_v48_3_strategy_after_error.py",
    "darwin_shape_sorter_live_v48_3_1_strategy_after_error.py",
]

HOME_ITEMS = [
    "darwin.db",
    "snapshots",
    "exports",
    "backups",
]


README_TEXT = """DARWIN — Baseline v48.3.1 Stable
================================

Esta baseline representa o marco estável da v48.3.1.

Parte executiva herdada da v47.13:
- memória executiva persistente de tensões;
- reidratação de tensões abertas no boot;
- compromisso executivo real;
- micro-rotina de resolução de tensão;
- revisão de ciclos passados antes de agir;
- cadeia auditável:
  tensão → revisão de memória → comparação → influência → hipótese → linhagem → validação → relatório.

Parte pedagógica física da v48.0:
- Physical Geometry Nursery;
- Shape Sorter;
- formas iniciais: círculo, quadrado e triângulo;
- avaliação de encaixe por contorno, tamanho, profundidade e orientação;
- regra aprendida: forma correta sozinha não basta.

Marco v48.1:
- visualizador ao vivo;
- rotação ativa;
- Darwin detecta rotation_mismatch;
- Darwin gira a peça antes de desistir;
- Darwin reavalia após rotação;
- Darwin encaixa o quadrado rotacionado após correção espacial.

Marco v48.2:
- erro exploratório controlado;
- Darwin testa hipótese fraca;
- Darwin detecta colisão;
- Darwin recua;
- Darwin registra memória do erro;
- Darwin evita repetir o mesmo par falho.

Marco v48.3.1:
- escolha de estratégia após erro;
- Darwin classifica a falha;
- contour_mismatch gera estratégia try_alternate_hole;
- Darwin executa a estratégia e tenta outro buraco para a mesma peça;
- cadeia auditável corrigida:
  controlled_explore_choose
  → controlled_collision_start
  → controlled_collision
  → error_memory_write
  → strategy_select
  → strategy_execute
  → insert_success.

Regra:
NÃO editar esta baseline diretamente.
NÃO rodar experimentos dentro desta baseline.
Use-a apenas como ponto de retorno, auditoria e preservação histórica.

Observação importante:
As tabelas geometry_*_v48, geometry_live_actions_v48_1, geometry_live_actions_v48_2
e geometry_live_actions_v48_3_1 NÃO são zeradas. Elas representam memória pedagógica
física e evidência visual/operacional.

Próximo desenvolvimento sugerido:
começar v48.4 a partir da pasta operacional atual, não desta baseline.

Direção natural:
v48.4 — generalização de estratégia:
Darwin deve aplicar a mesma política a novas falhas:
- size_mismatch → rejeitar par por tamanho;
- depth_mismatch → rejeitar inserção completa;
- rotation_mismatch → girar;
- contour_mismatch → tentar outro buraco;
- uncertain_failure → exploração cautelosa.
"""


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

LIVE_V48_1 = "geometry_live_actions_v48_1"
LIVE_V48_2 = "geometry_live_actions_v48_2"
LIVE_V48_3_1 = "geometry_live_actions_v48_3_1"


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

    db = DARWIN_HOME / "darwin.db"
    if not db.exists():
        missing.append("darwin_home/darwin.db")

    if missing:
        raise FileNotFoundError(
            "Arquivos essenciais não encontrados na pasta atual:\n"
            + "\n".join(f"- {item}" for item in missing)
            + "\n\nRode este script dentro da pasta darwin_local."
        )


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
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

    rows = conn.execute(
        f"""
        SELECT id, timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json
        FROM {table}
        ORDER BY id ASC
        """
    ).fetchall()

    out = []
    for row in rows:
        payload = parse_payload(str(row["payload_json"] or "{}"))
        out.append({key: row[key] for key in row.keys()} | {"payload": payload})
    return out


def has_event(rows: list[dict[str, Any]], action: str, piece: str | None = None, hole: str | None = None,
              note_contains: str | None = None) -> bool:
    for row in rows:
        if row["action_kind"] != action:
            continue
        if piece is not None and row["piece_id"] != piece:
            continue
        if hole is not None and row["hole_id"] != hole:
            continue
        if note_contains is not None and note_contains not in str(row["note"]):
            continue
        return True
    return False


def event_indices(rows: list[dict[str, Any]], action: str | None = None, piece: str | None = None,
                  hole: str | None = None, note_contains: str | None = None) -> list[int]:
    out = []
    for i, row in enumerate(rows):
        if action is not None and row["action_kind"] != action:
            continue
        if piece is not None and row["piece_id"] != piece:
            continue
        if hole is not None and row["hole_id"] != hole:
            continue
        if note_contains is not None and note_contains not in str(row["note"]):
            continue
        out.append(i)
    return out


def first_after(items: list[int], after: int) -> int | None:
    for item in items:
        if item > after:
            return item
    return None


def live_v48_1_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, LIVE_V48_1)
    counts = Counter(str(row["action_kind"]) for row in rows)

    checks = {
        "has_rows": bool(rows),
        "has_rotate_success": has_event(rows, "rotate_success", "piece_square_rotated", "hole_square"),
        "has_square_success": has_event(rows, "insert_success", "piece_square_rotated", "hole_square"),
        "has_triangle_success": has_event(rows, "insert_success", "piece_triangle", "hole_triangle"),
        "has_circle_success": has_event(rows, "insert_success", "piece_circle", "hole_circle"),
    }

    return {"total": len(rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_2_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, LIVE_V48_2)
    counts = Counter(str(row["action_kind"]) for row in rows)

    checks = {
        "has_rows": bool(rows),
        "has_controlled_explore_choose": has_event(rows, "controlled_explore_choose"),
        "has_controlled_collision": has_event(rows, "controlled_collision"),
        "has_error_memory_write": has_event(rows, "error_memory_write"),
        "has_avoid_repeat": has_event(rows, "avoid_repeat"),
        "has_rotate_success": has_event(rows, "rotate_success", "piece_square_rotated", "hole_square"),
        "has_square_success": has_event(rows, "insert_success", "piece_square_rotated", "hole_square"),
        "has_triangle_success": has_event(rows, "insert_success", "piece_triangle", "hole_triangle"),
        "has_circle_success": has_event(rows, "insert_success", "piece_circle", "hole_circle"),
    }

    return {"total": len(rows), "counts": dict(counts), "checks": checks, "ready": all(checks.values())}


def live_v48_3_1_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = live_rows(conn, LIVE_V48_3_1)
    counts = Counter(str(row["action_kind"]) for row in rows)

    explores = event_indices(rows, "controlled_explore_choose")
    starts = event_indices(rows, "controlled_collision_start")
    collisions = event_indices(rows, "controlled_collision")
    memories = event_indices(rows, "error_memory_write")
    selects = event_indices(rows, "strategy_select")
    executes = event_indices(rows, "strategy_execute")
    triangle_success = event_indices(rows, "insert_success", "piece_triangle", "hole_triangle")

    ordered_trace: list[int | None] = []
    ordered = False
    for a in explores:
        b = first_after(starts, a)
        c = first_after(collisions, b if b is not None else a)
        d = first_after(memories, c if c is not None else a)
        e = first_after(selects, d if d is not None else a)
        f = first_after(executes, e if e is not None else a)
        g = first_after(triangle_success, f if f is not None else a)
        trace = [a, b, c, d, e, f, g]
        if all(x is not None for x in trace):
            ordered = True
            ordered_trace = trace
            break

    execs = event_indices(rows, "strategy_execute")
    square_success = event_indices(rows, "insert_success", "piece_square_rotated", "hole_square")
    circle_success = event_indices(rows, "insert_success", "piece_circle", "hole_circle")
    solved_after_strategy = False
    if execs:
        s = execs[0]
        solved_after_strategy = (
            first_after(square_success, s) is not None
            and first_after(circle_success, s) is not None
            and first_after(triangle_success, s) is not None
        )

    checks = {
        "has_rows": bool(rows),
        "has_controlled_explore_choose": bool(explores),
        "has_controlled_collision_start": bool(starts),
        "has_controlled_collision": bool(collisions),
        "has_error_memory_write": bool(memories),
        "has_strategy_select": bool(selects),
        "has_strategy_execute": bool(executes),
        "strategy_maps_contour_to_try_alternate": has_event(rows, "strategy_select", "piece_triangle", "hole_square", "try_alternate_hole"),
        "strategy_executes_alternate_hole": has_event(rows, "strategy_execute", "piece_triangle", "hole_triangle", "try_alternate_hole"),
        "ordered_strategy_cycle": ordered,
        "has_avoid_repeat": has_event(rows, "avoid_repeat"),
        "has_triangle_success": bool(triangle_success),
        "has_circle_success": bool(circle_success),
        "has_square_success": bool(square_success),
        "has_rotate_success": has_event(rows, "rotate_success", "piece_square_rotated", "hole_square"),
        "solved_after_strategy": solved_after_strategy,
    }

    return {
        "total": len(rows),
        "counts": dict(counts),
        "checks": checks,
        "ordered_trace": ordered_trace,
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
        "baseline_ready": False,
        "baseline_warnings": [],
        "live_v48_1_summary": {},
        "live_v48_2_summary": {},
        "live_v48_3_1_summary": {},
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

        live1 = live_v48_1_summary(conn)
        live2 = live_v48_2_summary(conn)
        live31 = live_v48_3_1_summary(conn)

        summary["live_v48_1_summary"] = live1
        summary["live_v48_2_summary"] = live2
        summary["live_v48_3_1_summary"] = live31

        if not live1.get("ready"):
            warnings.append("v48_1_live_rotation_not_ready")
        if not live2.get("ready"):
            warnings.append("v48_2_controlled_error_not_ready")
        if not live31.get("ready"):
            warnings.append("v48_3_1_strategy_not_ready")

        summary["v47_clean"] = not any(w.startswith("v47_not_clean:") for w in warnings)
        summary["v48_geometry_ready"] = not any(w.startswith("v48_missing_or_low:") for w in warnings)
        summary["v48_1_live_rotation_ready"] = bool(live1.get("ready"))
        summary["v48_2_controlled_error_ready"] = bool(live2.get("ready"))
        summary["v48_3_1_strategy_ready"] = bool(live31.get("ready"))
        summary["baseline_ready"] = (
            summary["v47_clean"]
            and summary["v48_geometry_ready"]
            and summary["v48_1_live_rotation_ready"]
            and summary["v48_2_controlled_error_ready"]
            and summary["v48_3_1_strategy_ready"]
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

    item = {
        "source": str(src),
        "dest": str(dst),
        "size": src.stat().st_size,
        "sha256": sha256_file(src),
    }
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

    manifest["directories"].append(
        {
            "source": str(src),
            "dest": str(dst),
            "files": file_count,
            "bytes": total_bytes,
        }
    )

    print_status("DIR", f"{rel} -> {file_count} arquivo(s)")


def make_zip(baseline_dir: Path, dry_run: bool) -> Path:
    zip_base = baseline_dir
    zip_path = baseline_dir.with_suffix(".zip")

    if dry_run:
        print_status("DRYRUN", f"criaria ZIP: {zip_path}")
        return zip_path

    if zip_path.exists():
        zip_path.unlink()

    shutil.make_archive(str(zip_base), "zip", root_dir=baseline_dir)
    print()
    print(f"ZIP criado: {zip_path}")
    return zip_path


def write_readme_and_manifest(baseline_dir: Path, manifest: dict[str, Any], dry_run: bool) -> None:
    db_path = DARWIN_HOME / "darwin.db"
    manifest["sqlite_summary"] = sqlite_summary(db_path)
    manifest["created_at"] = now_iso()

    if dry_run:
        print_status("DRYRUN", "criaria README_BASELINE.txt e manifest.json")
        return

    (baseline_dir / "README_BASELINE.txt").write_text(README_TEXT, encoding="utf-8")
    (baseline_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print_status("OK", "README_BASELINE.txt")
    print_status("OK", "manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela baseline estável Darwin v48.3.1.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    parser.add_argument("--include-logs", action="store_true", help="Inclui darwin_home/logs se existir.")
    args = parser.parse_args()

    baseline_name = f"baseline_v48_3_1_stable_{now_stamp()}"
    baseline_dir = BASELINES_DIR / baseline_name

    print("=" * 72)
    print("DARWIN — FREEZE BASELINE v48.3.1 STABLE")
    print("=" * 72)
    print(f"Raiz do projeto: {PROJECT_ROOT}")
    print(f"Destino:         {baseline_dir}")
    print(f"Dry-run:         {args.dry_run}")
    print()

    ensure_project_root()

    manifest: dict[str, Any] = {
        "baseline": "v48.3.1_stable",
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
    live1 = summary.get("live_v48_1_summary", {})
    live2 = summary.get("live_v48_2_summary", {})
    live31 = summary.get("live_v48_3_1_summary", {})

    print()
    print("Resumo SQLite:")
    print(f"- status: {summary.get('status')}")
    print(f"- v47_clean: {summary.get('v47_clean')}")
    print(f"- v48_geometry_ready: {summary.get('v48_geometry_ready')}")
    print(f"- v48_1_live_rotation_ready: {summary.get('v48_1_live_rotation_ready')}")
    print(f"- v48_2_controlled_error_ready: {summary.get('v48_2_controlled_error_ready')}")
    print(f"- v48_3_1_strategy_ready: {summary.get('v48_3_1_strategy_ready')}")
    print(f"- baseline_ready: {summary.get('baseline_ready')}")
    print(f"- v48_1_live_actions_total: {live1.get('total')}")
    print(f"- v48_1_live_action_counts: {live1.get('counts')}")
    print(f"- v48_2_live_actions_total: {live2.get('total')}")
    print(f"- v48_2_live_action_counts: {live2.get('counts')}")
    print(f"- v48_3_1_live_actions_total: {live31.get('total')}")
    print(f"- v48_3_1_live_action_counts: {live31.get('counts')}")

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
                "geometry_live_actions_v48_3",
                "geometry_live_actions_v48_3_1",
            ]
        )
        for table in important_tables:
            print(f"- table:{table}: {summary.get('tables', {}).get(table)}")

        print()
        print(f"Baseline v48.3.1 congelada com sucesso em: {baseline_dir}")
        print(f"Pacote ZIP: {zip_path}")
        if warnings:
            print("ATENÇÃO: baseline tem avisos. Verifique antes de tratar como stable.")
        else:
            print("Baseline OK: v47 limpo, v48 pedagógico preservado e v48.3.1 estratégia após erro registrada.")
        print("Próximo passo: iniciar v48.4 a partir da pasta operacional atual, não desta baseline.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
