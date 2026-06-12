from __future__ import annotations

"""
DARWIN v49.33 - Diagnostico RZS/ELCL Regge Geometry

Uso:
    py darwin_check_v49_33_rzs_elcl_regge_geometry.py
    py darwin_check_v49_33_rzs_elcl_regge_geometry.py --details
"""

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_rzs_elcl_regge_geometry_v49_33"

SESSIONS = "regge_elcl_sessions_v49_33"
ARTICLE_SIGNALS = "regge_article_signals_v49_33"
NODES = "regge_relational_nodes_v49_33"
EDGES = "regge_relational_edges_v49_33"
TETRA = "regge_tetrahedra_v49_33"
GATES = "regge_projection_gates_v49_33"
REPAIRS = "regge_quality_repairs_v49_33"
REFLECTIONS = "regge_reflections_v49_33"
HANDOFFS = "regge_handoffs_v49_33"

REQUIRED_TABLES = [
    SESSIONS,
    ARTICLE_SIGNALS,
    NODES,
    EDGES,
    TETRA,
    GATES,
    REPAIRS,
    REFLECTIONS,
    HANDOFFS,
]

REQUIRED_SIGNALS = {
    "relational_graph_input",
    "elcl_projection",
    "k4_metric_clique",
    "regge_srmse_gate",
    "spectral_anchor_frontier",
    "boundary_ratio_quality",
    "quality_projector",
    "batch_coherent_recovery",
}

REQUIRED_GATES = {
    "LI_regge_reconstruction_error",
    "LXXXV_spectral_anchor_cost_error",
    "LXXXVI_compression_discretization",
    "LXXXVII_observed_n_scaling",
    "XCVI_boundary_ratio_threshold",
    "XCVIII_boundary_ratio_safety",
    "XCIV_quality_projector_mean",
    "XCV_edgewise_high_damage_limit",
    "C_batch_coherent_recovery",
}

PRIOR_TABLES = [
    "controlled_executor_sessions_v49_32",
    "autonomous_curriculum_sessions_v49_31",
    "learning_to_learn_sessions_v49_30",
    "formula_sketch_sessions_v49_28",
    "geometry_concepts_v49_7",
    "rzs_stress_tests_v49_3",
]


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    return parsed


def number(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        out = float(value)
    except (TypeError, ValueError):
        return fallback
    return out if math.isfinite(out) else fallback


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, session_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if session_id is not None:
        where = " WHERE session_id=?"
        params = (session_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        if "payload_json" in item:
            item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    completed = [
        r
        for r in rows(conn, SESSIONS)
        if r.get("phase") == "regge_projection_complete" and r.get("payload", {}).get("regge_projection_ready") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row.get("session_id") or ""), row


def semantic_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "semantic_memory"):
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM semantic_memory WHERE source=? AND key=?",
        (SOURCE, f"rzs_elcl_regge_v49_33:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM episodes WHERE module=? AND context=?",
        (SOURCE, f"regge_elcl:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def prior_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def check_article(signals: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    keys = {str(s.get("signal_key") or "") for s in signals}
    families = {str(s.get("signal_family") or "") for s in signals}
    return (
        payload.get("article_exists") is True
        and len(signals) >= 10
        and REQUIRED_SIGNALS.issubset(keys)
        and {"projection", "regge", "repair", "validation"}.issubset(families)
    )


def check_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bool:
    if len(nodes) < 24 or len(edges) < 40:
        return False
    inferred = [e for e in edges if int(e.get("inferred") or 0) == 1]
    if not inferred:
        return False
    kinds = {str(n.get("kind") or "") for n in nodes}
    if not {"root", "regulator", "semantic"}.issubset(kinds):
        return False
    for edge in edges[: min(120, len(edges))]:
        length = number(edge.get("length"), -1.0)
        support = number(edge.get("support"), -1.0)
        weight = number(edge.get("weight"), -1.0)
        if length <= 0.0 or not 0.0 <= support <= 1.0 or not 0.0 <= weight <= 1.0:
            return False
    return True


def check_tetra(tetra: list[dict[str, Any]]) -> bool:
    stable = [t for t in tetra if int(t.get("stable") or 0) == 1]
    if len(stable) < 1:
        return False
    for row in stable[:20]:
        if number(row.get("volume"), 0.0) <= 0.0:
            return False
        if number(row.get("aspect_ratio"), 99.0) > 3.50:
            return False
        if number(row.get("defect_proxy"), 99.0) > 0.55:
            return False
    return True


def check_gates(gates: list[dict[str, Any]]) -> bool:
    keys = {str(g.get("gate_key") or "") for g in gates}
    if not REQUIRED_GATES.issubset(keys):
        return False
    passed = sum(1 for g in gates if int(g.get("passed") or 0) == 1)
    if passed < 8:
        return False
    li = next((g for g in gates if g.get("gate_key") == "LI_regge_reconstruction_error"), None)
    if not li or int(li.get("passed") or 0) != 1:
        return False
    return number(li.get("score"), 9.0) <= number(li.get("threshold"), 0.0)


def check_repairs(repairs: list[dict[str, Any]], gates: list[dict[str, Any]]) -> bool:
    if len(repairs) < 8:
        return False
    batch = [r for r in repairs if int(r.get("batch_coherent") or 0) == 1]
    high = [r for r in repairs if str(r.get("repair_kind") or "") == "edgewise_high_damage_limit"]
    if not batch or not high:
        return False
    if not all(number(r.get("srmse_after"), 9.0) < number(r.get("srmse_before"), 0.0) for r in batch):
        return False
    if not any(int(r.get("missed_repair_count") or 0) >= 70 for r in high):
        return False
    gate_c = next((g for g in gates if g.get("gate_key") == "C_batch_coherent_recovery"), None)
    return gate_c is not None and int(gate_c.get("passed") or 0) == 1


def check_rzs(payload: dict[str, Any]) -> bool:
    decision = str(payload.get("rzs_decision") or "")
    return (
        decision in {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}
        and number(payload.get("sigma_before"), 0.0) > 0.0
        and number(payload.get("sigma_after"), 0.0) > 0.0
        and isinstance(payload.get("rzs_payload"), dict)
        and payload.get("rzs_payload", {}).get("prediction_valid") is True
    )


def diagnose(details: bool = False) -> dict[str, Any]:
    with connect() as conn:
        tables_ok = all(table_exists(conn, table) for table in REQUIRED_TABLES)
        session_id, completed = latest_completed(conn)
        payload = completed.get("payload", {}) if completed else {}
        signals = rows(conn, ARTICLE_SIGNALS, session_id) if session_id else []
        nodes = rows(conn, NODES, session_id) if session_id else []
        edges = rows(conn, EDGES, session_id) if session_id else []
        tetra = rows(conn, TETRA, session_id) if session_id else []
        gates = rows(conn, GATES, session_id) if session_id else []
        repairs = rows(conn, REPAIRS, session_id) if session_id else []
        reflections = rows(conn, REFLECTIONS, session_id) if session_id else []
        handoffs = rows(conn, HANDOFFS, session_id) if session_id else []
        semantic = semantic_count(conn, session_id) if session_id else 0
        episodes = episode_count(conn, session_id) if session_id else 0

        protected_before = payload.get("protected_counts_before", {})
        protected_after = payload.get("protected_counts_after", {})
        prior_present = all(prior_count(conn, table) > 0 for table in PRIOR_TABLES)
        protected_ok = protected_before == protected_after and payload.get("protected_sources_unchanged") is True

        checks = {
            "tables_exist": tables_ok,
            "completed_session": bool(session_id and payload.get("regge_projection_ready") is True),
            "article_signals_loaded": check_article(signals, payload),
            "relational_graph_projected": check_graph(nodes, edges),
            "k4_tetrahedra_reconstructed": check_tetra(tetra),
            "projection_gates_passed": check_gates(gates),
            "quality_repairs_logged": check_repairs(repairs, gates),
            "rzs_regulated_projection": check_rzs(payload),
            "reflections_written": len(reflections) >= 2,
            "handoff_written": len(handoffs) >= 1 and int(handoffs[-1].get("regge_projection_ready") or 0) == 1,
            "semantic_memory_written": semantic >= 1,
            "episode_written": episodes >= 1,
            "prior_data_still_present": prior_present,
            "protected_sources_unchanged": protected_ok,
        }

        ok = all(checks.values())
        gate_passed = sum(1 for g in gates if int(g.get("passed") or 0) == 1)
        stable_tetra = sum(1 for t in tetra if int(t.get("stable") or 0) == 1)
        inferred_edges = sum(1 for e in edges if int(e.get("inferred") or 0) == 1)
        result = {
            "ok": ok,
            "session_id": session_id,
            "checks": checks,
            "counts": {
                "signals": len(signals),
                "nodes": len(nodes),
                "edges": len(edges),
                "inferred_edges": inferred_edges,
                "tetra": len(tetra),
                "stable_tetra": stable_tetra,
                "gates": len(gates),
                "gate_passed": gate_passed,
                "repairs": len(repairs),
                "reflections": len(reflections),
                "handoffs": len(handoffs),
                "semantic": semantic,
                "episodes": episodes,
            },
            "gate_keys": [str(g.get("gate_key") or "") for g in gates],
            "rzs_decision": payload.get("rzs_decision"),
            "sigma_before": payload.get("sigma_before"),
            "sigma_after": payload.get("sigma_after"),
            "regge_srmse": payload.get("regge_srmse"),
            "payload": payload if details else {},
        }
        return result


def print_report(result: dict[str, Any], details: bool = False) -> None:
    print("DARWIN v49.33 - DIAGNOSTICO RZS/ELCL REGGE GEOMETRY")
    print("=" * 78)
    print(f"- sessao: {result.get('session_id')}")
    counts = result.get("counts", {})
    print(
        f"- sinais={counts.get('signals')} nos={counts.get('nodes')} arestas={counts.get('edges')} "
        f"inferidas={counts.get('inferred_edges')}"
    )
    print(
        f"- K4 estaveis={counts.get('stable_tetra')}/{counts.get('tetra')} "
        f"gates={counts.get('gate_passed')}/{counts.get('gates')} repairs={counts.get('repairs')}"
    )
    print(
        f"- sRMSE={number(result.get('regge_srmse'), 0.0):.3f} | "
        f"RZS={result.get('rzs_decision')} "
        f"sigma {number(result.get('sigma_before'), 0.0):.3f}->{number(result.get('sigma_after'), 0.0):.3f}"
    )
    print()
    labels = {
        "tables_exist": "tabelas v49.33 existem",
        "completed_session": "sessao completa e pronta",
        "article_signals_loaded": "sinais do artigo carregados",
        "relational_graph_projected": "grafo relacional projetado",
        "k4_tetrahedra_reconstructed": "K4/tetraedros reconstruidos",
        "projection_gates_passed": "gates de projecao passaram",
        "quality_repairs_logged": "reparos de qualidade registrados",
        "rzs_regulated_projection": "RZS regulou a projecao",
        "reflections_written": "reflexoes escritas",
        "handoff_written": "handoff escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
        "protected_sources_unchanged": "fontes anteriores preservadas",
    }
    for key, passed in result.get("checks", {}).items():
        print(f"- {labels.get(key, key)}: {'OK' if passed else 'FALHOU'}")
    print()
    print(f"Resultado final: {'OK' if result.get('ok') else 'FALHOU'}")
    print("Leitura: Darwin converteu grafo relacional em geometria Regge operacional com ELCL, K4, gates, reparo e RZS.")
    if details:
        print("\nJSON:")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.33 RZS/ELCL Regge Geometry")
    parser.add_argument("--details", action="store_true", help="mostra JSON detalhado")
    args = parser.parse_args()
    result = diagnose(details=args.details)
    print_report(result, args.details)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
