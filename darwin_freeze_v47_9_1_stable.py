from __future__ import annotations

"""
DARWIN — Freeze Baseline v47.9.1 Stable

Congela o estado atual da v47.9.1 depois do operador real compare_context.

IMPORTANTE:
Antes de congelar, rode:
    py darwin_v47_9_compare_context_operator_test.py --purge-compare-tests

A baseline ideal deve ficar limpa:
- tension_cases: 0
- tension_events: 0
- tension_probes: 0
- tension_outcomes: 0
- tension_resolution_routines: 0
- tension_resolution_steps: 0
- tension_context_comparisons: 0
- open_tension_cases: 0
- open_resolution_routines: 0

Uso:
    py darwin_freeze_v47_9_1_stable.py --dry-run
    py darwin_freeze_v47_9_1_stable.py

Incluir logs, se houver:
    py darwin_freeze_v47_9_1_stable.py --include-logs
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
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
]

OPTIONAL_FILES = [
    # ferramentas ainda úteis na raiz operacional
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

    # manifests recentes
    "v47_8_1_resolution_policy_repair_manifest.json",
    "v47_9_compare_context_operator_manifest.json",
    "v47_9_1_compare_context_repair_manifest.json",
]

HOME_ITEMS = [
    "darwin.db",
    "snapshots",
    "exports",
    "backups",
]


README_TEXT = """DARWIN — Baseline v47.9.1 Stable
=================================

Esta baseline representa o marco estável da v47.9.1:

- memória executiva persistente de tensões;
- reidratação de tensões abertas no boot;
- restauração de active_tension_id;
- compromisso executivo real;
- micro-rotina de resolução de tensão;
- seletor ampliado de política da micro-rotina;
- operador real compare_context antes do predict;
- tabela tension_context_comparisons;
- comando 10x para visualizar a última comparação contextual;
- repair v47.9.1 completando a ligação entre estágio compare_context_before_prediction
  e execução real de _v47_9_run_compare_context.

Regra:
NÃO editar esta baseline diretamente.
NÃO rodar experimentos dentro desta baseline.
Use-a apenas como ponto de retorno, auditoria e preservação histórica.

Próximo desenvolvimento sugerido:
começar v47.10/v48 a partir da pasta operacional atual, não desta baseline.

Direção natural:
transformar o resultado do compare_context em influência real sobre a escolha da hipótese,
não apenas em registro auditável antes do predict.
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

    db = DARWIN_HOME / "darwin.db"
    if not db.exists():
        missing.append("darwin_home/darwin.db")

    if missing:
        raise FileNotFoundError(
            "Arquivos essenciais não encontrados na pasta atual:\n"
            + "\n".join(f"- {item}" for item in missing)
            + "\n\nRode este script dentro da pasta darwin_local."
        )


def sqlite_summary(db_path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "not_found",
        "db_file": str(db_path),
        "tables": {},
        "v47_migration_present": False,
        "open_tension_cases": 0,
        "open_resolution_routines": 0,
        "baseline_clean": False,
        "baseline_warnings": [],
    }

    if not db_path.exists():
        return summary

    summary["status"] = "ok"

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        table_names = [name for (name,) in rows]

        for name in table_names:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                summary["tables"][name] = int(count)
            except Exception:
                summary["tables"][name] = None

        if "darwin_schema_migrations" in table_names:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM darwin_schema_migrations
                WHERE name='v47_tension_persistence_schema'
                """
            ).fetchone()
            summary["v47_migration_present"] = bool(row and int(row[0]) > 0)

        if "tension_cases" in table_names:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM tension_cases
                WHERE status NOT IN ('closed', 'archived', 'stale')
                """
            ).fetchone()
            summary["open_tension_cases"] = int(row[0]) if row else 0

        if "tension_resolution_routines" in table_names:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM tension_resolution_routines
                WHERE status='active'
                """
            ).fetchone()
            summary["open_resolution_routines"] = int(row[0]) if row else 0

    finally:
        conn.close()

    clean_tables = [
        "tension_cases",
        "tension_events",
        "tension_probes",
        "tension_outcomes",
        "tension_resolution_routines",
        "tension_resolution_steps",
        "tension_context_comparisons",
    ]

    dirty = []
    for table in clean_tables:
        count = summary["tables"].get(table, 0)
        if count not in (0, None):
            dirty.append(f"{table}={count}")

    if summary["open_tension_cases"]:
        dirty.append(f"open_tension_cases={summary['open_tension_cases']}")
    if summary["open_resolution_routines"]:
        dirty.append(f"open_resolution_routines={summary['open_resolution_routines']}")

    summary["baseline_clean"] = len(dirty) == 0
    summary["baseline_warnings"] = dirty
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
    parser = argparse.ArgumentParser(description="Congela baseline estável Darwin v47.9.1.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    parser.add_argument("--include-logs", action="store_true", help="Inclui darwin_home/logs se existir.")
    args = parser.parse_args()

    baseline_name = f"baseline_v47_9_1_stable_{now_stamp()}"
    baseline_dir = BASELINES_DIR / baseline_name

    print("=" * 72)
    print("DARWIN — FREEZE BASELINE v47.9.1 STABLE")
    print("=" * 72)
    print(f"Raiz do projeto: {PROJECT_ROOT}")
    print(f"Destino:         {baseline_dir}")
    print(f"Dry-run:         {args.dry_run}")
    print()

    ensure_project_root()

    manifest: dict[str, Any] = {
        "baseline": "v47.9.1_stable",
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
    print()
    print("Resumo SQLite:")
    print(f"- status: {summary.get('status')}")
    print(f"- v47_migration_present: {summary.get('v47_migration_present')}")
    print(f"- open_tension_cases: {summary.get('open_tension_cases')}")
    print(f"- open_resolution_routines: {summary.get('open_resolution_routines')}")
    print(f"- baseline_clean: {summary.get('baseline_clean')}")
    warnings = summary.get("baseline_warnings") or []
    if warnings:
        print("- baseline_warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if not args.dry_run:
        for table, count in summary.get("tables", {}).items():
            print(f"- table:{table}: {count}")

        print()
        print(f"Baseline v47.9.1 congelada com sucesso em: {baseline_dir}")
        print(f"Pacote ZIP: {zip_path}")
        if warnings:
            print("ATENÇÃO: baseline contém registros de teste/tensão. Rode purge antes se quiser uma baseline limpa.")
        else:
            print("Baseline limpa: sem tensões artificiais, rotinas abertas ou comparações pendentes.")
        print("Próximo passo: iniciar v47.10/v48 a partir da pasta operacional atual, não desta baseline.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
