from __future__ import annotations

"""
DARWIN v48.6 — Repair do freeze stable

Corrige:
    NameError: name 'live_v48_1_ready' is not defined

Causa:
    O script de freeze chama live_v48_1_ready(conn), mas a função genérica
    disponível no arquivo é live_basic(conn, table, min_insert=3).

Uso:
    py darwin_repair_v48_6_freeze_nameerror.py
    py darwin_freeze_v48_6_stable.py --dry-run
    py darwin_freeze_v48_6_stable.py
"""

import py_compile
from datetime import datetime, timezone
from pathlib import Path


TARGET = Path("darwin_freeze_v48_6_stable.py")
BACKUP_DIR = Path("v48_patch_backups")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def main() -> int:
    print("=" * 72)
    print("DARWIN v48.6 — REPAIR DO FREEZE STABLE")
    print("=" * 72)

    if not TARGET.exists():
        print(f"[ERRO] arquivo não encontrado: {TARGET}")
        print("Coloque este repair na pasta darwin_local.")
        return 2

    text = TARGET.read_text(encoding="utf-8")

    old = "live1 = live_v48_1_ready(conn)"
    new = 'live1 = live_basic(conn, "geometry_live_actions_v48_1")'

    if old not in text:
        if new in text:
            print("[OK] o arquivo já parece corrigido.")
            try:
                py_compile.compile(str(TARGET), doraise=True)
                print("[OK] py_compile passou.")
                return 0
            except Exception as exc:
                print("[ERRO] py_compile falhou mesmo assim:")
                print(exc)
                return 2

        print("[ERRO] trecho esperado não encontrado.")
        print("Não apliquei mudanças para evitar corromper o arquivo.")
        return 2

    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"darwin_freeze_v48_6_stable_pre_nameerror_repair_{stamp()}.py"
    backup.write_text(text, encoding="utf-8")
    print(f"[OK] backup criado: {backup}")

    text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] corrigido: {old} -> {new}")

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
    print("  py darwin_freeze_v48_6_stable.py --dry-run")
    print("  py darwin_freeze_v48_6_stable.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
