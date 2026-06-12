from __future__ import annotations

"""
DARWIN v49.21 - Diagnostico do Wake & Life Loop Core

Uso:
    py darwin_check_v49_21_wake_loop.py
    py darwin_check_v49_21_wake_loop.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

WK_SESSIONS = "wake_sessions_v49_21"
WK_PHASES = "wake_phase_events_v49_21"
WK_RESOLUTIONS = "wake_commitment_resolutions_v49_21"
WK_LIFE_CYCLES = "wake_life_cycles_v49_21"
WK_HANDOFFS = "wake_next_handoff_v49_21"

SOURCE = "darwin_wake_life_loop_v49_21"

EXPECTED_PHASES = [
    "wake_start",
    "load_sleep_plan",
    "restore_identity",
    "fulfill_commitment",
    "run_life_cycle",
    "evaluate_wake_state",
    "handoff_next_sleep",
]

VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    return parsed


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        if "evidence_json" in item:
            item["evidence"] = pj(str(item.get("evidence_json") or "{}"), {})
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, WK_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "session_complete" and r.get("payload", {}).get("session_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["session_id"]), row


def semantic_written(conn: sqlite3.Connection, session_id: str) -> bool:
    if not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source=? AND key=?
        """,
        (SOURCE, f"wake_life_loop_v49_21:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_written(conn: sqlite3.Connection, session_id: str) -> bool:
    if not table_exists(conn, "episodes"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module=? AND context=?
        """,
        (SOURCE, f"wake_life_loop:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def phases_ok(phases: list[dict[str, Any]]) -> bool:
    if len(phases) != len(EXPECTED_PHASES):
        return False
    names = [str(p.get("phase") or "") for p in phases]
    indices = [int(p.get("phase_index") or 0) for p in phases]
    if names != EXPECTED_PHASES:
        return False
    if indices != list(range(1, len(EXPECTED_PHASES) + 1)):
        return False
    for phase in phases:
        if str(phase.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(phase.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(phase.get("sigma_after") or 0.0) <= 0.0:
            return False
        if float(phase.get("energy_after") or 0.0) < float(phase.get("energy_before") or 0.0):
            return False
        if not str(phase.get("focus_key") or ""):
            return False
        if not str(phase.get("cognitive_action") or ""):
            return False
    return True


def sleep_plan_consumed(conn: sqlite3.Connection, complete_row: dict[str, Any], handoffs: list[dict[str, Any]]) -> bool:
    if not table_exists(conn, "sleep_wake_plans_v49_20"):
        return False
    payload = complete_row.get("payload", {}) if complete_row else {}
    source_sleep = str(complete_row.get("source_sleep_session_id") or payload.get("source_sleep_session_id") or "")
    source_plan = str(payload.get("source_wake_plan_id") or "")
    if handoffs:
        source_plan = source_plan or str(handoffs[-1].get("source_wake_plan_id") or "")
    if not source_sleep or not source_plan:
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM sleep_wake_plans_v49_20
        WHERE session_id=? AND wake_plan_id=?
        """,
        (source_sleep, source_plan),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def resolution_ok(resolutions: list[dict[str, Any]]) -> bool:
    if not resolutions:
        return False
    item = resolutions[-1]
    status = str(item.get("resolution_status") or "")
    evidence = item.get("evidence", {})
    if "fulfilled" not in status and "advanced" not in status:
        return False
    if float(item.get("fulfilled_score") or 0.0) < 0.65:
        return False
    if not str(item.get("reviewed_goal_id") or ""):
        return False
    if not evidence.get("reviewed_primary_goal"):
        return False
    return bool(str(item.get("commitment_text") or ""))


def life_cycles_ok(cycles: list[dict[str, Any]]) -> bool:
    if len(cycles) < 5:
        return False
    indices = [int(c.get("cycle_index") or 0) for c in cycles]
    if indices != list(range(1, len(cycles) + 1)):
        return False
    keys = {str(c.get("cycle_key") or "") for c in cycles}
    if "review_primary_goal" not in keys:
        return False
    if "prepare_next_agency_cycle" not in keys:
        return False
    for cycle in cycles:
        if int(cycle.get("completed") or 0) != 1:
            return False
        if str(cycle.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(cycle.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(cycle.get("sigma_after") or 0.0) <= 0.0:
            return False
        if not str(cycle.get("action_taken") or "") or not str(cycle.get("result_summary") or ""):
            return False
    return True


def handoff_ok(handoffs: list[dict[str, Any]]) -> bool:
    if not handoffs:
        return False
    item = handoffs[-1]
    if not str(item.get("next_recommended_core") or ""):
        return False
    if not str(item.get("next_action") or ""):
        return False
    if int(item.get("agency_ready") or 0) != 1:
        return False
    if int(item.get("sleep_ready") or 0) != 1:
        return False
    if float(item.get("confidence") or 0.0) < 0.65:
        return False
    return bool(str(item.get("source_wake_plan_id") or ""))


def rzs_influenced(phases: list[dict[str, Any]], cycles: list[dict[str, Any]]) -> bool:
    decisions = [str(p.get("rzs_decision") or "") for p in phases] + [str(c.get("rzs_decision") or "") for c in cycles]
    if not decisions:
        return False
    if any(d not in VALID_RZS for d in decisions):
        return False
    return any(d != "continue" for d in decisions)


def v49_20_present(conn: sqlite3.Connection) -> bool:
    required = ["sleep_wake_plans_v49_20", "sleep_consolidations_v49_20"]
    if not all(table_exists(conn, t) for t in required):
        return False
    row = conn.execute("SELECT COUNT(*) AS n FROM sleep_wake_plans_v49_20").fetchone()
    return bool(row and int(row["n"]) >= 1)


def v49_19_present(conn: sqlite3.Connection) -> bool:
    required = ["agency_commitments_v49_19", "agency_outcomes_v49_19"]
    if not all(table_exists(conn, t) for t in required):
        return False
    row = conn.execute("SELECT COUNT(*) AS n FROM agency_commitments_v49_19").fetchone()
    return bool(row and int(row["n"]) >= 1)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    phases = rows(conn, WK_PHASES, " WHERE session_id=?", (session_id,)) if session_id else []
    resolutions = rows(conn, WK_RESOLUTIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    cycles = rows(conn, WK_LIFE_CYCLES, " WHERE session_id=?", (session_id,)) if session_id else []
    handoffs = rows(conn, WK_HANDOFFS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    phase_decisions = sorted({str(p.get("rzs_decision") or "") for p in phases})
    cycle_decisions = sorted({str(c.get("rzs_decision") or "") for c in cycles})
    latest_resolution = resolutions[-1] if resolutions else {}
    latest_handoff = handoffs[-1] if handoffs else {}

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (WK_SESSIONS, WK_PHASES, WK_RESOLUTIONS, WK_LIFE_CYCLES, WK_HANDOFFS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "phases_in_order": phases_ok(phases),
        "sleep_plan_consumed": sleep_plan_consumed(conn, complete_row, handoffs) if session_id else False,
        "commitment_resolution_written": resolution_ok(resolutions),
        "life_cycles_written": life_cycles_ok(cycles),
        "handoff_written": handoff_ok(handoffs),
        "rzs_causally_influenced": rzs_influenced(phases, cycles),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "v49_20_data_still_present": v49_20_present(conn),
        "v49_19_data_still_present": v49_19_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "phases": len(phases),
            "resolutions": len(resolutions),
            "life_cycles": len(cycles),
            "handoffs": len(handoffs),
        },
        "phase_names": [str(p.get("phase") or "") for p in phases],
        "cycle_keys": [str(c.get("cycle_key") or "") for c in cycles],
        "rzs_decisions": sorted(set(phase_decisions + cycle_decisions)),
        "resolution": {
            "status": latest_resolution.get("resolution_status", ""),
            "fulfilled_score": round(float(latest_resolution.get("fulfilled_score") or 0.0), 3) if latest_resolution else 0.0,
            "reviewed_goal_id": latest_resolution.get("reviewed_goal_id", ""),
            "source_commitment_id": latest_resolution.get("source_commitment_id", ""),
        },
        "handoff": {
            "next_recommended_core": latest_handoff.get("next_recommended_core", ""),
            "next_action": latest_handoff.get("next_action", ""),
            "confidence": round(float(latest_handoff.get("confidence") or 0.0), 3) if latest_handoff else 0.0,
            "agency_ready": bool(int(latest_handoff.get("agency_ready") or 0)) if latest_handoff else False,
            "sleep_ready": bool(int(latest_handoff.get("sleep_ready") or 0)) if latest_handoff else False,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.21 - DIAGNOSTICO WAKE & LIFE LOOP")
    print("=" * 62)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- fases={c['phases']} resolucoes={c['resolutions']} ciclos={c['life_cycles']} handoffs={c['handoffs']}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print(f"- compromisso: {report['resolution']['status'] or 'nenhum'} score={report['resolution']['fulfilled_score']}")
    print(f"- handoff: {report['handoff']['next_action'] or 'nenhum'} confianca={report['handoff']['confidence']}")
    print()
    labels = {
        "tables_exist": "tabelas v49.21 existem",
        "completed_session": "sessao completa encontrada",
        "phases_in_order": "fases do acordar em ordem",
        "sleep_plan_consumed": "plano v49.20 foi consumido",
        "commitment_resolution_written": "compromisso foi resolvido",
        "life_cycles_written": "ciclos acordados escritos",
        "handoff_written": "handoff proximo escrito",
        "rzs_causally_influenced": "RZS influenciou decisoes",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "v49_20_data_still_present": "dados v49.20 ainda presentes",
        "v49_19_data_still_present": "dados v49.19 ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin acordou do sono v49.20, cumpriu o compromisso e deixou agencia pronta.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o acordar como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.21 Wake & Life Loop checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
