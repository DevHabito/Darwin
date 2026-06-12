from __future__ import annotations

"""
DARWIN v49.7 - Diagnostico da geometria como experiencia

Uso:
    py darwin_check_v49_7_geometry_experience.py
    py darwin_check_v49_7_geometry_experience.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SCENARIOS = "geometry_learning_scenarios_v49_7"
CONCEPTS = "geometry_concepts_v49_7"
NODES = "geometry_experience_nodes_v49_7"
EDGES = "geometry_experience_edges_v49_7"
WEIGHTS = "geometry_learning_weights_v49_7"
REPLAYS = "geometry_error_replay_v49_7"

REQUIRED_FAMILIES = {"angle", "metric", "area", "vector", "weight", "transformation"}


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if scenario_id is not None:
        where = " WHERE scenario_id=?"
        params = (scenario_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    scenario_rows = rows(conn, SCENARIOS)
    completed = [
        r
        for r in scenario_rows
        if r.get("phase") == "geometry_complete" and r.get("payload", {}).get("scenario_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["scenario_id"]), row


def phase_order_ok(events: list[dict[str, Any]]) -> bool:
    if not events:
        return False
    names = [str(e.get("phase")) for e in events]
    required = [
        "geometry_start",
        "source_memory_read",
        "curriculum_seed",
        "experience_cycle",
        "concept_consolidation",
        "geometry_complete",
    ]
    positions = []
    for name in required:
        try:
            positions.append(names.index(name))
        except ValueError:
            return False
    return positions == sorted(positions) and names[-1] == "geometry_complete"


def semantic_count(conn: sqlite3.Connection, scenario_id: str) -> int:
    if not table_exists(conn, "semantic_memory"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source='darwin_geometry_experience_v49_7'
          AND (key LIKE 'geometry_v49_7:%' OR key=?)
        """,
        (f"brain_v49_7:geometry_experience:{scenario_id}",),
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, scenario_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_geometry_experience_v49_7'
          AND context=?
        """,
        (f"geometry_v49_7:{scenario_id}",),
    ).fetchone()
    return int(row["n"]) if row else 0


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    scenario_id, complete_row = latest_completed(conn)
    events = rows(conn, SCENARIOS, scenario_id) if scenario_id else []
    concepts = rows(conn, CONCEPTS, scenario_id) if scenario_id else []
    nodes = rows(conn, NODES, scenario_id) if scenario_id else []
    edges = rows(conn, EDGES, scenario_id) if scenario_id else []
    weights = rows(conn, WEIGHTS, scenario_id) if scenario_id else []
    replays = rows(conn, REPLAYS, scenario_id) if scenario_id else []
    complete = complete_row.get("payload", {}) if complete_row else {}

    families = {str(c.get("family")) for c in concepts}
    angle_nodes = [n for n in nodes if n.get("family") == "angle"]
    weight_nodes = [n for n in nodes if n.get("family") == "weight"]
    error_nodes = [n for n in nodes if n.get("verdict") == "error"]
    hit_nodes = [n for n in nodes if n.get("verdict") == "hit"]
    changed_weights = [
        w
        for w in weights
        if abs(float(w.get("weight_after") or 0.0) - float(w.get("weight_before") or 0.0)) > 0.000001
    ]
    rzs_decisions = {str(n.get("rzs_decision")) for n in nodes if n.get("rzs_decision")}
    cognitive_actions = {str(n.get("cognitive_action")) for n in nodes if n.get("cognitive_action")}
    edge_kinds = {str(e.get("edge_kind")) for e in edges if e.get("edge_kind")}
    concept_keys = {str(c.get("concept_key")) for c in concepts}
    completed_cycles = int(complete.get("cycles_completed") or 0)
    first_error = float(complete.get("first_quarter_error") or 0.0)
    last_error = float(complete.get("last_quarter_error") or 999.0)

    checks = {
        "has_completed_scenario": bool(scenario_id),
        "phase_order_causal": phase_order_ok(events),
        "rich_geometry_curriculum": len(concepts) >= 20 and REQUIRED_FAMILIES.issubset(families),
        "angle_concepts_present": bool(angle_nodes) and "angle_min_rotation" in concept_keys and "triangle_angle_sum" in concept_keys,
        "weight_concepts_present": bool(weight_nodes) and "weighted_centroid_1d" in concept_keys and "lever_balance_torque" in concept_keys,
        "experience_nodes_created": len(nodes) >= max(72, completed_cycles) and all(str(n.get("node_id", "")).startswith("geo:") for n in nodes),
        "experience_graph_connected": len(edges) >= max(1, len(nodes) - 1) and {"temporal_sequence", "same_concept_refinement"}.issubset(edge_kinds),
        "darwin_made_mistakes": len(error_nodes) >= 8,
        "darwin_also_succeeded": len(hit_nodes) >= 4,
        "weights_changed": len(changed_weights) >= 16,
        "rzs_changed_behavior": len(rzs_decisions) >= 2 and any(d != "continue" for d in rzs_decisions) and len(cognitive_actions) >= 2,
        "replay_occurred": len(replays) >= 1 and any(float(r.get("error_after") or 0.0) < float(r.get("error_before") or 0.0) for r in replays),
        "learning_improved": bool(nodes) and last_error < first_error,
        "semantic_memory_written": semantic_count(conn, scenario_id) >= 10 if scenario_id else False,
        "episode_written": episode_count(conn, scenario_id) >= 1 if scenario_id else False,
        "protected_sources_unchanged": bool(complete.get("protected_sources_unchanged")),
    }
    return {
        "ok": all(checks.values()),
        "scenario_id": scenario_id,
        "checks": checks,
        "counts": {
            "events": len(events),
            "concepts": len(concepts),
            "nodes": len(nodes),
            "edges": len(edges),
            "weights": len(weights),
            "replays": len(replays),
            "errors": len(error_nodes),
            "hits": len(hit_nodes),
            "semantic": semantic_count(conn, scenario_id) if scenario_id else 0,
            "episodes": episode_count(conn, scenario_id) if scenario_id else 0,
        },
        "families": sorted(families),
        "rzs_decisions": sorted(rzs_decisions),
        "cognitive_actions": sorted(cognitive_actions),
        "first_quarter_error": first_error,
        "last_quarter_error": last_error,
        "complete_payload": complete,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.7 - DIAGNOSTICO DA GEOMETRIA EXPERIENCIAL")
    print("=" * 62)
    print(f"- cenario v49.7: {report['scenario_id'] or 'NENHUM'}")
    counts = report["counts"]
    print(
        f"- conceitos={counts['concepts']} nos={counts['nodes']} arestas={counts['edges']} "
        f"erros={counts['errors']} acertos={counts['hits']} replays={counts['replays']}"
    )
    print(f"- erro inicio={report['first_quarter_error']:.4f} erro final={report['last_quarter_error']:.4f}")
    print(f"- familias: {', '.join(report['families']) if report['families'] else 'nenhuma'}")
    print(f"- decisoes RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhuma'}")
    print()
    labels = {
        "has_completed_scenario": "cenario completo encontrado",
        "phase_order_causal": "fases em ordem causal",
        "rich_geometry_curriculum": "curriculo geometrico amplo",
        "angle_concepts_present": "angulos presentes",
        "weight_concepts_present": "pesos/centroides presentes",
        "experience_nodes_created": "nos de experiencia criados",
        "experience_graph_connected": "grafo de experiencia conectado",
        "darwin_made_mistakes": "Darwin errou de verdade",
        "darwin_also_succeeded": "Darwin tambem acertou",
        "weights_changed": "pesos de aprendizagem mudaram",
        "rzs_changed_behavior": "RZS alterou comportamento",
        "replay_occurred": "replay reduziu erro",
        "learning_improved": "erro medio caiu",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio criado",
        "protected_sources_unchanged": "fontes v48/v49 preservadas",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin criou nos geometricos, errou, corrigiu, ajustou pesos e consolidou experiencias.")
    else:
        print("Leitura: ainda falta evidencia para afirmar aprendizagem geometrica experiencial.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.7 Geometry Experience checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
