from __future__ import annotations

"""
DARWIN v47.8 — Repair + Patch Seguro do Seletor de Micro-Rotina

Corrige a falha causada pelo patch v47.8 anterior:

    SyntaxError: unterminated string literal
    line 4556: return "

O que este script faz:
1. Detecta se darwin_v61_nursery_v47.py compila.
2. Se não compilar, restaura o backup mais recente:
   v47_patch_backups/darwin_v61_nursery_v47_pre_v47_8_*.py
3. Reaplica o patch v47.8 usando blocos montados linha a linha,
   evitando string quebrada em return "\\n".join(...).
4. Compila com py_compile.
5. Cria manifest de reparo.

Uso:
    py darwin_repair_v47_8_resolution_policy.py --dry-run
    py darwin_repair_v47_8_resolution_policy.py

Depois:
    py darwin_v47_8_resolution_policy_test.py --dry-run
    py darwin_v47_8_resolution_policy_test.py
"""

import argparse
import hashlib
import json
import py_compile
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
BACKUP_DIR = PROJECT_ROOT / "v47_patch_backups"
MANIFEST_FILE = PROJECT_ROOT / "v47_8_resolution_policy_repair_manifest.json"


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


def latest_v47_8_backup() -> Path | None:
    if not BACKUP_DIR.exists():
        return None
    backups = sorted(
        BACKUP_DIR.glob("darwin_v61_nursery_v47_pre_v47_8_*.py"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups[0] if backups else None


def make_repair_backup(dry_run: bool) -> Path:
    repair_backup = BACKUP_DIR / f"darwin_v61_nursery_v47_pre_repair_v47_8_{now_stamp()}.py"
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

    backup = latest_v47_8_backup()
    if backup is None:
        raise FileNotFoundError(
            "Não encontrei backup v47.8 em v47_patch_backups/. "
            "Procure manualmente por darwin_v61_nursery_v47_pre_v47_8_*.py."
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


def stage_block() -> str:
    lines = [
        '    def _v47_7_stage_for_case(self, case: "LiveTensionCase") -> tuple[str, str]:',
        '        """',
        '        v47.8 — seletor ampliado de micro-rotina.',
        '',
        '        Retorna:',
        '            (stage, executable_action)',
        '',
        '        A política já distingue mais tipos de reparo, mas ainda retorna apenas',
        '        action_name executável e seguro para o runtime atual: predict/validate.',
        '        """',
        '        pending = self._v47_6_pending_hypothesis_for_pair(case.source_lower, case.source_upper)',
        '',
        '        if pending is not None:',
        '            return "validate_pending_hypothesis", "validate"',
        '',
        '        saturation = float(getattr(case, "saturation_cost", 0.0) or 0.0)',
        '        probe_count = int(getattr(case, "probe_count", 0) or 0)',
        '        inherited = list(getattr(case, "inherited_pairs", ()) or ())',
        '        ambiguity = float(getattr(case, "ambiguity_score", 0.0) or 0.0)',
        '        closure_deficit = float(getattr(case, "closure_deficit", 0.0) or 0.0)',
        '',
        '        if saturation >= 0.65 or probe_count >= 3:',
        '            # Futuro v48: consolidate/archive/weaken real.',
        '            # Agora: formular nova hipótese mínima para sair de repetição cega.',
        '            return "reduce_saturation_before_retry", "predict"',
        '',
        '        if inherited and ambiguity >= 0.25:',
        '            # Futuro v48: compare real entre pares herdados.',
        '            # Agora: registrar que a rotina exige comparação contextual antes do predict.',
        '            return "compare_context_before_prediction", "predict"',
        '',
        '        if case.status == TensionStatus.PROBING:',
        '            return "repair_missing_prediction", "predict"',
        '',
        '        if closure_deficit >= 0.75:',
        '            return "formulate_probe_hypothesis", "predict"',
        '',
        '        return "low_deficit_probe_check", "predict"',
        '',
        '    def tension_resolution_policy_summary(self) -> str:',
        '        active_id = getattr(self, "active_tension_id", None)',
        '        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None',
        '',
        '        if case is None:',
        '            return "\\n".join(',
        '                [',
        '                    "SELETOR DE MICRO-ROTINA v47.8",',
        '                    "- nenhuma tensão ativa no runtime",',
        '                ]',
        '            )',
        '',
        '        if not self._v47_6_case_is_actionable(case):',
        '            return "\\n".join(',
        '                [',
        '                    "SELETOR DE MICRO-ROTINA v47.8",',
        '                    f"- tensão {case.tension_id} não acionável ou já fechada",',
        '                ]',
        '            )',
        '',
        '        stage, action = self._v47_7_stage_for_case(case)',
        '        inherited = list(getattr(case, "inherited_pairs", ()) or [])',
        '',
        '        return "\\n".join(',
        '            [',
        '                "SELETOR DE MICRO-ROTINA v47.8",',
        '                f"- tensão ativa: {case.tension_id} ({case.source_pair})",',
        '                f"- estágio selecionado: {stage}",',
        '                f"- ação executável: {action}({case.source_pair})",',
        '                f"- pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f} | saturação={case.saturation_cost:.3f}",',
        '                f"- pares herdados considerados: {len(inherited)}",',
        '                "- operadores ricos ainda são classificados como estágio, não executados diretamente",',
        '            ]',
        '        )',
        '',
        '',
    ]
    return "\n".join(lines)


def replace_stage_function(text: str) -> tuple[str, int]:
    if "SELETOR DE MICRO-ROTINA v47.8" in text:
        print_status("PULOU", "seletor v47.8 já existe")
        return text, 0

    pattern = (
        r'    def _v47_7_stage_for_case\(self, case: "LiveTensionCase"\) -> tuple\[str, str\]:\n'
        r'.*?'
        r'(?=\n    def _v47_7_resolution_routine_plan\(self\))'
    )

    patched, n = re.subn(
        pattern,
        stage_block(),
        text,
        count=1,
        flags=re.DOTALL,
    )

    if n == 0:
        raise RuntimeError("Não encontrei _v47_7_stage_for_case para substituir.")

    print_status("OK", "seletor ampliado v47.8 inserido de forma segura")
    return patched, n


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, int]:
    if old not in text:
        print_status("AVISO", f"não encontrado: {label}")
        return text, 0
    text = text.replace(old, new, 1)
    print_status("OK", f"{label}: 1 ocorrência")
    return text, 1


def patch_menu(text: str) -> tuple[str, int]:
    changes = 0

    if "10p - mostrar seletor de política da micro-rotina" not in text:
        text, n = replace_once(
            text,
            '        print("10m - mostrar micro-rotina de resolução")\n',
            '        print("10m - mostrar micro-rotina de resolução")\n'
            '        print("10p - mostrar seletor de política da micro-rotina")\n',
            "menu adiciona comando 10p",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10p já existe")

    if 'choice in {"10p", "policy", "politica", "política"}' not in text:
        anchor = (
            '            elif choice in {"10m", "micro", "rotina", "routine"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.tension_resolution_routine_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10m", "micro", "rotina", "routine"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.tension_resolution_routine_summary())\n'
            '            elif choice in {"10p", "policy", "politica", "política"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.tension_resolution_policy_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10p",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10p já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c ou 10m.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m ou 10p.")\n',
        "mensagem de comando inválido inclui 10p",
    )
    changes += n

    return text, changes


def patch_policy(dry_run: bool) -> int:
    text = V47_FILE.read_text(encoding="utf-8")

    total = 0
    text, n = replace_stage_function(text)
    total += n
    text, n = patch_menu(text)
    total += n

    if dry_run:
        print_status("DRYRUN", f"aplicaria {total} mudança(s) seguras v47.8")
        return total

    V47_FILE.write_text(text, encoding="utf-8")
    print_status("OK", f"{total} mudança(s) v47.8 aplicadas com segurança")
    return total


def write_manifest(restored: bool, restored_from: Path | None, repair_backup: Path | None, changes: int, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "repair": "v47.8_resolution_policy_repair",
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
    parser = argparse.ArgumentParser(description="Repara e reaplica o seletor v47.8 com segurança.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever.")
    parser.add_argument("--force-restore", action="store_true", help="Restaura backup mesmo se o arquivo atual compilar.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.8 — REPAIR DO SELETOR AMPLIADO")
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

    changes = patch_policy(dry_run=args.dry_run)

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
    print("Repair v47.8 concluído.")
    print("Agora rode:")
    print("  py darwin_v47_8_resolution_policy_test.py --dry-run")
    print("  py darwin_v47_8_resolution_policy_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
