from __future__ import annotations

"""
DARWIN v49.26 - Diagnostico do Continuous Presence Loop

Uso:
    py darwin_check_v49_26_continuous_presence.py
    py darwin_check_v49_26_continuous_presence.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

PR_SESSIONS = "presence_sessions_v49_26"
PR_SIGNALS = "presence_signals_v49_26"
PR_TICKS = "presence_ticks_v49_26"
PR_ACTIONS = "presence_actions_v49_26"
PR_HANDOFFS = "presence_handoffs_v49_26"

SOURCE = "darwin_continuous_presence_loop_v49_26"
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}
REQUIRED_SIGNALS = {"voice_repair_state", "desire_state", "wake_handoff", "memory_growth", "presence_self"}
REQUIRED_ACTION_FAMILIES = {"voice_monitor", "desire_guard", "memory_replay", "presence_stabilize"}


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
    session_rows = rows(conn, PR_SESSIONS)
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
        (SOURCE, f"continuous_presence_v49_26:{session_id}"),
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
        (SOURCE, f"continuous_presence:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def signals_ok(signals: list[dict[str, Any]]) -> bool:
    if len(signals) < 5:
        return False
    kinds = {str(s.get("signal_kind") or "") for s in signals}
    if not REQUIRED_SIGNALS.issubset(kinds):
        return False
    for signal in signals:
        if not str(signal.get("source_table") or ""):
            return False
        if not str(signal.get("summary") or ""):
            return False
        salience = float(signal.get("salience") or 0.0)
        if salience <= 0.0 or salience > 1.0:
            return False
    return True


def ticks_ok(ticks: list[dict[str, Any]]) -> bool:
    if len(ticks) < 12:
        return False
    indices = [int(t.get("tick_index") or 0) for t in ticks]
    if indices != list(range(1, len(ticks) + 1)):
        return False
    if len({str(t.get("focus_key") or "") for t in ticks}) < 3:
        return False
    for tick in ticks:
        if str(tick.get("phase") or "") != "presence_tick":
            return False
        if not str(tick.get("focus_key") or ""):
            return False
        if not str(tick.get("attention_state") or ""):
            return False
        if str(tick.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(tick.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(tick.get("sigma_after") or 0.0) <= 0.0:
            return False
        if not str(tick.get("presence_action") or ""):
            return False
    return True


def actions_ok(actions: list[dict[str, Any]], ticks: list[dict[str, Any]]) -> bool:
    if len(actions) != len(ticks):
        return False
    families = {str(a.get("action_family") or "") for a in actions}
    if not REQUIRED_ACTION_FAMILIES.issubset(families):
        return False
    for action in actions:
        if str(action.get("status") or "") != "completed":
            return False
        if not str(action.get("action_key") or ""):
            return False
        if not str(action.get("effect_summary") or ""):
            return False
    return True


def handoff_ok(handoffs: list[dict[str, Any]], ticks: list[dict[str, Any]]) -> bool:
    if not handoffs:
        return False
    item = handoffs[-1]
    if not str(item.get("next_recommended_core") or ""):
        return False
    if not str(item.get("next_action") or ""):
        return False
    if int(item.get("continuous_presence_ready") or 0) != 1:
        return False
    if float(item.get("confidence") or 0.0) < 0.65:
        return False
    payload = item.get("payload", {})
    if int(payload.get("tick_count") or 0) != len(ticks):
        return False
    if int(payload.get("recognizer_count") or 0) == 0:
        return str(item.get("next_recommended_core") or "") == "darwin_real_voice_repair_wizard_v49_25"
    return True


def rzs_influenced(ticks: list[dict[str, Any]]) -> bool:
    decisions = {str(t.get("rzs_decision") or "") for t in ticks}
    return bool(decisions) and decisions.issubset(VALID_RZS) and any(d != "continue" for d in decisions)


def prior_data_present(conn: sqlite3.Connection) -> bool:
    required = [
        "voice_repair_results_v49_25",
        "desire_action_results_v49_24",
        "desire_dialogue_state_v49_23",
        "wake_next_handoff_v49_21",
    ]
    return all(table_exists(conn, table) for table in required)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, session_row = latest_completed_session(conn)
    signals = rows(conn, PR_SIGNALS, " WHERE session_id=?", (session_id,)) if session_id else []
    ticks = rows(conn, PR_TICKS, " WHERE session_id=?", (session_id,)) if session_id else []
    actions = rows(conn, PR_ACTIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    handoffs = rows(conn, PR_HANDOFFS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = session_row.get("payload", {}) if session_row else {}
    latest_handoff = handoffs[-1] if handoffs else {}
    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (PR_SESSIONS, PR_SIGNALS, PR_TICKS, PR_ACTIONS, PR_HANDOFFS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "signals_loaded": signals_ok(signals),
        "ticks_written": ticks_ok(ticks),
        "actions_written": actions_ok(actions, ticks),
        "handoff_written": handoff_ok(handoffs, ticks),
        "rzs_influenced_presence": rzs_influenced(ticks),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "prior_data_still_present": prior_data_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "source_voice_repair_session_id": str(session_row.get("source_voice_repair_session_id") or "") if session_row else "",
        "checks": checks,
        "counts": {
            "signals": len(signals),
            "ticks": len(ticks),
            "actions": len(actions),
            "handoffs": len(handoffs),
        },
        "signal_kinds": sorted({str(s.get("signal_kind") or "") for s in signals}),
        "focus_keys": [str(t.get("focus_key") or "") for t in ticks],
        "action_families": sorted({str(a.get("action_family") or "") for a in actions}),
        "rzs_decisions": sorted({str(t.get("rzs_decision") or "") for t in ticks}),
        "handoff": {
            "next_recommended_core": latest_handoff.get("next_recommended_core", ""),
            "next_action": latest_handoff.get("next_action", ""),
            "voice_ready": bool(int(latest_handoff.get("voice_ready") or 0)) if latest_handoff else False,
            "continuous_presence_ready": bool(int(latest_handoff.get("continuous_presence_ready") or 0)) if latest_handoff else False,
            "confidence": round(float(latest_handoff.get("confidence") or 0.0), 3) if latest_handoff else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.26 - DIAGNOSTICO CONTINUOUS PRESENCE")
    print("=" * 68)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    print(f"- voz fonte: {report['source_voice_repair_session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- sinais={c['signals']} ticks={c['ticks']} acoes={c['actions']} handoffs={c['handoffs']}")
    print(f"- sinais: {', '.join(report['signal_kinds']) if report['signal_kinds'] else 'nenhum'}")
    print(f"- familias: {', '.join(report['action_families']) if report['action_families'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    h = report["handoff"]
    print(f"- handoff: {h['next_action'] or 'nenhum'} confianca={h['confidence']}")
    print()
    labels = {
        "tables_exist": "tabelas v49.26 existem",
        "completed_session": "sessao completa encontrada",
        "signals_loaded": "sinais internos carregados",
        "ticks_written": "ticks de presenca escritos",
        "actions_written": "acoes cognitivas escritas",
        "handoff_written": "handoff vivo escrito",
        "rzs_influenced_presence": "RZS influenciou presenca",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin manteve presenca acordada com foco, RZS, memoria e handoff.")
    else:
        print("Leitura: ainda falta evidencia para aceitar presenca continua como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.26 Continuous Presence checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
