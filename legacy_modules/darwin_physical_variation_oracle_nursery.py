from __future__ import annotations

"""
Darwin Physical Variation Oracle Nursery
----------------------------------------

Versão para continuar o desenvolvimento quando o tutor humano está cansado.

IMPORTANTE:
- Este script NÃO substitui o mundo físico real.
- Ele cria um "tutor sintético/oráculo pedagógico" com regras simples e explícitas.
- Tudo que ele ensina é marcado como synthetic_oracle, para não confundir com observação real.
- Use para avançar arquitetura, grafo, validações e fluxo pedagógico.
- Depois, os casos mais importantes devem ser revalidados fisicamente por você.

Coloque este arquivo na mesma pasta de:
- darwin_home.py
- darwin_v61_nursery_v46.py
- darwin_physical_variation_nursery.py
- pasta darwin_home/

Executar modo interativo:
    py darwin_physical_variation_oracle_nursery.py

Executar lote automático direto:
    py darwin_physical_variation_oracle_nursery.py --batch 12

Executar até cobrir todas as variações ainda não observadas:
    py darwin_physical_variation_oracle_nursery.py --full
"""

import argparse
from dataclasses import dataclass
from typing import Optional

try:
    from darwin_v61_nursery_v46 import ActionPlan, NurseryActionResult
except Exception as exc:
    print("ERRO: não consegui importar darwin_v61_nursery_v46.py")
    print("Verifique se este arquivo está na mesma pasta e se o nome está correto.")
    print(f"Detalhe técnico: {exc!r}")
    raise

try:
    from darwin_physical_variation_nursery import (
        VARIATIONS,
        DarwinPhysicalVariationSession,
        ManualObjectSpec,
        PhysicalVariationEnvironment,
        VariationCondition,
    )
except Exception as exc:
    print("ERRO: não consegui importar darwin_physical_variation_nursery.py")
    print("Coloque este arquivo na mesma pasta do script de variação anterior.")
    print(f"Detalhe técnico: {exc!r}")
    raise


ORACLE_MODULE = "nursery_v46_physical_variation_oracle"
ORACLE_SOURCE_TAG = "synthetic_oracle"


@dataclass(frozen=True)
class OracleObservation:
    observed: str  # stable ou unstable
    confidence: str  # low, medium, high
    precision: str  # qualitative, semiquantitative
    rule_note: str


class SyntheticPhysicalOracle:
    """
    Oráculo pedagógico simples para simular observações físicas qualitativas.

    Regras intencionais:
    - square_A e square_B são boas bases em condições leves/moderadas.
    - triangle_A é fraca como base para quadrados.
    - triangle_A pode funcionar como topo sobre base quadrada.
    - toque_forte é tratado como perturbação forte e tende a derrubar.
    - tudo é marcado como sintético, não como medição real.
    """

    def observe(self, lower_id: str, upper_id: str, condition: VariationCondition) -> OracleObservation:
        lower_is_square = lower_id.startswith("square")
        upper_is_square = upper_id.startswith("square")
        lower_is_triangle = lower_id.startswith("triangle")
        upper_is_triangle = upper_id.startswith("triangle")
        code = condition.code

        # Perturbação forte: neste estágio pedagógico, assume limite severo.
        if code == "toque_forte":
            return OracleObservation(
                observed="unstable",
                confidence="medium",
                precision="qualitative",
                rule_note="perturbação forte tende a romper estabilidade em berçário manual sintético",
            )

        # Triângulo como base: ponto crítico persistente.
        if lower_is_triangle and upper_is_square:
            return OracleObservation(
                observed="unstable",
                confidence="high",
                precision="qualitative",
                rule_note="base triangular sustenta mal topo quadrado neste modelo sintético",
            )

        # Base quadrada com topo quadrado: robusta em variações leves.
        if lower_is_square and upper_is_square:
            if code in {"controle_plano", "superficie_inclinada", "topo_desalinhado", "toque_leve"}:
                return OracleObservation(
                    observed="stable",
                    confidence="medium" if code != "controle_plano" else "high",
                    precision="qualitative",
                    rule_note="base quadrada preserva estabilidade sob variação leve neste modelo sintético",
                )

        # Base quadrada com topo triangular: geralmente estável, mas menos robusta que quadrado-quadrado.
        if lower_is_square and upper_is_triangle:
            if code in {"controle_plano", "superficie_inclinada", "triangulo_girado", "toque_leve"}:
                return OracleObservation(
                    observed="stable",
                    confidence="medium",
                    precision="qualitative",
                    rule_note="triângulo como topo sobre base quadrada permanece funcional neste modelo sintético",
                )
            if code == "topo_desalinhado":
                return OracleObservation(
                    observed="unstable",
                    confidence="low",
                    precision="qualitative",
                    rule_note="topo triangular desalinhado é tratado como caso limítrofe e instável no modelo sintético",
                )

        # Condição triângulo girado sem triângulo no par: pouco informativa; mantém regra do par.
        if code == "triangulo_girado" and not (lower_is_triangle or upper_is_triangle):
            return OracleObservation(
                observed="stable" if lower_is_square else "unstable",
                confidence="low",
                precision="qualitative",
                rule_note="condição triângulo_girado é pouco informativa sem triângulo no par",
            )

        # Fallback conservador.
        return OracleObservation(
            observed="stable" if lower_is_square else "unstable",
            confidence="low",
            precision="qualitative",
            rule_note="fallback sintético baseado principalmente na geometria da base",
        )


class OraclePhysicalVariationEnvironment(PhysicalVariationEnvironment):
    def __init__(self, specs: list[ManualObjectSpec], oracle: SyntheticPhysicalOracle) -> None:
        super().__init__(specs)
        self.oracle = oracle
        self.oracle_trials: list[tuple[str, str, str, str, str]] = []

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

        obs = self.oracle.observe(lower_id, upper_id, condition)
        observed = obs.observed
        self.oracle_trials.append((lower_id, upper_id, condition.code, observed, obs.confidence))

        print("\n" + "-" * 72)
        print("VALIDAÇÃO SINTÉTICA POR ORÁCULO PEDAGÓGICO")
        print("-" * 72)
        print(f"Darwin quer testar: {upper_id} SOBRE {lower_id}")
        print(f"Condição: {condition.label} [{condition.code}]")
        print(f"Observação sintética: {observed}")
        print(f"Confiança sintética: {obs.confidence}")
        print(f"Precisão: {obs.precision}")
        print(f"Nota da regra: {obs.rule_note}")
        print("Aviso: isto é dado sintético, não observação física real.")

        common_learned = [
            f"variation_condition:{condition.code}:label:{condition.label}=true",
            f"variation_condition:{condition.code}:hint:{condition.hypothesis_hint}=true",
            f"pair_context:{lower_id}>{upper_id}:variation:{condition.code}:stack:{observed}=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:observed:{observed}=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:tested=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:source:{ORACLE_SOURCE_TAG}=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:confidence:{obs.confidence}=true",
            f"physical_variation:{lower_id}>{upper_id}:condition:{condition.code}:precision:{obs.precision}=true",
            f"synthetic_oracle:{condition.code}:{lower_id}>{upper_id}:rule_note:{self._safe_note(obs.rule_note)}=true",
        ]

        if observed == "stable":
            self.objects[upper_id].position = f"sobre_{lower_id}_em_{condition.code}_synthetic"
            learned = [
                f"obj:{lower_id}:affordance:suporta_empilhar=true",
                f"obj:{upper_id}:affordance:empilhavel=true",
                f"variation_effect:{condition.code}:{lower_id}>{upper_id}:preserved_stability=true",
                f"condition_rule:{condition.code}:{lower_id}:as_base:stable_with:{upper_id}=true",
                f"oracle_validation:{condition.code}:{lower_id}>{upper_id}:stable:{obs.confidence}=true",
            ] + common_learned
            return NurseryActionResult(
                True,
                (
                    f"[oráculo sintético] {upper_id} sobre {lower_id} foi marcado como estável "
                    f"em {condition.label} (confiança={obs.confidence})."
                ),
                0.82,
                0.34 if condition.destabilizing else 0.24,
                0.12,
                0.70,
                learned,
            )

        learned = [
            f"pair:{lower_id}>{upper_id}:stack:unstable=true",
            f"variation_effect:{condition.code}:{lower_id}>{upper_id}:destabilized=true",
            f"condition_rule:{condition.code}:{lower_id}:as_base:unstable_with:{upper_id}=true",
            f"oracle_validation:{condition.code}:{lower_id}>{upper_id}:unstable:{obs.confidence}=true",
        ] + common_learned
        return NurseryActionResult(
            False,
            (
                f"[oráculo sintético] {upper_id} sobre {lower_id} foi marcado como instável "
                f"em {condition.label} (confiança={obs.confidence})."
            ),
            0.34,
            0.44,
            0.56 if condition.destabilizing else 0.46,
            0.70,
            learned,
        )

    def _safe_note(self, text: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text.lower())
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip("_")[:80] or "sem_nota"


class DarwinPhysicalVariationOracleSession(DarwinPhysicalVariationSession):
    def __init__(self) -> None:
        super().__init__()
        self.oracle = SyntheticPhysicalOracle()
        self.agent.env = OraclePhysicalVariationEnvironment(self._default_specs(), self.oracle)
        self.home.add_episode(
            module=ORACLE_MODULE,
            context="start synthetic oracle variation nursery",
            action_taken="start_oracle_mode",
            outcome="success",
            lesson=(
                "Darwin entrou em modo de tutor sintético para continuar variações controladas "
                "sem depender de teste manual imediato. Dados devem ser revalidados fisicamente depois."
            ),
            sigma_before=self.agent.sigma_now(),
            sigma_after=self.agent.sigma_now(),
        )

    def intro(self) -> None:
        print("=" * 72)
        print("DARWIN — Physical Variation Oracle Nursery")
        print("=" * 72)
        print("\nObjetivo desta fase:")
        print("  • continuar o desenvolvimento mesmo quando o tutor humano está cansado")
        print("  • usar um oráculo pedagógico sintético para stable/unstable")
        print("  • marcar todo dado como synthetic_oracle")
        print("  • manter a arquitetura de previsão → validação → memória")
        print("\nCuidado científico:")
        print("  • isto NÃO é dado físico real")
        print("  • use para avançar o fluxo e depois revalide casos importantes")
        print("\nMundo físico sintético de variação:")
        print(self.agent.env.describe_world())
        print("\nComandos disponíveis:")
        print("  1 - rodar 1 passo automático sintético")
        print("  2 - rodar lote automático sintético")
        print("  3 - rodar cobertura completa restante")
        print("  4 - mostrar cobertura de variações")
        print("  5 - mostrar estado")
        print("  6 - mostrar currículo e painéis")
        print("  7 - exportar snapshot")
        print("  8 - sair")

    def run_one_oracle_step(self) -> None:
        lower, upper, condition, reason = self.choose_next_variation()
        reason = f"oráculo sintético: {reason}"
        self.run_variation_experiment(lower, upper, condition, reason)

    def run_batch(self, steps: int) -> None:
        steps = max(1, int(steps))
        for idx in range(steps):
            print("\n" + "#" * 72)
            print(f"LOTE SINTÉTICO — passo {idx + 1}/{steps}")
            print("#" * 72)
            self.run_one_oracle_step()
            # deixa o próprio agente consolidar quando achar necessário em execuções futuras;
            # aqui não forçamos consolidação para não esconder o efeito das variações.

    def run_full_remaining(self, max_steps: int = 36) -> None:
        """Roda até cobrir todas as combinações ainda ausentes, com limite de segurança."""
        for idx in range(max_steps):
            before = self._total_observations()
            if before >= len(self.pairs()) * len(VARIATIONS):
                print("\nCobertura completa detectada para pares × condições.")
                break
            print("\n" + "#" * 72)
            print(f"COBERTURA COMPLETA SINTÉTICA — passo {idx + 1}/{max_steps}")
            print("#" * 72)
            self.run_one_oracle_step()
            after = self._total_observations()
            if after <= before:
                print("\nAtenção: nenhuma nova observação detectada neste passo; interrompendo para evitar loop.")
                break

    def _total_observations(self) -> int:
        total = 0
        for lower, upper in self.pairs():
            for condition in VARIATIONS:
                stable = self.home.get_semantic_memory(
                    f"physical_variation:{lower}>{upper}:condition:{condition.code}:observed:stable"
                )
                unstable = self.home.get_semantic_memory(
                    f"physical_variation:{lower}>{upper}:condition:{condition.code}:observed:unstable"
                )
                if stable or unstable:
                    total += 1
        return total

    def run(self) -> None:
        self.intro()
        while True:
            choice = input("\nEscolha: ").strip().lower()
            if choice == "1":
                self.run_one_oracle_step()
            elif choice == "2":
                raw = input("Quantos passos sintéticos? [padrão 6]: ").strip()
                steps = int(raw) if raw.isdigit() else 6
                self.run_batch(steps)
            elif choice == "3":
                raw = input("Limite máximo de passos? [padrão 36]: ").strip()
                limit = int(raw) if raw.isdigit() else 36
                self.run_full_remaining(limit)
            elif choice == "4":
                print("\n" + "=" * 72)
                print(self.show_variation_coverage())
            elif choice == "5":
                print("\n" + "=" * 72)
                print(self.agent.show_state())
            elif choice == "6":
                print("\n" + "=" * 72)
                print(self.agent.curriculum_and_panels())
            elif choice == "7":
                snapshot = self.home.export_snapshot()
                print(f"\nSnapshot exportado em: {snapshot}")
            elif choice in {"8", "sair", "exit", "quit"}:
                print("\nEncerrando Physical Variation Oracle Nursery.")
                self.home.close()
                break
            else:
                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7 ou 8.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin Physical Variation Oracle Nursery")
    parser.add_argument("--batch", type=int, default=0, help="Roda N passos sintéticos e encerra.")
    parser.add_argument("--full", action="store_true", help="Roda cobertura sintética restante e encerra.")
    parser.add_argument("--limit", type=int, default=36, help="Limite de passos para --full.")
    args = parser.parse_args()

    session = DarwinPhysicalVariationOracleSession()
    if args.batch > 0:
        session.intro()
        session.run_batch(args.batch)
        print("\n" + "=" * 72)
        print(session.show_variation_coverage())
        session.home.close()
        return 0
    if args.full:
        session.intro()
        session.run_full_remaining(args.limit)
        print("\n" + "=" * 72)
        print(session.show_variation_coverage())
        session.home.close()
        return 0

    session.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
