from __future__ import annotations

'''
DARWIN v48.9 — Repair do diagnóstico de falha detectada

Corrige:
    Verificação "revisão: falha detectada" dando FALHOU apesar do evento existir.

Causa:
    O checker esperava:
        plan_failure_detected + observed_outcome == "failure"

    Mas o runtime registrou corretamente a falha específica:
        observed_outcome == "hidden_depth_failure"

    Isso é mais informativo e deve ser aceito pelo diagnóstico.

Uso:
    py darwin_repair_v48_9_check_failure_detected.py
    py darwin_check_v48_9_multistep_planning.py
    py darwin_check_v48_9_multistep_planning.py --details
'''

import py_compile
from datetime import datetime, timezone
from pathlib import Path


TARGET = Path("darwin_check_v48_9_multistep_planning.py")
BACKUP_DIR = Path("v48_patch_backups")


OLD = '''        "revision_failure_detected": has(rs, "plan_failure_detected", "task_revision_hidden_depth", outcome="failure"),'''
NEW = '''        "revision_failure_detected": has(rs, "plan_failure_detected", "task_revision_hidden_depth", outcome="hidden_depth_failure"),'''


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def main() -> int:
    print("=" * 72)
    print("DARWIN v48.9 — REPAIR DO CHECKER DE FALHA DETECTADA")
    print("=" * 72)

    if not TARGET.exists():
        print(f"[ERRO] arquivo não encontrado: {TARGET}")
        print("Coloque este repair na pasta darwin_local.")
        return 2

    text = TARGET.read_text(encoding="utf-8")

    if NEW in text:
        print("[OK] o checker já parece corrigido.")
        try:
            py_compile.compile(str(TARGET), doraise=True)
            print("[OK] py_compile passou.")
            return 0
        except Exception as exc:
            print("[ERRO] py_compile falhou mesmo assim:")
            print(exc)
            return 2

    if OLD not in text:
        print("[ERRO] trecho esperado não encontrado.")
        print("Não apliquei mudanças para evitar corromper o arquivo.")
        print("Procure manualmente por revision_failure_detected no checker.")
        return 2

    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"darwin_check_v48_9_pre_failure_detected_repair_{stamp()}.py"
    backup.write_text(text, encoding="utf-8")
    print(f"[OK] backup criado: {backup}")

    text = text.replace(OLD, NEW, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("[OK] checker corrigido: agora aceita observed_outcome='hidden_depth_failure'.")

    try:
        py_compile.compile(str(TARGET), doraise=True)
        print("[OK] py_compile passou.")
    except Exception as exc:
        print("[ERRO] py_compile falhou após repair:")
        print(exc)
        print(f"Restaure o backup se precisar: {backup}")
        return 2

    print()
    print("Agora rode:")
    print("  py darwin_check_v48_9_multistep_planning.py")
    print("  py darwin_check_v48_9_multistep_planning.py --details")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
