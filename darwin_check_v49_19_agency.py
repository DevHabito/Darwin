from __future__ import annotations

"""
DARWIN v49.19 - Diagnostico do Intention & Agency Core

Uso:
    py darwin_check_v49_19_agency.py
    py darwin_check_v49_19_agency.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

AG_SESSIONS = "agency_sessions_v49_19"
AG_INTENTIONS = "agency_intentions_v49_19"
AG_STEPS = "agency_action_steps_v49_19"
AG_OUTCOMES = "agency_outcomes_v49_19"
AG_COMMITMENTS = "agency_commitments_v49_19"
SOURCE = "darwin_intention_agency_core_v49_19"

EXPECTED_PHASES = [
    "wake_identity",
    "recall_autobiography",
    "resolve_intention",
    "execute_internal_action",
    "evaluate_prediction",
    "commit_next",
]


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback


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
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, AG_SESSIONS)
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
        (SOURCE, f"agency_v49_19:{session_id}"),
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
        (SOURCE, f"agency:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def intention_ok(intentions: list[dict[str, Any]]) -> bool:
    if not intentions:
        return False
    item = intentions[-1]
    if not str(item.get("source_identity_id") or ""):
        return False
    if float(item.get("priority") or 0.0) <= 0.0:
        return False
    if float(item.get("autonomy_score") or 0.0) < 0.60:
        return False
    if float(item.get("expected_value") or 0.0) <= 0.0:
        return False
    if float(item.get("sigma_before") or 0.0) <= 0.0 or float(item.get("sigma_after") or 0.0) <= 0.0:
        return False
    return True


def rzs_causal(intentions: list[dict[str, Any]]) -> bool:
    if not intentions:
        return False
    item = intentions[-1]
    decision = str(item.get("rzs_decision") or "")
    candidate = str(item.get("candidate_action") or "")
    selected = str(item.get("selected_action") or "")
    if decision == "continue":
        return candidate == selected
    if decision == "replay_memory":
        return selected.startswith("recall_autobiographical_sequence_before_")
    if decision == "narrow_focus":
        return selected.startswith("narrow_intention_before_")
    if decision == "consolidate":
        return selected == "consolidate_intention_before_action"
    if decision == "pause_for_stability":
        return selected == "pause_intention_for_stability"
    return False


def steps_ok(steps: list[dict[str, Any]]) -> bool:
    if len(steps) < len(EXPECTED_PHASES):
        return False
    phases = [str(s.get("phase") or "") for s in steps[: len(EXPECTED_PHASES)]]
    indices = [int(s.get("step_index") or 0) for s in steps]
    if phases != EXPECTED_PHASES:
        return False
    if indices != list(range(1, len(steps) + 1)):
        return False
    for step in steps:
        if int(step.get("completed") or 0) != 1:
            return False
        if float(step.get("sigma_before") or 0.0) <= 0.0 or float(step.get("sigma_after") or 0.0) <= 0.0:
            return False
    return True


def outcome_ok(outcomes: list[dict[str, Any]]) -> bool:
    if not outcomes:
        return False
    item = outcomes[-1]
    if float(item.get("success_score") or 0.0) < 0.65:
        return False
    if int(item.get("prediction_checked") or 0) != 1:
        return False
    if int(item.get("prediction_matched") or 0) != 1:
        return False
    if not str(item.get("lesson") or ""):
        return False
    return True


def commitment_ok(commitments: list[dict[str, Any]]) -> bool:
    if not commitments:
        return False
    item = commitments[-1]
    if str(item.get("status") or "") != "active":
        return False
    if float(item.get("confidence") or 0.0) < 0.55:
        return False
    return bool(str(item.get("commitment_text") or "")) and bool(str(item.get("next_trigger") or ""))


def v49_18_present(conn: sqlite3.Connection) -> bool:
    required = ["autobiography_identity_state_v49_18", "autobiography_next_predictions_v49_18"]
    if not all(table_exists(conn, t) for t in required):
        return False
    row = conn.execute("SELECT COUNT(*) AS n FROM autobiography_identity_state_v49_18").fetchone()
    return bool(row and int(row["n"]) >= 1)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    intentions = rows(conn, AG_INTENTIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    intention_id = str(intentions[-1].get("intention_id")) if intentions else ""
    steps = rows(conn, AG_STEPS, " WHERE session_id=? AND intention_id=?", (session_id, intention_id)) if intention_id else []
    outcomes = rows(conn, AG_OUTCOMES, " WHERE session_id=? AND intention_id=?", (session_id, intention_id)) if intention_id else []
    commitments = rows(conn, AG_COMMITMENTS, " WHERE session_id=? AND intention_id=?", (session_id, intention_id)) if intention_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    phases = [str(s.get("phase")) for s in steps]
    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (AG_SESSIONS, AG_INTENTIONS, AG_STEPS, AG_OUTCOMES, AG_COMMITMENTS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "intention_written": intention_ok(intentions),
        "rzs_causal_effect": rzs_causal(intentions),
        "steps_completed_in_order": steps_ok(steps),
        "internal_action_executed": "execute_internal_action" in phases and any(str(s.get("action_taken") or "") for s in steps if s.get("phase") == "execute_internal_action"),
        "prediction_evaluated": "evaluate_prediction" in phases and outcome_ok(outcomes),
        "commitment_written": commitment_ok(commitments),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "v49_18_data_still_present": v49_18_present(conn),
    }
    latest_intention = intentions[-1] if intentions else {}
    latest_outcome = outcomes[-1] if outcomes else {}
    latest_commitment = commitments[-1] if commitments else {}
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "intentions": len(intentions),
            "steps": len(steps),
            "outcomes": len(outcomes),
            "commitments": len(commitments),
        },
        "intention": {
            "candidate_action": latest_intention.get("candidate_action", ""),
            "selected_action": latest_intention.get("selected_action", ""),
            "autonomy_score": round(float(latest_intention.get("autonomy_score") or 0.0), 3) if latest_intention else 0.0,
            "expected_value": round(float(latest_intention.get("expected_value") or 0.0), 3) if latest_intention else 0.0,
            "rzs_decision": latest_intention.get("rzs_decision", ""),
            "sigma_before": round(float(latest_intention.get("sigma_before") or 0.0), 3) if latest_intention else 0.0,
            "sigma_after": round(float(latest_intention.get("sigma_after") or 0.0), 3) if latest_intention else 0.0,
        },
        "phases": phases,
        "outcome": {
            "success_score": round(float(latest_outcome.get("success_score") or 0.0), 3) if latest_outcome else 0.0,
            "stability_delta": round(float(latest_outcome.get("stability_delta") or 0.0), 3) if latest_outcome else 0.0,
            "prediction_checked": bool(latest_outcome.get("prediction_checked")) if latest_outcome else False,
            "prediction_matched": bool(latest_outcome.get("prediction_matched")) if latest_outcome else False,
        },
        "commitment": {
            "text": latest_commitment.get("commitment_text", ""),
            "trigger": latest_commitment.get("next_trigger", ""),
            "status": latest_commitment.get("status", ""),
            "confidence": round(float(latest_commitment.get("confidence") or 0.0), 3) if latest_commitment else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.19 - DIAGNOSTICO AGENCY CORE")
    print("=" * 58)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- intencoes={c['intentions']} passos={c['steps']} outcomes={c['outcomes']} compromissos={c['commitments']}")
    intent = report["intention"]
    print(f"- candidata: {intent['candidate_action'] or 'nenhuma'}")
    print(f"- selecionada: {intent['selected_action'] or 'nenhuma'}")
    print(f"- RZS: {intent['rzs_decision']} sigma {intent['sigma_before']}->{intent['sigma_after']}")
    print(f"- sucesso: {report['outcome']['success_score']} previsao={report['outcome']['prediction_matched']}")
    print()
    labels = {
        "tables_exist": "tabelas v49.19 existem",
        "completed_session": "sessao completa encontrada",
        "intention_written": "intencao escrita",
        "rzs_causal_effect": "RZS teve efeito causal",
        "steps_completed_in_order": "passos executados em ordem",
        "internal_action_executed": "acao interna executada",
        "prediction_evaluated": "previsao avaliada",
        "commitment_written": "compromisso escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "v49_18_data_still_present": "dados v49.18 ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin formou intencao, agiu internamente e registrou compromisso futuro.")
    else:
        print("Leitura: ainda falta evidencia para aceitar agencia interna como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.19 Agency checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
