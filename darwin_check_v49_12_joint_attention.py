from __future__ import annotations

"""
DARWIN v49.12 - Diagnostico de atencao compartilhada

Uso:
    py darwin_check_v49_12_joint_attention.py
    py darwin_check_v49_12_joint_attention.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

JA_SESSIONS = "joint_attention_sessions_v49_12"
JA_SCENES = "joint_attention_scenes_v49_12"
JA_FOCUS = "joint_attention_focus_events_v49_12"
JA_BINDINGS = "joint_attention_word_bindings_v49_12"
JA_ERRORS = "joint_attention_prediction_errors_v49_12"
JA_REPLAY = "joint_attention_replay_v49_12"
FW_MEANINGS = "voice_word_meanings_v49_10"
VI_SESSIONS = "vocal_imitation_sessions_v49_11"


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
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, JA_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "joint_attention_complete" and r.get("payload", {}).get("session_complete") is True
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
        WHERE source='darwin_joint_attention_v49_12'
          AND key=?
        """,
        (f"joint_attention_v49_12:{session_id}",),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_joint_attention_v49_12'
          AND context LIKE ?
        """,
        (f"joint_attention:{session_id}:%",),
    ).fetchone()
    return int(row["n"]) if row else 0


def source_exists(conn: sqlite3.Connection, table: str, session_id: str, min_rows: int) -> bool:
    if not session_id or not table_exists(conn, table):
        return False
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE session_id=?", (session_id,)).fetchone()
    return bool(row and int(row["n"]) >= min_rows)


def payload_float(payload: dict[str, Any], key: str, default: float) -> float:
    if key not in payload or payload[key] is None:
        return default
    try:
        return float(payload[key])
    except Exception:
        return default


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    payload = complete_row.get("payload", {}) if complete_row else {}
    scenes = rows(conn, JA_SCENES, session_id) if session_id else []
    focus = rows(conn, JA_FOCUS, session_id) if session_id else []
    bindings = rows(conn, JA_BINDINGS, session_id) if session_id else []
    errors = rows(conn, JA_ERRORS, session_id) if session_id else []
    replays = rows(conn, JA_REPLAY, session_id) if session_id else []
    words = {str(s.get("label_word")) for s in scenes if s.get("label_word")}
    first = focus[: max(1, len(focus) // 4)]
    last = focus[-max(1, len(focus) // 4) :]
    first_error = sum(float(f.get("prediction_error") or 0.0) for f in first) / max(1, len(first))
    last_error = sum(float(f.get("prediction_error") or 0.0) for f in last) / max(1, len(last))
    decisions = {str(f.get("rzs_decision")) for f in focus if f.get("rzs_decision")}
    improved = [
        f
        for f in focus
        if float(f.get("confidence_after") or 0.0) > float(f.get("confidence_before") or 0.0)
        and float(f.get("binding_strength_after") or 0.0) > float(f.get("binding_strength_before") or 0.0)
    ]
    correct_bindings = [b for b in bindings if int(b.get("is_correct") or 0) == 1]
    source_fw = str(payload.get("source_first_words_session_id") or "")
    source_vi = str(payload.get("source_vocal_imitation_session_id") or "")
    ep_n = episode_count(conn, session_id) if session_id else 0

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (JA_SESSIONS, JA_SCENES, JA_FOCUS, JA_BINDINGS, JA_ERRORS, JA_REPLAY)),
        "completed_session": bool(session_id),
        "reads_first_words_v49_10": source_exists(conn, FW_MEANINGS, source_fw, 4),
        "reads_vocal_imitation_v49_11": source_exists(conn, VI_SESSIONS, source_vi, 1),
        "scene_seeded": len(scenes) >= 6 and {"mamae", "papai", "felipe", "darwin"}.issubset(words),
        "focus_events_created": len(focus) >= 48,
        "initial_reference_errors_exist": any(float(f.get("prediction_error") or 0.0) > 0.0 for f in first),
        "reference_learning_improved": last_error < first_error,
        "bindings_strengthened": len(improved) >= 24 and len(correct_bindings) >= len(scenes),
        "prediction_errors_logged": len(errors) >= 4,
        "replay_occurred": len(replays) >= 1 and any(float(r.get("error_after") or 0.0) < float(r.get("error_before") or 0.0) for r in replays),
        "rzs_regulated": bool(decisions) and all(float(f.get("sigma_before") or 0.0) > 0.0 for f in focus),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episodes_written": ep_n >= len(focus) if session_id else False,
        "payload_consistent": int(payload.get("focus_count") or 0) == len(focus) and payload_float(payload, "last_error", 999.0) < payload_float(payload, "first_error", 0.0),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "scenes": len(scenes),
            "focus": len(focus),
            "bindings": len(bindings),
            "errors": len(errors),
            "replays": len(replays),
            "episodes": ep_n,
        },
        "words": sorted(words),
        "rzs_decisions": sorted(decisions),
        "first_error": first_error,
        "last_error": last_error,
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.12 - DIAGNOSTICO ATENCAO COMPARTILHADA")
    print("=" * 64)
    print(f"- sessao v49.12: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- cena={c['scenes']} foco={c['focus']} bindings={c['bindings']} "
        f"erros={c['errors']} replays={c['replays']}"
    )
    print(f"- erro inicio={report['first_error']:.4f} erro final={report['last_error']:.4f}")
    print(f"- palavras: {', '.join(report['words']) if report['words'] else 'nenhuma'}")
    print(f"- decisoes RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.12 existem",
        "completed_session": "sessao completa encontrada",
        "reads_first_words_v49_10": "leu primeiras palavras v49.10",
        "reads_vocal_imitation_v49_11": "leu imitacao vocal v49.11",
        "scene_seeded": "cena compartilhada semeada",
        "focus_events_created": "eventos de foco criados",
        "initial_reference_errors_exist": "erros iniciais de referencia existem",
        "reference_learning_improved": "erro de referencia caiu",
        "bindings_strengthened": "vinculos palavra-objeto fortaleceram",
        "prediction_errors_logged": "erros de predicao registrados",
        "replay_occurred": "replay de atencao ocorreu",
        "rzs_regulated": "RZS regulou atencao",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios escritos",
        "payload_consistent": "payload final consistente",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin aprendeu referencia compartilhada entre palavra, foco e objeto.")
    else:
        print("Leitura: ainda falta evidencia para aceitar atencao compartilhada como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.12 Joint Attention checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
