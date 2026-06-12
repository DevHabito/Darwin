from __future__ import annotations

"""
DARWIN v47.6.1 — Teste do Painel 10c

Verifica se, antes da primeira decisão comprometida da sessão, o relatório
executive_commitment_summary() já mostra a dívida executiva ativa reidratada.

Fluxo:
1. Cria 2 tensões abertas artificiais.
2. Encerra o runtime.
3. Instancia novo DarwinNurseryAgent, que reidrata as tensões.
4. Chama executive_commitment_summary() antes de choose_autonomous_action().
5. Esperado:
   - "dívida executiva ativa"
   - ID da tensão ativa
   - próximo ato esperado predict(...) ou validate(...)

Uso:
    py darwin_v47_6_1_commitment_panel_test.py --dry-run
    py darwin_v47_6_1_commitment_panel_test.py

Para limpar:
    py darwin_v47_6_1_commitment_panel_test.py --purge-panel-tests
"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[COMMITMENT_PANEL_TEST_V47_6_1]"
COUNTER_START = 47610


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def backup_db(reason: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"darwin_pre_{reason}_{now_stamp()}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


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


def print_counts(title: str) -> None:
    print()
    print(title)
    with connect() as conn:
        for table in ("tension_cases", "tension_events", "tension_probes", "tension_outcomes"):
            n = count_table(conn, table)
            value = "AUSENTE" if n < 0 else str(n)
            print(f"- {table}: {value}")


def purge_panel_tests() -> None:
    with connect() as conn:
        if not table_exists(conn, "tension_cases"):
            print("Tabela tension_cases não existe. Nada para apagar.")
            return

        rows = conn.execute(
            """
            SELECT tension_id
            FROM tension_cases
            WHERE semantic_summary LIKE ?
               OR tension_id LIKE 'TV4761%'
            """,
            (f"{PREFIX}%",),
        ).fetchall()

        ids = [str(row["tension_id"]) for row in rows]
        if not ids:
            print("Nenhum registro de painel v47.6.1 encontrado.")
            return

        placeholders = ",".join("?" for _ in ids)

        for table in ("tension_outcomes", "tension_probes", "tension_events"):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

        conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)
        conn.commit()

    print(f"Registros de painel apagados: {len(ids)} caso(s).")
    for tid in ids:
        print(f"- {tid}")


def create_open_tensions() -> list[str]:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)

        if hasattr(agent, "live_tension_counter_v46"):
            agent.live_tension_counter_v46 = COUNTER_START

        agent.step_counter = 51
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_6_1_commitment_panel_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão A aberta para testar painel 10c antes da decisão."
            ),
            inherited_pairs=["blue_cube>red_ball", "yellow_triangle>red_ball"],
            magnitude=1.22,
        )

        agent.step_counter = 52
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_6_1_commitment_panel_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão B aberta para testar dívida executiva ativa."
            ),
            inherited_pairs=["blue_cube>yellow_triangle"],
            magnitude=1.31,
        )

        agent.step_counter = 53
        agent.refresh_tension_economy(
            candidate_pairs=[
                "green_cylinder>red_ball",
                "yellow_triangle>blue_cube",
                "blue_cube>red_ball",
            ]
        )

        print()
        print("Mercado criado antes do reinício:")
        print(agent.live_tension_market_summary())
        print()
        print(agent.active_tension_summary())

        return [t1, t2]
    finally:
        home.close()


def verify_panel() -> bool:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)

        active_id = getattr(agent, "active_tension_id", None)
        summary = agent.executive_commitment_summary()

        print()
        print("Resumo 10c antes de choose_autonomous_action:")
        print(summary)

        ok = (
            active_id is not None
            and "dívida executiva ativa" in summary
            and str(active_id) in summary
            and "próximo ato esperado" in summary
        )

        print()
        print("Verificação:")
        print(f"- active_tension_id: {active_id}")
        print(f"- contém dívida executiva ativa: {'dívida executiva ativa' in summary}")
        print(f"- contém próximo ato esperado: {'próximo ato esperado' in summary}")
        print(f"- resultado: {'OK' if ok else 'FALHOU'}")

        return ok
    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.6.1 — TESTE DO PAINEL 10c")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Criar 2 tensões abertas marcadas como [COMMITMENT_PANEL_TEST_V47_6_1].")
        print("3. Encerrar runtime.")
        print("4. Instanciar novo agente e reidratar tensões.")
        print("5. Chamar executive_commitment_summary() antes de choose_autonomous_action().")
        print("6. Verificar se o painel 10c mostra dívida executiva ativa.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_6_1_commitment_panel_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")

    create_open_tensions()

    print_counts("Contagens após criação das tensões:")

    ok = verify_panel()

    print()
    print(f"Resultado final: {'OK' if ok else 'FALHOU'}")
    print()
    print("Para inspecionar manualmente:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10c")
    print("  10")
    print()
    print("Para limpar:")
    print("  py darwin_v47_6_1_commitment_panel_test.py --purge-panel-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste do painel 10c v47.6.1.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-panel-tests", action="store_true", help="Remove registros artificiais [COMMITMENT_PANEL_TEST_V47_6_1].")
    args = parser.parse_args()

    if args.purge_panel_tests:
        print("=" * 72)
        print("DARWIN v47.6.1 — PURGE DO PAINEL")
        print("=" * 72)
        backup = backup_db("v47_6_1_commitment_panel_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_panel_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
