from __future__ import annotations

"""
DARWIN v49.8 - Diagnostico do Companion Shell

Uso:
    py darwin_check_v49_8_companion_shell.py
    py darwin_check_v49_8_companion_shell.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SESSIONS = "companion_sessions_v49_8"
DIALOGUES = "companion_dialogues_v49_8"
MEMORY_QUERIES = "companion_memory_queries_v49_8"
AFFECT = "companion_affect_state_v49_8"
VOICE = "companion_voice_events_v49_8"

REQUIRED_TABLES = [SESSIONS, DIALOGUES, MEMORY_QUERIES, AFFECT, VOICE]
REQUIRED_INTENTS = {"status", "geometry_memory", "rzs_explain", "companion_direction", "next_milestone"}


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
        if "memory_refs_json" in item:
            item["memory_refs"] = pj(str(item.get("memory_refs_json") or "[]"), [])
        if "tokens_json" in item:
            item["tokens"] = pj(str(item.get("tokens_json") or "[]"), [])
        if "protected_counts_before_json" in item:
            item["protected_before"] = pj(str(item.get("protected_counts_before_json") or "{}"))
        if "protected_counts_after_json" in item:
            item["protected_after"] = pj(str(item.get("protected_counts_after_json") or "{}"))
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, SESSIONS)
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
        WHERE source='darwin_companion_shell_v49_8'
          AND key=?
        """,
        (f"companion_v49_8:last_dialogue:{session_id}",),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episodes_written(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_companion_shell_v49_8'
          AND context LIKE ?
        """,
        (f"companion:{session_id}:%",),
    ).fetchone()
    return int(row["n"]) if row else 0


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, session_row = latest_completed_session(conn)
    dialogues = rows(conn, DIALOGUES, session_id) if session_id else []
    queries = rows(conn, MEMORY_QUERIES, session_id) if session_id else []
    affect = rows(conn, AFFECT, session_id) if session_id else []
    voice = rows(conn, VOICE, session_id) if session_id else []
    intents = {str(d.get("intent")) for d in dialogues if d.get("intent")}
    decisions = {str(d.get("rzs_decision")) for d in dialogues if d.get("rzs_decision")}
    style_rules = {str(d.get("style_rule")) for d in dialogues if d.get("style_rule")}
    actions = {str(d.get("cognitive_action")) for d in dialogues if d.get("cognitive_action")}
    geometry_queries = [q for q in queries if q.get("geometry_scenario_id")]
    memory_ref_count = sum(len(d.get("memory_refs") or []) for d in dialogues)
    geometry_payloads = [d.get("payload", {}).get("geometry", {}) for d in dialogues]
    geometry_nodes = max([int(g.get("nodes") or 0) for g in geometry_payloads] or [0])
    response_text = "\n".join(str(d.get("response_text") or "") for d in dialogues).lower()
    episode_n = episodes_written(conn, session_id) if session_id else 0
    session_payload = session_row.get("payload", {}) if session_row else {}

    checks = {
        "tables_exist": all(table_exists(conn, table) for table in REQUIRED_TABLES),
        "completed_session": bool(session_id),
        "dialogue_loop_ran": len(dialogues) >= 6,
        "intent_coverage": REQUIRED_INTENTS.issubset(intents),
        "memory_queries_logged": len(queries) >= len(dialogues) >= 1,
        "memory_grounding_present": memory_ref_count >= 3,
        "geometry_memory_read": bool(geometry_queries) and geometry_nodes >= 72,
        "rzs_decision_logged": len(decisions) >= 1 and all(float(d.get("sigma_before") or 0.0) > 0.0 for d in dialogues),
        "rzs_changes_style": len(style_rules) >= 2 and len(actions) >= 2,
        "affect_state_logged": len(affect) >= len(dialogues) and all(0.0 <= float(a.get("stability") or -1.0) <= 1.0 for a in affect),
        "voice_events_logged": len(voice) >= len(dialogues),
        "companion_direction_answered": "presenca" in response_text or "diana" in response_text,
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episodes_written": episode_n >= len(dialogues) >= 1,
        "protected_sources_unchanged": bool(session_payload.get("protected_sources_unchanged")),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "dialogues": len(dialogues),
            "queries": len(queries),
            "affect": len(affect),
            "voice": len(voice),
            "episodes": episode_n,
            "memory_refs": memory_ref_count,
            "geometry_nodes": geometry_nodes,
        },
        "intents": sorted(intents),
        "decisions": sorted(decisions),
        "style_rules": sorted(style_rules),
        "actions": sorted(actions),
        "session_payload": session_payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.8 - DIAGNOSTICO DO COMPANION SHELL")
    print("=" * 60)
    print(f"- sessao v49.8: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- dialogos={c['dialogues']} consultas={c['queries']} voz={c['voice']} "
        f"memorias={c['memory_refs']} episodios={c['episodes']}"
    )
    print(f"- nos geometricos lidos: {c['geometry_nodes']}")
    print(f"- intents: {', '.join(report['intents']) if report['intents'] else 'nenhum'}")
    print(f"- decisoes RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.8 existem",
        "completed_session": "sessao completa encontrada",
        "dialogue_loop_ran": "loop de dialogo rodou",
        "intent_coverage": "cobertura de intents essenciais",
        "memory_queries_logged": "consultas de memoria registradas",
        "memory_grounding_present": "respostas ancoradas em memoria",
        "geometry_memory_read": "memoria geometrica v49.7 lida",
        "rzs_decision_logged": "RZS registrado com sigma",
        "rzs_changes_style": "RZS mudou estilo/acao",
        "affect_state_logged": "estado afetivo operacional registrado",
        "voice_events_logged": "eventos de voz registrados",
        "companion_direction_answered": "direcao tipo companion respondida",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios de dialogo escritos",
        "protected_sources_unchanged": "fontes anteriores preservadas",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin agora tem uma presenca local que fala a partir de memoria, RZS e experiencia.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o companion shell como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.8 Companion Shell checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
