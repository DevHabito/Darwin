from __future__ import annotations

"""
Darwin Physical Manual Nursery
------------------------------

Modo pedagógico em que você vira os olhos e as mãos do Darwin.

Fluxo principal:
1. Darwin observa / prevê / escolhe uma ação.
2. Quando ele precisar validar empilhamento físico, você testa na mesa.
3. Você informa o resultado: stable ou unstable.
4. Darwin registra no mesmo banco darwin_home/darwin.db.

Coloque este arquivo na mesma pasta de:
- darwin_home.py
- darwin_v61_nursery_v46.py
- pasta darwin_home/

Execute com:
    py darwin_physical_manual_nursery.py
"""

import sys
from dataclasses import dataclass
from typing import Optional

from darwin_home import DarwinHome

try:
    from darwin_v61_nursery_v46 import (
        ActionPlan,
        DarwinNurseryAgent,
        NurseryActionResult,
        NurseryEnvironment,
        NurseryObject,
    )
except Exception as exc:
    print("ERRO: não consegui importar darwin_v61_nursery_v46.py")
    print("Verifique se este arquivo está na mesma pasta e se o nome está correto.")
    print(f"Detalhe técnico: {exc!r}")
    raise


@dataclass
class ManualObjectSpec:
    obj_id: str
    color: str
    shape: str
    category: str = "block"
    can_roll: bool = False
    can_stack_symbolic: bool = True
    fit_slot: Optional[str] = None


class PhysicalManualEnvironment(NurseryEnvironment):
    """
    Ambiente físico-manual.

    Ele reaproveita a interface do NurseryEnvironment, mas substitui
    o resultado de empilhamento por uma validação feita por você.
    """

    def __init__(self, specs: list[ManualObjectSpec]) -> None:
        self.objects = {}
        self.slots = {
            "slot_square": "square",
            "slot_triangle": "triangle",
        }
        self.manual_trials: list[tuple[str, str, str]] = []
        self._build_from_specs(specs)

    def _build_from_specs(self, specs: list[ManualObjectSpec]) -> None:
        self.objects = {
            spec.obj_id: NurseryObject(
                obj_id=spec.obj_id,
                color=spec.color,
                shape=spec.shape,
                category=spec.category,
                can_roll=spec.can_roll,
                can_stack=spec.can_stack_symbolic,
                fit_slot=spec.fit_slot,
            )
            for spec in specs
        }

    def try_stack(self, lower_id: str, upper_id: str) -> NurseryActionResult:
        if lower_id == upper_id:
            return NurseryActionResult(
                False,
                "Não é possível empilhar um objeto sobre ele mesmo.",
                0.05,
                0.08,
                0.38,
                0.10,
                [],
            )

        print("\n" + "-" * 72)
        print("VALIDAÇÃO FÍSICA MANUAL")
        print("-" * 72)
        print(f"Darwin quer testar: {upper_id} SOBRE {lower_id}")
        print("Agora teste fisicamente com seus objetos na mesa.")
        print("Digite o resultado observado:")
        print("  stable   = ficou estável")
        print("  unstable = ficou instável / caiu / não sustentou")
        print("  skip     = pular este teste agora")

        while True:
            observed = input("Resultado físico [stable/unstable/skip]: ").strip().lower()
            if observed in {"stable", "s", "estavel", "estável"}:
                observed = "stable"
                break
            if observed in {"unstable", "u", "instavel", "instável", "caiu"}:
                observed = "unstable"
                break
            if observed in {"skip", "pular", "cancelar"}:
                return NurseryActionResult(
                    False,
                    f"Teste físico {upper_id} sobre {lower_id} foi pulado pelo tutor.",
                    0.10,
                    0.06,
                    0.20,
                    0.08,
                    [],
                )
            print("Entrada não reconhecida. Use stable, unstable ou skip.")

        self.manual_trials.append((lower_id, upper_id, observed))
        lower = self.objects[lower_id]
        upper = self.objects[upper_id]

        if observed == "stable":
            upper.position = f"sobre_{lower_id}"
            return NurseryActionResult(
                True,
                f"[manual] {upper_id} ficou estável sobre {lower_id} no teste físico.",
                1.05,
                0.36,
                0.06,
                0.92,
                [
                    f"obj:{lower_id}:affordance:suporta_empilhar=true",
                    f"obj:{upper_id}:affordance:empilhavel=true",
                    f"pair:{lower_id}>{upper_id}:stack:stable=true",
                    f"physical_manual:{lower_id}>{upper_id}:observed:stable=true",
                ],
            )

        return NurseryActionResult(
            False,
            f"[manual] A pilha {upper_id} sobre {lower_id} ficou instável no teste físico.",
            0.28,
            0.42,
            0.58,
            0.94,
            [
                f"pair:{lower_id}>{upper_id}:stack:unstable=true",
                f"physical_manual:{lower_id}>{upper_id}:observed:unstable=true",
            ],
        )

    def describe_world(self) -> str:
        parts = []
        for obj in self.objects.values():
            parts.append(
                f"{obj.obj_id}: cor={obj.color}, forma={obj.shape}, categoria={obj.category}, posicao={obj.position}"
            )
        slot_text = ", ".join(f"{slot}->{shape}" for slot, shape in self.slots.items())
        return "Objetos físicos manuais: " + " | ".join(parts) + f"\nSlots: {slot_text}"


class DarwinPhysicalManualSession:
    def __init__(self) -> None:
        self.home = DarwinHome("darwin_home")
        self.home.bootstrap()
        self.agent = DarwinNurseryAgent(self.home)
        self.agent.env = PhysicalManualEnvironment(self._default_specs())
        self._seed_physical_ontology()

    def _default_specs(self) -> list[ManualObjectSpec]:
        # Você pode editar as cores aqui conforme seus blocos reais.
        return [
            ManualObjectSpec("square_A", "cor_A", "square", fit_slot="square"),
            ManualObjectSpec("square_B", "cor_B", "square", fit_slot="square"),
            ManualObjectSpec("triangle_A", "cor_C", "triangle", fit_slot="triangle"),
        ]

    def _seed_physical_ontology(self) -> None:
        """
        Registra apenas ontologia básica.
        Não registra suporte/empilhável como verdade antecipada.
        Isso deixa Darwin descobrir estabilidade pelo teste físico.
        """
        for obj in self.agent.env.objects.values():
            learned = [
                f"obj:{obj.obj_id}:color:{obj.color}=true",
                f"obj:{obj.obj_id}:shape:{obj.shape}=true",
                f"obj:{obj.obj_id}:category:{obj.category}=true",
                f"obj:{obj.obj_id}:affordance:nao_rola_facil=true",
            ]
            for item in learned:
                key, value = item.split("=", 1)
                # boost baixo: não queremos saturar certeza cedo demais.
                self.agent.memory.learn(key, value, confidence_boost=0.05)
                node = self.agent.memory.nodes[key]
                self.home.upsert_semantic_memory(
                    key=key,
                    content=value,
                    confidence=node.confidence,
                    source="nursery_v46",
                )

        self.home.add_episode(
            module="nursery_v46_physical_manual",
            context="seed ontology for manual physical nursery",
            action_taken="seed_physical_ontology",
            outcome="success",
            lesson="Darwin recebeu ontologia básica de 2 quadrados e 1 triângulo, sem verdade antecipada de estabilidade.",
            sigma_before=self.agent.sigma_now(),
            sigma_after=self.agent.sigma_now(),
        )

    def intro(self) -> None:
        print("=" * 72)
        print("DARWIN — Physical Manual Nursery")
        print("=" * 72)
        print("\nObjetivo desta fase:")
        print("  • usar objetos reais: 2 quadrados e 1 triângulo")
        print("  • deixar Darwin prever antes do teste")
        print("  • você valida fisicamente stable/unstable")
        print("  • registrar o resultado no mesmo darwin.db")
        print("\nMundo físico manual:")
        print(self.agent.env.describe_world())
        print("\nComandos disponíveis:")
        print("  1 - passo autônomo do Darwin")
        print("  2 - experimento guiado: escolher base/topo e validar")
        print("  3 - mostrar mundo físico")
        print("  4 - mostrar estado")
        print("  5 - mostrar conceitos locais")
        print("  6 - mostrar currículo e painéis")
        print("  7 - exportar snapshot")
        print("  8 - listar pares possíveis")
        print("  9 - sair")

    def menu(self) -> str:
        return input("\nEscolha: ").strip().lower()

    def _print_pairs(self) -> list[tuple[str, str]]:
        ids = self.agent.env.object_ids()
        pairs = [(lower, upper) for lower in ids for upper in ids if lower != upper]
        print("\nPares possíveis: formato BASE <- TOPO")
        for idx, (lower, upper) in enumerate(pairs, start=1):
            print(f"  {idx}. {lower} <- {upper}   ({upper} sobre {lower})")
        return pairs

    def guided_experiment(self) -> None:
        pairs = self._print_pairs()
        raw = input("\nEscolha o número do par: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Entrada inválida.")
            return
        if idx < 1 or idx > len(pairs):
            print("Número fora da lista.")
            return

        lower, upper = pairs[idx - 1]
        predict_plan = ActionPlan(
            action_name="predict",
            target_a=lower,
            target_b=upper,
            explanation="experimento físico guiado: formular hipótese antes do teste real",
            novelty_residual=1.0,
            curriculum_bucket="predict",
            lesson_phase="physical_manual_lab",
            signature=f"manual_predict:{lower}:{upper}",
        )
        validate_plan = ActionPlan(
            action_name="validate",
            target_a="self",
            target_b=None,
            explanation="experimento físico guiado: validar no mundo real pela observação do tutor",
            novelty_residual=1.0,
            curriculum_bucket="validate",
            lesson_phase="physical_manual_lab",
            signature=f"manual_validate:{lower}:{upper}",
        )

        print("\n" + "=" * 72)
        print("PREVISÃO DO DARWIN")
        print("=" * 72)
        print(self.agent.execute_action(predict_plan))

        print("\n" + "=" * 72)
        print("VALIDAÇÃO FÍSICA")
        print("=" * 72)
        print(self.agent.execute_action(validate_plan))

    def run(self) -> None:
        self.intro()
        while True:
            choice = self.menu()
            if choice == "1":
                plan = self.agent.choose_autonomous_action()
                print("\n" + "=" * 72)
                print("PASSO AUTÔNOMO")
                print("=" * 72)
                print(self.agent.execute_action(plan))
            elif choice == "2":
                self.guided_experiment()
            elif choice == "3":
                print("\n" + "=" * 72)
                print("MUNDO FÍSICO")
                print("=" * 72)
                print(self.agent.env.describe_world())
            elif choice == "4":
                print("\n" + "=" * 72)
                print(self.agent.show_state())
            elif choice == "5":
                print("\n" + "=" * 72)
                print(self.agent.show_concepts())
            elif choice == "6":
                print("\n" + "=" * 72)
                print(self.agent.curriculum_and_panels())
            elif choice == "7":
                snapshot = self.home.export_snapshot()
                print(f"\nSnapshot exportado em: {snapshot}")
            elif choice == "8":
                self._print_pairs()
            elif choice in {"9", "sair", "exit", "quit"}:
                print("\nEncerrando Physical Manual Nursery.")
                self.home.close()
                break
            else:
                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8 ou 9.")


if __name__ == "__main__":
    DarwinPhysicalManualSession().run()
