from __future__ import annotations

"""
DARWIN v47.12.1 — Repair Seguro do Relatório Consolidado do Ciclo

Problema corrigido:
- O patch v47.12 inseriu métodos novos dentro do corpo de execute_action,
  deixando a função sem bloco indentado e causando:

    IndentationError: expected an indented block after function definition

Estratégia:
1. Restaurar o backup limpo criado antes do patch v47.12:
   v47_patch_backups/darwin_v61_nursery_v47_pre_v47_12_*.py
2. Reaplicar v47.12 corretamente:
   - métodos v47.12 entram ANTES de def execute_action;
   - execute_action recebe apenas a chamada extra:
       self._v47_12_record_cycle_report_after_validate(plan, result)
3. Compilar com py_compile.
4. Criar manifest de repair.

Uso:
    py darwin_repair_v47_12_1_cycle_report.py --dry-run
    py darwin_repair_v47_12_1_cycle_report.py

Depois:
    py darwin_v47_12_cycle_report_test.py --dry-run
    py darwin_v47_12_cycle_report_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_12_1_cycle_report_repair_manifest.json"


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


def latest_v47_12_backup() -> Path | None:
    if not BACKUP_DIR.exists():
        return None
    backups = sorted(
        BACKUP_DIR.glob("darwin_v61_nursery_v47_pre_v47_12_*.py"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups[0] if backups else None


def make_broken_backup(dry_run: bool) -> Path:
    backup_path = BACKUP_DIR / f"darwin_v61_nursery_v47_pre_repair_v47_12_1_{now_stamp()}.py"
    if dry_run:
        print_status("DRYRUN", f"criaria backup do arquivo atual quebrado: {backup_path}")
        return backup_path

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(V47_FILE, backup_path)
    print_status("OK", f"backup do arquivo atual criado: {backup_path}")
    return backup_path


def restore_pre_v47_12(dry_run: bool) -> tuple[Path, Path]:
    backup = latest_v47_12_backup()
    if backup is None:
        raise FileNotFoundError(
            "Não encontrei backup pré-v47.12 em v47_patch_backups/. "
            "Procure por darwin_v61_nursery_v47_pre_v47_12_*.py."
        )

    print_status("INFO", f"backup limpo a restaurar: {backup}")
    broken_backup = make_broken_backup(dry_run=dry_run)

    if dry_run:
        print_status("DRYRUN", f"restauraria {backup} -> {V47_FILE}")
        return backup, broken_backup

    shutil.copy2(backup, V47_FILE)
    print_status("OK", f"arquivo restaurado a partir de: {backup}")

    ok, error = compiles(V47_FILE)
    if not ok:
        raise RuntimeError(f"Backup restaurado não compila:\n{error}")

    print_status("OK", "arquivo restaurado compila")
    return backup, broken_backup


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, int]:
    if old not in text:
        print_status("AVISO", f"não encontrado: {label}")
        return text, 0
    text = text.replace(old, new, 1)
    print_status("OK", f"{label}: 1 ocorrência")
    return text, 1


def cycle_methods_block() -> str:
    lines = [
        '    # --------------------------',
        '    # relatório consolidado do ciclo cognitivo v47.12.1',
        '    # --------------------------',
        '',
        '    def _v47_12_initialize_cycle_report_tables(self) -> None:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.execute(',
        '                """',
        '                CREATE TABLE IF NOT EXISTS tension_cognitive_cycle_reports (',
        '                    id INTEGER PRIMARY KEY AUTOINCREMENT,',
        '                    report_id TEXT NOT NULL,',
        '                    tension_id TEXT NOT NULL,',
        '                    source_pair TEXT NOT NULL,',
        '                    timestamp TEXT NOT NULL,',
        '                    step INTEGER,',
        '                    status_after TEXT NOT NULL DEFAULT \'\',',
        '                    outcome_after TEXT NOT NULL DEFAULT \'\',',
        '                    comparison_id TEXT NOT NULL DEFAULT \'\',',
        '                    influence_id TEXT NOT NULL DEFAULT \'\',',
        '                    lineage_id TEXT NOT NULL DEFAULT \'\',',
        '                    hypothesis_id TEXT NOT NULL DEFAULT \'\',',
        '                    validation_result TEXT NOT NULL DEFAULT \'\',',
        '                    closure_assessment TEXT NOT NULL DEFAULT \'\',',
        '                    narrative TEXT NOT NULL DEFAULT \'\',',
        '                    payload_json TEXT NOT NULL DEFAULT \'{}\'',
        '                )',
        '                """',
        '            )',
        '            conn.execute(',
        '                """',
        '                CREATE INDEX IF NOT EXISTS idx_tension_cognitive_cycle_reports_tension',
        '                ON tension_cognitive_cycle_reports(tension_id, id)',
        '                """',
        '            )',
        '            conn.commit()',
        '',
        '    def _v47_12_latest_row_dict(self, table: str, tension_id: str) -> dict:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return {}',
        '',
        '        try:',
        '            with sqlite3.connect(db_path) as conn:',
        '                conn.row_factory = sqlite3.Row',
        '                row = conn.execute(',
        '                    f"SELECT * FROM {table} WHERE tension_id=? ORDER BY id DESC LIMIT 1",',
        '                    (tension_id,),',
        '                ).fetchone()',
        '            if row is None:',
        '                return {}',
        '            return {key: row[key] for key in row.keys()}',
        '        except Exception:',
        '            return {}',
        '',
        '    def _v47_12_find_case_for_plan(self, plan):',
        '        lower = str(getattr(plan, "target_a", "") or "")',
        '        upper = str(getattr(plan, "target_b", "") or "")',
        '        active_id = getattr(self, "active_tension_id", None)',
        '        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None',
        '',
        '        if case is not None and getattr(case, "source_lower", None) == lower and getattr(case, "source_upper", None) == upper:',
        '            return case',
        '',
        '        for candidate in list(getattr(self, "live_tension_cases", {}).values()):',
        '            if getattr(candidate, "source_lower", None) == lower and getattr(candidate, "source_upper", None) == upper:',
        '                return candidate',
        '',
        '        return case',
        '',
        '    def _v47_12_case_status_text(self, case) -> tuple[str, str]:',
        '        if case is None:',
        '            return "", ""',
        '        status = getattr(case, "status", "")',
        '        outcome = getattr(case, "outcome", "")',
        '        status_text = getattr(status, "value", str(status))',
        '        outcome_text = getattr(outcome, "value", str(outcome))',
        '        return status_text, outcome_text',
        '',
        '    def _v47_12_closure_assessment(self, case, result_text: str) -> str:',
        '        status_text, outcome_text = self._v47_12_case_status_text(case)',
        '        result_lower = str(result_text or "").lower()',
        '',
        '        if status_text in {"closed", "archived", "stale"}:',
        '            return f"cycle_resolved_by_status:{status_text}"',
        '        if "previsão confirmada" in result_lower or "validou" in result_lower:',
        '            return "cycle_validated_by_observation"',
        '        if "contradi" in result_lower or "falhou" in result_lower:',
        '            return "cycle_remains_open_after_contradiction"',
        '        if outcome_text:',
        '            return f"cycle_outcome:{outcome_text}"',
        '        return "cycle_state_uncertain"',
        '',
        '    def _v47_12_build_cycle_narrative(self, case, comparison: dict, influence: dict, lineage: dict, result_text: str, closure: str) -> str:',
        '        tension_id = getattr(case, "tension_id", "") if case is not None else ""',
        '        source_pair = getattr(case, "source_pair", "") if case is not None else ""',
        '        comparison_id = str(comparison.get("comparison_id", "") or "")',
        '        influence_id = str(influence.get("influence_id", "") or "")',
        '        lineage_id = str(lineage.get("lineage_id", "") or "")',
        '        hypothesis_id = str(lineage.get("hypothesis_id", "") or "")',
        '        bias = str(influence.get("bias_label", lineage.get("bias_label", "")) or "")',
        '        confidence = float(influence.get("confidence", lineage.get("confidence", 0.0)) or 0.0)',
        '',
        '        parts = [',
        '            f"ciclo v47.12.1 para {tension_id} ({source_pair})",',
        '            f"comparação={comparison_id or \'ausente\'}",',
        '            f"influência={influence_id or \'ausente\'}",',
        '            f"linhagem={lineage_id or \'ausente\'}",',
        '            f"hipótese={hypothesis_id or \'ausente\'}",',
        '            f"viés={bias or \'ausente\'}",',
        '            f"confiança={confidence:.3f}",',
        '            f"fechamento={closure}",',
        '        ]',
        '        return "; ".join(parts)',
        '',
        '    def _v47_12_report_already_recorded(self, tension_id: str, lineage_id: str, validation_result: str) -> bool:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return False',
        '',
        '        self._v47_12_initialize_cycle_report_tables()',
        '        with sqlite3.connect(db_path) as conn:',
        '            row = conn.execute(',
        '                """',
        '                SELECT COUNT(*)',
        '                FROM tension_cognitive_cycle_reports',
        '                WHERE tension_id=? AND lineage_id=? AND validation_result=?',
        '                """',
        '                ,',
        '                (tension_id, lineage_id, validation_result[:800]),',
        '            ).fetchone()',
        '        return bool(row and int(row[0]) > 0)',
        '',
        '    def _v47_12_record_cycle_report_after_validate(self, plan, result_text: str) -> None:',
        '        import sqlite3',
        '',
        '        try:',
        '            action_name = str(getattr(plan, "action_name", "") or "")',
        '            bucket = str(getattr(plan, "curriculum_bucket", "") or "")',
        '            if action_name != "validate":',
        '                return',
        '            if bucket != "routine_validate":',
        '                return',
        '',
        '            case = self._v47_12_find_case_for_plan(plan)',
        '            if case is None:',
        '                return',
        '',
        '            tension_id = str(getattr(case, "tension_id", "") or "")',
        '            source_pair = str(getattr(case, "source_pair", "") or "")',
        '            if not tension_id:',
        '                return',
        '',
        '            comparison = self._v47_12_latest_row_dict("tension_context_comparisons", tension_id)',
        '            influence = self._v47_12_latest_row_dict("tension_prediction_influences", tension_id)',
        '            lineage = self._v47_12_latest_row_dict("tension_hypothesis_lineage", tension_id)',
        '',
        '            comparison_id = str(comparison.get("comparison_id", "") or "")',
        '            influence_id = str(influence.get("influence_id", "") or "")',
        '            lineage_id = str(lineage.get("lineage_id", "") or "")',
        '            hypothesis_id = str(lineage.get("hypothesis_id", "") or "")',
        '            bias_label = str(influence.get("bias_label", lineage.get("bias_label", "")) or "")',
        '            confidence = float(influence.get("confidence", lineage.get("confidence", 0.0)) or 0.0)',
        '',
        '            validation_excerpt = str(result_text or "")[:800]',
        '            if self._v47_12_report_already_recorded(tension_id, lineage_id, validation_excerpt):',
        '                return',
        '',
        '            self._v47_12_initialize_cycle_report_tables()',
        '            db_path = self._v47_9_compare_db_path()',
        '            if not db_path.exists():',
        '                return',
        '',
        '            status_after, outcome_after = self._v47_12_case_status_text(case)',
        '            closure = self._v47_12_closure_assessment(case, result_text)',
        '            step = self._current_step()',
        '            report_id = f"CYCLE:{tension_id}:{step}"',
        '            now = self._v47_9_now_iso()',
        '            narrative = self._v47_12_build_cycle_narrative(case, comparison, influence, lineage, result_text, closure)',
        '',
        '            payload = {',
        '                "report_id": report_id,',
        '                "tension_id": tension_id,',
        '                "source_pair": source_pair,',
        '                "status_after": status_after,',
        '                "outcome_after": outcome_after,',
        '                "comparison_id": comparison_id,',
        '                "influence_id": influence_id,',
        '                "lineage_id": lineage_id,',
        '                "hypothesis_id": hypothesis_id,',
        '                "bias_label": bias_label,',
        '                "confidence": confidence,',
        '                "closure_assessment": closure,',
        '                "validation_result": validation_excerpt,',
        '                "narrative": narrative,',
        '                "effect": "full_cognitive_cycle_report_recorded",',
        '            }',
        '',
        '            with sqlite3.connect(db_path) as conn:',
        '                conn.execute(',
        '                    """',
        '                    INSERT INTO tension_cognitive_cycle_reports (',
        '                        report_id, tension_id, source_pair, timestamp, step,',
        '                        status_after, outcome_after, comparison_id, influence_id, lineage_id,',
        '                        hypothesis_id, validation_result, closure_assessment, narrative, payload_json',
        '                    )',
        '                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        '                    """',
        '                    ,',
        '                    (',
        '                        report_id,',
        '                        tension_id,',
        '                        source_pair,',
        '                        now,',
        '                        step,',
        '                        status_after,',
        '                        outcome_after,',
        '                        comparison_id,',
        '                        influence_id,',
        '                        lineage_id,',
        '                        hypothesis_id,',
        '                        validation_excerpt,',
        '                        closure,',
        '                        narrative,',
        '                        self._v47_9_safe_json(payload),',
        '                    ),',
        '                )',
        '                conn.commit()',
        '',
        '            self.last_cycle_report_lines = [',
        '                "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",',
        '                f"- relatório: {report_id}",',
        '                f"- tensão: {tension_id} ({source_pair})",',
        '                f"- estado final: {status_after} | desfecho={outcome_after}",',
        '                f"- comparação: {comparison_id or \'ausente\'}",',
        '                f"- influência: {influence_id or \'ausente\'}",',
        '                f"- linhagem: {lineage_id or \'ausente\'}",',
        '                f"- hipótese: {hypothesis_id or \'ausente\'}",',
        '                f"- viés: {bias_label or \'ausente\'} | confiança={confidence:.3f}",',
        '                f"- fechamento: {closure}",',
        '                f"- narrativa: {narrative}",',
        '            ]',
        '        except Exception as exc:',
        '            self.last_cycle_report_lines = [',
        '                "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",',
        '                f"- erro ao registrar relatório: {exc}",',
        '            ]',
        '',
        '    def cognitive_cycle_report_summary(self) -> str:',
        '        import sqlite3',
        '',
        '        lines = list(getattr(self, "last_cycle_report_lines", []))',
        '        if lines:',
        '            return chr(10).join(lines)',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return chr(10).join(["RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1", "- banco não encontrado"])',
        '',
        '        self._v47_12_initialize_cycle_report_tables()',
        '        active_id = getattr(self, "active_tension_id", None)',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            if active_id:',
        '                row = conn.execute(',
        '                    """',
        '                    SELECT report_id, tension_id, source_pair, status_after, outcome_after,',
        '                           comparison_id, influence_id, lineage_id, hypothesis_id,',
        '                           closure_assessment, narrative',
        '                    FROM tension_cognitive_cycle_reports',
        '                    WHERE tension_id=?',
        '                    ORDER BY id DESC',
        '                    LIMIT 1',
        '                    """',
        '                    ,',
        '                    (active_id,),',
        '                ).fetchone()',
        '            else:',
        '                row = None',
        '',
        '            if row is None:',
        '                row = conn.execute(',
        '                    """',
        '                    SELECT report_id, tension_id, source_pair, status_after, outcome_after,',
        '                           comparison_id, influence_id, lineage_id, hypothesis_id,',
        '                           closure_assessment, narrative',
        '                    FROM tension_cognitive_cycle_reports',
        '                    ORDER BY id DESC',
        '                    LIMIT 1',
        '                    """',
        '                ).fetchone()',
        '',
        '        if row is None:',
        '            return chr(10).join(',
        '                [',
        '                    "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",',
        '                    "- nenhum ciclo consolidado registrado nesta sessão/banco",',
        '                ]',
        '            )',
        '',
        '        return chr(10).join(',
        '            [',
        '                "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",',
        '                f"- relatório: {row[\'report_id\']}",',
        '                f"- tensão: {row[\'tension_id\']} ({row[\'source_pair\']})",',
        '                f"- estado final: {row[\'status_after\']} | desfecho={row[\'outcome_after\']}",',
        '                f"- comparação: {row[\'comparison_id\']}",',
        '                f"- influência: {row[\'influence_id\']}",',
        '                f"- linhagem: {row[\'lineage_id\']}",',
        '                f"- hipótese: {row[\'hypothesis_id\']}",',
        '                f"- fechamento: {row[\'closure_assessment\']}",',
        '                f"- narrativa: {row[\'narrative\']}",',
        '            ]',
        '        )',
        '',
        '',
    ]
    return chr(10).join(lines)


def apply_safe_patch(dry_run: bool) -> int:
    text = V47_FILE.read_text(encoding="utf-8")
    changes = 0

    if "def _v47_12_record_cycle_report_after_validate" not in text:
        anchor = '    def execute_action(self, plan):\n'
        text, n = replace_once(
            text,
            anchor,
            cycle_methods_block() + anchor,
            "métodos v47.12.1 inseridos antes de execute_action",
        )
        changes += n
    else:
        print_status("PULOU", "métodos v47.12 já existem")

    old_body = (
        '        result = self._execute_action_v47_10_base(plan)\n'
        '        self._v47_11_record_hypothesis_lineage_after_predict(plan, result)\n'
        '        return result\n'
    )
    new_body = (
        '        result = self._execute_action_v47_10_base(plan)\n'
        '        self._v47_11_record_hypothesis_lineage_after_predict(plan, result)\n'
        '        self._v47_12_record_cycle_report_after_validate(plan, result)\n'
        '        return result\n'
    )

    if "self._v47_12_record_cycle_report_after_validate(plan, result)" not in text:
        text, n = replace_once(
            text,
            old_body,
            new_body,
            "execute_action chama relatório consolidado após validate",
        )
        changes += n
    else:
        print_status("PULOU", "execute_action já chama relatório v47.12")

    if "10z - mostrar relatório consolidado do ciclo cognitivo" not in text:
        text, n = replace_once(
            text,
            '        print("10h - mostrar linhagem contextual da hipótese")\n',
            '        print("10h - mostrar linhagem contextual da hipótese")\n'
            '        print("10z - mostrar relatório consolidado do ciclo cognitivo")\n',
            "menu adiciona comando 10z",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10z já existe")

    if 'choice in {"10z", "cycle", "ciclo", "relatorio", "relatório"}' not in text:
        anchor = (
            '            elif choice in {"10h", "lineage", "linhagem", "hypothesis_lineage"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.hypothesis_lineage_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10h", "lineage", "linhagem", "hypothesis_lineage"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.hypothesis_lineage_summary())\n'
            '            elif choice in {"10z", "cycle", "ciclo", "relatorio", "relatório"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.cognitive_cycle_report_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10z",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10z já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x, 10i ou 10h.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x, 10i, 10h ou 10z.")\n',
        "mensagem de comando inválido inclui 10z",
    )
    changes += n

    if dry_run:
        print_status("DRYRUN", f"aplicaria {changes} mudança(s) v47.12.1")
        return changes

    V47_FILE.write_text(text, encoding="utf-8")
    print_status("OK", f"{changes} mudança(s) v47.12.1 aplicadas")
    return changes


def write_manifest(restored_from: Path, broken_backup: Path, changes: int, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "repair": "v47.12.1_cycle_report_safe_repair",
        "restored_from": str(restored_from),
        "broken_backup": str(broken_backup),
        "changes": changes,
        "file": str(V47_FILE),
        "hashes": {},
    }

    for path in (V47_FILE, restored_from, broken_backup):
        if path and path.exists():
            manifest["hashes"][str(path)] = sha256_file(path)

    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {MANIFEST_FILE.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair v47.12.1: relatório consolidado aplicado com indentação segura.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.12.1 — REPAIR DO RELATÓRIO CONSOLIDADO")
    print("=" * 72)
    print(f"Raiz:    {PROJECT_ROOT}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if not V47_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {V47_FILE}")

    ok_before, err_before = compiles(V47_FILE)
    if ok_before:
        print_status("OK", "arquivo atual compila antes do repair")
    else:
        print_status("ERRO", "arquivo atual não compila antes do repair")
        print(err_before.splitlines()[0] if err_before else "erro desconhecido")

    restored_from, broken_backup = restore_pre_v47_12(dry_run=args.dry_run)
    changes = apply_safe_patch(dry_run=args.dry_run)

    if args.dry_run:
        print_status("DRYRUN", "validaria py_compile depois da escrita")
        write_manifest(restored_from, broken_backup, changes, dry_run=True)
        return 0

    ok_after, err_after = compiles(V47_FILE)
    if not ok_after:
        print_status("ERRO", "py_compile falhou após repair v47.12.1")
        print(err_after)
        return 2

    print_status("OK", "py_compile passou após repair v47.12.1")
    write_manifest(restored_from, broken_backup, changes, dry_run=False)

    print()
    print("Repair v47.12.1 concluído.")
    print("Agora rode:")
    print("  py darwin_v47_12_cycle_report_test.py --dry-run")
    print("  py darwin_v47_12_cycle_report_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
