from __future__ import annotations

"""
DARWIN v49.24 - Diagnostico do Desire-to-Action Core

Uso:
    py darwin_check_v49_24_desire_action.py
    py darwin_check_v49_24_desire_action.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

DA_SESSIONS = "desire_action_sessions_v49_24"
DA_SOURCES = "desire_action_sources_v49_24"
DA_CHECKS = "desire_action_diagnostic_checks_v49_24"
DA_STEPS = "desire_action_steps_v49_24"
DA_RESULTS = "desire_action_results_v49_24"

SOURCE = "darwin_desire_action_core_v49_24"
EXPECTED_PHASES = [
    "desire_load",
    "select_action",
    "inspect_voice_history",
    "run_recognizer_probe",
    "run_simulated_voice_regression",
    "run_first_words_rehearsal",
    "build_next_voice_plan",
]
EXPECTED_CHECKS = {
    "voice_files_present",
    "voice_tables_present",
    "first_words_tables_present",
    "desire_points_to_voice",
    "windows_speech_recognizers",
    "default_audio_input_bind",
    "voice_presence_self_test",
    "first_words_rehearsal",
}
VALID_STATUS = {"pass", "warn", "fail"}
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
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, DA_SESSIONS)
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
        (SOURCE, f"desire_action_v49_24:{session_id}"),
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
        (SOURCE, f"desire_action:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def desire_source_valid(conn: sqlite3.Connection, session_row: dict[str, Any]) -> bool:
    source_id = str(session_row.get("source_desire_session_id") or "")
    if not source_id or not table_exists(conn, "desire_dialogue_state_v49_23"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM desire_dialogue_state_v49_23
        WHERE session_id=?
        """,
        (source_id,),
    ).fetchone()
    if row and int(row["n"]) >= 1:
        return True
    if not table_exists(conn, "desire_dialogue_sessions_v49_23"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM desire_dialogue_sessions_v49_23
        WHERE session_id=?
        """,
        (source_id,),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def sources_ok(sources: list[dict[str, Any]]) -> bool:
    if len(sources) < 3:
        return False
    kinds = {str(s.get("source_kind") or "") for s in sources}
    required = {"desire_state", "voice_history", "first_words_history"}
    if not required.issubset(kinds):
        return False
    for item in sources:
        if not str(item.get("source_table") or ""):
            return False
        if not str(item.get("summary") or ""):
            return False
        if float(item.get("confidence") or 0.0) <= 0.0:
            return False
    return True


def steps_ok(steps: list[dict[str, Any]]) -> bool:
    if len(steps) != len(EXPECTED_PHASES):
        return False
    phases = [str(s.get("phase") or "") for s in steps]
    if phases != EXPECTED_PHASES:
        return False
    indices = [int(s.get("step_index") or 0) for s in steps]
    if indices != list(range(1, len(EXPECTED_PHASES) + 1)):
        return False
    for step in steps:
        if int(step.get("completed") or 0) != 1:
            return False
        if not str(step.get("cognitive_action") or ""):
            return False
        if not str(step.get("result_summary") or ""):
            return False
        if str(step.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(step.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(step.get("sigma_after") or 0.0) <= 0.0:
            return False
    return True


def checks_ok(checks: list[dict[str, Any]]) -> bool:
    if len(checks) < len(EXPECTED_CHECKS):
        return False
    keys = {str(c.get("check_key") or "") for c in checks}
    if not EXPECTED_CHECKS.issubset(keys):
        return False
    pass_count = sum(1 for c in checks if str(c.get("status") or "") == "pass")
    for check in checks:
        if str(check.get("status") or "") not in VALID_STATUS:
            return False
        if str(check.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if not str(check.get("evidence") or ""):
            return False
        if float(check.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(check.get("sigma_after") or 0.0) <= 0.0:
            return False
    must_pass = {
        "voice_presence_self_test",
        "first_words_rehearsal",
        "voice_tables_present",
        "first_words_tables_present",
        "desire_points_to_voice",
    }
    status_by_key = {str(c.get("check_key") or ""): str(c.get("status") or "") for c in checks}
    return pass_count >= 5 and all(status_by_key.get(key) == "pass" for key in must_pass)


def result_ok(results: list[dict[str, Any]], checks: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    item = results[-1]
    readiness = float(item.get("readiness_score") or 0.0)
    executed = int(item.get("executed_checks") or 0)
    passed = int(item.get("passed_checks") or 0)
    warnings = int(item.get("warning_checks") or 0)
    failed = int(item.get("failed_checks") or 0)
    ready = int(item.get("real_voice_ready") or 0) == 1
    if str(item.get("action_family") or "") != "voice_repair":
        return False
    if not str(item.get("selected_desire") or ""):
        return False
    if executed != len(checks) or executed < len(EXPECTED_CHECKS):
        return False
    if passed + warnings + failed != executed:
        return False
    if readiness <= 0.0 or readiness > 1.0:
        return False
    if not str(item.get("next_action") or ""):
        return False
    if not ready and not str(item.get("blocked_by") or ""):
        return False
    payload = item.get("payload", {})
    if not isinstance(payload.get("check_keys", []), list):
        return False
    return EXPECTED_CHECKS.issubset(set(str(k) for k in payload.get("check_keys", [])))


def rzs_influenced(steps: list[dict[str, Any]], checks: list[dict[str, Any]]) -> bool:
    decisions = {str(x.get("rzs_decision") or "") for x in steps + checks}
    return bool(decisions) and decisions.issubset(VALID_RZS) and any(d != "continue" for d in decisions)


def prior_data_present(conn: sqlite3.Connection) -> bool:
    required = [
        "desire_dialogue_state_v49_23",
        "autonomous_preference_decisions_v49_22",
        "voice_presence_sessions_v49_9",
        "voice_first_word_sessions_v49_10",
    ]
    return all(table_exists(conn, table) for table in required)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, session_row = latest_completed_session(conn)
    sources = rows(conn, DA_SOURCES, " WHERE session_id=?", (session_id,)) if session_id else []
    steps = rows(conn, DA_STEPS, " WHERE session_id=?", (session_id,)) if session_id else []
    checks = rows(conn, DA_CHECKS, " WHERE session_id=?", (session_id,)) if session_id else []
    results = rows(conn, DA_RESULTS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = session_row.get("payload", {}) if session_row else {}
    latest_result = results[-1] if results else {}
    check_statuses = {str(c.get("check_key") or ""): str(c.get("status") or "") for c in checks}
    check_evidence = {str(c.get("check_key") or ""): str(c.get("evidence") or "") for c in checks}
    checks_map = {
        "tables_exist": all(table_exists(conn, t) for t in (DA_SESSIONS, DA_SOURCES, DA_CHECKS, DA_STEPS, DA_RESULTS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "desire_source_valid": desire_source_valid(conn, session_row) if session_id else False,
        "sources_written": sources_ok(sources),
        "steps_causal_order": steps_ok(steps),
        "diagnostic_checks_written": checks_ok(checks),
        "result_written": result_ok(results, checks),
        "rzs_influenced_action": rzs_influenced(steps, checks),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "prior_data_still_present": prior_data_present(conn),
    }
    return {
        "ok": all(checks_map.values()),
        "session_id": session_id,
        "source_desire_session_id": str(session_row.get("source_desire_session_id") or "") if session_row else "",
        "checks": checks_map,
        "counts": {
            "sources": len(sources),
            "steps": len(steps),
            "diagnostics": len(checks),
            "results": len(results),
        },
        "phases": [str(s.get("phase") or "") for s in steps],
        "rzs_decisions": sorted({str(x.get("rzs_decision") or "") for x in steps + checks}),
        "diagnostic_statuses": check_statuses,
        "diagnostic_evidence": check_evidence,
        "result": {
            "selected_desire": latest_result.get("selected_desire", ""),
            "action_family": latest_result.get("action_family", ""),
            "real_voice_ready": bool(int(latest_result.get("real_voice_ready") or 0)) if latest_result else False,
            "readiness_score": round(float(latest_result.get("readiness_score") or 0.0), 3) if latest_result else 0.0,
            "passed_checks": int(latest_result.get("passed_checks") or 0) if latest_result else 0,
            "warning_checks": int(latest_result.get("warning_checks") or 0) if latest_result else 0,
            "failed_checks": int(latest_result.get("failed_checks") or 0) if latest_result else 0,
            "blocked_by": latest_result.get("blocked_by", ""),
            "next_action": latest_result.get("next_action", ""),
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.24 - DIAGNOSTICO DESIRE-TO-ACTION")
    print("=" * 68)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    print(f"- desejo fonte: {report['source_desire_session_id'] or 'NENHUM'}")
    c = report["counts"]
    print(f"- fontes={c['sources']} passos={c['steps']} diagnosticos={c['diagnostics']} resultados={c['results']}")
    print(f"- fases: {', '.join(report['phases']) if report['phases'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    result = report["result"]
    print(f"- voz real pronta: {result['real_voice_ready']} readiness={result['readiness_score']}")
    print(f"- proxima acao: {result['next_action'] or 'nenhuma'}")
    if result["blocked_by"]:
        print(f"- bloqueio: {result['blocked_by']}")
    print()
    labels = {
        "tables_exist": "tabelas v49.24 existem",
        "completed_session": "sessao completa encontrada",
        "desire_source_valid": "desejo v49.23 fonte valido",
        "sources_written": "fontes de decisao escritas",
        "steps_causal_order": "passos em ordem causal",
        "diagnostic_checks_written": "diagnosticos obrigatorios escritos",
        "result_written": "resultado e plano seguinte escritos",
        "rzs_influenced_action": "RZS influenciou acao",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin converteu um desejo proprio em acao local auditavel.")
    else:
        print("Leitura: ainda falta evidencia para aceitar desejo->acao como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.24 Desire-to-Action checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
