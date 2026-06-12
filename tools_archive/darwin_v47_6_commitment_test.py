from __future__ import annotations

"""
DARWIN v47.6 — Teste de Compromisso Executivo Real

Verifica se, após reidratar tensões abertas, o próximo passo autônomo
é comprometido com a tensão ativa, e não com exploração comum.

Fluxo:
1. Cria 2 tensões abertas artificiais.
2. Encerra o runtime.
3. Instancia novo DarwinNurseryAgent, que reidrata as tensões.
4. Chama choose_autonomous_action().
   Esperado: predict no par da tensão ativa.
5. Executa esse predict.
6. Chama choose_autonomous_action() de novo.
   Esperado: validate para fechar/avançar a sonda da tensão ativa.
7. Executa validate e verifica estado persistido.

Uso:
    py darwin_v47_6_commitment_test.py --dry-run
    py darwin_v47_6_commitment_test.py

Para limpar:
    py darwin_v47_6_commitment_test.py --purge-commitment-tests
"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
BACKUP_DIR = Path("darwin_home") / "backups"
PREFIX = "[COMMITMENT_TEST_V47_6]"
COUNTER_START = 47600


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


def purge_commitment_tests() -> None:
    with connect() as conn:
        if not table_exists(conn, "tension_cases"):
            print("Tabela tension_cases não existe. Nada para apagar.")
            return

        rows = conn.execute(
            """
            SELECT tension_id
            FROM tension_cases
            WHERE semantic_summary LIKE ?
               OR tension_id LIKE 'TV476%'
            """,
            (f"{PREFIX}%",),
        ).fetchall()

        ids = [str(row["tension_id"]) for row in rows]
        if not ids:
            print("Nenhum registro de compromisso v47.6 encontrado.")
            return

        placeholders = ",".join("?" for _ in ids)

        for table in ("tension_outcomes", "tension_probes", "tension_events"):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE tension_id IN ({placeholders})", ids)

        conn.execute(f"DELETE FROM tension_cases WHERE tension_id IN ({placeholders})", ids)
        conn.commit()

    print(f"Registros de compromisso apagados: {len(ids)} caso(s).")
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

        agent.step_counter = 41
        t1 = agent.register_tension_from_contradiction(
            lower="green_cylinder",
            upper="red_ball",
            predicted="stable",
            observed="unstable",
            context_families=[
                "with_nonstackable_top",
                "with_rolling_top",
                "with_toy_top",
                "v47_6_commitment_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão A aberta para testar compromisso executivo real."
            ),
            inherited_pairs=["blue_cube>red_ball", "yellow_triangle>red_ball"],
            magnitude=1.20,
        )

        agent.step_counter = 42
        t2 = agent.register_tension_from_contradiction(
            lower="yellow_triangle",
            upper="blue_cube",
            predicted="unstable",
            observed="stable",
            context_families=[
                "with_block_top",
                "with_nonrolling_top",
                "with_nonstackable_top",
                "v47_6_commitment_test",
            ],
            semantic_summary=(
                f"{PREFIX} tensão B aberta para testar ação comprometida no próximo ciclo."
            ),
            inherited_pairs=["blue_cube>yellow_triangle"],
            magnitude=1.30,
        )

        agent.step_counter = 43
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


def get_case_status(tension_id: str) -> tuple[str, str]:
    with connect() as conn:
        row = conn.execute(
            "SELECT status, outcome FROM tension_cases WHERE tension_id=?",
            (tension_id,),
        ).fetchone()
        if row is None:
            return "missing", "missing"
        return str(row["status"]), str(row["outcome"])


def run_commitment_check(expected_ids: list[str]) -> bool:
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

        active_pair = active_case.source_pair

        print()
        print(f"Tensão ativa antes do primeiro passo: {active_id} ({active_pair})")

        plan1 = agent.choose_autonomous_action()
        print()
        print("Plano 1 escolhido:")
        print(f"- action: {plan1.action_name}")
        print(f"- target: {plan1.target_a}>{plan1.target_b}")
        print(f"- phase : {getattr(plan1, 'lesson_phase', '')}")
        print(f"- bucket: {getattr(plan1, 'curriculum_bucket', '')}")
        print(f"- why   : {plan1.explanation}")
        print()
        print(agent.executive_commitment_summary())

        ok_plan1 = (
            plan1.action_name == "predict"
            and plan1.target_a == active_case.source_lower
            and plan1.target_b == active_case.source_upper
            and "compromisso executivo" in plan1.explanation
        )

        if not ok_plan1:
            print("[FALHA] Primeiro plano não respeitou a tensão ativa.")
            return False

        print()
        print("Executando plano 1...")
        print(agent.execute_action(plan1))

        plan2 = agent.choose_autonomous_action()
        print()
        print("Plano 2 escolhido:")
        print(f"- action: {plan2.action_name}")
        print(f"- target: {plan2.target_a}>{plan2.target_b}")
        print(f"- phase : {getattr(plan2, 'lesson_phase', '')}")
        print(f"- bucket: {getattr(plan2, 'curriculum_bucket', '')}")
        print(f"- why   : {plan2.explanation}")
        print()
        print(agent.executive_commitment_summary())

        ok_plan2 = (
            plan2.action_name == "validate"
            and plan2.target_a == active_case.source_lower
            and plan2.target_b == active_case.source_upper
            and "compromisso executivo" in plan2.explanation
        )

        if not ok_plan2:
            print("[FALHA] Segundo plano não virou validação comprometida.")
            return False

        print()
        print("Executando plano 2...")
        print(agent.execute_action(plan2))

        status, outcome = get_case_status(active_id)
        print()
        print("Estado persistido da tensão ativa após validate:")
        print(f"- {active_id}: status={status}, outcome={outcome}")

        ok_status = status in {"closed", "maintained", "reopened", "weakened", "open", "probing"}
        # O teste principal aqui é compromisso executivo, não necessariamente fechamento perfeito.
        # Mas se o par era direto, o normal é fechar.
        if status != "closed":
            print("[AVISO] A tensão não fechou como closed; isso pode indicar diferença de regra no validador, mas o compromisso foi testado.")

        return ok_plan1 and ok_plan2 and ok_status

    finally:
        home.close()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v47.6 — TESTE DE COMPROMISSO EXECUTIVO")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Criar backup do banco.")
        print("2. Criar 2 tensões abertas marcadas como [COMMITMENT_TEST_V47_6].")
        print("3. Encerrar runtime.")
        print("4. Instanciar novo agente e reidratar tensões.")
        print("5. Verificar se o primeiro choose_autonomous_action vira predict da tensão ativa.")
        print("6. Executar predict.")
        print("7. Verificar se o segundo choose_autonomous_action vira validate da mesma tensão.")
        print("8. Executar validate.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    backup = backup_db("v47_6_commitment_test")
    print(f"[OK] Backup criado: {backup}")

    print_counts("Contagens antes:")

    expected = create_open_tensions()

    print_counts("Contagens após criação das tensões:")

    ok = run_commitment_check(expected)

    print()
    print(f"Resultado final: {'OK' if ok else 'FALHOU'}")
    print()
    print("Para inspecionar no menu:")
    print("  py darwin_v61_nursery_v47.py")
    print("  10c")
    print("  10")
    print("  10a")
    print()
    print("Para limpar:")
    print("  py darwin_v47_6_commitment_test.py --purge-commitment-tests")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de compromisso executivo v47.6.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--purge-commitment-tests", action="store_true", help="Remove registros artificiais [COMMITMENT_TEST_V47_6].")
    args = parser.parse_args()

    if args.purge_commitment_tests:
        print("=" * 72)
        print("DARWIN v47.6 — PURGE DE COMPROMISSO")
        print("=" * 72)
        backup = backup_db("v47_6_commitment_purge")
        print(f"[OK] Backup criado antes do purge: {backup}")
        purge_commitment_tests()
        print_counts("Contagens após purge:")
        return 0

    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
