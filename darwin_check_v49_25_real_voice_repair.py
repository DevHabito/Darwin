from __future__ import annotations

"""
DARWIN v49.25 - Diagnostico do Real Voice Repair Wizard

Uso:
    py darwin_check_v49_25_real_voice_repair.py
    py darwin_check_v49_25_real_voice_repair.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

VR_SESSIONS = "voice_repair_sessions_v49_25"
VR_CHECKS = "voice_repair_checks_v49_25"
VR_STEPS = "voice_repair_steps_v49_25"
VR_LIVE_TESTS = "voice_repair_live_tests_v49_25"
VR_RESULTS = "voice_repair_results_v49_25"

SOURCE = "darwin_real_voice_repair_wizard_v49_25"
EXPECTED_PHASES = [
    "load_v49_24_voice_blocker",
    "inspect_windows_speech",
    "inspect_audio_input",
    "verify_darwin_voice_modules",
    "prepare_live_first_words_test",
    "write_repair_plan",
]
EXPECTED_CHECKS = {
    "v49_24_voice_blocker_seen",
    "system_speech_assembly",
    "speech_synthesis_available",
    "installed_recognizers",
    "pt_br_recognizer",
    "default_audio_input_bind",
    "voice_repair_files_present",
    "voice_presence_self_test",
    "first_words_rehearsal",
    "live_first_words_test_prepared",
}
VALID_STATUS = {"pass", "warn", "fail"}
VALID_LIVE_STATUS = {"prepared", "blocked_no_recognizer", "completed", "partial", "no_words_heard", "failed"}
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
        if "expected_words_json" in item:
            item["expected_words"] = pj(str(item.get("expected_words_json") or "[]"), [])
        if "recognized_words_json" in item:
            item["recognized_words"] = pj(str(item.get("recognized_words_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, VR_SESSIONS)
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
        (SOURCE, f"real_voice_repair_v49_25:{session_id}"),
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
        (SOURCE, f"real_voice_repair:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def v49_24_source_valid(conn: sqlite3.Connection, session_row: dict[str, Any]) -> bool:
    source_id = str(session_row.get("source_action_session_id") or "")
    if not source_id or not table_exists(conn, "desire_action_results_v49_24"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM desire_action_results_v49_24
        WHERE session_id=?
        """,
        (source_id,),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


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
        if not str(step.get("repair_action") or ""):
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
    status_by_key = {str(c.get("check_key") or ""): str(c.get("status") or "") for c in checks}
    must_pass = {
        "v49_24_voice_blocker_seen",
        "system_speech_assembly",
        "speech_synthesis_available",
        "voice_repair_files_present",
        "voice_presence_self_test",
        "first_words_rehearsal",
        "live_first_words_test_prepared",
    }
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
    return all(status_by_key.get(key) == "pass" for key in must_pass)


def live_tests_ok(live_tests: list[dict[str, Any]], results: list[dict[str, Any]]) -> bool:
    if not live_tests:
        return False
    latest_result = results[-1] if results else {}
    recognizer_count = int(latest_result.get("recognizer_count") or 0)
    for item in live_tests:
        if str(item.get("status") or "") not in VALID_LIVE_STATUS:
            return False
        expected = item.get("expected_words", [])
        if not isinstance(expected, list) or not {"mamae", "papai", "felipe", "darwin"}.issubset(set(str(x).lower() for x in expected)):
            return False
    statuses = {str(item.get("status") or "") for item in live_tests}
    if recognizer_count == 0:
        return "blocked_no_recognizer" in statuses
    return bool(statuses.intersection({"prepared", "completed", "partial", "no_words_heard"}))


def result_ok(results: list[dict[str, Any]], checks: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    item = results[-1]
    readiness = float(item.get("readiness_score") or 0.0)
    recognizer_count = int(item.get("recognizer_count") or 0)
    ready = int(item.get("real_voice_ready") or 0) == 1
    if readiness <= 0.0 or readiness > 1.0:
        return False
    if not str(item.get("next_action") or ""):
        return False
    if not ready and not str(item.get("blocked_by") or ""):
        return False
    if recognizer_count == 0 and str(item.get("blocked_by") or "") != "windows_speech_recognizer_missing_or_unavailable":
        return False
    payload = item.get("payload", {})
    return EXPECTED_CHECKS.issubset(set(str(k) for k in payload.get("check_keys", [])))


def rzs_influenced(steps: list[dict[str, Any]], checks: list[dict[str, Any]]) -> bool:
    decisions = {str(x.get("rzs_decision") or "") for x in steps + checks}
    return bool(decisions) and decisions.issubset(VALID_RZS) and any(d != "continue" for d in decisions)


def prior_data_present(conn: sqlite3.Connection) -> bool:
    required = [
        "desire_action_results_v49_24",
        "voice_presence_sessions_v49_9",
        "voice_first_word_sessions_v49_10",
    ]
    return all(table_exists(conn, table) for table in required)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, session_row = latest_completed_session(conn)
    steps = rows(conn, VR_STEPS, " WHERE session_id=?", (session_id,)) if session_id else []
    checks = rows(conn, VR_CHECKS, " WHERE session_id=?", (session_id,)) if session_id else []
    live_tests = rows(conn, VR_LIVE_TESTS, " WHERE session_id=?", (session_id,)) if session_id else []
    results = rows(conn, VR_RESULTS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = session_row.get("payload", {}) if session_row else {}
    latest_result = results[-1] if results else {}
    checks_map = {
        "tables_exist": all(table_exists(conn, t) for t in (VR_SESSIONS, VR_CHECKS, VR_STEPS, VR_LIVE_TESTS, VR_RESULTS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "v49_24_source_valid": v49_24_source_valid(conn, session_row) if session_id else False,
        "steps_causal_order": steps_ok(steps),
        "diagnostic_checks_written": checks_ok(checks),
        "live_test_prepared": live_tests_ok(live_tests, results),
        "result_written": result_ok(results, checks),
        "rzs_influenced_repair": rzs_influenced(steps, checks),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "prior_data_still_present": prior_data_present(conn),
    }
    return {
        "ok": all(checks_map.values()),
        "session_id": session_id,
        "source_action_session_id": str(session_row.get("source_action_session_id") or "") if session_row else "",
        "checks": checks_map,
        "counts": {
            "steps": len(steps),
            "diagnostics": len(checks),
            "live_tests": len(live_tests),
            "results": len(results),
        },
        "phases": [str(s.get("phase") or "") for s in steps],
        "rzs_decisions": sorted({str(x.get("rzs_decision") or "") for x in steps + checks}),
        "diagnostic_statuses": {str(c.get("check_key") or ""): str(c.get("status") or "") for c in checks},
        "live_statuses": [str(t.get("status") or "") for t in live_tests],
        "result": {
            "recognizer_count": int(latest_result.get("recognizer_count") or 0) if latest_result else 0,
            "pt_br_available": bool(int(latest_result.get("pt_br_available") or 0)) if latest_result else False,
            "default_audio_ok": bool(int(latest_result.get("default_audio_ok") or 0)) if latest_result else False,
            "real_voice_ready": bool(int(latest_result.get("real_voice_ready") or 0)) if latest_result else False,
            "readiness_score": round(float(latest_result.get("readiness_score") or 0.0), 3) if latest_result else 0.0,
            "blocked_by": latest_result.get("blocked_by", ""),
            "next_action": latest_result.get("next_action", ""),
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.25 - DIAGNOSTICO REAL VOICE REPAIR")
    print("=" * 68)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    print(f"- fonte v49.24: {report['source_action_session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- passos={c['steps']} diagnosticos={c['diagnostics']} live_tests={c['live_tests']} resultados={c['results']}")
    print(f"- fases: {', '.join(report['phases']) if report['phases'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    result = report["result"]
    print(f"- recognizers={result['recognizer_count']} pt-BR={result['pt_br_available']} microfone={result['default_audio_ok']}")
    print(f"- voz real pronta: {result['real_voice_ready']} readiness={result['readiness_score']}")
    if result["blocked_by"]:
        print(f"- bloqueio: {result['blocked_by']}")
    print(f"- proxima acao: {result['next_action'] or 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.25 existem",
        "completed_session": "sessao completa encontrada",
        "v49_24_source_valid": "fonte v49.24 valida",
        "steps_causal_order": "passos em ordem causal",
        "diagnostic_checks_written": "diagnosticos obrigatorios escritos",
        "live_test_prepared": "teste real de primeiras palavras preparado",
        "result_written": "resultado e plano escritos",
        "rzs_influenced_repair": "RZS influenciou reparo",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin tem reparador auditavel para destravar voz real no Windows.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o reparo de voz como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.25 Real Voice Repair checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
