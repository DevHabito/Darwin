from __future__ import annotations

"""
DARWIN v47.12 — Teste do Relatório Consolidado do Ciclo Cognitivo

Verifica:
1. Tensão ativa seleciona compare_context_before_prediction.
2. compare_context é executado.
3. prediction_influence é persistida.
4. hypothesis_lineage é persistida.
5. validate registra tension_cognitive_cycle_reports.
6. O relatório 10z resume o ciclo completo.

Uso:
    py darwin_v47_12_cycle_report_test.py --dry-run
    py darwin_v47_12_cycle_report_test.py

Limpeza:
    py darwin_v47_12_cycle_report_test.py --purge-cycle-tests
"""

import argparse
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[CYCLE_TEST_V47_12]"
COUNTER_START = 47120


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
            "tension_prediction_influences",
            "tension_hypothesis_lineage",
            "tension_cognitive_cycle_reports",
        ):
            n = count_table(conn, table)
            value = "AUSENTE" if n < 0 else str(n)
            print(f"- {table}: {value}")


def purge_cycle_tests() -> None:
    with connect() as conn:
        ids = []
        if table_exists(conn, "tension_cases"):
            rows = conn.execute(
                """
                SELECT tension_id
                FROM tension_cases
                WHERE semantic_summary LIKE ?
                   OR tension_id LIKE 'TV4712%'
                """,
                (f"{PREFIX}%",),
            ).fetchall()
            ids = [str(row["tension_id"]) for row in rows]

        routine_ids = [f"RR:{tid}" for tid in ids]

        if ids:
            placeholders = ",".join("?" for _ in ids)

            for table in (
                "tension_cognitive_cycle_reports",
                "tension_hypothesis_lineage",
                "tension_prediction_influences",
                "tension_context_comparisons",
            ):
                if table_exists(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

            for table in ("tension_outcomes", "tension_probes", "tension_events"):
                if table_exists(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

            if table_exists(conn, "tension_cases"):
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
        print(f"Registros v47.12 apagados: {len(ids)} caso(s).")
        for tid in ids:
            print(f"- {tid}")
    else:
        print("Nenhum registro v47.12 encontrado.")


def create_open_tensions() -> list[str]:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)
        if hasattr(agent, "live_tension_counter_v46"):
            agent.live_tension_counter_v46 = COUNTER_START

        agent.step_counter = 101
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_12_cycle_test",
            ],
            semantic_summary=f"{PREFIX} tensão A para testar relatório consolidado.",
            inherited_pairs=[
                "blue_cube>red_ball",
                "yellow_triangle>red_ball",
                "green_cylinder>yellow_triangle",
            ],
            magnitude=1.22,
        )

        agent.step_counter = 102
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_12_cycle_test",
            ],
            semantic_summary=f"{PREFIX} tensão B para testar prontuário do ciclo cognitivo.",
            inherited_pairs=[
                "blue_cube>yellow_triangle",
                "green_cylinder>blue_cube",
            ],
            magnitude=1.31,
        )

        agent.step_counter = 103
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


def count_for(table: str, tension_id: str) -> int:
    with connect() as conn:
        if not table_exists(conn, table):
            return 0
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE tension_id=?",
            (tension_id,),
        ).fetchone()
        return int(row["n"]) if row else 0


def latest_report_id(tension_id: str) -> str:
    with connect() as conn:
        if not table_exists(conn, "tension_cognitive_cycle_reports"):
            return ""
        row = conn.execute(
            """
            SELECT report_id
            FROM tension_cognitive_cycle_reports
            WHERE tension_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (tension_id,),
        ).fetchone()
        return str(row["report_id"]) if row else ""


def routine_step_count() -> int:
    with connect() as conn:
        if not table_exists(conn, "tension_resolution_steps"):
            return 0
        row = conn.execute("SELECT COUNT(*) AS n FROM tension_resolution_steps").fetchone()
        return int(row["n"]) if row else 0


def run_cycle_check() -> bool:
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
        print("Executando plano 1...")
        print(agent.execute_action(plan1))

        print()
        print(agent.context_comparison_summary())
        print()
        print(agent.prediction_influence_summary())
        print()
        print(agent.hypothesis_lineage_summary())

        plan2 = agent.choose_autonomous_action()
        print()
        print("Plano 2:")
        print(f"- action: {plan2.action_name}")
        print(f"- target: {plan2.target_a}>{plan2.target_b}")
        print(f"- phase : {getattr(plan2, 'lesson_phase', '')}")
        print(f"- bucket: {getattr(plan2, 'curriculum_bucket', '')}")
        print(f"- why   : {plan2.explanation}")

        print()
        print("Executando plano 2...")
        print(agent.execute_action(plan2))

        print()
        print(agent.cognitive_cycle_report_summary())

        comparison_count = count_for("tension_context_comparisons", active_id)
        influence_count = count_for("tension_prediction_influences", active_id)
        lineage_count = count_for("tension_hypothesis_lineage", active_id)
        report_count = count_for("tension_cognitive_cycle_reports", active_id)
        report_id = latest_report_id(active_id)

        ok_compare = comparison_count >= 1
        ok_influence = influence_count >= 1
        ok_lineage = lineage_count >= 1
        ok_report = report_count >= 1 and bool(report_id)
        ok_plan1 = (
            plan1.action_name == "predict"
            and getattr(plan1, "lesson_phase", "") == "executive_resolution_routine"
            and getattr(plan1, "curriculum_bucket", "") == "routine_compare_influenced_predict"
        )
        ok_plan2 = (
            plan2.action_name == "validate"
            and getattr(plan2, "lesson_phase", "") == "executive_resolution_routine"
        )

        steps = routine_step_count()
        ok_steps = steps >= 2

        print()
        print("Verificação:")
        print(f"- policy stage compare: {ok_policy}")
        print(f"- comparação persistida: {ok_compare} ({comparison_count})")
        print(f"- influência persistida: {ok_influence} ({influence_count})")
        print(f"- linhagem persistida: {ok_lineage} ({lineage_count})")
        print(f"- relatório consolidado persistido: {ok_report} ({report_count})")
        print(f"- report_id: {report_id}")
        print(f"- plano 1 compare_influenced_predict: {ok_plan1}")
        print(f"- plano 2 validate: {ok_plan2}")
        print(f"- steps >= 2: {ok_steps}")

        ok = ok_policy and ok_compare and ok_influence and ok_lineage and ok_report and ok_plan1 and ok_plan2 and ok_steps
        print(f"- resultado: {'OK' if ok else 'FALHOU'}")
        return ok

    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.12 — TESTE DO RELATÓRIO DO CICLO")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Criar 2 tensões abertas marcadas como [CYCLE_TEST_V47_12].")
        print("3. Executar predict com comparação, influência e linhagem.")
        print("4. Executar validate.")
        print("5. Confirmar registro em tension_cognitive_cycle_reports.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_12_cycle_report_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")
    create_open_tensions()
    print_counts("Contagens após criação das tensões:")

    ok = run_cycle_check()

    print_counts("Contagens depois:")

    print()
    print(f"Resultado final: {'OK' if ok else 'FALHOU'}")
    print()
    print("Para inspecionar manualmente:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10z")
    print("  10h")
    print("  10i")
    print()
    print("Para limpar:")
    print("  py darwin_v47_12_cycle_report_test.py --purge-cycle-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de relatório consolidado v47.12.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-cycle-tests", action="store_true", help="Remove registros artificiais [CYCLE_TEST_V47_12].")
    args = parser.parse_args()

    if args.purge_cycle_tests:
        print("=" * 72)
        print("DARWIN v47.12 — PURGE DO RELATÓRIO DO CICLO")
        print("=" * 72)
        backup = backup_db("v47_12_cycle_report_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_cycle_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
