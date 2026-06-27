from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
MODULE = Path("darwin_contextual_language_learning_v49_37.py")
SESSIONS = "context_language_sessions_v49_37"
STATE = "context_language_state_v49_37"
WORDS = "learned_words_v49_37"
EXAMPLES = "learned_word_examples_v49_37"
ALIASES = "learned_word_aliases_v49_37"
CORRECTIONS = "learned_word_corrections_v49_37"
TURNS = "context_language_turns_v49_37"
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def pj(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def diagnose(details: bool = False) -> dict[str, Any]:
    required = (SESSIONS, STATE, WORDS, EXAMPLES, ALIASES, CORRECTIONS, TURNS)
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(table_exists(conn, table) for table in required)
        restart = conn.execute(
            f"SELECT * FROM {SESSIONS} WHERE phase='session_complete' AND mode='context_language_restart_test' ORDER BY id DESC LIMIT 1"
        ).fetchone() if tables_ok else None
        restart_session = str(restart["session_id"]) if restart else ""
        restart_turns = [
            dict(row) for row in conn.execute(f"SELECT * FROM {TURNS} WHERE session_id=? ORDER BY id", (restart_session,)).fetchall()
        ] if restart_session else []
        word = str(restart_turns[0]["normalized_word"]) if restart_turns else ""
        all_turns = [
            dict(row) for row in conn.execute(f"SELECT * FROM {TURNS} WHERE normalized_word=? ORDER BY id", (word,)).fetchall()
        ] if word else []
        learned = conn.execute(f"SELECT * FROM {WORDS} WHERE normalized_word=?", (word,)).fetchone() if word else None
        examples = [
            dict(row) for row in conn.execute(f"SELECT * FROM {EXAMPLES} WHERE normalized_word=? ORDER BY id", (word,)).fetchall()
        ] if word else []
        corrections = [
            dict(row) for row in conn.execute(f"SELECT * FROM {CORRECTIONS} WHERE normalized_word=? ORDER BY id", (word,)).fetchall()
        ] if word else []
        semantic = conn.execute("SELECT * FROM semantic_memory WHERE key=?", (f"learned_word_v49_37:{word}",)).fetchone() if word else None

    actions = {str(turn.get("action") or "") for turn in all_turns}
    session_ids = {str(turn.get("session_id") or "") for turn in all_turns}
    corrected_meaning = str(learned["meaning"]) if learned else ""
    source_text = MODULE.read_text(encoding="utf-8") if MODULE.exists() else ""
    checks = {
        "tables_exist": tables_ok,
        "runtime_word_not_hardcoded": bool(word and word not in source_text),
        "darwin_asked_unknown_meaning": "ask_unknown" in actions and any("O que" in str(turn.get("asked_back") or "") for turn in all_turns),
        "pending_context_taught_word": "teach_word" in actions and bool(learned),
        "meaning_recalled": any(turn.get("action") == "query_word" and corrected_meaning in str(turn.get("response_text") or "") for turn in all_turns if corrected_meaning),
        "correction_changed_meaning": bool(corrections) and corrections[-1]["old_meaning"] != corrections[-1]["corrected_meaning"],
        "example_became_evidence": bool(examples) and int(learned["evidence_count"] if learned else 0) >= 2,
        "persisted_across_restart": len(session_ids) >= 2 and len(restart_turns) >= 2 and all(word in str(turn.get("response_text") or "") for turn in restart_turns),
        "word_used_in_new_context": any(turn.get("action") == "use_word" and "outro contexto" in str(turn.get("response_text") or "") for turn in restart_turns),
        "semantic_promotion_after_evidence": bool(semantic) and str(learned["status"] if learned else "") == "consolidated",
        "rzs_audited": all(
            str(turn.get("rzs_decision") or "") in VALID_RZS
            and finite(turn.get("sigma_before"))
            and finite(turn.get("sigma_after"))
            for turn in all_turns
        ),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "word": word,
        "restart_session_id": restart_session,
        "counts": {
            "turns": len(all_turns),
            "sessions": len(session_ids),
            "examples": len(examples),
            "corrections": len(corrections),
            "evidence": int(learned["evidence_count"] if learned else 0),
        },
        "meaning": corrected_meaning,
        "actions": sorted(actions),
        "turns": all_turns if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.37 Contextual Language")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.37 - CHECK CONTEXTUAL LANGUAGE")
    print("=" * 68)
    print(f"- palavra runtime: {report['word']}")
    print(f"- significado final: {report['meaning']}")
    print(f"- turnos={report['counts']['turns']} sessoes={report['counts']['sessions']} evidencias={report['counts']['evidence']}")
    labels = {
        "tables_exist": "tabelas v49.37 existem",
        "runtime_word_not_hardcoded": "palavra de teste nao estava no codigo",
        "darwin_asked_unknown_meaning": "Darwin perguntou palavra desconhecida",
        "pending_context_taught_word": "resposta seguinte ensinou pelo contexto",
        "meaning_recalled": "significado foi recuperado",
        "correction_changed_meaning": "correcao substituiu significado anterior",
        "example_became_evidence": "exemplo aumentou evidencia",
        "persisted_across_restart": "aprendizado persistiu apos reinicio",
        "word_used_in_new_context": "palavra foi usada em outro contexto",
        "semantic_promotion_after_evidence": "promocao semantica exigiu evidencia",
        "rzs_audited": "RZS auditou todos os turnos",
    }
    for key, passed in report["checks"].items():
        print(f"- {labels[key]}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
