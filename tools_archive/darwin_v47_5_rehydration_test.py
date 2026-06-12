from __future__ import annotations

"""
DARWIN v47.5 — Teste de Reidratação de Tensões Persistentes

Este teste verifica se a v47.5 consegue:

1. Criar tensões persistentes abertas.
2. Encerrar o runtime.
3. Abrir um novo DarwinNurseryAgent.
4. Reconstituir live_tension_cases a partir do banco.
5. Restaurar active_tension_id.

Uso:
    py darwin_v47_5_rehydration_test.py --dry-run
    py darwin_v47_5_rehydration_test.py

Depois, para ver no menu:
    py darwin_v61_nursery_v47.py
    10r
    10
    10a

Para limpar:
    py darwin_v47_5_rehydration_test.py --purge-rehydration-tests
"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[REHYDRATION_TEST_V47_5]"
COUNTER_START = 47500


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


def purge_rehydration_tests() -> None:
    with connect() as conn:
        if not table_exists(conn, "tension_cases"):
            print("Tabela tension_cases não existe. Nada para apagar.")
            return

        rows = conn.execute(
            """
            SELECT tension_id
            FROM tension_cases
            WHERE semantic_summary LIKE ?
               OR tension_id LIKE 'TV475%'
            """,
            (f"{PREFIX}%",),
        ).fetchall()

        ids = [str(row["tension_id"]) for row in rows]
        if not ids:
            print("Nenhum registro de teste de reidratação encontrado.")
            return

        placeholders = ",".join("?" for _ in ids)

        for table in ("tension_outcomes", "tension_probes", "tension_events"):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

        conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)
        conn.commit()

    print(f"Registros de reidratação apagados: {len(ids)} caso(s).")
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

        agent.step_counter = 31
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_5_rehydration_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão aberta A para verificar reidratação após reinício."
            ),
            inherited_pairs=["blue_cube>red_ball", "yellow_triangle>red_ball"],
            magnitude=1.30,
        )

        agent.step_counter = 32
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_5_rehydration_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão aberta B para verificar restauração de foco executivo."
            ),
            inherited_pairs=["blue_cube>yellow_triangle"],
            magnitude=1.05,
        )

        agent.step_counter = 33
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


def verify_rehydration(expected_ids: list[str]) -> bool:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)

        print()
        print("Relatório de reidratação no novo runtime:")
        print(agent.v47_rehydration_summary())

        live_ids = set(getattr(agent, "live_tension_cases", {}).keys())
        expected = set(expected_ids)
        active = getattr(agent, "active_tension_id", None)

        print()
        print("Verificação:")
        print(f"- esperadas: {sorted(expected)}")
        print(f"- reidratadas: {sorted(live_ids)}")
        print(f"- active_tension_id: {active}")

        ok = expected.issubset(live_ids) and active in live_ids
        print(f"- resultado: {'OK' if ok else 'FALHOU'}")
        return ok
    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.5 — TESTE DE REIDRATAÇÃO")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Criar 2 tensões abertas marcadas como [REHYDRATION_TEST_V47_5].")
        print("3. Encerrar esse runtime.")
        print("4. Instanciar novo DarwinNurseryAgent.")
        print("5. Verificar se as tensões abertas voltaram para live_tension_cases.")
        print("6. Verificar se active_tension_id foi restaurado.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_5_rehydration_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")

    expected = create_open_tensions()

    print_counts("Contagens após criação das tensões:")

    ok = verify_rehydration(expected)

    print()
    print("Teste concluído.")
    print("Agora você pode rodar:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10r")
    print("  10")
    print("  10a")
    print()
    print("Para limpar:")
    print("  py darwin_v47_5_rehydration_test.py --purge-rehydration-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de reidratação v47.5.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-rehydration-tests", action="store_true", help="Remove registros artificiais [REHYDRATION_TEST_V47_5].")
    args = parser.parse_args()

    if args.purge_rehydration_tests:
        print("=" * 72)
        print("DARWIN v47.5 — PURGE DE REIDRATAÇÃO")
        print("=" * 72)
        backup = backup_db("v47_5_rehydration_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_rehydration_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
