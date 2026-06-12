from __future__ import annotations

"""
DARWIN v47 — Diagnóstico da Memória Executiva de Tensões

Este script verifica se a infraestrutura da v47 está viva no banco.

Ele NÃO altera nada.
Ele apenas lê:
- tension_cases
- tension_events
- tension_probes
- tension_outcomes
- darwin_schema_migrations
- últimos episódios
- estado atual

Uso:
    py darwin_check_v47_tensions.py

Uso detalhado:
    py darwin_check_v47_tensions.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("darwin_home") / "darwin.db"


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


def count_table(conn: sqlite3.Connection, table: str) -> int | None:
    if not table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])


def print_count(conn: sqlite3.Connection, table: str) -> None:
    n = count_table(conn, table)
    if n is None:
        print(f"- {table}: AUSENTE")
    else:
        print(f"- {table}: {n}")


def safe_json_preview(value: Any, max_len: int = 220) -> str:
    text = "" if value is None else str(value)
    try:
        parsed = json.loads(text)
        text = json.dumps(parsed, ensure_ascii=False)
    except Exception:
        pass
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def show_recent_rows(conn: sqlite3.Connection, table: str, columns: list[str], order_by: str, limit: int = 5) -> None:
    if not table_exists(conn, table):
        return

    n = count_table(conn, table) or 0
    if n <= 0:
        return

    print()
    print(f"Últimos registros em {table}:")
    col_expr = ", ".join(columns)
    rows = conn.execute(
        f"SELECT {col_expr} FROM {table} ORDER BY {order_by} DESC LIMIT ?",
        (limit,),
    ).fetchall()

    for row in rows:
        parts = []
        for col in columns:
            parts.append(f"{col}={safe_json_preview(row[col])}")
        print("  - " + " | ".join(parts))


def show_current_state(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "current_state"):
        return
    row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
    if row is None:
        return

    print()
    print("Estado atual:")
    for key in ("sigma", "energy", "info_self", "info_external", "latency", "pain_signal", "wellbeing_signal"):
        if key in row.keys():
            try:
                print(f"- {key}: {float(row[key]):.4f}")
            except Exception:
                print(f"- {key}: {row[key]}")


def show_latest_episodes(conn: sqlite3.Connection, limit: int = 5) -> None:
    if not table_exists(conn, "episodes"):
        return
    print()
    print(f"Últimos {limit} episódios:")
    rows = conn.execute(
        """
        SELECT timestamp, module, context, action_taken, outcome
        FROM episodes
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    for row in rows:
        outcome = str(row["outcome"] or "")
        if len(outcome) > 140:
            outcome = outcome[:139] + "…"
        print(f"  - {row['timestamp']} | {row['module']} | {row['action_taken']} | {outcome}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico da memória executiva de tensões v47.")
    parser.add_argument("--details", action="store_true", help="Mostra linhas recentes das tabelas v47.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47 — DIAGNÓSTICO DE TENSÕES")
    print("=" * 72)
    print(f"Banco: {DB_PATH}")
    print()

    with connect() as conn:
        print("Tabelas principais:")
        for table in (
            "tension_cases",
            "tension_events",
            "tension_probes",
            "tension_outcomes",
            "darwin_schema_migrations",
        ):
            print_count(conn, table)

        show_current_state(conn)
        show_latest_episodes(conn)

        if args.details:
            show_recent_rows(
                conn,
                "darwin_schema_migrations",
                ["name", "applied_at", "details_json"],
                "applied_at",
            )
            show_recent_rows(
                conn,
                "tension_cases",
                ["tension_id", "source_pair", "status", "outcome", "live_pressure", "updated_at"],
                "updated_at",
            )
            show_recent_rows(
                conn,
                "tension_events",
                ["tension_id", "timestamp", "event_type", "status_after", "note"],
                "id",
            )
            show_recent_rows(
                conn,
                "tension_probes",
                ["tension_id", "selected_at", "pair_key", "score", "judgment"],
                "id",
            )
            show_recent_rows(
                conn,
                "tension_outcomes",
                ["tension_id", "timestamp", "outcome", "observed", "closure_deficit_after"],
                "id",
            )

        tension_cases = count_table(conn, "tension_cases") or 0
        tension_events = count_table(conn, "tension_events") or 0

    print()
    if tension_cases == 0 and tension_events == 0:
        print("Leitura:")
        print("- A infraestrutura v47 existe, mas ainda não há tensão persistida.")
        print("- Isso é normal se a última execução não gerou contradição forte.")
        print("- Previsões 'uncertain' refinadas para stable não abrem tensão forte por padrão.")
    else:
        print("Leitura:")
        print("- A memória executiva de tensões já começou a registrar casos/eventos.")
        print("- Próximo passo: analisar se a preempção e o fechamento estão coerentes.")

    print()
    print("Diagnóstico concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
