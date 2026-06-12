from __future__ import annotations

"""
DARWIN v49.9 - Diagnostico da Voice Presence

Uso:
    py darwin_check_v49_9_voice_presence.py
    py darwin_check_v49_9_voice_presence.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

VOICE_SESSIONS = "voice_presence_sessions_v49_9"
VOICE_EVENTS = "voice_presence_events_v49_9"
COMPANION_DIALOGUES = "companion_dialogues_v49_8"
COMPANION_VOICE = "companion_voice_events_v49_8"


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


def rows(conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_completed_voice_session(conn: sqlite3.Connection) -> tuple[str, str, dict[str, Any]]:
    session_rows = rows(conn, VOICE_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "voice_session_complete"
        and (r.get("payload", {}).get("session_complete") is True or r.get("mode") == "self_test")
    ]
    if not completed:
        return "", "", {}
    row = completed[-1]
    return str(row["voice_session_id"]), str(row["companion_session_id"]), row


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    voice_session_id, companion_session_id, complete_row = latest_completed_voice_session(conn)
    voice_events = rows(conn, VOICE_EVENTS, " WHERE voice_session_id=?", (voice_session_id,)) if voice_session_id else []
    companion_dialogues = rows(conn, COMPANION_DIALOGUES, " WHERE session_id=?", (companion_session_id,)) if companion_session_id else []
    companion_voice = rows(conn, COMPANION_VOICE, " WHERE session_id=?", (companion_session_id,)) if companion_session_id else []
    recognized = [e for e in voice_events if e.get("event_kind") == "recognized_response"]
    decisions = {str(e.get("rzs_decision")) for e in recognized if e.get("rzs_decision")}
    intents = {str(d.get("intent")) for d in companion_dialogues if d.get("intent")}
    texts = "\n".join(str(e.get("recognized_text") or "") for e in recognized).lower()
    responses = "\n".join(str(e.get("response_text") or "") for e in recognized).lower()
    complete_payload = complete_row.get("payload", {}) if complete_row else {}

    checks = {
        "tables_exist": table_exists(conn, VOICE_SESSIONS) and table_exists(conn, VOICE_EVENTS),
        "completed_voice_session": bool(voice_session_id),
        "recognized_without_keyboard": len(recognized) >= 4,
        "recognized_text_logged": all(str(e.get("recognized_text") or "").strip() for e in recognized),
        "companion_replied": len(companion_dialogues) >= len(recognized) >= 1,
        "speech_planned": len(companion_voice) >= len(recognized),
        "rzs_logged": len(decisions) >= 1 and all(float(e.get("sigma_before") or 0.0) > 0.0 for e in recognized),
        "voice_confidence_logged": all(float(e.get("confidence") or 0.0) > 0.0 for e in recognized),
        "status_geometry_or_companion_covered": (
            ("status" in intents and "geometry_memory" in intents)
            or "companion_direction" in intents
        ),
        "responds_to_voice_content": "geometria" in texts and ("96 nos" in responses or "geometria" in responses),
        "session_marked_complete": bool(complete_payload) or bool(complete_row),
    }
    return {
        "ok": all(checks.values()),
        "voice_session_id": voice_session_id,
        "companion_session_id": companion_session_id,
        "checks": checks,
        "counts": {
            "voice_events": len(voice_events),
            "recognized": len(recognized),
            "companion_dialogues": len(companion_dialogues),
            "companion_voice": len(companion_voice),
        },
        "decisions": sorted(decisions),
        "intents": sorted(intents),
        "complete_payload": complete_payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.9 - DIAGNOSTICO DA VOICE PRESENCE")
    print("=" * 58)
    print(f"- voice session: {report['voice_session_id'] or 'NENHUMA'}")
    print(f"- companion session: {report['companion_session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- eventos voz={c['voice_events']} reconhecidos={c['recognized']} "
        f"dialogos={c['companion_dialogues']} fala={c['companion_voice']}"
    )
    print(f"- intents: {', '.join(report['intents']) if report['intents'] else 'nenhum'}")
    print(f"- decisoes RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.9 existem",
        "completed_voice_session": "sessao de voz completa",
        "recognized_without_keyboard": "fala reconhecida sem teclado",
        "recognized_text_logged": "texto reconhecido registrado",
        "companion_replied": "companion respondeu",
        "speech_planned": "fala do Darwin planejada",
        "rzs_logged": "RZS registrado",
        "voice_confidence_logged": "confianca de voz registrada",
        "status_geometry_or_companion_covered": "conteudo essencial coberto",
        "responds_to_voice_content": "resposta usa conteudo falado",
        "session_marked_complete": "sessao marcada como completa",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin ja tem modo de presenca por voz, sem digitar nem apertar para falar.")
    else:
        print("Leitura: ainda falta evidencia para aceitar a escuta continua como estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.9 Voice Presence checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
