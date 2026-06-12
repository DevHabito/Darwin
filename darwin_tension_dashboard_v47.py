from __future__ import annotations

"""
DARWIN v47.3 — Painel Executivo de Tensões

Objetivo:
- Ler a memória executiva persistente do Darwin.
- Mostrar tensões abertas, fechadas, arquivadas e eventos recentes.
- Não alterar nada no banco.
- Servir como "prontuário executivo" da v47.

Uso:
    py darwin_tension_dashboard_v47.py

Opções:
    py darwin_tension_dashboard_v47.py --all
    py darwin_tension_dashboard_v47.py --events 20
    py darwin_tension_dashboard_v47.py --case TV47202
    py darwin_tension_dashboard_v47.py --export
"""

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("darwin_home") / "darwin.db"
EXPORT_DIR = Path("darwin_home") / "exports"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


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


def count_where(conn: sqlite3.Connection, table: str, where: str = "1=1", params: tuple[Any, ...] = ()) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params).fetchone()
    return int(row["n"]) if row else 0


def fmt_float(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{ndigits}f}"
    except Exception:
        return str(value)


def short(text: Any, limit: int = 90) -> str:
    s = "" if text is None else str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def safe_json(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(str(value))
    except Exception:
        return value


def print_header(title: str) -> None:
    print()
    print(title)
    print("-" * 72)


def show_counts(conn: sqlite3.Connection) -> None:
    print_header("Resumo persistente")
    if not table_exists(conn, "tension_cases"):
        print("Tabela tension_cases ausente. Rode a preparação v47 primeiro.")
        return

    total = count_where(conn, "tension_cases")
    open_count = count_where(conn, "tension_cases", "status NOT IN ('closed', 'archived', 'stale')")
    closed_count = count_where(conn, "tension_cases", "status='closed'")
    archived_count = count_where(conn, "tension_cases", "status='archived'")
    stale_count = count_where(conn, "tension_cases", "status='stale'")
    events = count_where(conn, "tension_events")
    probes = count_where(conn, "tension_probes")
    outcomes = count_where(conn, "tension_outcomes")

    print(f"- casos totais:       {total}")
    print(f"- casos abertos:      {open_count}")
    print(f"- casos fechados:     {closed_count}")
    print(f"- casos arquivados:   {archived_count}")
    print(f"- casos obsoletos:    {stale_count}")
    print(f"- eventos:            {events}")
    print(f"- sondas:             {probes}")
    print(f"- desfechos:          {outcomes}")


def show_open_cases(conn: sqlite3.Connection, include_all: bool = False) -> None:
    if not table_exists(conn, "tension_cases"):
        return

    print_header("Casos executivos de tensão")

    where = "1=1" if include_all else "status NOT IN ('closed', 'archived', 'stale')"
    rows = conn.execute(
        f"""
        SELECT tension_id, source_pair, status, outcome,
               live_pressure, recency_score, continuity_score,
               ambiguity_score, closure_deficit, saturation_cost,
               economic_priority, updated_at, semantic_summary
        FROM tension_cases
        WHERE {where}
        ORDER BY
            CASE WHEN status IN ('open', 'probing', 'reopened') THEN 0 ELSE 1 END,
            economic_priority DESC,
            live_pressure DESC,
            updated_at DESC
        LIMIT 25
        """
    ).fetchall()

    if not rows:
        print("(nenhum caso para mostrar)")
        return

    for row in rows:
        print(
            f"- {row['tension_id']} | {row['source_pair']} | "
            f"status={row['status']} | outcome={row['outcome']} | "
            f"pressão={fmt_float(row['live_pressure'])} | "
            f"prioridade={fmt_float(row['economic_priority'])} | "
            f"déficit={fmt_float(row['closure_deficit'])} | "
            f"sat={fmt_float(row['saturation_cost'])}"
        )
        print(f"  atualizado={row['updated_at']}")
        if row["semantic_summary"]:
            print(f"  resumo={short(row['semantic_summary'], 140)}")


def show_recent_events(conn: sqlite3.Connection, limit: int = 12) -> None:
    if not table_exists(conn, "tension_events"):
        return

    print_header(f"Últimos {limit} eventos executivos")

    rows = conn.execute(
        """
        SELECT tension_id, timestamp, event_type, status_after,
               pressure_after, note
        FROM tension_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if not rows:
        print("(nenhum evento)")
        return

    for row in rows:
        print(
            f"- {row['timestamp']} | {row['tension_id']} | "
            f"{row['event_type']} | status={row['status_after']} | "
            f"pressão={fmt_float(row['pressure_after'])}"
        )
        if row["note"]:
            print(f"  nota={short(row['note'], 140)}")


def show_case(conn: sqlite3.Connection, tension_id: str) -> None:
    if not table_exists(conn, "tension_cases"):
        return

    row = conn.execute(
        "SELECT * FROM tension_cases WHERE tension_id=?",
        (tension_id,),
    ).fetchone()

    print_header(f"Prontuário da tensão {tension_id}")

    if row is None:
        print("Caso não encontrado.")
        return

    print(f"origem:            {row['source_pair']}")
    print(f"previsto/observado:{row['source_predicted']} -> {row['source_observed']}")
    print(f"status/outcome:    {row['status']} / {row['outcome']}")
    print(f"pressão:           {fmt_float(row['live_pressure'])}")
    print(f"prioridade:        {fmt_float(row['economic_priority'])}")
    print(f"recência:          {fmt_float(row['recency_score'])}")
    print(f"continuidade:      {fmt_float(row['continuity_score'])}")
    print(f"ambiguidade:       {fmt_float(row['ambiguity_score'])}")
    print(f"déficit fechamento:{fmt_float(row['closure_deficit'])}")
    print(f"saturação:         {fmt_float(row['saturation_cost'])}")
    print(f"aberto no passo:   {row['opened_step']}")
    print(f"último evento:     {row['last_event_step']}")
    print(f"atualizado:        {row['updated_at']}")
    print(f"resumo:            {row['semantic_summary']}")

    for field in ("source_labels_json", "inherited_pairs_json", "continuity_lines_json", "outcome_lines_json", "trail_json"):
        value = safe_json(row[field])
        print()
        print(f"{field}:")
        if isinstance(value, list):
            if not value:
                print("  []")
            for item in value[:12]:
                print(f"  - {item}")
        else:
            print(f"  {value}")

    if table_exists(conn, "tension_events"):
        print_header(f"Eventos de {tension_id}")
        rows = conn.execute(
            """
            SELECT timestamp, event_type, status_after, pressure_after, note
            FROM tension_events
            WHERE tension_id=?
            ORDER BY id ASC
            """,
            (tension_id,),
        ).fetchall()
        if not rows:
            print("(sem eventos)")
        for ev in rows:
            print(
                f"- {ev['timestamp']} | {ev['event_type']} | "
                f"status={ev['status_after']} | pressão={fmt_float(ev['pressure_after'])}"
            )
            if ev["note"]:
                print(f"  nota={ev['note']}")

    if table_exists(conn, "tension_probes"):
        print_header(f"Sondas de {tension_id}")
        rows = conn.execute(
            """
            SELECT selected_at, pair_key, score, judgment, observed, outcome
            FROM tension_probes
            WHERE tension_id=?
            ORDER BY id ASC
            """,
            (tension_id,),
        ).fetchall()
        if not rows:
            print("(sem sondas)")
        for probe in rows:
            print(
                f"- {probe['selected_at']} | {probe['pair_key']} | "
                f"score={fmt_float(probe['score'])} | observed={probe['observed']} | outcome={probe['outcome']}"
            )
            if probe["judgment"]:
                print(f"  juízo={probe['judgment']}")

    if table_exists(conn, "tension_outcomes"):
        print_header(f"Desfechos de {tension_id}")
        rows = conn.execute(
            """
            SELECT timestamp, outcome, observed, closure_deficit_after, outcome_lines_json
            FROM tension_outcomes
            WHERE tension_id=?
            ORDER BY id ASC
            """,
            (tension_id,),
        ).fetchall()
        if not rows:
            print("(sem desfechos)")
        for out in rows:
            print(
                f"- {out['timestamp']} | outcome={out['outcome']} | "
                f"observed={out['observed']} | déficit={fmt_float(out['closure_deficit_after'])}"
            )
            lines = safe_json(out["outcome_lines_json"])
            if isinstance(lines, list):
                for line in lines[:6]:
                    print(f"  {line}")


def export_csv(conn: sqlite3.Connection) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPORT_DIR / f"darwin_v47_tension_dashboard_{now_stamp()}.csv"

    if not table_exists(conn, "tension_cases"):
        raise RuntimeError("Tabela tension_cases ausente.")

    rows = conn.execute(
        """
        SELECT tension_id, source_pair, source_predicted, source_observed,
               status, outcome, live_pressure, recency_score, continuity_score,
               ambiguity_score, closure_deficit, saturation_cost,
               economic_priority, opened_step, last_event_step,
               updated_at, semantic_summary
        FROM tension_cases
        ORDER BY updated_at DESC
        """
    ).fetchall()

    fields = [
        "tension_id",
        "source_pair",
        "source_predicted",
        "source_observed",
        "status",
        "outcome",
        "live_pressure",
        "recency_score",
        "continuity_score",
        "ambiguity_score",
        "closure_deficit",
        "saturation_cost",
        "economic_priority",
        "opened_step",
        "last_event_step",
        "updated_at",
        "semantic_summary",
    ]

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Painel executivo de tensões persistentes Darwin v47.")
    parser.add_argument("--all", action="store_true", help="Mostra também casos fechados/arquivados.")
    parser.add_argument("--events", type=int, default=12, help="Número de eventos recentes a mostrar.")
    parser.add_argument("--case", type=str, default="", help="Mostra prontuário completo de uma tensão específica.")
    parser.add_argument("--export", action="store_true", help="Exporta tension_cases para CSV.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v47.3 — PAINEL EXECUTIVO DE TENSÕES")
    print("=" * 72)
    print(f"Banco: {DB_PATH}")

    with connect() as conn:
        show_counts(conn)

        if args.case:
            show_case(conn, args.case.strip())
        else:
            show_open_cases(conn, include_all=args.all)
            show_recent_events(conn, limit=max(1, args.events))

        if args.export:
            path = export_csv(conn)
            print()
            print(f"CSV exportado: {path}")

    print()
    print("Painel concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
