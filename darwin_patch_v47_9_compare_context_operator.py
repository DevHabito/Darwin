from __future__ import annotations

"""
DARWIN v47.9 — Operador Real compare_context

Objetivo:
- Tornar real o estágio compare_context_before_prediction introduzido em v47.8.1.
- Antes do predict, quando a política escolher compare_context_before_prediction,
  Darwin executa uma comparação contextual mínima e persistente.
- A ação externa continua segura: predict/validate.
- O operador real registra análise em:
  tension_context_comparisons

Uso:
    py darwin_patch_v47_9_compare_context_operator.py --dry-run
    py darwin_patch_v47_9_compare_context_operator.py

Teste:
    py darwin_v47_9_compare_context_operator_test.py --dry-run
    py darwin_v47_9_compare_context_operator_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_9_compare_context_operator_manifest.json"


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_9_{now_stamp()}{path.suffix}"

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


def compare_methods_block() -> str:
    lines = [
        '    # --------------------------',
        '    # operador compare_context v47.9',
        '    # --------------------------',
        '',
        '    def _v47_9_compare_db_path(self):',
        '        from pathlib import Path',
        '        return Path("darwin_home") / "darwin.db"',
        '',
        '    def _v47_9_now_iso(self) -> str:',
        '        from datetime import datetime, timezone',
        '        return datetime.now(timezone.utc).isoformat(timespec="seconds")',
        '',
        '    def _v47_9_safe_json(self, value) -> str:',
        '        import json',
        '        try:',
        '            return json.dumps(value, ensure_ascii=False, sort_keys=True)',
        '        except Exception:',
        '            return json.dumps(str(value), ensure_ascii=False)',
        '',
        '    def _v47_9_initialize_compare_tables(self) -> None:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.execute(',
        '                """',
        '                CREATE TABLE IF NOT EXISTS tension_context_comparisons (',
        '                    id INTEGER PRIMARY KEY AUTOINCREMENT,',
        '                    comparison_id TEXT NOT NULL,',
        '                    tension_id TEXT NOT NULL,',
        '                    source_pair TEXT NOT NULL,',
        '                    timestamp TEXT NOT NULL,',
        '                    step INTEGER,',
        '                    stage TEXT NOT NULL,',
        '                    inherited_pairs_json TEXT NOT NULL DEFAULT \'[]\',',
        '                    source_labels_json TEXT NOT NULL DEFAULT \'[]\',',
        '                    overlap_score REAL NOT NULL DEFAULT 0.0,',
        '                    ambiguity_score REAL NOT NULL DEFAULT 0.0,',
        '                    summary TEXT NOT NULL DEFAULT \'\',',
        '                    payload_json TEXT NOT NULL DEFAULT \'{}\'',
        '                )',
        '                """',
        '            )',
        '            conn.execute(',
        '                """',
        '                CREATE INDEX IF NOT EXISTS idx_tension_context_comparisons_tension',
        '                ON tension_context_comparisons(tension_id, id)',
        '                """',
        '            )',
        '            conn.commit()',
        '',
        '    def _v47_9_pair_parts(self, pair: str) -> tuple[str, str]:',
        '        text = str(pair or "")',
        '        if ">" not in text:',
        '            return text, ""',
        '        left, right = text.split(">", 1)',
        '        return left.strip(), right.strip()',
        '',
        '    def _v47_9_context_overlap(self, case: "LiveTensionCase") -> dict:',
        '        inherited = [str(x) for x in list(getattr(case, "inherited_pairs", ()) or [])]',
        '        labels = [str(x) for x in list(getattr(case, "source_labels", ()) or [])]',
        '        lower = str(getattr(case, "source_lower", "") or "")',
        '        upper = str(getattr(case, "source_upper", "") or "")',
        '',
        '        lower_refs = 0',
        '        upper_refs = 0',
        '        cross_refs = 0',
        '        inherited_parts = []',
        '',
        '        for pair in inherited:',
        '            a, b = self._v47_9_pair_parts(pair)',
        '            inherited_parts.append([a, b])',
        '            if lower and (a == lower or b == lower):',
        '                lower_refs += 1',
        '            if upper and (a == upper or b == upper):',
        '                upper_refs += 1',
        '            if lower and upper and ((a == lower and b == upper) or (a == upper and b == lower)):',
        '                cross_refs += 1',
        '',
        '        ambiguity = float(getattr(case, "ambiguity_score", 0.0) or 0.0)',
        '        inherited_weight = min(0.45, 0.09 * len(inherited))',
        '        label_weight = min(0.25, 0.04 * len(labels))',
        '        reference_weight = min(0.25, 0.05 * (lower_refs + upper_refs + cross_refs))',
        '        ambiguity_weight = min(0.20, 0.20 * ambiguity)',
        '        overlap_score = min(1.0, inherited_weight + label_weight + reference_weight + ambiguity_weight)',
        '',
        '        return {',
        '            "source_pair": case.source_pair,',
        '            "source_lower": lower,',
        '            "source_upper": upper,',
        '            "inherited_pairs": inherited,',
        '            "inherited_parts": inherited_parts,',
        '            "source_labels": labels,',
        '            "lower_refs": lower_refs,',
        '            "upper_refs": upper_refs,',
        '            "cross_refs": cross_refs,',
        '            "ambiguity_score": ambiguity,',
        '            "overlap_score": overlap_score,',
        '        }',
        '',
        '    def _v47_9_run_compare_context(self, case: "LiveTensionCase") -> str:',
        '        import sqlite3',
        '',
        '        self._v47_9_initialize_compare_tables()',
        '        db_path = self._v47_9_compare_db_path()',
        '        context = self._v47_9_context_overlap(case)',
        '        step = self._current_step()',
        '        comparison_id = f"CTX:{case.tension_id}:{step}"',
        '        now = self._v47_9_now_iso()',
        '',
        '        inherited = context["inherited_pairs"]',
        '        labels = context["source_labels"]',
        '        overlap = float(context["overlap_score"])',
        '        ambiguity = float(context["ambiguity_score"])',
        '',
        '        if inherited:',
        '            summary = (',
        '                f"compare_context v47.9: {case.source_pair} comparado com "',
        '                f"{len(inherited)} par(es) herdado(s); overlap={overlap:.3f}; "',
        '                f"ambiguidade={ambiguity:.3f}; seguir para hipótese controlada"',
        '            )',
        '        else:',
        '            summary = (',
        '                f"compare_context v47.9: {case.source_pair} sem pares herdados úteis; "',
        '                "seguir para hipótese controlada"',
        '            )',
        '',
        '        payload = {',
        '            "comparison_id": comparison_id,',
        '            "tension_id": case.tension_id,',
        '            "stage": "compare_context_before_prediction",',
        '            "context": context,',
        '            "decision": "predict_after_context_comparison",',
        '        }',
        '',
        '        if db_path.exists():',
        '            with sqlite3.connect(db_path) as conn:',
        '                conn.execute(',
        '                    """',
        '                    INSERT INTO tension_context_comparisons (',
        '                        comparison_id, tension_id, source_pair, timestamp, step, stage,',
        '                        inherited_pairs_json, source_labels_json, overlap_score,',
        '                        ambiguity_score, summary, payload_json',
        '                    )',
        '                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        '                    """',
        '                    ,',
        '                    (',
        '                        comparison_id,',
        '                        case.tension_id,',
        '                        case.source_pair,',
        '                        now,',
        '                        step,',
        '                        "compare_context_before_prediction",',
        '                        self._v47_9_safe_json(inherited),',
        '                        self._v47_9_safe_json(labels),',
        '                        overlap,',
        '                        ambiguity,',
        '                        summary,',
        '                        self._v47_9_safe_json(payload),',
        '                    ),',
        '                )',
        '                conn.commit()',
        '',
        '        self.last_context_comparison_lines = [',
        '            "COMPARAÇÃO CONTEXTUAL v47.9",',
        '            f"- comparação: {comparison_id}",',
        '            f"- tensão: {case.tension_id} ({case.source_pair})",',
        '            f"- pares herdados: {len(inherited)}",',
        '            f"- labels de origem: {len(labels)}",',
        '            f"- overlap={overlap:.3f} | ambiguidade={ambiguity:.3f}",',
        '            f"- decisão: predict_after_context_comparison",',
        '            f"- resumo: {summary}",',
        '        ]',
        '',
        '        return summary',
        '',
        '    def context_comparison_summary(self) -> str:',
        '        import sqlite3',
        '',
        '        lines = list(getattr(self, "last_context_comparison_lines", []))',
        '        if lines:',
        '            return chr(10).join(lines)',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return chr(10).join(["COMPARAÇÃO CONTEXTUAL v47.9", "- banco não encontrado"])',
        '',
        '        self._v47_9_initialize_compare_tables()',
        '        active_id = getattr(self, "active_tension_id", None)',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            if active_id:',
        '                row = conn.execute(',
        '                    """',
        '                    SELECT comparison_id, tension_id, source_pair, timestamp, stage,',
        '                           overlap_score, ambiguity_score, summary',
        '                    FROM tension_context_comparisons',
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
        '                    SELECT comparison_id, tension_id, source_pair, timestamp, stage,',
        '                           overlap_score, ambiguity_score, summary',
        '                    FROM tension_context_comparisons',
        '                    ORDER BY id DESC',
        '                    LIMIT 1',
        '                    """',
        '                ).fetchone()',
        '',
        '        if row is None:',
        '            return chr(10).join(',
        '                [',
        '                    "COMPARAÇÃO CONTEXTUAL v47.9",',
        '                    "- nenhuma comparação contextual registrada nesta sessão/banco",',
        '                ]',
        '            )',
        '',
        '        return chr(10).join(',
        '            [',
        '                "COMPARAÇÃO CONTEXTUAL v47.9",',
        '                f"- comparação: {row[\'comparison_id\']}",',
        '                f"- tensão: {row[\'tension_id\']} ({row[\'source_pair\']})",',
        '                f"- estágio: {row[\'stage\']}",',
        '                f"- overlap={float(row[\'overlap_score\']):.3f} | ambiguidade={float(row[\'ambiguity_score\']):.3f}",',
        '                f"- resumo: {row[\'summary\']}",',
        '            ]',
        '        )',
        '',
        '',
    ]
    return chr(10).join(lines)


def patch_v47(text: str) -> tuple[str, int]:
    changes = 0

    if "def _v47_9_run_compare_context" not in text:
        anchor = '    def _v47_7_resolution_routine_plan(self) -> Optional["ActionPlan"]:\n'
        text, n = replace_once(
            text,
            anchor,
            compare_methods_block() + anchor,
            "métodos compare_context v47.9 inseridos",
        )
        changes += n
    else:
        print_status("PULOU", "métodos compare_context v47.9 já existem")

    if "compare_context_summary = self._v47_9_run_compare_context(case)" not in text:
        old = (
            '        stage, next_action = self._v47_7_stage_for_case(case)\n'
            '\n'
            '        # A micro-rotina mantém a dívida como sonda viva quando ainda há déficit.\n'
        )
        new = (
            '        stage, next_action = self._v47_7_stage_for_case(case)\n'
            '        compare_context_summary = ""\n'
            '        if stage == "compare_context_before_prediction":\n'
            '            compare_context_summary = self._v47_9_run_compare_context(case)\n'
            '\n'
            '        # A micro-rotina mantém a dívida como sonda viva quando ainda há déficit.\n'
        )
        text, n = replace_once(
            text,
            old,
            new,
            "micro-rotina executa compare_context antes do predict",
        )
        changes += n
    else:
        print_status("PULOU", "chamada compare_context já existe")

    if "routine_compare_then_predict" not in text:
        old = '        routine_id = self._v47_7_upsert_routine(case, stage, next_action, reason)\n'
        new = (
            '        if compare_context_summary:\n'
            '            bucket = "routine_compare_then_predict"\n'
            '            reason = f"{compare_context_summary}; {reason}"\n'
            '\n'
            '        routine_id = self._v47_7_upsert_routine(case, stage, next_action, reason)\n'
        )
        text, n = replace_once(
            text,
            old,
            new,
            "reason/bucket incorporam comparação contextual",
        )
        changes += n
    else:
        print_status("PULOU", "bucket routine_compare_then_predict já existe")

    if "10x - mostrar última comparação contextual" not in text:
        text, n = replace_once(
            text,
            '        print("10p - mostrar seletor de política da micro-rotina")\n',
            '        print("10p - mostrar seletor de política da micro-rotina")\n'
            '        print("10x - mostrar última comparação contextual")\n',
            "menu adiciona comando 10x",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10x já existe")

    if 'choice in {"10x", "context", "comparar", "compare"}' not in text:
        anchor = (
            '            elif choice in {"10p", "policy", "politica", "política"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.tension_resolution_policy_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10p", "policy", "politica", "política"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.tension_resolution_policy_summary())\n'
            '            elif choice in {"10x", "context", "comparar", "compare"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.context_comparison_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10x",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10x já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m ou 10p.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p ou 10x.")\n',
        "mensagem de comando inválido inclui 10x",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.9_compare_context_operator",
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
    parser = argparse.ArgumentParser(description="Patch v47.9: operador real compare_context.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.9 — OPERADOR REAL compare_context")
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
    print("Patch v47.9 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_9_compare_context_operator_test.py --dry-run")
    print("  py darwin_v47_9_compare_context_operator_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
