from __future__ import annotations

"""
DARWIN v47.10 — Influência Real do compare_context na Hipótese

Objetivo:
- A v47.9.1 executa e persiste compare_context antes do predict.
- A v47.10 faz o resultado da comparação influenciar explicitamente a hipótese:
  compare_context -> prediction_influence -> predict.

Escopo rigoroso:
- Não altera o motor físico do predict.
- Não inventa novo operador amplo.
- Cria uma camada auditável de influência contextual sobre a hipótese.
- Registra essa influência em tension_prediction_influences.
- O plano muda de routine_compare_then_predict para routine_compare_influenced_predict.

Uso:
    py darwin_patch_v47_10_prediction_influence.py --dry-run
    py darwin_patch_v47_10_prediction_influence.py

Teste:
    py darwin_v47_10_prediction_influence_test.py --dry-run
    py darwin_v47_10_prediction_influence_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_10_prediction_influence_manifest.json"


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_10_{now_stamp()}{path.suffix}"

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


def influence_methods_block() -> str:
    lines = [
        '    # --------------------------',
        '    # influência contextual na hipótese v47.10',
        '    # --------------------------',
        '',
        '    def _v47_10_initialize_influence_tables(self) -> None:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.execute(',
        '                """',
        '                CREATE TABLE IF NOT EXISTS tension_prediction_influences (',
        '                    id INTEGER PRIMARY KEY AUTOINCREMENT,',
        '                    influence_id TEXT NOT NULL,',
        '                    comparison_id TEXT NOT NULL DEFAULT \'\',',
        '                    tension_id TEXT NOT NULL,',
        '                    source_pair TEXT NOT NULL,',
        '                    timestamp TEXT NOT NULL,',
        '                    step INTEGER,',
        '                    influence_kind TEXT NOT NULL,',
        '                    bias_label TEXT NOT NULL,',
        '                    confidence REAL NOT NULL DEFAULT 0.0,',
        '                    overlap_score REAL NOT NULL DEFAULT 0.0,',
        '                    ambiguity_score REAL NOT NULL DEFAULT 0.0,',
        '                    summary TEXT NOT NULL DEFAULT \'\',',
        '                    payload_json TEXT NOT NULL DEFAULT \'{}\'',
        '                )',
        '                """',
        '            )',
        '            conn.execute(',
        '                """',
        '                CREATE INDEX IF NOT EXISTS idx_tension_prediction_influences_tension',
        '                ON tension_prediction_influences(tension_id, id)',
        '                """',
        '            )',
        '            conn.commit()',
        '',
        '    def _v47_10_latest_context_comparison(self, case: "LiveTensionCase") -> dict:',
        '        import json',
        '        import sqlite3',
        '',
        '        self._v47_9_initialize_compare_tables()',
        '        self._v47_10_initialize_influence_tables()',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return {}',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            row = conn.execute(',
        '                """',
        '                SELECT comparison_id, tension_id, source_pair, timestamp, step, stage,',
        '                       inherited_pairs_json, source_labels_json, overlap_score,',
        '                       ambiguity_score, summary, payload_json',
        '                FROM tension_context_comparisons',
        '                WHERE tension_id=?',
        '                ORDER BY id DESC',
        '                LIMIT 1',
        '                """',
        '                ,',
        '                (case.tension_id,),',
        '            ).fetchone()',
        '',
        '        if row is None:',
        '            return {}',
        '',
        '        def parse_json(value, fallback):',
        '            try:',
        '                return json.loads(value) if value else fallback',
        '            except Exception:',
        '                return fallback',
        '',
        '        return {',
        '            "comparison_id": str(row["comparison_id"] or ""),',
        '            "tension_id": str(row["tension_id"] or ""),',
        '            "source_pair": str(row["source_pair"] or ""),',
        '            "timestamp": str(row["timestamp"] or ""),',
        '            "step": row["step"],',
        '            "stage": str(row["stage"] or ""),',
        '            "inherited_pairs": parse_json(row["inherited_pairs_json"], []),',
        '            "source_labels": parse_json(row["source_labels_json"], []),',
        '            "overlap_score": float(row["overlap_score"] or 0.0),',
        '            "ambiguity_score": float(row["ambiguity_score"] or 0.0),',
        '            "summary": str(row["summary"] or ""),',
        '            "payload": parse_json(row["payload_json"], {}),',
        '        }',
        '',
        '    def _v47_10_bias_from_context(self, comparison: dict) -> tuple[str, float, str]:',
        '        labels = [str(x) for x in comparison.get("source_labels", [])]',
        '        inherited = [str(x) for x in comparison.get("inherited_pairs", [])]',
        '        overlap = float(comparison.get("overlap_score", 0.0) or 0.0)',
        '        ambiguity = float(comparison.get("ambiguity_score", 0.0) or 0.0)',
        '',
        '        stable_markers = {',
        '            "with_block_top",',
        '            "with_nonrolling_top",',
        '            "with_stackable_context",',
        '        }',
        '        unstable_markers = {',
        '            "with_rolling_top",',
        '            "with_toy_top",',
        '            "with_nonstackable_top",',
        '        }',
        '',
        '        stable_hits = sum(1 for label in labels if label in stable_markers)',
        '        unstable_hits = sum(1 for label in labels if label in unstable_markers)',
        '',
        '        confidence = min(1.0, 0.35 + 0.35 * overlap + 0.20 * ambiguity + 0.03 * len(inherited))',
        '',
        '        if stable_hits > unstable_hits:',
        '            return "bias_toward_stable_probe", confidence, "marcadores contextuais favorecem estabilidade"',
        '        if unstable_hits > stable_hits:',
        '            return "bias_toward_unstable_probe", confidence, "marcadores contextuais favorecem instabilidade"',
        '        if overlap >= 0.55 and ambiguity >= 0.25:',
        '            return "bias_toward_context_guarded_probe", confidence, "overlap e ambiguidade exigem hipótese guardada"',
        '        return "bias_toward_cautious_probe", confidence, "comparação insuficiente para viés forte"',
        '',
        '    def _v47_10_build_prediction_influence(self, case: "LiveTensionCase") -> str:',
        '        import sqlite3',
        '',
        '        comparison = self._v47_10_latest_context_comparison(case)',
        '        if not comparison:',
        '            self.last_prediction_influence_lines = [',
        '                "INFLUÊNCIA CONTEXTUAL v47.10",',
        '                f"- tensão: {case.tension_id} ({case.source_pair})",',
        '                "- nenhuma comparação contextual disponível para influenciar a hipótese",',
        '            ]',
        '            return ""',
        '',
        '        bias_label, confidence, rationale = self._v47_10_bias_from_context(comparison)',
        '        step = self._current_step()',
        '        influence_id = f"INF:{case.tension_id}:{step}"',
        '        now = self._v47_9_now_iso()',
        '        overlap = float(comparison.get("overlap_score", 0.0) or 0.0)',
        '        ambiguity = float(comparison.get("ambiguity_score", 0.0) or 0.0)',
        '        comparison_id = str(comparison.get("comparison_id", "") or "")',
        '',
        '        summary = (',
        '            f"influência contextual v47.10: {bias_label} com confiança={confidence:.3f}; "',
        '            f"overlap={overlap:.3f}; ambiguidade={ambiguity:.3f}; {rationale}"',
        '        )',
        '',
        '        payload = {',
        '            "influence_id": influence_id,',
        '            "comparison_id": comparison_id,',
        '            "tension_id": case.tension_id,',
        '            "source_pair": case.source_pair,',
        '            "bias_label": bias_label,',
        '            "confidence": confidence,',
        '            "rationale": rationale,',
        '            "comparison": comparison,',
        '            "decision": "prediction_reason_modified_by_context",',
        '        }',
        '',
        '        self._v47_10_initialize_influence_tables()',
        '        db_path = self._v47_9_compare_db_path()',
        '        if db_path.exists():',
        '            with sqlite3.connect(db_path) as conn:',
        '                conn.execute(',
        '                    """',
        '                    INSERT INTO tension_prediction_influences (',
        '                        influence_id, comparison_id, tension_id, source_pair, timestamp, step,',
        '                        influence_kind, bias_label, confidence, overlap_score,',
        '                        ambiguity_score, summary, payload_json',
        '                    )',
        '                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        '                    """',
        '                    ,',
        '                    (',
        '                        influence_id,',
        '                        comparison_id,',
        '                        case.tension_id,',
        '                        case.source_pair,',
        '                        now,',
        '                        step,',
        '                        "contextual_prediction_bias",',
        '                        bias_label,',
        '                        confidence,',
        '                        overlap,',
        '                        ambiguity,',
        '                        summary,',
        '                        self._v47_9_safe_json(payload),',
        '                    ),',
        '                )',
        '                conn.commit()',
        '',
        '        self.last_prediction_influence_lines = [',
        '            "INFLUÊNCIA CONTEXTUAL v47.10",',
        '            f"- influência: {influence_id}",',
        '            f"- comparação-base: {comparison_id}",',
        '            f"- tensão: {case.tension_id} ({case.source_pair})",',
        '            f"- viés: {bias_label}",',
        '            f"- confiança={confidence:.3f} | overlap={overlap:.3f} | ambiguidade={ambiguity:.3f}",',
        '            f"- racional: {rationale}",',
        '            "- efeito: motivo da hipótese modificado pela comparação contextual",',
        '        ]',
        '',
        '        return summary',
        '',
        '    def prediction_influence_summary(self) -> str:',
        '        import sqlite3',
        '',
        '        lines = list(getattr(self, "last_prediction_influence_lines", []))',
        '        if lines:',
        '            return chr(10).join(lines)',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return chr(10).join(["INFLUÊNCIA CONTEXTUAL v47.10", "- banco não encontrado"])',
        '',
        '        self._v47_10_initialize_influence_tables()',
        '        active_id = getattr(self, "active_tension_id", None)',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            if active_id:',
        '                row = conn.execute(',
        '                    """',
        '                    SELECT influence_id, comparison_id, tension_id, source_pair, timestamp,',
        '                           bias_label, confidence, overlap_score, ambiguity_score, summary',
        '                    FROM tension_prediction_influences',
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
        '                    SELECT influence_id, comparison_id, tension_id, source_pair, timestamp,',
        '                           bias_label, confidence, overlap_score, ambiguity_score, summary',
        '                    FROM tension_prediction_influences',
        '                    ORDER BY id DESC',
        '                    LIMIT 1',
        '                    """',
        '                ).fetchone()',
        '',
        '        if row is None:',
        '            return chr(10).join(',
        '                [',
        '                    "INFLUÊNCIA CONTEXTUAL v47.10",',
        '                    "- nenhuma influência contextual registrada nesta sessão/banco",',
        '                ]',
        '            )',
        '',
        '        return chr(10).join(',
        '            [',
        '                "INFLUÊNCIA CONTEXTUAL v47.10",',
        '                f"- influência: {row[\'influence_id\']}",',
        '                f"- comparação-base: {row[\'comparison_id\']}",',
        '                f"- tensão: {row[\'tension_id\']} ({row[\'source_pair\']})",',
        '                f"- viés: {row[\'bias_label\']}",',
        '                f"- confiança={float(row[\'confidence\']):.3f} | overlap={float(row[\'overlap_score\']):.3f} | ambiguidade={float(row[\'ambiguity_score\']):.3f}",',
        '                f"- resumo: {row[\'summary\']}",',
        '            ]',
        '        )',
        '',
        '',
    ]
    return chr(10).join(lines)


def patch_v47(text: str) -> tuple[str, int]:
    changes = 0

    if "def _v47_10_build_prediction_influence" not in text:
        anchor = '    def _v47_7_resolution_routine_plan(self) -> Optional["ActionPlan"]:\n'
        text, n = replace_once(
            text,
            anchor,
            influence_methods_block() + anchor,
            "métodos de influência contextual v47.10 inseridos",
        )
        changes += n
    else:
        print_status("PULOU", "métodos v47.10 já existem")

    if "prediction_influence_summary = self._v47_10_build_prediction_influence(case)" not in text:
        old = (
            '        if compare_context_summary:\n'
            '            bucket = "routine_compare_then_predict"\n'
            '            reason = f"{compare_context_summary}; {reason}"\n'
            '\n'
            '        routine_id = self._v47_7_upsert_routine(case, stage, next_action, reason)\n'
        )
        new = (
            '        if compare_context_summary:\n'
            '            prediction_influence_summary = self._v47_10_build_prediction_influence(case)\n'
            '            bucket = "routine_compare_influenced_predict"\n'
            '            if prediction_influence_summary:\n'
            '                reason = f"{compare_context_summary}; {prediction_influence_summary}; {reason}"\n'
            '            else:\n'
            '                reason = f"{compare_context_summary}; {reason}"\n'
            '\n'
            '        routine_id = self._v47_7_upsert_routine(case, stage, next_action, reason)\n'
        )
        text, n = replace_once(
            text,
            old,
            new,
            "compare_context agora influencia o motivo da hipótese",
        )
        changes += n
    else:
        print_status("PULOU", "influência contextual já integrada ao reason")

    if "10i - mostrar influência contextual na hipótese" not in text:
        text, n = replace_once(
            text,
            '        print("10x - mostrar última comparação contextual")\n',
            '        print("10x - mostrar última comparação contextual")\n'
            '        print("10i - mostrar influência contextual na hipótese")\n',
            "menu adiciona comando 10i",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10i já existe")

    if 'choice in {"10i", "influence", "influencia", "influência"}' not in text:
        anchor = (
            '            elif choice in {"10x", "context", "comparar", "compare"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.context_comparison_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10x", "context", "comparar", "compare"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.context_comparison_summary())\n'
            '            elif choice in {"10i", "influence", "influencia", "influência"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.prediction_influence_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10i",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10i já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p ou 10x.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x ou 10i.")\n',
        "mensagem de comando inválido inclui 10i",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.10_prediction_influence",
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
    parser = argparse.ArgumentParser(description="Patch v47.10: influência contextual na hipótese.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.10 — INFLUÊNCIA CONTEXTUAL NA HIPÓTESE")
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
    print("Patch v47.10 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_10_prediction_influence_test.py --dry-run")
    print("  py darwin_v47_10_prediction_influence_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
