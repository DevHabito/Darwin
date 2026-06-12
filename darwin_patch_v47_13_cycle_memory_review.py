from __future__ import annotations

"""
DARWIN v47.13 — Revisão de Ciclos Passados Antes de Agir

Objetivo:
- A v47.12.1 criou relatórios consolidados do ciclo cognitivo.
- A v47.13 permite que Darwin consulte ciclos passados antes de agir
  quando encontra uma tensão parecida.

Escopo rigoroso:
- Não muda o motor físico do predict.
- Não muda validate.
- Não altera o fechamento de tensões.
- Apenas adiciona memória operacional consultiva antes do compare_context.
- Registra a consulta em tension_cycle_memory_reviews.
- Quando há ciclo passado relevante, o plano usa:
    routine_reviewed_compare_influenced_predict

Uso:
    py darwin_patch_v47_13_cycle_memory_review.py --dry-run
    py darwin_patch_v47_13_cycle_memory_review.py

Teste:
    py darwin_v47_13_cycle_memory_review_test.py --dry-run
    py darwin_v47_13_cycle_memory_review_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_13_cycle_memory_review_manifest.json"


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_13_{now_stamp()}{path.suffix}"

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


def review_methods_block() -> str:
    lines = [
        '    # --------------------------',
        '    # revisão de ciclos passados v47.13',
        '    # --------------------------',
        '',
        '    def _v47_13_initialize_cycle_review_tables(self) -> None:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.execute(',
        '                """',
        '                CREATE TABLE IF NOT EXISTS tension_cycle_memory_reviews (',
        '                    id INTEGER PRIMARY KEY AUTOINCREMENT,',
        '                    review_id TEXT NOT NULL,',
        '                    tension_id TEXT NOT NULL,',
        '                    source_pair TEXT NOT NULL,',
        '                    timestamp TEXT NOT NULL,',
        '                    step INTEGER,',
        '                    matches_count INTEGER NOT NULL DEFAULT 0,',
        '                    best_report_id TEXT NOT NULL DEFAULT \'\',',
        '                    best_source_pair TEXT NOT NULL DEFAULT \'\',',
        '                    best_hypothesis_id TEXT NOT NULL DEFAULT \'\',',
        '                    best_closure_assessment TEXT NOT NULL DEFAULT \'\',',
        '                    best_bias_label TEXT NOT NULL DEFAULT \'\',',
        '                    best_confidence REAL NOT NULL DEFAULT 0.0,',
        '                    similarity_score REAL NOT NULL DEFAULT 0.0,',
        '                    review_summary TEXT NOT NULL DEFAULT \'\',',
        '                    payload_json TEXT NOT NULL DEFAULT \'{}\'',
        '                )',
        '                """',
        '            )',
        '            conn.execute(',
        '                """',
        '                CREATE INDEX IF NOT EXISTS idx_tension_cycle_memory_reviews_tension',
        '                ON tension_cycle_memory_reviews(tension_id, id)',
        '                """',
        '            )',
        '            conn.commit()',
        '',
        '    def _v47_13_pair_tokens(self, pair: str) -> set:',
        '        text = str(pair or "")',
        '        if ">" in text:',
        '            left, right = text.split(">", 1)',
        '            return {left.strip(), right.strip()}',
        '        return {text.strip()} if text.strip() else set()',
        '',
        '    def _v47_13_json_from_text(self, value, fallback):',
        '        import json',
        '        try:',
        '            return json.loads(value) if value else fallback',
        '        except Exception:',
        '            return fallback',
        '',
        '    def _v47_13_recent_cycle_reports(self, limit: int = 30) -> list[dict]:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return []',
        '',
        '        self._v47_12_initialize_cycle_report_tables()',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            rows = conn.execute(',
        '                """',
        '                SELECT report_id, tension_id, source_pair, status_after, outcome_after,',
        '                       comparison_id, influence_id, lineage_id, hypothesis_id,',
        '                       closure_assessment, narrative, payload_json',
        '                FROM tension_cognitive_cycle_reports',
        '                ORDER BY id DESC',
        '                LIMIT ?',
        '                """',
        '                ,',
        '                (int(limit),),',
        '            ).fetchall()',
        '',
        '        reports = []',
        '        for row in rows:',
        '            payload = self._v47_13_json_from_text(row["payload_json"], {})',
        '            reports.append(',
        '                {',
        '                    "report_id": str(row["report_id"] or ""),',
        '                    "tension_id": str(row["tension_id"] or ""),',
        '                    "source_pair": str(row["source_pair"] or ""),',
        '                    "status_after": str(row["status_after"] or ""),',
        '                    "outcome_after": str(row["outcome_after"] or ""),',
        '                    "comparison_id": str(row["comparison_id"] or ""),',
        '                    "influence_id": str(row["influence_id"] or ""),',
        '                    "lineage_id": str(row["lineage_id"] or ""),',
        '                    "hypothesis_id": str(row["hypothesis_id"] or ""),',
        '                    "closure_assessment": str(row["closure_assessment"] or ""),',
        '                    "narrative": str(row["narrative"] or ""),',
        '                    "payload": payload,',
        '                    "bias_label": str(payload.get("bias_label", "") or ""),',
        '                    "confidence": float(payload.get("confidence", 0.0) or 0.0),',
        '                }',
        '            )',
        '        return reports',
        '',
        '    def _v47_13_score_cycle_report(self, case: "LiveTensionCase", report: dict) -> float:',
        '        case_pair = str(getattr(case, "source_pair", "") or "")',
        '        report_pair = str(report.get("source_pair", "") or "")',
        '        case_tokens = self._v47_13_pair_tokens(case_pair)',
        '        report_tokens = self._v47_13_pair_tokens(report_pair)',
        '',
        '        score = 0.0',
        '        if case_pair and report_pair and case_pair == report_pair:',
        '            score += 1.00',
        '',
        '        if case_tokens and report_tokens:',
        '            shared = len(case_tokens.intersection(report_tokens))',
        '            score += 0.25 * shared',
        '',
        '        closure = str(report.get("closure_assessment", "") or "")',
        '        if "resolved" in closure or "validated" in closure or str(report.get("status_after", "")) == "closed":',
        '            score += 0.25',
        '',
        '        confidence = float(report.get("confidence", 0.0) or 0.0)',
        '        score += min(0.25, 0.25 * confidence)',
        '',
        '        return min(1.75, score)',
        '',
        '    def _v47_13_review_past_cycles(self, case: "LiveTensionCase") -> str:',
        '        import sqlite3',
        '',
        '        self._v47_13_initialize_cycle_review_tables()',
        '        reports = self._v47_13_recent_cycle_reports(limit=30)',
        '        scored = []',
        '        for report in reports:',
        '            score = self._v47_13_score_cycle_report(case, report)',
        '            if score >= 0.75:',
        '                item = dict(report)',
        '                item["similarity_score"] = score',
        '                scored.append(item)',
        '',
        '        scored.sort(key=lambda item: float(item.get("similarity_score", 0.0)), reverse=True)',
        '        best = scored[0] if scored else {}',
        '        step = self._current_step()',
        '        review_id = f"REV:{case.tension_id}:{step}"',
        '        now = self._v47_9_now_iso()',
        '',
        '        if best:',
        '            summary = (',
        '                f"revisão de ciclo v47.13: encontrou ciclo passado {best.get(\'report_id\')} "',
        '                f"para {best.get(\'source_pair\')} com similaridade={float(best.get(\'similarity_score\', 0.0)):.3f}; "',
        '                f"hipótese anterior={best.get(\'hypothesis_id\', \'\') or \'ausente\'}; "',
        '                f"fechamento anterior={best.get(\'closure_assessment\', \'\') or \'ausente\'}"',
        '            )',
        '        else:',
        '            summary = ""',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if db_path.exists():',
        '            payload = {',
        '                "review_id": review_id,',
        '                "tension_id": case.tension_id,',
        '                "source_pair": case.source_pair,',
        '                "matches_count": len(scored),',
        '                "best": best,',
        '                "all_matches": scored[:5],',
        '                "decision": "use_prior_cycle_as_contextual_memory" if best else "no_prior_cycle_available",',
        '            }',
        '            with sqlite3.connect(db_path) as conn:',
        '                conn.execute(',
        '                    """',
        '                    INSERT INTO tension_cycle_memory_reviews (',
        '                        review_id, tension_id, source_pair, timestamp, step, matches_count,',
        '                        best_report_id, best_source_pair, best_hypothesis_id,',
        '                        best_closure_assessment, best_bias_label, best_confidence,',
        '                        similarity_score, review_summary, payload_json',
        '                    )',
        '                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        '                    """',
        '                    ,',
        '                    (',
        '                        review_id,',
        '                        case.tension_id,',
        '                        case.source_pair,',
        '                        now,',
        '                        step,',
        '                        len(scored),',
        '                        str(best.get("report_id", "") or ""),',
        '                        str(best.get("source_pair", "") or ""),',
        '                        str(best.get("hypothesis_id", "") or ""),',
        '                        str(best.get("closure_assessment", "") or ""),',
        '                        str(best.get("bias_label", "") or ""),',
        '                        float(best.get("confidence", 0.0) or 0.0),',
        '                        float(best.get("similarity_score", 0.0) or 0.0),',
        '                        summary,',
        '                        self._v47_9_safe_json(payload),',
        '                    ),',
        '                )',
        '                conn.commit()',
        '',
        '        if best:',
        '            self.last_cycle_memory_review_lines = [',
        '                "REVISÃO DE CICLOS PASSADOS v47.13",',
        '                f"- revisão: {review_id}",',
        '                f"- tensão atual: {case.tension_id} ({case.source_pair})",',
        '                f"- ciclos similares encontrados: {len(scored)}",',
        '                f"- melhor ciclo: {best.get(\'report_id\', \'\')}",',
        '                f"- par anterior: {best.get(\'source_pair\', \'\')}",',
        '                f"- hipótese anterior: {best.get(\'hypothesis_id\', \'\')}",',
        '                f"- fechamento anterior: {best.get(\'closure_assessment\', \'\')}",',
        '                f"- similaridade={float(best.get(\'similarity_score\', 0.0)):.3f}",',
        '                "- efeito: memória de ciclo anterior anexada ao motivo da próxima hipótese",',
        '            ]',
        '            return summary',
        '',
        '        self.last_cycle_memory_review_lines = [',
        '            "REVISÃO DE CICLOS PASSADOS v47.13",',
        '            f"- revisão: {review_id}",',
        '            f"- tensão atual: {case.tension_id} ({case.source_pair})",',
        '            "- nenhum ciclo passado suficientemente similar encontrado",',
        '        ]',
        '        return ""',
        '',
        '    def cycle_memory_review_summary(self) -> str:',
        '        import sqlite3',
        '',
        '        lines = list(getattr(self, "last_cycle_memory_review_lines", []))',
        '        if lines:',
        '            return chr(10).join(lines)',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return chr(10).join(["REVISÃO DE CICLOS PASSADOS v47.13", "- banco não encontrado"])',
        '',
        '        self._v47_13_initialize_cycle_review_tables()',
        '        active_id = getattr(self, "active_tension_id", None)',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            if active_id:',
        '                row = conn.execute(',
        '                    """',
        '                    SELECT review_id, tension_id, source_pair, matches_count, best_report_id,',
        '                           best_source_pair, best_hypothesis_id, best_closure_assessment,',
        '                           similarity_score, review_summary',
        '                    FROM tension_cycle_memory_reviews',
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
        '                    SELECT review_id, tension_id, source_pair, matches_count, best_report_id,',
        '                           best_source_pair, best_hypothesis_id, best_closure_assessment,',
        '                           similarity_score, review_summary',
        '                    FROM tension_cycle_memory_reviews',
        '                    ORDER BY id DESC',
        '                    LIMIT 1',
        '                    """',
        '                ).fetchone()',
        '',
        '        if row is None:',
        '            return chr(10).join(',
        '                [',
        '                    "REVISÃO DE CICLOS PASSADOS v47.13",',
        '                    "- nenhuma revisão de ciclo registrada nesta sessão/banco",',
        '                ]',
        '            )',
        '',
        '        return chr(10).join(',
        '            [',
        '                "REVISÃO DE CICLOS PASSADOS v47.13",',
        '                f"- revisão: {row[\'review_id\']}",',
        '                f"- tensão: {row[\'tension_id\']} ({row[\'source_pair\']})",',
        '                f"- ciclos similares: {row[\'matches_count\']}",',
        '                f"- melhor ciclo: {row[\'best_report_id\']}",',
        '                f"- par anterior: {row[\'best_source_pair\']}",',
        '                f"- hipótese anterior: {row[\'best_hypothesis_id\']}",',
        '                f"- fechamento anterior: {row[\'best_closure_assessment\']}",',
        '                f"- similaridade={float(row[\'similarity_score\']):.3f}",',
        '                f"- resumo: {row[\'review_summary\']}",',
        '            ]',
        '        )',
        '',
        '',
    ]
    return chr(10).join(lines)


def patch_v47(text: str) -> tuple[str, int]:
    changes = 0

    if "def _v47_13_review_past_cycles" not in text:
        anchor = '    def _v47_7_resolution_routine_plan(self) -> Optional["ActionPlan"]:\n'
        text, n = replace_once(
            text,
            anchor,
            review_methods_block() + anchor,
            "métodos de revisão de ciclos v47.13 inseridos",
        )
        changes += n
    else:
        print_status("PULOU", "métodos v47.13 já existem")

    if "cycle_memory_review_summary = self._v47_13_review_past_cycles(case)" not in text:
        old = (
            '        stage, next_action = self._v47_7_stage_for_case(case)\n'
            '        compare_context_summary = ""\n'
            '        if stage == "compare_context_before_prediction":\n'
            '            compare_context_summary = self._v47_9_run_compare_context(case)\n'
        )
        new = (
            '        stage, next_action = self._v47_7_stage_for_case(case)\n'
            '        cycle_memory_review_summary = ""\n'
            '        compare_context_summary = ""\n'
            '        if stage == "compare_context_before_prediction":\n'
            '            cycle_memory_review_summary = self._v47_13_review_past_cycles(case)\n'
            '            compare_context_summary = self._v47_9_run_compare_context(case)\n'
        )
        text, n = replace_once(
            text,
            old,
            new,
            "micro-rotina revisa ciclos passados antes do compare_context",
        )
        changes += n
    else:
        print_status("PULOU", "revisão de ciclos já integrada antes do compare_context")

    if "routine_reviewed_compare_influenced_predict" not in text:
        old = (
            '        if compare_context_summary:\n'
            '            prediction_influence_summary = self._v47_10_build_prediction_influence(case)\n'
            '            bucket = "routine_compare_influenced_predict"\n'
            '            if prediction_influence_summary:\n'
            '                reason = f"{compare_context_summary}; {prediction_influence_summary}; {reason}"\n'
            '            else:\n'
            '                reason = f"{compare_context_summary}; {reason}"\n'
        )
        new = (
            '        if compare_context_summary:\n'
            '            prediction_influence_summary = self._v47_10_build_prediction_influence(case)\n'
            '            if cycle_memory_review_summary:\n'
            '                bucket = "routine_reviewed_compare_influenced_predict"\n'
            '            else:\n'
            '                bucket = "routine_compare_influenced_predict"\n'
            '            if prediction_influence_summary and cycle_memory_review_summary:\n'
            '                reason = f"{cycle_memory_review_summary}; {compare_context_summary}; {prediction_influence_summary}; {reason}"\n'
            '            elif prediction_influence_summary:\n'
            '                reason = f"{compare_context_summary}; {prediction_influence_summary}; {reason}"\n'
            '            elif cycle_memory_review_summary:\n'
            '                reason = f"{cycle_memory_review_summary}; {compare_context_summary}; {reason}"\n'
            '            else:\n'
            '                reason = f"{compare_context_summary}; {reason}"\n'
        )
        text, n = replace_once(
            text,
            old,
            new,
            "reason/bucket incorporam revisão de ciclos passados",
        )
        changes += n
    else:
        print_status("PULOU", "bucket routine_reviewed_compare_influenced_predict já existe")

    old_guard = '            if bucket != "routine_compare_influenced_predict":\n                return\n'
    new_guard = '            if bucket not in {"routine_compare_influenced_predict", "routine_reviewed_compare_influenced_predict"}:\n                return\n'
    text, n = replace_once(
        text,
        old_guard,
        new_guard,
        "linhagem aceita bucket com revisão de memória",
    )
    changes += n

    if "10y - mostrar revisão de ciclos passados" not in text:
        text, n = replace_once(
            text,
            '        print("10z - mostrar relatório consolidado do ciclo cognitivo")\n',
            '        print("10z - mostrar relatório consolidado do ciclo cognitivo")\n'
            '        print("10y - mostrar revisão de ciclos passados")\n',
            "menu adiciona comando 10y",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10y já existe")

    if 'choice in {"10y", "review", "revisao", "revisão", "memoria", "memória"}' not in text:
        anchor = (
            '            elif choice in {"10z", "cycle", "ciclo", "relatorio", "relatório"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.cognitive_cycle_report_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10z", "cycle", "ciclo", "relatorio", "relatório"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.cognitive_cycle_report_summary())\n'
            '            elif choice in {"10y", "review", "revisao", "revisão", "memoria", "memória"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.cycle_memory_review_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10y",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10y já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x, 10i, 10h ou 10z.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x, 10i, 10h, 10z ou 10y.")\n',
        "mensagem de comando inválido inclui 10y",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.13_cycle_memory_review",
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
    parser = argparse.ArgumentParser(description="Patch v47.13: revisão de ciclos passados antes de agir.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.13 — REVISÃO DE CICLOS PASSADOS")
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
    print("Patch v47.13 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_13_cycle_memory_review_test.py --dry-run")
    print("  py darwin_v47_13_cycle_memory_review_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
