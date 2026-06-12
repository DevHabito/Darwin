from __future__ import annotations

"""
DARWIN v47.8.1 — Repair Seguro do Seletor Ampliado

Este script corrige a falha do repair anterior, que ainda podia gerar:

    SyntaxError: unterminated string literal
    line 4556: return "

Estratégia v2:
- restaurar o backup limpo pré-v47.8;
- reaplicar o seletor v47.8 usando chr(10).join(...), sem strings "\\n";
- compilar com py_compile;
- criar manifest.

Uso:
    py darwin_repair_v47_8_1_resolution_policy.py --dry-run
    py darwin_repair_v47_8_1_resolution_policy.py

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
MANIFEST_FILE = PROJECT_ROOT / "v47_8_1_resolution_policy_repair_manifest.json"


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


def latest_clean_v47_8_backup() -> Path | None:
    """
    O backup pre_v47_8 é criado ANTES do patch v47.8 alterar o arquivo.
    Portanto ele deve ser o estado limpo v47.7.
    """
    if not BACKUP_DIR.exists():
        return None

    backups = sorted(
        BACKUP_DIR.glob("darwin_v61_nursery_v47_pre_v47_8_*.py"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups[0] if backups else None


def make_repair_backup(dry_run: bool) -> Path:
    repair_backup = BACKUP_DIR / f"darwin_v61_nursery_v47_pre_repair_v47_8_1_{now_stamp()}.py"
    if dry_run:
        print_status("DRYRUN", f"criaria backup do arquivo atual: {repair_backup}")
        return repair_backup

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(V47_FILE, repair_backup)
    print_status("OK", f"backup do arquivo atual criado: {repair_backup}")
    return repair_backup


def restore_clean_backup(dry_run: bool) -> tuple[Path, Path]:
    backup = latest_clean_v47_8_backup()
    if backup is None:
        raise FileNotFoundError(
            "Não encontrei backup pré-v47.8 em v47_patch_backups/. "
            "Procure por darwin_v61_nursery_v47_pre_v47_8_*.py."
        )

    print_status("INFO", f"backup limpo a restaurar: {backup}")
    repair_backup = make_repair_backup(dry_run=dry_run)

    if dry_run:
        print_status("DRYRUN", f"restauraria {backup} -> {V47_FILE}")
        return backup, repair_backup

    shutil.copy2(backup, V47_FILE)
    print_status("OK", f"arquivo restaurado a partir de: {backup}")

    ok, error = compiles(V47_FILE)
    if not ok:
        raise RuntimeError(f"Backup restaurado não compila:\n{error}")

    print_status("OK", "arquivo restaurado compila")
    return backup, repair_backup


def stage_block() -> str:
    """
    Monta código-fonte sem usar "\\n" dentro do código gerado.
    Usa chr(10).join(...) para evitar qualquer string quebrada.
    """
    lines = [
        '    def _v47_7_stage_for_case(self, case: "LiveTensionCase") -> tuple[str, str]:',
        '        """',
        '        v47.8.1 — seletor ampliado de micro-rotina.',
        '',
        '        Retorna:',
        '            (stage, executable_action)',
        '',
        '        A política distingue mais tipos de reparo, mas ainda retorna apenas',
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
        '            return "reduce_saturation_before_retry", "predict"',
        '',
        '        if inherited and ambiguity >= 0.25:',
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
        '            return chr(10).join(',
        '                [',
        '                    "SELETOR DE MICRO-ROTINA v47.8.1",',
        '                    "- nenhuma tensão ativa no runtime",',
        '                ]',
        '            )',
        '',
        '        if not self._v47_6_case_is_actionable(case):',
        '            return chr(10).join(',
        '                [',
        '                    "SELETOR DE MICRO-ROTINA v47.8.1",',
        '                    f"- tensão {case.tension_id} não acionável ou já fechada",',
        '                ]',
        '            )',
        '',
        '        stage, action = self._v47_7_stage_for_case(case)',
        '        inherited = list(getattr(case, "inherited_pairs", ()) or [])',
        '',
        '        return chr(10).join(',
        '            [',
        '                "SELETOR DE MICRO-ROTINA v47.8.1",',
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
    return chr(10).join(lines)


def replace_stage_function(text: str) -> tuple[str, int]:
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

    print_status("OK", "seletor ampliado v47.8.1 inserido com chr(10).join")
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

    old_invalid = '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c ou 10m.")\n'
    new_invalid = '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m ou 10p.")\n'
    text, n = replace_once(text, old_invalid, new_invalid, "mensagem de comando inválido inclui 10p")
    changes += n

    return text, changes


def apply_patch(dry_run: bool) -> int:
    text = V47_FILE.read_text(encoding="utf-8")

    total = 0
    text, n = replace_stage_function(text)
    total += n
    text, n = patch_menu(text)
    total += n

    if dry_run:
        print_status("DRYRUN", f"aplicaria {total} mudança(s) v47.8.1")
        return total

    V47_FILE.write_text(text, encoding="utf-8")
    print_status("OK", f"{total} mudança(s) v47.8.1 aplicadas")
    return total


def write_manifest(restored_from: Path, repair_backup: Path, changes: int, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "repair": "v47.8.1_resolution_policy_safe_repair",
        "restored_from": str(restored_from),
        "repair_backup": str(repair_backup),
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
    parser = argparse.ArgumentParser(description="Repara v47.8 usando chr(10).join para evitar string quebrada.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.8.1 — REPAIR SEGURO DO SELETOR")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if not V47_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {V47_FILE}")

    restored_from, repair_backup = restore_clean_backup(dry_run=args.dry_run)
    changes = apply_patch(dry_run=args.dry_run)

    if args.dry_run:
        print_status("DRYRUN", "validaria py_compile depois da escrita")
        write_manifest(restored_from, repair_backup, changes, dry_run=True)
        return 0

    ok, error = compiles(V47_FILE)
    if not ok:
        print_status("ERRO", "arquivo ainda não compila após repair v47.8.1")
        print(error)
        return 2

    print_status("OK", "py_compile passou após repair v47.8.1")
    write_manifest(restored_from, repair_backup, changes, dry_run=False)

    print()
    print("Repair v47.8.1 concluído.")
    print("Agora rode:")
    print("  py darwin_v47_8_resolution_policy_test.py --dry-run")
    print("  py darwin_v47_8_resolution_policy_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
