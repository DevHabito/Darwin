from __future__ import annotations

"""
DARWIN v47.7 — Teste de Micro-Rotina de Resolução

Verifica se, após reidratar uma tensão aberta, o Darwin:
1. monta uma micro-rotina de resolução;
2. registra tension_resolution_routines e tension_resolution_steps;
3. escolhe predict no primeiro passo;
4. escolhe validate no segundo passo;
5. fecha ou atualiza a tensão ativa.

Uso:
    py darwin_v47_7_resolution_routine_test.py --dry-run
    py darwin_v47_7_resolution_routine_test.py

Para limpar:
    py darwin_v47_7_resolution_routine_test.py --purge-routine-tests
"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[ROUTINE_TEST_V47_7]"
COUNTER_START = 47700


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
        for table in (
            "tension_cases",
            "tension_events",
            "tension_probes",
            "tension_outcomes",
            "tension_resolution_routines",
            "tension_resolution_steps",
        ):
            n = count_table(conn, table)
            value = "AUSENTE" if n < 0 else str(n)
            print(f"- {table}: {value}")


def purge_routine_tests() -> None:
    with connect() as conn:
        ids: list[str] = []
        if table_exists(conn, "tension_cases"):
            rows = conn.execute(
                """
                SELECT tension_id
                FROM tension_cases
                WHERE semantic_summary LIKE ?
                   OR tension_id LIKE 'TV477%'
                """,
                (f"{PREFIX}%",),
            ).fetchall()
            ids = [str(row["tension_id"]) for row in rows]

        if not ids:
            print("Nenhum registro de rotina v47.7 encontrado.")
            return

        placeholders = ",".join("?" for _ in ids)

        for table in (
            "tension_resolution_steps",
            "tension_resolution_routines",
            "tension_outcomes",
            "tension_probes",
            "tension_events",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

        if table_exists(conn, "tension_cases"):
            conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)

        conn.commit()

    print(f"Registros de rotina apagados: {len(ids)} caso(s).")
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

        agent.step_counter = 61
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_7_resolution_routine_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão A aberta para testar rotina de resolução."
            ),
            inherited_pairs=["blue_cube>red_ball", "yellow_triangle>red_ball"],
            magnitude=1.18,
        )

        agent.step_counter = 62
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_7_resolution_routine_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão B aberta para testar rotina predict/validate."
            ),
            inherited_pairs=["blue_cube>yellow_triangle"],
            magnitude=1.32,
        )

        agent.step_counter = 63
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


def routine_counts_for(tension_id: str) -> tuple[int, int]:
    with connect() as conn:
        routines = 0
        steps = 0
        if table_exists(conn, "tension_resolution_routines"):
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM tension_resolution_routines WHERE tension_id=?",
                (tension_id,),
            ).fetchone()
            routines = int(row["n"]) if row else 0
        if table_exists(conn, "tension_resolution_steps"):
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM tension_resolution_steps WHERE tension_id=?",
                (tension_id,),
            ).fetchone()
            steps = int(row["n"]) if row else 0
        return routines, steps


def case_status(tension_id: str) -> tuple[str, str]:
    with connect() as conn:
        row = conn.execute(
            "SELECT status, outcome FROM tension_cases WHERE tension_id=?",
            (tension_id,),
        ).fetchone()
        if row is None:
            return "missing", "missing"
        return str(row["status"]), str(row["outcome"])


def run_routine_check() -> bool:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)

        print()
        print("Relatório de reidratação:")
        print(agent.v47_rehydration_summary())

        active_id = getattr(agent, "active_tension_id", None)
        active_case = agent.live_tension_cases.get(active_id) if active_id else None
        if active_case is None:
            print("[FALHA] Nenhuma tensão ativa reidratada.")
            return False

        print()
        print("Resumo da micro-rotina antes do primeiro passo:")
        print(agent.tension_resolution_routine_summary())

        plan1 = agent.choose_autonomous_action()
        print()
        print("Plano 1:")
        print(f"- action: {plan1.action_name}")
        print(f"- target: {plan1.target_a}>{plan1.target_b}")
        print(f"- phase : {getattr(plan1, 'lesson_phase', '')}")
        print(f"- bucket: {getattr(plan1, 'curriculum_bucket', '')}")
        print(f"- why   : {plan1.explanation}")
        print()
        print(agent.tension_resolution_routine_summary())

        ok1 = (
            plan1.action_name == "predict"
            and getattr(plan1, "lesson_phase", "") == "executive_resolution_routine"
            and plan1.target_a == active_case.source_lower
            and plan1.target_b == active_case.source_upper
            and "micro-rotina" in plan1.explanation
        )

        if not ok1:
            print("[FALHA] Plano 1 não veio da micro-rotina de resolução.")
            return False

        print()
        print("Executando plano 1...")
        print(agent.execute_action(plan1))

        plan2 = agent.choose_autonomous_action()
        print()
        print("Plano 2:")
        print(f"- action: {plan2.action_name}")
        print(f"- target: {plan2.target_a}>{plan2.target_b}")
        print(f"- phase : {getattr(plan2, 'lesson_phase', '')}")
        print(f"- bucket: {getattr(plan2, 'curriculum_bucket', '')}")
        print(f"- why   : {plan2.explanation}")
        print()
        print(agent.tension_resolution_routine_summary())

        ok2 = (
            plan2.action_name == "validate"
            and getattr(plan2, "lesson_phase", "") == "executive_resolution_routine"
            and plan2.target_a == active_case.source_lower
            and plan2.target_b == active_case.source_upper
            and "micro-rotina" in plan2.explanation
        )

        if not ok2:
            print("[FALHA] Plano 2 não virou validação da micro-rotina.")
            return False

        print()
        print("Executando plano 2...")
        print(agent.execute_action(plan2))

        routines, steps = routine_counts_for(active_id)
        status, outcome = case_status(active_id)
        print()
        print("Estado persistido após a micro-rotina:")
        print(f"- active_id: {active_id}")
        print(f"- routines: {routines}")
        print(f"- steps: {steps}")
        print(f"- status/outcome: {status}/{outcome}")

        ok_db = routines >= 1 and steps >= 2
        ok_status = status in {"closed", "open", "probing", "reopened", "weakened"}
        if status != "closed":
            print("[AVISO] A tensão ativa não fechou; rotina ainda assim registrou passos.")

        return ok1 and ok2 and ok_db and ok_status

    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.7 — TESTE DE MICRO-ROTINA")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Criar 2 tensões abertas marcadas como [ROUTINE_TEST_V47_7].")
        print("3. Encerrar runtime.")
        print("4. Instanciar novo agente e reidratar tensões.")
        print("5. Confirmar que choose_autonomous_action usa executive_resolution_routine.")
        print("6. Executar predict e validate dentro da micro-rotina.")
        print("7. Confirmar registros em tension_resolution_routines/steps.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_7_resolution_routine_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")
    create_open_tensions()
    print_counts("Contagens após criação das tensões:")

    ok = run_routine_check()

    print_counts("Contagens depois:")

    print()
    print(f"Resultado final: {'OK' if ok else 'FALHOU'}")
    print()
    print("Para inspecionar manualmente:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10m")
    print("  10c")
    print("  10")
    print()
    print("Para limpar:")
    print("  py darwin_v47_7_resolution_routine_test.py --purge-routine-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste da micro-rotina de resolução v47.7.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-routine-tests", action="store_true", help="Remove registros artificiais [ROUTINE_TEST_V47_7].")
    args = parser.parse_args()

    if args.purge_routine_tests:
        print("=" * 72)
        print("DARWIN v47.7 — PURGE DE MICRO-ROTINA")
        print("=" * 72)
        backup = backup_db("v47_7_resolution_routine_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_routine_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
