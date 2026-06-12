from __future__ import annotations

"""
DARWIN v47 — Smoke Test de Tensão Persistente

Objetivo:
- Gerar UMA tensão artificial, claramente marcada como teste.
- Exercitar o caminho real do agente v47:
  register_tension_from_contradiction()
  refresh_tension_economy()
  mark_probe_selected()
  finalize_probe_validation()
- Confirmar que as tabelas:
  tension_cases
  tension_events
  tension_probes
  tension_outcomes
  começam a receber registros.

Importante:
- Isto NÃO ensina conteúdo físico novo ao Darwin.
- Isto NÃO altera semantic_memory diretamente.
- Isto cria registros de teste na memória executiva de tensões.
- Os registros são marcados com [SMOKE_TEST_V47].
- Um backup do banco é criado antes do teste.

Uso recomendado:

    py darwin_v47_smoke_test_tension.py --dry-run
    py darwin_v47_smoke_test_tension.py
    py darwin_check_v47_tensions.py --details

Para apagar os registros de teste depois:

    py darwin_v47_smoke_test_tension.py --purge-smoke-tests

"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
SMOKE_PREFIX = "[SMOKE_TEST_V47]"
SMOKE_COUNTER_START = 47000


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def backup_db() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"darwin_pre_v47_smoke_test_{now_stamp()}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def purge_smoke_tests() -> None:
    with connect() as conn:
        if not table_exists(conn, "tension_cases"):
            print("Tabela tension_cases não existe. Nada para apagar.")
            return

        rows = conn.execute(
            """
            SELECT tension_id
            FROM tension_cases
            WHERE semantic_summary LIKE ?
               OR tension_id LIKE 'TV47%'
            """,
            (f"{SMOKE_PREFIX}%",),
        ).fetchall()

        ids = [str(row["tension_id"]) for row in rows]
        if not ids:
            print("Nenhum registro de smoke test encontrado.")
            return

        placeholders = ",".join("?" for _ in ids)

        # Apaga filhos primeiro.
        for table in ("tension_outcomes", "tension_probes", "tension_events"):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

        conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)
        conn.commit()

    print(f"Registros de smoke test apagados: {len(ids)} caso(s).")
    for tid in ids:
        print(f"- {tid}")


def run_smoke_test(dry_run: bool) -> None:
    print("=" * 72)
    print("DARWIN v47 — SMOKE TEST DE TENSÃO PERSISTENTE")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Instanciar DarwinNurseryAgent da v47.")
        print("3. Forçar uma contradição artificial marcada como [SMOKE_TEST_V47].")
        print("4. Recalcular economia de tensões.")
        print("5. Selecionar uma sonda artificial.")
        print("6. Finalizar a sonda como closed.")
        print("7. Mostrar contagens das tabelas v47.")
        print()
        print("Nenhuma escrita foi feita.")
        return

    backup_path = backup_db()
    print(f"[OK] Backup criado: {backup_path}")

    print_counts("Contagens antes:")

    # Imports só acontecem após o backup existir.
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()

    try:
        agent = DarwinNurseryAgent(home)

        # Evita colisão com TV001, TV002... de execuções reais futuras.
        # A tensão gerada aqui deve sair como TV47001.
        if hasattr(agent, "live_tension_counter_v46"):
            agent.live_tension_counter_v46 = SMOKE_COUNTER_START

        smoke_summary = (
            f"{SMOKE_PREFIX} contradição artificial para testar persistência v47; "
            "não representa observação física nova nem ensino semântico."
        )

        print()
        print("Abrindo tensão artificial controlada...")
        tension_id = agent.register_tension_from_contradiction(
            lower="blue_cube",
            upper="green_cylinder",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_rolling_top",
                "with_stackable_top",
                "v47_smoke_test",
            ],
            semantic_summary=smoke_summary,
            inherited_pairs=["green_cylinder>yellow_triangle"],
            magnitude=1.0,
        )
        print(f"[OK] Tensão criada: {tension_id}")

        print("Atualizando economia de tensões...")
        agent.refresh_tension_economy(
            candidate_pairs=[
                "blue_cube>green_cylinder",
                "green_cylinder>yellow_triangle",
            ]
        )
        print("[OK] Economia atualizada")

        case = agent.live_tension_cases.get(tension_id)
        if case is None:
            raise RuntimeError(f"Tensão {tension_id} não encontrada no runtime após abertura.")

        print("Selecionando sonda artificial...")
        agent.mark_probe_selected(
            lower="green_cylinder",
            upper="yellow_triangle",
            labels=[
                "with_block_top",
                "with_nonrolling_top",
                "with_stackable_top",
                "v47_smoke_test",
            ],
            score=0.88,
            judgment=(
                f"{SMOKE_PREFIX} sonda artificial para verificar registro em tension_probes"
            ),
        )
        print("[OK] Sonda registrada")

        print("Finalizando sonda artificial...")
        outcome = agent.finalize_probe_validation(
            lower="green_cylinder",
            upper="yellow_triangle",
            observed="stable",
        )
        print(f"[OK] Outcome: {outcome}")

        print("Atualizando economia após desfecho...")
        agent.refresh_tension_economy(
            candidate_pairs=[
                "blue_cube>green_cylinder",
                "green_cylinder>yellow_triangle",
            ]
        )

    finally:
        home.close()

    print_counts("Contagens depois:")

    print()
    print("Smoke test concluído.")
    print("Agora rode:")
    print("  py darwin_check_v47_tensions.py --details")
    print()
    print("Para limpar estes registros artificiais depois:")
    print("  py darwin_v47_smoke_test_tension.py --purge-smoke-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test da memória executiva de tensões v47.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever no banco.")
    parser.add_argument("--purge-smoke-tests", action="store_true", help="Remove registros artificiais [SMOKE_TEST_V47].")
    args = parser.parse_args()

    if args.purge_smoke_tests:
        print("=" * 72)
        print("DARWIN v47 — PURGE DE SMOKE TESTS")
        print("=" * 72)
        backup_path = backup_db()
        print(f"[OK] Backup criado antes do purge: {backup_path}")
        purge_smoke_tests()
        print_counts("Contagens após purge:")
        return 0

    run_smoke_test(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
