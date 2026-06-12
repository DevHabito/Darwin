from __future__ import annotations

"""
DARWIN v49.18 - Diagnostico da continuidade autobiografica

Uso:
    py darwin_check_v49_18_autobiography.py
    py darwin_check_v49_18_autobiography.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

AB_SESSIONS = "autobiography_sessions_v49_18"
AB_EVENTS = "autobiography_events_v49_18"
AB_CHAPTERS = "autobiography_chapters_v49_18"
AB_IDENTITY = "autobiography_identity_state_v49_18"
AB_PREDICTIONS = "autobiography_next_predictions_v49_18"
SOURCE = "darwin_autobiographical_continuity_v49_18"


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
        if "source_kinds_json" in item:
            item["source_kinds"] = pj(str(item.get("source_kinds_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, AB_SESSIONS)
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
        (SOURCE, f"autobiography_v49_18:{session_id}"),
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
        (SOURCE, f"autobiography:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def bounded(rows_: list[dict[str, Any]], keys: tuple[str, ...]) -> bool:
    if not rows_:
        return False
    for row in rows_:
        for key in keys:
            value = float(row.get(key) or 0.0)
            if value < 0.0 or value > 1.0:
                return False
    return True


def sequence_ok(events: list[dict[str, Any]]) -> bool:
    if not events:
        return False
    seq = [int(e.get("sequence_index") or 0) for e in events]
    return seq == list(range(1, len(events) + 1)) and all(str(e.get("event_time") or "") for e in events)


def chapters_ok(chapters: list[dict[str, Any]]) -> bool:
    if len(chapters) < 7:
        return False
    keys = {str(c.get("chapter_key")) for c in chapters}
    required = {"core_origin", "music", "preference", "self_reflection", "memory_game", "language"}
    if not required.issubset(keys):
        return False
    if not bounded(chapters, ("continuity_score", "dominant_valence", "stability")):
        return False
    return all(int(c.get("event_count") or 0) > 0 for c in chapters)


def identity_ok(identity_rows: list[dict[str, Any]]) -> bool:
    if not identity_rows:
        return False
    state = identity_rows[-1]
    statement = str(state.get("identity_statement") or "").lower()
    if "darwin" not in statement or "lembro" not in statement or "felipe" not in statement:
        return False
    if float(state.get("continuity_score") or 0.0) < 0.65:
        return False
    if int(state.get("remembered_event_count") or 0) < 40:
        return False
    if int(state.get("chapter_count") or 0) < 7:
        return False
    if str(state.get("active_preference_key") or "none") == "none":
        return False
    return True


def rzs_causal(identity_rows: list[dict[str, Any]]) -> bool:
    if not identity_rows:
        return False
    state = identity_rows[-1]
    decision = str(state.get("rzs_decision") or "")
    goal = str(state.get("current_goal") or "")
    action = str(state.get("next_action") or "")
    if float(state.get("sigma_before") or 0.0) <= 0.0:
        return False
    if float(state.get("sigma_after") or 0.0) <= 0.0:
        return False
    if decision == "continue":
        return action == goal
    if decision == "replay_memory":
        return action.startswith("recall_autobiographical_sequence_before_") and action != goal
    if decision == "narrow_focus":
        return action.startswith("narrow_autobiographical_focus_before_") and action != goal
    if decision == "consolidate":
        return action == "consolidate_autobiography_before_more_training"
    if decision == "pause_for_stability":
        return action == "pause_autobiography_for_stability"
    return False


def predictions_ok(predictions: list[dict[str, Any]]) -> bool:
    if len(predictions) < 3:
        return False
    for pred in predictions:
        confidence = float(pred.get("confidence") or 0.0)
        if confidence < 0.0 or confidence > 1.0:
            return False
        if not str(pred.get("predicted_outcome") or ""):
            return False
        if "sigma_after" not in str(pred.get("check_condition") or ""):
            return False
    return True


def v49_17_present(conn: sqlite3.Connection) -> bool:
    required = ["affective_preferences_v49_17", "affective_choice_trials_v49_17", "affective_consolidation_v49_17"]
    if not all(table_exists(conn, t) for t in required):
        return False
    row = conn.execute("SELECT COUNT(*) AS n FROM affective_consolidation_v49_17").fetchone()
    return bool(row and int(row["n"]) >= 1)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    events = rows(conn, AB_EVENTS, " WHERE session_id=?", (session_id,)) if session_id else []
    chapters = rows(conn, AB_CHAPTERS, " WHERE session_id=?", (session_id,)) if session_id else []
    identity = rows(conn, AB_IDENTITY, " WHERE session_id=?", (session_id,)) if session_id else []
    predictions = rows(conn, AB_PREDICTIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    source_kinds = sorted({str(e.get("source_kind")) for e in events if e.get("source_kind")})
    chapter_keys = sorted({str(c.get("chapter_key")) for c in chapters if c.get("chapter_key")})
    identity_state = identity[-1] if identity else {}
    top_prefs = identity_state.get("payload", {}).get("top_preferences", []) if identity_state else []

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (AB_SESSIONS, AB_EVENTS, AB_CHAPTERS, AB_IDENTITY, AB_PREDICTIONS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "events_collected": len(events) >= 40 and len(source_kinds) >= 7,
        "event_sequence_causal": sequence_ok(events),
        "event_metrics_bounded": bounded(events, ("salience", "valence", "self_relevance", "stability")),
        "chapters_built": chapters_ok(chapters),
        "identity_state_written": identity_ok(identity),
        "preferences_integrated": bool(top_prefs) and str(identity_state.get("active_preference_key") or "") in {str(p.get("preference_key")) for p in top_prefs},
        "rzs_causal_effect": rzs_causal(identity),
        "predictions_written": predictions_ok(predictions),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "v49_17_data_still_present": v49_17_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "events": len(events),
            "source_kinds": len(source_kinds),
            "chapters": len(chapters),
            "identity_rows": len(identity),
            "predictions": len(predictions),
            "open_loops": sum(int(e.get("open_loop") or 0) for e in events),
            "resolved_loops": sum(int(e.get("resolved_loop") or 0) for e in events),
        },
        "source_kinds": source_kinds,
        "chapter_keys": chapter_keys,
        "identity": {
            "continuity_score": round(float(identity_state.get("continuity_score") or 0.0), 3) if identity_state else 0.0,
            "active_preference_key": identity_state.get("active_preference_key", ""),
            "current_goal": identity_state.get("current_goal", ""),
            "next_action": identity_state.get("next_action", ""),
            "rzs_decision": identity_state.get("rzs_decision", ""),
            "sigma_before": round(float(identity_state.get("sigma_before") or 0.0), 3) if identity_state else 0.0,
            "sigma_after": round(float(identity_state.get("sigma_after") or 0.0), 3) if identity_state else 0.0,
            "identity_statement": identity_state.get("identity_statement", ""),
        },
        "predictions": [
            {
                "candidate_action": p.get("candidate_action"),
                "confidence": round(float(p.get("confidence") or 0.0), 3),
                "check_condition": p.get("check_condition"),
            }
            for p in predictions
        ],
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.18 - DIAGNOSTICO AUTOBIOGRAFIA")
    print("=" * 62)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- eventos={c['events']} fontes={c['source_kinds']} "
        f"capitulos={c['chapters']} previsoes={c['predictions']}"
    )
    ident = report["identity"]
    print(f"- continuidade: {ident['continuity_score']}")
    print(f"- RZS: {ident['rzs_decision']} sigma {ident['sigma_before']}->{ident['sigma_after']}")
    print(f"- proxima acao: {ident['next_action'] or 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.18 existem",
        "completed_session": "sessao completa encontrada",
        "events_collected": "eventos autobiograficos coletados",
        "event_sequence_causal": "sequencia causal auditavel",
        "event_metrics_bounded": "metricas de eventos entre 0 e 1",
        "chapters_built": "capitulos construidos",
        "identity_state_written": "estado de identidade escrito",
        "preferences_integrated": "preferencias v49.17 integradas",
        "rzs_causal_effect": "RZS alterou ou permitiu a acao corretamente",
        "predictions_written": "previsoes verificaveis escritas",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "v49_17_data_still_present": "dados v49.17 ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin manteve continuidade autobiografica e escolheu o proximo passo com RZS.")
    else:
        print("Leitura: ainda falta evidencia para aceitar autobiografia operacional como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.18 Autobiography checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
