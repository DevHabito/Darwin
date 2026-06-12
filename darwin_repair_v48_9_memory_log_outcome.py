from __future__ import annotations

'''
DARWIN v48.9 — Repair do Memory.log outcome

Corrige:
    TypeError: Memory.log() got an unexpected keyword argument 'outcome'

Causa:
    O visualizador v48.9 chama Memory.log(..., outcome="..."),
    mas a assinatura inicial aceitava observed_outcome=... e não outcome=....

Correção:
    - adiciona outcome: str = "" na assinatura;
    - quando observed_outcome não foi passado, usa outcome como observed_outcome;
    - preserva final_status e os demais campos.

Uso:
    py darwin_repair_v48_9_memory_log_outcome.py
    py darwin_multistep_planning_v48_9.py
'''

import py_compile
from datetime import datetime, timezone
from pathlib import Path


TARGET = Path("darwin_multistep_planning_v48_9.py")
BACKUP_DIR = Path("v48_patch_backups")


OLD_SIGNATURE = '''    def log(
        self,
        sid: str,
        action_kind: str,
        task: Task | None = None,
        plan: Plan | None = None,
        step: PlanStep | None = None,
        decision: str = "",
        observed_outcome: str = "",
        final_status: str = "",
        payload=None,
    ) -> None:
        if not self.enabled:
            return

        payload = payload or {}
'''

NEW_SIGNATURE = '''    def log(
        self,
        sid: str,
        action_kind: str,
        task: Task | None = None,
        plan: Plan | None = None,
        step: PlanStep | None = None,
        decision: str = "",
        outcome: str = "",
        observed_outcome: str = "",
        final_status: str = "",
        payload=None,
    ) -> None:
        if not self.enabled:
            return

        if outcome and not observed_outcome:
            observed_outcome = outcome

        payload = payload or {}
'''


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def main() -> int:
    print("=" * 72)
    print("DARWIN v48.9 — REPAIR MEMORY.LOG OUTCOME")
    print("=" * 72)

    if not TARGET.exists():
        print(f"[ERRO] arquivo não encontrado: {TARGET}")
        print("Coloque este repair na pasta darwin_local.")
        return 2

    text = TARGET.read_text(encoding="utf-8")

    if NEW_SIGNATURE in text:
        print("[OK] o arquivo já parece corrigido.")
        try:
            py_compile.compile(str(TARGET), doraise=True)
            print("[OK] py_compile passou.")
            return 0
        except Exception as exc:
            print("[ERRO] py_compile falhou mesmo assim:")
            print(exc)
            return 2

    if OLD_SIGNATURE not in text:
        print("[ERRO] trecho esperado não encontrado.")
        print("Não apliquei mudanças para evitar corromper o arquivo.")
        return 2

    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"darwin_multistep_planning_v48_9_pre_memory_log_outcome_{stamp()}.py"
    backup.write_text(text, encoding="utf-8")
    print(f"[OK] backup criado: {backup}")

    text = text.replace(OLD_SIGNATURE, NEW_SIGNATURE, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("[OK] assinatura Memory.log corrigida para aceitar outcome=...")

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
    print("  py darwin_multistep_planning_v48_9.py")
    print()
    print("Depois do ciclo visual, rode:")
    print("  py darwin_check_v48_9_multistep_planning.py")
    print("  py darwin_check_v48_9_multistep_planning.py --details")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
