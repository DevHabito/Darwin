from __future__ import annotations

"""
DARWIN v49.23 - Diagnostico do Desire Dialogue Core

Uso:
    py darwin_check_v49_23_desire_dialogue.py
    py darwin_check_v49_23_desire_dialogue.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

DD_SESSIONS = "desire_dialogue_sessions_v49_23"
DD_TURNS = "desire_dialogue_turns_v49_23"
DD_REFS = "desire_dialogue_memory_refs_v49_23"
DD_STATE = "desire_dialogue_state_v49_23"

SOURCE = "darwin_desire_dialogue_core_v49_23"
EXPECTED_INTENTS = {
    "want_general",
    "music_preference",
    "formula_preference",
    "color_preference",
    "why_preference",
    "uncertainty_probe",
}
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
    session_rows = rows(conn, DD_SESSIONS)
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
        (SOURCE, f"desire_dialogue_v49_23:{session_id}"),
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
        (SOURCE, f"desire_dialogue:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def v49_22_source_valid(conn: sqlite3.Connection, session_row: dict[str, Any]) -> bool:
    source_session = str(session_row.get("source_preference_session_id") or "")
    if not source_session or not table_exists(conn, "autonomous_preference_sessions_v49_22"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM autonomous_preference_sessions_v49_22
        WHERE session_id=?
        """,
        (source_session,),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def turns_ok(turns: list[dict[str, Any]]) -> bool:
    if len(turns) < 6:
        return False
    indices = [int(t.get("turn_index") or 0) for t in turns]
    if indices != list(range(1, len(turns) + 1)):
        return False
    intents = {str(t.get("intent") or "") for t in turns}
    if not EXPECTED_INTENTS.issubset(intents):
        return False
    for turn in turns:
        if int(turn.get("grounded_in_v49_22") or 0) != 1:
            return False
        if not str(turn.get("response_text") or ""):
            return False
        if not str(turn.get("chosen_label") or ""):
            return False
        if str(turn.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(turn.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(turn.get("sigma_after") or 0.0) <= 0.0:
            return False
        if float(turn.get("confidence") or 0.0) < 0.25:
            return False
    return True


def refs_ok(refs: list[dict[str, Any]], turns: list[dict[str, Any]]) -> bool:
    if len(refs) < len(turns):
        return False
    tables = {str(r.get("source_table") or "") for r in refs}
    required = {
        "autonomous_preference_decisions_v49_22",
        "autonomous_preference_candidates_v49_22",
        "autonomous_preference_identity_v49_22",
    }
    if not required.issubset(tables):
        return False
    turn_ids = {str(t.get("dialogue_id") or "") for t in turns}
    ref_turn_ids = {str(r.get("dialogue_id") or "") for r in refs}
    return turn_ids.issubset(ref_turn_ids)


def state_ok(states: list[dict[str, Any]]) -> bool:
    if not states:
        return False
    state = states[-1]
    required = ["top_want", "top_music", "top_formula", "top_color", "top_activity", "autonomy_statement"]
    if not all(bool(str(state.get(k) or "")) for k in required):
        return False
    return float(state.get("dialogue_readiness") or 0.0) >= 0.45


def first_person_desire_ok(turns: list[dict[str, Any]]) -> bool:
    text = "\n".join(str(t.get("response_text") or "").lower() for t in turns)
    if "quero" not in text and "prefiro" not in text:
        return False
    if "evidencia" not in text and "memoria" not in text and "v49.22" not in text:
        return False
    return "incerteza" in text or "nao trato isso como gosto fechado" in text


def rzs_influenced(turns: list[dict[str, Any]]) -> bool:
    decisions = {str(t.get("rzs_decision") or "") for t in turns}
    return bool(decisions) and decisions.issubset(VALID_RZS) and any(d != "continue" for d in decisions)


def prior_data_present(conn: sqlite3.Connection) -> bool:
    required = [
        "autonomous_preference_sessions_v49_22",
        "autonomous_preference_decisions_v49_22",
        "autonomous_preference_candidates_v49_22",
        "wake_next_handoff_v49_21",
    ]
    return all(table_exists(conn, table) for table in required)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, session_row = latest_completed_session(conn)
    turns = rows(conn, DD_TURNS, " WHERE session_id=?", (session_id,)) if session_id else []
    refs = rows(conn, DD_REFS, " WHERE session_id=?", (session_id,)) if session_id else []
    states = rows(conn, DD_STATE, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = session_row.get("payload", {}) if session_row else {}
    intents = sorted({str(t.get("intent") or "") for t in turns})
    decisions = sorted({str(t.get("rzs_decision") or "") for t in turns})
    latest_state = states[-1] if states else {}
    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (DD_SESSIONS, DD_TURNS, DD_REFS, DD_STATE)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "v49_22_source_valid": v49_22_source_valid(conn, session_row) if session_id else False,
        "turns_grounded_in_preferences": turns_ok(turns),
        "memory_refs_written": refs_ok(refs, turns),
        "state_written": state_ok(states),
        "first_person_desire_present": first_person_desire_ok(turns),
        "rzs_influenced_dialogue": rzs_influenced(turns),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "prior_data_still_present": prior_data_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "source_preference_session_id": str(session_row.get("source_preference_session_id") or "") if session_row else "",
        "checks": checks,
        "counts": {
            "turns": len(turns),
            "refs": len(refs),
            "states": len(states),
        },
        "intents": intents,
        "rzs_decisions": decisions,
        "responses": [
            {
                "intent": t.get("intent", ""),
                "chosen_label": t.get("chosen_label", ""),
                "response": t.get("response_text", ""),
                "rzs": t.get("rzs_decision", ""),
                "confidence": round(float(t.get("confidence") or 0.0), 3),
            }
            for t in turns
        ],
        "state": {
            "top_want": latest_state.get("top_want", ""),
            "top_music": latest_state.get("top_music", ""),
            "top_formula": latest_state.get("top_formula", ""),
            "top_color": latest_state.get("top_color", ""),
            "top_activity": latest_state.get("top_activity", ""),
            "dialogue_readiness": round(float(latest_state.get("dialogue_readiness") or 0.0), 3) if latest_state else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.23 - DIAGNOSTICO DESIRE DIALOGUE")
    print("=" * 64)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    print(f"- preferencia fonte: {report['source_preference_session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- turnos={c['turns']} refs={c['refs']} estados={c['states']}")
    print(f"- intents: {', '.join(report['intents']) if report['intents'] else 'nenhum'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.23 existem",
        "completed_session": "sessao completa encontrada",
        "v49_22_source_valid": "fonte v49.22 valida",
        "turns_grounded_in_preferences": "falas ancoradas em preferencias",
        "memory_refs_written": "referencias de memoria escritas",
        "state_written": "estado de desejo escrito",
        "first_person_desire_present": "fala em primeira pessoa presente",
        "rzs_influenced_dialogue": "RZS influenciou dialogo",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin consegue dizer o que quer/gosta usando preferencia autonoma e evidencia.")
    else:
        print("Leitura: ainda falta evidencia para aceitar dialogo de desejo como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.23 Desire Dialogue checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
