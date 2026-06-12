from __future__ import annotations

"""
DARWIN v48.1 — Diagnóstico de Rotação Ativa ao Vivo

Lê a tabela:
    geometry_live_actions_v48_1

e verifica formalmente se o visualizador ao vivo registrou o ciclo esperado:

    choose
    rotate_start
    rotate_success
    insert_success

Especialmente para:
    piece_square_rotated -> hole_square

Uso:
    py darwin_check_v48_1_live_rotation.py
    py darwin_check_v48_1_live_rotation.py --details
    py darwin_check_v48_1_live_rotation.py --recent 100
    py darwin_check_v48_1_live_rotation.py --export-json

Critério de aprovação:
- A tabela geometry_live_actions_v48_1 existe.
- Há pelo menos 1 rotate_start.
- Há pelo menos 1 rotate_success.
- Há insert_success para hole_square, hole_triangle e hole_circle.
- Há registro de piece_square_rotated -> hole_square com rotation_mismatch antes da rotação.
- Há registro posterior de rotate_success para piece_square_rotated -> hole_square.
- Há registro posterior de insert_success para piece_square_rotated -> hole_square.

Observação:
Este diagnóstico confirma autonomia local no micromundo geométrico.
Não afirma consciência, senciência ou autonomia geral.
"""

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_1"
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


def parse_payload(text: str) -> dict[str, Any]:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def fetch_rows(conn: sqlite3.Connection, recent: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT id, timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json
        FROM {TABLE}
        ORDER BY id DESC
        LIMIT ?
        """,
        (recent,),
    ).fetchall()

    items = []
    for row in reversed(rows):
        payload = parse_payload(row["payload_json"])
        item = {key: row[key] for key in row.keys()}
        item["payload"] = payload
        items.append(item)
    return items


def find_indices(rows: list[dict[str, Any]], *, action_kind: str | None = None,
                 piece_id: str | None = None, hole_id: str | None = None,
                 failure_reason: str | None = None) -> list[int]:
    out = []
    for i, row in enumerate(rows):
        if action_kind is not None and row.get("action_kind") != action_kind:
            continue
        if piece_id is not None and row.get("piece_id") != piece_id:
            continue
        if hole_id is not None and row.get("hole_id") != hole_id:
            continue
        if failure_reason is not None:
            payload_reason = str(row.get("payload", {}).get("failure_reason", "") or "")
            if payload_reason != failure_reason:
                continue
        out.append(i)
    return out


def first_after(indices: list[int], after: int) -> int | None:
    for idx in indices:
        if idx > after:
            return idx
    return None


def diagnose(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row.get("action_kind", "")) for row in rows)

    choose_rotation = find_indices(
        rows,
        action_kind="choose",
        piece_id="piece_square_rotated",
        hole_id="hole_square",
        failure_reason="rotation_mismatch",
    )

    # Algumas versões podem registrar escolha exploratória ou avaliação principal com outro action_kind.
    if not choose_rotation:
        choose_rotation = find_indices(
            rows,
            piece_id="piece_square_rotated",
            hole_id="hole_square",
            failure_reason="rotation_mismatch",
        )

    rotate_start = find_indices(
        rows,
        action_kind="rotate_start",
        piece_id="piece_square_rotated",
        hole_id="hole_square",
    )
    rotate_success = find_indices(
        rows,
        action_kind="rotate_success",
        piece_id="piece_square_rotated",
        hole_id="hole_square",
    )
    square_insert_success = find_indices(
        rows,
        action_kind="insert_success",
        piece_id="piece_square_rotated",
        hole_id="hole_square",
    )

    triangle_insert_success = find_indices(
        rows,
        action_kind="insert_success",
        piece_id="piece_triangle",
        hole_id="hole_triangle",
    )
    circle_insert_success = find_indices(
        rows,
        action_kind="insert_success",
        piece_id="piece_circle",
        hole_id="hole_circle",
    )

    ordered_rotation_cycle = False
    order_trace = []

    if choose_rotation:
        a = choose_rotation[0]
        b = first_after(rotate_start, a)
        c = first_after(rotate_success, b if b is not None else a)
        d = first_after(square_insert_success, c if c is not None else (b if b is not None else a))
        ordered_rotation_cycle = b is not None and c is not None and d is not None
        order_trace = [a, b, c, d]

    checks = {
        "table_has_rows": len(rows) > 0,
        "has_choose_rotation_mismatch": bool(choose_rotation),
        "has_rotate_start": bool(rotate_start),
        "has_rotate_success": bool(rotate_success),
        "has_square_insert_success_after_rotation": bool(square_insert_success),
        "has_triangle_insert_success": bool(triangle_insert_success),
        "has_circle_insert_success": bool(circle_insert_success),
        "ordered_rotation_cycle": ordered_rotation_cycle,
    }

    ok = all(checks.values())

    return {
        "ok": ok,
        "rows_analyzed": len(rows),
        "counts": dict(counts),
        "checks": checks,
        "indices": {
            "choose_rotation_mismatch": choose_rotation,
            "rotate_start": rotate_start,
            "rotate_success": rotate_success,
            "square_insert_success": square_insert_success,
            "triangle_insert_success": triangle_insert_success,
            "circle_insert_success": circle_insert_success,
            "ordered_trace": order_trace,
        },
    }


def row_summary(row: dict[str, Any]) -> str:
    reason = str(row.get("payload", {}).get("failure_reason", "") or "")
    score = float(row.get("score", 0.0) or 0.0)
    return (
        f"#{row['id']} | {row['timestamp']} | {row['action_kind']} | "
        f"{row['piece_id']} -> {row['hole_id']} | score={score:.3f} | "
        f"outcome={row['outcome']} | reason={reason or '-'} | note={row['note']}"
    )


def export_json(report: dict[str, Any], rows: list[dict[str, Any]]) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPORT_DIR / f"darwin_v48_1_live_rotation_diagnostic_{now_stamp()}.json"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db_path": str(DB_PATH),
        "table": TABLE,
        "diagnostic": report,
        "rows": rows,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico v48.1 de rotação ativa ao vivo.")
    parser.add_argument("--details", action="store_true", help="Mostra eventos recentes detalhados.")
    parser.add_argument("--recent", type=int, default=200, help="Quantidade de eventos recentes a analisar.")
    parser.add_argument("--export-json", action="store_true", help="Exporta relatório JSON em darwin_home/exports.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v48.1 — DIAGNÓSTICO DE ROTAÇÃO ATIVA AO VIVO")
    print("=" * 72)
    print(f"Banco:  {DB_PATH}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos")
    print()

    with connect() as conn:
        if not table_exists(conn, TABLE):
            print("[ERRO] tabela geometry_live_actions_v48_1 não existe.")
            print("Rode primeiro:")
            print("  py darwin_shape_sorter_live_v48_1_active_rotation.py")
            return 2

        total = conn.execute(f"SELECT COUNT(*) AS n FROM {TABLE}").fetchone()["n"]
        rows = fetch_rows(conn, args.recent)

    report = diagnose(rows)

    print("Resumo de eventos:")
    print(f"- total no banco: {total}")
    print(f"- analisados:     {report['rows_analyzed']}")
    for action_kind, count in sorted(report["counts"].items()):
        print(f"- {action_kind}: {count}")

    print()
    print("Verificações:")
    labels = {
        "table_has_rows": "há eventos registrados",
        "has_choose_rotation_mismatch": "detectou rotation_mismatch no quadrado rotacionado",
        "has_rotate_start": "iniciou rotação ativa",
        "has_rotate_success": "rotação resolveu o problema",
        "has_square_insert_success_after_rotation": "quadrado rotacionado foi encaixado depois",
        "has_triangle_insert_success": "triângulo foi encaixado",
        "has_circle_insert_success": "círculo foi encaixado",
        "ordered_rotation_cycle": "ordem correta: detectar → girar → resolver → encaixar",
    }
    for key, passed in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if passed else 'FALHOU'}")

    print()
    if report["ok"]:
        print("Resultado final: OK")
        print("Leitura: Darwin executou correção espacial ativa no micromundo v48.1.")
    else:
        print("Resultado final: FALHOU")
        print("Leitura: ainda falta evidência completa de rotação ativa registrada no banco.")

    if args.details:
        print()
        print("Eventos recentes:")
        for row in rows[-60:]:
            print("  " + row_summary(row))

        print()
        print("Traço ordenado da rotação:")
        trace = report["indices"].get("ordered_trace", [])
        for idx in trace:
            if idx is None:
                print("  - AUSENTE")
            elif 0 <= idx < len(rows):
                print("  " + row_summary(rows[idx]))

    if args.export_json:
        out = export_json(report, rows)
        print()
        print(f"JSON exportado: {out}")

    print()
    print("Próximo passo se OK:")
    print("  congelar v48.1 stable")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
