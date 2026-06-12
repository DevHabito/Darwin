from __future__ import annotations

"""
DARWIN v47.5 — Patch de Reidratação de Tensões Persistentes

Objetivo:
- Quando o Darwin iniciar, ele deve reconstruir live_tension_cases a partir
  das tabelas persistentes da v47.
- Isso permite que casos cognitivos abertos sobrevivam ao encerramento do processo.
- Não altera o banco durante a reidratação; apenas lê tension_cases abertas.

Arquivos alterados:
- darwin_v61_nursery_v47.py

Uso:
    py darwin_patch_v47_5_rehydrate_tensions.py --dry-run
    py darwin_patch_v47_5_rehydrate_tensions.py

Depois:
    py darwin_v47_5_rehydration_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_5_rehydrate_tensions_manifest.json"

REHYDRATION_METHODS = '\n    # --------------------------\n    # reidratação v47.5\n    # --------------------------\n\n    def _v47_json_list(self, raw) -> List[str]:\n        import json\n\n        if raw is None:\n            return []\n        if isinstance(raw, list):\n            return [str(x) for x in raw]\n        if isinstance(raw, tuple):\n            return [str(x) for x in raw]\n\n        text = str(raw)\n        if not text:\n            return []\n\n        try:\n            parsed = json.loads(text)\n        except Exception:\n            return [text]\n\n        if isinstance(parsed, list):\n            return [str(x) for x in parsed]\n        if parsed is None:\n            return []\n        return [str(parsed)]\n\n    def _v47_status_from_value(self, value) -> "TensionStatus":\n        try:\n            return TensionStatus(str(value))\n        except Exception:\n            return TensionStatus.OPEN\n\n    def _v47_outcome_from_value(self, value) -> "TensionOutcome":\n        try:\n            return TensionOutcome(str(value))\n        except Exception:\n            return TensionOutcome.UNKNOWN\n\n    def _v47_float_from_row(self, row: dict, key: str, default: float = 0.0) -> float:\n        value = row.get(key, None)\n        if value is None:\n            return float(default)\n        try:\n            return float(value)\n        except Exception:\n            return float(default)\n\n    def _v47_int_from_row(self, row: dict, key: str, default: int = 0) -> int:\n        value = row.get(key, None)\n        if value is None:\n            return int(default)\n        try:\n            return int(value)\n        except Exception:\n            return int(default)\n\n    def _v47_case_from_persistent_row(self, row: dict) -> "LiveTensionCase":\n        status = self._v47_status_from_value(row.get("status", "open"))\n        outcome = self._v47_outcome_from_value(row.get("outcome", "unknown"))\n\n        case = LiveTensionCase(\n            tension_id=str(row.get("tension_id", "")),\n            source_lower=str(row.get("source_lower", "")),\n            source_upper=str(row.get("source_upper", "")),\n            source_predicted=str(row.get("source_predicted", "")),\n            source_observed=str(row.get("source_observed", "")),\n            source_labels=tuple(self._v47_json_list(row.get("source_labels_json"))),\n            semantic_summary=str(row.get("semantic_summary", "")),\n            opened_step=self._v47_int_from_row(row, "opened_step", 0),\n            last_event_step=self._v47_int_from_row(row, "last_event_step", 0),\n            contradiction_magnitude=self._v47_float_from_row(row, "contradiction_magnitude", 1.0),\n            status=status,\n            outcome=outcome,\n            inherited_pairs=tuple(self._v47_json_list(row.get("inherited_pairs_json"))),\n        )\n\n        case.last_probe_lower = row.get("last_probe_lower") or None\n        case.last_probe_upper = row.get("last_probe_upper") or None\n\n        last_probe_step = row.get("last_probe_step")\n        case.last_probe_step = None if last_probe_step is None else self._v47_int_from_row(row, "last_probe_step", 0)\n\n        case.last_probe_score = self._v47_float_from_row(row, "last_probe_score", 0.0)\n        case.last_probe_judgment = str(row.get("last_probe_judgment", "") or "")\n        case.last_probe_labels = tuple(self._v47_json_list(row.get("last_probe_labels_json")))\n\n        case.continuity_lines = self._v47_json_list(row.get("continuity_lines_json"))\n        case.outcome_lines = self._v47_json_list(row.get("outcome_lines_json"))\n        case.trail = self._v47_json_list(row.get("trail_json"))\n\n        case.live_pressure = self._v47_float_from_row(row, "live_pressure", 0.0)\n        case.recency_score = self._v47_float_from_row(row, "recency_score", 0.0)\n        case.continuity_score = self._v47_float_from_row(row, "continuity_score", 0.0)\n        case.ambiguity_score = self._v47_float_from_row(row, "ambiguity_score", 0.0)\n        case.closure_deficit = self._v47_float_from_row(row, "closure_deficit", 1.0)\n        case.saturation_cost = self._v47_float_from_row(row, "saturation_cost", 0.0)\n        case.economic_priority = self._v47_float_from_row(row, "economic_priority", 0.0)\n\n        case.probe_count = self._v47_int_from_row(row, "probe_count", 0)\n        case.closure_hits = self._v47_int_from_row(row, "closure_hits", 0)\n        case.reopening_hits = self._v47_int_from_row(row, "reopening_hits", 0)\n        case.weakening_hits = self._v47_int_from_row(row, "weakening_hits", 0)\n\n        if not case.trail:\n            case.trail.append("reidratada da memória executiva persistente v47.5")\n\n        return case\n\n    def _v47_parse_tension_numeric_id(self, tension_id: str) -> int:\n        digits = "".join(ch for ch in str(tension_id) if ch.isdigit())\n        if not digits:\n            return 0\n        try:\n            return int(digits)\n        except Exception:\n            return 0\n\n    def _v47_rehydrate_open_tensions_from_store(self) -> int:\n        """\n        Reconstrói live_tension_cases a partir de tension_cases persistidos.\n\n        Regra:\n        - só reidrata casos não fechados/arquivados/stale;\n        - não grava eventos no banco durante boot;\n        - preserva active_tension_id pelo maior economic_priority/live_pressure;\n        - atualiza live_tension_counter_v46 para evitar colisão de IDs futuros.\n        """\n        self.last_tension_rehydration_lines: List[str] = []\n\n        store = getattr(self, "tension_store", None)\n        if store is None:\n            self.last_tension_rehydration_lines = [\n                "REIDRATAÇÃO v47.5",\n                "- persistência de tensões indisponível",\n            ]\n            return 0\n\n        if not hasattr(self, "live_tension_cases"):\n            self.init_live_tension_v46()\n\n        try:\n            rows = store.load_open_cases()\n        except Exception as exc:\n            self._v47_note_persistence_error(exc)\n            self.last_tension_rehydration_lines = [\n                "REIDRATAÇÃO v47.5",\n                f"- falha ao carregar casos: {exc!r}",\n            ]\n            return 0\n\n        if not rows:\n            self.last_tension_rehydration_lines = [\n                "REIDRATAÇÃO v47.5",\n                "- nenhum caso executivo aberto no banco",\n            ]\n            return 0\n\n        rehydrated: List[LiveTensionCase] = []\n        max_numeric_id = int(getattr(self, "live_tension_counter_v46", 0) or 0)\n\n        for row in rows:\n            try:\n                case = self._v47_case_from_persistent_row(dict(row))\n            except Exception as exc:\n                self._v47_note_persistence_error(exc)\n                continue\n\n            if not case.tension_id:\n                continue\n\n            self.live_tension_cases[case.tension_id] = case\n            rehydrated.append(case)\n            max_numeric_id = max(max_numeric_id, self._v47_parse_tension_numeric_id(case.tension_id))\n\n        if not rehydrated:\n            self.last_tension_rehydration_lines = [\n                "REIDRATAÇÃO v47.5",\n                "- nenhum caso pôde ser reconstruído",\n            ]\n            return 0\n\n        # Evita colisão com IDs persistidos, inclusive IDs altos de testes.\n        self.live_tension_counter_v46 = max(int(getattr(self, "live_tension_counter_v46", 0) or 0), max_numeric_id)\n\n        ranked = sorted(\n            rehydrated,\n            key=lambda c: (\n                float(getattr(c, "economic_priority", 0.0) or 0.0),\n                float(getattr(c, "live_pressure", 0.0) or 0.0),\n                int(getattr(c, "last_event_step", 0) or 0),\n            ),\n            reverse=True,\n        )\n        active = ranked[0]\n        self.active_tension_id = active.tension_id\n        self._v47_last_executive_active_id = active.tension_id\n\n        self.last_tension_rehydration_lines = [\n            "REIDRATAÇÃO v47.5",\n            f"- casos reidratados: {len(rehydrated)}",\n            f"- foco executivo restaurado: {active.tension_id} ({active.source_pair})",\n        ]\n        for case in ranked[:6]:\n            self.last_tension_rehydration_lines.append(\n                f"- {case.tension_id}: {case.source_pair} | status={case.status.value} | "\n                f"pressão={case.live_pressure:.3f} | prioridade={case.economic_priority:.3f} | "\n                f"déficit={case.closure_deficit:.3f}"\n            )\n\n        self.last_tension_market_lines = self.last_tension_rehydration_lines[:12]\n        return len(rehydrated)\n\n    def v47_rehydration_summary(self) -> str:\n        lines = list(getattr(self, "last_tension_rehydration_lines", []))\n        if not lines:\n            lines = [\n                "REIDRATAÇÃO v47.5",\n                "- ainda não houve tentativa de reidratação nesta sessão",\n            ]\n        return "\\n".join(lines)\n\n'


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


def backup_file(path: Path, dry_run: bool) -> str:
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_5_{now_stamp()}{path.suffix}"

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

    if "def _v47_rehydrate_open_tensions_from_store" not in text:
        anchor = (
            '    # --------------------------\n'
            '    # abertura / merge de tensão\n'
            '    # --------------------------\n'
        )
        replacement = REHYDRATION_METHODS + anchor
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "métodos de reidratação v47.5 inseridos",
        )
        changes += n
    else:
        print_status("PULOU", "métodos de reidratação já existem")

    if "self._v47_rehydrate_open_tensions_from_store()" not in text:
        anchor = "        self.hydrate_memory_from_home()\n"
        replacement = (
            "        self.hydrate_memory_from_home()\n"
            "        self._v47_rehydrate_open_tensions_from_store()\n"
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "chamada de reidratação no boot do agente",
        )
        changes += n
    else:
        print_status("PULOU", "chamada de reidratação já existe")

    # Integra um comando de menu leve, se o menu v47.4 estiver presente.
    if "10r - mostrar relatório de reidratação executiva" not in text:
        text, n = replace_once(
            text,
            '        print("10a - mostrar todas as tensões persistidas")\n',
            '        print("10a - mostrar todas as tensões persistidas")\n'
            '        print("10r - mostrar relatório de reidratação executiva")\n',
            "menu adiciona comando 10r",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10r já existe")

    if 'choice in {"10r", "rehydrate", "reidratar", "reidratacao", "reidratação"}' not in text:
        anchor = (
            '            elif choice in {"10a", "tensoes all", "tensões all", "tension all"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.show_tension_dashboard(include_closed=True))\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10a", "tensoes all", "tensões all", "tension all"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.show_tension_dashboard(include_closed=True))\n'
            '            elif choice in {"10r", "rehydrate", "reidratar", "reidratacao", "reidratação"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.v47_rehydration_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10r",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10r já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 ou 10a.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a ou 10r.")\n',
        "mensagem de comando inválido inclui 10r",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.5_rehydrate_tensions",
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
    parser = argparse.ArgumentParser(description="Patch v47.5: reidratação de tensões persistentes.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.5 — REIDRATAÇÃO DE TENSÕES")
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
    print("Patch v47.5 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_5_rehydration_test.py")
    print("  py darwin_v61_nursery_v47.py")
    print("  dentro do menu: 10r, 10, 10a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
