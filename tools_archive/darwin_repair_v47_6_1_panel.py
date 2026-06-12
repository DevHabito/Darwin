from __future__ import annotations

"""
DARWIN v47.6.1 — Repair + Patch Seguro do Painel 10c

Este script corrige a falha causada pelo patch anterior:

    SyntaxError: unterminated string literal
    line 4263: return "

O que ele faz:
1. Procura o backup mais recente:
   v47_patch_backups/darwin_v61_nursery_v47_pre_v47_6_1_*.py

2. Se o arquivo atual não compilar, restaura esse backup.

3. Aplica novamente o patch v47.6.1 usando substituição por bloco de função,
   evitando o bug de string quebrada em return "\\n".join(...).

4. Compila darwin_v61_nursery_v47.py com py_compile.

Uso:
    py darwin_repair_v47_6_1_panel.py --dry-run
    py darwin_repair_v47_6_1_panel.py

Depois:
    py darwin_v47_6_1_commitment_panel_test.py --dry-run
    py darwin_v47_6_1_commitment_panel_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_6_1_panel_repair_manifest.json"


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


def latest_v47_6_1_backup() -> Path | None:
    if not BACKUP_DIR.exists():
        return None
    backups = sorted(
        BACKUP_DIR.glob("darwin_v61_nursery_v47_pre_v47_6_1_*.py"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups[0] if backups else None


def make_repair_backup(dry_run: bool) -> Path:
    repair_backup = BACKUP_DIR / f"darwin_v61_nursery_v47_pre_repair_v47_6_1_{now_stamp()}.py"
    if dry_run:
        print_status("DRYRUN", f"criaria backup do arquivo atual quebrado: {repair_backup}")
        return repair_backup

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(V47_FILE, repair_backup)
    print_status("OK", f"backup do arquivo atual criado: {repair_backup}")
    return repair_backup


def restore_if_needed(dry_run: bool, force_restore: bool = False) -> tuple[bool, Path | None, Path | None]:
    ok, error = compiles(V47_FILE)

    if ok and not force_restore:
        print_status("OK", "darwin_v61_nursery_v47.py já compila; restauração não necessária")
        return False, None, None

    if not ok:
        print_status("ERRO", "arquivo atual não compila")
        first_line = error.splitlines()[0] if error else "erro desconhecido"
        print_status("INFO", first_line)

    backup = latest_v47_6_1_backup()
    if backup is None:
        raise FileNotFoundError(
            "Não encontrei backup v47.6.1 em v47_patch_backups/. "
            "Procure manualmente o arquivo darwin_v61_nursery_v47_pre_v47_6_1_*.py."
        )

    print_status("INFO", f"backup a restaurar: {backup}")

    repair_backup = make_repair_backup(dry_run=dry_run)

    if dry_run:
        print_status("DRYRUN", f"restauraria {backup} -> {V47_FILE}")
        return True, backup, repair_backup

    shutil.copy2(backup, V47_FILE)
    print_status("OK", f"arquivo restaurado a partir de: {backup}")

    ok_after, err_after = compiles(V47_FILE)
    if not ok_after:
        raise RuntimeError(f"Backup restaurado também não compila:\n{err_after}")

    print_status("OK", "arquivo restaurado compila")
    return True, backup, repair_backup


def new_summary_block() -> str:
    lines = [
        '    def executive_commitment_summary(self) -> str:',
        '        """',
        '        Relatório do compromisso executivo.',
        '',
        '        v47.6.1:',
        '        - se já houve uma decisão comprometida nesta sessão, mostra essa decisão;',
        '        - se ainda não houve, mas existe tensão ativa aberta/reidratada, mostra',
        '          a dívida executiva aguardando o próximo passo autônomo;',
        '        - se não há tensão ativa, informa que não existe foco executivo pendente.',
        '        """',
        '        lines = list(getattr(self, "last_executive_commitment_lines", []))',
        '',
        '        if lines and not (',
        '            len(lines) >= 2',
        '            and "ainda não houve decisão comprometida" in str(lines[1])',
        '        ):',
        '            return "\\\\n".join(lines)',
        '',
        '        active_id = getattr(self, "active_tension_id", None)',
        '        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None',
        '',
        '        if case is not None and self._v47_6_case_is_actionable(case):',
        '            pending = self._v47_6_pending_hypothesis_for_pair(case.source_lower, case.source_upper)',
        '            next_action = "validate" if pending is not None else "predict"',
        '',
        '            return "\\\\n".join(',
        '                [',
        '                    "COMPROMISSO EXECUTIVO v47.6.1",',
        '                    f"- dívida executiva ativa: {case.tension_id} ({case.source_pair})",',
        '                    f"- status: {case.status.value} | pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f}",',
        '                    f"- próximo ato esperado: {next_action}({case.source_pair})",',
        '                    "- aguardando o próximo passo autônomo para cumprir essa pendência",',
        '                ]',
        '            )',
        '',
        '        if active_id:',
        '            return "\\\\n".join(',
        '                [',
        '                    "COMPROMISSO EXECUTIVO v47.6.1",',
        '                    f"- foco executivo {active_id} não acionável ou já fechado",',
        '                ]',
        '            )',
        '',
        '        return "\\\\n".join(',
        '            [',
        '                "COMPROMISSO EXECUTIVO v47.6.1",',
        '                "- nenhuma dívida executiva ativa no runtime",',
        '            ]',
        '        )',
        '',
        '',
    ]

    # A lista acima usa "\\\\n" no texto do script gerado; precisamos virar "\\n" no arquivo Python final.
    return "\n".join(lines).replace('return "\\\\n".join', 'return "\\n".join')


def replace_function_block(text: str, function_name: str, replacement: str) -> tuple[str, bool]:
    marker = f"    def {function_name}("
    start = text.find(marker)
    if start < 0:
        return text, False

    # Procura o próximo método no mesmo nível de indentação.
    next_def = text.find("\n    def ", start + 1)
    while next_def != -1:
        candidate = text[next_def + 1 : next_def + 10]
        if candidate.startswith("    def "):
            break
        next_def = text.find("\n    def ", next_def + 1)

    if next_def == -1:
        end = len(text)
    else:
        end = next_def + 1

    patched = text[:start] + replacement + text[end:]
    return patched, True


def patch_panel(dry_run: bool) -> int:
    text = V47_FILE.read_text(encoding="utf-8")

    if "COMPROMISSO EXECUTIVO v47.6.1" in text and 'return "\n".join(lines)' in text:
        print_status("OK", "painel v47.6.1 já parece corrigido")
        return 0

    replacement = new_summary_block()
    patched, found = replace_function_block(text, "executive_commitment_summary", replacement)

    if not found:
        raise RuntimeError("Não encontrei a função executive_commitment_summary para substituir.")

    if dry_run:
        print_status("DRYRUN", "substituiria executive_commitment_summary por versão v47.6.1 segura")
        return 1

    V47_FILE.write_text(patched, encoding="utf-8")
    print_status("OK", "executive_commitment_summary substituída por versão v47.6.1 segura")
    return 1


def write_manifest(restored: bool, restored_from: Path | None, repair_backup: Path | None, changes: int, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "repair": "v47.6.1_panel_repair",
        "restored": restored,
        "restored_from": str(restored_from) if restored_from else None,
        "repair_backup": str(repair_backup) if repair_backup else None,
        "changes": changes,
        "file": str(V47_FILE),
        "hashes": {},
    }

    for path in (V47_FILE, restored_from, repair_backup):
        if path and path.exists():
            manifest["hashes"][str(path)] = sha256_file(path)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repara e reaplica o painel v47.6.1 com segurança.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever.")
    parser.add_argument("--force-restore", action="store_true", help="Restaura backup mesmo se o arquivo atual compilar.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.6.1 — REPAIR DO PAINEL 10c")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if not V47_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {V47_FILE}")

    restored, restored_from, repair_backup = restore_if_needed(
        dry_run=args.dry_run,
        force_restore=args.force_restore,
    )

    changes = patch_panel(dry_run=args.dry_run)

    if args.dry_run:
        print_status("DRYRUN", "validaria py_compile depois da escrita")
        write_manifest(restored, restored_from, repair_backup, changes, dry_run=True)
        return 0

    ok, error = compiles(V47_FILE)
    if not ok:
        print_status("ERRO", "arquivo ainda não compila após repair")
        print(error)
        return 2

    print_status("OK", "py_compile passou após repair")
    write_manifest(restored, restored_from, repair_backup, changes, dry_run=False)

    print()
    print("Repair v47.6.1 concluído.")
    print("Agora rode:")
    print("  py darwin_v47_6_1_commitment_panel_test.py --dry-run")
    print("  py darwin_v47_6_1_commitment_panel_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
