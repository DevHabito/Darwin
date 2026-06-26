from __future__ import annotations

"""
DARWIN v49.34 - Diagnostico Wake Word Guardian

Uso:
    py darwin_check_v49_34_wake_word_guardian.py
    py darwin_check_v49_34_wake_word_guardian.py --details
"""

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_wake_word_guardian_v49_34"

WG_SESSIONS = "wake_guardian_sessions_v49_34"
WG_EVENTS = "wake_guardian_events_v49_34"
WG_HANDOFFS = "wake_guardian_handoffs_v49_34"

REQUIRED_TABLES = [WG_SESSIONS, WG_EVENTS, WG_HANDOFFS]
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


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
        for r in rows(conn, WG_SESSIONS)
        if r.get("phase") == "guardian_complete" and r.get("payload", {}).get("wake_guardian_ready") is True
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
        (SOURCE, f"wake_guardian_v49_34:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM episodes WHERE module=? AND context=?",
        (SOURCE, f"wake_guardian:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def check_order(events: list[dict[str, Any]]) -> bool:
    kinds = [str(e.get("event_kind") or "") for e in events]
    needed = ["ignored_sleeping_noise", "wake_detected", "companion_voice_turn", "sleep_phrase_detected", "ignored_sleeping_noise", "wake_detected"]
    pos = 0
    for kind in kinds:
        if pos < len(needed) and kind == needed[pos]:
            pos += 1
    if pos == len(needed):
        return True
    compact = [k for k in kinds if k in {"ignored_sleeping_noise", "wake_detected", "wake_and_reply", "companion_voice_turn", "sleep_phrase_detected"}]
    return (
        len(compact) >= 5
        and compact[0] == "ignored_sleeping_noise"
        and any(k in {"wake_detected", "wake_and_reply"} for k in compact[1:3])
        and "sleep_phrase_detected" in compact
        and compact[-1] in {"wake_detected", "wake_and_reply"}
    )


def diagnose(details: bool = False) -> dict[str, Any]:
    with connect() as conn:
        tables_ok = all(table_exists(conn, table) for table in REQUIRED_TABLES)
        session_id, completed = latest_completed(conn)
        payload = completed.get("payload", {}) if completed else {}
        events = rows(conn, WG_EVENTS, session_id) if session_id else []
        handoffs = rows(conn, WG_HANDOFFS, session_id) if session_id else []
        semantic = semantic_count(conn, session_id) if session_id else 0
        episodes = episode_count(conn, session_id) if session_id else 0

        wake_events = [e for e in events if str(e.get("event_kind") or "") in {"wake_detected", "wake_and_reply"}]
        sleep_events = [e for e in events if str(e.get("event_kind") or "") == "sleep_phrase_detected"]
        reply_events = [e for e in events if str(e.get("event_kind") or "") in {"companion_voice_turn", "wake_and_reply"}]
        ignored_events = [e for e in events if str(e.get("event_kind") or "") == "ignored_sleeping_noise"]
        rzs = {str(e.get("rzs_decision") or "") for e in events if e.get("rzs_decision")}

        checks = {
            "tables_exist": tables_ok,
            "completed_session": bool(session_id and payload.get("wake_guardian_ready") is True),
            "wake_word_opens_presence": len(wake_events) >= 2 and all(e.get("state_after") == "awake" for e in wake_events),
            "sleep_phrase_returns_to_rest": len(sleep_events) >= 1 and sleep_events[-1].get("state_after") == "sleeping",
            "sleeping_noise_ignored": len(ignored_events) >= 1 and all(e.get("state_after") == "sleeping" for e in ignored_events[:1]),
            "companion_replied": len(reply_events) >= 1 and any(str(e.get("response_text") or "") for e in reply_events),
            "causal_order_valid": check_order(events),
            "rzs_regulated_actions": bool(rzs) and rzs.issubset(VALID_RZS) and all(number(e.get("sigma_before"), 0.0) > 0 for e in events),
            "background_listener_disclosed": payload.get("background_listener_required") is True,
            "self_test_no_microphone": payload.get("self_test_never_uses_microphone") is True,
            "handoff_written": len(handoffs) >= 1 and int(handoffs[-1].get("wake_guardian_ready") or 0) == 1,
            "semantic_memory_written": semantic >= 1,
            "episode_written": episodes >= 1,
        }
        result = {
            "ok": all(checks.values()),
            "session_id": session_id,
            "checks": checks,
            "counts": {
                "events": len(events),
                "wake_events": len(wake_events),
                "sleep_events": len(sleep_events),
                "reply_events": len(reply_events),
                "ignored_events": len(ignored_events),
                "handoffs": len(handoffs),
                "semantic": semantic,
                "episodes": episodes,
            },
            "event_kinds": [str(e.get("event_kind") or "") for e in events],
            "rzs_decisions": sorted(rzs),
            "payload": payload if details else {},
        }
        return result


def print_report(result: dict[str, Any], details: bool = False) -> None:
    print("DARWIN v49.34 - DIAGNOSTICO WAKE WORD GUARDIAN")
    print("=" * 72)
    print(f"- sessao: {result.get('session_id')}")
    counts = result.get("counts", {})
    print(
        f"- eventos={counts.get('events')} wake={counts.get('wake_events')} "
        f"sleep={counts.get('sleep_events')} replies={counts.get('reply_events')} ignored={counts.get('ignored_events')}"
    )
    print(f"- RZS: {', '.join(result.get('rzs_decisions', []))}")
    print()
    labels = {
        "tables_exist": "tabelas v49.34 existem",
        "completed_session": "sessao completa e pronta",
        "wake_word_opens_presence": "palavra Darwin acorda e abre presenca",
        "sleep_phrase_returns_to_rest": "frase de mimir volta ao descanso",
        "sleeping_noise_ignored": "ruido dormindo e ignorado",
        "companion_replied": "companion respondeu enquanto acordado",
        "causal_order_valid": "ordem causal acordar/conversar/dormir valida",
        "rzs_regulated_actions": "RZS regulou acoes",
        "background_listener_disclosed": "necessidade de listener em segundo plano registrada",
        "self_test_no_microphone": "self-test nao usou microfone",
        "handoff_written": "handoff escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
    }
    for key, passed in result.get("checks", {}).items():
        print(f"- {labels.get(key, key)}: {'OK' if passed else 'FALHOU'}")
    print()
    print(f"Resultado final: {'OK' if result.get('ok') else 'FALHOU'}")
    print("Leitura: Darwin pode ficar oculto, acordar por 'Darwin', conversar e voltar ao descanso por comando de voz.")
    if details:
        print("\nJSON:")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.34 Wake Word Guardian")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = diagnose(details=args.details)
    print_report(result, args.details)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
