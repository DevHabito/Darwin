from __future__ import annotations

"""
DARWIN — Integrar persistência de tensões na v47

Este script aplica uma integração pequena e reversível em:

    darwin_v61_nursery_v47.py

Ele conecta a economia de tensões viva do runtime ao módulo:

    darwin_tension_persistence_v47.py

Uso:
    py darwin_integrate_v47_persistence.py

Teste sem escrever nada:
    py darwin_integrate_v47_persistence.py --dry-run

Forçar reaplicação mesmo se detectar integração:
    py darwin_integrate_v47_persistence.py --force
"""

import argparse
import hashlib
import json
import py_compile
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
TENSION_MODULE = PROJECT_ROOT / "darwin_tension_persistence_v47.py"
DARWIN_HOME = PROJECT_ROOT / "darwin_home"
DB_PATH = DARWIN_HOME / "darwin.db"
BACKUP_DIR = PROJECT_ROOT / "v47_patch_backups"
MANIFEST_FILE = PROJECT_ROOT / "v47_persistence_integration_manifest.json"

IMPORT_BLOCK = 'try:\n    from darwin_tension_persistence_v47 import DarwinTensionStoreV47\nexcept Exception:\n    DarwinTensionStoreV47 = None  # type: ignore\n'
OLD_HELPER_ANCHOR = '    def _current_step(self) -> int:\n        return int(getattr(self, "step_counter", 0))\n\n    # --------------------------\n    # abertura / merge de tensão\n    # --------------------------\n'
NEW_HELPER_ANCHOR = '    def _current_step(self) -> int:\n        return int(getattr(self, "step_counter", 0))\n\n    # --------------------------\n    # persistência v47\n    # --------------------------\n\n    def _v47_enum_value(self, value):\n        return getattr(value, "value", value)\n\n    def _v47_note_persistence_error(self, exc: Exception) -> None:\n        msg = f"falha na persistência de tensão v47: {exc!r}"\n        if hasattr(self, "last_planner_error"):\n            self.last_planner_error = msg\n\n    def _v47_persist_case(self, case: "LiveTensionCase", event_type: str = "", note: str = "") -> None:\n        store = getattr(self, "tension_store", None)\n        if store is None or case is None:\n            return\n        try:\n            store.upsert_case(case)\n            if event_type:\n                store.record_event(\n                    tension_id=case.tension_id,\n                    event_type=event_type,\n                    step=getattr(case, "last_event_step", self._current_step()),\n                    status_after=str(self._v47_enum_value(getattr(case, "status", ""))),\n                    pressure_after=float(getattr(case, "live_pressure", 0.0) or 0.0),\n                    note=note,\n                    payload={\n                        "source_pair": case.source_pair,\n                        "active_tension_id": getattr(self, "active_tension_id", None),\n                    },\n                )\n        except Exception as exc:\n            self._v47_note_persistence_error(exc)\n\n    def _v47_record_probe(\n        self,\n        *,\n        case: "LiveTensionCase",\n        lower: str,\n        upper: str,\n        labels: Sequence[str],\n        score: float,\n        judgment: str,\n    ) -> None:\n        store = getattr(self, "tension_store", None)\n        if store is None or case is None:\n            return\n        try:\n            store.record_probe(\n                tension_id=case.tension_id,\n                lower_id=lower,\n                upper_id=upper,\n                selected_step=getattr(case, "last_probe_step", self._current_step()),\n                labels=list(labels),\n                score=float(score),\n                judgment=judgment,\n                payload={\n                    "source_pair": case.source_pair,\n                    "status": str(self._v47_enum_value(case.status)),\n                    "live_pressure": float(getattr(case, "live_pressure", 0.0) or 0.0),\n                },\n            )\n        except Exception as exc:\n            self._v47_note_persistence_error(exc)\n\n    def _v47_record_outcome(\n        self,\n        *,\n        case: "LiveTensionCase",\n        observed: str,\n        outcome_note: str,\n    ) -> None:\n        store = getattr(self, "tension_store", None)\n        if store is None or case is None:\n            return\n        try:\n            store.record_outcome(\n                tension_id=case.tension_id,\n                step=getattr(case, "last_event_step", self._current_step()),\n                outcome=outcome_note,\n                observed=observed,\n                closure_deficit_after=float(getattr(case, "closure_deficit", 0.0) or 0.0),\n                outcome_lines=list(getattr(case, "outcome_lines", [])),\n                payload={\n                    "source_pair": case.source_pair,\n                    "status": str(self._v47_enum_value(case.status)),\n                    "outcome": str(self._v47_enum_value(case.outcome)),\n                },\n            )\n        except Exception as exc:\n            self._v47_note_persistence_error(exc)\n\n    def _v47_sync_tension_cases(self, previous_active_tension_id: Optional[str] = None) -> None:\n        store = getattr(self, "tension_store", None)\n        if store is None:\n            return\n\n        try:\n            for case in list(getattr(self, "live_tension_cases", {}).values()):\n                store.upsert_case(case)\n            for case in list(getattr(self, "archived_tension_cases", {}).values()):\n                store.upsert_case(case)\n\n            current_active = getattr(self, "active_tension_id", None)\n            if previous_active_tension_id != current_active:\n                if previous_active_tension_id:\n                    store.record_event(\n                        tension_id=previous_active_tension_id,\n                        event_type="tension_preempted_out",\n                        step=self._current_step(),\n                        status_after="deprioritized",\n                        pressure_after=None,\n                        note=f"tensão ativa mudou de {previous_active_tension_id} para {current_active}",\n                        payload={"new_active_tension_id": current_active},\n                    )\n                if current_active:\n                    active_case = getattr(self, "live_tension_cases", {}).get(current_active)\n                    pressure = float(getattr(active_case, "live_pressure", 0.0) or 0.0) if active_case else None\n                    store.record_event(\n                        tension_id=current_active,\n                        event_type="tension_preempted_in",\n                        step=self._current_step(),\n                        status_after="active",\n                        pressure_after=pressure,\n                        note=f"tensão escolhida como foco executivo: {current_active}",\n                        payload={"previous_active_tension_id": previous_active_tension_id},\n                    )\n        except Exception as exc:\n            self._v47_note_persistence_error(exc)\n\n    # --------------------------\n    # abertura / merge de tensão\n    # --------------------------\n'
OLD_INIT = '        self.last_episode_summary = ""\n        self.last_planner_error = ""\n        self.recent_action_buckets: List[str] = []\n'
NEW_INIT = '        self.last_episode_summary = ""\n        self.last_planner_error = ""\n        self.tension_store = None\n        if DarwinTensionStoreV47 is not None:\n            try:\n                self.tension_store = DarwinTensionStoreV47()\n                self.tension_store.initialize_schema()\n            except Exception as exc:\n                self.last_planner_error = f"falha ao iniciar persistência de tensões v47: {exc!r}"\n        self.recent_action_buckets: List[str] = []\n'
OLD_REOPEN = '                self.active_tension_id = tension_id\n                return tension_id\n'
NEW_REOPEN = '                self.active_tension_id = tension_id\n                self._v47_persist_case(\n                    case,\n                    event_type="tension_reopened",\n                    note=f"tensão reaberta por contradição em {pair_key}",\n                )\n                return tension_id\n'
OLD_OPEN = '        self.live_tension_cases[tension_id] = case\n        self.active_tension_id = tension_id\n        return tension_id\n'
NEW_OPEN = '        self.live_tension_cases[tension_id] = case\n        self.active_tension_id = tension_id\n        self._v47_persist_case(\n            case,\n            event_type="tension_opened",\n            note=f"tensão aberta por contradição em {pair_key}",\n        )\n        return tension_id\n'
OLD_REFRESH_START = '        now = self._current_step()\n        market_lines: List[str] = ["ECONOMIA DE TENSÕES VIVAS"]\n'
NEW_REFRESH_START = '        previous_active_tension_id = getattr(self, "active_tension_id", None)\n        now = self._current_step()\n        market_lines: List[str] = ["ECONOMIA DE TENSÕES VIVAS"]\n'
OLD_REFRESH_END = '        self.last_tension_market_lines = market_lines[:12]\n        self._refresh_archive_lines()\n'
NEW_REFRESH_END = '        self.last_tension_market_lines = market_lines[:12]\n        self._refresh_archive_lines()\n        self._v47_sync_tension_cases(previous_active_tension_id=previous_active_tension_id)\n'
OLD_PROBE = '        case.continuity_lines = list(getattr(self, "last_probe_continuity_lines", []))[:4]\n        case.trail.append(f"sonda selecionada em {lower}>{upper} | score={score:.2f}")\n'
NEW_PROBE = '        case.continuity_lines = list(getattr(self, "last_probe_continuity_lines", []))[:4]\n        case.trail.append(f"sonda selecionada em {lower}>{upper} | score={score:.2f}")\n        self._v47_record_probe(\n            case=case,\n            lower=lower,\n            upper=upper,\n            labels=labels,\n            score=score,\n            judgment=judgment,\n        )\n        self._v47_persist_case(\n            case,\n            event_type="probe_state_synced",\n            note=f"estado de sonda sincronizado em {lower}>{upper}",\n        )\n'
OLD_OUTCOME = '        # Painel compatível com a base anterior.\n        if hasattr(self, "last_tension_outcome_lines"):\n            self.last_tension_outcome_lines = matched_case.outcome_lines[:]\n\n        return outcome_note\n'
NEW_OUTCOME = '        # Painel compatível com a base anterior.\n        if hasattr(self, "last_tension_outcome_lines"):\n            self.last_tension_outcome_lines = matched_case.outcome_lines[:]\n\n        self._v47_record_outcome(\n            case=matched_case,\n            observed=observed,\n            outcome_note=outcome_note,\n        )\n        self._v47_persist_case(\n            matched_case,\n            event_type="tension_outcome_synced",\n            note=f"desfecho de tensão sincronizado: {outcome_note}",\n        )\n\n        return outcome_note\n'


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def print_status(kind: str, message: str) -> None:
    print(f"[{kind:<7}] {message}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_ready() -> None:
    missing = []
    for path in (V47_FILE, TENSION_MODULE, DB_PATH):
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError(
            "Arquivos necessários não encontrados:\n"
            + "\n".join(f"- {m}" for m in missing)
            + "\n\nRode este script dentro da pasta darwin_local, depois de executar darwin_prepare_v47.py."
        )


def backup_files(dry_run: bool) -> dict[str, str]:
    stamp = now_stamp()
    file_backup = BACKUP_DIR / f"darwin_v61_nursery_v47_pre_persistence_{stamp}.py"
    db_backup = BACKUP_DIR / f"darwin_pre_v47_persistence_{stamp}.db"

    if dry_run:
        print_status("DRYRUN", f"criaria backup do v47: {file_backup}")
        print_status("DRYRUN", f"criaria backup do db:  {db_backup}")
        return {"v47_backup": str(file_backup), "db_backup": str(db_backup)}

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(V47_FILE, file_backup)
    shutil.copy2(DB_PATH, db_backup)
    print_status("OK", f"backup do v47 criado: {file_backup}")
    print_status("OK", f"backup do banco criado: {db_backup}")
    return {"v47_backup": str(file_backup), "db_backup": str(db_backup)}


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        print_status("AVISO", f"ponto de patch não encontrado: {label}")
        return text, False
    return text.replace(old, new, 1), True


def patch_import(text: str) -> tuple[str, bool]:
    if "DarwinTensionStoreV47" in text:
        print_status("PULOU", "import de DarwinTensionStoreV47 já existe")
        return text, False
    old = "from darwin_home import DarwinHome, compute_valence\n"
    new = old + "\n" + IMPORT_BLOCK + "\n"
    text, ok = replace_once(text, old, new, "import DarwinTensionStoreV47")
    if ok:
        print_status("OK", "import seguro de DarwinTensionStoreV47 inserido")
    return text, ok


def patch_helpers(text: str) -> tuple[str, bool]:
    if "def _v47_persist_case" in text:
        print_status("PULOU", "helpers _v47_* já existem")
        return text, False
    text, ok = replace_once(text, OLD_HELPER_ANCHOR, NEW_HELPER_ANCHOR, "helpers de persistência v47")
    if ok:
        print_status("OK", "helpers _v47_* inseridos no mixin")
    return text, ok


def patch_agent_init(text: str) -> tuple[str, bool]:
    if "self.tension_store = None" in text:
        print_status("PULOU", "self.tension_store já existe no agente")
        return text, False
    text, ok = replace_once(text, OLD_INIT, NEW_INIT, "inicialização self.tension_store")
    if ok:
        print_status("OK", "self.tension_store inicializado no DarwinNurseryAgent")
    return text, ok


def patch_register_tension(text: str) -> tuple[str, int]:
    changes = 0
    text2, ok = replace_once(text, OLD_REOPEN, NEW_REOPEN, "persistência em reabertura de tensão")
    if ok:
        text = text2
        changes += 1
        print_status("OK", "persistência em reabertura de tensão inserida")

    text2, ok = replace_once(text, OLD_OPEN, NEW_OPEN, "persistência em abertura de tensão")
    if ok:
        text = text2
        changes += 1
        print_status("OK", "persistência em abertura de tensão inserida")
    return text, changes


def patch_refresh(text: str) -> tuple[str, int]:
    changes = 0
    text2, ok = replace_once(text, OLD_REFRESH_START, NEW_REFRESH_START, "captura de tensão ativa anterior")
    if ok:
        text = text2
        changes += 1
        print_status("OK", "captura de active_tension_id anterior inserida")

    text2, ok = replace_once(text, OLD_REFRESH_END, NEW_REFRESH_END, "sincronização após refresh_tension_economy")
    if ok:
        text = text2
        changes += 1
        print_status("OK", "sincronização v47 após refresh_tension_economy inserida")
    return text, changes


def patch_probe_and_outcome(text: str) -> tuple[str, int]:
    changes = 0
    text2, ok = replace_once(text, OLD_PROBE, NEW_PROBE, "registro de sonda v47")
    if ok:
        text = text2
        changes += 1
        print_status("OK", "registro de sonda v47 inserido")

    text2, ok = replace_once(text, OLD_OUTCOME, NEW_OUTCOME, "registro de desfecho v47")
    if ok:
        text = text2
        changes += 1
        print_status("OK", "registro de desfecho v47 inserido")
    return text, changes


def patch_intro_label(text: str) -> tuple[str, int]:
    changes = 0
    replacements = [
        (
            'print("DARWIN v61 — Nursery v46 (economia competitiva da tensão viva)")',
            'print("DARWIN v61 — Nursery v47 (memória executiva persistente de tensões)")',
        ),
        (
            'print("  • tornar a tensão viva um estado persistente explícito, não só um cálculo momentâneo")',
            'print("  • persistir casos de tensão viva no banco como memória executiva")',
        ),
    ]
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            changes += 1
    if changes:
        print_status("OK", "rótulo de sessão atualizado para v47")
    return text, changes


def patch_text(text: str, force: bool) -> tuple[str, int]:
    if "def _v47_persist_case" in text and "self.tension_store = None" in text and not force:
        print_status("PULOU", "arquivo já parece integrado; use --force para tentar reaplicar")
        return text, 0

    total = 0
    text, ok = patch_import(text)
    total += int(ok)
    text, ok = patch_helpers(text)
    total += int(ok)
    text, ok = patch_agent_init(text)
    total += int(ok)

    text, n = patch_register_tension(text)
    total += n
    text, n = patch_refresh(text)
    total += n
    text, n = patch_probe_and_outcome(text)
    total += n
    text, n = patch_intro_label(text)
    total += n

    return text, total


def sqlite_counts() -> dict[str, int]:
    tables = [
        "tension_cases",
        "tension_events",
        "tension_probes",
        "tension_outcomes",
        "darwin_schema_migrations",
    ]
    result: dict[str, int] = {}
    conn = sqlite3.connect(DB_PATH)
    try:
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            result[table] = int(row[0]) if row else 0
    finally:
        conn.close()
    return result


def write_manifest(backups: dict[str, str], changes: int, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "v47_file": str(V47_FILE),
        "tension_module": str(TENSION_MODULE),
        "db_path": str(DB_PATH),
        "changes_applied": changes,
        "backups": backups,
        "sqlite_counts": sqlite_counts(),
        "hashes": {},
    }

    for path_str in [str(V47_FILE), str(TENSION_MODULE), str(DB_PATH), *backups.values()]:
        path = Path(path_str)
        if path.exists() and path.is_file():
            manifest["hashes"][path_str] = sha256_file(path)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Integra persistência de tensão ao Darwin v47.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    parser.add_argument("--force", action="store_true", help="Tenta reaplicar patch mesmo se já houver integração.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN — INTEGRAR PERSISTÊNCIA DE TENSÕES v47")
    print("=" * 72)
    print(f"Raiz do projeto: {PROJECT_ROOT}")
    print(f"Dry-run:         {args.dry_run}")
    print()

    ensure_ready()

    original = V47_FILE.read_text(encoding="utf-8")
    patched, changes = patch_text(original, force=args.force)

    if changes == 0:
        print()
        print("Nenhuma mudança aplicada.")
        return 0

    backups = backup_files(args.dry_run)

    if args.dry_run:
        print_status("DRYRUN", f"aplicaria {changes} mudança(s) em {V47_FILE.name}")
        write_manifest(backups, changes, dry_run=True)
        print()
        print("Dry-run concluído.")
        return 0

    V47_FILE.write_text(patched, encoding="utf-8")
    print_status("OK", f"{changes} mudança(s) aplicada(s) em {V47_FILE.name}")

    try:
        py_compile.compile(str(V47_FILE), doraise=True)
        py_compile.compile(str(TENSION_MODULE), doraise=True)
        print_status("OK", "compilação py_compile passou")
    except py_compile.PyCompileError as exc:
        print_status("ERRO", "falha de compilação após patch")
        print(str(exc))
        print("Restaure o backup do arquivo v47 se necessário.")
        return 2

    write_manifest(backups, changes, dry_run=False)

    print()
    print("Resumo SQLite:")
    for table, count in sqlite_counts().items():
        print(f"- {table}: {count}")

    print()
    print("Integração v47 concluída.")
    print("Próximo teste recomendado:")
    print("  py darwin_v61_nursery_v47.py")
    print("Depois rode alguns passos autônomos e verifique se tension_cases/tension_events começam a preencher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
