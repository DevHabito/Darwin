from __future__ import annotations

"""
DARWIN v49.29 - Diagnostico Child Story Nursery

Uso:
    py darwin_check_v49_29_child_story_nursery.py
    py darwin_check_v49_29_child_story_nursery.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SOURCE = "darwin_child_story_nursery_v49_29"

STORY_SESSIONS = "story_nursery_sessions_v49_29"
STORY_TEXTS = "story_texts_v49_29"
STORY_EXPOSURES = "story_exposures_v49_29"
STORY_REACTIONS = "story_reactions_v49_29"
STORY_REFLECTIONS = "story_reflections_v49_29"
STORY_REPLAY = "story_replay_v49_29"
STORY_HANDOFFS = "story_handoffs_v49_29"

REQUIRED_TABLES = [
    STORY_SESSIONS,
    STORY_TEXTS,
    STORY_EXPOSURES,
    STORY_REACTIONS,
    STORY_REFLECTIONS,
    STORY_REPLAY,
    STORY_HANDOFFS,
]


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
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        if "feature_json" in item:
            item["feature"] = pj(str(item.get("feature_json") or "{}"), {})
        if "safety_json" in item:
            item["safety"] = pj(str(item.get("safety_json") or "{}"), {})
        if "story_json" in item:
            item["story"] = pj(str(item.get("story_json") or "{}"), {})
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, STORY_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "session_complete" and r.get("payload", {}).get("session_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["session_id"]), row


def semantic_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "semantic_memory"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source=? AND key=?
        """,
        (SOURCE, f"story_nursery_v49_29:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module=? AND context=?
        """,
        (SOURCE, f"story_nursery:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def prior_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def storybook_safe(stories: list[dict[str, Any]]) -> bool:
    if len(stories) < 5:
        return False
    def number(item: dict[str, Any], key: str, fallback: float) -> float:
        value = item.get(key)
        return fallback if value is None else float(value)
    for story in stories:
        safety = story.get("safety", {})
        if int(story.get("child_safe") or 0) != 1:
            return False
        if bool(safety.get("external_source")):
            return False
        if number(story, "violence_score", 1.0) > 0.0:
            return False
        if number(story, "fear_score", 1.0) > 0.18:
            return False
        if number(story, "gentle_conflict_score", 1.0) > 0.30:
            return False
        if int(story.get("line_count") or 0) < 5:
            return False
    return True


def bounded_reactions(reactions: list[dict[str, Any]]) -> bool:
    fields = ["valence", "arousal", "comfort", "curiosity", "empathy", "stability"]
    for reaction in reactions:
        for field in fields:
            value = float(reaction.get(field) or -1.0)
            if value < 0.0 or value > 1.0:
                return False
        if float(reaction.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(reaction.get("sigma_after") or 0.0) <= 0.0:
            return False
        if not str(reaction.get("spoken_summary") or ""):
            return False
    return True


def rzs_causality_ok(reactions: list[dict[str, Any]]) -> bool:
    decisions = {str(r.get("rzs_decision")) for r in reactions if r.get("rzs_decision")}
    if len(decisions) < 2 or not any(d != "continue" for d in decisions):
        return False
    for reaction in reactions:
        decision = str(reaction.get("rzs_decision") or "")
        action = str(reaction.get("cognitive_action") or "")
        focus = str(reaction.get("attention_focus") or "")
        if decision == "continue" and action != "listen_with_warm_attention":
            return False
        if decision == "narrow_focus" and not action.startswith("focus_on_"):
            return False
        if decision == "replay_memory" and action != "replay_story_image":
            return False
        if decision == "consolidate" and action != "consolidate_story_feeling":
            return False
        if decision == "pause_for_stability" and action != "pause_story_for_calm":
            return False
        if decision == "narrow_focus" and not focus:
            return False
    return True


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    stories = rows(conn, STORY_TEXTS, session_id) if session_id else []
    exposures = rows(conn, STORY_EXPOSURES, session_id) if session_id else []
    reactions = rows(conn, STORY_REACTIONS, session_id) if session_id else []
    reflections = rows(conn, STORY_REFLECTIONS, session_id) if session_id else []
    replays = rows(conn, STORY_REPLAY, session_id) if session_id else []
    handoffs = rows(conn, STORY_HANDOFFS, session_id) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}

    story_ids = {str(s.get("story_id")) for s in stories}
    exposure_story_ids = {str(e.get("story_id")) for e in exposures}
    reaction_story_ids = {str(r.get("story_id")) for r in reactions}
    decisions = {str(r.get("rzs_decision")) for r in reactions if r.get("rzs_decision")}
    felt_states = {str(r.get("felt_state")) for r in reactions if r.get("felt_state")}
    focuses = {str(r.get("attention_focus")) for r in reactions if r.get("attention_focus")}
    source_kinds = {str(e.get("source_kind")) for e in exposures if e.get("source_kind")}
    handoff = handoffs[-1] if handoffs else {}
    protected_sources_unchanged = bool(payload.get("protected_sources_unchanged"))
    if not protected_sources_unchanged:
        before = payload.get("protected_counts_before", {})
        after = payload.get("protected_counts_after", {})
        protected_sources_unchanged = bool(before and before == after)

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in REQUIRED_TABLES),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "storybook_child_safe": storybook_safe(stories),
        "original_local_stories": bool(stories) and all(s.get("story", {}).get("original") is True for s in stories),
        "line_exposures_logged": len(exposures) >= 25 and source_kinds == {"original_child_story_line"} and story_ids.issubset(exposure_story_ids),
        "reactions_measured": len(reactions) >= len(exposures) and bounded_reactions(reactions),
        "affective_reaction_varied": len(felt_states) >= 3 and len(focuses) >= 3,
        "rzs_influenced_reaction": rzs_causality_ok(reactions),
        "reflections_written": len(reflections) >= len(story_ids) >= 5,
        "replay_logged": len(replays) >= 1 and "replay_memory" in {str(r.get("rzs_decision")) for r in replays},
        "handoff_written": bool(handoff) and int(handoff.get("story_reaction_ready") or 0) == 1 and int(handoff.get("child_safe_ready") or 0) == 1,
        "semantic_memory_written": semantic_count(conn, session_id) >= 1 if session_id else False,
        "episodes_written": episode_count(conn, session_id) >= len(story_ids) + 2 if session_id else False,
        "prior_data_still_present": prior_count(conn, "music_reactions_v49_16") > 0 and prior_count(conn, "self_model_statements_v49_27") > 0,
        "protected_sources_unchanged": protected_sources_unchanged,
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "stories": len(stories),
            "exposures": len(exposures),
            "reactions": len(reactions),
            "reflections": len(reflections),
            "replays": len(replays),
            "handoffs": len(handoffs),
            "semantic": semantic_count(conn, session_id) if session_id else 0,
            "episodes": episode_count(conn, session_id) if session_id else 0,
        },
        "story_ids": sorted(story_ids),
        "reaction_story_ids": sorted(reaction_story_ids),
        "decisions": sorted(decisions),
        "felt_states": sorted(felt_states),
        "focuses": sorted(focuses),
        "source_kinds": sorted(source_kinds),
        "handoff": {
            "next_action": handoff.get("next_action", ""),
            "story_reaction_ready": bool(int(handoff.get("story_reaction_ready") or 0)) if handoff else False,
            "child_safe_ready": bool(int(handoff.get("child_safe_ready") or 0)) if handoff else False,
            "confidence": float(handoff.get("confidence") or 0.0) if handoff else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.29 - DIAGNOSTICO CHILD STORY NURSERY")
    print("=" * 70)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- historias={c['stories']} exposicoes={c['exposures']} reacoes={c['reactions']} "
        f"reflexoes={c['reflections']} replays={c['replays']}"
    )
    print(f"- RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhum'}")
    print(f"- estados: {', '.join(report['felt_states']) if report['felt_states'] else 'nenhum'}")
    print(f"- focos: {', '.join(report['focuses']) if report['focuses'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.29 existem",
        "completed_session": "sessao completa encontrada",
        "storybook_child_safe": "historias infantis seguras",
        "original_local_stories": "historias originais locais",
        "line_exposures_logged": "exposicoes linha por linha registradas",
        "reactions_measured": "reacoes medidas",
        "affective_reaction_varied": "reacao afetiva variou",
        "rzs_influenced_reaction": "RZS influenciou reacao",
        "reflections_written": "reflexoes por historia escritas",
        "replay_logged": "replay narrativo registrado",
        "handoff_written": "handoff escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios escritos",
        "prior_data_still_present": "dados anteriores ainda presentes",
        "protected_sources_unchanged": "fontes anteriores preservadas",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin ouviu historias infantis seguras e reagiu com conforto, curiosidade, empatia e RZS.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o bercario de historias como marco completo.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.29 Child Story Nursery checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
