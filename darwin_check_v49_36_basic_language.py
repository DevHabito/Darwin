from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SESSIONS = "basic_language_sessions_v49_36"
LEXICON = "basic_language_lexicon_v49_36"
PATTERNS = "basic_language_patterns_v49_36"
TURNS = "basic_language_turns_v49_36"
REQUIRED_INTENTS = {
    "basic_identity_name",
    "basic_affect_state",
    "basic_sleep_quality",
    "basic_wellbeing",
    "basic_user_positive",
    "basic_user_tired",
    "basic_user_uncertain",
}
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def pj(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return fallback
    return parsed


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def rows(conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id", params).fetchall()]


def diagnose(details: bool = False) -> dict[str, Any]:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(table_exists(conn, table) for table in (SESSIONS, LEXICON, PATTERNS, TURNS))
        completed = rows(conn, SESSIONS, " WHERE phase='session_complete' AND turn_count>=10")
        session_id = str(completed[-1]["session_id"]) if completed else ""
        turns = rows(conn, TURNS, " WHERE session_id=?", (session_id,)) if session_id else []
        lexicon = rows(conn, LEXICON)
        patterns = rows(conn, PATTERNS)
        companion_status = []
        if table_exists(conn, "companion_dialogues_v49_8") and session_id:
            companion_status = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM companion_dialogues_v49_8 WHERE session_id=? AND lower(user_text)='qual seu status' ORDER BY id",
                    (session_id,),
                ).fetchall()
            ]

    intents = {str(turn.get("intent") or "") for turn in turns}
    patterns_by_intent: dict[str, int] = {}
    for pattern in patterns:
        key = str(pattern.get("intent") or "")
        patterns_by_intent[key] = patterns_by_intent.get(key, 0) + 1
    synonyms = sum(len(pj(str(item.get("synonyms_json") or "[]"), [])) for item in lexicon)
    grounded_turns = [
        turn for turn in turns
        if pj(str(turn.get("state_sources_json") or "[]"), [])
        and pj(str(turn.get("state_snapshot_json") or "{}"), {})
    ]
    questions_back = [turn for turn in turns if str(turn.get("asked_back") or "").endswith("?")]
    identity_turns = [turn for turn in turns if turn.get("intent") == "basic_identity_name"]
    sleep_turns = [turn for turn in turns if turn.get("intent") == "basic_sleep_quality"]
    synonym_expectations = {
        "qual e sua identidade": "basic_identity_name",
        "como esta seu animo": "basic_affect_state",
        "voce teve um bom repouso": "basic_sleep_quality",
        "como vai": "basic_wellbeing",
    }
    synonym_turns = {
        str(turn.get("normalized_text") or ""): str(turn.get("intent") or "")
        for turn in turns
        if str(turn.get("normalized_text") or "") in synonym_expectations
    }
    checks = {
        "tables_exist": tables_ok,
        "completed_session": bool(session_id and completed[-1].get("turn_count", 0) >= 10),
        "basic_vocabulary_seeded": len(lexicon) >= 20 and synonyms >= 40,
        "synonym_patterns_seeded": len(patterns) >= 55 and all(patterns_by_intent.get(key, 0) >= 4 for key in REQUIRED_INTENTS if key in {"basic_identity_name", "basic_affect_state", "basic_sleep_quality", "basic_wellbeing"}),
        "semantic_synonyms_understood": all(synonym_turns.get(text) == intent for text, intent in synonym_expectations.items()),
        "required_intents_understood": REQUIRED_INTENTS.issubset(intents),
        "identity_paraphrases_invariant": len(identity_turns) >= 3 and all("Darwin" in str(turn.get("response_text") or "") for turn in identity_turns),
        "nonbasic_status_not_hijacked": bool(companion_status) and companion_status[-1].get("intent") == "status",
        "sleep_answer_grounded": len(sleep_turns) >= 2 and all("energia" in str(turn.get("response_text") or "") for turn in sleep_turns),
        "state_grounding_recorded": len(grounded_turns) == len(turns) and len(turns) >= 10,
        "darwin_asks_questions": len(questions_back) >= 6,
        "user_answers_understood": {"basic_user_positive", "basic_user_tired", "basic_user_uncertain"}.issubset(intents),
        "rzs_caused_delivery": all(
            str(turn.get("rzs_decision") or "") in VALID_RZS
            and finite(turn.get("sigma_before"))
            and finite(turn.get("sigma_after"))
            for turn in turns
        ),
        "companion_delivery_path": all(turn.get("delivery_path") == "companion_core" for turn in turns),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "session_id": session_id,
        "counts": {
            "turns": len(turns),
            "intents": len(intents),
            "lexicon": len(lexicon),
            "synonyms": synonyms,
            "patterns": len(patterns),
            "questions_back": len(questions_back),
            "grounded_turns": len(grounded_turns),
        },
        "intents": sorted(intents),
        "sample_turns": turns[:5] if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.36 Basic Language")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.36 - CHECK BASIC GROUNDED LANGUAGE")
    print("=" * 68)
    counts = report["counts"]
    print(f"- sessao: {report['session_id']}")
    print(f"- vocabulario={counts['lexicon']} sinonimos={counts['synonyms']} padroes={counts['patterns']}")
    print(f"- turnos={counts['turns']} intents={counts['intents']} perguntas={counts['questions_back']}")
    labels = {
        "tables_exist": "tabelas v49.36 existem",
        "completed_session": "sessao integrada completa",
        "basic_vocabulary_seeded": "vocabulario e sinonimos semeados",
        "synonym_patterns_seeded": "parafrases suficientes por pergunta",
        "semantic_synonyms_understood": "sinonimos semanticos realmente compreendidos",
        "required_intents_understood": "perguntas basicas reconhecidas",
        "identity_paraphrases_invariant": "sinonimos de nome mantem identidade",
        "nonbasic_status_not_hijacked": "status nao e confundido com nome",
        "sleep_answer_grounded": "resposta de sono usa estado real",
        "state_grounding_recorded": "fontes de estado auditadas",
        "darwin_asks_questions": "Darwin faz perguntas de volta",
        "user_answers_understood": "respostas do Felipe compreendidas",
        "rzs_caused_delivery": "RZS registrado em cada resposta",
        "companion_delivery_path": "voz usa CompanionCore integrado",
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
