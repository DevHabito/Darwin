from __future__ import annotations

"""
DARWIN v48.0 — Teste do Shape Sorter Nursery

Verifica:
1. Criação das tabelas v48.
2. Reset limpo do mundo geométrico.
3. Lição básica do brinquedo de encaixe.
4. Acertos esperados:
   - square -> square
   - circle -> circle
   - triangle -> triangle
5. Rejeições esperadas:
   - square -> circle / triangle
   - circle -> square / triangle
   - triangle -> square / circle
6. Inferência de regras físicas simples.

Uso:
    py darwin_shape_sorter_v48_test.py --dry-run
    py darwin_shape_sorter_v48_test.py
"""

import argparse
import sqlite3
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco não encontrado: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None:
        return -1
    count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(count["n"]) if count else 0


def latest_attempt(conn: sqlite3.Connection, piece_id: str, hole_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM geometry_fit_attempts_v48
        WHERE piece_id=? AND hole_id=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (piece_id, hole_id),
    ).fetchone()


def run_test(dry_run: bool) -> int:
    print("=" * 72)
    print("DARWIN v48.0 — TESTE SHAPE SORTER")
    print("=" * 72)
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {dry_run}")
    print()

    if dry_run:
        print("Este teste irá:")
        print("1. Importar darwin_shape_sorter_nursery_v48.py.")
        print("2. Resetar as tabelas geométricas v48.")
        print("3. Executar a lição básica.")
        print("4. Confirmar encaixes e rejeições esperadas.")
        print("5. Confirmar regras inferidas.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    from darwin_shape_sorter_nursery_v48 import ShapeSorterNurseryV48

    nursery = ShapeSorterNurseryV48()
    try:
        nursery.reset_v48()
        results = nursery.run_basic_lesson()
        print(nursery.lesson_report(results))
    finally:
        nursery.close()

    expected = {
        ("piece_square_small_v48", "hole_square_v48"): True,
        ("piece_circle_small_v48", "hole_circle_v48"): True,
        ("piece_triangle_small_v48", "hole_triangle_v48"): True,
        ("piece_square_small_v48", "hole_circle_v48"): False,
        ("piece_square_small_v48", "hole_triangle_v48"): False,
        ("piece_circle_small_v48", "hole_square_v48"): False,
        ("piece_circle_small_v48", "hole_triangle_v48"): False,
        ("piece_triangle_small_v48", "hole_square_v48"): False,
        ("piece_triangle_small_v48", "hole_circle_v48"): False,
    }

    with connect() as conn:
        checks = []
        for pair, expected_fit in expected.items():
            piece_id, hole_id = pair
            row = latest_attempt(conn, piece_id, hole_id)
            ok = row is not None and bool(row["observed_fit"]) == expected_fit
            checks.append(ok)
            print(
                f"- {piece_id} -> {hole_id}: "
                f"esperado={'FIT' if expected_fit else 'NO_FIT'} | "
                f"observado={('FIT' if row and row['observed_fit'] else 'NO_FIT') if row else 'AUSENTE'} | "
                f"{'OK' if ok else 'FALHOU'}"
            )

        rules_count = table_count(conn, "geometry_rules_v48")
        attempts_count = table_count(conn, "geometry_fit_attempts_v48")
        concepts_count = table_count(conn, "geometry_spatial_concepts_v48")

    ok_pairs = all(checks)
    ok_rules = rules_count >= 3
    ok_attempts = attempts_count >= 9
    ok_concepts = concepts_count >= 5
    ok = ok_pairs and ok_rules and ok_attempts and ok_concepts

    print()
    print("Verificação:")
    print(f"- pares básicos OK: {ok_pairs}")
    print(f"- tentativas >= 9: {ok_attempts} ({attempts_count})")
    print(f"- regras >= 3: {ok_rules} ({rules_count})")
    print(f"- conceitos >= 5: {ok_concepts} ({concepts_count})")
    print(f"- resultado: {'OK' if ok else 'FALHOU'}")

    print()
    print("Para inspecionar:")
    print("  py darwin_shape_sorter_nursery_v48.py --dashboard")
    print("  py darwin_shape_sorter_nursery_v48.py --lesson all")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste do Darwin Shape Sorter v48.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    args = parser.parse_args()
    return run_test(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
