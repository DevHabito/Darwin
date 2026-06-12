from __future__ import annotations

"""
DARWIN v49.15 - Diagnostico da auto-reflexao

Uso:
    py darwin_check_v49_15_self_reflection.py
    py darwin_check_v49_15_self_reflection.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

REFL_SESSIONS = "mind_reflection_sessions_v49_15"
REFL_FINDINGS = "mind_reflection_findings_v49_15"
REFL_GOALS = "mind_learning_goals_v49_15"
REFL_REHEARSALS = "mind_goal_rehearsals_v49_15"


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


def rows(conn: sqlite3.Connection, table: str, reflection_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if reflection_id is not None:
        where = " WHERE reflection_id=?"
        params = (reflection_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        if "evidence_json" in item:
            item["evidence"] = pj(str(item.get("evidence_json") or "{}"))
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, REFL_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "reflection_complete" and r.get("payload", {}).get("reflection_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["reflection_id"]), row


def semantic_written(conn: sqlite3.Connection, reflection_id: str) -> bool:
    if not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source='darwin_self_reflection_v49_15'
          AND key=?
        """,
        (f"self_reflection_v49_15:{reflection_id}",),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_written(conn: sqlite3.Connection, reflection_id: str) -> bool:
    if not table_exists(conn, "episodes"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_self_reflection_v49_15'
          AND context=?
        """,
        (f"self_reflection:{reflection_id}",),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    reflection_id, complete_row = latest_completed(conn)
    payload = complete_row.get("payload", {}) if complete_row else {}
    findings = rows(conn, REFL_FINDINGS, reflection_id) if reflection_id else []
    goals = rows(conn, REFL_GOALS, reflection_id) if reflection_id else []
    rehearsals = rows(conn, REFL_REHEARSALS, reflection_id) if reflection_id else []
    kinds = {str(f.get("finding_kind")) for f in findings if f.get("finding_kind")}
    goal_kinds = {str(g.get("goal_kind")) for g in goals if g.get("goal_kind")}
    rzs_decisions = {str(g.get("rzs_decision")) for g in goals if g.get("rzs_decision")}
    priorities = [float(g.get("priority") or 0.0) for g in goals]
    has_voice_goal = "repair_real_voice_input" in goal_kinds or any("voice" in str(g.get("module_key")) for g in goals)

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (REFL_SESSIONS, REFL_FINDINGS, REFL_GOALS, REFL_REHEARSALS)),
        "completed_reflection": bool(reflection_id),
        "graph_measured": int(payload.get("graph_nodes") or 0) >= 80 and int(payload.get("graph_edges") or 0) >= 80,
        "findings_created": len(findings) >= 5 and {"strength", "gap"}.issubset(kinds),
        "goals_created": len(goals) >= 3,
        "goals_have_rzs": bool(rzs_decisions) and all(float(g.get("sigma_before") or 0.0) > 0.0 for g in goals),
        "priorities_ranked": priorities == sorted(priorities, reverse=True),
        "rehearsals_created": len(rehearsals) >= len(goals) * 3,
        "voice_gap_considered": has_voice_goal,
        "semantic_memory_written": semantic_written(conn, reflection_id) if reflection_id else False,
        "episode_written": episode_written(conn, reflection_id) if reflection_id else False,
    }
    return {
        "ok": all(checks.values()),
        "reflection_id": reflection_id,
        "checks": checks,
        "counts": {
            "findings": len(findings),
            "goals": len(goals),
            "rehearsals": len(rehearsals),
            "graph_nodes": int(payload.get("graph_nodes") or 0),
            "graph_edges": int(payload.get("graph_edges") or 0),
        },
        "finding_kinds": sorted(kinds),
        "goal_kinds": sorted(goal_kinds),
        "rzs_decisions": sorted(rzs_decisions),
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.15 - DIAGNOSTICO SELF REFLECTION")
    print("=" * 58)
    print(f"- reflexao: {report['reflection_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- grafo={c['graph_nodes']} nos/{c['graph_edges']} arestas")
    print(f"- achados={c['findings']} metas={c['goals']} ensaios={c['rehearsals']}")
    print(f"- tipos achado: {', '.join(report['finding_kinds']) if report['finding_kinds'] else 'nenhum'}")
    print(f"- metas: {', '.join(report['goal_kinds']) if report['goal_kinds'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.15 existem",
        "completed_reflection": "reflexao completa encontrada",
        "graph_measured": "grafo medido",
        "findings_created": "achados criados",
        "goals_created": "metas criadas",
        "goals_have_rzs": "metas reguladas por RZS",
        "priorities_ranked": "prioridades ordenadas",
        "rehearsals_created": "ensaios de metas criados",
        "voice_gap_considered": "lacuna de voz considerada",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin inspeciona o proprio grafo e escolhe proximas metas de treino.")
    else:
        print("Leitura: ainda falta evidencia para aceitar auto-reflexao como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.15 Self Reflection checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
