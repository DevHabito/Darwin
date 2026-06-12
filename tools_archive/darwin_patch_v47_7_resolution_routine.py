from __future__ import annotations

"""
DARWIN v47.7 — Micro-Rotina de Resolução de Tensão

Objetivo:
- Evoluir o compromisso executivo da v47.6 para uma micro-rotina explícita.
- Quando há tensão ativa, Darwin passa a registrar uma rotina de resolução:
  assess -> predict/validate -> update -> close/preempt.
- A rotina é persistida em tabelas novas:
  tension_resolution_routines
  tension_resolution_steps

Uso:
    py darwin_patch_v47_7_resolution_routine.py --dry-run
    py darwin_patch_v47_7_resolution_routine.py

Teste:
    py darwin_v47_7_resolution_routine_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_7_resolution_routine_manifest.json"

ROUTINE_METHODS = r'''
    # --------------------------
    # micro-rotina de resolução v47.7
    # --------------------------

    def _v47_7_routine_db_path(self):
        from pathlib import Path
        return Path("darwin_home") / "darwin.db"

    def _v47_7_initialize_resolution_tables(self) -> None:
        import sqlite3

        db_path = self._v47_7_routine_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_resolution_routines (
                    routine_id TEXT PRIMARY KEY,
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    current_stage TEXT NOT NULL DEFAULT 'assess',
                    next_action TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_resolution_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    routine_id TEXT NOT NULL,
                    tension_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    stage TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_resolution_routines_tension
                ON tension_resolution_routines(tension_id, status)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_resolution_steps_routine
                ON tension_resolution_steps(routine_id, id)
                """
            )
            conn.commit()

    def _v47_7_now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _v47_7_safe_json(self, value) -> str:
        import json
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return json.dumps(str(value), ensure_ascii=False)

    def _v47_7_routine_id(self, tension_id: str) -> str:
        return f"RR:{tension_id}"

    def _v47_7_case_payload(self, case: "LiveTensionCase", stage: str, next_action: str) -> dict:
        return {
            "tension_id": case.tension_id,
            "source_pair": case.source_pair,
            "status": getattr(case.status, "value", str(case.status)),
            "outcome": getattr(case.outcome, "value", str(case.outcome)),
            "live_pressure": float(getattr(case, "live_pressure", 0.0) or 0.0),
            "economic_priority": float(getattr(case, "economic_priority", 0.0) or 0.0),
            "closure_deficit": float(getattr(case, "closure_deficit", 0.0) or 0.0),
            "saturation_cost": float(getattr(case, "saturation_cost", 0.0) or 0.0),
            "stage": stage,
            "next_action": next_action,
        }

    def _v47_7_upsert_routine(self, case: "LiveTensionCase", stage: str, next_action: str, reason: str) -> str:
        import sqlite3

        self._v47_7_initialize_resolution_tables()

        db_path = self._v47_7_routine_db_path()
        routine_id = self._v47_7_routine_id(case.tension_id)
        now = self._v47_7_now_iso()
        payload = self._v47_7_case_payload(case, stage, next_action)

        if not db_path.exists():
            return routine_id

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO tension_resolution_routines (
                    routine_id, tension_id, source_pair, status, current_stage,
                    next_action, created_at, updated_at, last_reason, payload_json
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(routine_id) DO UPDATE SET
                    status='active',
                    current_stage=excluded.current_stage,
                    next_action=excluded.next_action,
                    updated_at=excluded.updated_at,
                    last_reason=excluded.last_reason,
                    payload_json=excluded.payload_json
                """,
                (
                    routine_id,
                    case.tension_id,
                    case.source_pair,
                    stage,
                    next_action,
                    now,
                    now,
                    reason,
                    self._v47_7_safe_json(payload),
                ),
            )
            conn.commit()

        return routine_id

    def _v47_7_record_routine_step(
        self,
        *,
        case: "LiveTensionCase",
        routine_id: str,
        stage: str,
        action_name: str,
        reason: str,
    ) -> None:
        import sqlite3

        db_path = self._v47_7_routine_db_path()
        if not db_path.exists():
            return

        payload = self._v47_7_case_payload(case, stage, action_name)

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO tension_resolution_steps (
                    routine_id, tension_id, timestamp, step, stage,
                    action_name, source_pair, reason, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    routine_id,
                    case.tension_id,
                    self._v47_7_now_iso(),
                    self._current_step(),
                    stage,
                    action_name,
                    case.source_pair,
                    reason,
                    self._v47_7_safe_json(payload),
                ),
            )
            conn.commit()

    def _v47_7_close_routine_if_case_closed(self, case: "LiveTensionCase") -> None:
        import sqlite3

        if case is None:
            return

        if case.status not in {TensionStatus.CLOSED, TensionStatus.ARCHIVED, TensionStatus.STALE}:
            return

        db_path = self._v47_7_routine_db_path()
        if not db_path.exists():
            return

        routine_id = self._v47_7_routine_id(case.tension_id)

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE tension_resolution_routines
                SET status=?, current_stage=?, next_action='', updated_at=?, last_reason=?
                WHERE routine_id=?
                """,
                (
                    getattr(case.status, "value", str(case.status)),
                    "done",
                    self._v47_7_now_iso(),
                    f"rotina encerrada porque a tensão está {getattr(case.status, 'value', case.status)}",
                    routine_id,
                ),
            )
            conn.commit()

    def _v47_7_stage_for_case(self, case: "LiveTensionCase") -> tuple[str, str]:
        pending = self._v47_6_pending_hypothesis_for_pair(case.source_lower, case.source_upper)

        if pending is not None:
            return "validate_pending_hypothesis", "validate"

        if case.status == TensionStatus.PROBING:
            return "repair_missing_prediction", "predict"

        return "formulate_probe_hypothesis", "predict"

    def _v47_7_resolution_routine_plan(self) -> Optional["ActionPlan"]:
        active_id = getattr(self, "active_tension_id", None)
        if not active_id:
            self.last_resolution_routine_lines = [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                "- nenhuma tensão ativa",
            ]
            return None

        case = getattr(self, "live_tension_cases", {}).get(active_id)
        if case is None:
            self.last_resolution_routine_lines = [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                f"- foco {active_id} ausente do runtime",
            ]
            return None

        self._v47_7_close_routine_if_case_closed(case)

        if not self._v47_6_case_is_actionable(case):
            self.last_resolution_routine_lines = [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                f"- foco {active_id} não acionável ou já fechado",
            ]
            return None

        stage, next_action = self._v47_7_stage_for_case(case)

        try:
            self._v47_6_mark_commitment_probe_if_needed(case)
        except Exception as exc:
            self._v47_note_persistence_error(exc)

        if next_action == "validate":
            novelty = 0.94
            bucket = "routine_validate"
            reason = (
                f"micro-rotina v47.7: validar a hipótese pendente da tensão ativa "
                f"{case.tension_id} ({case.source_pair}) para tentar reduzir ou fechar a dívida"
            )
        else:
            novelty = 0.90
            bucket = "routine_predict"
            reason = (
                f"micro-rotina v47.7: formular hipótese sobre a tensão ativa "
                f"{case.tension_id} ({case.source_pair}) antes de qualquer exploração comum"
            )

        routine_id = self._v47_7_upsert_routine(case, stage, next_action, reason)
        self._v47_7_record_routine_step(
            case=case,
            routine_id=routine_id,
            stage=stage,
            action_name=next_action,
            reason=reason,
        )

        self.last_resolution_routine_lines = [
            "MICRO-ROTINA DE RESOLUÇÃO v47.7",
            f"- rotina: {routine_id}",
            f"- tensão ativa: {case.tension_id} ({case.source_pair})",
            f"- estágio: {stage}",
            f"- próximo ato: {next_action}({case.source_pair})",
            f"- pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f} | prioridade={case.economic_priority:.3f}",
        ]

        try:
            self._v47_persist_case(
                case,
                event_type="resolution_routine_step_selected",
                note=f"{stage} -> {next_action}({case.source_pair})",
            )
        except Exception:
            pass

        return self._v47_6_make_action_plan(
            action_name=next_action,
            lower=case.source_lower,
            upper=case.source_upper,
            explanation=reason,
            novelty_residual=novelty,
            bucket=bucket,
            phase="executive_resolution_routine",
            signature=f"routine:{routine_id}:{stage}:{next_action}:{case.source_pair}",
        )

    def tension_resolution_routine_summary(self) -> str:
        lines = list(getattr(self, "last_resolution_routine_lines", []))
        if lines:
            return "\n".join(lines)

        active_id = getattr(self, "active_tension_id", None)
        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None

        if case is not None and self._v47_6_case_is_actionable(case):
            stage, next_action = self._v47_7_stage_for_case(case)
            return "\n".join(
                [
                    "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                    f"- rotina aguardando próximo passo para {case.tension_id} ({case.source_pair})",
                    f"- estágio previsto: {stage}",
                    f"- próximo ato provável: {next_action}({case.source_pair})",
                    f"- pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f}",
                ]
            )

        return "\n".join(
            [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                "- nenhuma rotina ativa no runtime",
            ]
        )

    def choose_autonomous_action(self) -> "ActionPlan":
        routine_plan = self._v47_7_resolution_routine_plan()
        if routine_plan is not None:
            return routine_plan

        return self._choose_autonomous_action_v47_6_commitment()

'''


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_7_{now_stamp()}{path.suffix}"

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

    if "def _v47_7_resolution_routine_plan" not in text:
        old_choose = (
            '    def choose_autonomous_action(self) -> "ActionPlan":\n'
            '        commitment_plan = self._v47_6_commitment_plan_from_active_tension()\n'
            '        if commitment_plan is not None:\n'
            '            return commitment_plan\n'
            '\n'
            '        return self._choose_autonomous_action_v47_base()\n'
        )
        new_choose = (
            '    def _choose_autonomous_action_v47_6_commitment(self) -> "ActionPlan":\n'
            '        commitment_plan = self._v47_6_commitment_plan_from_active_tension()\n'
            '        if commitment_plan is not None:\n'
            '            return commitment_plan\n'
            '\n'
            '        return self._choose_autonomous_action_v47_base()\n'
            '\n'
            + ROUTINE_METHODS
        )
        text, n = replace_once(
            text,
            old_choose,
            new_choose,
            "choose_autonomous_action evoluído para micro-rotina v47.7",
        )
        changes += n
    else:
        print_status("PULOU", "micro-rotina v47.7 já existe")

    if "10m - mostrar micro-rotina de resolução" not in text:
        text, n = replace_once(
            text,
            '        print("10c - mostrar compromisso executivo atual")\n',
            '        print("10c - mostrar compromisso executivo atual")\n'
            '        print("10m - mostrar micro-rotina de resolução")\n',
            "menu adiciona comando 10m",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10m já existe")

    if 'choice in {"10m", "micro", "rotina", "routine"}' not in text:
        anchor = (
            '            elif choice in {"10c", "commitment", "compromisso"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.executive_commitment_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10c", "commitment", "compromisso"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.executive_commitment_summary())\n'
            '            elif choice in {"10m", "micro", "rotina", "routine"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.tension_resolution_routine_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10m",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10m já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r ou 10c.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c ou 10m.")\n',
        "mensagem de comando inválido inclui 10m",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.7_resolution_routine",
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
    parser = argparse.ArgumentParser(description="Patch v47.7: micro-rotina de resolução de tensão.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.7 — MICRO-ROTINA DE RESOLUÇÃO")
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
        print("Nenhuma mudança aplicada.")
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
    print("Patch v47.7 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_7_resolution_routine_test.py --dry-run")
    print("  py darwin_v47_7_resolution_routine_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
