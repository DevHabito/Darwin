from __future__ import annotations

"""
DARWIN v47.9.1 — Repair do Operador compare_context

Problema corrigido:
- O patch v47.9 inseriu o bloco que usa compare_context_summary,
  mas não conseguiu inserir a inicialização/chamada:

      compare_context_summary = ""
      if stage == "compare_context_before_prediction":
          compare_context_summary = self._v47_9_run_compare_context(case)

- Resultado:
      NameError: name 'compare_context_summary' is not defined

Este repair:
1. Faz backup do darwin_v61_nursery_v47.py atual.
2. Insere a inicialização/chamada logo após:
      stage, next_action = self._v47_7_stage_for_case(case)
3. Compila com py_compile.
4. Cria manifest.

Uso:
    py darwin_repair_v47_9_1_compare_context.py --dry-run
    py darwin_repair_v47_9_1_compare_context.py

Depois:
    py darwin_v47_9_compare_context_operator_test.py --dry-run
    py darwin_v47_9_compare_context_operator_test.py
"""

import argparse
import hashlib
import json
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
BACKUP_DIR = PROJECT_ROOT / "v47_patch_backups"
MANIFEST_FILE = PROJECT_ROOT / "v47_9_1_compare_context_repair_manifest.json"


STAGE_LINE = '        stage, next_action = self._v47_7_stage_for_case(case)\n'

INSERT_BLOCK = (
    '        compare_context_summary = ""\n'
    '        if stage == "compare_context_before_prediction":\n'
    '            compare_context_summary = self._v47_9_run_compare_context(case)\n'
)


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


def compiles(path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def backup_file(path: Path, dry_run: bool) -> str:
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_9_1_repair_{now_stamp()}{path.suffix}"

    if dry_run:
        print_status("DRYRUN", f"criaria backup: {backup_path}")
        return str(backup_path)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    print_status("OK", f"backup criado: {backup_path}")
    return str(backup_path)


def patch_text(text: str) -> tuple[str, int]:
    if "def _v47_9_run_compare_context" not in text:
        raise RuntimeError(
            "Não encontrei _v47_9_run_compare_context. "
            "O patch v47.9 parece não estar aplicado."
        )

    if 'if compare_context_summary:' not in text:
        raise RuntimeError(
            "Não encontrei o bloco que usa compare_context_summary. "
            "Este repair é específico para o patch v47.9 parcial."
        )

    if 'compare_context_summary = ""' in text:
        print_status("PULOU", "compare_context_summary já está inicializado")
        return text, 0

    idx = text.find(STAGE_LINE)
    if idx < 0:
        raise RuntimeError(
            "Não encontrei a linha stage,next_action esperada na micro-rotina."
        )

    insert_at = idx + len(STAGE_LINE)

    patched = text[:insert_at] + INSERT_BLOCK + text[insert_at:]
    print_status("OK", "inicialização/chamada compare_context_summary inserida")
    return patched, 1


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "repair": "v47.9.1_compare_context_summary_initialization",
        "changes": changes,
        "file": str(V47_FILE),
        "backup": backup,
        "hashes": {},
    }

    for path in (V47_FILE, Path(backup)):
        if path.exists():
            manifest["hashes"][str(path)] = sha256_file(path)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair v47.9.1: inicializa compare_context_summary.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.9.1 — REPAIR compare_context")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if not V47_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {V47_FILE}")

    ok_before, err_before = compiles(V47_FILE)
    if ok_before:
        print_status("OK", "arquivo atual compila antes do repair")
    else:
        print_status("AVISO", "arquivo atual não compila antes do repair")
        print(err_before)

    original = V47_FILE.read_text(encoding="utf-8")
    patched, changes = patch_text(original)

    if changes == 0:
        print()
        print("Nenhuma mudança necessária.")
        return 0

    backup = backup_file(V47_FILE, dry_run=args.dry_run)

    if args.dry_run:
        print_status("DRYRUN", f"aplicaria {changes} mudança(s) em {V47_FILE.name}")
        write_manifest(changes, backup, dry_run=True)
        return 0

    V47_FILE.write_text(patched, encoding="utf-8")
    print_status("OK", f"{changes} mudança(s) aplicada(s) em {V47_FILE.name}")

    ok_after, err_after = compiles(V47_FILE)
    if not ok_after:
        print_status("ERRO", "py_compile falhou após repair")
        print(err_after)
        print("Use o backup se precisar restaurar.")
        return 2

    print_status("OK", "py_compile passou após repair")
    write_manifest(changes, backup, dry_run=False)

    print()
    print("Repair v47.9.1 concluído.")
    print("Agora rode:")
    print("  py darwin_v47_9_compare_context_operator_test.py --dry-run")
    print("  py darwin_v47_9_compare_context_operator_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
