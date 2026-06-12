from __future__ import annotations

"""
DARWIN v47.11 — Hipótese com Linhagem Contextual

Objetivo:
- A v47.10 fez a comparação contextual influenciar o motivo do predict.
- A v47.11 registra essa influência como linhagem formal da hipótese:
  compare_context_id + influence_id + bias_label + confidence + hypothesis_id.

Escopo rigoroso:
- Não muda o motor físico do predict.
- Não muda o resultado da hipótese.
- Apenas cria uma camada persistente, auditável e pós-ação:
  tension_hypothesis_lineage.
- Envolve execute_action com um wrapper seguro:
  execute_action -> _execute_action_v47_10_base -> registra linhagem se aplicável.

Uso:
    py darwin_patch_v47_11_hypothesis_lineage.py --dry-run
    py darwin_patch_v47_11_hypothesis_lineage.py

Teste:
    py darwin_v47_11_hypothesis_lineage_test.py --dry-run
    py darwin_v47_11_hypothesis_lineage_test.py
"""

import argparse
import hashlib
import json
import py_compile
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
BACKUP_DIR = PROJECT_ROOT / "v47_patch_backups"
MANIFEST_FILE = PROJECT_ROOT / "v47_11_hypothesis_lineage_manifest.json"


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_11_{now_stamp()}{path.suffix}"

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


def lineage_methods_block() -> str:
    lines = [
        '    # --------------------------',
        '    # linhagem contextual da hipótese v47.11',
        '    # --------------------------',
        '',
        '    def _v47_11_initialize_lineage_tables(self) -> None:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.execute(',
        '                """',
        '                CREATE TABLE IF NOT EXISTS tension_hypothesis_lineage (',
        '                    id INTEGER PRIMARY KEY AUTOINCREMENT,',
        '                    lineage_id TEXT NOT NULL,',
        '                    hypothesis_id TEXT NOT NULL DEFAULT \'\',',
        '                    tension_id TEXT NOT NULL,',
        '                    source_pair TEXT NOT NULL,',
        '                    comparison_id TEXT NOT NULL DEFAULT \'\',',
        '                    influence_id TEXT NOT NULL DEFAULT \'\',',
        '                    bias_label TEXT NOT NULL DEFAULT \'\',',
        '                    confidence REAL NOT NULL DEFAULT 0.0,',
        '                    timestamp TEXT NOT NULL,',
        '                    step INTEGER,',
        '                    action_signature TEXT NOT NULL DEFAULT \'\',',
        '                    status TEXT NOT NULL DEFAULT \'recorded\',',
        '                    result_excerpt TEXT NOT NULL DEFAULT \'\',',
        '                    payload_json TEXT NOT NULL DEFAULT \'{}\'',
        '                )',
        '                """',
        '            )',
        '            conn.execute(',
        '                """',
        '                CREATE INDEX IF NOT EXISTS idx_tension_hypothesis_lineage_tension',
        '                ON tension_hypothesis_lineage(tension_id, id)',
        '                """',
        '            )',
        '            conn.execute(',
        '                """',
        '                CREATE INDEX IF NOT EXISTS idx_tension_hypothesis_lineage_hypothesis',
        '                ON tension_hypothesis_lineage(hypothesis_id, id)',
        '                """',
        '            )',
        '            conn.commit()',
        '',
        '    def _v47_11_latest_prediction_influence(self, tension_id: str) -> dict:',
        '        import json',
        '        import sqlite3',
        '',
        '        self._v47_10_initialize_influence_tables()',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return {}',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            row = conn.execute(',
        '                """',
        '                SELECT influence_id, comparison_id, tension_id, source_pair, timestamp,',
        '                       bias_label, confidence, overlap_score, ambiguity_score, summary, payload_json',
        '                FROM tension_prediction_influences',
        '                WHERE tension_id=?',
        '                ORDER BY id DESC',
        '                LIMIT 1',
        '                """',
        '                ,',
        '                (tension_id,),',
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
        '            "influence_id": str(row["influence_id"] or ""),',
        '            "comparison_id": str(row["comparison_id"] or ""),',
        '            "tension_id": str(row["tension_id"] or ""),',
        '            "source_pair": str(row["source_pair"] or ""),',
        '            "timestamp": str(row["timestamp"] or ""),',
        '            "bias_label": str(row["bias_label"] or ""),',
        '            "confidence": float(row["confidence"] or 0.0),',
        '            "overlap_score": float(row["overlap_score"] or 0.0),',
        '            "ambiguity_score": float(row["ambiguity_score"] or 0.0),',
        '            "summary": str(row["summary"] or ""),',
        '            "payload": parse_json(row["payload_json"], {}),',
        '        }',
        '',
        '    def _v47_11_plan_pair(self, plan) -> tuple[str, str, str]:',
        '        lower = str(getattr(plan, "target_a", "") or "")',
        '        upper = str(getattr(plan, "target_b", "") or "")',
        '        pair = f"{lower}>{upper}" if lower or upper else ""',
        '        return lower, upper, pair',
        '',
        '    def _v47_11_hypothesis_id_from_object(self, hyp) -> str:',
        '        for attr in ("hypothesis_id", "id", "hid", "name", "uid"):',
        '            value = getattr(hyp, attr, None)',
        '            if value:',
        '                return str(value)',
        '        text = str(hyp)',
        '        if "H" in text:',
        '            import re',
        '            match = re.search(r"H\\d+", text)',
        '            if match:',
        '                return match.group(0)',
        '        return ""',
        '',
        '    def _v47_11_latest_hypothesis_for_pair(self, lower: str, upper: str) -> tuple[str, object]:',
        '        candidates = []',
        '        for hyp in list(getattr(self, "pending_hypotheses", []) or []):',
        '            if getattr(hyp, "lower_id", None) == lower and getattr(hyp, "upper_id", None) == upper:',
        '                candidates.append(hyp)',
        '        if not candidates:',
        '            return "", None',
        '        hyp = candidates[-1]',
        '        return self._v47_11_hypothesis_id_from_object(hyp), hyp',
        '',
        '    def _v47_11_lineage_already_recorded(self, tension_id: str, influence_id: str, hypothesis_id: str) -> bool:',
        '        import sqlite3',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return False',
        '',
        '        self._v47_11_initialize_lineage_tables()',
        '        with sqlite3.connect(db_path) as conn:',
        '            row = conn.execute(',
        '                """',
        '                SELECT COUNT(*)',
        '                FROM tension_hypothesis_lineage',
        '                WHERE tension_id=? AND influence_id=? AND hypothesis_id=?',
        '                """',
        '                ,',
        '                (tension_id, influence_id, hypothesis_id),',
        '            ).fetchone()',
        '        return bool(row and int(row[0]) > 0)',
        '',
        '    def _v47_11_record_hypothesis_lineage_after_predict(self, plan, result_text: str) -> None:',
        '        import sqlite3',
        '',
        '        try:',
        '            action_name = str(getattr(plan, "action_name", "") or "")',
        '            bucket = str(getattr(plan, "curriculum_bucket", "") or "")',
        '            if action_name != "predict":',
        '                return',
        '            if bucket != "routine_compare_influenced_predict":',
        '                return',
        '',
        '            active_id = getattr(self, "active_tension_id", None)',
        '            case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None',
        '            lower, upper, pair = self._v47_11_plan_pair(plan)',
        '',
        '            if case is None:',
        '                # fallback por par, caso o foco tenha mudado por algum motivo',
        '                for candidate in list(getattr(self, "live_tension_cases", {}).values()):',
        '                    if getattr(candidate, "source_lower", None) == lower and getattr(candidate, "source_upper", None) == upper:',
        '                        case = candidate',
        '                        break',
        '',
        '            if case is None:',
        '                return',
        '',
        '            influence = self._v47_11_latest_prediction_influence(case.tension_id)',
        '            if not influence:',
        '                return',
        '',
        '            hypothesis_id, hyp = self._v47_11_latest_hypothesis_for_pair(lower, upper)',
        '            if not hypothesis_id:',
        '                hypothesis_id = "HYPOTHESIS_PENDING_UNRESOLVED"',
        '',
        '            influence_id = str(influence.get("influence_id", "") or "")',
        '            if self._v47_11_lineage_already_recorded(case.tension_id, influence_id, hypothesis_id):',
        '                return',
        '',
        '            self._v47_11_initialize_lineage_tables()',
        '            db_path = self._v47_9_compare_db_path()',
        '            if not db_path.exists():',
        '                return',
        '',
        '            step = self._current_step()',
        '            lineage_id = f"LIN:{case.tension_id}:{hypothesis_id}:{step}"',
        '            now = self._v47_9_now_iso()',
        '            result_excerpt = str(result_text or "")[:800]',
        '            comparison_id = str(influence.get("comparison_id", "") or "")',
        '            bias_label = str(influence.get("bias_label", "") or "")',
        '            confidence = float(influence.get("confidence", 0.0) or 0.0)',
        '            action_signature = str(getattr(plan, "signature", "") or "")',
        '',
        '            payload = {',
        '                "lineage_id": lineage_id,',
        '                "hypothesis_id": hypothesis_id,',
        '                "tension_id": case.tension_id,',
        '                "source_pair": case.source_pair,',
        '                "comparison_id": comparison_id,',
        '                "influence_id": influence_id,',
        '                "bias_label": bias_label,',
        '                "confidence": confidence,',
        '                "action_signature": action_signature,',
        '                "plan_explanation": str(getattr(plan, "explanation", "") or ""),',
        '                "result_excerpt": result_excerpt,',
        '                "effect": "hypothesis_lineage_bound_to_contextual_influence",',
        '            }',
        '',
        '            with sqlite3.connect(db_path) as conn:',
        '                conn.execute(',
        '                    """',
        '                    INSERT INTO tension_hypothesis_lineage (',
        '                        lineage_id, hypothesis_id, tension_id, source_pair, comparison_id,',
        '                        influence_id, bias_label, confidence, timestamp, step,',
        '                        action_signature, status, result_excerpt, payload_json',
        '                    )',
        '                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        '                    """',
        '                    ,',
        '                    (',
        '                        lineage_id,',
        '                        hypothesis_id,',
        '                        case.tension_id,',
        '                        case.source_pair,',
        '                        comparison_id,',
        '                        influence_id,',
        '                        bias_label,',
        '                        confidence,',
        '                        now,',
        '                        step,',
        '                        action_signature,',
        '                        "recorded",',
        '                        result_excerpt,',
        '                        self._v47_9_safe_json(payload),',
        '                    ),',
        '                )',
        '                conn.commit()',
        '',
        '            self.last_hypothesis_lineage_lines = [',
        '                "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",',
        '                f"- linhagem: {lineage_id}",',
        '                f"- hipótese: {hypothesis_id}",',
        '                f"- tensão: {case.tension_id} ({case.source_pair})",',
        '                f"- comparação-base: {comparison_id}",',
        '                f"- influência-base: {influence_id}",',
        '                f"- viés: {bias_label} | confiança={confidence:.3f}",',
        '                "- efeito: hipótese vinculada à comparação e à influência contextual",',
        '            ]',
        '        except Exception as exc:',
        '            self.last_hypothesis_lineage_lines = [',
        '                "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",',
        '                f"- erro ao registrar linhagem: {exc}",',
        '            ]',
        '',
        '    def hypothesis_lineage_summary(self) -> str:',
        '        import sqlite3',
        '',
        '        lines = list(getattr(self, "last_hypothesis_lineage_lines", []))',
        '        if lines:',
        '            return chr(10).join(lines)',
        '',
        '        db_path = self._v47_9_compare_db_path()',
        '        if not db_path.exists():',
        '            return chr(10).join(["LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11", "- banco não encontrado"])',
        '',
        '        self._v47_11_initialize_lineage_tables()',
        '        active_id = getattr(self, "active_tension_id", None)',
        '',
        '        with sqlite3.connect(db_path) as conn:',
        '            conn.row_factory = sqlite3.Row',
        '            if active_id:',
        '                row = conn.execute(',
        '                    """',
        '                    SELECT lineage_id, hypothesis_id, tension_id, source_pair, comparison_id,',
        '                           influence_id, bias_label, confidence, timestamp, status',
        '                    FROM tension_hypothesis_lineage',
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
        '                    SELECT lineage_id, hypothesis_id, tension_id, source_pair, comparison_id,',
        '                           influence_id, bias_label, confidence, timestamp, status',
        '                    FROM tension_hypothesis_lineage',
        '                    ORDER BY id DESC',
        '                    LIMIT 1',
        '                    """',
        '                ).fetchone()',
        '',
        '        if row is None:',
        '            return chr(10).join(',
        '                [',
        '                    "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",',
        '                    "- nenhuma linhagem contextual registrada nesta sessão/banco",',
        '                ]',
        '            )',
        '',
        '        return chr(10).join(',
        '            [',
        '                "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",',
        '                f"- linhagem: {row[\'lineage_id\']}",',
        '                f"- hipótese: {row[\'hypothesis_id\']}",',
        '                f"- tensão: {row[\'tension_id\']} ({row[\'source_pair\']})",',
        '                f"- comparação-base: {row[\'comparison_id\']}",',
        '                f"- influência-base: {row[\'influence_id\']}",',
        '                f"- viés: {row[\'bias_label\']} | confiança={float(row[\'confidence\']):.3f}",',
        '                f"- status: {row[\'status\']}",',
        '            ]',
        '        )',
        '',
        '    def execute_action(self, plan):',
        '        result = self._execute_action_v47_10_base(plan)',
        '        self._v47_11_record_hypothesis_lineage_after_predict(plan, result)',
        '        return result',
        '',
        '',
    ]
    return chr(10).join(lines)


def patch_execute_action(text: str) -> tuple[str, int]:
    if "def _v47_11_record_hypothesis_lineage_after_predict" in text:
        print_status("PULOU", "linhagem v47.11 já existe")
        return text, 0

    match = re.search(
        r'    def execute_action\(self,\s*plan[^)]*\)[^:]*:\n',
        text,
    )
    if not match:
        raise RuntimeError("Não encontrei def execute_action(self, plan...) para envolver.")

    original_signature = match.group(0)
    renamed_signature = original_signature.replace("def execute_action", "def _execute_action_v47_10_base", 1)

    start, end = match.span()
    replacement = lineage_methods_block() + renamed_signature

    patched = text[:start] + replacement + text[end:]
    print_status("OK", "execute_action envolvido por linhagem v47.11")
    return patched, 1


def patch_menu(text: str) -> tuple[str, int]:
    changes = 0

    if "10h - mostrar linhagem contextual da hipótese" not in text:
        text, n = replace_once(
            text,
            '        print("10i - mostrar influência contextual na hipótese")\n',
            '        print("10i - mostrar influência contextual na hipótese")\n'
            '        print("10h - mostrar linhagem contextual da hipótese")\n',
            "menu adiciona comando 10h",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10h já existe")

    if 'choice in {"10h", "lineage", "linhagem", "hypothesis_lineage"}' not in text:
        anchor = (
            '            elif choice in {"10i", "influence", "influencia", "influência"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.prediction_influence_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10i", "influence", "influencia", "influência"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.prediction_influence_summary())\n'
            '            elif choice in {"10h", "lineage", "linhagem", "hypothesis_lineage"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.hypothesis_lineage_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10h",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10h já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x ou 10i.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x, 10i ou 10h.")\n',
        "mensagem de comando inválido inclui 10h",
    )
    changes += n

    return text, changes


def patch_v47(text: str) -> tuple[str, int]:
    total = 0
    text, n = patch_execute_action(text)
    total += n
    text, n = patch_menu(text)
    total += n
    return text, total


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.11_hypothesis_lineage",
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
    parser = argparse.ArgumentParser(description="Patch v47.11: hipótese com linhagem contextual.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.11 — HIPÓTESE COM LINHAGEM CONTEXTUAL")
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
    print("Patch v47.11 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_11_hypothesis_lineage_test.py --dry-run")
    print("  py darwin_v47_11_hypothesis_lineage_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
