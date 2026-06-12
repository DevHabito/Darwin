from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
TENSION_MODULE = PROJECT_ROOT / "darwin_tension_persistence_v47.py"
CHECKER_FILE = PROJECT_ROOT / "darwin_check_v47_tensions.py"
BACKUP_DIR = PROJECT_ROOT / "v47_patch_backups"
MANIFEST_FILE = PROJECT_ROOT / "v47_1_hygiene_manifest.json"

OLD_BLOCK = '        self.record_event(\n            tension_id=tension_id,\n            event_type="case_upserted",\n            step=case_get(case, "last_event_step"),\n            status_after=str(enum_value(case_get(case, "status", "open"))),\n            pressure_after=float(case_get(case, "live_pressure", 0.0) or 0.0),\n            note="caso sincronizado com persistência v47",\n            payload=payload,\n        )\n'
NEW_BLOCK = '        if emit_event:\n            self.record_event(\n                tension_id=tension_id,\n                event_type="case_upserted",\n                step=case_get(case, "last_event_step"),\n                status_after=str(enum_value(case_get(case, "status", "open"))),\n                pressure_after=float(case_get(case, "live_pressure", 0.0) or 0.0),\n                note="caso sincronizado com persistência v47",\n                payload=payload,\n            )\n'


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_1_{now_stamp()}{path.suffix}"
    if dry_run:
        print_status("DRYRUN", f"criaria backup: {backup_path}")
        return str(backup_path)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    print_status("OK", f"backup criado: {backup_path}")
    return str(backup_path)


def replace_all(text: str, old: str, new: str, label: str) -> tuple[str, int]:
    count = text.count(old)
    if count == 0:
        print_status("AVISO", f"não encontrado: {label}")
        return text, 0
    text = text.replace(old, new)
    print_status("OK", f"{label}: {count} ocorrência(s)")
    return text, count


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, int]:
    if old not in text:
        print_status("AVISO", f"não encontrado: {label}")
        return text, 0
    text = text.replace(old, new, 1)
    print_status("OK", f"{label}: 1 ocorrência")
    return text, 1


def patch_v47_file(text: str) -> tuple[str, int]:
    changes = 0

    text, n = replace_all(text, 'source="nursery_v46"', 'source="nursery_v47"', "semantic_memory source nursery_v47")
    changes += n
    text, n = replace_all(text, "source='nursery_v46'", "source='nursery_v47'", "semantic_memory source nursery_v47 aspas simples")
    changes += n

    text, n = replace_all(text, 'module="nursery_v46"', 'module="nursery_v47"', "episode module nursery_v47")
    changes += n
    text, n = replace_all(text, "module='nursery_v46'", "module='nursery_v47'", "episode module nursery_v47 aspas simples")
    changes += n

    hydrate_anchor = "'nursery_v45', 'nursery_v46')"
    if "'nursery_v47'" not in text and hydrate_anchor in text:
        text = text.replace(hydrate_anchor, "'nursery_v45', 'nursery_v46', 'nursery_v47')", 1)
        print_status("OK", "hydrate_memory_from_home agora inclui nursery_v47")
        changes += 1
    elif "'nursery_v47'" in text:
        print_status("PULOU", "nursery_v47 já aparece no arquivo")
    else:
        print_status("AVISO", "não encontrei âncora para adicionar nursery_v47 na hidratação")

    text, n = replace_all(text, "store.upsert_case(case)", "store.upsert_case(case, emit_event=False)", "upsert_case silencioso nos helpers v47")
    changes += n

    return text, changes


def patch_tension_module(text: str) -> tuple[str, int]:
    changes = 0

    text, n = replace_once(
        text,
        "    def upsert_case(self, case: Any) -> None:\n",
        "    def upsert_case(self, case: Any, emit_event: bool = True) -> None:\n",
        "assinatura upsert_case emit_event",
    )
    changes += n

    text, n = replace_once(text, OLD_BLOCK, NEW_BLOCK, "case_upserted agora é opcional")
    changes += n

    return text, changes


def patch_checker(text: str) -> tuple[str, int]:
    changes = 0
    text, n = replace_once(text, '    text = str(value or "")\n', '    text = "" if value is None else str(value)\n', "checker preserva 0.0")
    changes += n
    return text, changes


def patch_file(path: Path, patcher, dry_run: bool) -> tuple[int, str | None]:
    if not path.exists():
        print_status("AUSENTE", f"{path.name}; pulando")
        return 0, None

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


def compile_files() -> bool:
    ok = True
    for path in (V47_FILE, TENSION_MODULE, CHECKER_FILE):
        if not path.exists():
            continue
        try:
            py_compile.compile(str(path), doraise=True)
            print_status("OK", f"py_compile passou: {path.name}")
        except py_compile.PyCompileError as exc:
            print_status("ERRO", f"py_compile falhou: {path.name}")
            print(str(exc))
            ok = False
    return ok


def write_manifest(total_changes: int, backups: list[str | None], dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.1_hygiene",
        "total_changes": total_changes,
        "files": {
            "v47": str(V47_FILE),
            "tension_module": str(TENSION_MODULE),
            "checker": str(CHECKER_FILE),
        },
        "backups": [b for b in backups if b],
        "hashes": {},
    }

    for path in (V47_FILE, TENSION_MODULE, CHECKER_FILE):
        if path.exists():
            manifest["hashes"][str(path)] = sha256_file(path)

    for backup in manifest["backups"]:
        bpath = Path(backup)
        if bpath.exists():
            manifest["hashes"][backup] = sha256_file(bpath)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch v47.1: higiene de persistência e identidade.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.1 — HIGIENE DE PERSISTÊNCIA")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if not V47_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {V47_FILE}")
    if not TENSION_MODULE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {TENSION_MODULE}")

    total = 0
    backups: list[str | None] = []

    changes, backup = patch_file(V47_FILE, patch_v47_file, args.dry_run)
    total += changes
    backups.append(backup)

    changes, backup = patch_file(TENSION_MODULE, patch_tension_module, args.dry_run)
    total += changes
    backups.append(backup)

    changes, backup = patch_file(CHECKER_FILE, patch_checker, args.dry_run)
    total += changes
    backups.append(backup)

    print()
    if total == 0:
        print("Nenhuma mudança aplicada.")
        return 0

    if args.dry_run:
        print(f"Dry-run concluído. Mudanças planejadas: {total}")
        write_manifest(total, backups, dry_run=True)
        return 0

    if not compile_files():
        print()
        print("Patch aplicado, mas houve falha de compilação. Use os backups se precisar restaurar.")
        return 2

    write_manifest(total, backups, dry_run=False)

    print()
    print("Patch v47.1 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_smoke_test_tension.py")
    print("  py darwin_check_v47_tensions.py --details")
    print("  py darwin_v47_smoke_test_tension.py --purge-smoke-tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
