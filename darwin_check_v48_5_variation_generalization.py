from __future__ import annotations

"""
DARWIN v48.5 — Diagnóstico de Generalização por Variação

Lê:
    geometry_live_actions_v48_5

Valida por cenário, papéis e propriedades, não por nomes fixos de peças/buracos.

Uso:
    py darwin_check_v48_5_variation_generalization.py
    py darwin_check_v48_5_variation_generalization.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_5"


def parse_payload(value: str) -> dict:
    try:
        return json.loads(value or "{}")
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
            SELECT id, timestamp, scenario_id, action_kind, piece_id, hole_id, piece_role, hole_role,
                   failure_reason, recommendation, score, outcome, note, payload_json
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


def latest_complete_scenario(rows: list[dict]) -> str | None:
    completed = [r["scenario_id"] for r in rows if r["action_kind"] == "scenario_complete" and r["outcome"] == "success"]
    if completed:
        return completed[-1]
    scenario_ids = [r["scenario_id"] for r in rows if r["scenario_id"]]
    return scenario_ids[-1] if scenario_ids else None


def filter_scenario(rows: list[dict], scenario_id: str) -> list[dict]:
    return [r for r in rows if r["scenario_id"] == scenario_id]


def has(
    rows: list[dict],
    action: str | None = None,
    piece_role: str | None = None,
    hole_role: str | None = None,
    failure_reason: str | None = None,
    recommendation: str | None = None,
    outcome: str | None = None,
    note: str | None = None,
) -> bool:
    for row in rows:
        if action is not None and row["action_kind"] != action:
            continue
        if piece_role is not None and row["piece_role"] != piece_role:
            continue
        if hole_role is not None and row["hole_role"] != hole_role:
            continue
        if failure_reason is not None and row["failure_reason"] != failure_reason:
            continue
        if recommendation is not None and row["recommendation"] != recommendation:
            continue
        if outcome is not None and row["outcome"] != outcome:
            continue
        if note is not None and note not in str(row["note"]):
            continue
        return True
    return False


def unique_ids_randomized(rows: list[dict]) -> bool:
    # A v48.5 deve usar IDs variáveis como object_XXXXX e aperture_XXXXX.
    piece_ids = {r["piece_id"] for r in rows if r["piece_id"]}
    hole_ids = {r["hole_id"] for r in rows if r["hole_id"]}
    return (
        len(piece_ids) >= 6
        and len(hole_ids) >= 3
        and all(pid.startswith("object_") for pid in piece_ids)
        and all(hid.startswith("aperture_") for hid in hole_ids)
    )


def measurements_varied(rows: list[dict]) -> bool:
    inits = [r for r in rows if r["action_kind"] == "scenario_init"]
    if not inits:
        return False
    payload = inits[-1]["payload"]
    required = ["square_size", "triangle_size", "circle_size", "base_depth", "tolerance", "bad_angle"]
    return all(k in payload for k in required) and payload.get("bad_angle") not in (0, 45)


def diagnose(rows: list[dict]) -> dict:
    scenario_id = latest_complete_scenario(rows)
    scenario_rows = filter_scenario(rows, scenario_id) if scenario_id else []
    counts = Counter(row["action_kind"] for row in scenario_rows)

    checks = {
        "has_scenario": bool(scenario_id),
        "scenario_complete": has(scenario_rows, "scenario_complete", outcome="success"),
        "randomized_ids": unique_ids_randomized(scenario_rows),
        "measurements_varied": measurements_varied(scenario_rows),

        "contour_probe": has(scenario_rows, "probe_choose", "valid_triangle", "target_square", "contour_mismatch"),
        "contour_strategy": has(scenario_rows, "strategy_select", "valid_triangle", "target_square", "contour_mismatch", "try_alternate_hole"),
        "contour_alternate_target": has(scenario_rows, "strategy_execute_alternate_target", "valid_triangle", "target_triangle", recommendation="try_alternate_hole"),
        "triangle_success": has(scenario_rows, "insert_success", "valid_triangle", "target_triangle"),

        "size_probe": has(scenario_rows, "probe_choose", "oversize_circle", "target_circle", "size_mismatch"),
        "size_strategy": has(scenario_rows, "strategy_select", "oversize_circle", "target_circle", "size_mismatch", "reject_pair_size"),
        "size_outcome": has(scenario_rows, "strategy_outcome", "oversize_circle", "target_circle", "size_mismatch", "reject_pair_size"),

        "depth_probe": has(scenario_rows, "probe_choose", "deep_square", "target_square", "depth_mismatch"),
        "depth_strategy": has(scenario_rows, "strategy_select", "deep_square", "target_square", "depth_mismatch", "reject_pair_depth"),
        "depth_outcome": has(scenario_rows, "strategy_outcome", "deep_square", "target_square", "depth_mismatch", "reject_pair_depth"),

        "uncertain_probe": has(scenario_rows, "probe_choose", "unknown_piece", "target_circle", "uncertain_failure"),
        "uncertain_strategy": has(scenario_rows, "strategy_select", "unknown_piece", "target_circle", "uncertain_failure", "cautious_exploration"),
        "uncertain_outcome": has(scenario_rows, "strategy_outcome", "unknown_piece", "target_circle", "uncertain_failure", "cautious_exploration"),

        "rotation_probe": has(scenario_rows, "probe_choose", "rotated_square", "target_square", "rotation_mismatch"),
        "rotation_strategy": has(scenario_rows, "strategy_select", "rotated_square", "target_square", "rotation_mismatch", "rotate_piece"),
        "rotation_execute": has(scenario_rows, "strategy_execute", "rotated_square", "target_square", "rotation_mismatch", "rotate_piece"),
        "rotate_success": has(scenario_rows, "rotate_success", "rotated_square", "target_square"),
        "square_success": has(scenario_rows, "insert_success", "rotated_square", "target_square"),

        "circle_success": has(scenario_rows, "insert_success", "valid_circle", "target_circle"),
    }

    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "counts": dict(counts),
        "checks": checks,
        "rows_analyzed": len(scenario_rows),
    }


def row_summary(row: dict) -> str:
    info = row["failure_reason"] or row["recommendation"] or "-"
    return (
        f"#{row['id']} | {row['timestamp']} | {row['scenario_id']} | {row['action_kind']} | "
        f"{row['piece_role']}:{row['piece_id']} -> {row['hole_role']}:{row['hole_id']} | "
        f"score={float(row['score']):.3f} | info={info} | note={row['note']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico v48.5 generalização por variação.")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--recent", type=int, default=800)
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN v48.5 — DIAGNÓSTICO DE GENERALIZAÇÃO POR VARIAÇÃO")
    print("=" * 72)
    print(f"Banco:  {DB_PATH}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos")
    print()

    rows, total = fetch_rows(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe.")
        print("Rode primeiro:")
        print("  py darwin_shape_sorter_live_v48_5_variation_generalization.py")
        return 2

    report = diagnose(rows)

    print("Resumo:")
    print(f"- total no banco: {total}")
    print(f"- cenário analisado: {report['scenario_id']}")
    print(f"- eventos do cenário: {report['rows_analyzed']}")
    for kind, count in sorted(report["counts"].items()):
        print(f"- {kind}: {count}")

    labels = {
        "has_scenario": "há cenário analisável",
        "scenario_complete": "cenário concluiu com sucesso",
        "randomized_ids": "IDs variáveis foram usados",
        "measurements_varied": "medidas/tolerância/ângulo variaram",

        "contour_probe": "testou falha por contorno",
        "contour_strategy": "contour_mismatch → try_alternate_hole",
        "contour_alternate_target": "escolheu alvo alternativo por papel, não por nome fixo",
        "triangle_success": "triângulo válido foi resolvido",

        "size_probe": "testou falha por tamanho",
        "size_strategy": "size_mismatch → reject_pair_size",
        "size_outcome": "registrou rejeição por tamanho",

        "depth_probe": "testou falha por profundidade",
        "depth_strategy": "depth_mismatch → reject_pair_depth",
        "depth_outcome": "registrou rejeição por profundidade",

        "uncertain_probe": "testou falha incerta",
        "uncertain_strategy": "uncertain_failure → cautious_exploration",
        "uncertain_outcome": "registrou cautela",

        "rotation_probe": "testou falha por orientação",
        "rotation_strategy": "rotation_mismatch → rotate_piece",
        "rotation_execute": "executou rotação",
        "rotate_success": "rotação funcionou",
        "square_success": "quadrado rotacionado foi resolvido",

        "circle_success": "círculo válido foi resolvido",
    }

    print()
    print("Verificações:")
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")

    print()
    print(f"Resultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin aplicou a política por propriedades em cenário com nomes e medidas variáveis.")
    else:
        print("Leitura: ainda falta evidência completa da generalização por variação v48.5.")

    if args.details:
        scenario_id = report["scenario_id"]
        scenario_rows = filter_scenario(rows, scenario_id) if scenario_id else []
        print()
        print("Eventos do cenário:")
        for row in scenario_rows:
            print("  " + row_summary(row))

    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
