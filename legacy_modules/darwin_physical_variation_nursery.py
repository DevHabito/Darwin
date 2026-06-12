from __future__ import annotations

"""
Darwin Physical Variation Nursery
---------------------------------

Próxima fase do berçário físico manual.

Agora o Darwin testa os mesmos objetos reais sob variações controladas:
- superfície inclinada
- topo desalinhado
- triângulo girado
- toque leve
- toque forte
- repetição em superfície plana como controle

Fluxo:
1. Darwin escolhe ou você escolhe par + condição.
2. Darwin prevê antes do teste.
3. Você monta a situação física real e informa stable/unstable.
4. Darwin registra observação contextual no mesmo darwin_home/darwin.db.

Coloque este arquivo na mesma pasta de:
- darwin_home.py
- darwin_v61_nursery_v46.py
- pasta darwin_home/

Execute com:
    py darwin_physical_variation_nursery.py
"""

import re
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


NURSERY_SOURCE = "nursery_v46"
VARIATION_MODULE = "nursery_v46_physical_variation"


@dataclass(frozen=True)
class ManualObjectSpec:
    obj_id: str
    color: str
    shape: str
    category: str = "block"
    can_roll: bool = False
    can_stack_symbolic: bool = True
    fit_slot: Optional[str] = None


@dataclass(frozen=True)
class VariationCondition:
    code: str
    label: str
    instruction: str
    hypothesis_hint: str
    priority: float = 1.0
    requires_triangle: bool = False
    destabilizing: bool = False


VARIATIONS: list[VariationCondition] = [
    VariationCondition(
        code="superficie_inclinada",
        label="superfície levemente inclinada",
        instruction=(
            "Coloque a base e o topo em uma superfície levemente inclinada. "
            "Não force a queda; só observe se a pilha se sustenta."
        ),
        hypothesis_hint="estabilidade sob inclinação",
        priority=1.55,
        destabilizing=True,
    ),
    VariationCondition(
        code="topo_desalinhado",
        label="topo propositalmente desalinhado",
        instruction=(
            "Empilhe o topo um pouco fora do centro da base. "
            "Use um desalinhamento pequeno, mas perceptível."
        ),
        hypothesis_hint="estabilidade com desalinhamento",
        priority=1.35,
        destabilizing=True,
    ),
    VariationCondition(
        code="triangulo_girado",
        label="triângulo girado / orientação alterada",
        instruction=(
            "Se houver triângulo no par, gire o triângulo para uma orientação diferente. "
            "Teste se a orientação muda a estabilidade."
        ),
        hypothesis_hint="efeito da orientação do triângulo",
        priority=1.45,
        requires_triangle=True,
        destabilizing=True,
    ),
    VariationCondition(
        code="toque_leve",
        label="toque leve após montar",
        instruction=(
            "Monte a pilha normalmente e aplique um toque leve. "
            "Observe se ela continua estável."
        ),
        hypothesis_hint="resistência a pequena perturbação",
        priority=1.10,
        destabilizing=True,
    ),
    VariationCondition(
        code="toque_forte",
        label="toque mais forte após montar",
        instruction=(
            "Monte a pilha normalmente e aplique um toque mais forte, sem arremessar objetos. "
            "Observe se ela cai ou se sustenta."
        ),
        hypothesis_hint="resistência a perturbação forte",
        priority=0.85,
        destabilizing=True,
    ),
    VariationCondition(
        code="controle_plano",
        label="controle em superfície plana",
        instruction=(
            "Repita o empilhamento em superfície plana, sem inclinar, sem girar e sem tocar. "
            "Serve como controle para comparar com as variações."
        ),
        hypothesis_hint="controle de estabilidade em condição simples",
        priority=0.35,
        destabilizing=False,
    ),
]


class PhysicalVariationEnvironment(NurseryEnvironment):
    """
    Ambiente físico com variação contextual.

    Reaproveita a interface do NurseryEnvironment, mas o resultado de empilhamento
    vem da validação do tutor. A condição ativa entra nas memórias aprendidas.
    """

    def __init__(self, specs: list[ManualObjectSpec]) -> None:
        self.objects = {}
        self.slots = {
            "slot_square": "square",
            "slot_triangle": "triangle",
        }
        self.current_condition: VariationCondition = VARIATIONS[0]
        self.variation_trials: list[tuple[str, str, str, str]] = []
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

    def set_condition(self, condition: VariationCondition) -> None:
        self.current_condition = condition

    def try_stack(self, lower_id: str, upper_id: str) -> NurseryActionResult:
        condition = self.current_condition
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
        print("VALIDAÇÃO FÍSICA COM VARIAÇÃO CONTROLADA")
        print("-" * 72)
        print(f"Darwin quer testar: {upper_id} SOBRE {lower_id}")
        print(f"Condição: {condition.label} [{condition.code}]")
        print(f"Instrução: {condition.instruction}")
        print("\nDigite o resultado observado:")
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
                    f"Teste com variação {condition.code} para {upper_id} sobre {lower_id} foi pulado pelo tutor.",
                    0.10,
                    0.06,
                    0.20,
                    0.08,
                    [
                        f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:skipped=true",
                    ],
                )
            print("Entrada não reconhecida. Use stable, unstable ou skip.")

        self.variation_trials.append((lower_id, upper_id, condition.code, observed))
        lower = self.objects[lower_id]
        upper = self.objects[upper_id]

        common_learned = [
            f"variation_condition:{condition.code}:label:{condition.label}=true",
            f"variation_condition:{condition.code}:hint:{condition.hypothesis_hint}=true",
            f"pair_context:{lower_id}>{upper_id}:variation:{condition.code}:stack:{observed}=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:observed:{observed}=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:tested=true",
        ]

        if observed == "stable":
            upper.position = f"sobre_{lower_id}_em_{condition.code}"
            learned = [
                f"obj:{lower_id}:affordance:suporta_empilhar=true",
                f"obj:{upper_id}:affordance:empilhavel=true",
                f"variation_effect:{condition.code}:{lower_id}>{upper_id}:preserved_stability=true",
                f"condition_rule:{condition.code}:{lower_id}:as_base:stable_with:{upper_id}=true",
            ] + common_learned
            return NurseryActionResult(
                True,
                f"[variação manual] {upper_id} sobre {lower_id} ficou estável em {condition.label}.",
                1.00,
                0.40 if condition.destabilizing else 0.28,
                0.08,
                1.00,
                learned,
            )

        learned = [
            f"pair:{lower_id}>{upper_id}:stack:unstable=true",
            f"variation_effect:{condition.code}:{lower_id}>{upper_id}:destabilized=true",
            f"condition_rule:{condition.code}:{lower_id}:as_base:unstable_with:{upper_id}=true",
        ] + common_learned
        return NurseryActionResult(
            False,
            f"[variação manual] A pilha {upper_id} sobre {lower_id} ficou instável em {condition.label}.",
            0.36,
            0.50,
            0.68 if condition.destabilizing else 0.58,
            1.00,
            learned,
        )

    def describe_world(self) -> str:
        parts = []
        for obj in self.objects.values():
            parts.append(
                f"{obj.obj_id}: cor={obj.color}, forma={obj.shape}, categoria={obj.category}, posicao={obj.position}"
            )
        slot_text = ", ".join(f"{slot}->{shape}" for slot, shape in self.slots.items())
        return "Objetos físicos de variação: " + " | ".join(parts) + f"\nSlots: {slot_text}"


class DarwinPhysicalVariationSession:
    def __init__(self) -> None:
        self.home = DarwinHome("darwin_home")
        self.home.bootstrap()
        self.agent = DarwinNurseryAgent(self.home)
        self.agent.env = PhysicalVariationEnvironment(self._default_specs())
        self._seed_physical_ontology()

    def _default_specs(self) -> list[ManualObjectSpec]:
        return [
            ManualObjectSpec("square_A", "cor_A", "square", fit_slot="square"),
            ManualObjectSpec("square_B", "cor_B", "square", fit_slot="square"),
            ManualObjectSpec("triangle_A", "cor_C", "triangle", fit_slot="triangle"),
        ]

    def _seed_physical_ontology(self) -> None:
        for obj in self.agent.env.objects.values():
            learned = [
                f"obj:{obj.obj_id}:color:{obj.color}=true",
                f"obj:{obj.obj_id}:shape:{obj.shape}=true",
                f"obj:{obj.obj_id}:category:{obj.category}=true",
                f"obj:{obj.obj_id}:affordance:nao_rola_facil=true",
            ]
            for item in learned:
                key, value = item.split("=", 1)
                self.agent.memory.learn(key, value, confidence_boost=0.03)
                node = self.agent.memory.nodes[key]
                self.home.upsert_semantic_memory(
                    key=key,
                    content=value,
                    confidence=node.confidence,
                    source=NURSERY_SOURCE,
                )

        for condition in VARIATIONS:
            self.home.upsert_semantic_memory(
                key=f"variation_condition:{condition.code}:label:{condition.label}",
                content="true",
                confidence=0.20,
                source=NURSERY_SOURCE,
            )

        self.home.add_episode(
            module=VARIATION_MODULE,
            context="seed variation nursery ontology",
            action_taken="seed_variation_ontology",
            outcome="success",
            lesson="Darwin recebeu condições de variação controlada para testar estabilidade contextual.",
            sigma_before=self.agent.sigma_now(),
            sigma_after=self.agent.sigma_now(),
        )

    def intro(self) -> None:
        print("=" * 72)
        print("DARWIN — Physical Variation Nursery")
        print("=" * 72)
        print("\nObjetivo desta fase:")
        print("  • manter os mesmos 2 quadrados e 1 triângulo")
        print("  • variar o contexto físico: inclinação, desalinhamento, orientação e toque")
        print("  • testar se estabilidade depende de objeto + relação + condição")
        print("  • registrar observações no mesmo darwin.db")
        print("\nMundo físico de variação:")
        print(self.agent.env.describe_world())
        print("\nComandos disponíveis:")
        print("  1 - passo autônomo de variação: Darwin escolhe par + condição")
        print("  2 - experimento guiado: você escolhe condição e par")
        print("  3 - mostrar cobertura de variações")
        print("  4 - mostrar mundo físico")
        print("  5 - mostrar estado")
        print("  6 - mostrar conceitos locais")
        print("  7 - mostrar currículo e painéis")
        print("  8 - exportar snapshot")
        print("  9 - sair")

    def menu(self) -> str:
        return input("\nEscolha: ").strip().lower()

    def pairs(self) -> list[tuple[str, str]]:
        ids = list(self.agent.env.objects.keys())
        return [(lower, upper) for lower in ids for upper in ids if lower != upper]

    def _print_pairs(self) -> list[tuple[str, str]]:
        pairs = self.pairs()
        print("\nPares possíveis: formato BASE <- TOPO")
        for idx, (lower, upper) in enumerate(pairs, start=1):
            print(f"  {idx}. {lower} <- {upper}   ({upper} sobre {lower})")
        return pairs

    def _print_conditions(self, lower: Optional[str] = None, upper: Optional[str] = None) -> list[VariationCondition]:
        conditions = []
        print("\nCondições de variação:")
        for condition in VARIATIONS:
            if condition.requires_triangle and lower is not None and upper is not None:
                if "triangle" not in lower and "triangle" not in upper:
                    # Ainda mostramos, mas avisamos que é menos informativo.
                    suffix = "  [menos relevante: não há triângulo no par]"
                else:
                    suffix = ""
            else:
                suffix = ""
            conditions.append(condition)
            print(f"  {len(conditions)}. {condition.label} [{condition.code}]{suffix}")
        return conditions

    def _variation_count(self, lower: str, upper: str, condition_code: str) -> int:
        prefix = f"physical_variation:{lower}>{upper}:condition:{condition_code}:observed:%"
        row = self.home.conn.execute(
            "SELECT COUNT(*) AS n FROM semantic_memory WHERE key LIKE ?",
            (prefix,),
        ).fetchone()
        return int(row["n"] if row is not None else 0)

    def _pair_has_triangle(self, lower: str, upper: str) -> bool:
        return "triangle" in lower or "triangle" in upper

    def choose_next_variation(self) -> tuple[str, str, VariationCondition, str]:
        best: Optional[tuple[float, str, str, VariationCondition, str]] = None
        for lower, upper in self.pairs():
            for condition in VARIATIONS:
                if condition.requires_triangle and not self._pair_has_triangle(lower, upper):
                    continue
                count = self._variation_count(lower, upper, condition.code)
                score = condition.priority
                reasons = [condition.hypothesis_hint]
                if count == 0:
                    score += 4.0
                    reasons.append("sem observação nesta condição")
                else:
                    score -= 0.75 * count
                    reasons.append(f"já observado {count} vez(es)")
                if lower == "triangle_A":
                    score += 1.25
                    reasons.append("base triangular é ponto crítico")
                if upper == "triangle_A":
                    score += 0.65
                    reasons.append("triângulo como topo precisa contraste")
                if condition.destabilizing:
                    score += 0.45
                    reasons.append("variação pode revelar limite de estabilidade")
                if condition.code == "controle_plano" and count == 0:
                    score += 0.30
                    reasons.append("controle útil para comparação")

                candidate = (score, lower, upper, condition, " | ".join(reasons))
                if best is None or candidate[0] > best[0]:
                    best = candidate

        if best is None:
            # fallback: raro, mas evita falha caso todas as condições filtradas sumam
            lower, upper = self.pairs()[0]
            return lower, upper, VARIATIONS[0], "fallback: nenhuma variação elegível"
        _score, lower, upper, condition, reason = best
        return lower, upper, condition, reason

    def _make_plans(self, lower: str, upper: str, condition: VariationCondition, reason: str) -> tuple[ActionPlan, ActionPlan]:
        self.agent.env.set_condition(condition)
        explanation = (
            f"variação controlada: {condition.label}; {reason}; "
            "formular hipótese antes do teste contextual"
        )
        predict_plan = ActionPlan(
            action_name="predict",
            target_a=lower,
            target_b=upper,
            explanation=explanation,
            novelty_residual=1.0,
            curriculum_bucket="predict_variation",
            lesson_phase="physical_variation_lab",
            signature=f"variation_predict:{condition.code}:{lower}:{upper}",
        )
        validate_plan = ActionPlan(
            action_name="validate",
            target_a=lower,
            target_b=upper,
            explanation=(
                f"validar no mundo real sob variação {condition.label}; "
                "registrar estabilidade contextual observada pelo tutor"
            ),
            novelty_residual=1.0,
            curriculum_bucket="validate_variation",
            lesson_phase="physical_variation_lab",
            signature=f"variation_validate:{condition.code}:{lower}:{upper}",
        )
        return predict_plan, validate_plan

    def run_variation_experiment(self, lower: str, upper: str, condition: VariationCondition, reason: str) -> None:
        predict_plan, validate_plan = self._make_plans(lower, upper, condition, reason)

        print("\n" + "=" * 72)
        print("PREVISÃO DO DARWIN COM VARIAÇÃO")
        print("=" * 72)
        print(f"Par       : {upper} SOBRE {lower}")
        print(f"Condição  : {condition.label} [{condition.code}]")
        print(f"Motivo    : {reason}")
        print(self.agent.execute_action(predict_plan))

        print("\n" + "=" * 72)
        print("VALIDAÇÃO FÍSICA COM VARIAÇÃO")
        print("=" * 72)
        print(self.agent.execute_action(validate_plan))

    def autonomous_variation_step(self) -> None:
        lower, upper, condition, reason = self.choose_next_variation()
        self.run_variation_experiment(lower, upper, condition, reason)

    def guided_experiment(self) -> None:
        pairs = self._print_pairs()
        raw = input("\nEscolha o número do par: ").strip()
        try:
            pair_idx = int(raw)
        except ValueError:
            print("Entrada inválida.")
            return
        if pair_idx < 1 or pair_idx > len(pairs):
            print("Número fora da lista.")
            return

        lower, upper = pairs[pair_idx - 1]
        conditions = self._print_conditions(lower, upper)
        raw = input("\nEscolha o número da condição: ").strip()
        try:
            cond_idx = int(raw)
        except ValueError:
            print("Entrada inválida.")
            return
        if cond_idx < 1 or cond_idx > len(conditions):
            print("Número fora da lista.")
            return

        condition = conditions[cond_idx - 1]
        if condition.requires_triangle and not self._pair_has_triangle(lower, upper):
            print("Aviso: esta condição é menos informativa porque o par não contém triângulo.")
        reason = "experimento guiado pelo tutor"
        self.run_variation_experiment(lower, upper, condition, reason)

    def show_variation_coverage(self) -> str:
        lines = ["COBERTURA DE VARIAÇÕES CONTROLADAS"]
        lines.append("Formato: BASE <- TOPO | condição -> observações")
        total = 0
        for lower, upper in self.pairs():
            items = []
            for condition in VARIATIONS:
                stable_key = f"physical_variation:{lower}>{upper}:condition:{condition.code}:observed:stable"
                unstable_key = f"physical_variation:{lower}>{upper}:condition:{condition.code}:observed:unstable"
                stable = self.home.get_semantic_memory(stable_key)
                unstable = self.home.get_semantic_memory(unstable_key)
                if stable:
                    items.append(f"{condition.code}:stable")
                    total += 1
                elif unstable:
                    items.append(f"{condition.code}:unstable")
                    total += 1
            if items:
                lines.append(f"- {lower} <- {upper}: " + ", ".join(items))
            else:
                lines.append(f"- {lower} <- {upper}: sem variações observadas ainda")
        lines.append(f"\nTotal de observações contextuais detectadas: {total}")

        # Pequena síntese por condição
        lines.append("\nSÍNTESE POR CONDIÇÃO")
        for condition in VARIATIONS:
            stable_count = 0
            unstable_count = 0
            for lower, upper in self.pairs():
                if self.home.get_semantic_memory(f"physical_variation:{lower}>{upper}:condition:{condition.code}:observed:stable"):
                    stable_count += 1
                if self.home.get_semantic_memory(f"physical_variation:{lower}>{upper}:condition:{condition.code}:observed:unstable"):
                    unstable_count += 1
            lines.append(f"- {condition.code}: stable={stable_count}, unstable={unstable_count}")
        return "\n".join(lines)

    def run(self) -> None:
        self.intro()
        while True:
            choice = self.menu()
            if choice == "1":
                self.autonomous_variation_step()
            elif choice == "2":
                self.guided_experiment()
            elif choice == "3":
                print("\n" + "=" * 72)
                print(self.show_variation_coverage())
            elif choice == "4":
                print("\n" + "=" * 72)
                print("MUNDO FÍSICO DE VARIAÇÃO")
                print("=" * 72)
                print(self.agent.env.describe_world())
            elif choice == "5":
                print("\n" + "=" * 72)
                print(self.agent.show_state())
            elif choice == "6":
                print("\n" + "=" * 72)
                print(self.agent.show_concepts())
            elif choice == "7":
                print("\n" + "=" * 72)
                print(self.agent.curriculum_and_panels())
            elif choice == "8":
                snapshot = self.home.export_snapshot()
                print(f"\nSnapshot exportado em: {snapshot}")
            elif choice in {"9", "sair", "exit", "quit"}:
                print("\nEncerrando Physical Variation Nursery.")
                self.home.close()
                break
            else:
                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8 ou 9.")


if __name__ == "__main__":
    DarwinPhysicalVariationSession().run()
