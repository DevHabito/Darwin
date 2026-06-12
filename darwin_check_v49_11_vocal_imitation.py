from __future__ import annotations

"""
DARWIN v49.11 - Diagnostico da imitação vocal

Uso:
    py darwin_check_v49_11_vocal_imitation.py
    py darwin_check_v49_11_vocal_imitation.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

VI_SESSIONS = "vocal_imitation_sessions_v49_11"
VI_TARGETS = "vocal_imitation_targets_v49_11"
VI_ATTEMPTS = "vocal_motor_attempts_v49_11"
VI_WEIGHTS = "vocal_articulation_weights_v49_11"
VI_FEEDBACK = "vocal_caregiver_feedback_v49_11"
VI_REPLAY = "vocal_imitation_replay_v49_11"
FW_MEANINGS = "voice_word_meanings_v49_10"


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
        for key in ("target_syllables_json", "produced_syllables_json", "syllables_json"):
            if key in item:
                try:
                    item[key[:-5]] = json.loads(str(item.get(key) or "[]"))
                except Exception:
                    item[key[:-5]] = []
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, VI_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "vocal_imitation_complete" and r.get("payload", {}).get("session_complete") is True
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
        WHERE source='darwin_vocal_imitation_v49_11'
          AND key=?
        """,
        (f"vocal_imitation_v49_11:{session_id}",),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_vocal_imitation_v49_11'
          AND context LIKE ?
        """,
        (f"vocal_imitation:{session_id}:%",),
    ).fetchone()
    return int(row["n"]) if row else 0


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    payload = complete_row.get("payload", {}) if complete_row else {}
    targets = rows(conn, VI_TARGETS, session_id) if session_id else []
    attempts = rows(conn, VI_ATTEMPTS, session_id) if session_id else []
    weights = rows(conn, VI_WEIGHTS, session_id) if session_id else []
    feedback = rows(conn, VI_FEEDBACK, session_id) if session_id else []
    replays = rows(conn, VI_REPLAY, session_id) if session_id else []
    words = {str(t.get("target_word")) for t in targets if t.get("target_word")}
    first_quarter = attempts[: max(1, len(attempts) // 4)]
    last_quarter = attempts[-max(1, len(attempts) // 4) :]
    first_error = sum(float(a.get("articulation_error") or 0.0) for a in first_quarter) / max(1, len(first_quarter))
    last_error = sum(float(a.get("articulation_error") or 0.0) for a in last_quarter) / max(1, len(last_quarter))
    improved_weights = [
        w
        for w in weights
        if float(w.get("clarity_after") or 0.0) > float(w.get("clarity_before") or 0.0)
        or float(w.get("control_after") or 0.0) > float(w.get("control_before") or 0.0)
    ]
    decisions = {str(a.get("rzs_decision")) for a in attempts if a.get("rzs_decision")}
    produced_variants = {str(a.get("produced_text")) for a in attempts if a.get("produced_text")}
    source_first_words = str(payload.get("source_first_words_session_id") or "")
    fw_source_exists = False
    if source_first_words and table_exists(conn, FW_MEANINGS):
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {FW_MEANINGS} WHERE session_id=?", (source_first_words,)).fetchone()
        fw_source_exists = bool(row and int(row["n"]) >= 4)

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (VI_SESSIONS, VI_TARGETS, VI_ATTEMPTS, VI_WEIGHTS, VI_FEEDBACK, VI_REPLAY)),
        "completed_session": bool(session_id),
        "reads_first_words_v49_10": fw_source_exists,
        "targets_seeded": len(targets) >= 4 and {"mamae", "papai", "felipe", "darwin"}.issubset(words),
        "attempts_created": len(attempts) >= 32 and len(produced_variants) >= 8,
        "early_errors_exist": any(float(a.get("articulation_error") or 0.0) > 0.20 for a in first_quarter),
        "articulation_improved": last_error < first_error,
        "motor_weights_updated": len(improved_weights) >= 12,
        "feedback_logged": len(feedback) >= len(attempts),
        "replay_occurred": len(replays) >= 1 and any(float(r.get("error_after") or 0.0) < float(r.get("error_before") or 0.0) for r in replays),
        "rzs_regulated": bool(decisions) and all(float(a.get("sigma_before") or 0.0) > 0.0 for a in attempts),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episodes_written": episode_count(conn, session_id) >= len(attempts) if session_id else False,
        "payload_consistent": int(payload.get("attempt_count") or 0) == len(attempts) and float(payload.get("last_error") or 999.0) < float(payload.get("first_error") or 0.0),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "targets": len(targets),
            "attempts": len(attempts),
            "weights": len(weights),
            "feedback": len(feedback),
            "replays": len(replays),
            "episodes": episode_count(conn, session_id) if session_id else 0,
            "produced_variants": len(produced_variants),
        },
        "words": sorted(words),
        "rzs_decisions": sorted(decisions),
        "first_error": first_error,
        "last_error": last_error,
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.11 - DIAGNOSTICO DA IMITACAO VOCAL")
    print("=" * 60)
    print(f"- sessao v49.11: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- alvos={c['targets']} tentativas={c['attempts']} pesos={c['weights']} "
        f"feedback={c['feedback']} replays={c['replays']}"
    )
    print(f"- erro inicio={report['first_error']:.4f} erro final={report['last_error']:.4f}")
    print(f"- palavras: {', '.join(report['words']) if report['words'] else 'nenhuma'}")
    print(f"- decisoes RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.11 existem",
        "completed_session": "sessao completa encontrada",
        "reads_first_words_v49_10": "leu primeiras palavras v49.10",
        "targets_seeded": "alvos vocais semeados",
        "attempts_created": "tentativas vocais criadas",
        "early_errors_exist": "erros vocais iniciais existem",
        "articulation_improved": "erro articulatorio caiu",
        "motor_weights_updated": "pesos motores atualizados",
        "feedback_logged": "feedback registrado",
        "replay_occurred": "replay vocal ocorreu",
        "rzs_regulated": "RZS regulou imitacao",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios escritos",
        "payload_consistent": "payload final consistente",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin pratica a propria fala, erra, ajusta pesos motores e melhora.")
    else:
        print("Leitura: ainda falta evidencia para aceitar a imitacao vocal como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.11 Vocal Imitation checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
