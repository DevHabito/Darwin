from __future__ import annotations

"""
DARWIN v48.2 — Diagnóstico de Erro Exploratório Controlado

Lê:
    geometry_live_actions_v48_2

Verifica:
- houve escolha de hipótese fraca: controlled_explore_choose
- houve teste seguro: controlled_collision_start
- houve colisão controlada: controlled_collision
- houve escrita de memória de erro: error_memory_write
- houve avoid_repeat depois do erro
- o brinquedo foi resolvido depois: insert_success para square/triangle/circle
- se rotação foi necessária, rotate_success existe
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_2"


def parse_payload(value: str) -> dict:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco não encontrado: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE,),
    ).fetchone()
    return row is not None


def fetch_rows(conn: sqlite3.Connection, limit: int) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT id, timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json
        FROM {TABLE}
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for row in reversed(rows):
        item = {key: row[key] for key in row.keys()}
        item["payload"] = parse_payload(row["payload_json"])
        out.append(item)
    return out


def indices(rows: list[dict], action: str | None = None, piece: str | None = None,
            hole: str | None = None, reason: str | None = None) -> list[int]:
    out = []
    for i, row in enumerate(rows):
        if action is not None and row["action_kind"] != action:
            continue
        if piece is not None and row["piece_id"] != piece:
            continue
        if hole is not None and row["hole_id"] != hole:
            continue
        if reason is not None and str(row["payload"].get("failure_reason", "") or "") != reason:
            continue
        out.append(i)
    return out


def first_after(items: list[int], after: int) -> int | None:
    for item in items:
        if item > after:
            return item
    return None


def diagnose(rows: list[dict]) -> dict:
    counts = Counter(row["action_kind"] for row in rows)

    explore = indices(rows, "controlled_explore_choose")
    start = indices(rows, "controlled_collision_start")
    collision = indices(rows, "controlled_collision")
    mem = indices(rows, "error_memory_write")
    avoid = indices(rows, "avoid_repeat")

    square_success = indices(rows, "insert_success", "piece_square_rotated", "hole_square")
    triangle_success = indices(rows, "insert_success", "piece_triangle", "hole_triangle")
    circle_success = indices(rows, "insert_success", "piece_circle", "hole_circle")
    rotate_success = indices(rows, "rotate_success", "piece_square_rotated", "hole_square")

    ordered_error_cycle = False
    ordered_trace = []
    if explore:
        a = explore[0]
        b = first_after(start, a)
        c = first_after(collision, b if b is not None else a)
        d = first_after(mem, c if c is not None else (b if b is not None else a))
        e = first_after(avoid, d if d is not None else (c if c is not None else a))
        ordered_error_cycle = b is not None and c is not None and d is not None and e is not None
        ordered_trace = [a, b, c, d, e]

    solved_after_error = False
    if mem:
        m = mem[0]
        solved_after_error = (
            first_after(square_success, m) is not None
            and first_after(triangle_success, m) is not None
            and first_after(circle_success, m) is not None
        )

    checks = {
        "has_rows": bool(rows),
        "has_controlled_explore_choose": bool(explore),
        "has_controlled_collision_start": bool(start),
        "has_controlled_collision": bool(collision),
        "has_error_memory_write": bool(mem),
        "has_avoid_repeat": bool(avoid),
        "ordered_error_cycle": ordered_error_cycle,
        "has_square_success": bool(square_success),
        "has_triangle_success": bool(triangle_success),
        "has_circle_success": bool(circle_success),
        "solved_after_error": solved_after_error,
        "has_rotate_success": bool(rotate_success),
    }

    return {
        "ok": all(checks.values()),
        "counts": dict(counts),
        "checks": checks,
        "indices": {
            "controlled_explore_choose": explore,
            "controlled_collision_start": start,
            "controlled_collision": collision,
            "error_memory_write": mem,
            "avoid_repeat": avoid,
            "square_success": square_success,
            "triangle_success": triangle_success,
            "circle_success": circle_success,
            "rotate_success": rotate_success,
            "ordered_trace": ordered_trace,
        },
    }


def row_summary(row: dict) -> str:
    reason = str(row.get("payload", {}).get("failure_reason", "") or "")
    return (
        f"#{row['id']} | {row['timestamp']} | {row['action_kind']} | "
        f"{row['piece_id']} -> {row['hole_id']} | score={float(row['score']):.3f} | "
        f"outcome={row['outcome']} | reason={reason or '-'} | note={row['note']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico v48.2 erro exploratório controlado.")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--recent", type=int, default=250)
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v48.2 — DIAGNÓSTICO DE ERRO EXPLORATÓRIO CONTROLADO")
    print("=" * 72)
    print(f"Banco:  {DB_PATH}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos")
    print()

    with connect() as conn:
        if not table_exists(conn):
            print("[ERRO] tabela geometry_live_actions_v48_2 não existe.")
            print("Rode primeiro:")
            print("  py darwin_shape_sorter_live_v48_2_controlled_error.py")
            return 2

        total = conn.execute(f"SELECT COUNT(*) AS n FROM {TABLE}").fetchone()["n"]
        rows = fetch_rows(conn, args.recent)

    report = diagnose(rows)

    print("Resumo de eventos:")
    print(f"- total no banco: {total}")
    print(f"- analisados:     {len(rows)}")
    for kind, count in sorted(report["counts"].items()):
        print(f"- {kind}: {count}")

    print()
    print("Verificações:")
    labels = {
        "has_rows": "há eventos registrados",
        "has_controlled_explore_choose": "escolheu hipótese fraca controlada",
        "has_controlled_collision_start": "iniciou teste seguro de colisão",
        "has_controlled_collision": "detectou colisão controlada",
        "has_error_memory_write": "registrou memória do erro",
        "has_avoid_repeat": "evitou repetir par falho",
        "ordered_error_cycle": "ordem correta: explorar → colidir → memorizar → evitar",
        "has_square_success": "quadrado foi resolvido",
        "has_triangle_success": "triângulo foi resolvido",
        "has_circle_success": "círculo foi resolvido",
        "solved_after_error": "resolveu o brinquedo depois do erro",
        "has_rotate_success": "rotação ativa ainda funciona",
    }

    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print()
    print(f"Resultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin errou com segurança, recuou, memorizou e evitou repetir.")
    else:
        print("Leitura: ainda falta evidência completa do ciclo v48.2.")

    if args.details:
        print()
        print("Eventos recentes:")
        for row in rows[-80:]:
            print("  " + row_summary(row))

        print()
        print("Traço ordenado do erro:")
        for idx in report["indices"].get("ordered_trace", []):
            if idx is None:
                print("  - AUSENTE")
            elif 0 <= idx < len(rows):
                print("  " + row_summary(rows[idx]))

    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
