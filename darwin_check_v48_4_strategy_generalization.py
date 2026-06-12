from __future__ import annotations

"""
DARWIN v48.4 — Diagnóstico de Generalização de Estratégia

Lê:
    geometry_live_actions_v48_4

Verifica:
- contour_mismatch  -> try_alternate_hole
- size_mismatch     -> reject_pair_size
- depth_mismatch    -> reject_pair_depth
- rotation_mismatch -> rotate_piece
- uncertain_failure -> cautious_exploration
- resolução com peças válidas
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_4"


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


def has(rows: list[dict], action: str | None = None, piece: str | None = None,
        hole: str | None = None, note: str | None = None) -> bool:
    for row in rows:
        if action is not None and row["action_kind"] != action:
            continue
        if piece is not None and row["piece_id"] != piece:
            continue
        if hole is not None and row["hole_id"] != hole:
            continue
        if note is not None and note not in str(row["note"]):
            continue
        return True
    return False


def indices(rows: list[dict], action: str | None = None, piece: str | None = None,
            hole: str | None = None, note: str | None = None) -> list[int]:
    out = []
    for i, row in enumerate(rows):
        if action is not None and row["action_kind"] != action:
            continue
        if piece is not None and row["piece_id"] != piece:
            continue
        if hole is not None and row["hole_id"] != hole:
            continue
        if note is not None and note not in str(row["note"]):
            continue
        out.append(i)
    return out


def first_after(xs: list[int], after: int) -> int | None:
    for x in xs:
        if x > after:
            return x
    return None


def diagnose(rows: list[dict]) -> dict:
    counts = Counter(row["action_kind"] for row in rows)

    checks = {
        "has_rows": bool(rows),

        "contour_probe": has(rows, "probe_choose", "piece_triangle", "hole_square", "contour_mismatch"),
        "contour_strategy": has(rows, "strategy_select", "piece_triangle", "hole_square", "try_alternate_hole"),
        "contour_alternate_target": has(rows, "strategy_execute_alternate_target", "piece_triangle", "hole_triangle", "try_alternate_hole"),
        "triangle_success": has(rows, "insert_success", "piece_triangle", "hole_triangle"),

        "size_probe": has(rows, "probe_choose", "piece_circle_large", "hole_circle", "size_mismatch"),
        "size_strategy": has(rows, "strategy_select", "piece_circle_large", "hole_circle", "reject_pair_size"),
        "size_outcome": has(rows, "strategy_outcome", "piece_circle_large", "hole_circle", "reject_pair_size"),

        "depth_probe": has(rows, "probe_choose", "piece_square_deep", "hole_square", "depth_mismatch"),
        "depth_strategy": has(rows, "strategy_select", "piece_square_deep", "hole_square", "reject_pair_depth"),
        "depth_outcome": has(rows, "strategy_outcome", "piece_square_deep", "hole_square", "reject_pair_depth"),

        "uncertain_probe": has(rows, "probe_choose", "piece_unknown", "hole_circle", "uncertain_failure"),
        "uncertain_strategy": has(rows, "strategy_select", "piece_unknown", "hole_circle", "cautious_exploration"),
        "uncertain_outcome": has(rows, "strategy_outcome", "piece_unknown", "hole_circle", "cautious_exploration"),

        "rotation_probe": has(rows, "probe_choose", "piece_square_rotated", "hole_square", "rotation_mismatch"),
        "rotation_strategy": has(rows, "strategy_select", "piece_square_rotated", "hole_square", "rotate_piece"),
        "rotation_execute": has(rows, "strategy_execute", "piece_square_rotated", "hole_square", "rotate_piece"),
        "rotate_success": has(rows, "rotate_success", "piece_square_rotated", "hole_square"),
        "square_success": has(rows, "insert_success", "piece_square_rotated", "hole_square"),

        "circle_success": has(rows, "insert_success", "piece_circle", "hole_circle"),
    }

    # ordem mínima para caso de tamanho, profundidade e incerteza:
    ordered_rejections = True
    for piece, hole, rec in [
        ("piece_circle_large", "hole_circle", "reject_pair_size"),
        ("piece_square_deep", "hole_square", "reject_pair_depth"),
        ("piece_unknown", "hole_circle", "cautious_exploration"),
    ]:
        col = indices(rows, "controlled_collision", piece, hole)
        mem = indices(rows, "error_memory_write", piece, hole)
        sel = indices(rows, "strategy_select", piece, hole, rec)
        out = indices(rows, "strategy_outcome", piece, hole, rec)
        if not col:
            ordered_rejections = False
            continue
        a = col[0]
        b = first_after(mem, a)
        c = first_after(sel, b if b is not None else a)
        d = first_after(out, c if c is not None else a)
        if not all(x is not None for x in [b, c, d]):
            ordered_rejections = False

    checks["ordered_rejection_cycles"] = ordered_rejections

    return {
        "ok": all(checks.values()),
        "counts": dict(counts),
        "checks": checks,
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
    parser = argparse.ArgumentParser(description="Diagnóstico v48.4 generalização de estratégia.")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--recent", type=int, default=500)
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v48.4 — DIAGNÓSTICO DE GENERALIZAÇÃO DE ESTRATÉGIA")
    print("=" * 72)
    print(f"Banco:  {DB_PATH}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos")
    print()

    rows, total = fetch_rows(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe.")
        print("Rode primeiro:")
        print("  py darwin_shape_sorter_live_v48_4_strategy_generalization.py")
        return 2

    report = diagnose(rows)

    print("Resumo de eventos:")
    print(f"- total no banco: {total}")
    print(f"- analisados:     {len(rows)}")
    for kind, count in sorted(report["counts"].items()):
        print(f"- {kind}: {count}")

    labels = {
        "has_rows": "há eventos registrados",
        "contour_probe": "testou falha por contorno",
        "contour_strategy": "contour_mismatch → try_alternate_hole",
        "contour_alternate_target": "escolheu buraco alternativo",
        "triangle_success": "triângulo foi resolvido",
        "size_probe": "testou falha por tamanho",
        "size_strategy": "size_mismatch → reject_pair_size",
        "size_outcome": "registrou rejeição por tamanho",
        "depth_probe": "testou falha por profundidade",
        "depth_strategy": "depth_mismatch → reject_pair_depth",
        "depth_outcome": "registrou rejeição por profundidade",
        "uncertain_probe": "testou falha incerta",
        "uncertain_strategy": "uncertain_failure → cautious_exploration",
        "uncertain_outcome": "registrou exploração cautelosa",
        "rotation_probe": "testou falha por orientação",
        "rotation_strategy": "rotation_mismatch → rotate_piece",
        "rotation_execute": "executou estratégia de rotação",
        "rotate_success": "rotação funcionou",
        "square_success": "quadrado foi resolvido",
        "circle_success": "círculo foi resolvido",
        "ordered_rejection_cycles": "ordem correta nos ciclos de rejeição/cautela",
    }

    print()
    print("Verificações:")
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print()
    print(f"Resultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin generalizou a política de estratégia para múltiplos tipos de falha.")
    else:
        print("Leitura: ainda falta evidência completa da generalização v48.4.")

    if args.details:
        print()
        print("Eventos recentes:")
        for row in rows[-120:]:
            print("  " + row_summary(row))

    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
