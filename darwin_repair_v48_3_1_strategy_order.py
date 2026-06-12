from __future__ import annotations

"""
DARWIN v48.3.1 — Repair da Ordem Auditável da Estratégia Após Erro

Problema corrigido:
Na v48.3, o comportamento funcional passou, mas a auditoria falhou porque a ordem
dos eventos ficou:
    error_memory_write
    strategy_select
    controlled_collision

O correto para o prontuário é:
    controlled_collision
    error_memory_write
    strategy_select

Este repair cria:
    darwin_shape_sorter_live_v48_3_1_strategy_after_error.py

com nova tabela:
    geometry_live_actions_v48_3_1
"""

import py_compile
from pathlib import Path


SOURCE = Path("darwin_shape_sorter_live_v48_3_strategy_after_error.py")
TARGET = Path("darwin_shape_sorter_live_v48_3_1_strategy_after_error.py")


def main() -> int:
    print("=" * 72)
    print("DARWIN v48.3.1 — REPAIR DA ORDEM DE ESTRATÉGIA")
    print("=" * 72)

    if not SOURCE.exists():
        print(f"[ERRO] arquivo fonte não encontrado: {SOURCE}")
        print("Coloque este repair na pasta darwin_local, junto do arquivo v48.3 original.")
        return 2

    text = SOURCE.read_text(encoding="utf-8")

    text = text.replace("DARWIN v48.3", "DARWIN v48.3.1")
    text = text.replace("v48.3 —", "v48.3.1 —")
    text = text.replace("geometry_live_actions_v48_3", "geometry_live_actions_v48_3_1")
    text = text.replace(
        'root.title("DARWIN v48.3 — estratégia após erro")',
        'root.title("DARWIN v48.3.1 — estratégia após erro")',
    )
    text = text.replace(
        'text="DARWIN v48.3 — estratégia após erro"',
        'text="DARWIN v48.3.1 — estratégia após erro"',
    )

    old = """                    st = self.agent.remember_error(ev)
                    self.mem.log("controlled_collision",p.id,h.id,ev.score,"collision",ev.reason,asdict(ev))
                    self.log(f"COLISÃO: {p.id} -> {h.id} | {ev.reason}")
                    self.log(f"ESTRATÉGIA: {ev.reason} -> {st.recommendation}")
                    self.write_logic(self.eval_text("COLISÃO / ESTRATÉGIA",p,h,ev,"classificar falha")+f"\\nEstratégia: {st.recommendation}\\n{st.explanation}\\n")
"""

    new = """                    self.mem.log("controlled_collision",p.id,h.id,ev.score,"collision",ev.reason,asdict(ev))
                    self.log(f"COLISÃO: {p.id} -> {h.id} | {ev.reason}")
                    st = self.agent.remember_error(ev)
                    self.log(f"ESTRATÉGIA: {ev.reason} -> {st.recommendation}")
                    self.write_logic(self.eval_text("COLISÃO / ESTRATÉGIA",p,h,ev,"classificar falha")+f"\\nEstratégia: {st.recommendation}\\n{st.explanation}\\n")
"""

    if old not in text:
        print("[ERRO] bloco esperado não foi encontrado. O arquivo original parece diferente.")
        print("Não escrevi nada.")
        return 2

    text = text.replace(old, new, 1)

    TARGET.write_text(text, encoding="utf-8")
    py_compile.compile(str(TARGET), doraise=True)

    print(f"[OK] criado: {TARGET}")
    print("[OK] py_compile passou")
    print()
    print("Agora rode:")
    print("  py darwin_shape_sorter_live_v48_3_1_strategy_after_error.py")
    print("  py darwin_check_v48_3_1_strategy_after_error.py --details")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
