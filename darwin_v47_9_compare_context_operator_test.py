from __future__ import annotations

"""
DARWIN v47.9 — Teste do Operador Real compare_context

Verifica:
1. Criação de tensão com estágio compare_context_before_prediction.
2. Reidratação.
3. choose_autonomous_action executa _v47_9_run_compare_context antes do predict.
4. Uma linha aparece em tension_context_comparisons.
5. Predict/validate continuam seguros.
6. O comando/painel interno context_comparison_summary mostra a comparação.

Uso:
    py darwin_v47_9_compare_context_operator_test.py --dry-run
    py darwin_v47_9_compare_context_operator_test.py

Limpeza:
    py darwin_v47_9_compare_context_operator_test.py --purge-compare-tests
"""

import argparse
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[COMPARE_TEST_V47_9]"
COUNTER_START = 47900


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
            "tension_context_comparisons",
        ):
            n = count_table(conn, table)
            value = "AUSENTE" if n < 0 else str(n)
            print(f"- {table}: {value}")


def purge_compare_tests() -> None:
    with connect() as conn:
        ids = []
        if table_exists(conn, "tension_cases"):
            rows = conn.execute(
                """
                SELECT tension_id
                FROM tension_cases
                WHERE semantic_summary LIKE ?
                   OR tension_id LIKE 'TV479%'
                """,
                (f"{PREFIX}%",),
            ).fetchall()
            ids = [str(row["tension_id"]) for row in rows]

        routine_ids = [f"RR:{tid}" for tid in ids]

        if ids:
            placeholders = ",".join("?" for _ in ids)
            for table in ("tension_outcomes", "tension_probes", "tension_events"):
                if table_exists(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)
            if table_exists(conn, "tension_context_comparisons"):
                conn.execute(f"DELETE FROM tension_context_comparisons WHERE tension_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)

        if routine_ids:
            placeholders_r = ",".join("?" for _ in routine_ids)
            if table_exists(conn, "tension_resolution_steps"):
                conn.execute(
                    f"DELETE FROM tension_resolution_steps WHERE routine_id IN ({placeholders_r})",
                    routine_ids,
                )
            if table_exists(conn, "tension_resolution_routines"):
                conn.execute(
                    f"DELETE FROM tension_resolution_routines WHERE routine_id IN ({placeholders_r})",
                    routine_ids,
                )

        conn.commit()

    if ids:
        print(f"Registros v47.9 apagados: {len(ids)} caso(s).")
        for tid in ids:
            print(f"- {tid}")
    else:
        print("Nenhum registro v47.9 encontrado.")


def create_open_tensions() -> list[str]:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)
        if hasattr(agent, "live_tension_counter_v46"):
            agent.live_tension_counter_v46 = COUNTER_START

        agent.step_counter = 71
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_9_compare_test",
            ],
            semantic_summary=f"{PREFIX} tensão A para testar operador compare_context.",
            inherited_pairs=[
                "blue_cube>red_ball",
                "yellow_triangle>red_ball",
                "green_cylinder>yellow_triangle",
            ],
            magnitude=1.22,
        )

        agent.step_counter = 72
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_9_compare_test",
            ],
            semantic_summary=f"{PREFIX} tensão B para testar comparação antes de predict.",
            inherited_pairs=[
                "blue_cube>yellow_triangle",
                "green_cylinder>blue_cube",
            ],
            magnitude=1.31,
        )

        agent.step_counter = 73
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


def count_comparisons_for(tension_id: str) -> int:
    with connect() as conn:
        if not table_exists(conn, "tension_context_comparisons"):
            return 0
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tension_context_comparisons WHERE tension_id=?",
            (tension_id,),
        ).fetchone()
        return int(row["n"]) if row else 0


def routine_step_count() -> int:
    with connect() as conn:
        if not table_exists(conn, "tension_resolution_steps"):
            return 0
        row = conn.execute("SELECT COUNT(*) AS n FROM tension_resolution_steps").fetchone()
        return int(row["n"]) if row else 0


def run_compare_check() -> bool:
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
        print()
        print(f"Tensão ativa: {active_id}")

        print()
        print("Resumo do seletor antes do primeiro passo:")
        policy = agent.tension_resolution_policy_summary()
        print(policy)

        ok_policy = "compare_context_before_prediction" in policy

        plan1 = agent.choose_autonomous_action()
        print()
        print("Plano 1:")
        print(f"- action: {plan1.action_name}")
        print(f"- target: {plan1.target_a}>{plan1.target_b}")
        print(f"- phase : {getattr(plan1, 'lesson_phase', '')}")
        print(f"- bucket: {getattr(plan1, 'curriculum_bucket', '')}")
        print(f"- why   : {plan1.explanation}")
        print()
        print(agent.context_comparison_summary())
        print()
        print(agent.tension_resolution_routine_summary())

        comparisons = count_comparisons_for(active_id)
        ok_compare = comparisons >= 1 and "compare_context v47.9" in plan1.explanation

        ok_plan1 = (
            plan1.action_name == "predict"
            and getattr(plan1, "lesson_phase", "") == "executive_resolution_routine"
            and getattr(plan1, "curriculum_bucket", "") == "routine_compare_then_predict"
        )

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

        ok_plan2 = (
            plan2.action_name == "validate"
            and getattr(plan2, "lesson_phase", "") == "executive_resolution_routine"
        )

        print()
        print("Executando plano 2...")
        print(agent.execute_action(plan2))

        steps = routine_step_count()
        ok_steps = steps >= 2

        print()
        print("Verificação:")
        print(f"- policy stage compare: {ok_policy}")
        print(f"- comparação persistida: {ok_compare} ({comparisons})")
        print(f"- plano 1 compare_then_predict: {ok_plan1}")
        print(f"- plano 2 validate: {ok_plan2}")
        print(f"- steps >= 2: {ok_steps}")

        ok = ok_policy and ok_compare and ok_plan1 and ok_plan2 and ok_steps
        print(f"- resultado: {'OK' if ok else 'FALHOU'}")
        return ok

    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.9 — TESTE DO OPERADOR compare_context")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Criar 2 tensões abertas marcadas como [COMPARE_TEST_V47_9].")
        print("3. Reidratar tensões.")
        print("4. Verificar estágio compare_context_before_prediction.")
        print("5. Confirmar que choose_autonomous_action persiste tension_context_comparisons.")
        print("6. Executar predict e validate com segurança.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_9_compare_context_operator_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")
    create_open_tensions()
    print_counts("Contagens após criação das tensões:")

    ok = run_compare_check()

    print_counts("Contagens depois:")

    print()
    print(f"Resultado final: {'OK' if ok else 'FALHOU'}")
    print()
    print("Para inspecionar manualmente:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10x")
    print("  10p")
    print("  10m")
    print()
    print("Para limpar:")
    print("  py darwin_v47_9_compare_context_operator_test.py --purge-compare-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste do operador compare_context v47.9.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-compare-tests", action="store_true", help="Remove registros artificiais [COMPARE_TEST_V47_9].")
    args = parser.parse_args()

    if args.purge_compare_tests:
        print("=" * 72)
        print("DARWIN v47.9 — PURGE DO OPERADOR compare_context")
        print("=" * 72)
        backup = backup_db("v47_9_compare_context_operator_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_compare_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
