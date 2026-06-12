from __future__ import annotations

"""
DARWIN v47.4 — Integrar Painel Executivo ao Menu do Darwin

Este patch adiciona ao darwin_v61_nursery_v47.py:

  10  - mostrar memória executiva de tensões abertas
  10a - mostrar todas as tensões persistidas, inclusive fechadas

Também corrige:
  "Encerrando Darwin Nursery v46." -> "Encerrando Darwin Nursery v47."

O patch é pequeno e reversível:
- cria backup do arquivo antes de alterar;
- compila com py_compile depois;
- não altera o banco.

Uso:
    py darwin_patch_v47_4_menu_dashboard.py --dry-run
    py darwin_patch_v47_4_menu_dashboard.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_4_menu_dashboard_manifest.json"

MENU_ANCHOR = '    def menu(self) -> str:\n        return input("\\nEscolha: ").strip().lower()\n'
MENU_REPLACEMENT = '\n    def show_tension_dashboard(self, include_closed: bool = False, event_limit: int = 8) -> str:\n        """\n        Painel executivo interno da v47.\n\n        Lê diretamente as tabelas persistentes:\n        - tension_cases\n        - tension_events\n        - tension_probes\n        - tension_outcomes\n\n        Não altera o banco.\n        """\n        import sqlite3\n        from pathlib import Path\n\n        db_path = Path("darwin_home") / "darwin.db"\n        lines: List[str] = ["MEMÓRIA EXECUTIVA DE TENSÕES — v47"]\n\n        if not db_path.exists():\n            lines.append(f"(banco não encontrado: {db_path})")\n            return "\\n".join(lines)\n\n        def fmt(value, digits: int = 3) -> str:\n            if value is None:\n                return "-"\n            try:\n                return f"{float(value):.{digits}f}"\n            except Exception:\n                return str(value)\n\n        def short(value, limit: int = 120) -> str:\n            text = "" if value is None else str(value)\n            return text if len(text) <= limit else text[: limit - 1] + "…"\n\n        with sqlite3.connect(db_path) as conn:\n            conn.row_factory = sqlite3.Row\n\n            table = conn.execute(\n                "SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'tension_cases\'"\n            ).fetchone()\n            if table is None:\n                lines.append("(schema v47 de tensões ainda não existe)")\n                return "\\n".join(lines)\n\n            def count_table(name: str, where: str = "1=1") -> int:\n                exists = conn.execute(\n                    "SELECT name FROM sqlite_master WHERE type=\'table\' AND name=?",\n                    (name,),\n                ).fetchone()\n                if exists is None:\n                    return 0\n                row = conn.execute(f"SELECT COUNT(*) AS n FROM {name} WHERE {where}").fetchone()\n                return int(row["n"]) if row else 0\n\n            total = count_table("tension_cases")\n            opened = count_table("tension_cases", "status NOT IN (\'closed\', \'archived\', \'stale\')")\n            closed = count_table("tension_cases", "status=\'closed\'")\n            events = count_table("tension_events")\n            probes = count_table("tension_probes")\n            outcomes = count_table("tension_outcomes")\n\n            lines.append("- casos totais:    " + str(total))\n            lines.append("- casos abertos:   " + str(opened))\n            lines.append("- casos fechados:  " + str(closed))\n            lines.append("- eventos:         " + str(events))\n            lines.append("- sondas:          " + str(probes))\n            lines.append("- desfechos:       " + str(outcomes))\n            lines.append("")\n\n            where = "1=1" if include_closed else "status NOT IN (\'closed\', \'archived\', \'stale\')"\n            rows = conn.execute(\n                f"""\n                SELECT tension_id, source_pair, status, outcome,\n                       live_pressure, economic_priority, closure_deficit,\n                       saturation_cost, updated_at, semantic_summary\n                FROM tension_cases\n                WHERE {where}\n                ORDER BY\n                    CASE WHEN status IN (\'open\', \'probing\', \'reopened\') THEN 0 ELSE 1 END,\n                    economic_priority DESC,\n                    live_pressure DESC,\n                    updated_at DESC\n                LIMIT 12\n                """\n            ).fetchall()\n\n            lines.append("CASOS")\n            if not rows:\n                lines.append("(nenhum caso executivo para mostrar)")\n            for row in rows:\n                lines.append(\n                    f"- {row[\'tension_id\']} | {row[\'source_pair\']} | "\n                    f"status={row[\'status\']} | outcome={row[\'outcome\']} | "\n                    f"pressão={fmt(row[\'live_pressure\'])} | "\n                    f"prioridade={fmt(row[\'economic_priority\'])} | "\n                    f"déficit={fmt(row[\'closure_deficit\'])} | "\n                    f"sat={fmt(row[\'saturation_cost\'])}"\n                )\n                if row["semantic_summary"]:\n                    lines.append(f"  resumo={short(row[\'semantic_summary\'])}")\n\n            lines.append("")\n            lines.append(f"ÚLTIMOS {event_limit} EVENTOS")\n            exists_events = conn.execute(\n                "SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'tension_events\'"\n            ).fetchone()\n            if exists_events is None:\n                lines.append("(tabela tension_events ausente)")\n            else:\n                ev_rows = conn.execute(\n                    """\n                    SELECT tension_id, timestamp, event_type, status_after,\n                           pressure_after, note\n                    FROM tension_events\n                    ORDER BY id DESC\n                    LIMIT ?\n                    """,\n                    (max(1, int(event_limit)),),\n                ).fetchall()\n                if not ev_rows:\n                    lines.append("(nenhum evento)")\n                for ev in ev_rows:\n                    lines.append(\n                        f"- {ev[\'timestamp\']} | {ev[\'tension_id\']} | "\n                        f"{ev[\'event_type\']} | status={ev[\'status_after\']} | "\n                        f"pressão={fmt(ev[\'pressure_after\'])}"\n                    )\n                    if ev["note"]:\n                        lines.append(f"  nota={short(ev[\'note\'])}")\n\n        return "\\n".join(lines)\n\n    def menu(self) -> str:\n        return input("\\nEscolha: ").strip().lower()\n'
INTRO_OLD = '        print("  8 - reiniciar mundo local (mantendo memória persistente)")\n        print("  9 - sair")\n'
INTRO_NEW = '        print("  8 - reiniciar mundo local (mantendo memória persistente)")\n        print("  9 - sair")\n        print(" 10 - mostrar memória executiva de tensões abertas")\n        print("10a - mostrar todas as tensões persistidas")\n'
BRANCH_OLD = '            elif choice == "8":\n                print("\\n" + self.agent.reset_local_world())\n            elif choice in {"9", "sair", "exit", "quit"}:\n'
BRANCH_NEW = '            elif choice == "8":\n                print("\\n" + self.agent.reset_local_world())\n            elif choice in {"10", "tensoes", "tensões", "tension"}:\n                print("\\n" + "=" * 72)\n                print(self.show_tension_dashboard(include_closed=False))\n            elif choice in {"10a", "tensoes all", "tensões all", "tension all"}:\n                print("\\n" + "=" * 72)\n                print(self.show_tension_dashboard(include_closed=True))\n            elif choice in {"9", "sair", "exit", "quit"}:\n'


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_4_{now_stamp()}{path.suffix}"
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


def patch_v47(text: str) -> tuple[str, int]:
    changes = 0

    if "def show_tension_dashboard(self, include_closed: bool = False" not in text:
        text, n = replace_once(
            text,
            MENU_ANCHOR,
            MENU_REPLACEMENT,
            "método show_tension_dashboard inserido",
        )
        changes += n
    else:
        print_status("PULOU", "show_tension_dashboard já existe")

    text, n = replace_once(
        text,
        INTRO_OLD,
        INTRO_NEW,
        "menu adiciona comandos 10 e 10a",
    )
    changes += n

    text, n = replace_once(
        text,
        BRANCH_OLD,
        BRANCH_NEW,
        "run adiciona branches 10 e 10a",
    )
    changes += n

    text, n = replace_once(
        text,
        '                print("\\nEncerrando Darwin Nursery v46.")\n',
        '                print("\\nEncerrando Darwin Nursery v47.")\n',
        "mensagem de saída v47",
    )
    changes += n

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8 ou 9.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 ou 10a.")\n',
        "mensagem de comando inválido atualizada",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str | None, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.4_menu_dashboard",
        "changes": changes,
        "file": str(V47_FILE),
        "backup": backup,
        "hashes": {},
    }

    for path in (V47_FILE, Path(backup) if backup else None):
        if path and path.exists():
            manifest["hashes"][str(path)] = sha256_file(path)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Integra painel executivo de tensões ao menu do Darwin v47.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.4 — MENU COM PAINEL EXECUTIVO")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if not V47_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {V47_FILE}")

    original = V47_FILE.read_text(encoding="utf-8")
    patched, changes = patch_v47(original)

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

    try:
        py_compile.compile(str(V47_FILE), doraise=True)
        print_status("OK", "py_compile passou")
    except py_compile.PyCompileError as exc:
        print_status("ERRO", "py_compile falhou")
        print(str(exc))
        print("Use o backup se precisar restaurar.")
        return 2

    write_manifest(changes, backup, dry_run=False)

    print()
    print("Patch v47.4 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_2_multi_tension_test.py")
    print("  py darwin_v61_nursery_v47.py")
    print("  dentro do menu: 10 ou 10a")
    print("  py darwin_v47_2_multi_tension_test.py --purge-multi-tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
