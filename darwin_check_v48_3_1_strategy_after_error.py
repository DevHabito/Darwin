from __future__ import annotations

"""
DARWIN v48.3.1 — Diagnóstico de Estratégia Após Erro

Lê:
    geometry_live_actions_v48_3_1

Verifica uma cadeia auditável correta:
    controlled_explore_choose
    -> controlled_collision_start
    -> controlled_collision
    -> error_memory_write
    -> strategy_select
    -> strategy_execute
    -> insert_success

Uso:
    py darwin_check_v48_3_1_strategy_after_error.py
    py darwin_check_v48_3_1_strategy_after_error.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_3_1"


def parse_payload(s: str) -> dict:
    try:
        return json.loads(s or "{}")
    except Exception:
        return {}


def fetch_rows(limit: int) -> tuple[list[dict] | None, int]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco não encontrado: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,),
        ).fetchone()
        if not exists:
            return None, 0

        total = conn.execute(f"SELECT COUNT(*) AS n FROM {TABLE}").fetchone()["n"]
        raw = conn.execute(
            f"""
            SELECT id, timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json
            FROM {TABLE}
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    rows = []
    for row in reversed(raw):
        item = {key: row[key] for key in row.keys()}
        item["payload"] = parse_payload(item["payload_json"])
        rows.append(item)
    return rows, total


def idx(rows: list[dict], action: str | None = None, piece: str | None = None,
        hole: str | None = None, note_contains: str | None = None) -> list[int]:
    out = []
    for i, row in enumerate(rows):
        if action is not None and row["action_kind"] != action:
            continue
        if piece is not None and row["piece_id"] != piece:
            continue
        if hole is not None and row["hole_id"] != hole:
            continue
        if note_contains is not None and note_contains not in str(row["note"]):
            continue
        out.append(i)
    return out


def first_after(indices: list[int], after: int) -> int | None:
    for i in indices:
        if i > after:
            return i
    return None


def find_valid_strategy_trace(rows: list[dict]) -> list[int | None]:
    explores = idx(rows, "controlled_explore_choose")
    starts = idx(rows, "controlled_collision_start")
    collisions = idx(rows, "controlled_collision")
    memories = idx(rows, "error_memory_write")
    selects = idx(rows, "strategy_select")
    executes = idx(rows, "strategy_execute")
    triangle_success = idx(rows, "insert_success", "piece_triangle", "hole_triangle")

    for a in explores:
        b = first_after(starts, a)
        c = first_after(collisions, b if b is not None else a)
        d = first_after(memories, c if c is not None else a)
        e = first_after(selects, d if d is not None else a)
        f = first_after(executes, e if e is not None else a)
        g = first_after(triangle_success, f if f is not None else a)
        trace = [a, b, c, d, e, f, g]
        if all(x is not None for x in trace):
            return trace
    return []


def diagnose(rows: list[dict]) -> dict:
    counts = Counter(row["action_kind"] for row in rows)

    trace = find_valid_strategy_trace(rows)

    strategy_alt = idx(rows, "strategy_select", "piece_triangle", "hole_square", "try_alternate_hole")
    exec_alt = idx(rows, "strategy_execute", "piece_triangle", "hole_triangle", "try_alternate_hole")

    avoid = idx(rows, "avoid_repeat")
    tri_ok = idx(rows, "insert_success", "piece_triangle", "hole_triangle")
    cir_ok = idx(rows, "insert_success", "piece_circle", "hole_circle")
    sq_ok = idx(rows, "insert_success", "piece_square_rotated", "hole_square")
    rot_ok = idx(rows, "rotate_success", "piece_square_rotated", "hole_square")

    solved_after_strategy = False
    execs = idx(rows, "strategy_execute")
    if execs:
        s = execs[0]
        solved_after_strategy = (
            first_after(tri_ok, s) is not None
            and first_after(cir_ok, s) is not None
            and first_after(sq_ok, s) is not None
        )

    checks = {
        "has_rows": bool(rows),
        "has_controlled_explore_choose": bool(idx(rows, "controlled_explore_choose")),
        "has_controlled_collision_start": bool(idx(rows, "controlled_collision_start")),
        "has_controlled_collision": bool(idx(rows, "controlled_collision")),
        "has_error_memory_write": bool(idx(rows, "error_memory_write")),
        "has_strategy_select": bool(idx(rows, "strategy_select")),
        "has_strategy_execute": bool(idx(rows, "strategy_execute")),
        "strategy_maps_contour_to_try_alternate": bool(strategy_alt),
        "strategy_executes_alternate_hole": bool(exec_alt),
        "ordered_strategy_cycle": bool(trace),
        "has_avoid_repeat": bool(avoid),
        "has_triangle_success": bool(tri_ok),
        "has_circle_success": bool(cir_ok),
        "has_square_success": bool(sq_ok),
        "has_rotate_success": bool(rot_ok),
        "solved_after_strategy": solved_after_strategy,
    }

    return {
        "ok": all(checks.values()),
        "counts": dict(counts),
        "checks": checks,
        "trace": trace,
    }


def row_summary(row: dict) -> str:
    payload = row.get("payload", {})
    info = payload.get("failure_reason") or payload.get("recommendation")
    if not info and isinstance(payload.get("strategy"), dict):
        info = payload["strategy"].get("recommendation")
    return (
        f"#{row['id']} | {row['timestamp']} | {row['action_kind']} | "
        f"{row['piece_id']} -> {row['hole_id']} | score={float(row['score']):.3f} | "
        f"info={info or '-'} | note={row['note']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico v48.3.1 estratégia após erro.")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--recent", type=int, default=300)
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v48.3.1 — DIAGNÓSTICO DE ESTRATÉGIA APÓS ERRO")
    print("=" * 72)
    print(f"Banco:  {DB_PATH}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos")
    print()

    rows, total = fetch_rows(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe.")
        print("Rode primeiro:")
        print("  py darwin_shape_sorter_live_v48_3_1_strategy_after_error.py")
        return 2

    report = diagnose(rows)

    print("Resumo de eventos:")
    print(f"- total no banco: {total}")
    print(f"- analisados:     {len(rows)}")
    for kind, count in sorted(report["counts"].items()):
        print(f"- {kind}: {count}")

    labels = {
        "has_rows": "há eventos registrados",
        "has_controlled_explore_choose": "escolheu hipótese fraca",
        "has_controlled_collision_start": "iniciou teste seguro",
        "has_controlled_collision": "detectou colisão antes de memorizar",
        "has_error_memory_write": "registrou memória do erro",
        "has_strategy_select": "selecionou estratégia",
        "has_strategy_execute": "executou estratégia",
        "strategy_maps_contour_to_try_alternate": "contour_mismatch → try_alternate_hole",
        "strategy_executes_alternate_hole": "executou outro buraco para a mesma peça",
        "ordered_strategy_cycle": "ordem correta: erro → memória → estratégia → execução → sucesso",
        "has_avoid_repeat": "evitou repetir par falho",
        "has_triangle_success": "triângulo foi resolvido",
        "has_circle_success": "círculo foi resolvido",
        "has_square_success": "quadrado foi resolvido",
        "has_rotate_success": "rotação ativa ainda funciona",
        "solved_after_strategy": "resolveu brinquedo após estratégia",
    }

    print()
    print("Verificações:")
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print()
    print(f"Resultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin classificou o erro e escolheu uma estratégia física adequada, com ordem auditável correta.")
    else:
        print("Leitura: ainda falta evidência completa da política v48.3.1.")

    if args.details:
        print()
        print("Eventos recentes:")
        for row in rows[-100:]:
            print("  " + row_summary(row))

        print()
        print("Traço ordenado da estratégia:")
        trace = report["trace"]
        if not trace:
            print("  - nenhum traço completo encontrado")
        else:
            for i in trace:
                print("  " + row_summary(rows[i]))

    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
