from __future__ import annotations

"""
DARWIN v47.6 — Compromisso Executivo Real

Objetivo:
- Se o Darwin acorda com uma tensão aberta reidratada, o próximo passo autônomo
  deve respeitar essa pendência antes de voltar à exploração comum.
- A tensão aberta deixa de ser apenas memória restaurada e vira dívida operacional.

Uso:
    py darwin_patch_v47_6_executive_commitment.py --dry-run
    py darwin_patch_v47_6_executive_commitment.py

Teste:
    py darwin_v47_6_commitment_test.py
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
MANIFEST_FILE = PROJECT_ROOT / "v47_6_executive_commitment_manifest.json"

COMMITMENT_METHODS = '\n    # --------------------------\n    # compromisso executivo v47.6\n    # --------------------------\n\n    def _v47_6_make_action_plan(\n        self,\n        *,\n        action_name: str,\n        lower: str,\n        upper: Optional[str],\n        explanation: str,\n        novelty_residual: float,\n        bucket: str,\n        phase: str,\n        signature: str,\n    ) -> "ActionPlan":\n        # Cria ActionPlan de forma compatível com a dataclass atual.\n        try:\n            from dataclasses import fields as dataclass_fields\n\n            values = {\n                "action_name": action_name,\n                "target_a": lower,\n                "target_b": upper,\n                "explanation": explanation,\n                "novelty_residual": novelty_residual,\n                "curriculum_bucket": bucket,\n                "lesson_phase": phase,\n                "signature": signature,\n            }\n            kwargs = {}\n            for field in dataclass_fields(ActionPlan):\n                if field.name in values:\n                    kwargs[field.name] = values[field.name]\n                elif field.default is not field.default_factory:\n                    kwargs[field.name] = field.default\n                else:\n                    kwargs[field.name] = None\n            return ActionPlan(**kwargs)\n        except Exception:\n            return ActionPlan(action_name, lower, upper, explanation, novelty_residual, bucket, phase, signature)\n\n    def _v47_6_pending_hypothesis_for_pair(self, lower: str, upper: str) -> Optional["PendingHypothesis"]:\n        for hyp in list(getattr(self, "pending_hypotheses", [])):\n            if getattr(hyp, "lower_id", None) == lower and getattr(hyp, "upper_id", None) == upper:\n                return hyp\n        return None\n\n    def _v47_6_case_is_actionable(self, case: "LiveTensionCase") -> bool:\n        if case is None:\n            return False\n        if case.status in {TensionStatus.CLOSED, TensionStatus.ARCHIVED, TensionStatus.STALE}:\n            return False\n        if float(getattr(case, "closure_deficit", 0.0) or 0.0) <= 0.05:\n            return False\n        return True\n\n    def _v47_6_mark_commitment_probe_if_needed(self, case: "LiveTensionCase") -> None:\n        already_probe = (\n            case.status == TensionStatus.PROBING\n            and case.last_probe_pair == case.source_pair\n        )\n        if already_probe:\n            return\n\n        try:\n            self.mark_probe_selected(\n                lower=case.source_lower,\n                upper=case.source_upper,\n                labels=list(case.source_labels),\n                score=max(0.72, float(getattr(case, "live_pressure", 0.0) or 0.0)),\n                judgment=(\n                    "compromisso executivo v47.6: a tensão reidratada deve "\n                    "ser tratada como dívida operacional antes da exploração comum"\n                ),\n            )\n        except Exception as exc:\n            self._v47_note_persistence_error(exc)\n\n    def _v47_6_commitment_plan_from_active_tension(self) -> Optional["ActionPlan"]:\n        active_id = getattr(self, "active_tension_id", None)\n        if not active_id:\n            self.last_executive_commitment_lines = [\n                "COMPROMISSO EXECUTIVO v47.6",\n                "- nenhum foco executivo ativo",\n            ]\n            return None\n\n        case = getattr(self, "live_tension_cases", {}).get(active_id)\n        if not self._v47_6_case_is_actionable(case):\n            self.last_executive_commitment_lines = [\n                "COMPROMISSO EXECUTIVO v47.6",\n                f"- foco {active_id} não acionável ou já fechado",\n            ]\n            return None\n\n        lower = case.source_lower\n        upper = case.source_upper\n        pair = case.source_pair\n\n        pending = self._v47_6_pending_hypothesis_for_pair(lower, upper)\n\n        self._v47_6_mark_commitment_probe_if_needed(case)\n\n        if pending is not None:\n            explanation = (\n                f"compromisso executivo v47.6: validar hipótese pendente ligada à "\n                f"tensão ativa {case.tension_id} ({pair}); a pendência reidratada "\n                "tem prioridade sobre exploração comum"\n            )\n            plan = self._v47_6_make_action_plan(\n                action_name="validate",\n                lower=lower,\n                upper=upper,\n                explanation=explanation,\n                novelty_residual=0.92,\n                bucket="validate_commitment",\n                phase="executive_commitment_lab",\n                signature=f"commitment_validate:{case.tension_id}:{pair}",\n            )\n            action_line = f"- próximo ato comprometido: validate({pair})"\n        else:\n            explanation = (\n                f"compromisso executivo v47.6: formular hipótese diretamente sobre "\n                f"a tensão ativa {case.tension_id} ({pair}) antes de explorar outro caso"\n            )\n            plan = self._v47_6_make_action_plan(\n                action_name="predict",\n                lower=lower,\n                upper=upper,\n                explanation=explanation,\n                novelty_residual=0.88,\n                bucket="predict_commitment",\n                phase="executive_commitment_lab",\n                signature=f"commitment_predict:{case.tension_id}:{pair}",\n            )\n            action_line = f"- próximo ato comprometido: predict({pair})"\n\n        self.last_executive_commitment_lines = [\n            "COMPROMISSO EXECUTIVO v47.6",\n            f"- tensão ativa: {case.tension_id} ({pair})",\n            f"- status: {case.status.value} | pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f}",\n            action_line,\n        ]\n\n        try:\n            self._v47_persist_case(\n                case,\n                event_type="executive_commitment_selected",\n                note=action_line.replace("- ", "", 1),\n            )\n        except Exception:\n            pass\n\n        return plan\n\n    def executive_commitment_summary(self) -> str:\n        lines = list(getattr(self, "last_executive_commitment_lines", []))\n        if not lines:\n            lines = [\n                "COMPROMISSO EXECUTIVO v47.6",\n                "- ainda não houve decisão comprometida nesta sessão",\n            ]\n        return "\\n".join(lines)\n\n    def choose_autonomous_action(self) -> "ActionPlan":\n        commitment_plan = self._v47_6_commitment_plan_from_active_tension()\n        if commitment_plan is not None:\n            return commitment_plan\n\n        return self._choose_autonomous_action_v47_base()\n\n'


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
    backup_path = BACKUP_DIR / f"{path.stem}_pre_v47_6_{now_stamp()}{path.suffix}"

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

    if "def _v47_6_commitment_plan_from_active_tension" not in text:
        text, n = replace_once(
            text,
            "    def choose_autonomous_action(self) -> ActionPlan:\n",
            COMMITMENT_METHODS + "    def _choose_autonomous_action_v47_base(self) -> ActionPlan:\n",
            "wrapper de choose_autonomous_action v47.6",
        )
        changes += n
    else:
        print_status("PULOU", "compromisso executivo v47.6 já existe")

    if "10c - mostrar compromisso executivo atual" not in text:
        text, n = replace_once(
            text,
            '        print("10r - mostrar relatório de reidratação executiva")\n',
            '        print("10r - mostrar relatório de reidratação executiva")\n'
            '        print("10c - mostrar compromisso executivo atual")\n',
            "menu adiciona comando 10c",
        )
        changes += n
    else:
        print_status("PULOU", "menu 10c já existe")

    if 'choice in {"10c", "commitment", "compromisso"}' not in text:
        anchor = (
            '            elif choice in {"10r", "rehydrate", "reidratar", "reidratacao", "reidratação"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.v47_rehydration_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        replacement = (
            '            elif choice in {"10r", "rehydrate", "reidratar", "reidratacao", "reidratação"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.v47_rehydration_summary())\n'
            '            elif choice in {"10c", "commitment", "compromisso"}:\n'
            '                print("\\n" + "=" * 72)\n'
            '                print(self.agent.executive_commitment_summary())\n'
            '            elif choice in {"9", "sair", "exit", "quit"}:\n'
        )
        text, n = replace_once(
            text,
            anchor,
            replacement,
            "run adiciona branch 10c",
        )
        changes += n
    else:
        print_status("PULOU", "branch 10c já existe")

    text, n = replace_once(
        text,
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a ou 10r.")\n',
        '                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r ou 10c.")\n',
        "mensagem de comando inválido inclui 10c",
    )
    changes += n

    return text, changes


def write_manifest(changes: int, backup: str, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria manifest: {MANIFEST_FILE}")
        return

    manifest = {
        "created_at": now_iso(),
        "patch": "v47.6_executive_commitment",
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
    parser = argparse.ArgumentParser(description="Patch v47.6: compromisso executivo real.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.6 — COMPROMISSO EXECUTIVO REAL")
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
    print("Patch v47.6 concluído.")
    print("Teste recomendado:")
    print("  py darwin_v47_6_commitment_test.py")
    print("  py darwin_v61_nursery_v47.py")
    print("  dentro do menu: 10c, 10, 10a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
