from __future__ import annotations

"""
DARWIN v47.3.1 — Correção de Déficit 0.0 e Preempção Inicial

Corrige:
1. closure_deficit=0.0 virando 1.0 no tension_cases.
2. Primeiro refresh registrando preempted_out para a última tensão aberta,
   mesmo antes de haver foco executivo real.

Uso:
    py darwin_patch_v47_3_1_persistence_fixes.py --dry-run
    py darwin_patch_v47_3_1_persistence_fixes.py
"""

import argparse
import hashlib
import json
import py_compile
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
TENSION_MODULE = PROJECT_ROOT / "darwin_tension_persistence_v47.py"
DB_PATH = PROJECT_ROOT / "darwin_home" / "darwin.db"
BACKUP_DIR = PROJECT_ROOT / "v47_patch_backups"
MANIFEST_FILE = PROJECT_ROOT / "v47_3_1_persistence_fixes_manifest.json"

PREEMPT_ANCHOR = '                if current_active:\n                    active_case = getattr(self, "live_tension_cases", {}).get(current_active)\n                    pressure = float(getattr(active_case, "live_pressure", 0.0) or 0.0) if active_case else None\n                    store.record_event(\n                        tension_id=current_active,\n                        event_type="tension_preempted_in",\n                        step=self._current_step(),\n                        status_after="active",\n                        pressure_after=pressure,\n                        note=f"tensão escolhida como foco executivo: {current_active}",\n                        payload={"previous_active_tension_id": previous_active_tension_id},\n                    )\n'
PREEMPT_REPLACEMENT = '                if current_active:\n                    active_case = getattr(self, "live_tension_cases", {}).get(current_active)\n                    pressure = float(getattr(active_case, "live_pressure", 0.0) or 0.0) if active_case else None\n                    store.record_event(\n                        tension_id=current_active,\n                        event_type="tension_preempted_in",\n                        step=self._current_step(),\n                        status_after="active",\n                        pressure_after=pressure,\n                        note=f"tensão escolhida como foco executivo: {current_active}",\n                        payload={"previous_active_tension_id": previous_active_tension_id},\n                    )\n            self._v47_last_executive_active_id = current_active\n'


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


def backup_file(path: Path, dry_run: bool) -> str | None:
    if not path.exists():
        print_status("AUSENTE", f"{path.name} não existe; pulando backup")
        return None

    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_3_1_{now_stamp()}{path.suffix}"

    if dry_run:
        print_status("DRYRUN", f"criaria backup: {backup_path}")
        return str(backup_path)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    print_status("OK", f"backup criado: {backup_path}")
    return str(backup_path)


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, int]:
    if old not in text:
        print_status("AVISO", f"não encontrado: {label}")
        return text, 0
    text = text.replace(old, new, 1)
    print_status("OK", f"{label}: 1 ocorrência")
    return text, 1


def patch_tension_module(text: str) -> tuple[str, int]:
    changes = 0

    text, n = replace_once(
        text,
        '                    float(case_get(case, "closure_deficit", 1.0) or 1.0),\n',
        '                    float(1.0 if case_get(case, "closure_deficit", None) is None else case_get(case, "closure_deficit")),\n',
        "closure_deficit preserva 0.0",
    )
    changes += n

    text, n = replace_once(
        text,
        '                    float(case_get(case, "contradiction_magnitude", 1.0) or 1.0),\n',
        '                    float(1.0 if case_get(case, "contradiction_magnitude", None) is None else case_get(case, "contradiction_magnitude")),\n',
        "contradiction_magnitude preserva 0.0",
    )
    changes += n

    return text, changes


def patch_v47_file(text: str) -> tuple[str, int]:
    changes = 0

    text, n = replace_once(
        text,
        '        previous_active_tension_id = getattr(self, "active_tension_id", None)\n'
        '        now = self._current_step()\n',
        '        previous_active_tension_id = getattr(self, "_v47_last_executive_active_id", None)\n'
        '        now = self._current_step()\n',
        "refresh usa último foco executivo real",
    )
    changes += n

    if "self._v47_last_executive_active_id = None" not in text:
        text, n = replace_once(
            text,
            "        self.tension_store = None\n",
            "        self._v47_last_executive_active_id = None\n        self.tension_store = None\n",
            "inicializa _v47_last_executive_active_id",
        )
        changes += n
    else:
        print_status("PULOU", "_v47_last_executive_active_id já existe")

    if "self._v47_last_executive_active_id = current_active" not in text:
        text, n = replace_once(
            text,
            PREEMPT_ANCHOR,
            PREEMPT_REPLACEMENT,
            "atualiza _v47_last_executive_active_id após sync",
        )
        changes += n
    else:
        print_status("PULOU", "atualização _v47_last_executive_active_id já existe")

    return text, changes


def patch_file(path: Path, patcher, dry_run: bool) -> tuple[int, str | None]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    original = path.read_text(encoding="utf-8")
    patched, changes = patcher(original)

    if changes == 0:
        print_status("PULOU", f"{path.name}: nenhuma mudança necessária")
        return 0, None

    backup = backup_file(path, dry_run=dry_run)

    if dry_run:
        print_status("DRYRUN", f"aplicaria {changes} mudança(s) em {path.name}")
        return changes, backup

    path.write_text(patched, encoding="utf-8")
    print_status("OK", f"{changes} mudança(s) aplicada(s) em {path.name}")
    return changes, backup


def fix_existing_rows(dry_run: bool) -> int:
    if not DB_PATH.exists():
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tension_cases'"
        ).fetchone()
        if not exists:
            return 0

        rows = conn.execute(
            """
            SELECT tension_id
            FROM tension_cases
            WHERE status IN ('closed', 'archived')
              AND closure_deficit != 0.0
            """
        ).fetchall()

        ids = [str(row[0]) for row in rows]
        if not ids:
            print_status("OK", "nenhum registro existente precisa de correção closure_deficit")
            return 0

        print_status("INFO", f"registros existentes a corrigir: {len(ids)}")

        if dry_run:
            for tid in ids:
                print_status("DRYRUN", f"corrigiria closure_deficit=0.0 em {tid}")
            return len(ids)

        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE tension_cases SET closure_deficit=0.0 WHERE tension_id IN ({placeholders})",
            ids,
        )
        conn.commit()

    for tid in ids:
        print_status("OK", f"closure_deficit corrigido em {tid}")
    return len(ids)


def compile_files() -> bool:
    ok = True
    for path in (V47_FILE, TENSION_MODULE):
        try:
            py_compile.compile(str(path), doraise=True)
            print_status("OK", f"py_compile passou: {path.name}")
        except py_compile.PyCompileError as exc:
            print_status("ERRO", f"py_compile falhou: {path.name}")
            print(str(exc))
            ok = False
    return ok


def write_manifest(total_changes: int, db_fixes: int, backups: list[str | None], dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.3.1_persistence_fixes",
        "total_file_changes": total_changes,
        "db_rows_fixed": db_fixes,
        "files": {
            "v47": str(V47_FILE),
            "tension_module": str(TENSION_MODULE),
            "db": str(DB_PATH),
        },
        "backups": [b for b in backups if b],
        "hashes": {},
    }

    for path in (V47_FILE, TENSION_MODULE, DB_PATH):
        if path.exists():
            manifest["hashes"][str(path)] = sha256_file(path)

    for backup in manifest["backups"]:
        bpath = Path(backup)
        if bpath.exists():
            manifest["hashes"][backup] = sha256_file(bpath)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch v47.3.1: corrige closure_deficit 0.0 e preempção inicial.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.3.1 — FIXES DE PERSISTÊNCIA")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    total = 0
    backups: list[str | None] = []

    changes, backup = patch_file(TENSION_MODULE, patch_tension_module, args.dry_run)
    total += changes
    backups.append(backup)

    changes, backup = patch_file(V47_FILE, patch_v47_file, args.dry_run)
    total += changes
    backups.append(backup)

    db_fixes = fix_existing_rows(args.dry_run)

    print()
    if total == 0 and db_fixes == 0:
        print("Nenhuma mudança necessária.")
        return 0

    if args.dry_run:
        print(f"Dry-run concluído. Mudanças planejadas em arquivos: {total}; correções DB: {db_fixes}")
        write_manifest(total, db_fixes, backups, dry_run=True)
        return 0

    if not compile_files():
        print()
        print("Patch aplicado, mas houve falha de compilação. Use os backups se precisar restaurar.")
        return 2

    write_manifest(total, db_fixes, backups, dry_run=False)

    print()
    print("Patch v47.3.1 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_2_multi_tension_test.py")
    print("  py darwin_tension_dashboard_v47.py --all")
    print("  py darwin_v47_2_multi_tension_test.py --purge-multi-tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
