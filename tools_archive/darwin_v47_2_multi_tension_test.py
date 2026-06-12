from __future__ import annotations

"""
DARWIN v47.2 — Teste Controlado de Múltiplas Tensões Concorrentes

Objetivo:
- Abrir 3 tensões artificiais, claramente marcadas como teste.
- Forçar a economia v47 a escolher uma tensão ativa entre várias.
- Fechar a tensão ativa com uma sonda.
- Recalcular a economia para verificar preempção para outro caso.
- Confirmar persistência em:
  - tension_cases
  - tension_events
  - tension_probes
  - tension_outcomes

Importante:
- Este teste NÃO ensina conteúdo físico novo ao Darwin.
- Este teste NÃO escreve em semantic_memory diretamente.
- Ele cria apenas registros de teste na memória executiva de tensões.
- Tudo é marcado com [MULTI_TEST_V47_2].
- Um backup do banco é criado antes do teste.

Uso recomendado:
    py darwin_v47_2_multi_tension_test.py --dry-run
    py darwin_v47_2_multi_tension_test.py
    py darwin_check_v47_tensions.py --details

Para apagar os registros artificiais depois:
    py darwin_v47_2_multi_tension_test.py --purge-multi-tests
"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"

MULTI_PREFIX = "[MULTI_TEST_V47_2]"
MULTI_COUNTER_START = 47200


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco não encontrado: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def count_table(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return -1
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def print_counts(label: str) -> None:
    print()
    print(label)
    with connect() as conn:
        for table in ("tension_cases", "tension_events", "tension_probes", "tension_outcomes"):
            n = count_table(conn, table)
            value = "AUSENTE" if n < 0 else str(n)
            print(f"- {table}: {value}")


def backup_db(reason: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"darwin_pre_{reason}_{now_stamp()}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def purge_multi_tests() -> None:
    with connect() as conn:
        if not table_exists(conn, "tension_cases"):
            print("Tabela tension_cases não existe. Nada para apagar.")
            return

        rows = conn.execute(
            """
            SELECT tension_id
            FROM tension_cases
            WHERE semantic_summary LIKE ?
               OR tension_id LIKE 'TV472%'
            """,
            (f"{MULTI_PREFIX}%",),
        ).fetchall()

        ids = [str(row["tension_id"]) for row in rows]
        if not ids:
            print("Nenhum registro de multi-test encontrado.")
            return

        placeholders = ",".join("?" for _ in ids)

        for table in ("tension_outcomes", "tension_probes", "tension_events"):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

        conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)
        conn.commit()

    print(f"Registros de multi-test apagados: {len(ids)} caso(s).")
    for tid in ids:
        print(f"- {tid}")


def describe_market(agent, title: str) -> None:
    print()
    print(title)
    print("-" * 72)
    print(agent.live_tension_market_summary())
    print()
    print(agent.active_tension_summary())


def current_active_case(agent):
    active_id = getattr(agent, "active_tension_id", None)
    if not active_id:
        return None
    return agent.live_tension_cases.get(active_id)


def register_test_tensions(agent) -> list[str]:
    """
    Cria três tensões artificiais com perfis diferentes.

    A ideia é dar ao seletor executivo uma pequena competição:
    - caso A: contradição estável/instável em par ambíguo conhecido;
    - caso B: erro envolvendo red_ball como topo, alto valor de fechamento;
    - caso C: erro em par de blocos, menor recência.
    """
    tension_ids: list[str] = []

    # Tensão A — mais recente e bem conectada aos candidatos.
    agent.step_counter = 21
    tid = agent.register_tension_from_contradiction(
        lower="blue_cube",
        upper="green_cylinder",
        predicted="unstable",
        observed="stable",
        context_families=[
            "with_block_top",
            "with_rolling_top",
            "with_stackable_top",
            "v47_2_multi_test",
        ],
        semantic_summary=(
            f"{MULTI_PREFIX} tensão A: pessimismo artificial em par empilhável; "
            "teste de prioridade executiva e fechamento."
        ),
        inherited_pairs=[
            "yellow_triangle>green_cylinder",
            "green_cylinder>blue_cube",
        ],
        magnitude=1.15,
    )
    tension_ids.append(tid)

    # Tensão B — red_ball como topo, contradição mais forte.
    agent.step_counter = 18
    tid = agent.register_tension_from_contradiction(
        lower="green_cylinder",
        upper="red_ball",
        predicted="stable",
        observed="unstable",
        context_families=[
            "with_nonstackable_top",
            "with_rolling_top",
            "with_toy_top",
            "v47_2_multi_test",
        ],
        semantic_summary=(
            f"{MULTI_PREFIX} tensão B: otimismo artificial com red_ball como topo; "
            "teste de competição contra tensão A."
        ),
        inherited_pairs=[
            "yellow_triangle>red_ball",
            "blue_cube>red_ball",
        ],
        magnitude=1.35,
    )
    tension_ids.append(tid)

    # Tensão C — menos recente e menos conectada.
    agent.step_counter = 12
    tid = agent.register_tension_from_contradiction(
        lower="yellow_triangle",
        upper="blue_cube",
        predicted="unstable",
        observed="stable",
        context_families=[
            "with_nonstackable_top",
            "with_nonrolling_top",
            "v47_2_multi_test",
        ],
        semantic_summary=(
            f"{MULTI_PREFIX} tensão C: pessimismo artificial antigo; "
            "teste de decaimento por recência."
        ),
        inherited_pairs=[
            "blue_cube>yellow_triangle",
        ],
        magnitude=0.85,
    )
    tension_ids.append(tid)

    return tension_ids


def run_multi_test(dry_run: bool) -> None:
    print("=" * 72)
    print("DARWIN v47.2 — MULTI-TENSÃO CONTROLADA")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Instanciar DarwinNurseryAgent da v47.")
        print("3. Criar 3 tensões artificiais marcadas como [MULTI_TEST_V47_2].")
        print("4. Recalcular o mercado de tensões.")
        print("5. Mostrar qual tensão virou ativa.")
        print("6. Fechar a tensão ativa com uma sonda artificial.")
        print("7. Recalcular o mercado para verificar preempção.")
        print("8. Mostrar contagens finais.")
        print()
        print("Nenhuma escrita foi feita.")
        return

    backup_path = backup_db("v47_2_multi_tension_test")
    print(f"[OK] Backup criado: {backup_path}")

    print_counts("Contagens antes:")

    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()

    try:
        agent = DarwinNurseryAgent(home)

        if hasattr(agent, "live_tension_counter_v46"):
            agent.live_tension_counter_v46 = MULTI_COUNTER_START

        print()
        print("Abrindo 3 tensões artificiais concorrentes...")
        tension_ids = register_test_tensions(agent)
        for tid in tension_ids:
            print(f"[OK] Tensão criada: {tid}")

        agent.step_counter = 24
        print()
        print("Atualizando economia com candidatos competitivos...")
        agent.refresh_tension_economy(
            candidate_pairs=[
                "blue_cube>green_cylinder",
                "green_cylinder>red_ball",
                "yellow_triangle>blue_cube",
                "yellow_triangle>red_ball",
            ]
        )

        describe_market(agent, "Mercado após abertura das 3 tensões")

        active = current_active_case(agent)
        if active is None:
            raise RuntimeError("Nenhuma tensão ativa escolhida após refresh.")

        print()
        print(f"[OK] Tensão ativa escolhida: {active.tension_id} ({active.source_pair})")

        print("Selecionando sonda para a tensão ativa...")
        probe_lower = active.source_lower
        probe_upper = active.source_upper
        probe_labels = list(active.source_labels)

        agent.mark_probe_selected(
            lower=probe_lower,
            upper=probe_upper,
            labels=probe_labels,
            score=0.91,
            judgment=(
                f"{MULTI_PREFIX} sonda artificial para fechar a tensão ativa "
                f"{active.tension_id}"
            ),
        )
        print(f"[OK] Sonda selecionada: {probe_lower}>{probe_upper}")

        print("Finalizando sonda da tensão ativa...")
        outcome = agent.finalize_probe_validation(
            lower=probe_lower,
            upper=probe_upper,
            observed=active.source_observed,
        )
        print(f"[OK] Outcome da tensão ativa: {outcome}")

        print("Recalculando economia após fechamento da tensão ativa...")
        agent.step_counter = 25
        agent.refresh_tension_economy(
            candidate_pairs=[
                "blue_cube>green_cylinder",
                "green_cylinder>red_ball",
                "yellow_triangle>blue_cube",
                "yellow_triangle>red_ball",
            ]
        )

        describe_market(agent, "Mercado após fechamento da tensão ativa")

        next_active = current_active_case(agent)
        if next_active is None:
            print("[INFO] Nenhuma tensão ativa restante acima do limiar competitivo.")
        else:
            print(f"[OK] Nova tensão ativa: {next_active.tension_id} ({next_active.source_pair})")

    finally:
        home.close()

    print_counts("Contagens depois:")

    print()
    print("Multi-tension test concluído.")
    print("Agora rode:")
    print("  py darwin_check_v47_tensions.py --details")
    print()
    print("Para limpar estes registros artificiais depois:")
    print("  py darwin_v47_2_multi_tension_test.py --purge-multi-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste multi-tensão v47.2.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever no banco.")
    parser.add_argument("--purge-multi-tests", action="store_true", help="Remove registros artificiais [MULTI_TEST_V47_2].")
    args = parser.parse_args()

    if args.purge_multi_tests:
        print("=" * 72)
        print("DARWIN v47.2 — PURGE DE MULTI-TESTS")
        print("=" * 72)
        backup_path = backup_db("v47_2_multi_tension_purge")
        print(f"[OK] Backup criado antes do purge: {backup_path}")
        purge_multi_tests()
        print_counts("Contagens após purge:")
        return 0

    run_multi_test(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
