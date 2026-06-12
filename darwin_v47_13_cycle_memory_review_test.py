from __future__ import annotations

"""
DARWIN v47.13 — Teste de Revisão de Ciclos Passados

Verifica:
1. Um relatório consolidado passado é semeado como memória operacional.
2. Uma nova tensão parecida é aberta.
3. Darwin revisa ciclos passados antes do compare_context.
4. A revisão é persistida em tension_cycle_memory_reviews.
5. O plano vira routine_reviewed_compare_influenced_predict.
6. Predict/validate continuam funcionando.
7. O ciclo novo também recebe relatório consolidado.

Uso:
    py darwin_v47_13_cycle_memory_review_test.py --dry-run
    py darwin_v47_13_cycle_memory_review_test.py

Limpeza:
    py darwin_v47_13_cycle_memory_review_test.py --purge-review-tests
"""

import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[REVIEW_TEST_V47_13]"
COUNTER_START = 47130
PRIOR_TENSION_ID = "PRIOR_V4713_001"
PRIOR_REPORT_ID = "CYCLE:PRIOR_V4713_001:0"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def ensure_cycle_report_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tension_cognitive_cycle_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            tension_id TEXT NOT NULL,
            source_pair TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            step INTEGER,
            status_after TEXT NOT NULL DEFAULT '',
            outcome_after TEXT NOT NULL DEFAULT '',
            comparison_id TEXT NOT NULL DEFAULT '',
            influence_id TEXT NOT NULL DEFAULT '',
            lineage_id TEXT NOT NULL DEFAULT '',
            hypothesis_id TEXT NOT NULL DEFAULT '',
            validation_result TEXT NOT NULL DEFAULT '',
            closure_assessment TEXT NOT NULL DEFAULT '',
            narrative TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tension_cognitive_cycle_reports_tension
        ON tension_cognitive_cycle_reports(tension_id, id)
        """
    )
    conn.commit()


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
            "tension_cycle_memory_reviews",
        ):
            n = count_table(conn, table)
            value = "AUSENTE" if n < 0 else str(n)
            print(f"- {table}: {value}")


def purge_review_tests() -> None:
    with connect() as conn:
        ids = []
        if table_exists(conn, "tension_cases"):
            rows = conn.execute(
                """
                SELECT tension_id
                FROM tension_cases
                WHERE semantic_summary LIKE ?
                   OR tension_id LIKE 'TV4713%'
                """,
                (f"{PREFIX}%",),
            ).fetchall()
            ids = [str(row["tension_id"]) for row in rows]

        ids_with_prior = list(ids)
        ids_with_prior.append(PRIOR_TENSION_ID)
        routine_ids = [f"RR:{tid}" for tid in ids_with_prior]

        placeholders = ",".join("?" for _ in ids_with_prior)

        if placeholders:
            for table in (
                "tension_cycle_memory_reviews",
                "tension_cognitive_cycle_reports",
                "tension_hypothesis_lineage",
                "tension_prediction_influences",
                "tension_context_comparisons",
            ):
                if table_exists(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids_with_prior)

            for table in ("tension_outcomes", "tension_probes", "tension_events"):
                if table_exists(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids_with_prior)

            if table_exists(conn, "tension_cases"):
                conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids_with_prior)

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

    print("Registros v47.13 artificiais removidos, se existiam.")
    if ids:
        for tid in ids:
            print(f"- {tid}")
    print(f"- {PRIOR_TENSION_ID}")


def seed_prior_cycle_report() -> None:
    with connect() as conn:
        ensure_cycle_report_table(conn)
        conn.execute(
            "DELETE FROM tension_cognitive_cycle_reports WHERE tension_id=?",
            (PRIOR_TENSION_ID,),
        )

        payload = {
            "report_id": PRIOR_REPORT_ID,
            "tension_id": PRIOR_TENSION_ID,
            "source_pair": "yellow_triangle>blue_cube",
            "status_after": "closed",
            "outcome_after": "closed",
            "comparison_id": "CTX:PRIOR_V4713_001:0",
            "influence_id": "INF:PRIOR_V4713_001:0",
            "lineage_id": "LIN:PRIOR_V4713_001:H000:1",
            "hypothesis_id": "H000",
            "bias_label": "bias_toward_stable_probe",
            "confidence": 0.71,
            "closure_assessment": "cycle_resolved_by_status:closed",
            "validation_result": "Validou H000: previsão confirmada. Previsto=stable, observado=stable.",
            "narrative": "ciclo anterior artificial v47.13: yellow_triangle>blue_cube fechou como stable",
            "effect": "seed_prior_cycle_for_review_test",
        }

        conn.execute(
            """
            INSERT INTO tension_cognitive_cycle_reports (
                report_id, tension_id, source_pair, timestamp, step,
                status_after, outcome_after, comparison_id, influence_id, lineage_id,
                hypothesis_id, validation_result, closure_assessment, narrative, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                PRIOR_REPORT_ID,
                PRIOR_TENSION_ID,
                "yellow_triangle>blue_cube",
                now_iso(),
                0,
                "closed",
                "closed",
                "CTX:PRIOR_V4713_001:0",
                "INF:PRIOR_V4713_001:0",
                "LIN:PRIOR_V4713_001:H000:1",
                "H000",
                "Validou H000: previsão confirmada. Previsto=stable, observado=stable.",
                "cycle_resolved_by_status:closed",
                "ciclo anterior artificial v47.13: yellow_triangle>blue_cube fechou como stable",
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()

    print(f"[OK] Ciclo passado artificial semeado: {PRIOR_REPORT_ID}")


def create_open_tensions() -> list[str]:
    from darwin_home import DarwinHome
    from darwin_v61_nursery_v47 import DarwinNurseryAgent

    home = DarwinHome("darwin_home")
    home.bootstrap()
    try:
        agent = DarwinNurseryAgent(home)
        if hasattr(agent, "live_tension_counter_v46"):
            agent.live_tension_counter_v46 = COUNTER_START

        agent.step_counter = 111
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_13_review_test",
            ],
            semantic_summary=f"{PREFIX} tensão A para testar revisão de ciclo passado.",
            inherited_pairs=[
                "blue_cube>red_ball",
                "yellow_triangle>red_ball",
                "green_cylinder>yellow_triangle",
            ],
            magnitude=1.22,
        )

        agent.step_counter = 112
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_13_review_test",
            ],
            semantic_summary=f"{PREFIX} tensão B parecida com ciclo passado.",
            inherited_pairs=[
                "blue_cube>yellow_triangle",
                "green_cylinder>blue_cube",
            ],
            magnitude=1.31,
        )

        agent.step_counter = 113
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


def latest_review_best_report(tension_id: str) -> str:
    with connect() as conn:
        if not table_exists(conn, "tension_cycle_memory_reviews"):
            return ""
        row = conn.execute(
            """
            SELECT best_report_id
            FROM tension_cycle_memory_reviews
            WHERE tension_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (tension_id,),
        ).fetchone()
        return str(row["best_report_id"]) if row else ""


def routine_step_count() -> int:
    with connect() as conn:
        if not table_exists(conn, "tension_resolution_steps"):
            return 0
        row = conn.execute("SELECT COUNT(*) AS n FROM tension_resolution_steps").fetchone()
        return int(row["n"]) if row else 0


def run_review_check() -> bool:
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
        print(agent.cycle_memory_review_summary())

        ok_review_reason = "revisão de ciclo v47.13" in plan1.explanation
        ok_bucket = getattr(plan1, "curriculum_bucket", "") == "routine_reviewed_compare_influenced_predict"

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

        review_count = count_for("tension_cycle_memory_reviews", active_id)
        comparison_count = count_for("tension_context_comparisons", active_id)
        influence_count = count_for("tension_prediction_influences", active_id)
        lineage_count = count_for("tension_hypothesis_lineage", active_id)
        report_count = count_for("tension_cognitive_cycle_reports", active_id)
        best_report = latest_review_best_report(active_id)

        ok_review = review_count >= 1 and best_report == PRIOR_REPORT_ID
        ok_compare = comparison_count >= 1
        ok_influence = influence_count >= 1
        ok_lineage = lineage_count >= 1
        ok_report = report_count >= 1
        ok_plan1 = (
            plan1.action_name == "predict"
            and getattr(plan1, "lesson_phase", "") == "executive_resolution_routine"
            and ok_bucket
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
        print(f"- revisão persistida: {ok_review} ({review_count})")
        print(f"- melhor relatório recuperado: {best_report}")
        print(f"- motivo inclui revisão: {ok_review_reason}")
        print(f"- bucket reviewed_compare: {ok_bucket}")
        print(f"- comparação persistida: {ok_compare} ({comparison_count})")
        print(f"- influência persistida: {ok_influence} ({influence_count})")
        print(f"- linhagem persistida: {ok_lineage} ({lineage_count})")
        print(f"- relatório consolidado novo: {ok_report} ({report_count})")
        print(f"- plano 1 OK: {ok_plan1}")
        print(f"- plano 2 OK: {ok_plan2}")
        print(f"- steps >= 2: {ok_steps}")

        ok = (
            ok_policy and ok_review and ok_review_reason and ok_bucket and
            ok_compare and ok_influence and ok_lineage and ok_report and
            ok_plan1 and ok_plan2 and ok_steps
        )
        print(f"- resultado: {'OK' if ok else 'FALHOU'}")
        return ok

    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.13 — TESTE DE REVISÃO DE CICLOS PASSADOS")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Semear um relatório consolidado passado artificial.")
        print("3. Criar 2 tensões abertas marcadas como [REVIEW_TEST_V47_13].")
        print("4. Confirmar que Darwin revisa o ciclo passado antes do compare_context.")
        print("5. Confirmar bucket routine_reviewed_compare_influenced_predict.")
        print("6. Executar predict e validate com segurança.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_13_cycle_memory_review_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")
    seed_prior_cycle_report()
    create_open_tensions()
    print_counts("Contagens após seed e criação das tensões:")

    ok = run_review_check()

    print_counts("Contagens depois:")

    print()
    print(f"Resultado final: {'OK' if ok else 'FALHOU'}")
    print()
    print("Para inspecionar manualmente:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10y")
    print("  10z")
    print("  10h")
    print()
    print("Para limpar:")
    print("  py darwin_v47_13_cycle_memory_review_test.py --purge-review-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de revisão de ciclos passados v47.13.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-review-tests", action="store_true", help="Remove registros artificiais [REVIEW_TEST_V47_13].")
    args = parser.parse_args()

    if args.purge_review_tests:
        print("=" * 72)
        print("DARWIN v47.13 — PURGE DE REVISÃO DE CICLOS")
        print("=" * 72)
        backup = backup_db("v47_13_cycle_memory_review_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_review_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
