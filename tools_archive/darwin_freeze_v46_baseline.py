#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DARWIN — Freeze Baseline v46
----------------------------
Cria uma cópia congelada da versão atual do Darwin antes de iniciar a v47.

Uso recomendado, dentro da pasta darwin_local/:

    py darwin_freeze_v46_baseline.py

Opcional:

    py darwin_freeze_v46_baseline.py --name baseline_v46_stable
    py darwin_freeze_v46_baseline.py --include-logs
    py darwin_freeze_v46_baseline.py --dry-run

O script NÃO altera os arquivos do Darwin. Ele apenas cria uma pasta em baselines/
com cópias, manifesto, hashes SHA256 e um .zip do baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_FILES = [
    "darwin_v61_nursery_v46.py",
    "darwin_home.py",
    "darwin_memory_graph.py",
    "darwin_memory_graph_v2.py",
    "darwin_memory_graph_layers.py",
    "darwin_memory_graph_layers_v2.py",
    "darwin_memory_graph_layers_v3.py",
    "darwin_memory_graph_png.py",
    "darwin_physical_manual_nursery.py",
    "darwin_physical_variation_nursery.py",
    "darwin_physical_variation_oracle_nursery.py",
    "darwin_sleep_auto_guard.py",
    "darwin_sleep_consolidation.py",
    "darwin_phase1_bootstrap.py",
]

DEFAULT_HOME_ITEMS = [
    "darwin.db",
    "darwin",       # fallback caso o banco esteja salvo sem extensão
    "config",
    "snapshots",
    "exports",
]

OPTIONAL_HOME_ITEMS = [
    "logs",
]


@dataclass
class CopyRecord:
    kind: str
    source: str
    destination: str
    exists: bool
    size_bytes: int | None = None
    sha256: str | None = None
    note: str = ""


@dataclass
class BaselineManifest:
    project: str
    baseline_name: str
    created_at_utc: str
    source_root: str
    baseline_root: str
    python_version: str
    records: list[CopyRecord]
    sqlite_summary: dict[str, int | str]
    warnings: list[str]


def utc_now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def safe_copy_file(src: Path, dst: Path, dry_run: bool) -> CopyRecord:
    record = CopyRecord(
        kind="file",
        source=str(src),
        destination=str(dst),
        exists=src.exists(),
    )

    if not src.exists():
        record.note = "arquivo ausente; ignorado"
        return record

    record.size_bytes = file_size(src)
    record.sha256 = sha256_file(src)

    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    return record


def iter_files_in_dir(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (p for p in root.rglob("*") if p.is_file())


def safe_copy_dir(src: Path, dst: Path, dry_run: bool) -> list[CopyRecord]:
    records: list[CopyRecord] = []

    if not src.exists():
        records.append(
            CopyRecord(
                kind="directory",
                source=str(src),
                destination=str(dst),
                exists=False,
                note="diretório ausente; ignorado",
            )
        )
        return records

    files = list(iter_files_in_dir(src))
    if not files:
        records.append(
            CopyRecord(
                kind="directory",
                source=str(src),
                destination=str(dst),
                exists=True,
                note="diretório existe, mas está vazio",
            )
        )
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)
        return records

    for file_path in files:
        rel = file_path.relative_to(src)
        out = dst / rel
        records.append(safe_copy_file(file_path, out, dry_run=dry_run))

    return records


def summarize_sqlite(db_path: Path) -> dict[str, int | str]:
    if not db_path.exists():
        return {"status": "db_not_found"}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [str(r["name"]) for r in rows]
        summary: dict[str, int | str] = {"status": "ok", "db_file": str(db_path)}
        for table in table_names:
            try:
                count = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"]
                summary[f"table:{table}"] = int(count)
            except Exception as exc:
                summary[f"table:{table}"] = f"count_error:{exc!r}"
        conn.close()
        return summary
    except Exception as exc:
        return {"status": "error", "error": repr(exc), "db_file": str(db_path)}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_zip(folder: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in folder.rglob("*"):
            if p.is_file() and p != zip_path:
                zf.write(p, arcname=p.relative_to(folder.parent))


def detect_db_path(source_root: Path) -> Path:
    candidates = [
        source_root / "darwin_home" / "darwin.db",
        source_root / "darwin_home" / "darwin",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Congela a baseline v46 do Projeto Darwin antes da v47."
    )
    parser.add_argument(
        "--name",
        default="baseline_v46_stable",
        help="Nome lógico da baseline. Um timestamp será adicionado automaticamente.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Raiz do projeto Darwin. Padrão: pasta atual.",
    )
    parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Também copia darwin_home/logs, se existir.",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Não cria arquivo .zip da baseline.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria copiado, sem criar arquivos.",
    )
    args = parser.parse_args()

    source_root = Path(args.root).resolve()
    if not source_root.exists():
        print(f"ERRO: raiz não encontrada: {source_root}")
        return 2

    timestamp = utc_now_slug()
    baseline_name = f"{args.name}_{timestamp}"
    baseline_root = source_root / "baselines" / baseline_name

    records: list[CopyRecord] = []
    warnings: list[str] = []

    print("=" * 72)
    print("DARWIN — FREEZE BASELINE v46")
    print("=" * 72)
    print(f"Raiz do projeto: {source_root}")
    print(f"Destino:         {baseline_root}")
    print(f"Dry-run:         {args.dry_run}")
    print("")

    if baseline_root.exists() and not args.dry_run:
        print(f"ERRO: baseline já existe: {baseline_root}")
        return 3

    # 1) Copia scripts principais.
    for filename in DEFAULT_FILES:
        src = source_root / filename
        dst = baseline_root / "source_files" / filename
        rec = safe_copy_file(src, dst, dry_run=args.dry_run)
        records.append(rec)
        status = "OK" if rec.exists else "AUSENTE"
        print(f"[{status:7}] {filename}")
        if not rec.exists:
            warnings.append(f"arquivo ausente: {filename}")

    # 2) Copia itens importantes de darwin_home.
    home_root = source_root / "darwin_home"
    home_items = list(DEFAULT_HOME_ITEMS)
    if args.include_logs:
        home_items.extend(OPTIONAL_HOME_ITEMS)

    print("")
    print("darwin_home/")
    for item in home_items:
        src = home_root / item
        dst = baseline_root / "darwin_home" / item
        if src.is_dir():
            dir_records = safe_copy_dir(src, dst, dry_run=args.dry_run)
            records.extend(dir_records)
            print(f"[DIR    ] {src.relative_to(source_root)} -> {len(dir_records)} registro(s)")
        else:
            rec = safe_copy_file(src, dst, dry_run=args.dry_run)
            records.append(rec)
            status = "OK" if rec.exists else "AUSENTE"
            print(f"[{status:7}] {src.relative_to(source_root)}")
            if not rec.exists and item in {"darwin.db", "darwin"}:
                # Só avisa depois se nenhum dos dois bancos existir.
                pass

    db_path = detect_db_path(source_root)
    sqlite_summary = summarize_sqlite(db_path)
    if sqlite_summary.get("status") != "ok":
        warnings.append(f"resumo SQLite indisponível: {sqlite_summary}")

    manifest = BaselineManifest(
        project="Darwin",
        baseline_name=baseline_name,
        created_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source_root=str(source_root),
        baseline_root=str(baseline_root),
        python_version=sys.version.replace("\n", " "),
        records=records,
        sqlite_summary=sqlite_summary,
        warnings=warnings,
    )

    if not args.dry_run:
        write_json(
            baseline_root / "manifest.json",
            {
                **asdict(manifest),
                "records": [asdict(r) for r in records],
            },
        )

        readme = baseline_root / "README_BASELINE.txt"
        readme.write_text(
            "DARWIN — BASELINE v46 CONGELADA\n"
            "================================\n\n"
            f"Nome: {baseline_name}\n"
            f"Criada em UTC: {manifest.created_at_utc}\n"
            f"Origem: {source_root}\n\n"
            "Esta pasta é uma cópia de segurança técnica antes da v47.\n"
            "Não edite esta baseline. Trabalhe em cópias novas.\n\n"
            "Arquivos principais em: source_files/\n"
            "Persistência em: darwin_home/\n"
            "Manifesto técnico: manifest.json\n",
            encoding="utf-8",
        )

        if not args.no_zip:
            zip_path = baseline_root.parent / f"{baseline_name}.zip"
            make_zip(baseline_root, zip_path)
            print("")
            print(f"ZIP criado: {zip_path}")

    print("")
    print("Resumo SQLite:")
    for k, v in sqlite_summary.items():
        print(f"- {k}: {v}")

    if warnings:
        print("")
        print("Avisos:")
        for w in warnings:
            print(f"- {w}")

    print("")
    if args.dry_run:
        print("Dry-run concluído. Nenhum arquivo foi criado.")
    else:
        print(f"Baseline congelada com sucesso em: {baseline_root}")
        print("Próximo passo: iniciar v47 a partir de uma cópia, não desta baseline.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
